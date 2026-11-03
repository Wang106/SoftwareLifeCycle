'use strict';
// Preserve the original verified candidate, sandbox, zero retries and browser policy.
// This separate test-only component suite never replaces the eight Next journeys.
const path = require('node:path');
const original = require('../e2e/playwright.config.cjs');
module.exports = {
  ...original,
  testDir: __dirname,
  testMatch: ['authorization-approval.spec.ts'],
  outputDir: path.resolve(__dirname, '../component-browser-results/artifacts'),
  reporter: [['list'], ['json', { outputFile: path.resolve(__dirname, '../component-browser-results/results.json') }]],
};
