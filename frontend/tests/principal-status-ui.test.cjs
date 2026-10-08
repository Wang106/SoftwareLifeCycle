'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-principal-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/principal-status-draft.ts','components/principal-status-preparation.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const Result=require(path.join(output,'components/principal-status-result.js')).default;
const {PrincipalSubmission,principalSubmissionMessages}=require(path.join(output,'lib/principal-status-transport.js'));
const dictionary=require('../lib/i18n/zh.json');
const draft=require(path.join(output,'lib/principal-status-draft.js'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/principal-status-preparation.js')).default;
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const {preparePrincipalStatus:prepare,confirmPrincipalStatus:confirm,exportPrincipalStatus:exportRequest}=draft;
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id='12345678-1234-1234-1234-123456789abc',other='23456789-1234-1234-1234-123456789abc';
const target={id,principalType:'USER',status:'ACTIVE',historyStatus:'ACTIVE',protectedAdministrator:false,issuerMatchesConfiguration:true};
const reviewed=(value=target)=>confirm(prepare(value,'ADM-UI-1','Controlled UI reason'),true);
const receipt=(r,extra={})=>({principal_id:r.target.id,audit_event_no:r.request.body.event_no,
 applied_status:r.request.body.status,current_status:r.request.body.status,replayed:false,
 revoked_browser_sessions:r.request.body.status==='DISABLED'?2:0,...extra});
const render=(locale,component)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},component));
// Isolated hooks execute actual compiled handlers, not browser/DOM acceptance.
function harness(enabled=true,initial=target){
 const values=[],effects=[],copies=[],listeners=new Map();let index=0,tree,work=[],current={...initial},clipboard=async value=>{copies.push(value);};
 const hooks={
  useState(initial){const i=index++;if(!(i in values))values[i]=initial;return [values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}
 };
 const exports={};
 vm.runInNewContext(fs.readFileSync(path.join(output,'components/principal-status-preparation.js'),'utf8'),{
  exports,require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:
   name==='./principal-status-result'?{__esModule:true,default:Result}:
   name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),
  crypto:globalThis.crypto,window:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},navigator:{clipboard:{writeText:value=>clipboard(value)}},Error
 });
 function nodes(node){if(arguments.length===0)node=tree;if(Array.isArray(node))return node.flatMap(nodes);if(!node||typeof node!=='object')return [];return [node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;return node&&typeof node==='object'?text(node.props?.children):'';}
 function render(next=current,nextEnabled=enabled){current=next;enabled=nextEnabled;index=0;work=[];tree=exports.default({target:current,submissionEnabled:enabled});for(const fn of work)fn();return tree;}
 function change(name,value){nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});render();}
 function preview(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});render();}
 function check(checked){nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked}});render();}
 function button(label){return nodes().find(n=>n.type==='button'&&text(n)===label);}
 function state(){return nodes().find(n=>n.type===Result)?.props.state||null;}
 function fill(){change('event_no','ADM-UI-1');change('reason','Controlled UI reason');preview();check(true);}
 render();
 return {render,change,preview,check,button,fill,copies,nodes,state,listeners,text:()=>text(tree),clipboard:fn=>{clipboard=fn;}};
}
test('bilingual initial page keeps default-disabled preparation and enabled capability without unconfirmed sending',()=>{
 for(const locale of ['zh','en'])for(const enabled of [false,true]){
  const html=render(locale,React.createElement(Component,{target,submissionEnabled:enabled}));
  assert.ok(html.includes(enabled?(locale==='zh'?'此环境可进行受控提交':'Controlled submission is available'):
   (locale==='zh'?'本表单不会修改身份':'Preparation only.')));
  assert.ok(!html.includes('Send confirmed identity request'));assert.ok(!html.includes('发送已确认的身份请求'));
 }
});
test('unconfirmed, edited and default-disabled handlers cannot send',async()=>{
 const oldFetch=globalThis.fetch;let calls=0;
 try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  const h=harness();h.change('event_no','ADM-UI-1');h.change('reason','Controlled UI reason');h.preview();
  assert.equal(h.button('Send confirmed identity request').props.disabled,true);
  await h.button('Send confirmed identity request').props.onClick();assert.equal(calls,0);
  h.check(true);h.change('reason','Changed controlled reason');assert.equal(h.button('Send confirmed identity request'),undefined);
  const disabled=harness(false);disabled.fill();assert.equal(disabled.button('Send confirmed identity request'),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
for(const principalType of ['USER','SERVICE'])for(const status of ['ACTIVE','DISABLED'])
test('actual confirmed '+principalType+' '+status+' form sends exact command and becomes terminal',async()=>{
 const value={...target,principalType,status,historyStatus:status},h=harness(true,value);h.fill();
 const oldFetch=globalThis.fetch;let calls=0;
 try{
  globalThis.fetch=async(url,init)=>{
   calls++;assert.equal(url,'/auth/principal-status');assert.equal(init.method,'POST');
   assert.deepEqual(JSON.parse(init.body),{principal_id:id,...reviewed(value).request.body});
   return Response.json(receipt(reviewed(value),{token:'private',subject:'private'}));
  };
  const click=h.button('Send confirmed identity request').props.onClick;await click();h.render();
  assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);
  assert.equal(h.nodes().find(n=>n.type==='fieldset').props.disabled,true);
  assert.equal(h.button('Send confirmed identity request'),undefined);await click();assert.equal(calls,1);
 }finally{globalThis.fetch=oldFetch;}
});
test('synchronous duplicate click lock and sending unload warning use one request',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch;let finish,calls=0;
 try{
  globalThis.fetch=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};
  const click=h.button('Send confirmed identity request').props.onClick,first=click();await click();h.render();
  assert.equal(calls,1);assert.equal(h.state().phase,'sending');assert.ok(h.listeners.has('beforeunload'));
  const event={preventDefault(){this.prevented=true;}};h.listeners.get('beforeunload')(event);
  assert.equal(event.prevented,true);assert.equal(event.returnValue,'');
  h.change('event_no','ADM-CHANGED');assert.equal(h.state().review.request.body.event_no,'ADM-UI-1');
  finish(Response.json(receipt(reviewed())));await first;h.render();assert.equal(h.listeners.has('beforeunload'),false);
 }finally{globalThis.fetch=oldFetch;}
});
test('unknown recovery survives changed UUID, blocked new snapshots, disabled capability and denied retry',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch,bodies=[];
 try{
  globalThis.fetch=async(url,init)=>{
   bodies.push(init.body);if(bodies.length===1)throw Error('lost after commit');
   if(bodies.length===2)return Response.json({error:'session_required'},{status:401});
   return Response.json(receipt(reviewed(),{replayed:true,current_status:'ACTIVE'}));
  };
  await h.button('Send confirmed identity request').props.onClick();h.render();assert.equal(h.state().phase,'unknown');
  h.change('event_no','ADM-CHANGED');h.change('reason','Changed controlled reason');h.preview();h.check(false);
  for(const patch of [{id:other},{protectedAdministrator:true},{historyStatus:'DISABLED'}]){
   h.render({...target,...patch});h.render();assert.equal(h.state().review.target.id,id);
   assert.ok(h.button('Copy confirmed identity request'));assert.equal(h.button('Prepare another operation with a new audit number'),undefined);
  }
  await h.button('Copy confirmed identity request').props.onClick();h.render();
  assert.equal(h.copies[0],exportRequest(reviewed()));assert.ok(h.text().includes('Original identity request copied.'));
  h.render(undefined,false);assert.equal(h.button('Retry original identity request').props.disabled,true);
  await h.button('Retry original identity request').props.onClick();assert.equal(bodies.length,1);
  assert.equal(h.state().phase,'unknown');assert.ok(h.listeners.has('beforeunload'));
  h.render(undefined,true);await h.button('Retry original identity request').props.onClick();h.render();
  assert.equal(h.state().phase,'unknown');assert.equal(h.state().error,'session_required');
  assert.equal(h.button('Prepare another operation with a new audit number'),undefined);
  await h.button('Retry original identity request').props.onClick();h.render();
  assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.current_status,'ACTIVE');
  assert.equal(new Set(bodies).size,1);assert.equal(h.listeners.has('beforeunload'),false);
 }finally{globalThis.fetch=oldFetch;}
});
test('known first rejection permits a new key and requires fresh detail review',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch;
 try{
  globalThis.fetch=async()=>Response.json({error:'principal_status_conflict'},{status:409});
  await h.button('Send confirmed identity request').props.onClick();h.render();assert.equal(h.state().phase,'rejected');
  assert.equal(h.listeners.has('beforeunload'),false);
  h.button('Prepare another operation with a new audit number').props.onClick();h.render();
  assert.equal(h.state(),null);assert.notEqual(h.nodes().find(n=>n.props?.name==='event_no').props.value,'ADM-UI-1');
  assert.equal(h.nodes().find(n=>n.props?.name==='reason').props.value,'');assert.equal(h.button('Send confirmed identity request'),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('stale send handlers cannot use refreshed targets or a closed capability',async()=>{
 const oldFetch=globalThis.fetch;let calls=0;
 try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  for(const patch of [{id:other},{protectedAdministrator:true},{historyStatus:'DISABLED'}]){
   const h=harness();h.fill();const click=h.button('Send confirmed identity request').props.onClick;
   h.render({...target,...patch});await click();h.render();assert.equal(h.state(),null);
  }
  const h=harness();h.fill();const click=h.button('Send confirmed identity request').props.onClick;
  h.render(undefined,false);await click();assert.equal(calls,0);
 }finally{globalThis.fetch=oldFetch;}
});
test('pending copy synchronously blocks stale send/edit/preview and duplicate copy handlers',async()=>{
 const h=harness();h.fill();let finish;const oldFetch=globalThis.fetch;let calls=0,copies=0;
 try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  h.clipboard(()=>{copies++;return new Promise(resolve=>{finish=resolve;});});
  const click=h.button('Send confirmed identity request').props.onClick,copy=h.button('Copy confirmed identity request').props.onClick;
  const pending=copy();await copy();await click();h.change('event_no','ADM-CHANGED');h.preview();
  assert.equal(copies,1);assert.equal(calls,0);assert.equal(h.state(),null);
  assert.equal(h.nodes().find(n=>n.props?.name==='event_no').props.value,'ADM-UI-1');
  finish();await pending;h.render();assert.equal(h.button('Send confirmed identity request').props.disabled,false);
 }finally{globalThis.fetch=oldFetch;}
});
test('unknown request remains manually copyable after clipboard denial and target refresh',async()=>{
 const h=harness();h.fill();const oldFetch=globalThis.fetch;
 try{
  globalThis.fetch=async()=>{throw Error('lost');};await h.button('Send confirmed identity request').props.onClick();h.render();
  h.render({...target,protectedAdministrator:true});h.clipboard(async()=>{throw Error('clipboard denied');});
  await h.button('Copy confirmed identity request').props.onClick();h.render();
  assert.ok(h.text().includes('Clipboard unavailable'));assert.ok(h.text().includes('ADM-UI-1'));
  assert.equal(h.state().phase,'unknown');assert.equal(h.button('Copy confirmed identity request').props.disabled,false);
 }finally{globalThis.fetch=oldFetch;}
});
test('bilingual uncertainty retains earlier possible commit through a later allowlisted denial',async()=>{
 const c=new PrincipalSubmission(reviewed());await c.send(true,async()=>{throw Error('lost');});
 await c.send(true,async()=>Response.json({error:'admin_principal_protected'},{status:403}));
 for(const locale of ['zh','en']){
  const html=render(locale,React.createElement(Result,{state:c.state}));
  assert.ok(html.includes(locale==='zh'?'此前结果未知的操作可能已经提交':'earlier uncertain operation may have committed'));
  assert.ok(html.includes(locale==='zh'?'仅在内存中':'only in memory'));
 }
 const html=render('en',React.createElement(Result,{state:{...c.state,error:'private provider text'}}));
 assert.ok(!html.includes('private provider text'));
});
test('bilingual receipt distinguishes applied/observed status and actual revoked count with exact independent link',async()=>{
 const c=new PrincipalSubmission(reviewed());await c.send(true,async()=>Response.json(receipt(reviewed(),{current_status:'ACTIVE',replayed:true})));
 for(const locale of ['zh','en']){
  const html=render(locale,React.createElement(Result,{state:c.state}));
  for(const label of locale==='zh'?['本次操作应用的状态','回执中观察到的状态','本次操作撤销的浏览器会话数','打开当前身份详情与历史']:
   ['Applied status for this operation','Status observed in the receipt','Browser sessions revoked by this operation','Open current identity detail and history'])assert.ok(html.includes(label));
  assert.ok(html.includes('ADM-UI-1'));assert.ok(html.includes('&quot;revoked_browser_sessions&quot;: 2'));
  assert.ok(html.includes('/account/principals/'+id+'?offset=0'));assert.ok(html.includes('target="_blank"'));
  assert.ok(html.includes('rel="noopener noreferrer"'));assert.ok(html.includes(locale==='zh'?'不能据此证明原请求':'do not prove the result of the original request'));
 }
});
test('identity submission errors all have Chinese labels and UI stores no browser persistence or credentials',()=>{
 for(const message of Object.values(principalSubmissionMessages))assert.match(dictionary[message],/[\u4e00-\u9fff]/,message);
 for(const file of ['principal-status-preparation.tsx','principal-status-result.tsx']){
  const source=fs.readFileSync('components/'+file,'utf8');assert.ok(!/localStorage|sessionStorage|Authorization|Bearer|setInterval/.test(source));
 }
});

test('old send and confirmation handlers cannot revive an edited or newly reviewed request',async()=>{
 const oldFetch=globalThis.fetch;let calls=0;
 try{
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  const h=harness();h.fill();const click=h.button('Send confirmed identity request').props.onClick;
  const checkbox=h.nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange;
  h.change('reason','A changed controlled reason');await click();checkbox({target:{checked:true}});h.render();
  assert.equal(h.state(),null);assert.equal(h.button('Copy confirmed identity request'),undefined);
  h.preview();h.check(true);await click();h.render();assert.equal(calls,0);assert.equal(h.state(),null);
 }finally{globalThis.fetch=oldFetch;}
});
