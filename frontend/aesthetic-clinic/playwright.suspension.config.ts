import { defineConfig, devices } from '@playwright/test';

/**
 * Dedicated Playwright config for the biometric-suspension suite.
 *
 * Why a separate config:
 *  - The default config (`playwright.config.ts`) relies on a
 *    pre-started dev server and inherits whatever
 *    `VITE_BIOMETRIC_SUSPENDED` is baked into the local `.env`
 *    (default `false`).
 *  - The suspension suite asserts the build-time flag is `true`, so it
 *    must own a dev server with `VITE_BIOMETRIC_SUSPENDED=true`
 *    exported into the Vite process.
 *  - Keeping this config separate prevents the flag from leaking into
 *    the rest of the e2e suite (which still needs flag=false).
 *
 * Server lifecycle (this config owns BOTH processes):
 *  - Vite dev server on :5173 with `VITE_BIOMETRIC_SUSPENDED=true`
 *    baked into the bundle.
 *  - Django `manage.py runserver` on :8000 — the global setup
 *    (`tests/global-setup.ts`) resets the SQLite test DB before any
 *    test runs, so the suite hits real auth + CSRF endpoints.
 *  - `reuseExistingServer: !process.env.CI` lets a developer launch
 *    either process manually for debugging.
 *  - `webServer` is an array (Playwright supports multiple entries);
 *    each entry waits for its own `url` before tests run.
 *
 * Usage:
 *   cd frontend/aesthetic-clinic
 *   npm run test:e2e:suspension
 */
export default defineConfig({
  testDir: './tests/e2e',
  testMatch: /biometric_suspension_frontend\.spec\.ts/,
  globalSetup: './tests/global-setup.ts',
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: false,
  workers: 1,
  // `forbidOnly` mirrors the existing project pattern (CI guard): if
  // a developer accidentally commits `test.only`, the run fails fast
  // instead of skipping the rest of the suite.
  forbidOnly: !!process.env.CI,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      // Django backend. The local-reset script in
      // `backend/scripts/reset_test_db_local.sh` runs as part of
      // `global-setup.ts` before the suite starts, so the DB is
      // re-seeded every run. The `env/bin/python` path is the
      // project-managed virtualenv; reusing the system interpreter
      // would fail because Django is not installed at the OS level.
      command: 'cd ../../backend && env/bin/python manage.py runserver 127.0.0.1:8000',
      url: 'http://127.0.0.1:8000/api/auth/csrf/',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
      env: {
        DJANGO_USE_LOCAL_DB: '1',
      },
    },
    {
      // Vite frontend with the suspension flag baked in.
      command: 'npx vite --port 5173 --host 127.0.0.1',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'ignore',
      stderr: 'pipe',
      env: {
        VITE_BIOMETRIC_SUSPENDED: 'true',
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});