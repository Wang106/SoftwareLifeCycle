'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
const dict=require('../lib/i18n/zh.json'),templates=require('../lib/i18n/templates.json');
const translated={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/i18n.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,esModuleInterop:true}}).outputText)(n=>n.endsWith('zh.json')?dict:templates,translated,translated.exports);
const confirmation={exports:{}};
new Function('require','module','exports',ts.transpileModule(fs.readFileSync('lib/release-evidence-confirmation.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText)(require,confirmation,confirmation.exports);

const evidence={
  release:{id:'rel-uuid',version:'v1.0',release_type:'STANDARD',record_status:'DRAFT'},
  snapshot:{id:'snap-uuid',snapshot_no:'SNAP-1',status:'FROZEN',content_hash:'a'.repeat(64)},
  readiness:{overall:'READY',approval_eligible:true,
    coverage:{snapshot_id:'snap-uuid',snapshot_no:'SNAP-1',required_dvp_total:3,current_snapshot_executed:3,current_snapshot_passed:3,snapshot_match:true},
    rules:[{group:'Verification',rule:'Required DVP executed on current snapshot',evidence:'3 / 3',effective:'PASS'}]},
  approval:{approval_no:'APR-1',status:'APPROVED',current_snapshot_bound:true},
  decision:{decision_no:'RD-1',decision:'RELEASE',readiness_status:'READY',snapshot_id:'snap-uuid',current_evidence_bound:true},
  current_release_confirmed:true,
};

async function render(data,releaseId='rel-uuid',locale='en'){
 const compiled=ts.transpileModule(fs.readFileSync('components/release-evidence-summary.tsx','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2021,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const m={exports:{}},calls=[];
 const translate=c=>typeof c==='string'?translated.exports.translateText(c,locale):Array.isArray(c)?c.map(translate):c;
 const req=n=>n==='next/link'?({href,children})=>React.createElement('a',{href},children):n.endsWith('/lib/api')?{apiGet:async p=>{calls.push(p);return data;}}:n.endsWith('/release-evidence-confirmation')?confirmation.exports:n.endsWith('/localized')?{Localized:({children})=>React.createElement(React.Fragment,null,translate(children))}:require(n);
 new Function('require','module','exports',compiled)(req,m,m.exports);
 const html=renderToStaticMarkup(await m.exports.ReleaseEvidenceSummary({releaseId,expectedReleaseType:'STANDARD'}));
 return {html,calls};
}

test('renders the snapshot-readiness-approval-decision chain in english',async()=>{
 const {html,calls}=await render(evidence);
 assert.deepEqual(calls,['/api/v1/releases/rel-uuid/evidence-summary']);
 assert.ok(html.includes('Release evidence summary'));
 assert.ok(html.includes('SNAP-1')&&html.includes('FROZEN'));
 assert.ok(html.includes('/snapshots/SNAP-1'));
 assert.ok(html.includes('/approvals/APR-1')&&html.includes('/release-decisions/RD-1'));
 assert.ok(html.includes('Current snapshot bound')&&html.includes('Current evidence bound'));
 assert.ok(html.includes('Formal release evidence matches the current snapshot.'));
 assert.ok(html.includes('PASS'));
 assert.ok(html.includes('READY'));
});

test('renders the chain in chinese',async()=>{
 const {html}=await render(evidence,'rel-uuid','zh');
 assert.ok(html.includes('发布证据摘要'));
 assert.ok(html.includes('绑定当前快照'));
});

test('renders unknown placeholders when evidence is missing',async()=>{
 const {html,calls}=await render({
  release:{id:'rel-uuid',version:'v2',release_type:'STANDARD',record_status:'DRAFT'},
  snapshot:null,approval:null,decision:null,
  readiness:{overall:'NOT_READY',approval_eligible:false,coverage:{snapshot_id:null,snapshot_no:null,required_dvp_total:0,current_snapshot_executed:0,current_snapshot_passed:0,snapshot_match:false},rules:[]},
  current_release_confirmed:false,
 });
 assert.ok(html.includes('Current evidence does not confirm a formal release.'));
 assert.ok(!html.includes('/snapshots/')&&!html.includes('/approvals/')&&!html.includes('/release-decisions/'));
});

test('fails closed when the evidence response belongs to a different release type',async()=>{
 const {html}=await render({...evidence,release:{...evidence.release,release_type:'APPLICATION'}});
 assert.ok(html.includes('Evidence summary unavailable.'));
 assert.ok(!html.includes('Formal release evidence matches'));
});

test('does not confirm release when any recorded invariant contradicts the API claim',async()=>{
 const mutations=[
  value=>value.snapshot.status='DRAFT',
  value=>value.readiness.overall='NOT_READY',
  value=>value.readiness.approval_eligible=false,
  value=>value.readiness.coverage.snapshot_match=false,
  value=>value.approval.status='PENDING',
  value=>{value.approval.current_snapshot_bound=false;value.decision.current_evidence_bound=false;},
  value=>value.decision.decision='HOLD',
  value=>value.decision.readiness_status='NOT_READY',
  value=>value.decision.current_evidence_bound=false,
  value=>{value.decision.snapshot_id='different-snapshot';value.decision.current_evidence_bound=false;},
 ];
 for(const mutate of mutations){
  const value=structuredClone(evidence);mutate(value);
  const {html}=await render(value);
  assert.ok(html.includes('Current evidence does not confirm a formal release.'));
  assert.ok(html.includes('Release evidence response is inconsistent; formal release is not confirmed.'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});

test('does not present a summary when the API is unavailable',async()=>{
 const {html}=await render(null);
 assert.ok(html.includes('Evidence summary unavailable.'));
 assert.ok(!html.includes('Formal release evidence matches'));
});

test('malformed nested evidence fails closed without throwing during SSR',async()=>{
 const malformed=[{}, {...evidence,release:null}, {...evidence,readiness:null},
  {...evidence,release:{...evidence.release,version:'v'.repeat(101)}},
  {...evidence,readiness:{...evidence.readiness,coverage:null}},
  {...evidence,readiness:{...evidence.readiness,rules:[null]}},
  {...evidence,readiness:{...evidence.readiness,rules:[{...evidence.readiness.rules[0],evidence:'e'.repeat(501)}]}},
  {...evidence,snapshot:{...evidence.snapshot,id:null}},
  {...evidence,snapshot:{...evidence.snapshot,snapshot_no:'s'.repeat(81)}},
  {...evidence,approval:{...evidence.approval,current_snapshot_bound:'true'}},
  {...evidence,approval:{...evidence.approval,approval_no:'a'.repeat(51)}},
  {...evidence,decision:{...evidence.decision,snapshot_id:null}},
  {...evidence,decision:{...evidence.decision,decision_no:'d'.repeat(51)}},
  {...evidence,current_release_confirmed:'true'}];
 for(const value of malformed){
  const {html}=await render(value);
  assert.ok(html.includes('Evidence summary unavailable.'));
  assert.ok(!html.includes('Formal release evidence matches'));
 }
});

test('non-canonical snapshot hashes make the evidence unavailable',async()=>{
 const malformed=['a'.repeat(63),'a'.repeat(65),'g'.repeat(64),'A'.repeat(64)];
 for(const content_hash of malformed){
  const {html}=await render({...evidence,snapshot:{...evidence.snapshot,content_hash}});
  assert.ok(html.includes('Evidence summary unavailable.'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});

test('impossible coverage counts make the evidence unavailable',async()=>{
 const impossible=[
  {...evidence.readiness.coverage,current_snapshot_executed:2,current_snapshot_passed:3},
  {...evidence.readiness.coverage,current_snapshot_executed:4,current_snapshot_passed:3},
 ];
 for(const coverage of impossible){
  const {html}=await render({...evidence,readiness:{...evidence.readiness,coverage}});
  assert.ok(html.includes('Evidence summary unavailable.'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});

test('readiness snapshot identity contradictions make the evidence unavailable',async()=>{
 const malformed=[
  {...evidence,readiness:{...evidence.readiness,coverage:{...evidence.readiness.coverage,snapshot_id:'different-snapshot'}}},
  {...evidence,readiness:{...evidence.readiness,coverage:{...evidence.readiness.coverage,snapshot_no:'SNAP-DIFFERENT'}}},
  {...evidence,snapshot:null,approval:null,decision:null,current_release_confirmed:false,
   readiness:{...evidence.readiness,overall:'NOT_READY',approval_eligible:false,
    coverage:{...evidence.readiness.coverage,snapshot_match:true}}},
 ];
 for(const value of malformed){
  const {html}=await render(value);
  assert.ok(html.includes('Evidence summary unavailable.'));
  assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
 }
});

test('contradictory binding claims make the evidence unavailable',async()=>{
 const malformed=[
  {...evidence,snapshot:null,approval:{...evidence.approval,current_snapshot_bound:true},current_release_confirmed:false},
  {...evidence,approval:{...evidence.approval,current_snapshot_bound:false},decision:{...evidence.decision,current_evidence_bound:true},current_release_confirmed:false},
  {...evidence,decision:{...evidence.decision,snapshot_id:'different-snapshot',current_evidence_bound:true},current_release_confirmed:false},
 ];
 for(const value of malformed){
  const {html}=await render(value);
  assert.ok(html.includes('Evidence summary unavailable.'));
  assert.ok(!html.includes('Current snapshot bound')&&!html.includes('Current evidence bound'));
 }
});

test('duplicate readiness rule identities make the evidence unavailable',async()=>{
 const duplicate={...evidence.readiness.rules[0],effective:'FAIL',evidence:'0 / 3'};
 const value={...evidence,readiness:{...evidence.readiness,rules:[...evidence.readiness.rules,duplicate]}};
 const {html}=await render(value);
 assert.ok(html.includes('Evidence summary unavailable.'));
 assert.ok(!html.includes('Formal release evidence matches the current snapshot.'));
});

test('the same rule label in distinct groups remains valid',async()=>{
 const second={...evidence.readiness.rules[0],group:'Independent Review'};
 const value={...evidence,readiness:{...evidence.readiness,rules:[...evidence.readiness.rules,second]}};
 const {html}=await render(value);
 assert.ok(html.includes('Formal release evidence matches the current snapshot.'));
 assert.ok(!html.includes('Evidence summary unavailable.'));
});

test('is read-only and never links to a command form',async()=>{
 const {html}=await render(evidence);
 assert.ok(!html.includes('<form')&&!html.includes('method="post"')&&!html.includes('/commands'));
});
