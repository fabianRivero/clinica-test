# Tasks: payment-notifications

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~50-70 lines |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full implementation | PR 1 | All 3 phases in one PR — budget well under limit |

## Phase 1: Foundation — Add New Notification Types

- [x] 1.1 Add `CLIENT_PAYMENT_CANCELLED = "CLIENT_PAYMENT_CANCELLED"` to `Notification.Type` enum in `backend/notifications/models.py` (after line 15, after `CLIENT_PAYMENT_REJECTED`)
- [x] 1.2 Add `CLIENT_PAYMENT_PENDING_REVERSION = "CLIENT_PAYMENT_PENDING_REVERSION"` to `Notification.Type` enum in `backend/notifications/models.py` (after `CLIENT_PAYMENT_CANCELLED`)

## Phase 2: Core Implementation

### 2.1 Admin notification on new payment (client_api_views.py)

- [x] 2.1.1 Add imports in `backend/config/client_api_views.py`: `from notifications.models import Notification` and `from notifications.services import create_notification, admins_for_specialist_branch`
- [x] 2.1.2 After `PagoRealizado.objects.create()` at line 748, add admin notification block using `admins_for_specialist_branch(sucursal)` with type `Notification.Type.ADMIN_PAYMENT_PENDING_CONFIRMATION`, title `"Nuevo pago pendiente de revisión"`, message referencing client name and amount

### 2.2 Client notification on CANCELADO state (payments.py)

- [x] 2.2.1 In `backend/config/api/viewsets/payments.py`, add `CANCELADO` branch after line 219 in `PagosViewSet.update()`, calling `create_notification()` with type `Notification.Type.CLIENT_PAYMENT_CANCELLED`, title `"Pago cancelado"`, message `"Tu pago fue cancelado por administracion. Contacta a administracion para mas detalles."`
- [x] 2.2.2 Add `PENDIENTE` reversion branch after the RECHAZADO block, guarding on `old_state != PENDIENTE` before sending, using type `Notification.Type.CLIENT_PAYMENT_PENDING_REVERSION`, title `"Pago vuelto a pendiente"`, message `"Tu pago fue vuelto a estado pendiente por administracion."`

## Phase 3: Verification

- [x] 3.1 Verify `Notification.Type` enum imports correctly in `payments.py` and `client_api_views.py`
- [x] 3.2 Verify `admins_for_specialist_branch` is importable from `client_api_views.py` (no circular import)
- [x] 3.3 Verify `CLIENT_PAYMENT_CANCELLED` notification fires when `PagosViewSet.update()` transitions payment to CANCELADO
- [x] 3.4 Verify `CLIENT_PAYMENT_PENDING_REVERSION` notification fires only when payment reverts FROM non-PENDIENTE TO PENDIENTE (not on initial creation)
- [x] 3.5 Verify admin `ADMIN_PAYMENT_PENDING_CONFIRMATION` fires after `PagoRealizado.objects.create()` in client payment submission path
- [x] 3.6 Verify CANCELADO notification does NOT fire on initial payment creation (only on admin transition via `PagosViewSet.update()`)

(End of file - total 47 lines)