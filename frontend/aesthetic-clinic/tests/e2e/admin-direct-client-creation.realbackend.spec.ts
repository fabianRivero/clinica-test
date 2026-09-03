import { test, expect, type Route, type Request } from '@playwright/test';

/**
 * No-mock E2E contract test for the direct-client creation wizard.
 *
 * Why this spec exists: the original `admin-direct-client-creation.spec.ts`
 * mocked every backend call via `context.route(...).fulfill(...)`, so the
 * "3/3 passed" run validated the frontend against its own URL templates
 * (which were wrong). When the URL family diverged from
 * `/api/admin/clientes/directo/<int:direct_id>/<step>/`, the mocked
 * fixtures simply honoured the wrong URLs and never reached Django.
 *
 * This spec flips the strategy:
 *   - Stub ONLY endpoints that own the running session and unrelated
 *     auxiliary reads (login redirect, listing prefill) so the wizard
 *     can mount and navigate without pulling a full fixture.
 *   - Let the wizard speak to the real direct-mode URLs
 *     (`/api/admin/clientes/directo/initialize/` and the
 *     `/<int:direct_id>/<step>/` family) **unmocked**. If the frontend
 *     service functions emit the wrong path, the request 404s and the
 *     test fails loudly.
 *
 * Backend prerequisite: the Vite dev server is up at the
 * `baseURL` configured in `playwright.config.ts` and the Django backend
 * is reachable on the same origin. The global setup script seeds the
 * local DB, so the admin user below is available.
 *
 * This test focuses on Step 1 (user step) — that's the endpoint the
 * verify-report pinned as 404. The other steps use the same URL
 * template so passing step 1 implies the rest work. The wizard is
 * intentionally NOT driven past step 1 here; that keeps the test short
 * and avoids depending on biometric capture + medical PDF upload, which
 * have their own setup stories.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

async function login(page: any, context: any) {
  await context.clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

test.describe('Direct client creation wizard — real-backend URL contract', () => {
  // The standard ``npx playwright test`` invocation would race the
  // ``global-setup.ts`` DB reset against the live server. To run this
  // contract test, set ``PLAYWRIGHT_INCLUDE_REAL_BACKEND=1`` and use
  // ``playwright.realbackend.config.ts`` (which skips the global
  // reset). Without the env var we no-op so the default suite stays
  // stable.
  test.skip(
    !process.env.PLAYWRIGHT_INCLUDE_REAL_BACKEND,
    'Skipped: set PLAYWRIGHT_INCLUDE_REAL_BACKEND=1 to run against the live backend',
  );

  // Negative first: prove the OLD buggy URLs are 404. This locks the
  // test against accidental regressions to the wrong path template.
  test('Frontend NEVER calls the URLs that omit direct_id (404 lock)', async ({
    page,
    context,
  }) => {
    await login(page, context);

    // Track EVERY URL the wizard fires against `/api/admin/clientes/directo/`.
    // If a malformed URL (one missing the draft id segment) gets emitted,
    // Playwright will receive the upstream 404 from Django and we capture
    // it in `badUrls`.
    const badUrls: { url: string; status: number }[] = [];
    page.on('response', (response) => {
      const url = response.url();
      if (
        url.includes('/api/admin/clientes/directo/') &&
        response.status() === 404
      ) {
        badUrls.push({ url, status: response.status() });
      }
    });

    // Stub the destinations the wizard lands on AFTER finalize (the
    // client detail page mounts several read endpoints). Keeping them
    // stubbed so the test stays focused on the direct-mode URL family.
    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ clients: [] }),
      });
    });

    // Drive the wizard to step 1 submit. We let it call the real
    // initialize endpoint (which returns 201 + a `draftId`).
    //
    // The wizard's useEffect fires the initialize POST as soon as the
    // mount lands; we register the response listener BEFORE the
    // navigation so we don't miss a response that races us.
    const initializeResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/admin/clientes/directo/initialize/') &&
        response.request().method() === 'POST',
      { timeout: 30000 },
    );

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible({
      timeout: 15000,
    });

    const initResponse = await initializeResponsePromise;
    expect(initResponse.status()).toBeLessThan(400);

    // Fill step 1 with a unique synthetic CI so we don't collide with
    // any existing fixture data.
    const uniqueCi = `7${Date.now().toString().slice(-7)}`;
    const uniqueUsername = `nfi_${Date.now()}`;
    await page.fill('input[name="primerNombre"]', 'No');
    await page.fill('input[name="apellidoPaterno"]', 'Mock');
    await page.fill('input[name="ci"]', uniqueCi);
    await page.fill('input[name="username"]', uniqueUsername);
    await page.fill('input[name="email"]', `${uniqueUsername}@test.com`);
    await page.fill('input[name="telefono"]', '70000099');
    await page.fill('input[name="fechaNacimiento"]', '1990-01-01');
    await page.fill('input[name="direccionDomicilio"]', 'Calle Real 1');
    await page.fill('input[name="ocupacion"]', 'Test');
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.first().fill('test1234');
    await passwordInputs.nth(1).fill('test1234');
    await page.click('button:has-text("Guardar y continuar")');

    // Wait for the paso-1 POST. The frontend emits
    // `/api/admin/clientes/directo/<draftId>/paso-1/` — if that 404s the
    // contract is broken and this assertion fails.
    const step1Response = await page.waitForResponse(
      (response) =>
        /\/api\/admin\/clientes\/directo\/\d+\/paso-1\//.test(response.url()) &&
        response.request().method() === 'POST',
      { timeout: 10000 },
    );
    expect(
      step1Response.status(),
      `paso-1 must resolve to a non-404, but got ${step1Response.status()} for ${step1Response.url()}`,
    ).toBeLessThan(400);
    expect(step1Response.url()).toMatch(/\/api\/admin\/clientes\/directo\/\d+\/paso-1\//);

    // None of the direct URLs should have returned 404. If any did,
    // surface them so debugging is obvious.
    expect(
      badUrls,
      `Direct URLs returned 404:\n${badUrls.map((u) => `- ${u.url}`).join('\n')}`,
    ).toEqual([]);
  });
});
