'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-correction-recovery-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/acceptance-correction-workbench.tsx','components/change-coverage-collections.tsx','app/commands/page.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/acceptance-correction-workbench.js')).default;
const Result=require(path.join(output,'components/acceptance-correction-result.js')).default;
const {AcceptanceCorrectionSubmission,confirmAcceptanceCorrection}=require(path.join(output,'lib/acceptance-correction-transport.js'));
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const f=require('./fixtures/acceptance-correction-ui.cjs'),props=f.props,dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
// Compiled component event handlers with isolated hooks, not real browser acceptance.
function harness(action='SUPERSEDE'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current=props(action),clipboard=async value=>copies.push(value);
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/acceptance-correction-workbench.js'),'utf8'),{exports,
  require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='./acceptance-correction-result'?{__esModule:true,default:Result}:
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

const {exportAcceptanceCorrectionRecovery:exportText,parseAcceptanceCorrectionRecovery:parse,importAcceptanceCorrectionRecovery:restore,correctionRecoveryTextLimit:limit}=require(path.join(output,'lib/acceptance-correction-recovery.js'));
const origin='https://lifecycle.example';
const send='Send confirmed correction request',retry='Retry original correction request',query='Query original audit without resubmitting',start='Start a new request',copy='Copy correction recovery text',importButton='Import correction recovery without sending';
const exported=(action='SUPERSEDE')=>exportText(confirmAcceptanceCorrection(f.command(action),true),origin);
function stage(h,text){h.change('importText',text);h.button(importButton).props.onClick();h.render();}
for(const action of ['SUPERSEDE','WITHDRAW']){
 test(action+' strict canonical export/import preserves predecessor and original bytes, import has zero network',async()=>{
  const text=exported(action),c=parse(text,origin);assert.deepEqual(c,f.command(action));assert.deepEqual(parse(JSON.stringify(JSON.parse(text)),origin),c);
  const old=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};const s=restore(text,origin);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');assert.equal(s.send,undefined);
   await s.recover(true,async(url,init)=>{calls++;assert.equal(url,'/auth/acceptance-correction-receipt');assert.equal(init.body,JSON.stringify(c));return Response.json(f.receipt(c));});
   assert.equal(s.state.phase,'confirmed');await s.recover(true,async()=>{throw Error('terminal');});assert.equal(calls,1);
  }finally{globalThis.fetch=old;}
 });
 test(action+' imported UI is read-only even with submission capability, queries original audit and resets only confirmed',async()=>{
  const h=harness(action),old=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};stage(h,exported(action));assert.equal(calls,0);assert.equal(h.state().phase,'unknown');
   assert.equal(h.button(send),undefined);assert.equal(h.button(retry),undefined);assert.equal(h.button(start),undefined);assert.ok(h.nodes().find(n=>n.type==='form').props.hidden);
   globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/acceptance-correction-receipt');assert.equal(init.body,JSON.stringify(f.command(action)));return Response.json(f.receipt(JSON.parse(init.body)));};
   await h.button(query).props.onClick();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');h.button(start).props.onClick();h.render();assert.equal(h.state(),null);
   h.preview();h.check();assert.ok(h.button(send));
  }finally{globalThis.fetch=old;}
 });
 test(action+' query refusal, missing audit, read-only capability and concurrent clicks retain original uncertainty',async()=>{
  const h=harness(action),old=globalThis.fetch;let calls=0,finish;
  try{stage(h,exported(action));const click=h.button(query).props.onClick;
   h.render({...h.props(),submissionEnabled:false,recoveryEnabled:false});await click();assert.equal(h.state().phase,'unknown');
   h.render({...h.props(),recoveryEnabled:true});globalThis.fetch=async(url)=>{calls++;assert.equal(url,'/auth/acceptance-correction-receipt');return new Promise(r=>finish=r);};
   const p=h.button(query).props.onClick();await h.button(query).props.onClick();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'checking');
   finish(Response.json({error:'session_required'},{status:401}));await p;h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
   h.render({...h.props(),initialContext:props('WITHDRAW').initialContext});assert.equal(h.state().command.body.action,action);
   globalThis.fetch=async()=>Response.json({error:'outcome_unknown'},{status:502});await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(retry),undefined);
  }finally{globalThis.fetch=old;}
 });
 test(action+' manual export after lost response restores a new component without a write',async()=>{
  const h=harness(action),old=globalThis.fetch;let calls=0,body;
  try{h.preview();h.check();globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();
   await h.button(copy).props.onClick();assert.equal(calls,1);assert.deepEqual(parse(h.copies[0],origin),JSON.parse(body));
   const next=harness();stage(next,h.copies[0]);assert.equal(calls,1);assert.equal(next.button(send),undefined);
   globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/acceptance-correction-receipt');assert.equal(init.body,body);return Response.json(f.receipt(JSON.parse(body)));};
   await next.button(query).props.onClick();next.render();assert.equal(calls,2);assert.equal(next.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
}
test('origin/version/format/field/canonical-order/credential and duplicate-key mutations are rejected',()=>{
 const text=exported();const mutations=[d=>d.format='slc-business-recovery',d=>d.version=2,d=>d.origin='https://other.example',d=>d.operation='acceptance',d=>d.receipt={confirmed:true},
  d=>d.token='secret',d=>d.actor_principal_id=f.principal,d=>d.body.actor_name+=' ',d=>d.body.reason+=' ',d=>d.body.request_id=d.body.request_id.toUpperCase(),d=>d.target+=' ',
  d=>d.body.action='ASSIGN',d=>d.predecessor.action='WITHDRAW',d=>d.predecessor.id=f.key,d=>d.predecessor.criterion_id=f.key,d=>d.predecessor.token='secret',
  d=>d.body.reason='\ud800',d=>d.body.reason='中'.repeat(3000),d=>d.body=Object.fromEntries(Object.entries(d.body).reverse())];
 for(const mutate of mutations){const d=JSON.parse(text);mutate(d);assert.equal(parse(JSON.stringify(d,null,2),origin),null);}
 for(const [key,value]of [['version','1'],['origin',JSON.stringify(origin)],['request_id',JSON.stringify(f.key)],['previous_action','"ASSIGN"']]){
  if(!text.includes('"'+key+'":'))continue;assert.equal(parse(text.replace('"'+key+'":','"'+key+'": '+value+', "'+key+'":'),origin),null);
 }
 assert.equal(parse(text,origin+'/'),null);assert.equal(parse(text,'https://user:pass@lifecycle.example'),null);assert.equal(parse(text,'http://remote.example'),null);
 assert.equal(parse(' '.repeat(limit+1),origin),null);assert.equal(parse('中'.repeat(limit/2),origin),null);assert.equal(parse('null',origin),null);
 assert.throws(()=>exportText(confirmAcceptanceCorrection(f.command(),false),origin));assert.throws(()=>exportText({...confirmAcceptanceCorrection(f.command(),true),command:{...f.command(),target:' SCR '}},origin));
 for(const site of ['http://localhost:3000','http://127.0.0.1','http://[::1]:8080','https://lifecycle.example'])assert.ok(parse(exportText(confirmAcceptanceCorrection(f.command(),true),site),site));
});
test('stale import handlers and attempted controller refuse replacement; invalid text causes no network',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};stage(h,'invalid');assert.equal(h.state(),null);assert.ok(h.text().includes('Nothing was sent'));
  h.change('importText',exported());const stale=h.button(importButton).props.onClick;h.change('importText',exported('WITHDRAW'));stale();h.render();assert.equal(h.state(),null);
  h.button(importButton).props.onClick();h.render();assert.equal(h.state().command.body.action,'WITHDRAW');stale();h.render();assert.equal(h.state().command.body.action,'WITHDRAW');assert.equal(calls,0);
 }finally{globalThis.fetch=old;}
});
test('manual export lock blocks submit/query/import and failed clipboard leaves copyable original envelope',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0,finish;
 try{h.preview();h.check();const original=h.nodes().find(n=>n.type==='code').props.children;h.clipboard(()=>new Promise((r,j)=>finish=j));
  globalThis.fetch=async()=>{calls++;throw Error('unexpected');};const click=h.button(send).props.onClick,p=h.button(copy).props.onClick();await click();h.change('reason','other');h.render();assert.equal(calls,0);
  finish(Error('clipboard'));await p;h.render();assert.ok(h.text().includes('Select and copy the confirmed request below.'));assert.ok(h.text().includes('slc-acceptance-correction-recovery'));assert.ok(h.text().includes(original));
 }finally{globalThis.fetch=old;}
});
test('actual import/export UI text and original result are bilingual without rewriting raw recovery',()=>{
 for(const locale of ['zh','en']){const html=render(locale,React.createElement(Component,{...props(),submissionEnabled:false,recoveryEnabled:false}));
  assert.ok(html.includes(locale==='zh'?'恢复原更正审计查询':'Restore an original correction audit query'));assert.ok(html.includes(locale==='zh'?'导入更正恢复且不发送':importButton));}
 for(const key of ['Copy correction recovery text','Recovery text contains the original correction and predecessor, not proof of execution. Store it securely.',
 'Imported correction recovery is read-only. Nothing was sent; explicitly query your original audit after signing in.','Restore an original correction audit query',
 'Paste correction recovery text exported from this exact site. Import does not send, retry or query automatically.','Correction recovery text',importButton])assert.match(dictionary[key],/[\u4e00-\u9fff]/,key);
 const s=restore(exported(),origin);for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:s.state}));assert.ok(html.includes(locale==='zh'?'重新加载后丢失':'lost on reload'));assert.ok(html.includes('/activity/EVT-AC-'+f.key));}
});
test('editable export is not proof: changed actor/reason/request cannot confirm another original audit',async()=>{
 const original=f.command();
 for(const patch of [{actor_name:'Another declared actor'},{reason:'Another reason'},{request_id:f.replacement}]){
  const command={...original,body:{...original.body,...patch}},s=restore(exportText(confirmAcceptanceCorrection(command,true),origin),origin);
  await s.recover(true,async()=>Response.json(f.receipt(original)));assert.equal(s.state.phase,'unknown');assert.equal(s.state.receipt,null);assert.equal(s.send,undefined);
 }
});
