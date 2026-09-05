import { test, expect, type BrowserContext, type Page } from '@playwright/test';

/**
 * E2E coverage for the operation-manual-closure buttons rendered on the
 * admin operation detail page.
 *
 * Scope (operation-manual-closure):
 *   - Buttons visible only when `estado === "En proceso"` (the
 *     precondition for the manual flow).
 *   - "Finalizar" disabled when a precondition fails (here we mock the
 *     detail payload so the derived report has a missing sesion).
 *   - Tooltip names the failing precondition.
 *   - "Suspender" always enabled while EN_PROCESO.
 *   - Server 409 re-renders the modal from the authoritative
 *     precondition payload (race condition).
 *
 * Mirrors the `context.route(...)` mocking pattern used by every other
 * admin spec so the test stays deterministic and does not depend on a
 * seed DB.
 */

const ADMIN_USER = 'admin.closure';
const ADMIN_PASS = 'admin123456';

const OPERATION_ID = 4242;

type OperationDetailFixture = {
  id: string;
  rawId: number;
  patient: string;
  patientId: number;
  availableAppointments: number;
  procedure: string;
  serviceType: string;
  procedureType: string;
  branch: string;
  branchId: number;
  sessions: string;
  nextAppointment: string;
  quotaStatus: string;
  status: string;
  price: string;
  startDate: string;
  endDate: string;
  zonaGeneral: string;
  zonaEspecifica: string;
  detallesOperacion: string;
  recomendaciones: string;
  medicalRecordDate: string;
  medicalRecordReason: string;
  medicalRecordNotes: string;
  documentPdfUrl: string;
  documentPdfName: string;
  hasBiometricEnrollment: boolean;
  appointments: Array<{
    id: string;
    rawId: number;
    dateTime: string;
    specialist: string;
    status: string;
    biometricStatus: string;
    canConfirmBiometric: boolean;
    canCancelFromVerification: boolean;
    canManage: boolean;
  }>;
  quotas: Array<{
    id: string;
    rawId: number;
    number: number;
    amount: string;
    amountValue: string;
    dueDate: string;
    status: string;
    paymentsCount: number;
  }>;
  fotosAntes: Array<{ id: number; url: string; uploadedAt: string; fileName: string }>;
  fotosDespues: Array<{ id: number; url: string; uploadedAt: string; fileName: string }>;
};

const detailForEstado = (estado: string, sesionesTotales: number): OperationDetailFixture => ({
  id: `OP-${String(OPERATION_ID).padStart(4, '0')}`,
  rawId: OPERATION_ID,
  patient: 'Paciente Demo',
  patientId: 7,
  availableAppointments: 0,
  procedure: 'Laser facial',
  serviceType: 'Estetico',
  procedureType: 'Laser',
  branch: 'Sede Principal',
  branchId: 1,
  // Reported string intentionally does NOT have to match `sesionesTotales`;
  // the helper uses `currentSessions` (a separate number) from the same
  // payload. This mirrors the real backend's reporting.
  sessions: `${sesionesTotales} total | 0 confirmadas | 0 reservadas | ${sesionesTotales} libres`,
  nextAppointment: '',
  quotaStatus: 'Sin cuotas',
  status: estado,
  price: 'Bs 100.00',
  startDate: '',
  endDate: '',
  zonaGeneral: '',
  zonaEspecifica: '',
  detallesOperacion: '',
  recomendaciones: '',
  medicalRecordDate: '',
  medicalRecordReason: '',
  medicalRecordNotes: '',
  documentPdfUrl: '',
  documentPdfName: '',
  hasBiometricEnrollment: false,
  // No citas: sesiones.missing = sesionesTotales -> can_cerrar.ok = False
  // when sesionesTotales > 0.
  appointments: [],
  // No cuotas: cuotas.ok = True (vacio => no pending).
  quotas: [],
  fotosAntes: [],
  fotosDespues: [],
});

async function login(context: BrowserContext, page: Page) {
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.startsWith('/login'));
}

test.describe('Operation manual closure actions', () => {
  test('Buttons visible only when estado === "En proceso"', async ({ context, page }) => {
    // 1) Mock the operation detail endpoint with estado = FINALIZADA.
    await context.route(`**/api/admin/operaciones/${OPERATION_ID}/`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ operation: detailForEstado('Finalizada', 5) }),
      });
    });
    await login(context, page);
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    // Wait for the page to finish loading the mocked detail.
    await page.waitForSelector('[data-testid="operation-closure-actions"]', { state: 'detached' });
  });

  test('Finalizar disabled with tooltip when a precondition fails', async ({ context, page }) => {
    await context.route(`**/api/admin/operaciones/${OPERATION_ID}/`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ operation: detailForEstado('En proceso', 5) }),
      });
    });
    await login(context, page);
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    const finalizar = page.getByTestId('operation-finalizar-button');
    await expect(finalizar).toBeVisible();
    await expect(finalizar).toBeDisabled();
    const tooltip = await finalizar.getAttribute('title');
    expect(tooltip ?? '').toMatch(/No puedes finalizar/);
    expect(tooltip ?? '').toMatch(/5 sesion/);
  });

  test('Suspender always enabled while EN_PROCESO and modal opens', async ({ context, page }) => {
    await context.route(`**/api/admin/operaciones/${OPERATION_ID}/`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ operation: detailForEstado('En proceso', 5) }),
      });
    });
    await login(context, page);
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    const suspender = page.getByTestId('operation-suspender-button');
    await expect(suspender).toBeVisible();
    await expect(suspender).toBeEnabled();
    await suspender.click();
    await expect(page.getByTestId('operation-closure-confirm-modal')).toBeVisible();
  });

  test('Server 409 precondition re-renders the modal from the server report', async ({ context, page }) => {
    // 1) Mock the operation detail (EN_PROCESO, but with NO cuotas -> no
    //    monto mismatch; however we'll fake a 409 below to exercise the
    //    race-condition path).
    await context.route(`**/api/admin/operaciones/${OPERATION_ID}/`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ operation: detailForEstado('En proceso', 0) }),
      });
    });
    // 2) Mock the finalizar endpoint with a structured 409.
    await context.route(`**/api/admin/operaciones/${OPERATION_ID}/finalizar/`, async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          estado: 'EN_PROCESO',
          preconditions: {
            ok: false,
            sesiones: { ok: false, expected: 3, confirmed: 2, reserved: 0, pending: 0, missing: 1 },
            cuotas: { ok: true, pending: [] },
            monto: { ok: true, precioTotal: '0.00', sumaMontoProgramado: '0.00', diff: '0.00' },
          },
        }),
      });
    });
    await login(context, page);
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    // With sesiones_totales = 0, the client helper marks sesiones.ok =
    // False (expected 0, missing 0). To exercise the 409 path we click
    // anyway (bypassing the disabled button via JS) and confirm the
    // modal repaints from the server payload.
    await page.evaluate(() => {
      const btn = document.querySelector(
        '[data-testid="operation-finalizar-button"]',
      ) as HTMLButtonElement | null
      if (btn) btn.disabled = false
    })
    await page.getByTestId('operation-finalizar-button').click()
    await expect(page.getByTestId('operation-closure-confirm-modal')).toBeVisible()
    await page.getByTestId('operation-closure-confirm-button').click()
    // Wait for the modal's report to repaint with the server payload
    // (expected 3, missing 1 -> the server's truth).
    await expect(page.getByTestId('precondition-sesiones')).toContainText('Faltan 1 sesion(es)')
  })
})
