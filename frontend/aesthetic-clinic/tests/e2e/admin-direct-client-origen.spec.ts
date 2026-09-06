import { test, expect, type Route } from '@playwright/test';

/**
 * E2E coverage for the direct-mode ``Cliente.origen`` radio
 * (OpenSpec change ``cliente-origen-recurrente``).
 *
 * The flow lives at the top of step 1 in ``mode='direct'``. The radio
 * is required: clicking "Guardar y continuar" without a selection must
 * block the wizard on step 1, and a selection must flow through the
 * step 1 → finalize payload.
 *
 * Backend is mocked via ``context.route`` — same pattern as
 * ``admin-direct-client-creation.spec.ts`` — because Playwright's
 * ``globalSetup`` reseeds the local DB and these scenarios need to
 * assert the frontend wires ``origen`` correctly, not that a real
 * row persists.
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

test.describe('Direct-mode Cliente.origen radio (cliente-origen-recurrente)', () => {
  test.beforeEach(async ({ page, context }) => {
    await login(page, context);
  });

  test('No standalone "Crear cliente directo" button on /cms/clientes', async ({ page }) => {
    await page.goto('/cms/clientes');
    // The proposal explicitly removes the standalone PageHeader button.
    // The deep-link route at /cms/clientes/nuevo still mounts the wizard
    // (see App.tsx) so external links continue to work.
    const standaloneButton = page.getByRole('link', { name: 'Crear cliente directo' });
    await expect(standaloneButton).toHaveCount(0);
  });

  test('Admin listing renders the origen badge per row', async ({ page, context }) => {
    /**
     * Spec — ``cliente-origen`` › "Admin listing shows the origen badge".
     *
     * Two mocked Cliente rows: one with ``origen=NUEVO`` and one with
     * ``origen=RECURRENTE_PRE_SISTEMA``. The page must render a badge for
     * each row using a distinguishable label.
     */
    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          metrics: [],
          prospects: [],
          clients: [
            {
              id: 'CLI-0001',
              rawId: 1,
              clienteCodigo: 'CLI-0001',
              name: 'Ana Nuevo',
              ci: '11111',
              phone: '7000-0001',
              email: 'ana@example.com',
              status: 'Activo',
              activeOperations: 0,
              totalOperations: 0,
              lastAnalysis: 'Sin analisis',
              scheduledAppointments: [],
              hasBiometricEnrollment: false,
              origen: 'NUEVO',
            },
            {
              id: 'CLI-0002',
              rawId: 2,
              clienteCodigo: 'CLI-0002',
              name: 'Beto Recurrente',
              ci: '22222',
              phone: '7000-0002',
              email: 'beto@example.com',
              status: 'Activo',
              activeOperations: 0,
              totalOperations: 0,
              lastAnalysis: 'Sin analisis',
              scheduledAppointments: [],
              hasBiometricEnrollment: false,
              origen: 'RECURRENTE_PRE_SISTEMA',
            },
          ],
        }),
      });
    });

    await page.goto('/cms/clientes');

    // The header for the new column must be present so the badge column
    // is visible to operators.
    await expect(page.getByRole('columnheader', { name: 'Origen' })).toBeVisible();

    // The two badges must render with distinguishable labels per spec.
    await expect(page.getByTestId('client-origen-1')).toHaveText('Nuevo');
    await expect(page.getByTestId('client-origen-2')).toHaveText('Recurrente pre-sistema');
  });

  test('Required origin radio renders at top of direct step 1', async ({ page, context }) => {
    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
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
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // Radio must be present, above the user data fields.
    const fieldset = page.getByTestId('step-user-origen-fieldset');
    await expect(fieldset).toBeVisible();
    await expect(fieldset.locator('input[value="RECURRENTE_PRE_SISTEMA"]')).toBeVisible();
    await expect(fieldset.locator('input[value="NUEVO"]')).toBeVisible();

    // The "Sí" copy mirrors the spec wording.
    await expect(fieldset.getByText(/Sí, ya fue paciente/i)).toBeVisible();
    await expect(fieldset.getByText(/No, es nuevo/i)).toBeVisible();
  });

  test('Step 1 blocks advancing until an origin is selected', async ({ page, context }) => {
    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
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
      });
    });

    let paso1Calls = 0;
    await context.route('**/api/admin/clientes/directo/*/paso-1/', async (route: Route) => {
      paso1Calls += 1;
      const body = JSON.parse(route.request().postData() || '{}') as Record<string, unknown>;
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...body };
      draft.stepUserCompleted = true;
      draft.currentStep = 2;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // Fill the rest of step 1 but leave origen untouched.
    const uniqueCi = `9${Date.now().toString().slice(-7)}`;
    const uniqueUsername = `origen_${Date.now()}`;
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

    // Origin error must surface; wizard must not advance; paso-1 must NOT be called.
    await expect(page.getByTestId('step-user-origen-error')).toBeVisible();
    await expect(page).toHaveURL(/\/cms\/clientes\/nuevo$/);
    await expect(page.locator('input[name="precioTotal"]')).not.toBeVisible();
    expect(paso1Calls).toBe(0);
  });

  test('Selecting "Sí" persists origen=RECURRENTE_PRE_SISTEMA through finalize', async ({
    page,
    context,
  }) => {
    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
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
      });
    });

    let lastPaso1Body: Record<string, unknown> = {};
    await context.route('**/api/admin/clientes/directo/*/paso-1/', async (route: Route) => {
      lastPaso1Body = JSON.parse(route.request().postData() || '{}') as Record<string, unknown>;
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...lastPaso1Body };
      draft.stepUserCompleted = true;
      draft.currentStep = 2;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    // Stub the rest of the steps so the wizard can advance.
    await context.route('**/api/admin/clientes/directo/*/paso-2/', async (route: Route) => {
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...lastPaso1Body };
      draft.stepUserCompleted = true;
      draft.stepOperationCompleted = true;
      draft.currentStep = 3;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/paso-3/', async (route: Route) => {
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...lastPaso1Body };
      draft.stepUserCompleted = true;
      draft.stepOperationCompleted = true;
      draft.stepMedicalCompleted = true;
      draft.currentStep = 4;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    await context.route('**/api/admin/clientes/directo/*/paso-4/', async (route: Route) => {
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...lastPaso1Body };
      draft.stepUserCompleted = true;
      draft.stepOperationCompleted = true;
      draft.stepMedicalCompleted = true;
      draft.stepBiometricCompleted = true;
      draft.currentStep = 5;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    let finalizeCalls: Array<{ url: string; method: string }> = [];
    await context.route('**/api/admin/clientes/directo/*/finalizar/', async (route: Route) => {
      finalizeCalls.push({ url: route.request().url(), method: route.request().method() });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Cliente creado correctamente.',
          client: { id: 999, name: 'Cliente Origen Test' },
          operation: { id: 1, procedure: 'Servicio Demo' },
        }),
      });
    });

    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ clients: [] }),
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // Select "Sí, ya fue paciente".
    await page.getByTestId('step-user-origen-recurrente').check();
    await expect(page.getByTestId('step-user-origen-recurrente')).toBeChecked();

    // Fill the rest of step 1.
    const uniqueCi = `8${Date.now().toString().slice(-7)}`;
    const uniqueUsername = `origen_si_${Date.now()}`;
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

    // Step 2 inputs visible (wizard advanced).
    await expect(page.locator('input[name="precioTotal"]')).toBeVisible();
    expect(lastPaso1Body.origen).toBe('RECURRENTE_PRE_SISTEMA');

    // Drive through the remaining steps.
    await page.fill('input[name="zonaGeneral"]', 'Cuerpo');
    await page.fill('input[name="zonaEspecifica"]', 'Piernas');
    await page.fill('input[name="precioTotal"]', '100');
    await page.click('button:has-text("Guardar y continuar")');

    await page.setInputFiles('input[type="file"]', {
      name: 'ficha.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 stub\n'),
    });
    await page.click('button:has-text("Guardar ficha y continuar")');

    await page.click('button:has-text("Guardar y continuar")');

    await page.click('button:has-text("Confirmar pago y finalizar")');
    await page.getByRole('button', { name: 'Confirmar', exact: true }).click();

    await expect(page).toHaveURL(/\/cms\/clientes$/);
    await expect.poll(() => finalizeCalls.length).toBeGreaterThan(0);
    expect(finalizeCalls[0].method).toBe('POST');
  });

  test('Selecting "No" persists origen=NUEVO through paso-1', async ({ page, context }) => {
    await context.route('**/api/admin/clientes/directo/initialize/', async (route: Route) => {
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
      });
    });

    let lastPaso1Body: Record<string, unknown> = {};
    await context.route('**/api/admin/clientes/directo/*/paso-1/', async (route: Route) => {
      lastPaso1Body = JSON.parse(route.request().postData() || '{}') as Record<string, unknown>;
      const draft = blankDraftForDirect() as Record<string, any>;
      draft.userData = { ...(draft.userData as Record<string, unknown>), ...lastPaso1Body };
      draft.stepUserCompleted = true;
      draft.currentStep = 2;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          prospect: null,
          client: null,
          draft,
          serviceConfigs: [],
          operationStates: [],
          medicalConfig: emptyMedicalConfig(),
        }),
      });
    });

    await page.goto('/cms/clientes/nuevo');
    await expect(page.getByText(/Nuevo cliente directo/i).first()).toBeVisible();

    // Select "No, es nuevo".
    await page.getByTestId('step-user-origen-nuevo').check();
    await expect(page.getByTestId('step-user-origen-nuevo')).toBeChecked();

    // Fill the rest of step 1.
    const uniqueCi = `7${Date.now().toString().slice(-7)}`;
    const uniqueUsername = `origen_no_${Date.now()}`;
    await page.fill('input[name="primerNombre"]', 'Juan');
    await page.fill('input[name="apellidoPaterno"]', 'Perez');
    await page.fill('input[name="ci"]', uniqueCi);
    await page.fill('input[name="username"]', uniqueUsername);
    await page.fill('input[name="email"]', `${uniqueUsername}@test.com`);
    await page.fill('input[name="telefono"]', '70000002');
    await page.fill('input[name="fechaNacimiento"]', '1990-01-01');
    await page.fill('input[name="direccionDomicilio"]', 'Calle 1');
    await page.fill('input[name="ocupacion"]', 'Test');
    const passwordInputs = page.locator('input[type="password"]');
    await passwordInputs.first().fill('test1234');
    await passwordInputs.nth(1).fill('test1234');

    await page.click('button:has-text("Guardar y continuar")');

    await expect(page.locator('input[name="precioTotal"]')).toBeVisible();
    expect(lastPaso1Body.origen).toBe('NUEVO');
  });
});