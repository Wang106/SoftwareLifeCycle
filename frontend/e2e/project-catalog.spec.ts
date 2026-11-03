import { test, expect, type BrowserContext, type Page } from '@playwright/test';

const { startApp } = require('./fixture-server.cjs');
const { startStreamingProxy, allowedPath } = require('./streaming-proxy.cjs');
const { startProjectCatalogFixture, paths, query } = require('./project-catalog-fixture.cjs');

type Phase = 'headers' | 'body';
type FixtureRequest = {
  kind: 'target' | 'ancillary' | 'rejected'; method: string; url: string;
  phase: Phase | 'ready' | 'rejected'; receivedAt: number; headersSent: boolean;
  closedAt: number | null; finishedAt: number | null; status: number | null;
};
type Harness = {
  appOrigin: string;
  fixture: { requests: FixtureRequest[]; violations: unknown[]; pendingCount: number; recover(): void };
  stop(): Promise<void>; logs(): string;
};
type Proxy = { origin: string; violations: string[]; close(): Promise<void> };
type BrowserRead = { path: string; kind: 'document' | 'prefetch' };
const proxyOptions = { projectCatalogQuery: query };
let app: Harness | undefined;
let proxy: Proxy | undefined;
let phase: Phase | undefined;
let blocked: string[];
let browserReads: BrowserRead[];
let observations: { loading?: number; unavailable?: number; recovered?: number };

async function isolate(context: BrowserContext, origin: string) {
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), headers = await request.allHeaders();
    const raw = url.pathname + url.search;
    const asset = url.pathname.startsWith('/_next/static/') || url.pathname === '/favicon.ico';
    const prefetch = headers['next-router-prefetch'] === '1' || headers.purpose === 'prefetch' || headers['sec-purpose'] === 'prefetch';
    const navigation = request.isNavigationRequest() && request.resourceType() === 'document';
    const targetDocument = navigation && request.frame().parentFrame() === null && request.method() === 'GET' && raw === paths.page;
    const queryWithoutRsc = new URLSearchParams(url.search);
    queryWithoutRsc.delete('_rsc');
    const pageWithoutRsc = url.pathname + (queryWithoutRsc.size ? '?' + queryWithoutRsc : '');
    const knownPrefetch = !navigation && request.method() === 'GET' && headers.rsc === '1' && prefetch &&
      [paths.page, paths.firstPage, paths.resetPage].includes(pageWithoutRsc);
    // The language preference is the only browser cookie used by these cases.
    // It must not become an API credential; the fixture independently rejects cookies.
    const cookieAllowed = !headers.cookie || /^slc_language=(?:zh|en)$/.test(headers.cookie);
    if (url.origin !== origin || !['GET', 'HEAD'].includes(request.method()) ||
        headers.authorization || headers['proxy-authorization'] || !cookieAllowed ||
        !allowedPath(raw, proxyOptions) || (!(asset && !navigation) && !targetDocument && !knownPrefetch)) {
      blocked.push(`${request.method()} ${url.origin}${url.pathname}`);
      await route.abort('blockedbyclient');
      return;
    }
    if (!asset) browserReads.push({ path: raw, kind: targetDocument ? 'document' : 'prefetch' });
    // Continue through the streaming proxy. Buffering with fetch/fulfill would
    // prevent this case from observing the loading DOM while the API is held.
    await route.continue();
  });
  await context.routeWebSocket('**/*', socket => {
    blocked.push(`WebSocket ${socket.url()}`);
    socket.close();
  });
}

test.beforeEach(() => {
  app = undefined; proxy = undefined; phase = undefined;
  blocked = []; browserReads = []; observations = {};
});
test.afterEach(async ({ browser }, info) => {
  try {
    if (app) {
      await info.attach('synthetic-project-timeout-requests', {
        body: JSON.stringify({ phase, observations, requests: app.fixture.requests, browserReads }, null, 2),
        contentType: 'application/json',
      });
      if (info.status !== info.expectedStatus) {
        await info.attach('synthetic-project-timeout-next-log', { body: app.logs(), contentType: 'text/plain' });
      }
    }
    expect(blocked, 'Browser must not access external/private services, send credentials or mutate data').toEqual([]);
    if (app) expect(app.fixture.violations, 'The API fixture accepts only the finite synthetic GET scope').toEqual([]);
    if (proxy) expect(proxy.violations, 'The streaming proxy must reject unexpected requests and redirects').toEqual([]);
    if (info.status === 'passed') {
      info.annotations.push(
        { type: 'browser-engine', description: browser.browserType().name() },
        { type: 'synthetic-loopback-fixture', description: 'verified' },
        { type: 'browser-worker-index', description: String(info.workerIndex) },
      );
    }
  } finally {
    // A proxy cleanup failure must not leave the Next process or held API alive.
    try { if (proxy) await proxy.close(); } finally { if (app) await app.stop(); }
  }
});

async function timeoutJourney(page: Page, context: BrowserContext, heldPhase: Phase) {
  phase = heldPhase;
  const current: Harness = await startApp(() => startProjectCatalogFixture(heldPhase));
  app = current;
  const transport: Proxy = await startStreamingProxy(current.appOrigin, proxyOptions);
  proxy = transport;
  await isolate(context, transport.origin);
  const targetUrl = transport.origin + paths.page;
  const targetReads = () => current.fixture.requests.filter(request => request.kind === 'target');

  // Waiting for load here would hide the streaming shell until the server's
  // real, unmodified 15-second read budget has already expired.
  await page.goto(targetUrl, { waitUntil: 'commit' });
  const content = page.getByRole('main').locator('.content');
  const loading = content.getByRole('status');
  await expect(loading).toHaveCount(1);
  await expect(loading).toBeVisible();
  await expect(loading).toHaveClass(/(?:^|\s)page-loading(?:\s|$)/);
  await expect(loading).toHaveAttribute('aria-busy', 'true');
  await expect(loading.getByRole('heading', { name: '正在加载页面数据', exact: true })).toBeVisible();
  observations.loading = performance.now();
  await expect.poll(() => targetReads().length).toBe(1);
  expect(current.fixture.pendingCount).toBe(1);
  expect(targetReads()[0]).toMatchObject({
    method: 'GET', url: paths.api, phase: heldPhase, headersSent: heldPhase === 'body',
    closedAt: null, finishedAt: null, status: heldPhase === 'body' ? 200 : null,
  });
  const unavailable = content.getByRole('heading', { name: '组织目录暂不可用', exact: true });
  // This generous assertion deadline bounds the test, not production latency.
  // The existing unit contracts independently require the exact 15000 ms budget.
  await expect(unavailable).toBeVisible({ timeout: 25_000 });
  observations.unavailable = performance.now();
  await expect(loading).toHaveCount(0);
  await expect(content.getByRole('heading', { name: '项目', exact: true, level: 1 })).toBeVisible();
  const summary = content.locator('.summary > div > b');
  await expect(summary).toHaveCount(1);
  await expect(summary).toHaveText('—');
  await expect(content.locator('.tablewrap')).toHaveCount(0);
  await expect(content.getByText('当前页没有匹配记录。', { exact: true })).toHaveCount(0);
  for (const rawError of ['AbortError', 'SyntaxError', '/api/v1/organization-views/projects']) {
    await expect(content).not.toContainText(rawError);
  }
  await expect.poll(() => targetReads()[0].closedAt).not.toBeNull();
  expect(targetReads()[0].finishedAt).toBeNull();
  expect(current.fixture.pendingCount).toBe(0);
  expect(targetReads()).toHaveLength(1);

  const english = heldPhase === 'body';
  if (english) {
    await page.getByRole('button', { name: 'English', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(content.getByRole('heading', { name: 'Organization catalog unavailable', exact: true })).toBeVisible();
    expect(targetReads()).toHaveLength(1);
  }
  const retryLabel = english ? 'Read projects again' : '重新读取项目';
  const retry = content.getByRole('link', { name: retryLabel, exact: true });
  await expect(retry).toHaveAttribute('href', paths.page);
  await page.evaluate(() => { (window as Window & { projectCatalogDocumentMarker?: boolean }).projectCatalogDocumentMarker = true; });
  current.fixture.recover();
  await page.waitForTimeout(800); // Becoming healthy alone must not trigger another target read.
  await expect(summary).toHaveText('—');
  await expect(retry).toBeVisible();
  expect(targetReads()).toHaveLength(1);

  // The URL is unchanged. Arm an actual document response before clicking;
  // waitForURL alone could resolve immediately without any native reload.
  const [document] = await Promise.all([
    page.waitForResponse(response => response.url() === targetUrl &&
      response.request().isNavigationRequest() && response.request().method() === 'GET' &&
      response.request().frame() === page.mainFrame()),
    retry.click(),
  ]);
  expect(document.status()).toBe(200);
  await page.waitForLoadState('domcontentloaded');
  await expect(page).toHaveURL(targetUrl);
  await expect(content.getByRole('heading', { name: english ? 'Projects' : '项目', exact: true, level: 1 })).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { projectCatalogDocumentMarker?: boolean }).projectCatalogDocumentMarker)).toBeUndefined();
  await expect(summary).toHaveCount(1);
  await expect(summary).toHaveText('0');
  const table = content.locator('.tablewrap');
  await expect(table.getByText(english ? 'No matching records on this page.' : '当前页没有匹配记录。', { exact: true })).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(0);
  await expect(content.getByRole('heading', { name: english ? 'Organization catalog unavailable' : '组织目录暂不可用', exact: true })).toHaveCount(0);
  await expect(content.getByRole('link', { name: retryLabel, exact: true })).toHaveCount(0);
  await expect(loading).toHaveCount(0);
  expect(targetReads().map(({ method, url }) => ({ method, url }))).toEqual([
    { method: 'GET', url: paths.api }, { method: 'GET', url: paths.api },
  ]);
  expect(targetReads()[1]).toMatchObject({
    phase: 'ready', headersSent: true, status: 200, finishedAt: expect.any(Number),
  });
  expect(browserReads.filter(read => read.kind === 'document')).toEqual([
    { path: paths.page, kind: 'document' }, { path: paths.page, kind: 'document' },
  ]);
  observations.recovered = performance.now();
}

test('project catalog header stall becomes unavailable; native retry preserves the exact query', async ({ page, context }) => {
  await timeoutJourney(page, context, 'headers');
});

test('project catalog body stall becomes unavailable; native retry preserves the exact query', async ({ page, context }) => {
  await timeoutJourney(page, context, 'body');
});
