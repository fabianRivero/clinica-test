import { test, expect } from '@playwright/test';

const ADMIN_USER = 'admin.general';
const ADMIN_PASS = 'admin123456';

test.describe('Test 1 y 3: Admin General - Cliente y Especialista', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/admin/);
  });

  test('TEST 1: Flujo completo de creacion de cliente y validaciones', async ({ page }) => {
    const uniqueName = `Gral ${Date.now()}`;

    // 1. Crear Prospecto
    await page.getByRole('link', { name: 'Prospectos', exact: true }).click();
    await page.getByRole('link', { name: 'Registrar prospecto' }).click();
    await page.fill('input[name="nombres"]', uniqueName);
    await page.fill('input[name="apellidos"]', 'Test');
    await page.fill('input[name="telefono"]', '71111111');
    await page.click('button:has-text("Guardar prospecto")');

    // 2. Iniciar Conversion
    const row = page.locator('tr', { hasText: uniqueName });
    await row.waitFor({ state: 'visible' });
    await row.getByRole('link', { name: 'Convertir' }).click();
    await expect(page).toHaveURL(/\/convertir/);

    // PASO 1: Datos Usuario
    await page.fill('input[name="ci"]', '123456');
    await page.fill('input[name="fechaNacimiento"]', '1990-01-01');
    const passInput = page.locator('input[placeholder="Contraseña"]');
    if (await passInput.isVisible()) {
      await passInput.fill('test1234');
      await page.fill('input[placeholder="Confirmar contraseña"]', 'test1234');
    }
    await page.click('button:has-text("Guardar y continuar")');

    // PASO 2: Operacion (Validaciones)
    await expect(page.locator('input[name="precioTotal"]')).toBeVisible();

    // 1. Intento vacio para validar campos obligatorios
    await page.click('button:has-text("Guardar y continuar")');
    await expect(page.locator('text=/obligatoria|requerido/i').first()).toBeVisible();

    // 2. Rellenar correctamente
    // Seleccionar servicio por etiqueta (mas fiable)
    await page.getByLabel(/Servicio/i).selectOption({ index: 1 });

    await page.fill('input[name="zonaGeneral"]', 'Cuerpo');
    await page.fill('input[name="zonaEspecifica"]', 'Piernas');
    await page.fill('input[name="precioTotal"]', '850');

    // Rellenar las fechas (hoy o futura)
    const today = new Date().toISOString().split('T')[0];

    // 1. Fecha de Inicio / Registro (solo si esta habilitado)
    const fechaInicio = page.locator('input[name="fechaInicio"], label:has-text("Fecha de registro") input, label:has-text("Fecha de inicio") input').first();
    if (await fechaInicio.isEnabled()) {
      await fechaInicio.fill(today);
    }

    // 2. Cuota 1 (buscamos específicamente el que dice Cuota 1)
    const cuota1 = page.locator('label:has-text("Cuota 1") input');
    if (await cuota1.isEnabled()) {
      await cuota1.fill(today);
    }

    // Clic definitivo para pasar al Paso 3
    await page.click('button:has-text("Guardar y continuar")');

    // PASO 3: Ficha Medica (Validaciones)
    await expect(page.locator('text=/An.lisis est.tico/i').first()).toBeVisible();
    await page.click('button:has-text("Guardar ficha y continuar")');
    await expect(page.locator('text=/Debes adjuntar el PDF/i').first()).toBeVisible();
  });

  test('TEST 3: Crear especialista nuevo (Elegir sucursal)', async ({ page }) => {
    // 1. Ir a gestionar especialistas
    await page.click('text=Gestionar especialistas');
    
    // 2. Pulsar el boton de crear (el de la pagina principal, no el del sidebar)
    const crearBtn = page.locator('main').locator('text=Crear especialista').first();
    await crearBtn.waitFor({ state: 'visible' });
    await crearBtn.click();
    
    // 3. Esperar a que cargue el formulario
    await page.waitForURL('**/crear');
    const usernameInput = page.locator('#staff-username');
    await usernameInput.waitFor({ state: 'visible', timeout: 10000 });

    // 4. Rellenar datos basicos
    await usernameInput.fill(`esp.gral.${Date.now()}`);
    await page.fill('#staff-primer-nombre', 'Especialista');
    await page.fill('#staff-apellido-paterno', 'General');
    await page.fill('#staff-password', 'esp123456');
    await page.fill('#staff-ci', `CI${Date.now()}`);
    await page.fill('#staff-email', `esp.gral.${Date.now()}@test.com`);

    // 5. Validar sucursal (Si es Admin General global puede elegir, si tiene sucursal asignada estara bloqueado)
    const branchSelect = page.locator('#staff-branch, select[name="sucursal_id"]');
    if (await branchSelect.isVisible()) {
        const isEnabled = await branchSelect.isEnabled();
        if (isEnabled) {
            await branchSelect.selectOption({ label: 'Sucursal Sur' });
        } else {
            console.log('La sucursal esta bloqueada para este usuario, continuando...');
        }
    }

    // 6. Seleccionar especialidad (checkboxes)
    await page.click('.checkbox-pill >> text=Dermatologia laser');

    // 7. Guardar y verificar
    await page.click('button[type="submit"]');
    await expect(page.locator('text=Especialista creado')).toBeVisible();
  });
});
