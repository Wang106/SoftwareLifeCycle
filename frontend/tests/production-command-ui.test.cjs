'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-production-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/command-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx',
 '--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/command-workbench.js')).default;
const Result=require(path.join(output,'components/production-command-result.js')).default;
const {productionCommandMessages}=require(path.join(output,'components/production-command-result.js'));
const {ProductionSubmission,productionReview}=require(path.join(output,'lib/production-command-transport.js'));
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const f=require('./fixtures/production-command.cjs'),dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const props=operation=>({initialOperation:operation,initialTarget:operation==='test-release'?f.release:operation==='deployment'?f.authorization:'DEP-原始',initialStep:'',
 initialContext:{snapshot:f.snapshot,testReleaseNo:'TR-原始',purposeScope:'SOFTWARE_TEST',actor:'Declared operator',reason:'Original reason\n原文',
 productionLine:f.line,deploymentNo:'DEP-新建',changeoverNo:'CO-原始',fromRelease:f.from,note:'Original note\n原文'},
 submissionEnabled:false,recoveryEnabled:false,governanceSubmissionEnabled:false,governanceRecoveryEnabled:false,distributionSubmissionEnabled:false,distributionRecoveryEnabled:false,productionSubmissionEnabled:true,productionRecoveryEnabled:true});
// Actual compiled component handlers with isolated hooks; not browser acceptance.
function harness(operation='test-release'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current=props(operation),clipboard=async value=>copies.push(value);
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/command-workbench.js'),'utf8'),{exports,
  require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='./production-command-result'?{__esModule:true,default:Result}:
   name==='react/jsx-runtime'||name==='next/link'?require(name):require(path.resolve(output,'components',name)),
  crypto:globalThis.crypto,window:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},
  navigator:{clipboard:{writeText:value=>clipboard(value)}},Error,JSON});
 function nodes(node){if(arguments.length===0)node=tree;if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(!node||typeof node!=='object')return[];return[node,...nodes(node.props?.children)];}
 function text(node){if(Array.isArray(node))return node.map(text).join('');if(typeof node==='string')return node;return node&&typeof node==='object'?text(node.props?.children):'';}
 function rerender(next=current){current=next;index=0;work=[];tree=exports.default(current);for(const fn of work)fn();return tree;}
 function change(name,value){nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});rerender();}
 function preview(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});rerender();}
 function check(checked=true){nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked}});rerender();}
 function button(label){return nodes().find(n=>n.type==='button'&&text(n)===label);}
 function state(){return nodes().find(n=>n.props?.state?.command)?.props.state||null;}
 rerender();return{render:rerender,change,preview,check,button,nodes,state,listeners,copies,props:()=>current,text:()=>text(tree),clipboard:fn=>{clipboard=fn;}};
}
const send='Send confirmed business request',retry='Retry original business request',query='Query original audit without resubmitting',start='Start a new request';
for(const operation of ['test-release','deployment','changeover']){
 test(operation+' defaults to bilingual preparation without a send button',()=>{
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Component,{...props(operation),productionSubmissionEnabled:false,productionRecoveryEnabled:false}));
   assert.ok(html.includes(locale==='zh'?'可准备十四类命令':'Fourteen commands can be prepared.'));assert.ok(!html.includes(locale==='zh'?'发送已确认的业务请求':send));}
 });
 test(operation+' confirmed handler sends exact original body and projects a terminal receipt',async()=>{
  const h=harness(operation);h.preview();h.check();let calls=0,original;const oldFetch=globalThis.fetch;
  try{globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/production-command');assert.equal(init.method,'POST');original=JSON.parse(init.body);
    assert.equal(original.operation,operation);assert.equal(original.target,props(operation).initialTarget);
    assert.deepEqual({...original.body,request_id:f.key},productionReview(f.command(operation)).draft.payload);return Response.json({...f.receipt(original),token:'private'});};
   const click=h.button(send).props.onClick;await click();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);
   assert.equal(h.nodes().find(n=>n.type==='fieldset').props.disabled,true);assert.equal(h.button(send),undefined);assert.equal(h.button(retry),undefined);
   await click();assert.equal(calls,1);assert.ok(!h.listeners.has('beforeunload'));h.button(start).props.onClick();h.render();h.preview();h.check();
   globalThis.fetch=async(url,init)=>{assert.notEqual(JSON.parse(init.body).body.request_id,original.body.request_id);return Response.json(f.receipt(JSON.parse(init.body)));};
   await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');
  }finally{globalThis.fetch=oldFetch;}
 });
 test(operation+' lost response preserves original bytes across target/operation refresh and explicit retry',async()=>{
  const h=harness(operation);h.preview();h.check();const oldFetch=globalThis.fetch;let body,calls=0;
  const form=h.nodes().find(n=>n.type==='form').props.onSubmit,edit=h.nodes().find(n=>n.props?.name==='target').props.onChange;
  const select=h.nodes().find(n=>n.type==='select').props.onChange;
  try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'unknown');
   const original=h.state().command;edit({target:{value:'other'}});select({target:{value:'resource'}});form({preventDefault(){}});
   h.render({...props('changeover'),initialTarget:'other',initialContext:{batch:'other'}});assert.deepEqual(h.state().command,original);
   assert.equal(h.button(start),undefined);assert.ok(h.listeners.has('beforeunload'));
   globalThis.fetch=async(url,init)=>{calls++;assert.equal(init.body,body);return Response.json(f.receipt(original));};await h.button(retry).props.onClick();h.render();
   assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
  }finally{globalThis.fetch=oldFetch;}
 });
}
test('unconfirmed, edited and stale send/confirmation handlers cannot submit',async()=>{
 const h=harness();h.preview();const oldFetch=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};assert.equal(h.button(send).props.disabled,true);await h.button(send).props.onClick();
  h.check();const stale=h.button(send).props.onClick,checkbox=h.nodes().find(n=>n.props?.type==='checkbox').props.onChange;
  h.change('target',f.snapshot);await stale();checkbox({target:{checked:true}});h.render();assert.equal(h.button(send),undefined);
  h.preview();h.check();await stale();assert.equal(calls,0);assert.equal(h.state(),null);
 }finally{globalThis.fetch=oldFetch;}
});
test('synchronous double clicks and stale form events send once and warn while sending',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;let finish,calls=0,command;
 try{globalThis.fetch=async(url,init)=>{calls++;command=JSON.parse(init.body);return new Promise(resolve=>{finish=resolve;});};
  const click=h.button(send).props.onClick,pending=click();await click();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'sending');
  assert.ok(h.listeners.has('beforeunload'));let prevented=false;const event={preventDefault(){prevented=true;}};h.listeners.get('beforeunload')(event);assert.ok(prevented);
  assert.equal(h.button(start),undefined);finish(Response.json(f.receipt(command)));await pending;h.render();assert.equal(h.state().phase,'confirmed');
 }finally{globalThis.fetch=oldFetch;}
});
test('read-only transition still queries own original audit and cannot repeat the write',async()=>{
 const h=harness('deployment');h.preview();h.check();const oldFetch=globalThis.fetch;let body,calls=0;
 try{globalThis.fetch=async(url,init)=>{body=init.body;calls++;throw Error('lost');};await h.button(send).props.onClick();h.render();
  h.render({...h.props(),productionSubmissionEnabled:false,productionRecoveryEnabled:true});assert.equal(h.button(retry).props.disabled,true);await h.button(retry).props.onClick();assert.equal(calls,1);
  globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/production-command-receipt');assert.equal(init.body,body);return Response.json(f.receipt(JSON.parse(body)));};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
 }finally{globalThis.fetch=oldFetch;}
});
test('query lock rejects simultaneous query/retry and missing audit remains unknown',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0,finish;
 try{globalThis.fetch=async()=>{calls++;throw Error('lost');};await h.button(send).props.onClick();h.render();
  const read=h.button(query).props.onClick,write=h.button(retry).props.onClick;
  globalThis.fetch=async(url)=>{calls++;assert.equal(url,'/auth/production-command-receipt');return new Promise(resolve=>{finish=resolve;});};
  const pending=read();await read();await write();h.render();assert.equal(calls,2);assert.equal(h.state().phase,'checking');assert.ok(h.listeners.has('beforeunload'));
  finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('capability closure blocks stale handlers and later denial preserves earlier unknown',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('lost');};await h.button(send).props.onClick();h.render();const write=h.button(retry).props.onClick,read=h.button(query).props.onClick;
  h.render({...h.props(),productionSubmissionEnabled:false,productionRecoveryEnabled:false});await write();await read();assert.equal(calls,1);assert.equal(h.state().phase,'unknown');
  h.render({...h.props(),productionSubmissionEnabled:true,productionRecoveryEnabled:true});globalThis.fetch=async()=>Response.json({error:'submission_conflict'},{status:409});
  await h.button(retry).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.state().error,'submission_conflict');assert.equal(h.button(start),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('first explicit rejection permits new request; subsequent query uncertainty locks it again',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;
 try{globalThis.fetch=async()=>Response.json({error:'submission_conflict'},{status:409});await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'rejected');assert.ok(h.button(start));
  globalThis.fetch=async()=>Response.json({error:'outcome_unknown'},{status:502});await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('copy synchronously blocks send/edit/new review and clipboard failure keeps manual original',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0,finish;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};h.clipboard(()=>new Promise((resolve,reject)=>{finish=reject;}));
  const stale=h.button(send).props.onClick,pending=h.button('Copy confirmed request').props.onClick();await stale();h.change('target',f.snapshot);
  h.button(start).props.onClick();h.render();assert.ok(h.button(send));assert.equal(calls,0);finish(Error('clipboard'));await pending;h.render();assert.ok(h.text().includes('Select and copy the confirmed request below.'));
 }finally{globalThis.fetch=oldFetch;}
});
test('query refresh invalidates an unsent preview and its captured send handler',async()=>{
 const h=harness();h.preview();h.check();const stale=h.button(send).props.onClick,oldFetch=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};h.render({...h.props(),initialTarget:f.snapshot});await stale();h.render();assert.equal(calls,0);assert.equal(h.button(send),undefined);}
 finally{globalThis.fetch=oldFetch;}
});
test('production preparation rejects an invalid UTC time and oversized UTF-8 body before sending',()=>{
 const h=harness('changeover');h.change('timestamp','0100-01-01T00:00:00+01:00');h.preview();assert.equal(h.button(send),undefined);
 const oversized=harness('test-release');oversized.nodes().find(n=>n.type==='textarea').props.onChange({target:{value:'中'.repeat(3000)}});oversized.render();oversized.change('testReleaseNo','中'.repeat(50));
 oversized.change('actor','中'.repeat(120));oversized.preview();assert.equal(oversized.button(send),undefined);
});
test('first-submit capability cannot enable production sends',()=>{
 const h=harness();h.render({...h.props(),submissionEnabled:true,recoveryEnabled:true,productionSubmissionEnabled:false,productionRecoveryEnabled:false});
 h.preview();h.check();assert.equal(h.button(send),undefined);assert.ok(h.button('Copy confirmed request'));
});
test('all production receipts render bilingual original states, evidence, microseconds and independent links',async()=>{
 for(const operation of ['test-release','deployment','changeover']){
  const c=new ProductionSubmission(productionReview(f.command(operation)));await c.send(true,async()=>Response.json(f.receipt(c.state.command)));
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:c.state}));
   assert.ok(html.includes(locale==='zh'?'匹配的原子审计已确认原操作':'matching atomic audit'));
   assert.ok(html.includes('/activity/'+f.eventNo(c.state.command)));assert.ok(html.includes(c.state.review.draft.trace));
   assert.ok(html.includes(operation==='test-release'?'DRAFT':operation==='deployment'?'PENDING':'COMPLETED'));
   if(operation==='test-release'){assert.ok(html.includes('/snapshots/SNAP-0001-'+f.release.slice(0,8)));assert.ok(html.includes('Original reason'));assert.ok(html.includes(locale==='zh'?'不代表测试通过':'does not prove test success'));}
   if(operation==='deployment'){assert.ok(html.includes(f.authorization));assert.ok(html.includes(f.snapshot));assert.ok(html.includes(locale==='zh'?'不代表实际安装':'does not prove installation'));}
   if(operation==='changeover'){assert.ok(html.includes(f.from));assert.ok(html.includes('Original note'));assert.ok(html.includes('2026-10-09T02:00:00.123456Z'));assert.ok(html.includes(locale==='zh'?'不代表物理刷写':'does not prove physical flashing'));}
   assert.ok(html.includes('target="_blank"'));assert.ok(html.includes('rel="noopener noreferrer"'));assert.ok(html.includes(locale==='zh'?'原操作应用的值':'original applied values'));
  }
 }
 const c=new ProductionSubmission(productionReview(f.command('changeover')));await c.send(true,async()=>{throw Error('lost');});
 await c.send(true,async()=>Response.json({error:'submission_conflict'},{status:409}));
 for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:c.state}));assert.ok(html.includes(locale==='zh'?'此前结果未知的操作可能已经提交':'earlier uncertain operation may have committed'));
  assert.ok(html.includes(locale==='zh'?'重新加载后丢失':'lost on reload'));}
 assert.ok(!render('en',React.createElement(Result,{state:{...c.state,error:'private provider text'}})).includes('private provider text'));
 for(const message of Object.values(productionCommandMessages))assert.match(dictionary[message],/[\u4e00-\u9fff]/,message);
});
test('null time and note remain explicit in the original changeover request',async()=>{
 const command=f.command('changeover');command.body.note=null;
 const c=new ProductionSubmission(productionReview(command));await c.send(true,async()=>Response.json(f.receipt(c.state.command)));
 for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:c.state}));assert.ok(html.includes('&quot;note&quot;: null'));assert.ok(html.includes('COMPLETED'));}
 assert.equal(c.state.command.body.changed_at,null);
});

test('an uncertain production request survives a first-command context and independent capability change',async()=>{
 const h=harness();h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0,body;
 try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();
  const original=h.state().command;
  h.render({...h.props(),initialOperation:'snapshot',initialTarget:f.release,initialContext:{},
   submissionEnabled:true,recoveryEnabled:true,productionSubmissionEnabled:false,productionRecoveryEnabled:false});
  assert.deepEqual(h.state().command,original);assert.equal(h.button(retry).props.disabled,true);assert.equal(h.button(query).props.disabled,true);
  await h.button(retry).props.onClick();await h.button(query).props.onClick();assert.equal(calls,1);
  h.render({...h.props(),productionRecoveryEnabled:true});
  globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/production-command-receipt');assert.equal(init.body,body);return Response.json(f.receipt(original));};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
  h.button(start).props.onClick();h.render();h.preview();h.check();globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/first-command');throw Error('lost');};
  await h.button(send).props.onClick();h.render();assert.equal(h.state().command.operation,'snapshot');
 }finally{globalThis.fetch=oldFetch;}
});
test('first and governance gates cannot enable any production command',()=>{
 for(const operation of ['test-release','deployment','changeover']){
  const h=harness(operation);h.render({...h.props(),submissionEnabled:true,recoveryEnabled:true,governanceSubmissionEnabled:true,governanceRecoveryEnabled:true,distributionSubmissionEnabled:true,distributionRecoveryEnabled:true,productionSubmissionEnabled:false,productionRecoveryEnabled:false});
  h.preview();h.check();assert.equal(h.button(send),undefined);assert.ok(h.button('Copy confirmed request'));
 }
});
test('unknown production survives governance context and capability refresh without borrowing its gate',async()=>{
 const h=harness('changeover');h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0,body;
 try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();const original=h.state().command;
  h.render({...h.props(),initialOperation:'approval',initialTarget:'APR-new',governanceSubmissionEnabled:true,governanceRecoveryEnabled:true,distributionSubmissionEnabled:true,distributionRecoveryEnabled:true,productionSubmissionEnabled:false,productionRecoveryEnabled:false});
  assert.deepEqual(h.state().command,original);await h.button(retry).props.onClick();await h.button(query).props.onClick();assert.equal(calls,1);assert.equal(h.button(start),undefined);
  h.render({...h.props(),productionRecoveryEnabled:true});globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/production-command-receipt');assert.equal(init.body,body);return Response.json(f.receipt(original));};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
 }finally{globalThis.fetch=oldFetch;}
});

test('unknown production survives distribution context without borrowing its independent gate',async()=>{
 const h=harness('changeover');h.preview();h.check();const oldFetch=globalThis.fetch;let calls=0,body;
 try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();const original=h.state().command;
  h.render({...h.props(),initialOperation:'delivery',initialTarget:f.release,distributionSubmissionEnabled:true,distributionRecoveryEnabled:true,productionSubmissionEnabled:false,productionRecoveryEnabled:false});
  assert.deepEqual(h.state().command,original);await h.button(retry).props.onClick();await h.button(query).props.onClick();assert.equal(calls,1);assert.equal(h.button(start),undefined);
  h.render({...h.props(),productionRecoveryEnabled:true});globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/production-command-receipt');assert.equal(init.body,body);return Response.json(f.receipt(original));};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
 }finally{globalThis.fetch=oldFetch;}
});
