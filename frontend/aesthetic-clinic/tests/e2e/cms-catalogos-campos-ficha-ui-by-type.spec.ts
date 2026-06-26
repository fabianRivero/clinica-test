import { test, expect } from '@playwright/test';

/**
 * E2E coverage for the type-conditional UI on the `campos-ficha`
 * admin catalog form.
 *
 * Verifies the spec scenarios for `medical-form-field-editor-enhancements`:
 *   - Form renders the generic widget for each fieldType.
 *   - `isMultiple` and `allowsDetail` are hidden for non-selection types (REQ-9).
 *   - Saving SELECCION without `optionGroupId` -> backend 400 (REQ-5).
 *   - Saving SELECCION with `optionGroupId` -> success.
 *   - TEXTO without `optionGroupId` -> success (REQ-1).
 */

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

test.describe('Admin Catalog - Campos de ficha - UI by tipo_campo', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/(admin|cms)/);
  });

  test('campos-ficha: isMultiple and allowsDetail are hidden for TEXTO', async ({ page }) => {
    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    // Pick TEXTO from the fieldType dropdown.
    await page.selectOption('#catalog-field-fieldType', 'TEXTO');

    // The hidden hint appears.
    await expect(page.locator('[data-testid="campos-ficha-non-selection-hint"]')).toBeVisible();

    // The isMultiple / allowsDetail checkboxes are NOT rendered.
    await expect(page.locator('#catalog-field-isMultiple')).toHaveCount(0);
    await expect(page.locator('#catalog-field-allowsDetail')).toHaveCount(0);
  });

  test('campos-ficha: isMultiple and allowsDetail are hidden for NUMERO', async ({ page }) => {
    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    await page.selectOption('#catalog-field-fieldType', 'NUMERO');
    await expect(page.locator('[data-testid="campos-ficha-non-selection-hint"]')).toBeVisible();
    await expect(page.locator('#catalog-field-isMultiple')).toHaveCount(0);
    await expect(page.locator('#catalog-field-allowsDetail')).toHaveCount(0);
  });

  test('campos-ficha: isMultiple and allowsDetail are visible for SELECCION', async ({ page }) => {
    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    await page.selectOption('#catalog-field-fieldType', 'SELECCION');

    // No hint shown.
    await expect(page.locator('[data-testid="campos-ficha-non-selection-hint"]')).toHaveCount(0);

    // The checkboxes are rendered.
    await expect(page.locator('#catalog-field-isMultiple')).toBeVisible();
    await expect(page.locator('#catalog-field-allowsDetail')).toBeVisible();
  });

  test('campos-ficha: isMultiple and allowsDetail are visible for MULTISELECCION', async ({ page }) => {
    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    await page.selectOption('#catalog-field-fieldType', 'MULTISELECCION');

    await expect(page.locator('[data-testid="campos-ficha-non-selection-hint"]')).toHaveCount(0);
    await expect(page.locator('#catalog-field-isMultiple')).toBeVisible();
    await expect(page.locator('#catalog-field-allowsDetail')).toBeVisible();
  });

  test('campos-ficha: SELECCION without optionGroupId returns 400', async ({ page }) => {
    const suffix = Date.now().toString().slice(-6);
    const codigo = `UI-SEL-${suffix}`;
    const etiqueta = `UI seleccion sin grupo ${suffix}`;

    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    // sectionId required: pick the first non-empty option.
    const sectionSelect = page.locator('#catalog-field-sectionId');
    const sectionValues = await sectionSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(sectionValues.length).toBeGreaterThan(0);
    await sectionSelect.selectOption(sectionValues[0]);

    await page.fill('#catalog-field-code', codigo);
    await page.fill('#catalog-field-label', etiqueta);
    await page.selectOption('#catalog-field-fieldType', 'SELECCION');
    // Deliberately leave optionGroupId empty.

    await page.locator('form').getByRole('button', { name: 'Crear campo de ficha' }).click();

    // Expect a backend error referencing grupo de opciones.
    await expect(
      page.locator('text=/grupo de opciones|optionGroupId/i').first(),
    ).toBeVisible({ timeout: 8000 });
    await expect(page.locator('text=Registro creado')).toHaveCount(0);
  });

  test('campos-ficha: SELECCION with optionGroupId succeeds', async ({ page }) => {
    const suffix = Date.now().toString().slice(-6);
    const codigo = `UI-SEL2-${suffix}`;
    const etiqueta = `UI seleccion con grupo ${suffix}`;

    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    const sectionSelect = page.locator('#catalog-field-sectionId');
    const sectionValues = await sectionSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(sectionValues.length).toBeGreaterThan(0);
    await sectionSelect.selectOption(sectionValues[0]);

    await page.fill('#catalog-field-code', codigo);
    await page.fill('#catalog-field-label', etiqueta);
    await page.selectOption('#catalog-field-fieldType', 'SELECCION');

    const groupSelect = page.locator('#catalog-field-optionGroupId');
    const groupValues = await groupSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    expect(groupValues.length).toBeGreaterThan(0);
    await groupSelect.selectOption(groupValues[0]);

    await page.locator('form').getByRole('button', { name: 'Crear campo de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();
  });

  test('campos-ficha: TEXTO without optionGroupId succeeds', async ({ page }) => {
    const suffix = Date.now().toString().slice(-6);
    const codigo = `UI-TXT-${suffix}`;
    const etiqueta = `UI texto sin grupo ${suffix}`;

    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();

    const sectionSelect = page.locator('#catalog-field-sectionId');
    const sectionValues = await sectionSelect.locator('option').evaluateAll((options) =>
      options
        .filter((opt) => (opt as HTMLOptionElement).value !== '')
        .map((opt) => (opt as HTMLOptionElement).value),
    );
    await sectionSelect.selectOption(sectionValues[0]);

    await page.fill('#catalog-field-code', codigo);
    await page.fill('#catalog-field-label', etiqueta);
    await page.selectOption('#catalog-field-fieldType', 'TEXTO');

    await page.locator('form').getByRole('button', { name: 'Crear campo de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();
  });
});
