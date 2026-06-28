# Tasks: grupo-opciones-editor

## Review Workload Forecast

| Metric | Value |
|--------|-------|
| Backend sub-endpoints OpcionCatalogo (5 handlers + URLs) | ~150 lines |
| Backend tests | ~150 lines |
| Frontend API client + modal | ~150 lines |
| Frontend E2E | ~80 lines |
| **Total forecast** | **~530 lines** |
| Review budget | 400 lines |
| **Budget risk** | **High** |
| **Chained PRs recommended** | **Yes** |
| **Decision needed before apply** | **Yes** |

### Recommended PR split (feature-branch-chain)
- **PR 1 — Backend core** (~300 lines): sub-endpoints OpcionCatalogo + tests.
- **PR 2 — Frontend + integration** (~230 lines): API client + modal + E2E.

---

## PR 1 — Backend Core

### Phase 1: Sub-endpoints `OpcionCatalogo` (Backend)

#### 1.1 Register nested URL routes
- **File**: `backend/config/api_urls.py` (o equivalente donde se registran las rutas admin)
- **Action**: Agregar las 5 rutas nested para `grupos-opciones/<int:grupo_id>/opciones/`.
- **Acceptance**: las rutas están registradas y Django check pasa.

#### 1.2 Handler GET (list con filtros)
- **File**: `backend/config/api_views.py`
- **Action**: Handler para `GET /api/admin/catalogos/grupos-opciones/<grupo_id>/opciones/`. Filtros: `?active=true|false|all`, `?q=` (busca codigo + nombre + valor). Verifica que grupo exista (404 si no). Devuelve shape `{"items": [...]}`.
- **Acceptance**: GET con filtros válidos retorna 200 + items correctos; GET a grupo inexistente retorna 404.

#### 1.3 Handler POST crear (single)
- **File**: `backend/config/api_views.py`
- **Action**: Handler para `POST .../opciones/crear/`. Payload: `codigo`, `nombre`, `valor`, `orden` (opcional, auto-asigna max+1), `activo`. Validación: required fields + duplicate codigo en grupo + grupo existe. Devuelve shape `{"detail": "...", "item": {...}}`.
- **Acceptance**: POST válido retorna 201; duplicate retorna 400 con mensaje claro; grupo inexistente retorna 404.

#### 1.4 Handler POST crear-multiples (bulk)
- **File**: `backend/config/api_views.py`
- **Action**: Handler para `POST .../opciones/crear-multiples/`. Payload: `{"options": [{codigo, nombre, valor, orden, activo}, ...]}`. Wrap en `transaction.atomic()`. Valida cada item; si alguna falla, rollback todas.
- **Acceptance**: bulk válido retorna 201 con todas las opciones creadas; bulk con un item inválido retorna 400 y NINGUNA se crea.

#### 1.5 Handler POST actualizar
- **File**: `backend/config/api_views.py`
- **Action**: Handler para `POST .../opciones/<opcion_id>/actualizar/`. Payload: `nombre`, `valor`, `orden`, `activo`. Valida opcion existe.
- **Acceptance**: PUT válido retorna 200 con item actualizado; opción inexistente retorna 404.

#### 1.6 Handler POST estado (toggle)
- **File**: `backend/config/api_views.py`
- **Action**: Handler para `POST .../opciones/<opcion_id>/estado/`. Payload: `{"active": true|false}`. Setea `activo`.
- **Acceptance**: toggle válido retorna 200; opción inexistente retorna 404.

### Phase 2: Tests (Backend)

#### 2.1 Tests de list
- **File**: `backend/tests/test_opcion_catalogo_api.py` (nuevo)
- **Covers**:
  - List vacío para grupo sin opciones.
  - List con varias opciones.
  - List filtrado por `?active=true`.
  - List filtrado por `?active=false`.
  - List filtrado por `?q=`.
  - List a grupo inexistente → 404.

#### 2.2 Tests de create (single)
- **File**: mismo `backend/tests/test_opcion_catalogo_api.py`
- **Covers**:
  - Create válido.
  - Create sin `codigo` → 400.
  - Create sin `nombre` → 400.
  - Create sin `valor` → 400.
  - Create con `codigo` duplicado en el mismo grupo → 400.
  - Create con `orden` auto-asignado.
  - Create con grupo inexistente → 404.

#### 2.3 Tests de create-multiples (bulk)
- **File**: mismo
- **Covers**:
  - Bulk válido con 3 opciones.
  - Bulk con un item duplicado → 400 y rollback de las anteriores (verificar count).
  - Bulk con un item con campo faltante → 400 y rollback.
  - Bulk con grupo inexistente → 404.

#### 2.4 Tests de update y toggle
- **File**: mismo
- **Covers**:
  - Update válido.
  - Update opción inexistente → 404.
  - Toggle activo true → false.
  - Toggle opción inexistente → 404.

#### 2.5 Test de integración con serialización downstream
- **File**: mismo o nuevo
- **Covers**:
  - Opción inactiva NO aparece en `_serialize_medical_config` del campo que la usa.

#### 2.6 Run full backend test suite
- **Command**: `cd backend && python manage.py test`
- **Acceptance**: tests nuevos pasan; tests preexistentes no se rompen.

---

## PR 2 — Frontend + Integration

### Phase 3: API Client + Modal UI

#### 3.1 API client: agregar funciones para sub-endpoints
- **File**: `frontend/aesthetic-clinic/src/services/api/admin.ts`
- **Action**: Agregar funciones: `getGroupOptions(grupoId, filters)`, `createGroupOption(grupoId, payload)`, `createGroupOptionsBulk(grupoId, options)`, `updateGroupOption(grupoId, opcionId, payload)`, `toggleGroupOptionState(grupoId, opcionId, active)`.
- **Acceptance**: TypeScript compila sin errores (`npx tsc --noEmit`).

#### 3.2 Componente `OptionGroupModal`
- **File**: nuevo, ej. `frontend/aesthetic-clinic/src/components/admin/OptionGroupModal.tsx`
- **Action**: Modal con header (nombre grupo + X cerrar), toggle de filtro activas/todas/inactivas, búsqueda, lista de opciones con editar + toggle por row, checkbox por row (sin acción todavía), botón "Agregar opción", sub-form para crear/editar dentro del modal.
- **Acceptance**: modal se abre/cierra correctamente; `data-testid="option-group-modal"` accesible.

#### 3.3 Botón "Administrar opciones" en cada item de `grupos-opciones`
- **File**: `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx`
- **Action**: En `AdminOptionGroupsCatalogPage` (o equivalente), agregar un botón "Administrar opciones" en cada card/row. Al click, abre `OptionGroupModal` con el `grupo.id`.
- **Acceptance**: el botón es visible y funcional en cada item.

#### 3.4 Integración del modal con el API client
- **File**: `OptionGroupModal.tsx`
- **Action**: usar las funciones del API client (3.1) para list/create/edit/toggle dentro del modal. Refetch después de cada mutación.
- **Acceptance**: crear una opción desde el modal refresca la lista.

#### 3.5 Accesibilidad básica del modal
- **File**: `OptionGroupModal.tsx`
- **Action**: ESC cierra. Focus trap. Aria labels en controles.
- **Acceptance**: navegando con teclado, el modal funciona.

### Phase 4: E2E Tests

#### 4.1 Test E2E del modal de opciones
- **File**: `frontend/aesthetic-clinic/tests/e2e/admin_general.spec.ts` (extender)
- **Covers**:
  - Abrir modal desde un grupo.
  - Crear opción individual.
  - Editar opción.
  - Toggle activo.
  - Cerrar modal.
  - Verificar que opción inactiva no aparece en `_serialize_medical_config` (via API directa).

### Phase 5: Verificación

#### 5.1 Backend checks
- `cd backend && python manage.py check`
- `cd backend && python manage.py test tests.test_opcion_catalogo_api tests.test_campos_ficha_validation tests.test_medical_form_by_sector`

#### 5.2 Frontend checks
- `cd frontend/aesthetic-clinic && npx tsc --noEmit`
- `cd frontend/aesthetic-clinic && npm run lint`
- `cd frontend/aesthetic-clinic && npm run build`
- `cd frontend/aesthetic-clinic && npx playwright test admin_general.spec.ts -g "modal de opciones"`

#### 5.3 Smoke test manual
- **Action**: Crear un grupo desde `/cms/catalogos/grupos-opciones`, abrir modal, agregar 3 opciones, editar una, toggle una, cerrar. Confirmar que la lista refleja los cambios.
- **Acceptance**: flujo completo end-to-end funciona.

---

## Dependencies

- 1.x → 1.1 must finish before 1.2/1.3/1.4/1.5/1.6.
- 1.x → 2.x (tests) must run after handlers exist.
- 3.1 → 3.2 (modal can use API client only after functions exist).
- 3.2 → 3.3 (button wires up after modal exists).
- 3.3 → 3.4 (integration after wiring).
- 4.1 depends on 3.4 (E2E tests need functional UI).

## Success Criteria

- [ ] All 11 scenarios in `opcion-catalogo-api/spec.md` pass.
- [ ] All 11 scenarios in `grupo-opciones-editor-modal/spec.md` pass.
- [ ] `python manage.py test` exits 0 (new + regression).
- [ ] `npx tsc --noEmit`, `npm run lint`, `npm run build`, `npx playwright test` exit 0.
- [ ] Manual: admin can create group → open modal → add options → edit → toggle → close.
- [ ] Existing `grupos-opciones` catalog CRUD still works without regression.
- [ ] `_serialize_medical_config` test verifies inactive option disappears.