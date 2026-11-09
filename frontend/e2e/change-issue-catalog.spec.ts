import { test, expect, type BrowserContext, type Page } from '@playwright/test';
const { startApp } = require('./fixture-server.cjs');
const { startStreamingProxy, allowedPath } = require('./streaming-proxy.cjs');
const { startChangeIssueCatalogFixture, paths, queries, lateMarkers, observeCatalogRsc, summarizeCatalogCompletion } = require('./change-issue-catalog-fixture.cjs');
type Kind = 'changes' | 'issues';
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
  const p = paths[kind], options = { changeIssueCatalogQuery: queries[kind] };
  page.on('pageerror', error => pageErrors.push(error.name));
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), headers = await request.allHeaders();
    const raw = url.pathname + url.search;
    const asset = url.pathname.startsWith('/_next/static/') || url.pathname === '/favicon.ico';
    const navigation = request.isNavigationRequest() && request.resourceType() === 'document';
    const document = navigation && request.frame().parentFrame() === null && request.method() === 'GET' && [p.page, p.firstPage].includes(raw);
    const token = url.searchParams.get('_rsc');
    const withoutRsc = token === null ? raw : raw.slice(0, -('&_rsc=' + token).length);
    // A reset/project path has no business query, so its RSC delimiter is '?'.
    const businessPath = [p.resetPage, '/projects'].includes(url.pathname) && [...url.searchParams.keys()].every(key => key === '_rsc') ? url.pathname : withoutRsc;
    const rsc = !navigation && request.method() === 'GET' && headers.rsc === '1' &&
      [p.page, p.firstPage, p.nextPage, p.resetPage, '/projects'].includes(businessPath);
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
      await info.attach('synthetic-change-issue-timeout-requests', {
        body: JSON.stringify({ observations, requests: app.fixture.requests, browserReads, rscFlights: rscObserver?.requests ?? [], completionEvidence }, null, 2), contentType: 'application/json',
      });
      const initial = app.fixture.requests.find(read => read.kind === 'target');
      await info.attach('synthetic-change-issue-browser-timing', {
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
      if (info.status !== info.expectedStatus) await info.attach('synthetic-change-issue-next-log', { body: app.logs(), contentType: 'text/plain' });
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

async function journey(page: Page, context: BrowserContext, kind: Kind, phase: Phase) {
  observations = { kind, phase };
  const current: Harness = await startApp(() => startChangeIssueCatalogFixture(kind, phase)); app = current;
  const transport: Proxy = await startStreamingProxy(current.appOrigin, { changeIssueCatalogQuery: queries[kind] }); proxy = transport;
  await isolate(context, page, transport.origin, kind);
  await context.addCookies([{ name: 'slc_language', value: 'en', url: transport.origin }]);
  const p = paths[kind], targetUrl = transport.origin + p.page;
  const title = kind === 'changes' ? 'Software Change Requests' : 'Issues';
  const failure = kind === 'changes' ? 'Change catalog unavailable' : 'Issue catalog unavailable';
  const targetReads = () => current.fixture.requests.filter(read => read.kind === 'target');
  const content = page.getByRole('main').locator('.content'), loading = content.getByRole('status');
  const summary = content.locator('.summary > div > b'), unknown = Array(kind === 'changes' ? 3 : 1).fill('—');

  // Do not wait for DOMContentLoaded: the held API must still be incomplete.
  await page.goto(targetUrl, { waitUntil: 'commit' });
  await expect(content.getByRole('heading', { name: title, exact: true, level: 1 })).toBeVisible();
  const filters = content.locator('form.filters');
  await expect(filters).toBeVisible(); await expect(filters).toHaveAttribute('method', 'get');
  for (const key of ['q', 'status', 'scope', 'limit', ...(kind === 'changes' ? ['source', 'change_type', 'software_id', 'customer_id', 'project_id'] : ['severity'])]) {
    await expect(filters.locator(`input[name="${key}"]`)).toHaveValue(new URLSearchParams(queries[kind]).get(key)!);
  }
  await expect(filters.locator('input[name="offset"]')).toHaveCount(0);
  await expect(filters.getByRole('button', { name: 'Filter', exact: true })).toBeEnabled();
  await expect(loading).toHaveCount(1); await expect(loading).toBeVisible();
  await expect(loading).toHaveClass(/(?:^|\s)page-loading(?:\s|$)/); await expect(loading).toHaveAttribute('aria-busy', 'true');
  await expect(summary).toHaveText(unknown); await expect(content.locator('.tablewrap')).toHaveCount(0);
  observations.loading = performance.now();
  await expect.poll(() => targetReads().length).toBe(1);
  expect(current.fixture.pendingCount).toBe(1);
  expect(targetReads()[0]).toMatchObject({ method: 'GET', url: p.api, phase,
    headersSent: phase === 'body', closedAt: null, finishedAt: null, status: phase === 'body' ? 200 : null });

  // This is the real 15000ms app deadline, never a fixture release or fake clock.
  await expect(content.getByRole('heading', { name: failure, exact: true })).toBeVisible({ timeout: 25_000 });
  observations.unavailable = performance.now();
  documentTimings.push(await documentTiming(page, 'initial-timeout-document'));
  await expect(loading).toHaveCount(0); await expect(summary).toHaveText(unknown);
  await expect(filters).toBeVisible(); await expect(content.locator('.tablewrap')).toHaveCount(0);
  await expect(content.getByText('No matching records on this page.', { exact: true })).toHaveCount(0);
  for (const error of ['AbortError', 'SyntaxError', 'PRIVATE_', '/api/v1/change-catalog/']) await expect(content).not.toContainText(error);
  await expect.poll(() => targetReads()[0].closedAt).not.toBeNull();
  expect(targetReads()[0].finishedAt).toBeNull(); expect(current.fixture.pendingCount).toBe(0);
  // The exact timeout is independently unit-tested. Allow scheduling overhead,
  // while ruling out an immediate synthetic timeout masquerading as acceptance.
  expect(targetReads()[0].closedAt! - targetReads()[0].receivedAt).toBeGreaterThanOrEqual(14_000);
  expect(targetReads()[0].closedAt! - targetReads()[0].receivedAt).toBeLessThan(25_000);

  const chinese = phase === 'body';
  if (chinese) {
    await page.getByRole('button', { name: '中文', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  }
  const retryLabel = chinese ? (kind === 'changes' ? '重新读取变更' : '重新读取问题') : `Read ${kind} again`;
  const retry = content.getByRole('link', { name: retryLabel, exact: true });
  await expect(retry).toHaveAttribute('href', p.page);
  await page.evaluate(() => { (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker = true; });
  current.fixture.recover(); await page.waitForTimeout(800);
  await expect(retry).toBeVisible(); await expect(summary).toHaveText(unknown);
  expect(targetReads()).toHaveLength(1); // Neither healthy upstream nor language change retries.
  const [document] = await Promise.all([
    page.waitForResponse(response => response.url() === targetUrl && response.request().isNavigationRequest() &&
      response.request().method() === 'GET' && response.request().frame() === page.mainFrame()), retry.click(),
  ]);
  expect(document.status()).toBe(200); await page.waitForLoadState('domcontentloaded');
  await expect(page).toHaveURL(targetUrl);
  expect(await page.evaluate(() => (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker)).toBeUndefined();
  await expect(summary).toHaveText(unknown.map(() => '0'));
  await expect(content.locator('.tablewrap').getByText(chinese ? '当前页没有匹配记录。' : 'No matching records on this page.', { exact: true })).toBeVisible();
  await expect(content.locator('.tablewrap tbody tr')).toHaveCount(0); await expect(loading).toHaveCount(0);
  await expect(retry).toHaveCount(0);
  expect(targetReads().map(({ method, url }) => ({ method, url }))).toEqual([{ method: 'GET', url: p.api }, { method: 'GET', url: p.api }]);
  expect(targetReads()[1]).toMatchObject({ phase: 'ready', headersSent: true, status: 200, finishedAt: expect.any(Number) });
  expect(browserReads.filter(read => read.kind === 'document')).toEqual([{ path: p.page, kind: 'document' }, { path: p.page, kind: 'document' }]);
  observations.recovered = performance.now();
  documentTimings.push(await documentTiming(page, 'native-retry-document'));

  // A fresh document clears router cache. First-page success is deliberately 7;
  // the held next query must show — rather than retain those resolved metrics.
  const flights: RscObserver = observeCatalogRsc(page, transport.origin, kind); rscObserver = flights;
  current.fixture.hold();
  await page.goto(transport.origin + p.firstPage);
  await expect(summary).toHaveText(unknown.map(() => '7'));
  documentTimings.push(await documentTiming(page, 'fresh-first-page-document'));
  await page.evaluate(() => { (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker = true; });
  const next = content.getByRole('link', { name: chinese ? '下一页 →' : 'Next page →', exact: true });
  await expect(next).toHaveAttribute('href', p.nextPage); await next.click();
  await expect(page).toHaveURL(transport.origin + p.nextPage);
  await expect(loading).toBeVisible(); await expect(summary).toHaveText(unknown);
  await expect(filters).toBeVisible(); await expect(content.locator('.tablewrap')).toHaveCount(0);
  await expect.poll(() => targetReads().length).toBeGreaterThan(2);
  expect(current.fixture.pendingCount).toBeGreaterThan(0); observations.queryPending = performance.now();
  expect(await page.evaluate(() => (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker)).toBe(true);
  const beforeNavigation = flights.requests;
  const pendingCandidateIds = beforeNavigation.filter(read => read.outcome === 'pending').map(read => read.id);
  expect(pendingCandidateIds.length, 'A real target RSC body must still be pending before leaving').toBeGreaterThan(0);
  const lastBeforeNavigationId = Math.max(...beforeNavigation.map(read => read.id));
  await page.locator('.side a[href="/projects"]').click();
  await expect(page).toHaveURL(transport.origin + '/projects');
  await expect(content.getByRole('heading', { name: chinese ? '项目' : 'Projects', exact: true, level: 1 })).toBeVisible();
  await expect.poll(() => browserReads.some(read => read.kind === 'navigation' && read.path.startsWith('/projects'))).toBe(true);
  observations.destination = performance.now();
  const atDestination = flights.requests;
  const candidateIds = atDestination.filter(read => pendingCandidateIds.includes(read.id) || read.id > lastBeforeNavigationId).map(read => read.id);
  const liveAtDestinationIds = atDestination.filter(read => candidateIds.includes(read.id) && read.outcome === 'pending').map(read => read.id);
  const backendAtDestination = targetReads().slice(2);
  const liveBackendIds = backendAtDestination.filter(read => read.closedAt === null && read.finishedAt === null).map(read => read.id);
  let releasedIds: number[] = [], releasedAt: number | null = null, releaseAttemptAt: number | null = null;
  // If the browser already cancelled all candidate streams, do not perform a
  // no-op release and call it stale delivery. Await the actual upstream abort.
  if (liveAtDestinationIds.length && liveBackendIds.length) {
    releaseAttemptAt = performance.now(); releasedIds = current.fixture.releaseHeld();
    expect(releasedIds.every(id => liveBackendIds.includes(id))).toBe(true);
    if (releasedIds.length) { releasedAt = releaseAttemptAt; observations.released = releasedAt; }
  }
  completionEvidence = { atDestination, backendAtDestination, candidateIds, liveAtDestinationIds,
    liveBackendIds, releaseAttemptAt, releasedAt, releasedIds };
  await expect.poll(() => flights.requests.filter(read => candidateIds.includes(read.id)).every(read => read.outcome !== 'pending'),
    { timeout: 25_000, message: 'Wait for target RSC requestfinished/requestfailed, not just API close' }).toBe(true);
  await expect.poll(() => targetReads().slice(2).every(read => read.closedAt !== null),
    { timeout: 25_000, message: 'Each target API read must finish after explicit release or close aborted' }).toBe(true);
  // No fresh target retry may appear after leaving. Completed prefetch shells
  // before the held-query checkpoint are recorded but cannot prove late data.
  expect(flights.requests.map(read => read.id)).toEqual(atDestination.map(read => read.id));
  expect(targetReads().slice(2).map(read => read.id)).toEqual(backendAtDestination.map(read => read.id));
  // Inspect only already-finished exact target responses, without buffering
  // delivery. A 200 shell alone is not proof that stale catalog data arrived.
  await flights.inspectCompletedBodies(candidateIds);
  const browserOutcomes = flights.requests.filter(read => candidateIds.includes(read.id));
  const backendOutcomes = targetReads().slice(2);
  const result = summarizeCatalogCompletion({ backendReads: backendOutcomes, browserReads: browserOutcomes,
    releasedIds, releasedAt, liveAtDestinationIds });
  completionEvidence = { ...completionEvidence, browserOutcomes, backendOutcomes, result };
  // A finished transport is not yet a rendered React update. Cross two frame
  // callbacks before checking that the processed stream cannot replace /projects.
  await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
  await expect(page).toHaveURL(transport.origin + '/projects');
  await expect(content.getByRole('heading', { name: chinese ? '项目' : 'Projects', exact: true, level: 1 })).toBeVisible();
  await expect(content.locator('.summary > div > b')).toHaveText(['0']);
  await expect(content).not.toContainText('991');
  await expect(content).not.toContainText(lateMarkers[kind]);
  await expect(content.getByRole('heading', { name: chinese ? (kind === 'changes' ? '软件变更申请' : '问题') : title, exact: true, level: 1 })).toHaveCount(0);
  expect(await page.evaluate(() => (window as Window & { catalogDocumentMarker?: boolean }).catalogDocumentMarker)).toBe(true);
  expect(current.fixture.pendingCount).toBe(0);
}

test('change catalog header stall preserves shell; native retry and newer navigation stay isolated', async ({ page, context }) => { await journey(page, context, 'changes', 'headers'); });
test('change catalog body stall preserves shell; native retry and newer navigation stay isolated', async ({ page, context }) => { await journey(page, context, 'changes', 'body'); });
test('issue catalog header stall preserves shell; native retry and newer navigation stay isolated', async ({ page, context }) => { await journey(page, context, 'issues', 'headers'); });
test('issue catalog body stall preserves shell; native retry and newer navigation stay isolated', async ({ page, context }) => { await journey(page, context, 'issues', 'body'); });
