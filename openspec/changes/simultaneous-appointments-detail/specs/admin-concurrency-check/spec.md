# Delta for admin-concurrency-check

## ADDED Requirements

### Requirement: Concurrency Check Response Includes Appointment Details

The system SHALL return an `appointments` array containing detailed information for each simultaneous appointment when `POST /api/admin/disponibilidad/concurrencia/` is called.

#### Scenario: Response includes appointment details array

- GIVEN a valid `sucursal_id` and `fecha_hora` where specialists have overlapping appointments
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include an `appointments` array
- AND each entry SHALL contain `cliente` (client/prospect name), `tratamiento` (treatment name), `hora` (appointment time), and `tipo` (appointment type)

#### Scenario: Appointment types are correctly categorized

- GIVEN overlapping appointments of different types (`CitasMedicas`, `CitasProspectos`, `CitasClientesLibres`)
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN each appointment in the `appointments` array SHALL have a `tipo` field matching one of: `CitasMedicas`, `CitasProspectos`, `CitasClientesLibres`

#### Scenario: Empty appointments array when no overlaps

- GIVEN a valid `sucursal_id` and `fecha_hora` with no overlapping appointments
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `appointments: []` (empty array)