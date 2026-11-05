'use strict';
const fs = require('node:fs');
const path = require('node:path');
const REQUIRED_TITLES = Object.freeze(["synthetic creator denial never exposes an approval command or sends approval", "private synthetic scope is explicit and confirmation freezes the exact command", "duplicate clicks submit once and a valid synthetic reply confirms without automatic recovery", "synthetic historical receipt is bilingual and raw reason is never HTML", "disabled and readonly capabilities never send approval while explicit recovery only queries", "unknown approval survives same-origin reload only through manual audit-only import and exact query", "fresh manual recovery rejects a foreign-origin envelope without any API request", "fresh manual recovery rejects a valid wrong-target envelope without any API request", "synthetic context session unavailable fails closed without approval or receipt requests", "synthetic context permission denied fails closed without approval or receipt requests", "synthetic context target unavailable fails closed without approval or receipt requests", "synthetic permission loss after review rejects once and preserves the frozen command", "imported synthetic recovery session unavailable preserves unknown audit-only state", "imported synthetic original receipt unavailable preserves unknown audit-only state"]);
const REQUIRED_FILES = Object.freeze(Object.fromEntries(REQUIRED_TITLES.map(title => [title, "authorization-approval.spec.ts"])));
const MAX_REPORT_BYTES = 5 * 1024 * 1024;
const FAILURE = 'Component browser report is missing, invalid or incomplete.';
function requireValue(condition) { if (!condition) throw new Error(FAILURE); }
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function timestamp(value) { return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value) && Number.isFinite(Date.parse(value)); }
function validateBrowserReport(report) {
  requireValue(object(report) && object(report.config) && object(report.stats));
  requireValue(Array.isArray(report.errors) && report.errors.length === 0);
  const { stats, config } = report;
  requireValue(stats.expected === REQUIRED_TITLES.length && stats.unexpected === 0 && stats.flaky === 0 && stats.skipped === 0);
  requireValue(timestamp(stats.startTime) && Number.isFinite(stats.duration) && stats.duration > 0);
  requireValue(config.forbidOnly === true && Array.isArray(config.projects) && config.projects.length === 1);
  requireValue(config.shard == null && (!Array.isArray(config.argv) || !config.argv.includes('--list')));
  const project = config.projects[0];
  requireValue(object(project) && project.id === 'chromium' && project.name === 'chromium' && project.retries === 0 && project.repeatEach === 1);
  const found = new Set(); let visited = 0;
  function suites(rows, depth) {
    requireValue(Array.isArray(rows) && depth <= 20);
    for (const suite of rows) {
      requireValue(++visited <= 100 && object(suite) && Array.isArray(suite.specs));
      for (const spec of suite.specs) {
        requireValue(object(spec) && REQUIRED_TITLES.includes(spec.title) && !found.has(spec.title));
        requireValue(spec.file === REQUIRED_FILES[spec.title] && spec.ok === true && Array.isArray(spec.tests) && spec.tests.length === 1);
        found.add(spec.title);
        const test = spec.tests[0];
        requireValue(object(test) && test.projectId === 'chromium' && test.projectName === 'chromium');
        requireValue(test.expectedStatus === 'passed' && test.status === 'expected' && Array.isArray(test.results) && test.results.length === 1);
        const result = test.results[0];
        requireValue(object(result) && result.status === 'passed' && result.retry === 0);
        requireValue(Number.isInteger(result.workerIndex) && result.workerIndex >= 0 && Number.isInteger(result.parallelIndex) && result.parallelIndex >= 0);
        requireValue(timestamp(result.startTime) && Number.isFinite(result.duration) && result.duration > 0);
        requireValue(result.error == null && Array.isArray(result.errors) && result.errors.length === 0);
        requireValue(Array.isArray(result.annotations));
        for (const [type, description] of [['browser-engine', 'chromium'], ['synthetic-component-fixture', 'verified'], ['browser-worker-index', String(result.workerIndex)], ['evidence-layer', 'component-only-not-authentication']]) {
          const observed = result.annotations.filter(a => object(a) && a.type === type);
          requireValue(observed.length === 1 && observed[0].description === description);
        }
      }
      if (suite.suites !== undefined) suites(suite.suites, depth + 1);
    }
  }
  suites(report.suites, 0);
  requireValue(found.size === REQUIRED_TITLES.length);
  return { tests: REQUIRED_TITLES.length, passed: REQUIRED_TITLES.length, skipped: 0, retried: 0, project: 'chromium' };
}
function readBrowserReport(filename) {
  const fd = fs.openSync(filename, 'r');
  try {
    const stat = fs.fstatSync(fd);
    requireValue(stat.isFile() && stat.size > 0 && stat.size <= MAX_REPORT_BYTES);
    const bytes = Buffer.alloc(MAX_REPORT_BYTES + 1); let size = 0;
    while (size < bytes.length) {
      const read = fs.readSync(fd, bytes, size, bytes.length - size, null);
      if (!read) break;
      size += read;
    }
    requireValue(size > 0 && size <= MAX_REPORT_BYTES);
    return validateBrowserReport(JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, size))));
  } finally { fs.closeSync(fd); }
}
if (require.main === module) {
  try {
    requireValue(process.argv.length <= 3);
    readBrowserReport(process.argv[2] || path.resolve(__dirname, '../component-browser-results/results.json'));
    console.log(`Component browser evidence: ${REQUIRED_TITLES.length} synthetic journeys passed; zero skips, failures or retries. Not authentication acceptance.`);
  } catch {
    console.error(FAILURE);
    process.exitCode = 1;
  }
}
module.exports = { validateBrowserReport, readBrowserReport, REQUIRED_TITLES, REQUIRED_FILES, MAX_REPORT_BYTES };
