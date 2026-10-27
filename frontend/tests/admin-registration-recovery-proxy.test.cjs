'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve('.'),modules=new Map();
function load(file,stubs={}){
 const filename=path.resolve(root,file);
 if(!Object.keys(stubs).length&&modules.has(filename))return modules.get(filename);
 const exports={};
 if(!Object.keys(stubs).length)modules.set(filename,exports);
 const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,
  module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 vm.runInNewContext(code,{exports,process:{env:{}},require:name=>{
  if(Object.hasOwn(stubs,name))return stubs[name];
  if(name==='server-only')return {};
  if(name.startsWith('.')){
   let next=path.resolve(path.dirname(filename),name);
   if(next.endsWith('.json'))return JSON.parse(fs.readFileSync(next,'utf8'));
   next+=fs.existsSync(next+'.tsx')?'.tsx':'.ts';
   return load(next);
  }
  return require(name);
 },crypto:globalThis.crypto,TextEncoder,TextDecoder,Uint8Array,btoa,atob,AbortSignal,fetch,URL,URLSearchParams,Request,Response});
 return exports;
}
const session=load('lib/browser-session.ts'),auth=load('lib/browser-auth.ts'),audit=load('lib/admin-registration-audit.ts');
const {prepareRegistration}=load('lib/admin-registration-draft.ts');
const actor='12345678-1234-1234-1234-123456789abc',id='34567890-1234-1234-1234-123456789abc',scope='45678901-1234-1234-1234-123456789abc';
const origin='https://app.example.test',token='synthetic-token-only';
const env={BROWSER_OIDC_MODE:'code',BROWSER_SESSION_MODE:'encrypted',BROWSER_SESSION_KEY:Buffer.alloc(32,9).toString('base64url'),
 BROWSER_SESSION_ORIGIN:origin,API_BASE_URL:'https://api.example.test',OIDC_ISSUER_URL:'https://id.example.test/',
 OIDC_AUDIENCE:'software-api',OIDC_CLIENT_ID:'software-web',OIDC_AUTHORIZATION_URL:'https://id.example.test/authorize',
 OIDC_TOKEN_URL:'https://id.example.test/token',OIDC_JWKS_URL:'https://id.example.test/jwks',ADMIN_REGISTRATION_SUBMISSION_MODE:'enabled',
 ADMIN_REGISTRATION_APPROVED_API_BASE_URL:'https://api.example.test',ADMIN_REGISTRATION_APPROVED_APP_ORIGIN:origin};
const input=(kind='PRINCIPAL')=>({kind,newId:id,eventNo:'REGISTER-ORIGINAL',reason:'Approved 注册😀',...(kind==='PRINCIPAL'?
 {principalType:'USER',subject:'精确:Subject/😀',displayName:'名字😀'}:{principalId:actor,role:kind==='GLOBAL'?'AUDITOR':kind==='PROJECT'?'PROJECT_VIEWER':'SOFTWARE_VIEWER',...(kind==='GLOBAL'?{}:{scopeId:scope})})});
async function event(kind){const r=prepareRegistration(input(kind)),b=r.request.body;
 return {id:scope,event_no:b.event_no,event_type:kind==='PRINCIPAL'?'PRINCIPAL_REGISTERED':kind==='GLOBAL'?'GLOBAL_ROLE_REGISTERED':'MEMBERSHIP_REGISTERED',
 entity_type:kind==='PRINCIPAL'?'SECURITY_PRINCIPAL':kind==='GLOBAL'?'GLOBAL_ROLE':kind+'_MEMBERSHIP',entity_id:id,entity_ref:id,
 action:'REGISTER',actor_principal_id:actor,declared_actor_name:null,payload:kind==='PRINCIPAL'?
 {principal_id:id,principal_type:'USER',status:'DISABLED',reason:b.reason,request_digest:await audit.principalRegistrationDigest(r,env.OIDC_ISSUER_URL)}:
 {...(kind==='GLOBAL'?{grant_id:id}:{scope:kind,membership_id:id,scope_id:scope}),principal_id:actor,role:b.role,status:'SUSPENDED',reason:b.reason}};
}
async function fixture(kind='PRINCIPAL',options={}){
 const config=await auth.authConfig(env),now=Math.floor(Date.now()/1000);let sid=options.sid||scope;const calls=[];
 const cookie=await session.sealCookie(config.session,session.SESSION_COOKIE,{v:2,sid,binding:config.session.binding,issued:now,expires:now+600,principal:actor,token});
 const historical=await event(kind);
 const fetcher=async(url,init)=>{calls.push(url);assert.equal(init.method||'GET','GET');assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
 assert.equal(init.headers.Authorization,'Bearer '+token);assert.equal(init.headers['X-Browser-Session'],sid);
 if(url.endsWith('/security/me'))return Response.json({principal:{id:actor,principal_type:options.service?'SERVICE':'USER',display_name:'Admin'},read_only_mode:true,
 active_grant_counts:{GLOBAL:999,PROJECT:0,SOFTWARE:0},browser_session_id:sid},{status:options.revoked?401:200});
 if(url.includes('/security/admin/grants?'))return Response.json(options.malformed?{}:{scope:'GLOBAL',limit:10,offset:0,total:0,next_offset:null,items:[]},{status:options.adminStatus||200});
 assert.equal(url,env.API_BASE_URL+'/api/v1/activity/REGISTER-ORIGINAL');return Response.json(options.audit||historical,{status:options.auditStatus||200});};
 return {cookie,fetcher,calls,historical};
}
function request(body,cookie,headers={}){return new Request(origin+'/auth/admin-registration-receipt',{method:'POST',headers:{Origin:origin,'Sec-Fetch-Site':'same-origin','Content-Type':'application/json',Cookie:session.SESSION_COOKIE+'='+cookie,...headers},body:typeof body==='string'?body:JSON.stringify(body)});}
function privateResponse(r){assert.equal(r.headers.get('cache-control'),'private, no-store');assert.equal(r.headers.get('pragma'),'no-cache');assert.equal(r.headers.get('vary'),'Cookie');assert.equal(r.headers.get('referrer-policy'),'no-referrer');}
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test('GET-only original recovery with fresh readonly admin session '+kind,async()=>{
 const f=await fixture(kind),r=await auth.handleAdminRegistrationRecovery(request(input(kind),f.cookie),env,f.fetcher);privateResponse(r);assert.equal(r.status,200);
 const value=await r.json();assert.equal(value.id,id);assert.equal(value.applied_status,kind==='PRINCIPAL'?'DISABLED':'SUSPENDED');
 for(const key of ['current_status','replayed','revoked_browser_sessions','subject','issuer','request_digest','token'])assert.equal(value[key],undefined);
 assert.equal(f.calls.filter(u=>u.includes('/activity/')).length,1);assert.equal(f.calls.length,4);
});
test('Python ensure_ascii=False sorted compact Unicode digest golden and surrogate rejection',async()=>{
 assert.equal(await audit.principalRegistrationDigest(prepareRegistration(input()),env.OIDC_ISSUER_URL),'d10001e7dd31998b4feeac12ae1cb44ca9f3279ceff296343260ed3667855c20');
 const f=await fixture(),r=await auth.handleAdminRegistrationRecovery(request({...input(),subject:'bad\ud800'},f.cookie),env,f.fetcher);assert.equal(r.status,400);assert.equal(f.calls.length,0);
});
for(const options of [{revoked:true},{service:true},{adminStatus:403},{adminStatus:401},{malformed:true}])test('authorization before audit '+JSON.stringify(options),async()=>{
 const f=await fixture('GLOBAL',options),r=await auth.handleAdminRegistrationRecovery(request(input('GLOBAL'),f.cookie),env,f.fetcher);assert.notEqual(r.status,200);privateResponse(r);assert.ok(!f.calls.some(u=>u.includes('/activity/')));
});
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test('all audit attribution and payload fields bound '+kind,async()=>{
 const r=prepareRegistration(input(kind)),original=await event(kind);
 for(const key of ['id','event_no','event_type','entity_type','entity_id','entity_ref','action','actor_principal_id','declared_actor_name']){
 assert.equal(await audit.projectAdminRegistrationAudit({...original,[key]:'tampered'},r,actor,env.OIDC_ISSUER_URL),null,key);}
 for(const key of Object.keys(original.payload))for(const missing of [false,true]){const p={...original.payload};if(missing)delete p[key];else p[key]='tampered';
 assert.equal(await audit.projectAdminRegistrationAudit({...original,payload:p},r,actor,env.OIDC_ISSUER_URL),null,key);}
 assert.equal(await audit.projectAdminRegistrationAudit({...original,payload:{...original.payload,extra:true}},r,actor,env.OIDC_ISSUER_URL),null);
 if(kind==='PRINCIPAL')assert.equal(await audit.projectAdminRegistrationAudit(original,r,actor,'https://other.example'),null);
});
test('gates, origin, content bounds and private failure responses avoid upstream',async()=>{
 const f=await fixture();for(const [req,e,status] of [[request(input(),f.cookie),{...env,ADMIN_REGISTRATION_SUBMISSION_MODE:'disabled'},503],
 [request(input(),f.cookie),{...env,ADMIN_REGISTRATION_APPROVED_API_BASE_URL:'https://other.example'},503],
 [request(input(),f.cookie,{Origin:'https://evil.example'}),env,403],[request(input(),f.cookie,{'Content-Type':'text/plain'}),env,415],
 [request('x'.repeat(8193),f.cookie),env,413],[request(input(),f.cookie,{'Content-Length':'8193'}),env,413],
 [request('{bad',f.cookie),env,400],[new Request(origin+'/auth/admin-registration-receipt'),env,405]]){
 const r=await auth.handleAdminRegistrationRecovery(req,e,f.fetcher);assert.equal(r.status,status);privateResponse(r);}
 assert.equal(f.calls.length,0);
 const r=await auth.handleAdminRegistrationRecovery(new Request(origin+'/auth/admin-registration-receipt',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:new Uint8Array([0xff])}),env,f.fetcher);assert.equal(r.status,400);
});
test('missing or foreign original evidence stays unknown and no private payload escapes',async()=>{
 for(const options of [{auditStatus:404},{auditStatus:500},{audit:{...(await event('PRINCIPAL')),actor_principal_id:scope}}]){
 const f=await fixture('PRINCIPAL',options),r=await auth.handleAdminRegistrationRecovery(request(input(),f.cookie),env,f.fetcher);assert.equal(r.status,502);assert.deepEqual(await r.json(),{error:'outcome_unknown'});}
});
test('same actor may recover in a newly issued session without original session identifiers',async()=>{
 for(const sid of [scope,'56789012-1234-1234-1234-123456789abc']){
 const f=await fixture('GLOBAL',{sid}),r=await auth.handleAdminRegistrationRecovery(request(input('GLOBAL'),f.cookie),env,f.fetcher);
 assert.equal(r.status,200);assert.equal((await r.json()).audit_event_no,'REGISTER-ORIGINAL');}
});
test('second Python golden preserves escaping, combining Unicode and line separator',async()=>{
 const value={...input(),displayName:'Name "quoted"\\path',reason:'Reason café é',subject:'Sub\u2028ject/🧪'};
 assert.equal(await audit.principalRegistrationDigest(prepareRegistration(value),env.OIDC_ISSUER_URL),'5a26b820b2cf6c056ff1fd43de80cddd90f72397c79cb7407b6bc08d66429907');
});
