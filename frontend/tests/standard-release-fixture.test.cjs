'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { EventEmitter } = require('node:events');
const { REQUIRED_TITLES, REQUIRED_FILES } = require('../scripts/check-browser-report.cjs');
test('standard release requires exactly four additional mandatory browser journeys', () => {
 assert.equal(REQUIRED_TITLES.length, 16);
 for (const title of REQUIRED_TITLES.slice(12)) assert.equal(REQUIRED_FILES[title], 'standard-release.spec.ts');
});
function harness() {
 const source = fs.readFileSync(require.resolve('../e2e/standard-release-fixture.cjs'), 'utf8');
 let handler, server;
 const http = { createServer(fn) { handler=fn; server=new EventEmitter(); server.listen=()=>queueMicrotask(()=>server.emit('listening')); server.address=()=>({port:12345}); server.close=()=>queueMicrotask(()=>server.emit('close')); server.closeAllConnections=()=>{}; return server; } };
 const sandbox={require:n=>n==='node:http'?http:require(n),module:{exports:{}},Buffer,URL,URLSearchParams,setTimeout,clearTimeout}; vm.runInNewContext(source,sandbox);
 function read(url, overrides={}) {
  const response=new EventEmitter(); Object.assign(response,{headersSent:false,destroyed:false,writableEnded:false,body:'',writeHead(status){this.status=status;this.headersSent=true;},flushHeaders(){},write(s){this.body+=s;},end(s=''){this.body+=s;this.writableEnded=true;this.emit('finish');this.emit('close');},destroy(){this.destroyed=true;this.emit('close');}});
  handler({url,method:'GET',headers:{},...overrides},response); return response;
 }
 return {api:sandbox.module.exports,read};
}
for (const stage of ['parent','batch']) for (const phase of ['headers','body']) test(stage+' '+phase+' mock fixture holds and only explicit release completes old data',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture(stage,phase),p=h.api.paths;
 try {
  const old=h.read(stage==='parent'?p.api:p.batchApi); assert.equal(f.pendingCount,1); assert.equal(old.headersSent,phase==='body');
  f.recover(); assert.equal(old.writableEnded,false); const fresh=h.read(stage==='parent'?p.api:p.batchApi); assert.equal(fresh.status,200); JSON.parse(fresh.body);
  const ids=f.releaseHeld(); assert.equal(ids.length,1); assert.ok(old.body.includes(h.api.lateMarker)); JSON.parse(old.body); assert.equal(f.pendingCount,0);
  assert.ok(f.requests[0].finishedAt>=f.requests[0].receivedAt); assert.equal(f.requests[1].phase,'ready');
 }finally{await f.close();}
});
test('mock fixture rejects credentials mutations and every unknown endpoint or query',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture('parent','headers');
 try{for(const [url,options] of [[h.api.paths.api,{method:'POST'}],[h.api.paths.api,{headers:{authorization:'PRIVATE'}}],[h.api.paths.api,{headers:{cookie:''}}],[h.api.paths.api+'&other=PRIVATE',{}],['/api/v1/dashboard/summary',{}],['/auth/session',{}],[h.api.paths.api,{headers:{'content-length':'1'}}]]) assert.equal(h.read(url,options).status,400);
 assert.equal(f.violations.length,7); assert.ok(!JSON.stringify(f.requests).includes('PRIVATE'));}finally{await f.close();}
});
const {allowedPath}=require('../e2e/streaming-proxy.cjs');
const standard=require('../e2e/standard-release-fixture.cjs');
test('standard proxy opt-in is finite and does not broaden the API or other query scopes',()=>{
 const options={standardReleaseQuery:standard.query+standard.childQuery};
 for(const p of standard.browserPaths){assert.equal(allowedPath(p),false);assert.equal(allowedPath(p,options),true);assert.equal(allowedPath(p+(p.includes('?')?'&':'?')+'_rsc=opaque_1',options),true);}
 for(const p of [standard.paths.api,standard.paths.batchApi,standard.paths.page+'&q=x',standard.paths.page+'&_rsc=a&_rsc=b','/releases/application','/projects?q=x','/releases/standard?token=PRIVATE'])assert.equal(allowedPath(p,options),false);
 for(const options of [{standardReleaseQuery:'x'},{standardReleaseQuery:standard.query+standard.childQuery,extra:1}])assert.throws(()=>allowedPath('/',options));
});
for(const stage of ['parent','batch'])test(stage+' cancellation is not recorded as a completed stale response',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture(stage,'body');
 try{const res=h.read(stage==='parent'?h.api.paths.api:h.api.paths.batchApi);res.destroy();assert.equal(f.requests[0].finishedAt,null);assert.ok(Number.isFinite(f.requests[0].closedAt));assert.equal(f.releaseHeld().length,0);assert.equal(f.pendingCount,0);}finally{await f.close();}
});
for(const stage of ['parent','batch'])test(stage+' finite healthy payloads keep reversed ID associations and empty-parent shape',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture(stage,'headers');f.recover();
 try {const parents=JSON.parse(h.read(h.api.paths.api).body),batch=JSON.parse(h.read(h.api.paths.batchApi).body);assert.equal(parents.items[0].id,batch.items[1].release_id);assert.equal(batch.items[1].items.length,2);assert.equal(batch.items[0].items.length,1);assert.equal(JSON.parse(h.read(h.api.paths.resetApi).body).items.length,0);}finally{await f.close();}
});

function browserRequest(url, overrides = {}) {
  return { url: () => url, method: () => 'GET', isNavigationRequest: () => false,
    resourceType: () => 'fetch', headers: () => ({ rsc: '1' }), failure: () => ({ errorText: 'net::ERR_ABORTED' }), ...overrides };
}
for (const kind of ['standard']) test(kind + ' RSC observer tracks exact non-document request identities through terminal events', () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345';
  const observer = standard.observeStandardRsc(page, origin);
  try {
    for (const request of [
      browserRequest(origin + standard.paths.firstPage), browserRequest('http://127.0.0.1:23456' + standard.paths.page),
      browserRequest(origin + standard.paths.page + '&other=1'), browserRequest(origin + standard.paths.page, { method: () => 'POST' }),
      browserRequest(origin + standard.paths.page, { isNavigationRequest: () => true }),
      browserRequest(origin + standard.paths.page, { resourceType: () => 'document' }),
      browserRequest(origin + standard.paths.page, { headers: () => ({}) }),
    ]) page.emit('request', request);
    assert.deepEqual(observer.requests, []);
    const live = browserRequest(origin + standard.paths.nextPage + '&_rsc=fixture'), cancelled = browserRequest(origin + standard.paths.page);
    page.emit('request', live); page.emit('request', cancelled);
    assert.deepEqual(observer.requests.map(r => r.outcome), ['pending', 'pending']);
    page.emit('requestfinished', browserRequest(live.url())); // Same URL is not the same Request.
    assert.equal(observer.requests[0].outcome, 'pending');
    page.emit('response', { request: () => live, status: () => 200 });
    page.emit('requestfinished', live); page.emit('requestfailed', cancelled);
    assert.deepEqual(observer.requests.map(r => [r.outcome, r.status, r.failure]), [['finished', 200, null], ['failed', null, 'net::ERR_ABORTED']]);
    assert.ok(observer.requests.every(r => r.endedAt >= r.receivedAt));
    assert.ok(Object.isFrozen(observer.requests)); assert.ok(Object.isFrozen(observer.requests[0]));
    const count = observer.requests.length; observer.stop(); observer.stop(); page.emit('request', browserRequest(origin + standard.paths.page));
    assert.equal(observer.requests.length, count);
    for (const name of ['request', 'response', 'requestfinished', 'requestfailed']) assert.equal(page.listenerCount(name), 0);
  } finally { observer.stop(); }
});
function completion() {
  return { backendReads: [{ id: 2, receivedAt: 1, closedAt: 5, finishedAt: 4 }], releasedIds: [2], releasedAt: 3,
    liveAtDestinationIds: [0], browserReads: [{ id: 0, outcome: 'finished', status: 200, failure: null, receivedAt: 1, endedAt: 6, prefetch: false, bodyInspected: true, bodyBytes: 100, containsLateMarker: true }] };
}
test('completion evidence distinguishes real late completion, cancellation, and mixed outcomes', () => {
  assert.equal(standard.summarizeCatalogCompletion(completion()).outcome, 'late-data-completed');
  const cancelled = completion(); cancelled.releasedIds = []; cancelled.releasedAt = null; cancelled.liveAtDestinationIds = [];
  cancelled.backendReads[0].finishedAt = null; cancelled.browserReads[0] = { ...cancelled.browserReads[0], outcome: 'failed', failure: 'net::ERR_ABORTED' };
  assert.equal(standard.summarizeCatalogCompletion(cancelled).outcome, 'cancelled');
  const mixed = completion(); mixed.browserReads.push({ ...mixed.browserReads[0], id: 1, outcome: 'failed', failure: 'net::ERR_ABORTED' });
  assert.equal(standard.summarizeCatalogCompletion(mixed).outcome, 'mixed');
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
]) test('completion evidence rejects ' + name, () => { const value = completion(); change(value); assert.throws(() => standard.summarizeCatalogCompletion(value), /incomplete_catalog_completion/); });

for (const kind of ['standard']) test(kind + ' shell-only prefetch plus cancelled data cannot claim late-data completion', async () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = standard.observeStandardRsc(page, origin);
  let shellReads = 0, cancelledReads = 0;
  try {
    const shell = browserRequest(origin + standard.paths.nextPage + '&_rsc=shell', { headers: () => ({ rsc: '1', 'next-router-prefetch': '1' }) });
    const data = browserRequest(origin + standard.paths.nextPage + '&_rsc=data');
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
    const result = standard.summarizeCatalogCompletion({ backendReads: [{ id: 2, receivedAt: releasedAt - 1, finishedAt: releasedAt, closedAt: releasedAt }],
      releasedIds: [2], releasedAt, liveAtDestinationIds: [0, 1], browserReads: rows });
    assert.equal(result.outcome, 'cancelled-with-shell-completion');
    assert.equal(result.completedLateDataResponses, 0); assert.equal(result.completedShellResponses, 1); assert.equal(result.cancelledBrowserRequests, 1);
    assert.ok(!JSON.stringify(rows).includes('PRIVATE_BODY'));
    await observer.inspectCompletedBodies([0, 1]); assert.equal(shellReads, 1, 'do not reread completed bytes');
  } finally { observer.stop(); }
});
for (const kind of ['standard']) test(kind + ' completed marker body is the only late-data proof and raw bytes are not retained', async () => {
  const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = standard.observeStandardRsc(page, origin);
  try {
    const request = browserRequest(origin + standard.paths.nextPage + '&_rsc=data'); page.emit('request', request);
    const releasedAt = performance.now(), bytes = Buffer.from('PRIVATE_BODY ' + standard.lateMarker);
    page.emit('response', { request: () => request, status: () => 200, body: async () => bytes });
    page.emit('requestfinished', request); await observer.inspectCompletedBodies([0]);
    assert.equal(observer.requests[0].containsLateMarker, true); assert.equal(observer.requests[0].bodyBytes, bytes.length);
    assert.ok(!JSON.stringify(observer.requests).includes('PRIVATE_BODY'));
    assert.equal(standard.summarizeCatalogCompletion({ backendReads: [{ id: 2, receivedAt: releasedAt - 1, finishedAt: releasedAt, closedAt: releasedAt }],
      releasedIds: [2], releasedAt, liveAtDestinationIds: [0], browserReads: observer.requests }).outcome, 'late-data-completed');
  } finally { observer.stop(); }
});
test('completed-body inspection fails closed for missing response, oversized bytes and untracked IDs', async () => {
  assert.equal(standard.MAX_RSC_BODY_BYTES, 256 * 1024);
  for (const mode of ['missing', 'oversized', 'failure', 'pending', 'unknown', 'empty', 'duplicate']) {
    const page = new EventEmitter(), origin = 'http://127.0.0.1:12345', observer = standard.observeStandardRsc(page, origin);
    try {
      const request = browserRequest(origin + standard.paths.nextPage); page.emit('request', request);
      if (mode !== 'missing') page.emit('response', { request: () => request, status: () => 200, body: async () => {
        if (mode === 'failure') throw Error('PRIVATE_BODY_ERROR');
        return Buffer.alloc(standard.MAX_RSC_BODY_BYTES + 1, 120);
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
  assert.throws(() => standard.summarizeCatalogCompletion(shell), /incomplete_catalog_completion/);
  const missing = completion(); missing.browserReads[0].bodyInspected = false;
  assert.throws(() => standard.summarizeCatalogCompletion(missing), /incomplete_catalog_completion/);
});
test('invalid fixture dimensions fail before any server construction',async()=>{
 for(const stage of [undefined,null,'standard','__proto__'])await assert.rejects(standard.startStandardReleaseFixture(stage,'headers'),/invalid_standard_fixture_stage/);
 for(const phase of [undefined,null,'ready','HEADER'])await assert.rejects(standard.startStandardReleaseFixture('parent',phase),/invalid_standard_fixture_phase/);
});
test('mock fixture close aborts pending reads and cannot be reopened',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture('batch','body');h.read(h.api.paths.batchApi);
 await f.close();await f.close();assert.equal(f.pendingCount,0);assert.equal(f.requests[0].finishedAt,null);
 for(const action of ['recover','hold','releaseHeld'])assert.throws(()=>f[action](),/standard_fixture_closed/);
});
for(const [name,offset] of [['first',0],['last',10]])test('pagination contract '+name+' parent matches actual count and next offset',()=>{
 const p=standard.catalog(offset);assert.equal(p.total,12);assert.equal(p.limit,10);assert.equal(p.offset,offset);
 assert.equal(p.items.length,Math.min(p.limit,Math.max(0,p.total-p.offset)));
 assert.equal(p.next_offset,p.offset+p.limit<p.total?p.offset+p.limit:null);
});
test('pagination contract pages partition all twelve parents without overlap',()=>{
 const first=standard.catalog(0),last=standard.catalog(10),ids=[...first.items,...last.items].map(r=>r.id);
 assert.equal(first.next_offset,last.offset);assert.equal(new Set(ids).size,12);assert.equal(ids.length,12);
 assert.ok(!first.items.some(r=>r.id===standard.releaseId));assert.equal(last.items[0].id,standard.releaseId);
});
for(const offset of [0,10])test('pagination contract batch maps exactly the corresponding parent page '+offset,()=>{
 const parent=standard.catalog(offset),batch=standard.batch(offset,10);
 assert.equal(batch.limit,parent.limit);assert.equal(batch.offset,parent.offset);
 assert.equal(parent.items.length,offset===0?10:2);
 assert.deepEqual(batch.items.map(r=>r.release_id).sort(),parent.items.map(r=>r.id).sort());
 assert.equal(new Set(batch.items.map(r=>r.release_id)).size,parent.items.length);
 for(const row of batch.items){assert.equal(row.limit,10);assert.equal(row.offset,row.release_id===standard.releaseId?10:0);assert.equal(row.items.length,Math.min(row.limit,Math.max(0,row.total-row.offset)));assert.equal(row.next_offset,row.offset+row.limit<row.total?row.offset+row.limit:null);}
});
test('pagination contract selected child pages partition twelve versions and retain parent offset',()=>{
 const batches=[standard.batch(10,0),standard.batch(10,10)];
 const pages=batches.map(b=>b.items.find(r=>r.release_id===standard.releaseId));
 assert.ok(batches.every(b=>b.offset===10));assert.equal(pages[0].next_offset,pages[1].offset);
 assert.equal(pages[0].items.length,10);assert.equal(pages[1].items.length,2);assert.equal(pages[1].next_offset,null);
 const ids=pages.flatMap(p=>p.items.map(r=>r.id));assert.equal(ids.length,12);assert.equal(new Set(ids).size,12);
});
test('pagination contract finite mock routes serve matching first and last parent/batch pages',async()=>{
 const h=harness(),f=await h.api.startStandardReleaseFixture('parent','headers');f.recover();
 try{
  assert.equal(new URLSearchParams(h.api.query).get('offset'),'10');
  for(const [parentPath,batchPath,offset,count]of [[h.api.paths.firstApi,h.api.paths.firstBatchApi,0,10],[h.api.paths.api,h.api.paths.batchApi,10,2],[h.api.paths.api,h.api.paths.nextBatchApi,10,2],[h.api.paths.api,h.api.paths.childFirstApi,10,2]]){
   const parent=JSON.parse(h.read(parentPath).body),batch=JSON.parse(h.read(batchPath).body);
   assert.equal(parent.offset,offset);assert.equal(parent.items.length,count);assert.equal(batch.offset,offset);
   assert.deepEqual(batch.items.map(r=>r.release_id).sort(),parent.items.map(r=>r.id).sort());
  }
  const obsolete=h.api.paths.api.replace('offset=10','offset=20');assert.equal(h.read(obsolete).status,400);
 }finally{await f.close();}
});
test('pagination contract late marker preserves last-page IDs and valid counts',async()=>{
 for(const stage of ['parent','batch']){
  const h=harness(),f=await h.api.startStandardReleaseFixture(stage,'body');
  try{const res=h.read(stage==='parent'?h.api.paths.api:h.api.paths.batchApi);f.releaseHeld();const data=JSON.parse(res.body);
   assert.equal(data.offset,10);assert.equal(data.limit,10);assert.equal(data.items.length,2);
   if(stage==='parent'){assert.equal(data.total,12);assert.equal(data.next_offset,null);assert.deepEqual(data.items.map(r=>r.id),[h.api.releaseId,h.api.secondId]);}
   else assert.deepEqual(data.items.map(r=>r.release_id),[h.api.secondId,h.api.releaseId]);
  }finally{await f.close();}
 }
});

// Exercise the actual browser assertion without opening a browser. This model
// encodes native details visibility, not a replacement for real-browser CI.
function pendingAssertion() {
 const ts=require('typescript');
 const source=fs.readFileSync(require.resolve('../e2e/standard-release.spec.ts'),'utf8');
 const ast=ts.createSourceFile('standard-release.spec.ts',source,ts.ScriptTarget.Latest,true);
 const fn=ast.statements.find(node=>ts.isFunctionDeclaration(node)&&node.name?.text==='assertPendingApplications');
 assert.ok(fn,'Browser journey must distinguish pending DOM from visible status');
 const code=ts.transpile(fn.getText(ast)+'\nmodule.exports=assertPendingApplications;', {target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS});
 const sandbox={module:{exports:{}},expect:locator=>({
  async toHaveCount(count){assert.equal(locator.count,count);},
  async toHaveJSProperty(name,value){assert.equal(locator.row[name],value);},
  async toBeVisible(){assert.equal(locator.count,1);assert.equal(locator.visible,true);},
 })};
 vm.runInNewContext(code,sandbox);return sandbox.module.exports;
}
function disclosureContent(selectedId,change=()=>{}) {
 const rows=[standard.releaseId,standard.secondId].map(id=>({id:'standard-software-'+id,open:id===selectedId,pending:1,status:1}));change(rows);
 const status=(items,options)=>({count:items.reduce((n,row)=>n+(options?.includeHidden||row.open?row.status:0),0),visible:items.some(row=>row.open&&row.status===1)});
 return {locator(selector){
  assert.equal(selector,'.standard-software-card');return {count:rows.length,nth(index){const row=rows[index];return {row,
   async getAttribute(name){assert.equal(name,'id');return row.id;},
   locator(selector){assert.equal(selector,'[data-standard-application-state="pending"]');return {count:row.pending};},
   getByRole(role,options){assert.equal(role,'status');return status([row],options);},
  };}};
 },getByRole(role,options){assert.equal(role,'status');return status(rows,options);}};
}
test('pending browser assertion counts two DOM states but only selected disclosure is visible',async()=>{
 await pendingAssertion()(disclosureContent(standard.releaseId),standard.releaseId);
});
test('pending browser assertion keeps both unselected disclosures closed during new navigation',async()=>{
 await pendingAssertion()(disclosureContent(null),null);
});
for(const [name,change]of [
 ['missing hidden pending state',rows=>{rows[1].pending=0;}],
 ['duplicate hidden pending state',rows=>{rows[1].pending=2;}],
 ['missing hidden status',rows=>{rows[1].status=0;}],
 ['unexpected open disclosure',rows=>{rows[1].open=true;}],
 ['selected disclosure closed',rows=>{rows[0].open=false;}],
 ['extra parent row',rows=>{rows.push({...rows[1]});}],
])test('pending browser assertion rejects '+name,async()=>{
 const check=pendingAssertion();await assert.rejects(check(disclosureContent(standard.releaseId,change),standard.releaseId),{name:'AssertionError'});
});
