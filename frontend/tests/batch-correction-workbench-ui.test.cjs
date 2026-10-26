'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-batch-correction-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/batch-correction-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/batch-correction-workbench.js')).default,Result=require(path.join(output,'components/batch-correction-workbench.js')).BatchCorrectionResult;
const {LanguageProvider}=require(path.join(output,'components/localized.js')),dictionary=require('../lib/i18n/zh.json'),ts=require('typescript');
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const id=n=>`${n.repeat(8)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(12)}`;
const context={deployment_no:'DEP-原始',batch_no:'BATCH-原始',batch_id:id('1'),release_id:id('2'),snapshot_id:id('3'),history_state:'IMPORTED_CORRECTED',expected_revision:2,predecessor_id:id('4'),started_at:'2026-10-26T01:00:00.123456Z',ended_at:null,changeover_id:id('5'),note:'Original note'};
const props={deploymentNo:context.deployment_no,batchNo:context.batch_no,contextEnabled:true,submissionEnabled:true,recoveryEnabled:true};
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
const load='Load private correction context',send='Send confirmed batch correction',retry='Retry original batch correction',query='Query original audit without resubmitting',reset='Reload context for a new correction';
function receipt(c){return {operation:c.operation,target:c.target,request_id:c.body.request_id,audit_event_no:'EVT-BC-'+c.body.request_id.replaceAll('-',''),result:{batch_id:c.context.batch_id,batch_no:c.target.batch_no,release_id:c.context.release_id,snapshot_id:c.context.snapshot_id,started_at:c.body.started_at??c.context.started_at,ended_at:c.body.ended_at??c.context.ended_at,changeover_id:c.body.changeover_id,note:c.body.note,correction_reason:c.body.correction_reason,revision:c.body.expected_revision+1,predecessor_id:c.body.predecessor_id}};}
// Compiled handlers plus real transport, isolated hooks; not browser acceptance.
function harness(initial=props){
 const values=[],effects=[],listeners=new Map();let index=0,tree,work=[],current=initial;
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/batch-correction-workbench.js'),'utf8'),{exports,require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='react/jsx-runtime'||name==='next/link'?require(name):require(path.resolve(output,'components',name)),fetch:(...args)=>globalThis.fetch(...args),AbortSignal,crypto:globalThis.crypto,window:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},Error,JSON});
 function nodes(node){if(arguments.length===0)node=tree;if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(!node||typeof node!=='object')return[];return[node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;return node&&typeof node==='object'?text(node.props?.children):'';}
 function rerender(next=current){current=next;index=0;work=[];tree=exports.default(current);for(const fn of work)fn();return tree;}
 function change(name,value){nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});rerender();}
 function prepare(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});rerender();}
 function check(checked=true){nodes().find(n=>n.props?.type==='checkbox').props.onChange({target:{checked}});rerender();}
 function button(label){return nodes().find(n=>n.type==='button'&&text(n)===label);}
 function state(){return nodes().find(n=>n.props?.state?.command)?.props.state||null;}
 rerender();return {render:rerender,change,prepare,check,button,nodes,state,listeners,props:()=>current,text:()=>text(tree)};
}
async function ready(h){const old=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/batch-correction-context');assert.deepEqual(JSON.parse(init.body),{deployment_no:context.deployment_no,batch_no:context.batch_no});return Response.json(context);};await h.button(load).props.onClick();h.render();h.change('correction_reason','Original reason\n原文');h.prepare();}finally{globalThis.fetch=old;}}
for(const locale of ['zh','en'])test(`${locale}: default disabled has no unauthenticated context/form/send`,async()=>{
 const p={...props,contextEnabled:false,submissionEnabled:false,recoveryEnabled:false},html=render(locale,React.createElement(Component,p));
 for(const label of ['Correct recorded batch facts','Public history is not permission. Load private authenticated context before preparing a correction.','Batch correction submission is disabled or unavailable for this session.'])assert.ok(html.includes(locale==='zh'?dictionary[label]:label),label);
 assert.ok(!html.includes('<form'));assert.ok(!html.includes(send));assert.ok(!html.includes(context.batch_id));const h=harness(p);let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await h.button(load).props.onClick();assert.equal(calls,0);}finally{globalThis.fetch=old;}
});
test('private context loads explicitly and confirmation freezes before single send',async()=>{
 const h=harness();await ready(h);assert.equal(h.state(),null);assert.equal(h.button(send),undefined);h.check(false);assert.equal(h.state(),null);h.check();assert.equal(h.state().phase,'idle');const frozen=h.state().command;h.change('note','should not replace');assert.equal(h.state().command,frozen);
 let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/batch-correction');const c=JSON.parse(init.body);assert.deepEqual(c,frozen);return Response.json({...receipt(c),token:'not-shown'});};const click=h.button(send).props.onClick;await click();h.render();await click();assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);assert.equal(h.button(retry),undefined);}finally{globalThis.fetch=old;}
});
test('null time preserves context while null note and changeover clear',async()=>{
 const h=harness();await ready(h);h.change('started_at','');h.change('ended_at','');h.change('note','');h.change('changeover_id','');h.prepare();h.check();const c=h.state().command;assert.equal(c.body.started_at,null);assert.equal(c.body.ended_at,null);assert.equal(c.body.note,null);assert.equal(c.body.changeover_id,null);assert.equal(c.context.started_at,context.started_at);assert.ok(h.text().includes('Blank start or end time preserves the current recorded time; it does not clear it.'));
});
test('unknown retains original bytes across route and capability changes',async()=>{
 const h=harness();await ready(h);h.check();let body,calls=0;const old=globalThis.fetch;
 try{globalThis.fetch=async(_url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();const c=h.state().command;assert.equal(h.state().phase,'unknown');assert.equal(h.button(reset),undefined);assert.equal(h.button(load),undefined);assert.ok(h.listeners.has('beforeunload'));
  h.render({...props,deploymentNo:'NEW',batchNo:'OTHER',submissionEnabled:false});assert.equal(h.state().command,c);assert.equal(h.button(retry).props.disabled,true);await h.button(retry).props.onClick();assert.equal(calls,1);
  h.render({...props,deploymentNo:'NEW',batchNo:'OTHER'});globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/batch-correction');assert.equal(init.body,body);return Response.json(receipt(c));};await h.button(retry).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
 }finally{globalThis.fetch=old;}
});
test('read-only transition queries original audit; later denial cannot erase unknown',async()=>{
 const h=harness();await ready(h);h.check();const old=globalThis.fetch;let body;
 try{globalThis.fetch=async(_url,init)=>{body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render({...props,submissionEnabled:false});
  globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/batch-correction-receipt');assert.equal(init.body,body);return Response.json({error:'submission_forbidden'},{status:403});};await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(reset),undefined);
  const c=h.state().command;globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/batch-correction-receipt');assert.equal(init.body,body);return Response.json(receipt(c));};await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');
 }finally{globalThis.fetch=old;}
});
test('known stale rejection requires new private context before a new request',async()=>{
 const h=harness();await ready(h);h.check();const old=globalThis.fetch;try{globalThis.fetch=async()=>Response.json({error:'version_conflict'},{status:409});await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'rejected');assert.equal(h.button(retry),undefined);h.button(reset).props.onClick();h.render();assert.equal(h.state(),null);assert.equal(h.nodes().find(n=>n.type==='form'),undefined);assert.ok(h.button(load));}finally{globalThis.fetch=old;}
});
test('context load doubleclick and stale navigation response do not overwrite another target',async()=>{
 const h=harness();let finish,calls=0;const old=globalThis.fetch;
 try{globalThis.fetch=async()=>{calls++;return new Promise(resolve=>{finish=resolve;});};const click=h.button(load).props.onClick,pending=click();await click();h.render({...props,batchNo:'NEW'});finish(Response.json(context));await pending;h.render();assert.equal(calls,1);assert.equal(h.nodes().find(n=>n.type==='form'),undefined);assert.equal(h.state(),null);}finally{globalThis.fetch=old;}
});
test('foreign and malformed private context never opens the form',async()=>{
 for(const value of [{...context,batch_no:'OTHER'},null,{...context,expected_revision:-1}]){const h=harness(),old=globalThis.fetch;try{globalThis.fetch=async()=>Response.json(value);await h.button(load).props.onClick();h.render();assert.equal(h.nodes().find(n=>n.type==='form'),undefined);assert.ok(h.text().includes('Private correction context could not be loaded. Nothing was sent.'));}finally{globalThis.fetch=old;}}
});
test('synchronous duplicate send interlocks',async()=>{
 const h=harness();await ready(h);h.check();let finish,calls=0,c;const old=globalThis.fetch;
 try{globalThis.fetch=async(_url,init)=>{calls++;c=JSON.parse(init.body);return new Promise(resolve=>{finish=resolve;});};const click=h.button(send).props.onClick,pending=click();await click();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'sending');assert.equal(h.button(reset),undefined);finish(Response.json(receipt(c)));await pending;h.render();assert.equal(h.state().phase,'confirmed');}finally{globalThis.fetch=old;}
});
test('bilingual original receipt escapes raw evidence and links original audit',async()=>{
 const h=harness();await ready(h);h.change('note','Note');h.change('correction_reason','<script>raw</script>');h.prepare();h.check();const old=globalThis.fetch;
 try{globalThis.fetch=async(_url,init)=>Response.json(receipt(JSON.parse(init.body)));await h.button(send).props.onClick();h.render();for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:h.state()}));assert.ok(html.includes(locale==='zh'?dictionary['Batch correction result']:'Batch correction result'));assert.ok(html.includes('>Note<'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(html.includes('/activity/EVT-BC-'));assert.ok(html.includes('target="_blank"'));}}finally{globalThis.fetch=old;}
});
test('server page only enables unique current USER session and exposes booleans',async()=>{
 const file=path.resolve('app/deployments/[id]/batches/[batchNo]/correct/page.tsx'),code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 async function run(configured,values,identity){let cookieCalls=0,sessionCalls=0,seen;const m={exports:{}};
  new Function('require','module','exports',code)(name=>name==='next/headers'?{cookies:async()=>{cookieCalls++;return{getAll:()=>values};}}:name==='next/link'?({children})=>children:name.endsWith('/browser-auth')?{authConfig:async()=>({session:{}}),batchCorrectionSubmissionConfigured:()=>configured}:name.endsWith('/browser-session')?{SESSION_COOKIE:'private-cookie',resolveSession:async()=>{sessionCalls++;return identity;}}:name.endsWith('/batch-correction-workbench')?{__esModule:true,default:p=>{seen=p;return React.createElement('div');}}:name.endsWith('/localized')?{Localized:({children})=>children}:require(name),m,m.exports);
  renderToStaticMarkup(await m.exports.default({params:Promise.resolve({id:'DEP',batchNo:'BATCH'})}));return {seen,cookieCalls,sessionCalls};}
 const disabled=await run(false,[{value:'secret'}],null);assert.equal(disabled.cookieCalls,0);assert.equal(disabled.seen.contextEnabled,false);
 const ambiguous=await run(true,[{value:'a'},{value:'b'}],null);assert.equal(ambiguous.sessionCalls,0);assert.equal(ambiguous.seen.submissionEnabled,false);
 const active=await run(true,[{value:'secret'}],{principal:{principal_type:'USER'},read_only_mode:false});assert.equal(active.seen.submissionEnabled,true);assert.equal(active.seen.recoveryEnabled,true);assert.ok(!JSON.stringify(active.seen).includes('secret'));
 const readonly=await run(true,[{value:'secret'}],{principal:{principal_type:'USER'},read_only_mode:true});assert.equal(readonly.seen.contextEnabled,true);assert.equal(readonly.seen.submissionEnabled,false);assert.equal(readonly.seen.recoveryEnabled,true);
 const service=await run(true,[{value:'secret'}],{principal:{principal_type:'SERVICE'},read_only_mode:false});assert.equal(service.seen.contextEnabled,false);
});
