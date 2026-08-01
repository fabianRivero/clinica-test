# Delta for Seed Client Baseline

## ADDED Requirements

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

## MODIFIED Requirements

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
