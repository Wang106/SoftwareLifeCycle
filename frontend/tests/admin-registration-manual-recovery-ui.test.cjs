'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-registration-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/admin-registration-preparation.tsx','components/admin-registration-result.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/admin-registration-preparation.js')).default;
const RecoveryResult=require(path.join(output,'components/admin-registration-recovery-result.js')).default;
const Result=require(path.join(output,'components/admin-registration-result.js')).default;
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const {prepareRegistration,confirmRegistration}=require(path.join(output,'lib/admin-registration-draft.js'));
const {RegistrationSubmission,registrationMessages,registrationDenials}=require(path.join(output,'lib/admin-registration-transport.js'));
const dictionary=require('../lib/i18n/zh.json');
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const newId='34567890-1234-1234-1234-123456789abc',principalId='12345678-1234-1234-1234-123456789abc',
 scopeId='45678901-1234-1234-1234-123456789abc';
function reviewed(kind='PRINCIPAL'){
 return confirmRegistration(prepareRegistration({kind,newId,eventNo:'ADM-UI-ORIGINAL',reason:'Controlled UI reason',
  ...(kind==='PRINCIPAL'?{principalType:'USER',subject:'Exact:Subject/😀',displayName:'Test user'}:
   {principalId,role:kind==='GLOBAL'?'AUDITOR':kind==='PROJECT'?'PROJECT_VIEWER':'SOFTWARE_VIEWER',...(kind==='GLOBAL'?{}:{scopeId})})}),true);
}
function receipt(r,extra={}){const b=r.request.body;return {kind:r.kind,id:newId,audit_event_no:b.event_no,
 applied_status:r.initialStatus,current_status:r.initialStatus,replayed:false,
 ...(r.kind==='PRINCIPAL'?{revoked_browser_sessions:0}:{principal_id:principalId,role:b.role,...(r.kind==='GLOBAL'?{}:{scope_id:scopeId})}),...extra};}
const render=(locale,component)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},component));
// Exercise the actual compiled component's event handlers with isolated React hooks.
// This is deterministic component logic coverage, not browser/DOM acceptance.
function harness(enabled=true,recoveryEnabled=true,clipboard=null){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[];
 const hooks={
  useState(initial){const i=index++;if(!(i in values))values[i]=initial;
   return [values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];
   if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j]))){work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}}
 };
 const exports={};
 vm.runInNewContext(fs.readFileSync(path.join(output,'components/admin-registration-preparation.js'),'utf8'),{
  exports,require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:
   name==='./admin-registration-result'?{__esModule:true,default:Result}:
   name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),
  crypto:globalThis.crypto,window:{location:{origin:'https://example.test'},addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},
  navigator:{clipboard:{writeText:async value=>{copies.push(value);if(clipboard)await clipboard(value);}}},Error
 });
 function nodes(node){if(arguments.length===0)node=tree;if(Array.isArray(node))return node.flatMap(nodes);if(!node||typeof node!=='object')return [];
  return [node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;
  return node&&typeof node==='object'?text(node.props?.children):'';}
 function render(next=enabled,nextRecovery=recoveryEnabled){enabled=next;recoveryEnabled=nextRecovery;index=0;work=[];tree=exports.default({submissionEnabled:enabled,recoveryEnabled});for(const fn of work)fn();return tree;}
 function field(name){const n=nodes().find(n=>n.props?.name===name);assert.ok(n,'missing '+name);return n;}
 function change(name,value){field(name).props.onChange({target:{value}});render();}
 function button(label){return nodes().find(n=>n.type==='button'&&text(n)===label);}
 function preview(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});render();}
 function confirm(){nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});render();}
 function fill(kind='PRINCIPAL'){
  change('operation',kind);change('new_id',newId);
  if(kind==='PRINCIPAL'){change('subject','Exact:Subject/😀');change('display_name','Test user');}
  else{change('principal_id',principalId);if(kind!=='GLOBAL')change('scope_id',scopeId);}
  change('event_no','ADM-UI-ORIGINAL');change('reason','Controlled UI reason');preview();confirm();
 }
 function state(){return nodes().find(n=>n.type===Result)?.props.state||null;}
 render();return {recovered:()=>nodes().find(n=>n.type===RecoveryResult)?.props.state||null,render,nodes,field,change,button,preview,confirm,fill,state,listeners,copies,text};
}
const reveal='Reveal registration recovery text locally',copy='Copy sensitive registration recovery text',restore='Import registration recovery without sending',query='Query original registration audit without resubmitting',send='Send confirmed registration request',retry='Retry original registration request';
function historical(r){const {current_status,replayed,revoked_browser_sessions,...value}=receipt(r);return value;}
async function exported(kind='PRINCIPAL'){const h=harness();h.fill(kind);assert.equal(h.button(copy),undefined);const old=globalThis.fetch;try{globalThis.fetch=async()=>{throw Error('lost');};await h.button(send).props.onClick();h.render();h.button(reveal).props.onClick();h.render();await h.button(copy).props.onClick();h.render();return {h,text:h.copies.at(-1)};}finally{globalThis.fetch=old;}}
function stage(h,text){h.change('importText',text);h.button(restore).props.onClick();h.render();}
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test(`${kind}: unknown export imports without calls or new IDs and only queries historical audit`,async()=>{
 const {h,text}=await exported(kind);assert.equal(h.state().phase,'unknown');assert.ok(text.includes(newId));const fresh=harness(false);let calls=0;const old=globalThis.fetch;
 try{globalThis.fetch=async(url)=>{calls++;assert.equal(url,'/auth/admin-registration-receipt');return Response.json(historical(reviewed(kind)));};stage(fresh,text);assert.equal(calls,0);assert.equal(fresh.recovered().phase,'unknown');assert.equal(fresh.button(send),undefined);assert.equal(fresh.button(retry),undefined);assert.equal(fresh.button(copy),undefined);assert.equal(fresh.nodes().find(n=>n.type==='form').props.hidden,true);await fresh.button(query).props.onClick();fresh.render();assert.equal(calls,1);assert.equal(fresh.recovered().phase,'confirmed');assert.equal(fresh.recovered().historicalreceipt.current_status,undefined);assert.equal(fresh.recovered().historicalreceipt.replayed,undefined);assert.equal(fresh.recovered().historicalreceipt.id,newId);assert.equal(fresh.state(),null);
 }finally{globalThis.fetch=old;}
});
test('native unknown query confirms historical result and removes obsolete retry without re-registering',async()=>{
 const {h}=await exported();const old=globalThis.fetch;try{globalThis.fetch=async()=>Response.json(historical(reviewed()));await h.button(query).props.onClick();h.render();assert.equal(h.recovered().phase,'confirmed');assert.equal(h.state(),null);assert.equal(h.button(retry),undefined);assert.ok(h.button('Prepare another registration with new identifiers'));}finally{globalThis.fetch=old;}
});
test('invalid and wrong-site import is local-only; revoked capability prevents stale query and submit',async()=>{
 const {text}=await exported(),h=harness();let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};for(const value of ['{}',text.replace('example.test','foreign.test')]){stage(h,value);assert.equal(h.recovered(),null);}stage(h,text);const stale=h.button(query).props.onClick;h.render(false,false);await stale();assert.equal(calls,0);assert.equal(h.recovered().phase,'unknown');const native=harness();native.fill();const staleSend=native.button(send).props.onClick;native.render(false,false);await staleSend();assert.equal(calls,0);}finally{globalThis.fetch=old;}
});
test('explicit reveal warning precedes recovery payload; clipboard failure preserves manual fallback and blocks duplicate copy/query',async()=>{
 const {text}=await exported();let finish,copies=0;const h=harness(true,true,()=>{copies++;return new Promise((_r,reject)=>{finish=reject;});});stage(h,text);h.button(reveal).props.onClick();h.render();const click=h.button(copy).props.onClick,pending=click();await click();assert.equal(copies,1);let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await h.button(query).props.onClick();assert.equal(calls,0);finish(Error('clipboard denied'));await pending;h.render();assert.ok(h.nodes().some(n=>n.type==='code'&&n.props.children===text));assert.equal(h.recovered().phase,'unknown');}finally{globalThis.fetch=old;}
});
for(const locale of ['zh','en'])test(`${locale}: sensitive warning and historical-only result are bilingual with no current-status claim`,()=>{
 const r={phase:'confirmed',review:reviewed(),error:null,historicalreceipt:historical(reviewed())};const html=render(locale,React.createElement(RecoveryResult,{state:r}));assert.ok(html.includes(locale==='zh'?dictionary['Historical audit only. This does not establish current identity status, effective grants, replay success or permission.']:'Historical audit only. This does not establish current identity status, effective grants, replay success or permission.'));assert.ok(!html.includes('current_status'));assert.ok(!html.includes('replayed'));assert.ok(html.includes('DISABLED'));
});
test('synchronous native-send interlock blocks stale reveal/query handlers and later native confirmation clears stale audit uncertainty',async()=>{
 const h=harness();h.fill();let finish,calls=0;const old=globalThis.fetch,staleQuery=h.button(query).props.onClick,staleReveal=h.button(reveal).props.onClick;
 try{globalThis.fetch=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};const pending=h.button(send).props.onClick();staleReveal();await staleQuery();h.render();assert.equal(calls,1);assert.equal(h.button(copy),undefined);finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;h.render();globalThis.fetch=async()=>Response.json({error:'outcome_unknown'},{status:502});await h.button(query).props.onClick();h.render();assert.equal(h.recovered().phase,'unknown');globalThis.fetch=async()=>Response.json(receipt(reviewed()));await h.button(retry).props.onClick();h.render();assert.equal(h.recovered(),null);assert.equal(h.state().phase,'confirmed');}finally{globalThis.fetch=old;}
});
test('registration page keeps recovery capability for read-only administrator but denies unavailable/non-admin page',async()=>{
 const ts=require('typescript'),code=ts.transpileModule(fs.readFileSync('app/account/grants/new/page.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 async function run(state,readOnly,configured=true){let seen;const m={exports:{}};new Function('require','module','exports',code)(name=>name==='next/headers'?{cookies:async()=>({get:()=>({value:'private-cookie'})})}:name==='next/link'?({children})=>children:name.endsWith('/browser-auth')?{authConfig:async()=>({session:{}}),registrationSubmissionConfigured:()=>configured}:name.endsWith('/browser-session')?{SESSION_COOKIE:'cookie',readAdminGrants:async()=>({state,read_only_mode:readOnly})}:name.endsWith('/admin-registration-preparation')?{__esModule:true,default:props=>{seen=props;return React.createElement('div');}}:name.endsWith('/localized')?{Localized:({children})=>children}:require(name),m,m.exports);renderToStaticMarkup(await m.exports.default());return seen;}
 assert.deepEqual(await run('ready',true),{submissionEnabled:false,recoveryEnabled:true});assert.deepEqual(await run('ready',false,false),{submissionEnabled:false,recoveryEnabled:false});assert.equal(await run('forbidden',false),undefined);assert.equal(await run('unavailable',false),undefined);
});
