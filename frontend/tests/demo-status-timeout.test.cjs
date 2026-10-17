'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup} = require('react-dom/server');

function load(file, resolve, globals = {}) {
  const module = {exports: {}};
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), {compilerOptions: {
    target: ts.ScriptTarget.ES2021, module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
  }}).outputText;
  new Function('require', 'module', 'exports', ...Object.keys(globals), source)(
    resolve, module, module.exports, ...Object.values(globals));
  return module.exports;
}
function harness(fetch, base = 'https://example.invalid') {
  let next = 0;
  const timers = new Map(), calls = [];
  const api = load('lib/api.ts', name => name === 'server-only' ? {} :
    name === 'next/server' ? {connection: async () => {}} : require(name), {
    process: {env: {API_BASE_URL: base}},
    fetch: async (...args) => {calls.push(args); return fetch(...args);},
    setTimeout: (run, delay) => {const id = ++next; timers.set(id, {run, delay}); return id;},
    clearTimeout: id => timers.delete(id),
  });
  return {...api, timers, calls, expire: () => {
    for (const [id, timer] of [...timers]) {timers.delete(id); timer.run();}
  }};
}
const pending = () => new Promise(() => {});
const flush = async () => {for (let i = 0; i < 12; i++) await Promise.resolve();};

test('status read deadline cancels stalled headers and settles even if fetch ignores cancellation', async () => {
  const h = harness(pending);
  const result = h.apiGet('/health/ready', {timeoutMs: 10000});
  await flush();
  assert.equal(h.timers.size, 1);
  assert.equal([...h.timers.values()][0].delay, 10000);
  assert.equal(h.calls[0][1].cache, 'no-store');
  assert.equal(h.calls[0][1].signal.aborted, false);
  h.expire();
  assert.equal(await result, null);
  assert.equal(h.calls[0][1].signal.aborted, true);
  assert.equal(h.calls.length, 1);
  assert.equal(h.timers.size, 0);
});
test('deadline also covers stalled JSON bodies and ignores late success', async () => {
  let finishBody;
  const h = harness(async () => ({ok: true, json: () => new Promise(resolve => {finishBody = resolve;})}));
  const result = h.apiGet('/api/v1/demo/zfi-import', {timeoutMs: 10000});
  await flush(); h.expire();
  assert.equal(await result, null);
  assert.equal(h.calls[0][1].signal.aborted, true);
  finishBody({initialized: true}); await flush();
  assert.equal(await result, null);
  assert.equal(h.calls.length, 1);
});
test('successful bounded reads retain data and clear their cancellation timers', async () => {
  const data = {sample_only: true};
  const h = harness(async () => ({ok: true, json: async () => data}));
  assert.equal(await h.apiGet('/api/v1/demo/release-evidence', {timeoutMs: 10000}), data);
  assert.equal(h.timers.size, 0);
  assert.equal(h.calls[0][1].signal.aborted, false);
});
test('HTTP, network and malformed JSON failures clear deadlines without retry or exception leakage', async () => {
  for (const fetch of [async () => ({ok: false}), async () => {throw Error('private upstream');},
    async () => ({ok: true, json: async () => {throw Error('private response');}})]) {
    const h = harness(fetch);
    assert.equal(await h.apiGet('/health/ready', {timeoutMs: 10000}), null);
    assert.equal(h.calls.length, 1); assert.equal(h.timers.size, 0);
  }
});
test('unconfigured API never contacts upstream and invalid deadlines fail closed', async () => {
  const absent = harness(pending, '');
  assert.equal(await absent.apiGet('/health/ready', {timeoutMs: 10000}), null);
  assert.equal(absent.calls.length, 0); assert.equal(absent.timers.size, 0);
  const h = harness(pending);
  for (const timeoutMs of [0, -1, NaN, Infinity, 2147483648]) {
    assert.equal(await h.apiGet('/health/ready', {timeoutMs}), null);
  }
  assert.equal(h.calls.length, 0); assert.equal(h.timers.size, 0);
});
test('existing callers retain their no-store read behavior without a new deadline', async () => {
  const h = harness(async () => ({ok: true, json: async () => ({value: 1})}));
  assert.deepEqual(await h.apiGet('/existing'), {value: 1});
  assert.deepEqual(h.calls, [['https://example.invalid/existing', {cache: 'no-store'}]]);
  assert.equal(h.timers.size, 0);
});
test('late network rejection after timeout remains handled', async () => {
  let reject;
  const h = harness(() => new Promise((resolve, fail) => {reject = fail;}));
  const result = h.apiGet('/health/ready', {timeoutMs: 10000});
  await flush(); h.expire(); assert.equal(await result, null);
  reject(Error('late upstream error')); await flush();
  assert.equal(h.calls.length, 1);
});
test('real status page renders after one stalled read while preserving the other family observations', async () => {
  const identities = require('../lib/demo-family-identities.json');
  const data = {
    '/health/ready': {status: 'ready', version: identities.api_version, database_revision: identities.database_revision},
    '/api/v1/demo/release-evidence': {sample_only: true, initialized: true,
      items: Object.entries(identities.evidence).map(([version, release_id]) => ({version, release_id,
        release_type: version.includes('-SSR-') ? 'STANDARD' : 'APPLICATION'}))},
  };
  const h = harness(async url => {
    const path = new URL(url).pathname;
    return path === '/api/v1/demo/zfi-import' ? pending() : {ok: true, json: async () => data[path]};
  });
  const inspect = load('lib/demo-status.ts', name => name.endsWith('demo-family-identities.json') ? identities : require(name));
  const page = load('app/demo/status/page.tsx', name => name === 'next/link' ?
    ({href, children}) => React.createElement('a', {href}, children) :
    name.endsWith('/lib/api') ? h : name.endsWith('/lib/demo-status') ? inspect :
    name.endsWith('/localized') ? {Localized: ({children}) => React.createElement(React.Fragment, null, children)} : require(name));
  const output = page.default(); await flush();
  assert.deepEqual(h.calls.map(([url]) => new URL(url).pathname), [
    '/health/ready', '/api/v1/demo/zfi-import', '/api/v1/demo/release-evidence']);
  assert.equal(h.timers.size, 1); // The two completed reads already released their timers.
  assert.equal([...h.timers.values()][0].delay, 10000);
  h.expire();
  const html = renderToStaticMarkup(await output);
  assert.ok(html.includes('Demonstration data checks not confirmed'));
  assert.equal((html.match(/Confirmed for this data check/g) || []).length, 2);
  assert.equal((html.match(/Not confirmed: endpoint unavailable/g) || []).length, 1);
  assert.ok(html.includes('Not recorded'));
  assert.ok(!html.includes('SSR: 4') && !html.includes('ASR: 16'));
  assert.equal(h.timers.size, 0); assert.equal(h.calls.length, 3);
});
