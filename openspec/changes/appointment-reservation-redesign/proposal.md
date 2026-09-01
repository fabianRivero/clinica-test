# Proposal: Appointment Reservation Redesign

## Why

Today the reservation flow only captures the bare minimum: tratamiento + fecha + hora. The admin picks a slot, presses "Verificar Disponibilidad", and confirms. There is no record of what was planned for that cita — duration estimate, what procedure will be performed, on which body zone, with which specialist, or with which equipment. When the cita is later moved to `REALIZADA_PENDIENTE_VERIFICACION`, a single button flips the state with no record of what actually happened either — no real start/end times, no list of specialists who attended, no list of machinery used, no description of the procedure performed.

That gap means we cannot answer the most important operational questions: *how long did this appointment really take?*, *which equipment is being double-booked?*, *which specialist is doing what?*, and *what should the next appointment in this treatment plan be?* Without structured planning + actuals, the clinic is making decisions on memory.

This change introduces two new modals and a new catalog so that each cita carries both the plan (what we expect to happen) and the actual (what actually happened), with machinery visibility so the admin can see conflicts before confirming — but still decide for themselves.

## What changes

- A new `ReservationModal` replaces the inline reservation blocks at `cms/clientes/:id` and `cms/operaciones/:id`. It captures: tratamiento, fecha, hora, duración estimada (minutos), descripción general, notas previas, procedimiento planificado, zona del cuerpo planificada, especialistas planificados (multi-select), maquinaria planificada (rows with cantidad). It preserves the existing availability-of-specialists + nearby-appointments (1h ±) panel, and adds a new machinery-conflicts panel that warns (without blocking) when selected equipment overlaps with other reservations.
- A new `Maquinaria` catalog (nombre, marca, descripción, cantidad total, sucursal nullable for global) with admin-general vs admin-de-sucursal scopes, exposed in `AdminCatalogsPage` like every other catalog.
- A new `CloseAppointmentModal` triggered by the "Cambiar a pendiente de verificación" action. It captures: hora real inicio, hora real fin, procedimiento realizado, zona del cuerpo realizada, especialistas que atendieron (prepopulated), maquinaria utilizada (prepopulated).
- An always-editable notes panel on every cita with `descripcion_general`, `notas_previas`, `notas_post`, `foto_antes`, `foto_despues`.
- A read-only "Mis citas" view on the specialist interface, listing every cita the authenticated specialist is assigned to (planned or attended), with date, time, full planning data, and machinery list.
- Backend endpoints to support the above: extend the reservation endpoint, extend `pendiente-biometria`, new `check-maquinaria`, new `notas` PATCH, new `mis-citas`, machinery registered in the catalog dispatch.

## Out of scope

- `CitaProspecto` and `CitaClienteLibre` flows — different lifecycle, untouched.
- The biometric verification flow itself — we only change what data is captured at the moment the cita is moved to `REALIZADA_PENDIENTE_VERIFICACION`, not how it later transitions to `CONFIRMADA`.
- Payments, plans, quotas — untouched.
- Reschedule / reprogram flow — keeps its current API.
- Cancellation — untouched.
- Notifications sent to clients — not modified by this change.
- Historical backfill of old citas with the new fields — old rows stay with null/blank fields.

## User experience

### Reservation (admin, from cms/clientes/:id or cms/operaciones/:id)

1. Admin clicks "Reservar cita" → `ReservationModal` opens.
2. Admin selects **tratamiento** (the current select).
3. Admin picks **fecha** + **hora** (current date+time inputs).
4. Admin enters **duración estimada** (minutes, default 60), **descripción general**, **notas previas**, **procedimiento planificado**, **zona del cuerpo planificada**.
5. Admin optionally selects **especialistas planificados** (multi-select, "No seleccionado" by default).
6. Admin optionally adds rows of **maquinaria planificada** (maquinaria + cantidad).
7. Admin clicks **"Verificar disponibilidad"** → the existing panel refreshes (citas in 1h ± window, specialists on shift). If any selected machinery overlaps, a new machinery-conflicts panel appears under it listing the conflicting citas (date, time, client, cantidad reservada). The button **"Confirmar reserva"** is NEVER disabled by a conflict.
8. Admin clicks **"Confirmar reserva"** → cita is created with `estado=PROGRAMADA` and all the optional fields persisted.

### Close (admin)

9. Later, admin clicks **"Cambiar a pendiente de verificación"** on a `PROGRAMADA` cita → `CloseAppointmentModal` opens.
10. Modal is prepopulated with the planned values where available.
11. Admin enters **hora real inicio** (must be ≥ scheduled `fecha_hora` − 1h) and **hora real fin** (must be > inicio). If `fin - inicio` differs > 50% from `duracion_estimada_minutos`, a yellow warning appears.
12. Admin confirms **procedimiento realizado**, **zona del cuerpo realizada**, **especialistas que atendieron** (multi-select), **maquinaria utilizada** (rows + cantidad).
13. Admin clicks **"Confirmar cierre"** → cita goes to `REALIZADA_PENDIENTE_VERIFICACION`. Real times, performed fields, attended staff, and used machinery are persisted.

### Notes panel (admin or specialist assigned to the cita)

14. From any cita detail, admin or assigned specialist opens the **notes panel** (tab/acordeón): descripción general, notas previas, notas post, foto antes, foto después. Each has an "Editar" button that opens an inline editor. No state restriction: notes are always editable.

### Maquinaria catalog (admin general, admin de sucursal)

15. Admin goes to **Catálogos → Maquinaria**.
16. Admin general sees all machines and can assign any to "Todas las sucursales" (global) or to a specific sucursal.
17. Admin de sucursal sees globales + own; can create/edit only own; cannot edit globales.

### Mis citas (specialist)

18. Specialist logs in and goes to **"Mis citas"** in their sidebar.
19. They see a read-only list of every cita where they appear in `CitaEspecialista` (planned or attended). Each row shows cliente, fecha, hora, procedimiento planificado, zona, descripción general, notas previas, sucursal, estado, and the maquinaria list.
20. Clicking a row (optional) expands inline details; no actions are exposed.

## Affected users and permissions

- **Admin general** — full access: machinery catalog CRUD (global or any sucursal), all reservation flows, close, notes, sees all citas.
- **Admin de sucursal** — machinery CRUD restricted to own sucursal + read-only globals; reservation and close flows in own sucursal; notes on own sucursal's citas.
- **Specialist** — read-only access to "Mis citas" (citas where they appear in `CitaEspecialista`); can edit `descripcion_general`, `notas_previas`, `notas_post`, `foto_antes`, `foto_despues` of those citas.
- **Cliente** — no change in visible flows.

## Risks and mitigations

- **MEDIA serving and Pillow dependency** — first ImageField usage in the codebase. Mitigation: add Pillow to `requirements.txt`, confirm `MEDIA_ROOT`/`MEDIA_URL` are wired in `urlpatterns` for `DEBUG=True`.
- **M2M through-model mistakes** — wrong `on_delete` could orphan or cascade `CitaMaquinaria`. Mitigation: `on_delete=PROTECT` on `Maquinaria`, `CASCADE` on `CitaMedica`.
- **Conflict visibility leaks** — admins can see other admins' clients via the conflict-list endpoint. Mitigation: filter by `sucursal_id` so admins only see conflicts in their own branch.
- **Optional fields mistaken for required** — admins might skip planning data thinking it's required. Mitigation: explicit "No seleccionado" placeholders + tooltip on each optional field.
- **Close modal re-entry** — admin might need to fix real hours or staff after closing. Mitigation: expose a `PATCH /api/admin/citas/:id/notas/` and a small edit-real-data endpoint, scoped to `REALIZADA_PENDIENTE_VERIFICACION` only.

## Rollback plan

- All new `CitaMedica` fields are null/blank → dropping them in a follow-up migration removes everything cleanly.
- `Maquinaria`, `CitaMaquinaria`, `CitaEspecialista` are new tables; can be dropped without touching existing data.
- `ReservationModal`/`CloseAppointmentModal`/`AppointmentNotesPanel` are pure additions to the UI; reverting to the inline `ClientReservationSection` keeps the system functional.
- The catalog `maquinaria` slug is one entry in `_catalog_key_to_slug` and its three dispatch functions; removal is a one-line change.

## Open questions

Reference: `explore.md → Open questions`.

1. Should `foto_antes`/`foto_despues` only be surfaced in the notes panel, or also requested in the close modal?
2. Should `maquinaria_planificada` be accepted inside the reservation POST body, or via a separate endpoint after reservation?
3. After a cita is `REALIZADA_PENDIENTE_VERIFICACION`, can the admin re-edit the real fields (hours, procedimiento, staff, machinery)?
4. Specialist "Mis citas": all assigned citas or only future ones?