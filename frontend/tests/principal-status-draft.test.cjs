'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-principal-draft-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'lib/principal-status-draft.ts','components/principal-status-preparation.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const draft=require(path.join(output,'lib/principal-status-draft.js'));
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/principal-status-preparation.js')).default;
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const {preparePrincipalStatus:prepare,confirmPrincipalStatus:confirm,exportPrincipalStatus:exportRequest}=draft;
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id='12345678-1234-1234-1234-123456789abc',other='23456789-1234-1234-1234-123456789abc';
const target={id,principalType:'USER',status:'ACTIVE',historyStatus:'ACTIVE',protectedAdministrator:false,issuerMatchesConfiguration:true};
for(const principalType of ['USER','SERVICE'])for(const status of ['ACTIVE','DISABLED']){
 test('exact status API request: '+principalType+' '+status,()=>{
  const review=prepare({...target,principalType,status,historyStatus:status,id:id.toUpperCase()},'ADM:001','  测试身份状态变更原因  ');
  assert.throws(()=>exportRequest(review),/Confirm/);
  assert.deepEqual(JSON.parse(exportRequest(confirm(review,true))),{method:'POST',
   path:'/api/v1/security/admin/principals/'+id+'/status',
   body:{event_no:'ADM:001',expected_status:status,status:status==='ACTIVE'?'DISABLED':'ACTIVE',reason:'测试身份状态变更原因'}});
  assert.equal(review.target.principalType,principalType);
 });
}
test('protected admins, mismatched snapshots and malformed targets fail before preparation',()=>{
 for(const patch of [{id:'../admin'},{principalType:'BOT'},{protectedAdministrator:true},
  {protectedAdministrator:'false'},{issuerMatchesConfiguration:1},{status:'SUSPENDED'},{historyStatus:'DISABLED'}])
  assert.throws(()=>prepare({...target,...patch},'ADM-1','Controlled reason'));
});
test('issuer mismatch is advisory and never injected into exact body',()=>{
 const review=prepare({...target,issuerMatchesConfiguration:false,issuer:'private-issuer',subject:'private-subject',token:'secret'},'ADM-1','Controlled reason');
 assert.equal(review.target.issuerMatchesConfiguration,false);
 const exported=exportRequest(confirm(review,true));
 for(const marker of ['issuer','subject','token','actor','principalType','historyStatus','protectedAdministrator'])assert.ok(!exported.includes(marker));
 assert.equal(Object.hasOwn(review.target,'token'),false);
});
test('audit keys preserve exact accepted API boundaries',()=>{
 for(const key of ['', '/bad','.bad','bad key','x'.repeat(51),'key/secret'])assert.throws(()=>prepare(target,key,'Controlled reason'),/Audit number/);
 for(const key of ['A','A'.repeat(50),'ADM:1_key-2.3'])assert.equal(prepare(target,key,'Controlled reason').request.body.event_no,key);
});
test('reason validation follows bounded printable Unicode code points',()=>{
 for(const reason of ['four','  abc  ','x'.repeat(501),'reason\ncontrol','reason\u007fcontrol'])assert.throws(()=>prepare(target,'ADM-1',reason),/Reason/);
 for(const reason of ['x'.repeat(5),'x'.repeat(500),'😀'.repeat(500)])assert.equal(prepare(target,'ADM-1',reason).request.body.reason,reason);
 assert.throws(()=>prepare(target,'ADM-1','😀'.repeat(501)),/Reason/);
});
test('frozen review isolates caller mutation and exports stable retry bytes',()=>{
 const source={...target},review=confirm(prepare(source,'ADM-1','Controlled reason'),true),before=exportRequest(review);
 source.id=other;source.status='DISABLED';
 assert.equal(exportRequest(review),before);
 assert.throws(()=>{review.request.body.event_no='OTHER';},TypeError);
 assert.throws(()=>{review.target.id=other;},TypeError);
 assert.throws(()=>exportRequest(confirm(review,false)),/Confirm/);
});
const render=(locale,value)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},React.createElement(Component,{target:value})));
test('bilingual initial preparation has session consequences and no transport controls',()=>{
 assert.ok(render('zh',target).includes('准备身份状态变更'));
 assert.ok(render('en',target).includes('Enabling does not restore old sessions'));
 for(const locale of ['zh','en']){
  const html=render(locale,target);
  assert.ok(html.includes('<form'));assert.ok(!html.includes('method="post"'));
  assert.ok(!html.includes('type="checkbox"'));
  for(const field of ['issuer','subject','actor','token','password','status','principal_id'])assert.ok(!html.includes('name="'+field+'"'));
 }
 const source=fs.readFileSync('components/principal-status-preparation.tsx','utf8');
 assert.ok(!/fetch\(|localStorage|sessionStorage|Authorization|Bearer/.test(source));
});
test('blocked snapshots render informative bilingual messages without preparation forms',()=>{
 for(const [patch,label] of [[{protectedAdministrator:true},'separate recovery procedure'],[{historyStatus:'DISABLED'},'Refresh identity detail']]){
  const value={...target,...patch};
  assert.ok(render('en',value).includes(label));assert.ok(!render('en',value).includes('<form'));
  assert.ok(!render('zh',value).includes('<form'));
 }
 assert.ok(render('en',{...target,issuerMatchesConfiguration:false}).includes('Issuer mismatch is informational'));
});
// Deterministic handlers with isolated hooks; this is not real browser acceptance.
function harness(){
 const values=[],effects=[],copies=[];let index=0,tree,work=[],current={...target},clipboard=async value=>{copies.push(value);};
 const hooks={
  useState(initial){const i=index++;if(!(i in values))values[i]=initial;return [values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}
 };
 const exports={};
 vm.runInNewContext(fs.readFileSync(path.join(output,'components/principal-status-preparation.js'),'utf8'),{
  exports,require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:
   name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),
  crypto:globalThis.crypto,navigator:{clipboard:{writeText:value=>clipboard(value)}},Error
 });
 function nodes(node){if(arguments.length===0)node=tree;if(Array.isArray(node))return node.flatMap(nodes);if(!node||typeof node!=='object')return [];return [node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;return node&&typeof node==='object'?text(node.props?.children):'';}
 function render(next=current){current=next;index=0;work=[];tree=exports.default({target:current});for(const fn of work)fn();return tree;}
 function change(name,value){nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});render();}
 function preview(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});render();}
 function check(checked){nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked}});render();}
 function button(label){return nodes().find(n=>n.type==='button'&&text(n)===label);}
 function fill(){change('event_no','ADM-UI-1');change('reason','Controlled UI reason');preview();check(true);}
 render();
 return {render,change,preview,check,button,fill,copies,nodes,text:()=>text(tree),clipboard:fn=>{clipboard=fn;}};
}
test('actual handlers require confirmation, invalidate on edit and retain exact copy bytes',async()=>{
 const h=harness();h.change('event_no','ADM-UI-1');h.change('reason','Controlled UI reason');h.preview();
 assert.equal(h.button('Copy confirmed identity request').props.disabled,true);
 await h.button('Copy confirmed identity request').props.onClick();assert.equal(h.copies.length,0);
 h.check(true);await h.button('Copy confirmed identity request').props.onClick();h.render();
 const original=h.copies[0];assert.equal(JSON.parse(original).body.event_no,'ADM-UI-1');
 await h.button('Copy confirmed identity request').props.onClick();h.render();assert.equal(h.copies[1],original);
 h.check(false);assert.equal(h.button('Copy confirmed identity request').props.disabled,true);
 h.check(true);h.change('reason','Changed controlled reason');assert.equal(h.button('Copy confirmed identity request'),undefined);
 h.preview();assert.equal(h.button('Copy confirmed identity request').props.disabled,true);
});
test('target refresh immediately hides frozen request and requires a new preview',()=>{
 for(const patch of [{id:other},{principalType:'SERVICE'},{status:'DISABLED',historyStatus:'DISABLED'},
  {protectedAdministrator:true},{historyStatus:'DISABLED'},{issuerMatchesConfiguration:false}]){
  const h=harness();h.fill();assert.ok(h.button('Copy confirmed identity request'));
  h.render({...target,...patch});assert.equal(h.button('Copy confirmed identity request'),undefined);
  h.render();assert.equal(h.button('Copy confirmed identity request'),undefined);
 }
});
test('generating another audit key revokes the old confirmation',()=>{
 const h=harness();h.fill();h.button('Generate audit number').props.onClick();h.render();
 assert.equal(h.button('Copy confirmed identity request'),undefined);
 assert.match(h.nodes().find(n=>n.props?.name==='event_no').props.value,/^ADM-[0-9a-f-]{36}$/);
});
test('clipboard failure retains confirmed exact preview for manual copying',async()=>{
 const h=harness();h.fill();h.clipboard(async()=>{throw Error('permission denied');});
 await h.button('Copy confirmed identity request').props.onClick();h.render();
 assert.ok(h.text().includes('Clipboard unavailable'));assert.ok(h.text().includes('ADM-UI-1'));
 assert.equal(h.button('Copy confirmed identity request').props.disabled,false);
});
test('refresh during pending copy clears preview and ignores stale completion message',async()=>{
 const h=harness();h.fill();let finish;h.clipboard(()=>new Promise(resolve=>{finish=resolve;}));
 const pending=h.button('Copy confirmed identity request').props.onClick();h.render();
 assert.equal(h.button('Copy confirmed identity request').props.disabled,true);
 h.render({...target,id:other});h.render();finish();await pending;h.render();
 assert.equal(h.button('Copy confirmed identity request'),undefined);
 assert.ok(!h.text().includes('Identity request copied'));
});
