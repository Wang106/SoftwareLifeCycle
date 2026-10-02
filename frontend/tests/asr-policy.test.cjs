'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const ts=require('typescript');
const React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const rid='11111111-1111-4111-8111-111111111111';
function load(file,api,collections){
 const compiled=ts.transpileModule(fs.readFileSync(path.resolve(file),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}};
 const requireMock=name=>{
  if(name==='next/link')return ({href,children})=>React.createElement('a',{href},children);
  if(name.endsWith('/lib/api'))return {apiGet:api};
  if(name.endsWith('/localized'))return {Localized:({children})=>React.createElement(React.Fragment,null,children)};
  if(name.endsWith('/asr-policy'))return {AsrPolicy:collections};
  return require(name);
 };
 new Function('require','module','exports',compiled)(requireMock,module,module.exports);return module.exports;
}
const sid='22222222-2222-4222-8222-222222222222';
const aid='33333333-3333-4333-8333-333333333333';
const summary={release_id:rid,snapshot:{id:sid,snapshot_no:'SNAP-RAW',status:'DRAFT',content_hash:'raw-hash',is_current_snapshot:true},artifact_count:123,sha_recorded_count:100,policy_recorded_count:45,rule_count:999};
function page(items=[],extra={}){return {release_id:rid,snapshot_id:sid,snapshot_artifact_id:null,total:999,next_offset:1,items,...extra};}
async function render(search={},responses={}){
 const requests=[];
 const api=async url=>{requests.push(url);if(url.includes('/summary?'))return 'summary' in responses?responses.summary:summary;
  return url.includes('/artifacts?')?('artifacts' in responses?responses.artifacts:page([{id:aid,component_code:'RAW',component_version:'raw-version',filename:'raw.hex',artifact_type:'HEX',sha256:'a'.repeat(64),classification:'CONFIDENTIAL',distribution_level:'INTERNAL_ONLY',ai_access_policy:'DENY',rule_count:999}])):('rules' in responses?responses.rules:page([{id:'rule-id',snapshot_artifact_id:aid,filename:'raw.hex',component_code:'RAW',distribution_level:'INTERNAL_ONLY',recipient_type:'CUSTOMER',purpose:'PRODUCTION',recipient_code:'raw-recipient',decision:'ALLOW'}],{snapshot_artifact_id:search.policy_artifact_id??null}));};
 const {AsrPolicy}=load('components/asr-policy.tsx',api);const html=renderToStaticMarkup(await AsrPolicy({releaseId:rid,search}));return {html,requests};
}
function links(html){return [...html.matchAll(/href="([^"]+)"/g)].map(m=>m[1].replaceAll('&amp;','&'));}
test('policy full recording counts and raw ALLOW keep internal distribution denied',async()=>{
 const {html,requests}=await render({policy_limit:'1',policy_artifact_offset:'2',policy_rule_offset:'3'});
 assert.ok(html.includes('123')&&html.includes('100')&&html.includes('45')&&html.includes('999')&&html.includes('raw-hash')&&html.includes('raw.hex'));
 assert.ok(html.includes('ALLOW')&&html.includes('External distribution denied')&&html.includes('DRAFT'));
 assert.equal(requests.length,3);assert.ok(requests[1].includes('snapshot_id='+sid)&&requests[1].includes('limit=1&offset=2'));assert.ok(requests[2].includes('limit=1&offset=3'));
 const parameters=links(html).filter(url=>url.includes('?')).map(url=>new URL(url,'https://test.invalid').searchParams);
 assert.ok(parameters.every(q=>q.get('policy_snapshot_id')===sid));
 assert.ok(parameters.some(q=>q.get('policy_artifact_offset')==='1'&&q.get('policy_rule_offset')==='3'));
 assert.ok(parameters.some(q=>q.get('policy_artifact_offset')==='2'&&q.get('policy_rule_offset')==='1'));
});
test('artifact drilldown preserves artifact offset and resets rule offset on exact snapshot',async()=>{
 const {html,requests}=await render({policy_artifact_id:aid,policy_artifact_offset:'2',policy_rule_offset:'3'});
 assert.ok(requests[2].includes('snapshot_artifact_id='+aid));assert.ok(html.includes('Selected artifact: '));
 const params=links(html).filter(url=>url.includes('?')).map(url=>new URL(url,'https://test.invalid').searchParams);
 assert.ok(params.some(q=>q.get('policy_artifact_id')===aid&&q.get('policy_rule_offset')==='0'&&q.get('policy_artifact_offset')==='2'));
 assert.ok(params.some(q=>!q.has('policy_artifact_id')&&q.get('policy_rule_offset')==='0'&&q.get('policy_snapshot_id')===sid));
});
test('summary unavailable, foreign release or wrong requested pin stops child reads',async()=>{
 for(const response of [null,{...summary,release_id:'foreign'},{...summary,snapshot:{...summary.snapshot,id:'wrong-pin'}}]){
  const {html,requests}=await render({policy_snapshot_id:sid},{summary:response});
  assert.ok(html.includes('Snapshot policy unavailable'));assert.equal(requests.length,1);assert.ok(requests[0].includes('/summary?'));
 }
});
test('no snapshot stops child reads instead of zero evidence tables',async()=>{
 const {html,requests}=await render({}, {summary:{...summary,snapshot:null}});
 assert.ok(html.includes('No snapshot has been recorded'));assert.equal(requests.length,1);assert.ok(!html.includes('Frozen artifact manifest'));
});
test('foreign child release or snapshot rejected independently without bulk fallback',async()=>{
 for(const extra of [{release_id:'foreign'},{snapshot_id:'foreign'}]){
  const {html,requests}=await render({}, {artifacts:page([],extra)});
  assert.ok(html.includes('Policy artifact page unavailable')&&html.includes('raw-recipient'));assert.equal(requests.length,3);
 }
 const {html}=await render({policy_artifact_id:aid}, {rules:page([],{snapshot_artifact_id:'foreign'})});
 assert.ok(html.includes('Policy rule page unavailable')&&html.includes('raw.hex'));
});
test('array rule filter and offset forwarded as invalid while artifact read unaffected',async()=>{
 const {html,requests}=await render({policy_limit:'1',policy_artifact_id:[aid,aid],policy_rule_offset:['0','1'],policy_artifact_offset:'2'},{rules:null});
 assert.ok(requests[1].includes('offset=2')&&!requests[1].includes('snapshot_artifact_id'));
 assert.ok(requests[2].includes('offset=invalid')&&requests[2].includes('snapshot_artifact_id=invalid'));
 assert.ok(html.includes('Policy rule page unavailable')&&html.includes('raw.hex'));
 assert.ok(links(html).some(url=>url.includes('policy_rule_offset=invalid')));
});
test('empty and beyond-end pages retain summary counts and first links',async()=>{
 const {html}=await render({}, {artifacts:page([],{next_offset:null}),rules:page([],{next_offset:null,total:0})});
 assert.ok(html.includes('No frozen artifacts on this page.')&&html.includes('No recipient rules on this page.')&&html.includes('123'));
 assert.ok(!html.includes('Next page'));assert.equal(links(html).filter(url=>url.includes('offset=0')).length,3);
});
test('historical pin keeps exact UUID and clear latest link',async()=>{
 const {html,requests}=await render({policy_snapshot_id:sid},{summary:{...summary,snapshot:{...summary.snapshot,is_current_snapshot:false}}});
 assert.ok(html.includes('Viewing a pinned historical snapshot.')&&html.includes('Read latest policy'));
 assert.ok(requests.every(url=>url.includes('snapshot_id='+sid)));
});
