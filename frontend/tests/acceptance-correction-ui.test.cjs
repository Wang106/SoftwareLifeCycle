'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-correction-ui-'));
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
const send='Send confirmed correction request',retry='Retry original correction request',query='Query original audit without resubmitting',start='Start a new request',copy='Copy confirmed correction request';
for(const action of ['SUPERSEDE','WITHDRAW']){
 test(action+' defaults to bilingual disabled preparation',()=>{
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Component,{...props(action),submissionEnabled:false,recoveryEnabled:false}));
   assert.ok(html.includes(locale==='zh'?'更正验收标准与 DVP 的关系':'Correct an acceptance-to-DVP relationship'));
   assert.ok(!html.includes(locale==='zh'?dictionary[send]:send));assert.ok(html.includes(f.predecessor));}
 });
 test(action+' exact confirmation sends once and projects terminal original receipt',async()=>{
  const h=harness(action);h.preview();assert.ok(h.button(send).props.disabled);h.check();const old=globalThis.fetch;let calls=0,c;
  try{globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/acceptance-correction');c=JSON.parse(init.body);
    assert.deepEqual({...c,body:{...c.body,request_id:f.key}},f.command(action));assert.notEqual(c.body.request_id,f.predecessor);return Response.json({...f.receipt(c),token:'private',effective:false});};
   const click=h.button(send).props.onClick;await click();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);
   await click();assert.equal(calls,1);assert.equal(h.button(retry),undefined);assert.ok(!h.listeners.has('beforeunload'));h.button(start).props.onClick();h.render();h.preview();h.check();
   globalThis.fetch=async(url,init)=>{assert.notEqual(JSON.parse(init.body).body.request_id,c.body.request_id);return Response.json(f.receipt(JSON.parse(init.body)));};
   await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
 test(action+' unknown retains bytes across refreshed context and explicit retry',async()=>{
  const h=harness(action);h.preview();h.check();const old=globalThis.fetch;let body,calls=0;
  try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'unknown');
   const c=h.state().command;assert.equal(h.button(start),undefined);assert.ok(h.listeners.has('beforeunload'));
   h.change('predecessor',f.key);h.render({...h.props(),initialContext:{...props('WITHDRAW').initialContext,target:'another'}});
   assert.deepEqual(h.state().command,c);globalThis.fetch=async(url,init)=>{calls++;assert.equal(init.body,body);return Response.json(f.receipt(c));};
   await h.button(retry).props.onClick();h.render();assert.equal(calls,2);assert.equal(h.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
 test(action+' bilingual result uses original audit/DVP links and excludes current evidence',async()=>{
  const s=new AcceptanceCorrectionSubmission(confirmAcceptanceCorrection(f.command(action),true));
  await s.send(true,async()=>Response.json({...f.receipt(s.state.command),effective:true,current_status:'PASSED',token:'private'}));
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:s.state}));
   assert.ok(html.includes(locale==='zh'?dictionary['Acceptance correction result']:'Acceptance correction result'));
   assert.ok(html.includes('/activity/EVT-AC-'+f.key));assert.ok(html.includes('/activity/EVT-AC-'+f.predecessor));
   assert.ok(html.includes('/testing/dvp/'+f.dvp));assert.equal(html.includes('/testing/dvp/'+f.replacement),action==='SUPERSEDE');
   assert.ok(html.includes('target="_blank"'));assert.ok(html.includes('rel="noopener noreferrer"'));assert.ok(!html.includes('private'));assert.ok(!html.includes('current_status'));
   assert.ok(html.includes(locale==='zh'?'此结果只确认原替代或撤销操作':'This confirms the original replacement or withdrawal only'));
  }
 });
}
test('unchecked, edited and stale context handlers cannot submit',async()=>{
 const h=harness();h.preview();const old=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await h.button(send).props.onClick();h.check();
  const stale=h.button(send).props.onClick,check=h.nodes().find(n=>n.props?.type==='checkbox').props.onChange;
  h.change('reason','changed');await stale();check({target:{checked:true}});h.render();assert.equal(h.button(send),undefined);
  h.preview();h.check();await stale();assert.equal(calls,0);
  const newer=h.button(send).props.onClick;h.render({...h.props(),initialContext:{...h.props().initialContext,predecessor:f.key}});await newer();h.render();assert.equal(calls,0);assert.equal(h.button(send),undefined);
 }finally{globalThis.fetch=old;}
});
test('synchronous send/query/retry double clicks interlock',async()=>{
 const h=harness();h.preview();h.check();const old=globalThis.fetch;let calls=0,finish;
 try{globalThis.fetch=async()=>{calls++;return new Promise(r=>finish=r);};const click=h.button(send).props.onClick,pending=click();await click();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'sending');
  finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;h.render();
  const read=h.button(query).props.onClick,write=h.button(retry).props.onClick,p=read();await read();await write();h.render();assert.equal(calls,2);assert.equal(h.state().phase,'checking');
  finish(Response.json({error:'outcome_unknown'},{status:502}));await p;h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
 }finally{globalThis.fetch=old;}
});
test('stale capability handlers are blocked; read-only recovery preserves original bytes',async()=>{
 const h=harness();h.preview();h.check();const old=globalThis.fetch;let calls=0,body;
 try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();
  const write=h.button(retry).props.onClick,read=h.button(query).props.onClick;
  h.render({...h.props(),submissionEnabled:false,recoveryEnabled:false});await write();await read();assert.equal(calls,1);
  h.render({...h.props(),recoveryEnabled:true});await write();assert.equal(calls,1);
  globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/acceptance-correction-receipt');assert.equal(init.body,body);return Response.json(f.receipt(JSON.parse(body)));};
  await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(calls,2);
 }finally{globalThis.fetch=old;}
});
test('unknown survives later refusal; only initial rejection permits new request',async()=>{
 const old=globalThis.fetch;
 try{const h=harness();h.preview();h.check();globalThis.fetch=async()=>{throw Error('lost');};await h.button(send).props.onClick();h.render();
  globalThis.fetch=async()=>Response.json({error:'submission_conflict'},{status:409});await h.button(retry).props.onClick();h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
  for(const locale of ['zh','en'])assert.ok(render(locale,React.createElement(Result,{state:h.state()})).includes(locale==='zh'?'此前结果未知的操作可能已经提交':'earlier uncertain operation may have committed'));
  const rejected=harness();rejected.preview();rejected.check();await rejected.button(send).props.onClick();rejected.render();assert.equal(rejected.state().phase,'rejected');assert.ok(rejected.button(start));
 }finally{globalThis.fetch=old;}
});
test('copy lock blocks send/edit/reset; clipboard failure preserves manual original',async()=>{
 const h=harness();h.preview();h.check();const old=globalThis.fetch;let calls=0,finish;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};h.clipboard(()=>new Promise((r,j)=>finish=j));const click=h.button(send).props.onClick,pending=h.button(copy).props.onClick();
  await click();h.change('reason','other');h.button(start).props.onClick();h.render();assert.ok(h.button(send));assert.equal(calls,0);
  finish(Error('clipboard'));await pending;h.render();assert.ok(h.text().includes('Select and copy the confirmed request below.'));
  await click();h.render();assert.equal(h.state().phase,'unknown');assert.notEqual(h.state().command.body.reason,'other');
 }finally{globalThis.fetch=old;}
});
test('invalid predecessor/action, blank reason and oversized UTF8 fail preparation',()=>{
 for(const [field,value]of [['predecessor','invalid'],['previousAction','WITHDRAW'],['criterion','invalid'],['reason',' '],['reason','中'.repeat(3000)],['dvp',f.dvp]]){
  const h=harness();h.change(field,value);h.preview();assert.equal(h.button(send),undefined);assert.ok(h.text().includes('context or request is invalid'));
 }
});
test('new presentation strings are translated; unexpected provider text stays hidden',()=>{
 for(const file of ['acceptance-correction-workbench.tsx','acceptance-correction-result.tsx']){
  const source=fs.readFileSync('components/'+file,'utf8');for(const match of source.matchAll(/<Localized>\{'([^']+)'\}<\/Localized>/g))assert.match(dictionary[match[1]],/[\u4e00-\u9fff]/,match[1]);
 }
 const s=new AcceptanceCorrectionSubmission(confirmAcceptanceCorrection(f.command(),true));
 assert.ok(!render('en',React.createElement(Result,{state:{...s.state,phase:'unknown',error:'private_provider_error'}})).includes('private_provider_error'));
});
function mocked(file,replacements){const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,file),'utf8'),{exports,require:name=>name in replacements?replacements[name]:name==='react/jsx-runtime'||name==='next/link'?require(name):require(path.resolve(output,path.dirname(file),name)),process:{env:{}},URLSearchParams,encodeURIComponent,Promise});return exports.default;}
test('commands page independently gates correction, unique session and read-only query; ordinary ASSIGN stays separate',async()=>{
 const gates=['firstSubmissionConfigured','governanceSubmissionConfigured','distributionSubmissionConfigured','productionSubmissionConfigured','evidenceSubmissionConfigured','resourceSubmissionConfigured'];
 for(const [enabled,cookieCount,readOnly]of [[false,1,false],[true,0,false],[true,2,false],[true,1,true],[true,1,false]]){
  let resolved=0;const auth={authConfig:async()=>({session:{}}),acceptanceCorrectionSubmissionConfigured:()=>enabled,...Object.fromEntries(gates.map(n=>[n,()=>false]))};
  const Page=mocked('app/commands/page.js',{'next/headers':{cookies:async()=>({getAll:()=>Array(cookieCount).fill({value:'opaque'})})},
   '../../lib/browser-auth':auth,'../../lib/browser-session':{SESSION_COOKIE:'session',resolveSession:async()=>{resolved++;return {read_only_mode:readOnly};}}});
  const tree=await Page({searchParams:Promise.resolve({target:'SCR-1',criterion:f.criterion,predecessor:f.predecessor,previous_dvp:f.dvp,previous_action:'SUPERSEDE',correction_action:'WITHDRAW'})});
  const children=tree.props.children,correction=children.find(n=>n?.props?.initialContext?.predecessor),ordinary=children.find(n=>n?.props?.initialOperation);
  assert.equal(correction.props.submissionEnabled,enabled&&cookieCount===1&&!readOnly);assert.equal(correction.props.recoveryEnabled,enabled&&cookieCount===1);
  assert.equal(resolved,enabled&&cookieCount===1?1:0);assert.equal(ordinary.props.evidenceSubmissionEnabled,false);
  assert.equal(correction.props.initialContext.previousAction,'SUPERSEDE');assert.equal(correction.props.initialContext.action,'WITHDRAW');
 }
});
test('coverage entry links bind effective predecessor; ended history has no correction entry',async()=>{
 const data={change_id:f.entity,request_no:'SCR-1',release_id:'none',snapshot_id:'none',candidate_count:0,gap_count:0,summary:{acceptance:{total:1},change_points:{total:0},issues:{total:0},dvp:{total:1}}};
 for(const [action,effective,expected]of [['ASSIGN',true,2],['SUPERSEDE',true,2],['WITHDRAW',false,0],['ASSIGN',false,0],['ASSIGN',undefined,0]]){
  const Page=mocked('components/change-coverage-collections.js',{'../lib/api':{apiGet:async url=>{
   const kind=url.includes('/groups/')?url.split('/groups/')[1].split('/')[0]:url.includes('/assignments?')?'acceptance':undefined;
   return {...data,kind,group_id:f.criterion,ref:'AC-1',description:'original',item_count:1,assignment_count:1,total:1,next_offset:null,
    items:url.includes('/assignments?')?[{id:f.predecessor,dvp_item_id:f.dvp,action,effective,reason:'original'}]:[]};
  }}});
  const node=await Page({data,search:{group_kind:'acceptance',group_id:f.criterion}}),html=render('en',node);
  const links=[...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&')).filter(u=>u.startsWith('/commands?')&&u.includes('predecessor='));
  assert.equal(links.length,expected);for(const link of links){const q=new URL(link,'https://example.test').searchParams;assert.equal(q.get('predecessor'),f.predecessor);assert.equal(q.get('previous_dvp'),f.dvp);assert.equal(q.get('previous_action'),action);assert.equal(q.get('criterion'),f.criterion);assert.equal(q.get('target'),'SCR-1');}
 }
});
test('copy blocks during sending and preserves canonical original bytes after unknown',async()=>{
 const h=harness();h.preview();h.check();const old=globalThis.fetch;let finish,body;
 try{globalThis.fetch=async(url,init)=>{body=init.body;return new Promise(r=>finish=r);};const pending=h.button(send).props.onClick();h.render();
  await h.button(copy).props.onClick();assert.equal(h.copies.length,0);
  finish(Response.json({error:'outcome_unknown'},{status:502}));await pending;h.render();await h.button(copy).props.onClick();assert.equal(h.copies[0],body);
 }finally{globalThis.fetch=old;}
});
