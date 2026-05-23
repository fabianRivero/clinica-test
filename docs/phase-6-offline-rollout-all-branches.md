# Fase 6 — Rollout global (todas las sucursales) para verificación tablet online/offline

## Objetivo
Activar y operar de forma estable los métodos de verificación por tablet (online y offline) en **todas las sucursales**, con monitoreo diario y protocolo de resolución de incidencias.

## Decisión de alcance
- El método de tablet **online** queda habilitado para cualquier sucursal con kiosko activo.
- El método de tablet **offline** queda habilitado para cualquier sucursal con kiosko activo y snapshot local válido.
- No se restringe funcionalidad por sucursal en runtime; solo por permisos de sesión/kiosko y estado de la cita.

## Checklist de despliegue por sucursal
1. Confirmar que la sucursal tiene al menos un `TabletKiosko` activo.
2. Validar login kiosko + login cliente en modo online.
3. Validar carga de snapshot del día.
4. Forzar desconexión y validar cola offline.
5. Reconectar y validar sincronización (`accepted/duplicate/conflict/rejected`).
6. Validar visibilidad de conflictos en admin.
7. Validar resolución manual de conflictos por admin con motivo.

## Monitoreo operativo diario (primeras 2 semanas)
- Consultar `GET /api/admin/citas/offline/metricas/?days=1` por la mañana y cierre.
- Alertar si:
  - `conflictRate > 0.05`
  - `rejectRate > 0.02`
  - pendientes sin sincronizar > 24h

## Protocolo de incidentes
1. Si hay cola creciente de pendientes:
   - revisar conectividad del dispositivo,
   - confirmar sesión kiosko activa,
   - reintentar sync.
2. Si hay conflictos recurrentes:
   - revisar operación concurrente en múltiples tablets,
   - resolver desde endpoint admin,
   - registrar causa raíz.
3. Si hay rechazos por payload:
   - revisar versión frontend y contrato API,
   - bloquear temporalmente kiosk desactualizado.

## Criterios de cierre de Fase 6
- Todas las sucursales operativas con tablet online.
- Todas las sucursales con fallback offline funcional.
- Conflictos resueltos dentro de SLA definido por operación.
- Reporte semanal de métricas sin degradación sostenida.
