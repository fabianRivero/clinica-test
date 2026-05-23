# Fase 0 — Especificación funcional y técnica base para verificación offline en tablet

## 1) Objetivo
Definir de forma cerrada el comportamiento de verificación de citas en modo online y offline para tablet/web kiosk, incluyendo privacidad, auditoría, manejo de intentos, datos mínimos locales y política de conflictos para sincronización posterior.

## 2) Decisiones funcionales cerradas

### 2.1 Flujo único de negocio
Se mantiene un único flujo de negocio de verificación de cita para todos los dispositivos. Solo varía la mecánica de identificación/autenticación según conectividad.

Prioridad de métodos:
1. Biometría
2. Tablet online
3. Tablet offline
4. Manual admin (fallback)

### 2.2 Modo online
- Login directo con credenciales del cliente (sin selección previa de perfil).
- No se usa lista local de clientes del día.
- No aplica bloqueo local offline por intentos (control delegado al backend online).

### 2.3 Modo offline
- Se habilita lista local de clientes/citas del día.
- Búsqueda por CI completo ingresado por el cliente.
- La UI solo muestra CI enmascarado.
- En pantalla de validación se muestra únicamente:
  - CI enmascarado
  - Hora de cita
  - Procedimiento (si aplica)
- Se aplica control de intentos por cliente (no global), con bloqueo temporal por cliente al superar umbral.

## 3) Datos mínimos offline (snapshot diario)

### 3.1 Citas
- `appointment_id` (`rawId`)
- `operation_id` (`operationRawId`)
- `date_time` (`dateTime`)
- `status`
- `branch_id`
- `verification_status` (si está disponible)
- `verification_method` (si está disponible)

### 3.2 Cliente
- `client_id` interno
- CI para matching offline (preferible `ci_hash` + `ci_last4` para UI)

### 3.3 Operación/UI
- `procedure`
- `reserve_message` (si requerido por UX)

### 3.4 Metadatos de sincronización
- `snapshot_id`
- `schema_version`
- `server_time`

## 4) Política de conflictos e idempotencia (definición)
- Una cita puede quedar verificada una sola vez.
- Todo evento offline debe tener `event_id` UUID único e inmutable.
- El backend debe procesar sync de forma transaccional por cita para evitar dobles verificaciones por carrera.
- Resultado por evento al sincronizar:
  - `accepted`
  - `duplicate` (mismo `event_id` ya procesado)
  - `conflict` (cita ya verificada o estado no compatible)
  - `rejected` (payload inválido/regla incumplida)

## 5) Auditoría requerida para offline
Además del evento actual de confirmación de cita, para offline se requiere registrar:
- `origin_mode` (`ONLINE` | `OFFLINE`)
- `event_id`
- `device_id` y/o `tablet_kiosk_id`
- `recorded_at_device`
- `confirmed_at_server` (al sincronizar)
- `sync_status`
- `conflict_reason` (si aplica)
- intentos por cliente en offline (éxito/fallo/bloqueo)

## 6) Privacidad y seguridad (base)
- CI enmascarado en toda UI de offline.
- Evitar exposición de CI completo persistente tras búsqueda.
- Datos mínimos del día (principio de minimización).
- Retención corta y purga automática.

## 7) Criterios de aceptación (resumen)
1. Separación clara de flujo online/offline.
2. Online: login directo, sin selección de perfil.
3. Offline: búsqueda por CI completo contra lista local del día.
4. Offline: mostrar solo CI enmascarado + hora + procedimiento.
5. Control de intentos por cliente solo en offline.
6. Sin bloqueo local offline en online.
7. Auditoría distingue `origin_mode`.
8. Búsqueda por CI aplica solo offline.

## 8) Referencias de implementación actual revisadas
- Frontend tablet kiosk: `frontend/aesthetic-clinic/src/pages/tablet/TabletKioskPage.tsx`
- API tablet frontend: `frontend/aesthetic-clinic/src/services/api/tablet.ts`
- Tipos tablet frontend: `frontend/aesthetic-clinic/src/types/tablet.ts`
- Flujos tablet backend: `backend/config/client_api_views.py`
- Modelo de eventos de confirmación: `backend/operations/models.py`
