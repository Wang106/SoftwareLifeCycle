const path = require('node:path');
const { defineConfig } = require('@playwright/test');

// Only the fixed isolated candidate checked by CI; no arbitrary executable override.
if (!process.env.RUNNER_TEMP || !path.isAbsolute(process.env.RUNNER_TEMP)) {
  throw new Error('An absolute RUNNER_TEMP is required for the verified Chrome candidate');
}
const chromeExecutable = path.join(require('node:fs').realpathSync(process.env.RUNNER_TEMP),
  'slc-official-chrome/Google Chrome.app/Contents/MacOS/Google Chrome');

// Synthetic loopback only. A browser that cannot launch with its sandbox enabled
// must fail this job; there is deliberately no unsandboxed fallback.
module.exports = defineConfig({
  testDir: '.',
  testMatch: ['readonly.spec.ts', 'page-loading.spec.ts'],
  fullyParallel: false,
  workers: 1,
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  forbidOnly: true,
  outputDir: path.resolve(__dirname, '../browser-results/artifacts'),
  reporter: [['list'], ['json', { outputFile: path.resolve(__dirname, '../browser-results/results.json') }]],
  use: {
    browserName: 'chromium',
    headless: true,
    launchOptions: { executablePath: chromeExecutable, chromiumSandbox: true },
    serviceWorkers: 'block',
    acceptDownloads: false,
    viewport: { width: 1280, height: 900 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
});
