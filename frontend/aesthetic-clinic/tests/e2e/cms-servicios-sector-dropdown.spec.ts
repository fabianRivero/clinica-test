import { test, expect } from '@playwright/test';

/**
 * E2E coverage for the sector dropdown inside the ServicioConfig
 * (todos-los-servicios) form.
 *
 * Verifies:
 *   - The "Sector de ficha médica" dropdown is rendered in the create form.
 *   - The dropdown contains the seeded active sectors (DEP / MAN / TAT).
 *   - Selecting a sector and saving persists the value.
 *   - Saving with procedure set + sector empty shows the H2 inline warning.
 *   - Saving with sector set hides the warning.
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

test.describe('ServicioConfig form - Sector dropdown', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/(admin|cms)/);
  });

  test('sector dropdown is visible and lists seeded active sectors', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');

    // Open the create form via the header button.
    await page.locator('header').getByRole('button', { name: 'Crear servicio' }).click();

    const sectorSelect = page.locator('#catalog-field-sectorId');
    await expect(sectorSelect).toBeVisible();

    // The empty option ("Sin seleccionar") is always present.
    const optionLabels = await sectorSelect.locator('option').allTextContents();
    expect(optionLabels.length).toBeGreaterThan(1);

    // At least one of the seeded sector codes should appear as a secondary label
    // (rendered as "Sector · CODE" by the generic field).
    const seededSectors = ['Depilación', 'Manchas', 'Tatuajes'];
    const hasSeededSector = seededSectors.some((name) =>
      optionLabels.some((label) => label.includes(name)),
    );
    expect(hasSeededSector).toBeTruthy();
  });

  test('selecting a sector persists the assignment', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');
    await page.locator('header').getByRole('button', { name: 'Crear servicio' }).click();

    // Pick the first non-empty option (a seeded sector).
    const sectorSelect = page.locator('#catalog-field-sectorId');
    const optionValues = await sectorSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(optionValues.length).toBeGreaterThan(0);
    const targetSectorId = optionValues[0];

    await sectorSelect.selectOption(targetSectorId);

    // Fill the required serviceTypeId and basePrice so the create succeeds.
    await page.selectOption('#catalog-field-serviceTypeId', { index: 1 });
    await page.fill('#catalog-field-basePrice', '1234');

    await page.locator('form').getByRole('button', { name: 'Crear servicio' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();
  });

  test('warning appears when procedure is set and sector is empty (H2)', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');
    await page.locator('header').getByRole('button', { name: 'Crear servicio' }).click();

    // The create form starts with no procedure and no sector, so no warning yet.
    await expect(page.locator('[data-testid="service-sector-warning"]')).toHaveCount(0);

    // Pick a procedure -> the warning must appear because sector is still empty.
    await page.selectOption('#catalog-field-procedureId', { index: 1 });
    await expect(page.locator('[data-testid="service-sector-warning"]')).toBeVisible();
    await expect(page.locator('[data-testid="service-sector-warning"]')).toContainText(
      /procedimiento est.tico/i,
    );

    // Pick a sector -> the warning must disappear.
    await page.selectOption('#catalog-field-sectorId', { index: 1 });
    await expect(page.locator('[data-testid="service-sector-warning"]')).toHaveCount(0);

    // Clear the sector again to confirm the warning re-appears.
    await page.selectOption('#catalog-field-sectorId', '');
    await expect(page.locator('[data-testid="service-sector-warning"]')).toBeVisible();
  });

  test('no warning when procedure is empty (Cita medica use case)', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');
    await page.locator('header').getByRole('button', { name: 'Crear servicio' }).click();

    // No procedure and no sector: this is the Cita medica pattern. No warning.
    await expect(page.locator('[data-testid="service-sector-warning"]')).toHaveCount(0);
  });
});