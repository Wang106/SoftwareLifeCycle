'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jose = require('jose');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-distribution-proxy-'));
require('node:child_process').execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'),
  'lib/browser-auth.ts', '--target', 'ES2021', '--module', 'commonjs', '--strict', '--skipLibCheck', '--outDir', output]);
const modules = new Map();
function load(file) {
  if (modules.has(file)) return modules.get(file);
  const exports = {}; modules.set(file, exports);
  vm.runInNewContext(fs.readFileSync(path.join(output, file+'.js'), 'utf8'), {
    exports, require: name => name === 'server-only' ? {} : name === 'jose' ? jose : load(name.replace('./','')),
    crypto:globalThis.crypto, TextEncoder, TextDecoder, Uint8Array, btoa, atob, AbortSignal, fetch, URL, URLSearchParams, Request, Response,
  });
  return exports;
}
const { handleAuth, handleGrantStatus, handleAdminRegistration, authConfig, grantSubmissionConfigured,
 registrationSubmissionConfigured, handlePrincipalStatus, principalSubmissionConfigured, LOGIN_COOKIE, handleFirstCommand, firstSubmissionConfigured, handleDistributionCommand, distributionSubmissionConfigured } = load('browser-auth');
const { SESSION_COOKIE, openCookie, sealCookie } = load('browser-session');
after(() => fs.rmSync(output, { recursive:true, force:true }));
const origin = 'https://app.example.test';
const env = { BROWSER_OIDC_MODE:'code', BROWSER_SESSION_MODE:'encrypted',
  BROWSER_SESSION_KEY:Buffer.alloc(32,9).toString('base64url'), BROWSER_SESSION_ORIGIN:origin, API_BASE_URL:'https://api.example.test',
  OIDC_ISSUER_URL:'https://id.example.test/', OIDC_AUDIENCE:'software-api', OIDC_CLIENT_ID:'software-web',
  OIDC_AUTHORIZATION_URL:'https://id.example.test/authorize', OIDC_TOKEN_URL:'https://id.example.test/token', OIDC_JWKS_URL:'https://id.example.test/jwks' };
const id = '12345678-1234-1234-1234-123456789abc';
// Match the actual backend response/model contract, including its USER discriminator.
const identity = { principal:{id,principal_type:'USER',display_name:'评审人 / Reviewer'}, read_only_mode:true,
  active_grant_counts:{GLOBAL:0,PROJECT:1,SOFTWARE:2} };
const keysPromise = (async()=>{
 const keys = await jose.generateKeyPair('RS256');
 const jwk = await jose.exportJWK(keys.publicKey); return {...keys,jwk:{...jwk,kid:'provider-key',alg:'RS256',use:'sig'}};
})();
function request(operation, {method, cookie, query='', requestOrigin=origin, headerOrigin=origin, site='same-origin'}={}) {
 const headers = {Origin:headerOrigin,'Sec-Fetch-Site':site}; if(cookie) headers.Cookie=cookie;
 return new Request(`${requestOrigin}/auth/${operation}${query}`, {method:method||(operation==='login'||operation==='logout'?'POST':'GET'),headers});
}
function cookieLines(response) { return response.headers.getSetCookie(); }
function cookie(response, name) { return cookieLines(response).find(line=>line.startsWith(name+'='))?.split(';')[0]; }
function privateResponse(response) {
 assert.equal(response.headers.get('cache-control'),'private, no-store');assert.equal(response.headers.get('pragma'),'no-cache');
 assert.equal(response.headers.get('vary'),'Cookie');assert.equal(response.headers.get('referrer-policy'),'no-referrer');
}
async function start(environment=env) {
 const response=await handleAuth(request('login'),'login',environment);privateResponse(response);assert.equal(response.status,303);
 const authorization=new URL(response.headers.get('location'));
 return {response,authorization,pending:cookie(response,LOGIN_COOKIE),environment,registry:new Map()};
}
async function mockProvider(flow, options={}) {
 const keys=await keysPromise,now=Math.floor(Date.now()/1000);
 const claims={iss:env.OIDC_ISSUER_URL,sub:'operator-123',iat:now,exp:now+300};
 const accessClaims={...claims,aud:env.OIDC_AUDIENCE,...options.access};
 const idClaims={...claims,aud:env.OIDC_CLIENT_ID,nonce:flow.authorization.searchParams.get('nonce'),...options.id};
 const sign=(payload,key=keys.privateKey,header={alg:'RS256',kid:'provider-key'})=>new jose.SignJWT(payload).setProtectedHeader(header).sign(key);
 const access=options.accessToken||await sign(accessClaims,options.accessKey);
 const idToken=options.idToken||await sign(idClaims,options.idKey);
 const calls=[];
 const fetcher=async(url,init)=>{
  calls.push(url);assert.equal(init.redirect,'error');assert.equal(init.cache,'no-store');assert.ok(init.signal);
  if(url===env.OIDC_TOKEN_URL){
   assert.equal(init.method,'POST');const body=new URLSearchParams(init.body);
   assert.equal(body.get('code'),'provider-code');assert.equal(body.get('grant_type'),'authorization_code');
   assert.equal(body.get('redirect_uri'),origin+'/auth/callback');assert.equal(body.get('client_id'),env.OIDC_CLIENT_ID);
   const verifier=body.get('code_verifier');assert.match(verifier,/^[A-Za-z0-9_-]{43}$/);
   const challenge=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))).toString('base64url');
   assert.equal(challenge,flow.authorization.searchParams.get('code_challenge'));
   if(options.onExchange)options.onExchange(init);
   if(options.tokenResponse)return options.tokenResponse();
   return Response.json({access_token:access,id_token:idToken,token_type:'Bearer',expires_in:300,refresh_token:'must-not-be-retained',...options.tokens});
  }
  if(url===env.OIDC_JWKS_URL)return options.jwksResponse?options.jwksResponse():Response.json({keys:[keys.jwk]});
  if(url===env.API_BASE_URL+'/api/v1/security/me/browser-sessions'){
   assert.equal(init.method,'POST');assert.equal(init.headers.Authorization,`Bearer ${access}`);const body=JSON.parse(init.body);
   flow.registry.set(body.id,{...body,revoked:false});return Response.json({id:body.id,expires_at:body.expires_at});
  }
  if(url.startsWith(env.API_BASE_URL+'/api/v1/security/me/browser-sessions/')&&url.endsWith('/revoke')){
   const sid=url.split('/').at(-2),row=flow.registry.get(sid);if(!row)return Response.json({detail:'session_not_found'},{status:404});row.revoked=true;return Response.json({id:sid,status:'revoked'});
  }
  if(url===env.API_BASE_URL+'/api/v1/security/me'){
   assert.equal(init.headers.Authorization,`Bearer ${access}`);
   const sid=init.headers['X-Browser-Session'];if(sid&&(!flow.registry.has(sid)||flow.registry.get(sid).revoked))return Response.json({detail:'invalid_browser_session'},{status:401});
   return Response.json({...options.identity||identity,...(sid?{browser_session_id:sid}:{})},{status:options.identityStatus||200});
  }
  throw new Error('unexpected outbound URL: '+url);
 };
 return {fetcher,calls,access,idToken};
}
function callback(flow,query) { return request('callback',{cookie:flow.pending,query:query||'?'+new URLSearchParams({code:'provider-code',state:flow.authorization.searchParams.get('state'),iss:env.OIDC_ISSUER_URL})}); }
async function complete(flow,options={}) {
 const provider=await mockProvider(flow,options);
 const response=await handleAuth(callback(flow),'callback',flow.environment,provider.fetcher);privateResponse(response);
 return {...provider,response};
}

const f=require('./fixtures/distribution-command.cjs');
const distributionEnv={...env,DISTRIBUTION_COMMAND_SUBMISSION_MODE:'enabled',DISTRIBUTION_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL,DISTRIBUTION_COMMAND_APPROVED_APP_ORIGIN:origin};
function commandRequest(session,body=f.command('delivery'),options={}){return new Request(origin+'/auth/'+(options.recover?'distribution-command-receipt':'distribution-command'),{method:options.method||'POST',headers:{Origin:options.origin||origin,'Sec-Fetch-Site':options.site||'same-origin','Content-Type':options.contentType||'application/json',...(session?{Cookie:session}:{}),...options.headers},...(options.method==='GET'?{}:{body:options.raw===undefined?JSON.stringify(body):options.raw})});}
async function writeFixture(options={}){const flow=await start(),login=await complete(flow,{identity:{...identity,read_only_mode:false},...options});return{flow,login,session:cookie(login.response,SESSION_COOKIE)};}
test('independent distribution gate requires explicit approved bindings and POST on both routes',async()=>{
 const config=await authConfig(env);assert.equal(distributionSubmissionConfigured(distributionEnv,config),true);assert.equal(distributionSubmissionConfigured(distributionEnv,null),false);
 let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const mode of ['submit','recover']){
  for(const patch of [{DISTRIBUTION_COMMAND_SUBMISSION_MODE:undefined},{DISTRIBUTION_COMMAND_SUBMISSION_MODE:'disabled'},
   {DISTRIBUTION_COMMAND_SUBMISSION_MODE:'true'},{DISTRIBUTION_COMMAND_APPROVED_API_BASE_URL:undefined},
   {DISTRIBUTION_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL+'/'},{DISTRIBUTION_COMMAND_APPROVED_APP_ORIGIN:'https://other.test'},
   {BROWSER_OIDC_MODE:'disabled'},{BROWSER_SESSION_KEY:'invalid'}]){
   const response=await handleDistributionCommand(commandRequest(),{...distributionEnv,...patch},mode,never);
   assert.equal(response.status,503);privateResponse(response);assert.deepEqual(await response.json(),{error:'distribution_submission_disabled'});
  }
  const existing={...env,FIRST_COMMAND_SUBMISSION_MODE:'enabled',FIRST_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL,FIRST_COMMAND_APPROVED_APP_ORIGIN:origin,
   GOVERNANCE_COMMAND_SUBMISSION_MODE:'enabled',GOVERNANCE_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL,GOVERNANCE_COMMAND_APPROVED_APP_ORIGIN:origin,
   PRINCIPAL_STATUS_SUBMISSION_MODE:'enabled',ADMIN_REGISTRATION_SUBMISSION_MODE:'enabled',NEXT_PUBLIC_DISTRIBUTION_COMMAND_SUBMISSION_MODE:'enabled'};
  assert.equal((await handleDistributionCommand(commandRequest(),existing,mode,never)).status,503);
  const get=await handleDistributionCommand(commandRequest(null,null,{method:'GET'}),distributionEnv,mode,never);assert.equal(get.status,405);assert.equal(get.headers.get('allow'),'POST');
 }
 assert.equal(calls,0);
});
test('origin/media/declared and streaming body bounds/extra fields reject before network',async()=>{
 let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const mode of ['submit','recover']){
  for(const options of [{origin:'https://evil.test'},{site:'same-site'},{site:'cross-site'}])assert.equal((await handleDistributionCommand(commandRequest(null,f.command('delivery'),options),distributionEnv,mode,never)).status,403);
  assert.equal((await handleDistributionCommand(commandRequest(null,null,{contentType:'text/plain'}),distributionEnv,mode,never)).status,415);
  for(const options of [{raw:'x'.repeat(8193)},{headers:{'Content-Length':'8193'}}])assert.equal((await handleDistributionCommand(commandRequest(null,null,options),distributionEnv,mode,never)).status,413);
  for(const body of [null,[],{...f.command('delivery'),url:'https://evil'},
   {...f.command('delivery'),body:{...f.command('delivery').body,token:'private'}},
   {...f.command('delivery'),operation:'actual'},{...f.command('delivery'),target:'../evil'}])assert.equal((await handleDistributionCommand(commandRequest(null,body),distributionEnv,mode,never)).status,400);
  const invalid=new Request(origin+'/auth/distribution-command',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:new Uint8Array([255])});
  assert.equal((await handleDistributionCommand(invalid,distributionEnv,mode,never)).status,400);
 }
 assert.equal(calls,0);
});
test('unique current token-bound USER session rejects missing/duplicate/revoked/service credentials',async()=>{
 const w=await writeFixture();let writes=0;const mock=async(url,init)=>{if(init.method==='POST'){writes++;throw Error('unexpected');}return w.login.fetcher(url,init);};
 for(const mode of ['submit','recover'])for(const session of [undefined,w.session+'; '+w.session,SESSION_COOKIE+'=invalid'])assert.equal((await handleDistributionCommand(commandRequest(session),distributionEnv,mode,mock)).status,401);
 for(const principal of [{...identity.principal,principal_type:'SERVICE'},{...identity.principal,id:f.key}]){
  const response=await handleDistributionCommand(commandRequest(w.session),distributionEnv,'submit',async(url,init)=>{
   if(init.method==='POST'){writes++;throw Error('unexpected');}return Response.json({...identity,principal,read_only_mode:false,browser_session_id:init.headers['X-Browser-Session']});});assert.equal(response.status,401);
 }
 for(const row of w.flow.registry.values())row.revoked=true;assert.equal((await handleDistributionCommand(commandRequest(w.session),distributionEnv,'submit',mock)).status,401);assert.equal(writes,0);
});
test('read-only identity denies writes but explicitly recovers its own original audit',async()=>{
 const w=await writeFixture({identity}),c=f.command('delivery');let writes=0,reads=0;
 const mock=async(url,init)=>{if(url.includes('/activity/')){reads++;return Response.json(f.audit(c,id));}if(init.method==='POST'){writes++;throw Error('unexpected');}return w.login.fetcher(url,init);};
 const denied=await handleDistributionCommand(commandRequest(w.session,c),distributionEnv,'submit',mock);assert.equal(denied.status,403);assert.deepEqual(await denied.json(),{error:'read_only_mode'});
 const recovered=await handleDistributionCommand(commandRequest(w.session,c,{recover:true}),distributionEnv,'recover',mock);assert.equal(recovered.status,200);assert.deepEqual(await recovered.json(),f.receipt(c));assert.equal(writes,0);assert.equal(reads,1);
});

for(const operation of ['delivery','distribution','authorization']){
 test('fixed '+operation+' POST binds original body and own atomic audit without exposing credentials',async()=>{
  const w=await writeFixture(),c=f.command(operation),calls=[],path='/api/v1/'+(operation==='delivery'?'deliveries':operation==='distribution'?'distributions':'authorizations');
  const mock=async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   calls.push({url,method:init.method});assert.equal(init.headers.Authorization,'Bearer '+w.login.access);assert.ok(init.headers['X-Browser-Session']);
   assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
   if(init.method==='POST'){assert.equal(url,env.API_BASE_URL+path);assert.deepEqual(JSON.parse(init.body),c.body);
    return Response.json({status:'CURRENT',token:'private'},{status:201});}
   assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));return Response.json(f.audit(c,id));
  };
  const response=await handleDistributionCommand(commandRequest(w.session,c),distributionEnv,'submit',mock);
  assert.equal(response.status,200);privateResponse(response);assert.deepEqual(await response.json(),f.receipt(c));
  assert.equal(calls.length,2);assert.equal(calls[0].method,'POST');assert.equal(calls[1].method,undefined);
 });
 test('explicit '+operation+' recovery only GETs original audit even in read-only mode',async()=>{
  const w=await writeFixture({identity}),c=f.command(operation);let writes=0,reads=0;
  const response=await handleDistributionCommand(commandRequest(w.session,c,{recover:true}),distributionEnv,'recover',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   if(init.method==='POST')writes++;reads++;assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));return Response.json(f.audit(c,id));
  });
  assert.equal(response.status,200);assert.deepEqual(await response.json(),f.receipt(c));assert.equal(writes,0);assert.equal(reads,1);
 });
}
test('backend idempotency, business and scope conflicts produce fixed errors without leaking backend detail',async()=>{
 const w=await writeFixture();
 for(const [status,detail,error]of [[401,'private','session_required'],[403,'private','submission_forbidden'],[422,'private','invalid_request'],
  [409,'request_id already used for different or legacy content','request_conflict'],[409,'request_id or business number already exists','request_conflict'],
  [409,'Delivery package number and revision already exist','submission_conflict'],[409,'private','submission_conflict']]){
  const response=await handleDistributionCommand(commandRequest(w.session),distributionEnv,'submit',async(url,init)=>
   init.method==='POST'?Response.json({detail,token:'private'},{status}):w.login.fetcher(url,init));
  assert.equal(response.status,status);privateResponse(response);assert.deepEqual(await response.json(),{error});
 }
});
test('lost, wrong-status, oversized or unknown POST does not repeat writes or query current detail',async()=>{
 const w=await writeFixture();
 for(const operation of ['delivery','distribution','authorization'])for(const reply of [()=>{throw Error('lost');},
  ()=>Response.json({detail:'private'},{status:404}),()=>Response.json({detail:'private'},{status:500}),()=>Response.json({},{status:302}),
  ()=>Response.json({},{status:503}),()=>Response.json({},{status:200}),()=>new Response('private'),
  ()=>Response.json({padding:'x'.repeat(16385)}),()=>Response.json({},{headers:{'Content-Length':'16385'}})]){
  let writes=0,reads=0;
  const response=await handleDistributionCommand(commandRequest(w.session,f.command(operation)),distributionEnv,'submit',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   if(init.method==='POST'){writes++;return reply();}reads++;throw Error('unexpected read');
  });
  assert.equal(response.status,502);assert.deepEqual(await response.json(),{error:'outcome_unknown'});assert.equal(writes,1);assert.equal(reads,0);
 }
});
test('201 still requires exact actor, fingerprint, revision, recipient and original scope audit',async()=>{
 const w=await writeFixture();
 for(const operation of ['delivery','distribution','authorization']){
  const c=f.command(operation),good=f.audit(c,id);
  for(const mutate of [e=>e.actor_principal_id=f.key,e=>e.event_no='WRONG',e=>e.payload.request.token='private',
   e=>e.payload.request[Object.keys(e.payload.request)[0]]='CHANGED',e=>e.payload.revision=0,e=>e.payload.status='APPROVED',
   e=>{if(operation==='delivery')e.payload.snapshot_artifact_ids=[f.release];
     else if(operation==='distribution')e.payload.recipient_code='OTHER';else e.payload.site_code='OTHER';}]){
   const audit=JSON.parse(JSON.stringify(good));mutate(audit);
   const response=await handleDistributionCommand(commandRequest(w.session,c),distributionEnv,'submit',async(url,init)=>{
    if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
    return init.method==='POST'?Response.json({},{status:201}):Response.json(audit);
   });
   assert.equal(response.status,502);assert.deepEqual(await response.json(),{error:'outcome_unknown'});
  }
 }
});
test('missing, denied, invalid, oversized or interrupted audit stays unknown with no business POST',async()=>{
 const w=await writeFixture(),c=f.command('authorization');
 for(const reply of [()=>Response.json({detail:'not found'},{status:404}),()=>Response.json({detail:'private'},{status:403}),
  ()=>new Response('{',{headers:{'Content-Type':'application/json'}}),()=>Response.json({...f.audit(c,id),padding:'x'.repeat(16385)}),
  ()=>Response.json(f.audit(c,id),{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new Uint8Array([255]),{headers:{'Content-Type':'application/json'}}),
  ()=>new Response(new ReadableStream({start(c){c.error(Error('interrupted'));}}),{headers:{'Content-Type':'application/json'}})]){
  let writes=0;
  const response=await handleDistributionCommand(commandRequest(w.session,c,{recover:true}),distributionEnv,'recover',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);if(init.method==='POST')writes++;return reply();
  });
  assert.equal(response.status,502);privateResponse(response);assert.deepEqual(await response.json(),{error:'outcome_unknown'});assert.equal(writes,0);
 }
});
test('lost original write then audit query preserves READY/DRAFT despite later status changes',async()=>{
 const w=await writeFixture();
 for(const operation of ['delivery','distribution','authorization']){
  const c=f.command(operation);let writes=0,body;
  const mock=async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   if(init.method==='POST'){writes++;body=init.body;throw Error('lost after commit');}
   return Response.json({...f.audit(c,id),current_status:operation==='authorization'?'APPROVED':'SENT'});
  };
  assert.equal((await handleDistributionCommand(commandRequest(w.session,c),distributionEnv,'submit',mock)).status,502);
  const recovered=await handleDistributionCommand(commandRequest(w.session,c,{recover:true}),distributionEnv,'recover',mock);
  assert.equal(recovered.status,200);assert.equal((await recovered.json()).result.status,operation==='authorization'?'DRAFT':'READY');
  assert.equal(writes,1);assert.equal(body,JSON.stringify(c.body));
 }
});
test('server helper rejects invalid mode, operations, credential injection and mismatched target before network',async()=>{
 const {executeDistributionCommand}=load('browser-session'),config=await authConfig(env);let calls=0;
 for(const input of [{...f.command('delivery'),target:f.key},{...f.command('delivery'),url:'https://evil'},
  {...f.command('delivery'),operation:'approval'},{...f.command('authorization'),body:{...f.command('authorization').body,restriction_note:'😀'.repeat(2200)}}]){
  assert.equal((await executeDistributionCommand(config.session,undefined,input,'submit',async()=>{calls++;})).status,400);
 }
 assert.equal((await executeDistributionCommand(config.session,undefined,f.command('delivery'),'wrong',async()=>{calls++;})).status,400);assert.equal(calls,0);
});
