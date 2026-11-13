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
  const activeNavigation = page.locator('.nav a[aria-current="page"]');
  await expect(activeNavigation).toHaveCount(1);
  await expect(activeNavigation).toHaveAttribute('href', '/production/batches');
  const historyLink = page.getByRole('link', { name: '查看更正历史', exact: true });
  await expect(historyLink).toHaveAttribute('href', paths.historyPage);
  await historyLink.click();
  await expect(page).toHaveURL(app.appOrigin + paths.historyPage);
  await expect(activeNavigation).toHaveCount(1);
  await expect(activeNavigation).toHaveAttribute('href', '/deployments');
  await expect(page.getByRole('heading', { name: '生产批次更正历史', exact: true })).toBeVisible();
  const main = page.getByRole('main');
  const baseline = main.locator('section').filter({ has: page.getByRole('heading', { name: '原始记录基线', exact: true }) });
  const effective = main.locator('section').filter({ has: page.getByRole('heading', { name: '当前有效记录事实', exact: true }) });
  await expect(baseline).toContainText(values.baselineNote);
  await expect(baseline).toContainText(values.baselineVersion);
  await expect(baseline).not.toContainText(values.effectiveNote);
  await expect(effective).toContainText(values.effectiveNote);
  await expect(effective).toContainText(values.effectiveVersion);
  await expect(effective).not.toContainText(values.baselineNote);

  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expect(activeNavigation).toHaveAttribute('href', '/deployments');
  await expect(page.getByRole('heading', { name: 'Recorded baseline', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Effective recorded facts', exact: true })).toBeVisible();
  expect((await context.cookies()).find(cookie => cookie.name === 'slc_language')?.value).toBe('en');
  await page.reload();
  await expect(activeNavigation).toHaveCount(1);
  await expect(activeNavigation).toHaveAttribute('href', '/deployments');
  await expect(page.getByRole('heading', { name: 'Batch correction history', exact: true })).toBeVisible();
  const englishBaseline = main.locator('section').filter({ has: page.getByRole('heading', { name: 'Recorded baseline', exact: true }) });
  const englishEffective = main.locator('section').filter({ has: page.getByRole('heading', { name: 'Effective recorded facts', exact: true }) });
  await expect(englishBaseline.getByText(values.baselineNote, { exact: true })).toBeVisible();
  await expect(englishBaseline).toContainText(values.baselineVersion);
  await expect(englishBaseline).not.toContainText(values.effectiveNote);
  await expect(englishEffective.getByText(values.effectiveNote, { exact: true })).toBeVisible();
  await expect(englishEffective).toContainText(values.effectiveVersion);
  await expect(englishEffective).not.toContainText(values.baselineNote);
  await info.attach('synthetic-history-english', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
  await page.getByRole('link', { name: 'Open controlled batch correction workbench', exact: true }).click();
  await expect(page.getByText('Batch correction submission is disabled or unavailable for this session.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Load private correction context', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Send confirmed batch correction', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Prepare batch correction', exact: true })).toHaveCount(0);

  // Existing creation forms must be reachable from Create without a catalog detour.
  // This remains preparation-only: the harness rejects every non-GET request.
  const createLink = page.locator('.appactions a[href="/create"]');
  await createLink.click();
  await expect(page.getByRole('heading', { name: 'Create lifecycle record', exact: true })).toBeVisible();
  await expect(page.locator('article.createcard-unavailable')).toHaveCount(3);
  await expect(page.locator('article.createcard-unavailable').filter({ hasText: 'Software Change Request' }))
    .toContainText('Creation form not implemented');
  await expect(page.getByText('File upload is not implemented. Resource references do not upload or store files.', { exact: true })).toBeVisible();
  await page.locator('.creategrid a[href="/releases/application/new"]').click();
  await expect(page.getByRole('heading', { name: 'Create application release draft', exact: true })).toBeVisible();
  await expect(page.getByText('Currently cannot save online. The public sample is read-only; real identity is not configured.', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Project UUID', { exact: true })).toBeEditable();
  await expect(page.getByLabel('Standard release UUID', { exact: true })).toBeEditable();
  await page.getByLabel('Version (maximum 100 characters)', { exact: true }).fill('SYNTHETIC-ASR-DRAFT');
  await expect(page.getByRole('button', { name: 'Submit empty DRAFT', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await expect(page.getByRole('heading', { name: '新建应用发布草稿', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '新建应用发布草稿', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Create application release draft', exact: true })).toBeVisible();
  await createLink.click();
  await expect(page).toHaveURL(app.appOrigin + '/create');
  await expect(page.getByRole('heading', { name: 'Create lifecycle record', exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(app.appOrigin + '/releases/application/new');
  await expect(page.getByRole('heading', { name: 'Create application release draft', exact: true })).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(app.appOrigin + '/create');
  await expect(page.getByRole('heading', { name: 'Create lifecycle record', exact: true })).toBeVisible();

  await page.evaluate(() => { (window as Window & { creationDocumentMarker?: boolean }).creationDocumentMarker = true; });
  for (const [operation, field] of [['test-release', 'testReleaseNo'], ['delivery', 'packageNo'], ['authorization', 'authorizationNo']]) {
    const href = '/commands?operation=' + operation;
    await page.locator('.creategrid a[href="' + href + '"]').click();
    await expect(page).toHaveURL(app.appOrigin + href);
    await expect(page.locator('form.commandform select').first()).toHaveValue(operation);
    await expect(page.locator('input[name="' + field + '"]')).toBeEditable();
    await page.locator('input[name="' + field + '"]').fill('SYNTHETIC-PREPARATION-ONLY');
    await expect(page.locator('input[name="' + field + '"]')).toHaveValue('SYNTHETIC-PREPARATION-ONLY');
    await expect(page.getByRole('button', { name: 'Send confirmed business request', exact: true })).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(app.appOrigin + '/create');
    await expect(page.locator('article.createcard-unavailable')).toHaveCount(3);
    await page.goForward();
    await expect(page).toHaveURL(app.appOrigin + href);
    await expect(page.locator('form.commandform select').first()).toHaveValue(operation);
    expect(await page.evaluate(() => (window as Window & { creationDocumentMarker?: boolean }).creationDocumentMarker)).toBe(true);
    await createLink.click();
    await expect(page).toHaveURL(app.appOrigin + '/create');
    await page.locator('.creategrid a[href="' + href + '"]').click();
    await expect(page.locator('form.commandform select').first()).toHaveValue(operation);
    await createLink.click();
    await expect(page).toHaveURL(app.appOrigin + '/create');
  }
  await page.getByRole('button', { name: '中文', exact: true }).click();
  await expect(page.locator('article.createcard-unavailable').filter({ hasText: '软件变更申请' })).toContainText('新建表单尚未实现');
  await expect(page.locator('.creategrid a[href="/releases/application/new"]').filter({ hasText: '应用发布' })).toContainText('打开填写表单');
  await expect(page.getByText('文件上传尚未实现；资源引用不会上传或存储文件。', { exact: true })).toBeVisible();
  await page.locator('.creategrid a[href="/commands?operation=test-release"]').click();
  await expect(page.locator('form.commandform select').first()).toHaveValue('test-release');
  await page.reload();
  await expect(page.locator('form.commandform select').first()).toHaveValue('test-release');
  await expect(page.locator('input[name="testReleaseNo"]')).toBeEditable();
  await expect(page.getByRole('button', { name: '发送已确认的业务请求', exact: true })).toHaveCount(0);
  await info.attach('synthetic-create-test-release-chinese', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
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
  const baseline = page.getByRole('main').locator('section').filter({ has: page.getByRole('heading', { name: '原始记录基线', exact: true }) });
  await expect(baseline.getByText(values.baselineNote, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'English', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Batch correction history', exact: true })).toBeVisible();
  await info.attach('synthetic-history-recovered-english', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' });
});
