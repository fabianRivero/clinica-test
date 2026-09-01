# Tasks: payment-physical-virtual

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~600-900 (backend ~450-600 incl. tests, frontend ~150-300) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | PR | Focused test command | Rollback boundary |
|------|------|----|---------------------|-------------------|
| 1a | Schema + validation + backfill migration | PR 1a | `python manage.py test billing.tests` | Revert migration 0009 + model fields |
| 1b | Read + create serializers, branch helper | PR 1a | `python manage.py test billing.tests.test_pago_realizado_create_serializer` | Revert two serializers |
| 2a | PagosViewSet admin endpoint + tests | PR 1b | `python manage.py test billing.tests.test_admin_register_payment` | Revert `@action` in viewsets/payments.py |
| 2b | Client upload refactor | PR 1b | `python manage.py test billing.tests.test_client_upload_payment_receipt` | Revert `client_upload_payment_receipt` |
| 2c | Patch 7 existing factory calls | PR 1b | `python manage.py test tests.test_quota_status_rules tests.test_operation_price_plan_update` | Revert 7 `monto_virtual=` lines |
| 3a | Client page selector + breakdown | PR 2 | `npm run lint && npx tsc --noEmit && npm run build` | Revert `ClientPaymentsPage.tsx` |
| 3b | Admin modal + service + breakdown | PR 2 | `npm run lint && npx tsc --noEmit && npm run build` | Revert `AdminPaymentsPage.tsx` + tabs |

## Phase 1: Backend — Model & Migration

- [x] 1.1 Add `MetodoPago` + 3 fields to `PagoRealizado` (+ ~20).
- [x] 1.2 Extend `clean()` with VIRTUAL/FISICO/MIXTO branches (+ ~35).
- [x] 1.3 Generate migration 0009 (3 AddFields + RunPython backfill) (+ ~70).
- [x] 1.4 Add 5 model tests (clean rules + backfill idempotency) (+ ~120).  *Implemented 11 clean tests + 6 patched factory calls.*

**Verify**: `makemigrations --dry-run --check billing` (no diff) and `python manage.py test billing.tests`. ✅

## Phase 2: Backend — Serializers & Helpers

- [x] 2.1 Expose new fields on `PagoRealizadoSerializer` (+ ~5).
- [x] 2.2 Add `PagoRealizadoCreateSerializer` write-only with `validate()` (+ ~45).
- [x] 2.3 Add `assert_cuota_in_user_branch` + `assert_not_over_payment` helpers (+ ~25).
- [x] 2.4 Add serializer derivation test (+ ~30).  *Implemented 8 create serializer tests + 2 read serializer tests.*

**Verify**: `python manage.py test billing.tests.test_pago_realizado_create_serializer tests.test_quota_status_rules`. ✅

## Phase 2 deviation note

The factory-call patch from Phase 4.3 was moved into Commit 2 of PR 1 because the new ``PagoRealizado.clean()`` rejects the historical ``PagoRealizado.objects.create(...)`` calls that don't set ``monto_virtual=monto_pagado``. Without the patch, ``tests.test_operation_price_plan_update`` fails with ``ValidationError({'monto_virtual': ...})`` from the very first row it creates. The patch sets ``metodo_pago=VIRTUAL``, ``monto_virtual=Decimal("100.00")`` and ``monto_fisico=Decimal("0")`` on all 7 factory calls (2 in ``test_quota_status_rules.py`` + 5 in ``test_operation_price_plan_update.py``). Phase 4 will need only the client-upload-related patches, if any.

**Verify**: `python manage.py test billing.tests.test_pago_realizado_create_serializer tests.test_quota_status_rules`.

## Phase 3: Backend — Admin Endpoint

- [ ] 3.1 Add `@action register_payment` on `PagosViewSet` (+ ~80).
- [ ] 3.2 Add 4 endpoint tests (happy/cross-branch/over-pay/MIXTO-mismatch) (+ ~140).
- [ ] 3.3 Add notification test (+ ~35).

**Verify**: `python manage.py test billing.tests.test_admin_register_payment billing.tests.test_admin_register_payment_notifies_branch_admins_once`.

## Phase 4: Backend — Client Upload Refactor

- [ ] 4.1 Refactor `client_upload_payment_receipt` for method + breakdown + reuse (+ ~50 net).
- [ ] 4.2 Add 5 endpoint tests (+ ~150).
- [ ] 4.3 Patch 7 factory calls to set `monto_virtual=monto_pagado` (+ ~7).

**Verify**: `python manage.py test billing.tests.test_client_upload_payment_receipt tests.test_quota_status_rules tests.test_operation_price_plan_update`.

## Phase 5: Frontend — Client Page

- [ ] 5.1 Extend `payment` TS type (+ ~10).
- [ ] 5.2 Add `paymentMethod` state + `<select>` + conditional fields (+ ~70).
- [ ] 5.3 Send new fields; render breakdown line when `paymentMethod !== 'VIRTUAL'` (+ ~25).

**Verify**: `cd frontend/aesthetic-clinic && npm run lint && npx tsc --noEmit && npm run build`.

## Phase 6: Frontend — Admin Page

- [ ] 6.1 Add `registerAdminPayment` service (+ ~20).
- [ ] 6.2 Add "Registrar pago" button + modal (+ ~110).
- [ ] 6.3 Render breakdown line; minor tabs update (+ ~25).

**Verify**: `cd frontend/aesthetic-clinic && npm run lint && npx tsc --noEmit && npm run build`.

## Phase 7: End-to-End Verification

- [ ] 7.1 `python manage.py test` (all green).
- [ ] 7.2 `npm run lint && npx tsc --noEmit && npm run build` (all green).
- [ ] 7.3 `python manage.py migrate billing 0008 --plan` (reverse callable).