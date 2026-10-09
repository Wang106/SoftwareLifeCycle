'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-recovery-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/command-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx',
 '--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/command-workbench.js')).default;
const Result=require(path.join(output,'components/evidence-resource-command-result.js')).default;
const {evidenceResourceMessages}=require(path.join(output,'components/evidence-resource-command-result.js'));
const {EvidenceSubmission,evidenceReview}=require(path.join(output,'lib/evidence-command-transport.js'));
const {ResourceSubmission,resourceReview}=require(path.join(output,'lib/resource-command-transport.js'));
const commandReview=c=>c.operation==='resource'?resourceReview(c):evidenceReview(c);
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const evidence=require('./fixtures/evidence-command.cjs'),resource=require('./fixtures/resource-command.cjs');
const f={...evidence,command:operation=>operation==='resource'?resource.command():evidence.command(operation),receipt:c=>c.operation==='resource'?resource.receipt(c):evidence.receipt(c)};
const dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const props=operation=>{const c=f.command(operation),b=c.body;return{initialOperation:operation,initialTarget:c.target,initialStep:'',
 initialContext:{release:b.release_id,snapshot:b.snapshot_id,decision:b.decision,evidence:b.evidence_ref??'',criterion:b.criterion_id,dvp:b.dvp_item_id,
 actor:b.actor_name,reason:b.reason,entityType:b.entity_type,title:b.title,locationKind:b.location_kind,location:b.location,description:b.description},
 submissionEnabled:false,recoveryEnabled:false,governanceSubmissionEnabled:false,governanceRecoveryEnabled:false,distributionSubmissionEnabled:false,distributionRecoveryEnabled:false,productionSubmissionEnabled:false,productionRecoveryEnabled:false,
 evidenceSubmissionEnabled:operation!=='resource',evidenceRecoveryEnabled:operation!=='resource',resourceSubmissionEnabled:operation==='resource',resourceRecoveryEnabled:operation==='resource'};};
const submitUrl=operation=>operation==='resource'?'/auth/resource-command':'/auth/evidence-command';
const recoverUrl=operation=>submitUrl(operation)+'-receipt';
// Actual compiled component handlers with isolated hooks; not browser acceptance.
function harness(operation='impact'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current=props(operation),clipboard=async value=>copies.push(value);
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/command-workbench.js'),'utf8'),{exports,
  require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='./evidence-resource-command-result'?{__esModule:true,default:Result}:
   name==='react/jsx-runtime'||name==='next/link'?require(name):require(path.resolve(output,'components',name)),
  crypto:globalThis.crypto,window:{location:{origin:'https://lifecycle.example'},addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)},
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

const {businessReview,exportBusinessRecovery,parseBusinessRecovery}=require(path.join(output,'lib/business-recovery.js'));
const origin='https://lifecycle.example',stage='Stage original request for audit query only',copyRecovery='Copy original recovery text';
const groups=[['first',['snapshot','actual','batch']],['governance',['approval','decision']],['distribution',['delivery','distribution','authorization']],
 ['production',['test-release','deployment','changeover']],['evidence',['impact','acceptance']],['resource',['resource']]];
function gates(group,write=true,read=true){return Object.fromEntries(['first','governance','distribution','production','evidence','resource'].flatMap(g=>[[g==='first'?'submissionEnabled':g+'SubmissionEnabled',g===group&&write],[g==='first'?'recoveryEnabled':g+'RecoveryEnabled',g===group&&read]]));}
for(const [group,operations] of groups)for(const operation of operations){
 const fixture=require('./fixtures/'+group+'-command.cjs');
 test(operation+' actual import handlers stage without network and query only after an explicit action',async()=>{
  const text=exportBusinessRecovery(businessReview(fixture.command(operation)),origin),command=parseBusinessRecovery(text,origin),h=harness();
  const oldFetch=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};h.render({...h.props(),...gates(group)});h.change('recoveryText',text);
   h.button(stage).props.onClick();h.render();assert.equal(calls,0);assert.equal(h.state().phase,'unknown');assert.equal(h.state().error,'outcome_unknown');
   assert.equal(h.button(send),undefined);assert.equal(h.button(retry),undefined);assert.equal(h.button(start),undefined);assert.deepEqual(h.state().command,command);
   assert.equal(h.nodes().find(n=>n.type==='form').props.hidden,true);
   h.render({...h.props(),...gates(group,false,true)});globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/'+group+'-command-receipt');assert.equal(init.body,JSON.stringify(command));return Response.json(fixture.receipt(command));};
   await h.button(query).props.onClick();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');assert.ok(h.button(start));
   h.button(start).props.onClick();h.render();assert.equal(h.state(),null);
  }finally{globalThis.fetch=oldFetch;}
 });
}
test('imported unknown survives unrelated gates/context and later denial without a write path',async()=>{
 const fixture=require('./fixtures/production-command.cjs'),text=exportBusinessRecovery(businessReview(fixture.command('changeover')),origin),h=harness();
 const oldFetch=globalThis.fetch;let calls=0;
 try{h.render({...h.props(),...gates('production')});h.change('recoveryText',text);h.button(stage).props.onClick();h.render();const original=h.state().command,read=h.button(query).props.onClick;
  h.render({...h.props(),initialOperation:'resource',initialTarget:resource.target,...gates('resource')});
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await read();await h.button(query).props.onClick();assert.equal(calls,0);assert.equal(h.button(retry),undefined);assert.deepEqual(h.state().command,original);
  h.render({...h.props(),productionRecoveryEnabled:true});globalThis.fetch=async()=>{calls++;return Response.json({error:'submission_forbidden'},{status:403});};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(calls,1);assert.equal(h.button(start),undefined);
 }finally{globalThis.fetch=oldFetch;}
});
test('invalid, foreign and tampered recovery never stages or fetches',()=>{
 const text=exportBusinessRecovery(businessReview(f.command('impact')),origin);
 for(const invalid of ['null',text.replace(origin,'https://other.example'),text.replace('"version": 1','"version": 2'),text.replace('"origin":','"token":"secret","origin":')]){
  const h=harness();h.change('recoveryText',invalid);h.button(stage).props.onClick();h.render();assert.equal(h.state(),null);assert.ok(h.text().includes('Nothing was sent.'));
 }
});
test('an existing prepared or uncertain operation cannot be overwritten by import or stale handlers',async()=>{
 const h=harness('resource'),stageOld=h.button(stage).props.onClick,text=exportBusinessRecovery(businessReview(f.command('impact')),origin),oldFetch=globalThis.fetch;
 try{h.preview();h.check();h.change('recoveryText',text);stageOld();h.render();assert.equal(h.state(),null);
  globalThis.fetch=async()=>{throw Error('lost');};await h.button(send).props.onClick();h.render();const original=h.state().command;
  h.change('recoveryText',text);stageOld();h.render();assert.deepEqual(h.state().command,original);assert.equal(h.button(stage).props.disabled,true);
 }finally{globalThis.fetch=oldFetch;}
});
test('recovery export clipboard lock prevents sends and retains manual canonical text on failure',async()=>{
 const h=harness('impact');h.preview();h.check();let reject,exported,calls=0;const oldFetch=globalThis.fetch;
 try{h.clipboard(value=>{exported=value;return new Promise((resolve,fail)=>reject=fail);});globalThis.fetch=async()=>{calls++;throw Error('unexpected');};
  const pending=h.button(copyRecovery).props.onClick();await h.button(send).props.onClick();h.change('target','other');h.button(start).props.onClick();h.render();
  assert.ok(parseBusinessRecovery(exported,origin));assert.equal(calls,0);assert.ok(h.nodes().some(n=>n.type==='pre'&&n.props.children===exported));
  reject(Error('clipboard'));await pending;h.render();assert.ok(h.text().includes('Select and copy the confirmed request below.'));
 }finally{globalThis.fetch=oldFetch;}
});
test('recovery UI is bilingual and explicitly warns about query-only restoration and private business text',()=>{
 for(const locale of ['zh','en']){const html=render(locale,React.createElement(Component,props('impact')));
  assert.ok(html.includes(locale==='zh'?'恢复原业务请求':'Restore an original business request'));
  assert.ok(html.includes(locale==='zh'?'不会自动发送或查询':'never sends or queries automatically'));
  assert.ok(html.includes(locale==='zh'?'私有引用路径':'private reference paths'));
 }
});
