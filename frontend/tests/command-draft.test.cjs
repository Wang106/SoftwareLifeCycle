'use strict';
const { test, after } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const output = mkdtempSync(path.join(tmpdir(), 'slc-commands-'));
execFileSync(process.execPath, [require.resolve('typescript/bin/tsc'), 'lib/command-draft.ts',
  '--target', 'ES2021', '--module', 'commonjs', '--strict', '--skipLibCheck', '--outDir', output]);
const { blankFields, prepare, confirm, exportRequest } = require(path.join(output, 'command-draft.js'));
after(() => rmSync(output, { recursive: true, force: true }));
const key = '12345678-1234-1234-1234-123456789abc';
const release = '23456789-1234-1234-1234-123456789abc';
const snapshot = '34567890-1234-1234-1234-123456789abc';
const actual = { ...blankFields, target: 'DEP', release, snapshot, version: '0', reason: 'Controlled evidence' };
function exported(operation, fields) {
  return JSON.parse(exportRequest(confirm(prepare(operation, fields, key), true)));
}
test('snapshot request is scoped to the UUID and requires confirmation before export', () => {
  const review = prepare('snapshot', { ...blankFields, target: release.toUpperCase() }, key);
  assert.throws(() => exportRequest(review), /Confirm/);
  const request = JSON.parse(exportRequest(confirm(review, true)));
  assert.deepEqual(request, { method: 'POST', path: `/api/v1/releases/${release}/create-snapshot`, body: { request_id: key } });
  assert.equal(review.draft.audit, '/activity/EVT-SN-12345678123412341234123456789abc');
  assert.equal(review.confirmed, false);
});
test('editing source fields cannot mutate the frozen reviewed payload; repeat export keeps the key', () => {
  const fields = { ...actual };
  const review = confirm(prepare('actual', fields, key), true);
  const before = exportRequest(review);
  fields.reason = 'Changed'; fields.target = 'OTHER';
  assert.equal(exportRequest(review), before);
  assert.throws(() => { review.draft.payload.expected_version = 999; }, TypeError);
  assert.throws(() => exportRequest(confirm(review, false)), /Confirm/);
});
test('actual baseline-zero reports carry explicit version and reason without fabricated context', () => {
  assert.deepEqual(exported('actual', actual).body, { request_id: key,
    actual_release_id: release, actual_snapshot_id: snapshot, expected_version: 0,
    correction_reason: 'Controlled evidence', deployed_at: null });
  assert.throws(() => prepare('actual', { ...actual, version: '' }, key), /Expected version/);
});
for (const version of ['-1', '1.5', '01', ' 0', '0 ', 'Infinity', '9007199254740992']) {
  test(`invalid or imprecise expected version ${JSON.stringify(version)} is rejected`, () => {
    assert.throws(() => prepare('actual', { ...actual, version }, key), /Expected version/);
  });
}
for (const reason of ['', ' \n ', 'a'.repeat(2001)]) {
  test(`missing/blank/oversized reason (${reason.length}) is rejected even at version zero`, () => {
    assert.throws(() => prepare('actual', { ...actual, reason }, key), /reason/);
  });
}
test('UTC-equivalent explicit timestamps canonicalize equally; omission stays distinct', () => {
  const utc = exported('actual', { ...actual, timestamp: '2026-10-01T08:00:00Z' });
  const offset = exported('actual', { ...actual, timestamp: '2026-10-01T16:00:00+08:00' });
  assert.deepEqual(utc, offset);
  assert.notDeepEqual(utc, exported('actual', actual));
});
for (const timestamp of ['2026-02-30T08:00:00Z', '2026-10-01T24:00:00Z', '2026-10-01T08:60:00Z',
  '2026-10-01T08:00:00+24:00', '2026-10-01T08:00:00', 'not a date']) {
  test(`invalid/ambiguous time ${timestamp} is rejected`, () => {
    assert.throws(() => prepare('actual', { ...actual, timestamp }, key), /Time/);
  });
}
test('batch request preserves exact note, optional nulls and safely encodes business identifiers', () => {
  const fields = { ...blankFields, target: 'DEP? #%', batch: 'B? #%', note: ' Exact note\n' };
  const review = prepare('batch', fields, key);
  assert.equal(review.draft.path, '/api/v1/deployments/DEP%3F%20%23%25/batches');
  assert.equal(review.draft.trace, '/production/batches/B%3F%20%23%25');
  assert.deepEqual(exported('batch', fields).body, { request_id: key, batch_no: 'B? #%',
    changeover_id: null, started_at: null, note: ' Exact note\n' });
});
for (const changes of [{ release: 'bad' }, { snapshot: 'bad' }, { target: '' }, { target: 'DEP\n' + 'X' }, { target: 'a'.repeat(51) }, { target: '..' }, { target: 'DEP/A' }, { target: 'DEP\\A' }]) {
  test(`invalid actual identifier ${JSON.stringify(changes)} is rejected`, () => {
    assert.throws(() => prepare('actual', { ...actual, ...changes }, key));
  });
}
test('invalid key, invalid optional changeover and unsupported operation fail closed', () => {
  assert.throws(() => prepare('snapshot', { ...blankFields, target: release }, 'bad'));
  assert.throws(() => prepare('batch', { ...blankFields, target: 'DEP', batch: 'B', changeover: 'bad' }, key));
  assert.throws(() => prepare('unsupported', actual, key), /Unsupported/);
});
const approvalFields = { ...blankFields, target: 'AP? #%', step: snapshot, actor: ' Declared Reviewer ',
  action: 'APPROVED', note: ' Exact comment\n' };
const decisionFields = { ...blankFields, target: 'AP', actor: 'Release Authority', decisionNo: 'RD? #%',
  readiness: 'READY', decision: 'RELEASE', note: ' Exact notes\n' };
test('keyed approval exports the exact step, declaration and comment, with correctly scoped trace/audit', () => {
  const review = prepare('approval', approvalFields, key);
  assert.equal(review.draft.path, '/api/v1/approvals/AP%3F%20%23%25/actions');
  assert.equal(review.draft.trace, '/approvals/AP%3F%20%23%25');
  assert.equal(review.draft.audit, '/activity/EVT-AP-12345678123412341234123456789abc');
  assert.throws(() => exportRequest(review), /Confirm/);
  assert.deepEqual(exported('approval', approvalFields).body, { request_id: key,
    expected_step_id: snapshot, actor: ' Declared Reviewer ', action: 'APPROVED', comment: ' Exact comment\n' });
});
for (const action of ['APPROVED', 'RETURNED', 'REJECTED']) {
  test(`approval action ${action} requires explicit exact step`, () => {
    assert.equal(exported('approval', { ...approvalFields, action, note: '' }).body.action, action);
    assert.equal(exported('approval', { ...approvalFields, action, note: '' }).body.comment, null);
  });
}
for (const changes of [{ step: '' }, { step: 'bad' }, { action: '' }, { action: 'approved' },
  { action: 'CANCELLED' }, { actor: '' }, { actor: '   ' }, { actor: 'A'.repeat(121) }, { actor: 'A\nB' }]) {
  test(`approval invalid declaration/step/action ${JSON.stringify(changes)} fails closed`, () => {
    assert.throws(() => prepare('approval', { ...approvalFields, ...changes }, key));
  });
}
test('decision exports exact readiness/decision declarations and encoded record/audit links', () => {
  const review = prepare('decision', decisionFields, key);
  assert.equal(review.draft.path, '/api/v1/approvals/AP/release-decision');
  assert.equal(review.draft.trace, '/release-decisions/RD%3F%20%23%25');
  assert.equal(review.draft.audit, '/activity/EVT-RD-12345678123412341234123456789abc');
  assert.deepEqual(exported('decision', decisionFields).body, { request_id: key,
    decision_no: 'RD? #%', decided_by: 'Release Authority', readiness_status: 'READY',
    decision: 'RELEASE', notes: ' Exact notes\n' });
  assert.equal(exported('decision', { ...decisionFields, readiness: ' DECLARED ', decision: ' HOLD ', note: '' }).body.decision, ' HOLD ');
  assert.equal(exported('decision', { ...decisionFields, note: '' }).body.notes, null);
});
for (const changes of [{ decisionNo: '' }, { decisionNo: '..' }, { decisionNo: 'RD/A' }, { decisionNo: 'R'.repeat(51) },
  { readiness: '' }, { readiness: ' ' }, { readiness: 'R'.repeat(31) }, { decision: '' },
  { decision: 'D'.repeat(31) }, { decision: 'HOLD\n' }, { target: 'AP/A' }]) {
  test(`invalid decision content ${JSON.stringify(changes)} is rejected`, () => {
    assert.throws(() => prepare('decision', { ...decisionFields, ...changes }, key));
  });
}
test('governance repeated confirmed exports retain content/key; source edits cannot alter review', () => {
  for (const [operation, source] of [['approval', approvalFields], ['decision', decisionFields]]) {
    const fields = { ...source }; const review = confirm(prepare(operation, fields, key), true);
    const before = exportRequest(review); fields.actor = 'Changed'; fields.step = release; fields.decision = 'HOLD';
    assert.equal(exportRequest(review), before);
    assert.throws(() => { review.draft.payload.actor = 'Forged'; }, TypeError);
    assert.throws(() => exportRequest(confirm(review, false)), /Confirm/);
  }
});
const impactFields = {...blankFields,target:'ISS? #%',release,snapshot,decision:'NEEDS_REVIEW',actor:' Reviewer ',reason:' Evidence reason\n ',evidence:' reference '};
const assignmentFields = {...blankFields,target:'SCR? #%',criterion:release,dvp:snapshot,actor:' Contributor ',reason:' Assignment reason '};
const resourceFields = {...blankFields,target:release,entityType:'RELEASE',title:' Evidence ',locationKind:'WEB_URL',location:' https://example.com/evidence?q=@review ',description:' Description ',actor:' Contributor ',reason:' Reference reason '};
test('impact export pins exact release/snapshot, normalizes API text and uses hyphenated audit UUID',()=>{
 const review=prepare('impact',impactFields,key);
 assert.equal(review.draft.path,'/api/v1/issues/ISS%3F%20%23%25/impact-assessments');
 assert.equal(review.draft.trace,'/issues/ISS%3F%20%23%25');
 assert.equal(review.draft.audit,`/activity/EVT-IMPACT-${key}`);
 assert.deepEqual(exported('impact',impactFields).body,{request_id:key,release_id:release,snapshot_id:snapshot,decision:'NEEDS_REVIEW',actor_name:'Reviewer',reason:'Evidence reason',evidence_ref:'reference'});
 assert.equal(exported('impact',{...impactFields,evidence:'  '}).body.evidence_ref,null);
});
for(const decision of ['AFFECTED','NOT_AFFECTED','NEEDS_REVIEW']){
 test(`explicit impact judgment ${decision} is retained`,()=>assert.equal(exported('impact',{...impactFields,decision}).body.decision,decision));
}
for(const changes of [{target:'../ISS'},{release:'bad'},{snapshot:''},{decision:''},{decision:'PASS'},{reason:'  '},{reason:'R'.repeat(4001)},{evidence:'E'.repeat(2001)},{actor:'A'.repeat(121)}]){
 test(`invalid impact content ${JSON.stringify(changes).slice(0,80)} rejected`,()=>assert.throws(()=>prepare('impact',{...impactFields,...changes},key)));
}
test('acceptance link pins criterion and DVP UUID, trims reason/actor and uses exact SCR trace',()=>{
 const review=prepare('acceptance',assignmentFields,key);
 assert.equal(review.draft.path,'/api/v1/changes/SCR%3F%20%23%25/acceptance-dvp-links');
 assert.equal(review.draft.trace,'/changes/SCR%3F%20%23%25/coverage');
 assert.equal(review.draft.audit,`/activity/EVT-AC-${key}`);
 assert.deepEqual(exported('acceptance',assignmentFields).body,{request_id:key,criterion_id:release,dvp_item_id:snapshot,actor_name:'Contributor',reason:'Assignment reason'});
});
for(const changes of [{criterion:''},{dvp:'bad'},{target:'..'},{actor:'  '},{reason:''}]){
 test(`invalid assignment ${JSON.stringify(changes)} rejected`,()=>assert.throws(()=>prepare('acceptance',{...assignmentFields,...changes},key)));
}
test('resource export uses exact target UUID, canonical trimmed text and original URL spelling',()=>{
 const review=prepare('resource',resourceFields,key);
 assert.equal(review.draft.path,'/api/v1/resources');assert.equal(review.draft.trace,`/resources/${key}`);
 assert.equal(review.draft.audit,`/activity/EVT-LK-${key}`);
 assert.deepEqual(exported('resource',resourceFields).body,{request_id:key,actor_name:'Contributor',reason:'Reference reason',entity_type:'RELEASE',entity_id:release,title:'Evidence',location_kind:'WEB_URL',location:'https://example.com/evidence?q=@review',description:'Description'});
 assert.equal(exported('resource',{...resourceFields,description:' '}).body.description,'');
});
for(const [locationKind,location] of [['WEB_URL','http://example.com:8080/%20data#evidence'],['LOCAL_PATH','/srv/evidence/file.pdf'],['LOCAL_PATH','C:\\evidence\\file.pdf'],['LOCAL_PATH','D:/evidence/file.pdf'],['NETWORK_PATH','\\\\server\\share\\file.pdf'],['NETWORK_PATH','//server/share/file.pdf']]){
 test(`valid reference ${locationKind} ${location} remains text without normalization`,()=>assert.equal(exported('resource',{...resourceFields,locationKind,location}).body.location,location));
}
for(const location of ['javascript:alert(1)','file:///tmp/x','https://user:pass@example.com/x','https://@example.com/x','https:///example.com','https://example.com:65536/x','https://example.com/%0a','https://example.com/%7F','https://example.com/a b','https://example.com\\x','https://example.com/%invalid']){
 test(`unsafe or malformed web reference ${location} rejected`,()=>assert.throws(()=>prepare('resource',{...resourceFields,location},key)));
}
for(const [locationKind,location] of [['LOCAL_PATH','relative/file'],['LOCAL_PATH','//server/share'],['LOCAL_PATH','C:relative'],['NETWORK_PATH','//server'],['NETWORK_PATH','\\\\server\\'],['NETWORK_PATH','/srv/share'],['','/tmp/a']]){
 test(`invalid path/kind ${locationKind} ${location} rejected`,()=>assert.throws(()=>prepare('resource',{...resourceFields,locationKind,location},key)));
}
for(const changes of [{entityType:'APPROVAL'},{entityType:''},{target:'bad'},{title:''},{title:'T'.repeat(241)},{reason:'R\nX'},{actor:'A\nB'},{description:'D\tX'},{description:'D'.repeat(4001)},{location:'L'.repeat(4001)}]){
 test(`invalid resource content ${JSON.stringify(changes).slice(0,80)} rejected`,()=>assert.throws(()=>prepare('resource',{...resourceFields,...changes},key)));
}
test('all three evidence forms keep immutable confirmed exports; unconfirmed or revoked exports fail',()=>{
 for(const [operation,source] of [['impact',impactFields],['acceptance',assignmentFields],['resource',resourceFields]]){
  const fields={...source};const raw=prepare(operation,fields,key);assert.throws(()=>exportRequest(raw),/Confirm/);
  const review=confirm(raw,true);const before=exportRequest(review);fields.reason='Changed';fields.target=snapshot;fields.location='https://different.example/';
  assert.equal(exportRequest(review),before);assert.throws(()=>{review.draft.payload.reason='Forged';},TypeError);
  assert.throws(()=>exportRequest(confirm(review,false)),/Confirm/);
 }
});
