'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { setTimeout: delay } = require('node:timers/promises');
const { queries, paths, startChangeIssueCatalogFixture } = require('../e2e/change-issue-catalog-fixture.cjs');
function observe(promise) {
  let settled = false;
  const result = promise.then(value => { settled = true; return { value }; }, error => { settled = true; return { error }; });
  return { result, get settled() { return settled; } };
}
async function until(check) {
  for (let n = 0; n < 200; n++) { if (check()) return; await delay(5); }
  assert.ok(check(), 'fixture observation did not arrive');
}
function read(origin, url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(origin, { path: url, method: 'GET', ...options }, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk)); res.once('error', reject);
      res.once('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
    });
    req.once('error', reject); req.setTimeout(2000, () => req.destroy(Error('fixture_client_timeout'))); req.end(options.body);
  });
}
test('only two fixed catalog kinds and two stall phases are accepted', async () => {
  assert.equal(queries.changes, 'q=A+%26+B&status=IN_VERIFICATION&scope=STANDARD&limit=10&offset=20&source=INTERNAL&change_type=ENHANCEMENT&software_id=software-one&customer_id=customer-one&project_id=project-one');
  assert.equal(queries.issues, 'q=A+%26+B&status=OPEN&scope=STANDARD&limit=10&offset=20&severity=HIGH');
  for (const kind of [undefined, null, '', 'projects', 'requests', '__proto__']) await assert.rejects(startChangeIssueCatalogFixture(kind, 'headers'), /invalid_change_issue_fixture_kind/);
  for (const phase of [undefined, null, '', 'ready', 'HEADERS']) await assert.rejects(startChangeIssueCatalogFixture('changes', phase), /invalid_change_issue_fixture_phase/);
});
for (const kind of ['changes', 'issues']) {
  const p = paths[kind];
  test(kind + ' finite fixed query forms match production normalization', () => {
    assert.equal(p.page, '/' + kind + '?' + queries[kind]);
    assert.equal(p.api, '/api/v1/change-catalog/' + (kind === 'changes' ? 'requests' : 'issues') + '?' + queries[kind]);
    assert.equal(p.firstApi, p.api.replace('&offset=20', ''));
    assert.equal(p.nextPage, p.firstPage + '&offset=20');
  });
  for (const phase of ['headers', 'body']) test(kind + ' ' + phase + ' hold needs client abort; recovery serves only a fresh exact read', { timeout: 5000 }, async () => {
    const fixture = await startChangeIssueCatalogFixture(kind, phase), controller = new AbortController();
    let held;
    try {
      const response = fetch(fixture.apiOrigin + p.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) });
      if (phase === 'body') {
        const r = await response; assert.equal(r.status, 200);
        const reader = r.body.getReader(); assert.equal(new TextDecoder().decode((await reader.read()).value), '{');
        held = observe(reader.read());
      } else held = observe(response);
      await until(() => fixture.pendingCount === 1);
      assert.equal(fixture.requests[0].phase, phase);
      assert.equal(fixture.requests[0].headersSent, phase === 'body');
      assert.equal(fixture.requests[0].finishedAt, null);
      fixture.recover(); fixture.recover(); await delay(30);
      assert.equal(held.settled, false);
      assert.equal(fixture.requests.length, 1);
      const fresh = await read(fixture.apiOrigin, p.api);
      assert.equal(fresh.status, 200);
      assert.deepEqual(JSON.parse(fresh.body), { kind, total: 0, limit: 10, offset: 20, next_offset: null, items: [], ...(kind === 'changes' ? { in_verification: 0, ready_for_release: 0 } : {}) });
      assert.equal(held.settled, false);
      controller.abort(); assert.ok((await held.result).error);
      await until(() => fixture.requests[0].closedAt !== null);
      assert.equal(fixture.requests[0].finishedAt, null);
      assert.deepEqual(fixture.releaseHeld(), [], 'an aborted hold is not a delivered stale response');
      assert.equal(fixture.pendingCount, 0);
      assert.deepEqual(fixture.violations, []);
    } finally { controller.abort(); await fixture.close(); if (held) await held.result; }
  });
  test(kind + ' ancillary first page/reset/projects remain finite and cannot release a held read', { timeout: 5000 }, async () => {
    const fixture = await startChangeIssueCatalogFixture(kind, 'headers'), controller = new AbortController();
    const held = observe(fetch(fixture.apiOrigin + p.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) }));
    try {
      await until(() => fixture.pendingCount === 1);
      for (const [url, wantedKind, total, limit, next] of [[p.firstApi, kind, 7, 10, 20], [p.resetApi, kind, 0, 50, null], [p.resetApi.slice(0, -1), kind, 0, 50, null], ['/api/v1/organization-views/projects?', 'projects', 0, 50, null], ['/api/v1/organization-views/projects', 'projects', 0, 50, null]]) {
        const result = await read(fixture.apiOrigin, url), data = JSON.parse(result.body);
        assert.equal(result.status, 200); assert.equal(data.kind, wantedKind); assert.equal(data.total, total); assert.equal(data.limit, limit); assert.equal(data.offset, 0); assert.equal(data.next_offset, next);
      }
      assert.equal(fixture.requests.filter(r => r.kind === 'target').length, 1);
      assert.equal(held.settled, false); assert.equal(fixture.pendingCount, 1);
      assert.deepEqual(fixture.violations, []);
    } finally { controller.abort(); await fixture.close(); await held.result; }
  });
  for (const phase of ['headers', 'body']) test(kind + ' late ' + phase + ' release completes valid stale JSON only when explicitly requested', { timeout: 5000 }, async () => {
    const fixture = await startChangeIssueCatalogFixture(kind, phase);
    try {
      fixture.recover(); assert.equal(JSON.parse((await read(fixture.apiOrigin, p.api)).body).total, 0);
      fixture.hold();
      const held = observe(fetch(fixture.apiOrigin + p.api, { signal: AbortSignal.timeout(3000) }).then(r => r.json()));
      await until(() => fixture.pendingCount === 1); await delay(30);
      assert.equal(held.settled, false);
      assert.deepEqual(fixture.releaseHeld(), [1]); assert.deepEqual(fixture.releaseHeld(), []);
      const late = (await held.result).value; assert.equal(late.total, 991);
      assert.equal(late.items.length, 1); assert.equal(late.items[0].title, lateMarkers[kind]);
      await until(() => fixture.requests[1].closedAt !== null);
      assert.ok(fixture.requests[1].finishedAt >= fixture.requests[1].receivedAt);
      assert.equal(fixture.pendingCount, 0);
      assert.ok(Object.isFrozen(fixture.requests)); assert.ok(Object.isFrozen(fixture.requests[0]));
      assert.throws(() => { fixture.requests[0].url = '/changed'; }, TypeError);
    } finally { await fixture.close(); }
  });
  test(kind + ' rejects mutations credentials bodies unknown queries and other catalog scope, redacting input', { timeout: 5000 }, async () => {
    const fixture = await startChangeIssueCatalogFixture(kind, 'headers');
    const cases = [
      [p.api, { method: 'POST' }], [p.api, { method: 'HEAD' }],
      ...['authorization', 'proxy-authorization', 'cookie'].flatMap(name => [[p.api, { headers: { [name]: 'PRIVATE_VALUE' } }], [p.api, { headers: { [name]: '' } }]]),
      [p.api, { headers: { 'content-length': '1' }, body: 'x' }], [p.api, { headers: { 'transfer-encoding': 'chunked' }, body: 'x' }],
      [p.api + '&token=PRIVATE_VALUE', {}], [p.api + '&q=A+%26+B', {}], [p.api + '&_rsc=fixture', {}],
      [p.api.replace('A+%26+B', 'A%20%26%20B'), {}], [p.api.replace('offset=20', 'offset=21'), {}],
      [paths[kind === 'changes' ? 'issues' : 'changes'].api, {}], ['/api/v1/dashboard/summary', {}], ['/auth/session', {}], ['/control/recover', {}], ['http://outside.invalid' + p.api, {}],
    ];
    try {
      for (const [url, options] of cases) { const result = await read(fixture.apiOrigin, url, options); assert.equal(result.status, 400, url); assert.ok(!result.body.includes('PRIVATE_')); }
      assert.equal(fixture.violations.length, cases.length); assert.equal(fixture.pendingCount, 0);
      assert.ok(fixture.requests.every(r => r.kind === 'rejected' && r.url === '[rejected]'));
      assert.ok(!JSON.stringify([fixture.requests, fixture.violations]).includes('PRIVATE_'));
    } finally { await fixture.close(); }
  });
  for (const phase of ['headers', 'body']) test(kind + ' close aborts ' + phase + ' hold and controls cannot reopen a stopped fixture', { timeout: 5000 }, async () => {
    const fixture = await startChangeIssueCatalogFixture(kind, phase);
    const held = observe(fetch(fixture.apiOrigin + p.api, { signal: AbortSignal.timeout(3000) }).then(r => r.text()));
    try {
      await until(() => fixture.pendingCount === 1); await fixture.close(); await fixture.close();
      assert.ok((await held.result).error); assert.equal(fixture.pendingCount, 0);
      assert.equal(fixture.requests[0].finishedAt, null); assert.ok(Number.isFinite(fixture.requests[0].closedAt));
      for (const action of ['recover', 'hold', 'releaseHeld']) assert.throws(() => fixture[action](), /change_issue_fixture_closed/);
    } finally { await fixture.close(); await held.result; }
  });
}

const { EventEmitter } = require('node:events');
const { observeCatalogRsc, summarizeCatalogCompletion, lateMarkers, MAX_RSC_BODY_BYTES } = require('../e2e/change-issue-catalog-fixture.cjs');
function browserRequest(url, overrides = {}) {
  return { url: () => url, method: () => 'GET', isNavigationRequest: () => false,
    resourceType: () => 'fetch', headers: () => ({ rsc: '1' }), failure: () => ({ errorText: 'net::ERR_ABORTED' }), ...overrides };
}
for (const kind of ['changes', 'issues']) test(kind + ' RSC observer tracks exact non-document request identities through terminal events', () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345';
  const observer = observeCatalogRsc(page, origin, kind);
  try {
    for (const request of [
      browserRequest(origin + paths[kind].firstPage), browserRequest('http://127.0.0.1:23456' + paths[kind].page),
      browserRequest(origin + paths[kind].page + '&other=1'), browserRequest(origin + paths[kind].page, { method: () => 'POST' }),
      browserRequest(origin + paths[kind].page, { isNavigationRequest: () => true }),
      browserRequest(origin + paths[kind].page, { resourceType: () => 'document' }),
      browserRequest(origin + paths[kind].page, { headers: () => ({}) }),
    ]) page.emit('request', request);
    assert.deepEqual(observer.requests, []);
    const live = browserRequest(origin + paths[kind].nextPage + '&_rsc=fixture'), cancelled = browserRequest(origin + paths[kind].page);
    page.emit('request', live); page.emit('request', cancelled);
    assert.deepEqual(observer.requests.map(r => r.outcome), ['pending', 'pending']);
    page.emit('requestfinished', browserRequest(live.url())); // Same URL is not the same Request.
    assert.equal(observer.requests[0].outcome, 'pending');
    page.emit('response', { request: () => live, status: () => 200 });
    page.emit('requestfinished', live); page.emit('requestfailed', cancelled);
    assert.deepEqual(observer.requests.map(r => [r.outcome, r.status, r.failure]), [['finished', 200, null], ['failed', null, 'net::ERR_ABORTED']]);
    assert.ok(observer.requests.every(r => r.endedAt >= r.receivedAt));
    assert.ok(Object.isFrozen(observer.requests)); assert.ok(Object.isFrozen(observer.requests[0]));
    const count = observer.requests.length; observer.stop(); observer.stop(); page.emit('request', browserRequest(origin + paths[kind].page));
    assert.equal(observer.requests.length, count);
    for (const name of ['request', 'response', 'requestfinished', 'requestfailed']) assert.equal(page.listenerCount(name), 0);
  } finally { observer.stop(); }
});
function completion() {
  return { backendReads: [{ id: 2, receivedAt: 1, closedAt: 5, finishedAt: 4 }], releasedIds: [2], releasedAt: 3,
    liveAtDestinationIds: [0], browserReads: [{ id: 0, outcome: 'finished', status: 200, failure: null, receivedAt: 1, endedAt: 6, prefetch: false, bodyInspected: true, bodyBytes: 100, containsLateMarker: true }] };
}
test('completion evidence distinguishes real late completion, cancellation, and mixed outcomes', () => {
  assert.equal(summarizeCatalogCompletion(completion()).outcome, 'late-data-completed');
  const cancelled = completion(); cancelled.releasedIds = []; cancelled.releasedAt = null; cancelled.liveAtDestinationIds = [];
  cancelled.backendReads[0].finishedAt = null; cancelled.browserReads[0] = { ...cancelled.browserReads[0], outcome: 'failed', failure: 'net::ERR_ABORTED' };
  assert.equal(summarizeCatalogCompletion(cancelled).outcome, 'cancelled');
  const mixed = completion(); mixed.browserReads.push({ ...mixed.browserReads[0], id: 1, outcome: 'failed', failure: 'net::ERR_ABORTED' });
  assert.equal(summarizeCatalogCompletion(mixed).outcome, 'mixed');
});
for (const [name, change] of [
  ['no browser candidate', value => { value.browserReads = []; }], ['no backend candidate', value => { value.backendReads = []; }],
  ['pending browser body', value => { value.browserReads[0].outcome = 'pending'; value.browserReads[0].endedAt = null; }],
  ['release was actually a cancelled no-op', value => { value.backendReads[0].finishedAt = null; }],
  ['unreleased response mislabeled as stale', value => { value.releasedIds = []; value.releasedAt = null; value.liveAtDestinationIds = []; value.backendReads[0].finishedAt = null; }],
  ['response finished before stale release', value => { value.browserReads[0].endedAt = 2; }],
  ['unknown release identity', value => { value.releasedIds = [99]; }],
  ['non-cancellation network failure', value => { value.browserReads[0].outcome = 'failed'; value.browserReads[0].failure = 'net::ERR_FAILED'; }],
  ['backend still pending', value => { value.backendReads[0].closedAt = null; }],
  ['no live browser at release', value => { value.liveAtDestinationIds = []; }],
]) test('completion evidence rejects ' + name, () => { const value = completion(); change(value); assert.throws(() => summarizeCatalogCompletion(value), /incomplete_catalog_completion/); });

for (const kind of ['changes', 'issues']) test(kind + ' shell-only prefetch plus cancelled data cannot claim late-data completion', async () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = observeCatalogRsc(page, origin, kind);
  let shellReads = 0, cancelledReads = 0;
  try {
    const shell = browserRequest(origin + paths[kind].nextPage + '&_rsc=shell', { headers: () => ({ rsc: '1', 'next-router-prefetch': '1' }) });
    const data = browserRequest(origin + paths[kind].nextPage + '&_rsc=data');
    page.emit('request', shell); page.emit('request', data);
    const releasedAt = performance.now();
    page.emit('response', { request: () => shell, status: () => 200, body: async () => { shellReads++; return Buffer.from('SHELL_ONLY_PRIVATE_BODY'); } });
    page.emit('response', { request: () => data, status: () => 200, body: async () => { cancelledReads++; return Buffer.from('DO_NOT_INSPECT'); } });
    page.emit('requestfinished', shell); page.emit('requestfailed', data);
    await observer.inspectCompletedBodies([0, 1]);
    const rows = observer.requests;
    assert.equal(rows[0].prefetch, true); assert.equal(rows[1].prefetch, false);
    assert.equal(rows[0].containsLateMarker, false); assert.equal(rows[0].bodyInspected, true);
    assert.equal(rows[1].bodyInspected, false); assert.equal(shellReads, 1); assert.equal(cancelledReads, 0);
    const result = summarizeCatalogCompletion({ backendReads: [{ id: 2, receivedAt: releasedAt - 1, finishedAt: releasedAt, closedAt: releasedAt }],
      releasedIds: [2], releasedAt, liveAtDestinationIds: [0, 1], browserReads: rows });
    assert.equal(result.outcome, 'cancelled-with-shell-completion');
    assert.equal(result.completedLateDataResponses, 0); assert.equal(result.completedShellResponses, 1); assert.equal(result.cancelledBrowserRequests, 1);
    assert.ok(!JSON.stringify(rows).includes('PRIVATE_BODY'));
    await observer.inspectCompletedBodies([0, 1]); assert.equal(shellReads, 1, 'do not reread completed bytes');
  } finally { observer.stop(); }
});
for (const kind of ['changes', 'issues']) test(kind + ' completed marker body is the only late-data proof and raw bytes are not retained', async () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = observeCatalogRsc(page, origin, kind);
  try {
    const request = browserRequest(origin + paths[kind].nextPage + '&_rsc=data'); page.emit('request', request);
    const releasedAt = performance.now(), bytes = Buffer.from('PRIVATE_BODY ' + lateMarkers[kind]);
    page.emit('response', { request: () => request, status: () => 200, body: async () => bytes });
    page.emit('requestfinished', request); await observer.inspectCompletedBodies([0]);
    assert.equal(observer.requests[0].containsLateMarker, true); assert.equal(observer.requests[0].bodyBytes, bytes.length);
    assert.ok(!JSON.stringify(observer.requests).includes('PRIVATE_BODY'));
    assert.equal(summarizeCatalogCompletion({ backendReads: [{ id: 2, receivedAt: releasedAt - 1, finishedAt: releasedAt, closedAt: releasedAt }],
      releasedIds: [2], releasedAt, liveAtDestinationIds: [0], browserReads: observer.requests }).outcome, 'late-data-completed');
  } finally { observer.stop(); }
});
test('completed-body inspection fails closed for missing response, oversized bytes and untracked IDs', async () => {
  assert.equal(MAX_RSC_BODY_BYTES, 256 * 1024);
  for (const mode of ['missing', 'oversized', 'failure', 'pending', 'unknown', 'empty', 'duplicate']) {
    const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = observeCatalogRsc(page, origin, 'changes');
    try {
      const request = browserRequest(origin + paths.changes.nextPage); page.emit('request', request);
      if (mode !== 'missing') page.emit('response', { request: () => request, status: () => 200, body: async () => {
        if (mode === 'failure') throw Error('PRIVATE_BODY_ERROR');
        return Buffer.alloc(MAX_RSC_BODY_BYTES + 1, 120);
      } });
      if (mode !== 'pending') page.emit('requestfinished', request);
      const ids = mode === 'unknown' ? [99] : mode === 'empty' ? [] : mode === 'duplicate' ? [0, 0] : [0];
      await assert.rejects(observer.inspectCompletedBodies(ids), { message: 'incomplete_catalog_body_evidence' });
      assert.equal(observer.requests[0].bodyInspected, false);
    } finally { observer.stop(); }
  }
});
test('shell-only completion and uninspected bytes are not enough for catalog completion', () => {
  const shell = completion(); shell.browserReads[0].containsLateMarker = false;
  assert.throws(() => summarizeCatalogCompletion(shell), /incomplete_catalog_completion/);
  const missing = completion(); missing.browserReads[0].bodyInspected = false;
  assert.throws(() => summarizeCatalogCompletion(missing), /incomplete_catalog_completion/);
});
