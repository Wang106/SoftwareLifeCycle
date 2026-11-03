'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { setTimeout: delay } = require('node:timers/promises');
const { query, paths, startProjectCatalogFixture } = require('../e2e/project-catalog-fixture.cjs');

function observe(promise) {
  let settled = false;
  const result = promise.then(value => { settled = true; return { value }; },
    error => { settled = true; return { error }; });
  return { result, get settled() { return settled; } };
}
async function until(check) {
  for (let attempt = 0; attempt < 200; attempt++) {
    if (check()) return;
    await delay(5);
  }
  assert.ok(check(), 'fixture observation did not arrive');
}
function rawRequest(origin, url, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(origin, { path: url, method: 'GET', ...options }, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.once('error', reject);
      res.once('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
    });
    req.once('error', reject);
    req.setTimeout(2000, () => req.destroy(Error('fixture_client_timeout')));
    req.end(options.body);
  });
}

test('project fixture exposes fixed query forms and rejects unknown phase', async () => {
  assert.equal(query, 'q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20');
  assert.equal(paths.page, '/projects?' + query);
  assert.equal(paths.api, '/api/v1/organization-views/projects?' + query);
  assert.equal(paths.firstApi, paths.api.slice(0, -'&offset=20'.length));
  for (const phase of [undefined, null, '', 'ready', 'error', 'HEADERS']) {
    await assert.rejects(startProjectCatalogFixture(phase), /invalid_project_fixture_phase/);
  }
});

test('headers remain pending across recover; only a new exact GET gets valid empty data', { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture('headers');
  const controller = new AbortController();
  const held = observe(fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) }));
  try {
    await until(() => fixture.pendingCount === 1);
    const original = fixture.requests[0];
    assert.equal(original.kind, 'target');
    assert.equal(original.phase, 'headers');
    assert.equal(original.headersSent, false);
    assert.equal(original.status, null);
    assert.equal(original.finishedAt, null);
    assert.equal(original.closedAt, null);
    await delay(30);
    assert.equal(held.settled, false);
    fixture.recover(); fixture.recover();
    assert.equal(fixture.requests.length, 1);
    await delay(30);
    assert.equal(held.settled, false, 'recover must not complete the old response');
    const recovered = await fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.timeout(2000) });
    assert.equal(recovered.status, 200);
    assert.deepEqual(await recovered.json(), { kind: 'projects', total: 0, limit: 10, offset: 20, next_offset: null, items: [] });
    assert.deepEqual(fixture.requests.map(r => [r.kind, r.url, r.phase]),
      [['target', paths.api, 'headers'], ['target', paths.api, 'ready']]);
    assert.equal(held.settled, false);
    controller.abort();
    assert.ok((await held.result).error);
    await until(() => fixture.requests[0].closedAt !== null);
    assert.equal(fixture.requests[0].finishedAt, null);
    assert.equal(fixture.pendingCount, 0);
    assert.deepEqual(fixture.violations, []);
  } finally { controller.abort(); await fixture.close(); await held.result; }
});

test('body hold flushes headers and partial JSON but never finishes before client abort', { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture('body');
  const controller = new AbortController();
  let rest;
  try {
    const response = await fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('content-type'), 'application/json');
    const reader = response.body.getReader();
    const first = await reader.read();
    assert.equal(first.done, false);
    assert.equal(new TextDecoder().decode(first.value), '{');
    rest = observe(reader.read());
    assert.equal(fixture.requests[0].headersSent, true);
    assert.equal(fixture.requests[0].phase, 'body');
    assert.equal(fixture.requests[0].finishedAt, null);
    fixture.recover();
    await delay(30);
    assert.equal(rest.settled, false);
    assert.equal(fixture.requests.length, 1);
    const recovered = await fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.timeout(2000) });
    assert.equal((await recovered.json()).total, 0);
    assert.equal(rest.settled, false);
    controller.abort();
    assert.ok((await rest.result).error);
    await until(() => fixture.requests[0].closedAt !== null);
    assert.equal(fixture.requests[0].finishedAt, null);
    assert.deepEqual(fixture.violations, []);
  } finally { controller.abort(); await fixture.close(); if (rest) await rest.result; }
});

test('finite ancillary reads never release or increment the held target', { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture('headers');
  const controller = new AbortController();
  const held = observe(fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) }));
  try {
    await until(() => fixture.pendingCount === 1);
    for (const [url, limit] of [[paths.firstApi, 10], [paths.resetApi, 50], [paths.resetApi.slice(0, -1), 50]]) {
      const result = await rawRequest(fixture.apiOrigin, url);
      assert.equal(result.status, 200);
      assert.deepEqual(JSON.parse(result.body), { kind: 'projects', total: 0, limit, offset: 0, next_offset: null, items: [] });
    }
    assert.equal(fixture.requests.filter(r => r.kind === 'target').length, 1);
    assert.equal(fixture.requests.filter(r => r.kind === 'ancillary').length, 3);
    assert.equal(fixture.pendingCount, 1);
    assert.equal(held.settled, false);
    assert.deepEqual(fixture.violations, []);
  } finally { controller.abort(); await fixture.close(); await held.result; }
});

test('unknown queries paths credentials bodies and mutation methods are rejected without exposing input', { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture('headers');
  const cases = [
    [paths.api, { method: 'POST' }], [paths.api, { method: 'HEAD' }],
    [paths.api, { headers: { authorization: 'Bearer PRIVATE_TOKEN' } }],
    [paths.api, { headers: { authorization: '' } }],
    [paths.api, { headers: { cookie: 'PRIVATE_COOKIE=value' } }],
    [paths.api, { headers: { cookie: '' } }],
    [paths.api, { headers: { 'proxy-authorization': 'PRIVATE_PROXY' } }],
    [paths.api, { headers: { 'content-length': '1' }, body: 'x' }],
    [paths.api, { headers: { 'transfer-encoding': 'chunked' }, body: 'x' }],
    [paths.api.replace('offset=20', 'offset=21'), {}],
    [paths.api + '&q=PRIVATE_DUPLICATE', {}],
    [paths.api + '&token=PRIVATE_QUERY', {}],
    [paths.api + '&_rsc=fixture', {}],
    [paths.api.replace('q=A+%26+B', 'q=A%20%26%20B'), {}],
    ['/api/v1/organization-views/customers?' + query, {}],
    ['/auth/session', {}], ['/control/recover', {}],
    ['http://outside.invalid' + paths.api, {}],
  ];
  try {
    for (const [url, options] of cases) {
      const result = await rawRequest(fixture.apiOrigin, url, options);
      assert.equal(result.status, 400, url);
      assert.ok(!result.body.includes('PRIVATE_'));
    }
    assert.equal(fixture.violations.length, cases.length);
    assert.equal(fixture.requests.filter(r => r.kind === 'target' || r.kind === 'ancillary').length, 0);
    assert.equal(fixture.pendingCount, 0);
    assert.ok(!JSON.stringify({ requests: fixture.requests, violations: fixture.violations }).includes('PRIVATE_'));
    assert.ok(fixture.requests.every(r => r.url === '[rejected]'));
  } finally { await fixture.close(); }
});

test('observations are immutable snapshots and finish differs from aborted close', { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture('headers');
  try {
    fixture.recover();
    const response = await fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.timeout(2000) });
    await response.json();
    await until(() => fixture.requests[0]?.closedAt !== null);
    const snapshot = fixture.requests;
    assert.ok(Object.isFrozen(snapshot));
    assert.ok(Object.isFrozen(snapshot[0]));
    assert.throws(() => { snapshot[0].kind = 'rejected'; }, TypeError);
    assert.throws(() => snapshot.push({}), TypeError);
    assert.equal(fixture.requests[0].kind, 'target');
    const entry = snapshot[0];
    assert.ok(Number.isFinite(entry.receivedAt));
    assert.ok(entry.finishedAt >= entry.receivedAt);
    assert.ok(entry.closedAt >= entry.finishedAt);
    assert.equal(entry.status, 200);
    assert.equal(entry.headersSent, true);
  } finally { await fixture.close(); }
});

for (const phase of ['headers', 'body']) test(`close terminates held ${phase}, clears pending and is idempotent`, { timeout: 5000 }, async () => {
  const fixture = await startProjectCatalogFixture(phase);
  const controller = new AbortController();
  let held;
  try {
    if (phase === 'headers') held = observe(fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) }));
    else {
      const response = await fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(3000)]) });
      held = observe(response.text());
    }
    await until(() => fixture.pendingCount === 1);
    await fixture.close(); await fixture.close();
    assert.ok((await held.result).error);
    assert.equal(fixture.pendingCount, 0);
    assert.ok(Number.isFinite(fixture.requests[0].closedAt));
    assert.equal(fixture.requests[0].finishedAt, null);
    assert.throws(() => fixture.recover(), /project_fixture_closed/);
    await assert.rejects(fetch(fixture.apiOrigin + paths.api, { signal: AbortSignal.timeout(1000) }));
  } finally { controller.abort(); await fixture.close(); if (held) await held.result; }
});
