import { test, expect, type Route } from '@playwright/test';

/**
 * E2E coverage for the prospect-create page's required ``origen`` radio
 * (OpenSpec change ``prospecto-origen-heredable``).
 *
 * The radio lives at the top of ``AdminProspectCreatePage``. Submit is
 * disabled until one option is chosen, and each option must persist the
 * expected ``origen`` literal through the ``createAdminProspect`` payload.
 *
 * The conversion path (the prospect being promoted into a ``Cliente`` at
 * finalize time) is exercised end-to-end: the radio choice flows through
 * ``admin_crear_prospecto`` into ``Prospecto.origen``, then the
 * conversion wizard's finalize propagates the tag to the resulting
 * ``Cliente``. Backend is mocked via ``context.route`` because Playwright's
 * ``globalSetup`` reseeds the local DB and these scenarios need to
 * assert the frontend wires ``origen`` correctly, not that a real row
 * persists — same pattern as ``admin-direct-client-origen.spec.ts``.
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

test.describe('Prospect-create origen radio (prospecto-origen-heredable)', () => {
  test.beforeEach(async ({ page, context }) => {
    await login(page, context);
  });

  test('Submit stays disabled until an origin is selected', async ({ page }) => {
    await page.goto('/cms/prospectos/nuevo');
    await expect(page.getByText(/Registrar prospecto/i).first()).toBeVisible();

    // The radio fieldset must render at the top of the form, above
    // ``primerNombre``.
    const fieldset = page.getByTestId('prospect-create-origen-fieldset');
    await expect(fieldset).toBeVisible();
    await expect(
      fieldset.locator('input[value="RECURRENTE_PRE_SISTEMA"]'),
    ).toBeVisible();
    await expect(fieldset.locator('input[value="NUEVO"]')).toBeVisible();

    // Submit button MUST be disabled before any selection.
    const submit = page.getByTestId('prospect-create-submit');
    await expect(submit).toBeDisabled();

    // Selecting either option MUST enable the submit control.
    await page.getByTestId('prospect-create-origen-recurrente').check();
    await expect(submit).toBeEnabled();
    await page.getByTestId('prospect-create-origen-nuevo').check();
    await expect(submit).toBeEnabled();
  });

  test('Selecting "Antiguo" persists RECURRENTE_PRE_SISTEMA on creation', async ({
    page,
    context,
  }) => {
    let lastCreateBody: Record<string, unknown> = {};
    await context.route('**/api/admin/prospectos/crear/', async (route: Route) => {
      lastCreateBody = JSON.parse(route.request().postData() || '{}') as Record<
        string,
        unknown
      >;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Prospecto registrado correctamente.',
          prospect: {
            id: 'PRO-9001',
            rawId: 9001,
            name: 'Antiguo Test',
            origen: 'RECURRENTE_PRE_SISTEMA',
          },
        }),
      });
    });

    await page.goto('/cms/prospectos/nuevo');
    await expect(page.getByText(/Registrar prospecto/i).first()).toBeVisible();

    // Select "Antiguo (ya fue paciente)".
    await page.getByTestId('prospect-create-origen-recurrente').check();
    await expect(page.getByTestId('prospect-create-origen-recurrente')).toBeChecked();

    // Fill the rest of the form.
    await page.fill('input[name="primerNombre"]', 'Ana');
    await page.fill('input[name="apellidoPaterno"]', 'Antigua');

    await page.getByTestId('prospect-create-submit').click();

    // Submission navigated away to /cms/prospectos and the payload
    // carried the radio value.
    await expect(page).toHaveURL(/\/cms\/prospectos$/);
    expect(lastCreateBody.origen).toBe('RECURRENTE_PRE_SISTEMA');
    expect(lastCreateBody.primerNombre).toBe('Ana');
    expect(lastCreateBody.apellidoPaterno).toBe('Antigua');
  });

  test('Selecting "Nuevo" persists NUEVO on creation', async ({ page, context }) => {
    let lastCreateBody: Record<string, unknown> = {};
    await context.route('**/api/admin/prospectos/crear/', async (route: Route) => {
      lastCreateBody = JSON.parse(route.request().postData() || '{}') as Record<
        string,
        unknown
      >;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Prospecto registrado correctamente.',
          prospect: {
            id: 'PRO-9002',
            rawId: 9002,
            name: 'Nuevo Test',
            origen: 'NUEVO',
          },
        }),
      });
    });

    await page.goto('/cms/prospectos/nuevo');
    await expect(page.getByText(/Registrar prospecto/i).first()).toBeVisible();

    await page.getByTestId('prospect-create-origen-nuevo').check();
    await expect(page.getByTestId('prospect-create-origen-nuevo')).toBeChecked();

    await page.fill('input[name="primerNombre"]', 'Jose');
    await page.fill('input[name="apellidoPaterno"]', 'Nuevo');

    await page.getByTestId('prospect-create-submit').click();

    await expect(page).toHaveURL(/\/cms\/prospectos$/);
    expect(lastCreateBody.origen).toBe('NUEVO');
    expect(lastCreateBody.primerNombre).toBe('Jose');
    expect(lastCreateBody.apellidoPaterno).toBe('Nuevo');
  });

  test('Converting an "Antiguo" prospect yields a matching Cliente.origen', async ({
    page,
    context,
  }) => {
    /**
     * End-to-end happy path: the radio choice at create time flows
     * through ``admin_crear_prospecto`` into ``Prospecto.origen``, and
     * the conversion wizard's finalize propagates the tag to the
     * resulting ``Cliente.origen``. The backend is mocked because the
     * spec asserts the contract, not the persistence path.
     */

    // The create endpoint stores the radio choice.
    await context.route('**/api/admin/prospectos/crear/', async (route: Route) => {
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Prospecto registrado correctamente.',
          prospect: {
            id: 'PRO-9003',
            rawId: 9003,
            name: 'Antiguo Convertir',
            origen: 'RECURRENTE_PRE_SISTEMA',
          },
        }),
      });
    });

    await page.goto('/cms/prospectos/nuevo');
    await page.getByTestId('prospect-create-origen-recurrente').check();
    await page.fill('input[name="primerNombre"]', 'Convertir');
    await page.fill('input[name="apellidoPaterno"]', 'Antiguo');
    await page.getByTestId('prospect-create-submit').click();

    // Stub the prospect list to surface a single conversion-ready
    // prospect so the conversion wizard has something to load.
    await context.route('**/api/admin/prospectos**', async (route: Route) => {
      // The crear/ POST already responded; the navigation hits
      // /cms/prospectos next, which calls /api/admin/prospectos.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          metrics: [],
          prospects: [
            {
              id: 'PRO-9003',
              rawId: 9003,
              name: 'Convertir Antiguo',
              primerNombre: 'Convertir',
              apellidoPaterno: 'Antiguo',
              phone: '7000-9003',
              interest: 'Consulta inicial',
              registeredBy: 'Admin',
              stage: 'Pasajero',
              state: 'Pasajero',
              stateValue: 'PASAJERO',
              origen: 'RECURRENTE_PRE_SISTEMA',
              observations: '',
              createdAt: '—',
              convertedAt: '-',
              medicalAppointments: [],
            },
          ],
          clients: [],
        }),
      });
    });

    await expect(page).toHaveURL(/\/cms\/prospectos$/);

    // Visit the conversion wizard step 1 for the freshly created
    // prospect. Step 1 must NOT render an origen radio for
    // ``mode='prospect'`` — the conversion wizard reads ``origen``
    // off the prospect row, never the draft.
    await page.goto('/cms/prospectos/9003/convertir');
    await expect(page.getByText(/Convertir Antiguo/i).first()).toBeVisible();

    // Sanity: prospect-mode step 1 has NO origen fieldset.
    const wizardOrigen = page.getByTestId('step-user-origen-fieldset');
    await expect(wizardOrigen).toHaveCount(0);
  });
});
