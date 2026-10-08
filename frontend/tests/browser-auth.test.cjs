'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jose = require('jose');
const output = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'slc-auth-'));
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
const { handleAuth, authConfig, LOGIN_COOKIE } = load('browser-auth');
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
test('disabled mode performs no network request for any auth operation',async()=>{
 let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const operation of ['login','callback','session','logout']){const response=await handleAuth(request(operation),operation,{},never);assert.equal(response.status,503);privateResponse(response);assert.deepEqual(await response.json(),{error:'login_not_configured'});}
 assert.equal(calls,0);
});
test('strict configuration rejects non-HTTPS endpoints, insecure scopes and incomplete secret mode',async()=>{
 for(const patch of [{BROWSER_OIDC_MODE:'implicit'},{BROWSER_SESSION_MODE:'disabled'},{OIDC_AUTHORIZATION_URL:'http://id.test/authorize'},{OIDC_TOKEN_URL:'https://user:secret@id.test/token'},{OIDC_JWKS_URL:'https://id.test/jwks?untrusted=x'},{OIDC_ISSUER_URL:'https://ID.test/'},{OIDC_CLIENT_ID:''},{OIDC_AUDIENCE:''},{OIDC_SCOPE:'openid offline_access'},{OIDC_SCOPE:'profile'},{OIDC_CLIENT_AUTH:'client_secret_post'},{OIDC_CLIENT_AUTH:'client_secret_basic'},{OIDC_CLIENT_SECRET:'unrequested-secret'}]) await assert.rejects(authConfig({...env,...patch}));
});
test('login POST sets random encrypted five-minute transaction and fixed PKCE S256 callback',async()=>{
 const a=await start(),b=await start();const params=a.authorization.searchParams;
 assert.equal(a.authorization.origin,'https://id.example.test');assert.equal(params.get('response_type'),'code');assert.equal(params.get('response_mode'),'query');
 assert.equal(params.get('redirect_uri'),origin+'/auth/callback');assert.equal(params.get('scope'),'openid');assert.equal(params.get('code_challenge_method'),'S256');
 for(const key of ['state','nonce','code_challenge']){assert.match(params.get(key),/^[A-Za-z0-9_-]{43}$/);assert.notEqual(params.get(key),b.authorization.searchParams.get(key));}
 const line=cookieLines(a.response)[0];for(const attribute of ['Path=/','Max-Age=300','HttpOnly','Secure','SameSite=Lax'])assert.ok(line.includes(attribute));
 assert.ok(!line.includes('Domain='));assert.ok(!line.includes(params.get('nonce')));assert.equal(params.get('code_verifier'),null);
});
test('cross-origin login/logout and GET login/logout do not change cookies',async()=>{
 for(const operation of ['login','logout']){
  for(const patch of [{headerOrigin:'https://evil.test'},{headerOrigin:''},{requestOrigin:'https://evil.test'},{site:'cross-site'},{site:'same-site'}]){const response=await handleAuth(request(operation,patch),operation,env);assert.equal(response.status,403);assert.equal(cookieLines(response).length,0);privateResponse(response);}
  const response=await handleAuth(request(operation,{method:'GET'}),operation,env);assert.equal(response.status,405);assert.equal(response.headers.get('allow'),'POST');assert.equal(cookieLines(response).length,0);
 }
});
test('signed provider round trip issues USER session, returns current identity and logs out',async()=>{
 const flow=await start(),result=await complete(flow);assert.equal(result.response.status,303);assert.equal(result.response.headers.get('location'),origin+'/account');
 assert.equal(result.calls.length,4);const session=cookie(result.response,SESSION_COOKIE);assert.ok(session);assert.ok(cookie(result.response,LOGIN_COOKIE).endsWith('='));
 const response=await handleAuth(request('session',{cookie:session}),'session',env,result.fetcher);assert.equal(response.status,200);privateResponse(response);
 const data=await response.json();assert.deepEqual(data,identity);assert.ok(!JSON.stringify(data).includes(result.access));assert.ok(!JSON.stringify(data).includes('must-not-be-retained'));
 const config=await authConfig(env);const envelope=await openCookie(config.session,SESSION_COOKIE,session.split('=')[1]);assert.equal(envelope.token,result.access);assert.equal(envelope.principal,id);assert.ok(envelope.expires-envelope.issued<=300);assert.equal(envelope.refresh_token,undefined);
 const logout=await handleAuth(request('logout',{cookie:session}),'logout',env,result.fetcher);assert.equal(logout.status,303);assert.equal(cookieLines(logout).length,2);for(const line of cookieLines(logout))assert.ok(line.includes('Max-Age=0'));
 const after=await handleAuth(request('session'),'session',env,result.fetcher);assert.equal(after.status,401);assert.equal(cookieLines(after).length,1);
});
test('confidential client uses encoded Basic credentials only at token endpoint',async()=>{
 const environment={...env,OIDC_CLIENT_AUTH:'client_secret_basic',OIDC_CLIENT_SECRET:'s:e+c/ret'};
 const flow=await start(environment);let checked=false;
 const result=await complete(flow,{onExchange:init=>{checked=true;const raw=Buffer.from(init.headers.Authorization.slice(6),'base64').toString();assert.equal(raw,'software-web:s%3Ae%2Bc%2Fret');assert.equal(new URLSearchParams(init.body).get('client_secret'),null);}});
 assert.equal(result.response.status,303);assert.equal(checked,true);assert.ok(!result.response.headers.get('location').includes(environment.OIDC_CLIENT_SECRET));
});
test('state/issuer/query/cookie errors clear pending transaction before contacting provider',async()=>{
 const flow=await start(),state=flow.authorization.searchParams.get('state');let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const query of ['?code=provider-code&state=wrong','?code=provider-code',`?code=provider-code&state=${state}&state=${state}`,`?code=provider-code&code=other&state=${state}`,`?code=provider-code&state=${state}&iss=https://evil.test/`,`?code=provider-code&state=${state}&return_to=https://evil.test`,`?code=provider-code&state=${state}&access_token=injected`,`?code=&state=${state}`]){
  const response=await handleAuth(callback(flow,query),'callback',env,never);assert.equal(response.status,400);assert.ok(cookie(response,LOGIN_COOKIE).endsWith('='));assert.equal(cookie(response,SESSION_COOKIE),undefined);
 }
 for(const badCookie of ['',flow.pending.slice(0,-8),flow.pending+'; '+flow.pending]){const req=callback(flow);req.headers.set('cookie',badCookie);const response=await handleAuth(req,'callback',env,never);assert.equal(response.status,400);}
 assert.equal(calls,0);
});
test('expired transaction and provider config rebinding prevent token exchange',async()=>{
 const flow=await start(),config=await authConfig(env);const tx=await openCookie(config.session,LOGIN_COOKIE,flow.pending.split('=')[1]);tx.issued-=301;tx.expires-=301;
 const expired=LOGIN_COOKIE+'='+await sealCookie(config.session,LOGIN_COOKIE,tx);const never=async()=>{throw Error('unexpected network');};
 assert.equal((await handleAuth(request('callback',{cookie:expired,query:callback(flow).url.split('/callback')[1]}),'callback',env,never)).status,400);
 for(const patch of [{OIDC_CLIENT_ID:'other-client'},{OIDC_TOKEN_URL:'https://other.test/token'},{OIDC_ISSUER_URL:'https://other.test/'}])assert.equal((await handleAuth(callback(flow),'callback',{...env,...patch},never)).status,400);
});
test('provider error text and callback code are never reflected in response',async()=>{
 const flow=await start();const response=await handleAuth(callback(flow,'?'+new URLSearchParams({state:flow.authorization.searchParams.get('state'),error:'access_denied',error_description:'private-token-value',error_uri:'https://evil.test'})),'callback',env);
 assert.equal(response.status,401);assert.deepEqual(await response.json(),{error:'login_failed'});assert.ok(!JSON.stringify([...response.headers]).includes('private-token-value'));
});
test('browser callback failure redirects to a fixed localized account error and clears pending cookie',async()=>{
 const flow=await start(),req=callback(flow,'?state=wrong&error_description=private-value');req.headers.set('accept','text/html');
 const response=await handleAuth(req,'callback',env);assert.equal(response.status,303);assert.equal(response.headers.get('location'),origin+'/account?auth=failed');assert.ok(cookie(response,LOGIN_COOKIE).endsWith('='));assert.ok(!JSON.stringify([...response.headers]).includes('private-value'));
});
const now=()=>Math.floor(Date.now()/1000);
const invalidClaims=[
 ['wrong ID issuer',{id:{iss:'https://evil.test/'}}],['wrong ID audience',{id:{aud:'other-client'}}],
 ['wrong nonce',{id:{nonce:'wrong'}}],['expired ID token',{id:{exp:now()-1}}],['future ID iat',{id:{iat:now()+120}}],
 ['missing ID nonce',{id:{nonce:undefined}}],['missing ID expiration',{id:{exp:undefined}}],
 ['missing ID subject',{id:{sub:undefined}}],['missing ID issued-at',{id:{iat:undefined}}],
 ['old ID authentication',{id:{iat:now()-120}}],['blank subject',{id:{sub:' '}}],['wrong ID azp',{id:{azp:'other-client'}}],
 ['multiple ID audiences without azp',{id:{aud:[env.OIDC_CLIENT_ID,'other']}}],['wrong access issuer',{access:{iss:'https://evil.test/'}}],
 ['wrong API audience',{access:{aud:env.OIDC_CLIENT_ID}}],['expired access token',{access:{exp:now()-1}}],
 ['missing access expiration',{access:{exp:undefined}}],['missing access subject',{access:{sub:undefined}}],
 ['future access iat',{access:{iat:now()+120}}],['mismatched subject',{access:{sub:'another-operator'}}],
 ['wrong access azp',{access:{azp:'other-client'}}],['bad access hash',{id:{at_hash:'wrong'}}],['bad code hash',{id:{c_hash:'wrong'}}],
 ['wrong bearer type',{tokens:{token_type:'MAC'}}],['invalid expires_in',{tokens:{expires_in:0}}],
 ['oversized access token',{tokens:{access_token:'x'.repeat(2401)}}],['missing ID token',{tokens:{id_token:null}}],
 ['inactive local principal',{identityStatus:401}],['service principal',{identity:{...identity,principal:{...identity.principal,principal_type:'SERVICE'}}}],
 ['non-contract HUMAN discriminator',{identity:{...identity,principal:{...identity.principal,principal_type:'HUMAN'}}}],
];
for(const [label,options] of invalidClaims)test('callback rejects '+label,async()=>{
 const flow=await start(),result=await complete(flow,options);assert.equal(result.response.status,401);assert.equal(cookie(result.response,SESSION_COOKIE),undefined);assert.ok(cookie(result.response,LOGIN_COOKIE).endsWith('='));assert.deepEqual(await result.response.json(),{error:'login_failed'});
 if(!options.identityStatus&&!options.identity)assert.equal(result.calls.includes(env.API_BASE_URL+'/api/v1/security/me'),false);
});
test('wrong signing key, unsigned JWT and HS256 algorithm are rejected',async()=>{
 const other=await jose.generateKeyPair('RS256');
 const flow=await start(),unsigned=new jose.UnsecuredJWT({}).encode();
 const hmac=await new jose.SignJWT({}).setProtectedHeader({alg:'HS256'}).sign(new Uint8Array(32));
 for(const options of [{idKey:other.privateKey},{accessKey:other.privateKey},{idToken:unsigned},{idToken:hmac}]){const result=await complete(flow,options);assert.equal(result.response.status,401);assert.equal(cookie(result.response,SESSION_COOKIE),undefined);assert.equal(result.calls.includes(env.API_BASE_URL+'/api/v1/security/me'),false);}
});
test('hashes and multiple ID audiences with correct azp are accepted',async()=>{
 const flow=await start(),base=await mockProvider(flow);
 const hash=async value=>Buffer.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))).slice(0,16)).toString('base64url');
 const result=await complete(flow,{accessToken:base.access,id:{aud:[env.OIDC_CLIENT_ID,'other'],azp:env.OIDC_CLIENT_ID,at_hash:await hash(base.access),c_hash:await hash('provider-code')}});assert.equal(result.response.status,303);
});
test('failed, redirected, malformed and oversized token/JWKS responses fail closed',async()=>{
 const flow=await start();
 const responses=[()=>new Response(null,{status:302,headers:{Location:'https://evil.test'}}),()=>Response.json({error:'private-error'},{status:400}),()=>new Response('<html>'),()=>new Response('{',{headers:{'content-type':'application/json'}}),()=>new Response('x'.repeat(70000),{headers:{'content-type':'application/json'}})];
 for(const response of responses)for(const key of ['tokenResponse','jwksResponse']){const result=await complete(flow,{[key]:response});assert.equal(result.response.status,401);assert.equal(cookie(result.response,SESSION_COOKIE),undefined);assert.deepEqual(await result.response.json(),{error:'login_failed'});}
});
test('session expiration, identity mismatch and provider reconfiguration clear invalid cookies',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE),config=await authConfig(env);
 const payload=await openCookie(config.session,SESSION_COOKIE,session.split('=')[1]);payload.issued-=901;payload.expires-=901;
 const expired=SESSION_COOKIE+'='+await sealCookie(config.session,SESSION_COOKIE,payload);let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const [value,environment] of [[expired,env],[session,{...env,OIDC_CLIENT_ID:'new-client'}]]){const response=await handleAuth(request('session',{cookie:value}),'session',environment,never);assert.equal(response.status,401);assert.ok(cookieLines(response)[0].includes('Max-Age=0'));}assert.equal(calls,0);
 for(const identityOverride of [{...identity,principal:{...identity.principal,id:'23456789-1234-1234-1234-123456789abc'}},{...identity,principal:{...identity.principal,principal_type:'SERVICE'}}]){const provider=await mockProvider(flow,{accessToken:result.access,identity:identityOverride});assert.equal((await handleAuth(request('session',{cookie:session}),'session',env,provider.fetcher)).status,401);}
});
test('session responses revalidate grants and never serialize provider extras',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE);
 const provider=await mockProvider(flow,{accessToken:result.access,identity:{...identity,active_grant_counts:{GLOBAL:0,PROJECT:0,SOFTWARE:0},token:'secret',principal:{...identity.principal,email:'private@example.test'}}});
 const response=await handleAuth(request('session',{cookie:session}),'session',env,provider.fetcher);assert.equal(response.status,200);const data=await response.json();assert.equal(data.active_grant_counts.PROJECT,0);assert.ok(!JSON.stringify(data).includes('secret'));assert.ok(!JSON.stringify(data).includes('email'));
});
test('callback/session require GET and session refuses a mismatched application origin',async()=>{
 for(const operation of ['callback','session']){const response=await handleAuth(request(operation,{method:'POST'}),operation,env);assert.equal(response.status,405);assert.equal(response.headers.get('allow'),'GET');}
 assert.equal((await handleAuth(request('session',{requestOrigin:'https://evil.test'}),'session',env)).status,403);
});
test('browser callback consumes pending cookie and reused provider code cannot create another session',async()=>{
 const flow=await start(),provider=await mockProvider(flow);let redeemed=false;
 const fetcher=async(url,init)=>{
  if(url===env.OIDC_TOKEN_URL){if(redeemed)return Response.json({error:'invalid_grant'},{status:400});redeemed=true;}
  return provider.fetcher(url,init);
 };
 const first=await handleAuth(callback(flow),'callback',env,fetcher);assert.equal(first.status,303);
 const noPending=callback(flow);noPending.headers.delete('cookie');assert.equal((await handleAuth(noPending,'callback',env,fetcher)).status,400);
 const replay=await handleAuth(callback(flow),'callback',env,fetcher);assert.equal(replay.status,401);assert.equal(cookie(replay,SESSION_COOKIE),undefined);
});
test('browser-controlled redirect, issuer, scope and PKCE inputs cannot override operator settings',async()=>{
 const response=await handleAuth(request('login',{query:'?return_to=https://evil.test&redirect_uri=https://evil.test&scope=offline_access&code_challenge=attacker'}),'login',env);
 assert.equal(response.status,303);const url=new URL(response.headers.get('location'));
 assert.equal(url.origin,'https://id.example.test');assert.equal(url.searchParams.get('redirect_uri'),origin+'/auth/callback');assert.equal(url.searchParams.get('scope'),'openid');assert.notEqual(url.searchParams.get('code_challenge'),'attacker');
});
test('cookie authenticated data prevents using a session cookie as a login transaction',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE);let calls=0;
 const req=callback(flow);req.headers.set('cookie',LOGIN_COOKIE+'='+session.split('=')[1]);
 const response=await handleAuth(req,'callback',env,async()=>{calls++;throw Error('unexpected');});assert.equal(response.status,400);assert.equal(calls,0);
});
test('root issuer without trailing slash remains exact and valid in configuration',async()=>{
 const config=await authConfig({...env,OIDC_ISSUER_URL:'https://id.example.test'});assert.equal(config.issuer,'https://id.example.test');
});
test('successful logout revokes copied encrypted cookie and remains idempotent',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE);
 for(let n=0;n<2;n++){const response=await handleAuth(request('logout',{cookie:session}),'logout',env,result.fetcher);assert.equal(response.status,303);privateResponse(response);}
 const replay=await handleAuth(request('session',{cookie:session}),'session',env,result.fetcher);assert.equal(replay.status,401);
 assert.ok(cookie(replay,SESSION_COOKIE).endsWith('='));
});
for(const failure of ['network','500','401','malformed'])test('logout preserves cookie when revocation fails: '+failure,async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE);
 const fetcher=async(url,init)=>{if(url.endsWith('/revoke')){if(failure==='network')throw Error('offline');if(failure==='malformed')return Response.json({status:'revoked'});return Response.json({detail:'private-provider-error'},{status:Number(failure)});}return result.fetcher(url,init);};
 const response=await handleAuth(request('logout',{cookie:session}),'logout',env,fetcher);assert.equal(response.status,503);privateResponse(response);assert.equal(cookieLines(response).length,0);assert.deepEqual(await response.json(),{error:'logout_unavailable'});
 assert.equal((await handleAuth(request('session',{cookie:session}),'session',env,result.fetcher)).status,200);
 const req=request('logout',{cookie:session});req.headers.set('accept','text/html');const html=await handleAuth(req,'logout',env,fetcher);assert.equal(html.status,303);assert.equal(html.headers.get('location'),origin+'/account?auth=logout_failed');assert.equal(cookieLines(html).length,0);
});
test('backend rollback lacking session validation proof fails closed',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE);
 const fetcher=async(url,init)=>url===env.API_BASE_URL+'/api/v1/security/me'?Response.json(identity):result.fetcher(url,init);
 assert.equal((await handleAuth(request('session',{cookie:session}),'session',env,fetcher)).status,401);
});
test('registration failure cannot issue a session cookie',async()=>{
 const flow=await start(),provider=await mockProvider(flow);const fetcher=async(url,init)=>url.endsWith('/browser-sessions')?Response.json({detail:'unavailable'},{status:503}):provider.fetcher(url,init);
 const response=await handleAuth(callback(flow),'callback',env,fetcher);assert.equal(response.status,401);assert.equal(cookie(response,SESSION_COOKIE),undefined);
});
test('legacy cookie requires new login and does not reach backend',async()=>{
 const flow=await start(),result=await complete(flow),session=cookie(result.response,SESSION_COOKIE),config=await authConfig(env);
 const envelope=await openCookie(config.session,SESSION_COOKIE,session.split('=')[1]);envelope.v=1;delete envelope.sid;
 const old=SESSION_COOKIE+'='+await sealCookie(config.session,SESSION_COOKIE,envelope);let calls=0;
 const response=await handleAuth(request('session',{cookie:old}),'session',env,async()=>{calls++;throw Error('unexpected');});assert.equal(response.status,401);assert.equal(calls,0);
});

const { readAdminGrants } = load('browser-session');
async function grantFixture() {
 const flow=await start(), login=await complete(flow), config=await authConfig(env);
 const encrypted=cookie(login.response,SESSION_COOKIE).split('=')[1];
 const sid=(await openCookie(config.session,SESSION_COOKIE,encrypted)).sid;
 const row={id,scope:'GLOBAL',role:'PLATFORM_ADMIN',status:'ACTIVE',effective:true,
   principal:{id,display_name:'管理员 <script>',status:'ACTIVE',secret:'must-not-render'},
   target:null,token:'must-not-render'};
 return {config,encrypted,sid,row,login};
}
test('private admin catalog forwards validated session and projects only allowed fields',async()=>{
 const f=await grantFixture();let seen=0;
 const fetcher=async(url,init)=>{
  if(url.includes('/admin/grants?')){
   seen++;assert.equal(new URL(url).searchParams.get('limit'),'10');
   assert.equal(init.headers['X-Browser-Session'],f.sid);
   assert.equal(init.headers.Authorization,'Bearer '+f.login.access);
   assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');
   return Response.json({scope:'GLOBAL',total:11,limit:10,offset:0,next_offset:10,items:[f.row],token:'private'});
  }return f.login.fetcher(url,init);
 };
 const result=await readAdminGrants(f.config.session,f.encrypted,'GLOBAL','ACTIVE',0,fetcher);
 assert.equal(result.state,'ready');assert.equal(result.total,11);assert.equal(result.next_offset,10);
 assert.equal(seen,1);assert.ok(!JSON.stringify(result).includes('must-not-render'));
 assert.equal(result.items[0].principal.display_name,'管理员 <script>');
});
test('grant counts cannot override backend administrator denial',async()=>{
 const f=await grantFixture();
 for(const [status,state] of [[401,'session_required'],[403,'forbidden'],[500,'unavailable']]){
  const fetcher=async(url,init)=>url.includes('/admin/grants?')?
   Response.json({detail:'sensitive denial'},{status}):f.login.fetcher(url,init);
  assert.equal((await readAdminGrants(f.config.session,f.encrypted,'GLOBAL','',0,fetcher)).state,state);
 }
});
test('invalid filters and absent session do not request the administrator catalog',async()=>{
 const f=await grantFixture();let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const [scope,status,offset] of [['OTHER','',0],['GLOBAL','OTHER',0],['GLOBAL','',-1],['GLOBAL','',100001],['GLOBAL','',0.5]]){
  assert.equal((await readAdminGrants(f.config.session,f.encrypted,scope,status,offset,never)).state,'invalid_filter');
 }
 assert.equal((await readAdminGrants(f.config.session,undefined,'GLOBAL','',0,never)).state,'session_required');
 assert.equal(calls,0);
});
test('revoked browser session prevents administrator reads',async()=>{
 const f=await grantFixture();let adminCalls=0;
 const fetcher=async(url,init)=>{if(url.includes('/admin/grants?'))adminCalls++;return f.login.fetcher(url,init);};
 const session=SESSION_COOKIE+'='+f.encrypted;
 await handleAuth(request('logout',{cookie:session}),'logout',env,fetcher);
 assert.equal((await readAdminGrants(f.config.session,f.encrypted,'GLOBAL','',0,fetcher)).state,'session_required');
 assert.equal(adminCalls,0);
});
test('malformed private catalog fails closed without exposing upstream JSON',async()=>{
 const f=await grantFixture();
 const good={scope:'GLOBAL',total:1,limit:10,offset:0,next_offset:null,items:[f.row]};
 for(const body of [{...good,scope:'PROJECT'},{...good,total:-1},{...good,next_offset:2},
   {...good,items:[{...f.row,target:{id}}]},{...good,items:[{...f.row,principal:{...f.row.principal,status:'UNKNOWN'}}]},
   {...good,items:[{...f.row,status:'SUSPENDED'}]}, {...good,limit:100}]){
  const fetcher=async(url,init)=>url.includes('/admin/grants?')?Response.json(body):f.login.fetcher(url,init);
  assert.equal((await readAdminGrants(f.config.session,f.encrypted,'GLOBAL','ACTIVE',0,fetcher)).state,'unavailable');
 }
});

const { readAdminGrantDetail } = load('browser-session');
function statusEvent() {
 return {id,event_no:'EVT-ADMIN-01',action:'SUSPEND',occurred_at:'2026-10-08T04:00:00Z',
  actor_principal_id:id,actor_display_name:'操作人 <script>',expected_status:'ACTIVE',
  status:'SUSPENDED',reason:'测试原因 <script>',reason_truncated:false,payload_json:{secret:'private'}};
}
function detailFetcher(f,options={}) {
 const detailPath=env.API_BASE_URL+'/api/v1/security/admin/grants/'+(options.scope||'GLOBAL')+'/'+id;
 return async(url,init)=>{
  if(url===detailPath){
   assert.equal(init.headers['X-Browser-Session'],f.sid);assert.equal(init.cache,'no-store');
   return Response.json(options.detail||f.row,{status:options.detailStatus||200});
  }
  if(url.startsWith(detailPath+'/history?')){
   assert.equal(new URL(url).searchParams.get('limit'),'10');
   assert.equal(init.headers.Authorization,'Bearer '+f.login.access);
   return Response.json(options.history||{scope:'GLOBAL',grant_id:id,current_status:'SUSPENDED',
    coverage:'GLOBAL_ROLE_STATUS_CHANGED_ONLY',total:11,limit:10,offset:0,next_offset:10,items:[statusEvent()]},
    {status:options.historyStatus||200});
  }
  return f.login.fetcher(url,init);
 };
}
test('exact grant detail and history preserve independent status snapshots without secrets',async()=>{
 const f=await grantFixture();
 const result=await readAdminGrantDetail(f.config.session,f.encrypted,'GLOBAL',id.toUpperCase(),0,detailFetcher(f));
 assert.equal(result.state,'ready');assert.equal(result.grant.id,id);
 assert.equal(result.grant.status,'ACTIVE');assert.equal(result.current_status,'SUSPENDED');
 assert.equal(result.total,11);assert.equal(result.next_offset,10);
 assert.equal(result.items[0].reason,'测试原因 <script>');
 assert.ok(!JSON.stringify(result).includes('private'));assert.ok(!JSON.stringify(result).includes('must-not-render'));
});
test('each exact read enforces backend denials; detail failure does not fetch history',async()=>{
 const f=await grantFixture();
 for(const [status,state] of [[401,'session_required'],[403,'forbidden'],[404,'not_found'],[503,'unavailable']]){
  for(const at of ['detail','history']){
   let histories=0;const fetcher=detailFetcher(f,{[at+'Status']:status});
   const wrapped=async(url,init)=>{if(url.includes('/history?'))histories++;return fetcher(url,init);};
   assert.equal((await readAdminGrantDetail(f.config.session,f.encrypted,'GLOBAL',id,0,wrapped)).state,state);
   if(at==='detail')assert.equal(histories,0);
  }
 }
});
test('exact history rejects wrong identity, coverage, pagination and malformed events',async()=>{
 const f=await grantFixture(), base={scope:'GLOBAL',grant_id:id,current_status:'ACTIVE',
  coverage:'GLOBAL_ROLE_STATUS_CHANGED_ONLY',total:1,limit:10,offset:0,next_offset:null,items:[statusEvent()]};
 for(const history of [{...base,grant_id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'},
  {...base,scope:'PROJECT'},{...base,coverage:'MEMBERSHIP_STATUS_CHANGED_ONLY'},
  {...base,next_offset:3},{...base,total:-1},{...base,items:[{...statusEvent(),reason:'x'.repeat(501)}]},
  {...base,items:[{...statusEvent(),occurred_at:'not-a-date'}]},
  {...base,items:[{...statusEvent(),status:'DISABLED'}]}]){
  assert.equal((await readAdminGrantDetail(f.config.session,f.encrypted,'GLOBAL',id,0,detailFetcher(f,{history}))).state,'unavailable');
 }
 assert.equal((await readAdminGrantDetail(f.config.session,f.encrypted,'GLOBAL',id,0,
  detailFetcher(f,{detail:{...f.row,id:'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'}}))).state,'unavailable');
});
test('exact grant paths validate filters and revoked sessions before private reads',async()=>{
 const f=await grantFixture();let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const [scope,grantId,offset] of [['OTHER',id,0],['GLOBAL','../secrets',0],['GLOBAL',id,-1],['GLOBAL',id,100001]]){
  assert.equal((await readAdminGrantDetail(f.config.session,f.encrypted,scope,grantId,offset,never)).state,'invalid_filter');
 }
 assert.equal(calls,0);
 await handleAuth(request('logout',{cookie:SESSION_COOKIE+'='+f.encrypted}),'logout',env,f.login.fetcher);
 assert.equal((await readAdminGrantDetail(f.config.session,f.encrypted,'GLOBAL',id,0,f.login.fetcher)).state,'session_required');
});
test('project and software exact histories accept owned targets and nullable legacy values',async()=>{
 const f=await grantFixture();
 for(const scope of ['PROJECT','SOFTWARE']){
  const detail={...f.row,scope,target:{id,code:'OWNED',name:'Owned target'}};
  const history={scope,grant_id:id,current_status:'ACTIVE',coverage:'MEMBERSHIP_STATUS_CHANGED_ONLY',
   total:11,limit:10,offset:10,next_offset:null,items:[{...statusEvent(),expected_status:null,status:null,
    actor_principal_id:null,actor_display_name:null,reason:null,reason_truncated:false}]};
  const result=await readAdminGrantDetail(f.config.session,f.encrypted,scope,id,10,detailFetcher(f,{scope,detail,history}));
  assert.equal(result.state,'ready');assert.equal(result.grant.target.id,id);assert.equal(result.items[0].reason,null);
 }
});
