# Explore: operation-observations-photos

## Context

The user wants a new section at the bottom of `cms/operaciones/<id>` (admin operation detail page) that lets the admin edit `Operacion.detalles_op` (a `TextField` already on the model) and attach persistent before/after photos at the **operation** level. The photos stay until the admin deletes them — replacing on every upload is rejected by the user.

Two important constraints from the orchestrator (verified by the explore phase):

- The text area edits `Operacion.detalles_op` (existing field on `backend/operations/models.py:55`). Do NOT add a new column.
- The per-cita single `foto_antes` / `foto_despues` `ImageField` on `CitaMedica` (`backend/operations/models.py:207-216`) is a different concern and must NOT surface in this new gallery.

## Current behavior

- **Page entry point** — `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx`. 1664 lines. Loader at line 53 calls `getAdminOperationDetail(operationId)`. `reload()` at line 54 is the canonical "refresh from server" trigger after every mutation.
- **Page composition** — three `SectionCard`s stacked: "Información principal" (lines 665-799, includes the current detalles/recomendaciones editor inline), "Documento y observaciones" (lines 801-865, clinical record + scanned PDF), and "Citas y cuotas" (lines 867-1332, appointments list and quotas editor). After the third section there is NO fourth section today — the JSX ends with the modal/lightbox/confirm dialog renders.
- **Existing text editor** — lines 746-794. Already edits `detalles_op` and `recomendaciones` together via `updateAdminOperationDetails` (line 251) which calls the backend at `POST /api/admin/operaciones/<id>/actualizar-detalles/` (`backend/config/api_urls.py:281-285`, handler `admin_update_operation_details` at `backend/config/api_views.py:4521`). This is a JSON-only endpoint (`load_payload(request)` + `payload.get(...)`). **The text save already works**; the new section reuses this endpoint, but should not be forced to also save `recomendaciones`.
- **Existing appointment-level photos** — `CitaMedica.foto_antes` / `foto_despues` (`backend/operations/models.py:207-216`), single `ImageField` each, served via `upload_to="citas/%Y/%m/%d/{antes,despues}/"`. Edited via the per-cita multipart `PATCH /api/admin/citas/<id>/notas/` endpoint (`backend/config/api_views.py:3582-3666`, `admin_update_appointment_notes`). Frontend preview lives in the "Datos reales al cierre" modal overlay at `AdminOperationDetailPage.tsx:1384-1607` via `photoPreviewUrl` state (line 67). The preview lightbox reuses `booking-modal-overlay` styling.
- **Backend serializer for operation detail** — `_operation_detail(operacion)` at `backend/config/api_views.py:403-551`. Returns a JSON dict where `detallesOperacion` (line 466) and `recomendaciones` (line 467) are exposed for the page.
- **Existing per-operation endpoint pattern** — `admin_operacion_detalle` at `backend/config/api_views.py:4491-4518`. Decorators: `@require_GET` + `@admin_required`. Returns `{operation: _operation_detail(operacion)}`. No transaction wrapper needed for GET.
- **Existing write endpoint pattern for this page** — `admin_update_operation_details` (`api_views.py:4521`), decorators: `@require_POST` + `@admin_required` + `@transaction.atomic`, parses JSON via `load_payload`, returns `{detail, operation: _operation_detail(operacion)}`.
- **Media serving** — `MEDIA_URL="/media/"`, `MEDIA_ROOT=BASE_DIR/"media"` (`backend/config/settings.py:203-204`). Pillow is already installed (the project already uses `ImageField`).
- **Frontend API client** — `frontend/aesthetic-clinic/src/services/api/admin.ts`. `requestJsonWithBody` (line 76), `requestFormDataWithBody` (line 77), `requestJsonWithBodyIdempotent` (line 78). All in `apiClient.ts:63-150`.
- **Existing ad-hoc multi-file upload UI** — `<input type="file" multiple accept="image/*,...">` + `Array.from(event.target.files ?? [])`. See `AdminTicketDetailPage.tsx:218`, `SpecialistMessagesPage.tsx:43,85`, `SpecialistPortalPage.tsx:167`. No shared component yet.
- **Existing multipart call pattern for files** — `patchAppointmentNotes` at `admin.ts:290-308` builds a `FormData`, appends each file/value, calls `requestFormDataWithBody` to `PATCH /api/admin/citas/<id>/notas/`. Same pattern would apply for the new photo-upload endpoint.
- **Confirm dialog hook** — `useConfirmDialog` at `frontend/aesthetic-clinic/src/hooks/useConfirmDialog.tsx:55-89`. Returns `{confirm, ConfirmDialog}`. `confirm({title, message, tone})` returns a `Promise<boolean>`. Already used in `AdminOperationDetailPage.tsx:56` for `handleMarkPendingWithConfirm`.

## Files that will change

| File | Current role | Change reason |
| --- | --- | --- |
| `backend/operations/models.py` | Defines `Operacion` (line 22) and friends. `detalles_op` exists at line 55. | Add a new model for the operation-level photo gallery (`OperacionFoto` or similar). NOT touching `Operacion.detalles_op` (reused). |
| `backend/operations/migrations/0XXX_*.py` | New auto-generated migration for the photo model | Will be auto-generated. |
| `backend/config/api_views.py` | Defines `_operation_detail` and all admin endpoints | Add new endpoints (multipart upload, list-embed in detail, delete). Extend `_operation_detail` to embed the gallery payload. |
| `backend/config/api_urls.py` | URL routing for admin endpoints (lines 280-358) | Register the new photo upload and delete routes. |
| `backend/operations/admin.py` (if exists) | Django admin registration | Register the new model if Django admin uses it. **Uncertain — verify in propose phase.** |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Renders the page (1664 lines today) | Add the new section at the bottom: text area + two multi-file inputs + gallery thumbnails with delete buttons. Decide how to mount `<ConfirmDialog />` for delete confirms. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | API client | Add `uploadAdminOperationPhotos(operationId, files, kind)` and `deleteAdminOperationPhoto(operationId, photoId)`. Reuse `requestFormDataWithBody` for upload. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | TS types | Extend the `OperationDetailResponse` (or equivalent) shape with the gallery payload. Define `OperationPhoto`, `UploadPhotosResponse`, etc. |
| `frontend/aesthetic-clinic/src/hooks/useConfirmDialog.tsx` | Confirm dialog hook | No change — reuse `confirm({title, message, tone})` for delete. |
| `backend/tests/test_operation_observations_photos.py` | (new test file) | Cover upload (single + multiple files), 5 MB cap, delete, list in detail payload, gallery order stability. |

## Files that will be created

| File | Purpose |
| --- | --- |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | New section component: text area + two upload inputs + gallery with delete buttons. Self-contained so `AdminOperationDetailPage.tsx` stays close to the 1664-line envelope. **Decision deferred to propose.** |

## Backend contracts to extend

| Endpoint | Current payload | New payload |
| --- | --- | --- |
| `GET /api/admin/operaciones/<id>/` | `{operation: _operation_detail(...)}` | Adds `operation.fotosAntes: [{id, url, uploadedAt, fileName}]` and `operation.fotosDespues: [...]` arrays. Embedded inline in `_operation_detail`. |
| `POST /api/admin/operaciones/<id>/actualizar-detalles/` | `{details, recommendations, sessionsTotal?}` | Unchanged. The text save for `detalles_op` reuses this endpoint. The new section passes only `{details}` (no `recommendations` and no `sessionsTotal`). **Confirm with backend payload validation that optional fields are truly optional and don't reset other fields when omitted.** |

## Backend contracts to add

| Endpoint | Method | Purpose | Payload |
| --- | --- | --- | --- |
| `/api/admin/operaciones/<id>/fotos/<kind>/` | POST (multipart) | Append photos of `<kind> ∈ {antes, despues}` to the operation. Returns 201 with the new photo objects. | Field name: `archivos` (matches `Array.from(fileList)`) — multiple files. Each file ≤ 5 MB. |
| `/api/admin/operaciones/<id>/fotos/<photo_id>/` | DELETE | Remove a single photo. Returns 204 or `{detail}` on 404. | No body. |

## Patterns to follow

- **`admin_required + transaction.atomic + json_response`** — same decorator stack as `admin_update_operation_details` (`api_views.py:4521-4524`).
- **5 MB cap** — mirror `MAX_IMAGE_BYTES = 5 * 1024 * 1024` from `admin_update_appointment_notes` (`api_views.py:3641`). Reject one file at a time so the error message is per-file.
- **Multifile `FormData` shape** — the client appends multiple files under the same key (`archivos`). Django exposes them via `request.FILES.getlist('archivos')`. No new pattern needs inventing.
- **Storage path** — `upload_to="operaciones/%Y/%m/%d/<kind>/"` to mirror the per-cita pattern (`"citas/%Y/%m/%d/antes/"`) and keep backups organized.
- **`_operation_detail` extension** — embed the gallery in the same payload to avoid a second round-trip on page load.
- **Frontend service wrappers** — `requestFormDataWithBody` for upload; `requestJsonWithBody(url, {})` or a dedicated `requestDelete` helper for delete. **Check if a `requestDelete` helper already exists in `apiClient.ts` before deciding.** Uncertain.
- **Confirm dialog** — `confirm({title: 'Eliminar foto', message: '¿Eliminar esta foto? Esta accion no se puede deshacer.', tone: 'warning'})` per thumbnail.

## Open questions

These are decisions for the proposal phase. NOT decided here.

1. **Placement of the new section in the page** — at the very bottom (after "Citas y cuotas") vs as a fourth sibling before the appointments section vs folded into the existing "Información principal" section. The orchestrator said "at the bottom", but the propose phase should confirm whether the text-area editor from "Información principal" (lines 762-794) should be moved INTO the new section or kept duplicated, since both edit the same field.
2. **Single "Guardar" button vs split workflow** — text save on its own button, photo uploads auto-fire on file selection (no button). Or one "Guardar todo" button at the section bottom.
3. **Photo ordering in the gallery** — upload order (chronological, oldest first), reverse-chronological (newest first, like Instagram), or DB id order. The API must guarantee stable order across reloads.
4. **Where the photo model lives** — `backend/operations/models.py` next to `Operacion`, or a separate `backend/operations/photos.py`. New model is small (operacion FK, kind, image, uploaded_at). Keeping it in `models.py` is consistent with `CitaMaquinaria`/`CitaEspecialista` pattern (same file).
5. **Delete endpoint shape** — per-photo (`DELETE /api/admin/operaciones/<op>/fotos/<photo_id>/`) vs batch (`DELETE` with body listing ids). The user explicitly chose persistent-with-per-photo-delete, which favors per-photo.
6. **Photo kind discriminator** — separate endpoints (`/fotos/antes/` and `/fotos/despues/`) vs a single endpoint with `kind` in the URL or body. The user labeled them as two separate inputs, suggesting two URLs. Tradeoff: two URLs are slightly more typing in `api_urls.py` but the frontend mapping is trivial.
7. **Gallery scope for citas** — the existing per-cita `foto_antes`/`foto_despues` (used in "Datos reales al cierre" modal) must NOT appear here. The new gallery is operation-scoped only. Must not be accidentally merged.
8. **Photos and `Operacion.estado=CANCELADA`** — should the gallery still be editable after cancellation? Probably yes (admin might still want to attach documentation after the fact), but the propose phase should confirm.
9. **File-type validation** — images only (per `accept="image/*"`) or accept PDFs too (since the page already references a clinical PDF)? The user's request says "Fotos" so images only, but the propose phase should confirm.

## Risks

- **Disk space and orphan files** — uploaded images stay on disk forever unless the delete endpoint also removes the file from `MEDIA_ROOT`. Make sure the handler calls `instance.imagen.delete(save=False)` after the model delete. Otherwise: orphan files pile up in `media/operaciones/...`.
- **5 MB cap consistency** — the existing per-cita cap is 5 MB (`api_views.py:3641`). Mirror it on the new endpoint. If we drop the cap or raise it, we diverge from the existing convention.
- **Deletion race** — if the admin uploads and deletes in quick succession, two requests can race. The `transaction.atomic` ensures the delete is consistent but cannot prevent a stale-list-after-reload bug in the UI. Mitigate by always reloading after each mutation.
- **Migration ordering** — adding a new model that points at `Operacion` is additive. Existing migrations end at `0026_citamedica_descripcion_general_and_more.py`. The auto-generated migration number is irrelevant but must be unique and applied before tests run.
- **No existing test covers the operation detail endpoint** — `grep` shows zero tests call `admin_operacion_detalle` or `actualizar-detalles/`. The new test file is the first; do NOT couple it to the existing `test_appointment_close_split.py` patterns blindly.
- **Frontend bundle growth** — `AdminOperationDetailPage.tsx` is already 1664 lines. Adding the section inline pushes it past 1800. The propose phase should decide whether to extract to a sibling component (preferred) or inline.
- **MEDIA serving in production** — `MEDIA_URL` is wired but production deployments (Whitenoise, S3, etc.) may not serve uploaded files. Out of scope for this change, but verify local dev works end-to-end.
- **Pillow / image format edge cases** — `ImageField` validates basic format but rejects HEIC and other modern formats silently. Document that uploads must be JPEG/PNG/WEBP.
- **`Operacion` has no `paciente.actualizar_estado_automaticamente()` trigger concern** — uploads do not change the operation state, so the post-save hook at `models.py:698-701` does not need touching.

## Readiness checklist

- [x] Architectural facts verified against source (model fields, endpoints, decorators).
- [x] Prior-change house style read (`appointment-close-split/explore.md` mirrored).
- [x] Files-to-touch list compiled with one-line justifications.
- [x] Open questions enumerated for the propose phase (NOT decided here).
- [x] Risks documented with specific causes.
