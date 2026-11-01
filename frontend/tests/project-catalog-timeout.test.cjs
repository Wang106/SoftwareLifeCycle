'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');
const zh = require('../lib/i18n/zh.json');
const flush = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); };
const data = {kind:'projects',total:1,limit:50,offset:0,next_offset:null,items:[{id:'project-original',code:'P-1',name:'Original project',status:'ACTIVE',site_count:2}]};
function harness(fetch, locale = 'en') {
  const cache = new Map(), timers = new Map(), requests = [], apiCalls = []; let timerId = 0;
  function load(file) {
    file = path.resolve(file);
    if (cache.has(file)) return cache.get(file).exports;
    const m = {exports:{}}; cache.set(file,m);
    const source = ts.transpileModule(fs.readFileSync(file,'utf8'), {compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
    new Function('require','module','exports','process','fetch','setTimeout','clearTimeout',source)(name => {
      if (name === 'server-only') return {};
      if (name === 'next/server') return {connection:async()=>{}};
      if (name === 'next/link') return ({href,children})=>React.createElement('a',{href,'data-framework-link':'true'},children);
      if (name.endsWith('/localized')) return {Localized:({children})=>React.createElement(React.Fragment,null,locale==='zh'&&typeof children==='string'?(zh[children]??children):children)};
      if (name.startsWith('.')) {
        const resolved = path.resolve(path.dirname(file),name);
        const target = fs.existsSync(resolved+'.ts')?resolved+'.ts':resolved+'.tsx';
        const result = load(target);
        return name.endsWith('/api')?{...result,apiGet:(...args)=>{apiCalls.push(args);return result.apiGet(...args);}}:result;
      }
      return require(name);
    },m,m.exports,{env:{API_BASE_URL:'https://example.invalid'}},async(...args)=>{requests.push(args);return fetch(...args);},
    (run,delay)=>{const id=++timerId;timers.set(id,{run,delay});return id;},id=>timers.delete(id));
    return m.exports;
  }
  async function page(kind='projects',search={}) {
    const element = await load(`app/${kind}/page.tsx`).default({searchParams:Promise.resolve(search)});
    return renderToStaticMarkup(await element.type(element.props));
  }
  return {page,timers,requests,apiCalls,expire(){for(const [id,t] of [...timers]){timers.delete(id);t.run();}}};
}
function unavailable(html) {
  assert.match(html,/Organization catalog unavailable/);
  assert.match(html,/>—<\/b>/);
  assert.doesNotMatch(html,/>0<\/b>|Original project|No matching records on this page|PRIVATE_|Next page/);
}
for (const phase of ['headers','body']) test(`actual project page bounds stalled ${phase}, ignores late result, and preserves native retry query`,async()=>{
  let settle;
  const held = new Promise(resolve=>{settle=resolve;});
  const h=harness(()=>phase==='headers'?held:Promise.resolve({ok:true,json:()=>held}));
  const search={q:'A & B',status:'ACTIVE',customer_id:'customer / one',limit:'10',offset:'20',redirect:'https://untrusted.invalid',token:'PRIVATE_TOKEN'};
  const result=h.page('projects',search); await flush();
  assert.deepEqual([...h.timers.values()].map(t=>t.delay),[15000]);
  assert.equal(h.requests.length,1); assert.equal(h.requests[0][1].cache,'no-store');
  assert.equal(h.requests[0][1].signal.aborted,false);
  h.expire(); const html=await result; unavailable(html);
  assert.equal(h.requests[0][1].signal.aborted,true); assert.equal(h.timers.size,0);
  const retry=html.match(/<a href="([^"]+)">Read projects again<\/a>/);
  assert.ok(retry,'explicit native retry must be available');
  const url=new URL(retry[1].replaceAll('&amp;','&'),'https://site.invalid');
  assert.equal(url.pathname,'/projects');
  assert.deepEqual([...url.searchParams],Object.entries(search).slice(0,5));
  assert.doesNotMatch(html,/PRIVATE_TOKEN|untrusted.invalid|<script/);
  settle(phase==='headers'?{ok:true,json:async()=>data}:data); await flush();
  assert.equal(await result,html); assert.equal(h.requests.length,1);
  // A user's ordinary GET reload reads the same normalized query once, without a router cache.
  const fresh=harness(async()=>({ok:true,json:async()=>data}));
  const recovered=await fresh.page('projects',Object.fromEntries(url.searchParams));
  assert.match(recovered,/Original project/); assert.doesNotMatch(recovered,/Read projects again|Organization catalog unavailable/);
  assert.equal(fresh.requests.length,1); assert.equal(fresh.requests[0][0],h.requests[0][0]);
});
test('late project rejection remains handled without an automatic retry',async()=>{
  let reject; const h=harness(()=>new Promise((_,fail)=>{reject=fail;}));
  const result=h.page(); await flush(); assert.equal(h.timers.size,1); h.expire(); unavailable(await result);
  reject(Error('PRIVATE_LATE_ERROR')); await flush(); assert.equal(h.requests.length,1);
});
test('project HTTP, network, malformed JSON and wrong-kind failures remain unavailable without leaking errors',async()=>{
  for(const read of [async()=>({ok:false}),async()=>{throw Error('PRIVATE_NETWORK');},async()=>({ok:true,json:async()=>{throw Error('PRIVATE_JSON');}}),async()=>({ok:true,json:async()=>({...data,kind:'customers'})})]) {
    const h=harness(read); unavailable(await h.page()); assert.equal(h.requests.length,1); assert.equal(h.timers.size,0);
  }
});
test('project failure retry retains duplicate-filter rejection and is bilingual',async()=>{
  const h=harness(async()=>({ok:false}),'zh');
  const html=await h.page('projects',{q:['one','two'],offset:'99',country:'PRIVATE_COUNTRY'});
  assert.ok(html.includes(zh['Organization catalog unavailable'])); assert.match(html,/重新读取项目/);
  assert.match(html,/href="\/projects\?q=invalid&amp;offset=99"/);
  assert.doesNotMatch(html,/PRIVATE_COUNTRY|Read projects again/); assert.equal(h.requests.length,1);
});
test('successful empty project catalog remains a real zero, not an unavailable state',async()=>{
  const h=harness(async()=>({ok:true,json:async()=>({...data,total:0,items:[]})}));
  const html=await h.page(); assert.match(html,/>0<\/b>/); assert.match(html,/No matching records on this page/);
  assert.doesNotMatch(html,/Read projects again|Organization catalog unavailable/); assert.equal(h.timers.size,0);
});
for(const kind of ['customers','suppliers']) test(`${kind} keeps its existing unbounded call and no new retry UI`,async()=>{
  const h=harness(async()=>({ok:false})); const html=await h.page(kind);
  assert.equal(h.apiCalls.length,1); assert.equal(h.apiCalls[0].length,1);
  assert.equal(h.timers.size,0); assert.deepEqual(h.requests[0][1],{cache:'no-store'});
  assert.doesNotMatch(html,/Read projects again/);
});
