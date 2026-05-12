import { test, expect } from '@playwright/test';

const SUCURSAL_USER = 'admin.sucursal';
const SUCURSAL_PASS = 'admin123456';

test.describe('Test 2 y 4: Admin Sucursal - Aislamiento y Especialistas', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', SUCURSAL_USER);
    await page.fill('input[name="password"]', SUCURSAL_PASS);
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Sucursal: Sucursal Sur')).toBeVisible();
  });

  test('TEST 2: Flujo de cliente como Admin de Sucursal (Aislamiento)', async ({ page }) => {
    const uniqueName = `Sucursal ${Date.now()}`;
    
    await page.getByRole('link', { name: 'Prospectos', exact: true }).click();
    await page.getByRole('link', { name: 'Registrar prospecto' }).click();
    
    // El admin de sucursal NO debe poder elegir sucursal
    await expect(page.locator('select[name="sucursal_id"]')).not.toBeVisible();
    
    await page.fill('input[name="nombres"]', uniqueName);
    await page.fill('input[name="apellidos"]', 'Sur');
    await page.fill('input[name="telefono"]', '73333333');
    await page.click('button:has-text("Guardar prospecto")');

    await expect(page.locator('tr', { hasText: uniqueName })).toBeVisible();
  });

  test('TEST 4: Crear especialista como Admin de Sucursal (Sucursal Bloqueada)', async ({ page }) => {
    // Vamos por el camino que funcionaba: Gestionar especialistas
    await page.click('text=Gestionar especialistas');
    
    // Ahora, dentro de la pagina de gestion, pulsamos el boton de crear
    // Usamos 'main' para ignorar el sidebar
    const crearBtn = page.locator('main').locator('text=Crear especialista').first();
    await crearBtn.waitFor({ state: 'visible' });
    await crearBtn.click();
    
    // Esperar a que la URL cambie a la de creacion
    await page.waitForURL('**/crear');
    
    const usernameInput = page.locator('#staff-username');
    await usernameInput.waitFor({ state: 'visible', timeout: 10000 });
    await usernameInput.fill(`esp.suc.${Date.now()}`);
    
    await page.fill('#staff-primer-nombre', 'Especialista');
    await page.fill('#staff-apellido-paterno', 'Sucursal');
    await page.fill('#staff-password', 'esp123456');
    await page.fill('#staff-ci', `CI${Date.now()}`);
    await page.fill('#staff-email', `esp.suc.${Date.now()}@test.com`);

    // El admin de sucursal NO debe elegir sucursal (se asigna auto en el backend)
    const branchSelect = page.locator('select[name="sucursal_id"], #staff-branch');
    if (await branchSelect.isVisible()) {
        await expect(branchSelect).toBeDisabled();
    }

    // Seleccionar una especialidad (es un grid de checkboxes)
    // Buscamos una especialidad que sabemos que existe por el reset de base de datos
    await page.click('.checkbox-pill >> text=Consulta medica');

    await page.click('button[type="submit"]');
    await expect(page.locator('text=Especialista creado')).toBeVisible();
  });
});
