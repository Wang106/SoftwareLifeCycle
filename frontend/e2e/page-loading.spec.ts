import { test, expect, type BrowserContext } from '@playwright/test';
const { startApp } = require('./fixture-server.cjs');
const { startStreamingProxy } = require('./streaming-proxy.cjs');
const { startLoadingFixture, endpoints } = require('./page-loading-fixture.cjs');
type Harness = { appOrigin: string; fixture: { requests: { path: string }[]; violations: unknown[]; releaseDashboard(failure?: boolean): void }; stop(): Promise<void>; logs(): string };
let app: Harness;
let proxy: { origin: string; violations: string[]; close(): Promise<void> };
let blocked: string[];
let onFirstPrefetch: (() => Promise<void>) | undefined;
let browserReads: { path: string; rsc: boolean; prefetch: boolean }[];
async function isolateStreaming(context: BrowserContext) {
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), headers = request.headers();
    const pagePath = ['/', '/changes', '/issues', '/projects'].includes(url.pathname);
    const asset = url.pathname.startsWith('/_next/static/') || url.pathname === '/favicon.ico';
    const queryAllowed = [...url.searchParams.keys()].every(key => key === '_rsc');
    if (url.origin !== app.appOrigin || !['GET', 'HEAD'].includes(request.method()) || (!asset && (!pagePath || !queryAllowed))) {
      blocked.push(`${request.method()} ${url.origin}${url.pathname}`); await route.abort('blockedbyclient'); return;
    }
    if (pagePath) browserReads.push({ path: url.pathname, rsc: headers.rsc === '1', prefetch: headers['next-router-prefetch'] === '1' || headers.purpose === 'prefetch' || headers['sec-purpose'] === 'prefetch' });
    // Do not buffer via route.fetch/fulfill: that would invalidate streaming timing.
    // A fixed loopback streaming proxy rejects redirects before they reach the browser.
    if (url.pathname === '/changes' && headers['next-router-prefetch'] === '1' && onFirstPrefetch) { const act = onFirstPrefetch; onFirstPrefetch = undefined; await act(); }
    await route.continue();
  });
  await context.routeWebSocket('**/*', socket => { blocked.push(`WebSocket ${socket.url()}`); socket.close(); });
}
test.beforeEach(async ({ context }) => { app = await startApp(startLoadingFixture); proxy = await startStreamingProxy(app.appOrigin); app.appOrigin = proxy.origin; blocked = []; onFirstPrefetch = undefined; browserReads = []; await isolateStreaming(context); });
test.afterEach(async ({ browser }, info) => {
  try {
    if (info.status !== info.expectedStatus) await info.attach('synthetic-loading-next-log', { body: app.logs(), contentType: 'text/plain' });
    expect(blocked, 'No external, private or mutation requests').toEqual([]);
    expect(app.fixture.violations).toEqual([]);
    expect(proxy.violations).toEqual([]);
    if (info.status === 'passed') info.annotations.push({ type: 'browser-engine', description: browser.browserType().name() }, { type: 'synthetic-loopback-fixture', description: 'verified' }, { type: 'browser-worker-index', description: String(info.workerIndex) });
  } finally { await proxy.close(); await app.stop(); }
});

test('dashboard streams before data; bounded full prefetch follows; long sidebar and mobile remain consistent', async ({ page }, info) => {
  await page.goto(app.appOrigin + '/', { waitUntil: 'commit' });
  await expect(page.getByRole('heading', { name: '生命周期仪表盘', exact: true })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('正在加载页面数据');
  await expect.poll(() => app.fixture.requests.filter(r => r.path === endpoints.dashboard).length).toBe(1);
  await page.waitForTimeout(800); // Observe a held upstream, not a response-speed threshold.
  expect(app.fixture.requests.map(r => r.path)).toEqual([endpoints.dashboard]);
  app.fixture.releaseDashboard();
  await expect(page.getByText('SYNTHETIC_LOADING_ACTIVITY_0', { exact: true })).toBeVisible();
  await expect(page.getByRole('status')).toHaveCount(0);
  await expect.poll(() => app.fixture.requests.filter(r => r.path !== endpoints.dashboard).map(r => r.path).sort()).toEqual([endpoints.changes, endpoints.issues].sort());
  expect(browserReads.filter(r => r.prefetch).map(r => r.path).sort()).toEqual(['/changes', '/issues']);
  await page.waitForTimeout(800);
  expect(app.fixture.requests.length).toBe(3);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const side = page.locator('.side');
  await side.evaluate(element => { element.scrollTop = element.scrollHeight; });
  expect(await page.evaluate(() => {
    let node = document.elementFromPoint(8, innerHeight - 2);
    while (node) { const color = getComputedStyle(node).backgroundColor; if (color !== 'rgba(0, 0, 0, 0)' && color !== 'transparent') return color; node = node.parentElement; }
    return 'none';
  })).toBe('rgb(17, 24, 39)');
  await expect(page.locator('.sidefoot')).toBeInViewport();
  await info.attach('synthetic-long-sidebar', { body: await page.screenshot(), contentType: 'image/png' });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(side).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('foreground navigation proceeds while dashboard is held; late dashboard cannot replace the current route', async ({ page }) => {
  await page.goto(app.appOrigin + '/', { waitUntil: 'commit' });
  await expect(page.getByRole('status')).toBeVisible();
  await page.locator('.side a[href="/projects"]').click();
  await expect(page.getByRole('heading', { name: '项目', exact: true })).toBeVisible();
  await expect.poll(() => browserReads.some(r => r.path === '/projects' && r.rsc && !r.prefetch)).toBe(true);
  expect(app.fixture.requests.some(r => r.path === endpoints.projects)).toBe(true);
  expect(app.fixture.requests.some(r => r.path === endpoints.changes || r.path === endpoints.issues)).toBe(false);
  app.fixture.releaseDashboard();
  await page.waitForTimeout(1200); // Give a stale result/idle callback an opportunity to surface.
  await expect(page.getByRole('heading', { name: '项目', exact: true })).toBeVisible();
  await expect(page.getByText('SYNTHETIC_LOADING_ACTIVITY_0', { exact: true })).toHaveCount(0);
  expect(app.fixture.requests.some(r => r.path === endpoints.changes || r.path === endpoints.issues)).toBe(false);
});

test('dashboard failure reveals no private error or fabricated data; explicit native retry recovers', async ({ page }) => {
  app.fixture.releaseDashboard(true);
  await page.goto(app.appOrigin + '/');
  await expect(page.locator('.datasource')).toBeVisible();
  await expect(page.locator('body')).not.toContainText('PRIVATE_FIXTURE_ERROR');
  await expect(page.getByText('SYNTHETIC_LOADING_ACTIVITY_0', { exact: true })).toHaveCount(0);
  await page.waitForTimeout(800);
  expect(app.fixture.requests.map(r => r.path)).toEqual([endpoints.dashboard]);
  await page.getByRole('button', { name: 'English', exact: true }).click();
  const retry = page.getByRole('link', { name: 'Read dashboard again', exact: true });
  await expect(retry).toHaveAttribute('href', '/');
  await page.evaluate(() => { (window as Window & { loadingDocumentMarker?: boolean }).loadingDocumentMarker = true; });
  app.fixture.releaseDashboard();
  await retry.click();
  await expect(page.getByText('SYNTHETIC_LOADING_ACTIVITY_0', { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { loadingDocumentMarker?: boolean }).loadingDocumentMarker)).toBeUndefined();
  expect(app.fixture.requests.filter(r => r.path === endpoints.dashboard).length).toBe(2);
});


test('navigation after the first background admission revokes the remaining queue', async ({ page }) => {
  await page.goto(app.appOrigin + '/', { waitUntil: 'commit' });
  await expect(page.getByRole('status')).toBeVisible();
  onFirstPrefetch = async () => { await page.locator('.side a[href="/projects"]').evaluate((anchor: HTMLAnchorElement) => anchor.click()); };
  app.fixture.releaseDashboard();
  await expect(page.getByRole('heading', { name: '项目', exact: true })).toBeVisible();
  expect(browserReads.some(r => r.path === '/changes' && r.prefetch)).toBe(true);
  await page.waitForTimeout(1200);
  expect(browserReads.some(r => r.path === '/issues' && r.prefetch)).toBe(false);
  expect(app.fixture.requests.some(r => r.path === endpoints.issues)).toBe(false);
  expect(app.fixture.requests.some(r => r.path === endpoints.projects)).toBe(true);
});
