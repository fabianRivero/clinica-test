# Phase 5 — Rollout y operación (multi-sucursal)

Date: 2026-05-22

## Objetivo
Desplegar gestión de sucursales de forma controlada, con monitoreo y reversibilidad.

## Feature flag
Frontend:
- `VITE_ENABLE_BRANCH_MANAGEMENT=true` habilita módulo de sucursales.
- `false` oculta la navegación y redirige `/admin/sucursales` a `/admin`.

## Plan de despliegue recomendado
1. Deploy backend (endpoints y validaciones) con flag frontend en `false`.
2. Ejecutar smoke tests backend en entorno de staging.
3. Habilitar flag solo para staging (`true`) y validar UX completa.
4. Habilitar flag en producción de forma gradual.

## Smoke checklist post-deploy
- [ ] Admin general ve menú “Sucursales”.
- [ ] Admin sucursal NO ve menú “Sucursales”.
- [ ] Crear sucursal funciona con idempotencia.
- [ ] Editar sucursal (ciudad/dirección) persiste cambios.
- [ ] Desactivar sucursal con pendientes muestra advertencia y exige confirmación.
- [ ] Reactivar sucursal funciona.
- [ ] Usuario admin sucursal de una sucursal inactiva recibe 403 en APIs administrativas.
- [ ] Filtros del listado funcionan: estado, ciudad, admin, sucursal.

## Métricas/observabilidad mínima
- Conteo de respuestas 403 por sucursal inactiva.
- Conteo de respuestas 409 por desactivación con pendientes.
- Tasa de errores 5xx en endpoints `/api/admin/sucursales/*`.
- Latencia p95 de listado y de endpoint de impacto.

## Plan de rollback
1. Poner `VITE_ENABLE_BRANCH_MANAGEMENT=false` (oculta módulo sin rollback de DB).
2. Mantener backend arriba para no romper dependencias existentes.
3. Revisar logs de 403/409/5xx y corregir antes de reactivar flag.
