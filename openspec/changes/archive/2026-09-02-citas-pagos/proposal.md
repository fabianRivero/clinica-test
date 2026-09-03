# Proposal: citas-pagos

## Intent

`CitaMedica` and `CitaClienteLibre` are now billable in admin reports but carry no price column and no payment surface — charges today live on the parent `Operacion.cuotas`. Adds admin-side charging (v1, admin-only) via a `precio` field per cita and a sibling `PagoCita` model mirroring the proven `pagos-fisicos-virtuales` flow.

## Scope

### In Scope

- `backend/billing/models.py`: new `PagoCita` with two nullable FKs (`cita_medica`, `cita_cliente_libre`) + `clean()` XOR; reuse `metodo_pago` / breakdown / `comprobante_url` (`comprobantes_citas/%Y/%m/`) / `estado_verificacion` from `pagos-fisicos-virtuales`.
- `CitaMedica` + `CitaClienteLibre` gain `precio: DecimalField(default=0, MinValueValidator(0))`. Single additive migration.
- `POST /operaciones/<id>/citas/<cita_id>/cobrar/` on `OperacionesViewSet`. `AdminRequired` + new `assert_cita_in_user_branch`.
- `POST /citas-medicas-libres/<id>/cobrar/` on `FreeMedicalAppointmentViewSet`.
- Over-payment guard analogous to `assert_not_over_payment`, scoped to `cita.precio` inside `select_for_update`; reject `precio=0` HTTP 400.
- Reject charging on `CANCELADA` / `NO_ASISTIO`; create as `APROBADO` immediately.
- Appointment serializers expose `precio`, `saldoPendiente`, `pagos_count`, `pagos[]`.
- Frontend: `AdminRegisterAppointmentPaymentModal` parameter variant (cleaner than prop-shimming — header copy + quota-number shape diverge). "Cobrar cita" button in `ClientAppointmentSection`, `AdminOperationDetailPage`, free-appointment variant.
- Django unittests: `clean()` (VIRTUAL/FISICO/MIXTO, XOR), branch isolation, over-payment, `precio=0`, cancellation cascade.

### Out of Scope

- Client self-service payment (admin-only v1; seam preserved).
- Editing `precio` after first `APROBADO` charge.
- Linking `precio` to `ServicioConfig`.
- Any change to `PagoRealizado` / `CuotaPlanPago` or appointment state machine.

## Capabilities

### New Capabilities
- `appointment-payment`: admin charges both cita types with VIRTUAL/FISICO/MIXTO + optional receipt, branch-isolated, over-payment guarded.

### Modified Capabilities
- None — `appointment-reservation-redesign` and `appointment-states` untouched at spec level.

## Approach

Approach #2 from exploration: sibling `PagoCita` table mirroring `pagos-fisicos-virtuales` 1:1 with separate `comprobantes_citas/` path. No risk to `PagoRealizado`; clean ORM scoping per FK; trivial discriminator enforcement.

## Affected Areas

| Area | Impact |
|------|--------|
| `backend/operations/models.py` | Modified — `precio` on both cita models |
| `backend/billing/models.py` | Modified — new `PagoCita` |
| `backend/billing/validators.py` | Modified — `assert_cita_in_user_branch` |
| `backend/billing/migrations/` | New — `precio` columns + `PagoCita` table |
| `backend/config/api/viewsets/operaciones.py` | Modified — `cobrar` action |
| `backend/config/api/viewsets/clientes.py` | Modified — `cobrar` action + payload helpers |
| `backend/config/api/serializers/payments.py` | Modified — write + read serializers |
| `frontend/.../components/admin/AdminRegisterAppointmentPaymentModal.tsx` | New |
| `frontend/.../pages/admin/ClientAppointmentSection.tsx`, `AdminOperationDetailPage.tsx`, `ClientFreeMedicalAppointmentSection.tsx` | Modified |
| `frontend/.../types/admin.ts`, `services/api/admin.ts` | Modified |
| `backend/billing/tests.py` | Modified |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Legacy appointments (no `precio`) get charged | Low | `precio=0` default; HTTP 400 |
| Over-payment race | Med | `select_for_update` + view-level guard |
| Receipt filename collision with `PagoRealizado` | Low | Distinct `comprobantes_citas/%Y/%m/` path |
| Admin cross-branch charge | Med | `assert_cita_in_user_branch`, 404 on mismatch |

## Rollback Plan

Revert migration (drops `precio` + `PagoCita`); remove endpoints and modal/button. **Safety net**: `precio=0` default makes the change additive — after rollback every cita becomes non-billable again; `PagoRealizado` flow untouched.

## Dependencies

None.

## Success Criteria

- [ ] Admin charges both cita types with VIRTUAL/FISICO/MIXTO + optional receipt.
- [ ] Legacy appointments stay free; HTTP 400 on attempt.
- [ ] Over-payment and cross-branch rejected.
- [ ] `saldoPendiente` and `pagos[]` visible in appointment detail.
- [ ] No regression in `test_quota_status_rules.py` / `test_operation_price_plan_update.py`.
- [ ] Django tests green.
