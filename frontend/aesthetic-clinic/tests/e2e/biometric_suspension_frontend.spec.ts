import { test, expect, type BrowserContext, type Page, type Route, type Request } from '@playwright/test';

/**
 * E2E coverage for the biometric-suspension build flag
 * (`VITE_BIOMETRIC_SUSPENDED=true`).
 *
 * Asserts:
 *  (a) The `api/biometric/agents/` heartbeat poll is never issued
 *      while the flag is on.
 *  (b) The "Lector de huellas sin conexion" offline banner is replaced
 *      by the explicit "Huella biometrica suspendida" notice.
 *  (c) The "Confirmar con huella" button is not rendered even when the
 *      backend reports `canConfirmBiometric: true`.
 *  (d) The `BiometricVerifyCaptureModal` never mounts while suspended.
 *  (e) The prospect-conversion wizard advances through step 4
 *      (biometric) and the **step-5 control ("Finalizar")** is shown
 *      without firing any biometric endpoint and without the capture
 *      affordance.
 *  (f) Manual non-biometric actions remain visible on the client
 *      detail page so the operator can finish the appointment flow.
 *
 * Must be run via the dedicated config
 * `playwright.suspension.config.ts` (npm script
 * `test:e2e:suspension`) which owns BOTH the Django backend and the
 * Vite dev server with `VITE_BIOMETRIC_SUSPENDED=true` exported. The
 * default `playwright.config.ts` is left untouched so the rest of the
 * suite continues to run with the flag off.
 *
 * Why we do NOT modify the stale `biometric_verification.spec.ts` /
 * `biometric_enrollment.spec.ts`:
 *  - Their `login()` helper asserts `/\/admin/` but the current app
 *    redirects to `/cms` after login. The mismatch is a pre-existing
 *    issue that fails those specs before any of this code runs. The
 *    fix belongs to a separate Playwright hygiene change — touching
 *    them here would mix PRs and obscure the suspension contract.
 *  - The new specs in this file use `/\/(admin|cms)/` so they pass
 *    under either redirect target.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

async function login(page: Page, context: BrowserContext): Promise<void> {
  await context.clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

/**
 * Classified recorder: a single route handler per biometric URL pattern
 * so precedence is unambiguous. Routes push a tagged entry to the
 * shared recorders and always answer with the suspended payload so
 * any accidental call from the page is visible to the test.
 */
function guardBiometricSurface(
  context: BrowserContext,
  recorders: {
    agentList: string[];
    anyBiometric: string[];
  },
): Promise<void> {
  return context.route(/\/api\/biometric\//, async (route: Route, request: Request) => {
    const url = request.url();
    recorders.anyBiometric.push(`${request.method()} ${url}`);
    if (/\/api\/biometric\/agents\/?$/.test(url)) {
      recorders.agentList.push(`${request.method()} ${url}`);
    }
    await route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'BIOMETRIC_SUSPENDED (test guard)', code: 'BIOMETRIC_SUSPENDED' }),
    });
  });
}

const emptyMedicalConfig = () => ({
  procedureId: null,
  procedureName: '',
  sections: [],
  antecedentes: [],
  implantes: [],
  cirugias: [],
  tiposPiel: [],
  gradosDeshidratacion: [],
  grosoresPiel: [],
  patologiasCutaneas: [],
});

test.describe('Biometric suspension — frontend suppression (VITE_BIOMETRIC_SUSPENDED=true)', () => {
  test('Client detail: no biometric requests, suspended banner, manual-only actions', async ({
    page,
    context,
  }) => {
    const recorders = { agentList: [], anyBiometric: [] };
    await guardBiometricSurface(context, recorders);

    await login(page, context);
    // Stable client id from the seeded DB. The test does not depend on
    // biometric enrollment — only on the page shell rendering so the
    // suspended banner can appear above the appointment table.
    await page.goto('/cms/clientes/1');
    await expect(page.getByText(/Panel administrativo/i)).toBeVisible();

    // (a) Heartbeat poll and any biometric call must be absent.
    expect(recorders.agentList, 'agents endpoint should not be polled while suspended').toEqual([]);
    expect(recorders.anyBiometric, 'no biometric endpoint may be hit while suspended').toEqual([]);

    // (b) Suspended notice is visible; offline banner is not.
    await expect(page.getByTestId('biometric-suspended-banner')).toBeVisible();
    await expect(page.getByText(/Lector de huellas sin conexion/i)).toHaveCount(0);

    // (d) Verify modal never mounts.
    await expect(page.getByTestId('biometric-verify-capture-modal')).toHaveCount(0);

    // (c) The "Confirmar con huella" button is hidden everywhere on the
    //     page (sessions card, appointment table).
    await expect(page.getByRole('button', { name: /Confirmar con huella/i })).toHaveCount(0);

    // (f) Manual actions remain available so the operator can finish
    //     the appointment flow without biometric verification. Exact
    //     button depends on the seed data.
    await expect(
      page.getByRole('button', {
        name: /Reactivar|Reprogramar|A\u00f1adir procedimiento|Confirmar cita|Cancelar reserva/,
      }).first(),
    ).toBeVisible();
  });

  test('Prospect conversion: wizard advances from step 4 to step 5 without biometric capture', async ({
    page,
    context,
  }) => {
    const recorders = { agentList: [], anyBiometric: [] };
    await guardBiometricSurface(context, recorders);

    // Build a draft that has steps 1-3 already complete so the wizard
    // starts at step 4 (biometric). Every save endpoint flips the
    // matching `stepXCompleted` flag and returns the updated draft so
    // the stepper can advance. The conversion stub is suspended-aware:
    // it accepts an empty template (the suspension contract) and
    // returns the same response shape the live backend would.
    let draft = {
      currentStep: 4,
      stepUserCompleted: true,
      stepOperationCompleted: true,
      stepMedicalCompleted: true,
      stepBiometricCompleted: false,
      userData: {} as Record<string, unknown>,
      operationData: {} as Record<string, unknown>,
      medicalData: {} as Record<string, unknown>,
      biometricData: {
        provider: 'DIGITAL_PERSONA',
        template: '',
        quality: 0,
        deviceSerial: '',
        consentAccepted: true,
        capturedAt: '',
      },
    };
    const basePayload = () => ({
      prospect: {
        id: 1,
        name: 'Prospecto',
        phone: '0',
        interest: '-',
        state: '-',
        registeredBy: '-',
        createdAt: '-',
      },
      client: null,
      serviceConfigs: [],
      operationStates: [],
      medicalConfig: emptyMedicalConfig(),
    });

    await context.route(
      /\/api\/admin\/prospectos\/\d+\/conversion\//,
      async (route: Route, request: Request) => {
        if (request.method() === 'GET') {
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...basePayload(), draft }),
          });
          return;
        }
        if (request.method() === 'POST') {
          // POST to /paso-4/ (or any step save) advances the matching
          // completion flag. The wizard reads the response and bumps
          // `activeStep`, so we model that here. While the build flag
          // is on, the hook allows an empty biometric template — we
          // reflect that by accepting whatever biometricData the page
          // sent and just flipping the completion flag.
          if (/paso-4\//.test(request.url())) {
            draft = { ...draft, stepBiometricCompleted: true, currentStep: 5 };
          }
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...basePayload(), draft }),
          });
          return;
        }
        await route.fallback(request);
      },
    );
    // The conversion wizard calls `getAdminPayments(month, year)` which
    // hits `/api/admin/pagos/` (Spanish), not `/api/admin/payments/`.
    // Without this stub the wizard would surface a real QR config (or
    // a 4xx) on the step 5 page.
    await context.route(/\/api\/admin\/pagos\/?(\?.*)?$/, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ paymentQrConfig: null }),
      });
    });

    await login(page, context);
    await page.goto('/cms/prospectos/1/convertir');

    // The wizard renders step 4 (biometric) on first paint with the
    // suspended banner. Web-first assertion waits for visibility.
    await expect(page.getByTestId('biometric-suspended-banner')).toBeVisible();
    await expect(page.getByRole('button', { name: /Capturar huella/i })).toHaveCount(0);

    // Save the (deliberately empty) biometric step. The hook should
    // accept it without a captured template because the build flag is
    // on, and the wizard advances to step 5.
    await page.getByRole('button', { name: /Guardar y continuar/i }).click();

    // (e) Step 5 ("Primer pago") is reachable — confirms the wizard
    //     actually transitioned, not just re-rendered. The page
    //     heading and the step-5 finalization button are the actual
    //     step-5 controls:
    //       - heading: `ConversionStepPayment.tsx` renders `Primer pago`.
    //       - submit button: `ConversionStepPayment.tsx:96` renders
    //         `Confirmar pago y finalizar`.
    await expect(page.getByRole('heading', { name: /Primer pago/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /Confirmar pago y finalizar/i })).toBeVisible();

    // The save round-trip fired, but the test guard confirms no
    // biometric endpoint was ever hit.
    expect(recorders.anyBiometric, 'no biometric endpoint may be hit while suspended').toEqual([]);
    expect(recorders.agentList, 'agents endpoint should not be polled while suspended').toEqual([]);
  });
});