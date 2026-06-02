# Design: QR de Pago por Sucursal

## Technical Approach

Add a nullable FK `sucursal` to `ConfiguracionPagoQR` with `unique=True`, making each branch's QR configuration independent. Three surfaces must change:

1. **Client API** (`client_payments`): filter QR by `request.user.sucursal_id`
2. **Admin ViewSet** (`PagosViewSet`): scope QR reads/writes to admin's branch
3. **Serializer**: expose `sucursal` field in `ConfiguracionPagoQRSerializer`

A data migration runs after the schema migration to attach any pre-existing global QR to the principal branch (`es_principal=True`).

---

## Architecture Decisions

### Decision: FK `null=True, blank=True, unique=True`

| Option | Tradeoff |
|--------|----------|
| `null=False` | Forces every existing row to acquire a branch immediately at migration time; risky if no principal branch exists |
| **`null=True, blank=True, unique=True`** | Existing global QR can remain null during migration; new records require branch; prevents multiple QR configs per branch |

**Choice**: `null=True, blank=True, unique=True`
**Rationale**: Aligns with how `GastoSucursal.sucursal` (PROTECT, non-null) and `Cliente.sucursal_registro` (SET_NULL, nullable) are modeled in the codebase. Backward compatibility without forcing immediate data cleanup.

---

### Decision: Backward Compatibility for Existing Global QR

There is exactly one global `ConfiguracionPagoQR` record today (singleton-like behavior via `order_by("-updated_at").first()`). After migration:
- Records with `sucursal=null` are invisible to client API (returns 404 for users without branch)
- Admin ViewSet shows only branch-scoped records via `get_user_branch`

**Choice**: Data migration attaches existing global QR to principal branch (`es_principal=True`). If no principal branch exists, QR is set to null (no branch QR visible until manually configured).
**Alternatives considered**: Delete global QR; require admin to re-create per branch
**Rationale**: Zero data loss — existing clinic QR is preserved at the principal branch.

---

### Decision: Admin Horizontal Filtering

`PagosViewSet.list()` already uses `get_user_branch(request)` (line 42 in `payments.py`). QR config in the response comes from `ConfiguracionPagoQR.objects.order_by("-updated_at").first()` — this is currently unscoped.

**Choice**: Add `.filter(sucursal=branch)` when fetching QR config in both `list()` and `update_qr_config()`. Apply ` UniqueConstraint(fields=["sucursal"], name="uniq_config_qr_sucursal")` in Meta.

**Alternative considered**: No scope in admin — but the proposal explicitly requires admin horizontal filtering.
**Rationale**: Consistent with how all other admin viewsets in this codebase scope data to branch (e.g. `PagosViewSet.list` filters payments by branch).

---

## Data Flow

```
Client Request
    │
    ▼
GET /cliente/pagos/  (client_api_views.py → client_payments)
    │
    │  request.user.cliente → usuario.sucursal
    ▼
ConfiguracionPagoQR.objects.filter(sucursal=user.sucursal).first()
    │
    ▼
_payment_qr_config_item(config)  →  JSON response
```

```
Admin Request
    │
    ▼
GET /pagos/  (viewsets/payments.py → PagosViewSet.list)
    │
    │  get_user_branch(request) → branch
    ▼
ConfiguracionPagoQR.objects.filter(sucursal=branch).first()
    │
    ▼
paymentQrConfig in Response
```

```
Admin POST /pagos/configuracion-qr/
    │
    │  same branch scoping in update_qr_config action
    ▼
config.sucursal = branch  (implicit save)
```

---

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/billing/models.py` | Modify | Add `sucursal = FK(Sucursal, null=True, blank=True)` + `UniqueConstraint` to `ConfiguracionPagoQR` |
| `backend/billing/admin.py` | Modify | Register `ConfiguracionPagoQR` with list filter and readonly branch |
| `backend/billing/migrations/XXXX_qr_sucursal_fk.py` | Create | Schema: add `sucursal` FK (nullable, unique) |
| `backend/billing/migrations/XXXX_qr_sucursal_data.py` | Create | Data: migrate global QR to principal branch |
| `backend/config/api/serializers/payments.py` | Modify | Add `sucursal` field to `ConfiguracionPagoQRSerializer` |
| `backend/config/api/viewsets/payments.py` | Modify | Scope QR config lookup by `get_user_branch(request)` |
| `backend/config/client_api_views.py` | Modify | Scope QR lookup by `request.user.cliente.sucursal_registro` |

---

## Interfaces / Contracts

### Serializer Change (`ConfiguracionPagoQRSerializer`)

```python
class ConfiguracionPagoQRSerializer(serializers.ModelSerializer):
    sucursal = serializers.PrimaryKeyRelatedField(
        queryset=Sucursal.objects.filter(activa=True),
        required=False,
        allow_null=True,
    )
    # existing fields...
```

### Client API — existing contract augmented

The `paymentQrConfig` object in `GET /cliente/pagos/` gains a `sucursal` field:

```json
{
  "paymentQrConfig": {
    "hasQr": true,
    "qrImageUrl": "https://...",
    "instructions": "...",
    "sucursal": 1
  }
}
```

**Existing response shape is backward compatible** — only new clients see `sucursal`.

### Admin API — QR config scoped

`GET /pagos/` returns `paymentQrConfig` filtered to the admin's branch. `POST /pagos/configuracion-qr/` creates/updates only the admin's branch config.

---

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `ConfiguracionPagoQR.sucursal` FK and unique constraint | Django ORM tests: create with same `sucursal` raises IntegrityError |
| Unit | `client_payments` scopes QR by `user.cliente.sucursal_registro` | Mock `request.user.cliente.sucursal_registro`, assert correct queryset filter |
| Unit | `PagosViewSet` scopes QR by `get_user_branch` | Mock request + user branch, assert config is filtered |
| Integration | Data migration assigns global QR to principal branch | Test migration on copy of production snapshot |
| Integration | Client without branch gets 404 for QR | Request as client with `sucursal=null` |

---

## Migration / Rollout

1. **Schema migration** (`XXXX_qr_sucursal_fk.py`): Add `sucursal` FK column as nullable, add unique constraint index
2. **Data migration** (`XXXX_qr_sucursal_data.py`): Run AFTER schema — find the single existing `ConfiguracionPagoQR` record (if any) and set `sucursal` to the `Sucursal` where `es_principal=True`; if no principal, leave null
3. **No feature flags needed** — FK is nullable, so client API returns 404 only for null-branch users (safe, matches spec)

**Rollback**: Reverse migrations in reverse order — data migration first (restore FK to null), then schema.

---

## Open Questions

- [ ] Does `Cliente.usuario` always have a `sucursal` (i.e., can `request.user.cliente.sucursal_registro` be safely accessed, or should we guard with a hasattr)? The spec says 404 if no branch — check that `Usuario.sucursal` (accounts model) is never null for clients.
- [ ] Should `admin_update_payment_qr_config` in `api_views.py` also scope by branch? It is a super-admin endpoint — current behavior is global singleton. The proposal implies it stays global for super-admins; confirm with team.
