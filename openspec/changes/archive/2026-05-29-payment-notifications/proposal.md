# Proposal: payment-notifications

## Intent

Close notification gaps in the payment workflow. Currently, admins are not alerted when clients submit new payments, and clients are not notified when their payments are cancelled or reverted to pending. This change adds the missing notification triggers without modifying the existing payment verification logic.

## Scope

### In Scope
- Add `CLIENT_PAYMENT_CANCELLED` notification type
- Send admin notification when client creates a new payment (PENDIENTE state)
- Send client notification when payment transitions to: APROBADO, RECHAZADO, CANCELADO, or PENDIENTE

### Out of Scope
- Changes to `PagosViewSet.update()` business logic for verification states
- Modifications to `CuotaPlanPago` model
- Frontend changes to notification display

## Capabilities

### New Capabilities
- `payment-notification-triggers`: Automatic notifications for payment state transitions — admin gets alerted on new submissions; client gets alerted on all status outcomes
- `client-payment-cancelled`: New notification type sent to client when their payment is set to CANCELADO state

### Modified Capabilities
- None

## Approach

Inject notification calls into existing payment service paths — no new service layer needed.

1. **Add type**: Add `CLIENT_PAYMENT_CANCELLED` to `Notification.Type` enum in `notifications/models.py`
2. **Admin on new payment**: In `billing/models.py` `PagoRealizado` save(), hook a notification send when `estado_verificacion` becomes `PENDIENTE` on first create. Requires branch context — use the associated `clinica` FK.
3. **Client on status change**: In `config/api/viewsets/payments.py` `PagosViewSet.update()`, after state transitions to APROBADO/RECHAZADO/CANCELADO/PENDIENTE, call `create_notification()` with the appropriate type.
4. **Import path**: Ensure `create_notification` is reachable from `billing/models.py` — if not, add an import or move notification trigger to `viewsets/payments.py` where the service is already imported.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `notifications/models.py` | Modified | Add CLIENT_PAYMENT_CANCELLED to Notification.Type enum |
| `config/api/viewsets/payments.py` | Modified | Add notification calls after state transitions in PagosViewSet.update() |
| `billing/models.py` | Modified | Add notification trigger when PagoRealizado enters PENDIENTE state on create |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Circular import if billing imports notifications | Low | Place notification trigger in viewsets layer instead of models if needed |
| PENDIENTE re-triggers on every save after first create | Medium | Gate on created signal or check `_state.adding` to fire only on initial create |

## Rollback Plan

1. Remove `CLIENT_PAYMENT_CANCELLED` from `Notification.Type`
2. Revert notification calls in `viewsets/payments.py` and `billing/models.py`
3. No database migration needed — notification types are application-level enums

## Dependencies

- `notifications/services.py`: `create_notification()` function must be importable from payment code paths
- No external dependencies

## Success Criteria

- [ ] Admin receives `ADMIN_PAYMENT_PENDING_CONFIRMATION` when a client submits a new payment
- [ ] Client receives `CLIENT_PAYMENT_CONFIRMED` when admin sets payment to APROBADO
- [ ] Client receives `CLIENT_PAYMENT_REJECTED` when admin sets payment to RECHAZADO
- [ ] Client receives `CLIENT_PAYMENT_CANCELLED` when admin sets payment to CANCELADO
- [ ] Client receives notification when payment reverts to PENDIENTE state
- [ ] No circular imports or runtime errors in payment code paths