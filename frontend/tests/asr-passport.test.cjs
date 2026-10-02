'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const ts=require('typescript');const React=require('react');const {renderToStaticMarkup}=require('react-dom/server');
const rid='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222',did='33333333-3333-4333-8333-333333333333';
const summary={release_id:rid,selection:{snapshot_id:sid,decision_id:did},profile:{id:rid,version:'RAW-VERSION',status:'APPROVED',software:{name:'RAW-SOFTWARE',code:'RAW-CODE'},snapshot:{id:sid,snapshot_no:'RAW-SNAPSHOT',content_hash:'a'.repeat(64),status:'FROZEN',is_current_snapshot:true}},decision:{decision_no:'RAW-DECISION',decision:'RELEASE',snapshot_id:sid,snapshot_no:'RAW-SNAPSHOT',is_current_snapshot:true,is_latest_decision:true,context_consistent:true,decided_by:'RAW-ACTOR',decided_at:'2026-10-02T12:30:00',approval_no:'RAW-APR',approval_status:'APPROVED',decision_notes:'RAW-NOTE'},counts:{decisions:123,deliveries:234,distributions:345,authorizations:456}};
const items={decisions:[{...summary.decision,snapshot_content_hash:'b'.repeat(64),is_selected_snapshot:true}],deliveries:[{id:'delivery-id',package_no:'RAW-PACKAGE',revision:9,status:'DRAFT',snapshot_no:'RAW-SNAPSHOT',recipient_code:'RAW-RECIPIENT'}],distributions:[{id:'distribution-id',distribution_no:'RAW-DISTRIBUTION',package_no:'RAW-PACKAGE',package_revision:9,recipient_code:'RAW-RECIPIENT',status:'SENT'}],authorizations:[{id:'authorization-id',authorization_no:'RAW-AUTH',snapshot_no:'RAW-SNAPSHOT',site_code:'RAW-SITE',line_code:'RAW-LINE',status:'APPROVED'}]};
async function render(search={},responses={}){
 const requests=[];const api=async url=>{requests.push(url);if(url.includes('/summary?'))return 'summary' in responses?responses.summary:summary;
 const kind=url.split('/').at(-1).split('?')[0];return kind in responses?responses[kind]:{release_id:rid,...summary.selection,total:summary.counts[kind],next_offset:1,items:items[kind]};};
 const compiled=ts.transpileModule(fs.readFileSync('app/releases/application/[releaseId]/passport/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};const requireMock=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:api}:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,children)}:require(n);
 new Function('require','module','exports',compiled)(requireMock,module,module.exports);
 const html=renderToStaticMarkup(await module.exports.default({params:Promise.resolve({releaseId:rid}),searchParams:Promise.resolve(search)}));return {html,requests};
}
function queries(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&')).filter(u=>u.includes('?')).map(u=>new URL(u,'https://example.test').searchParams);}
test('passport bounded groups retain full counts, full hashes and public fields',async()=>{
 const {html,requests}=await render({passport_limit:'1',passport_decisions_offset:'2',passport_deliveries_offset:'3'});
 for(const raw of ['123','234','345','456','RAW-ACTOR','RAW-NOTE','RAW-SOFTWARE','RAW-PACKAGE','RAW-DISTRIBUTION','RAW-AUTH','a'.repeat(64),'b'.repeat(64)])assert.ok(html.includes(raw),raw);
 assert.equal(requests.length,5);assert.ok(requests[0].includes('/passport/summary?'));assert.ok(requests.slice(1).every(u=>u.includes('snapshot_id='+sid)&&u.includes('decision_id='+did)&&u.includes('limit=1')));
 assert.ok(requests[1].endsWith('offset=2')&&requests[2].endsWith('offset=3'));assert.ok(html.includes('FORMALLY RELEASED'));
 const q=queries(html);assert.ok(q.every(p=>p.get('passport_snapshot_id')===sid&&p.get('passport_decision_id')===did));
 assert.ok(q.some(p=>p.get('passport_decisions_offset')==='1'&&p.get('passport_deliveries_offset')==='3'));
 assert.ok(q.some(p=>p.get('passport_decisions_offset')==='2'&&p.get('passport_deliveries_offset')==='1'));
});
for(const kind of ['decisions','deliveries','distributions','authorizations'])test(kind+' failure remains independent and keeps summary',async()=>{
 const {html,requests}=await render({}, {[kind]:null});assert.ok(html.includes('234')&&html.includes('Passport record page unavailable.'));assert.equal(requests.length,5);
 for(const other of Object.keys(items).filter(x=>x!==kind))assert.ok(html.includes(other==='decisions'?'Formal decision history':items[other][0][other==='deliveries'?'package_no':other==='distributions'?'distribution_no':'authorization_no']));
});
for(const field of ['release_id','snapshot_id','decision_id'])test('reject foreign child '+field,async()=>{
 const {html}=await render({}, {deliveries:{release_id:rid,...summary.selection,[field]:'foreign',items:items.deliveries,total:1,next_offset:null}});assert.ok(html.includes('Passport record page unavailable.')&&!html.includes('RAW-PACKAGE</span> Rev'));
});
for(const result of [null,{...summary,release_id:'foreign'},{...summary,profile:{...summary.profile,id:'foreign'}},{...summary,selection:{...summary.selection,snapshot_id:'wrong'}}])test('unavailable/foreign/mismatched parent stops child reads',async()=>{
 const {html,requests}=await render({passport_snapshot_id:sid,passport_decision_id:did},{summary:result});assert.equal(requests.length,1);assert.ok(html.includes('Software passport unavailable'));
});
for(const field of ['is_current_snapshot','is_latest_decision','context_consistent'])test('historical or inconsistent '+field+' never claims current release',async()=>{
 const {html}=await render({}, {summary:{...summary,decision:{...summary.decision,[field]:false}}});assert.ok(html.includes('HISTORICAL RELEASE')&&!html.includes('FORMALLY RELEASED'));assert.ok(html.includes('Read latest passport'));
});
test('explicit missing pins stay missing and no formal decision is fabricated',async()=>{
 const empty={...summary,selection:{snapshot_id:'none',decision_id:'none'},decision:null,profile:{...summary.profile,snapshot:null}};
 const {html,requests}=await render({passport_snapshot_id:'none',passport_decision_id:'none'}, {summary:empty,decisions:null,deliveries:null,distributions:null,authorizations:null});
 assert.ok(requests.every(u=>u.includes('snapshot_id=none')&&u.includes('decision_id=none')));assert.ok(html.includes('NOT RELEASED')&&html.includes('For exact release'));
});
test('empty beyond-end pages keep total counts and first-page links',async()=>{
 const responses=Object.fromEntries(Object.keys(items).map(k=>[k,{release_id:rid,...summary.selection,total:summary.counts[k],next_offset:null,items:[]}]))
 const {html}=await render({},responses);assert.ok(html.includes('No outbound records on these pages.')&&html.includes('234'));assert.ok(!html.includes('Next page'));assert.equal(queries(html).length,4);
});
test('array query inputs fail closed without dropping pins',async()=>{
 const {requests}=await render({passport_snapshot_id:[sid,sid],passport_decision_id:did},{summary:null});assert.ok(requests[0].includes('snapshot_id=invalid'));
 const result=await render({passport_limit:['1','2'],passport_deliveries_offset:['0','1']},{deliveries:null});assert.ok(result.requests[2].includes('limit=invalid&offset=invalid'));
});
