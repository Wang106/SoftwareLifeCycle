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
