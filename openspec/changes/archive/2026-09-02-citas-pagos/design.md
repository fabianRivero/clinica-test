# Design: citas-pagos

Implements [`appointment-payment`](../citas-pagos/specs/appointment-payment/spec.md). Admin charges `CitaMedica` and `CitaClienteLibre` with VIRTUAL/FISICO/MIXTO, branch-isolated, over-payment guarded, audit-preserving. Mirrors the proven `pagos-fisicos-virtuales` flow against a new sibling `PagoCita` table; `PagoRealizado` / `CuotaPlanPago` are untouched.

## Technical Approach

A sibling `PagoCita` model in `billing` carries two nullable FKs (`cita_medica`, `cita_cliente_libre`) with a `CheckConstraint` XOR enforced in `clean()`. `CitaMedica` and `CitaClienteLibre` each gain an additive `precio: DecimalField(default=0, MinValueValidator(0))`. The model reuses `PagoRealizado.MetodoPago` + `EstadoVerificacion` choices; receipt path is `comprobantes_citas/%Y/%m/`. Two new `@action` endpoints land on the **client-detail `OperacionesViewSet`** in `config/api/viewsets/clientes.py` (the one registered by `routers_clientes.py` under `/operaciones/`) and on `FreeMedicalAppointmentViewSet`, gated by `AdminRequired` + a new `assert_cita_in_user_branch` helper that lives in `billing/validators.py` (where `assert_cuota_in_user_branch` already lives). Both endpoints wrap the cita row in `select_for_update`, reject `precio == 0`, reject terminal states (`CANCELADA`/`NO_ASISTIO`), enforce an over-payment guard analogous to `assert_not_over_payment`, and create `PagoCita` rows as `APROBADO` directly (admin collected in person — no second pair of eyes). Read serializers (`_appointment_item` / `_free_client_appointment_item`) extend with `precio`, `saldoPendiente`, `pagos_count`, `pagos[]`. Frontend mirrors the cuota modal as `AdminRegisterAppointmentPaymentModal` (parameter variant: `appointment` prop instead of `quota`); a new `registerAdminAppointmentPayment` service posts to the two new endpoints.

## Architecture Decisions

### Decision: Sibling `PagoCita` table (not polymorphism on `PagoRealizado`)

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| New `PagoCita` table; FK to `CitaMedica`/`CitaClienteLibre`; reuse `MetodoPago`/`EstadoVerificacion` choices via Python import. | Add nullable `cita` FK on `PagoRealizado` with discriminator; or generic relation; or `ContentType` polymorphism. | Citas are not cuotas: separate receipt path (`comprobantes_citas/`), separate over-payment scope (single `precio`, not sum of `monto_programado`), separate admin audit trail. Sharing `PagoRealizado` would force a discriminator column AND risk cuota-side `actualizar_estado_por_pagos()` seeing cita rows. Sibling table isolates both failure modes. Cross-table reads stay trivial via a `PagoCita` prefetch on the cita serializers. |

### Decision: Two nullable FKs + XOR (not single discriminator column)

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| `cita_medica: FK(null)` + `cita_cliente_libre: FK(null)` + `CheckConstraint(NOT(both) AND (one))` + `clean()` XOR. | Single `cita_type` discriminator + one nullable FK; or `ContentType` generic. | Two FKs make the ORM joins explicit (admin list endpoints prefetch the related cita in one query) and let `PagoCita.Meta.indexes` cover both FKs with `db_index=True`. Discriminator columns hide the type from the query planner and force `CASE WHEN` everywhere. ContentType is overkill for two known models and adds a join table. |

### Decision: `AdminRegisterAppointmentPaymentModal` as parameter variant (not prop-shim on the cuota modal)

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| New component that mirrors `AdminRegisterPaymentModal`'s body but accepts `appointment: AdminAppointment` instead of `quota: AdminPaymentQuota`. | Add a `kind: 'quota' \| 'appointment'` discriminator prop; or conditional rendering inside one mega-modal. | The header (`<patient> | <operation> | Cuota N` vs `<patient> | Cita <datetime>`), the disabled-when-over-paid rule (cuotas are over-paid when `saldo <= 0`; citas when `saldo == 0` OR `precio == 0`), the submit payload shape, and the parent wiring (cuota POSTs to `pagos/cuotas/<id>/pagos/`; cita POSTs to two distinct URLs) all diverge enough that a discriminated union inside the existing modal fights React rendering more than it helps. A side-by-side component keeps each prop surface stable and lets `sdd-apply` move them independently. |

### Decision: Branch-isolation helper in `billing/validators.py`

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| Add `assert_cita_in_user_branch(request, cita)` next to the existing `assert_cuota_in_user_branch` and `assert_not_over_payment` in `backend/billing/validators.py`. | New `backend/config/api/viewsets/_helpers.py`; or duplicate the helper in each viewset. | The existing helper module already centralises two cross-cutting admin validators and is the proven seam for branch-isolation. Reusing it keeps `from billing.validators import …` importable from both new endpoints and keeps the failure semantics aligned (404 on mismatch, matching the cuota flow). The prompt's "_helpers.py" hint referenced a non-existent module. |

### Decision: `assert_not_over_payment_cita` helper (not direct view-level check)

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| Add `assert_not_over_cita_payment(cita, new_amount)` to `billing/validators.py` next to `assert_not_over_payment`. | Inline the aggregation in each of the two viewset actions. | The aggregation rule (sum APROBADO + new > `precio`) is identical for both cita types and is conceptually identical to the cuota check; placing it in `validators.py` keeps the seam consistent and lets both endpoints unit-test it without standing up the full viewset. |

### Decision: Additive migration, no backfill

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| Single migration `0010_cita_precio_and_pago_cita.py`: `AddField("citas_medicas", "precio", default=0)` + same for `citas_clientes_libres` + `CreateModel("PagoCita")` with FK indexes. No `RunPython` backfill. | Backfill `precio = operacion.precio_total / sesiones_totales` for legacy rows; or split into two migrations. | `precio = 0` is the safest default: legacy appointments stay non-billable, the endpoint rejects them with a friendly 400, and no historical price assumption leaks into the audit trail. Backfilling would invent prices the admin never approved. Splitting into two migrations would delay `PagoCita` availability for no benefit (both ship together). |

### Decision: Receipt storage path `comprobantes_citas/%Y/%m/`

| Choice | Alternatives | Rationale |
|--------|--------------|-----------|
| `PagoCita.comprobante_url = FileField(upload_to="comprobantes_citas/%Y/%m/", …)` — distinct from `comprobantes_pagos/`. | Reuse `comprobantes_pagos/`; or `comprobantes/%Y/%m/<source>/`. | Distinct top-level folder keeps a clean admin audit split (cita vs cuota) and avoids filename collisions between two tables that share an allowed-extension list. Mirrors the proven `pagos-fisicos-virtuales` precedent (`comprobantes_pagos/`). |

## Data Flow

### Admin `cobrar` (both cita types — `CitaMedica` example)

```
 admin browser                DRF router              viewset action         billing layer
     │ POST                       │                          │                       │
     │ /api/admin/operaciones/    │                          │                       │
     │   <op_id>/citas/<id>/      │                          │                       │
     │   cobrar/                  │                          │                       │
     │ (multipart, paymentMethod, │                          │                       │
     │  amount, montoFisico?,     │                          │                       │
     │  montoVirtual?,            │                          │                       │
     │  receiptFile?, details?)   │                          │                       │
     │ ────────────────────────►  │ OperacionesViewSet       │                       │
     │                            │ (routers_clientes.py)    │                       │
     │                            │ ───────────────────────► │ @action cobrar        │
     │                            │                          │  1) select_for_update │
     │                            │                          │     CitaMedica ─────► │ DB row lock
     │                            │                          │  2) assert_cita_in    │
     │                            │                          │     _user_branch ───► │ PermissionDenied → 403
     │                            │                          │  3) precio == 0?     │
     │                            │                          │     → 400 + no row    │
     │                            │                          │  4) estado in        │
     │                            │                          │     {CANCELADA,       │
     │                            │                          │      NO_ASISTIO}?     │
     │                            │                          │     → 400 + no row    │
     │                            │                          │  5) PagoCitaCreate    │
     │                            │                          │     Serializer ─────► │ shape errors → 400
     │                            │                          │  6) assert_not_over_  │
     │                            │                          │     cita_payment ───► │ over-paid → 400
     │                            │                          │  7) PagoCita.save()  │
     │                            │                          │     APROBADO,         │
     │                            │                          │     verificado_por=   │
     │                            │                          │     request.user ───► │ INSERT row
     │                            │                          │  8) cita.refresh_     │
     │                            │                          │     from_db()         │
     │                            │ ◄────────────────────── │ Response 201          │
     │ ◄──────────────────────── │                          │  { detail, payment,  │
     │ 201 + cita payload         │                          │    appointment w/     │
     │                            │                          │    precio,            │
     │                            │                          │    saldoPendiente,    │
     │                            │                          │    pagos[],           │
     │                            │                          │    pagos_count }      │
```

### Client-detail GET (read payload refresh)

```
 admin reloads client detail      DRF router                  viewset                serializer
     │                                  │                            │                        │
     │ GET /api/admin/clientes/<id>/    │                            │                        │
     │ ────────────────────────────►    │ ClientesViewSet            │                        │
     │                                  │ ─────────────────────────► │ retrieve               │
     │                                  │                            │ _admin_client_queryset │
     │                                  │                            │ (prefetch cita +       │
     │                                  │                            │  PagoCita via new      │
     │                                  │                            │  prefetch)             │
     │                                  │                            │ _admin_client_detail   │
     │                                  │                            │ ─────────────────────► │ _appointment_item /
     │                                  │                            │                        │ _free_client_…
     │                                  │                            │                        │ reads cita.precio,
     │                                  │                            │                        │ computes
     │                                  │                            │                        │ saldoPendiente =
     │                                  │                            │                        │  precio − sum(
     │                                  │                            │                        │   APROBADO pago)
     │                                  │                            │                        │ paginates pagos[]
     │                                  │ ◄─────────────────────────│ 200 client payload    │
     │ ◄─────────────────────────────│                            │                        │
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/operations/models.py` | Modify | Add `precio = DecimalField(default=0, MinValueValidator(0))` to `CitaMedica` and `CitaClienteLibre`. |
| `backend/billing/models.py` | Modify | Add `PagoCita` class (two nullable FKs, `CheckConstraint` XOR, `metodo_pago`, `monto_pagado`, `monto_fisico`, `monto_virtual`, `comprobante_url` w/ `comprobantes_citas/%Y/%m/`, `estado_verificacion`, `detalles_pago`, `created_at`, `updated_at`). `Meta.indexes` covers both FKs. |
| `backend/billing/migrations/0010_cita_precio_and_pago_cita.py` | Create | `AddField("citas_medicas","precio")` + `AddField("citas_clientes_libres","precio")` + `CreateModel("PagoCita")` with FK indexes. No backfill. |
| `backend/billing/validators.py` | Modify | Add `assert_cita_in_user_branch(request, cita)` (raises `PermissionDenied` → 403, distinct from the cuota helper's 404; spec mandates 403 for cross-branch). Add `assert_not_over_cita_payment(cita, new_amount)` summing APROBADO `PagoCita` rows against `cita.precio`. |
| `backend/config/api/serializers/payments.py` | Modify | Add `PagoCitaCreateSerializer` (mirrors `PagoRealizadoCreateSerializer` shape — `paymentMethod`, `monto_pagado`, `montoFisico?`, `montoVirtual?`, `receiptFile?`, `details?`; receipt optional regardless of method since this is admin-only). Add `PagoCitaSerializer` (read — `id`, `monto_pagado`, `metodo_pago`, `monto_fisico`, `monto_virtual`, `comprobante_url`, `estado_verificacion`, `detalles_pago`, `created_at`). |
| `backend/config/api/viewsets/clientes.py` | Modify | In **client-detail `OperacionesViewSet`** (the one in this file, registered by `routers_clientes.py`): add `@action(detail=True, methods=["post"], url_path=r"citas/(?P<cita_id>\d+)/cobrar")` `cobrar_cita` — locks `CitaMedica` with `select_for_update`, runs all 5 guards, returns updated cita item. In `FreeMedicalAppointmentViewSet`: add `@action(detail=True, methods=["post"], url_path="cobrar")` `cobrar` — same guards against `CitaClienteLibre`. Update `_client_appointment_item` import and `_admin_client_queryset` to `Prefetch` `cita_medica__pagos_cita` and `cita_cliente_libre__pagos_cita` (reverse relation). Update `_admin_client_detail` to compute and inject `precio`, `saldoPendiente`, `pagos_count`, `pagos[]` into both cita items. Update `_free_client_appointment_item` likewise. |
| `backend/config/client_api_views.py` | Modify | Extend `_appointment_item` to include `precio`, `saldoPendiente`, `pagos_count`, `pagos[]` (so every cita payload — admin detail, client portal, kiosko — surfaces the breakdown). The cita is already prefetched; only the new attrs are added. |
| `frontend/aesthetic-clinic/src/components/admin/AdminRegisterAppointmentPaymentModal.tsx` | Create | Parameter variant of `AdminRegisterPaymentModal`. Same VIRTUAL/FISICO/MIXTO + breakdown + optional receipt form, but header reads `<patient> | Cita <datetime>`, the disabled rule is `precio == 0 || saldoPendiente == 0`, accepts `appointment: AdminAppointment` instead of `quota`. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Modify | Add "Cobrar cita" button per row when `appointment.precio > 0 && appointment.estado not in {CANCELADA, NO_ASISTIO}`. Opens the new modal. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | Modify | Same as above (the operation detail page re-renders cita rows; both spots get the button). |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientFreeMedicalAppointmentSection.tsx` | Modify | Free-appointment variant: button enabled when `precio > 0` and `estado !== CANCELADA`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | Modify | Add `registerAdminAppointmentPayment(operationId, citaId, payload)` for `CitaMedica` (POSTs to `/api/admin/operaciones/<op_id>/citas/<cita_id>/cobrar/`) and `registerAdminFreeAppointmentPayment(citaId, payload)` for `CitaClienteLibre` (POSTs to `/api/admin/citas-medicas-libres/<cita_id>/cobrar/`). Both reuse the same multipart builder as `registerAdminPayment`. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modify | Add `AdminAppointment = { rawId, operationRawId \| null, isFreeMedicalAppointment, precio, saldoPendiente, pagos_count, pagos: AdminAppointmentPayment[] }` plus the `AdminAppointmentPayment` shape mirroring the `PagoCitaSerializer` output. Add `RegisterAdminAppointmentPaymentPayload` / `RegisterAdminAppointmentPaymentResponse`. |
| `frontend/aesthetic-clinic/src/types/common.ts` | Modify | Extend `ClientAppointment` with the four new optional fields (`precio`, `saldoPendiente`, `pagos_count`, `pagos?`). |
| `backend/billing/tests/test_admin_register_appointment_payment.py` | Create | Model `clean()` rules + branch isolation + over-payment + cancellation cascade + receipt path + endpoint success for FISICO/VIRTUAL/MIXTO. |

## Interfaces / Contracts

### `PagoCita` model (`backend/billing/models.py`)

```python
class PagoCita(TimeStampedModel):
    MetodoPago = PagoRealizado.MetodoPago          # reused
    EstadoVerificacion = PagoRealizado.EstadoVerificacion  # reused

    cita_medica = FK("operations.CitaMedica", null=True, blank=True,
                     related_name="pagos_cita", on_delete=CASCADE)
    cita_cliente_libre = FK("operations.CitaClienteLibre", null=True, blank=True,
                            related_name="pagos_cita", on_delete=CASCADE)
    monto_pagado = DecimalField(max_digits=10, decimal_places=2,
                                validators=[MinValueValidator(0)])
    metodo_pago = CharField(max_length=10, choices=MetodoPago.choices,
                            default=MetodoPago.VIRTUAL)
    monto_fisico = DecimalField(..., default=0)
    monto_virtual = DecimalField(..., default=0)
    comprobante_url = FileField(upload_to="comprobantes_citas/%Y/%m/",
                                blank=True,
                                validators=[FileExtensionValidator([...])])
    estado_verificacion = CharField(..., default=EstadoVerificacion.PENDIENTE)
    detalles_pago = TextField(blank=True)

    class Meta:
        db_table = "pagos_citas"
        ordering = ("-created_at",)
        indexes = [
            Index(fields=["cita_medica", "-created_at"]),
            Index(fields=["cita_cliente_libre", "-created_at"]),
        ]
        constraints = [
            CheckConstraint(
                check=(
                    models.Q(cita_medica__isnull=True, cita_cliente_libre__isnull=False)
                    | models.Q(cita_medica__isnull=False, cita_cliente_libre__isnull=True)
                ),
                name="pago_cita_xor_cita_fk",
            ),
        ]

    def clean(self):
        # XOR — exactly one FK set
        if bool(self.cita_medica_id) == bool(self.cita_cliente_libre_id):
            raise ValidationError({"__all__": "PagoCita requiere exactamente una cita asociada."})
        # Method-driven amount validation (delegates to a module-level helper
        # so PagoRealizado.clean() and PagoCita.clean() stay in lock-step)
        _validate_metodo_pago_amounts(self)  # same rules as PagoRealizado
```

### `PagoCitaCreateSerializer`

```python
class PagoCitaCreateSerializer(serializers.Serializer):
    paymentMethod = ChoiceField(choices=PagoRealizado.MetodoPago.choices)
    monto_pagado = DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    montoFisico  = DecimalField(required=False, allow_null=True, min_value=0)
    montoVirtual = DecimalField(required=False, allow_null=True, min_value=0)
    receiptFile  = FileField(required=False, allow_null=True)   # optional regardless of method
    details      = CharField(required=False, allow_blank=True, default="")
    # validate() mirrors PagoRealizadoCreateSerializer.validate() — VIRTUAL/FISICO/MIXTO
    # breakdown rules, but receipt is OPTIONAL for VIRTUAL (admin collected in person).
```

### `PagoCitaSerializer` (read)

| Field | Type | Source |
|-------|------|--------|
| `id` | int | `pk` |
| `monto_pagado` | str | `currency(pago.monto_pagado)` |
| `metodo_pago` | str | `pago.metodo_pago` |
| `monto_fisico` | str | `currency(pago.monto_fisico)` |
| `monto_virtual` | str | `currency(pago.monto_virtual)` |
| `comprobante_url` | str | absolute URL or empty |
| `estado_verificacion` | str | `pago.estado_verificacion` |
| `detalles_pago` | str | `pago.detalles_pago` |
| `created_at` | str | ISO 8601 |

### New endpoints

**`POST /api/admin/operaciones/<int:operation_id>/citas/<int:cita_id>/cobrar/`** (client-detail `OperacionesViewSet.cobrar_cita`)

Request: same `multipart/form-data` shape as `PagoRealizadoCreateSerializer`, plus the implicit `cita_id` from the URL. Response `201`: `{ detail, payment: PagoCitaSerializer-shaped dict, appointment: <extended cita item> }`. Error responses: `400` (validation / over-payment / `precio == 0` / terminal state), `403` (cross-branch), `404` (cita not found).

**`POST /api/admin/citas-medicas-libres/<int:pk>/cobrar/`** (`FreeMedicalAppointmentViewSet.cobrar`)

Same request + response shape, no nested `operation_id`.

### New TypeScript types (`frontend/.../src/types/admin.ts`)

```ts
export type AdminAppointmentPayment = {
  id: number
  monto_pagado: string
  metodo_pago: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  monto_fisico: string
  monto_virtual: string
  comprobante_url: string
  estado_verificacion: 'PENDIENTE' | 'APROBADO' | 'RECHAZADO' | 'CANCELADO'
  detalles_pago: string
  created_at: string
}

export type AdminAppointment = {
  rawId: number
  operationRawId: number | null
  isFreeMedicalAppointment?: boolean
  precio: string              // "0.00" default — backend fills in
  saldoPendiente: string      // "precio - sum(APROBADO)"
  pagos_count: number
  pagos: AdminAppointmentPayment[]
  // … existing ClientAppointment fields inherited
}

export type RegisterAdminAppointmentPaymentPayload = {
  paymentMethod: 'VIRTUAL' | 'FISICO' | 'MIXTO'
  amount: string
  montoFisico?: string
  montoVirtual?: string
  receiptFile?: File
  details?: string
}
```

## Testing Strategy

Django `TestCase` suite under `backend/billing/tests/test_admin_register_appointment_payment.py`. Factory helper mirrors the existing `_AdminPaymentGraph`.

| Layer | Test | Asserts |
|-------|------|---------|
| Model | `test_clean_xor_requires_exactly_one_fk` | Both FKs set or both null → `ValidationError`. Setting only one passes. |
| Model | `test_clean_virtual_requires_receipt_when_method_virtual` (admin-only path: receipt optional, but the helper validates amount match). | See helper test below. |
| Helper | `test_validate_metodo_pago_amounts_via_clean` | VIRTUAL → `monto_virtual == monto_pagado`; FISICO → `monto_fisico == monto_pagado`; MIXTO → both `> 0` and sum matches. |
| Helper | `test_assert_cita_in_user_branch_same_branch_silent` | Same branch → no exception. |
| Helper | `test_assert_cita_in_user_branch_cross_branch_raises_403` | Different branch → `PermissionDenied`. |
| Helper | `test_assert_not_over_cita_payment_rejects_overpay` | `precio=100`, APROBADO sum=80, attempt to add 50 → raises. |
| Endpoint | `test_cobrar_cita_fisico_happy_path` | Same-branch admin, FISICO no receipt → 201, `APROBADO`, row persisted. |
| Endpoint | `test_cobrar_cita_virtual_no_receipt_succeeds_for_admin` | The admin-receipt-allowed semantic. |
| Endpoint | `test_cobrar_cita_mixto_breakdown_mismatch_400` | `montoFisico + montoVirtual != monto_pagado` → 400. |
| Endpoint | `test_cobrar_cita_precio_zero_400` | `precio == 0` → 400, no row. |
| Endpoint | `test_cobrar_cita_cancelada_returns_400` | State `CANCELADA` → 400, no row. |
| Endpoint | `test_cobrar_cita_no_asistio_returns_400` | State `NO_ASISTIO` → 400, no row. |
| Endpoint | `test_cobrar_cita_over_payment_returns_400` | Inside `select_for_update` block — race + aggregate check. |
| Endpoint | `test_cobrar_cita_cross_branch_returns_403` | Distinct from cuota's 404 — assert 403. |
| Endpoint | `test_cobrar_cita_libre_fisico_happy_path` | Same suite for `FreeMedicalAppointmentViewSet.cobrar`. |
| Endpoint | `test_cobrar_cita_libre_cross_branch_returns_403` | Same branch check on `CitaClienteLibre`. |
| Read | `test_appointment_item_includes_precio_saldo_pagos` | After one APROBADO row, payload has correct `saldoPendiente` and `pagos_count == 1`. |
| Read | `test_cancellation_does_not_delete_pago_cita_rows` | `estado=CANCELADA` preserves rows and rejects new cobrar. |
| File | `test_receipt_uploads_to_comprobantes_citas_path` | Upload lands under `comprobantes_citas/YYYY/MM/`, never `comprobantes_pagos/`. |

## Threat Matrix

`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.`

This change adds DRF endpoints, a sibling model, a serializer, a helper, and a frontend modal. No new process spawn, no new shell, no new VCS or PR automation, no new executable-file handling. The single file upload flows through Django's standard `FileField` storage backends (already in use for `PagoRealizado.comprobante_url`).

## Migration / Rollout

1. **Deploy backend migration `0010_cita_precio_and_pago_cita.py` first.** Adds `CitaMedica.precio`, `CitaClienteLibre.precio` (both `default=0`, additive — no rewrite of existing rows), and creates `pagos_citas` table with FK indexes. No backfill: legacy citas stay non-billable until an admin explicitly sets `precio`.
2. **Deploy backend code** (model `PagoCita`, serializer, viewset actions, helper, read-payload extension, tests). Safe to deploy alone — no behavioral change until the new endpoints are hit.
3. **Deploy frontend** (modal, page wiring, types, services). Safe to deploy earlier than backend since the new modal only fires when an admin clicks "Cobrar cita"; without the endpoints the click yields a 404 and the modal surfaces the error message.
4. **No feature flag.** `precio == 0` is the natural disable for legacy appointments; admins set `precio` from the existing operation/cita edit flows before the cobrar button appears.

**Rollback:** Revert migration `0010` (drops `PagoCita`, drops both `precio` columns — additive, no data loss because nothing else references them). Revert code, modal, and service. `PagoRealizado` and the cuota flow are untouched in both directions.

## Open Questions

None.
