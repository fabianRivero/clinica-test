# Contrato v2 de verificacion de citas

## Fecha
- 2026-05-21

## Objetivo
Estandarizar la representacion de verificacion de citas con campos explicitos y retirar dependencias funcionales del modelo legacy de confirmacion biometrica.

## Campos canonicos

### Agenda admin (`/api/admin/dashboard/agenda/`)
- `appointmentStatus`: `programada | pendiente_verificacion | confirmada`
- `verificationStatus`: `pendiente | verificada | no_requerida`
- `verificationMethod`: `biometria | qr | manual | otro | null`

### Citas cliente (dashboard/reservas/disponibilidad)
- `verificationStatus`: `pendiente | verificada | no_requerida`
- `verificationMethod`: `biometria | qr | manual | otro | null`

## Legacy retirado del payload cliente
Estos campos ya no son parte del contrato cliente:
- `confirmationStatus`
- `confirmationLabel`
- `biometric`

## Notas de compatibilidad
- En agenda admin se mantiene `status` legacy para compatibilidad transitoria con consumidores antiguos.
- Frontend usa los campos canonicos como fuente de verdad para render.

## Criterios de aceptacion de contrato
1. Todos los endpoints cliente de citas incluyen `verificationStatus` y `verificationMethod`.
2. Ningun endpoint cliente de citas devuelve `confirmationStatus`, `confirmationLabel` o `biometric`.
3. Agenda admin expone `appointmentStatus`, `verificationStatus` y `verificationMethod`.
