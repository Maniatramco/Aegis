import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'walkthrough.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 720000,
  expect: { timeout: 20000 },
  reporter: 'list',
  use: {
    baseURL: process.env.AEGIS_TEST_BASE_URL || 'http://127.0.0.1:3000',
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
});
