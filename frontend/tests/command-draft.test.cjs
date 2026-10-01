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
const deliveryFields = {...blankFields,target:release,packageNo:'PK? #%',revision:'2',artifacts:`${snapshot.toUpperCase()}\n${release}`,recipientType:' CUSTOMER ',recipientCode:' CUS-001 ',purpose:' PRODUCTION ',actor:' Declared creator '};
const distributionFields = {...blankFields,target:snapshot,distributionNo:'DS? #%',recipientType:'CUSTOMER',recipientCode:'CUS-001'};
const authorizationFields = {...blankFields,target:snapshot,release,authorizationNo:'PA? #%',customer:release,project:snapshot,site:' SITE ',line:' LINE ',purpose:'PRODUCTION',limitMode:'FINITE',limit:'3',note:' Exact restriction\n'};
test('delivery exports exact declarations, canonical frozen artifact set and exact revision trace',()=>{
 const review=prepare('delivery',deliveryFields,key);
 assert.equal(review.draft.path,'/api/v1/deliveries');assert.equal(review.draft.trace,'/distribution/deliveries/PK%3F%20%23%25/2');
 assert.equal(review.draft.audit,'/activity/EVT-DP-12345678123412341234123456789abc');
 assert.deepEqual(exported('delivery',deliveryFields).body,{request_id:key,release_id:release,package_no:'PK? #%',revision:2,snapshot_artifact_ids:[release,snapshot],recipient_type:' CUSTOMER ',recipient_code:' CUS-001 ',purpose:' PRODUCTION ',created_by:' Declared creator '});
 assert.deepEqual(exported('delivery',{...deliveryFields,artifacts:`${release}\r\n${snapshot}`,actor:''}).body.snapshot_artifact_ids,[release,snapshot]);
 assert.equal(exported('delivery',{...deliveryFields,actor:''}).body.created_by,null);
});
test('distribution requires an exact package UUID, carries no invented operator and has scoped traces',()=>{
 const review=prepare('distribution',distributionFields,key);
 assert.equal(review.draft.path,'/api/v1/distributions');assert.equal(review.draft.trace,'/distribution/distributions/DS%3F%20%23%25');
 assert.equal(review.draft.audit,'/activity/EVT-DS-12345678123412341234123456789abc');
 assert.deepEqual(exported('distribution',distributionFields).body,{request_id:key,delivery_package_id:snapshot,distribution_no:'DS? #%',recipient_type:'CUSTOMER',recipient_code:'CUS-001'});
});
test('authorization exports explicit finite scope and exact restriction without approval fields',()=>{
 const review=prepare('authorization',authorizationFields,key);
 assert.equal(review.draft.path,'/api/v1/authorizations');assert.equal(review.draft.trace,'/distribution/authorizations/PA%3F%20%23%25');
 assert.equal(review.draft.audit,'/activity/EVT-PA-12345678123412341234123456789abc');
 assert.deepEqual(exported('authorization',authorizationFields).body,{request_id:key,distribution_id:snapshot,release_id:release,authorization_no:'PA? #%',customer_id:release,project_id:snapshot,site_code:' SITE ',line_code:' LINE ',purpose:'PRODUCTION',batch_limit:3,restriction_note:' Exact restriction\n'});
 assert.equal(exported('authorization',{...authorizationFields,limitMode:'UNLIMITED',limit:'',note:''}).body.batch_limit,null);
 assert.equal(exported('authorization',{...authorizationFields,note:''}).body.restriction_note,null);
});
for(const value of ['', '0','-1','1.2','01',' 1','1 ','1e3','2147483648','9007199254740992','Infinity']) {
 test(`invalid revision ${JSON.stringify(value)} rejected`,()=>assert.throws(()=>prepare('delivery',{...deliveryFields,revision:value},key),/Revision/));
 test(`invalid finite quota ${JSON.stringify(value)} cannot silently become unlimited`,()=>assert.throws(()=>prepare('authorization',{...authorizationFields,limit:value},key),/Batch limit/));
}
for(const changes of [{limitMode:''},{limitMode:'finite'},{limitMode:'UNLIMITED',limit:'3'},{limitMode:'UNLIMITED',limit:' '}]) {
 test(`ambiguous quota mode ${JSON.stringify(changes)} rejected`,()=>assert.throws(()=>prepare('authorization',{...authorizationFields,...changes},key)));
}
for(const changes of [{target:'bad'},{packageNo:'../PK'},{packageNo:'P'.repeat(51)},{artifacts:''},{artifacts:'bad'},{artifacts:`${release}\n\n${snapshot}`},{artifacts:`${release}\n${release.toUpperCase()}`},{artifacts:Array(201).fill(release).join('\n')},{recipientType:''},{recipientType:'R'.repeat(51)},{recipientCode:' '},{recipientCode:'C'.repeat(81)},{purpose:''},{purpose:'P\nQ'},{actor:' '},{actor:'A'.repeat(121)}]) {
 test(`invalid delivery input ${JSON.stringify(changes).slice(0,70)} rejected`,()=>assert.throws(()=>prepare('delivery',{...deliveryFields,...changes},key)));
}
for(const changes of [{target:'PK-001'},{distributionNo:''},{distributionNo:'..'},{distributionNo:'D'.repeat(51)},{recipientType:'TYPE\t'},{recipientCode:''}]) {
 test(`invalid distribution input ${JSON.stringify(changes)} rejected`,()=>assert.throws(()=>prepare('distribution',{...distributionFields,...changes},key)));
}
for(const changes of [{target:''},{release:'ASR 2.3.4'},{customer:'CUS-001'},{project:'PROJ'},{authorizationNo:'PA/A'},{authorizationNo:'P'.repeat(51)},{site:''},{site:'S'.repeat(81)},{line:' '},{line:'L\n'},{purpose:' '},{purpose:'P'.repeat(51)}]) {
 test(`invalid authorization input ${JSON.stringify(changes).slice(0,70)} rejected`,()=>assert.throws(()=>prepare('authorization',{...authorizationFields,...changes},key)));
}
test('distribution chain reviews keep immutable nested artifacts and stable keys with confirmation gates',()=>{
 for(const [operation,source] of [['delivery',deliveryFields],['distribution',distributionFields],['authorization',authorizationFields]]) {
  const fields={...source};const raw=prepare(operation,fields,key);assert.throws(()=>exportRequest(raw),/Confirm/);
  const review=confirm(raw,true);const before=exportRequest(review);fields.limit='999';fields.artifacts='';fields.recipientCode='OTHER';
  assert.equal(exportRequest(review),before);assert.throws(()=>{review.draft.payload.batch_limit=999;},TypeError);
  if(operation==='delivery')assert.throws(()=>review.draft.payload.snapshot_artifact_ids.push(key),TypeError);
  assert.throws(()=>exportRequest(confirm(review,false)),/Confirm/);
 }
});
test('positive integer storage bounds are accepted without rounding',()=>{
 assert.equal(exported('delivery',{...deliveryFields,revision:'2147483647'}).body.revision,2147483647);
 assert.equal(exported('authorization',{...authorizationFields,limit:'2147483647'}).body.batch_limit,2147483647);
});
const testReleaseFields={...blankFields,target:release,snapshot,testReleaseNo:' TR? #% ',purposeScope:'SOFTWARE_TEST',actor:' Contributor ',reason:' Frozen test scope\n '};
const deploymentFields={...blankFields,target:release,productionLine:snapshot,deploymentNo:'DEP? #%'};
const changeoverFields={...blankFields,target:'DEP? #%',fromRelease:release,changeoverNo:'CO? #%',note:' Exact history\n'};
test('test release pins exact frozen UUIDs, normalized schema text and hyphenated event UUID',()=>{
 const review=prepare('test-release',testReleaseFields,key);
 assert.equal(review.draft.path,'/api/v1/testing/releases');assert.equal(review.draft.trace,'/testing/releases/TR%3F%20%23%25');
 assert.equal(review.draft.audit,`/activity/EVT-TR-${key}`);
 assert.deepEqual(exported('test-release',testReleaseFields).body,{request_id:key,release_id:release,snapshot_id:snapshot,test_release_no:'TR? #%',purpose_scope:'SOFTWARE_TEST',actor_name:'Contributor',reason:'Frozen test scope'});
});
for(const purposeScope of ['SOFTWARE_TEST','BATTERY_TEST','CUSTOMER_TEST']){
 test(`explicit test purpose ${purposeScope} retains bounded test scope`,()=>assert.equal(exported('test-release',{...testReleaseFields,purposeScope}).body.purpose_scope,purposeScope));
}
for(const changes of [{target:''},{snapshot:'bad'},{purposeScope:''},{purposeScope:'PRODUCTION'},{purposeScope:'software_test'},{testReleaseNo:' '},{testReleaseNo:'TR/A'},{testReleaseNo:'T'.repeat(51)},{testReleaseNo:' '+'T'.repeat(50)},{actor:''},{actor:'A'.repeat(121)},{reason:' '},{reason:'R'.repeat(4001)}]){
 test(`invalid test draft ${JSON.stringify(changes).slice(0,60)} rejected`,()=>assert.throws(()=>prepare('test-release',{...testReleaseFields,...changes},key)));
}
test('deployment expectation uses exact authorization and line IDs without invented software or actor',()=>{
 const review=prepare('deployment',deploymentFields,key);
 assert.equal(review.draft.path,'/api/v1/deployments');assert.equal(review.draft.trace,'/deployments/DEP%3F%20%23%25');
 assert.equal(review.draft.audit,'/activity/EVT-DPLOY-12345678123412341234123456789abc');
 assert.deepEqual(exported('deployment',deploymentFields).body,{request_id:key,authorization_id:release,production_line_id:snapshot,deployment_no:'DEP? #%'});
});
for(const changes of [{target:'PA-001'},{productionLine:''},{productionLine:'LINE-2'},{deploymentNo:''},{deploymentNo:'..'},{deploymentNo:'DEP/A'},{deploymentNo:'D'.repeat(51)}]){
 test(`invalid deployment ${JSON.stringify(changes)} rejected`,()=>assert.throws(()=>prepare('deployment',{...deploymentFields,...changes},key)));
}
test('changeover exports explicit source and exact note, with encoded deployment history and hex audit',()=>{
 const review=prepare('changeover',changeoverFields,key);
 assert.equal(review.draft.path,'/api/v1/deployments/DEP%3F%20%23%25/changeovers');assert.equal(review.draft.trace,'/deployments/DEP%3F%20%23%25');
 assert.equal(review.draft.audit,'/activity/EVT-CO-12345678123412341234123456789abc');
 assert.deepEqual(exported('changeover',changeoverFields).body,{request_id:key,changeover_no:'CO? #%',from_release_id:release,changed_at:null,note:' Exact history\n'});
 assert.equal(exported('changeover',{...changeoverFields,note:''}).body.note,null);
});
test('changeover UTC equivalence matches but omission stays distinct',()=>{
 const utc=exported('changeover',{...changeoverFields,timestamp:'2026-10-01T08:00:00Z'});
 assert.deepEqual(utc,exported('changeover',{...changeoverFields,timestamp:'2026-10-01T16:00:00+08:00'}));
 assert.notDeepEqual(utc,exported('changeover',changeoverFields));
});
for(const changes of [{target:''},{target:'DEP/A'},{changeoverNo:''},{changeoverNo:'..'},{changeoverNo:'C'.repeat(51)},{fromRelease:''},{fromRelease:'ASR 2.3.3'},{timestamp:'2026-02-30T08:00:00Z'},{timestamp:'2026-10-01T08:00:00'},{timestamp:'2026-10-01T08:00:00+24:00'}]){
 test(`invalid changeover ${JSON.stringify(changes)} rejected`,()=>assert.throws(()=>prepare('changeover',{...changeoverFields,...changes},key)));
}
test('last three command reviews require confirmation and retain stable immutable content/keys',()=>{
 for(const [operation,source] of [['test-release',testReleaseFields],['deployment',deploymentFields],['changeover',changeoverFields]]){
  const fields={...source};const raw=prepare(operation,fields,key);assert.throws(()=>exportRequest(raw),/Confirm/);
  const review=confirm(raw,true),before=exportRequest(review);fields.purposeScope='PRODUCTION';fields.productionLine=key;fields.fromRelease=key;
  assert.equal(exportRequest(review),before);assert.throws(()=>{review.draft.payload.status='APPROVED';},TypeError);
  assert.throws(()=>exportRequest(confirm(review,false)),/Confirm/);
 }
});
