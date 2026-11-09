 'use strict';
const http = require('node:http');
const { once } = require('node:events');
const { performance } = require('node:perf_hooks');
const releaseId = '11111111-1111-4111-8111-111111111111';
const secondId = '22222222-2222-4222-8222-222222222222';
const query = 'q=A+%26+B&status=RELEASED&software_id=software-one&limit=10&offset=10';
const childQuery = '&applications_for=' + releaseId + '&application_offset=10';
const page = '/releases/standard?';
const api = '/api/v1/release-catalog/standard?';
const batchApi = '/api/v1/release-catalog/standard/applications?';
const paths = Object.freeze({ page: page+query+childQuery, api: api+query, batchApi: batchApi+query+childQuery,
 firstPage: page+query.replace('&offset=10',''), firstApi: api+query.replace('&offset=10',''),
 firstBatchApi: batchApi+query.replace('&offset=10',''),
 nextPage: page+query, nextBatchApi: batchApi+query,
 childFirstPage: page+query+childQuery.replace('application_offset=10','application_offset=0'),
 childFirstApi: batchApi+query+childQuery.replace('application_offset=10','application_offset=0'),
 resetPage: '/releases/standard', resetApi: api });
const browserPaths = Object.freeze([paths.page,paths.firstPage,paths.nextPage,paths.childFirstPage,paths.resetPage]);
const MAX_RSC_BODY_BYTES = 256 * 1024;
const lateMarker = 'SYNTHETIC_LATE_STANDARD_RELEASE_991';
// One fixed filtered dataset, sliced by the same limit/offset contract as the API.
const parentIds = Object.freeze([
 ...Array.from({length:10},(_,index)=>`33333333-3333-4333-8333-${String(index+1).padStart(12,'0')}`),
 releaseId,secondId,
]);
function catalog(offset=10, late=false) {
 const limit=10,total=parentIds.length;
 return {kind:'standard',limit,offset,total,next_offset:offset+limit<total?offset+limit:null,
 items:parentIds.slice(offset,offset+limit).map((id,index)=>({id,version:late?lateMarker:'baseline-'+(offset+index+1),status:'RELEASED',software:{name:'Synthetic software '+(offset+index+1),code:'SW-'+(offset+index)},supplier:{name:'Synthetic supplier',code:'SUP-1'}}))};
}
function batch(offset=10,childOffset=10,late=false) {
 const parent=catalog(offset);
 // Reverse intentionally: the UI must join by ID rather than array position.
 return {limit:parent.limit,offset:parent.offset,items:[...parent.items].reverse().map(({id})=>{
 const start=id===releaseId?childOffset:0,total=id===releaseId?12:1;
 return {release_id:id,limit:10,offset:start,total,next_offset:start+10<total?start+10:null,
 items:Array.from({length:Math.min(10,Math.max(0,total-start))},(_,i)=>({id:id+'-'+(start+i),version:late?lateMarker:'application-'+(start+i+1),status:'RELEASED'}))};})};
}
async function startStandardReleaseFixture(stage, phase) {
 if (!['parent','batch'].includes(stage)) throw Error('invalid_standard_fixture_stage');
 if (!['headers','body'].includes(phase)) throw Error('invalid_standard_fixture_phase');
 const requests=[],violations=[],pending=new Map(),open=new Map();
 const responses=new Map([[paths.api,()=>catalog()],[paths.batchApi,()=>batch()],
 [paths.firstApi,()=>catalog(0)],[paths.firstBatchApi,()=>batch(0,0)],
 [paths.nextBatchApi,()=>batch(10,0)],[paths.childFirstApi,()=>batch(10,0)],
 [paths.resetApi,()=>({kind:'standard',limit:50,offset:0,total:0,next_offset:null,items:[]})],
 [paths.resetApi.slice(0,-1),()=>({kind:'standard',limit:50,offset:0,total:0,next_offset:null,items:[]})],
 ['/api/v1/organization-views/projects?',()=>({kind:'projects',limit:50,offset:0,total:0,next_offset:null,items:[]})],
 ['/api/v1/organization-views/projects',()=>({kind:'projects',limit:50,offset:0,total:0,next_offset:null,items:[]})]]);
 let ready=false,stopped=false,closing;
 function headers(res,entry){entry.status=200;res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});}
 const server=http.createServer((req,res)=>{
 const response=responses.get(req.url),target=stage==='parent'?req.url===paths.api:[paths.batchApi,paths.nextBatchApi].includes(req.url);
 const credentials=['authorization','proxy-authorization','cookie'].some(k=>Object.hasOwn(req.headers,k));
 const body=Object.hasOwn(req.headers,'transfer-encoding')||(Object.hasOwn(req.headers,'content-length')&&req.headers['content-length']!=='0');
 const allowed=req.method==='GET'&&response&&!credentials&&!body;
 const entry={id:requests.length,kind:!allowed?'rejected':target?'target':'ancillary',stage:allowed?(req.url.startsWith(batchApi)?'batch':'parent'):'rejected',method:req.method,url:allowed?req.url:'[rejected]',phase:!allowed?'rejected':target&&!ready?phase:'ready',receivedAt:performance.now(),headersSent:false,closedAt:null,finishedAt:null,status:null}; requests.push(entry);
 let resolveClose;open.set(res,new Promise(resolve=>{resolveClose=resolve;}));
 res.once('finish',()=>{entry.finishedAt=performance.now();});res.once('close',()=>{entry.closedAt=performance.now();pending.delete(res);open.delete(res);resolveClose();});
 if(!allowed){violations.push({reason:'standard_fixture_rejected'});entry.status=400;res.writeHead(400,{'content-type':'application/json'});res.end('{"error":"standard_fixture_rejected"}');entry.headersSent=res.headersSent;return;}
 if(target&&!ready){pending.set(res,entry);if(phase==='body'){headers(res,entry);res.flushHeaders();res.write('{');entry.headersSent=res.headersSent;}return;}
 headers(res,entry);res.end(JSON.stringify(response()));entry.headersSent=res.headersSent;
 });
 server.listen(0,'127.0.0.1');await once(server,'listening');
 function assertOpen(){if(stopped)throw Error('standard_fixture_closed');}
 return {apiOrigin:`http://127.0.0.1:${server.address().port}`,
 get requests(){return Object.freeze(requests.map(e=>Object.freeze({...e})));},get violations(){return Object.freeze(violations.map(e=>Object.freeze({...e})));},get pendingCount(){return pending.size;},
 recover(){assertOpen();ready=true;},hold(){assertOpen();ready=false;},
 releaseHeld(){assertOpen();const ids=[];for(const [res,entry]of pending){if(res.destroyed||res.writableEnded)continue;
 const body=JSON.stringify(stage==='parent'?catalog(10,true):batch(10,entry.url===paths.batchApi?10:0,true));
 if(!res.headersSent)headers(res,entry);ids.push(entry.id);res.end(phase==='body'?body.slice(1):body);entry.headersSent=res.headersSent;}return Object.freeze(ids);},
 close(){if(closing)return closing;stopped=true;closing=(async()=>{const closed=[...open.values()],listener=once(server,'close');server.close();for(const res of pending.keys())res.destroy();server.closeAllConnections();await listener;await Promise.all(closed);})();return closing;}};
}
// Observe the browser transport without buffering or changing its requests.
// The caller installs this before first-page navigation, so prefetch is visible.
function observeStandardRsc(page, origin) {
  const target = new URL(origin);
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || target.origin !== origin) throw Error('loopback_observer_required');
  const rows = new Map(), responses = new Map(), allowed = [paths.page, paths.nextPage];
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
          row.containsLateMarker = bytes.includes(Buffer.from(lateMarker));
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
module.exports={query,childQuery,paths,browserPaths,releaseId,secondId,lateMarker,catalog,batch,MAX_RSC_BODY_BYTES,startStandardReleaseFixture,observeStandardRsc,summarizeCatalogCompletion};
