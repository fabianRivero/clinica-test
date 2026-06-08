import { test, expect } from '@playwright/test';

const CLIENT_USER = 'cliente.e2e';
const CLIENT_PASS = 'test123456';
const ADMIN_SUCURSAL_USER = 'admin.sucursal';
const ADMIN_SUCURSAL_PASS = 'admin123456';

/**
 * Task 4.3: Playwright E2E — telefono cascade to Cliente
 *
 * Test flow:
 * 1. Login as Cliente
 * 2. Click on profile chip to open modal
 * 3. Edit telefono field
 * 4. Save changes
 * 5. Verify telefono was updated in the database via API
 */
test.describe('Profile Edit Modal — telefono cascade to Cliente', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', CLIENT_USER);
    await page.fill('input[name="password"]', CLIENT_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/cliente/);
  });

  test('edit telefono via profile modal and verify cascade to Cliente', async ({ page }) => {
    const newTelefono = `7${Date.now().toString().slice(-7)}`;

    // Step 1: Click on profile chip to open the edit modal
    const profileChip = page.locator('.profile-chip--client');
    await expect(profileChip).toBeVisible();
    await profileChip.click();

    // Step 2: Wait for modal to appear
    const modal = page.locator('.booking-modal-overlay');
    await expect(modal).toBeVisible();
    await expect(page.locator('.booking-modal-header h2')).toHaveText('Editar perfil');

    // Step 3: Clear and update the telefono field
    const telefonoInput = page.locator('input[name="telefono"]');
    await expect(telefonoInput).toBeVisible();
    await telefonoInput.clear();
    await telefonoInput.fill(newTelefono);

    // Step 4: Submit the form
    await page.locator('button[type="submit"]').click();

    // Step 5: Wait for modal to close
    await expect(modal).not.toBeVisible();

    // Step 6: Verify the telefono was updated by fetching the session
    const response = await page.request.get('/api/auth/me/', {
      headers: {
        Accept: 'application/json',
      },
    });
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.user.telefono).toBe(newTelefono);
  });

  test('modal opens on profile chip click and closes on cancel', async ({ page }) => {
    // Click profile chip to open modal
    const profileChip = page.locator('.profile-chip--client');
    await profileChip.click();

    // Verify modal is open
    await expect(page.locator('.booking-modal-overlay')).toBeVisible();
    await expect(page.locator('.booking-modal-header h2')).toHaveText('Editar perfil');

    // Click cancel button
    await page.locator('button:has-text("Cancelar")').click();

    // Verify modal is closed
    await expect(page.locator('.booking-modal-overlay')).not.toBeVisible();
  });
});

test.describe('Profile Edit Modal — ADMIN_SUCURSAL role', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_SUCURSAL_USER);
    await page.fill('input[name="password"]', ADMIN_SUCURSAL_PASS);
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Sucursal: Sucursal Sur')).toBeVisible();
  });

  test('edit telefono via profile modal as ADMIN_SUCURSAL', async ({ page }) => {
    const newTelefono = `7${Date.now().toString().slice(-7)}`;

    // Step 1: Click on profile chip to open the edit modal (AdminLayout uses .profile-chip without modifier)
    const profileChip = page.locator('.profile-chip');
    await expect(profileChip).toBeVisible();
    await profileChip.click();

    // Step 2: Wait for modal to appear
    const modal = page.locator('.booking-modal-overlay');
    await expect(modal).toBeVisible();
    await expect(page.locator('.booking-modal-header h2')).toHaveText('Editar perfil');

    // Step 3: Clear and update the telefono field
    const telefonoInput = page.locator('input[name="telefono"]');
    await expect(telefonoInput).toBeVisible();
    await telefonoInput.clear();
    await telefonoInput.fill(newTelefono);

    // Step 4: Submit the form
    await page.locator('button[type="submit"]').click();

    // Step 5: Wait for modal to close
    await expect(modal).not.toBeVisible();

    // Step 6: Verify the telefono was updated by fetching the session
    const response = await page.request.get('/api/auth/me/', {
      headers: {
        Accept: 'application/json',
      },
    });
    expect(response.status()).toBe(200);

    const data = await response.json();
    expect(data.user.telefono).toBe(newTelefono);
  });
});
