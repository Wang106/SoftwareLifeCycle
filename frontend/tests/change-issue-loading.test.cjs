'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const {renderToReadableStream} = require('react-dom/server');
const zh = require('../lib/i18n/zh.json');
const flush = async () => { for (let n=0;n<30;n++) await Promise.resolve(); };
function harness(fetch, locale='en') {
  const modules = new Map(), timers = new Map(), requests = []; let nextTimer=0;
  function load(file) {
    file=path.resolve(file); if(modules.has(file)) return modules.get(file).exports;
    const m={exports:{}}; modules.set(file,m);
    const compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
    new Function('require','module','exports','process','fetch','setTimeout','clearTimeout',compiled)(name=>{
      if(name==='server-only') return {};
      if(name==='next/server') return {connection:async()=>{}};
      if(name==='next/link') return ({href,children})=>React.createElement('a',{href,'data-framework-link':true},children);
      if(name.endsWith('/localized')) return {Localized:({children})=>React.createElement(React.Fragment,null,locale==='zh'&&typeof children==='string'?(zh[children]??children):children)};
      if(name.startsWith('.')) {const target=path.resolve(path.dirname(file),name);return load(fs.existsSync(target+'.ts')?target+'.ts':target+'.tsx');}
      return require(name);
    },m,m.exports,{env:{API_BASE_URL:'https://example.invalid'}},async(...args)=>{requests.push(args);return fetch(...args);},
      (run,delay)=>{const id=++nextTimer;timers.set(id,{run,delay});return id;},id=>timers.delete(id));
    return m.exports;
  }
  const Page=load('components/change-issue-catalog.tsx').default;
  return {Page,requests,timers,expire(){for(const [id,t] of [...timers]){timers.delete(id);t.run();}}};
}
async function streamPage(Page,kind,search={}) {
  const stream=await renderToReadableStream(React.createElement('html',null,React.createElement('body',null,
    React.createElement(React.Suspense,{fallback:React.createElement('p',null,'GLOBAL_LOADING')},React.createElement(Page,{kind,search})))));
  const reader=stream.getReader();
  const read=async()=>{const chunk=await reader.read();return chunk.done?'':new TextDecoder().decode(chunk.value);};
  return {stream,read,async rest(){let value='',chunk;while((chunk=await read())!=='')value+=chunk;return value;}};
}
function noInventedData(html) {
  assert.doesNotMatch(html,/>0<\/b>|No matching records|PRIVATE_|SYNTHETIC_LATE|Next page/);
}
for(const kind of ['changes','issues']) for(const phase of ['headers','body']) {
  test(`${kind} streams its own heading and filters while ${phase} are held, then times out with exact native retry`,{timeout:5000},async()=>{
    let release;const held=new Promise(resolve=>{release=resolve;});
    const h=harness(()=>phase==='headers'?held:Promise.resolve({ok:true,json:()=>held}));
    const search={q:'A & B',status:'ACTIVE',scope:'STANDARD',limit:'10',offset:'20',...(kind==='changes'?{source:'ISSUE',project_id:'project / one'}:{severity:'HIGH'}),token:'PRIVATE_TOKEN',redirect:'https://untrusted.invalid'};
    const page=await streamPage(h.Page,kind,search);
    try {
      const first=await page.read();
      assert.match(first,new RegExp('<h1[^>]*>'+(kind==='changes'?'Software Change Requests':'Issues')));
      assert.match(first,/<form[^>]*method="get"/);assert.match(first,/name="q"[^>]*value="A &amp; B"/);
      assert.match(first,/role="status"/);assert.match(first,/aria-busy="true"/);assert.match(first,/>—<\/b>/);
      assert.doesNotMatch(first,/GLOBAL_LOADING|catalog unavailable|Read (changes|issues) again/);noInventedData(first);
      await flush();assert.deepEqual([...h.timers.values()].map(t=>t.delay),[15000]);
      assert.equal(h.requests.length,1);assert.equal(h.requests[0][1].cache,'no-store');
      assert.equal(h.requests[0][1].signal.aborted,false);
      h.expire();const final=await page.rest();
      assert.match(final,new RegExp(kind==='changes'?'Change catalog unavailable':'Issue catalog unavailable'));
      assert.match(final,/>—<\/b>/);noInventedData(final);
      assert.equal(h.requests[0][1].signal.aborted,true);assert.equal(h.timers.size,0);
      const retry=final.match(new RegExp('<a href="([^"]+)">Read '+kind+' again<\\/a>'));
      assert.ok(retry,'retry must be a native link, not a prefetched framework link');
      const url=new URL(retry[1].replaceAll('&amp;','&'),'https://site.invalid');
      assert.equal(url.pathname,'/'+kind);
      for(const [key,value] of Object.entries(search)) if(!['token','redirect'].includes(key))assert.equal(url.searchParams.get(key),value);
      assert.equal(url.searchParams.has('token'),false);assert.equal(url.searchParams.has('redirect'),false);
      assert.doesNotMatch(first+final,/PRIVATE_TOKEN|untrusted\.invalid/);
      release(phase==='headers'?{ok:true,json:async()=>({kind,items:[],total:999})}:{kind,items:[],total:999});
      await flush();assert.equal(h.requests.length,1,'late success must not retry');
    } finally {release(phase==='headers'?{ok:false}:null);await page.stream.allReady;}
  });
}
function suspense(element) {
  if(!React.isValidElement(element))return null;
  if(element.type===React.Suspense)return element;
  for(const child of React.Children.toArray(element.props.children)){const found=suspense(child);if(found)return found;}
  return null;
}
test('kind and normalized filters key the data boundary so navigation cannot reuse old pending content',()=>{
  const h=harness(()=>new Promise(()=>{}));
  const boundary=(kind,search)=>{const page=h.Page({kind,search});assert.equal(typeof page?.then,'undefined','the shell must not await API data');const result=suspense(page);assert.ok(result);return result;};
  const one=boundary('changes',{q:'old',offset:'10'});
  const changed=boundary('changes',{q:'new',offset:'10'});
  const same=boundary('changes',{q:'old',offset:'10',token:'PRIVATE_IGNORED'});
  assert.notEqual(one.key,changed.key);assert.equal(one.key,same.key);
  assert.notEqual(boundary('changes',{}).key,boundary('issues',{}).key);
  assert.notEqual(boundary('changes',{q:['one','two']}).key,boundary('changes',{q:'one'}).key);
  assert.equal(h.requests.length,0,'building the shell must not start reads outside its data boundary');
});
for(const kind of ['changes','issues']) test(`${kind} successful empty data and explicit new read are distinct from failure in both languages`,async()=>{
  for(const locale of ['en','zh']) {
    const failed=harness(async()=>({ok:false}),locale);const first=await streamPage(failed.Page,kind,{q:['a','b'],offset:'20',extra:'PRIVATE_EXTRA'});const failedHtml=await first.rest();
    const label=locale==='zh'?(kind==='changes'?'重新读取变更':'重新读取问题'):`Read ${kind} again`;
    assert.ok(failedHtml.includes(label));assert.match(failedHtml,new RegExp('href="/'+kind+'\\?q=invalid&amp;offset=20"'));noInventedData(failedHtml);
    assert.equal(failed.requests.length,1);assert.equal(failed.timers.size,0);
    const recovered=harness(async()=>({ok:true,json:async()=>({kind,total:0,limit:50,offset:20,next_offset:null,items:[],in_verification:0,ready_for_release:0})}),locale);
    const next=await streamPage(recovered.Page,kind,{q:'invalid',offset:'20'});const html=await next.rest();
    assert.ok(html.includes(locale==='zh'?zh['No matching records on this page.']:'No matching records on this page.'));
    assert.match(html,/>0<\/b>/);assert.ok(!html.includes(label));
    assert.equal(recovered.requests.length,1);assert.equal(recovered.requests[0][0],failed.requests[0][0]);assert.equal(recovered.timers.size,0);
  }
});
for(const kind of ['changes','issues']) test(`${kind} late rejection stays handled after timeout without another read`,async()=>{
  let reject;const h=harness(()=>new Promise((_,fail)=>{reject=fail;}));
  const page=await streamPage(h.Page,kind);await page.read();await flush();
  assert.equal(h.timers.size,1);h.expire();const final=await page.rest();
  assert.match(final,/catalog unavailable/);noInventedData(final);
  reject(Error('PRIVATE_LATE_ERROR'));await flush();assert.equal(h.requests.length,1);assert.equal(h.timers.size,0);
});
for(const kind of ['changes','issues']) test(`${kind} HTTP network JSON and wrong-kind failures release the boundary without private detail`,async()=>{
  for(const fetch of [async()=>({ok:false}),async()=>{throw Error('PRIVATE_NETWORK');},
    async()=>({ok:true,json:async()=>{throw Error('PRIVATE_JSON');}}),
    async()=>({ok:true,json:async()=>({kind:kind==='changes'?'issues':'changes',total:0,items:[]})})]) {
    const h=harness(fetch);const page=await streamPage(h.Page,kind);const html=await page.rest();
    assert.match(html,/catalog unavailable/);noInventedData(html);
    assert.equal(h.requests.length,1);assert.equal(h.timers.size,0);
  }
});
