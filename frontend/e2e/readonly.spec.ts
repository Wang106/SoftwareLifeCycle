import { test, expect, type BrowserContext } from '@playwright/test';

// No production identity, auth bypass or business fixture route is installed.
const { startApp, paths, values } = require('./fixture-server.cjs');
type Harness = {
  appOrigin: string;
  fixture: {
    requests: { url: string; method: string }[];
    violations: unknown[];
    setMode(mode: 'ready' | 'unavailable'): void;
  };
  stop(): Promise<void>;
  logs(): string;
};
let app: Harness;
let blocked: string[];
let speculativePrefetches: number;

async function isolate(context: BrowserContext) {
  // Even other loopback services are outside this browser's allowed destination.
  // The real Next response is buffered here; this suite makes no streaming/timing claim.
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== app.appOrigin || !['GET', 'HEAD'].includes(request.method())) {
      blocked.push(`${request.method()} ${url.origin}${url.pathname}`);
      await route.abort('blockedbyclient');
      return;
    }
    const headers = request.headers();
    if (headers['next-router-prefetch'] === '1' || headers.purpose === 'prefetch' || headers['sec-purpose'] === 'prefetch') {
      // Sidebar speculative reads are outside this bounded slice. Clicked routes
      // still reach the real Next process and its synthetic backend normally.
      speculativePrefetches += 1;
      await route.abort('blockedbyclient');
      return;
    }
    const response = await route.fetch({ maxRedirects: 0 });
    if (response.status() >= 300 && response.status() < 400) {
      blocked.push(`Unexpected redirect ${url.pathname}`);
      await route.abort('blockedbyclient');
      return;
    }
    await route.fulfill({ response });
  });
  await context.routeWebSocket('**/*', socket => {
    blocked.push(`WebSocket ${socket.url()}`);
    socket.close();
  });
}

test.beforeAll(async () => { app = await startApp(); });
test.afterAll(async () => { if (app) await app.stop(); });
test.beforeEach(async ({ context }) => {
  blocked = [];
  speculativePrefetches = 0;
  app.fixture.setMode('ready');
  await isolate(context);
});
test.afterEach(async ({ browser }, info) => {
  info.annotations.push({ type: 'isolated-speculative-prefetches', description: String(speculativePrefetches) });
  if (info.status !== info.expectedStatus) {
    await info.attach('synthetic-next-log', { body: app.logs(), contentType: 'text/plain' });
  }
  expect(blocked, 'Browser must never contact external services or submit any mutation').toEqual([]);
  expect(app.fixture.violations, 'Synthetic API must reject and report unknown/private/write requests').toEqual([]);
  if (info.status === 'passed') {
    info.annotations.push({ type: 'browser-engine', description: browser.browserType().name() });
    info.annotations.push({ type: 'synthetic-loopback-fixture', description: 'verified' });
    info.annotations.push({ type: 'browser-worker-index', description: String(info.workerIndex) });
  }
});

test('real DOM preserves recorded versus corrected evidence through navigation and language changes; writes stay disabled', async ({ page, context }, info) => {
  await page.goto(app.appOrigin + paths.batchPage);
  await expect(page.getByRole('heading', { name: values.batchNo, exact: true })).toBeVisible();
  const historyLink = page.getByRole('link', { name: '查看更正历史', exact: true });
  await expect(historyLink).toHaveAttribute('href', paths.historyPage);
  await historyLink.click();
  await expect(page).toHaveURL(app.appOrigin + paths.historyPage);
  await expect(page.getByRole('heading', { name: '生产批次更正历史', exact: true })).toBeVisible();
  const baseline = page.locator('section').filter({ has: page.getByRole('heading', { name: '原始记录基线', exact: true }) });
  const effective = page.locator('section').filter({ has: page.getByRole('heading', { name: '当前有效记录事实', exact: true }) });
  await expect(baseline).toContainText(values.baselineNote);
  await expect(baseline).toContainText(values.baselineVersion);
  await expect(baseline).not.toContainText(values.effectiveNote);
  await expect(effective).toContainText(values.effectiveNote);
  await expect(effective).toContainText(values.effectiveVersion);
  await expect(effective).not.toContainText(values.baselineNote);

  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(page.getByRole('heading', { name: 'Recorded baseline', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Effective recorded facts', exact: true })).toBeVisible();
  expect((await context.cookies()).find(cookie => cookie.name === 'slc_language')?.value).toBe('en');
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Batch correction history', exact: true })).toBeVisible();
  await expect(page.getByText(values.baselineNote, { exact: true })).toBeVisible();
  await expect(page.locator('section').filter({ has: page.getByRole('heading', { name: 'Effective recorded facts', exact: true }) })).toContainText(values.effectiveNote);
  await info.attach('synthetic-history-english', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await page.getByRole('link', { name: 'Open controlled batch correction workbench', exact: true }).click();
  await expect(page.getByText('Batch correction submission is disabled or unavailable for this session.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load private correction context', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Send confirmed batch correction', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Prepare batch correction', exact: true })).toHaveCount(0);
});

test('history failure shows no substitute evidence; native retry explicitly performs a fresh read', async ({ page }, info) => {
  app.fixture.setMode('unavailable');
  await page.goto(app.appOrigin + paths.historyPage);
  await expect(page.getByRole('heading', { name: '更正历史不可用', exact: true })).toBeVisible();
  await expect(page.getByText(values.baselineNote, { exact: true })).toHaveCount(0);
  await expect(page.getByText(values.effectiveNote, { exact: true })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('BROWSER_PRIVATE_UPSTREAM_ERROR');
  const retry = page.getByRole('link', { name: '重新读取此历史', exact: true });
  await expect(retry).toHaveAttribute('href', paths.historyPage);
  // A new Document instance distinguishes native reload from cached Next navigation.
  await page.evaluate(() => { (window as Window & { fixtureDocumentMarker?: boolean }).fixtureDocumentMarker = true; });
  const before = app.fixture.requests.filter(request => request.url === paths.historyApi).length;
  app.fixture.setMode('ready');
  // Merely making the fixture healthy must not replace the displayed failure.
  await expect(page.getByRole('heading', { name: '更正历史不可用', exact: true })).toBeVisible();
  await retry.click();
  await expect(page.getByRole('heading', { name: '生产批次更正历史', exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as Window & { fixtureDocumentMarker?: boolean }).fixtureDocumentMarker)).toBeUndefined();
  expect(app.fixture.requests.filter(request => request.url === paths.historyApi).length).toBeGreaterThan(before);
  await expect(page.getByText(values.baselineNote, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Batch correction history', exact: true })).toBeVisible();
  await info.attach('synthetic-history-recovered-english', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
});
