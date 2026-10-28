'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-evidence-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/command-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx',
 '--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Selector=require(path.join(output,'components/private-evidence-selector.js')).default;
const Component=require(path.join(output,'components/command-workbench.js')).default;
const Result=require(path.join(output,'components/distribution-command-result.js')).default;
const {distributionCommandMessages}=require(path.join(output,'components/distribution-command-result.js'));
const {DistributionSubmission,distributionReview}=require(path.join(output,'lib/distribution-command-transport.js'));
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const f=require('./fixtures/distribution-command.cjs'),dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const props=operation=>({initialOperation:operation,initialTarget:operation==='resource'?f.release:operation==='approval'?'AP-1':operation==='impact'?'ISSUE-1':'SCR-1',initialStep:f.artifact,
 initialContext:{actor:'Declared',reason:'Reason',action:'APPROVED',note:'',release:f.release,snapshot:f.artifact,criterion:f.artifact,dvp:f.artifact2,decision:'NEEDS_REVIEW',evidence:'',entityType:'RELEASE',title:'Note',locationKind:'WEB_URL',location:'https://example.com/evidence',description:''},
 evidenceSelectionEnabled:true,governanceSubmissionEnabled:true,governanceRecoveryEnabled:true,evidenceSubmissionEnabled:true,evidenceRecoveryEnabled:true,resourceSubmissionEnabled:true,resourceRecoveryEnabled:true});
// Actual compiled component handlers with isolated hooks; not browser acceptance.
function workbenchHarness(operation='approval'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current={...props(operation),evidenceSelectionEnabled:true},clipboard=async value=>copies.push(value);
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},
  useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},
  useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/command-workbench.js'),'utf8'),{exports,
  require:name=>name==='react'?hooks:name==='./localized'?{Localized:({children})=>children}:name==='./distribution-command-result'?{__esModule:true,default:Result}:
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
const {blankFields}=require(path.join(output,'lib/command-draft.js'));
const uid=n=>`${n.repeat(8)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(12)}`;
const fields={...blankFields,target:'AP-1',release:uid('1'),entityType:'RELEASE'};
const context={change_request_id:uid('2'),request_no:'SCR-1',project_id:uid('3')};
function response(r,extra={}){
 if(r.operation==='approval')return{context:{approval_id:uid('2'),approval_no:r.target,project_id:uid('3'),target_type:'RELEASE',target_id:uid('1'),snapshot_id:uid('4'),status:'PENDING'},step:{step_id:uid('5'),step_order:1,role_name:'Note',status:'PENDING'},...extra};
 if(r.operation==='resource')return{context:{entity_type:r.entity_type,entity_id:r.target,entity_ref:'Note',project_ids:[uid('3')]},...extra};
 const c=r.operation==='impact'?{issue_id:uid('2'),issue_no:r.target,release_id:r.release_id,project_id:uid('3')}:{...context,request_no:r.target};
 const item=r.operation==='criteria'?{criterion_id:uid('5'),criterion_no:'Note',description:'  Raw\n原文  '}:r.operation==='dvp'?{dvp_item_id:uid('6'),item_no:'Note',title:'Title',plan_id:uid('7'),plan_no:'Plan'}:{snapshot_id:uid('8'),snapshot_no:'Note',snapshot_number:1,status:'FROZEN'};
 return{context:c,items:[item],limit:r.limit,offset:r.offset,next_offset:null,...extra};
}
function selectorHarness(operation='approval',changes={}){
 const values=[],effects=[];let index=0,tree,work=[],applied=[],current={operation,fields,contextKey:'key',enabled:true,locked:false,onApply:(patch,key)=>{applied.push({patch,key});return true;},...changes};
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/private-evidence-selector.js'),'utf8'),{exports,require:name=>name==='react'?hooks:name==='./localized'?require(path.join(output,'components/localized.js')):name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),fetch:(...args)=>globalThis.fetch(...args),AbortSignal,Error,JSON});
 function nodes(node=tree){if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(!node||typeof node!=='object')return[];return[node,...nodes(node.props?.children??null)];}
 function text(node=tree){if(Array.isArray(node))return node.map(n=>text(n)).join('');if(typeof node==='string'||typeof node==='number')return String(node);return node&&typeof node==='object'?text(node.props?.children??null):'';}
 function rerender(next=current){current=next;index=0;work=[];tree=exports.default(current);for(const fn of work)fn();return tree;}
 rerender();return {render:rerender,nodes,text,applied,props:()=>current,button:label=>nodes().find(n=>n.type==='button'&&text(n)===label)};
}
const load='Load private evidence context',apply='Apply selected values to preparation';
async function loaded(h,custom){const old=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/evidence-selection');assert.equal(init.method,'POST');return Response.json(custom?custom(JSON.parse(init.body)):response(JSON.parse(init.body)));};await h.button(load).props.onClick();h.render();}finally{globalThis.fetch=old;}}
for(const locale of ['zh','en'])test(`${locale}: disabled evidence selector keeps manual fallback and never automatically reads`,async()=>{
 const label='Private selection is disabled or unavailable for this session. Manual preparation remains available.';
 const html=render(locale,React.createElement(Selector,{operation:'approval',fields,contextKey:'key',onApply:()=>true}));assert.ok(html.includes(locale==='zh'?dictionary[label]:label));
 const h=selectorHarness('approval',{enabled:false});let calls=0,old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await h.button(load).props.onClick();assert.equal(calls,0);}finally{globalThis.fetch=old;}
});
for(const operation of ['approval','acceptance','impact','resource'])test(`${operation}: exact private read and separate apply fills only allowed preparation fields`,async()=>{
 const target=operation==='resource'?uid('9'):operation==='approval'?'AP-1':operation==='impact'?'ISSUE-1':'SCR-1';
 const h=selectorHarness(operation,{fields:{...fields,target}});await loaded(h);assert.equal(h.applied.length,0);
 for(const [name,value] of operation==='acceptance'?[['selectedCriterion',uid('5')],['selectedDvp',uid('6')]]:operation==='impact'?[['selectedSnapshot',uid('8')]]:[]){h.nodes().find(n=>n.props?.name===name).props.onChange({target:{value}});h.render();}
 h.button(apply).props.onClick();assert.equal(h.applied.length,1);assert.deepEqual({...h.applied[0].patch},operation==='approval'?{step:uid('5')}:operation==='acceptance'?{criterion:uid('5'),dvp:uid('6')}:operation==='impact'?{snapshot:uid('8')}:{target:uid('9'),entityType:'RELEASE'});
});
test('acceptance pages are independently requested and changed SCR context clears both choices',async()=>{
 const h=selectorHarness('acceptance',{fields:{...fields,target:'SCR-1'}});let calls=[];
 await loaded(h,r=>{calls.push(r.operation);const value=response(r);if(r.operation==='criteria'){value.items=Array.from({length:5},(_,i)=>({...value.items[0],criterion_id:uid(String(i+4))}));value.next_offset=5;}return value;});assert.deepEqual(calls,['criteria','dvp']);
 h.nodes().find(n=>n.props?.name==='selectedCriterion').props.onChange({target:{value:uid('4')}});h.render();
 const old=globalThis.fetch;try{globalThis.fetch=async(_u,init)=>{const r=JSON.parse(init.body);assert.equal(r.offset,5);return Response.json(response(r,{context:{...context,project_id:uid('a')}}));};await h.button('Load next evidence choices page').props.onClick();h.render();assert.equal(h.button(apply),undefined);assert.equal(h.applied.length,0);}finally{globalThis.fetch=old;}
});
test('stale target, disabled capability and duplicate reads cannot apply stale evidence',async()=>{
 const h=selectorHarness();let finish,calls=0;const old=globalThis.fetch;try{globalThis.fetch=async(_u,init)=>{calls++;return new Promise(resolve=>{finish=()=>resolve(Response.json(response(JSON.parse(init.body))));});};const click=h.button(load).props.onClick,pending=click();await click();h.render({...h.props(),contextKey:'changed',fields:{...fields,target:'AP-2'}});finish();await pending;h.render();assert.equal(calls,1);assert.equal(h.button(apply),undefined);await loaded(h);const stale=h.button(apply).props.onClick;h.render({...h.props(),enabled:false});stale();assert.equal(h.applied.length,0);}finally{globalThis.fetch=old;}
});
test('malformed and mismatched upstream evidence fails closed without applying',async()=>{
 for(const value of [null,{context:{}},response({operation:'approval',target:'FOREIGN'})]){const h=selectorHarness();await loaded(h,()=>value);assert.equal(h.button(apply),undefined);assert.equal(h.applied.length,0);}
});
for(const type of ['CUSTOMER','SUPPLIER'])test(`${type}: unsupported unscoped resource never makes a private read`,async()=>{
 const h=selectorHarness('resource',{fields:{...fields,target:uid('9'),entityType:type}});let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};assert.equal(h.button(load).props.disabled,true);await h.button(load).props.onClick();assert.equal(calls,0);}finally{globalThis.fetch=old;}
});
for(const operation of ['approval','acceptance','impact','resource'])test(`${operation}: workbench selection resets confirmation, binds fields and deliberate manual reset clears them`,()=>{
 const h=workbenchHarness(operation);h.preview();h.check();const selector=h.nodes().find(n=>n.type===Selector),patch=operation==='approval'?{step:uid('5')}:operation==='acceptance'?{criterion:uid('5'),dvp:uid('6')}:operation==='impact'?{snapshot:uid('8')}:{target:f.release,entityType:'RELEASE'};
 assert.equal(selector.props.onApply(patch,selector.props.contextKey),true);h.render();assert.equal(h.button('Send confirmed business request'),undefined);const name=Object.keys(patch)[0];assert.equal(h.nodes().find(n=>n.props?.name===name).props.readOnly,true);h.change(name,'foreign');assert.equal(h.nodes().find(n=>n.props?.name===name).props.value,patch[name]);h.button('Switch to manual entry and clear selected context').props.onClick();h.render();assert.equal(h.nodes().find(n=>n.props?.name===name).props.value,'');
});
test('impact release change invalidates previous selection and late callback; resource type also invalidates',()=>{
 const h=workbenchHarness('impact'),old=h.nodes().find(n=>n.type===Selector);assert.equal(old.props.onApply({snapshot:uid('8')},old.props.contextKey),true);h.render();h.change('release',uid('a'));assert.equal(h.nodes().find(n=>n.props?.name==='snapshot').props.value,'');assert.equal(old.props.onApply({snapshot:uid('8')},old.props.contextKey),false);
 const r=workbenchHarness('resource'),sel=r.nodes().find(n=>n.type===Selector);r.nodes().find(n=>n.type==='select'&&n.props.value==='RELEASE').props.onChange({target:{value:'PROJECT'}});r.render();assert.equal(sel.props.onApply({target:f.release,entityType:'RELEASE'},sel.props.contextKey),false);
});
test('unknown attempted request survives selector callbacks, new props and manual reset',async()=>{
 const h=workbenchHarness('impact');h.preview();h.check();const old=globalThis.fetch;try{globalThis.fetch=async()=>{throw Error('lost');};await h.button('Send confirmed business request').props.onClick();h.render();const command=h.state().command,selector=h.nodes().find(n=>n.type===Selector);assert.equal(selector.props.locked,true);assert.equal(selector.props.onApply({snapshot:uid('8')},selector.props.contextKey),false);h.render({...h.props(),initialTarget:'ISSUE-other'});assert.equal(h.state().command,command);}finally{globalThis.fetch=old;}
});
for(const locale of ['zh','en'])test(`${locale}: loaded raw reference/role tokens and whitespace remain evidence, not translation`,async()=>{
 const h=selectorHarness('approval');await loaded(h);const html=render(locale,h.render());assert.ok(html.includes('Note'));assert.ok(html.includes(uid('5')));
 const a=selectorHarness('acceptance',{fields:{...fields,target:'SCR-1'}});await loaded(a);const rendered=render(locale,a.render());assert.ok(rendered.includes('Note'));assert.ok(rendered.includes('  Raw\n原文  '));
});

test('commands page private evidence selector gate is independent, current USER and read-only safe with exact cookie cardinality',async()=>{
 const ts=require('typescript'),code=ts.transpileModule(fs.readFileSync('app/commands/page.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 async function run(enabled,identity,cookieCount=1){let seen,cookies=0,resolves=0;const m={exports:{}},auth=new Proxy({authConfig:async()=>({session:{}}),privateEvidenceSelectionConfigured:()=>enabled},{get:(obj,key)=>key in obj?obj[key]:()=>false});
  new Function('require','module','exports',code)(name=>name==='next/headers'?{cookies:async()=>{cookies++;return{getAll:()=>Array(cookieCount).fill({value:'secret'})};}}:name==='next/link'?({children})=>children:name.endsWith('/browser-auth')?auth:name.endsWith('/browser-session')?{SESSION_COOKIE:'cookie',resolveSession:async()=>{resolves++;return identity;}}:name.endsWith('/command-workbench')?{__esModule:true,default:props=>{seen=props;return React.createElement('div');}}:name.endsWith('/command-draft')?require(path.join(output,'lib/command-draft.js')):name.endsWith('/localized')?{Localized:({children})=>children}:require(name),m,m.exports);renderToStaticMarkup(await m.exports.default({searchParams:Promise.resolve({operation:'approval',target:'AP-1'})}));return{seen,cookies,resolves};}
 const disabled=await run(false,null);assert.equal(disabled.cookies,0);assert.equal(disabled.seen.evidenceSelectionEnabled,false);for(const n of [0,2])assert.equal((await run(true,null,n)).resolves,0);const readonly=await run(true,{principal:{principal_type:'USER'},read_only_mode:true});assert.equal(readonly.seen.evidenceSelectionEnabled,true);assert.equal(readonly.seen.governanceSubmissionEnabled,false);assert.ok(!JSON.stringify(readonly.seen).includes('secret'));assert.equal((await run(true,{principal:{principal_type:'SERVICE'},read_only_mode:false})).seen.evidenceSelectionEnabled,false);
});
test('criterion and DVP explicit choices survive same-context pages without automatically choosing replacements',async()=>{
 const h=selectorHarness('acceptance',{fields:{...fields,target:'SCR-1'}}),old=globalThis.fetch;let calls=[];
 try{globalThis.fetch=async(_u,init)=>{const r=JSON.parse(init.body);calls.push([r.operation,r.offset]);const v=response(r);if(r.offset===0){const key=r.operation==='criteria'?'criterion_id':'dvp_item_id';v.items=Array.from({length:5},(_,i)=>({...v.items[0],[key]:uid(String(i+4))}));v.next_offset=5;}else{const key=r.operation==='criteria'?'criterion_id':'dvp_item_id';v.items=[{...v.items[0],[key]:uid('b')}];}return Response.json(v);};
 await h.button(load).props.onClick();h.render();h.nodes().find(n=>n.props?.name==='selectedCriterion').props.onChange({target:{value:uid('4')}});h.render();h.nodes().find(n=>n.props?.name==='selectedDvp').props.onChange({target:{value:uid('5')}});h.render();
 await h.button('Load next DVP choices page').props.onClick();h.render();await h.button('Load next evidence choices page').props.onClick();h.render();h.button(apply).props.onClick();assert.deepEqual({...h.applied[0].patch},{criterion:uid('4'),dvp:uid('5')});assert.deepEqual(calls,[['criteria',0],['dvp',0],['dvp',5],['criteria',5]]);
 }finally{globalThis.fetch=old;}
});
