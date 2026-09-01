# Proposal: Operation Observations Photos

> **Executive summary**: add a new "Observaciones del procedimiento" section at the bottom of `cms/operaciones/<id>` for editing `Operacion.detalles_op` and managing persistent before/after photo galleries — **which replaces the existing inline detalles/recomendaciones editor at `AdminOperationDetailPage.tsx:746-794`, removes its trigger button, and makes `recomendaciones` read-only on this page.** The legacy `admin_update_operation_details` endpoint is kept for backward compatibility but no longer wired to any UI.

## Why

The operation detail page at `cms/operaciones/<id>` (renderer `AdminOperationDetailPage.tsx`, 1664 lines today) lets the admin read `Operacion.detalles_op` and `recomendaciones` via an inline editor at lines 762-794 (the "Cambiar detalles y recomendaciones" button + form) — but that editor is being **replaced** by this change. After this change, the only edit surface on the page for `detalles_op` is the new section, and `recomendaciones` is read-only. There is also no way to attach **persistent** before/after photos at the operation level — the only photo fields today live on `CitaMedica` (`foto_antes`, `foto_despues`, `backend/operations/models.py:207-216`) and are a single-replace `ImageField` per cita, scoped to the per-cita "Datos reales al cierre" modal overlay (`AdminOperationDetailPage.tsx:1384-1607`).

The user wants a new section at the bottom of `cms/operaciones/<id>` that:

1. Edits `Operacion.detalles_op` (existing `TextField` — do NOT add a new column).
2. Lets the admin upload any number of "antes" and "despues" photos for the operation as a whole.
3. Keeps uploaded photos persistent until the admin explicitly deletes one. Replacing on every upload is rejected.

Two constraints were locked by the orchestrator and verified against source:

- The text editor reuses the existing `Operacion.detalles_op` field. No schema migration for the text.
- The per-cita `foto_antes` / `foto_despues` fields are a separate concern and MUST NOT appear in the new gallery.

## What changes

A new fourth section at the bottom of `AdminOperationDetailPage.tsx` (after "Citas y cuotas") that renders:

- One textarea bound to `detalles_op` (the "observaciones del procedimiento" the user asked for).
- Two `accept="image/*" multiple` inputs — one for "Fotos antes", one for "Fotos despues".
- Two thumbnail galleries, each with a per-photo delete button that opens a confirm dialog.
- A single `Guardar` button that persists the textarea content. Photo uploads auto-fire on file selection (see Decision 2 below).

Two new backend endpoints and one new model. The existing `GET /api/admin/operaciones/<id>/` payload is extended to embed the photo gallery, so the page loads in a single round-trip. The new section is extracted into a sibling component (see Decision 1).

## Out of scope

- Editing `Operacion.recomendaciones` from anywhere on this page. The new section touches `detalles_op` only; `recomendaciones` becomes a read-only field rendered inside the new section (display only, no textarea, no save button). The existing endpoint that updates it remains available server-side for backward compatibility, but no longer has any UI surface here.
- Editing `Operacion.sesiones_totales` from the new section. Already handled in "Citas y cuotas".
- Replacing the existing per-cita single `foto_antes` / `foto_despues` fields on `CitaMedica`. They remain a per-cita replace-style capture for the close-time flow.
- Bulk-select multi-delete on the gallery. UX is per-photo delete with confirm (see Decision 5).
- Drag-reorder of gallery thumbnails. The API guarantees stable upload-order; reorder is not in v1.
- PDF attachments. Inputs accept `image/*` only (see Decision 9).
- Changing the production MEDIA serving setup (Whitenoise / S3) — only verified locally.
- A bulk upload progress UI (X/N indicators). The new section shows one toast per upload + per delete, same shape as the existing `showNotification` calls.

## Decisions resolved during planning

These were deferred by the orchestrator. The proposal locks them down so the spec phase does not have to re-ask.

### 1. Section placement — extracted to a sibling component

The new section lives in a new file `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` and is imported + rendered by `AdminOperationDetailPage.tsx`. The page gets a new `<SectionCard title="Observaciones del procedimiento">…</SectionCard>` at the bottom (after the existing "Citas y cuotas" block, before the closing `</div>`).

**Justification**: the page is already 1664 lines; inlining pushes it past 1800 and creates review friction. The page already imports sibling components (`ReservationModal`, `CerrarCitaModal`, `RescheduleAppointmentModal`); one more follows the established pattern. The new component receives `operation` and `onReload` as props — same pattern the existing modals use.

### 2. Single Guardar button (text) + auto-upload on file select (photos)

- Textarea has its own `Guardar` button that calls `updateAdminOperationDetails({ details })` (the existing endpoint) and triggers `onReload()` on success.
- Photo inputs fire `uploadAdminOperationPhotos(operationId, files, kind)` immediately when files are selected. No submit button for photos.
- Each upload shows a toast (`showNotification({ kind: 'success', message: 'Foto antes subida.' })` per file, or one error toast with the per-file error from the backend).
- Each delete opens the existing `useConfirmDialog().confirm({ title: 'Eliminar foto', message: '…', tone: 'warning' })`, then calls `deleteAdminOperationPhoto` and reloads.

**Justification**: the inline editor this section replaces (previously at lines 762-794) was a single Guardar button for the textarea. Auto-upload for files is the established UX for the per-cita photo replacement at `AdminTicketDetailPage.tsx:218` and `SpecialistMessagesPage.tsx:43,85` — those fire on file select, not on a submit. Mixing both patterns (button for text, auto for files) keeps the new section consistent with its neighbours.

### 3. Photo gallery ordering — uploaded_at ASC, id ASC as tiebreak

The API returns photos ordered by `uploaded_at ASC, id ASC`. This is upload-chronological (oldest first), matching the storage path convention and giving the admin a stable, predictable order across reloads. Reverse-chronological (Instagram-style) was rejected because it makes new uploads jump to the top and breaks the "before/after" mental model — admins want to compare the earliest antes photo against the latest despues photo without re-sorting.

The new model has a compound index on `(operacion, kind, uploaded_at, id)` to make this ordering an index-only scan and avoid a sort on large galleries.

### 4. New model lives in `backend/operations/models.py`

`OperacionFoto` is added to `backend/operations/models.py` next to `Operacion` and `CitaMedica`. Extraction to `backend/operations/photos.py` was rejected because:

- `models.py` already contains `Operacion`, `CitaMedica`, `CitaMaquinaria`, `CitaEspecialista`, `PlantillaProcedimiento`, `ConfiguracionProcedimiento`, `Disponibilidad`, etc. — 719 lines total. Adding a ~30-line model is in-family.
- The FK target (`Operacion`) is in the same file; cross-file FKs work but require more imports.
- Existing `CitaMedica.foto_antes` / `foto_despues` are already in `models.py` and live alongside `CitaMedica`. Same cohesion argument applies here.

If the file grows past a comfortable threshold later, extraction is straightforward (single FK + 4 fields).

### 5. Delete endpoint shape — per-photo DELETE

`DELETE /api/admin/operaciones/<operacion_id>/fotos/<photo_id>/` with no body. Returns 204 on success, 404 if the photo does not exist or belongs to a different operation.

**Justification**: the user explicitly chose "persistent-with-per-photo-delete". Per-photo clicks map 1:1 to per-photo endpoints. Batch DELETE with body listing ids was rejected — it implies bulk-select UX (which the orchestrator did not ask for) and adds a body-parsing surface for no v1 benefit.

### 6. Observations editor relationship — REPLACES the inline editor (LOCKED)

The orchestrator confirmed the replacement. The new bottom section is the **single edit surface** for `Operacion.detalles_op` on this page, and the old inline editor is gone:

- The "Cambiar detalles y recomendaciones" trigger button at `AdminOperationDetailPage.tsx:757-759` is REMOVED.
- The inline form at `AdminOperationDetailPage.tsx:762-794` (the editor with both textareas) is REMOVED, along with all of its state: `isEditingDetails`, `detailsForm`, `handleSaveDetails`, `startEditingDetails`, and the corresponding cancel/edit-toggle handlers.
- The read-only note-grid at `AdminOperationDetailPage.tsx:746-755` (the "Detalles de la operación" / "Recomendaciones" display block) STAYS, but `recomendaciones` now has **no editor anywhere on the page** — it is rendered read-only inside the new section (display only, no textarea, no save button).
- The new bottom section owns its own textarea bound to `detalles_op` only. The field is renamed in the UI label to **"Observaciones del procedimiento"** (matches the user's framing); the backend column stays `Operacion.detalles_op`.
- `Operacion.recomendaciones` remains on the model and is still readable via `_operation_detail` — admins can see the value, they just cannot edit it from this page anymore.

**Why replace (not coexist):**

- The existing endpoint does NOT do partial updates (see Decision 6.1 below). Two editors that each save `detalles_op` race and clobber each other, and any reuse of `actualizar-detalles/` would silently overwrite `recomendaciones` and `sesiones_totales`.
- `recomendaciones` and `detalles_op` are two semantically different fields. The new section was explicitly framed as "observaciones del procedimiento", which maps to `detalles_op` only. Bundling `recomendaciones` into the new editor would conflate them.
- Clean ownership: one editor, one field, one save. The legacy `recomendaciones` editor was over-featured for v1 and is rarely used; the field itself stays on the model so other surfaces (future re-wiring, data import, admin scripts) can still mutate it through the existing endpoint.

### 6.1 Endpoint shape for the new text save — NEW endpoint required

The existing `POST /api/admin/operaciones/<id>/actualizar-detalles/` (`api_views.py:4521-4573`) **does not support partial updates**. Lines 4548-4551 unconditionally overwrite `detalles_op`, `recomendaciones`, AND `sesiones_totales` on every save. The frontend today sends `{ details, recommendations, sessionsTotal }` together and they are all set.

The new bottom section only edits `detalles_op`. We need a new endpoint:

- **NEW** `POST /api/admin/operaciones/<id>/actualizar-observaciones/` (JSON, single field `details`). Touches `detalles_op` only. Returns `{ detail, operation: _operation_detail(...) }` for symmetry with the existing endpoint.

This avoids the clobber risk and avoids changing the contract of the existing endpoint (which would break the inline form, the cms/clientes/ pages, etc., even though we are removing the inline form here).

### 7. Backend endpoint names

- `POST /api/admin/operaciones/<int:operacion_id>/fotos/<str:kind>/` — multipart upload, appends photos of `kind ∈ {antes, despues}`. Field name `archivos` (multi-file under the same key). 5 MB cap per file. Status 201 with `{ detail, operation: _operation_detail(...) }`.
- `DELETE /api/admin/operaciones/<int:operacion_id>/fotos/<int:photo_id>/` — removes a single photo. Also deletes the file from disk via `instance.imagen.delete(save=False)` to prevent orphans. Returns 204 on success, 404 if not found.

URL pattern mirrors `/api/admin/operaciones/<id>/actualizar-detalles/` and `/api/admin/citas/<id>/notas/`. Decorator stack: `@require_POST` / `@require_http_methods(["DELETE"])`, `@admin_required`, `@transaction.atomic`. `kind` is validated against `{ antes, despues }` — anything else returns 400.

### 8. Migration strategy

One new auto-generated Django migration for the new `OperacionFoto` model. No data migration. The `Operacion.detalles_op` field is unchanged. Migration filename will be picked by `python manage.py makemigrations` (the existing migration sequence ends at `0026_citamedica_descripcion_general_and_more.py` per explore).

### 9. Response shape additions to `_operation_detail`

`_operation_detail(operacion)` at `api_views.py:403-551` adds two new fields:

- `operation.fotosAntes: Array<{ id: number, url: string, uploadedAt: string (ISO 8601), fileName: string }>`
- `operation.fotosDespues: Array<{ id, url, uploadedAt, fileName }>`

Both arrays are ordered by `uploaded_at ASC, id ASC`. `url` is a fully-qualified absolute URL built from `request.build_absolute_uri(photo.imagen.url)` so the frontend can drop it straight into `<img src>`. No second fetch is needed — the page renders the gallery from the existing detail payload.

The `Operacion` queryset in `_operation_detail` gets a new `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))` so the gallery is a single query, not N+1.

### 10. Partial-success on upload — per-file success/failure surface

The endpoint validates each file independently and reports per-file outcomes. Response shape on partial success:

```json
{
  "detail": "Algunas fotos no pudieron subirse.",
  "saved": [{ "id": 42, "url": "...", "uploadedAt": "...", "fileName": "antes-1.jpg" }],
  "errors": {
    "archivos[2]": "La imagen no puede superar los 5 MB (tamano actual: 7340032 bytes)."
  },
  "operation": { ... full operation detail ... }
}
```

- HTTP 201 when at least one file saved successfully (partial success).
- HTTP 400 when zero files saved (full failure, with per-file errors).
- HTTP 400 if `archivos` is missing entirely or `kind` is not in `{antes, despues}`.
- HTTP 413 is NOT used — the existing per-cita endpoint returns 400 with `errors[fotoAntes] = "..."` and the new endpoint mirrors that.

**Justification**: the per-cita photo endpoint (`api_views.py:3582-3666`) already does per-file validation with a `5 MB` cap and returns `{detail: "Datos invalidos.", errors: {...}}` on 400. Mirroring that shape keeps the frontend error-handling code symmetrical. Failing the whole batch on a single oversized file is hostile UX (admin uploads 10 files, one is 5.1 MB, all 9 succeed and one fails, but the admin has to redo all 10).

## User experience

### Admin flow (cms/operaciones/<id>)

1. Admin opens the operation detail page. Scrolls past "Información principal", "Documento y observaciones", and "Citas y cuotas".
2. A new section "Observaciones del procedimiento" appears at the bottom. It contains:
   - One textarea labeled "Observaciones del procedimiento" bound to `operation.detallesOperacion` (the only editable field in this section).
   - A read-only display block showing the current `recomendaciones` value, labeled "Recomendaciones" — text only, no textarea, no save button. If the value is empty, the block renders the existing placeholder text.
   - Below the textarea, two horizontal blocks:
     - **Fotos antes**: a `Seleccionar archivos…` button (multi-select, `accept="image/*"`) + a grid of thumbnails with a small `×` button on each.
     - **Fotos despues**: same shape.
   - At the very bottom: a single `Guardar` button for the textarea. Photo uploads do NOT use this button.
3. Admin edits the textarea and clicks `Guardar`. Toast: "Observaciones guardadas.".
4. Admin clicks `Seleccionar archivos…` under "Fotos antes", picks 3 JPEGs from disk. The page immediately starts uploading each file (sequential or parallel — TBD in spec phase). Per file: a brief "Subiendo…" toast, then "Foto antes subida." on success or "No se pudo subir la foto: …" on failure. Thumbnails appear in the gallery as each upload completes.
5. Admin clicks the `×` on a thumbnail. The existing confirm dialog asks "¿Eliminar esta foto? Esta accion no se puede deshacer." (ES, verbatim). On confirm, the file is deleted server-side and from disk, the gallery reloads, the thumbnail disappears.
6. Admin leaves the page and returns later. The gallery is still there (persistent until deleted).
7. The "Cambiar detalles y recomendaciones" button (previously at line 757) and the inline detalles form (previously at lines 762-794) are gone. There is no longer any UI on this page that edits `recomendaciones` — admins see the value but cannot change it here. The model column stays and the legacy endpoint remains available for any other caller.

### Out-of-scope-but-related UX (already on the page)

- The per-cita single-replace photo flow ("Datos reales al cierre" modal at `AdminOperationDetailPage.tsx:1384-1607`) is untouched. It still uses `CitaMedica.foto_antes` / `foto_despues`. The new gallery does NOT show those photos.
- The per-cita `notes` photos at `/api/admin/citas/<id>/notas/` (`descripcionGeneral`, `notasPrevias`, `notasPost`, `fotoAntes`, `fotoDespues`) — same, untouched.

### Sketch (plain text)

```
┌─ Observaciones del procedimiento ────────────────────────────────────┐
│                                                                     │
│  Observaciones del procedimiento                                    │
│  [textarea, 6 rows, bound to operation.detallesOperacion]            │
│                                                                     │
│                                            [ Guardar ]              │
│                                                                     │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  Fotos antes                                  [ + Seleccionar … ]   │
│  ┌────┐ ┌────┐ ┌────┐                                              │
│  │img │ │img │ │img │                                              │
│  │ ×  │ │ ×  │ │ ×  │                                              │
│  └────┘ └────┘ └────┘                                              │
│                                                                     │
│  Fotos despues                                [ + Seleccionar … ]   │
│  ┌────┐ ┌────┐                                                      │
│  │img │ │img │                                                      │
│  │ ×  │ │ ×  │                                                      │
│  └────┘ └────┘                                                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

The thumbnails are clickable to open a lightbox preview (the existing `photoPreviewUrl` pattern at line 67 can be reused, or a sibling component — spec phase decides).

## API surface

### New endpoints

| Method | URL | Body | Response |
| --- | --- | --- | --- |
| POST | `/api/admin/operaciones/<int:operacion_id>/actualizar-observaciones/` | JSON `{ "details": "..." }` | 200 `{ "detail": "...", "operation": <_operation_detail> }` |
| POST | `/api/admin/operaciones/<int:operacion_id>/fotos/<str:kind>/` | multipart, `archivos` multi-file (≤ 5 MB each, image/*) | 201 `{ "detail": "...", "saved": [...], "errors": {...}, "operation": <_operation_detail> }` — `errors` is empty on full success. 400 on full failure or invalid `kind`. |
| DELETE | `/api/admin/operaciones/<int:operacion_id>/fotos/<int:photo_id>/` | none | 204 on success. 404 if photo not found OR belongs to a different operation (don't leak existence). |

### Modified endpoints

| Method | URL | Current payload | New payload |
| --- | --- | --- | --- |
| GET | `/api/admin/operaciones/<int:operacion_id>/` | `{operation: _operation_detail(operacion)}` | Adds `operation.fotosAntes` and `operation.fotosDespues` arrays (see Decision 9). |
| POST | `/api/admin/operaciones/<int:operacion_id>/actualizar-detalles/` | `{ details, recommendations, sessionsTotal? }` | **Unchanged — kept for backward compatibility, deprecated.** No UI in this change calls it anymore (the inline editor is removed). The handler gets a `DeprecationWarning` docstring and is left in place so other internal callers, admin scripts, or future re-wiring can still use it. No removal is planned in this proposal; removal is a future breaking change with its own migration. |

`/api/admin/citas/<id>/notas/` is NOT modified.

## Data model

### New model `OperacionFoto` (in `backend/operations/models.py`)

```python
class OperacionFoto(TimeStampedModel):
    class Kind(models.TextChoices):
        ANTES = "antes", "Antes"
        DESPUES = "despues", "Despues"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="fotos_operacion",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    imagen = models.ImageField(upload_to="operaciones/%Y/%m/%d/<kind>/")
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "operaciones_fotos"
        ordering = ("uploaded_at", "id")
        indexes = [
            models.Index(fields=["operacion", "kind", "uploaded_at", "id"]),
        ]
```

- `upload_to="operaciones/%Y/%m/%d/<kind>/"` mirrors the per-cita pattern at `models.py:208/213` so backups stay organized by date.
- `related_name="fotos_operacion"` matches the existing FK convention (`operacion.citas_medicas`, `operacion.cuotas_plan_pagos`).
- `on_delete=CASCADE` matches `CitaMedica.foto_antes` behavior: when the operation is deleted, photos go with it.
- No `updated_at` semantics for the photo itself — uploads are immutable. `TimeStampedModel` provides `created_at`/`updated_at` but `updated_at` stays at `created_at` for new rows (Pillow ImageField doesn't mutate the file). If `updated_at` is required by the base class, accept the redundancy.

### Unchanged

- `Operacion.detalles_op` (line 55) — reused; this is the field the new section edits. **No new column on `Operacion` is introduced.**
- `Operacion.recomendaciones` (line 56) — no longer editable from this page; remains a writable column on the model and is still readable via `_operation_detail` (displayed read-only in the new section). No schema change.
- `CitaMedica.foto_antes` / `foto_despues` (lines 207-216) — separate concern, untouched.

### Migration

One new auto-generated migration (for `OperacionFoto` only). No data backfill. `Operacion.detalles_op` already exists. No column is added to `Operacion`.

## Affected areas

| File | Impact | Description |
| --- | --- | --- |
| `backend/operations/models.py` | Modified | Add `OperacionFoto` model. No change to existing models. |
| `backend/operations/migrations/0XXX_*.py` | New | Auto-generated by `makemigrations`. |
| `backend/config/api_views.py` | Modified | Add `admin_update_operation_observaciones`, `admin_upload_operation_photos`, `admin_delete_operation_photo`. Extend `_operation_detail` to embed `fotosAntes` / `fotosDespues`. Add new `Prefetch`. |
| `backend/config/api_urls.py` | Modified | Register the three new routes next to `actualizar-detalles/` (around line 285). |
| `backend/tests/test_operation_observations_photos.py` | New | ~15 tests covering: upload single + multi, 5 MB cap per file, kind validation, delete + disk cleanup, list embedding in detail payload, gallery ordering stability, optional-field behavior of `actualizar-observaciones/`, partial-success response shape. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | Add `uploadAdminOperationPhotos`, `deleteAdminOperationPhoto`, `updateAdminOperationObservaciones`. Reuse `requestFormDataWithBody` and `requestDelete` (already imported at `admin.ts:80`, already used at `admin.ts:1171`). |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | Extend `OperationDetailResponse` / equivalent with `fotosAntes`, `fotosDespues` arrays. Add `OperationPhoto`, `UploadPhotosResponse` types. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Modified | Render `<OperationObservationsSection operation={operation} onReload={reload} />` after the "Citas y cuotas" block. **Remove the inline detalles form (lines 762-794), its trigger button at lines 757-759, and all of its state (`isEditingDetails`, `detailsForm`, `handleSaveDetails`, `startEditingDetails`, and any cancel/edit-toggle handlers).** Keep the read-only note-grid at lines 746-755 only if it still serves a purpose without the editor; otherwise drop it together with the editor. |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | New | Self-contained section: textarea + 2 file inputs + 2 galleries with delete. Owns its local state. Calls `onReload` after each mutation. |

## Risks and mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| Disk orphans — deleted DB rows leave files in `media/operaciones/...` | Med | The DELETE handler calls `instance.imagen.delete(save=False)` before `instance.delete()`. Wrap in `transaction.atomic` and test with `os.path.exists`. |
| `actualizar-observaciones/` accidentally clobbers `recomendaciones` / `sesiones_totales` if reused from `actualizar-detalles/` | Low | New endpoint with its own handler that updates `update_fields=["detalles_op", "updated_at"]` only. Code review checklist item. |
| 5 MB cap divergence from the per-cita endpoint | Low | Same constant `MAX_IMAGE_BYTES = 5 * 1024 * 1024` from `api_views.py:3641`. If the cap is changed later, both endpoints change together. |
| Upload race — admin deletes + uploads the same file in quick succession | Low | `transaction.atomic` per handler. UI always calls `reload()` after each mutation, so stale state cannot outlive the next refresh. |
| Frontend page still grows — 1664 + extraction overhead ≈ 1700 | Med | Extraction reduces net page growth. Spec phase must enforce ≤ 50 net lines added to `AdminOperationDetailPage.tsx` (1 import + 1 render + deletions). |
| `recomendaciones` becomes silently read-only — admins who used the inline editor today are surprised | Med | Explicit callout in the section heading or in a one-time toast: "Ahora las recomendaciones se muestran de solo lectura. Edita 'Observaciones del procedimiento' abajo." (transient). |
| **Existing admins who relied on the inline `recomendaciones` editor lose that capability** | Med | The field is still readable on the page (display only, in the new section). The legacy `admin_update_operation_details` endpoint is kept for backward compatibility, so the field is still writable through the API — future work could re-wire a different editor surface (modal, separate page) without server-side work. No data is lost: the column is unchanged. |
| HEIC / unsupported image formats silently rejected by `ImageField` | Low | Document accepted formats in the file-input `accept` hint and in the error toast. JPEG / PNG / WEBP supported. |
| MEDIA serving in production (Whitenoise / S3) | Out of scope | Verify locally. Deployment docs flagged as follow-up. |
| Per-cita `foto_antes` / `foto_despues` accidentally shown in the new gallery | Low | Gallery reads from `Operacion.fotos_operacion` only (new FK). The per-cita fields stay on `CitaMedica` and are not joined into `_operation_detail` for this purpose. Spec phase test asserts no overlap. |

## Open questions deferred to spec phase

The spec phase should NOT re-decide anything in "Decisions resolved during planning" above — those are locked. Open questions below are flagged for the spec phase to either resolve or escalate.

1. **RESOLVED — editor duplication (previously Question #1)**: the orchestrator confirmed `detalles_op` only, replacing the inline editor. No re-surfacing needed. `recomendaciones` becomes read-only inside the new section. The legacy `actualizar-detalles/` endpoint is kept for backward compatibility (deprecated, no UI caller).

2. **Sequential vs parallel file uploads in the new section** — the spec phase picks one. Recommendation: sequential, simpler error reporting.

3. **Lightbox click target for thumbnails** — the spec phase picks: reuse the existing `photoPreviewUrl` pattern (cross-component state via prop) or extract a small `PhotoLightbox` component (cleaner). Recommendation: extract.

4. **One-time migration toast for the read-only `recomendaciones`** — wording and lifetime (one toast per session vs persisted banner). Recommendation: one toast per session keyed on `operation.id`, dismissed by user.

5. **Auto-upload behavior on rapid re-selection of the same file path** — `input.value` reset pattern. Standard, but spec phase confirms.

## Rollback plan

- The three new endpoints are additive — disable the routes in `api_urls.py` to remove them.
- The `_operation_detail` extension is additive — revert to a single fetch by ignoring the new fields on the frontend.
- The new model `OperacionFoto` is additive — the migration rolls back with `migrate operations zero` (Django auto-generates the reverse).
- The frontend extraction is one new file + one import + one render line in the page — revert by removing the import and the render line.
- The inline editor removal is the only destructive change. If rollback is needed, restore lines 746-798 verbatim from git history along with the removed state (`isEditingDetails`, `detailsForm`, `handleSaveDetails`, `startEditingDetails`). Note: if the user had edited `recomendaciones` between deploy and rollback, that data is preserved in the DB (we never delete the column), so the restored editor reads it back. The legacy endpoint itself is untouched and still works for any other caller.

## Success criteria

- [ ] Admin can edit `Operacion.detalles_op` from a new section at the bottom of `cms/operaciones/<id>` and the change persists.
- [ ] Admin can upload multiple images to "Fotos antes" and "Fotos despues" in one operation; uploads auto-fire on file selection.
- [ ] Admin can delete any single photo from either gallery; the photo disappears from the gallery AND from disk (`media/operaciones/...`).
- [ ] On page reload, the gallery shows all previously-uploaded photos in stable upload-order (oldest first).
- [ ] Uploading one oversized file does NOT fail the other files in the same selection — partial success is reported per file.
- [ ] The new section respects the `Operacion.Estado` lifecycle (editable in `BORRADOR` and `EN_PROCESO`; readonly but visible in `FINALIZADA` and `CANCELADA` — spec phase confirms).
- [ ] The "Cambiar detalles y recomendaciones" button at `AdminOperationDetailPage.tsx:757-759` is gone. The inline detalles form at lines 762-794 and its state are gone. `recomendaciones` is rendered read-only inside the new section.
- [ ] No `Operacion` column is added. `Operacion.detalles_op` is reused; `Operacion.recomendaciones` is unchanged on the model.
- [ ] The legacy `admin_update_operation_details` endpoint remains callable and contract-compatible (kept for backward compatibility; no UI in this change calls it).
- [ ] All 15+ new tests in `test_operation_observations_photos.py` pass. Existing 31+ tests across `test_appointment_close_split`, `test_maquinaria_conflicts`, `test_maquinaria_catalog`, `test_appointment_reservation_extended`, `test_especialista_mis_citas` still pass.
- [ ] `npx tsc -b --noEmit` from `frontend/aesthetic-clinic` introduces no new TypeScript errors.
- [ ] `AdminOperationDetailPage.tsx` net line delta ≤ +50 (extraction to `OperationObservationsSection.tsx` enforces this).