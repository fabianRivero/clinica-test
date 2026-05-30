# Exploration: simultaneous-appointments-detail

## Current State

The scheduling modal for prospects (`AdminProspectsPage.tsx` lines 514-653) includes a "citas simultaneas" (simultaneous appointments) section (lines 614-646) that shows:

- **Count only**: `concurrencyInfo.concurrency` — total number of overlapping appointments
- **Specialists list**: `concurrencyInfo.presentes` — specialists on duty (name + specialty only)

The backend endpoint `POST /api/admin/disponibilidad/concurrencia/` (`disponibilidad.py:417-462`) calculates a 1-hour window before and after the selected time and returns:
- `concurrency` (integer count)
- `presentes` (list of specialists with `id`, `usuario__primer_nombre`, `usuario__apellido_paterno`, `especialidad`)
- `hora_inicio`, `hora_fin`, `hora_seleccionada`

**What it does NOT return**: The actual list of appointments with client/treatment details. The `get_concurrency()` function (`scheduling.py:86-119`) only counts — it queries `CitasMedicas`, `CitasProspectos`, and `CitasClientesLibres` but returns `.count()`, not the records.

## Affected Areas

### Frontend
- `frontend/aesthetic-clinic/src/pages/admin/AdminProspectsPage.tsx` — Booking modal (lines 514-653), specifically the `.concurrency-results` div (lines 614-646)
- `frontend/aesthetic-clinic/src/types/admin.ts` — `AdminConcurrencyCheckResponse` type (lines 645-656)
- `frontend/aesthetic-clinic/src/services/api/admin.ts` — `checkAdminConcurrency()` function (lines 396-411)

### Backend
- `backend/config/api/viewsets/disponibilidad.py` — `concurrencia` action (lines 417-462)
- `backend/operations/scheduling.py` — `get_concurrency()` function (lines 86-119)
- `backend/operations/models.py` — `CitasMedica` (line 134), `CitasProspecto` (line 278), `CitasClienteLibre` (line 331)

## Data Available vs Missing

| Appointment Type | Client Field | Treatment Field | Currently Returned |
|-----------------|--------------|-----------------|-------------------|
| `CitasMedicas` | `operacion.paciente` (Cliente) | `operacion.servicio_config.proc_estetico.proceso` | No |
| `CitasProspectos` | `prospecto` (Prospecto) | `servicio_config.proc_estetico.proceso` | No |
| `CitasClientesLibres` | `cliente` (Cliente) | `servicio_config.proc_estetico.proceso` | No |

**Currently returned**: Specialist names and count only.

**Missing**: The actual appointment records with client names and treatment names.

## Recommendation

**Extend the `concurrencia` endpoint** to return appointment details instead of just a count:

1. **Backend** (`disponibilidad.py`): Modify `concurrencia` action to return a list of appointments with client and treatment info, not just the count. The response would include an array of:
   - `tipo` (CitasMedicas | CitasProspectos | CitasClientesLibres)
   - `cliente_nombre` (computed from the FK relation)
   - `tratamiento` (from proc_estetico.proceso)
   - `fecha_hora`, `especialista`

2. **Frontend** (`AdminProspectsPage.tsx`): Replace the simple text showing count with a list displaying each simultaneous appointment's client and treatment.

3. **Type definition** (`types/admin.ts`): Extend `AdminConcurrencyCheckResponse` to include the appointments array.

## Risks

- **Performance**: Querying all three appointment tables with joins for client/treatment data could be slower than the current count-only query. Consider adding pagination or limiting to a reasonable window.
- **Data exposure**: Ensure the endpoint only returns data for the current branch (already enforced by `sucursal_id` filter, but verify no cross-branch leaks).
- **Breaking changes**: Any change to `AdminConcurrencyCheckResponse` type will affect `useClientDetail.ts` which uses the same type for reschedule checks.

## Ready for Proposal

Yes. The investigation is complete. The next step is an SDD proposal that outlines:
1. New/modified backend endpoint returning appointment details
2. Type extension for frontend
3. UI changes to display the list
