# Delta for Seed Client Baseline

## Purpose

The `seed_client_baseline` management command SHALL initialize a real client deployment with prompted production credentials, one principal branch, and the complete operational catalog baseline. It exists alongside `seed_production_baseline`, whose fixed minimal data is insufficient for client onboarding, and `seed_pdf_baseline`, whose demo users, patients, biometrics, schedules, and destructive cleanup are unsuitable for production.

## ADDED Requirements

### Requirement: Role baseline

The command SHALL create exactly `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, and `CLIENTE` without duplicates.

#### Scenario: Fresh database
- GIVEN no roles exist
- WHEN the command completes
- THEN exactly the four baseline roles SHALL exist

#### Scenario: Idempotent re-run
- GIVEN the four roles already exist
- WHEN the command is re-run with identical input
- THEN no role SHALL be duplicated

#### Scenario: Unrelated role exists
- GIVEN an unrelated role exists
- WHEN the command completes
- THEN the unrelated role SHALL remain unchanged

### Requirement: Branch creation

The command SHALL collect `nombre`, `ciudad`, and `direccion`, create or update the principal active `Sucursal`, and set `es_principal=False` on every other branch.

#### Scenario: Fresh database
- GIVEN no branch exists
- WHEN valid branch data is supplied
- THEN one active principal branch SHALL be created

#### Scenario: Idempotent re-run
- GIVEN the named principal branch already has the supplied data
- WHEN the command is re-run
- THEN no branch SHALL be duplicated

#### Scenario: Duplicate branch name
- GIVEN another branch already uses the supplied unique name
- WHEN validation runs
- THEN the command SHALL reject the input unless that branch is the confirmed update target

### Requirement: Admin general creation

The command SHALL collect `username`, `password`, `primer_nombre`, `apellido_paterno`, and `email`; create or update that user with role `ADMIN_PRINCIPAL`, the principal branch, and all three flags `is_active`, `is_staff`, and `is_superuser` true; and hash supplied passwords through `set_password()`.

#### Scenario: Fresh database
- GIVEN the username is available and the credentials are valid
- WHEN the command completes
- THEN the linked superuser SHALL be created with a hashed password

#### Scenario: Idempotent re-run
- GIVEN the target admin already exists
- WHEN the command is re-run with a new password
- THEN the admin SHALL be updated and the password SHALL rotate without duplication

#### Scenario: Duplicate username
- GIVEN the username belongs to a different existing user
- WHEN validation runs
- THEN the command SHALL reject it without modifying that user

### Requirement: Tablet kiosk creation

The command SHALL collect `codigo` and `clave`, create or update the matching `TabletKiosko`, link it to the principal branch, set `activo=True`, and hash the secret through `set_clave()`.

#### Scenario: Fresh database
- GIVEN the kiosk code is available
- WHEN valid kiosk data is supplied
- THEN an active linked kiosk SHALL be created with a hashed secret

#### Scenario: Idempotent re-run
- GIVEN a kiosk with the supplied code exists
- WHEN the command is re-run
- THEN that kiosk SHALL be updated without duplication

#### Scenario: Existing kiosk changes branch
- GIVEN the matching kiosk belongs to another branch
- WHEN the command completes
- THEN it SHALL be relinked to the principal branch

### Requirement: Catalog baseline

The command SHALL independently reproduce the exact catalog values from `seed_pdf_baseline._seed_catalogs()` plus its three `Sector` records: 2 `TipoServicio`, 8 `CategoriaGasto`, 1 `ProcEsteticosTipo`, 3 `ProcEstetico`, 4 `ServicioConfig` priced 850/650/1500/120, 6 `AntecedenteMedico`, 5 `ImplanteInjerto`, 7 `CirugiaEstetica`, 2 `GrupoOpciones`, 6 `TipoPiel`, 3 `GradoDeshidratacion`, 5 `GrosorPiel`, 28 `PatologiaCutanea`, and 3 `Sector`. It SHALL NOT modify or invoke `seed_pdf_baseline`.

#### Scenario: Fresh database
- GIVEN no baseline catalog records exist
- WHEN the command completes
- THEN every listed record and exact value SHALL exist

#### Scenario: Idempotent re-run
- GIVEN the complete baseline exists
- WHEN the command is re-run
- THEN no catalog record SHALL be duplicated

#### Scenario: Existing catalog value differs
- GIVEN a baseline record exists with stale mutable values
- WHEN the command completes
- THEN that record SHALL be updated to the baseline value

### Requirement: Interactive mode

With no CLI flags, the command SHALL prompt for every input, display sensible defaults in brackets, and validate non-empty values, email format, uniqueness constraints, and password length of at least eight characters.

#### Scenario: Fresh interactive run
- GIVEN no CLI flags are passed
- WHEN the operator accepts or enters valid values
- THEN every required prompt SHALL be shown and the command SHALL proceed

#### Scenario: Re-run with defaults
- GIVEN previously seeded values are available as defaults
- WHEN the operator accepts them
- THEN the command SHALL complete without duplicates

#### Scenario: Invalid input
- GIVEN an empty value, malformed email, weak password, or conflicting unique value is entered
- WHEN validation runs
- THEN the command SHALL explain the error and SHALL NOT seed until valid input is supplied

### Requirement: Non-interactive mode

The command SHALL accept `--branch-name`, `--branch-city`, `--branch-address`, `--admin-username`, `--admin-password`, `--admin-first-name`, `--admin-last-name`, `--admin-email`, `--kiosk-code`, and `--kiosk-password`; `--non-interactive` or all required value flags SHALL suppress prompts.

#### Scenario: Complete flags on fresh database
- GIVEN all required value flags are valid
- WHEN the command runs
- THEN it SHALL complete without prompting

#### Scenario: Idempotent flagged re-run
- GIVEN the supplied baseline already exists
- WHEN the same flags are passed again
- THEN the command SHALL update in place without prompting or duplicating data

#### Scenario: Missing non-interactive value
- GIVEN `--non-interactive` is passed without every required value
- WHEN validation runs
- THEN the command SHALL fail before writing data and identify missing flags

### Requirement: Safety check on existing main branch

If a principal branch predates execution, the command SHALL print its current data and require explicit interactive confirmation or `--replace-main-branch` in non-interactive mode before replacement.

#### Scenario: Interactive replacement
- GIVEN a principal branch already exists
- WHEN its data is printed and the operator confirms
- THEN the command SHALL update it and demote all other branches

#### Scenario: Confirmed idempotent re-run
- GIVEN the existing principal branch already matches the input
- WHEN the operator explicitly confirms
- THEN the command SHALL continue without duplication

#### Scenario: Unconfirmed replacement
- GIVEN a principal branch exists
- WHEN confirmation is declined or non-interactive mode omits `--replace-main-branch`
- THEN the command SHALL abort without changes

### Requirement: Atomic transaction

The command SHALL execute all validation-dependent writes inside one `transaction.atomic` boundary so any failure rolls back every write.

#### Scenario: Successful fresh transaction
- GIVEN all input and database operations are valid
- WHEN the command completes
- THEN all baseline entities SHALL be committed together

#### Scenario: Successful idempotent transaction
- GIVEN the baseline already exists
- WHEN the command completes again
- THEN all updates SHALL commit together without duplicates

#### Scenario: Failure after partial processing
- GIVEN any seeding step raises an error
- WHEN the transaction exits
- THEN NOTHING from that invocation SHALL be created or updated

### Requirement: Output summary

After a successful run, the command SHALL print a clear created/updated summary and show the final admin and kiosk credentials exactly once.

#### Scenario: Fresh database summary
- GIVEN the baseline is created successfully
- WHEN output is finalized
- THEN created entities and final credentials SHALL be shown once

#### Scenario: Idempotent re-run summary
- GIVEN the baseline already exists
- WHEN the command succeeds
- THEN updated or unchanged outcomes SHALL be clearly distinguished without duplicate credential output

#### Scenario: Failed execution
- GIVEN the command rolls back
- WHEN error output is produced
- THEN no success summary or final credentials SHALL be printed

## Modified Capabilities

None.

## Removed Capabilities

None.
