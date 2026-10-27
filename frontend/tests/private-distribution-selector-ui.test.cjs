'use strict';
const {test,after}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const output=fs.mkdtempSync(path.join(require('node:os').tmpdir(),'slc-distribution-ui-'));
require('node:child_process').execFileSync(process.execPath,[require.resolve('typescript/bin/tsc'),
 'components/command-workbench.tsx','--target','ES2021','--module','commonjs','--jsx','react-jsx',
 '--esModuleInterop','--resolveJsonModule','--strict','--skipLibCheck','--outDir',output]);
fs.symlinkSync(path.resolve('node_modules'),path.join(output,'node_modules'),'dir');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const Selector=require(path.join(output,'components/private-distribution-selector.js')).default;
const Component=require(path.join(output,'components/command-workbench.js')).default;
const Result=require(path.join(output,'components/distribution-command-result.js')).default;
const {distributionCommandMessages}=require(path.join(output,'components/distribution-command-result.js'));
const {DistributionSubmission,distributionReview}=require(path.join(output,'lib/distribution-command-transport.js'));
const {LanguageProvider}=require(path.join(output,'components/localized.js'));
const f=require('./fixtures/distribution-command.cjs'),dictionary=require('../lib/i18n/zh.json');
const render=(locale,node)=>renderToStaticMarkup(React.createElement(LanguageProvider,{initialLocale:locale},node));
after(()=>fs.rmSync(output,{recursive:true,force:true}));
const props=operation=>({initialOperation:operation,initialTarget:operation==='delivery'?f.release:operation==='distribution'?f.packageId:f.distribution,initialStep:'',
 initialContext:{packageNo:'PKG-原始',revision:'2',artifacts:[f.artifact2,f.artifact].join('\n'),actor:'  Declared creator  ',
 recipientType:'CUSTOMER',recipientCode:'  CUST-原始  ',purpose:'  PRODUCTION  ',distributionNo:'DS-原始',authorizationNo:'PA-原始',
 release:f.release,customer:f.customer,project:f.project,site:'  SITE-原始  ',line:'  LINE-原始  ',limitMode:'FINITE',limit:'2',note:'Original restriction\n原文'},
 submissionEnabled:false,recoveryEnabled:false,governanceSubmissionEnabled:false,governanceRecoveryEnabled:false,distributionSubmissionEnabled:true,distributionRecoveryEnabled:true});
// Actual compiled component handlers with isolated hooks; not browser acceptance.
function workbenchHarness(operation='delivery'){
 const values=[],effects=[],listeners=new Map(),copies=[];let index=0,tree,work=[],current={...props(operation),selectionEnabled:true},clipboard=async value=>copies.push(value);
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
const send='Send confirmed business request',retry='Retry original business request',query='Query original audit without resubmitting',start='Start a new request';
const {blankFields}=require(path.join(output,'lib/command-draft.js'));
const uid=n=>`${n.repeat(8)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(4)}-${n.repeat(12)}`;
const base={release_id:uid('1'),snapshot_id:uid('2'),release_decision_id:uid('3'),project_id:uid('4')};
const fields={...blankFields,target:base.release_id,recipientType:'CUSTOMER',recipientCode:'CUST',purpose:'PRODUCTION'};
const artifact=(n='5')=>({snapshot_artifact_id:uid(n),filename:'Note',artifact_type:'HEX',component_code:'Comp',component_version:'1.0',sha256:'a'.repeat(64),policy_decision:'ALLOW'});
const line={site_id:uid('7'),site_code:'SITE',site_name:'Site原始',line_id:uid('8'),line_code:'LINE',line_name:'Line原始'};
function response(request,extra={}){const common={...base,recipient_type:'CUSTOMER',recipient_code:'CUST',purpose:'PRODUCTION'};
 if(request.operation==='distribution')return {context:{...common,release_decision_id:null,delivery_package_id:request.target_id,package_no:'PKG',revision:2,status:'READY'},...extra};
 return {context:request.operation==='delivery'?{...common,release_id:request.target_id,recipient_type:request.recipient_type,recipient_code:request.recipient_code,purpose:request.purpose}:{...common,distribution_id:request.target_id,distribution_no:'DS',delivery_package_id:uid('9'),package_no:'PKG',revision:2,customer_id:uid('a')},items:request.operation==='delivery'?[artifact()]:[line],limit:request.limit,offset:request.offset,next_offset:null,...extra};}
function selectorHarness(operation='delivery',changes={}){
 const values=[],effects=[];let index=0,tree,work=[],applied=[],current={operation,fields,contextKey:'key',enabled:true,locked:false,onApply:(patch,key)=>{applied.push({patch,key});return true;},...changes};
 const hooks={useState(initial){const i=index++;if(!(i in values))values[i]=initial;return[values[i],next=>{values[i]=typeof next==='function'?next(values[i]):next;}];},useRef(initial){const i=index++;if(!(i in values))values[i]={current:initial};return values[i];},useEffect(fn,deps){const i=index++,old=effects[i];if(!old||deps.some((d,j)=>!Object.is(d,old.deps[j])))work.push(()=>{old?.cleanup?.();effects[i]={deps,cleanup:fn()};});}};
 const exports={};vm.runInNewContext(fs.readFileSync(path.join(output,'components/private-distribution-selector.js'),'utf8'),{exports,require:name=>name==='react'?hooks:name==='./localized'?require(path.join(output,'components/localized.js')):name==='react/jsx-runtime'?require(name):require(path.resolve(output,'components',name)),fetch:(...args)=>globalThis.fetch(...args),AbortSignal,Error,JSON});
 function nodes(node=tree){if(Array.isArray(node))return node.flatMap(n=>nodes(n));if(!node||typeof node!=='object')return[];return[node,...nodes(node.props?.children??null)];}
 function text(node=tree){if(Array.isArray(node))return node.map(n=>text(n)).join('');if(typeof node==='string'||typeof node==='number')return String(node);return node&&typeof node==='object'?text(node.props?.children??null):'';}
 function rerender(next=current){current=next;index=0;work=[];tree=exports.default(current);for(const fn of work)fn();return tree;}
 rerender();return {render:rerender,nodes,text,applied,props:()=>current,button:label=>nodes().find(n=>n.type==='button'&&text(n)===label)};
}
const load='Load private selection context',next='Load next private choices page',apply='Apply selected values to preparation';
async function loaded(h){const old=globalThis.fetch;try{globalThis.fetch=async(url,init)=>{assert.equal(url,'/auth/distribution-selection');assert.equal(init.method,'POST');return Response.json(response(JSON.parse(init.body)));};await h.button(load).props.onClick();h.render();}finally{globalThis.fetch=old;}}
for(const locale of ['zh','en'])test(`${locale}: disabled selector has no automatic reads and retains explicit manual fallback`,async()=>{
 const html=render(locale,React.createElement(Selector,{operation:'delivery',fields,contextKey:'key',onApply:()=>true}));const label='Private selection is disabled or unavailable for this session. Manual preparation remains available.';assert.ok(html.includes(locale==='zh'?dictionary[label]:label));const h=selectorHarness('delivery',{enabled:false});let calls=0;const old=globalThis.fetch;try{globalThis.fetch=async()=>{calls++;throw Error('unexpected');};await h.button(load).props.onClick();assert.equal(calls,0);assert.equal(h.applied.length,0);}finally{globalThis.fetch=old;}
});
for(const operation of ['delivery','distribution','authorization'])test(`${operation}: explicit private read and separate apply fills only scoped fields, never submits`,async()=>{
 const h=selectorHarness(operation);await loaded(h);assert.equal(h.applied.length,0);if(operation==='delivery'){h.nodes().find(n=>n.props?.name==='selectedArtifact').props.onChange({target:{checked:true}});h.render();}if(operation==='authorization'){h.nodes().find(n=>n.props?.name==='selectedLine').props.onChange({target:{value:line.line_id}});h.render();}h.button(apply).props.onClick();h.render();assert.equal(h.applied.length,1);const p={...h.applied[0].patch};assert.equal(h.applied[0].key,'key');if(operation==='delivery')assert.deepEqual(p,{artifacts:uid('5'),recipientType:'CUSTOMER',recipientCode:'CUST',purpose:'PRODUCTION'});if(operation==='distribution')assert.deepEqual(p,{recipientType:'CUSTOMER',recipientCode:'CUST'});if(operation==='authorization')assert.deepEqual(p,{release:uid('1'),customer:uid('a'),project:uid('4'),purpose:'PRODUCTION',site:'SITE',line:'LINE'});assert.equal(p.limitMode,undefined);assert.equal(p.request_id,undefined);
});
test('delivery pagination pins snapshot and decision, retains explicitly selected IDs, changed context clears selection',async()=>{
 const h=selectorHarness();const old=globalThis.fetch;let page=0;try{globalThis.fetch=async(_url,init)=>{const r=JSON.parse(init.body);if(!page++)return Response.json(response(r,{items:['5','6','7','8','9'].map(artifact),next_offset:5}));assert.equal(r.offset,5);assert.equal(r.expected_snapshot_id,base.snapshot_id);assert.equal(r.expected_decision_id,base.release_decision_id);return Response.json(response(r,{context:{...response(r).context,project_id:uid('b')}}));};await h.button(load).props.onClick();h.render();h.nodes().find(n=>n.props?.name==='selectedArtifact').props.onChange({target:{checked:true}});h.render();await h.button(next).props.onClick();h.render();assert.equal(h.button(apply),undefined);assert.equal(h.applied.length,0);assert.ok(h.text().includes('Private selection unavailable or changed.'));}finally{globalThis.fetch=old;}
});
test('stale target/capability and duplicate load cannot expose or apply an old response',async()=>{
 const h=selectorHarness();let finish,calls=0;const old=globalThis.fetch;try{globalThis.fetch=async(_url,init)=>{calls++;return new Promise(resolve=>{finish=()=>resolve(Response.json(response(JSON.parse(init.body))));});};const click=h.button(load).props.onClick,pending=click();await click();h.render({...h.props(),contextKey:'other',fields:{...fields,target:uid('b')}});finish();await pending;h.render();assert.equal(calls,1);assert.equal(h.button(apply),undefined);await loaded(h);const stale=h.button(apply).props.onClick;h.render({...h.props(),enabled:false});stale();assert.equal(h.applied.length,0);}finally{globalThis.fetch=old;}
});
test('malformed and foreign response is rejected, with no fabricated selectable fields',async()=>{
 const old=globalThis.fetch;try{for(const value of [null,{context:{...base}},response({operation:'distribution',target_id:uid('b')})]){const h=selectorHarness();globalThis.fetch=async()=>Response.json(value);await h.button(load).props.onClick();h.render();assert.equal(h.button(apply),undefined);assert.equal(h.applied.length,0);}}finally{globalThis.fetch=old;}
});
for(const operation of ['delivery','distribution','authorization'])test(`${operation}: workbench application invalidates review, locks exact selected fields and manual switch clears them`,()=>{
 const h=workbenchHarness(operation);h.preview();h.check();const selector=h.nodes().find(n=>n.type===Selector),patch=operation==='delivery'?{artifacts:f.artifact,recipientType:'CUSTOMER',recipientCode:'CUST',purpose:'PRODUCTION'}:operation==='distribution'?{recipientType:'CUSTOMER',recipientCode:'CUST'}:{release:f.release,customer:f.customer,project:f.project,purpose:'PRODUCTION',site:'SITE',line:'LINE'};
 assert.equal(selector.props.onApply(patch,selector.props.contextKey),true);h.render();assert.equal(h.button(send),undefined);const name=operation==='authorization'?'site':'recipientCode';assert.equal(h.nodes().find(n=>n.props?.name===name).props.readOnly,true);h.change(name,'FOREIGN');assert.equal(h.nodes().find(n=>n.props?.name===name).props.value,patch[name]);h.button('Switch to manual entry and clear selected context').props.onClick();h.render();assert.equal(h.nodes().find(n=>n.props?.name===name).props.value,'');assert.equal(h.nodes().find(n=>n.props?.name===name).props.readOnly,false);
});
test('workbench target change invalidates selection; unknown attempt survives stale selector apply and prop changes',async()=>{
 const h=workbenchHarness('distribution'),selector=h.nodes().find(n=>n.type===Selector);h.change('target',f.release);assert.equal(selector.props.onApply({recipientType:'CUSTOMER',recipientCode:'CUST'},selector.props.contextKey),false);h.change('target',f.packageId);h.preview();h.check();const old=globalThis.fetch;try{globalThis.fetch=async()=>{throw Error('lost');};await h.button(send).props.onClick();h.render();const command=h.state().command,current=h.nodes().find(n=>n.type===Selector);assert.equal(current.props.locked,true);assert.equal(current.props.onApply({recipientType:'CUSTOMER',recipientCode:'NEW'},current.props.contextKey),false);h.render({...h.props(),initialTarget:f.release});assert.equal(h.state().command,command);}finally{globalThis.fetch=old;}
});
for(const locale of ['zh','en'])test(`${locale}: loaded raw filename and component values are escaped and never translated`,async()=>{
 const h=selectorHarness(),old=globalThis.fetch;try{globalThis.fetch=async(_url,init)=>Response.json(response(JSON.parse(init.body),{items:[{...artifact(),filename:'Note',component_code:'<script>raw</script>'}]}));await h.button(load).props.onClick();h.render();const html=render(locale,h.render());assert.ok(html.includes('Note'));assert.ok(html.includes('&lt;script&gt;raw&lt;/script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(html.includes(locale==='zh'?dictionary['Choose eligible frozen artifacts explicitly. File names and hashes are original evidence.']:'Choose eligible frozen artifacts explicitly. File names and hashes are original evidence.'));}finally{globalThis.fetch=old;}
});
test('successful pinned next page retains prior explicit artifact selection without auto-selecting later candidates',async()=>{
 const h=selectorHarness(),old=globalThis.fetch;let calls=0;try{globalThis.fetch=async(_url,init)=>{const r=JSON.parse(init.body);calls++;return Response.json(response(r,calls===1?{items:['5','6','7','8','9'].map(artifact),next_offset:5}:{items:[artifact('b')]}));};await h.button(load).props.onClick();h.render();h.nodes().find(n=>n.props?.name==='selectedArtifact').props.onChange({target:{checked:true}});h.render();await h.button(next).props.onClick();h.render();assert.equal(h.nodes().find(n=>n.props?.name==='selectedArtifact').props.checked,false);h.button(apply).props.onClick();assert.equal(h.applied[0].patch.artifacts,uid('5'));assert.equal(calls,2);}finally{globalThis.fetch=old;}
});
test('commands page private selector gate is independent, current USER and read-only safe with exact cookie cardinality',async()=>{
 const ts=require('typescript'),code=ts.transpileModule(fs.readFileSync('app/commands/page.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 async function run(enabled,identity,cookieCount=1){let seen,cookies=0,resolves=0;const m={exports:{}},auth=new Proxy({authConfig:async()=>({session:{}}),privateDistributionSelectionConfigured:()=>enabled},{get:(obj,key)=>key in obj?obj[key]:()=>false});
  new Function('require','module','exports',code)(name=>name==='next/headers'?{cookies:async()=>{cookies++;return{getAll:()=>Array(cookieCount).fill({value:'secret'})};}}:name==='next/link'?({children})=>children:name.endsWith('/browser-auth')?auth:name.endsWith('/browser-session')?{SESSION_COOKIE:'cookie',resolveSession:async()=>{resolves++;return identity;}}:name.endsWith('/command-workbench')?{__esModule:true,default:props=>{seen=props;return React.createElement('div');}}:name.endsWith('/command-draft')?require(path.join(output,'lib/command-draft.js')):name.endsWith('/localized')?{Localized:({children})=>children}:require(name),m,m.exports);renderToStaticMarkup(await m.exports.default({searchParams:Promise.resolve({operation:'delivery',target:base.release_id})}));return{seen,cookies,resolves};}
 const disabled=await run(false,null);assert.equal(disabled.cookies,0);assert.equal(disabled.seen.selectionEnabled,false);for(const n of [0,2])assert.equal((await run(true,null,n)).resolves,0);const readonly=await run(true,{principal:{principal_type:'USER'},read_only_mode:true});assert.equal(readonly.seen.selectionEnabled,true);assert.equal(readonly.seen.distributionSubmissionEnabled,false);assert.ok(!JSON.stringify(readonly.seen).includes('secret'));assert.equal((await run(true,{principal:{principal_type:'SERVICE'},read_only_mode:false})).seen.selectionEnabled,false);
});
