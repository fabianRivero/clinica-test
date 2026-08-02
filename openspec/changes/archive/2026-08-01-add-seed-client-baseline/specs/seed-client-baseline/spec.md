# Delta for Seed Client Baseline

> **Merge note (2026-08-01)**: This delta spec has been merged in place with the delta from change `reform-database-seed-scripts` (3 ADDED requirements + 2 MODIFIED requirements). The two MODIFIED requirements (Catalog baseline, Atomic transaction) were replaced in their entirety. The 3 ADDED requirements are appended under "ADDED Requirements (from `reform-database-seed-scripts`)" below. The file remains the source of truth for the capability `seed-client-baseline` until `add-seed-client-baseline` is itself archived.

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

The command SHALL preserve its existing catalog baseline and SHALL guarantee this exact aesthetic set: `ProcEsteticosTipo(tipo="Laser", descripcion="Procedimientos laser de la ficha medica.", orden=1, activo=True)`; procedures under that type identified by `(tipo_p_estetico, proceso)`: `Depilacion definitiva` / `Procedimiento de depilacion definitiva.` / order 1, `Tratamiento de manchas` / `Procedimiento para tratamiento de manchas.` / order 2, and `Borrado de tatuajes` / `Procedimiento para borrado de tatuajes.` / order 3, all active; and one active `ServicioConfig` per procedure, identified by `(tipo_servicio, proc_estetico)`, linked to the treatment `TipoServicio` and priced `850.00`, `650.00`, and `1500.00` respectively. The treatment `TipoServicio.tipo` identity MUST be reconciled to one value for both commands without retaining both current spellings (`Tratamiento estetico` and `Tratamiento estético`). It MUST NOT seed allergy catalogs or demo clinical data. (Previously: The catalog contract referred indirectly to `seed_pdf_baseline` and did not expressly prohibit allergy writes.)

#### Scenario: Fresh or partially completed aesthetic set
- GIVEN any subset of the specified type, procedures, or service links is missing
- WHEN the command completes
- THEN every specified record and relationship SHALL exist with the stated values and no duplicate natural key

#### Scenario: Idempotent reconciliation
- GIVEN all specified natural keys exist with complete or stale mutable values
- WHEN the command is rerun
- THEN the specified mutable values SHALL match this baseline without duplicate records

#### Scenario: Preserve unrelated and operator custom data
- GIVEN unrelated catalog rows or operator custom rows outside the specified natural keys exist
- WHEN the command completes
- THEN those rows and their relationships SHALL remain unchanged and no row SHALL be deleted

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

The command SHALL execute roles, principal branch, general admin, tablet kiosk, all permitted catalogs including the complete aesthetic set, and sectors inside its existing single all-or-nothing transaction. (Previously: The transaction covered the prior baseline without explicitly naming partial aesthetic completion.)

#### Scenario: Successful fresh or partial completion
- GIVEN validation succeeds and any baseline subset is absent
- WHEN all writes succeed
- THEN every creation and reconciliation from the invocation SHALL commit together without duplicates

#### Scenario: Failure during aesthetic reconciliation
- GIVEN any write fails after processing begins, including a procedure or service-link write
- WHEN the transaction exits
- THEN NOTHING created or updated by that invocation SHALL persist

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

## ADDED Requirements (from `reform-database-seed-scripts`)

### Requirement: Configurable admin URL

The success summary MUST use a valid configured admin URL, or append exactly `/admin` to a valid configured base URL, and MUST NOT hard-code a domain.

#### Scenario: Explicit or derived URL
- GIVEN a valid explicit admin URL or base URL is configured
- WHEN the command prints its success summary
- THEN it MUST print the normalized explicit URL or the base URL followed by exactly one `/admin`

#### Scenario: Invalid URL configuration
- GIVEN neither source is an absolute HTTP(S) URL
- WHEN pre-write validation runs
- THEN the command MUST fail, identify the URL configuration, and write nothing

### Requirement: Allergy catalogs remain operator-managed

The command MUST NOT create or update `ProductoAlergia`, `TipoAlergia`, or `GravedadAlergia` records.

#### Scenario: Empty or populated allergy catalogs
- GIVEN the allergy catalogs are empty or contain operator-managed records
- WHEN the command completes
- THEN all allergy catalog records MUST remain unchanged

### Requirement: Cross-command aesthetic product consistency

`seed_client_baseline` and `seed_pdf_baseline` MUST yield the same `Laser` procedure type, three procedures, and treatment-service relationships defined by the Catalog baseline requirement. This requirement specifies observable outcomes and MUST NOT require a shared internal library.

#### Scenario: Equivalent starting databases
- GIVEN equivalent databases lack the aesthetic set
- WHEN each command succeeds on one database
- THEN the resulting procedure type, procedures, and treatment-service links MUST match on their specified identities and mutable values

### Requirement: PDF demo FichaCampo seed

> **Source note (2026-08-02, post-`9baeaa4` reconciliation)**: This requirement was added by commit `9baeaa4 feat(seeds): seed PDF demo FichaCampo (35 rows) in clean_baseline` AFTER the original `add-seed-client-baseline` change was archived. It is recorded here so the archived spec remains a faithful representation of the merged capability that `add-seed-client-baseline` contributed to, not a verbatim copy of the original delta at archive time.

When `seed_pdf_baseline` runs, `seed_form_configuration` MUST also create the demo `FichaCampo` rows that mirror the historical PDF baseline. The two PUNTO_D sections (depilacion and manchas) each own the same 13 fields in the literal historical order and the PUNTO_E section (tatuajes) owns 9 fields, for a total of 35 demo `FichaCampo` rows. Every field is keyed on `(seccion, codigo)` and is reconciled through `update_or_create`, so re-running the command leaves the count unchanged. Group references reuse the `GrupoOpciones` rows already produced by `seed_aesthetic_catalog` (`SI_NO` and `PROFUNDIDAD_TATUAJE`); no new groups or options are introduced. The `seed_client_baseline` command MUST NOT create these demo fields.

#### Scenario: PUNTO_D demo fields present
- GIVEN `seed_pdf_baseline` completes
- WHEN the PUNTO_D section under `Depilacion definitiva` is queried
- THEN exactly 13 active `FichaCampo` rows exist with codigos `BRONCEADO`, `ISOTRETINOINA`, `DESODORANTES`, `INFLAMATORIOS`, `TIPO_DEPILACION`, `DESORDEN_HORMONAL`, `DIABETES_METFORMINA`, `HIPOTIROIDISMO`, `KETOCONAZOL`, `DIURETICOS`, `TIPO_VELLO`, `COLOR_VELLO`, `GROSOR_VELLO` in that order

#### Scenario: Manchas PUNTO_D owns independent fields
- GIVEN `seed_pdf_baseline` completes
- WHEN the PUNTO_D section under `Tratamiento de manchas` is queried
- THEN it owns the same 13 codigos in the same order, with distinct row ids from the depilacion PUNTO_D rows

#### Scenario: PUNTO_E demo fields present
- GIVEN `seed_pdf_baseline` completes
- WHEN the PUNTO_E section under `Borrado de tatuajes` is queried
- THEN exactly 9 active `FichaCampo` rows exist with codigos `TIEMPO_ANTIGUEDAD`, `PROFUNDIDAD_TATUAJE`, `COLOR_TATUAJE`, `TIPO_CICATRIZACION`, `PROTECTOR_SOLAR`, `OTROS_CUIDADOS`, `TIPO_COLOR_PIEL`, `AREA_CORPORAL`, `AREA_FACIAL` in that order

#### Scenario: Group references resolve to existing GrupoOpciones
- GIVEN `seed_aesthetic_catalog` already ran before form configuration
- WHEN demo fields are written
- THEN every `SELECCION` field references the matching `GrupoOpciones` (SI_NO for binary fields, PROFUNDIDAD_TATUAJE for tatuaje depth); TEXTO fields have `grupo_opciones=None`

#### Scenario: Re-run is idempotent
- GIVEN `seed_pdf_baseline` already wrote the demo fields
- WHEN the command is re-run
- THEN the `FichaCampo` count SHALL remain 35 and each codigo SHALL still resolve to one row per section

#### Scenario: Stale mutable values are reconciled
- GIVEN a pre-existing `FichaCampo` has a stale `etiqueta` or `orden`
- WHEN `seed_form_configuration` runs again
- THEN the row is updated to the literal value and no duplicate row is created

#### Scenario: seed_client_baseline does not seed demo fields
- GIVEN `seed_client_baseline` completes
- WHEN `FichaCampo` rows are queried
- THEN no `BRONCEADO`, `PROFUNDIDAD_TATUAJE`, or other demo-only codigo is present

## Modified Capabilities

- **Catalog baseline** (replaced) — now locks the exact aesthetic set (`Laser` + 3 procedures + 3 service links at 850/650/1500), explicitly excludes allergy catalogs, and requires a single canonical `TipoServicio.tipo` spelling reconciled across both commands. Added scenarios for partial completion, idempotent reconciliation, and operator-data preservation.
- **Atomic transaction** (replaced) — now explicitly names the complete aesthetic set as part of the single all-or-nothing transaction; added scenario for failure during aesthetic reconciliation.

## Removed Capabilities

None.
