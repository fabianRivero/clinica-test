import { test, expect } from '@playwright/test';

/**
 * E2E coverage for the sectores tab in the admin catalog UI.
 *
 * Verifies:
 *   - The "Sectores" tab is reachable at /cms/catalogos/sectores.
 *   - Admin can create a Sector (code + nombre + descripcion).
 *   - Admin can toggle a Sector to inactive and back to active.
 *   - Newly created Sector appears in the catalog list.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

test.describe('Admin Catalog - Sectores', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/(admin|cms)/);
  });

  test('sectores: tab visible, create flow, toggle and list refresh', async ({ page }) => {
    const uniqueCode = `QA${Date.now().toString().slice(-6)}`;
    const uniqueName = `Sector QA ${Date.now()}`;

    // 1. Navigate to the Sectores tab.
    await page.goto('/cms/catalogos/sectores');
    await expect(page).toHaveURL(/\/cms\/catalogos\/sectores/);

    // 2. Verify the page-level "Crear sector" header button is rendered.
    await expect(
      page.locator('header').getByRole('button', { name: 'Crear sector' }),
    ).toBeVisible();

    // 3. Open the create form and fill required fields.
    await page.locator('header').getByRole('button', { name: 'Crear sector' }).click();
    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueName);

    // 4. Submit the create form.
    await page.locator('form').getByRole('button', { name: 'Crear sector' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    // 5. Verify the new sector appears in the catalog list.
    const card = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(card).toBeVisible();

    // 6. Toggle the sector to inactive.
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    // 7. Verify it disappears from the active filter.
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueName })).toHaveCount(0);

    // 8. Reactivate the sector.
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    const inactiveCard = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(inactiveCard).toBeVisible();
    await inactiveCard.getByRole('button', { name: 'Activar' }).click();
    await expect(page.locator('text=Registro reactivado')).toBeVisible();

    // 9. Verify it reappears in the active filter.
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueName })).toHaveCount(1);
  });

  test('sectores: tab link is present in catalog navigation', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');
    // The "Sectores" link appears both in the sidebar and in the section tabs.
    // We scope to the section tabs nav to assert the tab is rendered.
    const tabNav = page.getByLabel('Subsecciones de cat\u00e1logos');
    const sectoresTab = tabNav.getByRole('link', { name: 'Sectores', exact: true });
    await expect(sectoresTab).toBeVisible();
    await sectoresTab.click();
    await expect(page).toHaveURL(/\/cms\/catalogos\/sectores/);
  });
});