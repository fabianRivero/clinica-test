# Delta for Appointment States

## ADDED Requirements

### Requirement: Manual Confirmation During Biometric Suspension

While biometric verification is suspended, the system MUST preserve the existing appointment state machine and MUST allow an authorized user to confirm an appointment manually. A successful suspended-mode confirmation MUST set `estado=CONFIRMADA`, `metodo_confirmacion=MANUAL`, and `verif_biometria=false`; it MUST NOT set or update biometric confirmation data. Biometric confirmation routes MUST NOT transition an appointment while suspended.

#### Scenario: Pending appointment is confirmed manually

- GIVEN suspended mode and an appointment in `REALIZADA_PENDIENTE_VERIFICACION`
- WHEN an authorized user confirms it through the manual confirmation workflow
- THEN `estado` MUST become `CONFIRMADA` and `metodo_confirmacion` MUST become `MANUAL`
- AND `verif_biometria` MUST remain `false`

#### Scenario: Stale client attempts biometric confirmation

- GIVEN suspended mode and an appointment in `REALIZADA_PENDIENTE_VERIFICACION`
- WHEN a canonical or legacy biometric confirmation request is made
- THEN the response MUST identify `BIOMETRIC_SUSPENDED`
- AND the appointment state and confirmation fields MUST remain unchanged

#### Scenario: Other appointment transitions remain valid

- GIVEN suspended mode and an appointment eligible for an existing non-biometric transition
- WHEN an authorized user performs that transition
- THEN the transition MUST follow the existing appointment-state rules
- AND suspension MUST NOT block it solely because biometric verification is unavailable
