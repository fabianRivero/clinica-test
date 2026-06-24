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

test.describe('Catalog list: search + active filter + create', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.clearCookies();
    await page.goto('/login');
    await page.fill('input[name="username"]', ADMIN_USER);
    await page.fill('input[name="password"]', ADMIN_PASS);
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/\/(admin|cms)/);
  });

  test('tipos-servicio: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Tipo Test ${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/tipos-servicio');

    // The header Create button and the form submit button share the same label,
    // so we scope to <header> for the reveal click and to <form> for the submit.
    await page.locator('header').getByRole('button', { name: 'Crear tipo de servicio' }).click();

    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear tipo de servicio' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('especialidades: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Espec Test ${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/especialidades');
    await page.locator('header').getByRole('button', { name: 'Crear especialidad' }).click();
    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear especialidad' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('categorias-gasto: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Cat Test ${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/categorias-gasto');
    await page.locator('header').getByRole('button', { name: 'Crear categoria' }).click();
    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear categoria' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('procedimientos-esteticos: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Proc Test ${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/procedimientos-esteticos');
    await page.locator('header').getByRole('button', { name: 'Crear procedimiento' }).click();
    await page.selectOption('#catalog-field-procedureTypeId', { index: 1 });
    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear procedimiento' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('todos-los-servicios: create, deactivate and filter flow', async ({ page }) => {
    await page.goto('/cms/catalogos/todos-los-servicios');

    // Before creating anything, switching to "Inactivos" should show the empty
    // state (no inactive items exist yet) — covers WARNING #6 (Sin registros copy).
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('text=Sin registros')).toBeVisible();
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'all');

    await page.locator('header').getByRole('button', { name: 'Crear servicio' }).click();
    await page.selectOption('#catalog-field-serviceTypeId', { index: 1 });
    // Capture the label of the selected Tipo de servicio so we can search by it.
    const serviceTypeLabel = await page
      .locator('#catalog-field-serviceTypeId option')
      .nth(1)
      .textContent();
    expect(serviceTypeLabel).toBeTruthy();
    const searchNeedle = (serviceTypeLabel ?? '').trim().split(' ')[0];
    await page.fill('#catalog-field-basePrice', '100');
    await page.locator('form').getByRole('button', { name: 'Crear servicio' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card').first()).toBeVisible();

    // Search by a substring of the selected Tipo de servicio — the new card should
    // remain visible (covers WARNING #5: search must be exercised on this catalog).
    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card').first()).toBeVisible();
    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');

    // Deactivate every visible card using a while-loop that is robust to the
    // list refetch + re-render triggered by the toggle. The previous
    // for-loop captured `count` upfront and then iterated by position, which
    // skipped every other item after the first reload (covers CRITICAL #1).
    // A fresh locator is built on every iteration so it always targets the
    // current first "Desactivar" button after each reload.
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const deactivateBtn = page.getByRole('button', { name: 'Desactivar' }).first();
      const isVisible = await deactivateBtn
        .isVisible({ timeout: 1000 })
        .catch(() => false);
      if (!isVisible) {
        break;
      }
      await deactivateBtn.click({ force: true });
      await expect(page.locator('text=Registro desactivado').first()).toBeVisible();
      // Give the post-toggle refetch a moment to settle so the next iteration
      // does not race with an in-flight re-render.
      await page.waitForLoadState('networkidle');
    }

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card').first()).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card')).toHaveCount(0);
  });

  test('campos-ficha: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Campo Test ${Date.now()}`;
    const uniqueCode = `TEST_${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/campos-ficha');
    await page.locator('header').getByRole('button', { name: 'Crear campo de ficha' }).click();
    await page.selectOption('#catalog-field-sectionId', { index: 1 });
    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-label', uniqueTitle);
    await page.selectOption('#catalog-field-fieldType', { index: 1 });
    await page.locator('form').getByRole('button', { name: 'Crear campo de ficha' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    // Search by the internal `codigo` (covers the Q-OR search across code+label).
    await page.fill('input[type="search"][aria-label="Buscar registros"]', uniqueCode);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('patologias-cutaneas: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Pat Test ${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/patologias-cutaneas');
    await page.locator('header').getByRole('button', { name: 'Crear patología cutanea' }).click();
    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear patología cutanea' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });

  test('grupos-opciones: search, filter and deactivate flow', async ({ page }) => {
    const uniqueTitle = `Grupo Test ${Date.now()}`;
    const uniqueCode = `GRUPO_${Date.now()}`;
    const searchNeedle = uniqueTitle.split(' ')[1];

    await page.goto('/cms/catalogos/grupos-opciones');
    await page.locator('header').getByRole('button', { name: 'Crear grupo de opciones' }).click();
    await page.fill('#catalog-field-code', uniqueCode);
    await page.fill('#catalog-field-name', uniqueTitle);
    await page.locator('form').getByRole('button', { name: 'Crear grupo de opciones' }).click();
    await expect(page.locator('text=Registro creado')).toBeVisible();

    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', searchNeedle);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    // Search by the internal `codigo` (covers the Q-OR search across code+name).
    await page.fill('input[type="search"][aria-label="Buscar registros"]', uniqueCode);
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.fill('input[type="search"][aria-label="Buscar registros"]', '');
    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    const card = page.locator('.catalog-admin-card', { hasText: uniqueTitle });
    await card.getByRole('button', { name: 'Desactivar' }).click();
    await expect(page.locator('text=Registro desactivado')).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'false');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toBeVisible();

    await page.selectOption('select[aria-label="Filtrar por estado"]', 'true');
    await expect(page.locator('.catalog-admin-card', { hasText: uniqueTitle })).toHaveCount(0);
  });
});
