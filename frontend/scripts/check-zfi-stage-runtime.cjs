'use strict';
// Local production-route verification. Never connects to a provider or business database.
// Run after `npm run build`: node scripts/check-zfi-stage-runtime.cjs
const assert = require('node:assert/strict');
const http = require('node:http');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const {existsSync} = require('node:fs');

const expectedRoles = {
  STANDARD: ['Electronics Engineer', 'Electronics Manager', 'Systems Engineer', 'R&D Director'],
  APPLICATION: ['Application Engineer', 'Application Manager', 'Systems Engineer', 'Project Manager'],
};
const recordedRoles = {
  STANDARD: ['电子工程师', '电子经理', '系统工程师', '研发总监'],
  APPLICATION: ['应用工程师', '应用经理', '系统工程师', '项目经理'],
};
const translations = {
  en: {
    matched: 'Matched records', current: 'Current stage', recorded: 'Recorded pending stage',
    unknown: 'Stage cannot be confirmed', unavailable: 'Excel import API unavailable',
    invalid: 'Invalid or repeated stage parameter. The stage filter was not applied; other filters remain in effect.',
    disclaimer: 'Recorded sample stages do not establish current frozen Snapshot binding, authorized tasks or formal release.',
  },
  zh: {
    matched: '匹配记录数', current: '当前节点', recorded: '已记录待审节点',
    unknown: '节点无法确认', unavailable: 'Excel 导入 API 暂不可用',
    invalid: '节点参数无效或重复。未应用节点筛选，其他筛选条件仍然有效。',
    disclaimer: '样例已记录节点不能证明当前冻结快照绑定、已授权任务或正式发布。',
  },
};
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
function row(type, stage) {
  const prefix = type === 'STANDARD' ? 'SSR' : 'ASR';
  return {
    source_ref: `REF-${prefix}-${stage}`,
    release_id: `00000000-0000-4000-8000-${type === 'STANDARD' ? '1' : '2'}0000000000${stage}`,
    version: `${prefix}-runtime-stage-${stage}`,
    release_type: type,
    product: 'runtime target',
    customer: type === 'APPLICATION' ? 'KUBO' : null,
    project_code: type === 'APPLICATION' ? `PROJECT-${stage}` : null,
    record_status: 'READY',
    approval_no: `APR-${prefix}-${stage}`,
    approval_status: 'PENDING',
    source_release_date: '2026-10-23',
    approval_progress: {approved_steps: stage - 1, total_steps: 4, current_step_order: stage,
      current_role: recordedRoles[type][stage - 1], closed: false},
    supplied_artifacts: 0,
    supplied_test_evidence: 0,
  };
}
const items = ['STANDARD', 'APPLICATION'].flatMap(type => [1, 2, 3, 4].map(stage => row(type, stage)));
items.push({...row('APPLICATION', 1), release_id: '00000000-0000-4000-8000-299999999999',
  version: 'ASR-runtime-unknown', approval_progress: {...row('APPLICATION', 1).approval_progress, current_role: '电子经理'}});
const receipt = {sample_only: true, initialized: true, import_event_no: 'EVT-RUNTIME-READ-ONLY',
  synthetic_approvals: true, approval_routes: recordedRoles, items};

async function main() {
  assert.ok(existsSync('.next/BUILD_ID'), 'Build the actual Next production app first: npm run build');
  const requests = [], violations = [], observations = [];
  let mode = 'ready';
  const api = http.createServer((req, res) => {
    requests.push({method: req.method, url: req.url});
    if (req.method !== 'GET' || req.url !== '/api/v1/demo/zfi-import'
      || req.headers.authorization || req.headers.cookie) {
      violations.push({method: req.method, url: req.url});
      res.writeHead(400); res.end(); return;
    }
    if (mode === 'error') {
      res.writeHead(503, {'content-type': 'text/plain'});
      res.end('LOCAL_PRIVATE_STAGE_UPSTREAM_ERROR');
      return;
    }
    res.writeHead(200, {'content-type': 'application/json'});
    res.end(JSON.stringify(receipt));
  });
  let child, logs = '';
  try {
    const apiPort = await listen(api), appPort = await unusedPort();
    const base = `http://127.0.0.1:${appPort}`;
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

    async function read(path, locale, expectedMode = 'ready') {
      mode = expectedMode;
      const before = requests.length;
      const response = await fetch(base + path, {headers: {Cookie: `slc_language=${locale}`,
        'User-Agent': 'Local-ZFI-stage-runtime-verification'}, signal: AbortSignal.timeout(10000)});
      // React inserts hydration comments between adjacent text nodes. They are not user-visible.
      const html = (await response.text()).replace(/<!--[\s\S]*?-->/g, '');
      assert.equal(response.status, 200);
      assert.ok(response.headers.get('cache-control')?.includes('no-store'));
      assert.ok(html.includes(`lang="${locale === 'zh' ? 'zh-CN' : 'en'}"`));
      assert.equal(requests.length - before, 1, 'Each production page read must make exactly one API GET');
      assert.ok(!html.includes('LOCAL_PRIVATE_'), 'Upstream error bodies must not leak');
      observations.push({path, locale, mode: expectedMode});
      return html;
    }

    for (const locale of ['zh', 'en']) {
      for (let stage = 1; stage <= 4; stage++) {
        const html = await read(`/demo/zfi?stage=${stage}`, locale);
        assert.ok(html.includes(`${translations[locale].matched}: 2`));
        assert.ok(html.includes(translations[locale].disclaimer));
        assert.ok(html.includes(`SSR-runtime-stage-${stage}`));
        assert.ok(html.includes(`ASR-runtime-stage-${stage}`));
        assert.ok(html.includes(`${translations[locale].current}: ${stage}`));
        for (const type of ['STANDARD', 'APPLICATION']) {
          const role = locale === 'zh' ? recordedRoles[type][stage - 1] : expectedRoles[type][stage - 1];
          assert.ok(html.includes(role.replaceAll('&', '&amp;')), `${locale} ${type} stage ${stage} role`);
        }
        for (const other of [1, 2, 3, 4].filter(value => value !== stage)) {
          assert.ok(!html.includes(`SSR-runtime-stage-${other}`));
          assert.ok(!html.includes(`ASR-runtime-stage-${other}`));
        }
        assert.ok(!html.includes('method="post"') && !html.includes('/api/commands'));
      }

      const combined = await read('/demo/zfi?stage=2&type=APPLICATION&customer=KUBO&status=PENDING&q=runtime%20target', locale);
      assert.ok(combined.includes(`${translations[locale].matched}: 1`));
      assert.ok(combined.includes('ASR-runtime-stage-2'));
      assert.ok(!combined.includes('SSR-runtime-stage-2') && !combined.includes('ASR-runtime-stage-1'));

      const duplicate = await read('/demo/zfi?stage=1&stage=2&type=APPLICATION&customer=KUBO&status=PENDING&q=runtime%20target', locale);
      assert.ok(duplicate.includes(translations[locale].invalid));
      assert.ok(duplicate.includes(`${translations[locale].matched}: 5`));
      assert.ok(!duplicate.match(/<input[^>]*name="stage"/));
      for (let stage = 1; stage <= 4; stage++) assert.ok(duplicate.includes(`ASR-runtime-stage-${stage}`));
      assert.ok(duplicate.includes('ASR-runtime-unknown'));
    }

    for (const locale of ['zh', 'en']) {
      const unavailable = await read('/demo/zfi?stage=3', locale, 'error');
      assert.ok(unavailable.includes(translations[locale].unavailable));
      assert.ok(!unavailable.includes(`${translations[locale].matched}:`));
      assert.ok(!unavailable.includes('SSR-runtime-stage-3') && !unavailable.includes('ASR-runtime-stage-3'));
      const recovered = await read('/demo/zfi?stage=3', locale, 'ready');
      assert.ok(recovered.includes(`${translations[locale].matched}: 2`));
      assert.ok(recovered.includes('SSR-runtime-stage-3') && recovered.includes('ASR-runtime-stage-3'));
    }

    assert.deepEqual(violations, [], 'Only the expected loopback GET without identity headers is allowed');
    assert.ok(requests.every(request => request.method === 'GET'));
    console.log(`PASS: ${observations.length} production route observations; ${requests.length} loopback API GETs`);
    console.log('Local controlled HTTP/SSR verification only; not browser, Cloudflare, Render, authority, Snapshot-binding or formal-release acceptance.');
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
