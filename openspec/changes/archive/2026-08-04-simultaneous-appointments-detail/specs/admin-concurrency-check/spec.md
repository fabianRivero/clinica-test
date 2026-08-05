# Delta for admin-concurrency-check

## MODIFIED Requirements

### Requirement: Concurrency Check Endpoint Returns Overlap Count and Specialist Names

The system SHALL return the count of overlapping appointments, the names of specialists who have those appointments, and an `appointments` array describing each overlapping appointment, when `POST /api/admin/disponibilidad/concurrencia/` is called with valid `sucursal_id` and `fecha_hora` parameters.

(Previously: response included only `concurrency` count and `presentes` (specialist names); the endpoint now additionally returns per-appointment details so admins can see who is already booked at each overlapping time.)

#### Scenario: Successful concurrency check with no overlaps

- GIVEN a valid `sucursal_id` and `fecha_hora` (future datetime) with no overlapping appointments in the 2-hour window (1h before to 1h after `fecha_hora`)
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `concurrency: 0`, `presentes: []`, and `appointments: []`

#### Scenario: Successful concurrency check with overlapping appointments

- GIVEN a valid `sucursal_id` and `fecha_hora` where specialists have overlapping appointments in the 2-hour window
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `concurrency` with the count of overlapping appointments
- AND `presentes` SHALL contain an array of specialist names who have simultaneous appointments
- AND `appointments` SHALL contain one entry per overlapping appointment

### Requirement: Concurrency Check Response Includes Appointment Details

The system SHALL return an `appointments` array containing detailed information for each simultaneous appointment when `POST /api/admin/disponibilidad/concurrencia/` is called.

(Previously: `appointments` used field names `cliente` and `tratamiento`; the actual contract uses `cliente_nombre` and `tratamiento_nombre` to align with backend serializer and frontend type.)

#### Scenario: Response includes appointment details array

- GIVEN a valid `sucursal_id` and `fecha_hora` where overlapping appointments exist in the 2-hour window
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include an `appointments` array
- AND each entry SHALL contain `cliente_nombre` (client/prospect name, never null — rendered as the string `"Cliente no registrado"` when no associated client exists), `tratamiento_nombre` (treatment name, may be null), `hora` (appointment time in ISO 8601 format), and `tipo` (appointment type)

#### Scenario: Appointment types are correctly categorized

- GIVEN overlapping appointments of different types (`CitasMedicas`, `CitasProspectos`, `CitasClientesLibres`)
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN each appointment in the `appointments` array SHALL have a `tipo` field matching one of: `CitasMedicas`, `CitasProspectos`, `CitasClientesLibres`

#### Scenario: Empty appointments array when no overlaps

- GIVEN a valid `sucursal_id` and `fecha_hora` with no overlapping appointments
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `appointments: []` (empty array)