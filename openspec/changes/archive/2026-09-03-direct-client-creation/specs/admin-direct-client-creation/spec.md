# Spec: admin-direct-client-creation

## Purpose

Define the admin-only entry point on `/cms/clientes` that creates a brand-new `Cliente` + `Usuario (CLIENTE)` without any prior `Prospecto`. Reuses the 5-step wizard but starts from a `(prospecto=NULL, cliente=NULL)` draft and creates both rows atomically on finalize.

## Requirements

### Requirement: Direct Client Entry Point

The system MUST expose an admin-only "Crear cliente directo" action on `/cms/clientes` PageHeader. Activation MUST initialize a `ProspectoConversionBorrador` draft with `prospecto=NULL` and `cliente=NULL`, attributed to the current admin, and open the wizard at step 1.

#### Scenario: Admin opens the direct wizard

- GIVEN an authenticated admin on `/cms/clientes`
- WHEN the admin clicks "Crear cliente directo"
- THEN a draft with `prospecto=NULL` and `cliente=NULL` is created
- AND the wizard opens at step 1 with 5 steps visible

#### Scenario: Non-admin is forbidden

- GIVEN an authenticated non-admin
- WHEN they request the direct creation initialize endpoint
- THEN the response returns 403 and no draft row is created

### Requirement: Step 1 Uniqueness

The system MUST reject any `ci` already owned by any `Cliente` (active or inactive) and any `username` already owned by any `Usuario`. On rejection, the system MUST return 400 with a Spanish error and MUST NOT create any draft, `Usuario`, or `Cliente` row.

#### Scenario: Duplicate CI or username rejected

- GIVEN a `Cliente` with `ci` "1234567" OR a `Usuario` with `username` "taken_user" exists
- WHEN the admin submits step 1 in direct mode with that `ci` or `username`
- THEN the response returns 400 with a Spanish message
- AND no `Usuario`, `Cliente`, or draft row is created

#### Scenario: Valid step 1 advances

- GIVEN a draft in direct mode at step 1
- WHEN the admin submits a unique `ci`, unique `username`, and all required fields
- THEN the response returns 200 and the draft advances to step 2

### Requirement: Steps 2–5 Behavior

Steps 2 through 5 MUST behave identically to the prospect→client flow. The biometric step MUST stamp any fingerprint from the wizard payload and MUST skip migration when no biometric is provided.

#### Scenario: Biometric stamped from wizard payload

- GIVEN a draft in direct mode past step 4 with a fingerprint payload
- WHEN the admin submits step 4
- THEN the fingerprint is recorded against the draft and no prospect migration occurs

### Requirement: Finalize Atomic Creation

On finalize, the system MUST create a new `Usuario` (`rol=CLIENTE`, `is_active=true`) and a new `Cliente` linked to it inside a single `transaction.atomic()` block. The system MUST NOT call `marcar_como_convertido` and MUST NOT perform prospect biometric migration. On any error, the system MUST roll back so that no `Usuario`, `Cliente`, or draft row persists.

#### Scenario: Successful finalize

- GIVEN a draft in direct mode with all 5 steps complete
- WHEN the admin submits finalize
- THEN a `Usuario (CLIENTE)` is created
- AND a `Cliente` linked to that `Usuario` is created
- AND the draft row is deleted
- AND the response returns 200 with the new `cliente_codigo`

#### Scenario: Finalize rolls back on error

- GIVEN a draft in direct mode with all 5 steps complete
- AND a database error is forced during `Cliente` insertion
- WHEN the admin submits finalize
- THEN no `Usuario` row persists
- AND no `Cliente` row persists
- AND the draft row is preserved
- AND the response returns 500

### Requirement: New Client Appears in Listing

After a successful direct finalize, the new `Cliente` MUST appear in `/cms/clientes` with a non-null, unique `cliente_codigo`.

#### Scenario: Listing includes the new client

- GIVEN an admin finalized a direct creation for "Maria Lopez" with `ci` "9999999"
- WHEN the admin navigates to `/cms/clientes`
- THEN a row for "Maria Lopez" with `ci` "9999999" appears with a non-null `cliente_codigo`

### Requirement: Cancel Cleans Up the Draft

The admin MUST be able to cancel the wizard at any step. On cancel, the system MUST delete the draft and MUST NOT create any `Usuario` or `Cliente` row.

#### Scenario: Cancel deletes the draft

- GIVEN a draft in direct mode at any step
- WHEN the admin cancels
- THEN the draft row is deleted
- AND no `Usuario` or `Cliente` row exists for this session