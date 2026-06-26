# Proposal: Visual Medical Form Editor

## Intent

Enable clinic admins to visually assemble medical form sections (`FichaSeccion`) and fields (`FichaCampo`) per `Sector` and/or `ProcEstetico` via UI, without code changes. The existing generic catalog forms are insufficient for field-type UX; this change adds type-aware editing and section management.

## Scope

### In Scope
- Full CRUD for `FichaSeccion` via admin catalog API (`secciones-ficha`) with dual binding to `sector` and/or `proc_estetico`
- UI enhancements to existing `campos-ficha` form: type-conditional fields per `tipo_campo` (TEXTO/NUMERO/FECHA/BOOLEANO/SELECCION/MULTISELECCION)
- Backend validation: `grupo_opciones` required when `tipo_campo ∈ {SELECCION, MULTISELECCION}`
- Frontend new tab `/cms/catalogos/secciones-ficha`
- Backend + frontend tests

### Out of Scope
- CRUD for `GrupoOpciones` / `OpcionCatalogo`
- Changes to `_serialize_medical_config` or `_validate_medical_step`
- Changes to `medical-form-sector-management` spec

## Capabilities

### New Capabilities
- `medical-form-section-editor`: Admin CRUD for `FichaSeccion` via `/api/admin/catalogos/secciones-ficha/`. Filters: `?active`, `?q` (codigo/nombre), `?sector=<id>`, `?proc_estetico=<id>`. Validates `UniqueConstraint(proc_estetico, codigo)` — same codigo allowed across different procedures.
- `medical-form-field-editor-enhancements`: Improved `campos-ficha` form with type-aware UI: textarea for TEXTO, number input for NUMERO, date picker for FECHA, checkbox for BOOLEANO, GrupoOpciones dropdown for SELECCION/MULTISELECCION. Validates `grupo_opciones` is set when required.

### Modified Capabilities
- None — `medical-form-sector-management` spec requirements are unchanged.

## Approach

1. **Backend — `secciones-ficha` catalog**: Extend `api_views.py` catalog machinery (5 integration points) following the `sectores` pattern. Title field: `nombre`. Unique constraint validation scoped per `proc_estetico`.
2. **Backend — `campos-ficha` validation**: In `_catalog_parse_payload`, add rule: if `tipo_campo` is SELECCION or MULTISELECCION and `grupo_opciones` is null → 400 error.
3. **Frontend — `secciones-ficha` tab**: New tab at `/cms/catalogos/secciones-ficha` with form: nombre, codigo, sector (optional dropdown), proc_estetico (optional dropdown), orden, activo. Validation: at least one of sector/proc_estetico must be set.
4. **Frontend — `campos-ficha` enhancements**: Conditional form fields based on `tipo_campo` selection. Show `es_multiple` and `permite_detalle` only for SELECCION/MULTISELECCION.
5. **Tests**: `test_secciones_ficha_crud.py` (backend), `test_campos_ficha_validation.py` (backend), `cms-catalogos-secciones-ficha.spec.ts` (E2E), `cms-catalogos-campos-ficha-ui-by-type.spec.ts` (E2E).

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api_views.py` | Modified | Add `secciones-ficha` catalog key (5 integration points) |
| `backend/catalogs/tests.py` | Modified | Add `test_secciones_ficha_crud.py`, `test_campos_ficha_validation.py` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modified | Add `secciones-ficha` to `catalogFallbackInfo` |
| `frontend/aesthetic-clinic/src/pages/cms/catalogos/` | Modified | New `SeccionesFichaTab.tsx`, enhanced `CamposFichaForm.tsx` with type-conditional UI |
| `frontend/aesthetic-clinic/tests/e2e/` | New | `cms-catalogos-secciones-ficha.spec.ts`, `cms-catalogos-campos-ficha-ui-by-type.spec.ts` |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Unique constraint per procedure not enforced in UI list | Med | List filters default to current proc; display codigo scoped to proc |
| Dual binding (sector + proc_estetico) creates ambiguous scope | Med | UI requires at least one; clear labeling of effective scope |
| `_validate_medical_step` tight coupling | Low | No changes to serialization; add integration test coverage |
| Admin requests GrupoOpciones editor | Med | Out-of-scope is documented; capture as separate change |

## Rollback Plan

1. Revert `api_views.py` catalog additions — remove `secciones-ficha` from all 5 integration points
2. Revert `_catalog_parse_payload` validation change
3. Delete `frontend/aesthetic-clinic/src/pages/cms/catalogos/SeccionesFichaTab.tsx`
4. Revert `AdminCatalogsPage.tsx` changes
5. Rollback migration not needed — all models already exist; only catalog wiring changes

## Dependencies

- `sectores-especializados-ficha-medica` (merged) — provides `Sector` model and `FichaSeccion.sector` FK
- `backend/catalogs/migrations/0006_seed_sectores_and_reassign_fichaseccion.py` (merged) — pre-existing

## Success Criteria

- [ ] `GET /api/admin/catalogos/secciones-ficha/` returns 200 with filtered results
- [ ] `GET /api/admin/catalogos/secciones-ficha/?sector=<id>&proc_estetico=<id>` returns scoped sections
- [ ] Creating section with duplicate `(proc_estetico, codigo)` returns 400
- [ ] Creating a SELECCION field without `grupo_opciones` returns 400
- [ ] Campos-ficha form renders correct input type per `tipo_campo`
- [ ] E2E: secciones-ficha CRUD via UI completes without errors
- [ ] E2E: campos-ficha type-conditional UI renders correctly
- [ ] Existing `test_medical_form_by_sector.py` tests still pass