'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const rid='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222';
const summary={release_id:rid,snapshot_id:sid,snapshot:{id:sid,snapshot_no:'RAW-SNAPSHOT',content_hash:'a'.repeat(64),status:'FROZEN'},overall:'READY',approval_eligible:true,exception_total:123,coverage:{snapshot_no:'RAW-SNAPSHOT',dvp_execution_coverage:67},artifact_policy:{sha_completeness:100,policy_completeness:100},rules:[{group:'Verification',rule:'Required DVP executed on current snapshot',raw:'FAIL',effective:'EXCEPTION_GRANTED',evidence:'2 / 3'},{group:'Artifact Control',rule:'SHA-256 complete for formal artifacts',raw:'PASS',effective:'PASS',evidence:'4 / 4'}]};
const row={id:'raw-exception-id',exception_no:'RAW-EXCEPTION',status:'APPROVED',scope:'RAW-SCOPE',rule_code:'RAW-RULE',snapshot_no:'RAW-SNAPSHOT',reason:'RAW-REASON',compensating_control:'RAW-CONTROL'};
const page={release_id:rid,snapshot_id:sid,total:123,next_offset:1,items:[row]};
async function render(search={},responses={}){
 const requests=[];const api=async url=>{requests.push(url);return url.includes('/summary?')?('summary' in responses?responses.summary:summary):('exceptions' in responses?responses.exceptions:page)};
 const compiled=ts.transpileModule(fs.readFileSync('app/releases/application/[releaseId]/readiness/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};const mock=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:api}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,children)}:require(n);
 new Function('require','module','exports',compiled)(mock,module,module.exports);
 return {html:renderToStaticMarkup(await module.exports.default({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve(search)})),requests};
}
function queries(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&')).filter(u=>u.includes('?')).map(u=>new URL(u,'https://example.test').searchParams)}
test('readiness preserves raw/effective gates, full totals, UUID/hash and exception metadata',async()=>{
 const {html,requests}=await render({readiness_limit:'1',readiness_exception_offset:'2'});
 for(const text of ['123',sid,'a'.repeat(64),'RAW-EXCEPTION','RAW-SCOPE','RAW-REASON','RAW-CONTROL','EXCEPTION_GRANTED','2 / 3'])assert.ok(html.includes(text),text);
 assert.equal(requests.length,2);assert.ok(requests[0].includes('/readiness/summary?'));assert.ok(requests[1].endsWith('snapshot_id='+sid+'&limit=1&offset=2'));
 assert.ok(queries(html).every(q=>q.get('readiness_snapshot_id')===sid&&q.get('readiness_limit')==='1'));assert.ok(queries(html).some(q=>q.get('readiness_exception_offset')==='1'));
});
for(const result of [null,{...summary,release_id:'foreign'},{...summary,snapshot_id:'foreign'},{...summary,snapshot:{...summary.snapshot,id:'foreign'}}])test('summary failure/foreign/stale pin never falls back or reads exceptions',async()=>{
 const {html,requests}=await render({readiness_snapshot_id:sid},{summary:result});assert.equal(requests.length,1);assert.ok(html.includes('Readiness unavailable')&&html.includes('Read latest readiness'));
});
for(const response of [null,{...page,release_id:'foreign'},{...page,snapshot_id:'foreign'}])test('exception failure/foreign pin retains gates and complete total',async()=>{
 const {html,requests}=await render({}, {exceptions:response});assert.equal(requests.length,2);assert.ok(html.includes('Readiness exception page unavailable.')&&html.includes('123')&&html.includes('EXCEPTION_GRANTED'));
 assert.ok(!html.includes('RAW-EXCEPTION')&&!html.includes('None recorded for the current snapshot.'));
});
test('empty beyond-end page is not absence of recorded exceptions',async()=>{
 const {html}=await render({readiness_exception_offset:'999'},{exceptions:{...page,next_offset:null,items:[]}});
 assert.ok(html.includes('No approved exceptions on this page.')&&html.includes('123'));assert.ok(!html.includes('Next page'));assert.ok(queries(html).some(q=>q.get('readiness_exception_offset')==='0'));
});
test('zero summary is labeled none and preserves blocked gates',async()=>{
 const {html}=await render({}, {summary:{...summary,overall:'NOT_READY',approval_eligible:false,exception_total:0},exceptions:{...page,total:0,next_offset:null,items:[]}});
 assert.ok(html.includes('BLOCKED')&&html.includes('None recorded for the current snapshot.'));
});
test('explicit no snapshot remains pinned none without fabricated snapshot hash',async()=>{
 const {html,requests}=await render({readiness_snapshot_id:'none'}, {summary:{...summary,snapshot_id:'none',snapshot:null,overall:'NOT_READY',approval_eligible:false,exception_total:0,coverage:{snapshot_no:null,dvp_execution_coverage:0}},exceptions:{...page,snapshot_id:'none',total:0,next_offset:null,items:[]}});
 assert.ok(requests.every(u=>u.includes('snapshot_id=none')));assert.ok(html.includes('No snapshot')&&html.includes('BLOCKED')&&!html.includes('a'.repeat(64)));
});
test('array inputs fail closed and invalid page parameters leave gates visible',async()=>{
 let result=await render({readiness_snapshot_id:[sid,sid]},{summary:null});assert.ok(result.requests[0].endsWith('snapshot_id=invalid'));
 result=await render({readiness_limit:['1','2'],readiness_exception_offset:['0','1']},{exceptions:null});assert.ok(result.requests[1].endsWith('limit=invalid&offset=invalid'));assert.ok(result.html.includes('EXCEPTION_GRANTED'));
});
