'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const React=require('react');
const {renderToReadableStream}=require('react-dom/server');
const zh=require('../lib/i18n/zh.json');
function load(file,stubs={},globals={}) {
  const module={exports:{}};
  new Function('require','module','exports',...Object.keys(globals),ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2021,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText)(name=>stubs[name]??require(name),module,module.exports,...Object.values(globals));
  return module.exports;
}
function page(apiGet,language='en') {
  const Localized=({children})=>React.createElement(React.Fragment,null,typeof children==='string'&&language==='zh'?(zh[children]??children):children);
  return load('app/page.tsx',{'../lib/api':{apiGet},'../components/localized':{Localized},'../components/navigation-priority':{PriorityLink:({children,href,...rest})=>React.createElement('a',{href,...rest},children),DashboardReady:()=>React.createElement('i',{'data-dashboard-ready':true})},'../components/page-loading':load('components/page-loading.tsx',{'./localized':{Localized}})}).default;
}
const empty={active_changes:0,open_issues:0,high_open_issues:0,ready_releases:0,current_release:null,recent_activity:[]};
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
async function begin(Page){const stream=await renderToReadableStream(React.createElement('html',null,React.createElement('body',null,React.createElement(Page))));const reader=stream.getReader();const initial=new TextDecoder().decode((await reader.read()).value);return {initial,async rest(){let text='';for(;;){const chunk=await reader.read();if(chunk.done)return text;text+=new TextDecoder().decode(chunk.value);}}};}
function cards(html){for(const href of ['/changes','/issues','/releases/application','/testing/dvp'])assert.match(html,new RegExp('href="'+href+'"'));assert.equal((html.match(/class="metric">—/g)||[]).length,4);assert.doesNotMatch(html,/class="metric">0|data-dashboard-ready/);}
function harness(stage){const headers=deferred(),body=deferred(),calls=[],timers=[];const api=load('lib/api.ts',{'server-only':{},'next/server':{connection:async()=>{}}},{process:{env:{API_BASE_URL:'https://fixture.invalid'}},fetch:(...args)=>{calls.push(args);return headers.promise;},setTimeout:(fn,ms)=>{const timer={fn,ms,cleared:false};timers.push(timer);return timer;},clearTimeout:timer=>{timer.cleared=true;}});if(stage==='body')headers.resolve({ok:true,json:()=>body.promise});return {api,calls,timers,settle(data){if(stage==='headers')headers.resolve({ok:true,json:async()=>data});else body.resolve(data);}};}
for(const stage of ['headers','body'])test(`initial stream has navigable unknown metrics before deferred ${stage}; real API success preserves 15000ms budget`,async()=>{
  const h=harness(stage),s=await begin(page(h.api.apiGet));
  try {assert.match(s.initial,/Lifecycle Dashboard/);assert.match(s.initial,/aria-busy="true"/);assert.match(s.initial,/Reading dashboard data/);cards(s.initial);assert.deepEqual(h.timers.map(t=>t.ms),[15000]);assert.equal(h.calls.length,1);assert.equal(h.calls[0][0],'https://fixture.invalid/api/v1/dashboard/summary');assert.equal(h.calls[0][1].cache,'no-store');}
  finally {h.settle({...empty,active_changes:7,open_issues:5,ready_releases:3,current_release:{id:'r1',version:'1.0',status:'READY',snapshot_no:'S1',coverage:75},recent_activity:[{event_no:'EV1',summary:'REAL_ACTIVITY',entity_ref:'fixture',occurred_at:'2026-01-01'}]});}
  const html=await s.rest();for(const value of ['7','5','3','75%'])assert.match(html,new RegExp('class="metric">'+value));assert.match(html,/REAL_ACTIVITY/);assert.match(html,/data-dashboard-ready/);assert.equal(h.timers[0].cleared,true);assert.equal(h.calls.length,1);
});
for(const stage of ['headers','body'])test(`real API ${stage} timeout does not grant readiness and ignores late data`,async()=>{const h=harness(stage),s=await begin(page(h.api.apiGet));assert.equal(h.timers[0].ms,15000);h.timers[0].fn();const html=await s.rest();cards(html);assert.match(html,/Current release data unavailable/);assert.match(html,/Recent activity unavailable/);assert.doesNotMatch(html,/No activity records|No release data|No current application release/);assert.match(html,/<a href="\/">Read dashboard again/);assert.equal(h.calls[0][1].signal.aborted,true);h.settle({...empty,active_changes:99});await new Promise(r=>setImmediate(r));assert.equal(h.calls.length,1);assert.doesNotMatch(html,/99|data-dashboard-ready/);});
for(const language of ['en','zh'])test(`null failure and genuine empty success remain distinct in ${language}`,async()=>{const unavailable=await begin(page(async()=>null,language));const failure=await unavailable.rest();const failureHtml=unavailable.initial+failure;for(const key of ['Current release data unavailable','Recent activity unavailable','Dashboard data unavailable. Try reading again later.'])assert.ok(failureHtml.includes(language==='zh'?zh[key]:key),key);assert.doesNotMatch(failureHtml,/data-dashboard-ready/);const s=await begin(page(async()=>empty,language));const html=s.initial+await s.rest();assert.equal((html.match(/class="metric">0/g)||[]).length,3);assert.match(html,/data-dashboard-ready/);assert.ok(html.includes(language==='zh'?zh['No activity records available.']:'No activity records available.'));});
test('loading copy is translated and streamed in Chinese',async()=>{const pending=deferred(),s=await begin(page(()=>pending.promise,'zh'));try {for(const key of ['Reading dashboard data','Dashboard metrics are not yet available. You can open a section while the read completes.']){assert.equal(typeof zh[key],'string');assert.ok(s.initial.includes(zh[key]));}cards(s.initial);}finally{pending.resolve(null);await s.rest();}});
