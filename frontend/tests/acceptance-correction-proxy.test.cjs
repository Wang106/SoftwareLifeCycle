'use strict';

const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jose = require('jose');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-correction-proxy-'));
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
 registrationSubmissionConfigured, handlePrincipalStatus, principalSubmissionConfigured, LOGIN_COOKIE, handleFirstCommand, firstSubmissionConfigured, handleAcceptanceCorrection, acceptanceCorrectionSubmissionConfigured } = load('browser-auth');
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

const f=require('./fixtures/acceptance-correction.cjs');
const correctionEnv={...env,ACCEPTANCE_CORRECTION_SUBMISSION_MODE:'enabled',ACCEPTANCE_CORRECTION_APPROVED_API_BASE_URL:env.API_BASE_URL,ACCEPTANCE_CORRECTION_APPROVED_APP_ORIGIN:origin};
function commandRequest(session,body=f.command(),options={}){return new Request(origin+'/auth/'+(options.recover?'acceptance-correction-receipt':'acceptance-correction'),{method:options.method||'POST',headers:{Origin:options.origin||origin,'Sec-Fetch-Site':options.site||'same-origin','Content-Type':options.contentType||'application/json',...(session?{Cookie:session}:{}),...options.headers},...(options.method==='GET'?{}:{body:options.raw===undefined?JSON.stringify(body):options.raw})});}
async function writeFixture(options={}){const flow=await start(),login=await complete(flow,{identity:{...identity,read_only_mode:false},...options});return{flow,login,session:cookie(login.response,SESSION_COOKIE)};}
test('correction gate requires exact independent approved API/app configuration on both routes',async()=>{const config=await authConfig(env);assert.equal(acceptanceCorrectionSubmissionConfigured(correctionEnv,config),true);assert.equal(acceptanceCorrectionSubmissionConfigured(correctionEnv,null),false);let calls=0;for(const mode of ['submit','recover']){for(const patch of [{ACCEPTANCE_CORRECTION_SUBMISSION_MODE:undefined},{ACCEPTANCE_CORRECTION_SUBMISSION_MODE:'true'},{ACCEPTANCE_CORRECTION_APPROVED_API_BASE_URL:env.API_BASE_URL+'/'},{ACCEPTANCE_CORRECTION_APPROVED_APP_ORIGIN:'https://other.test'},{BROWSER_OIDC_MODE:'disabled'},{BROWSER_SESSION_KEY:'invalid'}]){const r=await handleAcceptanceCorrection(commandRequest(),{...correctionEnv,...patch},mode,async()=>{calls++;});assert.equal(r.status,503);privateResponse(r);}const r=await handleAcceptanceCorrection(commandRequest(),{...env,RESOURCE_COMMAND_SUBMISSION_MODE:'enabled',PRODUCTION_COMMAND_SUBMISSION_MODE:'enabled',NEXT_PUBLIC_ACCEPTANCE_CORRECTION_SUBMISSION_MODE:'enabled'},mode);assert.equal(r.status,503);const get=await handleAcceptanceCorrection(commandRequest(null,null,{method:'GET'}),correctionEnv,mode);assert.equal(get.status,405);assert.equal(get.headers.get('allow'),'POST');}assert.equal(calls,0);});
test('correction rejects cross-origin malformed/oversized/wrong-operation requests before outbound network',async()=>{let calls=0;for(const [options,status]of [[{origin:'https://evil'},403],[{site:'cross-site'},403],[{contentType:'text/plain'},415],[{raw:'{'},400],[{raw:'x'.repeat(8193)},413],[{headers:{'Content-Length':'8193'}},413],[{raw:JSON.stringify({...f.command(),operation:'resource'})},400]]){const r=await handleAcceptanceCorrection(commandRequest(null,f.command(),options),correctionEnv,'submit',async()=>{calls++;});assert.equal(r.status,status);privateResponse(r);}assert.equal(calls,0);});
for(const operation of ['SUPERSEDE','WITHDRAW']) {
 test(operation+' create/replay HTTP require own original audit; current POST result is ignored',async()=>{const w=await writeFixture(),c=f.command(operation);for(const status of [200,201]){const calls=[];const r=await handleAcceptanceCorrection(commandRequest(w.session,c),correctionEnv,'submit',async(url,init)=>{calls.push([url,init.method]);if(url.endsWith('/security/me'))return w.login.fetcher(url,init);if(init.method==='POST'){assert.equal(url,env.API_BASE_URL+'/api/v1/changes/'+encodeURIComponent(c.target)+'/acceptance-dvp-links');assert.deepEqual(JSON.parse(init.body),c.body);return Response.json({status:'PASSED',token:'private'},{status});}assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));return Response.json(f.audit(c,id));});assert.equal(r.status,200);privateResponse(r);assert.deepEqual(await r.json(),f.receipt(c));assert.equal(calls.length,3);}});
 test(operation+' read-only denies write but original own audit recovery uses only GET',async()=>{const w=await writeFixture({identity}),c=f.command(operation);let writes=0,reads=0;const mock=async(url,init)=>{if(url.endsWith('/security/me'))return w.login.fetcher(url,init);if(init.method==='POST')writes++;reads++;return Response.json(f.audit(c,id));};assert.equal((await handleAcceptanceCorrection(commandRequest(w.session,c),correctionEnv,'submit',mock)).status,403);const r=await handleAcceptanceCorrection(commandRequest(w.session,c,{recover:true}),correctionEnv,'recover',mock);assert.equal(r.status,200);assert.deepEqual(await r.json(),f.receipt(c));assert.equal(writes,0);assert.equal(reads,1);});
 test(operation+' lost or wrong-status write never automatically repeats or queries current objects',async()=>{const w=await writeFixture(),c=f.command(operation);for(const reply of [()=>{throw Error('lost');},()=>Response.json({},{status:202}),()=>Response.json({},{status:500}),()=>new Response('{')]){let writes=0,reads=0;const r=await handleAcceptanceCorrection(commandRequest(w.session,c),correctionEnv,'submit',async(url,init)=>{if(url.endsWith('/security/me'))return w.login.fetcher(url,init);if(init.method==='POST'){writes++;return reply();}reads++;throw Error('unexpected');});assert.equal(r.status,502);assert.equal(writes,1);assert.equal(reads,0);}});
 test(operation+' altered original actor/body/target audit stays unknown with no business POST',async()=>{const w=await writeFixture(),c=f.command(operation);for(const mutate of [e=>e.actor_principal_id=f.entity,e=>e.entity_ref='OTHER',e=>e.detail='OTHER',e=>e.declared_actor_name='OTHER',e=>{e.payload.previous_dvp_item_id=f.key;}]){const e=f.audit(c,id);mutate(e);let writes=0;const r=await handleAcceptanceCorrection(commandRequest(w.session,c,{recover:true}),correctionEnv,'recover',async(url,init)=>{if(url.endsWith('/security/me'))return w.login.fetcher(url,init);assert.equal(init.method,'GET');assert.equal(url,env.API_BASE_URL+'/api/v1/activity/'+f.eventNo(c));if(init.method==='POST')writes++;return Response.json(e);});assert.equal(r.status,502);assert.equal(writes,0);assert.deepEqual(await r.json(),{error:'outcome_unknown'});}});
 test(operation+' missing/denied/oversized/invalid original audit never proves absence or retries writes',async()=>{const w=await writeFixture(),c=f.command(operation);for(const reply of [()=>Response.json({detail:'private'},{status:404}),()=>Response.json({detail:'private'},{status:403}),()=>Response.json({padding:'x'.repeat(16385)}),()=>new Response(new Uint8Array([255]),{headers:{'content-type':'application/json'}})]){const r=await handleAcceptanceCorrection(commandRequest(w.session,c,{recover:true}),correctionEnv,'recover',async(url,init)=>{if(url.endsWith('/security/me'))return w.login.fetcher(url,init);assert.equal(init.method,'GET');return reply();});assert.equal(r.status,502);privateResponse(r);assert.deepEqual(await r.json(),{error:'outcome_unknown'});}});
}
test('correction requires current token-bound USER and never exposes backend denial details',async()=>{assert.equal((await handleAcceptanceCorrection(commandRequest(),correctionEnv,'submit')).status,401);const w=await writeFixture();const r=await handleAcceptanceCorrection(commandRequest(w.session),correctionEnv,'submit',async(url,init)=>url.endsWith('/security/me')?Response.json({...identity,principal:{...identity.principal,principal_type:'SERVICE'},browser_session_id:init.headers['X-Browser-Session']}):Promise.reject(Error('unexpected')));assert.equal(r.status,401);for(const [status,detail,error]of [[401,'private','session_required'],[403,'private','submission_forbidden'],[422,'private','invalid_request'],[409,'request_id already used for a different assessment','request_conflict'],[409,'assignment request conflict','request_conflict'],[409,'criterion/test pair already assigned; retry with its original request_id','submission_conflict']]){const r=await handleAcceptanceCorrection(commandRequest(w.session),correctionEnv,'submit',async(url,init)=>init.method==='POST'?Response.json({detail,token:'private'},{status}):w.login.fetcher(url,init));assert.equal(r.status,status);assert.deepEqual(await r.json(),{error});}});
test('ordinary evidence gate cannot enable correction; invalid UTF-8 and ordinary ASSIGN never reach backend',async()=>{
 let calls=0;const fetcher=async()=>{calls++;throw Error('unexpected');};
 const disabled=await handleAcceptanceCorrection(commandRequest(),{...env,EVIDENCE_COMMAND_SUBMISSION_MODE:'enabled',EVIDENCE_COMMAND_APPROVED_API_BASE_URL:env.API_BASE_URL,EVIDENCE_COMMAND_APPROVED_APP_ORIGIN:origin},'submit',fetcher);
 assert.equal(disabled.status,503);
 for(const body of [new Uint8Array([255]),JSON.stringify(require('./fixtures/evidence-command.cjs').command('acceptance'))]){
 const r=await handleAcceptanceCorrection(commandRequest(null,null,{raw:body}),correctionEnv,'submit',fetcher);assert.equal(r.status,400);
 }assert.equal(calls,0);
});
test('ambiguous cookie and token-bound principal mismatch reject before business or audit network',async()=>{
 const w=await writeFixture();
 let calls=0;
 const duplicate=await handleAcceptanceCorrection(commandRequest(w.session+'; '+w.session),correctionEnv,'recover',async()=>{calls++;throw Error('unexpected');});
 assert.equal(duplicate.status,401);assert.equal(calls,0);
 const mismatch=await handleAcceptanceCorrection(commandRequest(w.session),correctionEnv,'recover',async(url,init)=>{
 calls++;assert.equal(url,env.API_BASE_URL+'/api/v1/security/me');
 return Response.json({...identity,principal:{...identity.principal,id:f.entity},browser_session_id:init.headers['X-Browser-Session']});
 });assert.equal(mismatch.status,401);assert.equal(calls,1);
});
