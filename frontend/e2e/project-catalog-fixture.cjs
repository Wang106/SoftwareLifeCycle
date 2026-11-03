'use strict';
// Synthetic loopback API only. The application supplies the real read timer.
const http = require('node:http');
const { once } = require('node:events');
const { performance } = require('node:perf_hooks');

const query = 'q=A+%26+B&status=ACTIVE&customer_id=customer-one&limit=10&offset=20';
const firstQuery = query.slice(0, -'&offset=20'.length);
const apiBase = '/api/v1/organization-views/projects';
const paths = Object.freeze({
  page: '/projects?' + query,
  api: apiBase + '?' + query,
  firstPage: '/projects?' + firstQuery,
  firstApi: apiBase + '?' + firstQuery,
  resetPage: '/projects',
  resetApi: apiBase + '?',
});
const ancillary = new Map([
  [paths.firstApi, { limit: 10, offset: 0 }],
  [paths.resetApi, { limit: 50, offset: 0 }],
  // HTTP clients may omit the delimiter of an empty query.
  [apiBase, { limit: 50, offset: 0 }],
]);

function emptyCatalog(limit, offset) {
  return { kind: 'projects', total: 0, limit, offset, next_offset: null, items: [] };
}

async function startProjectCatalogFixture(phase) {
  if (!['headers', 'body'].includes(phase)) throw Error('invalid_project_fixture_phase');
  const requests = [], violations = [], pending = new Set(), open = new Map();
  let ready = false, stopped = false, closing;
  const server = http.createServer((req, res) => {
    const target = req.url === paths.api;
    const other = ancillary.get(req.url);
    const credentials = ['authorization', 'proxy-authorization', 'cookie']
      .some(name => Object.hasOwn(req.headers, name));
    const hasBody = Object.hasOwn(req.headers, 'transfer-encoding') ||
      (Object.hasOwn(req.headers, 'content-length') && req.headers['content-length'] !== '0');
    const allowed = req.method === 'GET' && (target || other) && !credentials && !hasBody;
    const entry = {
      kind: !allowed ? 'rejected' : target ? 'target' : 'ancillary',
      method: req.method,
      // Rejected URL/query/header values are not evidence and may contain secrets.
      url: allowed ? req.url : '[rejected]',
      phase: !allowed ? 'rejected' : target && !ready ? phase : 'ready',
      receivedAt: performance.now(), headersSent: false,
      closedAt: null, finishedAt: null, status: null,
    };
    requests.push(entry);
    let resolveClose;
    open.set(res, new Promise(resolve => { resolveClose = resolve; }));
    res.once('finish', () => { entry.finishedAt = performance.now(); });
    res.once('close', () => {
      entry.closedAt = performance.now();
      pending.delete(res); open.delete(res); resolveClose();
    });
    function headers(status) {
      entry.status = status;
      res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    }
    if (!allowed) {
      violations.push({ method: req.method, reason: 'project_fixture_rejected' });
      headers(400); res.end('{"error":"project_fixture_rejected"}');
      entry.headersSent = res.headersSent;
      return;
    }
    if (target && !ready) {
      pending.add(res);
      if (phase === 'body') {
        headers(200); res.flushHeaders(); res.write('{');
        entry.headersSent = res.headersSent;
      }
      return; // No fixture timeout or delayed success: wait for the app's abort.
    }
    const values = target ? { limit: 10, offset: 20 } : other;
    headers(200); res.end(JSON.stringify(emptyCatalog(values.limit, values.offset)));
    entry.headersSent = res.headersSent;
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return {
    apiOrigin: `http://127.0.0.1:${server.address().port}`,
    get requests() { return Object.freeze(requests.map(entry => Object.freeze({ ...entry }))); },
    get violations() { return Object.freeze(violations.map(entry => Object.freeze({ ...entry }))); },
    get pendingCount() { return pending.size; },
    recover() {
      if (stopped) throw Error('project_fixture_closed');
      ready = true; // Only future target reads recover; never finish a held response.
    },
    close() {
      if (closing) return closing;
      stopped = true;
      closing = (async () => {
        const responsesClosed = [...open.values()];
        const listenerClosed = once(server, 'close');
        server.close();
        for (const response of pending) response.destroy();
        server.closeAllConnections();
        await listenerClosed;
        await Promise.all(responsesClosed);
      })();
      return closing;
    },
  };
}

module.exports = { query, paths, startProjectCatalogFixture };
