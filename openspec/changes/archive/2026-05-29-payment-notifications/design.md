# Design: payment-notifications

## Technical Approach

Inject notification triggers into the two existing payment code paths — the admin `PagosViewSet.update()` for state transitions, and `client_api_views.py` for new payment submissions. No new service layer, no signals, no model-layer request context needed. The `PagoRealizado.save()` is NOT the right place for the client-submission notification because it lacks request/user context and `_state.adding` alone cannot distinguish update-from-pending vs re-submission-from-rejected.

## Architecture Decisions

### Decision: Admin notification trigger placement (model vs view layer)

**Choice**: Place in `client_api_views.py` after `PagoRealizado.objects.create()`, not in `PagoRealizado.save()`.

**Alternatives considered**:
- `PagoRealizado.save()` — rejected because it has no access to `request.user` for `created_by_id` and cannot determine if the request came from a client API call vs admin panel
- Django `post_save` signal — same problem as save(), no request context

**Rationale**: The view layer has `request.user` (the client). We know the payment is new because we just called `.create()`. Branch context is available via `payment.cuota.operacion.paciente.sucursal_registro`. Direct placement is explicit, debuggable, and matches the pattern already used in `PagosViewSet.update()`.

---

### Decision: PENDIENTE detection strategy (first-create guard)

**Choice**: In `client_api_views.py`, place notification call directly after the `.create()` call — no guard needed because there is no code path where we call `.create()` but don't want the notification.

**Alternatives considered**:
- `_state.adding` in `PagoRealizado.save()` — rejected because `.create()` calls `save()` internally, so every create goes through save(); adding the notification there would fire for both new creates and updated records re-set to PENDIENTE (the `editable_payment` branch on line 729)
- Custom field `notification_sent` boolean flag — rejected as unnecessary state

**Rationale**: The `editable_payment` branch (line 729) calls `.save()` on an existing object and sets `estado_verificacion = PENDIENTE`. This is a re-submission, not a new payment. Putting the notification in `save()` would fire for both paths, causing duplicates. The notification in `PagosViewSet.update()` for PENDIENTE reversion uses a state-change guard (`old_state != new_state`).

---

### Decision: Branch/sucursal resolution for admin notification

**Choice**: Use `payment.cuota.operacion.paciente.sucursal_registro` to get the `Sucursal` FK for the notification `branch` field. No new queries — `PagoRealizado` is already prefetched with `select_related`.

**Alternatives considered**:
- Add a direct `sucursal` FK to `PagoRealizado` — rejected, would require migration and doesn't solve the need for any other payment code paths
- Query `Operacion` for `sucursal` — unnecessary, the relation is already accessible through the existing chain

**Rationale**: `Operacion` has no direct `Sucursal` FK (confirmed from codebase reading). The spec explicitly states to use `paciente.sucursal_registro`. This chain is already covered by the `select_related` in the view's queryset.

---

## Data Flow

### Path 1: Admin notification on new client payment submission

```
client_api_views.py
    └─ PagoRealizado.objects.create(..., estado_verificacion=PENDIENTE)
           │
           ▼
    create_notification(
        recipient=Admin users for that branch,
        type=ADMIN_PAYMENT_PENDING_CONFIRMATION,
        branch=sucursal_registro,
        source_entity_id=payment.id
    )
```

### Path 2: Client notification on admin state transition (APROBADO / RECHAZADO / CANCELADO / PENDIENTE)

```
PagosViewSet.update()
    └─ payment.estado_verificacion = new_state
    └─ payment.save()
           │
           ▼
    create_notification(
        recipient=payment.cuota.operacion.paciente.usuario,
        type={CLIENT_PAYMENT_CONFIRMED | CLIENT_PAYMENT_REJECTED | CLIENT_PAYMENT_CANCELLED | CLIENT_PAYMENT_PENDING_REVERSION},
        branch=payment.cuota.operacion.paciente.sucursal_registro,
        source_entity_id=payment.id
    )
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/notifications/models.py` | Modify | Add `CLIENT_PAYMENT_CANCELLED` to `Notification.Type` enum |
| `backend/config/api/viewsets/payments.py` | Modify | Add CANCELADO and PENDIENTE-reversion client notifications in `update()` |
| `backend/config/client_api_views.py` | Modify | Add admin notification after new `PagoRealizado.objects.create()` |

## Interfaces / Contracts

### New Notification Type

```python
# backend/notifications/models.py
class Notification(models.Model):
    class Type(models.TextChoices):
        # ... existing types ...
        CLIENT_PAYMENT_CANCELLED = "CLIENT_PAYMENT_CANCELLED"
```

### Admin Notification Call (client_api_views.py)

```python
# After line 748 in client_api_views.py
from notifications.services import create_notification
from notifications.models import Notification
from notifications.services import admins_for_specialist_branch

# ... existing code through payment creation ...

admin_notification_types = [Notification.Type.ADMIN_PAYMENT_PENDING_CONFIRMATION]
sucursal = payment.cuota.operacion.paciente.sucursal_registro
for admin in admins_for_specialist_branch(sucursal):
    create_notification(
        recipient=admin,
        branch=sucursal,
        type=Notification.Type.ADMIN_PAYMENT_PENDING_CONFIRMATION,
        title="Nuevo pago pendiente de revisión",
        message=f"El cliente {payment.cuota.operacion.paciente.usuario.get_full_name()} "
                f"envio un comprobante de Bs {payment.monto_pagado}.",
        action_url="/admin/pagos",
        source_event="payment.pending_submission",
        source_entity_type="payment",
        source_entity_id=payment.id,
        created_by_type="client",
        created_by_id=request.user.id,
    )
```

### PagosViewSet.update() — Add CANCELADO and PENDIENTE branches

```python
# In PagosViewSet.update(), after line 219 (after existing APROBADO/RECHAZADO blocks)
elif status_value == PagoRealizado.EstadoVerificacion.CANCELADO:
    create_notification(
        recipient=payment.cuota.operacion.paciente.usuario,
        branch=payment.cuota.operacion.paciente.sucursal_registro,
        type=Notification.Type.CLIENT_PAYMENT_CANCELLED,
        title="Pago cancelado",
        message="Tu pago fue cancelado por administracion. Contacta a administracion para mas detalles.",
        action_url="/cliente/pagos",
        source_event="payment.cancelled",
        source_entity_type="payment",
        source_entity_id=payment.id,
        created_by_type="admin",
        created_by_id=request.user.id,
    )
elif status_value == PagoRealizado.EstadoVerificacion.PENDIENTE:
    # Only fire if moving FROM a non-PENDIENTE state (reversion)
    create_notification(
        recipient=payment.cuota.operacion.paciente.usuario,
        branch=payment.cuota.operacion.paciente.sucursal_registro,
        type=Notification.Type.CLIENT_PAYMENT_CONFIRMED,  # reuse or create new type
        title="Pago vuelto a pendiente",
        message="Tu pago fue vuelto a estado pendiente por administracion.",
        action_url="/cliente/pagos",
        source_event="payment.reverted_to_pending",
        source_entity_type="payment",
        source_entity_id=payment.id,
        created_by_type="admin",
        created_by_id=request.user.id,
    )
```

## Testing Strategy

**Note**: Backend has NO existing tests for this module. All tests must be created.

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `Notification.Type` enum has new type | Direct import + assert in choices |
| Unit | `admins_for_specialist_branch()` returns correct admins | Mock `Usuario.objects.filter()` |
| Integration | Admin notification sent after `PagoRealizado.objects.create()` in client view | `ClientAPITestCase` with authenticated client, mock `create_notification`, assert called with correct args |
| Integration | Client notification sent for each state transition (APROBADO, RECHAZADO, CANCELADO, PENDIENTE) | `APITestCase` with admin auth, mock `create_notification`, call `update()` with each status, assert called with correct type |
| Integration | CANCELADO notification NOT sent on first create (only on admin transition) | Verify `create_notification` not called when payment created in client view |

## Migration / Rollout

No database migration required. `Notification.Type` is a Django `TextChoices` enum — application-level only. Deploy as a standard feature release.

## Open Questions

- [ ] **PENDIENTE reversion notification type**: The spec says "notification to inform the client" but does not define the type. `CLIENT_PAYMENT_CONFIRMED` is semantically wrong for a reversion. Should we use a new type like `CLIENT_PAYMENT_PENDING_REVERSION`, or is reusing an existing type acceptable? **Recommend**: create `CLIENT_PAYMENT_PENDING_REVERSION` in the same change to keep types precise.
- [ ] **Existing tests**: Since there are no existing tests for payments module, should we create a base test class first, or write tests only for the new notification logic?