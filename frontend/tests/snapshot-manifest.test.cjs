'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const rid='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222',aid='33333333-3333-4333-8333-333333333333';
const snapshot={id:sid,release_id:rid,snapshot_no:'SNAP RAW',snapshot_number:8,status:'DRAFT',content_hash:'b'.repeat(64),created_at:'2026-10-02T00:00:00',is_current_snapshot:false,release:{id:rid,type:'STANDARD',version:'RAW'},artifact_count:123,rule_count:999};
function load(file,api){
 const compiled=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};
 const req=name=>name==='next/link'?({href,children})=>React.createElement('a',{href},children):name.endsWith('/lib/api')?{apiGet:api}:name.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,children)}:name.endsWith('/snapshot-manifest')?{SnapshotManifest:()=>React.createElement('div',null,'bounded collections')}:require(name);
 new Function('require','module','exports',compiled)(req,module,module.exports);return module.exports;
}
function page(items=[],extra={}){return {release_id:rid,snapshot_id:sid,snapshot_no:snapshot.snapshot_no,snapshot_artifact_id:null,total:999,next_offset:1,items,...extra};}
function links(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));}
async function render(search={},responses={}){
 const requests=[];
 const api=async url=>{requests.push(url);const extra={snapshot_artifact_id:typeof search.manifest_artifact_id==='string'?search.manifest_artifact_id:null};return url.includes('/artifacts?')?('artifacts' in responses?responses.artifacts:page([{id:aid,filename:'raw.hex',component_code:'RAW',component_version:'raw-version',artifact_type:'HEX',sha256:'a'.repeat(64),classification:'CONFIDENTIAL',distribution_level:'INTERNAL_ONLY',ai_access_policy:'DENY',rule_count:999}],extra)):('rules' in responses?responses.rules:page([{id:'rule-id',snapshot_artifact_id:aid,filename:'raw.hex',component_code:'RAW',distribution_level:'INTERNAL_ONLY',recipient_type:'CUSTOMER',purpose:'PRODUCTION',recipient_code:'raw-recipient',decision:'ALLOW'}],extra));};
 const {SnapshotManifest}=load('components/snapshot-manifest.tsx',api);return {html:renderToStaticMarkup(await SnapshotManifest({snapshot,search})),requests};
}
test('full hashes, exact anchor, counts and independent pinned pagination',async()=>{
 const {html,requests}=await render({manifest_limit:'1',manifest_artifact_offset:'2',manifest_rule_offset:'3'});
 assert.equal(requests.length,2);assert.ok(requests[0].includes('/SNAP%20RAW/artifacts?snapshot_id='+sid+'&limit=1&offset=2'));assert.ok(requests[1].includes('limit=1&offset=3'));
 assert.ok(html.includes('a'.repeat(64))&&html.includes('artifact-'+aid)&&html.includes('123')&&html.includes('999')&&html.includes('ALLOW')&&html.includes('External distribution denied'));
 const qs=links(html).map(u=>new URL(u,'https://test.invalid').searchParams);assert.ok(qs.every(q=>q.get('manifest_snapshot_id')===sid));
 assert.ok(qs.some(q=>q.get('manifest_artifact_offset')==='1'&&q.get('manifest_rule_offset')==='3'));
 assert.ok(qs.some(q=>q.get('manifest_artifact_offset')==='2'&&q.get('manifest_rule_offset')==='1'));
});
test('selecting exact file filters both reads, resets both cursors; clearing restores all',async()=>{
 const {html,requests}=await render({manifest_artifact_id:aid,manifest_artifact_offset:'2',manifest_rule_offset:'3'});
 assert.ok(requests.every(u=>u.includes('snapshot_artifact_id='+aid)));
 const qs=links(html).map(u=>new URL(u,'https://test.invalid').searchParams);
 assert.ok(qs.some(q=>q.get('manifest_artifact_id')===aid&&q.get('manifest_artifact_offset')==='0'&&q.get('manifest_rule_offset')==='0'));
 assert.ok(qs.some(q=>!q.has('manifest_artifact_id')&&q.get('manifest_artifact_offset')==='0'&&q.get('manifest_rule_offset')==='0'));
});
for(const key of ['release_id','snapshot_id','snapshot_no','snapshot_artifact_id'])test('wrong child '+key+' fails only its own table with no fallback',async()=>{
 const {html,requests}=await render({}, {artifacts:page([],{[key]:'foreign'})});assert.ok(html.includes('Manifest artifact page unavailable')&&html.includes('raw-recipient'));assert.equal(requests.length,2);
 const other=await render({}, {rules:page([],{[key]:'foreign'})});assert.ok(other.html.includes('Manifest rule page unavailable')&&other.html.includes('raw.hex'));
});
test('invalid arrays passed for API validation; empty pages retain total counts',async()=>{
 const {requests}=await render({manifest_limit:['1','2'],manifest_artifact_id:[aid,aid],manifest_rule_offset:['0','1']},{artifacts:null,rules:null});
 assert.ok(requests.every(u=>u.includes('limit=invalid')&&u.includes('snapshot_artifact_id=invalid')));assert.ok(requests[1].includes('offset=invalid'));
 const {html}=await render({}, {artifacts:page([],{next_offset:null,total:123}),rules:page([],{next_offset:null,total:999})});
 assert.ok(html.includes('123')&&html.includes('999')&&html.includes('No frozen artifacts on this page.')&&html.includes('No recipient rules on this page.')&&!html.includes('Next page'));
});
async function parent(response=snapshot,search={}){
 const requests=[];const api=async u=>{requests.push(u);return response;};const Page=load('app/snapshots/[snapshotNo]/page.tsx',api).default;
 return {html:renderToStaticMarkup(await Page({params:Promise.resolve({snapshotNo:snapshot.snapshot_no}),searchParams:Promise.resolve(search)})),requests};
}
test('parent summary preserves historical and preparation semantics with exact ids',async()=>{
 const {html,requests}=await parent();assert.deepEqual(requests,['/api/v1/snapshots/SNAP%20RAW/summary']);
 assert.ok(html.includes('b'.repeat(64))&&html.includes('HISTORICAL')&&html.includes('A newer snapshot exists.')&&html.includes('bounded collections'));
 const href=links(html).find(u=>u.includes('operation=test-release'));assert.equal(new URL(href,'https://test.invalid').searchParams.get('snapshot'),sid);
 assert.ok(links(html).includes('/releases/standard/'+rid)&&links(html).includes('/snapshots/SNAP%20RAW/compare'));
});
test('missing or foreign parent and invalid pin fail closed',async()=>{
 for(const [response,search] of [[null,{}],[{...snapshot,snapshot_no:'foreign'},{}],[snapshot,{manifest_snapshot_id:'foreign'}],[snapshot,{manifest_snapshot_id:[sid,sid]}]]){
  const {html,requests}=await parent(response,search);assert.ok(html.includes('Snapshot unavailable')&&!html.includes('bounded collections'));assert.equal(requests.length,1);
 }
});
test('missing release retains frozen identity without fabricated preparation targets',async()=>{
 const {html}=await parent({...snapshot,release:null});assert.ok(html.includes('Release unavailable')&&html.includes(sid)&&html.includes('bounded collections'));assert.ok(!html.includes('operation=test-release')&&!html.includes('operation=delivery'));
});
