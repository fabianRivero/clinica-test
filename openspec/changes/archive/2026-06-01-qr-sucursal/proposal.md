# Proposal: QR de Pago por Sucursal

## Intent

El modelo `ConfiguracionPagoQR` es actualmente un singleton global sin relación con `Sucursal`. El endpoint `GET /cliente/pagos/` obtiene el QR mediante `ConfiguracionPagoQR.objects.order_by("-updated_at").first()`, sin filtrar por sucursal del cliente.

**Meta**: cada sucursal tiene su propio QR de pagos, reachable desde la API del cliente.

---

## Scope

### In Scope
- Agregar FK `sucursal → Sucursal` a `ConfiguracionPagoQR`
- Endpoint `GET /cliente/pagos/` filtra por `request.user.sucursal`
- Admin de Django: QR configurable **por sucursal**
- Migración de datos: FK null-safe, QR global existente migra a sucursal principal o null

### Out of Scope
- Generación de QR dinámico (los QR ya existen como imagen/texto)
- Integración con procesador de pagos
- Nuevos endpoints más allá del cliente

---

## Capabilities

### New Capabilities
- `pago-qr-sucursal`: Cada sucursal tiene su configuración QR独立的. El endpoint cliente devuelve el QR de la sucursal del usuario autenticado.

### Modified Capabilities
- None (el singleton global no era una capability declarada — era implementación accidental)

---

## Approach

1. **Modelo**: agregar `sucursal = FK(Sucursal, null=True, unique=True)` a `ConfiguracionPagoQR`. Mantener `null=True` para backward compatibility durante migración.
2. **Queries**: modificar `GET /cliente/pagos/` para filtrar `ConfiguracionPagoQR.objects.filter(sucursal=user.sucursal).first()`
3. **Admin**: exponer campo sucursal en Admin, filtrar por sucursal logueada
4. **Migración**: data migration que asigne el QR global existente a la sucursal principal (`es_principal=True`) o marques null si no hay principal

---

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/billing/models.py` | Modified | FK `sucursal` en `ConfiguracionPagoQR` |
| `backend/config/api/viewsets/payments.py` | Modified | Filtrar por `request.user.sucursal` |
| `backend/config/api/serializers/payments.py` | Modified | Serializer expone QR de sucursal |
| `backend/config/client_api_views.py` | Modified | Vista que devuelve QR por cliente/sucursal |

---

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Clientes sin sucursal asignada → QR null | Medium | Verificar `user.sucursal` existe antes de consultar; fallback 404 si null |
| Migración de datos con QR pre-existente | Low | Data migration primero, luego schema migration |
| Admin ve QR de otras sucursales | Low | Filter horizontal en Admin |

---

## Rollback Plan

1. Revertir migración: `python manage.py migrate billing 00XX_previous`
2. Restaurar `ConfiguracionPagoQR` sin FK `sucursal`
3. Restaurar queries que usan `order_by("-updated_at").first()`

---

## Dependencies

- `Sucursal` model ya existe en `backend/catalogs/models.py`
- Requiere usuario con `sucursal` asignada — verificar en auth layer

---

## Success Criteria

- [ ] `ConfiguracionPagoQR` tiene FK `sucursal` funcional
- [ ] `GET /cliente/pagos/` devuelve el QR de la sucursal del usuario
- [ ] Admin permite editar QR por sucursal
- [ ] Migración no rompe datos existentes
- [ ] Test: cliente de Sucursal A no ve QR de Sucursal B
