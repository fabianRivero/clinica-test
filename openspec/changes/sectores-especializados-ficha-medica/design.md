# Design: Specialized Sectors for Medical Forms

## Technical Approach

Introduce `Sector` as a new catalog entity that groups `FichaSeccion` records independently of `ProcEstetico`. `ServicioConfig` gets an optional `sector` FK; when set, the medical form step filters sections by that sector instead of by procedure. The existing `proc_estetico` FK on `FichaSeccion` is preserved as nullable for backward compatibility.

## Architecture Decisions

### ADR-1: Sector as a new entity, not a re-use of ProcEstetico

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Re-use `ProcEstetico` as sector | Tight coupling: service identity (what you sell) equals form grouping; blocks new services with same form but different name | Rejected |
| New `Sector` model | Adds a catalog entity; requires new CRUD screen and API | **Chosen** |

**Rationale**: A service like "Depilación día de la madre" must share the same form as "Depilación definitiva" without being the same `ProcEstetico`. Sector decouples form reuse from service identity, matching the product requirement. `ProcEstetico` remains the authoritative entity for service naming and pricing.

### ADR-2: Nullable FK from ServicioConfig to Sector

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Required `sector` FK | Forces all existing services to have a sector; breaking change | Rejected |
| Nullable `sector` FK | Backward compatible; existing services with no sector show no form (legacy behavior) | **Chosen** |

**Rationale**: "Cita médica" has no `proc_estetico` and must continue showing no form. Adding a nullable FK preserves this behavior without requiring a migration of all existing records.

### ADR-3: FichaSeccion keeps proc_estetico as nullable legacy FK

| Option | Tradeoff | Decision |
|--------|----------|----------|
| (a) Replace FK: drop `proc_estetico`, add `sector` | Forces reassignment of all `FichaSeccion` records; risk of data loss if migration fails | Rejected |
| (b) Add nullable `sector`, deprecate `proc_estetico` | Two FKs coexist;FichaSeccion can filter by either; backward-compatible | **Chosen** |
| (c) Junction table `FichaSeccionSector` (many-to-many) | Over-engineered; sector is a single-parent grouping, not shared | Rejected |

**Rationale**: `proc_estetico` on `FichaSeccion` is already nullable in practice (the field exists, and the seed already creates sections for multiple procedures). Adding `sector` as the primary filter path with `proc_estetico` as a fallback preserves all existing `FichaSeccion` data while enabling the new sector-based routing.

## Data Flow

```
Prospect Conversion Step 3 — Medical Form Load

Admin ──selects service──► Frontend (step 2 submits serviceConfigId)
                                   │
                                   ▼
                         Frontend (step 3 requests medical config)
                                   │
                         GET /api/admin/prospect-conversion/{id}/medical/
                                   │
                                   ▼
                         Backend: _serialize_medical_config(service_config)
                                   │
              ┌────────────────────┴────────────────────┐
              │                                             │
   service_config.sector exists?               service_config.sector is NULL
              │                                             │
   Filter: FichaSeccion.objects            Filter: FichaSeccion.objects
     .filter(sector=sector, activo=True)      .filter(proc_estetico=proc, activo=True)
              │                                             │
              └────────────────────┬────────────────────┘
                                   │
                         Serialize sections + shared config
                                   │
                                   ▼
                         JSON response → Frontend renders form
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/catalogs/models.py` | Modify | Add `Sector(CatalogoEditableModel)` with `codigo`, `nombre`; unique constraints on `codigo` and `nombre` (case-insensitive via custom validators) |
| `backend/catalogs/models.py` | Modify | Add `sector = FK(Sector, null=True, blank=True)` to `ServicioConfig` |
| `backend/clinical/models.py` | Modify | Add `sector = FK(Sector, null=True, blank=True)` to `FichaSeccion`; keep `proc_estetico` as-is |
| `backend/config/api_views.py` | Modify | Add `sectores` to `_catalog_key_to_slug` set, `_catalog_summary_descriptor`, `_catalog_page_data`, `_catalog_parse_payload`, `model_map` in `_catalog_get_instance` |
| `backend/config/prospect_conversion_views.py` | Modify | Update `_serialize_medical_config` to branch on `service_config.sector` |
| `backend/accounts/management/commands/seed_pdf_baseline.py` | Modify | Create 3 Sector seeds; reassign `FichaSeccion` FKs from `proc_estetico` to `sector` |
| `backend/catalogs/admin.py` | Modify | Register `Sector` model |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | Modify | Add `'sectores'` to `catalogFallbackInfo` |
| `frontend/aesthetic-clinic/src/components/admin/` | Modify | If `AdminCatalogTabs` hardcodes catalog list, add `sectores` there |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepMedical.tsx` | No change | Backend now returns sector-filtered sections; frontend renders them as-is |
| `frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx` | No change (service form dropdown) | The service edit/create form dropdown will be added in a follow-up story for `todos-los-servicios` catalog expansion |
| `backend/clinical/migrations/00XX_add_sector_models.py` | Create | Migration: add `catalogs_sector` table; add `sector` FK to `ServicioConfig` and `FichaSeccion`; make `proc_estetico` on `FichaSeccion` explicit nullable |
| `backend/clinical/migrations/00XY_migrate_ficha_seccion_sector.py` | Create | Data migration: create Sector records, set `FichaSeccion.sector` FK from seed mapping |

## Interfaces / Contracts

### Sector model

```python
# backend/catalogs/models.py
class Sector(CatalogoEditableModel):
    codigo = models.CharField(max_length=20, unique=True)  # e.g. "DEP", "MAN", "TAT"
    nombre = models.CharField(max_length=120, unique=True)  # e.g. "Depilación"

    class Meta:
        db_table = "catalogs_sector"
        ordering = ("orden", "nombre")
        constraints = [
            models.UniqueConstraint(
                models.functions.Lower("codigo"),
                name="uniq_sector_codigo_ci",
            ),
            models.UniqueConstraint(
                models.functions.Lower("nombre"),
                name="uniq_sector_nombre_ci",
            ),
        ]
```

### _serialize_medical_config branching logic (pseudocode)

```python
# backend/config/prospect_conversion_views.py  — around line 490
def _serialize_medical_config(service_config):
    # ... shared catalog lookups (antecedentes, implantes, etc.) unchanged ...

    if service_config is None:
        return {"procedureId": None, "procedureName": "", "sections": [], **shared_config}

    if service_config.sector_id is not None:
        # NEW: filter by sector
        sections = (
            FichaSeccion.objects
            .filter(sector=service_config.sector_id, activo=True)
            .prefetch_related("campos__grupo_opciones__opciones")
            .order_by("orden", "nombre")
        )
    elif service_config.proc_estetico_id is not None:
        # LEGACY: filter by proc_estetico (backward compat)
        sections = (
            FichaSeccion.objects
            .filter(proc_estetico=service_config.proc_estetico_id, activo=True)
            .prefetch_related("campos__grupo_opciones__opciones")
            .order_by("orden", "nombre")
        )
    else:
        sections = []

    return {
        "procedureId": service_config.proc_estetico_id,
        "procedureName": service_config.proc_estetico.proceso if service_config.proc_estetico else "",
        "sections": [_serialize_section(s) for s in sections],
        **shared_config,
    }
```

### Admin Catalog API contract for sectores

Endpoints are identical to existing catalogs — no new URL patterns needed:

```
GET  /api/admin/catalogos/sectores/?active=true|false|all&q=<search>
POST /api/admin/catalogos/sectores/crear/
PATCH /api/admin/catalogos/sectores/<id>/actualizar/
POST  /api/admin/catalogos/sectores/<id>/estado/
```

Payload shape for create/update:
```json
{
  "name": "Depilación",
  "code": "DEP",
  "description": "Formularios para servicios de depilación",
  "active": true,
  "order": 1
}
```

Response item shape (matches all other catalogs):
```json
{
  "id": 1,
  "title": "Depilación",
  "subtitle": "DEP",
  "active": true,
  "meta": [{"label": "Descripción", "value": "..."}],
  "data": {"name": "Depilación", "code": "DEP", "description": "...", "order": 1}
}
```

Uniqueness: `code` and `name` are enforced case-insensitive unique at the DB constraint level. The API returns HTTP 400 with `"Ya existe un registro con esos datos clave."` on violation (same as other catalogs).

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Backend unit | `Sector` CRUD, uniqueness constraints | `backend/tests/test_sector_crud.py` — Django unittest |
| Backend unit | `_serialize_medical_config` branches: sector set / sector null+proc set / both null | `backend/tests/test_medical_form_by_sector.py` |
| Backend unit | Prospect conversion step 3 with sector-null service returns empty sections | `backend/tests/test_prospect_conversion.py` (extend) |
| Frontend E2E | Sector CRUD screen at `/admin/catalogos` | `frontend/tests/e2e/cms-catalogos-sectores.spec.ts` — Playwright |
| Frontend E2E | Service form shows sector dropdown populated with active sectors | `frontend/tests/e2e/cms-servicios-sector-dropdown.spec.ts` — Playwright |

## Migration / Rollout

1. **Migration 1 — Schema**: Add `catalogs_sector` table; add nullable `sector` FK to `ServicioConfig` and `FichaSeccion`; make `proc_estetico` on `FichaSeccion` explicit nullable (already is in DB terms but not in model).
2. **Migration 2 — Data**: Seed creates 3 Sector records (`DEP`="Depilación", `MAN`="Manchas", `TAT`="Tatuajes"). For each `FichaSeccion` where `proc_estetico.codigo` maps to `PUNTO_D` (depilación/definitiva or manchas), set `sector=DEP`. Where `proc_estetico.codigo` maps to `PUNTO_E`, set `sector=TAT`. Leave `sector=NULL` for any section that doesn't match (future sections explicitly assigned).
3. **Feature flag**: Not required — all existing services with null sector retain legacy behavior (no form shown).

**Note**: Per the proposal, "Depilación definitiva" and "Tratamiento de manchas" both belong to the SAME Sector "Depilación" (A3 decision). Both map to `PUNTO_D` in the seed and both are assigned to the `DEP` sector.

## Open Questions

- [ ] Should the Sector CRUD screen be at `/admin/catalogos/sectores` (tabs inside existing `AdminCatalogsPage`) or a separate route? Recommendation: tab inside `AdminCatalogsPage` following the existing pattern.
- [ ] The service form (`todos-los-servicios` catalog) needs a sector dropdown — is this in scope for this change or a follow-up? Recommendation: follow-up story since it touches a different catalog's form definition.
