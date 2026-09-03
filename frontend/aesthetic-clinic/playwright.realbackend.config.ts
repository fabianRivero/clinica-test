import { defineConfig, devices } from '@playwright/test';

// LOCAL-ONLY CONFIG — used to run the no-mock E2E spec against the
// already-running dev servers. Skips the global DB-reset hook because
// reset_test_db_local.sh currently fails on a pre-existing seeder
// validation error unrelated to this change.
//
// This file is a temporary harness; do not commit it long-term.
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /admin-direct-client-creation\.realbackend\.spec\.ts/,
  timeout: 60000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
