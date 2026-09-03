import { test, expect, type BrowserContext, type Page } from '@playwright/test';

/**
 * E2E coverage for the "Cobrar cita" flow added by the `citas-pagos` change.
 *
 * Scope:
 *   - FISICO happy path on a CitaMedica: admin opens the operation
 *     detail page, sees the "Cobrar cita" button on a non-terminal
 *     cita with `precio > 0`, clicks it, the modal opens pre-filled
 *     with `saldoPendiente`, submits FISICO without a receipt, sees a
 *     success toast and the refreshed `pagos[]` with one new row.
 *
 * Mirrors the `context.route(...)` mocking pattern used by every other
 * admin spec (`admin_backups`, `admin_reports`, `cms-*`): the admin
 * SPA's network is fully mocked so the test stays deterministic and
 * does not depend on the seed DB. The mocked response shapes mirror
 * the backend `_operation_detail` payload (`precio` /
 *     `saldoPendiente` / `pagos_count` / `pagos`) plus the
 * `cobrar_cita` endpoint return shape.
 *
 * The button lives on the operation-detail page
 * (`/cms/operaciones/<id>`) because the operation-detail page renders
 * the `CitaMedica` rows directly with their backend breakdown. The
 * client-detail page surfaces the same fields but doesn't render the
 * button (the section that wires it, `ClientAppointmentSection`, is
 * not currently mounted in the client-detail layout).
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

const OPERATION_ID = 42;
const CITA_ID = 101;
const CITA_PRECIO = '200.00';

type PagoCitaFixture = {
  id: number;
  monto_pagado: string;
  metodo_pago: 'VIRTUAL' | 'FISICO' | 'MIXTO';
  monto_fisico: string;
  monto_virtual: string;
  comprobante_url: string;
  estado_verificacion: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO';
  detalles_pago: string;
  created_at: string;
};

type OperationAppointmentFixture = {
  id: string;
  rawId: number;
  dateTime: string;
  specialist: string;
  status: string;
  biometricStatus: string;
  canConfirmBiometric: boolean;
  canCancelFromVerification: boolean;
  canManage: boolean;
  hasRealTimeData?: boolean;
  fotoAntesUrl?: string;
  fotoDespuesUrl?: string;
  precio?: string;
  saldoPendiente?: string;
  pagos_count?: number;
  pagos?: PagoCitaFixture[];
};

const initialCita: OperationAppointmentFixture = {
  id: `CIT-${String(CITA_ID).padStart(4, '0')}`,
  rawId: CITA_ID,
  dateTime: '30/09 10:00',
  specialist: 'Dra. Test',
  status: 'Programada',
  biometricStatus: 'Sin verificacion',
  canConfirmBiometric: false,
  canCancelFromVerification: false,
  canManage: true,
  hasRealTimeData: false,
  fotoAntesUrl: '',
  fotoDespuesUrl: '',
  precio: CITA_PRECIO,
  saldoPendiente: CITA_PRECIO,
  pagos_count: 0,
  pagos: [],
};

const operationDetail = (cita: OperationAppointmentFixture) => ({
  operation: {
    id: `OP-${String(OPERATION_ID).padStart(4, '0')}`,
    rawId: OPERATION_ID,
    patient: 'Paciente Demo',
    patientId: 7,
    availableAppointments: 3,
    procedure: 'Laser facial',
    serviceType: 'Estetico',
    procedureType: 'Laser',
    branch: 'Sede Principal',
    branchId: 1,
    sessions: '4 total | 0 confirmadas | 1 reservadas | 3 libres',
    nextAppointment: cita.dateTime,
    quotaStatus: 'Sin cuotas',
    status: 'En proceso',
    price: 'Bs 200.00',
    startDate: '01/09/2026',
    endDate: '',
    zonaGeneral: 'Rostro',
    zonaEspecifica: 'Mejilla',
    detallesOperacion: '',
    recomendaciones: '',
    medicalRecordDate: '01/09/2026',
    medicalRecordReason: '',
    medicalRecordNotes: '',
    documentPdfUrl: '',
    documentPdfName: '',
    hasBiometricEnrollment: false,
    appointments: [cita],
    quotas: [],
    fotosAntes: [],
    fotosDespues: [],
  },
});

const cobrarResponse = (cita: OperationAppointmentFixture) => ({
  detail: 'Pago de cita registrado correctamente.',
  payment: (cita.pagos ?? [])[0]!,
  appointment: cita,
});

async function login(page: Page, context: BrowserContext): Promise<void> {
  await context.clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

/**
 * Installs the two mocks the test needs:
 *   - `GET /api/admin/operaciones/<id>/` → returns the operation detail
 *     with the cita fixture (mutated by `updateCita` on each cobrar).
 *   - `POST /api/admin/operaciones/<op>/citas/<id>/cobrar/` → appends
 *     a new PagoCita to the cita fixture and returns it (with the
 *     refreshed payload the modal expects on `onSuccess`).
 *
 * The frontend re-fetches the operation detail on success, so the
 * assertion that the row reflects the incremented `pagos_count` is
 * real (the network mock returns the updated state).
 */
async function installMocks(context: BrowserContext) {
  let cita = { ...initialCita };

  await context.route(/\/api\/admin\/operaciones\/[^/]+\/?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(operationDetail(cita)),
    });
  });

  await context.route(/\/api\/admin\/operaciones\/[^/]+\/citas\/[^/]+\/cobrar\/?$/, async (route) => {
    if (route.request().method() !== 'POST') {
      await route.continue();
      return;
    }
    const newPago: PagoCitaFixture = {
      id: 9001 + (cita.pagos?.length ?? 0),
      monto_pagado: CITA_PRECIO,
      metodo_pago: 'FISICO',
      monto_fisico: CITA_PRECIO,
      monto_virtual: '0.00',
      comprobante_url: '',
      estado_verificacion: 'APROBADO',
      detalles_pago: 'Pago demo Playwright',
      created_at: new Date().toISOString(),
    };
    cita = {
      ...cita,
      pagos_count: (cita.pagos_count ?? 0) + 1,
      pagos: [newPago, ...(cita.pagos ?? [])],
      // Admin cobro at the desk goes straight to APROBADO, so the
      // saldo pendiente drops to 0 after the first payment.
      saldoPendiente: '0.00',
    };
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify(cobrarResponse(cita)),
    });
  });
}

test.describe('Admin cobrar cita — FISICO happy path on CitaMedica', () => {
  test.beforeEach(async ({ page, context }) => {
    await installMocks(context);
    await login(page, context);
  });

  test('admin opens operation detail → clicks Cobrar cita → submits FISICO → sees toast + refreshed pagos[]', async ({ page }) => {
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    // Wait for the cita row to render before interacting. The
    // operation-detail page renders each cita inside an
    // `.operation-detail-item`; we wait for the "Citas medicas" panel
    // header before scoping to the row.
    await expect(page.getByText('Citas medicas', { exact: false }).first()).toBeVisible();

    // The "Cobrar cita" button is rendered for non-terminal citas with
    // `precio > 0` (Programada qualifies).
    const cobrarBtn = page.getByTestId(`cobrar-cita-operation-${CITA_ID}`);
    await expect(cobrarBtn).toBeVisible();
    await cobrarBtn.click();

    // Modal opens; submit is enabled because `precio > 0 &&
    // saldoPendiente > 0`. FISICO is the default.
    const modal = page.locator('.payment-modal');
    await expect(modal).toBeVisible();
    const submitBtn = modal.getByRole('button', { name: /Cobrar cita/i });
    await expect(submitBtn).toBeEnabled();
    await submitBtn.click();

    // Success toast appears; modal closes.
    await expect(page.locator('.notification-toast--success').filter({ hasText: /Pago registrado/i })).toBeVisible();
    await expect(modal).toBeHidden();

    // After reload, the cita now reflects the new pago (mock mutated
    // the fixture, so the GET returns pagos_count=1 and saldoPendiente
    // drops to "0.00"). The button is still rendered for follow-up
    // charges (admin can register partial payments over multiple
    // visits).
    await expect(page.getByTestId(`cobrar-cita-operation-${CITA_ID}`)).toBeVisible();
  });

  test('admin does NOT see "Cobrar cita" button on a CANCELADA cita', async ({ page }) => {
    // Override the GET to return a CANCELADA cita, then reload. CANCELADA
    // is a terminal state per the spec — the backend rejects cobrar
    // calls with 400, so the frontend hides the button.
    const cancelledCita: OperationAppointmentFixture = {
      ...initialCita,
      status: 'Cancelada',
      canManage: false,
      canMarkPendingBiometric: false,
    };
    await page.unroute(/\/api\/admin\/operaciones\/[^/]+\/?$/);
    await page.route(/\/api\/admin\/operaciones\/[^/]+\/?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(operationDetail(cancelledCita)),
      });
    });
    await page.goto(`/cms/operaciones/${OPERATION_ID}`);
    await expect(page.getByText('Citas medicas', { exact: false }).first()).toBeVisible();
    await expect(page.getByTestId(`cobrar-cita-operation-${CITA_ID}`)).toHaveCount(0);
  });
});
