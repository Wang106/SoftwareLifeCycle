import { test, expect, type BrowserContext, type Page, type Locator } from '@playwright/test';
const { startApp } = require('./fixture-server.cjs');
const { startStreamingProxy, allowedPath } = require('./streaming-proxy.cjs');
const { startStandardReleaseFixture, paths, query, childQuery, browserPaths, releaseId, lateMarker, observeStandardRsc, summarizeCatalogCompletion } = require('./standard-release-fixture.cjs');
type Kind = 'parent' | 'batch';
type Phase = 'headers' | 'body';
type Read = {
  id: number; kind: 'target' | 'ancillary' | 'rejected'; method: string; url: string;
  phase: Phase | 'ready' | 'rejected'; receivedAt: number; headersSent: boolean;
  closedAt: number | null; finishedAt: number | null; status: number | null;
};
type Harness = {
  appOrigin: string;
  fixture: { requests: Read[]; violations: unknown[]; pendingCount: number; recover(): void; hold(): void; releaseHeld(): number[] };
  stop(): Promise<void>; logs(): string;
};
type BrowserFlight = { id: number; path: string; receivedAt: number; endedAt: number | null;
  outcome: 'pending' | 'finished' | 'failed'; status: number | null; failure: string | null;
  prefetch: boolean; bodyInspected: boolean; bodyBytes: number | null; containsLateMarker: boolean | null };
type RscObserver = { requests: BrowserFlight[]; inspectCompletedBodies(ids: number[]): Promise<void>; stop(): void };
let rscObserver: RscObserver | undefined, completionEvidence: Record<string, unknown> | undefined;
type Proxy = { origin: string; violations: string[]; close(): Promise<void> };
let app: Harness | undefined, proxy: Proxy | undefined;
let blocked: string[], pageErrors: string[];
let browserReads: { path: string; kind: 'document' | 'prefetch' | 'navigation' }[];
let documentTimings: Awaited<ReturnType<typeof documentTiming>>[];
let observations: { kind?: Kind; phase?: Phase; loading?: number; unavailable?: number; recovered?: number; queryPending?: number; destination?: number; released?: number };

async function documentTiming(page: Page, stage: string) {
  const timing = await page.evaluate(() => {
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    const paint = performance.getEntriesByType('paint');
    const value = (name: string) => paint.find(entry => entry.name === name)?.startTime ?? null;
    return {
      timeOriginEpochMs: performance.timeOrigin, observedAtDocumentMs: performance.now(),
      navigation: navigation ? {
        type: navigation.type, startTime: navigation.startTime, requestStart: navigation.requestStart,
        responseStart: navigation.responseStart, responseEnd: navigation.responseEnd,
        domInteractive: navigation.domInteractive, domContentLoadedEventEnd: navigation.domContentLoadedEventEnd,
        loadEventEnd: navigation.loadEventEnd, transferSize: navigation.transferSize,
        encodedBodySize: navigation.encodedBodySize, decodedBodySize: navigation.decodedBodySize,
      } : null,
      firstPaintMs: value('first-paint'), firstContentfulPaintMs: value('first-contentful-paint'),
      largestContentfulPaintMs: null,
    };
  });
  return { stage, ...timing };
}

async function isolate(context: BrowserContext, page: Page, origin: string, kind: Kind) {
  const p = paths, options = { standardReleaseQuery: query+childQuery };
  page.on('pageerror', error => pageErrors.push(error.name));
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), headers = await request.allHeaders();
    const raw = url.pathname + url.search;
    const asset = url.pathname.startsWith('/_next/static/') || url.pathname === '/favicon.ico';
    const navigation = request.isNavigationRequest() && request.resourceType() === 'document';
    const document = navigation && request.frame().parentFrame() === null && request.method() === 'GET' && browserPaths.includes(raw);
    const token = url.searchParams.get('_rsc');
    const withoutRsc = token === null ? raw : raw.slice(0, -('&_rsc=' + token).length);
    // A reset/project path has no business query, so its RSC delimiter is '?'.
    const businessPath = [p.resetPage, '/projects'].includes(url.pathname) && [...url.searchParams.keys()].every(key => key === '_rsc') ? url.pathname : withoutRsc;
    const rsc = !navigation && request.method() === 'GET' && headers.rsc === '1' &&
      [...browserPaths, '/projects'].includes(businessPath);
    const prefetch = headers['next-router-prefetch'] === '1' || headers.purpose === 'prefetch' || headers['sec-purpose'] === 'prefetch';
    const cookieAllowed = !headers.cookie || /^slc_language=(?:zh|en)$/.test(headers.cookie);
    if (url.origin !== origin || !['GET', 'HEAD'].includes(request.method()) ||
        Object.hasOwn(headers, 'authorization') || Object.hasOwn(headers, 'proxy-authorization') || !cookieAllowed ||
        !allowedPath(raw, options) || (!(asset && !navigation) && !document && !rsc)) {
      blocked.push(`${request.method()} ${url.origin}${url.pathname}`); await route.abort('blockedbyclient'); return;
    }
    if (!asset) browserReads.push({ path: raw, kind: document ? 'document' : prefetch ? 'prefetch' : 'navigation' });
    // Never route.fetch/fulfill: the stream must reach the browser before data.
    await route.continue();
  });
  await context.routeWebSocket('**/*', socket => { blocked.push(`WebSocket ${socket.url()}`); socket.close(); });
}

test.beforeEach(() => { app = undefined; proxy = undefined; blocked = []; pageErrors = []; browserReads = []; observations = {}; documentTimings = []; rscObserver = undefined; completionEvidence = undefined; });
test.afterEach(async ({ browser }, info) => {
  try {
    if (app) {
      await info.attach('synthetic-standard-release-timeout-requests', {
        body: JSON.stringify({ observations, requests: app.fixture.requests, browserReads, rscFlights: rscObserver?.requests ?? [], completionEvidence }, null, 2), contentType: 'application/json',
      });
      const initial = app.fixture.requests.find(read => read.kind === 'target');
      await info.attach('synthetic-standard-release-browser-timing', {
        body: JSON.stringify({
          scope: 'Same signed-CI Chromium journey, synthetic loopback only; not production latency.',
          conditions: 'Fresh Next process after auth readiness and fresh browser context per journey. Retry reuses the process/context. Request routing disables browser HTTP cache; this is not a fully cold-machine measurement.',
          units: 'Navigation/paint entries are browser document-relative milliseconds; fixture and shell observations share Node worker monotonic milliseconds. Do not subtract between these clock domains.',
          missing: 'Null means unavailable/not collected. Zero NavigationTiming fields can mean incomplete/not applicable, not zero latency. LCP was not collected.',
          nodeWorker: {
            apiReceivedAt: initial?.receivedAt ?? null, shellObservedAt: observations.loading ?? null,
            apiClosedAt: initial?.closedAt ?? null,
            shellAfterApiReceiptMs: initial && observations.loading !== undefined ? observations.loading - initial.receivedAt : null,
            apiHeldMs: initial?.closedAt != null ? initial.closedAt - initial.receivedAt : null,
          }, documentTimings,
        }, null, 2), contentType: 'application/json',
      });
      if (info.status !== info.expectedStatus) await info.attach('synthetic-standard-release-next-log', { body: app.logs(), contentType: 'text/plain' });
    }
    expect(blocked, 'No external/private services, credentials or mutations').toEqual([]);
    expect(pageErrors, 'No uncaught browser errors').toEqual([]);
    if (app) expect(app.fixture.violations, 'Only the finite synthetic anonymous GET scope').toEqual([]);
    if (proxy) expect(proxy.violations, 'No unexpected requests or redirects').toEqual([]);
    if (info.status === 'passed') info.annotations.push(
      { type: 'browser-engine', description: browser.browserType().name() },
      { type: 'synthetic-loopback-fixture', description: 'verified' },
      { type: 'browser-worker-index', description: String(info.workerIndex) },
    );
  } finally { rscObserver?.stop(); try { if (proxy) await proxy.close(); } finally { if (app) await app.stop(); } }
});

async function assertPendingApplications(content: Locator, selectedId: string | null) {
  const cards = content.locator('.standard-software-card');
  await expect(cards).toHaveCount(2);
  for (let index = 0; index < 2; index++) {
    const row = cards.nth(index);
    const selected = selectedId !== null && await row.getAttribute('id') === 'standard-software-' + selectedId;
    await expect(row.locator('[data-standard-application-state="pending"]')).toHaveCount(1);
    await expect(row.getByRole('status', { includeHidden: true })).toHaveCount(1);
    await expect(row).toHaveJSProperty('open', selected);
    if (selected) await expect(row.getByRole('status')).toBeVisible();
    else await expect(row.getByRole('status')).toHaveCount(0);
  }
  // Closed native details still own pending DOM, but expose no accessible status.
  await expect(content.getByRole('status', { includeHidden: true })).toHaveCount(2);
  await expect(content.getByRole('status')).toHaveCount(selectedId === null ? 0 : 1);
}

async function journey(page: Page, context: BrowserContext, kind: Kind, phase: Phase) {
  observations = { kind, phase };
  const current: Harness = await startApp(() => startStandardReleaseFixture(kind, phase)); app = current;
  const transport: Proxy = await startStreamingProxy(current.appOrigin, { standardReleaseQuery: query+childQuery }); proxy = transport;
  await isolate(context, page, transport.origin, kind);
  await context.addCookies([{ name: 'slc_language', value: 'en', url: transport.origin }]);
  const p = paths, targetUrl = transport.origin + p.page;
  const initialAnchor = kind === 'batch' ? '#standard-software-' + releaseId : '';
  const title = 'Standard Releases';
  const targetReads = () => current.fixture.requests.filter(read => read.kind === 'target');
  const content = page.getByRole('main').locator('.content');
  const filters = content.locator('form.filters');
  const loading = content.getByRole('status', { includeHidden: true });
  const parentState = content.locator('[data-standard-catalog-state]');
  const card = content.locator('#standard-software-'+releaseId);
  const assertParent = async (offset = 10) => {
    await expect(content.locator('.supplier-release-card > summary')).toContainText('Synthetic supplier');
    await expect(content.locator('.standard-software-card')).toHaveCount(offset === 0 ? 10 : 2);
    const summaries = content.locator('.standard-software-card > summary');
    await expect(summaries.first()).toContainText(offset === 0 ? 'baseline-1' : 'baseline-11');
    await expect(summaries.last()).toContainText(offset === 0 ? 'baseline-10' : 'baseline-12');
    await expect(content.locator('#standard-software-'+releaseId)).toHaveCount(offset === 0 ? 0 : 1);
    await expect(content).toContainText('Total releases: 12');
    await expect(content.getByRole('link', {name:'First page',exact:true}).last()).toHaveAttribute('href',p.firstPage);
  };
  // A retry must fetch a new document even when the current page already has
  // the selected row's fragment. A hash-only jump is not a successful retry.
  await page.goto(targetUrl + initialAnchor, {waitUntil:'commit'});
  await expect(content.getByRole('heading',{name:title,exact:true,level:1})).toBeVisible();
  await expect(filters).toHaveAttribute('method','get');
  for(const key of ['q','status','software_id','limit']) await expect(filters.locator(`input[name="${key}"]`)).toHaveValue(new URLSearchParams(query).get(key)!);
  for(const key of ['offset','applications_for','application_offset']) await expect(filters.locator(`input[name="${key}"]`)).toHaveCount(0);
  await expect(filters.getByRole('button',{name:'Filter',exact:true})).toBeEnabled();
  await expect.poll(()=>targetReads().length).toBe(1);
  if(kind==='parent'){
    await expect(parentState).toHaveAttribute('data-standard-catalog-state','pending');
    await expect(loading).toHaveCount(1);await expect(loading).toBeVisible();
    await expect(content.locator('.supplier-release-card')).toHaveCount(0);
    expect(current.fixture.requests).toHaveLength(1);
  }else{
    await expect(parentState).toHaveAttribute('data-standard-catalog-state','ready');
    await expect(card.locator('[data-standard-application-state]')).toHaveAttribute('data-standard-application-state','pending');
    await assertParent();await assertPendingApplications(content, releaseId);
    await expect(card).not.toContainText('Recorded count: 0');expect(current.fixture.requests).toHaveLength(2);
  }
  observations.loading=performance.now();
  expect(targetReads()[0]).toMatchObject({phase,headersSent:phase==='body',closedAt:null,finishedAt:null});
  const unavailable=kind==='parent'?content.getByRole('heading',{name:'Release catalog unavailable',exact:true}):card.getByText('Application release page unavailable. The API is unavailable or pagination is invalid.',{exact:true});
  await expect(unavailable).toBeVisible({timeout:25_000});observations.unavailable=performance.now();
  await expect(loading).toHaveCount(0);await expect(filters).toBeVisible();
  if(kind==='batch'){await assertParent();await expect(card.locator('[data-standard-application-state]')).toHaveAttribute('data-standard-application-state','unavailable');}
  else await expect(parentState).toHaveAttribute('data-standard-catalog-state','unavailable');
  await expect(content).not.toContainText('No releases on this page.');
  if(kind==='batch')await expect(card).not.toContainText('Recorded count: 0');
  for(const privateText of ['AbortError','SyntaxError','PRIVATE_','/api/v1/'])await expect(content).not.toContainText(privateText);
  await expect.poll(()=>targetReads()[0].closedAt).not.toBeNull();expect(targetReads()[0].finishedAt).toBeNull();
  // Parent and child share the read budget; framework connection setup is not included.
  expect(targetReads()[0].closedAt!-current.fixture.requests[0].receivedAt).toBeGreaterThanOrEqual(14_000);
  expect(targetReads()[0].closedAt!-targetReads()[0].receivedAt).toBeLessThan(25_000);
  documentTimings.push(await documentTiming(page,'initial-timeout-document'));
  const retry=(kind==='parent'?content:card).getByRole('link',{name:kind==='parent'?'Read standard releases again':'Read application releases again',exact:true});
  await expect(page).toHaveURL(targetUrl + initialAnchor);
  await expect(retry).toHaveAttribute('href',p.page);
  await page.evaluate(()=>{(window as Window & {catalogDocumentMarker?:boolean}).catalogDocumentMarker=true;});
  current.fixture.recover();
  const [document]=await Promise.all([page.waitForResponse(r=>r.url()===targetUrl&&r.request().isNavigationRequest()),retry.click()]);
  expect(document.status()).toBe(200);await page.waitForLoadState('domcontentloaded');
  await expect(page).toHaveURL(targetUrl);
  expect(await page.evaluate(()=>(window as Window & {catalogDocumentMarker?:boolean}).catalogDocumentMarker)).toBeUndefined();
  await assertParent();await expect(card).toContainText('Recorded count: 12');await expect(card).toContainText('application-11');await expect(card).toContainText('application-12');
  expect(targetReads()).toHaveLength(2);await expect(loading).toHaveCount(0);
  documentTimings.push(await documentTiming(page,'native-retry-document'));observations.recovered=performance.now();
  // Child navigation preserves the parent page and seven-key selection; parent navigation clears it.
  const childFirst=card.getByRole('link',{name:'First page',exact:true});await expect(childFirst).toHaveAttribute('href',p.childFirstPage+'#standard-software-'+releaseId);
  await childFirst.click();await expect(page).toHaveURL(transport.origin+p.childFirstPage+'#standard-software-'+releaseId);
  await expect(card).toContainText('application-1');
  await expect(card.getByRole('link',{name:'Next page →',exact:true})).toHaveAttribute('href',p.page+'#standard-software-'+releaseId);
  await content.getByRole('link',{name:'First page',exact:true}).last().click();
  await expect(page).toHaveURL(transport.origin+p.firstPage);await assertParent(0);
  // Reset is a new query while a prior stream is pending; a second hold tests route navigation.
  for (const destination of [p.resetPage, '/projects']) {
  const baseline = targetReads().length;
  current.fixture.hold();
  const flights:RscObserver=observeStandardRsc(page,transport.origin);rscObserver=flights;
  await page.goto(transport.origin+p.firstPage);
  await assertParent(0);
  await page.evaluate(()=>{(window as Window & {catalogDocumentMarker?:boolean}).catalogDocumentMarker=true;});
  const next=content.getByRole('link',{name:'Next page →',exact:true}).last();
  await expect(next).toHaveAttribute('href',p.nextPage);await next.click();
  await expect(page).toHaveURL(transport.origin+p.nextPage);
  await expect.poll(()=>current.fixture.pendingCount).toBeGreaterThan(0);
  if(kind==='parent'){await expect(loading).toHaveCount(1);await expect(loading).toBeVisible();}
  else await assertPendingApplications(content, null);
  await expect(filters).toBeVisible();observations.queryPending=performance.now();
  if(kind==='parent')await expect(content.locator('.supplier-release-card')).toHaveCount(0);else await assertParent();
  const beforeNavigation = flights.requests;
  const pendingCandidateIds = beforeNavigation.filter(read => read.outcome === 'pending').map(read => read.id);
  expect(pendingCandidateIds.length, 'A real target RSC body must still be pending before leaving').toBeGreaterThan(0);
  const lastBeforeNavigationId = Math.max(...beforeNavigation.map(read => read.id));
  if(destination===p.resetPage)await filters.getByRole('link',{name:'Reset',exact:true}).click();
  else await page.locator('.side a[href="/projects"]').click();
  await expect(page).toHaveURL(transport.origin+destination);
  await expect(content.getByRole('heading',{name:destination===p.resetPage?title:'Projects',exact:true,level:1})).toBeVisible();
  if(destination===p.resetPage){await expect(content).toContainText('No releases on this page.');await expect(filters.locator('input[name="q"]')).toHaveValue('');}
  observations.destination = performance.now();
  const atDestination = flights.requests;
  const candidateIds = atDestination.filter(read => pendingCandidateIds.includes(read.id) || read.id > lastBeforeNavigationId).map(read => read.id);
  const liveAtDestinationIds = atDestination.filter(read => candidateIds.includes(read.id) && read.outcome === 'pending').map(read => read.id);
  const backendAtDestination = targetReads().slice(baseline);
  const liveBackendIds = backendAtDestination.filter(read => read.closedAt === null && read.finishedAt === null).map(read => read.id);
  let releasedIds: number[] = [], releasedAt: number | null = null, releaseAttemptAt: number | null = null;
  // If the browser already cancelled all candidate streams, do not perform a
  // no-op release and call it stale delivery. Await the actual upstream abort.
  if (liveAtDestinationIds.length && liveBackendIds.length) {
    releaseAttemptAt = performance.now(); releasedIds = current.fixture.releaseHeld();
    expect(releasedIds.every(id => liveBackendIds.includes(id))).toBe(true);
    if (releasedIds.length) { releasedAt = releaseAttemptAt; observations.released = releasedAt; }
  }
  const checkpoint = { atDestination, backendAtDestination, candidateIds, liveAtDestinationIds,
    liveBackendIds, releaseAttemptAt, releasedAt, releasedIds };
  await expect.poll(() => flights.requests.filter(read => candidateIds.includes(read.id)).every(read => read.outcome !== 'pending'),
    { timeout: 25_000, message: 'Wait for target RSC requestfinished/requestfailed, not just API close' }).toBe(true);
  await expect.poll(() => targetReads().slice(baseline).every(read => read.closedAt !== null),
    { timeout: 25_000, message: 'Each target API read must finish after explicit release or close aborted' }).toBe(true);
  // No fresh target retry may appear after leaving. Completed prefetch shells
  // before the held-query checkpoint are recorded but cannot prove late data.
  expect(flights.requests.map(read => read.id)).toEqual(atDestination.map(read => read.id));
  expect(targetReads().slice(baseline).map(read => read.id)).toEqual(backendAtDestination.map(read => read.id));
  // Inspect only already-finished exact target responses, without buffering
  // delivery. A 200 shell alone is not proof that stale catalog data arrived.
  await flights.inspectCompletedBodies(candidateIds);
  const browserOutcomes = flights.requests.filter(read => candidateIds.includes(read.id));
  const backendOutcomes = targetReads().slice(baseline);
  const result = summarizeCatalogCompletion({ backendReads: backendOutcomes, browserReads: browserOutcomes,
    releasedIds, releasedAt, liveAtDestinationIds });
  completionEvidence = { ...completionEvidence, [destination]: {...checkpoint, browserOutcomes, backendOutcomes, result} };
  // A finished transport is not yet a rendered React update. Cross two frame
  // callbacks before checking that the processed stream cannot replace /projects.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page).toHaveURL(transport.origin+destination);
  await expect(content.getByRole('heading',{name:destination===p.resetPage?title:'Projects',exact:true,level:1})).toBeVisible();
  if(destination===p.resetPage)await expect(content).toContainText('No releases on this page.');
  else await expect(content.locator('.summary > div > b')).toHaveText(['0']);
  await expect(content).not.toContainText('991');
  await expect(content).not.toContainText(lateMarker);
  if(destination!==p.resetPage)await expect(content.getByRole('heading', { name: title, exact: true, level: 1 })).toHaveCount(0);
  expect(await page.evaluate(() => (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker)).toBe(true);
  expect(current.fixture.pendingCount).toBe(0);flights.stop();
  }
}

test('standard release parent header stall preserves layers; native retry and newer navigation stay isolated',async({page,context})=>{await journey(page,context,'parent','headers');});
test('standard release parent body stall preserves layers; native retry and newer navigation stay isolated',async({page,context})=>{await journey(page,context,'parent','body');});
test('standard release batch header stall preserves layers; native retry and newer navigation stay isolated',async({page,context})=>{await journey(page,context,'batch','headers');});
test('standard release batch body stall preserves layers; native retry and newer navigation stay isolated',async({page,context})=>{await journey(page,context,'batch','body');});
