'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToReadableStream} = require('react-dom/server');
const zh = require('../lib/i18n/zh.json');
const flush = async () => { for (let n=0;n<60;n++) await Promise.resolve(); };
const deferred = () => { let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject}; };
const parent = {kind:'standard',limit:50,offset:0,total:2,next_offset:null,items:[
  {id:'std-one',version:'SSR_PARENT_PROOF',status:'RELEASED',software:{name:'BMS',code:'BMS'},supplier:{name:'Supplier',code:'S'}},
  {id:'std-two',version:'SSR_SECOND_PROOF',status:'DRAFT',software:null,supplier:null},
]};
const batch = {limit:50,offset:0,items:parent.items.map(row=>({release_id:row.id,limit:10,offset:0,total:1,next_offset:null,items:[{id:'app-'+row.id,version:'ASR_CHILD_PROOF',status:'READY'}]}))};
const response = data => ({ok:true,json:async()=>data});

function harness(fetch, locale='en') {
  const modules=new Map(),timers=new Map(),requests=[];let nextTimer=0,now=0;
  function load(file) {
    file=path.resolve(file);if(modules.has(file))return modules.get(file).exports;
    const m={exports:{}};modules.set(file,m);
    const compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
    new Function('require','module','exports','process','fetch','setTimeout','clearTimeout','performance',compiled)(name=>{
      if(name==='server-only')return {};
      if(name==='next/server')return {connection:async()=>{}};
      if(name==='next/link')return ({href,children,prefetch})=>React.createElement('a',{href,'data-framework-link':true,'data-prefetch':String(prefetch)},children);
      if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,locale==='zh'&&typeof children==='string'?(zh[children]??children):children)};
      if(name.startsWith('.')){const target=path.resolve(path.dirname(file),name);return load(fs.existsSync(target+'.ts')?target+'.ts':target+'.tsx');}
      return require(name);
    },m,m.exports,{env:{API_BASE_URL:'https://example.invalid'}},async(...args)=>{requests.push(args);return fetch(...args);},
      (run,delay)=>{const id=++nextTimer;timers.set(id,{run,delay,at:now});return id;},id=>timers.delete(id),{now:()=>now});
    return m.exports;
  }
  return {Page:load('components/supplier-release-catalog.tsx').default,requests,timers,
    at(value){now=value;},expire(){for(const [id,t] of [...timers]){now=Math.max(now,t.at+t.delay);timers.delete(id);t.run();}}};
}
async function stream(Page,search={}) {
  const output=await renderToReadableStream(React.createElement('html',null,React.createElement('body',null,
    React.createElement(React.Suspense,{fallback:React.createElement('p',null,'GLOBAL_LOADING')},React.createElement(Page,{search})))));
  const reader=output.getReader();let html='';
  const done=(async()=>{for(;;){const next=await reader.read();if(next.done)return html;html+=new TextDecoder().decode(next.value);}})();
  await flush();return {output,done,get html(){return html;}};
}
function shell(html) {
  assert.match(html,/<h1[^>]*>Standard Releases/);assert.match(html,/<form[^>]*method="get"/);
  assert.doesNotMatch(html,/GLOBAL_LOADING|PRIVATE_/);
}
function nativeRetry(html,label) {
  const matches=[...html.matchAll(/<a href="([^"]+)">([^<]+)<\/a>/g)].filter(m=>m[2]===label);
  assert.ok(matches.length,'expected a native, non-prefetched retry link: '+label);
  return matches.map(m=>new URL(m[1].replaceAll('&amp;','&'),'https://site.invalid'));
}
const search={q:'A & B',status:'READY',software_id:'software one',limit:'50',offset:'0',applications_for:'std-one',application_offset:'0',token:'PRIVATE_TOKEN',redirect:'PRIVATE_REDIRECT'};

for(const phase of ['headers','body'])test('standard parent '+phase+' stall streams filters and unknown counts, then native retry',{timeout:5000},async()=>{
  const held=deferred();const h=harness(()=>phase==='headers'?held.promise:Promise.resolve({ok:true,json:()=>held.promise}));
  const page=await stream(h.Page,search);
  try {
    shell(page.html);assert.match(page.html,/name="q"[^>]*value="A &amp; B"/);assert.match(page.html,/aria-busy="true"/);assert.match(page.html,/—/);
    assert.doesNotMatch(page.html,/SSR_PARENT_PROOF|No releases on this page|Read standard releases again/);
    assert.equal(h.requests.length,1);assert.deepEqual([...h.timers.values()].map(t=>t.delay),[15000]);
    assert.equal(h.requests[0][1].cache,'no-store');assert.equal(h.requests[0][1].signal.aborted,false);
    h.expire();const html=await page.done;
    assert.match(html,/Release catalog unavailable/);assert.doesNotMatch(html,/SSR_PARENT_PROOF|Recorded count:|No releases on this page/);
    assert.equal(h.requests[0][1].signal.aborted,true);assert.equal(h.timers.size,0);assert.equal(h.requests.length,1);
    const retry=nativeRetry(html,'Read standard releases again')[0];assert.equal(retry.pathname,'/releases/standard');
    for(const key of ['q','status','software_id','limit','offset','applications_for','application_offset'])assert.equal(retry.searchParams.get(key),search[key]);
    assert.equal(retry.searchParams.has('token'),false);assert.equal(retry.searchParams.has('redirect'),false);
    held.resolve(phase==='headers'?response(parent):parent);await flush();assert.equal(h.requests.length,1,'late parent must not start batch');
  } finally {held.resolve(phase==='headers'?response(null):null);await page.output.allReady;}
});

for(const phase of ['headers','body'])test('standard batch '+phase+' stall leaves real parents and pagination visible',{timeout:5000},async()=>{
  const held=deferred();const h=harness(url=>url.includes('/applications?')?(phase==='headers'?held.promise:Promise.resolve({ok:true,json:()=>held.promise})):Promise.resolve(response(parent)));
  const page=await stream(h.Page,search);
  try {
    shell(page.html);await flush();assert.match(page.html,/SSR_PARENT_PROOF|SSR_SECOND_PROOF/);assert.match(page.html,/Total releases:/);
    assert.match(page.html,/Unknown supplier/);assert.match(page.html,/First page/);assert.match(page.html,/aria-busy="true"/);
    assert.doesNotMatch(page.html,/ASR_CHILD_PROOF|Application release page unavailable|No application releases on this page/);
    assert.equal(h.requests.length,2);assert.deepEqual([...h.timers.values()].map(t=>t.delay),[15000]);
    assert.equal(h.requests[1][1].signal.aborted,false);h.expire();const html=await page.done;
    assert.match(html,/SSR_PARENT_PROOF/);assert.equal((html.match(/Application release page unavailable/g)||[]).length,2);
    assert.doesNotMatch(html,/ASR_CHILD_PROOF|No application releases on this page/);
    assert.doesNotMatch(html,/Recorded count:(?:\s|<!-- -->)*\d/,'unknown pending counts must not become invented numbers');
    const retries=nativeRetry(html,'Read application releases again');assert.equal(retries.length,2);
    for(const retry of retries){for(const key of ['q','status','software_id','limit','offset','applications_for','application_offset'])assert.equal(retry.searchParams.get(key),search[key]);assert.match(retry.hash,/^#standard-software-std-(one|two)$/);}
    assert.equal(h.requests[1][1].signal.aborted,true);assert.equal(h.timers.size,0);
    held.resolve(phase==='headers'?response(batch):batch);await flush();assert.equal(h.requests.length,2,'late batch must not retry');
  } finally {held.resolve(phase==='headers'?response(null):null);await page.output.allReady;}
});

for(const elapsed of [0,5000,14999,15000,16000])test('standard batch uses remaining read allowance after parent '+elapsed+'ms',{timeout:5000},async()=>{
  const heldParent=deferred(),heldBatch=deferred();const h=harness(url=>url.includes('/applications?')?heldBatch.promise:Promise.resolve({ok:true,json:()=>heldParent.promise}));
  const page=await stream(h.Page);
  try {
    shell(page.html);assert.equal(h.requests.length,1);h.at(elapsed);heldParent.resolve(parent);await flush();
    assert.match(page.html,/SSR_PARENT_PROOF/);
    if(elapsed<15000){assert.equal(h.requests.length,2);assert.deepEqual([...h.timers.values()].map(t=>t.delay),[15000-elapsed]);h.expire();}
    else {assert.equal(h.requests.length,1,'exhausted allowance must not admit batch');assert.equal(h.timers.size,0);}
    const html=await page.done;assert.match(html,/Application release page unavailable/);assert.doesNotMatch(html,/ASR_CHILD_PROOF/);
  } finally {heldParent.resolve(null);heldBatch.resolve(response(null));await page.output.allReady;}
});

function boundary(element) {
  if(!React.isValidElement(element))return null;if(element.type===React.Suspense)return element;
  for(const child of React.Children.toArray(element.props.children)){const found=boundary(child);if(found)return found;}return null;
}
test('standard shell is synchronous and keys parent and child selections without unknown query fields',()=>{
  const h=harness(()=>new Promise(()=>{}));
  const key=search=>{const el=h.Page({search});assert.equal(typeof el?.then,'undefined');const b=boundary(el);assert.ok(b);return b.key;};
  const base=key(search);assert.equal(base,key({...search,extra:'PRIVATE_IGNORED'}));
  for(const field of ['q','status','software_id','limit','offset','applications_for','application_offset'])assert.notEqual(base,key({...search,[field]:'other'}),field);
  assert.notEqual(key({q:'one'}),key({q:['one','two']}));assert.equal(h.requests.length,0);
});

for(const stage of ['parent','batch'])test('standard '+stage+' late rejection stays handled without automatic retries',async()=>{
  const held=deferred();const h=harness(url=>stage==='parent'||url.includes('/applications?')?held.promise:Promise.resolve(response(parent)));
  const page=await stream(h.Page);shell(page.html);await flush();h.expire();const html=await page.done;
  assert.match(html,/unavailable/);held.reject(Error('PRIVATE_LATE_FAILURE'));await flush();
  assert.equal(h.requests.length,stage==='parent'?1:2);assert.equal(h.timers.size,0);assert.doesNotMatch(html,/PRIVATE_LATE_FAILURE/);
});

test('standard genuine empty parent and children stay distinct from failure in both languages',async()=>{
  for(const locale of ['en','zh']){
    const emptyParent=harness(async()=>response({...parent,total:0,items:[]}),locale);const p=await stream(emptyParent.Page);const html=await p.done;
    assert.ok(html.includes(locale==='en'?'No releases on this page.':zh['No releases on this page.']));assert.equal(emptyParent.requests.length,1);assert.equal(emptyParent.timers.size,0);
    const childEmpty={...batch,items:batch.items.map(p=>({...p,total:0,items:[]}))};
    const h=harness(async url=>response(url.includes('/applications?')?childEmpty:parent),locale);const c=await stream(h.Page);const out=await c.done;
    assert.ok(out.includes(locale==='en'?'No application releases on this page.':zh['No application releases on this page.']));assert.match(out,/SSR_PARENT_PROOF/);assert.equal(h.requests.length,2);assert.equal(h.timers.size,0);
    const failed=harness(async()=>({ok:false}),locale);const f=await stream(failed.Page,{q:['a','b'],applications_for:'std-one',application_offset:'10',extra:'PRIVATE_EXTRA'});const fail=await f.done;
    assert.ok(fail.includes(locale==='en'?'Read standard releases again':zh['Read standard releases again']));
    assert.match(fail,/q=invalid&amp;applications_for=std-one&amp;application_offset=10/);assert.doesNotMatch(fail,/PRIVATE_EXTRA/);
  }
});

test('standard HTTP network JSON and wrong-kind failures never create child reads or leak errors',async()=>{
  for(const fetch of [async()=>({ok:false}),async()=>{throw Error('PRIVATE_NETWORK');},async()=>({ok:true,json:async()=>{throw Error('PRIVATE_JSON');}}),async()=>response({...parent,kind:'application'})]){
    const h=harness(fetch);const p=await stream(h.Page);const html=await p.done;assert.match(html,/Release catalog unavailable/);assert.doesNotMatch(html,/PRIVATE_|SSR_PARENT_PROOF/);assert.equal(h.requests.length,1);assert.equal(h.timers.size,0);
  }
});

test('standard directory framework links disable unsolicited prefetch without changing navigation targets',async()=>{
  const h=harness(async url=>response(url.includes('/applications?')?batch:parent));const p=await stream(h.Page,search);const html=await p.done;
  const links=[...html.matchAll(/<a href="([^"]+)" data-framework-link="true" data-prefetch="([^"]+)"/g)];
  assert.ok(links.length>=10);for(const link of links)assert.equal(link[2],'false',link[1]);
  for(const href of ['/releases/application','/demo/releases','/demo/zfi','/releases/standard/std-one','/releases/application/app-std-one'])assert.ok(links.some(link=>link[1]===href),href);
  assert.equal(h.requests.length,2);
});
