# Design: Operation Observations Photos

## Overview

This document is the technical architecture for adding an "Observaciones del procedimiento" section at the bottom of `cms/operaciones/<id>` that edits `Operacion.detalles_op` and manages a persistent per-operation before/after photo gallery. It bridges the proposal and the spec by spelling out the concrete backend model, endpoint contracts, frontend component shape, and the deletion sequence that locks the spec.

The change **replaces** the existing inline detalles/recomendaciones editor at `AdminOperationDetailPage.tsx:746-794` (and its trigger button at lines 757-759), demotes `recomendaciones` to read-only on this page, and adds a new sibling component `OperationObservationsSection.tsx` to keep `AdminOperationDetailPage.tsx` within the 1664-line envelope.

## Architecture decisions

| # | Decision | Rationale |
| --- | --- | --- |
| AD1 | New model `OperacionFoto` is added to `backend/operations/models.py` next to `Operacion` / `CitaMedica`. No extraction to a separate `photos.py`. | Same-file cohesion with the existing FK target and `CitaMedica.foto_antes` pattern. File is 719 lines today; one ~40-line model is in-family. |
| AD2 | `OperacionFoto` inherits from `models.Model` directly, **not** from `TimeStampedModel`. | The spec (`specs/operation-observations-photos/spec.md:250,255`) explicitly mandates "SHALL NOT define an `updated_at` field" and "no `updated_at` column". `TimeStampedModel` would inject `updated_at` (`common/models.py:6`), which contradicts the spec. The proposal example is overridden by the spec — see Contradiction callout below. |
| AD3 | `imagen.upload_to` uses a **callable** that returns `f"operaciones/{now:%Y/%m/%d}/{instance.kind}/"` (interpolated from `instance`). | The `kind` is per-row, not per-model, so a static `upload_to=".../<kind>/..."` cannot work (Django's `upload_to` is a Python format string applied to the **current datetime**, not the model instance). The callable is invoked by `FieldFile.save()` after the row's PK exists; the FK to `operacion` is set on the instance before `save()`, so `instance.kind` is available. |
| AD4 | Original filename is preserved with a UUID4 prefix on collision. | Filenames from a multi-file picker can repeat (`foto.jpg` picked twice). Pure-original keeps the admin's intent; the UUID prefix is invisible in the gallery (the API exposes `fileName` separately, mapped to `imagen.name`'s basename) and prevents name collisions on disk. |
| AD5 | Disk cleanup on delete lives in the endpoint (`instance.imagen.delete(save=False)` before `instance.delete()`), not in a model signal. | The endpoint owns the side effect. A `post_delete` signal would couple model lifecycle to storage behaviour; a non-storage delete (e.g. from a management command) would also delete the file unintentionally. Endpoints are the natural seam. |
| AD6 | `_operation_detail(operacion)` grows an optional `request=None` parameter; the gallery URLs are built with `request.build_absolute_uri(photo.imagen.url)` when `request` is provided. | The function is called from 8 sites today (`api_views.py:403, 3859, 4062, 4323, 4518, 4573, 4954, 5089`); threading `request` through every call site is a large refactor for a feature whose only consumer is the new section. Optional parameter keeps the existing call sites byte-identical. When the request is omitted, the gallery returns relative URLs — harmless for the consumers that don't render the gallery. |
| AD7 | `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))` is added inside the existing `_operation_detail`-feeding queryset (both `admin_operacion_detalle` at `api_views.py:4494-4513` and the post-write re-query at `api_views.py:4554-4571`). | One extra query, no N+1. The compound index on `(operacion, kind, uploaded_at, id)` (spec line 250) makes the ordering index-only. |
| AD8 | The new text-save endpoint `actualizar-observaciones/` is **brand-new**; the existing `actualizar-detalles/` endpoint stays on the server (no UI caller) per spec line 298. | The existing endpoint at `api_views.py:4521` writes `detalles_op`, `recomendaciones`, AND `sesiones_totales` unconditionally (lines 4548-4551). Wiring the new section to it would clobber the other two fields on every textarea save. A dedicated endpoint with `update_fields=["detalles_op"]` (no `updated_at` since the model has none — see AD2) is the only safe option. |
| AD9 | The new section's lifecycle prop is `editable`, derived in `AdminOperationDetailPage` from `["borrador", "en proceso"].includes(operation.status.toLowerCase())`. | The spec (lines 124-144) requires editable in `BORRADOR` AND `EN_PROCESO`. The existing `canEditPricePlan` at line 592 only matches `en proceso` and is therefore too narrow; the new prop is computed independently. |
| AD10 | `requestDelete` already exists in `apiClient.ts:214` and is already imported in `admin.ts:80`. The new `deleteAdminOperationPhoto` calls it. | Reuse, no new helper. |
| AD11 | Multipart upload uses `requestFormDataWithBody` (admin.ts:78) with a `FormData` whose `archivos` key is repeated per file. The server reads via `request.FILES.getlist("archivos")`. | Identical to the per-cita `patchAppointmentNotes` pattern (`admin.ts:290-308`). |

## Contradiction surface

The proposal (`proposal.md:228-249`) gives an `OperacionFoto(TimeStampedModel)` code sample that would inject `updated_at`. The spec (`spec.md:250, 255`) explicitly forbids `updated_at`. The spec is the binding contract — AD2 follows the spec and the migration will create a model **without** `created_at`/`updated_at` columns. If the model needs `created_at` semantics later, an additive migration can add it.

## Data model

### New model `OperacionFoto` (in `backend/operations/models.py`)

Append after `CitaMedica` (line 217), before `class PlantillaProcedimiento`. The model is **not** an abstract subclass.

```python
class OperacionFoto(models.Model):
    class Kind(models.TextChoices):
        ANTES = "antes", "Antes"
        DESPUES = "despues", "Despues"

    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="fotos_operacion",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    imagen = models.ImageField(upload_to=_operacion_foto_upload_to)
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "operaciones_fotos"
        ordering = ("uploaded_at", "id")
        indexes = [
            models.Index(fields=["operacion", "kind", "uploaded_at", "id"]),
        ]


def _operacion_foto_upload_to(instance: "OperacionFoto", filename: str) -> str:
    """Callable upload_to for OperacionFoto.imagen.

    Returns ``operaciones/<YYYY>/<MM>/<DD>/<kind>/<uuid-prefix>-<filename>``
    so that same-day uploads do not collide and the path stays organised by
    date AND kind. Django invokes this once per save, after the row's PK
    exists; the FK is set by the endpoint before ``save()``, so
    ``instance.kind`` is available.
    """
    stamp = timezone.now().strftime("%Y/%m/%d")
    prefix = uuid.uuid4().hex[:12]
    return f"operaciones/{stamp}/{instance.kind}/{prefix}-{filename}"
```

Field-by-field contract (per spec line 244-249):

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | implicit `BigAutoField` | Primary key |
| `operacion` | `ForeignKey("operations.Operacion", on_delete=CASCADE, related_name="fotos_operacion")` | Required |
| `kind` | `CharField(max_length=10, choices=Kind.choices)` | Required. Choices: `"antes"`, `"despues"` |
| `imagen` | `ImageField(upload_to=_operacion_foto_upload_to)` | Required. 5 MB cap enforced at the endpoint layer |
| `uploaded_at` | `DateTimeField(auto_now_add=True, db_index=True)` | Set on insert. No `updated_at` per AD2 |

`Meta` per spec line 250: `db_table = "operaciones_fotos"`, `ordering = ("uploaded_at", "id")`, `indexes = [Index(fields=["operacion", "kind", "uploaded_at", "id"])]`.

### Imports to add at the top of `models.py`

```python
import uuid
```

`timezone` is already imported (line 7). No new third-party dependency.

### Unchanged

- `Operacion.detalles_op` (line 55) — reused; no new column.
- `Operacion.recomendaciones` (line 56) — read-only on the page; column unchanged.
- `CitaMedica.foto_antes` / `foto_despues` (lines 207-216) — separate per-cita concern; untouched.

### Django admin registration

Append to `backend/operations/admin.py`:

```python
from operations.models import OperacionFoto  # add to the import block


@admin.register(OperacionFoto)
class OperacionFotoAdmin(admin.ModelAdmin):
    list_display = ("id", "operacion", "kind", "uploaded_at")
    list_filter = ("kind",)
    search_fields = ("operacion__paciente__usuario__primer_nombre",)
```

House style: every concrete model is registered in the project's Django admin.

## Migration

One new auto-generated migration under `backend/operations/migrations/`. Expected shape:

- **Filename**: `0027_operacionfoto.py` (auto-numbered — the existing sequence ends at `0026_citamedica_descripcion_general_and_more.py`).
- **Dependencies**: `('operations', '0026_citamedica_descripcion_general_and_more.py')` plus whatever Django determines for the FK targets (none — `Operacion` is in the same app).
- **Operations**: a single `migrations.CreateModel(...)` with the four fields and the Meta block above. The `upload_to` is stored as the dotted path of the callable (`operations.models._operacion_foto_upload_to`).

No data migration; `Operacion.detalles_op` is unchanged.

## API surface

### Endpoint changes

| Method + Path | Current state | New state |
| --- | --- | --- |
| `GET /api/admin/operaciones/<id>/` | `{operation: _operation_detail(operacion)}` | Adds `operation.fotosAntes` and `operation.fotosDespues` arrays. Threading `request` into `_operation_detail` so URLs are absolute. |
| `POST /api/admin/operaciones/<id>/actualizar-detalles/` | Updates detalles_op + recomendaciones + sesiones_totales | **Unchanged** — kept for backward compatibility (no UI caller in this change). |
| `POST /api/admin/citas/<id>/notas/` | Multipart PATCH | **Unchanged.** Per-cita gallery is a separate concern. |

### New endpoint: `admin_update_operation_observaciones`

Decorators and shape mirror `admin_update_operation_details` at `api_views.py:4521-4573`, but the persist step is narrower.

```python
@require_POST
@admin_required
@transaction.atomic
def admin_update_operation_observaciones(request, operacion_id):
    payload = load_payload(request)
    if payload is None:
        return json_response(
            {"detail": "El cuerpo de la solicitud no es JSON valido."},
            status=400,
        )

    if "details" not in payload:
        return json_response(
            {
                "detail": "Datos invalidos.",
                "errors": {"details": "Debes enviar el campo details."},
            },
            status=400,
        )

    operacion = (
        Operacion.objects.select_for_update(of=("self",))
        .filter(pk=operacion_id)
        .first()
    )
    if not operacion:
        return json_response(
            {"detail": "No encontramos la operacion solicitada."},
            status=404,
        )

    operacion.detalles_op = (payload.get("details") or "").strip()
    operacion.save(update_fields=["detalles_op"])
    # Re-fetch with prefetches so _operation_detail returns the full payload.
    operacion = _operation_detail_queryset().get(pk=operacion.pk)

    return json_response({
        "detail": "Las observaciones fueron actualizadas correctamente.",
        "operation": _operation_detail(operacion, request=request),
    })
```

Key contract points:

- `update_fields=["detalles_op"]` is intentional. Per AD2 the model has no `updated_at`, so adding it here would crash with `FieldDoesNotExist`. The spec (line 298) text about `["detalles_op", "updated_at"]` is also overridden by AD2 — only `detalles_op` is updated.
- `recomendaciones` and `sesiones_totales` are NOT touched. The spec (line 42) and proposal (Decision 6.1) lock this.
- The `select_for_update` row lock mirrors the legacy endpoint to prevent concurrent textarea saves racing.
- After save, we re-query through the same queryset helper used by `admin_operacion_detalle` (see below) so `fotos_antes` / `fotos_despues` reflect the new state without a second round-trip.

### New endpoint: `admin_upload_operation_photos`

Reference patterns:

- Multipart parse + per-file image cap: `admin_update_appointment_notes` at `api_views.py:3582-3666` (especially `MAX_IMAGE_BYTES = 5 * 1024 * 1024` at line 3641).
- Atomic write returning the canonical detail: `admin_cerrar_cita` (same module).

```python
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@require_POST
@admin_required
@transaction.atomic
def admin_upload_operation_photos(request, operacion_id, kind):
    if kind not in {"antes", "despues"}:
        return json_response(
            {
                "detail": "Datos invalidos.",
                "errors": {"kind": "Solo se permiten los valores 'antes' o 'despues'."},
            },
            status=400,
        )

    operacion = Operacion.objects.filter(pk=operacion_id).first()
    if not operacion:
        return json_response(
            {"detail": "No encontramos la operacion solicitada."},
            status=404,
        )

    files = request.FILES.getlist("archivos")
    if not files:
        return json_response(
            {
                "detail": "Datos invalidos.",
                "errors": {"archivos": "Debes adjuntar al menos una imagen."},
            },
            status=400,
        )

    saved_payload = []
    errors = {}

    for index, upload in enumerate(files):
        if upload.size > MAX_IMAGE_BYTES:
            errors[f"archivos[{index}]"] = (
                f"La imagen no puede superar los 5 MB "
                f"(tamano actual: {upload.size} bytes)."
            )
            continue
        foto = OperacionFoto.objects.create(
            operacion=operacion,
            kind=kind,
            imagen=upload,
        )
        saved_payload.append({
            "id": foto.pk,
            "url": request.build_absolute_uri(foto.imagen.url),
            "uploadedAt": foto.uploaded_at.isoformat(),
            "fileName": os.path.basename(foto.imagen.name),
        })

    if not saved_payload:
        return json_response(
            {"detail": "Datos invalidos.", "errors": errors}, status=400,
        )

    operacion = _operation_detail_queryset().get(pk=operacion.pk)
    detail_msg = (
        "Fotos guardadas." if not errors
        else "Algunas fotos no pudieron subirse."
    )
    return json_response(
        {
            "detail": detail_msg,
            "saved": saved_payload,
            "errors": errors,
            "operation": _operation_detail(operacion, request=request),
        },
        status=201,
    )
```

Contract per spec lines 174-200:

- **201** when at least one file saved (partial success tolerated).
- **400** when zero files saved (all invalid) OR `kind` invalid OR `archivos` missing.
- Per-file validation; failures in one file do not abort siblings.
- The `saved` array carries `{id, url, uploadedAt, fileName}` matching the spec shape.
- `os.path.basename(foto.imagen.name)` strips the `<uuid-prefix>-` so `fileName` is what the admin picked on disk.
- `MAX_IMAGE_BYTES` constant lives at module scope so a future change touches both this endpoint and `admin_update_appointment_notes` together.

### New endpoint: `admin_delete_operation_photo`

```python
@require_http_methods(["DELETE"])
@admin_required
@transaction.atomic
def admin_delete_operation_photo(request, operacion_id, photo_id):
    foto = (
        OperacionFoto.objects
        .select_related("operacion")
        .filter(pk=photo_id, operacion_id=operacion_id)
        .first()
    )
    if not foto:
        # The photo either doesn't exist OR belongs to another operation.
        # Return 404 in both cases — don't leak cross-operation existence.
        return json_response(
            {"detail": "No encontramos la foto solicitada."},
            status=404,
        )

    # Endpoint owns the side effect (AD5).
    foto.imagen.delete(save=False)
    foto.delete()
    return json_response({}, status=204)
```

Notes:

- The 404 case covers BOTH "no row at all" AND "row exists but belongs to a different operation" (spec line 205).
- `foto.imagen.delete(save=False)` removes the file from `MEDIA_ROOT` without re-saving the model.
- The endpoint never returns the deleted `OperacionFoto` in the response body (204 has no body); the frontend triggers `onReload()` to re-fetch the detail payload.

### `_operation_detail` extension

Add a new optional parameter to the function signature at `api_views.py:403`:

```python
def _operation_detail(operacion, request=None):
    ...
    # Existing dict literal stays exactly the same up to the
    # 'appointments' / 'quotas' blocks. Append after them:

    def _photo_to_payload(foto):
        url = (
            request.build_absolute_uri(foto.imagen.url)
            if request is not None
            else foto.imagen.url
        )
        return {
            "id": foto.pk,
            "url": url,
            "uploadedAt": foto.uploaded_at.isoformat(),
            "fileName": os.path.basename(foto.imagen.name),
        }

    fotos_antes = [
        _photo_to_payload(f)
        for f in operacion.fotos_operacion.all() if f.kind == "antes"
    ]
    fotos_despues = [
        _photo_to_payload(f)
        for f in operacion.fotos_operacion.all() if f.kind == "despues"
    ]

    return {
        ...
        # Existing keys unchanged. Append at the end:
        "fotosAntes": fotos_antes,
        "fotosDespues": fotos_despues,
    }
```

Threading `request` into the 8 call sites: only the 4 that serve admin UI with photo rendering need it. The other 4 (cita-close re-renders inside `_client_appointment_item`-style returns) currently do not display the gallery and therefore keep the default `request=None`. The apply phase must update these four sites (per proposal line 277):

- `api_views.py:4518` (`admin_operacion_detalle`) — pass `request=request`.
- `api_views.py:4573` (`admin_update_operation_details`) — pass `request=request`. Also note this endpoint stays unchanged semantically, but its 200 response now embeds the gallery.
- `api_views.py:4954` and `api_views.py:5089` — pass `request=request` if these render `operation` in admin responses (verify during apply).
- `api_views.py:3859`, `:4062`, `:4323` — these are inside cita-side handlers. The `operation` payload they return is for the admin's operation detail view. Pass `request=request` to all of them; the gallery is now always populated.

### Queryset helper to avoid duplication

Both `admin_operacion_detalle` (line 4494-4513) and the new `admin_update_operation_observaciones` re-query the `Operacion` with the same prefetches. Add a small private helper above `admin_operacion_detalle`:

```python
def _operation_detail_queryset():
    return Operacion.objects.select_related(
        "paciente__usuario",
        "servicio_config__tipo_servicio",
        "servicio_config__proc_estetico__tipo_p_estetico",
        "ficha_clinica",
    ).prefetch_related(
        Prefetch(
            "citas_medicas",
            queryset=CitaMedica.objects.select_related().order_by("fecha_hora"),
        ),
        Prefetch(
            "cuotas_plan_pagos",
            queryset=CuotaPlanPago.objects.prefetch_related("pagos_realizados").order_by("nro_cuota"),
        ),
        # NEW — gallery is a single query, ordered by upload time (AD7).
        Prefetch(
            "fotos_operacion",
            queryset=OperacionFoto.objects.order_by("uploaded_at", "id"),
        ),
    )
```

The existing inline `Operacion.objects.select_related(...).prefetch_related(...)` literals at `api_views.py:4494-4510` and `api_views.py:4554-4569` are replaced with `_operation_detail_queryset()`. No behaviour change beyond the new prefetch.

### Permission model

| Role | actualizar-observaciones | upload fotos | delete foto |
| --- | --- | --- | --- |
| Admin principal | Yes | Yes | Yes |
| Admin de sucursal | Yes (own branch scope via `admin_required`) | Yes | Yes |
| Specialist | No | No | No |
| Cliente | No | No | No |

`@admin_required` (defined at `api_helpers.py:47`) is the only guard; no extra scope checks beyond the existing branch-active check. The `operacion_id` URL argument is canonical — no cross-operation leakage (the delete endpoint enforces this in the queryset filter).

### URL routing

In `backend/config/api_urls.py` immediately after the existing `actualizar-detalles/` route (line 281-285):

```python
    path(
        "operaciones/<int:operacion_id>/actualizar-observaciones/",
        admin_update_operation_observaciones,
        name="admin-operation-update-observaciones-api",
    ),
    path(
        "operaciones/<int:operacion_id>/fotos/<str:kind>/",
        admin_upload_operation_photos,
        name="admin-operation-upload-photos-api",
    ),
    path(
        "operaciones/<int:operacion_id>/fotos/<int:photo_id>/",
        admin_delete_operation_photo,
        name="admin-operation-delete-photo-api",
    ),
```

The `<str:kind>` converter accepts `antes` / `despues`. The endpoint itself rejects other values with 400 (so the URL still matches `laterales`, but the body returns a clean error).

## Frontend changes

### New component: `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx`

House style: matches `AppointmentNotesPanel.tsx` (sibling, 249 lines) and `CerrarCitaModal.tsx` (sibling, modal). This component is **not** a modal — it is rendered inline inside a `<SectionCard>` that the **page** owns, so the section header and description stay consistent with "Información principal", "Documento y observaciones", "Citas y cuotas".

**Component prop shape:**

```ts
interface OperacionPhoto {
  id: number
  url: string  // absolute URL, ready for <img src>
  uploadedAt: string  // ISO 8601
  fileName: string
}

interface OperationObservationsSectionProps {
  operacion: OperationDetailData  // the same object AdminOperationDetailPage already has
  editable: boolean  // true for BORRADOR + EN_PROCESO (AD9)
  onSaved: () => void  // called after a successful guardar or photo op; reloads the detail
}
```

`onSaved` is the same callback the existing `handleSaveSessions` (line 263) calls after `reload()` — the page passes `() => reload()` directly. Three separate callbacks for the three action types were listed in the brief; we collapse to one because every success path calls `reload()` (the API responses embed the new payload, but `reload()` keeps the page consistent with other sections that re-fetch). If the apply phase finds a need to differentiate (e.g. for toast text), split into three callbacks then.

**Local state:**

```ts
const [detailsText, setDetailsText] = useState(...)
const [saving, setSaving] = useState(false)
const [uploading, setUploading] = useState<Record<"antes" | "despues", boolean>>({
  antes: false,
  despues: false,
})
const [photos, setPhotos] = useState<{
  antes: OperacionPhoto[]
  despues: OperacionPhoto[]
}>({ antes: [], despues: [] })
const [deletingId, setDeletingId] = useState<number | null>(null)
```

**Effect:** when `operacion.rawId` changes (navigation to a different operation), reset `detailsText` from `operacion.detallesOperacion` (treating the placeholder string `"Sin detalles registrados."` as empty). Initial state populated on mount via `useState(() => initFromOperacion(operacion))` — no `useEffect`, to avoid the lint warning the codebase already enforces.

**Textarea save flow:**

1. User edits `detailsText`.
2. Clicks `Guardar` → `saving=true`, await `updateAdminOperationObservaciones(operacion.rawId, { details: detailsText })`.
3. On success: `showNotification({ kind: 'success', message: 'Observaciones guardadas.' })`, `onSaved()`.
4. On `ApiError.fieldErrors.details`: surface inline under the textarea (do NOT overwrite `detailsText`).

**Photo upload flow (auto-fire on file select, per spec line 66):**

1. User picks files under "Fotos antes" → `<input type="file" multiple accept="image/*" onChange={...}>`.
2. `Array.from(event.target.files ?? [])` → build `FormData`, append each file under `archivos` (per spec line 71).
3. `setUploading({ ...uploading, antes: true })`, call `uploadAdminOperationPhotos(operacion.rawId, files, 'antes')`.
4. Optimistically merge response `saved[]` into `photos.antes` (so the gallery updates immediately, no flicker).
5. On partial errors, surface inline: `"<archivos[1]>: La imagen no puede superar los 5 MB"`.
6. Reset `event.target.value = ''` so the same file can be re-picked after an error (standard pattern, see `SpecialistMessagesPage.tsx:43,85`).
7. Final step: `onSaved()` (the API response already includes the updated `operation` payload, but `reload()` keeps `AdminOperationDetailPage` in sync).

Sequential vs parallel uploads: the apply phase picks **sequential** (proposal open question #2). For-loop over the FileList, one POST per file. The total round-trip is bounded by the size of a typical photo selection (3-5 files), so the latency cost is negligible and the error reporting stays per-file with no interleaving.

**Photo delete flow:**

1. User clicks `×` on a thumbnail → `confirm({ title: 'Eliminar foto', message: '¿Eliminar esta foto? Esta accion no se puede deshacer.', tone: 'warning' })` via `useConfirmDialog()`.
2. On cancel: no API call, gallery unchanged.
3. On confirm: `setDeletingId(photo.id)`, call `deleteAdminOperationPhoto(operacion.rawId, photo.id)`.
4. On success: optimistically remove the photo from `photos.antes` or `photos.despues`, `showNotification({ kind: 'success', message: 'Foto eliminada.' })`, `onSaved()`.
5. On error: surface via notification, leave the gallery unchanged.

**Read-only mode (when `editable === false`):**

- `<textarea>` renders `disabled`.
- `Guardar` button does not render.
- `<input type="file">` does not render.
- Each thumbnail renders WITHOUT the `×` button.
- The gallery still renders (read-only thumbnails) per spec line 144.

**Empty-state placeholder:** when `photos.antes.length === 0`, render `<p className="field__hint">Sin fotos.</p>` above the file input (spec line 91).

### API client additions — `frontend/aesthetic-clinic/src/services/api/admin.ts`

Add three new functions and two new types. Imports already present in `admin.ts`:

```ts
import { requestJson, requestJsonWithBody, requestFormDataWithBody, requestDelete }
  from './apiClient'  // lines 75-81
```

New functions:

```ts
export function updateAdminOperationObservaciones(
  operacionId: number,
  payload: { details: string },
) {
  return requestJsonWithBody<UpdateAdminOperationObservacionesResponse>(
    `/api/admin/operaciones/${operacionId}/actualizar-observaciones/`,
    payload,
  )
}

export function uploadAdminOperationPhotos(
  operacionId: number,
  files: File[],
  kind: 'antes' | 'despues',
) {
  const formData = new FormData()
  files.forEach((file) => formData.append('archivos', file))
  return requestFormDataWithBody<UploadAdminOperationPhotosResponse>(
    `/api/admin/operaciones/${operacionId}/fotos/${kind}/`,
    formData,
  )
}

export function deleteAdminOperationPhoto(operacionId: number, photoId: number) {
  return requestDelete(
    `/api/admin/operaciones/${operacionId}/fotos/${photoId}/`,
  )
}
```

`requestDelete` is already imported (line 80) and used at line 1171 — pure reuse, no new helper.

### Type additions — `frontend/aesthetic-clinic/src/types/admin.ts`

Add at the bottom of the file (or alongside `OperationDetailData` at line 478):

```ts
export type OperacionFoto = {
  id: number
  url: string  // absolute URL
  uploadedAt: string  // ISO 8601
  fileName: string
}

export type OperationDetailData = {
  ...existing fields...
  fotosAntes: OperacionFoto[]
  fotosDespues: OperacionFoto[]
}

export type UpdateAdminOperationObservacionesResponse = {
  detail: string
  operation: OperationDetailData
}

export type UploadAdminOperationPhotosResponse = {
  detail: string
  saved: OperacionFoto[]
  errors: Record<string, string>
  operation: OperationDetailData
}
```

`OperationDetailData` is at line ~458 (find via grep; the brief shows the file's actual lines 480-506). Append `fotosAntes` and `fotosDespues` to the existing shape — TS will surface "missing property" errors at compile time if any consumer is missed.

### `AdminOperationDetailPage.tsx` changes

Imports to add (after line 24):

```ts
import { OperationObservationsSection } from './components/OperationObservationsSection'
```

State to remove (lines 71-77):

```ts
const [isEditingDetails, setIsEditingDetails] = useState(false)
const [isSavingDetails, setIsSavingDetails] = useState(false)
const [detailsForm, setDetailsForm] = useState({...})
```

Handlers to remove (lines 224-259):

```ts
const startEditingDetails = () => {...}
const handleSaveDetails = async (event: FormEvent) => {...}
```

`FormEvent` import on line 1 (`type FormEvent`) becomes unused — drop it.

Lifecycle prop to add (after `canEditPricePlan` at line 592):

```ts
const canEditObservations = ['borrador', 'en proceso'].includes(
  operation.status.toLowerCase(),
)
```

JSX to remove (lines 746-794):

- The `<div className="operation-card__note-grid">…</div>` block stays **only if** the "Detalles de la operación" article is dropped or moved. Per spec line 28-36 + line 294, the read-only "Recomendaciones" block moves into the new section; the "Detalles de la operación" display block must NOT be in the page anymore (the new section IS the edit surface for `detalles_op` and shows its current value as the textarea prepopulation). Net result: **delete the entire `operation-card__note-grid` div, the trigger button, and the conditional form**. Replace with nothing.
- The `{!canEditPricePlan ? <small>…</small> : null}` at line 796-798 belongs to the editor — drop it too. The hint about sessions is also redundant because the page already says so elsewhere; if the apply phase finds a clean home for it, move it; otherwise drop.

JSX to add (after the closing `</SectionCard>` at line 1332, before `<ReservationModal>` at line 1334):

```tsx
<SectionCard
  eyebrow="Bitácora clínica"
  title="Observaciones del procedimiento"
  description="Registra notas clínicas y archiva fotos antes y después del procedimiento."
>
  <OperationObservationsSection
    operacion={operation}
    editable={canEditObservations}
    onSaved={reload}
  />
</SectionCard>
```

Net delta target: `≤ +50 lines` per spec line 23 (1 import + 1 lifecycle const + 1 render block + the deletions).

### CSS / class names

Reuse existing classes: `SectionCard`, `button button--ghost`, `button`, `field field--full`, `field__hint`, `input textarea`, `form-grid`, `form-actions`, `_grid-2cols`, `_panel-card`, `booking-modal-overlay` (for the confirm dialog via `useConfirmDialog`).

New class names introduced by the section — only if absolutely necessary:

| Class | Purpose |
| --- | --- |
| `observations-section__gallery` | Flex/grid wrapper for the thumbnails inside each kind block |
| `observations-section__thumb` | Each `<img>` + delete button pair |
| `observations-section__thumb-button` | The `×` overlay on each thumbnail |
| `observations-section__recommendations` | Read-only "Recomendaciones" display block (matches existing `field__hint` style for empty state) |
| `observations-section__kind-block` | Wrapper around one kind's input + gallery |

If `AppointmentNotesPanel.tsx:78-120` and `AdminOperationDetailPage.tsx:746-755` already cover all the visual patterns we need (they use `field field--full`, `input textarea`, `button`, `button--ghost`), drop the new classes and reuse those — visual consistency over novelty.

## Sequence flows

### Edit observaciones

```
Admin opens cms/operaciones/<id>
  → GET /api/admin/operaciones/<id>/
    → backend: _operation_detail_queryset() prefetches fotos_operacion
    ← 200 { operation: { fotosAntes: [...], fotosDespues: [...], ... } }
  → SectionCard "Observaciones del procedimiento" renders

Admin edits textarea, clicks Guardar
  → updateAdminOperationObservaciones(rawId, { details: "nuevo" })
    → POST /api/admin/operaciones/<id>/actualizar-observaciones/
      → backend: detalles_op = "nuevo", save(update_fields=["detalles_op"])
    ← 200 { detail, operation: <fresh payload> }
  → onSaved() = reload() → page re-fetches with canonical state
```

### Upload photo (auto-fire)

```
Admin picks 3 files under "Fotos antes"
  → handleUpload('antes', [file1, file2, file3])
    → For loop, sequential POSTs:
      → uploadAdminOperationPhotos(rawId, [file1], 'antes')
        → POST /api/admin/operaciones/<id>/fotos/antes/  (multipart)
        → backend: create OperacionFoto, imagen saved under
                   operaciones/<yyyy>/<mm>/<dd>/antes/<uuid>-<filename>
        ← 201 { saved: [{id, url, ...}], errors: {}, operation: <payload> }
      → merge saved[] into photos.antes optimistically
    → repeat for file2, file3
  → event.target.value = ''
  → onSaved() = reload()
```

### Delete photo

```
Admin clicks × on thumbnail id=42
  → confirm({ title: 'Eliminar foto', message: '…', tone: 'warning' })
    → user clicks "Cancelar" → no request, gallery unchanged
    → user clicks "Confirmar" → resolve(true)
  → deleteAdminOperationPhoto(rawId, 42)
    → DELETE /api/admin/operaciones/<id>/fotos/42/
      → backend: foto.imagen.delete(save=False); foto.delete()
    ← 204
  → setPhotos({ ...photos, antes: photos.antes.filter(...) })
  → onSaved() = reload()
```

## Tests

### Backend (Django unittest)

New file: `backend/tests/test_operation_observations_photos.py`. House style mirrors `test_appointment_close_split.py` — `TestCase` + `setUpTestData` fixtures + `self.client.force_login(self.admin)` + `self.client.post(url, data=..., content_type=...)`.

Fixture builder `_make_fixtures(cls)` creates an admin user, a cliente, an `Operacion(estado=EN_PROCESO)`, mirroring lines 36-90 of `test_appointment_close_split.py`. Plus a helper to spin up a tiny PNG via `SimpleUploadedFile` (pattern at `test_appointment_close_split.py:374-385`).

| Class | Test | Verifies |
| --- | --- | --- |
| `UpdateObservacionesTests` | `test_happy_path_persists_detalles_op` | POST `{details: "nuevo"}` → 200, `operacion.detalles_op == "nuevo"`, `recomendaciones` and `sesiones_totales` unchanged |
| | `test_missing_details_returns_400` | POST `{}` → 400, `errors.details` present |
| | `test_invalid_json_returns_400` | POST malformed body → 400, `detail` mentions JSON |
| | `test_missing_operacion_returns_404` | POST to `/operaciones/9999/actualizar-observaciones/` → 404 |
| | `test_anonymous_returns_401` | No `force_login` → 401 |
| | `test_non_admin_returns_403` | Force-login a cliente → 403 |
| | `test_does_not_clobber_recomendaciones` | Pre-set `recomendaciones="X"`, send `{details: "Y"}`, assert `recomendaciones == "X"` after |
| | `test_does_not_clobber_sesiones_totales` | Same as above for `sesiones_totales` |
| | `test_strips_whitespace` | `{details: "  nuevo  "}` → `detalles_op == "nuevo"` |
| `UploadPhotosTests` | `test_single_upload_persists_row_and_returns_201` | One file under `archivos`, kind=`antes` → 201, `saved.length==1`, `OperacionFoto.objects.count()==1`, file on disk at `media/operaciones/<date>/antes/<uuid>-<filename>` |
| | `test_multi_upload_persists_all` | Three files → 201, `saved.length==3`, three `OperacionFoto` rows, all `kind="antes"` |
| | `test_partial_success_one_oversized` | Three files, one > 5 MB → 201, `saved` has two, `errors["archivos[i]"]` set, the oversize file's row does NOT exist |
| | `test_all_oversized_returns_400` | All three > 5 MB → 400, `errors["archivos[i]"]` for each, zero rows |
| | `test_missing_archivos_returns_400` | No file → 400, `errors.archivos` set |
| | `test_invalid_kind_returns_400` | `kind="laterales"` → 400, `errors.kind` set, no row |
| | `test_kind_despues_stored_separately` | Upload to `despues`, query `fotos_operacion.filter(kind="despues").count() == 1` |
| | `test_detail_payload_after_upload_includes_new_photo` | POST upload → response `operation.fotosAntes[0].url` is an absolute URL (`startswith("http")`) |
| | `test_operacion_not_found_returns_404` | POST to `/operaciones/9999/fotos/antes/` → 404 |
| `DeletePhotoTests` | `test_delete_existing_returns_204_and_frees_disk` | Setup foto, capture `imagen.path`, DELETE → 204, `not os.path.exists(imagen_path)`, `OperacionFoto.objects.count() == 0` |
| | `test_cross_operation_delete_returns_404` | Foto on operacion 7, DELETE `/operaciones/8/fotos/<id>/` → 404, foto still exists |
| | `test_delete_missing_photo_returns_404` | DELETE non-existent id → 404 |
| `OperationDetailGalleryTests` | `test_detail_payload_includes_fotos_antes_ordered_by_upload_time` | Three fotos uploaded at different times → GET detail → `fotosAntes` in upload-time ASC |
| | `test_detail_payload_includes_fotos_despues` | Same for `despues` |
| | `test_empty_gallery_returns_empty_arrays` | Operacion with no fotos → `fotosAntes == []`, `fotosDespues == []` |
| | `test_gallery_is_single_query_no_n_plus_1` | Use `assertNumQueries` with `prefetch_related` already on the queryset — confirm gallery doesn't add queries beyond the existing baseline |
| `LifecycleTests` | `test_borrador_is_editable` | Pre-set `estado="BORRADOR"`, upload succeeds, save text succeeds |
| | `test_en_proceso_is_editable` | `estado="EN_PROCESO"`, both ops succeed |
| | `test_finalizada_is_read_only` | `estado="FINALIZADA"`, the new endpoint still persists (server doesn't gate) — but the FE prop drives visibility. **The backend does NOT gate on estado; the lifecycle is FE-only.** Document this in the test docstring. |

Total: ~22 tests. Combined with the existing 31+ tests in `test_appointment_close_split`, `test_maquinaria_conflicts`, `test_maquinaria_catalog`, `test_appointment_reservation_extended`, `test_especialista_mis_citas`, all still pass (the spec line 328 success criterion).

### Frontend

No new Playwright tests added in this change. The per-section component has no shared sibling to extract a test from. Manual smoke test per the change risk; out of scope for v1.

## Risks & mitigations

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| N+1 on `_operation_detail` if `fotos_operacion` is not prefetched | Med | `_operation_detail_queryset()` adds `Prefetch("fotos_operacion", queryset=OperacionFoto.objects.order_by("uploaded_at", "id"))` (AD7). The test `test_gallery_is_single_query_no_n_plus_1` asserts `assertNumQueries` stays at the existing baseline. |
| Disk orphans on delete | Med | `instance.imagen.delete(save=False)` runs in the endpoint (AD5) before `instance.delete()`. Test `test_delete_existing_returns_204_and_frees_disk` checks `os.path.exists(path) == False`. |
| Concurrent upload races (two uploads, one delete, in flight) | Low | Not addressed in v1 — out of scope per proposal. Each handler runs in `transaction.atomic`; UI always `reload()`s after each mutation so stale state cannot outlive the next refresh. |
| Lifecycle edge case: `BORRADOR` already has photos | Low | The spec section "Editable in BORRADOR and EN_PROCESO" (line 124) means even `BORRADOR` operations are editable. The lifecycle test `test_borrador_is_editable` covers this. The FE derives `canEditObservations` from `operation.status`, matching AD9. |
| Lifecycle gate on the server | Low | The spec makes lifecycle a FE-only concern (line 124). The backend accepts mutations regardless of `estado`. Document this in the test docstring for `LifecycleTests`. If a future spec needs server-side enforcement, add an early `if operacion.estado in {FINALIZADA, CANCELADA}: return 400` in each handler. |
| Sequential upload latency when admin picks 10 files | Low | For-loop is sequential per proposal open question #2. Typical pick is 1-5 files. If real usage shows larger picks, switch to `Promise.all` later. |
| Filename collision with original names preserved | Low | UUID4 prefix (`AD4`) prevents disk collisions. The `fileName` field returned to the FE strips the prefix, so the admin still sees the name they picked. |
| `request` threading into `_operation_detail` breaks a non-admin call site | Low | The optional `request=None` parameter (AD6) defaults to relative URLs. All 8 call sites must pass `request=request`; the apply phase must verify each. Test `test_detail_payload_after_upload_includes_new_photo` asserts `url` starts with `http`. |
| `_operation_detail` payload growth on large galleries | Low | Arrays are bounded by what the admin uploads; payload size stays small for typical use. The compound index keeps the query fast (AD7). |
| The page still grows: 1664 → ~1700 lines despite extraction | Med | Extraction reduces net delta. Spec target is `≤ +50` (line 23). Apply phase must verify with `git diff --stat` before merge. |
| Existing admins who relied on inline `recomendaciones` editor lose that capability | Med | `recomendaciones` is still rendered read-only in the new section (spec line 28). The legacy `admin_update_operation_details` endpoint remains on the server (no UI caller). No data is deleted. Future re-wiring is a one-frontend-screen task, no server work. |
| HEIC / unsupported image formats silently rejected by Pillow | Low | `accept="image/*"` hint in the input. Toast on error mentions the file extension. Documented as a known limitation in the proposal risk table. |
| Per-cita `foto_antes` / `foto_despues` accidentally shown in the new gallery | Low | Gallery reads from `operacion.fotos_operacion` only. The per-cita fields stay on `CitaMedica`. Test asserts no overlap by checking the detail payload's `appointments[*].fotoAntesUrl` is unchanged from before. |
| MEDIA serving in production (Whitenoise / S3) | Out of scope | Verify locally. Deployment docs flagged as follow-up. |

### Line-delta budget

| File | Estimated delta |
| --- | --- |
| `backend/operations/models.py` | +40 lines (model + callable + UUID/timezone import) |
| `backend/operations/migrations/0027_operacionfoto.py` | +25 lines (new file, auto-generated) |
| `backend/operations/admin.py` | +10 lines (import + admin class) |
| `backend/config/api_views.py` | +160 lines (3 handlers + `_operation_detail` extension + `_operation_detail_queryset` helper + `request` threading at 8 sites) |
| `backend/config/api_urls.py` | +18 lines (3 new path entries) |
| `backend/tests/test_operation_observations_photos.py` | +450 lines (new file, 22 tests) |
| `frontend/aesthetic-clinic/src/types/admin.ts` | +20 lines (3 types + 2 fields on existing type) |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | +35 lines (3 new functions) |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | -60 / +20 → net **-40 lines** (state/handlers/JSX removed, lifecycle const + import + render block added) |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | +280 lines (new file) |
| **Total** | **~+960 lines across 10 files, with one file shrinking by 40** |

The page-level delta is the spec target (`≤ +50` net lines; our estimate is `-40`, well under).

## Implementation order (apply phase)

1. **Backend model**: add `OperacionFoto` + `_operacion_foto_upload_to` to `backend/operations/models.py`. Add the import `import uuid`.
2. **Django admin**: register `OperacionFoto` in `backend/operations/admin.py`.
3. **Migration**: run `python manage.py makemigrations operations` to produce `0027_operacionfoto.py`. Verify the auto-generated `upload_to` references `_operacion_foto_upload_to`.
4. **Backend queryset helper**: add `_operation_detail_queryset()` near `_operation_detail` at `api_views.py:403`. Replace the inline querysets at `api_views.py:4494-4510` and `api_views.py:4554-4569`.
5. **Backend `_operation_detail` extension**: add `request=None` param, append `fotosAntes` / `fotosDespues` keys, build absolute URLs when `request` is provided. Thread `request=request` through the 8 call sites.
6. **Backend endpoints**: add `admin_update_operation_observaciones`, `admin_upload_operation_photos`, `admin_delete_operation_photo` to `api_views.py`.
7. **URL routes**: add 3 entries to `api_urls.py` immediately after `actualizar-detalles/`.
8. **Backend tests**: write `backend/tests/test_operation_observations_photos.py`. Run `python manage.py test operations.tests.test_operation_observations_photos`.
9. **Frontend types**: add `OperacionFoto`, `OperationDetailData.fotosAntes/fotosDespues`, `UpdateAdminOperationObservacionesResponse`, `UploadAdminOperationPhotosResponse` to `types/admin.ts`. Run `npx tsc -b --noEmit` to surface broken consumers.
10. **Frontend API client**: add `updateAdminOperationObservaciones`, `uploadAdminOperationPhotos`, `deleteAdminOperationPhoto` to `services/api/admin.ts`.
11. **Frontend component**: create `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx`.
12. **Frontend page wiring**: edit `AdminOperationDetailPage.tsx` — remove the 3 state vars, remove the 2 handlers, drop the 49-line JSX block, drop the now-unused `FormEvent` import, add the `OperationObservationsSection` import, add the `canEditObservations` const, mount the new `<SectionCard>` after line 1332.
13. **Final regression**: `python manage.py test operations` (existing 31+ tests still pass), `npx tsc -b --noEmit` from `frontend/aesthetic-clinic`, manual smoke on the dev server for upload/delete/save flows in each of the 4 lifecycle states.

Each step compiles cleanly before moving to the next; the migration (step 3) is a hard prerequisite for steps 4-8; the type additions (step 9) are a hard prerequisite for steps 10-12.

## Out of scope (explicit)

- Editing `Operacion.recomendaciones` from any UI surface in this change.
- Editing `Operacion.sesiones_totales` from the new section (handled in "Citas y cuotas" via `handleSaveSessions`).
- Drag-reorder of gallery thumbnails.
- Bulk-select multi-delete on the gallery.
- PDF / non-image attachments (`accept="image/*"` only).
- Server-side lifecycle gating (FE-only).
- Audit log entries for photo upload/delete (no `CitaMedica.save()`-style signal needed since uploads are additive).
- MEDIA production deployment (Whitenoise / S3) — verify locally.
- Specialist-side photo capture (specialists have no path to this page).
- A lightbox component for click-to-zoom (reusing the existing `photoPreviewUrl` pattern at `AdminOperationDetailPage.tsx:67` is one-line if needed later; out of scope for v1).

## Affected areas (recap)

| File | Impact | Description |
| --- | --- | --- |
| `backend/operations/models.py` | Modified | Add `OperacionFoto` + `_operacion_foto_upload_to` + `import uuid`. |
| `backend/operations/migrations/0027_operacionfoto.py` | New | Auto-generated. |
| `backend/operations/admin.py` | Modified | Register `OperacionFoto`. |
| `backend/config/api_views.py` | Modified | Add 3 handlers, `_operation_detail_queryset()` helper, `_operation_detail(operacion, request=None)` extension, thread `request` through 8 call sites. |
| `backend/config/api_urls.py` | Modified | 3 new routes next to `actualizar-detalles/`. |
| `backend/tests/test_operation_observations_photos.py` | New | ~22 tests across 4 TestCase classes. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modified | Add 3 types + 2 fields on `OperationDetailData`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modified | Add 3 functions. |
| `frontend/aesthetic-clinic/src/pages/admin/components/OperationObservationsSection.tsx` | New | Section component, ~280 lines. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Modified | Remove inline editor (state + handlers + JSX), mount new section. Net delta -40 lines. |