'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-release-recovery-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),'components/release-decision-supersession-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx','--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Component=require(path.join(output,'components/release-decision-supersession-workbench.js')).default;
const Result=require(path.join(output,'components/release-decision-supersession-result.js')).default;
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const recovery=require(path.join(output,'lib/release-decision-supersession-recovery.js'));
const transport=require(path.join(output,'lib/release-decision-supersession-transport.js'));
const f=require('./fixtures/release-decision-supersession.cjs'),dictionary=require('../lib/i18n/zh.json'),origin='https://slc.example.com';
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const initial=c=>({target:c.target,predecessor:c.predecessor.id,release:c.predecessor.release_id,snapshot:c.predecessor.snapshot_id,previousNo:c.predecessor.decision_no,previousDecision:c.predecessor.decision,previousReadiness:c.predecessor.readiness_status,decisionNo:c.body.decision_no,actor:c.body.decided_by,readiness:c.body.readiness_status,decision:c.body.decision,notes:c.body.notes,correctionReason:c.body.correction_reason});
const exported=c=>recovery.exportReleaseDecisionSupersessionRecovery(transport.confirmReleaseDecisionSupersession(c,true),origin);
function harness(extra={}){
 const values=[],effects=[],copies=[],listeners=new Map();let index=0,tree,work=[],props={initialContext:initial(f.command()),submissionEnabled:true,recoveryEnabled:true,...extra},clipboard=async s=>copies.push(s),ids=0;
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/release-decision-supersession-workbench.js'),'utf8'),{exports,require:name=>name==='react'?hooks:name==='./localized'?require(path.join(output,'components/localized.js')):name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),crypto:{randomUUID:()=>{ids++;return f.command().body.request_id;}},window:{location:{origin},addEventListener:(n,fn)=>listeners.set(n,fn),removeEventListener:n=>listeners.delete(n)},navigator:{clipboard:{writeText:s=>clipboard(s)}},Error,JSON});
 function nodes(n=tree){if(Array.isArray(n))return n.flatMap(v=>nodes(v));if(!n||typeof n!=='object')return[];return[n,...nodes(n.props?.children??null)];}
 function text(n=tree){if(Array.isArray(n))return n.map(v=>text(v)).join('');if(typeof n==='string'||typeof n==='number')return String(n);return n&&typeof n==='object'?text(n.props?.children??null):'';}
 function rerender(next=props){props=next;index=0;work=[];tree=exports.default(props);for(const fn of work)fn();return tree;}
 function change(name,value){nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});rerender();}
 const button=label=>nodes().find(n=>n.type==='button'&&text(n)===label);
 function prepare(){nodes().find(n=>n.type==='form').props.onSubmit({preventDefault(){}});rerender();nodes().find(n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});rerender();}
 rerender();return{render:rerender,change,prepare,button,nodes,text,copies,listeners,props:()=>props,ids:()=>ids,clipboard:fn=>clipboard=fn,state:()=>nodes().find(n=>n.type===Result)?.props.state};
}
const imp='Import replacement request for audit query only',query='Query original audit without resubmitting',send='Send confirmed replacement request',copy='Copy replacement recovery text',reveal='Reveal replacement recovery text';
function importIt(h,c=f.command()){h.change('replacementRecoveryImport',exported(c));h.button(imp).props.onClick();h.render();}
for(const locale of ['zh','en'])test(`${locale}: manual import notice is bilingual and initial SSR makes no network call`,()=>{
 const html=render(locale,React.createElement(Component,{})),label='Recover a saved replacement request';assert.ok(html.includes(locale==='zh'?dictionary[label]:label));assert.ok(!html.includes('replacementRecoveryExport'));
});
test('import makes zero network calls/new UUIDs, hides send and only explicit recovery can query',async()=>{
 const h=harness({submissionEnabled:false}),old=globalThis.fetch;let calls=0;try{globalThis.fetch=async(_u,init)=>{calls++;assert.equal(_u,'/auth/release-decision-supersession-receipt');return Response.json(f.receipt(f.command()));};importIt(h);assert.equal(calls,0);assert.equal(h.ids(),0);assert.equal(h.button(send),undefined);assert.equal(h.state().phase,'unknown');await h.button(query).props.onClick();h.render();assert.equal(calls,1);assert.equal(h.state().phase,'confirmed');assert.equal(h.button(send),undefined);}finally{globalThis.fetch=old;}
});
test('prepared and unknown attempts export exact canonical body without automatic storage/network/new IDs',async()=>{
 const h=harness(),old=globalThis.fetch;let calls=0;try{globalThis.fetch=async()=>{calls++;throw Error('lost');};h.prepare();h.button(reveal).props.onClick();h.render();const text=h.nodes().find(n=>n.props?.name==='replacementRecoveryExport').props.value;assert.deepEqual(recovery.parseReleaseDecisionSupersessionRecovery(text,origin),f.command());await h.button(copy).props.onClick();assert.equal(calls,0);await h.button(send).props.onClick();h.render();assert.equal(h.state().phase,'unknown');await h.button(copy).props.onClick();assert.equal(h.copies[0],h.copies[1]);assert.equal(h.ids(),1);assert.ok(h.listeners.has('beforeunload'));assert.equal(h.button(imp),undefined);}finally{globalThis.fetch=old;}
});
test('duplicate import/query and busy clipboard protect frozen attempt, metadata and reset',async()=>{
 const h=harness();h.change('replacementRecoveryImport',exported(f.command()));const click=h.button(imp).props.onClick;click();click();h.render();const original=h.state().command;let finish,calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;return new Promise(resolve=>finish=()=>resolve(Response.json(f.receipt(f.command()))));};const run=h.button(query).props.onClick,pending=run();await run();finish();await pending;h.render();assert.equal(calls,1);let done;h.clipboard(()=>new Promise(resolve=>done=resolve));const cp=h.button(copy).props.onClick();h.button('Start a new request').props.onClick();assert.equal(h.state().command,original);done();await cp;h.render();h.button('Start a new request').props.onClick();h.render();assert.equal(h.state(),undefined);}finally{globalThis.fetch=old;}
});
test('route context changes invalidate unattempted reviews, but retain original unknown recovery',async()=>{
 const h=harness();h.prepare();const stale=h.button(send).props.onClick;h.render({...h.props(),initialContext:{...initial(f.command()),target:'OTHER'}});await stale();h.render();assert.equal(h.state(),undefined);
 const r=harness(),old=globalThis.fetch;try{globalThis.fetch=async()=>{throw Error('lost');};importIt(r);await r.button(query).props.onClick();r.render();const original=r.state().command;r.render({...r.props(),initialContext:{target:'OTHER'}});assert.equal(r.state().command,original);assert.equal(r.button('Start a new request'),undefined);}finally{globalThis.fetch=old;}
});
test('invalid, foreign-origin and different explicit approval import are rejected locally',()=>{
 for(const value of ['{}',exported({...f.command(),target:'FOREIGN'}),exported(f.command()).replace(origin,'https://foreign.example')]){const h=harness();h.change('replacementRecoveryImport',value);h.button(imp).props.onClick();h.render();assert.equal(h.state(),undefined);assert.equal(h.ids(),0);assert.ok(h.text().includes('invalid or belongs'));}
});
test('disabled recovery is not a permission bypass and original imported data cannot be replaced',async()=>{
 const h=harness({recoveryEnabled:false});h.change('replacementRecoveryImport',exported(f.command()));const click=h.button(imp).props.onClick;click();h.render();const original=h.state().command;click();assert.equal(h.state().command,original);await h.button(query).props.onClick();assert.equal(h.state().phase,'unknown');assert.equal(h.button(query).props.disabled,true);
});
for(const locale of ['zh','en'])test(`${locale}: imported descriptive labels are explicitly unverified even after historical receipt; raw text preserved`,async()=>{
 const c=f.command();c.predecessor.decision_no='Note';c.predecessor.decision='FAKE';c.predecessor.readiness_status='UNVERIFIED';c.body.correction_reason='Raw reason 原文';const h=harness({initialContext:{}}),old=globalThis.fetch;
 try{globalThis.fetch=async()=>Response.json(f.receipt(c));importIt(h,c);await h.button(query).props.onClick();h.render();assert.equal(h.state().phase,'confirmed');const html=render(locale,h.render());assert.ok(html.includes('Note'));assert.ok(html.includes('Raw reason 原文'));const warning='Predecessor number, decision and readiness are unverified preparation metadata, including after audit confirmation. The original audit verifies the original request and predecessor UUID, not those descriptive labels or the current effective decision.';assert.ok(html.includes(locale==='zh'?dictionary[warning]:warning));assert.equal(h.button(send),undefined);}finally{globalThis.fetch=old;}
});
