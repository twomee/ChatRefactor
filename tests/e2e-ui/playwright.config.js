// @ts-check
const { defineConfig } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://localhost:8090';
const WS_BASE = BASE_URL.replace(/^http/, 'ws');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60_000,
  retries: 1,
  workers: 1,
  reporter: [['html', { open: 'never' }], ['list']],

  expect: {
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.01,
    },
  },

  snapshotPathTemplate: '{testDir}/../snapshots/{arg}{ext}',

  projects: [
    {
      name: 'setup',
      testDir: '.',
      testMatch: /global\.setup\.js/,
    },
    {
      name: 'e2e',
      dependencies: ['setup'],
      use: {
        baseURL: BASE_URL,
        browserName: 'chromium',
        headless: true,
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
        trace: 'retain-on-failure',
        actionTimeout: 10_000,
        navigationTimeout: 15_000,
      },
    },
  ],
});
