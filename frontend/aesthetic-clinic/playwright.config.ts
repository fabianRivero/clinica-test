import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/global-setup.ts',
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 1,
  // `forbidOnly` mirrors the dedicated `playwright.suspension.config.ts`
  // and the standard CI guard pattern: if a developer accidentally
  // commits `test.only`, the run fails fast instead of skipping the
  // rest of the suite.
  forbidOnly: !!process.env.CI,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173', // Cambiar a 5174 si es necesario
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
