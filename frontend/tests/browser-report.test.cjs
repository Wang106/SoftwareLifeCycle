'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { validateBrowserReport, readBrowserReport, REQUIRED_TITLES, REQUIRED_FILES, MAX_REPORT_BYTES } = require('../scripts/check-browser-report.cjs');
const cli = path.resolve(__dirname, '../scripts/check-browser-report.cjs');
function fixture() {
  return { config: { forbidOnly: true, projects: [{ id: 'chromium', name: 'chromium', retries: 0, repeatEach: 1 }] },
    errors: [], stats: { expected: 6, unexpected: 0, flaky: 0, skipped: 0, startTime: '2026-10-28T00:00:00.000Z', duration: 1000 },
    suites: [{ title: 'readonly.spec.ts', specs: REQUIRED_TITLES.map(title => ({ title, file: REQUIRED_FILES[title], ok: true,
      tests: [{ projectId: 'chromium', projectName: 'chromium', expectedStatus: 'passed', status: 'expected', results: [{
        status: 'passed', retry: 0, workerIndex: 0, parallelIndex: 0, startTime: '2026-10-28T00:00:00.000Z', duration: 100, errors: [], annotations: [{ type: 'browser-engine', description: 'chromium' },
          { type: 'synthetic-loopback-fixture', description: 'verified' }, { type: 'browser-worker-index', description: '0' }],
      }] }],
    })) }] };
}
function first(report) { return report.suites[0].specs[0].tests[0]; }
test('synthetic complete JSON validates all six exact journeys, including nested suites', () => {
  const value = fixture(); const specs = value.suites[0].specs; value.suites[0].specs = [];
  value.suites[0].suites = [{ specs }];
  assert.deepEqual(validateBrowserReport(value), { tests: 6, passed: 6, skipped: 0, retried: 0, project: 'chromium' });
});
for (const [name, change] of [
  ['empty suites', r => { r.suites = []; }], ['missing journey', r => r.suites[0].specs.pop()],
  ['duplicate title', r => { r.suites[0].specs[1].title = REQUIRED_TITLES[0]; }],
  ['unexpected journey', r => { r.suites[0].specs[1].title = 'some other test'; }],
  ['wrong source', r => { r.suites[0].specs[0].file = 'fake.spec.ts'; }],
  ['wrong stats', r => { r.stats.expected = 1; }], ['skipped stats', r => { r.stats.skipped = 1; }],
  ['flaky stats', r => { r.stats.flaky = 1; }], ['failure stats', r => { r.stats.unexpected = 1; }],
  ['report error', r => { r.errors.push({ message: 'private error' }); }],
  ['not ok spec', r => { r.suites[0].specs[0].ok = false; }],
  ['expected failure', r => { first(r).expectedStatus = 'failed'; }],
  ['flaky test', r => { first(r).status = 'flaky'; }], ['skipped test', r => { first(r).status = 'skipped'; }],
  ['unexecuted test', r => { first(r).results = []; }],
  ['retry attempt', r => { first(r).results[0].retry = 1; }],
  ['multiple attempts', r => { first(r).results.push({ ...first(r).results[0] }); }],
  ['failed result', r => { first(r).results[0].status = 'failed'; }],
  ['interrupted result', r => { first(r).results[0].status = 'interrupted'; }],
  ['skipped result', r => { first(r).results[0].status = 'skipped'; }],
  ['error result', r => { first(r).results[0].error = { message: 'private error' }; }],
  ['errors result', r => { first(r).results[0].errors = [{}]; }],
  ['missing worker', r => { first(r).results[0].workerIndex = -1; }],
  ['missing duration', r => { delete first(r).results[0].duration; }],
  ['missing start', r => { first(r).results[0].startTime = 'unknown'; }],
  ['missing runtime browser annotation', r => { first(r).results[0].annotations = []; }],
  ['wrong actual browser', r => { first(r).results[0].annotations[0].description = 'firefox'; }],
  ['unverified fixture', r => { first(r).results[0].annotations[1].description = 'unknown'; }],
  ['wrong runtime worker', r => { first(r).results[0].annotations[2].description = '1'; }],
  ['duplicate runtime browser', r => { first(r).results[0].annotations.push({ type: 'browser-engine', description: 'chromium' }); }],
  ['wrong browser project', r => { first(r).projectName = 'firefox'; }],
  ['unnamed config project', r => { r.config.projects[0].name = ''; }],
  ['multiple projects', r => { r.config.projects.push({ ...r.config.projects[0] }); }],
  ['configured retries', r => { r.config.projects[0].retries = 1; }],
  ['configured repeats', r => { r.config.projects[0].repeatEach = 2; }],
  ['test list only', r => { r.config.argv = ['test', '--list']; }],
  ['focused tests allowed', r => { r.config.forbidOnly = false; }],
  ['sharded subset', r => { r.config.shard = { current: 1, total: 2 }; }],
]) test('rejects '+name, () => { const report = fixture(); change(report); assert.throws(() => validateBrowserReport(report)); });
test('rejects null/malformed roots and excessive suite nesting without accepting empty evidence', () => {
  for (const value of [null, {}, [], { config: null }]) assert.throws(() => validateBrowserReport(value));
  const value = fixture(); let node = value.suites[0];
  for (let i=0; i<22; i++) { node.suites = [{ specs: [] }]; node = node.suites[0]; }
  assert.throws(() => validateBrowserReport(value));
});
test('bounded CLI requires real report file, redacts all malformed content and accepts synthetic complete fixture', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'slc-browser-report-'));
  try {
    const filename = path.join(directory, 'report.json');
    for (const content of ['', '{PRIVATE_SECRET', JSON.stringify({ ...fixture(), errors: [{ message: 'PRIVATE_SECRET' }] }), 'x'.repeat(MAX_REPORT_BYTES+1)]) {
      fs.writeFileSync(filename, content);
      const result = spawnSync(process.execPath, [cli, filename], { encoding: 'utf8' });
      assert.equal(result.status, 1); assert.equal(result.stdout, '');
      assert.equal(result.stderr.trim(), 'Browser acceptance report is missing, invalid or incomplete.');
      assert.ok(!result.stderr.includes('PRIVATE_SECRET') && !result.stderr.includes(directory));
    }
    fs.writeFileSync(filename, JSON.stringify(fixture()));
    assert.equal(readBrowserReport(filename).passed, 6);
    assert.equal(spawnSync(process.execPath, [cli, filename], { encoding: 'utf8' }).status, 0);
    assert.equal(spawnSync(process.execPath, [cli, filename+'-missing'], { encoding: 'utf8' }).status, 1);
    assert.throws(() => readBrowserReport(directory));
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('old two-journey evidence cannot pass expanded loading acceptance', () => { const value = fixture(); value.stats.expected = 2; value.suites[0].specs = value.suites[0].specs.slice(0, 2); assert.throws(() => validateBrowserReport(value)); });
