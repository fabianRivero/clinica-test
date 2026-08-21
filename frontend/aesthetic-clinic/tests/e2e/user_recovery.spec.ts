import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';
const CLIENT_USER = 'cliente.e2e';
const CLIENT_ORIGINAL_PASS = 'test123456';

/**
 * E2E coverage for the admin-assisted user recovery flow.
 *
 * The Playwright config resets the database before each run
 * (tests/global-setup.ts runs backend/scripts/reset_test_db_local.sh),
 * so we don't need to restore user passwords between tests.
 *
 * Tests:
 *  - full recovery flow: admin resets cliente.e2e → cliente logs in
 *    with the temporary password → ForcePasswordChange modal is
 *    inescapable → user picks a new password → modal unmounts and
 *    navigation works normally.
 *  - admin search + reveal: admin searches for cliente.e2e by
 *    username, opens the 'Ver username' modal, confirms the username
 *    is shown. Read-only — leaves the DB unchanged.
 */

test.describe('User Recovery — full reset + forced change flow', () => {
  test('admin resets cliente.e2e, cliente logs in with temp password and is forced to change it', async ({
    page,
    context,
  }) => {
    // Step 1: admin login
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/cms/);

    // Step 2: admin searches cliente.e2e by username
    await page.goto('/cms/equipo/recuperar');
    await expect(page.locator('h1, h2').filter({ hasText: 'Recuperar acceso' }).first()).toBeVisible();
    const searchInput = page.locator('input[name="q"]');
    await expect(searchInput).toBeVisible();
    await searchInput.fill(CLIENT_USER);
    await page.locator('button[type="submit"]', { hasText: 'Buscar' }).click();

    // Step 3: cliente.e2e is in the results
    const row = page.locator('tr', { hasText: CLIENT_USER });
    await expect(row).toBeVisible();

    // Step 4: admin opens the reset modal and triggers the reset
    await row.locator('button', { hasText: 'Resetear contrasena' }).click();
    await expect(
      page.locator('h2, strong').filter({ hasText: 'Resetear contrasena' }).first(),
    ).toBeVisible();
    const confirmButton = page.locator('button', {
      hasText: 'Generar contrasena temporal',
    });
    await expect(confirmButton).toBeVisible();
    await confirmButton.click();

    // Step 5: the temporary password is rendered
    const tempPasswordInput = page.locator('input[aria-label="Contrasena temporal"]');
    await expect(tempPasswordInput).toBeVisible();
    const temporaryPassword = await tempPasswordInput.inputValue();
    expect(temporaryPassword).toBeTruthy();
    expect(temporaryPassword.length).toBeGreaterThanOrEqual(8);
    // The temp password must NOT match the original — that would defeat
    // the whole point of the reset.
    expect(temporaryPassword).not.toBe(CLIENT_ORIGINAL_PASS);

    // Close the modal.
    await page.locator('button', { hasText: 'Cerrar' }).first().click();

    // Step 6: admin logs out
    await page.locator('button', { hasText: 'Cerrar sesion' }).first().click();
    await expect(page).toHaveURL(/\/login/);

    // Step 7: cliente.e2e logs in with the temporary password.
    await context.clearCookies();
    await page.fill('input[name="username"]', CLIENT_USER);
    await page.fill('input[name="password"]', temporaryPassword);
    await page.click('button[type="submit"]');

    // Step 8: the inescapable ForcePasswordChange overlay is rendered
    // and the regular Cliente dashboard does not load (the modal is
    // mounted on top of Routes in App.tsx).
    await expect(page).toHaveURL(/\/cliente/);
    const forceModal = page.locator('[aria-labelledby="force-password-title"]');
    await expect(forceModal).toBeVisible();
    await expect(
      page.locator('h2#force-password-title'),
    ).toHaveText('Cambia tu contrasena');

    // The username/email/telefono fields are deliberately hidden in the
    // forced-change modal — only password fields are visible.
    await expect(page.locator('input[name="username"]')).toHaveCount(0);
    await expect(page.locator('input[name="email"]')).toHaveCount(0);
    await expect(page.locator('input[name="telefono"]')).toHaveCount(0);

    // Step 9: pick a new password and submit.
    const newPassword = 'freshpass123';
    await page.locator('input[name="password"]').fill(newPassword);
    await page.locator('input[name="confirmPassword"]').fill(newPassword);
    await page.locator('button[type="submit"]', { hasText: 'Actualizar contrasena' }).click();

    // Step 10: the modal unmounts and the cliente dashboard is
    // interactive.
    await expect(forceModal).not.toBeVisible();
    // The cliente dashboard always renders the welcome card.
    await expect(page.locator('text=Resumen').first()).toBeVisible({ timeout: 15000 });
  });
});

test.describe('User Recovery — admin search and reveal username', () => {
  test('admin searches by username and sees the cliente.e2e row; reveals username in modal', async ({
    page,
    context,
  }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/cms/);

    await page.goto('/cms/equipo/recuperar');
    const searchInput = page.locator('input[name="q"]');
    await searchInput.fill(CLIENT_USER);
    await page.locator('button[type="submit"]', { hasText: 'Buscar' }).click();

    const row = page.locator('tr', { hasText: CLIENT_USER });
    await expect(row).toBeVisible();

    // The row renders the username in a <code> tag.
    await expect(row.locator('code', { hasText: CLIENT_USER })).toBeVisible();

    // Open the 'Ver username' modal.
    await row.locator('button', { hasText: 'Ver username' }).click();

    const usernameModal = page.locator('[aria-label="Username del usuario"]');
    await expect(usernameModal).toBeVisible();
    const usernameInput = usernameModal.locator('input[aria-label="Username del usuario"]');
    await expect(usernameInput).toHaveValue(CLIENT_USER);
  });
});