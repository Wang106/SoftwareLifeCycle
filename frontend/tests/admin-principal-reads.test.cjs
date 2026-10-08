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
const session=load('lib/browser-session.ts'),localized=load('components/localized.tsx');
const id='12345678-1234-1234-1234-123456789abc',other='23456789-1234-1234-1234-123456789abc',token='signed-test-token';
const env={BROWSER_SESSION_MODE:'encrypted',BROWSER_SESSION_KEY:Buffer.alloc(32,7).toString('base64url'),
 BROWSER_SESSION_ORIGIN:'https://app.example.test',API_BASE_URL:'https://api.example.test'};
const principal={id,principal_type:'USER',display_name:'身份 <script>',status:'DISABLED',created_at:'2026-10-08T00:00:00Z',
 issuer_matches_configuration:true,admin_principal_protected:false,status_history_supported:true,subject:'private-subject',token};
const audit={id:other,event_no:'STATUS-01',action:'ENABLE',occurred_at:'2026-10-08T01:00:00Z',
 actor_principal_id:null,actor_display_name:null,expected_status:null,status:'ACTIVE',reason:'原因 <script>',
 reason_truncated:false,payload_json:{token}};
const page=(items,offset=0,total=items.length)=>({total,limit:10,offset,next_offset:offset+10<total?offset+10:null,items});
async function fixture(){
 const config=await session.sessionConfig(env),now=Math.floor(Date.now()/1000);
 let sid,revoked=false;const calls=[];
 const me={principal:{id,principal_type:'USER',display_name:'Reader'},read_only_mode:true,
  active_grant_counts:{GLOBAL:999,PROJECT:0,SOFTWARE:0}};
 const base=async(url,init)=>{
  assert.equal(init.cache,'no-store');assert.equal(init.redirect,'error');assert.ok(init.signal);
  assert.equal(init.headers.Authorization,'Bearer '+token);
  if(url.endsWith('/browser-sessions')){const b=JSON.parse(init.body);sid=b.id;return Response.json(b);}
  assert.equal(url,env.API_BASE_URL+'/api/v1/security/me');
  if(revoked)return Response.json({detail:'private'},{status:401});
  return Response.json({...me,...(init.headers['X-Browser-Session']?{browser_session_id:init.headers['X-Browser-Session']}:{})});
 };
 const issued=await session.establishSession(config,token,now+600,base);
 assert.ok(issued);
 const mock=(options={})=>async(url,init)=>{
  if(!url.includes('/admin/principals'))return base(url,init);
  calls.push(url);assert.equal(init.headers.Authorization,'Bearer '+token);
  assert.equal(init.headers['X-Browser-Session'],sid);assert.equal(init.cache,'no-store');
  assert.equal(init.redirect,'error');assert.ok(init.signal);
  if(url.includes('/history?'))return Response.json(options.history??{
   ...page([audit]),principal_id:id,current_status:'ACTIVE',coverage:'PRINCIPAL_STATUS_CHANGED_ONLY'
  },{status:options.historyStatus??200});
  if(url.includes('/principals?'))return Response.json(options.catalog??page([principal]),{status:options.catalogStatus??200});
  return Response.json(options.detail??principal,{status:options.detailStatus??200});
 };
 return {config,cookie:issued.cookie.value,mock,calls,revoke:()=>{revoked=true;}};
}
test('catalog includes disabled ungranted identity and projects credentials out',async()=>{
 const f=await fixture(),result=await session.readAdminPrincipals(f.config,f.cookie,id.toUpperCase(),'USER','DISABLED',0,f.mock());
 assert.equal(result.state,'ready');assert.equal(result.items[0].id,id);assert.equal(result.items[0].status,'DISABLED');
 assert.equal(result.read_only_mode,true);assert.equal(result.items[0].subject,undefined);
 assert.ok(!JSON.stringify(result).includes(token));
 const url=new URL(f.calls[0]);assert.equal(url.searchParams.get('principal_id'),id);
 assert.equal(url.searchParams.get('principal_type'),'USER');assert.equal(url.searchParams.get('status'),'DISABLED');
 assert.equal(url.searchParams.get('limit'),'10');
});
test('backend admin/session denial is authoritative despite global grant count',async()=>{
 const f=await fixture();
 for(const [status,state] of [[401,'session_required'],[403,'forbidden'],[500,'unavailable'],[404,'unavailable']])
  assert.equal((await session.readAdminPrincipals(f.config,f.cookie,'','','',0,f.mock({catalogStatus:status}))).state,state);
 f.revoke();f.calls.length=0;
 assert.equal((await session.readAdminPrincipals(f.config,f.cookie,'','','',0,f.mock())).state,'session_required');
 assert.equal(f.calls.length,0);
});
test('invalid filters, UUID paths and absent sessions make no network requests',async()=>{
 const f=await fixture();let calls=0;const never=async()=>{calls++;throw Error('unexpected');};
 for(const [pid,kind,status,offset] of [['../private','','',0],['','BOT','',0],['','','SUSPENDED',0],['','','',-1],['','','',100001],['','','',0.5]])
  assert.equal((await session.readAdminPrincipals(f.config,f.cookie,pid,kind,status,offset,never)).state,'invalid_filter');
 assert.equal((await session.readAdminPrincipals(f.config,undefined,'','','',0,never)).state,'session_required');
 for(const [pid,offset] of [['../private',0],[id,-1],[id,100001]])
  assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,pid,offset,never)).state,'invalid_filter');
 assert.equal(calls,0);
});
test('catalog rejects malformed metadata, duplicate or filter-mismatched rows',async()=>{
 const f=await fixture(),good=page([principal]);
 for(const catalog of [{...good,total:-1},{...good,limit:50},{...good,next_offset:10},
  {...good,items:[]},page([principal,principal]),
  page([{...principal,id:other}]),page([{...principal,status:'ACTIVE'}]),
  page([{...principal,principal_type:'SERVICE'}]),page([{...principal,issuer_matches_configuration:'true'}]),
  page([{...principal,admin_principal_protected:0}]),page([{...principal,created_at:'bad'}]),
  page([{...principal,display_name:'x'.repeat(201)}]),page([{...principal,status_history_supported:false}])])
  assert.equal((await session.readAdminPrincipals(f.config,f.cookie,id,'USER','DISABLED',0,f.mock({catalog}))).state,'unavailable');
});
test('catalog supports empty, later and final API-budget pages without invalid next links',async()=>{
 const f=await fixture();
 assert.equal((await session.readAdminPrincipals(f.config,f.cookie,'','','',0,f.mock({catalog:page([])}))).total,0);
 const last=await session.readAdminPrincipals(f.config,f.cookie,'','','',10,f.mock({catalog:page([principal],10,11)}));
 assert.equal(last.state,'ready');assert.equal(last.next_offset,null);
 const capped=await session.readAdminPrincipals(f.config,f.cookie,'','','',100000,f.mock({
  catalog:page(Array.from({length:10},(_,n)=>({...principal,id:'00000000-0000-0000-0000-'+String(n).padStart(12,'0')})),100000,100011)}));
 assert.equal(capped.state,'ready');assert.equal(capped.navigation_limited,true);assert.equal(capped.next_offset,null);
});
test('detail/history retain distinct status snapshots and project only bounded evidence',async()=>{
 const f=await fixture(),result=await session.readAdminPrincipalDetail(f.config,f.cookie,id.toUpperCase(),0,f.mock());
 assert.equal(result.state,'ready');assert.equal(result.principal.status,'DISABLED');assert.equal(result.current_status,'ACTIVE');
 assert.equal(result.items[0].reason,audit.reason);assert.equal(result.items[0].expected_status,null);
 assert.ok(!JSON.stringify(result).includes(token));assert.ok(!JSON.stringify(result).includes('payload_json'));
 assert.equal(f.calls[0],env.API_BASE_URL+'/api/v1/security/admin/principals/'+id);
});
test('detail and history failures fail closed and wrong target never falls back',async()=>{
 const f=await fixture();
 for(const at of ['detail','history'])for(const [status,state] of [[401,'session_required'],[403,'forbidden'],[404,'not_found'],[503,'unavailable']]){
  f.calls.length=0;
  assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,f.mock({[at+'Status']:status,[at]:{detail:'principal_not_found'}}))).state,state);
  if(at==='detail')assert.equal(f.calls.length,1);
 }
 f.calls.length=0;
 assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,f.mock({detail:{...principal,id:other}}))).state,'unavailable');
 assert.equal(f.calls.length,1);
});
test('history enforces exact identity, coverage, bounds and event uniqueness',async()=>{
 const f=await fixture(),good={...page([audit]),principal_id:id,current_status:'ACTIVE',coverage:'PRINCIPAL_STATUS_CHANGED_ONLY'};
 for(const history of [{...good,principal_id:other},{...good,coverage:'PRINCIPAL_REGISTERED_ONLY'},
  {...good,current_status:'SUSPENDED'},{...good,offset:1},{...good,next_offset:10},
  {...good,items:[{...audit,status:'SUSPENDED'}]},{...good,items:[{...audit,reason:'x'.repeat(501)}]},
  {...good,items:[{...audit,occurred_at:'bad'}]},{...good,items:[{...audit,actor_principal_id:'bad'}]},
  {...good,items:[{...audit,reason_truncated:'false'}]},
  {...good,...page([audit,audit])}])
  assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,f.mock({history}))).state,'unavailable');
});
test('full history permits 500 Unicode code points and bounded large body',async()=>{
 const f=await fixture(),history={...page(Array.from({length:10},(_,n)=>({...audit,
  id:'00000000-0000-0000-0000-'+String(n).padStart(12,'0'),reason:'😀'.repeat(500),actor_display_name:'人'.repeat(200)}))),
  principal_id:id,current_status:'ACTIVE',coverage:'PRINCIPAL_STATUS_CHANGED_ONLY'};
 assert.ok(Buffer.byteLength(JSON.stringify(history))>16384);
 assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,f.mock({history}))).state,'ready');
 assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,f.mock({
  history:{...history,private:'x'.repeat(32768)}}))).state,'unavailable');
 assert.equal((await session.readAdminPrincipals(f.config,f.cookie,'','','',0,f.mock({
  catalog:{...page([principal]),private:'x'.repeat(16384)}}))).state,'unavailable');
});
function render(locale,node){return renderToStaticMarkup(React.createElement(localized.LanguageProvider,{initialLocale:locale},node));}
async function pageNode(which,result,{query={},config=true}={}){
 const file=which==='catalog'?'app/account/principals/page.tsx':'app/account/principals/[id]/page.tsx';
 const depth=which==='catalog'?'../../../':'../../../../';
 let calls=0,args;
 const mod=load(file,{
  'next/link':({children,...props})=>React.createElement('a',props,children),
  'next/headers':{cookies:async()=>({get:()=>({value:'encrypted'})})},
  [depth+'lib/browser-auth']:{authConfig:async()=>config?{session:{}}:null},
  [depth+'lib/browser-session']:{SESSION_COOKIE:session.SESSION_COOKIE,
   readAdminPrincipals:async(...value)=>{calls++;args=value;return result;},
   readAdminPrincipalDetail:async(...value)=>{calls++;args=value;return result;}
  }
 });
 return {node:await mod.default({params:Promise.resolve({id}),searchParams:Promise.resolve(query)}),calls,args};
}
test('catalog SSR is bilingual, escapes stored text and retains exact links/filter values',async()=>{
 const result={state:'ready',total:11,next_offset:10,navigation_limited:false,read_only_mode:true,
  items:[{...principal,subject:undefined,token:undefined}]};
 const {node}=await pageNode('catalog',result,{query:{principal_type:'USER',status:'DISABLED'}});
 const zh=render('zh',node),en=render('en',node);
 assert.ok(zh.includes('身份管理'));assert.ok(en.includes('Identity administration'));
 assert.ok(zh.includes('&lt;script&gt;'));assert.ok(!zh.includes('<script>'));
 assert.ok(zh.includes('/account/principals/'+id));assert.ok(en.includes('value="DISABLED"'));
 assert.ok(en.includes('principal_type=USER'));assert.ok(en.includes('offset=10'));
 assert.ok(!en.includes(token));assert.ok(!en.includes('method="post"'));
});
test('detail SSR keeps both statuses, translates evidence coverage and blocks preparation when read snapshots differ',async()=>{
 const result={state:'ready',principal,items:[audit],current_status:'ACTIVE',total:1,next_offset:null,
  read_only_mode:true,navigation_limited:false};
 const {node}=await pageNode('detail',result);
 const zh=render('zh',node),en=render('en',node);
 assert.ok(zh.includes('身份详情与状态历史'));assert.ok(en.includes('Identity detail and status history'));
 assert.ok(zh.includes('读取快照'));assert.ok(en.includes('Registration and provider history are not included'));
 assert.ok(zh.includes('&lt;script&gt;'));assert.ok(!en.includes('<form'));
 assert.ok(!en.includes(token));assert.ok(en.includes('DISABLED'));assert.ok(en.includes('ACTIVE'));
});
test('disabled and denied pages do not render identity data or forms',async()=>{
 for(const which of ['catalog','detail']){
  const disabled=await pageNode(which,{state:'ready'},{config:false});
  assert.equal(disabled.calls,0);assert.ok(render('en',disabled.node).includes('Login is not available'));
  for(const state of ['session_required','forbidden','unavailable','not_found','invalid_filter']){
   const html=render('zh',(await pageNode(which,{state})).node);
   assert.ok(!html.includes(id));assert.ok(!html.includes('<form'));
  }
 }
});
test('repeated, unknown and malformed page query values never reach helpers',async()=>{
 for(const which of ['catalog','detail'])for(const query of [{offset:['0','10']},{offset:'-1'},{offset:'1.5'},{token:'private'}]){
  const p=await pageNode(which,{state:'ready'},{query});
  assert.equal(p.calls,0);assert.ok(render('en',p.node).includes('Invalid identity filters'));
 }
 for(const query of [{principal_id:[id,other]},{principal_type:['USER','SERVICE']},{status:['ACTIVE','DISABLED']}]){
  const p=await pageNode('catalog',{state:'ready'},{query});assert.equal(p.calls,0);
 }
});

test('unsupported API route 404 is unavailable rather than a missing identity',async()=>{
 const f=await fixture();
 for(const at of ['detail','history'])
  assert.equal((await session.readAdminPrincipalDetail(f.config,f.cookie,id,0,
   f.mock({[at+'Status']:404,[at]:{detail:'Not Found'}}))).state,'unavailable');
});

test('exact detail integrates preparation only on matching unprotected snapshots',async()=>{
 const ready={state:'ready',principal,items:[],current_status:'DISABLED',total:0,next_offset:null,
  read_only_mode:true,navigation_limited:false};
 for(const locale of ['zh','en']){
  const html=render(locale,(await pageNode('detail',ready)).node);
  assert.ok(html.includes('<form'));assert.ok(html.includes(locale==='zh'?'准备身份状态变更':'Prepare identity status change'));
  assert.ok(!html.includes('method="post"'));assert.ok(!html.includes('type="checkbox"'));
  assert.ok(!html.includes('name="principal_id"'));assert.ok(!html.includes(token));
  const protectedHtml=render(locale,(await pageNode('detail',{...ready,principal:{...principal,admin_principal_protected:true}})).node);
  assert.ok(!protectedHtml.includes('<form'));
 }
});
