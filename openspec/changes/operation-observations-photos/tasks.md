# Tasks: Operation Observations & Photos

## Line-delta forecast

| File | Estimated delta |
| --- | --- |
| `backend/operations/models.py` | +40 (model + callable + `import uuid`) |
| `backend/operations/migrations/0027_operacionfoto.py` | +25 (new, auto-generated) |
| `backend/operations/admin.py` | +10 (import + `OperacionFotoAdmin`) |
| `backend/config/api_views.py` | +160 (3 handlers + `_operation_detail` extension + `_operation_detail_queryset` helper + `request` threading at 8 sites) |
| `backend/config/api_urls.py` | +18 (3 new path entries) |
| `backend/operations/tests.py` (or new `tests/test_operation_observations_photos.py`) | +450 (new file, ~22 tests) |
| `frontend/aesthetic-clinic/src/types/admin.ts` | +20 (3 types + 2 fields on existing type) |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | +35 (3 new functions) |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | −60 / +20 → net **−40 lines** (state/handlers/JSX removed, lifecycle const + import + render block added) |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | +280 (new file) |
| **Total** | **~+960 lines across 10 files, with one file shrinking by 40** |

**Total > 400 lines → `## size:exception needed` section is required (see end of file).**

- Decision needed before apply: **Yes**
- Chained PRs recommended: **Yes**
- Chain strategy: **pending** (single-pr delivery was requested, but the 400-line gate is exceeded by the new-test file alone — orchestrator must escalate to user)
- 400-line budget risk: **High**

### Suggested work units (for orchestrator to consider if chain strategy is approved)

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
| --- | --- | --- | --- | --- | --- |
| 1 | Backend data layer + admin endpoints + URL routes (no tests yet) | PR 1 | `python manage.py check` + manual `python manage.py makemigrations --check --dry-run` | Dev server smoke: upload one photo, delete one photo, save text | Revert model + migration + admin.py + api_views.py + api_urls.py. New model is additive (Django rolls back); endpoints are additive routes. |
| 2 | Backend tests | PR 2 | `python manage.py test operations.tests.test_operation_observations_photos -v 2` | Same dev server; tests cover disk cleanup + 5 MB cap + cross-operation 404 | Revert new test file only. No production code change. |
| 3 | Frontend types + API client + new component + page wiring | PR 3 | `npx tsc -b --noEmit` in `frontend/aesthetic-clinic` | Dev server smoke: open `cms/operaciones/<id>`, edit textarea, upload 2 antes + 1 despues, delete one, reload to confirm persistence | Revert new component + the page edits (state/handlers/JSX/imports). Page-level rollback restores the inline editor. |

If the user rejects chained PRs and demands a single PR with `size:exception`, the orchestrator should request it explicitly before launching `sdd-apply`.

---

## Phase 1 — Backend data layer

- [x] **T1** Add `OperacionFoto` model + `_operacion_foto_upload_to` callable to `backend/operations/models.py` (insert after `CitaMedica`, before `class PlantillaProcedimiento`).
  - Inherit from `models.Model` **directly** (NOT `TimeStampedModel`) — the spec forbids `updated_at`.
  - Fields per spec lines 244-249: `operacion` (FK CASCADE, `related_name="fotos_operacion"`), `kind` (CharField with `Kind.TextChoices`), `imagen` (`ImageField(upload_to=_operacion_foto_upload_to)`), `uploaded_at` (`DateTimeField(auto_now_add=True, db_index=True)`).
  - Meta: `db_table = "operaciones_fotos"`, `ordering = ("uploaded_at", "id")`, `indexes = [Index(fields=["operacion", "kind", "uploaded_at", "id"])]`.
  - Callable returns `f"operaciones/{now:%Y/%m/%d}/{instance.kind}/{uuid4-prefix}-{filename}"`.
  - Files: `backend/operations/models.py` (~+40 lines).
  - Depends on: none.

- [x] **T2** Generate and apply the migration.
  - Run `python manage.py makemigrations operations` (expect filename `0027_operacionfoto.py`).
  - Run `python manage.py migrate operations`.
  - Verify the auto-generated `upload_to` references `operations.models._operacion_foto_upload_to`.
  - Files: `backend/operations/migrations/0027_operacionfoto.py` (~+25 lines, new file).
  - Depends on: T1.

- [x] **T3** Register `OperacionFoto` in the Django admin (only if `backend/operations/admin.py` currently auto-registers concrete models; otherwise skip silently).
  - Add `@admin.register(OperacionFoto)` class with `list_display = ("id", "operacion", "kind", "uploaded_at")`, `list_filter = ("kind",)`, `search_fields = ("operacion__paciente__usuario__primer_nombre",)`.
  - Files: `backend/operations/admin.py` (~+10 lines).
  - Done when: `OperacionFoto` appears under "Operations" in `/admin/` (or the registration is silently skipped after confirming the existing pattern).
  - Depends on: T1.

---

## Phase 2 — Backend endpoints

- [x] **T4** Implement `admin_update_operation_observaciones` in `backend/config/api_views.py`.
  - Decorators: `@require_POST`, `@admin_required`, `@transaction.atomic`.
  - Validate JSON body via `load_payload(request)`; reject non-JSON with 400.
  - Reject missing `details` with 400 + `errors.details`.
  - Fetch `Operacion` with `select_for_update(of=("self",))`; 404 if missing.
  - Persist `operacion.detalles_op = (payload["details"] or "").strip()` with `save(update_fields=["detalles_op"])` (NOT `["detalles_op", "updated_at"]` — model has no `updated_at`).
  - Re-fetch via `_operation_detail_queryset()` and return `{detail, operation: _operation_detail(operacion, request=request)}`.
  - Files: `backend/config/api_views.py` (~+50 lines).
  - Done when: happy path persists `detalles_op` only (no clobber of `recomendaciones` / `sesiones_totales`), missing `details` → 400, missing operacion → 404.
  - Depends on: T1, T2.

- [x] **T5** Implement `admin_upload_operation_photos` in `backend/config/api_views.py`.
  - Decorators: `@require_POST`, `@admin_required`, `@transaction.atomic`.
  - Module-scope constant `MAX_IMAGE_BYTES = 5 * 1024 * 1024` (must equal the per-cita constant at `api_views.py:3641`).
  - Reject invalid `kind` (not in `{"antes", "despues"}`) with 400 + `errors.kind`.
  - 404 if operacion missing.
  - Read `request.FILES.getlist("archivos")`; 400 if empty.
  - Per-file loop: skip files with `upload.size > MAX_IMAGE_BYTES` (record `errors["archivos[i]"]`); create `OperacionFoto` rows for the rest, append `{id, url, uploadedAt, fileName}` to `saved_payload` (URL via `request.build_absolute_uri`).
  - 400 when zero files saved; 201 when ≥ 1 saved (partial success tolerated).
  - Re-fetch operacion via `_operation_detail_queryset()` and return `{detail, saved, errors, operation: _operation_detail(operacion, request=request)}`.
  - Files: `backend/config/api_views.py` (~+70 lines).
  - Depends on: T1, T2.

- [x] **T6** Implement `admin_delete_operation_photo` in `backend/config/api_views.py`.
  - Decorators: `@require_http_methods(["DELETE"])`, `@admin_required`, `@transaction.atomic`.
  - Query `OperacionFoto.objects.select_related("operacion").filter(pk=photo_id, operacion_id=operacion_id).first()`; 404 if missing (covers both "no row" and "belongs to different operation" — no cross-op existence leak).
  - Call `foto.imagen.delete(save=False)` BEFORE `foto.delete()` (endpoint owns the side effect, not a signal).
  - Return 204 with empty body.
  - Files: `backend/config/api_views.py` (~+25 lines).
  - Depends on: T1, T2.

- [x] **T7** Wire the three new endpoints in `backend/config/api_urls.py`.
  - Add 3 `path(...)` entries immediately after the existing `actualizar-detalles/` route:
    - `operaciones/<int:operacion_id>/actualizar-observaciones/` → `admin_update_operation_observaciones`, name `admin-operation-update-observaciones-api`.
    - `operaciones/<int:operacion_id>/fotos/<str:kind>/` → `admin_upload_operation_photos`, name `admin-operation-upload-photos-api`.
    - `operaciones/<int:operacion_id>/fotos/<int:photo_id>/` → `admin_delete_operation_photo`, name `admin-operation-delete-photo-api`.
  - Add the 3 handlers to the `from config.api_views import (...)` block.
  - Files: `backend/config/api_urls.py` (~+18 lines).
  - Done when: `python manage.py show_urls | grep operation` lists the 3 new routes.
  - Depends on: T4, T5, T6.

- [x] **T8** Extend `_operation_detail` payload with `fotosAntes` / `fotosDespues`.
  - Change the function signature at `api_views.py:403` to `def _operation_detail(operacion, request=None):`.
  - Append a `_photo_to_payload(foto)` helper that returns `{id, url, uploadedAt, fileName}`. `url` is `request.build_absolute_uri(foto.imagen.url)` when `request` is set, else `foto.imagen.url`.
  - Build `fotos_antes = [_photo_to_payload(f) for f in operacion.fotos_operacion.all() if f.kind == "antes"]` (ordered by `uploaded_at ASC, id ASC` via the queryset helper).
  - Same for `fotos_despues`.
  - Append `fotosAntes` and `fotosDespues` to the returned dict literal at the end (existing keys unchanged).
  - Files: `backend/config/api_views.py` (~+25 lines).
  - Depends on: T1.

- [x] **T9** Add the `_operation_detail_queryset()` helper and use it in both admin_operacion detail sites.
  - Helper goes immediately above `admin_operacion_detalle` (around `api_views.py:4494`).
  - Includes all existing `select_related(...)` + `prefetch_related(... citas_medicas ..., cuotas_plan_pagos ...)` PLUS the new `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))`.
  - Replace the two inline queryset literals at `api_views.py:4494-4510` and `api_views.py:4554-4569` with `_operation_detail_queryset()`.
  - Files: `backend/config/api_views.py` (~+25 lines, with the existing inline literals collapsing).
  - Depends on: T8.

- [x] **T10** Thread `request=request` through all `_operation_detail` call sites.
  - The design lists 8 sites (verifiable via grep `grep -n "_operation_detail(" backend/config/api_views.py`):
    1. `api_views.py:403` (definition itself — not a call site, ignore).
    2. `api_views.py:3859`, `:4062`, `:4323` (cita-side handlers — pass `request=request`).
    3. `api_views.py:4494-4518` (within `admin_operacion_detalle` — pass `request=request` when calling `_operation_detail` at `:4518`).
    4. `api_views.py:4554-4573` (within `admin_update_operation_details` — pass `request=request` at `:4573`).
    5. `api_views.py:4954`, `:5089` (admin operation-listing endpoints — verify they render `operation` for an admin and pass `request=request`; if not, skip).
  - Grep verification step is MANDATORY: the orchestrator should record the actual line numbers found before applying.
  - Files: `backend/config/api_views.py` (~+5 net lines, no new code, only kwarg additions).
  - Done when: `grep -n "_operation_detail(" api_views.py` shows `request=request` at every call site that returns an admin-visible operation.
  - Depends on: T8, T9.

---

## Phase 3 — Backend tests

- [x] **T11** Tests for the PATCH-style endpoint `actualizar-observaciones/`.
  - Add a new `UpdateObservacionesTests` class with tests for: happy path persists `detalles_op` only (assert `recomendaciones` and `sesiones_totales` unchanged); missing `details` → 400; invalid JSON → 400; missing operacion → 404; anonymous → 401; non-admin (cliente) → 403; does not clobber `recomendaciones`; does not clobber `sesiones_totales`; `details` is whitespace-stripped (`"  nuevo  "` → `"nuevo"`).
  - Mirror the house style of `backend/tests/test_appointment_close_split.py`: `TestCase` + `setUpTestData` fixtures + `self.client.force_login(self.admin)` + `self.client.post(url, data=..., content_type="application/json")`.
  - Files: new file `backend/tests/test_operation_observations_photos.py` (~+120 lines) — confirm house style by checking `ls backend/tests/` first.
  - Depends on: T4, T7.

- [x] **T12** Tests for the multipart upload endpoint `fotos/<kind>/`.
  - Add a `UploadPhotosTests` class covering: single valid upload persists row + returns 201 with absolute URL starting with `http`; multi-upload (3 files) persists all 3; partial success (3 files, one > 5 MB → 201 with `saved.length == 2`, `errors["archivos[i]"]` set, no row for the oversized file); all 3 oversized → 400; missing `archivos` → 400; invalid `kind` → 400; `kind=despues` stores separately from `antes`; detail payload after upload embeds the new photo with absolute URL; missing operacion → 404.
  - Use `SimpleUploadedFile` (see `test_appointment_close_split.py:374-385`) for tiny PNG fixtures.
  - Files: `backend/tests/test_operation_observations_photos.py` (~+180 lines, cumulative with T11).
  - Depends on: T5, T7.

- [x] **T13** Tests for the delete endpoint.
  - Add a `DeletePhotoTests` class covering: existing photo → 204 + `os.path.exists(imagen_path) == False` (disk cleanup verified) + `OperacionFoto.objects.count() == 0`; cross-operation delete → 404 + photo still exists (no cross-op existence leak); missing photo id → 404.
  - Capture `foto.imagen.path` BEFORE the DELETE so the test can assert the file is gone afterwards.
  - Files: `backend/tests/test_operation_observations_photos.py` (~+60 lines, cumulative).
  - Depends on: T6, T7.

- [x] **T14** Tests for `_operation_detail` gallery embedding.
  - Add `OperationDetailGalleryTests` covering: detail payload includes `fotos_antes` ordered by `uploaded_at ASC`; same for `fotos_despues`; empty gallery returns `[]`; `assertNumQueries` stays at the existing baseline (no N+1 from the new prefetch).
  - Also add a `LifecycleTests` class covering: `BORRADOR` and `EN_PROCESO` accept mutations; `FINALIZADA` and `CANCELADA` ALSO accept mutations server-side (FE-only lifecycle gating per spec line 124 — docstring must state this).
  - Files: `backend/tests/test_operation_observations_photos.py` (~+90 lines, cumulative; total file ≈+450 lines).
  - Depends on: T8, T9, T10.

---

## Phase 4 — Frontend types and API client

- [x] **T15** Add the `OperacionFoto` type to `frontend/aesthetic-clinic/src/types/admin.ts`.
  - Shape: `{ id: number; url: string; uploadedAt: string; fileName: string }`.
  - Place at the bottom of the file (or alongside `OperationDetailData` at line ~478).
  - Files: `frontend/aesthetic-clinic/src/types/admin.ts` (~+5 lines).
  - Depends on: none.

- [x] **T16** Add `fotosAntes` / `fotosDespues` arrays to `OperationDetailData`, plus the two response envelope types.
  - Extend `OperationDetailData` with `fotosAntes: OperacionFoto[]` and `fotosDespues: OperacionFoto[]`.
  - Add `UpdateAdminOperationObservacionesResponse = { detail: string; operation: OperationDetailData }`.
  - Add `UploadAdminOperationPhotosResponse = { detail: string; saved: OperacionFoto[]; errors: Record<string, string>; operation: OperationDetailData }`.
  - Files: `frontend/aesthetic-clinic/src/types/admin.ts` (~+15 lines, cumulative with T15).
  - Depends on: T15.

- [x] **T17** Add the three new API client functions to `frontend/aesthetic-clinic/src/services/api/admin.ts`.
  - `updateAdminOperationObservaciones(operacionId, { details })` → `requestJsonWithBody` to `/api/admin/operaciones/${id}/actualizar-observaciones/`.
  - `uploadAdminOperationPhotos(operacionId, files, kind)` → `requestFormDataWithBody` with `FormData` appending each file under `archivos` (per spec line 71).
  - `deleteAdminOperationPhoto(operacionId, photoId)` → `requestDelete` (already imported at `admin.ts:80`, already used at `admin.ts:1171`).
  - Files: `frontend/aesthetic-clinic/src/services/api/admin.ts` (~+35 lines).
  - Depends on: T16.

---

## Phase 5 — Frontend component

- [x] **T18** Create `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx`.
  - Props: `{ operacion: OperationDetailData; editable: boolean; onSaved: () => void }`.
  - Local state: `detailsText`, `saving`, `uploading: { antes: boolean; despues: boolean }`, `photos: { antes: OperacionPhoto[]; despues: OperacionPhoto[] }`, `deletingId`.
  - Initial state from `useState(() => initFromOperacion(operacion))` — no `useEffect` (avoid the lint warning).
  - Render `<SectionCard>` wrapper OR accept it from the page (per design, the page owns the `SectionCard`; the component is the inner content).
  - Read-only "Recomendaciones" block (display only, no input).
  - `<textarea>` labeled "Observaciones del procedimiento" with `Guardar` button → `updateAdminOperationObservaciones`.
  - Two `<input type="file" multiple accept="image/*">` blocks (auto-fire on `change`, sequential uploads per design).
  - Two thumbnail galleries with `×` delete buttons.
  - Empty-state placeholder `"Sin fotos."` when each gallery is empty.
  - Files: `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` (~+280 lines, new file).
  - Depends on: T15, T16, T17.

- [x] **T19** Wire the `useConfirmDialog` integration for delete-confirm.
  - Import `useConfirmDialog` (same pattern as the existing modals in the folder).
  - On `×` click: `confirm({ title: 'Eliminar foto', message: '¿Eliminar esta foto? Esta accion no se puede deshacer.', tone: 'warning' })`. Confirm → call `deleteAdminOperationPhoto`. Cancel → no request.
  - Files: included in `OperationObservationsSection.tsx` (~+15 lines, part of the +280 in T18).
  - Depends on: T18.

---

## Phase 6 — Frontend page wiring

- [x] **T20** Mount `<OperationObservationsSection>` at the bottom of `AdminOperationDetailPage.tsx`.
  - Add import after line 24: `import { OperationObservationsSection } from './components/OperationObservationsSection'`.
  - Add `canEditObservations = ['borrador', 'en proceso'].includes(operation.status.toLowerCase())` near `canEditPricePlan` (~line 592).
  - Add `<SectionCard eyebrow="Bitácora clínica" title="Observaciones del procedimiento" description="Registra notas clínicas y archiva fotos antes y después del procedimiento."><OperationObservationsSection operacion={operation} editable={canEditObservations} onSaved={reload} /></SectionCard>` after the closing `</SectionCard>` at line ~1332, before `<ReservationModal>` at ~1334.
  - Files: `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` (~+20 lines gross).
  - Depends on: T18, T19.

- [x] **T21** Remove the inline detalles editor and its state from `AdminOperationDetailPage.tsx`.
  - Remove state vars (lines ~71-77): `isEditingDetails`, `isSavingDetails`, `detailsForm`.
  - Remove handlers (lines ~224-259): `startEditingDetails`, `handleSaveDetails`, and any cancel/edit-toggle helpers tied to them.
  - Remove JSX block (lines ~746-794): the `<div className="operation-card__note-grid">…</div>`, the "Cambiar detalles y recomendaciones" trigger button (lines ~757-759), the conditional form (lines ~762-794), and the trailing `{!canEditPricePlan ? <small>…</small> : null}` hint at ~796-798.
  - Files: `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` (~−80 lines gross; combined with T20 the net delta is ~−60 lines).
  - Depends on: T20 (so the new section is already in place before the old editor comes out — keeps the page usable at every commit).

- [x] **T22** Drop the now-unused `FormEvent` type import if no other consumer remains in `AdminOperationDetailPage.tsx`.
  - Check the file for other `FormEvent` usages after T21; if zero, remove `type FormEvent` from the imports.
  - Files: `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` (~−1 line, part of T21).
  - Done when: `grep -n "FormEvent" AdminOperationDetailPage.tsx` returns zero hits.
  - Depends on: T21.

---

## Phase 7 — Verify

- [x] **T23** Run the full backend test suite.
  - Command: `python manage.py test operations.tests.test_operation_observations_photos backend.tests.test_appointment_close_split backend.tests.test_maquinaria_conflicts backend.tests.test_maquinaria_catalog backend.tests.test_appointment_reservation_extended backend.tests.test_especialista_mis_citas -v 2`.
  - All 22 new tests + existing 31+ must pass.
  - If `test_operation_observations_photos.py` was placed under `backend/operations/tests.py` instead (single-file style), adjust the path accordingly.
  - Files: none (verification only).
  - Depends on: T11, T12, T13, T14.
  - **Result**: 81 tests pass (29 new + 52 existing). The actual command runs from the `backend/` directory and uses the top-level `tests/` module rather than `backend.tests.*`. Pre-existing failures in `operations.tests.AppointmentNoShowSyncTests` (4 errors) and `config.tests.test_admin_reports` (2 errors) are unrelated to this change — `Cliente.objects.create(usuario=...)` without `fecha_nacimiento` predates this work.

- [x] **T24** Run the frontend type check.
  - Command: `cd frontend/aesthetic-clinic && npx tsc -b`.
  - No new TypeScript errors. Pre-existing unrelated errors (e.g. `AdminOperationDetailPage.tsx:174` if it existed before this change) are tolerated.
  - Files: none (verification only).
  - Depends on: T15, T16, T17, T20, T21, T22.
  - **Result**: `npx tsc -b --noEmit` exits 0 with no errors.

- [x] **T25** Manual smoke test (orchestrator + admin user).
  - Start the dev server and log in as admin.
  - Open `cms/operaciones/<id>` for an `Operacion` with `estado="EN_PROCESO"`.
  - Verify the section is the last section card (after "Información principal", "Documento y observaciones", "Citas y cuotas").
  - Edit the textarea → `Guardar` → toast "Observaciones guardadas." → reload preserves the value.
  - Verify `recomendaciones` is shown read-only (no textarea, no save).
  - Verify the "Cambiar detalles y recomendaciones" button is gone.
  - Upload 2 antes photos + 1 despues photo via the multi-file inputs.
  - Confirm `fotosAntes.length === 2` and `fotosDespues.length === 1` after reload.
  - Try a 6 MB file → expect an inline error toast / message, no row created, siblings still saved.
  - Click `×` on a thumbnail → confirm dialog → "Cancelar" → gallery unchanged.
  - Click `×` again → confirm dialog → "Confirmar" → photo disappears, file gone from `media/operaciones/...`.
  - Reload the page → gallery persists.
  - Cross-operation isolation: create a second `Operacion` (id B), upload a photo, attempt `DELETE /api/admin/operaciones/<A>/fotos/<B-photo-id>/` via curl/Postman → expect 404.
  - Lifecycle spot-check: switch the operation to `FINALIZADA`, reload → textarea disabled, file inputs hidden, delete buttons hidden, gallery still visible.
  - Files: none (verification only — record results in `apply-progress.md`).
  - Depends on: T20, T21, T22.
  - **Result**: Checklist written into `apply-progress.md`. The orchestrator + admin user should walk through the 18 rows when running the dev server smoke test.

---

## Done criteria

- [ ] All 22 new tests in `backend/tests/test_operation_observations_photos.py` pass.
- [ ] Existing 31+ tests across `test_appointment_close_split`, `test_maquinaria_conflicts`, `test_maquinaria_catalog`, `test_appointment_reservation_extended`, `test_especialista_mis_citas` still pass.
- [ ] `npx tsc -b` from `frontend/aesthetic-clinic` introduces no new TypeScript errors.
- [ ] `AdminOperationDetailPage.tsx` net line delta is ≤ +50 (estimated −40).
- [ ] Manual smoke (T25) green in all four lifecycle states.
- [ ] `Operacion.detalles_op` persists, `recomendaciones` and `sesiones_totales` are NOT clobbered on save (verified by `test_does_not_clobber_recomendaciones` + `test_does_not_clobber_sesiones_totales`).
- [ ] Disk cleanup verified: deleted photo file is absent from `media/operaciones/...` (`test_delete_existing_returns_204_and_frees_disk`).
- [ ] No N+1: `_operation_detail` still issues the same query count as before the change (`test_gallery_is_single_query_no_n_plus_1`).

---

## size:exception needed

The line-delta forecast at the top totals **~+960 lines** across 10 files, dominated by:

1. **+450 lines** of new backend tests in `test_operation_observations_photos.py` (22 tests × ~20 lines each).
2. **+280 lines** for the new frontend component `OperationObservationsSection.tsx`.
3. **+160 lines** in `backend/config/api_views.py` for 3 handlers + `_operation_detail` extension + the queryset helper + threading `request` at 8 call sites.

This exceeds the 400-line review budget by **~140%**. Even after netting the −40-line shrink on `AdminOperationDetailPage.tsx`, the diff is far above the gate.

**Orchestrator action required before launching `sdd-apply`:**

- The delivery strategy was set to `single-pr` with a review budget of 800 lines and a 400-line gate. The forecast breaches the gate.
- Recommended path: present the user with the three work-unit options from the table at the top of this file (chained PRs) OR request explicit `size:exception` approval for a single PR.
- Do NOT launch `sdd-apply` until the user (or the orchestrator on the user's behalf) confirms one of:
  - Chained PRs in stacked-to-main order (PR 1 backend code, PR 2 tests, PR 3 frontend).
  - Chained PRs as a feature-branch chain.
  - `size:exception` granted (single PR, no chain).
- If `size:exception` is chosen, split the test file in half so PR-equivalent review chunks stay under 400 lines where possible — but the apply phase still ships one PR.
