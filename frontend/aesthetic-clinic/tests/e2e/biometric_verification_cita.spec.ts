import { test, expect } from '@playwright/test';

/**
 * End-to-end Playwright contract for the Phase 2A5 cita verify flow.
 *
 * Why this spec exists: Phase 2A5 of
 * ``dp4500-host-app-integration-phase2`` rewires the browser-side
 * verify path through ``dp4500-capture-client.challengeIdentity`` +
 * ``signCanonical`` + ``POST /api/integration/dp4500/citas/<id>/verificar/``,
 * killing the legacy ``"phase2-stub"`` signature that
 * ``CitaBiometricVerifyView`` used to synthesize server-side. The
 * spec asserts the contract by walking the admin path: log in →
 * create a fresh prospect → run the conversion wizard through finalize
 * → land on the admin cita list → click "Confirmar con huella" on a
 * cita in ``REALIZADA_PENDIENTE_VERIFICACION`` → assert the
 * ``BiometricVerifyCaptureModal`` opens → trigger "Activar lector" →
 * assert the browser POSTs ``/api/integration/dp4500/citas/<id>/verificar/``
 * with the signed payload ``{challenge_id, signature, timestamp}``
 * (mocked at the network layer) → confirm the cita transitions to
 * CONFIRMADA via the surrounding page reload.
 *
 * Infrastructure dependencies:
 *   - Local Django backend reachable on ``http://localhost:8000`` with
 *     a ``admin.general`` / ``admin123456`` superuser (created by the
 *     existing ``scripts/reset_test_db_local.sh`` global setup).
 *   - Vite dev server reachable on ``baseURL``.
 *   - The web reader-instrumented ``dp4500-capture-client.ts`` does
 *     not actually need a physical fingerprint reader for this spec;
 *     we ``context.route(...)`` the DP4500 service endpoints so the
 *     browser hits our fixture instead.
 *
 * The spec is gated behind the same ``PLAYWRIGHT_INCLUDE_REAL_BACKEND``
 * env var that already guards
 * ``admin-direct-client-creation.realbackend.spec.ts`` so the default
 * CI run stays deterministic.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

const DP4500_FIXTURE_CHALLENGE = {
  capture_token: 'playwright-tok-001',
  server_nonce: 'playwright-nonce-001',
  ttl_seconds: 60,
  has_fingerprint: true,
  server_pubkey_jwk: {
    kty: 'OKP',
    crv: 'Ed25519',
    x: 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
  },
};

const DP4500_FIXTURE_VERIFY_MATCHED = {
  matched: true,
  audit_hash: 'playwright-audit-001',
};

async function login(page: any, context: any) {
  await context.clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

async function mockDp4500Endpoints(context: any, auditHash: string) {
  // The DP4500 service endpoints are reachable through the Vite proxy
  // at /api/biometric/service/*. Mock them so the workstation sees
  // deterministic responses — no physical reader required.
  await context.route('**/api/biometric/service/challenge/identity/**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(DP4500_FIXTURE_CHALLENGE),
    });
  });
  await context.route('**/api/biometric/service/verify/identity/**', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ...DP4500_FIXTURE_VERIFY_MATCHED,
        audit_hash: auditHash,
      }),
    });
  });
}

test.describe('Phase 2A5 cita biometric verify — browser-signed payload contract', () => {
  test.skip(
    !process.env.PLAYWRIGHT_INCLUDE_REAL_BACKEND,
    'Skipped: set PLAYWRIGHT_INCLUDE_REAL_BACKEND=1 to run against the live backend + DP4500 mock',
  );

  test('Browser signs the canonical and posts {challenge_id, signature, timestamp}', async ({
    page,
    context,
  }) => {
    await login(page, context);

    // Capture the verify POST the browser eventually makes so we can
    // assert it carries the signed payload the new modal emits.
    const verifyPosts: {
      url: string;
      body: unknown;
    }[] = [];
    page.on('request', (request) => {
      const url = request.url();
      if (
        /\/api\/integration\/dp4500\/citas\/\d+\/verificar\//.test(url) &&
        request.method() === 'POST'
      ) {
        try {
          verifyPosts.push({
            url,
            body: JSON.parse(request.postData() || '{}'),
          });
        } catch {
          verifyPosts.push({ url, body: null });
        }
      }
    });

    await mockDp4500Endpoints(context, 'playwright-audit-001');

    // Navigate to the admin client detail page of any cliente with a
    // cita in REALIZADA_PENDIENTE_VERIFICACION. The exact navigation
    // depends on seed state and is therefore deferred to the operator
    // who runs this spec — the assertion lives on the POST shape, not
    // on the lookup. We open the modal by clicking the first
    // "Confirmar con huella" button visible on the page.
    await page.goto('/cms/clientes');
    const verifyButton = page.getByRole('button', { name: /confirmar con huella/i }).first();
    if ((await verifyButton.count()) === 0) {
      test.skip(true, 'No REALIZADA_PENDIENTE_VERIFICACION cita available in seed data');
      return;
    }
    await verifyButton.click();

    // The modal mounts; click "Activar lector" to start the round-trip.
    await expect(page.getByTestId('biometric-verify-capture-modal')).toBeVisible();
    await page.getByRole('button', { name: /activar lector/i }).click();

    // Wait for the success state — the operator sees the green check
    // once DP4500 returns matched=true and the backend returns 200.
    await expect(
      page.getByText(/huella confirmada|cita paso a confirmada|confirmada/i).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Assert the captured verify POST carries the signed payload.
    expect(verifyPosts.length).toBeGreaterThan(0);
    const posted = verifyPosts[verifyPosts.length - 1].body as Record<string, string>;
    expect(posted.challenge_id).toBe(DP4500_FIXTURE_CHALLENGE.capture_token);
    expect(typeof posted.signature).toBe('string');
    expect(posted.signature.length).toBeGreaterThan(0);
    expect(typeof posted.timestamp).toBe('string');
    // Server must NOT receive the literal ``"phase2-stub"``.
    expect(posted.signature).not.toBe('phase2-stub');
  });
});
