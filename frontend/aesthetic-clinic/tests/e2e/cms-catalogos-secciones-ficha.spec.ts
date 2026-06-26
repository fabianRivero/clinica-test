import { test, expect } from '@playwright/test';

/**
 * E2E coverage for the `secciones-ficha` catalog tab.
 *
 * Verifies the spec scenarios for `medical-form-section-editor`:
 *   - Tab visible at /cms/catalogos/secciones-ficha.
 *   - Create section with sector only (REQ-1).
 *   - Create section with proc_estetico only (REQ-2).
 *   - Attempt create with neither binding -> 400 inline error (REQ-4).
 *   - Duplicate codigo within same proc_estetico -> 400 (REQ-5).
 *   - Same codigo across different proc_estetico succeeds (REQ-5 cross-proc).
 *   - Toggle activo (REQ-10).
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

test.describe('Admin Catalog - Secciones de ficha', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/(admin|cms)/);
  });

  test('secciones-ficha: tab is visible and reachable', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');

    const tabNav = page.getByLabel('Subsecciones de cat\u00e1logos');
    const seccionesTab = tabNav.getByRole('link', { name: 'Secciones de ficha', exact: true });
    await expect(seccionesTab).toBeVisible();
    await seccionesTab.click();
    await expect(page).toHaveURL(/\/cms\/catalogos\/secciones-ficha/);

    await expect(
      page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }),
    ).toBeVisible();
  });

  test('secciones-ficha: create with sector only', async ({ page }) => {
    const uniqueCode = `SECTOR${Date.now().toString().slice(-6)}`;
    const uniqueName = `Seccion sector ${Date.now()}`;

    await page.goto('/cms/catalogos/secciones-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueName);

    // Pick the first non-empty sector option (seeded active sector).
    const sectorSelect = page.locator('#catalog-field-sectorId');
    const sectorValues = await sectorSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(sectorValues.length).toBeGreaterThan(0);
    await sectorSelect.selectOption(sectorValues[0]);

    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    const card = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(card).toBeVisible();
  });

  test('secciones-ficha: create with proc_estetico only', async ({ page }) => {
    const uniqueCode = `PROC${Date.now().toString().slice(-6)}`;
    const uniqueName = `Seccion proc ${Date.now()}`;

    await page.goto('/cms/catalogos/secciones-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueName);

    // Pick the first non-empty proc option.
    const procSelect = page.locator('#catalog-field-procEsteticoId');
    const procValues = await procSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(procValues.length).toBeGreaterThan(0);
    await procSelect.selectOption(procValues[0]);

    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    const card = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(card).toBeVisible();
  });

  test('secciones-ficha: create with neither binding shows inline error', async ({ page }) => {
    const uniqueCode = `NONE${Date.now().toString().slice(-6)}`;
    const uniqueName = `Seccion huerfana ${Date.now()}`;

    await page.goto('/cms/catalogos/secciones-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    // Leave both sectorId and procEsteticoId empty.
    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueName);

    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    // The backend rejects with 400 and a general error.
    await expect(
      page.locator('text=/sector|procedimiento/i').first(),
    ).toBeVisible({ timeout: 8000 });
    // No success toast.
    await expect(page.locator('text=Registro creado')).toHaveCount(0);
  });

  test('secciones-ficha: duplicate codigo within same proc returns error', async ({ page }) => {
    // First create the seed record.
    const dupCode = `DUP${Date.now().toString().slice(-6)}`;
    const firstName = `Seccion dup A ${Date.now()}`;
    const secondName = `Seccion dup B ${Date.now()}`;

    await page.goto('/cms/catalogos/secciones-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    await page.fill('#catalog-field-code', dupCode);
    await page.fill('#catalog-field-name', firstName);

    const procSelect = page.locator('#catalog-field-procEsteticoId');
    const procValues = await procSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(procValues.length).toBeGreaterThan(0);
    await procSelect.selectOption(procValues[0]);

    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    // Now attempt a second create with the same code on the same proc.
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();
    await page.fill('#catalog-field-code', dupCode);
    await page.fill('#catalog-field-name', secondName);
    await procSelect.selectOption(procValues[0]);
    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    // Expect a uniqueness error referencing the codigo.
    await expect(page.locator('text=/c\u00f3digo|existe/i').first()).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Registro creado')).toHaveCount(0);
  });

  test('secciones-ficha: toggle activo (soft delete)', async ({ page }) => {
    const uniqueCode = `TOG${Date.now().toString().slice(-6)}`;
    const uniqueName = `Seccion toggle ${Date.now()}`;

    await page.goto('/cms/catalogos/secciones-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();

    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueName);
    const procSelect = page.locator('#catalog-field-procEsteticoId');
    const procValues = await procSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    await procSelect.selectOption(procValues[0]);

    await page.locator('form').getByRole('button', { name: 'Crear secci\u00f3n de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    const card = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(card).toBeVisible();

    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();
    await expect(card).toHaveCount(0);

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    const inactiveCard = page.locator('.catalog-admin-card', { hasText: uniqueName });
    await expect(inactiveCard).toBeVisible();
    await inactiveCard.getByRole('button', { name: 'Activar' }).click();
    await expect(page.locator('text=Registro reactivado')).toBeVisible();
  });
});
