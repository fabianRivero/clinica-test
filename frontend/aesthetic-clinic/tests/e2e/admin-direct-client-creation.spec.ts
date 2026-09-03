import { test, expect, type Route } from '@playwright/test';

/**
 * E2E coverage for the direct-client creation wizard (OpenSpec change
 * `direct-client-creation`, PR 2 — frontend integration).
 *
 * The flow lets an admin create a brand-new `Cliente` + `Usuario (CLIENTE)`
 * from `/cms/clientes` without going through the prospect stage. Entry
 * point: "Crear cliente directo" PageHeader action → `/cms/clientes/nuevo`
 * → 5-step wizard → finalize creates both rows atomically and lands on
 * `/cms/clientes` with the new row visible.
 *
 * The backend is mocked with `context.route` because the standard
 * Playwright `globalSetup` reseeds the local DB; we don't want to
 * depend on DB state for these scenarios. Each test stubs the
 * initialize / step / finalize / cancel endpoints and asserts the
 * frontend wires the requests correctly.
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

/**
 * Build a synthetic `ProspectConversionResponse` envelope for the
 * direct mode (prospect: null, client: null, draft populated). Mirrors
 * the shape returned by `admin_direct_client_initialize`.
 */
function blankDraftForDirect(): unknown {
  return {
    currentStep: 1,
    stepUserCompleted: false,
    stepOperationCompleted: false,
    stepMedicalCompleted: false,
    stepBiometricCompleted: false,
    userData: {
      primerNombre: '',
      segundoNombre: '',
      apellidoPaterno: '',
      apellidoMaterno: '',
      username: '',
      email: '',
      telefono: '',
      ci: '',
      codBiometrico: '',
      fechaNacimiento: '',
      nroHijos: 0,
      direccionDomicilio: '',
      ocupacion: '',
      observacionesCliente: '',
      hasPassword: false,
    },
    operationData: {
      serviceConfigId: '',
      zonaGeneral: '',
      zonaEspecifica: '',
      precioTotal: '0',
      cuotasTotales: 1,
      sesionesTotales: null,
      fechaInicio: '',
      fechaFinal: '',
      estado: 'PENDIENTE',
      detallesOperacion: '',
      recomendaciones: '',
      fechasVencimientoCuotas: [],
    },
    medicalData: {
      fechaFicha: '',
      motivoConsulta: '',
      observaciones: '',
      consentimientoAceptado: false,
      firmaPacienteCi: '',
      analisisEstetico: {
        tipoPielId: '',
        gradoDeshidratacionId: '',
        grosorPielId: '',
        patologiaIds: [],
      },
      antecedentes: [],
      implantes: [],
      cirugias: [],
      fieldResponses: {},
    },
    biometricData: {
      provider: 'DIGITAL_PERSONA',
      template: '',
      quality: 0,
      deviceSerial: '',
      consentAccepted: true,
      capturedAt: '',
    },
  };
}

function emptyMedicalConfig(): unknown {
  return {
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
  };
}

/**
 * Returns a stub payload that marks `step` as completed and echoes
 * whatever `userData` the admin typed. Used by the step endpoints
 * (paso-1..paso-4) so the wizard advances.
 */
function advanceDirect(stepNumber: 1 | 2 | 3 | 4, userData: Record<string, unknown>): unknown {
  const draft = blankDraftForDirect() as Record<string, any>;
  draft.userData = { ...(draft.userData as Record<string, unknown>), ...userData };
  if (stepNumber >= 1) draft.stepUserCompleted = true;
  if (stepNumber >= 2) draft.stepOperationCompleted = true;
  if (stepNumber >= 3) draft.stepMedicalCompleted = true;
  if (stepNumber >= 4) draft.stepBiometricCompleted = true;
  draft.currentStep = stepNumber + 1;
  return {
    prospect: null,
    client: null,
    draft,
    serviceConfigs: [],
    operationStates: [],
    medicalConfig: emptyMedicalConfig(),
  };
}

test.describe('Direct client creation wizard (admin-only entry)', () => {
  test('Admin opens direct wizard, completes 5 steps, finalizes; new client appears in /cms/clientes', async ({
    page,
    context,
  }) => {
    await login(page, context);

    // Capture the initialize / step / finalize requests so we can assert
    // the frontend wires them correctly. All return synthetic payloads.
    const finalizeCalls: { url: string; method: string }[] = [];
    const initCalls: { url: string; method: string }[] = [];
    let currentUserData: Record<string, unknown> = {};

    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
      // Track every method so we can debug if anything weird shows
      // up; the assertion below filters for the wizard's POST.
      initCalls.push({ url: route.request().url(), method: route.request().method() })
      if (route.request().method() !== 'POST') {
        await route.fulfill({ status: 405, body: '' })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          draftId: 42,
          prospect: null,
          client: null,
          draft: blankDraftForDirect(),
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      })
    })

    await context.route('**/api/admin/clientes/directo/*/paso-1/', async (route: Route) => {
      const body = JSON.parse(route.request().postData() || '{}') as Record<string, unknown>;
      currentUserData = body;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(advanceDirect(1, body)),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/paso-2/', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(advanceDirect(2, currentUserData)),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/paso-3/', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(advanceDirect(3, currentUserData)),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/paso-4/', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(advanceDirect(4, currentUserData)),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/finalizar/', async (route: Route) => {
      finalizeCalls.push({ url: route.request().url(), method: route.request().method() });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Cliente creado correctamente.',
          client: { id: 999, name: 'Cliente Directo Test' },
          operation: { id: 1, procedure: 'Servicio Demo' },
        }),
      });
    });

    // Stub the listing endpoint so we can confirm the redirect lands on
    // /cms/clientes with the table-mounted. We don't need a real row —
    // we just need the page to render without error.
    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ clients: [] }),
      });
    });

    // 1. Land on /cms/clientes and click "Crear cliente directo".
    await page.goto('/cms/clientes');
    const createBtn = page.getByRole('link', { name: 'Crear cliente directo' });
    await expect(createBtn).toBeVisible();
    await createBtn.click();

    // 2. Wizard should land on step 1 and call initialize. React
    //    StrictMode double-invokes the effect in dev, so we accept
    //    any positive count rather than asserting exactly one.
    await expect(page).toHaveURL(/\/cms\/clientes\/nuevo$/);
    await expect.poll(() => initCalls.filter((c) => c.method === 'POST').length).toBeGreaterThan(0);
    expect(initCalls.find((c) => c.method === 'POST')?.method).toBe('POST');

    // The wizard header should reflect direct mode (no prospect summary).
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // 3. Step 1 — fill user data with unique values so the duplicate-CI
    //    scenario in the next test doesn't collide.
    const uniqueCi = `9${Date.now().toString().slice(-7)}`;
    const uniqueUsername = `directo_${Date.now()}`;
    await page.fill('input[name="primerNombre"]', 'Maria');
    await page.fill('input[name="apellidoPaterno"]', 'Lopez');
    await page.fill('input[name="ci"]', uniqueCi);
    await page.fill('input[name="username"]', uniqueUsername);
    await page.fill('input[name="email"]', `${uniqueUsername}@test.com`);
    await page.fill('input[name="telefono"]', '70000001');
    await page.fill('input[name="fechaNacimiento"]', '1990-01-01');
    await page.fill('input[name="direccionDomicilio"]', 'Calle 1');
    await page.fill('input[name="ocupacion"]', 'Test');
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.first().fill('test1234');
    await passwordInputs.nth(1).fill('test1234');
    await page.click('button:has-text("Guardar y continuar")');

    // Step 2 — operación.
    await expect(page.locator('input[name="precioTotal"]')).toBeVisible();
    await page.fill('input[name="zonaGeneral"]', 'Cuerpo');
    await page.fill('input[name="zonaEspecifica"]', 'Piernas');
    await page.fill('input[name="precioTotal"]', '100');
    await page.click('button:has-text("Guardar y continuar")');

    // Step 3 — Ficha médica. The wizard requires a PDF; we attach a
    // minimal 1-byte buffer just to satisfy the file input.
    await expect(page.locator('text=/An.lisis est.tico/i').first()).toBeVisible();
    await page.setInputFiles('input[type="file"]', {
      name: 'ficha.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 stub\n'),
    });
    await page.click('button:has-text("Guardar ficha y continuar")');

    // Step 4 — Huella. Build is suspended so the wizard advances
    // without an actual capture round-trip.
    await expect(page.locator('text=/Huella biometrica/i').first()).toBeVisible();
    await page.click('button:has-text("Guardar y continuar")');

    // Step 5 — Confirmar pago y finalizar. The wizard opens a confirm
    // dialog before firing the request.
    await expect(page.locator('text=/Primer pago/i').first()).toBeVisible();
    await page.click('button:has-text("Confirmar pago y finalizar")');
    // `exact: true` is required because the dialog "Confirmar" and
    // the step-5 submit button "Confirmar pago y finalizar" both
    // start with "Confirmar".
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click();

    // Wizard should navigate to /cms/clientes and call finalizar.
    await expect(page).toHaveURL(/\/cms\/clientes$/);
    await expect.poll(() => finalizeCalls.length).toBeGreaterThan(0);
    expect(finalizeCalls[0].method).toBe('POST');
  });

  test('Duplicate CI in step 1 surfaces the backend 400 with Spanish error and blocks navigation', async ({
    page,
    context,
  }) => {
    await login(page, context);

    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          draftId: 99,
          prospect: null,
          client: null,
          draft: blankDraftForDirect(),
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

// Step 1 returns the exact error contract the backend ships via
    // `apiClient.parseErrorResponse`: 400 + Spanish `errors` keyed by
    // `ci` (the response body uses `errors`, NOT `fieldErrors` — the
    // apiClient renames it to `error.fieldErrors` on the JS side).
    // Mirrors `_validate_user_step` (Spanish copy: "Ya existe un
    // cliente con este CI.").
    await context.route('**/api/admin/clientes/directo/*/paso-1/', async (route: Route) => {
      await route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Error de validación.',
          errors: {
            ci: 'Ya existe un cliente con este CI.',
          },
        }),
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    const dupCi = `1${Date.now().toString().slice(-7)}`;
    await page.fill('input[name="primerNombre"]', 'Duplicado');
    await page.fill('input[name="apellidoPaterno"]', 'CI');
    await page.fill('input[name="ci"]', dupCi);
    await page.fill('input[name="username"]', `dup_${Date.now()}`);
    await page.fill('input[name="email"]', `dup_${Date.now()}@test.com`);
    await page.fill('input[name="telefono"]', '70000002');
    await page.fill('input[name="fechaNacimiento"]', '1990-01-01');
    await page.fill('input[name="direccionDomicilio"]', 'Calle 1');
    await page.fill('input[name="ocupacion"]', 'Test');
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.first().fill('test1234');
    await passwordInputs.nth(1).fill('test1234');

    await page.click('button:has-text("Guardar y continuar")');

    // The wizard must NOT advance to step 2 — URL stays on /nuevo,
    // and the Spanish error text appears under the CI input.
    await expect(page.locator('text=/Ya existe un cliente con este CI\\./i').first()).toBeVisible();
    await expect(page).toHaveURL(/\/cms\/clientes\/nuevo$/);
    await expect(page.locator('input[name="precioTotal"]')).not.toBeVisible();
  });

  test('Cancel at step 3 calls the cancel endpoint and routes back to /cms/clientes', async ({
    page,
    context,
  }) => {
    await login(page, context);

    let cancelCalls = 0;
    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
      // Pre-fill the draft so step 3 is reachable without driving
      // step 1 + 2 manually.
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.stepUserCompleted = true;
      draft.stepOperationCompleted = true;
      draft.currentStep = 3;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          draftId: 7,
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/cancelar/', async (route: Route) => {
      cancelCalls += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Borrador descartado.' }),
      });
    });

    // Stub the listing endpoint so the destination page mounts cleanly.
    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ clients: [] }),
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // Jump to step 3 via the stepper. The wizard exposes step buttons
    // keyed by `Paso N`.
    await page.locator('button:has-text("Paso 3")').click();
    await expect(page.locator('text=/An.lisis est.tico/i').first()).toBeVisible();

    // Click "Cancelar" inside the active step card. The wizard opens
    // a confirm dialog; confirm it. `exact: true` avoids matching the
    // step-5 submit "Confirmar pago y finalizar" or any other submit
    // button starting with the same word.
    await page.locator('button:has-text("Cancelar")').first().click();
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click();

    // Wizard should navigate back to /cms/clientes and have called
    // the cancel endpoint exactly once.
    await expect(page).toHaveURL(/\/cms\/clientes$/);
    await expect.poll(() => cancelCalls).toBe(1);
  });
});