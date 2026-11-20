'use strict';
const fs = require('node:fs');
const path = require('node:path');
const REQUIRED_TITLES=Object.freeze(['browser selected binary reaches closed temporary file through actual relay','lost response refresh recovers original disk receipt without another write','default disabled picker has no file control or relay calls','lower trusted admission rejects selected bytes before reservation']);
const REQUIRED_FILES=Object.freeze(Object.fromEntries(REQUIRED_TITLES.map(t=>[t,'private-upload.spec.ts'])));
const MAX_REPORT_BYTES = 5 * 1024 * 1024;
const FAILURE = 'Upload browser report is missing, invalid or incomplete.';
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
        for (const [type, description] of [['browser-engine', 'chromium'], ['browser-worker-index', String(result.workerIndex)], ['evidence-layer', 'browser-real-relay-test-api-disk-not-production']]) {
          const observed = result.annotations.filter(a => object(a) && a.type === type);
          requireValue(observed.length === 1 && observed[0].description === description);
        }
        const evidence=result.annotations.filter(a=>object(a)&&a.type==='upload-storage-evidence');
        requireValue(evidence.length===1&&typeof evidence[0].description==='string'&&evidence[0].description.length<4096);
        const e=JSON.parse(evidence[0].description),index=REQUIRED_TITLES.indexOf(spec.title),write=index<2;
        requireValue(object(e)&&Object.keys(e).sort().join(',')==='cleanup,counts,disk,queries,relay,violations');
        requireValue(JSON.stringify(e.violations)==='[]'&&object(e.cleanup)&&e.cleanup.cleaned===true&&e.cleanup.listener_closed===true&&e.cleanup.pending===0);
        const counts=write?{reserve:1,put:1,writes:1,receipts:index===1?3:2}:{reserve:0,put:0,writes:0,receipts:0};
        requireValue(e.queries?.identity===(index===0?4:index===1?5:index===3?1:0)&&e.queries?.context===(write?3:index===2?0:1));
        const relay={context:index===2?0:1,reserve:write?1:0,content:write?1:0,receipt:index===1?1:0};
        for(const [key,value]of Object.entries(counts))requireValue(e.counts?.[key]===value);
        for(const [key,value]of Object.entries(relay))requireValue(e.relay?.[key]===value);
        if(write){const expected=require('node:crypto').createHash('sha256').update(Buffer.from(Array.from({length:65539},(_,i)=>i%256))).digest('hex');requireValue(object(e.disk)&&/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(e.disk.request_id)&&e.disk.component_id==='52345678-1234-4234-8234-123456789abc'&&e.disk.bytes===65539&&e.disk.sha256===expected&&e.disk.closed_before_read===true)}else requireValue(e.disk===null);
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
    readBrowserReport(process.argv[2] || path.resolve(__dirname, '../browser-results/upload/results.json'));
    console.log(`Upload browser evidence: ${REQUIRED_TITLES.length} synthetic journeys passed; zero skips, failures or retries. Test API disk only; not real identity or production storage acceptance.`);
  } catch {
    console.error(FAILURE);
    process.exitCode = 1;
  }
}
module.exports = { validateBrowserReport, readBrowserReport, REQUIRED_TITLES, REQUIRED_FILES, MAX_REPORT_BYTES };
