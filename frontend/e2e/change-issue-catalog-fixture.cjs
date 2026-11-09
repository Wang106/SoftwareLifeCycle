'use strict';
// Synthetic loopback API only. The app owns its API read deadline; completed
// browser-body inspection below has a separate bounded evidence-read deadline.
const http = require('node:http');
const { once } = require('node:events');
const { performance } = require('node:perf_hooks');
const queries = Object.freeze({
  changes: 'q=A+%26+B&status=IN_VERIFICATION&scope=STANDARD&limit=10&offset=20&source=INTERNAL&change_type=ENHANCEMENT&software_id=software-one&customer_id=customer-one&project_id=project-one',
  issues: 'q=A+%26+B&status=OPEN&scope=STANDARD&limit=10&offset=20&severity=HIGH',
});
const MAX_RSC_BODY_BYTES = 256 * 1024;
const lateMarkers = Object.freeze({ changes: 'SYNTHETIC_LATE_CATALOG_ROW_CHANGES_991', issues: 'SYNTHETIC_LATE_CATALOG_ROW_ISSUES_991' });
const paths = Object.freeze(Object.fromEntries(Object.entries(queries).map(([kind, query]) => {
  const api = '/api/v1/change-catalog/' + (kind === 'changes' ? 'requests' : 'issues');
  const first = query.replace('&offset=20', '');
  return [kind, Object.freeze({ page: '/' + kind + '?' + query, api: api + '?' + query,
    firstPage: '/' + kind + '?' + first, nextPage: '/' + kind + '?' + first + '&offset=20', firstApi: api + '?' + first,
    resetPage: '/' + kind, resetApi: api + '?' })];
})));
function catalog(kind, total, limit, offset, next_offset = null) {
  return { kind, total, limit, offset, next_offset, items: [],
    ...(kind === 'changes' ? { in_verification: total, ready_for_release: total } : {}) };
}
function lateCatalog(kind) {
  return { ...catalog(kind, 991, 10, 20), items: [{
    id: '33333333-3333-4333-8333-333333333333', title: lateMarkers[kind], scope: 'STANDARD',
    ...(kind === 'changes' ? { request_no: 'SCR-SYNTHETIC-LATE', status: 'IN_VERIFICATION', source: 'INTERNAL', change_type: 'ENHANCEMENT' } :
      { issue_no: '900991', status: 'OPEN', severity: 'HIGH' }),
  }] };
}
async function startChangeIssueCatalogFixture(kind, phase) {
  if (!Object.hasOwn(paths, kind)) throw Error('invalid_change_issue_fixture_kind');
  if (!['headers', 'body'].includes(phase)) throw Error('invalid_change_issue_fixture_phase');
  const p = paths[kind], requests = [], violations = [], pending = new Map(), open = new Map();
  const ancillary = new Map([
    [p.firstApi, catalog(kind, 7, 10, 0, 20)],
    [p.resetApi, catalog(kind, 0, 50, 0)], [p.resetApi.slice(0, -1), catalog(kind, 0, 50, 0)],
    ['/api/v1/organization-views/projects?', catalog('projects', 0, 50, 0)],
    ['/api/v1/organization-views/projects', catalog('projects', 0, 50, 0)],
  ]);
  let ready = false, stopped = false, closing;
  function headers(res, entry) {
    entry.status = 200;
    res.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
  }
  const server = http.createServer((req, res) => {
    const target = req.url === p.api, other = ancillary.get(req.url);
    const credentials = ['authorization', 'proxy-authorization', 'cookie'].some(name => Object.hasOwn(req.headers, name));
    const body = Object.hasOwn(req.headers, 'transfer-encoding') || (Object.hasOwn(req.headers, 'content-length') && req.headers['content-length'] !== '0');
    const allowed = req.method === 'GET' && (target || other) && !credentials && !body;
    const entry = { id: requests.length, kind: !allowed ? 'rejected' : target ? 'target' : 'ancillary', method: req.method,
      url: allowed ? req.url : '[rejected]', phase: !allowed ? 'rejected' : target && !ready ? phase : 'ready',
      receivedAt: performance.now(), headersSent: false, closedAt: null, finishedAt: null, status: null };
    requests.push(entry);
    let resolveClose;
    open.set(res, new Promise(resolve => { resolveClose = resolve; }));
    res.once('finish', () => { entry.finishedAt = performance.now(); });
    res.once('close', () => { entry.closedAt = performance.now(); pending.delete(res); open.delete(res); resolveClose(); });
    if (!allowed) {
      violations.push({ method: req.method, reason: 'change_issue_fixture_rejected' });
      entry.status = 400; res.writeHead(400, { 'content-type': 'application/json', 'cache-control': 'no-store' });
      res.end('{"error":"change_issue_fixture_rejected"}'); entry.headersSent = res.headersSent; return;
    }
    if (target && !ready) {
      pending.set(res, entry);
      if (phase === 'body') { headers(res, entry); res.flushHeaders(); res.write('{'); entry.headersSent = res.headersSent; }
      return;
    }
    headers(res, entry); res.end(JSON.stringify(target ? catalog(kind, 0, 10, 20) : other)); entry.headersSent = res.headersSent;
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  function assertOpen() { if (stopped) throw Error('change_issue_fixture_closed'); }
  return {
    apiOrigin: `http://127.0.0.1:${server.address().port}`,
    get requests() { return Object.freeze(requests.map(entry => Object.freeze({ ...entry }))); },
    get violations() { return Object.freeze(violations.map(entry => Object.freeze({ ...entry }))); },
    get pendingCount() { return pending.size; },
    recover() { assertOpen(); ready = true; }, // Only future reads recover, never a held response.
    hold() { assertOpen(); ready = false; },
    releaseHeld() {
      assertOpen();
      // Separate explicit stale-result probe, never used for the deadline/retry proof.
      const body = JSON.stringify(lateCatalog(kind)), releasedIds = [];
      for (const [res, entry] of pending) {
        if (res.destroyed || res.writableEnded) continue;
        if (!res.headersSent) headers(res, entry);
        releasedIds.push(entry.id);
        res.end(phase === 'body' ? body.slice(1) : body); entry.headersSent = res.headersSent;
      }
      return Object.freeze(releasedIds);
    },
    close() {
      if (closing) return closing;
      stopped = true;
      closing = (async () => {
        const responsesClosed = [...open.values()], listenerClosed = once(server, 'close');
        server.close(); for (const res of pending.keys()) res.destroy(); server.closeAllConnections();
        await listenerClosed; await Promise.all(responsesClosed);
      })();
      return closing;
    },
  };
}
// Observe the browser transport without buffering or changing its requests.
// The caller installs this before first-page navigation, so prefetch is visible.
function observeCatalogRsc(page, origin, kind) {
  if (!Object.hasOwn(paths, kind)) throw Error('invalid_change_issue_fixture_kind');
  const target = new URL(origin);
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || target.origin !== origin) throw Error('loopback_observer_required');
  const rows = new Map(), responses = new Map(), allowed = [paths[kind].page, paths[kind].nextPage];
  const onRequest = request => {
    const url = new URL(request.url()), raw = url.pathname + url.search;
    if (url.origin !== origin || request.method() !== 'GET' || request.isNavigationRequest() ||
        request.resourceType() === 'document' || request.headers().rsc !== '1' ||
        !allowed.some(path => raw === path || (raw.startsWith(path + '&_rsc=') && /^[A-Za-z0-9_-]+$/.test(raw.slice((path + '&_rsc=').length))))) return;
    if (rows.has(request)) return;
    const headers = request.headers();
    rows.set(request, { id: rows.size, path: raw, receivedAt: performance.now(), endedAt: null,
      prefetch: headers['next-router-prefetch'] === '1' || headers.purpose === 'prefetch' || headers['sec-purpose'] === 'prefetch',
      outcome: 'pending', status: null, failure: null, bodyInspected: false, bodyBytes: null, containsLateMarker: null });
  };
  const onResponse = response => { const row = rows.get(response.request()); if (row) { row.status = response.status(); responses.set(response.request(), response); } };
  const terminal = (request, outcome) => {
    const row = rows.get(request);
    if (!row || row.outcome !== 'pending') return;
    row.outcome = outcome; row.endedAt = performance.now();
    if (outcome === 'failed') row.failure = request.failure()?.errorText === 'net::ERR_ABORTED' ? 'net::ERR_ABORTED' : 'unexpected_failure';
  };
  const onFinished = request => terminal(request, 'finished'), onFailed = request => terminal(request, 'failed');
  page.on('request', onRequest); page.on('response', onResponse);
  page.on('requestfinished', onFinished); page.on('requestfailed', onFailed);
  return {
    get requests() { return Object.freeze([...rows.values()].map(row => Object.freeze({ ...row }))); },
    async inspectCompletedBodies(ids) {
      // Reads Playwright's already-completed response storage, never the live
      // transport. Only bounded metadata is retained or attached. Playwright
      // returns a full Buffer; the cap rejects it after retrieval, not allocation.
      const fail = () => { throw Error('incomplete_catalog_body_evidence'); };
      if (!Array.isArray(ids) || !ids.length || ids.length > 8 || new Set(ids).size !== ids.length ||
          !ids.every(id => [...rows.values()].some(row => row.id === id))) fail();
      const deadline = performance.now() + 5000;
      for (const [request, row] of rows) {
        if (!ids.includes(row.id)) continue;
        if (row.outcome === 'pending') fail();
        if (row.outcome === 'failed' || row.bodyInspected) continue;
        const response = responses.get(request);
        if (!response || typeof response.body !== 'function' || row.status !== 200) fail();
        let timer;
        try {
          const remaining = deadline - performance.now(); if (remaining <= 0) fail();
          const bytes = await Promise.race([response.body(), new Promise((resolve, reject) => {
            timer = setTimeout(() => reject(Error('body_evidence_timeout')), remaining);
          })]);
          if (!Buffer.isBuffer(bytes) || bytes.length > MAX_RSC_BODY_BYTES) fail();
          row.bodyBytes = bytes.length;
          row.containsLateMarker = bytes.includes(Buffer.from(lateMarkers[kind]));
          row.bodyInspected = true;
        } catch { fail(); } finally { if (timer) clearTimeout(timer); }
      }
    },
    stop() {
      responses.clear();
      page.off('request', onRequest); page.off('response', onResponse);
      page.off('requestfinished', onFinished); page.off('requestfailed', onFailed);
    },
  };
}

// Reject empty candidates and distinguish transport cancellation from actual
// post-release body completion. Backend and browser IDs are separate domains;
// Next may coalesce reads, so this is not a claimed one-to-one request mapping.
function summarizeCatalogCompletion({ backendReads, browserReads, releasedIds, releasedAt, liveAtDestinationIds }) {
  const requireEvidence = condition => { if (!condition) throw Error('incomplete_catalog_completion'); };
  for (const rows of [backendReads, browserReads]) {
    requireEvidence(Array.isArray(rows) && rows.length > 0);
    requireEvidence(rows.every(row => Number.isInteger(row.id) && row.id >= 0));
    requireEvidence(new Set(rows.map(row => row.id)).size === rows.length);
  }
  for (const ids of [releasedIds, liveAtDestinationIds]) requireEvidence(Array.isArray(ids) && new Set(ids).size === ids.length);
  requireEvidence(releasedIds.every(id => backendReads.some(row => row.id === id)));
  requireEvidence(liveAtDestinationIds.every(id => browserReads.some(row => row.id === id)));
  requireEvidence(releasedIds.length ? Number.isFinite(releasedAt) && liveAtDestinationIds.length > 0 : releasedAt === null);
  for (const row of backendReads) {
    requireEvidence(Number.isFinite(row.receivedAt) && Number.isFinite(row.closedAt) && row.closedAt >= row.receivedAt);
    if (releasedIds.includes(row.id)) requireEvidence(Number.isFinite(row.finishedAt) && row.finishedAt >= releasedAt && row.closedAt >= row.finishedAt);
    else requireEvidence(row.finishedAt === null);
  }
  let completed = 0, shells = 0, cancelled = 0;
  for (const row of browserReads) {
    requireEvidence(Number.isFinite(row.receivedAt) && Number.isFinite(row.endedAt) && row.endedAt >= row.receivedAt);
    if (row.outcome === 'failed') { requireEvidence(row.failure === 'net::ERR_ABORTED'); cancelled++; }
    else {
      requireEvidence(row.outcome === 'finished' && row.status === 200 && row.failure === null &&
        row.bodyInspected === true && Number.isInteger(row.bodyBytes) && row.bodyBytes >= 0 &&
        row.bodyBytes <= MAX_RSC_BODY_BYTES && typeof row.containsLateMarker === 'boolean');
      if (row.containsLateMarker) {
        requireEvidence(releasedIds.length > 0 && liveAtDestinationIds.includes(row.id) && row.endedAt >= releasedAt);
        completed++;
      } else shells++;
    }
  }
  // Shell-only RSC completion is not evidence that the held catalog data was
  // delivered or cancelled. At least one actual data/cancellation path is needed.
  requireEvidence(completed + cancelled > 0);
  const outcome = completed ? (cancelled || shells ? 'mixed' : 'late-data-completed') :
    shells ? 'cancelled-with-shell-completion' : 'cancelled';
  return Object.freeze({ outcome, completedLateDataResponses: completed, completedShellResponses: shells,
    cancelledBrowserRequests: cancelled, releasedBackendResponses: releasedIds.length });
}
module.exports = { queries, paths, lateMarkers, MAX_RSC_BODY_BYTES, startChangeIssueCatalogFixture, observeCatalogRsc, summarizeCatalogCompletion };
