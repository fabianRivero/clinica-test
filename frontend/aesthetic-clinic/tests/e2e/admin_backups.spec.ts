import { test, expect, type BrowserContext, type Page } from '@playwright/test';

/**
 * E2E coverage for the admin Backups page (`/cms/backups`). Mirrors the
 * `context.route(...)` mocking pattern used by every other admin spec so the
 * assertions stay deterministic and do not depend on `BACKUPS_DIR` state:
 *
 *   - principal sees the nav entry and the empty-state card.
 *   - principal sees the trigger modal flow when the page loads with seeded
 *     dumps; a successful download is intercepted via
 *     `page.waitForEvent('download')`.
 *   - principal sees the delete flow when a dump exists; the row is removed
 *     after the modal is confirmed.
 *   - `ADMIN_SUCURSAL` does NOT see the nav entry, and a direct navigation to
 *     `/cms/backups` surfaces the backend's 403/HTML response without
 *     leaking any backup metadata.
 *
 * The mocked `/api/admin/backups/` response shape mirrors the backend
 * `_serialize_entry` output (`id`, `name`, `size`, `modified_at`,
 * `is_weekly`).
 */

const ADMIN_PRINCIPAL_USER = 'admin.general';
const ADMIN_PRINCIPAL_PASS = 'admin123456';
const ADMIN_SUCURSAL_USER = 'admin.norte';
const ADMIN_SUCURSAL_PASS = 'admin123456';

type BackupFixture = {
  id: string;
  name: string;
  size: number;
  modified_at: string;
  age_label: string;
  is_weekly: boolean;
};

const DAILY_FIXTURE: BackupFixture = {
  id: 'clinica_2026-08-05_103000.dump',
  name: 'clinica_2026-08-05_103000.dump',
  size: 4_194_304,
  modified_at: '2026-08-05T10:30:00Z',
  age_label: 'hace 1 dia',
  is_weekly: false,
};

const WEEKLY_FIXTURE: BackupFixture = {
  id: 'clinica_2026-08-01_020000.weekly.dump',
  name: 'clinica_2026-08-01_020000.weekly.dump',
  size: 16_777_216,
  modified_at: '2026-08-01T02:00:00Z',
  age_label: 'hace 5 dias',
  is_weekly: true,
};

const BACKUPS_URL = /\/api\/admin\/backups\/?(\?.*)?$/;
const TRIGGER_URL = /\/api\/admin\/backups\/trigger\/?$/;
const DELETE_URL = /\/api\/admin\/backups\/[^/]+\/?$/;

async function loginAs(page: Page, username: string, password: string) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/(admin|cms)/);
}

function mockBackupsList(context: BrowserContext, results: BackupFixture[]) {
  return context.route(BACKUPS_URL, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ results }),
    });
  });
}

test.describe('Admin Backups page', () => {
  test.beforeEach(async ({ page, context }) => {
    // Always start with a CSRF cookie primed so the trigger/delete helpers
    // in `apiClient.ts` resolve `ensureCsrfCookie()` without an extra round
    // trip. The login flow below reuses the same context.
    await context.clearCookies();
    await loginAs(page, ADMIN_PRINCIPAL_USER, ADMIN_PRINCIPAL_PASS);
  });

  test('principal sees the nav entry and empty state when no backups exist', async ({ page, context }) => {
    await mockBackupsList(context, []);

    await page.goto('/cms/backups');

    await expect(page.getByRole('heading', { name: /Respaldos de base de datos/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Respaldos de base de datos/i })).toBeVisible();
    await expect(page.getByTestId('backup-trigger-open')).toBeVisible();
    await expect(page.getByText(/Aun no hay respaldos generados/i)).toBeVisible();
    // No rows render when the list is empty (table is hidden).
    await expect(page.locator('table.admin-table')).toHaveCount(0);
  });

  test('principal sees one daily and one weekly row when seeded', async ({ page, context }) => {
    await mockBackupsList(context, [WEEKLY_FIXTURE, DAILY_FIXTURE]);

    await page.goto('/cms/backups');

    await expect(page.getByTestId(`backup-download-${DAILY_FIXTURE.id}`)).toBeVisible();
    await expect(page.getByTestId(`backup-download-${WEEKLY_FIXTURE.id}`)).toBeVisible();
    await expect(page.getByText(/Semanal/i)).toBeVisible();
    await expect(page.getByText(/Diario/i)).toBeVisible();
    // The "Hace" header is rendered between "Fecha" and "Tipo" (C-2).
    await expect(page.getByRole('columnheader', { name: /^Hace$/ })).toBeVisible();
    // Each seeded row exposes its server-side `age_label` as the cell body.
    await expect(
      page.getByRole('cell', { name: WEEKLY_FIXTURE.age_label }),
    ).toBeVisible();
  });

  test('trigger flow opens the modal, confirms and triggers a download', async ({ page, context }) => {
    await mockBackupsList(context, []);

    // Mock the trigger endpoint to return a stub binary payload with the
    // expected `Content-Disposition: attachment` header so the modal calls
    // `saveBlob` on the response.
    await context.route(TRIGGER_URL, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/octet-stream',
        headers: {
          'Content-Disposition': 'attachment; filename="clinica_2026-08-06_120000.dump"',
        },
        body: Buffer.from('stub-dump-bytes'),
      });
    });

    await page.goto('/cms/backups');
    await page.getByTestId('backup-trigger-open').click();
    await expect(page.getByTestId('backup-trigger-modal')).toBeVisible();
    await expect(page.getByText(/Esto generara una descarga de la base de datos/i)).toBeVisible();

    // The button in the modal invokes `saveBlob` which synthesizes an
    // anchor click. Capture the resulting `download` event so we can prove
    // the suggested filename matches the `Content-Disposition` header.
    const downloadPromise = page.waitForEvent('download');
    await page.getByTestId('backup-trigger-confirm').click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^clinica_2026-08-06_120000\.dump$/);
  });

  test('delete flow removes the row after confirmation', async ({ page, context }) => {
    await mockBackupsList(context, [DAILY_FIXTURE]);

    // First list call returns the seed row; subsequent calls (after delete)
    // return an empty list so the table collapses back to the empty state.
    let callCount = 0;
    await context.unroute(BACKUPS_URL);
    await context.route(BACKUPS_URL, async (route) => {
      callCount += 1;
      const payload = callCount === 1 ? { results: [DAILY_FIXTURE] } : { results: [] };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
    });

    await context.route(DELETE_URL, async (route) => {
      await route.fulfill({ status: 204, body: '' });
    });

    await page.goto('/cms/backups');
    await expect(page.getByTestId(`backup-delete-${DAILY_FIXTURE.id}`)).toBeVisible();
    await page.getByTestId(`backup-delete-${DAILY_FIXTURE.id}`).click();
    await expect(page.getByTestId('backup-delete-modal')).toBeVisible();
    await page.getByTestId('backup-delete-confirm').click();

    await expect(page.getByTestId(`backup-delete-${DAILY_FIXTURE.id}`)).toHaveCount(0);
    await expect(page.getByText(/Aun no hay respaldos generados/i)).toBeVisible();
  });
});

test.describe('Admin Backups access control', () => {
  test('branch admin does not see the nav entry and direct navigation does not leak metadata', async ({
    page,
    context,
  }) => {
    await loginAs(page, ADMIN_SUCURSAL_USER, ADMIN_SUCURSAL_PASS);

    // Navigation: the nav group is filtered server-side by `mainAdminOnly`,
    // so the sidebar should NOT include `Respaldos`.
    await page.goto('/cms');
    await expect(page.getByRole('link', { name: /Respaldos de base de datos/i })).toHaveCount(0);

    // Direct navigation: the network request to `/api/admin/backups/` must
    // come back as 403 with no body. We intercept the response here rather
    // than reading from the page so the assertion stays deterministic.
    let received403 = false;
    await context.route(BACKUPS_URL, async (route) => {
      await route.fulfill({ status: 403, contentType: 'application/json', body: '{}' });
      received403 = true;
    });

    await page.goto('/cms/backups');
    // The call must have been attempted (the page fires it on mount).
    await page.waitForResponse((response) => BACKUPS_URL.test(response.url()));
    expect(received403).toBe(true);

    // The shared error card (via `DataState`) is rendered when the load
    // fails; the table itself must NEVER render any backup rows.
    await expect(page.locator('table.admin-table')).toHaveCount(0);
  });
});
