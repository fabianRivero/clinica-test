# Exploration: citas-pagos

## Current State

The clinic schedules two flavours of medical appointments today, neither of which carries a charge:

- **`CitaMedica`** (`backend/operations/models.py` lines 134-307) — FK to `Operacion`, FK to `Sucursal`, states `PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA` (plus `CANCELADA`, `NO_ASISTIO`). Created via `POST /operaciones/<id>/reserva/` (`backend/config/api/viewsets/clientes.py` lines 513-572). Lives under `Operacion.citas_medicas` reverse FK. Already carries many planning/real-time fields (`descripcion_general`, `notas_previas`, `foto_antes`, `duracion_estimada_minutos`, etc.) but **no `precio` column** — payment, when it exists, lives one level up on the linked `CuotaPlanPago` of the parent `Operacion`.
- **`CitaClienteLibre`** (`backend/operations/models.py` lines 479-526) — FK to `Cliente`, FK to `ServicioConfig` (consulta/cita-medica only — `clean()` blocks `proc_estetico_id`), states `PROGRAMADA → REALIZADA` (plus `CANCELADA`, `NO_ASISTIO`). Created via `POST /citas-medicas-libres/<client_id>/` (`backend/config/api/viewsets/clientes.py` lines 615-661). Free, walk-in style appointment.

Payments live in a sibling app (`backend/billing/models.py`):

- **`PagoRealizado`** (lines 96-243) — FK to `CuotaPlanPago`, fields `monto_pagado`, `metodo_pago` (VIRTUAL/FISICO/MIXTO), `monto_fisico`, `monto_virtual`, `comprobante_url` (upload_to=`comprobantes_pagos/%Y/%m/`), `estado_verificacion` (PENDIENTE/APROBADO/RECHAZADO/CANCELADO). `clean()` enforces per-method rules (VIRTUAL needs receipt, FISICO has receipt optional, MIXTO needs both halves > 0 and sum to total). `save()` triggers `cuota.actualizar_estado_por_pagos()` and `paciente.actualizar_estado_automaticamente()`. Receipt file storage uses `comprobantes_pagos/`, separate from `citas/<YYYY>/<MM>/<DD>/antes|despues/` photos.
- **`CuotaPlanPago`** (lines 29-93) — FK to `Operacion` (NOT to `CitaMedica`). So a cita currently has no payment surface.

The reference change **`pagos-fisicos-virtuales`** already implements exactly the admin flow we need to mirror:

- New `@action` on `PagosViewSet` (`backend/config/api/viewsets/payments.py` lines 273-375) at `POST /api/pagos/cuotas/<cuota_id>/pagos/`, gated by `AdminRequired` + branch isolation via `assert_cuota_in_user_branch(request, cuota)`. Creates `PagoRealizado` **APROBADO** immediately (admin collected the cash/QR themselves) and fires `CLIENT_PAYMENT_CONFIRMED` to the client.
- Write serializer `PagoRealizadoCreateSerializer` (`backend/config/api/serializers/payments.py` lines 14-66) — NOT a ModelSerializer; explicit shape with `paymentMethod`, `monto_pagado`, optional `montoFisico`/`montoVirtual`/`receiptFile`/`details`.
- Branch-scoped read via `get_user_branch(request)` and the `assert_cuota_in_user_branch` helper (`backend/billing/validators.py` lines 32-53).
- Frontend `AdminRegisterPaymentModal` (`frontend/aesthetic-clinic/src/components/admin/AdminRegisterPaymentModal.tsx`) is fully reusable: takes `quota: AdminPaymentQuota | null` (typed in `frontend/aesthetic-clinic/src/types/admin.ts` lines 608-620), isOpen/isSubmitting/errorMessage, onClose, onSubmit — derives `saldoPendiente = amount - paidAmount`, prefills 50/50 MIXTO breakdown, optionally attaches a receipt.

Both `CitaMedica` and `CitaClienteLibre` lack any `precio`/`monto` column. The appointment payload helper `_appointment_item` (`backend/config/client_api_views.py` lines 399-518) and the free-appointment helper `_free_client_appointment_item` (`backend/config/api/viewsets/clientes.py` lines 187-207) emit `dateTime`, `status`, `specialist`, etc., but no price/saldo fields.

Today the admin payment UI lives in three places that reuse `AdminRegisterPaymentModal`:

- `frontend/aesthetic-clinic/src/pages/admin/AdminPaymentsPage.tsx` lines 62-65 + 184-208 — cuotas tab.
- `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` lines 112-114 + 484-508 — cuotas from operation detail.
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientPaymentSection.tsx` lines 78-116 — cuotas from client detail.

For appointments specifically:

- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` lines 133-204 renders a row of buttons per appointment (Cancelar, Reprogramar, Confirmar con huella, etc.). No "Cobrar" button.
- `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` lines 917-1004 renders appointments inside the operation detail with the same action set. No "Cobrar" button.
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientFreeMedicalAppointmentSection.tsx` only handles the booking form; there is no admin actions list per free appointment — those live in `ClientAppointmentSection` (which lists both via the `_free_client_appointment_item` marker `isFreeMedicalAppointment`).

## Affected Areas

- `backend/operations/models.py` — `CitaMedica` and `CitaClienteLibre` both need a new `precio: DecimalField(default=0)` column; migration must be backward-compatible (existing appointments stay free). Possibly a `Pago` reverse FK accessor.
- `backend/billing/models.py` — new payment model (decision pending) or new FK on existing `PagoRealizado`; new `clean()`/validation rules that do not require a parent `CuotaPlanPago`. Migration that introduces the FK/column without breaking existing `PagoRealizado.cuota` NOT NULL constraint.
- `backend/config/api/serializers/payments.py` — either a new write serializer `PagoCitaCreateSerializer` or a generalized `PagoRealizadoCreateSerializer` that drops the `cuota` requirement. Read serializer for the cita context (`PagoCitaSerializer` or extended `PagoRealizadoSerializer`) must surface the appointment reference.
- `backend/config/api/viewsets/clientes.py` — new `@action` on `FreeMedicalAppointmentViewSet` for `POST /citas-medicas-libres/<id>/cobrar/`. Update `_free_client_appointment_item` and `_appointment_item` to include `precio`, `saldoPendiente`, `paymentsCount`.
- `backend/config/api/viewsets/operaciones.py` or a new dedicated viewset — new `@action` for `POST /operaciones/<id>/citas/<cita_id>/cobrar/` (matches the existing nested-resource style used by `reserva`). Need a branch-isolation helper that targets `CitaMedica` rather than `CuotaPlanPago`.
- `backend/billing/validators.py` — add a sibling helper `assert_cita_in_user_branch(request, cita)` (cita may carry FK to `cliente.usuario.sucursal` either via `Operacion.paciente` or directly on `CitaClienteLibre.cliente`).
- `backend/billing/migrations/` — new migration adding `precio` to both appointment tables and the new payment FK/column; backfill `precio=0` (no-op). Idempotent backfill pattern from `0009_payment_physical_virtual_fields.py`.
- `frontend/aesthetic-clinic/src/types/admin.ts` — new `AdminRegisterAppointmentPayment` payload type + appointment context type that mirrors `AdminPaymentQuota` but uses the appointment's `precio` instead of `monto_programado`.
- `frontend/aesthetic-clinic/src/services/api/admin.ts` — new `registerAdminAppointmentPayment(citaId, payload)` calling `POST /api/admin/citas-medicas-libres/<id>/cobrar/` or `POST /api/admin/operaciones/<op>/citas/<cita>/cobrar/`. New helpers `cancelAdminAppointmentPayment` if we allow refunds (out of scope per locked decisions).
- `frontend/aesthetic-clinic/src/components/admin/AdminRegisterPaymentModal.tsx` — DECISION POINT. Either (a) keep the modal as-is and pass an `AdminRegisterAppointmentPaymentQuota`-shaped object whose `amount` comes from `cita.precio` and `paidAmount` from approved payments; or (b) introduce a thin wrapper that fixes the modal's header copy ("Cita N" instead of "Cuota N").
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` — add a "Cobrar cita" button for citas where `estado != CANCELADA && estado != NO_ASISTIO && precio > 0`, gated by a new `canCharge` flag on the appointment payload.
- `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` — same "Cobrar cita" button in the appointment list (around line 917-1004), plus a second instance for the free-medical-appointment variant.
- `openspec/specs/` — new delta spec `citas-pagos` under the most-fitting existing domain (likely a new `appointment-payment` domain, or extending `payment-physical-virtual`); reference format lives in `openspec/changes/pagos-fisicos-virtuales/specs/payment-physical-virtual/spec.md`.

## Approaches

### 1. **Reuse `PagoRealizado` with a nullable `cuota` + new FK `cita` (GenericForeignKey)**

Add a `GenericForeignKey` to `PagoRealizado` that can point at either `CitaMedica` or `CitaClienteLibre`. Keep the existing `cuota` FK as nullable. Validation/clean methods get a polymorphic branch.

- Pros: zero new tables; reuses the entire read/history/UI infrastructure already built for `pagos-fisicos-virtuales`. Single migration with idempotent backfill (existing cuota rows untouched).
- Cons: `PagoRealizado` becomes polymorphic on read; serializers must render whichever FK is set. `GenericForeignKey` makes queries (`payments_count`, history) harder to optimise and admin lists (`/cms/pagos/pendientes`) currently scope by `cuota__operacion__paciente__usuario__sucursal_id`. Branch isolation must switch from `cuota__operacion__…` to either `content_type` lookup or a denormalised `cliente_usuario_sucursal_id` column.
- Effort: Medium. The branch-scoping and admin-payment-list queries are the bulk of the work.

### 2. **Sibling model `PagoCita` (new table with two nullable FKs + discriminator)**

Add a new `PagoCita` model in `backend/billing/models.py` mirroring `PagoRealizado`'s fields (`metodo_pago`, `monto_fisico`, `monto_virtual`, `comprobante_url` with the **same** `comprobantes_pagos/%Y/%m/` path, `estado_verificacion`, etc.). Two nullable FKs `cita_medica` and `cita_cliente_libre`, with `clean()` enforcing exactly one is set.

- Pros: clean separation; doesn't touch the existing `PagoRealizado`/cuota flow at all. Easy to scope queries (`PagoCita.objects.filter(cita_medica__operacion__paciente__usuario__sucursal_id=branch)` or `cita_cliente_libre__cliente__usuario__sucursal_id=branch`). New table, no migration risk on `pagos_realizados`.
- Cons: code duplication of the validation rules (`metodo_pago` + breakdown rules) — but a shared `clean()` mixin or helper function kills that. Two write serializers (or one generic) needed. The admin payment history list needs to merge both `PagoRealizado` and `PagoCita` rows, or stay separate (recommended: keep them separate for now — different payment surfaces).
- Effort: Low-Medium. Clear data model, single migration that introduces one table + two FKs. Mirrors the `pagos-fisicos-virtuales` shape 1:1.

### 3. **Two separate models `PagoCitaMedica` + `PagoCitaClienteLibre`**

One model per appointment type. Each carries its own FK (non-null), validation, and serializer.

- Pros: simplest data model per type. No polymorphism on read.
- Cons: maximum duplication (`metodo_pago`, `clean()`, `save()`). Two migrations. The UI can't show "all payments for this client" without a UNION; we'd have to merge in the view layer. Adding a third appointment type later (e.g. `CitaProspecto`?) means a third model.
- Effort: Low per model, High overall.

## Recommendation

**Approach #2: a sibling `PagoCita` model with two nullable FKs + a discriminator check.** Reasons:

1. The `pagos-fisicos-virtuales` design already proved that the admin-side "register payment on behalf of client" workflow (modal, serializer shape, branch isolation, file upload path) works exactly as a sibling payment row. We mirror 95% of the code.
2. No risk to the existing `PagoRealizado` flow — every test under `test_quota_status_rules.py` and `test_operation_price_plan_update.py` continues to work unchanged.
3. Branch scoping is two clean ORM filters (one per FK path) — no `GenericForeignKey` indexing concerns, no `content_type` joins on the admin list page.
4. The discriminator check (`cita_medica_id XOR cita_cliente_libre_id`) goes in `clean()` and the serializer; trivial to enforce.
5. Future-proof: if we ever charge `CitaProspecto` or another appointment type, we either add a third nullable FK or migrate to a real GFK. Today's data is bounded to two types, so the two-FK approach is the simplest correct shape.

**Locked design choices (do not re-question):**

- New `precio: DecimalField(default=0, validators=[MinValueValidator(0)])` on both `CitaMedica` and `CitaClienteLibre`. Backfill = `0` (no-op). The admin can edit `precio` at booking time (extend `OperationReservationCreateSerializer` and `FreeMedicalAppointmentCreateSerializer` with an optional `precio` field) and later (new endpoint `POST /citas/<id>/actualizar-precio/` or a sub-action — see Risks for scope).
- Admin-only first release. Client self-service (`/cliente/citas/<id>/comprobante/`-style endpoint) is **out of scope** for this change; the spec should leave a clean seam (e.g. a doc comment + the same `PagoCita` model that a future change can read/write from a client view) but no client endpoint, no client notification changes, no `client_upload_payment_receipt`-style function in this change.
- Charging is allowed at any state **except** `CANCELADA` and `NO_ASISTIO`. `PROGRAMADA`, `REALIZADA_PENDIENTE_VERIFICACION`, `CONFIRMADA` (CitaMedica) and `REALIZADA` (CitaClienteLibre) all accept a charge. The endpoint must reject `CANCELADA`/`NO_ASISTIO` explicitly. Charging does **not** mutate `estado`.
- Over-payment guard analogous to `assert_not_over_payment`: the new endpoint must reject when `sum(PagoCita.monto_pagado where estado_verificacion=APROBADO for this cita) + new.monto_pagado > cita.precio`. Implemented as a view-level guard (matching `pagos-fisicos-virtuales`).
- On cascade: keep existing `on_delete=CASCADE` behaviour. If a cita is deleted, its `PagoCita` rows go with it (matches `PagoRealizado.cuota` cascade). Cancelling a cita does NOT delete its `PagoCita` rows — the admin keeps the audit trail and can issue a refund via `estado_verificacion=CANCELADO` (admin's responsibility, same channel as `PagoRealizado`).
- Receipt file storage path stays `comprobantes_pagos/%Y/%m/` (already supports both flows — the existing field validators `FileExtensionValidator(["png","jpg","jpeg","webp","pdf"])` apply as-is). No collision: same prefix as `PagoRealizado`, but Django's storage backend disambiguates by `upload_to` callable if needed.
- Frontend modal: **option A** — keep `AdminRegisterPaymentModal` unchanged and pass a synthetic `AdminPaymentQuota` whose `amount = cita.precio`, `paidAmount = sum(approved pagos)`, `quotaNumber = cita.rawId` (string-encoded for display, e.g. `"Cita-0042"`), `patient = client full name`, `operation = operation name || serviceConfig.tipo`. The modal's `saldoPendiente` derivation works as-is. Adds a tiny `headerSubtitle` prop so the header reads "Cita 0042 · Sesión #1" instead of "Cuota 3", but the existing copy "Cuota N" can stay if we prefer zero changes to the modal. Decision deferred to `sdd-design` after the orchestrator picks the exact UX.

## Risks

- **Migration / backfill** — Low. New columns (`precio=0`) and a new `PagoCita` table are purely additive. No existing test exercises `CitaMedica.precio` or `CitaClienteLibre.precio`; no factory call to update.
- **Branch isolation** — Med. Need a new helper `assert_cita_in_user_branch(request, cita)` because the existing `assert_cuota_in_user_branch` reads `cuota.operacion.paciente…` which is meaningless for `PagoCita`. The helper resolves the client's `sucursal_id` from either path and rejects (404) on mismatch.
- **Over-payment guard** — Med. The aggregation must scope to the **same** cita. The view-level guard (mirroring `assert_not_over_payment`) runs inside a `select_for_update` on the cita row to avoid races. If a cita has `precio=0` (default for legacy), every charge must be rejected with HTTP 400 ("La cita no tiene precio configurado.") — this protects against accidental charging of pre-migration appointments.
- **Price editing after first charge** — Med. If the admin lowers `precio` after an `APROBADO` payment already covers more than the new `precio`, the over-payment guard starts failing. The spec should require: editing `precio` DOWN is allowed only when no `APROBADO` `PagoCita` rows exist, OR the new `precio` is `>= sum(APROBADO.monto_pagado)`. Editing UP is always allowed. Symmetrical to `Operacion.actualizar_precio`'s existing rule. **Default for v1: disallow price edits entirely (admin must cancel payments first); document the limitation; spec a future endpoint.** This keeps the change small.
- **Receipt storage collisions** — Low. `comprobantes_pagos/%Y/%m/` is already shared; existing `PagoRealizado` upload uses the same prefix. Django's storage backend handles same-name uploads by suffixing. The `pagos-fisicos-virtuales` design tested this in production.
- **State-machine coupling** — Low. Charging does not transition `estado`. Cancel/confirm flows stay untouched. No spec for `appointment-states` needs modification.
- **Notification** — Low. We do NOT fire `CLIENT_PAYMENT_CONFIRMED` because clients have no portal view for cita payments in v1 (admin-only). We do NOT fire `ADMIN_PAYMENT_PENDING_CONFIRMATION` because admin payment is APROBADO at create time (mirrors `pagos-fisicos-virtuales` admin endpoint behaviour). Future change adds the notification when client-side is enabled.
- **API surface growth** — Low-Med. Two new endpoints (`/operaciones/<id>/citas/<cita_id>/cobrar/` and `/citas-medicas-libres/<id>/cobrar/`). Both are `@action` on existing viewsets — no new viewset, no new permission class. Total backend code growth: ~150 lines.
- **Frontend state** — Med. Each parent page (`ClientAppointmentSection`, `AdminOperationDetailPage`, `ClientFreeMedicalAppointmentSection`-adjacent) needs a `registerAppointment`, `isRegisteringAppointment`, `registerAppointmentError` triplet and a new `registerAppointmentModalOpen` flag. The modal itself is reused (no new component). ~80 LOC across three files.
- **Client detail payload** — Low. Adding `precio`, `saldoPendiente`, `paymentsCount`, `canCharge` to both appointment payload helpers (`_appointment_item`, `_free_client_appointment_item`) is additive and types-friendly (`AdminPaymentQuota` already declares the same fields with similar semantics).

## Ready for Proposal

**Yes.** The orchestrator should run `sdd-propose` next.

Findings to feed into the proposal:

- Capability name suggestion: `appointment-payment` (mirrors `payment-physical-virtual`).
- Data model: new `PagoCita` table in `backend/billing/models.py` with two nullable FKs (`cita_medica`, `cita_cliente_libre`), `metodo_pago` + breakdown + receipt reused from `pagos-fisicos-virtuales`.
- Two new admin endpoints (AdminRequired + branch isolation): one on `OperacionesViewSet` (`/operaciones/<id>/citas/<cita_id>/cobrar/`), one on `FreeMedicalAppointmentViewSet` (`/citas-medicas-libres/<id>/cobrar/`).
- Two `precio` columns (default 0) on `CitaMedica` and `CitaClienteLibre`, both optional in the reservation serializers so legacy callers still work.
- Admin-only; client self-service explicitly out of scope (with a clean seam).
- Over-payment guard analogous to `assert_not_over_payment`, but scoped to the cita and to `cita.precio`.
- Frontend reuses `AdminRegisterPaymentModal` with a synthetic `AdminPaymentQuota`-shaped prop. New "Cobrar cita" button in three list contexts.

Open UX micro-decision to defer to `sdd-design`:

- Header copy in the modal: keep "Cuota N" (zero modal changes) or add a `headerSubtitle` prop and show "Cita 0042 · Sesión #1" (5-line modal change).
