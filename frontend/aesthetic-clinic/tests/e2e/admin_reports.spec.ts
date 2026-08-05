import { test, expect, type BrowserContext, type Page } from '@playwright/test';

/**
 * E2E coverage for the `/cms/reportes/*` admin reports area.
 *
 * Scope:
 *   - Navigation: each of the four report URLs renders its dedicated page
 *     (clients, prospects, income, expenses).
 *   - Period controls: the income and expenses reports expose the
 *     `.expense-period-controls` widget (month/year + navigation arrows).
 *   - Export button visibility: when the endpoint returns rows, the
 *     "↓ Excel" button appears; when the endpoint returns no rows, it is
 *     hidden (the `ReportTable` short-circuits before rendering it).
 *   - Export click triggers a real download via `page.waitForEvent('download')`
 *     so the XLSX emission path (`XLSX.writeFile`) is exercised end-to-end.
 *
 * The network for the four `/api/admin/reportes/*` endpoints is mocked with
 * `context.route(...)`. The fixtures below are deterministic so the test
 * can assert on row counts and column values without depending on the seed
 * DB. They are intentionally light (no invoice URL for the empty case) so
 * the empty-state branch of `ReportTable` (which hides the export button)
 * is observable.
 *
 * Pre-existing convention used by every other spec in this folder:
 *   - Login as `admin.general` / `admin123456` (seeded by
 *     `seed_pdf_baseline` and confirmed by `reset_test_db_local.sh`).
 *   - The post-login redirect target is `/\/(admin|cms)/` because the app
 *     switched from `/admin` to `/cms` for the admin SPA — see the comment
 *     block in `biometric_suspension_frontend.spec.ts` for context.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

type ReportFixture = {
  branch: { id: number; name: string };
  rows: Record<string, unknown>[];
  cap?: number;
  truncated?: boolean;
  month?: number;
  year?: number;
};

const branchFixture = { id: 1, name: 'Sucursal Principal' };

const clientsFixture: ReportFixture = {
  branch: branchFixture,
  cap: 500,
  truncated: false,
  rows: [
    {
      firstName: 'Ana',
      lastName: 'Aguilar',
      ci: '1001',
      status: 'Activo',
      lastAppointmentDate: '2026-07-15T15:30:00Z',
      nextAppointmentDate: '2026-08-20T10:00:00Z',
      lastPaymentDate: '2026-08-01T12:00:00Z',
      nextPaymentDate: '2026-08-15T00:00:00',
    },
    {
      firstName: 'Andres',
      lastName: 'Alvarez',
      ci: '1002',
      status: 'Activo',
      lastAppointmentDate: null,
      nextAppointmentDate: null,
      lastPaymentDate: null,
      nextPaymentDate: null,
    },
  ],
};

const prospectsFixture: ReportFixture = {
  branch: branchFixture,
  cap: 500,
  truncated: false,
  rows: [
    {
      firstName: 'Paula',
      lastName: 'Perez',
      phone: '71111111',
      ci: '-',
      interest: 'Consulta',
      state: 'Pasajero',
      createdAt: '2026-08-01',
      registeredBy: 'admin.general',
      lastAppointmentDate: '2026-08-05T09:00:00Z',
      nextAppointmentDate: '2026-08-25T16:30:00Z',
    },
  ],
};

const incomeFixture: ReportFixture = {
  branch: branchFixture,
  month: 8,
  year: 2026,
  cap: 500,
  truncated: false,
  rows: [
    {
      paymentId: 1,
      date: '2026-08-03',
      time: '10:30',
      amount: '250.00',
      clientName: 'Ana Aguilar',
      serviceName: 'Limpieza facial',
      status: 'Aprobado',
      invoiceUrl: 'http://example.com/invoice-1.pdf',
      invoiceName: 'invoice-1.pdf',
    },
  ],
};

// Empty fixture used to assert the export button is hidden when no rows
// match the current branch/period. Same shape, zero rows.
const emptyIncomeFixture: ReportFixture = {
  branch: branchFixture,
  month: 8,
  year: 2026,
  cap: 500,
  truncated: false,
  rows: [],
};

const expensesFixture: ReportFixture = {
  branch: branchFixture,
  month: 8,
  year: 2026,
  cap: 500,
  truncated: false,
  rows: [
    {
      id: 'exp-1',
      rawId: 1,
      date: '2026-08-05',
      dateLabel: '5 ago 2026',
      categoryId: 1,
      category: 'Insumos',
      concept: 'Guantes',
      units: '10',
      unitCost: '2.50',
      total: '25.00',
      totalLabel: 'Bs 25.00',
      provider: 'Proveedor Demo',
      invoiceUrl: 'http://example.com/invoice-1.pdf',
      invoiceName: 'invoice-1.pdf',
      details: '-',
      branchId: branchFixture.id,
      branchName: branchFixture.name,
      registeredBy: 'admin.general',
    },
  ],
};

async function login(page: Page, context: BrowserContext): Promise<void> {
  await context.clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', ADMIN_USER);
  await page.fill('input[name="password"]', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

/**
 * Install JSON route handlers for the four report endpoints. The mocks are
 * unconditional so the spec does not depend on seed data. Each handler
 * returns the fixture verbatim; for the "empty" case the test installs an
 * override via `context.unroute(...)` and a fresh handler that replies
 * with `emptyIncomeFixture`.
 */
async function installReportMocks(
  context: BrowserContext,
  overrides: { income?: ReportFixture; expenses?: ReportFixture } = {},
): Promise<void> {
  const income = overrides.income ?? incomeFixture;
  const expenses = overrides.expenses ?? expensesFixture;

  await context.route(/\/api\/admin\/reportes\/clientes\/?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(clientsFixture),
    });
  });

  await context.route(/\/api\/admin\/reportes\/prospectos\/?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(prospectsFixture),
    });
  });

  await context.route(/\/api\/admin\/reportes\/ingresos\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(income),
    });
  });

  // The expenses report reuses the existing gastos endpoint, which is the
  // SAME shape the regular expenses list hits. We mock it under both URL
  // patterns so the test stays scoped to the report surface even if the
  // helper does not get a month/year.
  await context.route(/\/api\/admin\/gastos\/?(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        month: expenses.month,
        year: expenses.year,
        branch: { id: expenses.branch.id, name: expenses.branch.name },
        metrics: [],
        categories: [],
        expenses: expenses.rows,
      }),
    });
  });
}

test.describe('Admin Reports — /cms/reportes/* navigation, period controls, and export', () => {
  test.beforeEach(async ({ page, context }) => {
    await installReportMocks(context);
    await login(page, context);
  });

  test('Clients report renders the table at /cms/reportes/clientes', async ({ page }) => {
    await page.goto('/cms/reportes/clientes');
    // `ReportLayout` renders the title in both the `PageHeader` (`<h1>`) and
    // the `SectionCard` (`<h2>`) when `withPeriod` is false. `.first()`
    // disambiguates so the strict-mode locator resolves to the page heading.
    await expect(page.getByRole('heading', { name: /Reporte de clientes/i }).first()).toBeVisible();
    // The clients report does NOT expose month/year period controls; the
    // `↓ Excel` button lives inside its own `.expense-period-controls`
    // wrapper (mirroring `AdminExpenseListPage`'s right-aligned action slot).
    await expect(page.locator('.expense-period-controls')).toHaveCount(1);
    // Row count matches the fixture.
    await expect(page.locator('table.admin-table tbody tr')).toHaveCount(clientsFixture.rows.length);
    // The export button is rendered because there are rows.
    await expect(page.getByRole('button', { name: /↓ Excel/i })).toBeVisible();
  });

  test('Prospects report renders the table at /cms/reportes/prospectos', async ({ page }) => {
    await page.goto('/cms/reportes/prospectos');
    // `ReportLayout` renders the title in both the `PageHeader` (`<h1>`) and
    // the `SectionCard` (`<h2>`). `.first()` disambiguates so the strict-mode
    // locator resolves to the page heading.
    await expect(page.getByRole('heading', { name: /Reporte de prospectos/i }).first()).toBeVisible();
    // Same single `.expense-period-controls` wrapper as the clients report.
    await expect(page.locator('.expense-period-controls')).toHaveCount(1);
    await expect(page.locator('table.admin-table tbody tr')).toHaveCount(prospectsFixture.rows.length);
    await expect(page.getByRole('button', { name: /↓ Excel/i })).toBeVisible();
  });

  test('Income report at /cms/reportes/ingresos exposes period controls', async ({ page }) => {
    await page.goto('/cms/reportes/ingresos');
    // `ReportLayout` renders the title in both the `PageHeader` (`<h1>`) and
    // the `SectionCard` (`<h2>`). `.first()` disambiguates so the strict-mode
    // locator resolves to the page heading.
    await expect(page.getByRole('heading', { name: /Reporte de ingresos/i }).first()).toBeVisible();
    // Period controls MUST be visible on the income report.
    await expect(page.locator('.expense-period-controls')).toBeVisible();
    // Month + year selects live inside the period controls.
    await expect(page.locator('.expense-period-controls select')).toHaveCount(2);
    await expect(page.locator('table.admin-table tbody tr')).toHaveCount(incomeFixture.rows.length);
    await expect(page.getByRole('button', { name: /↓ Excel/i })).toBeVisible();
  });

  test('Expenses report at /cms/reportes/gastos exposes period controls', async ({ page }) => {
    await page.goto('/cms/reportes/gastos');
    // `ReportLayout` renders the title in both the `PageHeader` (`<h1>`) and
    // the `SectionCard` (`<h2>`). `.first()` disambiguates so the strict-mode
    // locator resolves to the page heading.
    await expect(page.getByRole('heading', { name: /Reporte de gastos/i }).first()).toBeVisible();
    await expect(page.locator('.expense-period-controls')).toBeVisible();
    await expect(page.locator('.expense-period-controls select')).toHaveCount(2);
    await expect(page.locator('table.admin-table tbody tr')).toHaveCount(expensesFixture.rows.length);
    await expect(page.getByRole('button', { name: /↓ Excel/i })).toBeVisible();
  });

  test('Export button is hidden when the endpoint returns no rows', async ({ page, context }) => {
    // Re-route the income endpoint with an empty payload. We keep the
    // other mocks intact so the rest of the test infrastructure stays
    // stable.
    await context.unroute(/\/api\/admin\/reportes\/ingresos\/?(\?.*)?$/);
    await context.route(/\/api\/admin\/reportes\/ingresos\/?(\?.*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(emptyIncomeFixture),
      });
    });

    await page.goto('/cms/reportes/ingresos');
    // The empty-state DataState is visible and there is no table.
    await expect(page.getByText(/Sin ingresos en el mes seleccionado/i)).toBeVisible();
    await expect(page.locator('table.admin-table')).toHaveCount(0);
    // Export button MUST be absent because ReportTable short-circuits
    // when there are zero rows.
    await expect(page.getByRole('button', { name: /↓ Excel/i })).toHaveCount(0);
  });

  test('Export button is visible and triggers a download when rows exist', async ({ page }) => {
    await page.goto('/cms/reportes/ingresos');
    const exportButton = page.getByRole('button', { name: /↓ Excel/i });
    await expect(exportButton).toBeVisible();

    // `waitForEvent('download')` is the canonical Playwright way to
    // verify a programmatic download. The browser fires the event when
    // `XLSX.writeFile` triggers a Blob URL click, so the event reaching
    // Playwright proves the export path ran without inspecting the file
    // contents.
    const downloadPromise = page.waitForEvent('download');
    await exportButton.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^ingresos_\d+_\d+\.xlsx$/);
  });
});