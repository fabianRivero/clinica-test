# Tasks: citas-pagos

## Review Workload Forecast

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Work Units

| Unit | Goal | PR | Focused test command |
|------|------|----|----------------------|
| 1 | Backend data layer | PR 1 | `python manage.py test billing.tests.test_admin_register_appointment_payment.PagoCitaModelTests -v 2` |
| 2 | Backend endpoints + serializers + tests | PR 2 | `python manage.py test billing.tests.test_admin_register_appointment_payment config.tests.test_admin_cobrar_cita_endpoint -v 2` |
| 3 | Frontend modal + types + API helper | PR 3 | `cd frontend/aesthetic-clinic && npm run lint && npx tsc --noEmit` |
| 4 | Page wiring + Playwright smoke | PR 4 | `cd frontend/aesthetic-clinic && npx playwright test admin-cobrar-cita --reporter=line` |

Rollback: PR 1 — revert (no dep). PR 2 — model + `precio` stay, endpoints gone. PR 3 — pages compile, endpoints untouched. PR 4 — modal uncalled. Harness: PR 1/2 = N/A; PR 3 = lint+tsc; PR 4 = Playwright + dev backend (FISICO happy path on `CitaMedica`).

## Phase 1 — Backend Data Layer (PR 1)

- [x] 1.1 Add `precio = DecimalField(default=0, validators=[MinValueValidator(0)])` to `CitaMedica` and `CitaClienteLibre` in `backend/operations/models.py`.
- [x] 1.2 Append `PagoCita` to `backend/billing/models.py` near `PagoRealizado`: two nullable FKs, XOR `CheckConstraint`, FK indexes, `db_table="pagos_citas"`.
- [x] 1.3 Add shared `_validate_metodo_pago_amounts` so `PagoCita.clean()` and `PagoRealizado.clean()` stay in lock-step for VIRTUAL/FISICO/MIXTO.
- [x] 1.4 Implement `PagoCita.clean()` enforcing XOR and delegating to the helper.
- [x] 1.5 Generate `backend/billing/migrations/0010_cita_precio_and_pago_cita.py` — `AddField` on both cita tables + `CreateModel("PagoCita")`; no backfill.
- [x] 1.6 Add `assert_cita_in_user_branch(request, cita)` and `assert_not_over_cita_payment(cita, new_amount)` to `backend/billing/validators.py`.
- [x] 1.7 `PagoCitaModelTests` — XOR rule, VIRTUAL/FISICO/MIXTO, receipt under `comprobantes_citas/YYYY/MM/`.
- [x] 1.8 `ValidatorsTests` — branch isolation silent/403, over-payment accept/reject.

## Phase 2 — Backend Serializers + Endpoints (PR 2)

- [x] 2.1 Add `PagoCitaCreateSerializer` (write) + `PagoCitaSerializer` (read) to `backend/config/api/serializers/payments.py`; receipt optional regardless of method.
- [x] 2.2 Extend `_appointment_item` / `_free_client_appointment_item` and `_admin_client_queryset` prefetch in `backend/config/api/viewsets/clientes.py` to expose `precio`, `saldoPendiente`, `pagos_count`, `pagos[]`.
- [x] 2.3 Add `cobrar_cita` `@action` on client-detail `OperacionesViewSet`: `select_for_update`, branch isolation, `precio==0` reject, terminal-state reject, over-payment guard, create as `APROBADO`.
- [x] 2.4 Add `cobrar` `@action` on `FreeMedicalAppointmentViewSet` mirroring 2.3.
- [x] 2.5 Extend `_appointment_item` in `backend/config/client_api_views.py` with the four new fields.

## Phase 3 — Backend Tests (PR 2)

- [x] 3.1 `EndpointTests` — FISICO/VIRTUAL/MIXTO happy paths on both endpoints, MIXTO mismatch → 400, `precio=0` → 400, `CANCELADA`/`NO_ASISTIO` → 400, over-payment → 400, cross-branch → 403.
- [x] 3.2 `ReadPayloadTests` — APROBADO row → correct `saldoPendiente` + `pagos_count`; cancellation preserves rows and rejects new cobrar.
- [x] 3.3 `ReceiptPathTests` — file lands under `media/comprobantes_citas/YYYY/MM/`, never `comprobantes_pagos/`.

## Phase 4 — Frontend Foundation (PR 3)

- [x] 4.1 Add `AdminAppointmentPayment`, `AdminAppointment`, payload/response types to `frontend/aesthetic-clinic/src/types/admin.ts`.
- [x] 4.2 Extend `ClientAppointment` in `frontend/aesthetic-clinic/src/types/common.ts` with optional `precio`, `saldoPendiente`, `pagos_count`, `pagos`.
- [x] 4.3 Add `registerAdminAppointmentPayment` + `registerAdminFreeAppointmentPayment` in `frontend/aesthetic-clinic/src/services/api/admin.ts`, reusing the multipart builder.
- [x] 4.4 Create `frontend/aesthetic-clinic/src/components/admin/AdminRegisterAppointmentPaymentModal.tsx` — parameter variant; disabled when `precio == 0 || saldoPendiente == 0`; header `<patient> | Cita <datetime>`.

## Phase 5 — Frontend Wiring + Verification (PR 4)

- [x] 5.1 Add "Cobrar cita" button in `ClientAppointmentSection.tsx`, enabled when `precio > 0 && estado not in {CANCELADA, NO_ASISTIO}`; refreshes cita payload on success.
- [x] 5.2 Same wiring in `AdminOperationDetailPage.tsx`.
- [x] 5.3 Same wiring for the free variant in `ClientFreeMedicalAppointmentSection.tsx`.
- [x] 5.4 Add Playwright `admin-cobrar-cita.spec.ts` — FISICO happy path on `CitaMedica`: open detail → click → submit no receipt → assert toast + refreshed `pagos[]`.
