# Tasks: hide-catalog-orden

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~115 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

---

## Phase 1: Backend response shape (4 catalogs)

- [x] 1.1 Drop `Orden` from `campos-ficha` list response. In `backend/config/api_views.py`: delete line 1405 (`{"label": "Orden", "value": str(item.orden)}`), delete line 1418 (`"order": item.orden,` from the `values` dict), and delete line 1483 (`_catalog_field("order", "Orden", "number", ...)`). No surrounding code moves.

- [x] 1.2 Drop `Orden` from `secciones-ficha` list response. In `backend/config/api_views.py`: delete line 1804 (`{"label": "Orden", "value": str(item.orden)}`), delete line 1819 (`"order": item.orden,` from the `values` dict), and delete line 1866 (`_catalog_field("order", "Orden", "number", ...)`).

- [x] 1.3 Drop `Orden` from `especialidades` list response. In `backend/config/api_views.py`: delete line 1557 (`{"label": "Orden", "value": str(item.orden)}`), delete line 1567 (`"order": item.orden,` from the `values` dict), and delete line 1591 (`_catalog_field("order", "Orden", "number", ...)`). This catalog has no `fields` array entry for `order` in `sectores`, so the form field removal completes the hiding.

- [x] 1.4 Drop `Orden` from `sectores` list response. In `backend/config/api_views.py`: delete line 1728 (`{"label": "Orden", "value": str(item.orden)}`) and delete line 1739 (`"order": item.orden,` from the `values` dict). No form field entry exists for `order` in this catalog (confirmed at lines 1760–1764).

## Phase 2: Backend payload parsing (3 catalogs)

- [x] 2.1 Replace payload-driven `orden` assignment in `campos-ficha`. In `backend/config/api_views.py` around line 2029, change `obj.orden = order or 0` to `if instance is None: obj.orden = (FichaCampo.objects.aggregate(Max("orden"))["orden__max"] or 0) + 1`. Keep the `order = int_value(...)` read at line 1992 but do not assign it anywhere. On update (`instance is not None`) the line is simply absent — the existing DB value is untouched.

- [x] 2.2 Replace payload-driven `orden` assignment in `secciones-ficha`. In `backend/config/api_views.py` around line 2141, change `obj.orden = order or 0` to `if instance is None: obj.orden = (FichaSeccion.objects.aggregate(Max("orden"))["orden__max"] or 0) + 1`. Mirror the `sectores` pattern at lines 2095–2100 exactly.

- [x] 2.3 Replace payload-driven `orden` assignment in `especialidades`. In `backend/config/api_views.py` around line 2053, change `obj.orden = order or 0` to `if instance is None: obj.orden = (Especialidad.objects.aggregate(Max("orden"))["orden__max"] or 0) + 1`. Note: this branch currently always assigns `order or 0` regardless of create/update; apply the same create-only auto-assign. `Max` is already imported at line 11.

## Phase 3: Tests

- [x] 3.1 Update `backend/tests/test_secciones_ficha_crud.py`. In each create test (`test_create_section_with_sector_only_returns_201`, `test_create_section_with_proc_only_returns_201`, `test_create_section_with_both_bindings_returns_201`, `test_create_section_with_duplicate_codigo_in_same_proc_returns_400`, `test_create_section_with_same_codigo_in_different_proc_returns_201`): remove `"order": 1` from the payload and change `self.assertEqual(created.orden, 1)` to `self.assertEqual(created.orden, FichaSeccion.objects.aggregate(Max("orden"))["orden__max"])`. Add `from django.db.models import Max` to the imports. In `test_update_section_persists_changes` (line 419): change `self.assertEqual(section.orden, 9)` to `self.assertEqual(section.orden, 1)` (orden must be preserved, not overwritten to 9). Add a new test `test_update_with_order_9_preserves_orden` that sends `{"order": 9}` in the update payload and asserts `orden` is unchanged.

- [x] 3.2 Review `backend/tests/test_campos_ficha_validation.py` for any assertions that reference `orden` or `order`. Scan all test methods — the file covers `grupo_opciones` validation only. No changes expected, but if any `orden` assertions are found, update them to the auto-assign contract. Task: review and adjust if needed. Run `python manage.py test backend.tests.test_campos_ficha_validation` to confirm green baseline.

- [x] 3.3 Create `backend/tests/test_admin_catalog_especialidades_orden.py`. Mirror `test_admin_catalog_sectores.py` structure for the auto-assign + preserve behavior. Import `from django.db.models import Max`. In `setUp` create two `Especialidad` records with explicit `orden=1` and `orden=2`. Cover: `test_create_auto_assigns_max_plus_1` (POST without `order` field, assert `orden == 3`), `test_create_ignores_explicit_order` (POST with `order: 999`, assert `orden == 3` not 999), `test_update_preserves_orden` (update existing with `order: 9`, assert `orden` unchanged), `test_list_response_has_no_order_in_metadata` (GET list, assert no metadata entry with `label == "Orden"`), `test_list_response_has_no_order_in_values` (assert `"order" not in item["values"]`), `test_form_fields_has_no_order_entry` (assert no `fields` entry with `name == "order"`).

- [x] 3.4 Run `python manage.py test backend.tests.test_admin_catalog_sectores backend.tests.test_secciones_ficha_crud backend.tests.test_campos_ficha_validation backend.tests.test_admin_catalog_especialidades_orden` and confirm all pass. Address any failures before marking complete.

## Phase 4: Spec archive (deferred to sdd-archive)

- [ ] 4.1 Move `openspec/changes/hide-catalog-orden/specs/medical-form-section-editor/spec.md` → `openspec/specs/medical-form-section-editor/spec.md`. This is a deferred `sdd-archive` task — do NOT execute in the apply phase. Mark it as pending in the apply phase task list.

- [ ] 4.2 Move `openspec/changes/hide-catalog-orden/specs/catalog-orden-auto-assigned/spec.md` → `openspec/specs/catalog-orden-auto-assigned/spec.md`. Also deferred to `sdd-archive` phase.

---

## Implementation Order

Backend response stripping (Phase 1) → Payload parsing (Phase 2) → Tests (Phase 3) → Archive (Phase 4). Phases 1 and 2 are independent of each other but both must land before Phase 3 tests can green. Phase 4 is entirely separate and runs after the implementation PR merges.

## Notes

- `Max` is already imported at `api_views.py:11` — no new import needed.
- No database migration required; existing `orden` values are untouched.
- Frontend requires zero changes — `CatalogPage` renders `metadata` and `fields` dynamically.
- The `sectores` catalog already implements the auto-assign pattern (lines 2095–2100) — use it as the exact template for the three other catalogs.
