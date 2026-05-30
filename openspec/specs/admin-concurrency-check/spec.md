# Admin Concurrency Check Specification

## Purpose

The admin concurrency check endpoint provides information about overlapping appointments at a specific branch during a time window. This allows administrators to make informed decisions about double-booking or rescheduling.

## Requirements

### Requirement: Concurrency Check Endpoint Returns Overlap Count and Specialist Names

The system SHALL return the count of overlapping appointments and the names of specialists who have those appointments when `POST /api/admin/disponibilidad/concurrencia/` is called with valid `sucursal_id` and `fecha_hora` parameters.

#### Scenario: Successful concurrency check with no overlaps

- GIVEN a valid `sucursal_id` and `fecha_hora` (future datetime)
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `concurrency: 0` and `presentes: []`

#### Scenario: Successful concurrency check with overlapping appointments

- GIVEN a valid `sucursal_id` and `fecha_hora` where specialists have overlapping appointments
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN the response SHALL include `concurrency` with the count of overlapping specialists
- AND `presentes` SHALL contain an array of specialist names who have simultaneous appointments

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

### Requirement: Concurrency Check Filters by Branch

The system SHALL only return appointments belonging to the specified `sucursal_id` to prevent data leakage across branches.

#### Scenario: Branch filter is enforced

- GIVEN a valid `sucursal_id` and `fecha_hora`
- WHEN the admin calls `POST /api/admin/disponibilidad/concurrencia/`
- THEN only appointments at that specific branch SHALL be considered in the concurrency calculation
- AND appointments at other branches SHALL NOT appear in the response