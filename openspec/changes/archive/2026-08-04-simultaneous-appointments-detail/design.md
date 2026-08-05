# Design: simultaneous-appointments-detail

## Technical Approach

Replace the count-only `get_concurrency()` with a query that returns actual appointment records annotated with client name, treatment name, time, and type. The ViewSet serializes each record into a flat `appointments` array. The frontend extends `AdminConcurrencyCheckResponse` with an additive `appointments` field and renders it in the modal.

## Architecture Decisions

### Decision: Query method for appointment records

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Full model instances + prefetch_related | Simpler ORM traversal, lazy-loads FKs silently, easy to miss N+1 | Rejected |
| `.values()` with explicit FK traversal | One round-trip per table,明确的フィールド only, FK traversal via string notation | **Chosen** — existing code uses `.values_list()` pattern; aligns with existing `get_specialists_present` approach |
| Raw SQL UNION | Maximum control but fragile, no ORM protection | Rejected |

### Decision: Handling three appointment types

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Three separate queries + Python merge | Simple, individual ordering, easy to add ordering per type | Rejected — Python-side merge adds latency and complexity |
| `Q` objects with `outerref` subquery | Single query but complex Django ORM | Rejected |
| UNION ALL via Django ORM union() + annotated tipo | Single DB round-trip, flat list, annotated `tipo` differentiates models | **Chosen** — Proposal explicitly calls for a union; spec confirms `tipo` field distinguishes appointment classes |

### Decision: Backward compatibility

`AdminConcurrencyCheckResponse` currently has no `appointments` field. The new field is **additive only**. All existing consumers (`ClientReservationSection`, `ClientAppointmentSection`, `ClientFreeMedicalAppointmentSection`) check `concurrencyInfo` — they will ignore the new array field and continue to work. No version bumps or feature flags required.

## Data Flow

```
User selects date + time
       │
       ▼
AdminProspectsPage → checkAdminConcurrency()  ──POST /api/admin/disponibilidad/concurrencia/
       │                                                       │
       │◄────────────────── Response {                            ▼
       │                    concurrency: N,             ConcurrenciaViewSet.concurrencia()
       │                    appointments: [               │
       │                      {cliente_nombre,              │
       │                       tratamiento_nombre,  ───►  get_concurrency_unioned()
       │                       hora,                              │
       │                       tipo},          ───►  QuerySet union
       │                    ...],                                    │
       │                    presentes: [...]               ▼
       │                  }                     annotated values list
       ▼
   Modal renders:
   - appointments list (NEW)
   - specialist list (unchanged)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/operations/scheduling.py` | Modify | Add `get_concurrency_detail()` returning list of dicts |
| `backend/config/api/viewsets/disponibilidad.py` | Modify | Call new function, merge appointments into response |
| `frontend/aesthetic-clinic/src/types/admin.ts` | Modify | Additive `appointments` field on `AdminConcurrencyCheckResponse` |
| `frontend/aesthetic-clinic/src/pages/admin/AdminProspectsPage.tsx` | Modify | Render appointments list in modal section "citas simultaneas" |

## Interfaces / Contracts

### Backend — `get_concurrency_detail()` (new function in `scheduling.py`)

```python
def get_concurrency_detail(sucursal_id, fecha, hora_inicio, hora_fin):
    """
    Returns a list of appointment detail dicts overlapping the time window.
    Each dict: { cliente_nombre, tratamiento_nombre, hora, tipo }
    tipo is one of: 'CitasMedicas', 'CitasProspectos', 'CitasClientesLibres'
    """
    start_dt = timezone.make_aware(datetime.combine(fecha, hora_inicio))
    end_dt   = timezone.make_aware(datetime.combine(fecha, hora_fin))

    medicas_qs = CitaMedica.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado__in=BLOCKING_RESERVATION_STATES
    ).values(
        'fecha_hora',
        cliente_nombre=F('operacion__cliente__nombre'),
        tratamiento=F('servicio_config__proc_estetico__proceso__nombre'),
    ).annotate(tipo=Value('CitasMedicas', output_field=CharField()))

    prospectos_qs = CitaProspecto.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaProspecto.Estado.PROGRAMADA
    ).values(
        'fecha_hora',
        cliente_nombre=F('prospecto__nombre'),
        tratamiento=F('servicio_config__proc_estetico__proceso__nombre'),
    ).annotate(tipo=Value('CitasProspectos', output_field=CharField()))

    libres_qs = CitaClienteLibre.objects.filter(
        sucursal_id=sucursal_id,
        fecha_hora__gte=start_dt,
        fecha_hora__lt=end_dt,
        estado=CitaClienteLibre.Estado.PROGRAMADA
    ).values(
        'fecha_hora',
        cliente_nombre=F('cliente__nombre'),
        tratamiento=F('servicio_config__proc_estetico__proceso__nombre'),
    ).annotate(tipo=Value('CitasClientesLibres', output_field=CharField()))

    return (
        medicas_qs.union(prospectos_qs, libres_qs)
        .order_by('fecha_hora')
    )
```

> **Note**: `operacion__cliente__nombre` on `CitaMedica` — if `operacion` is nullable and `CitasMedicas` may be booked without an operation, the client name may be null. Use `Coalesce` to default to a placeholder display name.

### Updated `concurrencia` endpoint response

```python
return Response({
    "concurrency": len(appointments),   # count from list length (backward compatible int)
    "appointments": [                   # new — list of detail dicts
        {
            "cliente_nombre": "...",   # may be null on CitaMedica without operacion
            "tratamiento_nombre": "...",
            "hora": "10:30",
            "tipo": "CitasMedicas",
        },
        ...
    ],
    "presentes": especialistas,
    "hora_inicio": hora_ventana_inicio.strftime("%H:%M"),
    "hora_fin": hora_ventana_fin.strftime("%H:%M"),
    "hora_seleccionada": hora_inicio.strftime("%H:%M"),
})
```

### Frontend type update

```typescript
export type AdminConcurrencyCheckResponse = {
  concurrency: number
  presentes: Array<{
    id: number
    usuario__primer_nombre: string
    usuario__apellido_paterno: string
    especialidad: string
  }>
  hora_inicio?: string
  hora_fin?: string
  hora_seleccionada?: string
  appointments?: Array<{        // new — additive, optional for backward compat
    cliente_nombre: string | null
    tratamiento_nombre: string | null
    hora: string
    tipo: 'CitasMedicas' | 'CitasProspectos' | 'CitasClientesLibres'
  }>
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `get_concurrency_detail()` returns correct shape, count matches existing `get_concurrency()`, null client names handled | Django test with TestCase seeding 3 appointment types |
| Integration | `POST /disponibilidad/concurrencia/` returns appointments array with correct fields | DRF APIClient test |
| E2E | Modal in `AdminProspectsPage` renders appointments list when present | Playwright test targeting `.concurrency-results` |

## Migration / Rollout

No migration required. This is a forward-only additive change — existing consumers are unaffected.

## Open Questions

- [ ] **CitaMedica client name nullability**: `operacion` FK may be null on some `CitaMedica` records. Should we show "Sin cliente asociado" or skip those records from the list? The spec says empty array when no overlaps — but a record with null client is still an overlapping appointment. Recommend: display null clients as "Cliente no registrado" so admins still see the time slot is occupied.
