'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jose = require('jose');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-first-proxy-'));
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
 registrationSubmissionConfigured, handlePrincipalStatus, principalSubmissionConfigured, LOGIN_COOKIE, handleFirstCommand, firstSubmissionConfigured } = load('browser-auth');
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
const f=require('./fixtures/first-command.cjs');
const firstEnv={...env,FIRST_COMMAND_SUBMISSION_MODE:'enabled',FIRST_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL,FIRST_COMMAND_APPROVED_APP_ORIGIN:origin};
function firstRequest(session,body=f.command('actual'),options={}){return new Request(origin+'/auth/'+(options.recover?'first-command-receipt':'first-command'),{method:options.method||'POST',headers:{Origin:options.origin||origin,'Sec-Fetch-Site':options.site||'same-origin','Content-Type':options.contentType||'application/json',...(session?{Cookie:session}:{}),...options.headers},...(options.method==='GET'?{}:{body:options.raw===undefined?JSON.stringify(body):options.raw})});}
async function writeFixture(options={}){const flow=await start(),login=await complete(flow,{identity:{...identity,read_only_mode:false},...options});return {flow,login,session:cookie(login.response,SESSION_COOKIE)};}
test('first-command independent gate requires explicit exact approved bindings and POST on both routes',async()=>{
 const config=await authConfig(env);assert.equal(firstSubmissionConfigured(firstEnv,config),true);assert.equal(firstSubmissionConfigured(firstEnv,null),false);
 let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const mode of ['submit','recover']){
  for(const patch of [{FIRST_COMMAND_SUBMISSION_MODE:undefined},{FIRST_COMMAND_SUBMISSION_MODE:'disabled'},
   {FIRST_COMMAND_SUBMISSION_MODE:'true'},{FIRST_COMMAND_APPROVED_API_BASE_URL:undefined},
   {FIRST_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL+'/'},{FIRST_COMMAND_APPROVED_APP_ORIGIN:'https://other.test'},
   {BROWSER_OIDC_MODE:'disabled'},{BROWSER_SESSION_KEY:'invalid'}]){
   const response=await handleFirstCommand(firstRequest(),{...firstEnv,...patch},mode,never);
   assert.equal(response.status,503);privateResponse(response);assert.deepEqual(await response.json(),{error:'first_submission_disabled'});
  }
  const existing={...env,PRINCIPAL_STATUS_SUBMISSION_MODE:'enabled',ADMIN_REGISTRATION_SUBMISSION_MODE:'enabled',NEXT_PUBLIC_FIRST_COMMAND_SUBMISSION_MODE:'enabled'};
  assert.equal((await handleFirstCommand(firstRequest(),existing,mode,never)).status,503);
  const get=await handleFirstCommand(firstRequest(null,null,{method:'GET'}),firstEnv,mode,never);
  assert.equal(get.status,405);assert.equal(get.headers.get('allow'),'POST');
 }
 assert.equal(calls,0);
});
test('first-command origin/media/body bounds and extra fields fail before network',async()=>{
 let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const mode of ['submit','recover']){
  for(const options of [{origin:'https://evil.test'},{site:'same-site'},{site:'cross-site'}])
   assert.equal((await handleFirstCommand(firstRequest(null,f.command('actual'),options),firstEnv,mode,never)).status,403);
  assert.equal((await handleFirstCommand(firstRequest(null,null,{contentType:'text/plain'}),firstEnv,mode,never)).status,415);
  for(const options of [{raw:'x'.repeat(8193)},{headers:{'Content-Length':'8193'}}])
   assert.equal((await handleFirstCommand(firstRequest(null,null,options),firstEnv,mode,never)).status,413);
  for(const body of [null,[],{...f.command('actual'),url:'https://evil'},
   {...f.command('actual'),body:{...f.command('actual').body,actor:id}},
   {...f.command('actual'),operation:'approval'},{...f.command('actual'),target:'../evil'}])
   assert.equal((await handleFirstCommand(firstRequest(null,body),firstEnv,mode,never)).status,400);
  const invalid=new Request(origin+'/auth/first-command',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:new Uint8Array([255])});
  assert.equal((await handleFirstCommand(invalid,firstEnv,mode,never)).status,400);
 }
 assert.equal(calls,0);
});
test('unique current token-bound session is required; revoked or service identities cannot post',async()=>{
 const w=await writeFixture();let writes=0;
 const mock=async(url,init)=>{if(init.method==='POST'){writes++;throw Error('unexpected');}return w.login.fetcher(url,init);};
 for(const mode of ['submit','recover'])for(const session of [undefined,w.session+'; '+w.session,SESSION_COOKIE+'=invalid'])
  assert.equal((await handleFirstCommand(firstRequest(session),firstEnv,mode,mock)).status,401);
 for(const principal of [{...identity.principal,principal_type:'SERVICE'},{...identity.principal,id:f.key}]){
  const response=await handleFirstCommand(firstRequest(w.session),firstEnv,'submit',async(url,init)=>{
   if(init.method==='POST'){writes++;throw Error('unexpected');}
   return Response.json({...identity,principal,read_only_mode:false,browser_session_id:init.headers['X-Browser-Session']});
  });assert.equal(response.status,401);
 }
 for(const row of w.flow.registry.values())row.revoked=true;
 assert.equal((await handleFirstCommand(firstRequest(w.session),firstEnv,'submit',mock)).status,401);assert.equal(writes,0);
});
test('read-only identity denies business write but may recover its own committed audit without a write',async()=>{
 const w=await writeFixture({identity}),c=f.command('actual');let writes=0,reads=0;
 const mock=async(url,init)=>{
  if(url.includes('/activity/')){reads++;return Response.json(f.audit(c,id));}
  if(init.method==='POST'){writes++;throw Error('unexpected');}return w.login.fetcher(url,init);
 };
 const denied=await handleFirstCommand(firstRequest(w.session,c),firstEnv,'submit',mock);
 assert.equal(denied.status,403);assert.deepEqual(await denied.json(),{error:'read_only_mode'});
 const recovered=await handleFirstCommand(firstRequest(w.session,c,{recover:true}),firstEnv,'recover',mock);
 assert.equal(recovered.status,200);assert.deepEqual(await recovered.json(),f.receipt(c));assert.equal(writes,0);assert.equal(reads,1);
});
for(const operation of ['snapshot','actual','batch'])test('fixed '+operation+' POST then exact atomic audit, credentials remain server-only',async()=>{
 const w=await writeFixture(),c=f.command(operation),calls=[];
 const mock=async(url,init)=>{
  if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
  calls.push({url,method:init.method});assert.equal(init.headers.Authorization,'Bearer '+w.login.access);
  assert.ok(init.headers['X-Browser-Session']);assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
  if(init.method==='POST'){
   const path=operation==='snapshot'?'/api/v1/releases/'+c.target+'/create-snapshot':
    '/api/v1/deployments/'+encodeURIComponent(c.target)+(operation==='actual'?'/actual':'/batches');
   assert.equal(url,env.API_BASE_URL+path);assert.deepEqual(JSON.parse(init.body),c.body);
   return Response.json({status:'CURRENT',token:'private'},{status:operation==='actual'?200:201});
  }
  assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));return Response.json(f.audit(c,id));
 };
 const response=await handleFirstCommand(firstRequest(w.session,c),firstEnv,'submit',mock);
 assert.equal(response.status,200);privateResponse(response);assert.deepEqual(await response.json(),f.receipt(c));
 assert.equal(calls.length,2);assert.equal(calls[0].method,'POST');assert.equal(calls[1].method,undefined);
});
for(const operation of ['snapshot','actual','batch'])test('explicit '+operation+' recovery only GETs original audit and never resubmits',async()=>{
 const w=await writeFixture(),c=f.command(operation);let writes=0,reads=0;
 const response=await handleFirstCommand(firstRequest(w.session,c,{recover:true}),firstEnv,'recover',async(url,init)=>{
  if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
  if(init.method==='POST')writes++;reads++;assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));
  return Response.json(f.audit(c,id));
 });
 assert.equal(response.status,200);assert.deepEqual(await response.json(),f.receipt(c));assert.equal(writes,0);assert.equal(reads,1);
});
test('backend scope/version/key conflicts map to fixed labels and never disclose arbitrary detail',async()=>{
 const w=await writeFixture();
 for(const [status,detail,error] of [[401,'private','session_required'],[403,'private','submission_forbidden'],[422,'private','invalid_request'],
  [409,'request_id already used for different or legacy content','request_conflict'],
  [409,'actual_version conflict: expected 4, current 6','version_conflict'],[409,'private','submission_conflict']]){
  const response=await handleFirstCommand(firstRequest(w.session),firstEnv,'submit',async(url,init)=>
   init.method==='POST'?Response.json({detail,token:'private'},{status}):w.login.fetcher(url,init));
  assert.equal(response.status,status);privateResponse(response);assert.deepEqual(await response.json(),{error});
 }
});
test('unknown/lost POST is not retried or replaced with current-object observation',async()=>{
 const w=await writeFixture();
 for(const reply of [()=>{throw Error('lost after commit');},()=>Response.json({detail:'Not Found'},{status:404}),
  ()=>Response.json({detail:'private'},{status:500}),()=>Response.json({},{status:302}),()=>Response.json({},{status:503}),
  ()=>new Response('private'),()=>Response.json({padding:'x'.repeat(16385)}),
  ()=>Response.json({},{headers:{'Content-Length':'16385'}})]){
  let writes=0,reads=0;const response=await handleFirstCommand(firstRequest(w.session),firstEnv,'submit',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   if(init.method==='POST'){writes++;return reply();}reads++;throw Error('unexpected extra read');
  });
  assert.equal(response.status,502);assert.deepEqual(await response.json(),{error:'outcome_unknown'});assert.equal(writes,1);assert.equal(reads,0);
 }
});
test('successful HTTP without matching own atomic audit still remains unknown',async()=>{
 const w=await writeFixture(),c=f.command('actual'),good=f.audit(c,id);
 for(const audit of [{...good,actor_principal_id:f.key},{...good,event_no:'WRONG'},
  {...good,payload:{...good.payload,request:{...good.payload.request,correction_reason:'Changed'}}},
  {...good,payload:{...good.payload,after:{...good.payload.after,actual_version:9}}}]){
  const response=await handleFirstCommand(firstRequest(w.session,c),firstEnv,'submit',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   return init.method==='POST'?Response.json({actual_version:5}):Response.json(audit);
  });assert.equal(response.status,502);assert.deepEqual(await response.json(),{error:'outcome_unknown'});
 }
});
test('missing, unsupported, denied, malformed, oversized or interrupted audit never proves absence',async()=>{
 const w=await writeFixture(),c=f.command('batch');
 for(const reply of [()=>Response.json({detail:'audit event not found'},{status:404}),()=>Response.json({detail:'private'},{status:403}),
  ()=>new Response('{',{headers:{'Content-Type':'application/json'}}),()=>Response.json({...f.audit(c,id),padding:'x'.repeat(16385)}),
  ()=>Response.json(f.audit(c,id),{headers:{'Content-Length':'16385'}}),
  ()=>new Response(new ReadableStream({start(controller){controller.error(Error('interrupted'));}}),{headers:{'Content-Type':'application/json'}})]){
  let writes=0;const response=await handleFirstCommand(firstRequest(w.session,c,{recover:true}),firstEnv,'recover',async(url,init)=>{
   if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
   if(init.method==='POST')writes++;return reply();
  });assert.equal(response.status,502);privateResponse(response);assert.deepEqual(await response.json(),{error:'outcome_unknown'});assert.equal(writes,0);
 }
});
test('lost write then explicit recovery keeps original key/body and later applied state',async()=>{
 const w=await writeFixture(),c=f.command('actual'),bodies=[];let writes=0;
 const mock=async(url,init)=>{
  if(url===env.API_BASE_URL+'/api/v1/security/me')return w.login.fetcher(url,init);
  if(init.method==='POST'){writes++;bodies.push(init.body);throw Error('lost after commit');}
  return Response.json({...f.audit(c,id),current_version:9,current_status:'MATCH'});
 };
 const first=await handleFirstCommand(firstRequest(w.session,c),firstEnv,'submit',mock);assert.equal(first.status,502);
 const recovered=await handleFirstCommand(firstRequest(w.session,c,{recover:true}),firstEnv,'recover',mock);
 assert.equal(recovered.status,200);const receipt=await recovered.json();assert.equal(receipt.result.actual_version,5);
 assert.equal(receipt.result.status,'MISMATCH');assert.equal(writes,1);assert.equal(bodies[0],JSON.stringify(c.body));
});
test('direct server helper validates operation, target, extra fields and mode before any network',async()=>{
 const {executeFirstCommand}=load('browser-session'),config=await authConfig(env);let calls=0;
 for(const input of [{...f.command('actual'),target:'../evil'},{...f.command('actual'),url:'https://evil'},
  {...f.command('actual'),operation:'approval'},
  {...f.command('batch'),body:{...f.command('batch').body,note:'😀'.repeat(2200)}}]){
  const result=await executeFirstCommand(config.session,undefined,input,'submit',async()=>{calls++;});assert.equal(result.status,400);
 }
 const badMode=await executeFirstCommand(config.session,undefined,f.command('actual'),'wrong',async()=>{calls++;});
 assert.equal(badMode.status,400);assert.equal(calls,0);
});

