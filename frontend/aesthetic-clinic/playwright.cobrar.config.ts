import { defineConfig, devices } from '@playwright/test';

/**
 * Local config for `admin-cobrar-cita.spec.ts` only. Bypasses the
 * project's `globalSetup` (which reseeds the local DB and currently
 * fails on a pre-existing PagoRealizado validation error in
 * `seed_branch_test_scenarios.py`, unrelated to this change).
 *
 * The spec mocks every backend endpoint it touches with `context.route`,
 * so it does not depend on DB state at all. Both the Vite dev server
 * (5173) and the Django backend (8000) must be running for the
 * `/login` round-trip to work.
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /admin-cobrar-cita\.spec\.ts$/,
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 1,
  reporter: 'line',
  use: {
    baseURL: 'http://localhost:5173',
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
