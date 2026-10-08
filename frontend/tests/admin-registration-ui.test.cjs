'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-registration-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/admin-registration-preparation.tsx','components/admin-registration-result.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/admin-registration-preparation.js')).default;
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
test('initial bilingual page distinguishes disabled preparation from enabled capability and has no unconfirmed send',()=>{
 for(const locale of ['zh','en']){
  const disabled=render(locale,React.createElement(Component)),enabled=render(locale,React.createElement(Component,{submissionEnabled:true}));
  assert.ok(disabled.includes(locale==='zh'?'本表单不会创建身份或授权':'Preparation only.'));
  assert.ok(enabled.includes(locale==='zh'?'受控注册已开放':'Controlled registration is available.'));
  for(const html of [disabled,enabled]){
   assert.ok(!html.includes('Send confirmed registration request'));assert.ok(!html.includes('发送已确认的注册请求'));
   for(const field of ['issuer','actor','token','password','api_url'])assert.ok(!html.includes('name="'+field+'"'));
  }
 }
});
// Exercise the actual compiled component's event handlers with isolated React hooks.
// This is deterministic component logic coverage, not browser/DOM acceptance.
function harness(enabled=true){
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
  crypto:globalThis.crypto,window:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},
  navigator:{clipboard:{writeText:async value=>{copies.push(value);}}},Error
 });
 function nodes(node=tree){if(Array.isArray(node))return node.flatMap(nodes);if(!node||typeof node!=='object')return [];
  return [node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;
  return node&&typeof node==='object'?text(node.props?.children):'';}
 function render(next=enabled){enabled=next;index=0;work=[];tree=exports.default({submissionEnabled:enabled});for(const fn of work)fn();return tree;}
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
 render();return {render,nodes,field,change,button,preview,confirm,fill,state,listeners,copies,text};
}
test('editing a preview clears confirmation; disabled form never offers sending',()=>{
 const h=harness(false);h.fill();assert.ok(h.button('Copy confirmed registration request'));
 assert.equal(h.button('Send confirmed registration request'),undefined);
 h.change('reason','Changed reviewed reason');assert.equal(h.button('Copy confirmed registration request'),undefined);
 h.preview();assert.equal(h.button('Copy confirmed registration request').props.disabled,true);
});
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test('actual registration form sends exact confirmed '+kind+' input and projects receipt',async()=>{
 const h=harness(true);h.fill(kind);const oldFetch=globalThis.fetch;let calls=0;
 try{
  globalThis.fetch=async(url,init)=>{
   calls++;assert.equal(url,'/auth/admin-registration');const input=JSON.parse(init.body);
   assert.equal(input.kind,kind);assert.equal(input.newId,newId);assert.equal(input.eventNo,'ADM-UI-ORIGINAL');
   assert.equal(input.reason,'Controlled UI reason');assert.equal(input.issuer,undefined);assert.equal(input.status,undefined);
   return Response.json(receipt(reviewed(kind),{subject:'private',token:'secret'}));
  };
  await h.button('Send confirmed registration request').props.onClick();h.render();
  assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);
  assert.equal(h.nodes().find(n=>n.type==='fieldset').props.disabled,true);
  assert.equal(h.button('Send confirmed registration request'),undefined);
  assert.ok(h.button('Prepare another registration with new identifiers'));
 }finally{globalThis.fetch=oldFetch;}
});
test('actual form synchronously locks duplicate clicks and warns while sending',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch;let finish,calls=0;
 try{
  globalThis.fetch=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
  const click=h.button('Send confirmed registration request').props.onClick,first=click(),second=click();
  await second;h.render();assert.equal(calls,1);assert.equal(h.state().phase,'sending');
  assert.equal(h.nodes().find(n=>n.type==='fieldset').props.disabled,true);assert.ok(h.listeners.has('beforeunload'));
  finish(Response.json(receipt(reviewed())));await first;h.render();assert.equal(h.state().phase,'confirmed');
  assert.equal(h.listeners.has('beforeunload'),false);
 }finally{globalThis.fetch=oldFetch;}
});
test('unknown UI freezes original fields, retains warning through rejection, copies and retries original bytes',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch,bodies=[];
 try{
  globalThis.fetch=async(url,init)=>{
   bodies.push(init.body);if(bodies.length===1)throw Error('lost after commit');
   if(bodies.length===2)return Response.json({error:'submission_forbidden'},{status:403});
   return Response.json(receipt(reviewed(),{replayed:true,current_status:'ACTIVE'}));
  };
  await h.button('Send confirmed registration request').props.onClick();h.render();
  assert.equal(h.state().phase,'unknown');assert.equal(bodies.length,1);assert.ok(h.listeners.has('beforeunload'));
  let prevented=false;const event={preventDefault(){prevented=true;}};h.listeners.get('beforeunload')(event);
  assert.equal(prevented,true);assert.equal(event.returnValue,'');
  for(const [name,value] of [['new_id',principalId],['event_no','ADM-CHANGED'],['subject','Changed subject']])h.change(name,value);
  assert.equal(h.state().review.request.body.principal_id,newId);assert.equal(h.field('event_no').props.value,'ADM-UI-ORIGINAL');
  assert.equal(h.button('Prepare another registration with new identifiers'),undefined);
  await h.button('Copy confirmed registration request').props.onClick();h.render();
  assert.ok(h.copies[0].includes('ADM-UI-ORIGINAL'));assert.ok(h.text(h.render()).includes('Original registration request copied.'));
  h.render(false);assert.equal(h.button('Retry original registration request').props.disabled,true);
  await h.button('Retry original registration request').props.onClick();h.render(false);assert.equal(bodies.length,1);
  h.render(true);await h.button('Retry original registration request').props.onClick();h.render();
  assert.equal(h.state().phase,'unknown');assert.equal(h.state().error,'submission_forbidden');
  assert.equal(h.button('Prepare another registration with new identifiers'),undefined);
  await h.button('Retry original registration request').props.onClick();h.render();
  assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.current_status,'ACTIVE');
  assert.equal(new Set(bodies).size,1);assert.equal(h.listeners.has('beforeunload'),false);
 }finally{globalThis.fetch=oldFetch;}
});
test('known rejection permits a fresh review with new UUID/key and cleared target fields',async()=>{
 const h=harness();h.fill('PROJECT');const oldFetch=globalThis.fetch;
 try{
  globalThis.fetch=async()=>Response.json({error:'recipient_inactive'},{status:409});
  await h.button('Send confirmed registration request').props.onClick();h.render();
  assert.equal(h.state().phase,'rejected');h.button('Prepare another registration with new identifiers').props.onClick();h.render();
  assert.equal(h.state(),null);assert.notEqual(h.field('new_id').props.value,newId);
  assert.notEqual(h.field('event_no').props.value,'ADM-UI-ORIGINAL');
  assert.equal(h.field('principal_id').props.value,'');assert.equal(h.field('scope_id').props.value,'');
  assert.equal(h.field('reason').props.value,'');assert.equal(h.button('Send confirmed registration request'),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('result SSR localizes uncertainty and retry denial without arbitrary backend text',async()=>{
 const c=new RegistrationSubmission(reviewed());await c.send(true,async()=>{throw Error('lost');});
 await c.send(true,async()=>Response.json({error:'session_required'},{status:401}));
 for(const [locale,expected] of [['zh','此前结果未知的操作可能已经提交'],['en','earlier uncertain operation may have committed']]){
  const html=render(locale,React.createElement(Result,{state:c.state}));assert.ok(html.includes(expected));assert.ok(!html.includes('/account/grants/PRINCIPAL/'));
 }
 const html=render('en',React.createElement(Result,{state:{...c.state,error:'private provider text'}}));
 assert.ok(!html.includes('private provider text'));assert.ok(html.includes('The outcome is unknown.'));
});
for(const kind of ['PRINCIPAL','GLOBAL','PROJECT','SOFTWARE'])test('bilingual receipt preserves exact identifiers, applied/observed states and detail link '+kind,async()=>{
 const r=reviewed(kind),c=new RegistrationSubmission(r);await c.send(true,async()=>Response.json(receipt(r,{current_status:'ACTIVE',replayed:true})));
 for(const locale of ['zh','en']){
  const html=render(locale,React.createElement(Result,{state:c.state}));
  assert.ok(html.includes(locale==='zh'?'本次操作应用的状态':'Applied status for this operation'));
  assert.ok(html.includes(locale==='zh'?'回执中观察到的状态':'Status observed in the receipt'));
  assert.ok(html.includes('ADM-UI-ORIGINAL'));assert.ok(html.includes(newId));assert.ok(html.includes(r.initialStatus));
  assert.ok(html.includes(locale==='zh'?'仅在内存中':'only in memory'));
  if(kind==='PRINCIPAL')assert.ok(html.includes(locale==='zh'?'身份详情读取尚未开放':'Identity detail reading is not available yet'));
  else{assert.ok(html.includes('/account/grants/'+kind+'/'+newId+'?offset=0'));assert.ok(html.includes('target="_blank"'));}
 }
});
test('every allowlisted registration denial has an actual Chinese label',()=>{
 for(const errors of Object.values(registrationDenials))for(const error of errors)assert.equal(typeof registrationMessages[error],'string');
 for(const message of Object.values(registrationMessages))assert.match(dictionary[message],/[\u4e00-\u9fff]/,message);
});
