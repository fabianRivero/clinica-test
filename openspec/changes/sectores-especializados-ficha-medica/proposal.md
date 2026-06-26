# Proposal: Specialized Sectors for Medical Forms

## Intent

Allow new services to reuse existing medical form questions without duplicating seeds or code. Currently, `FichaSeccion` filters by `ProcEstetico` — preventing a new service like "Depilación día de la madre" from sharing "Depilación definitiva"'s form. Introducing `Sector` as an intermediate grouping between `ServicioConfig` and `FichaSeccion` decouples form reuse from service identity.

## Scope

### In Scope
- New `catalogs.Sector` model with CRUD admin UI
- Add nullable `sector` FK to `ServicioConfig` (B1 decision: no FK from `ProcEstetico`)
- Add nullable `sector` FK to `FichaSeccion` as replacement for `proc_estetico` FK
- Update `_serialize_medical_config` to filter sections by sector when service has one
- Backend seed migration: create 3 sectors (Depilación, Manchas, Tatuajes) and reassign existing `FichaSeccion` records
- Sector CRUD via existing admin catalog API pattern
- Frontend: sector dropdown in service create/edit form; sector management screen

### Out of Scope
- Deleting `ProcEstetico` model (remains for service naming/pricing)
- Multi-sector assignment per service
- Migrating existing persisted `FichaClinica` / `FichaRespuestaCampo` data (schema-only migration)

## Capabilities

### New Capabilities
- `medical-form-sector-management`: Enables admin users to create, list, update, and toggle Sector records. Sectors define which medical form sections (`FichaSeccion`) apply to a service. A service without a sector shows no medical form (legacy backward-compatibility).

### Modified Capabilities
- `admin-catalog-management`: Extended to include `sectores` as a sixth catalog with the same API contract as existing five catalogs. Title field: `nombre`.

## Approach

1. **Model**: Add `Sector(nombre, codigo, descripcion, activo, orden)` to `catalogs/`. Make `FichaSeccion.sector` FK nullable (replacing `proc_estetico` FK). Add `ServicioConfig.sector` FK nullable.

2. **Filter change**: In `_serialize_medical_config`, when `service_config.sector` is set, filter `FichaSeccion` by `sector=service_config.sector` instead of by `proc_estetico`. If sector is null, use legacy behavior (no form or `proc_estetico`-based form for backward compat).

3. **Data migration**: Seed creates 3 Sector records. A migration script reassigns existing `FichaSeccion`:
   - Depilación sector ← "Depilación definitiva" sections (PUNTO_D)
   - Manchas sector ← "Tratamiento de manchas" sections (PUNTO_D, same sector as depilation per A3)
   - Tatuajes sector ← "Borrado de tatuajes" sections (PUNTO_E)

4. **API**: Sector enters the same admin catalog pattern at `/api/admin/catalogos/sectores/`.

5. **UI**: React admin adds sector dropdown to `todos-los-servicios` create/edit form. New `sectores` screen under `/cms/catalogos/`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/catalogs/models.py` | Modified | New `Sector` model; `ServicioConfig` gets `sector` FK |
| `backend/clinical/models.py` | Modified | `FichaSeccion` gets `sector` FK (replaces `proc_estetico` FK) |
| `backend/config/prospect_conversion_views.py` | Modified | `_serialize_medical_config` filters by sector |
| `backend/catalogs/admin.py` | Modified | Register `Sector` model |
| `backend/accounts/management/commands/seed_pdf_baseline.py` | Modified | Create Sector seed records; assign sections to sectors |
| `frontend/aesthetic-clinic/cms/catalogos/` | Modified | Sector CRUD screen + service form dropdown |
| `backend/` migration | New | Data migration to populate sectors and reassign sections |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing form data stored with `proc_estetico` FK becomes orphaned | Low | `FichaSeccion` is a template (not persisted per-operation); actual answers link to `FichaClinica` via `FichaCampo` |
| Sector null on existing services shows empty form | Low | Legacy: services with null sector and null proc_estetico already show no form; test covers this |
| Admin creates sector with no sections (admin error) | Medium | Document requirement that sectors need sections; UI shows warning |

## Rollback Plan

1. Revert migration: `Sector` and `sector` FKs remain but unused
2. Revert `_serialize_medical_config` to original `proc_estetico`-based filtering
3. Re-seed `FichaSeccion.proc_estetico` from backup if data was corrupted
4. Revert `ServicioConfig.sector` to null for all records via migration

## Dependencies

- None (no external services)

## Success Criteria

- [ ] New service "Depilación día de la madre" can be created with sector=Depilación and sees the same form sections as "Depilación definitiva"
- [ ] Service with `sector=null` (e.g., "Cita médica") shows no medical form in conversion flow
- [ ] `python manage.py test` passes including new tests for sector-based filtering
- [ ] Sector CRUD screen reachable at `/cms/catalogos/sectores/` and fully functional
- [ ] Service create/edit form shows sector dropdown with ability to select or leave empty
