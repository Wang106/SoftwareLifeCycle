'use strict';
// Local production-SSR verification. Never connects to a provider or business database.
// Run after `npm run build`: node scripts/check-production-history-loading.cjs
const assert = require('node:assert/strict');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {performance} = require('node:perf_hooks');
const {existsSync} = require('node:fs');

const routes = [
  {kind:'batch',page:'/deployments/DEP-FIXTURE/batches/PB-FIXTURE/history',api:'/api/v1/deployments/DEP-FIXTURE/batches/PB-FIXTURE/history',record:'PB-FIXTURE'},
  {kind:'changeover',page:'/deployments/DEP-FIXTURE/changeovers/CO-FIXTURE/history',api:'/api/v1/deployments/DEP-FIXTURE/changeovers/CO-FIXTURE/history',record:'CO-FIXTURE'},
];
const zh = require('../lib/i18n/zh.json');
const label = (text,locale) => locale==='zh' ? zh[text] : text;
const loading = {en:'Loading correction history',zh:'正在读取更正历史'};
const retry = {en:'Read this history again',zh:zh['Read this history again']};
function fixture(route) {return {kind:route.kind,record_no:route.record,deployment_no:'DEP-FIXTURE',stored_status:'ACTIVE',history_state:'NOT_RECORDED',recorded_baseline:null,effective:{revision:0,head_id:null,values:{note:'LOCAL_RAW_NOTE'}},correction_count:0,limit:50,truncated:false,corrections:[]};}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function listen(server) {
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server.address().port;
}
async function unusedPort() {
  const server = http.createServer();
  const selected = await listen(server);
  await new Promise(resolve => server.close(resolve));
  return selected;
}
const heading = (tag, text) => `<${tag}>${text}</${tag}>`;

async function main() {
  assert.ok(existsSync('.next/BUILD_ID'), 'Build the actual Next production app first: npm run build');
  const observations = [], requests = [], violations = [];
  let active;
  const api = http.createServer((req, res) => {
    requests.push({method: req.method, url: req.url});
    if (req.method !== 'GET' || req.url !== active?.route.api || req.headers.authorization || req.headers.cookie) {
      violations.push({method: req.method, url: req.url});
      res.writeHead(400); res.end(); return;
    }
    active.seen = true;
    active.response = res;
    const ownAttempt=active;res.on('close',()=>{ownAttempt.connectionClosed=true;});
    if (active.mode === 'body') {
      res.writeHead(200, {'content-type': 'application/json'});
      res.flushHeaders(); res.write('{'); // Valid headers, deliberately unfinished JSON.
    } else if (active.mode === 'http-error') {
      res.writeHead(503); res.end('LOCAL_PRIVATE_UPSTREAM_ERROR');
    } else if (active.mode === 'bad-json') {
      res.writeHead(200, {'content-type': 'application/json'});
      res.end('LOCAL_PRIVATE_INVALID_JSON');
    } else if (active.mode === 'mismatch') {
      res.writeHead(200, {'content-type':'application/json'});res.end(JSON.stringify({...fixture(active.route),deployment_no:'FOREIGN-PRIVATE'}));
    } else if (active.mode === 'ready') {
      res.writeHead(200, {'content-type': 'application/json'});
      res.end(JSON.stringify(fixture(active.route)));
    }
    // `gate` and `headers` withhold all headers. The test explicitly releases a gate.
  });
  let child, logs = '';
  const started = performance.now();
  try {
    const apiPort = await listen(api), appPort = await unusedPort();
    const base = `http://127.0.0.1:${appPort}`;
    // Allowlist environment rather than forwarding credentials or provider settings.
    child = spawn(process.execPath, [require.resolve('next/dist/bin/next'), 'start',
      '--hostname', '127.0.0.1', '--port', String(appPort)], {
      env: {PATH: process.env.PATH, NODE_ENV: 'production', NEXT_TELEMETRY_DISABLED: '1',
        API_BASE_URL: `http://127.0.0.1:${apiPort}`, NEXT_PUBLIC_API_BASE_URL: '', NEXT_PUBLIC_API_URL: '',
        BROWSER_OIDC_MODE: 'disabled', BROWSER_SESSION_MODE: 'disabled'},
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    child.on('error', error => {logs += error.message;});
    for (const stream of [child.stdout, child.stderr]) stream.on('data', chunk => {logs = (logs + chunk).slice(-8000);});
    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (child.exitCode !== null) throw Error(`Next exited before readiness: ${logs}`);
      try {
        const response = await fetch(base + '/auth/session', {signal: AbortSignal.timeout(1000)});
        await response.arrayBuffer();
        if (response.status === 503) {ready = true; break;}
      } catch {}
      await pause(100);
    }
    assert.ok(ready, `Next production server did not become ready: ${logs}`);

    async function read(route, locale, mode) {
      active = {route, mode, seen: false, released: false};
      const attempt = active, before = requests.length, begin = performance.now();
      let fallbackMs;
      const response = await fetch(base + route.page, {
        headers: {Cookie: `slc_language=${locale}`, 'User-Agent': 'Local-SSR-stream-verification'},
        signal: AbortSignal.timeout(25000),
      });
      assert.equal(response.status, 200);
      assert.ok(response.headers.get('cache-control')?.includes('no-store'));
      let html = '';
      const decoder = new TextDecoder(), reader = response.body.getReader();
      try {
        for (;;) {
          const {value, done} = await reader.read();
          if (done) {html += decoder.decode(); break;}
          html += decoder.decode(value, {stream: true});
          if (fallbackMs === undefined && html.includes(heading('h1', loading[locale]))) {
            fallbackMs = performance.now() - begin;
            if (mode === 'gate') {
              // Causal assertion, not a machine-speed benchmark: no API response exists yet.
              for (let i = 0; !attempt.seen && i < 40; i++) await pause(25);
              assert.ok(attempt.seen, 'Expected local API request before releasing its response');
              assert.equal(attempt.response.headersSent, false);
              attempt.released = true;
              attempt.response.writeHead(200, {'content-type': 'application/json'});
              attempt.response.end(JSON.stringify(fixture(route)));
            }
          }
        }
      } finally {reader.releaseLock();}
      const elapsedMs = performance.now() - begin;
      assert.equal(requests.length - before, 1, 'No background retries or duplicate API reads');
      assert.ok(html.includes(`lang="${locale === 'zh' ? 'zh-CN' : 'en'}"`));
      assert.ok(!html.includes('LOCAL_PRIVATE_'), 'Upstream error bodies must not leak');
      if (['gate', 'ready'].includes(mode)) {
        assert.ok(html.includes(heading('h1',label(route.kind==='batch'?'Batch correction history':'Changeover correction history',locale))), 'Render exact history');
        assert.ok(html.includes('LOCAL_RAW_NOTE'));assert.ok(html.includes(route.record));
        assert.ok(!html.includes(heading('h1',label('Correction history unavailable',locale))));
        if (mode === 'gate') {
          assert.ok(attempt.released, 'Loading markup must arrive before the API gate is released');
          assert.ok(html.includes('aria-busy="true"'));
        }
      } else {
        assert.ok(html.includes(heading('h1',label('Correction history unavailable',locale))), 'Render translated unavailable state');
        assert.ok(html.includes(`href="${route.page}">${retry[locale]}</a>`), 'Offer an explicit same-page reload');
        assert.ok(!html.includes('LOCAL_RAW_NOTE'));assert.ok(!html.includes('FOREIGN-PRIVATE'));
        assert.ok(!html.includes('href="/snapshots/'), 'Unavailable data must not fabricate release evidence');
        if (['headers', 'body'].includes(mode)) {
          assert.ok(elapsedMs >= 14000 && elapsedMs < 23000, 'Use the real 15s deadline for headers and body');
          assert.ok(fallbackMs !== undefined && fallbackMs < 14000, 'Loading markup must precede timeout');
          for(let i=0;!attempt.connectionClosed&&i<40;i++)await pause(25);
          assert.ok(attempt.connectionClosed,'Timed-out upstream connection is cancelled');
        }
      }
      observations.push({page: route.page, locale, mode, fallbackMs: fallbackMs === undefined ? null : Math.round(fallbackMs),
        completeMs: Math.round(elapsedMs)});
      console.log(JSON.stringify(observations.at(-1)));
    }

    for (const route of routes) for (const locale of ['zh', 'en']) {
      await read(route, locale, 'gate');
      // Cover both endpoints/locales; swap header/body stalls across the four cases.
      const mode = (route.kind === 'batch') === (locale === 'zh') ? 'headers' : 'body';
      await read(route, locale, mode);
      await read(route, locale, 'ready'); // Explicit subsequent GET recovers; no stale timeout result.
      await read(route, locale, 'http-error');
      await read(route, locale, 'bad-json');
      await read(route, locale, 'mismatch');
    }
    for(const route of routes)for(const locale of ['zh','en']){
      const before=requests.length, page=route.page.replace(/\/history$/, '/correct');
      const response=await fetch(base+page,{headers:{Cookie:`slc_language=${locale}`},signal:AbortSignal.timeout(5000)});
      const html=await response.text();assert.equal(response.status,200);
      const title=route.kind==='batch'?'Batch correction workbench':'Changeover correction workbench';
      const disabled=route.kind==='batch'?'Batch correction submission is disabled or unavailable for this session.':'Changeover correction submission is disabled or unavailable for this session.';
      assert.ok(html.includes(label(title,locale)));assert.ok(html.includes(label(disabled,locale)));
      assert.ok(/<button[^>]*disabled/.test(html));assert.equal(requests.length,before,'Disabled workbench must not fetch private context');
      observations.push({page,locale,mode:'disabled-workbench',upstreamCalls:0});
    }
    assert.deepEqual(violations, [], 'Only expected loopback GETs without identity headers are allowed');
    console.log(`PASS: ${observations.length} production SSR observations; ${requests.length} loopback API GETs; ${Math.round(performance.now() - started)}ms total`);
    console.log('Local controlled HTTP/SSR verification only; not browser, Cloudflare, Render, cold-start or user-network latency acceptance.');
  } finally {
    if (child?.pid && child.exitCode === null && child.signalCode === null) {
      const exited = once(child, 'exit').catch(() => {});
      child.kill('SIGTERM');
      await Promise.race([exited, pause(2000)]);
      if (child.exitCode === null && child.signalCode === null) {
        child.kill('SIGKILL');
        await Promise.race([exited, pause(2000)]);
      }
    }
    api.closeAllConnections();
    await new Promise(resolve => api.close(resolve));
  }
}

main().catch(error => {console.error(error.stack); process.exitCode = 1;});
