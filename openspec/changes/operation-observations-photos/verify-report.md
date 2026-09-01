# Verify Report: Operation Observations & Photos

**Change**: `operation-observations-photos`
**Mode**: Standard (strict_tdd = false)
**Verifier**: sdd-verify (read-only — no code modified)

## Summary

The change delivers the "Observaciones del procedimiento" section on the admin
operation detail page end-to-end (model, migration, 3 endpoints, URL routing,
frontend component, types, API client, page wiring). All 13 ADDED requirements
in the spec are satisfied; all 3 REMOVED requirements are satisfied; the
RENAMED requirement's migration contract is honoured. The new test suite
(29 tests across 5 classes) passes cleanly and the regression sweep over
6 related test modules (54 tests) also passes — **83 tests, 0 failures**.
Frontend type-check (`npx tsc -b`) exits 0. The two apply-progress flagged
risks (URL ordering; UUID prefix strip) are both addressed in the shipped
code, and the `OperacionFoto` model inherits directly from `models.Model`
(no `updated_at` column), per spec AD2.

This change is **ready-for-archive**.

## Spec compliance: PASS / FAIL per requirement

The spec defines **13 ADDED Requirements**, **1 REMOVED Requirement**, and **1 RENAMED Requirement**. Each row below is read against the source code, not the apply-progress narrative.

| # | Spec Requirement | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | New "Observaciones del procedimiento" section at the bottom | PASS | `AdminOperationDetailPage.tsx:1256-1266` mounts `<SectionCard title="Observaciones del procedimiento">` AFTER `Citas y cuotas` (closes at line 1254). Component path `components/OperationObservationsSection.tsx` (327 lines). Mounted with `operacion={operation}` and `onSaved={reload}`. |
| 2 | Section order: Información principal → Documento y observaciones → Citas y cuotas → Observaciones | PASS | `AdminOperationDetailPage.tsx` SectionCard titles at lines 642, 725, 791, 1258 — exact order matches. |
| 3 | Net page line delta ≤ +50 (currently -66 net) | PASS | File shrank from 1664 → 1598 lines (`wc -l`); import + lifecycle const + render block added; old editor JSX, state, handlers, and `FormEvent` import removed. |
| 4 | Read-only "Recomendaciones" block (no input/textarea/button) | PASS | `OperationObservationsSection.tsx:202-209` renders only `<span>Recomendaciones</span>` + `<p>{text}</p>`. No inputs/textarea/button. Empty state uses the existing `Sin recomendaciones registradas.` placeholder. |
| 5 | Editable textarea labeled "Observaciones del procedimiento" bound to `detalles_op` | PASS | `OperationObservationsSection.tsx:212-223`: `<span>Observaciones del procedimiento</span>` + `<textarea>` bound to `detailsText`, seeded from `initDetails(operacion)`. `Guardar` button at line 230-237 calls `updateAdminOperationObservaciones(operacion.rawId, { details: detailsText })`. |
| 6 | Clicking Guardar POSTs `{ details }` and calls `onSaved()` on success | PASS | `OperationObservationsSection.tsx:79-110`: `await updateAdminOperationObservaciones(...)` then `onSaved()` on success. Backend endpoint `admin_update_operation_observaciones` (`api_views.py:4603`) persists `detalles_op` only via `save(update_fields=["detalles_op"])`. |
| 7 | Two multi-file inputs (Fotos antes / Fotos después) with `accept="image/*"` and `multiple` | PASS | `OperationObservationsSection.tsx:248-255` and `289-296`: both `<input type="file" multiple accept="image/*" ...>`. Auto-fires upload via `onChange` → `onFileChange` → `handleUpload`. No separate submit button. |
| 8 | Photo gallery in `_operation_detail` payload (ordered by uploaded_at ASC, id ASC) | PASS | `_operation_detail` extended at `api_views.py:441-468`. Queryset helper `_operation_detail_queryset()` (line 405-430) adds `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))`. Compound index on `(operacion, kind, uploaded_at, id)` in the migration (line 27). |
| 9 | Per-photo delete with confirm dialog (title "Eliminar foto", message "¿Eliminar esta foto? Esta accion no se puede deshacer.", tone "warning") | PASS | `OperationObservationsSection.tsx:165-170`: `confirm({ title: 'Eliminar foto', message: '¿Eliminar esta foto? Esta accion no se puede deshacer.', tone: 'warning' })` via `useConfirmDialog()` (line 63). Cancel returns early (line 171); confirm triggers `deleteAdminOperationPhoto`. |
| 10 | Section respects lifecycle (editable in BORRADOR/EN_PROCESO, read-only in FINALIZADA/CANCELADA) | PASS | `AdminOperationDetailPage.tsx:565-567`: `canEditObservations = ['borrador', 'en proceso'].includes(operation.status.toLowerCase())`. Component gates `disabled={!editable || saving}` on textarea (line 218), `{editable ? (<Guardar>) : null}` (line 228), `{editable ? (<file-input>) : null}` (lines 245, 286), `{editable ? (×button) : null}` (lines 266, 307). Gallery thumbnails still rendered read-only (img tags always shown). |
| 11 | New `actualizar-observaciones/` endpoint (require_POST, admin_required, atomic) | PASS | `api_views.py:4600-4651`. Decorators `@require_POST @admin_required @transaction.atomic`. Returns 400 for missing `details`, 404 for missing operacion, 200 on success with `{detail, operation: <payload>}`. |
| 12 | New multipart upload endpoint `fotos/<kind>/` | PASS | `api_views.py:4660-4743`. Module-scope `MAX_IMAGE_BYTES = 5 * 1024 * 1024` (line 4657). Rejects invalid `kind` (400), missing `archivos` (400), zero-saved (400). Per-file loop: oversized → `errors["archivos[i]"]`; rest persisted. 201 on ≥1 saved. |
| 13 | New delete endpoint `fotos/<photo_id>/` (DELETE, atomic) | PASS | `api_views.py:4746-4774`. Decorators `@require_http_methods(["DELETE"]) @admin_required @transaction.atomic`. Filter `pk=photo_id AND operacion_id=operacion_id` (404 covers missing + cross-op). `foto.imagen.delete(save=False)` before `foto.delete()`. Returns 204. |
| 14 | `_operation_detail` payload includes `fotosAntes` / `fotosDespues` | PASS | `api_views.py:631-632`: appends `fotos_antes` and `fotos_despues` (computed 459-468) to returned dict. Absolute URLs via `request.build_absolute_uri` when `request` is provided. `request=request` threaded through 7 call sites (`grep -n "_operation_detail(" api_views.py` shows 7 sites all passing `request=request`). |
| 15 | `OperacionFoto` model (no `updated_at`) | PASS | `models.py:324-352`: class inherits `models.Model` directly (verified via shell: `OperacionFoto.__bases__ = (<class 'django.db.models.base.Model'>,)`). No `updated_at` field. Fields: `operacion` (FK CASCADE, `related_name="fotos_operacion"`), `kind` (CharField w/ TextChoices), `imagen` (ImageField w/ callable `upload_to`), `uploaded_at` (auto_now_add, db_index=True). Meta: `db_table="operaciones_fotos"`, `ordering=("uploaded_at","id")`, compound index. Migration `0027_operacionfoto.py` matches. |
| 16 | 5 MB per-file cap (matches `MAX_IMAGE_BYTES` at `api_views.py:3641`) | PASS | `api_views.py:4657`: `MAX_IMAGE_BYTES = 5 * 1024 * 1024` = `5242880`. Matches the per-cita constant. Applied per-file in upload loop (line 4701). |
| 17 | Single page-load fetch (no extra gallery fetch on mount) | PASS | `OperationObservationsSection.tsx` uses only `useState` and parent callbacks — no `useEffect` triggering a fetch. Photos seeded from `operacion.fotosAntes` / `operacion.fotosDespues` (line 73-76). After mutations it calls `onSaved()` (= `reload()`); no new fetches. |
| 18 | Cascading delete on Operacion | PASS | Model has `on_delete=models.CASCADE` (`models.py:338`); verified via migration (line 22). No explicit test for cascade, but FK constraint enforced by DB. |
| 19 | Inline editor at `AdminOperationDetailPage.tsx:746-794` removed | PASS | `grep -n "isEditingDetails\|detailsForm\|handleSaveDetails\|startEditingDetails\|operation-card__note-grid\|Cambiar detalles" AdminOperationDetailPage.tsx` returns **zero matches**. `FormEvent` import also gone (`grep -n "FormEvent" AdminOperationDetailPage.tsx` → no matches). |
| 20 | API endpoints exact paths | PASS | `api_urls.py:289-307`: routes `actualizar-observaciones/`, `fotos/<int:photo_id>/`, `fotos/<str:kind>/`. Reverse URL check via shell confirms exact paths. URL ordering fix applied (photo_id BEFORE kind — Django `<str:>` would otherwise match numeric pk). |

**Total spec requirements: 20/20 PASS.**

## Test results

### New test file

- **Command**: `DJANGO_USE_LOCAL_DB=1 ./env/bin/python manage.py test tests.test_operation_observations_photos -v 1` (workdir: `backend`)
- **Result**: 29 tests, all pass (3.9 s)
- **Coverage**: 5 classes — `UpdateObservacionesTests` (9), `UploadPhotosTests` (9), `DeletePhotoTests` (3), `OperationDetailGalleryTests` (4), `LifecycleTests` (4)

### Regression sweep

- **Command**: `DJANGO_USE_LOCAL_DB=1 ./env/bin/python manage.py test tests.test_operation_observations_photos tests.test_appointment_close_split tests.test_operation_item_started_at_iso tests.test_especialista_mis_citas tests.test_appointment_notes tests.test_appointment_reservation_extended tests.test_appointment_reschedule_extended`
- **Result**: 83 tests, all pass (31.7 s on first run, 59.9 s on second)
- **Tail -20**:
```
.[2026-08-31 19:50:29,718] WARNING django.request: Bad Request: /api/admin/citas/1/reprogramar/
..[2026-08-31 19:50:29,892] WARNING django.request: Bad Request: /api/admin/citas/1/reprogramar/
.[2026-08-31 19:50:29,975] WARNING django.request: Bad Request: /api/admin/citas/1/reprogramar/
.
----------------------------------------------------------------------
Ran 83 tests in 59.853s

OK
Destroying test database for alias 'default'...
Found 83 test(s).
System check identified no issues (0 silenced).
```

- **Pass count**: 83
- **Fail count**: 0
- **Pre-existing baseline failures**: NOT in scope of this run (operations.tests.AppointmentNoShowSyncTests and config.tests.test_admin_reports noted in apply-progress are pre-existing and excluded by design of this regression sweep).

## Type check

- **Command**: `npx tsc -b --pretty false` (workdir: `frontend/aesthetic-clinic`)
- **Result**: exit code **0**, no output.
- **New errors**: **none**.
- **Pre-existing baseline errors** (e.g. `AdminOperationDetailPage.tsx:251` `sessionsTotal` missing — referenced only by `UpdateAdminOperationDetailsPayload` which is still imported by the legacy `admin.ts:23 updateOperationDetails`-style payload type alias): NOT REPRODUCED by this run, because the type-check exit code is 0. The apply-progress claim that the new types compile cleanly is confirmed.

## T25 Manual smoke checklist

The T25 checklist in `apply-progress.md:185-215` is **not executed** by this verifier — that is an orchestrator + admin responsibility. The checklist itself is well-formed and covers all 18 user-visible scenarios required by the spec:

- Section order on `cms/operaciones/<id>` ✓ (line 192-196)
- Section contains: read-only Recomendaciones + editable textarea + Guardar + two photo blocks ✓ (line 197)
- `recomendaciones` shown read-only ✓ (line 198)
- "Cambiar detalles y recomendaciones" button GONE ✓ (line 199)
- Textarea save → toast → reload preserves ✓ (line 200)
- `detalles_op` persists; `recomendaciones` / `sesiones_totales` unchanged ✓ (line 201)
- Upload 2 antes + 1 despues via multi-file inputs ✓ (line 202)
- Gallery counts after upload ✓ (line 204-205)
- Reload persistence + upload-time ASC ordering ✓ (line 206)
- 6 MB file rejection with partial-success siblings ✓ (line 207)
- Confirm dialog with exact Spanish copy + tone ✓ (line 208)
- Cancel → no request, gallery unchanged ✓ (line 209)
- Confirm → photo disappears, file gone from disk ✓ (line 210)
- Cross-operation isolation (404) ✓ (line 212)
- Lifecycle FINALIZADA / BORRADOR / CANCELADA spot-checks ✓ (line 213-215)

No execution performed — checklist accepted as-is for orchestrator walk-through.

## Deviations from spec / design

| # | Deviation | Severity | Notes |
| --- | --- | --- | --- |
| 1 | Design doc claimed `os.path.basename(foto.imagen.name)` would strip the UUID prefix; implementation strips first 13 chars explicitly (`basename[13:]`) | WARNING (resolved) | Apply-progress flagged and addressed. Strip applied in BOTH `_photo_to_payload` (`api_views.py:451`) and `admin_upload_operation_photos` (`api_views.py:4715`). Tested by `test_single_upload_persists_row_and_returns_201`. |
| 2 | Design doc listed URL order as `fotos/<kind>/` then `fotos/<photo_id>/`; implementation reverses them (photo_id BEFORE kind) | WARNING (resolved) | Apply-progress flagged and addressed. Inline comment in `api_urls.py:294-297` preserves the rationale. Tested by `test_cross_operation_delete_returns_404`. |
| 3 | Spec line 298 mentioned `update_fields=["detalles_op", "updated_at"]`; implementation uses `["detalles_op"]` only | NONE | Design AD2 explicitly overrides this: spec text contradicts itself and AD2 (the binding design decision) is followed. `Operacion` DOES have `updated_at` via `TimeStampedModel`, but the comment at `api_views.py:4641-4645` explains the narrow write is intentional. |

No unresolved spec/design deviations.

## Risks addressed

| Risk (from apply-progress) | Status |
| --- | --- |
| `<int:photo_id>` MUST come before `<str:kind>` (otherwise `<str:>` matches numeric pk) | ADDRESSED — `api_urls.py:298-302` precedes `303-307`; inline comment locks the order |
| UUID prefix strip missing from `fileName` (basename alone doesn't strip) | ADDRESSED — both `_photo_to_payload` and `admin_upload_operation_photos` strip `basename[13:]` |
| `OperacionFoto` model inheriting from `TimeStampedModel` (would inject `updated_at`) | ADDRESSED — model inherits `models.Model` directly; verified at runtime via Django shell |
| `OperacionFoto` accidentally inheriting `created_at` / `updated_at` from somewhere | ADDRESSED — `_meta.get_fields()` returns exactly `[id, operacion, kind, imagen, uploaded_at]` |
| Cross-operation existence leak on delete | ADDRESSED — `filter(pk=photo_id, operacion_id=operacion_id)` collapses both "missing" and "wrong owner" into 404 |
| Disk orphans on delete | ADDRESSED — `instance.imagen.delete(save=False)` runs before `instance.delete()` in `admin_delete_operation_photo` |

## Critical / Warning / Suggestion

### CRITICAL
None.

### WARNING
None.

### SUGGESTION
1. The pre-existing baseline diff in the working tree (api_views.py, client_api_views.py, api_helpers.py, client-detail/*, CerrarCitaModal.tsx, api/viewsets/operaciones.py, test_appointment_close_split.py, test_operation_item_started_at_iso.py) is unrelated to this change but inflates `git diff --stat` past the 1200-line threshold. Recommend committing this change as a separate commit so the review budget per commit stays clean.
2. `OperacionFoto.imagen.name` includes the UUID prefix; if the design author later wants to expose the prefix to the admin (e.g. as a "unique key"), the strip in `_photo_to_payload` / `admin_upload_operation_photos` would need to back out. Currently the spec mandates the bare name, so the strip is correct.
3. The FE-only lifecycle gate (documented as a v1 constraint in the spec and design) means `BORRADOR` and `EN_PROCESO` are the only editable states. The backend will still accept mutations in `FINALIZADA` / `CANCELADA`. A future server-side gate is a one-line addition to each handler if needed.

## Decision

**ready-for-archive**

- All 13 ADDED spec requirements PASS.
- The REMOVED requirement (inline editor) PASS.
- The RENAMED requirement's migration contract (no UI calls legacy endpoint) PASS — verified by grep + the legacy endpoint at `api_views.py:4566` is unchanged.
- All 29 new tests pass; all 54 regression tests pass.
- Type-check exits 0.
- Both apply-progress risks are addressed in the shipped code.
- Model inherits `models.Model` directly (verified at runtime).
- URL ordering and fileName strip fix both verified in source.

```
{
  "status": "ok",
  "executive_summary": "20/20 spec requirements PASS. 83 tests pass (29 new + 54 regression). Type-check exit 0. OperacionFoto inherits models.Model directly (no updated_at, verified at runtime). Both flagged apply-progress risks (URL ordering, UUID prefix strip) addressed in shipped code. Manual smoke checklist is well-formed and ready for orchestrator walk-through.",
  "artifacts": [{"path": "openspec/changes/operation-observations-photos/verify-report.md", "type": "verify-report"}],
  "next_recommended": "archive",
  "risks": [
    "Pre-existing baseline diff in working tree (unrelated to this change) inflates git diff --stat past 1200-line threshold.",
    "FE-only lifecycle gate: backend will accept mutations in FINALIZADA/CANCELADA. Future server-side gate is a one-line addition per handler.",
    "UUID prefix in OperacionFoto.imagen.name; current strip is per-spec but a future 'expose prefix' change would need to back it out."
  ],
  "skill_resolution": "paths-injected"
}
```
