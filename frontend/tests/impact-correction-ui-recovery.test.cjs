'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-correction-recovery-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/impact-correction-workbench.tsx','components/issue-collections.tsx','app/issues/[id]/impact/[releaseId]/page.tsx','app/commands/page.tsx',
 '--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/impact-correction-workbench.js')).default;
const Result=require(path.join(output,'components/impact-correction-result.js')).default;
const {ImpactCorrectionSubmission,confirmImpactCorrection}=require(path.join(output,'lib/impact-correction-transport.js'));
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const f=require('./fixtures/impact-correction-ui.cjs'),props=f.props,dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
// Compiled component event handlers with isolated hooks, not real browser acceptance.
function harness(action='NEEDS_REVIEW'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current=props(action),clipboard=async value=>copies.push(value);
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/impact-correction-workbench.js'),'utf8'),{exports,
  require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='./impact-correction-result'?{__esModule:true,default:Result}:
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

const {exportImpactCorrectionRecovery:exportText,parseImpactCorrectionRecovery:parse,importImpactCorrectionRecovery:restore,impactCorrectionRecoveryTextLimit:limit}=require(path.join(output,'lib/impact-correction-recovery.js'));
const origin='https://lifecycle.example';
const send='Send confirmed correction request',retry='Retry original correction request',query='Query original audit without resubmitting',start='Start a new request',copy='Copy correction recovery text',importButton='Import correction recovery without sending';
const exported=(decision='NEEDS_REVIEW')=>exportText(confirmImpactCorrection(f.command(decision),true),origin);
function stage(h,text){h.change('importText',text);h.button(importButton).props.onClick();h.render();}
for(const decision of ['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW']){
 test(decision+' bilingual preparation has independent disabled gate and separate reasons',()=>{
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Component,{...props(decision),submissionEnabled:false,recoveryEnabled:false}));
   assert.ok(html.includes(locale==='zh'?'替代一个影响判断':'Replace an impact judgment'));assert.ok(html.includes(f.predecessor));
   assert.ok(html.includes('name="correctionReason"'));assert.ok(html.includes('name="reason"'));assert.ok(!html.includes(locale==='zh'?dictionary[send]:send));assert.ok(!html.includes('WITHDRAW'));
  }
 });
 test(decision+' exact confirmation sends once and confirms only original whitelisted receipt',async()=>{
  const h=harness(decision);h.preview();assert.equal(h.button(send).props.disabled,true);h.check();const old=globalThis.fetch;let calls=0,c;
  try{globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/impact-correction');c=JSON.parse(init.body);
   assert.deepEqual({...c,body:{...c.body,request_id:f.key}},f.command(decision));assert.notEqual(c.body.request_id,f.predecessor);
   return Response.json({...f.receipt(c),token:'private',effective:false});};
   const click=h.button(send).props.onClick;await click();h.render();assert.equal(h.state().phase,'confirmed');assert.equal(h.state().receipt.token,undefined);
   await click();assert.equal(calls,1);assert.equal(h.button(retry),undefined);assert.ok(!h.listeners.has('beforeunload'));
   h.button(start).props.onClick();h.render();h.preview();h.check();globalThis.fetch=async(url,init)=>{assert.notEqual(JSON.parse(init.body).body.request_id,c.body.request_id);return Response.json(f.receipt(JSON.parse(init.body)));};
   await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
 test(decision+' lost result retains original bytes across context refresh and explicit retry',async()=>{
  const h=harness(decision),old=globalThis.fetch;let body;h.preview();h.check();
  try{globalThis.fetch=async(url,init)=>{body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();
   assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);assert.ok(h.listeners.has('beforeunload'));const c=h.state().command;
   h.change('correctionReason','other');h.render({...h.props(),initialContext:{...props().initialContext,target:'other',predecessor:f.key}});
   assert.deepEqual(h.state().command,c);globalThis.fetch=async(url,init)=>{assert.equal(init.body,body);return Response.json(f.receipt(c));};
   await h.button(retry).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
 test(decision+' original result is bilingual with exact context/audit/historical snapshot links',async()=>{
  const s=new ImpactCorrectionSubmission(confirmImpactCorrection(f.command(decision),true));
  await s.send(true,async()=>Response.json({...f.receipt(s.state.command),token:'private',current_status:'PASSED',replayed:true}));
  for(const locale of ['zh','en']){const html=render(locale,React.createElement(Result,{state:s.state}));
   assert.ok(html.includes(locale==='zh'?'影响更正结果':'Impact correction result'));assert.ok(html.includes('/activity/EVT-IMPACT-'+f.key));assert.ok(html.includes('/activity/EVT-IMPACT-'+f.predecessor));
   assert.ok(html.includes('/issues/'+encodeURIComponent(s.state.command.target)+'/impact/'+f.release+'?snapshot_id='+f.snapshot));
   assert.ok(html.includes('/snapshots/'+encodeURIComponent(s.state.receipt.result.snapshot_no)));assert.ok(html.includes('target="_blank"'));assert.ok(html.includes('rel="noopener noreferrer"'));
   for(const text of ['private','current_status','replayed'])assert.ok(!html.includes(text));
  }
 });
 test(decision+' strict manual recovery preserves nullable evidence and import never writes',async()=>{
  const text=exported(decision),c=parse(text,origin);assert.deepEqual(c,f.command(decision));assert.deepEqual(parse(JSON.stringify(JSON.parse(text)),origin),c);
  const old=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};const s=restore(text,origin);assert.equal(calls,0);assert.equal(s.state.phase,'unknown');assert.equal(s.send,undefined);assert.ok(Object.isFrozen(s));
   await s.recover(true,async(url,init)=>{calls++;assert.equal(url,'/auth/impact-correction-receipt');assert.equal(init.body,JSON.stringify(c));return Response.json(f.receipt(c));});
   assert.equal(s.state.phase,'confirmed');await s.recover(true,async()=>{throw Error('terminal');});assert.equal(calls,1);
  }finally{globalThis.fetch=old;}
 });
 test(decision+' imported UI has no send or retry and queries original audit only',async()=>{
  const h=harness(decision),old=globalThis.fetch;let calls=0;
  try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};stage(h,exported(decision));assert.equal(calls,0);assert.equal(h.state().phase,'unknown');
   for(const label of [send,retry,start])assert.equal(h.button(label),undefined);assert.ok(h.nodes().find(n=>n.type==='form').props.hidden);
   globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/impact-correction-receipt');assert.equal(init.body,JSON.stringify(f.command(decision)));return Response.json(f.receipt(JSON.parse(init.body)));};
   await h.button(query).props.onClick();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');h.button(start).props.onClick();h.render();h.preview();h.check();assert.ok(h.button(send));
  }finally{globalThis.fetch=old;}
 });
 test(decision+' export after lost response restores a new component without business resubmission',async()=>{
  const h=harness(decision),old=globalThis.fetch;let calls=0,body;h.preview();h.check();
  try{globalThis.fetch=async(url,init)=>{calls++;body=init.body;throw Error('lost');};await h.button(send).props.onClick();h.render();await h.button(copy).props.onClick();
   assert.equal(calls,1);assert.deepEqual(parse(h.copies[0],origin),JSON.parse(body));const next=harness();stage(next,h.copies[0]);assert.equal(calls,1);assert.equal(next.button(send),undefined);
   globalThis.fetch=async(url,init)=>{calls++;assert.equal(url,'/auth/impact-correction-receipt');assert.equal(init.body,body);return Response.json(f.receipt(JSON.parse(body)));};
   await next.button(query).props.onClick();next.render();assert.equal(calls,2);assert.equal(next.state().phase,'confirmed');
  }finally{globalThis.fetch=old;}
 });
}
test('unchecked, edited and stale context or capability callbacks cannot send',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};h.preview();await h.button(send).props.onClick();h.check();const stale=h.button(send).props.onClick,check=h.nodes().find(n=>n.props?.type==='checkbox').props.onChange;
  h.change('evidence','changed');await stale();check({target:{checked:true}});h.render();assert.equal(h.button(send),undefined);h.preview();h.check();await stale();assert.equal(calls,0);
  const newer=h.button(send).props.onClick;h.render({...h.props(),submissionEnabled:false});await newer();assert.equal(calls,0);
  h.render({...h.props(),submissionEnabled:true,initialContext:{...h.props().initialContext,predecessor:f.key}});await newer();h.render();assert.equal(calls,0);assert.equal(h.button(send),undefined);
 }finally{globalThis.fetch=old;}
});
test('synchronous send/query/retry interlock and later refusal preserve unknown',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0,finish;h.preview();h.check();
 try{globalThis.fetch=async()=>{calls++;return new Promise(r=>finish=r);};const write=h.button(send).props.onClick,p=write();await write();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'sending');
  finish(Response.json({error:'outcome_unknown'},{status:502}));await p;h.render();const read=h.button(query).props.onClick,retryClick=h.button(retry).props.onClick,p2=read();await read();await retryClick();h.render();assert.equal(calls,2);assert.equal(h.state().phase,'checking');
  finish(Response.json({error:'submission_forbidden'},{status:403}));await p2;h.render();assert.equal(h.state().phase,'unknown');assert.equal(h.button(start),undefined);
  const click=h.button(retry).props.onClick;h.render({...h.props(),submissionEnabled:false});await click();assert.equal(calls,2);
 }finally{globalThis.fetch=old;}
});
test('malformed context, nondecisions, each blank reason and combined UTF8 budget fail preparation',()=>{
 for(const [field,value]of [['predecessor','invalid'],['previousDecision','WITHDRAW'],['decision','WITHDRAWN'],['release','invalid'],['snapshot','invalid'],['reason',' '],['correctionReason',' '],['reason','中'.repeat(3000)],['correctionReason','中'.repeat(3000)]]){
  const h=harness();h.change(field,value);h.preview();assert.equal(h.button(send),undefined);assert.ok(h.text().includes('context or request is invalid'));
 }
});
test('nullable/unicode references and normalization are preserved without fetching locations',()=>{
 for(const ref of [null,'证据 😀']){const c=f.command();c.body.evidence_ref=ref;const text=exportText(confirmImpactCorrection(c,true),origin);assert.deepEqual(parse(text,origin),c);}
 const h=harness();h.change('evidence',' ');h.preview();h.check();const raw=h.nodes().filter(n=>n.type==='pre').map(n=>n.props.children.props.children)[0];assert.equal(JSON.parse(raw).body.evidence_ref,null);
});
test('origin/format/version/credentials/duplicate keys/canonical order reject altered recovery',()=>{
 const text=exported(),mutations=[d=>d.format='slc-acceptance-correction-recovery',d=>d.version=2,d=>d.origin='https://other.example',d=>d.operation='impact',
 d=>d.receipt={confirmed:true},d=>d.token='secret',d=>d.actor_principal_id=f.principal,d=>d.body.actor_name+=' ',d=>d.body.reason+=' ',d=>d.body.correction_reason+=' ',
 d=>d.body.request_id=d.body.request_id.toUpperCase(),d=>d.target+=' ',d=>d.body.action='WITHDRAW',d=>d.body.decision='WITHDRAWN',
 d=>d.predecessor.id=f.key,d=>d.predecessor.release_id=f.key,d=>d.predecessor.snapshot_id=f.key,d=>d.predecessor.token='secret',d=>d.body.reason='\ud800',d=>d.body.reason='中'.repeat(3000),
 d=>d.body=Object.fromEntries(Object.entries(d.body).reverse())];
 for(const mutate of mutations){const d=JSON.parse(text);mutate(d);assert.equal(parse(JSON.stringify(d,null,2),origin),null);}
 for(const [key,value]of [['version','1'],['origin',JSON.stringify(origin)],['request_id',JSON.stringify(f.key)],['decision','"AFFECTED"']])assert.equal(parse(text.replace('"'+key+'":','"'+key+'": '+value+', "'+key+'":'),origin),null);
 for(const site of [origin+'/','https://user:pass@lifecycle.example','http://remote.example'])assert.equal(parse(text,site),null);
 for(const input of [' '.repeat(limit+1),'中'.repeat(limit/2),'null'])assert.equal(parse(input,origin),null);
 assert.throws(()=>exportText(confirmImpactCorrection(f.command(),false),origin));
 assert.throws(()=>exportText({...confirmImpactCorrection(f.command(),true),command:{...f.command(),target:' other '}},origin));
 for(const site of ['http://localhost:3000','http://127.0.0.1','http://[::1]:8080',origin])assert.ok(parse(exportText(confirmImpactCorrection(f.command(),true),site),site));
});
test('stale imports or attempted controller cannot be replaced and no network occurs',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0;
 try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};stage(h,'invalid');assert.equal(h.state(),null);assert.ok(h.text().includes('Nothing was sent'));
  h.change('importText',exported());const stale=h.button(importButton).props.onClick;h.change('importText',exported('AFFECTED'));stale();h.render();assert.equal(h.state(),null);
  h.button(importButton).props.onClick();h.render();assert.equal(h.state().command.body.decision,'AFFECTED');stale();h.render();assert.equal(h.state().command.body.decision,'AFFECTED');assert.equal(calls,0);
 }finally{globalThis.fetch=old;}
});
test('manual copy lock blocks editing/send/query and clipboard failure leaves original recovery text',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0,finish;h.preview();h.check();
 try{h.clipboard(()=>new Promise((r,j)=>finish=j));globalThis.fetch=async()=>{calls++;throw Error('unexpected');};const click=h.button(send).props.onClick,p=h.button(copy).props.onClick();await click();h.change('correctionReason','other');h.render();assert.equal(calls,0);
  finish(Error('clipboard'));await p;h.render();assert.ok(h.text().includes('Select and copy'));assert.ok(h.text().includes('slc-impact-correction-recovery'));assert.ok(h.text().includes(f.command().body.correction_reason));
 }finally{globalThis.fetch=old;}
});
test('imported query denied or unavailable retains unknown even when capabilities/context change',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0;stage(h,exported());const c=h.state().command;
 try{const read=h.button(query).props.onClick;h.render({...h.props(),recoveryEnabled:false});globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await read();assert.equal(calls,0);
  h.render({...h.props(),recoveryEnabled:true,submissionEnabled:false,initialContext:props('AFFECTED').initialContext});
  for(const [status,error]of [[401,'session_required'],[502,'outcome_unknown'],[503,'impact_correction_disabled']]){
   globalThis.fetch=async url=>{assert.equal(url,'/auth/impact-correction-receipt');return Response.json({error},{status});};await h.button(query).props.onClick();h.render();
   assert.equal(h.state().phase,'unknown');assert.deepEqual(h.state().command,c);assert.equal(h.button(retry),undefined);assert.equal(h.button(start),undefined);
  }
 }finally{globalThis.fetch=old;}
});
test('editable exports are not success evidence and changed body cannot confirm another original receipt',async()=>{
 const original=f.command();for(const patch of [{actor_name:'other'},{reason:'other'},{correction_reason:'other'},{decision:'AFFECTED'},{request_id:f.predecessor.replace('890','891')},{evidence_ref:null}]){
  const c={...original,body:{...original.body,...patch}},s=restore(exportText(confirmImpactCorrection(c,true),origin),origin);
  await s.recover(true,async()=>Response.json(f.receipt(original)));assert.equal(s.state.phase,'unknown');assert.equal(s.state.receipt,null);assert.equal(s.send,undefined);
 }
});
test('new strings are Chinese/English while original envelopes remain exact and provider details hidden',()=>{
 for(const file of ['impact-correction-workbench.tsx','impact-correction-result.tsx','impact-correction-history.tsx']){
  const source=fs.readFileSync('components/'+file,'utf8');for(const match of source.matchAll(/<Localized>\{'([^']+)'\}<\/Localized>/g)){if(match[1].trim()==='·')continue;assert.match(dictionary[match[1]],/[\u4e00-\u9fff]/,match[1]);}
 }
 const s=restore(exported(),origin);for(const locale of ['zh','en']){
  const html=render(locale,React.createElement(Result,{state:s.state}));assert.ok(html.includes('/activity/EVT-IMPACT-'+f.key));assert.ok(html.includes(locale==='zh'?'重新加载后丢失':'lost on reload'));
 }
 assert.ok(!render('en',React.createElement(Result,{state:{...s.state,error:'private_provider_error'}})).includes('private_provider_error'));
});

function mocked(file,replacements){const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,file),'utf8'),{exports,require:name=>name in replacements?replacements[name]:name==='react/jsx-runtime'||name==='next/link'?require(name):require(path.resolve(output,path.dirname(file),name)),process:{env:{}},URLSearchParams,encodeURIComponent,Promise});return exports.default;}
test('commands independently gates Impact replacement, unique session and read-only recovery without Acceptance enablement',async()=>{
 const gates=['firstSubmissionConfigured','governanceSubmissionConfigured','distributionSubmissionConfigured','productionSubmissionConfigured','evidenceSubmissionConfigured','resourceSubmissionConfigured'];
 for(const [enabled,cookieCount,readOnly]of [[false,1,false],[true,0,false],[true,2,false],[true,1,true],[true,1,false]]){
  let resolved=0,acceptanceGate=0;const auth={authConfig:async()=>({session:{}}),impactCorrectionSubmissionConfigured:()=>enabled,acceptanceCorrectionSubmissionConfigured:()=>{acceptanceGate++;return true;},...Object.fromEntries(gates.map(n=>[n,()=>false]))};
  const Page=mocked('app/commands/page.js',{'next/headers':{cookies:async()=>({getAll:()=>Array(cookieCount).fill({value:'opaque'})})},'../../lib/browser-auth':auth,'../../lib/browser-session':{SESSION_COOKIE:'session',resolveSession:async()=>{resolved++;return {read_only_mode:readOnly};}}});
  const tree=await Page({searchParams:Promise.resolve({operation:'impact-correction',target:'ISS-1',release:f.release,snapshot:f.snapshot,predecessor:f.predecessor,previous_decision:'AFFECTED',correction_action:'WITHDRAW'})});
  const children=tree.props.children,correction=children.find(n=>n?.props?.initialContext?.previousDecision),ordinary=children.find(n=>n?.props?.initialOperation);
  assert.equal(correction.props.submissionEnabled,enabled&&cookieCount===1&&!readOnly);assert.equal(correction.props.recoveryEnabled,enabled&&cookieCount===1);
  assert.equal(resolved,enabled&&cookieCount===1?1:0);assert.equal(acceptanceGate,0);assert.equal(ordinary.props.evidenceSubmissionEnabled,false);
  assert.deepEqual({...correction.props.initialContext},{target:'ISS-1',release:f.release,snapshot:f.snapshot,predecessor:f.predecessor,previousDecision:'AFFECTED'});
 }
});
test('repeated/unbounded correction query fields stay blank instead of selecting an arbitrary context',async()=>{
 const Page=mocked('app/commands/page.js',{'next/headers':{cookies:async()=>{throw Error('disabled');}},'../../lib/browser-session':{SESSION_COOKIE:'session',resolveSession:async()=>{throw Error('disabled');}},'../../lib/browser-auth':{authConfig:async()=>null,...Object.fromEntries(['firstSubmissionConfigured','governanceSubmissionConfigured','distributionSubmissionConfigured','productionSubmissionConfigured','evidenceSubmissionConfigured','resourceSubmissionConfigured','acceptanceCorrectionSubmissionConfigured','impactCorrectionSubmissionConfigured'].map(n=>[n,()=>false]))}});
 const tree=await Page({searchParams:Promise.resolve({operation:'impact-correction',target:['ISS-A','ISS-B'],release:[f.release],snapshot:'x'.repeat(37),predecessor:'x'.repeat(37),previous_decision:['AFFECTED']})});
 const c=tree.props.children.find(n=>n?.props?.initialContext?.previousDecision!==undefined);assert.deepEqual({...c.props.initialContext},{target:'',release:'',snapshot:'',predecessor:'',previousDecision:''});assert.equal(c.props.submissionEnabled,false);
});
const History=require(path.join(output,'components/impact-correction-history.js')).default;
function correctionLinks(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&')).filter(u=>u.startsWith('/commands?')&&new URL(u,origin).searchParams.get('operation')==='impact-correction');}
test('history links bind exact Issue/Release/Snapshot/predecessor/decision for original and replacement leaves',()=>{
 for(const previous of [null,f.key]){const judgment={id:f.predecessor,release_id:f.release,snapshot_id:f.snapshot,decision:'AFFECTED',supersedes_id:previous,superseded_by_id:null,correction_reason:previous?'original':null};
  const html=render('en',React.createElement(History,{judgment,issueNo:f.command().target})),links=correctionLinks(html);assert.equal(links.length,1);
  const q=new URL(links[0],origin).searchParams;assert.equal(q.get('target'),f.command().target);assert.equal(q.get('release'),f.release);assert.equal(q.get('snapshot'),f.snapshot);assert.equal(q.get('predecessor'),f.predecessor);assert.equal(q.get('previous_decision'),'AFFECTED');
  assert.ok(!html.includes('<form')&&!html.includes('Send confirmed correction request'));
 }
});
test('ended, incomplete, noncanonical or nonjudgment history has no replacement entry',()=>{
 const valid={id:f.predecessor,release_id:f.release,snapshot_id:f.snapshot,decision:'AFFECTED',superseded_by_id:null};
 for(const patch of [{superseded_by_id:f.key},{superseded_by_id:undefined},{id:'bad'},{release_id:f.release.toUpperCase()},{snapshot_id:null},{decision:'WITHDRAWN'}])assert.equal(correctionLinks(render('en',React.createElement(History,{judgment:{...valid,...patch},issueNo:'ISS-1'}))).length,0);
 assert.equal(correctionLinks(render('en',React.createElement(History,{judgment:valid}))).length,0);
});
test('actual selected frozen summary and paginated history wire the entry without additional API calls',async()=>{
 const assessment={id:f.predecessor,release_id:f.release,snapshot_id:f.snapshot,decision:'AFFECTED',reason:'original',actor_name:'original',evidence_ref:null,created_at:'then',superseded_by_id:null};
 const data={issue_id:f.entity,issue_no:'ISS-1',release_id:f.release,snapshot_id:f.snapshot,release:{id:f.release,type:'APPLICATION',version:'v1'},snapshot:{id:f.snapshot,snapshot_no:'SNAP-1',status:'FROZEN',number:1,content_hash:'a'.repeat(64)},assessment,component_count:0,verification_count:0};
 for(const [patch,expected]of [[{},1],[{snapshot:{...data.snapshot,status:'DRAFT'}},0],[{assessment:{...assessment,release_id:f.key}},0],[{assessment:{...assessment,snapshot_id:f.key}},0],[{assessment:{...assessment,superseded_by_id:f.key}},0]]){
  let calls=0;const Page=mocked('app/issues/[id]/impact/[releaseId]/page.js',{'../../../../../lib/api':{apiGet:async()=>{calls++;return {...data,...patch};}},'../../../../../components/issue-collections':{__esModule:true,default:()=>null}});
  const html=render('en',await Page({params:Promise.resolve({id:'ISS-1',releaseId:f.release}),searchParams:Promise.resolve({snapshot_id:f.snapshot})}));
  assert.equal(correctionLinks(html).length,expected);assert.equal(calls,1);
 }
 let calls=0;const Collections=mocked('components/issue-collections.js',{'../lib/api':{apiGet:async url=>{calls++;return {issue_id:f.entity,issue_no:'ISS-1',total:1,next_offset:null,items:url.includes('/assessments?')?[assessment]:[]};}}});
 const html=render('en',await Collections({data:{id:f.entity,issue_no:'ISS-1',linked_count:0,candidate_count:0,assessment_count:1},search:{}}));assert.equal(calls,3);assert.equal(correctionLinks(html).length,1);
});
