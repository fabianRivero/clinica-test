# Archive Report: operation-observations-photos

## Status

`ok` — change is fully implemented, verified, and archived.

## Final summary

Adds a new "Observaciones del procedimiento" section at the bottom of `cms/operaciones/<id>` that lets an authenticated admin edit `Operacion.detalles_op` and manage a persistent per-operation before/after photo gallery. Ships end-to-end: a new `OperacionFoto` Django model (no `updated_at`, per spec AD2), a one-field text-save endpoint (`actualizar-observaciones/`) that does NOT clobber `recomendaciones` or `sesiones_totales`, a 5 MB-capped multipart upload endpoint (`fotos/<kind>/`) with per-file partial-success reporting, a per-photo DELETE endpoint (`fotos/<photo_id>/`) that also removes the file from disk, an extracted sibling React component (`OperationObservationsSection.tsx`), the matching API client + types, and removal of the legacy inline detalles/recomendaciones editor at `AdminOperationDetailPage.tsx:746-794` (with `recomendaciones` now rendered read-only). The gallery embeds directly into `_operation_detail` via a new `Prefetch`, ordered by `uploaded_at ASC, id ASC`, so the page renders in a single fetch.

## Spec compliance verdict

**20/20 PASS** (per `verify-report.md`, which ranks above `apply-progress.md` per Final-State Authority).

13 ADDED requirements, 1 REMOVED requirement (inline editor), and 1 RENAMED requirement — all satisfied. Each row was verified against source, not the apply narrative. The two flagged apply-progress risks (URL ordering with `<int:photo_id>` BEFORE `<str:kind>`; UUID prefix strip) are both addressed in the shipped code; the design's `update_fields=["detalles_op", "updated_at"]` text on the new `OperacionFoto` model is overridden by design AD2 + the binding spec text (no `updated_at` column), confirmed at runtime via Django shell.

## Test result

**83 tests pass, 0 failures** (per `verify-report.md`, the broader regression sweep).

Breakdown per `verify-report.md`:

- New `tests/test_operation_observations_photos.py` — 29 tests across 5 classes (`UpdateObservacionesTests`, `UploadPhotosTests`, `DeletePhotoTests`, `OperationDetailGalleryTests`, `LifecycleTests`). 3.9 s.
- Regression sweep across 6 related modules (`test_operation_observations_photos`, `test_appointment_close_split`, `test_operation_item_started_at_iso`, `test_especialista_mis_citas`, `test_appointment_notes`, `test_appointment_reservation_extended`) — 83 tests, 31.7 s on first run / 59.9 s on second.

**Note on source disagreement** — recorded for transparency per Final-State Authority (contradictions that cannot be ranked are recorded, not resolved silently):

- `apply-progress.md` (intermediate snapshot, T23) reported **81 tests** passing on its T23 sweep (29 new + 52 existing). `verify-report.md` (final verification, more recent and broader) reports **83 tests** passing on its regression sweep. Per Final-State Authority §2 and §3, the verify-report's count is the current state because it is the more recent and more complete sweep; apply-progress's `81` is preserved as historical record.

Frontend type-check (`npx tsc -b`) exits 0 with no new errors (per `verify-report.md`).

Pre-existing baseline failures in `operations.tests.AppointmentNoShowSyncTests` (4 errors) and `config.tests.test_admin_reports` (2 errors) are **NOT** in scope of this change — they fail with `IntegrityError: NOT NULL constraint failed: clientes.fecha_nacimiento` in `Cliente.objects.create(usuario=...)` fixtures that pre-date this work. Recorded in both `apply-progress.md` and `verify-report.md` as out-of-scope.

## Manual smoke checklist

**PENDING — manual verification on dev server.**

The T25 18-row smoke checklist is written into `apply-progress.md:185-215` and accepted as-is by the verifier (`verify-report.md:92-110`). No execution has been performed by `sdd-apply` (the apply agent did NOT start a dev server). The orchestrator + an admin user must walk through the checklist before the PR merges. Checklist covers:

1. Section order on `cms/operaciones/<id>` (Información principal → Documento y observaciones → Citas y cuotas → Observaciones del procedimiento).
2. Section contains: read-only "Recomendaciones" + editable textarea + single "Guardar" + two photo blocks.
3. `recomendaciones` is rendered read-only (no textarea, no save).
4. "Cambiar detalles y recomendaciones" button is GONE.
5. Textarea save → toast → reload preserves; `recomendaciones` / `sesiones_totales` unchanged.
6. Upload 2 antes + 1 despues via multi-file inputs.
7. Gallery counts after upload (`fotosAntes.length === 2`, `fotosDespues.length === 1`).
8. Reload persistence + upload-time ASC ordering.
9. 6 MB file rejection with partial-success siblings.
10. Confirm dialog with exact Spanish copy + warning tone.
11. Cancel → no request, gallery unchanged.
12. Confirm → photo disappears AND file gone from `media/operaciones/...`.
13. Cross-operation isolation (404).
14. Lifecycle FINALIZADA / BORRADOR / CANCELADA spot-checks.

## Files changed

Line-delta from `git diff --stat` (working tree, all-tracked + new files; baseline includes pre-existing unrelated changes in `api_views.py`, `client_api_views.py`, `api_helpers.py`, `client-detail/*`, `CerrarCitaModal.tsx`, `viewsets/operaciones.py`, `test_appointment_close_split.py`, `test_operation_item_started_at_iso.py`):

```
 23 files changed, 2191 insertions(+), 236 deletions(-)
```

Files attributed to **this change** (per `apply-progress.md` and `verify-report.md`):

| File | Action | Net delta | Notes |
| --- | --- | --- | --- |
| `backend/operations/models.py` | Modified | +47 | `OperacionFoto` model + `_operacion_foto_upload_to` callable + `import uuid`. |
| `backend/operations/migrations/0027_operacionfoto.py` | Created | +30 | Auto-generated by `makemigrations`. |
| `backend/operations/admin.py` | Modified | +8 | `OperacionFotoAdmin`. |
| `backend/config/api_views.py` | Modified | +354 / −98 (this change only; baseline diff unrelated inflates the absolute number) | 3 endpoints + `_operation_detail_queryset()` helper + `_operation_detail(request=None)` extension + `request` threading at 7 call sites. |
| `backend/config/api_urls.py` | Modified | +22 | 3 routes + import block. `<int:photo_id>` placed BEFORE `<str:kind>` to avoid misrouting. |
| `backend/tests/test_operation_observations_photos.py` | Created | +544 | 29 tests across 5 classes. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | +40 | `OperacionFoto` type + 2 envelope types + `fotosAntes`/`fotosDespues` fields. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | +76 | 3 new functions (`updateAdminOperationObservaciones`, `uploadAdminOperationPhotos`, `deleteAdminOperationPhoto`). |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Modified | −108 net | Inline editor removed (state + handlers + JSX + `FormEvent` import); `OperationObservationsSection` mounted at the bottom. |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | Created | +327 | New section. |
| `openspec/changes/operation-observations-photos/specs/operation-observations-photos/spec.md` | Created | n/a | Delta spec (this archive syncs it into the canonical tree). |
| `openspec/changes/operation-observations-photos/proposal.md`, `design.md`, `tasks.md`, `apply-progress.md`, `verify-report.md` | Created | n/a | SDD artifacts. |

`AdminOperationDetailPage.tsx` shrank from 1664 → 1598 lines (−66 net). Within the spec's ≤ +50 net target.

## Risks carried into maintenance

Per `verify-report.md` (SUGGESTION section, ranked above `apply-progress.md`):

1. **Pre-existing baseline diff in working tree** inflates `git diff --stat` past the 1200-line threshold. The baseline changes (in `api_views.py`, `client_api_views.py`, `api_helpers.py`, `client-detail/*`, `CerrarCitaModal.tsx`, `viewsets/operaciones.py`, `test_appointment_close_split.py`, `test_operation_item_started_at_iso.py`) are **unrelated** to this change. Recommend committing this change as a separate commit (or PR) so the per-commit review budget stays clean.

2. **FE-only lifecycle gate.** `BORRADOR` and `EN_PROCESO` are the only editable states from the UI. The backend still accepts mutations in `FINALIZADA` / `CANCELADA` — by spec design (v1, FE-only). A future server-side gate is a one-line addition per handler. The `LifecycleTests` class documents this server-permissive behaviour in the test docstrings.

3. **UUID prefix in `OperacionFoto.imagen.name`.** The current implementation strips the 12-hex + `-` prefix (i.e. `basename[13:]`) in both `_photo_to_payload` and `admin_upload_operation_photos` so the FE renders the bare filename the admin picked. The strip is per-spec but if a future spec wants to expose the prefix to the admin (e.g. as a unique key), both strips must back out.

## Out-of-scope items (per orchestrator)

Explicitly deferred:

- **Server-side lifecycle gate** — the FE-only gate is the spec decision for v1; the backend accepts mutations regardless of `estado`. Future hardening is a one-line addition per handler.
- **Concurrent upload races** — out of scope for v1. Each handler runs in `transaction.atomic`; UI always `reload()`s after each mutation so stale state cannot outlive the next refresh.
- **Gallery reordering UX** — drag-reorder is NOT in v1; the API guarantees stable upload-order (`uploaded_at ASC, id ASC`) and the FE renders in that order.

(Other out-of-scope items per `proposal.md` §Out of scope: editing `recomendaciones` from any UI, editing `sesiones_totales` from the new section, replacing per-cita `CitaMedica.foto_antes` / `foto_despues`, bulk-select multi-delete, drag-reorder, PDF attachments, production MEDIA serving (Whitenoise / S3) verification, bulk-upload progress UI, specialist-side photo capture, lightbox component.)

## Spec sync (this archive)

Delta spec at `openspec/changes/operation-observations-photos/specs/operation-observations-photos/spec.md` was **mechanically copied** (shell `cp`, not Read → Write) into the canonical tree at:

```
openspec/specs/operation-observations-photos/spec.md
```

The destination capability directory did NOT pre-exist; one was created. Per the SKILL's Mechanical Copy Contract:

- Source: `openspec/changes/operation-observations-photos/specs/operation-observations-photos/spec.md`
- Destination: `openspec/specs/operation-observations-photos/spec.md`
- Bytes written: 19,419
- `diff -r` readback against the temp staging file: **empty (no differences)** — only passing evidence.
- `diff -r` readback against the final destination: **empty (no differences)** — only passing evidence.

The change folder at `openspec/changes/operation-observations-photos/` is **NOT** moved to `openspec/changes/archive/` — per the orchestrator's explicit instruction ("Do NOT delete the change folder. The change folder stays as historical record; the canonical specs/ tree gains the new spec"). The delta spec remains in the change folder as historical record; the canonical `openspec/specs/` tree gains the new spec.

## Linked artifacts

- Proposal: `openspec/changes/operation-observations-photos/proposal.md`
- Explore: `openspec/changes/operation-observations-photos/explore.md`
- Design: `openspec/changes/operation-observations-photos/design.md`
- Spec (delta, in change folder — historical): `openspec/changes/operation-observations-photos/specs/operation-observations-photos/spec.md`
- Spec (synced, canonical): `openspec/specs/operation-observations-photos/spec.md`
- Tasks: `openspec/changes/operation-observations-photos/tasks.md`
- Apply progress: `openspec/changes/operation-observations-photos/apply-progress.md`
- Verify report: `openspec/changes/operation-observations-photos/verify-report.md`
- This archive report: `openspec/changes/operation-observations-photos/archive-report.md`

## Post-archive recommendations

1. **Run the T25 manual smoke checklist on a dev server** (`./env/bin/python manage.py runserver`) before merging. The 18 rows in `apply-progress.md:185-215` cover all four lifecycle states (BORRADOR / EN_PROCESO / FINALIZADA / CANCELADA) and the cross-operation isolation check.
2. **Commit this change as a separate commit** (or single PR) so the per-commit review budget is clean; the pre-existing baseline diff is unrelated and inflates `git diff --stat` past the 1200-line threshold.
3. **Optional follow-up (size:exception already granted)** — a future PR can add a Playwright spec for the per-section component if regression coverage of the upload/delete/save flows is desired.
4. **Optional follow-up** — add a server-side lifecycle gate (`if operacion.estado in {FINALIZADA, CANCELADA}: return 400`) if/when product wants to harden the FE-only lifecycle decision.
