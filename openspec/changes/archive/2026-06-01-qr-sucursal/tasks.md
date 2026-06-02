# Tasks: QR de Pago por Sucursal

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120–180 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Migration (Schema + Data)

- [x] 1.1 Create schema migration `XXXX_add_sucursal_to_configuracion_pago_qr` in `backend/billing/migrations/` — add `sucursal = FK(Sucursal, null=True, blank=True)` and `UniqueConstraint(fields=["sucursal"], name="uniq_config_qr_sucursal")` to `ConfiguracionPagoQR`
- [x] 1.2 Create data migration `XXXX_migrate_global_qr_to_principal_branch` in `backend/billing/migrations/` — if any `ConfiguracionPagoQR` record exists, set its `sucursal` to the `Sucursal` where `es_principal=True`; if none exists, leave `sucursal=null`

## Phase 2: Core Implementation

- [x] 2.1 Add `sucursal = models.ForeignKey("catalogs.Sucursal", null=True, blank=True, on_delete=models.SET_NULL)` to `ConfiguracionPagoQR` in `backend/billing/models.py` with `UniqueConstraint(fields=["sucursal"], name="uniq_config_qr_sucursal")` in Meta
- [x] 2.2 Register `ConfiguracionPagoQR` in `backend/billing/admin.py` with `list_display`, `list_filter`, and readonly `sucursal` field — use `get_queryset` to filter by admin's branch via `get_user_branch`
- [x] 2.3 Add `sucursal` field to `ConfiguracionPagoQRSerializer` in `backend/config/api/serializers/payments.py` — expose as `PrimaryKeyRelatedField(read_only=True)` or regular FK field
- [x] 2.4 Update `PagosViewSet.list` in `backend/config/api/viewsets/payments.py` (line 94): change `ConfiguracionPagoQR.objects.order_by("-updated_at").first()` to `ConfiguracionPagoQR.objects.filter(sucursal=branch).first()`
- [x] 2.5 Update `PagosViewSet.update_qr_config` in `backend/config/api/viewsets/payments.py` (line 138): change unscoped query to `ConfiguracionPagoQR.objects.filter(sucursal=branch).first()` and set `config.sucursal = branch` before saving
- [x] 2.6 Update `client_payments` in `backend/config/client_api_views.py` (line 691): change `ConfiguracionPagoQR.objects.order_by("-updated_at").first()` to filter by `request.cliente.sucursal_registro` — return 404 if client has no branch assigned

## Phase 3: Testing

- [ ] 3.1 Test: Create two `ConfiguracionPagoQR` records with different `sucursal` values — second create with same `sucursal` raises `IntegrityError` (unique constraint)
- [ ] 3.2 Test: Call `GET /cliente/pagos/` as a client with `sucursal_registro=null` — response is HTTP 404 with `{"detail": "No branch assigned to user"}`
- [ ] 3.3 Test: Call `GET /cliente/pagos/` as a client with `sucursal_registro=SucursalA` — response contains QR config for Sucursal A only
- [ ] 3.4 Test: Admin of Sucursal A calls `GET /pagos/` — `paymentQrConfig` shows only Sucursal A's QR config