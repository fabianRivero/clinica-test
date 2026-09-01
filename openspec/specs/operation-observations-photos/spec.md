# Delta for admin-operation-observations

## Purpose

This spec adds an "Observaciones del procedimiento" section at the bottom of `cms/operaciones/<id>` so an authenticated admin can read/write `Operacion.detalles_op` and manage a persistent per-operation photo gallery split into "antes" and "después". The section replaces the existing inline detalles/recomendaciones editor and its "Cambiar detalles y recomendaciones" trigger button; `Operacion.recomendaciones` becomes read-only on this page (still visible, not editable here). The gallery embeds in the existing operation-detail payload, persists across reloads, and supports per-photo delete with a confirm dialog. Adds one new Django model (`OperacionFoto`), one new endpoint for the text save (`actualizar-observaciones/`), one multipart upload endpoint (`fotos/<kind>/`), and one delete endpoint (`fotos/<photo_id>/`).

## ADDED Requirements

### Requirement: New "Observaciones del procedimiento" section at the bottom of cms/operaciones/<id>

The admin operation detail page SHALL render a new `<SectionCard title="Observaciones del procedimiento">` AFTER the existing "Citas y cuotas" section card. The section SHALL contain, in order: a read-only "Recomendaciones" block, a `<textarea>` labeled "Observaciones del procedimiento" bound to `Operacion.detalles_op`, a single `Guardar` button, and two photo blocks labeled "Fotos antes del tratamiento" and "Fotos después del tratamiento", each with a multi-file input and a thumbnail gallery. The section SHALL live in `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` and SHALL be mounted via `operation={operation}` and `onReload={reload}` props.

#### Scenario: Section is the last section card

- GIVEN an admin opens `cms/operaciones/<id>` for an `Operacion` with `estado="EN_PROCESO"`
- WHEN the page renders
- THEN the section order SHALL be: "Información principal", "Documento y observaciones", "Citas y cuotas", "Observaciones del procedimiento".

#### Scenario: Net page line delta is bounded

- GIVEN the section is extracted to a sibling component
- WHEN the page mounts the section
- THEN the net line delta of `AdminOperationDetailPage.tsx` SHALL be ≤ +50 (one import + one render + deletions).

---

### Requirement: Read-only "Recomendaciones" block

The new section SHALL render the current value of `Operacion.recomendaciones` as a read-only display block labeled "Recomendaciones". The block SHALL NOT contain any textarea, save button, or input control. When `recomendaciones` is empty, the block SHALL render the existing placeholder text used elsewhere on the page.

#### Scenario: Recomendaciones displays its current value

- GIVEN an `Operacion` with `recomendaciones="Usar protector solar FPS 50 cada 4 horas."`
- WHEN the page renders
- THEN the "Recomendaciones" block SHALL display exactly that text
- AND SHALL NOT render any `<textarea>` or `<input>` for `recomendaciones`.

---

### Requirement: Editable "Observaciones del procedimiento" textarea bound to detalles_op

The new section SHALL render a `<textarea>` labeled "Observaciones del procedimiento" bound to `Operacion.detalles_op`. Clicking `Guardar` SHALL POST `{ "details": "<textarea value>" }` to the new `actualizar-observaciones/` endpoint and SHALL call `onReload()` on success. The endpoint SHALL update `Operacion.detalles_op` only — it SHALL NOT modify `Operacion.recomendaciones` or `Operacion.sesiones_totales`.

#### Scenario: Textarea prepopulates and saves

- GIVEN an `Operacion` with `detalles_op="antiguo"`, `recomendaciones="recom"`, `sesiones_totales=10`
- WHEN the admin edits the textarea to "nuevo" and clicks `Guardar`
- THEN the system SHALL POST `{ "details": "nuevo" }` to `/api/admin/operaciones/<id>/actualizar-observaciones/`
- AND on HTTP 200 the page SHALL call `onReload()`
- AND `Operacion.detalles_op` SHALL be `"nuevo"`
- AND `recomendaciones` SHALL remain `"recom"`
- AND `sesiones_totales` SHALL remain `10`.

#### Scenario: Server validation error shows inline

- GIVEN the server returns HTTP 400 with `{ "errors": { "details": "..." } }`
- WHEN the response arrives
- THEN the textarea SHALL display the inline error
- AND `detalles_op` SHALL NOT be overwritten.

---

### Requirement: Two multi-file photo inputs

The section SHALL render two `<input type="file" multiple accept="image/*">` controls labeled "Fotos antes del tratamiento" and "Fotos después del tratamiento". Selecting files SHALL auto-fire an upload to `/api/admin/operaciones/<id>/fotos/<kind>/` — no separate submit button SHALL be required for photos.

#### Scenario: Input accepts multiple image files

- GIVEN the admin selects `antes-1.jpg`, `antes-2.jpg`, `antes-3.png` under "Fotos antes del tratamiento"
- WHEN the selection is confirmed
- THEN the section SHALL send a multipart POST with each file under the `archivos` field to `/api/admin/operaciones/<id>/fotos/antes/`
- AND each file SHALL be ≤ 5 MB.

---

### Requirement: Photo gallery renders inside the new section

The section SHALL render two thumbnail grids, one per kind. Each thumbnail SHALL show the image and a delete affordance (`×` button). The gallery SHALL be sourced from `operation.fotosAntes` and `operation.fotosDespues` — no additional fetch SHALL be issued on page load.

#### Scenario: Gallery renders from the existing detail payload

- GIVEN `operation.fotosAntes = [{id: 11, url: "/media/operaciones/.../a.jpg", uploadedAt: "2026-08-30T12:00:00Z", fileName: "a.jpg"}]`
- WHEN the page renders
- THEN "Fotos antes del tratamiento" SHALL display one thumbnail for that entry
- AND no additional API call SHALL be issued.

#### Scenario: Empty gallery shows placeholder

- GIVEN the `Operacion` has zero photos
- WHEN the page renders
- THEN each gallery SHALL render an empty-state placeholder ("Sin fotos.")
- AND the file input SHALL remain visible.

---

### Requirement: Per-photo delete with confirm dialog

Each thumbnail SHALL render a delete control that opens a confirm dialog with the exact Spanish copy: title "Eliminar foto", message "¿Eliminar esta foto? Esta accion no se puede deshacer.", tone "warning", buttons "Confirmar" and "Cancelar". On confirm, the section SHALL `DELETE /api/admin/operaciones/<id>/fotos/<photo_id>/` and SHALL call `onReload()` on success. On cancel, no request SHALL be issued.

#### Scenario: Delete requires confirmation

- GIVEN a thumbnail with id `42`
- WHEN the admin clicks its delete control
- THEN the confirm dialog SHALL open with the exact title "Eliminar foto" and message "¿Eliminar esta foto? Esta accion no se puede deshacer."
- AND no API call SHALL be issued until "Confirmar" is clicked.

#### Scenario: Confirmed delete removes the photo and frees disk

- GIVEN `OperacionFoto(42)` with `operacion_id=7` and `imagen` saved under `media/operaciones/.../antes/<file>.jpg`
- WHEN the admin confirms and the server returns HTTP 204
- THEN the row SHALL be deleted
- AND the file SHALL be removed from disk
- AND `onReload()` SHALL refresh the gallery.

#### Scenario: Cancelled delete leaves the gallery unchanged

- WHEN the admin clicks "Cancelar" in the confirm dialog
- THEN no API call SHALL be issued
- AND the gallery SHALL remain unchanged.

---

### Requirement: Section respects the Operacion lifecycle

The section SHALL be editable in `BORRADOR` and `EN_PROCESO` and read-only (textarea disabled, file inputs hidden, delete buttons hidden, gallery thumbnails still shown) in `FINALIZADA` and `CANCELADA`.

#### Scenario: Editable in EN_PROCESO

- GIVEN `estado="EN_PROCESO"`
- WHEN the page renders
- THEN the textarea SHALL be enabled
- AND the file inputs SHALL be visible
- AND delete buttons SHALL be visible on existing thumbnails.

#### Scenario: Read-only in FINALIZADA

- GIVEN `estado="FINALIZADA"`
- WHEN the page renders
- THEN the textarea SHALL be disabled
- AND `Guardar` SHALL NOT render
- AND the file inputs SHALL NOT render
- AND delete buttons SHALL NOT render
- AND the gallery thumbnails SHALL still render read-only.

---

### Requirement: New `actualizar-observaciones/` endpoint

`POST /api/admin/operaciones/<int:operacion_id>/actualizar-observaciones/` SHALL be decorated with `@require_POST`, `@admin_required`, `@transaction.atomic`. Body: JSON `{ "details": string }`. The endpoint SHALL persist `Operacion.detalles_op = details` ONLY (no other field). Returns HTTP 200 with `{ "detail": "...", "operation": <_operation_detail> }`.

#### Scenario: Happy path persists detalles_op

- WHEN an authenticated admin POSTs `{ "details": "nuevo" }` to `/api/admin/operaciones/7/actualizar-observaciones/`
- THEN the server SHALL return HTTP 200 with `{ "detail": "...", "operation": <payload> }`
- AND `Operacion(7).detalles_op` SHALL be `"nuevo"`
- AND `recomendaciones` and `sesiones_totales` SHALL be unchanged.

#### Scenario: Missing details returns 400

- WHEN an authenticated admin POSTs `{}`
- THEN the server SHALL return HTTP 400 with `{ "detail": "Datos invalidos.", "errors": { "details": "..." } }`.

#### Scenario: Nonexistent operacion returns 404

- WHEN an authenticated admin POSTs to `/api/admin/operaciones/9999/actualizar-observaciones/`
- THEN the server SHALL return HTTP 404.

---

### Requirement: New multipart upload endpoint

`POST /api/admin/operaciones/<int:operacion_id>/fotos/<str:kind>/` SHALL be decorated with `@require_POST`, `@admin_required`, `@transaction.atomic`. `kind` SHALL be one of `{ "antes", "despues" }`. Body: `multipart/form-data` with field `archivos` repeated per file (each ≤ 5 MB, `image/*`). Each file SHALL be validated independently — per-file failures SHALL NOT abort successful siblings.

Responses:
- **HTTP 201** when at least one file is saved: `{ "detail": "Fotos guardadas.", "saved": [{id, url, uploadedAt, fileName}], "errors": {}, "operation": <_operation_detail> }`.
- **HTTP 400** when zero files saved: `{ "detail": "Datos invalidos.", "errors": { "archivos[i]": "..." } }`.
- **HTTP 400** when `archivos` is missing or `kind` is invalid.

#### Scenario: Single valid upload persists and returns

- WHEN an authenticated admin POSTs multipart with `kind=antes` and one `archivos` entry `antes-1.jpg` (3 MB, JPEG)
- THEN the server SHALL return HTTP 201
- AND the file SHALL be saved under `media/operaciones/<yyyy>/<mm>/<dd>/antes/`
- AND an `OperacionFoto` row SHALL be persisted with `operacion_id=<id>`, `kind="antes"`
- AND `saved` SHALL contain one entry with `id`, `url`, `uploadedAt`, `fileName="antes-1.jpg"`.

#### Scenario: Partial success — one file too large

- GIVEN three files: `a.jpg` (2 MB), `b.jpg` (7 MB), `c.png` (1 MB)
- WHEN the admin POSTs with `kind=despues`
- THEN the server SHALL return HTTP 201
- AND `saved` SHALL contain entries for `a.jpg` and `c.png`
- AND `errors` SHALL contain `{ "archivos[1]": "La imagen no puede superar los 5 MB (tamano actual: 7340032 bytes)." }`
- AND no row SHALL exist for `b.jpg`.

#### Scenario: Invalid kind returns 400

- WHEN the admin POSTs with `kind="laterales"`
- THEN the server SHALL return HTTP 400 with `errors.kind` set.

---

### Requirement: New delete endpoint

`DELETE /api/admin/operaciones/<int:operacion_id>/fotos/<int:photo_id>/` SHALL be decorated with `@require_http_methods(["DELETE"])`, `@admin_required`, `@transaction.atomic`. SHALL remove the matching `OperacionFoto` row AND call `instance.imagen.delete(save=False)` to remove the file from disk. Returns HTTP 204 on success; HTTP 404 if the photo does not exist OR belongs to a different `operacion_id` (no cross-operation existence leak).

#### Scenario: Delete existing photo returns 204

- GIVEN `OperacionFoto(42)` with `operacion_id=7`
- WHEN the admin DELETEs `/api/admin/operaciones/7/fotos/42/`
- THEN the server SHALL return HTTP 204
- AND the row SHALL be deleted
- AND the file SHALL be removed from disk.

#### Scenario: Cross-operation delete returns 404

- GIVEN `OperacionFoto(42)` belongs to `Operacion(7)`
- WHEN the admin DELETEs `/api/admin/operaciones/8/fotos/42/`
- THEN the server SHALL return HTTP 404
- AND `OperacionFoto(42)` SHALL still exist.

---

### Requirement: Gallery embedded in `_operation_detail` payload

`_operation_detail(operacion)` SHALL add two new keys: `fotosAntes: [{id, url, uploadedAt, fileName}]` and `fotosDespues: [{id, url, uploadedAt, fileName}]`. Both arrays SHALL be ordered by `uploaded_at ASC, id ASC`. `url` SHALL be a fully-qualified absolute URL built from `request.build_absolute_uri(photo.imagen.url)`. The `Operacion` queryset SHALL include `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))` so the gallery is a single query (no N+1).

#### Scenario: Detail payload includes ordered arrays

- GIVEN an `Operacion` has three `OperacionFoto` rows with `kind="antes"` (uploaded at t1, t2, t3) and two with `kind="despues"` (uploaded at t4, t5)
- WHEN an authenticated admin GETs `/api/admin/operaciones/<id>/`
- THEN `operation.fotosAntes` SHALL contain three entries in uploaded-at ASC order
- AND `operation.fotosDespues` SHALL contain two entries in uploaded-at ASC order
- AND each entry SHALL have `id` (number), `url` (absolute URL), `uploadedAt` (ISO 8601 string), `fileName` (string).

---

### Requirement: OperacionFoto data model

A new `OperacionFoto` model SHALL live in `backend/operations/models.py`:

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | `AutoField` (implicit) | Primary key |
| `operacion` | `ForeignKey("operations.Operacion", on_delete=CASCADE, related_name="fotos_operacion")` | Required |
| `kind` | `CharField(max_length=10, choices=[("antes", "Antes"), ("despues", "Despues")])` | Required |
| `imagen` | `ImageField(upload_to="operaciones/%Y/%m/%d/<kind>/")` | Required. 5 MB cap enforced at the endpoint layer |
| `uploaded_at` | `DateTimeField(auto_now_add=True, db_index=True)` | Set on insert |

`Meta` SHALL set `db_table = "operaciones_fotos"`, `ordering = ("uploaded_at", "id")`, and `indexes = [Index(fields=["operacion", "kind", "uploaded_at", "id"])]`. The model SHALL NOT define an `updated_at` field.

#### Scenario: Model persists with auto fields

- WHEN the endpoint persists a new `OperacionFoto` with `operacion_id=7`, `kind="antes"`, `imagen=<file>`
- THEN the row SHALL be created with `id` (auto), `uploaded_at` set to the current time, and no `updated_at` column
- AND the file SHALL live at `media/operaciones/<yyyy>/<mm>/<dd>/antes/`.

#### Scenario: Cascading delete on Operacion

- GIVEN `Operacion(7)` has 3 `OperacionFoto` rows
- WHEN `Operacion(7).delete()` is called
- THEN the 3 `OperacionFoto` rows SHALL be deleted (CASCADE).

---

### Requirement: 5 MB per-file cap

The upload endpoint SHALL reject any file whose size exceeds `5 * 1024 * 1024` bytes (5 MB). The constant SHALL match the per-cita `MAX_IMAGE_BYTES` value at `backend/config/api_views.py:3641`. Per-file failures SHALL be reported as `errors["archivos[i]"]` so the admin can retry only the failing files.

#### Scenario: Cap constant matches existing convention

- GIVEN the new endpoint defines `MAX_IMAGE_BYTES = 5 * 1024 * 1024`
- WHEN compared with the per-cita endpoint's `MAX_IMAGE_BYTES`
- THEN both constants SHALL equal `5242880`.

---

### Requirement: Single page-load fetch

The admin operation detail page SHALL render the new section using ONLY the data returned by the existing `GET /api/admin/operaciones/<id>/`. No additional fetch SHALL be triggered by the new section on initial render, page reload, or navigation back.

#### Scenario: No extra gallery fetch on mount

- GIVEN the page receives the detail payload including `fotosAntes` and `fotosDespues`
- WHEN the section mounts
- THEN no `fetch`/`axios`/`requestJson*`/`requestFormData*` call SHALL be issued for gallery data.

---

## REMOVED Requirements

### Requirement: Inline editor for `Operacion.detalles_op` and `Operacion.recomendaciones`

The system SHALL NOT render the inline detalles/recomendaciones editor (previously at `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx:762-794`) on `cms/operaciones/<id>`. The system SHALL NOT render the "Cambiar detalles y recomendaciones" trigger button (previously at `AdminOperationDetailPage.tsx:757-759`). The system SHALL NOT render a textarea or save control for `Operacion.recomendaciones` anywhere on this page.

(Reason: the new section is the single edit surface for `detalles_op`, and `recomendaciones` is intentionally demoted to read-only to eliminate the clobber risk between two editors sharing the legacy `actualizar-detalles/` endpoint and to keep the section focused on `detalles_op`.)

(Migration: the read-only "Recomendaciones" block inside the new section preserves visibility. The legacy `POST /api/admin/operaciones/<id>/actualizar-detalles/` endpoint is kept on the server for backward compatibility — no UI in this change calls it, but admin scripts or future re-wirings can still mutate `recomendaciones` and `sesiones_totales`. The `Operacion.recomendaciones` column is unchanged; no data is deleted. The new `actualizar-observaciones/` endpoint writes `detalles_op` only via `update_fields=["detalles_op", "updated_at"]`. The removed React state — `isEditingDetails`, `detailsForm`, `handleSaveDetails`, `startEditingDetails`, cancel/edit-toggle handlers — has no consumer outside the deleted editor.)

---

## RENAMED Requirements

### Requirement: `Admin can edit operation details and recommendations inline` → `Admin can edit operation details via the Observaciones del procedimiento section and view recommendations read-only`

(Reason: the edit surface for `Operacion.detalles_op` moves from an inline form inside "Información principal" to a dedicated section at the bottom. The field being edited is unchanged. The recommendation editor is removed; the value is now read-only.)

(Migration: any test asserting the "Cambiar detalles y recomendaciones" button MUST be updated to assert its absence. Any test asserting inline textarea labels "Detalles de la operación" / "Recomendaciones" (edit mode) MUST be updated to assert the new "Observaciones del procedimiento" textarea label and the read-only "Recomendaciones" block. The legacy `actualizar-detalles/` endpoint contract is unchanged; no consumer test for that endpoint needs migration.)

---

## Compatibility

- `GET /api/admin/operaciones/<id>/` payload gains `fotosAntes` / `fotosDespues`. Strictly-typed consumers (`OperationDetailResponse` in `frontend/aesthetic-clinic/src/types/admin.ts`) MUST be updated.
- `POST /api/admin/operaciones/<id>/actualizar-detalles/` is UNCHANGED. The handler at `backend/config/api_views.py:4521` remains; no UI in this change calls it.
- `POST /api/admin/citas/<id>/notas/` is UNCHANGED. Per-cita photos are a separate concern and MUST NOT appear in the new gallery.
- The lifecycle rule (editable in `BORRADOR` / `EN_PROCESO`, read-only in `FINALIZADA` / `CANCELADA`) does NOT apply to the per-cita close-time photo flow.

## Reference

- Proposal: `openspec/changes/operation-observations-photos/proposal.md`
- Explore: `openspec/changes/operation-observations-photos/explore.md`
- Per-cita photo endpoint pattern: `backend/config/api_views.py:3582-3666`
- Per-operation endpoint pattern: `backend/config/api_views.py:4491-4573`
- Detail helper: `_operation_detail(operacion)` at `backend/config/api_views.py:403-551`
