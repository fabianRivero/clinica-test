# Verify Report: hide-catalog-orden

**Date**: 2026-07-01
**Change**: hide-catalog-orden
**Project**: clinica-test
**Execution mode**: interactive (adversarial verify, fresh context)

---

## Status: `ok`

---

## Executive Summary

All 56 tests pass. The implementation matches both spec files exactly. The four catalogs (`especialidades`, `campos-ficha`, `secciones-ficha`, `sectores`) have `orden` stripped from metadata, values, and form fields. The three writable catalogs correctly auto-assign `orden = max+1` on create and preserve it on update. The `tipos-procedimiento` catalog (correctly out-of-scope) still exposes `order` and is unchanged. No frontend changes are needed or present.

---

## 1. Spec → Implementation Cross-Check

### `catalog-orden-auto-assigned/spec.md`

| Scenario ID | Scenario | Spec file | Status | Evidence | Notes |
|---|---|---|---|---|---|
| create-auto-1 | Create without `order` field → `orden = max+1` | catalog-orden-auto-assigned | **PASS** | `api_views.py:2050-2052` (especialidades), `2021-2023` (campos-ficha), `2143-2145` (secciones-ficha), `2094-2099` (sectores) | All 4 branches use `aggregate(Max("orden"))["orden__max"] or 0) + 1` |
| create-auto-2 | Create with explicit `order: 999` → ignored, `orden = max+1` | catalog-orden-auto-assigned | **PASS** | `api_views.py:1984` (`_ = int_value("order"...)` — especialidades), `2044`, `2110` | `_` discard + create-only assignment pattern consistent across 3 branches |
| update-preserve-1 | Update with `order: 999` → `orden` unchanged | catalog-orden-auto-assigned | **PASS** | `api_views.py:2050` (else branch absent), `2021` (else absent), `2143` (else absent) | All 3 mutable catalogs assign `obj.orden` ONLY inside `if instance is None:` |
| metadata-hidden-1 | List: no `Orden` in metadata | catalog-orden-auto-assigned | **PASS** | `api_views.py:1553-1558` (especialidades), `1398-1407` (campos-ficha), `1794-1803` (secciones-ficha), `1720-1727` (sectores) | Confirmed by `test_admin_catalog_especialidades_orden:68-81` |
| values-hidden-1 | List: no `order` in values | catalog-orden-auto-assigned | **PASS** | `api_views.py:1560-1563` (especialidades), `1408-1417` (campos-ficha), `1805-1810` (secciones-ficha), `1728-1732` (sectores) | Confirmed by `test_admin_catalog_especialidades_orden:83-95` |
| fields-hidden-1 | Form: no `order` field entry | catalog-orden-auto-assigned | **PASS** | `api_views.py:1583-1586` (especialidades), `1437-1484` (campos-ficha), `1829-1856` (secciones-ficha), `1752-1757` (sectores) | Confirmed by `test_admin_catalog_especialidades_orden:97-109` |
| ordering-unchanged-1 | List ordered by `orden, nombre` | catalog-orden-auto-assigned | **PASS** | `api_views.py:1546`, `1389`, `1786`, `1713` | `order_by("orden", "nombre")` confirmed in all 4 branches |

### `medical-form-section-editor/spec.md`

| Scenario ID | Scenario | Spec file | Status | Evidence | Notes |
|---|---|---|---|---|---|
| edit-preserves-orden | Update section → `orden` unchanged | medical-form-section-editor | **PASS** | `api_views.py:2143` (create-only assign); `test_secciones_ficha_crud.py:420-445` | `test_update_section_persists_changes` sends `order: 9`, asserts `orden == 1` |
| update-ignores-order-field | Update with `order: 999` → ignored | medical-form-section-editor | **PASS** | `test_secciones_ficha_crud.py:447-472` | `test_update_with_order_9_preserves_orden` covers this explicitly |
| REQ-11-removed | Manual reorder via PATCH removed | medical-form-section-editor | **PASS** | No `obj.orden =` in update branch of secciones-ficha (`api_views.py:2138-2146`) | Auto-assign contract replaces manual assignment |

---

## 2. Code Review — `backend/config/api_views.py`

### `especialidades` branch (lines 1537–1588, 2037–2053)

| Check | Expected | Found | Status |
|---|---|---|---|
| Metadata: no `Orden` entry | Absent | Lines 1553-1558 contain only `Descripción` + `Especialistas vinculados` | **PASS** |
| Values: no `order` key | Absent | Lines 1560-1563: only `name`, `description` | **PASS** |
| Fields: no `order` entry | Absent | Lines 1583-1586: only `name`, `description` | **PASS** |
| Create: read `order` but discard | `_ = int_value("order", ...)` | Line 2044 | **PASS** |
| Create: assign `max+1` | `obj.orden = max_orden + 1` inside `if instance is None` | Lines 2050-2052 | **PASS** |
| Update: do NOT touch `obj.orden` | No assignment in else/update branch | Confirmed absent | **PASS** |

### `campos-ficha` branch (lines 1378–1486, 1975–2024)

| Check | Expected | Found | Status |
|---|---|---|---|
| Metadata: no `Orden` entry | Absent | Lines 1398-1407: only `Código`, `Tipo`, `Grupo de opciones`, `Requerido`, `Detalle` | **PASS** |
| Values: no `order` key | Absent | Lines 1408-1417: no `order` | **PASS** |
| Fields: no `order` entry | Absent | Lines 1437-1484: no `order` field | **PASS** |
| Create: read `order` but discard | `_ = int_value("order", ...)` | Line 1984 | **PASS** |
| Create: assign `max+1` | `obj.orden = max_orden + 1` inside `if instance is None` | Lines 2021-2023 | **PASS** |
| Update: do NOT touch `obj.orden` | No assignment in else/update branch | Confirmed absent | **PASS** |

### `secciones-ficha` branch (lines 1760–1858, 2102–2146)

| Check | Expected | Found | Status |
|---|---|---|---|
| Metadata: no `Orden` entry | Absent | Lines 1794-1803: only `Código`, `Sector`, `Procedimiento estético` | **PASS** |
| Values: no `order` key | Absent | Lines 1805-1810: `name`, `code`, `sectorId`, `procEsteticoId` only | **PASS** |
| Fields: no `order` entry | Absent | Lines 1829-1856: no `order` field | **PASS** |
| Create: read `order` but discard | `_ = int_value("order", ...)` | Line 2110 | **PASS** |
| Create: assign `max+1` | `obj.orden = max_orden + 1` inside `if instance is None` | Lines 2143-2145 | **PASS** |
| Update: do NOT touch `obj.orden` | No assignment in else/update branch | Confirmed absent | **PASS** |

### `sectores` branch (lines 1702–1758, 2081–2100)

| Check | Expected | Found | Status |
|---|---|---|---|
| Metadata: no `Orden` entry | Absent | Lines 1720-1727: only `Código`, `Descripción`, `Servicios vinculados` | **PASS** |
| Values: no `order` key | Absent | Lines 1728-1732: `code`, `name`, `description` only | **PASS** |
| Fields: no `order` entry | Absent (already had none) | Lines 1752-1757: `code`, `name`, `description` only | **PASS** |
| Create: assign `max+1` | Already correct at lines 2094-2099 | `max_orden = Sector.objects.aggregate(Max("orden"))["orden__max"] or 0; obj.orden = max_orden + 1` | **PASS** |
| Update: do NOT touch `obj.orden` | Already correct | No assignment in update branch | **PASS** |

### `Max` import usage

| Usage | Line | Status |
|---|---|---|
| `from django.db.models import Max` | Line 11 | Present |
| `Especialidad.objects.aggregate(Max("orden"))` | 2051 | Used |
| `FichaCampo.objects.aggregate(Max("orden"))` | 2022 | Used |
| `FichaSeccion.objects.aggregate(Max("orden"))` | 2144 | Used |
| `Sector.objects.aggregate(Max("orden"))` | 2098 | Used |
| `ProcEsteticosTipo.objects.aggregate(Max('orden'))` | 1965 | Used (tipos-procedimiento, unchanged) |

`Max` is not orphaned — all existing usages remain active.

### `tipos-procedimiento` out-of-scope observation

The `tipos-procedimiento` branch (line 1324) still contains `"order": item.orden,` in its per-item `values` dict (line 1350). This was correctly identified as out-of-scope in the design doc (Section "Out of Scope"): this change only covers `especialidades`, `campos-ficha`, `secciones-ficha`, `sectores`. `tipos-procedimiento` is untouched. No action required.

---

## 3. Test Review

### `test_secciones_ficha_crud.py`

| Test | New contract asserted | Status |
|---|---|---|
| `test_create_section_with_sector_only_returns_201` (line 231) | `orden == baseline_max + 1`; payload no longer has `order` | **PASS** |
| `test_create_section_with_proc_only_returns_201` (line 259) | `orden == baseline_max + 1` | **PASS** |
| `test_create_section_with_both_bindings_returns_201` (line 283) | `orden == baseline_max + 1` | **PASS** |
| `test_update_section_persists_changes` (line 420) | Sends `order: 9`; asserts `orden == 1` (preserved) | **PASS** |
| `test_update_with_order_9_preserves_orden` (line 447) | Explicit scenario: `orden == 3` after `order: 9` in payload | **PASS** |

No test asserts the old contract (`orden == payload order`). Old assertions like `orden == 1` for a created item are gone. `Max` imported at line 17.

### `test_admin_catalog_sectores.py`

| Test | Contract | Status |
|---|---|---|
| `test_list_returns_baseline_seed_sectores` (line 91) | `assertNotIn("order", sample["values"])` + `assertNotIn("Orden", [m.label])` | **PASS** |
| `test_create_sector_persists_and_returns_201` (line 193) | `orden == baseline_max + 1` (ignores payload `order: 5`) | **PASS** |
| `test_update_sector_persists_changes` (line 297) | `orden` preserved when `order: 9` sent | **PASS** |
| `test_create_sector_auto_assigns_orden_plus_one` (line 355) | Without `order` in payload: `orden == baseline_max + 1` | **PASS** |
| `test_update_sector_does_not_change_orden` (line 373) | orden unchanged after update | **PASS** |

### `test_admin_catalog_especialidades_orden.py`

| Test | Axis | Status |
|---|---|---|
| `test_list_response_has_no_order_in_metadata` (line 68) | Hidden in metadata | **PASS** |
| `test_list_response_has_no_order_in_values` (line 83) | Hidden in values | **PASS** |
| `test_form_fields_has_no_order_entry` (line 97) | Hidden in fields | **PASS** |
| `test_create_auto_assigns_max_plus_1` (line 114) | Auto-assign axis | **PASS** |
| `test_create_ignores_explicit_order` (line 133) | Ignore-on-payload axis | **PASS** |
| `test_update_preserves_orden` (line 200) | Preserve-on-update axis | **PASS** |
| `test_create_asigna_orden_max_mas_uno` (line 155) | Spanish alias — auto-assign | **PASS** |
| `test_create_ignora_order_del_payload` (line 176) | Spanish alias — ignore-on-payload | **PASS** |

All 3 axes (auto-assign, ignore-on-payload, preserve-on-update) are covered by at least 2 tests each. No test asserts the old contract.

### `test_campos_ficha_validation.py`

File was reviewed (not modified per tasks). Contains no assertions about `orden` or `order`. Correctly scoped to `grupo_opciones` validation only. No changes needed.

---

## 4. Test Execution

```
python3 manage.py test tests.test_admin_catalog_sectores tests.test_secciones_ficha_crud tests.test_campos_ficha_validation tests.test_admin_catalog_especialidades_orden -v 2
```

**Result: 56 tests, 26.197s — ALL PASS**

No failures, no errors. System check: no issues.

---

## 5. Frontend Impact Check

`frontend/aesthetic-clinic/src/pages/admin/AdminCatalogsPage.tsx`

| Check | Location | Result |
|---|---|---|
| Form renders from `data.fields` only | Line 553: `fields={data.fields}` | **PASS** — no hardcoded field list |
| Card metadata renders from `item.metadata` only | Lines 604-611: `{item.metadata.map(...)` | **PASS** — dynamic iteration |
| Pre-fill form state from `editingItem.values` | Line 312: `buildFormState(fields, editingItem?.values)` | **PASS** — dynamic |
| No hardcoded `orden` reference anywhere | Full file grep | **PASS** — zero occurrences |
| `tipos-procedimiento` still renders (unchanged) | Line 658: `AdminProcedureTypesCatalogPage` | Correctly untouched |

The frontend is fully passive — it renders exactly what the API returns. Removing `orden` from the API response naturally hides it everywhere with zero frontend changes.

---

## 6. Out-of-Scope Guard

`tipos-procedimiento` still exposes `"order": item.orden` in its `values` dict (line 1350 of `api_views.py`) and has no `Orden` in metadata. This is **correctly out-of-scope**: the design doc explicitly lists the 4 catalogs that are in scope, and `tipos-procedimiento` was not among them. No scope leak detected.

---

## Verification Checklist Summary

| Area | Result |
|---|---|
| Spec → Implementation match | **PASS** — all 9 scenarios across both spec files verified |
| Code review — 4 catalog branches | **PASS** — all 24 individual checks pass |
| `Max` import usage | **PASS** — all 5 usages active, no orphan |
| `tipos-procedimiento` out-of-scope | **PASS** — confirmed untouched |
| Test review — `test_secciones_ficha_crud.py` | **PASS** — new contract fully asserted |
| Test review — `test_admin_catalog_sectores.py` | **PASS** — baseline contract confirmed |
| Test review — `test_admin_catalog_especialidades_orden.py` | **PASS** — 3 axes covered, 8 tests |
| Test execution | **PASS** — 56/56 green |
| Frontend impact | **PASS** — zero hardcoded `orden`, fully passive |
| Out-of-scope guard | **PASS** — no scope leak |

---

## Risks

None. All checks pass.

---

## Recommendation

**Ready for archive.** The implementation is complete, correct, and fully tested. Proceed to `sdd-archive` phase to move the delta specs into the canonical spec directory.
