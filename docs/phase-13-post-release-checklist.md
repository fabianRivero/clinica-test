# Fase 13 - Checklist operativo post-release

## Ventana sugerida
- Primeras 24 horas
- Primeros 7 dias

## 1) Smoke checks funcionales
- Admin dashboard agenda carga con estado de verificacion.
- Admin cliente detalle muestra columna "Verificacion" correctamente.
- Cliente dashboard muestra metodo de verificacion.
- Cliente reservas muestra badge por `verificationStatus`.

## 2) Verificacion de contrato API
- `/api/client/dashboard/`:
  - incluye `verificationStatus`, `verificationMethod`
  - no incluye `confirmationStatus`, `confirmationLabel`, `biometric`
- `/api/client/reservas/`:
  - incluye `verificationStatus`, `verificationMethod`
  - no incluye `confirmationStatus`, `confirmationLabel`, `biometric`
- `/api/admin/dashboard/agenda/`:
  - incluye `appointmentStatus`, `verificationStatus`, `verificationMethod`

## 3) Monitoreo de errores
- Revisar errores frontend por parseo de campos de citas.
- Revisar errores backend 5xx en endpoints de agenda/reservas/dashboard.
- Revisar picos de soporte relacionados a estados de verificacion.

## 4) Go/No-Go para fase siguiente
- GO si:
  - no hay regresiones funcionales
  - no hay consumidores rompiendo por contrato v2
  - sin errores severos durante 7 dias
- NO-GO si:
  - hay dependencias ocultas de campos legacy
  - hay inconsistencias entre `verificationStatus` y `verificationMethod`

## 5) Evidencia minima para cierre
- Capturas de UI de admin/cliente.
- Respuestas JSON de endpoints clave.
- Resumen de incidencias y acciones correctivas.
