# Delta for cliente-origen

## ADDED Requirements

### Requirement: prospect-side origin feeding Cliente.origen

`Cliente.origen` MAY receive its value from a pre-existing `Prospecto.origen` carried into `mode='prospect'` finalize, in addition to the `mode='direct'` admin radio path. When a `Cliente` is created from a `Prospecto`, the resulting `Cliente.origen` MUST equal `prospecto.origen`. The `Cliente.origen` write-once guarantee and the `mode='reactivation'` non-overwrite guarantee from the existing spec MUST continue to hold for the prospect-sourced path.

#### Scenario: Client converted from prospect inherits prospect origin

- GIVEN a `Prospecto` with `origen = RECURRENTE_PRE_SISTEMA`
- WHEN `admin_prospect_conversion_finalize` completes a `mode='prospect'` draft
- THEN the newly created `Cliente.origen` is `RECURRENTE_PRE_SISTEMA`

#### Scenario: Prospect-side origin respects write-once

- GIVEN a `Cliente` created from a prospect with `origen = NUEVO`
- WHEN admin sends `PATCH /api/admin/clientes/{id}/perfil/` with `{"origen": "RECURRENTE_PRE_SISTEMA"}`
- THEN the response returns 400
- AND the live row's `origen` remains `NUEVO`

### Requirement: future prospect list badge (informational)

> **Updated 2026-09-05**: this requirement was originally informational-only ("MAY in a future change"). A follow-up change added the column and filter to `AdminProspectsPage`. The updated behavior is documented below; the historical "no badge" scenario is preserved as a closed marker for traceability.

The admin prospect list view at `/cms/prospectos` SHALL expose an `origen` column with a visual badge and a filter selector so admins can identify at a glance whether a prospect is `NUEVO` (a brand-new prospect) or `RECURRENTE_PRE_SISTEMA` (a pre-system returning patient).

#### Scenario: Origin column rendered per prospect row (added 2026-09-05)

- GIVEN the system is at the post-`prospecto-origen-heredable` state and the prospect-list UI has been updated
- WHEN `/cms/prospectos` renders the prospect table
- THEN each row shows an `Origen` cell with a badge labelled `Nuevo` for `origen=NUEVO` and `Recurrente pre-sistema` for `origen=RECURRENTE_PRE_SISTEMA`

#### Scenario: Origin filter narrows the prospect list (added 2026-09-05)

- GIVEN the admin is on `/cms/prospectos`
- WHEN the admin selects `Recurrente pre-sistema` in the Origen filter
- THEN only prospects whose `origen` equals `RECURRENTE_PRE_SISTEMA` are listed

#### Scenario: No prospect list badge in this change (closed 2026-09-05)

- GIVEN the system at the moment `prospecto-origen-heredable` was first archived
- WHEN `/cms/prospectos` was rendered
- THEN no `origen` badge was displayed for any prospect row
- AND a follow-up change added the badge (see scenarios above)
