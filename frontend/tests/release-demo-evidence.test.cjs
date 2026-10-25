'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const code=ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText;
const i18n={exports:{}};new Function('require','module','exports',code)(n=>n.endsWith('zh.json')?dict:templates,i18n,i18n.exports);
const confirmation={exports:{}};new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/release-evidence-confirmation.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(require,confirmation,confirmation.exports);
const row={release_id:'11111111-1111-4111-8111-111111111111',version:'DEMO-EVIDENCE-ASR-B-2.0',release_type:'APPLICATION',record_status:'DRAFT',snapshot:{id:'22222222-2222-4222-8222-222222222222',snapshot_no:'SNAP-2',status:'FROZEN',content_hash:'a'.repeat(64)},readiness:{overall:'NOT_READY',approval_eligible:false,coverage:{snapshot_id:'22222222-2222-4222-8222-222222222222',snapshot_no:'SNAP-2',required_dvp_total:3,current_snapshot_executed:0,current_snapshot_passed:0,snapshot_match:false},rules:[{group:'Verification',rule:'Required DVP executed on current snapshot',effective:'FAIL',evidence:'0 / 3'}]},approval:{approval_no:'APR-2',status:'APPROVED',current_snapshot_bound:true},decision:{decision_no:'RD-2',decision:'HOLD',readiness_status:'NOT_READY',snapshot_id:'22222222-2222-4222-8222-222222222222',current_evidence_bound:true},current_release_confirmed:false,change_request_no:'SCR-DEMO',dvp_items:[{id:'33333333-3333-4333-8333-333333333333',item_no:'DVP-SOFTWARE'}]};
async function render(data,locale='en'){
 const compiled=ts.transpileModule(fs.readFileSync('app/demo/releases/page.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const module={exports:{}},calls=[];
 const translate=c=>typeof c==='string'?i18n.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:async path=>{calls.push(path);return data;}}:n.endsWith('/release-evidence-confirmation')?confirmation.exports:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
 new Function('require','module','exports',compiled)(req,module,module.exports);
 return {html:renderToStaticMarkup(await module.exports.default()),calls};
}
for(const locale of ['en','zh'])test('blocked approval evidence and exact links in '+locale,async()=>{
 const {html,calls}=await render({sample_only:true,initialized:true,items:[row]},locale);
 assert.deepEqual(calls,['/api/v1/demo/release-evidence']);
 assert.ok(html.includes(locale==='en'?'Current evidence does not confirm a formal release.':'当前证据不能确认正式发布。'));
 assert.ok(html.includes(locale==='en'?'Tests on an older snapshot':'旧快照上的测试'));
 assert.ok(html.includes('APR-2')&&html.includes('RD-2')&&html.includes('22222222-2222-4222-8222-222222222222'));
 assert.ok(html.includes('/testing/dvp/33333333-3333-4333-8333-333333333333?release_id=11111111-1111-4111-8111-111111111111&amp;snapshot_no=SNAP-2'));
 assert.ok(html.includes('/releases/application/11111111-1111-4111-8111-111111111111/passport'));
 assert.ok(!html.includes('<form')&&!html.includes('operation='));
});
test('positive SSR has exact decision and no application-only link',async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[{...row,release_type:'STANDARD',current_release_confirmed:true,readiness:{...row.readiness,overall:'READY',approval_eligible:true,coverage:{...row.readiness.coverage,snapshot_match:true}},decision:{...row.decision,decision:'RELEASE',readiness_status:'READY'}}]});
 assert.ok(html.includes('Formal release evidence matches the current snapshot.'));
 assert.ok(html.includes('/releases/standard/11111111-1111-4111-8111-111111111111')&&!html.includes('/passport'));
});
test('claimed release with a non-frozen snapshot fails closed',async()=>{
 const claimed={...row,current_release_confirmed:true,snapshot:{...row.snapshot,status:'DRAFT'},readiness:{...row.readiness,overall:'READY',approval_eligible:true,coverage:{...row.readiness.coverage,snapshot_match:true}},decision:{...row.decision,decision:'RELEASE',readiness_status:'READY'}};
 const {html}=await render({sample_only:true,initialized:true,items:[claimed]});
 assert.ok(html.includes('Current evidence does not confirm a formal release.'));
 assert.ok(html.includes('Release evidence response is inconsistent; formal release is not confirmed.'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});
for(const locale of ['en','zh'])test('unknown release type stays visible without an invented SSR or ASR route in '+locale,async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[{...row,release_type:'FUTURE'}]},locale);
 assert.ok(html.includes(i18n.exports.translateText('Unrecognized release type',locale)));
 assert.ok(html.includes(i18n.exports.translateText('Unknown values are not mapped to SSR or ASR.',locale)));
 assert.ok(html.includes('<code>FUTURE</code>'));
 assert.ok(!html.includes('/releases/application/11111111-1111-4111-8111-111111111111'));
 assert.ok(!html.includes('/releases/standard/11111111-1111-4111-8111-111111111111'));
 assert.ok(!html.includes('/releases/application/11111111-1111-4111-8111-111111111111/readiness'));
 assert.ok(!html.includes('/releases/application/11111111-1111-4111-8111-111111111111/passport'));
});
for(const [name,data,expected] of [['unavailable',null,'Evidence API unavailable'],['not installed',{sample_only:true,initialized:false,items:[]},'Evidence samples not installed'],['foreign response',{sample_only:false,initialized:true,items:[row]},'Evidence API unavailable']])test(name+' never fabricates proof',async()=>{
 const {html}=await render(data);assert.ok(html.includes(expected)&&!html.includes('APR-2')&&!html.includes('RD-2'));
});
test('uninitialized responses carrying evidence rows fail closed',async()=>{
 const {html}=await render({sample_only:true,initialized:false,items:[row]});
 assert.ok(html.includes('Evidence API unavailable'));
 assert.ok(!html.includes('Evidence samples not installed'));
 assert.ok(!html.includes('APR-2')&&!html.includes('RD-2'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});
test('initialized responses without evidence rows fail closed',async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[]});
 assert.ok(html.includes('Evidence API unavailable'));
 assert.ok(!html.includes('Evidence samples not installed'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});
test('malformed list or row fails closed without throwing during SSR',async()=>{
 const malformed=[{sample_only:true,initialized:true,items:null},
  {sample_only:true,initialized:true,items:[null]},
  {sample_only:true,initialized:true,items:[{...row,release_id:'r'.repeat(65)}]},
  {sample_only:true,initialized:true,items:[{...row,readiness:null}]},
  {sample_only:true,initialized:true,items:[{...row,readiness:{...row.readiness,coverage:null}}]},
  {sample_only:true,initialized:true,items:[{...row,readiness:{...row.readiness,rules:[{...row.readiness.rules[0],rule:'r'.repeat(241)}]}}]},
  {sample_only:true,initialized:true,items:[{...row,snapshot:{...row.snapshot,status:undefined}}]},
  {sample_only:true,initialized:true,items:[{...row,dvp_items:[{id:null,item_no:'DVP'}]}]},
  {sample_only:true,initialized:true,items:[{...row,dvp_items:[{id:'item',item_no:'d'.repeat(51)}]}]},
  {sample_only:true,initialized:true,items:[{...row,change_request_no:'c'.repeat(51)}]},
  {sample_only:true,initialized:true,items:[{...row,current_release_confirmed:'true'}]}];
 for(const value of malformed){
  const {html}=await render(value);
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('APR-2')&&!html.includes('RD-2'));
 }
});
test('non-canonical snapshot hashes never produce demonstration release proof',async()=>{
 const malformed=['a'.repeat(63),'a'.repeat(65),'g'.repeat(64),'A'.repeat(64)];
 for(const content_hash of malformed){
  const value={sample_only:true,initialized:true,items:[{...row,snapshot:{...row.snapshot,content_hash}}]};
  const {html}=await render(value);
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('APR-2')&&!html.includes('RD-2'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});
test('non-canonical UUID identities never produce demonstration release proof',async()=>{
 const malformed=[
  {...row,release_id:'not-a-uuid'},
  {...row,snapshot:{...row.snapshot,id:'22222222-2222-4222-8222-22222222222A'}},
  {...row,readiness:{...row.readiness,coverage:{...row.readiness.coverage,snapshot_id:'snapshot-id'}}},
  {...row,decision:{...row.decision,snapshot_id:'22222222222242228222222222222222'}},
  {...row,dvp_items:[{...row.dvp_items[0],id:'dvp-item'}]},
 ];
 for(const item of malformed){
  const {html}=await render({sample_only:true,initialized:true,items:[item]});
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('APR-2')&&!html.includes('RD-2'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});
test('impossible coverage counts never produce demonstration release proof',async()=>{
 const impossible=[
  {...row.readiness.coverage,current_snapshot_executed:2,current_snapshot_passed:3,snapshot_match:true},
  {...row.readiness.coverage,current_snapshot_executed:4,current_snapshot_passed:3,snapshot_match:true},
 ];
 for(const coverage of impossible){
  const value={sample_only:true,initialized:true,items:[{...row,current_release_confirmed:true,
   readiness:{...row.readiness,overall:'READY',approval_eligible:true,coverage},
   decision:{...row.decision,decision:'RELEASE',readiness_status:'READY'}}]};
  const {html}=await render(value);
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});
test('readiness snapshot identity contradictions make the complete demonstration unavailable',async()=>{
 const malformed=[
  {...row,readiness:{...row.readiness,coverage:{...row.readiness.coverage,snapshot_id:'66666666-6666-4666-8666-666666666666'}}},
  {...row,readiness:{...row.readiness,coverage:{...row.readiness.coverage,snapshot_no:'SNAP-DIFFERENT'}}},
  {...row,snapshot:null,approval:null,decision:null,current_release_confirmed:false,
   readiness:{...row.readiness,coverage:{...row.readiness.coverage,snapshot_match:true}}},
 ];
 for(const item of malformed){
  const {html}=await render({sample_only:true,initialized:true,items:[item]});
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});
test('contradictory binding claims make the complete demonstration unavailable',async()=>{
 const malformed=[
  {...row,snapshot:null,approval:{...row.approval,current_snapshot_bound:true}},
  {...row,approval:{...row.approval,current_snapshot_bound:false},decision:{...row.decision,current_evidence_bound:true}},
  {...row,decision:{...row.decision,snapshot_id:'66666666-6666-4666-8666-666666666666',current_evidence_bound:true}},
 ];
 for(const item of malformed){
  const {html}=await render({sample_only:true,initialized:true,items:[item]});
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('Current snapshot bound')&&!html.includes('Current evidence bound'));
 }
});
test('duplicate readiness rule identities never produce demonstration release proof',async()=>{
 const duplicate={...row.readiness.rules[0],effective:'PASS',evidence:'3 / 3'};
 const value={sample_only:true,initialized:true,items:[{...row,current_release_confirmed:true,
  readiness:{...row.readiness,overall:'READY',approval_eligible:true,
   coverage:{required_dvp_total:3,current_snapshot_executed:3,current_snapshot_passed:3,snapshot_match:true},
   rules:[...row.readiness.rules,duplicate]},
  decision:{...row.decision,decision:'RELEASE',readiness_status:'READY'}}]};
 const {html}=await render(value);
 assert.ok(html.includes('Evidence API unavailable'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});
test('duplicate release identities make the complete demonstration unavailable',async()=>{
 const conflicting={...row,version:'CONFLICTING',current_release_confirmed:true,
  readiness:{...row.readiness,overall:'READY',approval_eligible:true,
   coverage:{required_dvp_total:3,current_snapshot_executed:3,current_snapshot_passed:3,snapshot_match:true}},
  decision:{...row.decision,decision:'RELEASE',readiness_status:'READY'}};
 const {html}=await render({sample_only:true,initialized:true,items:[row,conflicting]});
 assert.ok(html.includes('Evidence API unavailable'));
 assert.ok(!html.includes('APR-2')&&!html.includes('CONFLICTING'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});
test('duplicate DVP identities make the complete demonstration unavailable',async()=>{
 const duplicate={...row.dvp_items[0],item_no:'CONFLICTING-DVP'};
 const value={sample_only:true,initialized:true,items:[{...row,dvp_items:[...row.dvp_items,duplicate]}]};
 const {html}=await render(value);
 assert.ok(html.includes('Evidence API unavailable'));
 assert.ok(!html.includes('33333333-3333-4333-8333-333333333333')&&!html.includes('CONFLICTING-DVP'));
});
const secondRow={...row,release_id:'44444444-4444-4444-8444-444444444444',version:'DEMO-EVIDENCE-SSR-C-3.0',release_type:'STANDARD',
 snapshot:{...row.snapshot,id:'55555555-5555-4555-8555-555555555555',snapshot_no:'SNAP-3'},
 readiness:{...row.readiness,coverage:{...row.readiness.coverage,snapshot_id:'55555555-5555-4555-8555-555555555555',snapshot_no:'SNAP-3'}},
 approval:{...row.approval,approval_no:'APR-3'},
 decision:{...row.decision,decision_no:'RD-3',snapshot_id:'55555555-5555-4555-8555-555555555555'}};
test('distinct evidence families may retain the same DVP identity in separate release contexts',async()=>{
 const {html}=await render({sample_only:true,initialized:true,items:[row,secondRow]});
 assert.ok(!html.includes('Evidence API unavailable'));
 assert.ok(html.includes('APR-2')&&html.includes('APR-3'));
 assert.ok(html.includes('/testing/dvp/33333333-3333-4333-8333-333333333333?release_id=11111111-1111-4111-8111-111111111111&amp;snapshot_no=SNAP-2'));
 assert.ok(html.includes('/testing/dvp/33333333-3333-4333-8333-333333333333?release_id=44444444-4444-4444-8444-444444444444&amp;snapshot_no=SNAP-3'));
});
test('cross-release evidence identity conflicts make the complete demonstration unavailable',async()=>{
 const conflicts=[
  {...secondRow,snapshot:{...secondRow.snapshot,id:row.snapshot.id},
   readiness:{...secondRow.readiness,coverage:{...secondRow.readiness.coverage,snapshot_id:row.snapshot.id}},
   decision:{...secondRow.decision,snapshot_id:row.snapshot.id}},
  {...secondRow,snapshot:{...secondRow.snapshot,snapshot_no:row.snapshot.snapshot_no},
   readiness:{...secondRow.readiness,coverage:{...secondRow.readiness.coverage,snapshot_no:row.snapshot.snapshot_no}}},
  {...secondRow,approval:{...secondRow.approval,approval_no:row.approval.approval_no}},
  {...secondRow,decision:{...secondRow.decision,decision_no:row.decision.decision_no}},
 ];
 for(const conflicting of conflicts){
  const {html}=await render({sample_only:true,initialized:true,items:[row,conflicting]});
  assert.ok(html.includes('Evidence API unavailable'));
  assert.ok(!html.includes('APR-2')&&!html.includes('APR-3'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});
