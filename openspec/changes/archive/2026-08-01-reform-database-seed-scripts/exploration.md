## Exploration: reform-database-seed-scripts

### Scope (narrowed per orchestrator + user clarification, 2026-07-31)

This change covers **exactly two commands** and nothing else:

1. **`seed_client_baseline`** — the existing clean baseline. **Document its current behavior exactly; preserve it.** It is the production-facing bootstrap and is the only command that is NOT recreated from scratch. Any refactor or migration of this command must keep its current behavior bit-for-bit unless a `MODIFIED` OpenSpec scenario explicitly changes a contract.
2. **`seed_pdf_baseline`** — recreated from scratch on current models. The current implementation stays in place until the replacement is ready; the recreation is a follow-up work unit, and the focus of this exploration is the clean baseline. This artifact documents the clean baseline in detail and only records the existence and known drift of `seed_pdf_baseline` for future work.

**Out of scope (explicitly):** `seed_production_baseline`, `seed_branch_test_scenarios`, `ensure_main_branch`, `purge_data_keep_admin`, fixtures, wrapper scripts, and any migration repair. They were covered in earlier broad exploration and are not part of this change.

The deep review of the clean baseline below has been re-verified against the live source on 2026-07-31: `backend/accounts/management/commands/seed_client_baseline.py` (794 lines), `backend/accounts/tests/test_seed_client_baseline.py` (347 lines, 10 end-to-end + 3 helper tests), `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` (9 requirements, ADDED only, no MODIFIED/REMOVED), and migrations `catalogs/0006_seed_sectores_and_reassign_fichaseccion.py` and `operations/0008_data_migrate_sucursales.py`. No code was executed and no file was modified by this exploration.

### Current State

#### Clean baseline: `seed_client_baseline`
The clean baseline is the production-facing bootstrap. Its intended behavior is to take real client credentials and produce a fresh, atomic, validated, idempotent, non-destructive deployment baseline that operators can run by hand or from a script.

**Identification**
- Django management command, file `backend/accounts/management/commands/seed_client_baseline.py`.
- Class `accounts.management.commands.seed_client_baseline.Command`.
- `BaseCommand.help`: "Seeds a real client deployment baseline: roles, principal branch, admin general, tablet kiosk, and the full operational catalog."
- Invocation: `python manage.py seed_client_baseline` (interactive) or `python manage.py seed_client_baseline --non-interactive ...` with required value flags. Optional `--replace-main-branch` to overwrite an existing principal branch in non-interactive mode.
- No wrapper scripts, fixtures, or model migrations invoke it; it is a standalone command.
- The `add-seed-client-baseline` OpenSpec change documents and tests it (`openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` and `tasks.md`).
- VPS guide reference: `docs/vps-setup-from-scratch.md` section 5.2 option 1.

**Inputs (10 required fields and 2 control flags)**
- Branch: `--branch-name`, `--branch-city`, `--branch-address`.
- Admin: `--admin-username`, `--admin-password`, `--admin-first-name`, `--admin-last-name`, `--admin-email`.
- Tablet kiosk: `--kiosk-code`, `--kiosk-password`.
- Mode: `--non-interactive` (or auto-detected when all 10 value flags are present and non-empty).
- Override: `--replace-main-branch` (non-interactive only; required to replace a different principal branch).

**Prompts (interactive mode, in order)**
1. `Branch name [default]` — default is `Sede Principal` if no principal branch exists; otherwise existing principal branch's `nombre`.
2. `Branch city [default]` — existing `ciudad` or empty.
3. `Branch address [default]` — existing `direccion` or empty.
4. `Admin username [default]` — existing superuser's `username` or `admin.general`.
5. `Admin password` — never defaulted; empty default value.
6. `Admin first name [default]` — existing superuser's `primer_nombre` or `Administrador`.
7. `Admin last name [default]` — existing superuser's `apellido_paterno` or `General`.
8. `Admin email [default]` — existing superuser's `email` or `admin.general@clinic.local`.
9. `Kiosk code [default]` — existing kiosk linked to the principal branch, else `KIOSKO-PRINCIPAL`.
10. `Kiosk password` — never defaulted; empty default value.
- Each prompt accepts the default by pressing Enter (`_prompt` falls back to `default or ""`).
- No re-prompt loop on validation failure; the validator raises `CommandError` after the prompt phase completes.

**Validation (`_validate_values`, pre-transaction)**
- Every required field must be non-empty.
- `admin_email` must pass `django.core.validators.validate_email`.
- `admin_password` must pass `django.contrib.auth.password_validation.validate_password` (Django built-ins: length, common passwords, numeric, similarity to user attributes).
- `kiosk_password` must be at least 8 characters (only length check; not Django's full validator set).
- `admin_username` collisions are rejected only when the existing user with that username is **not** a superuser; collisions with the target superuser are accepted for in-place update.
- `kiosk_code` collisions are rejected only when more than one matching `TabletKiosko` row exists; a single existing kiosk is updated in place.
- All errors are collected and raised as a single `CommandError` listing every problem.

**Existing main branch safety check (`_handle_existing_main_branch`)**
- Pre-transaction; runs only when an active principal branch already exists.
- Prints the existing branch's `nombre`, `ciudad`, `direccion`, `activa` as a warning block.
- `same_identity` is true when name, city, and address all match the supplied values.
- Non-interactive:
  - `same_identity` → proceed silently (idempotent re-run).
  - Different identity and `--replace-main-branch` set → proceed.
  - Different identity and no flag → `CommandError`, abort before any write.
- Interactive:
  - `same_identity` → asks "Continue? [Y/n]"; "n" aborts with `CommandError`, anything else proceeds.
  - Different identity → asks "Replace the existing principal branch and demote all others? [y/N]"; "y" or "yes" proceeds, anything else aborts.
- `_prompt_confirm` only accepts `y` or `yes` (case-insensitive); any other input (including empty) is treated as "no" and aborts.

**Models created/updated (in one `transaction.atomic`)**
1. `accounts.Rol` (4 records, `update_or_create` on `rol`):
   - `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE`.
2. `catalogs.Sucursal` (`update_or_create` on `nombre`):
   - Creates or updates the branch with `es_principal=True`, `activa=True`, supplied `ciudad`/`direccion`.
   - Demotes all other `Sucursal` rows with `es_principal=True` to `es_principal=False`.
3. `accounts.Usuario` (`update_or_create` on `username`):
   - Fields: `primer_nombre`, `segundo_nombre=""`, `apellido_paterno`, `apellido_materno=""`, `email`, `telefono=""`, `rol=ADMIN_PRINCIPAL`, `sucursal=branch`, `is_active=True`, `is_staff=True`, `is_superuser=True`.
   - Password is set via `set_password(...)` and saved (full save, not `update_fields`).
4. `operations.TabletKiosko` (`update_or_create` on `codigo`):
   - Fields: `nombre=f"Tablet {branch.nombre}"`, `sucursal=branch`, `activo=True`.
   - Secret is set via `set_clave(...)` (hashes with Django's `make_password`) and saved.
5. Catalog baselines (all `update_or_create`):
   - `catalogs.TipoServicio` (2): `Cita de consulta` (order 1), `Tratamiento estetico` (order 2).
   - `billing.CategoriaGasto` (8): `Alquiler`, `Servicios`, `Insumos`, `Equipamiento`, `Marketing`, `Sueldos`, `Mantenimiento`, `Otros`.
   - `catalogs.ProcEsteticosTipo` (1): `Laser`.
   - `catalogs.ProcEstetico` (3, all under `Laser`): `Depilacion definitiva` (order 1), `Tratamiento de manchas` (order 2), `Borrado de tatuajes` (order 3).
   - `catalogs.ServicioConfig` (4): three rows linking `Tratamiento estetico` to each procedure (precio 850, 650, 1500) and one row linking `Cita de consulta` with `proc_estetico=None` (precio 120).
   - `catalogs.AntecedenteMedico` (6): `Diabetes`, `Asma`, `Hipertension`, `Cancer`, `Otro`, `Ninguna`.
   - `catalogs.ImplanteInjerto` (5): `Menton`, `Mejillas`, `Nariz`, `Otro`, `Ninguno`.
   - `catalogs.CirugiaEstetica` (7): `Blefaroplastia`, `Rinoplastia`, `Bichectomia`, `Rinomodelacion`, `Lifting`, `Botox`, `Ninguna`.
   - `catalogs.GrupoOpciones` (2): `SI_NO` and `PROFUNDIDAD_TATUAJE`.
   - `catalogs.OpcionCatalogo` (4): `Si`/`No` under `SI_NO`; `Superficial`/`Profunda` under `PROFUNDIDAD_TATUAJE`.
   - `catalogs.TipoPiel` (6): `Piel normal`, `Mixta`, `Seca`, `Grasa`, `Desvitalizada`, `Hidratada`.
   - `catalogs.GradoDeshidratacion` (3): `Leve`, `Medio`, `Alto`.
   - `catalogs.GrosorPiel` (5): `Fina`, `Media fina`, `Media`, `Media gruesa`, `Gruesa`.
   - `catalogs.PatologiaCutanea` (28): fixed list ending in `Vitiligo`.
6. `catalogs.Sector` (3, `update_or_create` on `codigo`): `DEP`, `MAN`, `TAT` with descriptions matching the PDF.

**Transaction and idempotency**
- All writes run inside one `transaction.atomic`. Any exception rolls back the whole command. Confirmed by `test_transaction_rollback_on_failure`.
- All writes are `update_or_create` on stable natural keys (`rol`, `username`, `nombre`, `codigo`, `(tipo_servicio, proc_estetico)`, `nombre`, `codigo`, `(grupo, codigo)`, `codigo`). Running the command multiple times on the same database produces the same final state without duplicates.
- The command does **not** create or modify records of any other model. It does not touch demo staff, patients, prospects, agendas, allergies, biometric data, or notifications.

**Output summary (`_print_summary`)**
- Always printed on success: `Roles`, `Branch`, `Admin`, `Kiosk`, `Catalogs` counts.
- Final credentials block: admin username, email, name, kiosk code, kiosk secret — printed exactly once, in plaintext, only when the command succeeds.
- Static footer: `URL Admin: https://reactproject.site/admin` (note: hard-coded; not derived from any flag).
- Per-step output: "Branch created/updated", "Admin created/updated", "Kiosk created/updated", "Catalog baseline seeded.", "Sectors seeded."
- On failure: `_print_summary` is never called; `_summary_passwords` is never written.

**Tests (`backend/accounts/tests/test_seed_client_baseline.py`)**
- 10 end-to-end scenarios under `SeedClientBaselineTests`:
  1. `test_fresh_db_creates_all_baseline_records` — full record inventory and exact prices.
  2. `test_idempotent_rerun_no_duplicates` — no duplication on second non-interactive run.
  3. `test_non_interactive_skips_prompts` — `input` is never called.
  4. `test_non_interactive_missing_flags_aborts` — `CommandError` lists the missing flag and no rows are written.
  5. `test_weak_password_rejected` — Django's validators reject `short`.
  6. `test_malformed_email_rejected` — `not-an-email` is rejected.
  7. `test_duplicate_username_rejected` — pre-existing non-superuser with same username is untouched.
  8. `test_replace_main_branch_required_in_non_interactive` — different principal branch without the flag is rejected; old branch untouched.
  9. `test_replace_main_branch_updates` — flag demotes old principal; the supplied branch becomes the sole principal.
  10. `test_transaction_rollback_on_failure` — simulated mid-transaction failure leaves no rows in any baseline table.
- 3 helper tests under `CommandHelpersTest` for `_flag_for` and `_prompt_confirm`.
- Test isolation relies on the data migration `0008_data_migrate_sucursales` that creates `Sede Principal` with `direccion="Direccion Central"`; tests clear its `es_principal` flag in `setUp` and exclude it from assertions.

**Documentation**
- `docs/vps-setup-from-scratch.md` 5.2 option 1: usage, flags, prompt order, validations, idempotency, atomicity, replace-main-branch semantics, sample output.
- `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md`: nine requirements (Role baseline, Branch creation, Admin general creation, Tablet kiosk creation, Catalog baseline, Interactive mode, Non-interactive mode, Safety check on existing main branch, Atomic transaction, Output summary) with Given/When/Then scenarios.
- No fixtures, no wrapper scripts, no migration invokes it.

**Drift against current models (preservation implications)**
The command's inputs and writes are minimal and well-aligned with current models. The following observations affect how to preserve behavior, not change the command's purpose:
- `accounts.Usuario` has `first_name=None` and `last_name=None`; the model uses `primer_nombre`/`apellido_paterno` exclusively. The command's `defaults` match this contract.
- The required catalog baseline does not include the current `ProductoAlergia`, `TipoAlergia`, or `GravedadAlergia` catalogs. They were never part of the production bootstrap's documented scope. The 12+1-model table in the VPS guide already states this explicitly.
- `catalogs.ServicioConfig.sector` is a new field (added in migration `0005`); the command does not set it. Its `update_or_create` does not pass `sector`, so re-running leaves existing `sector` values untouched on operator-edited rows. This is idempotent but not "reconcile to baseline": if operators add a sector later, the command will not re-stamp it.
- The form configuration (`clinical.FichaSeccion`, `clinical.FichaCampo`) is **not** part of the production bootstrap; the VPS guide describes it as PDF-seed-only. Migration `0006_seed_sectores_and_reassign_fichaseccion` creates the three `Sector` records (DEP, MAN, TAT) on migrate, and the seed command upserts them again on top. This is intentional and matches the spec.
- The migration `0008_data_migrate_sucursales` already creates a `Sede Principal` row with `direccion="Direccion Central"` after migrate. The command's interactive default for branch name is `Sede Principal` and its `same_identity` check uses `nombre + ciudad + direccion`. On a fresh migrate-only database, the `Sede Principal` row's `direccion` does not match any value the command has written yet, so a fresh run that supplies only defaults will not be flagged as `same_identity`. Tests compensate by clearing `es_principal` in `setUp` and excluding the migration branch by name.
- Hard-coded summary footer URL `https://reactproject.site/admin` is not derivable from any flag. Behavior should be preserved as-is or moved to a constant; the OpenSpec should call it out explicitly.

**Safety properties of the clean baseline (preservation requirements)**
- The command does not delete any data; it never calls `delete()` and never calls any purge routine. It only creates or updates.
- It does not touch any data outside its own natural keys. Existing rows that match the natural keys are updated in place; existing rows that do not are untouched.
- All writes are atomic. There is no "partial commit" mode.
- Pre-transaction validation means failure leaves the database as it was.
- The only interactive moment that can abort is `_handle_existing_main_branch`'s confirmations; everything else fails fast with a `CommandError` before any write.

**Acceptance criteria for preserving the clean baseline's intended behavior**
A refactor that recreates or reformats this command MUST keep the following properties:

1. Command identity, file location, and CLI surface remain: `python manage.py seed_client_baseline` plus the 10 value flags, `--non-interactive`, and `--replace-main-branch`.
2. Pre-transaction validation identical to today: required non-empty, `admin_email` valid email, `admin_password` valid per Django's password validators, `kiosk_password` length ≥ 8, `admin_username` collision rejected only when existing user is not a superuser, `kiosk_code` rejected only when more than one existing kiosk shares the code.
3. Existing main branch safety check preserved in both modes, including `same_identity` semantics, "Continue? [Y/n]" (default yes when identical), "Replace the existing principal branch and demote all others? [y/N]" (default no when different), and the `--replace-main-branch` requirement in non-interactive mode.
4. One `transaction.atomic` boundary covering roles, branch, admin, kiosk, catalogs, and sectors. Any failure rolls back everything.
5. Same write set, same natural keys, same defaults inside `update_or_create`, and same per-record fields as today. `set_password` and `set_clave` are the only places where secrets touch storage.
6. Summary output still printed once, only on success, including the same five counts (`Roles`, `Branch`, `Admin`, `Kiosk`, `Catalogs`) and a final credentials block.
7. Existing 10 end-to-end tests plus 3 helper tests still pass without modification. Any refactor that changes a natural key, a default value, or a write field must update the corresponding assertion or the failing test in the same change.
8. The command continues to be a no-op with respect to demo data, prospects, patients, schedules, biometric data, allergies, notifications, sessions, audit logs, and any model not listed in its write set.
9. The command continues to be safe against a non-empty database: it never deletes rows, never truncates, and never reassigns branches other than demoting other `es_principal=True` rows.
10. The OpenSpec delta for any refactor MUST list every preserved behavior as a `MODIFIED` scenario (no removal) and add `ADDED` requirements only for the refactor's new behavior.

#### Reference target: `seed_pdf_baseline` (out of scope for this change, kept for context only)

This task is focused on documenting the clean baseline exactly, per the user's clarification. The recreation of `seed_pdf_baseline` is a follow-up work unit, not part of this artifact's deep review. The summary below is the minimum needed to keep the two commands decoupled during the eventual recreation:

- File: `backend/accounts/management/commands/seed_pdf_baseline.py`. Mixed demo/reset command.
- 1,051 lines; atomic via `@transaction.atomic` on `handle`.
- Writes roles, 3 branches (`Sede Principal`, `Sucursal Norte`, `Sucursal Sur`), 3 admin users (`admin.general`, `admin.norte`, `admin.sur`), 4 specialist users, 5 specialties + links, the same 13 catalog/sector set as the clean baseline, `FichaSeccion`/`FichaCampo` form configuration, 2 prospectos, 2 demo patients with full operation/cuota/pago/cita/biometric history, 3 tablet kiosks, and Mon–Fri 08:00–18:00 agendas for each specialist.
- Deletes all `AgendaExcepcionEspecialista`, `AgendaHabitualDia`, `AgendaHabitualEspecialista`, `DiaBloqueadoAgendaGlobal`, `HuellaBiometricaCliente`, `PagoRealizado`, `CuotaPlanPago`, `CitaMedica`, and `Operacion` rows before recreating its own.
- No CLI flags, no validation, no confirmation, no environment guard, no tests.
- Drift vs. current models: `Especialista.sucursal_base` is not set; `ServicioConfig.sector` is not set; schedules use weekday indices `0..4` (current `DiaSemana.LUNES..VIERNES` is `1..5`, `DOMINGO=0`); legacy mock biometric rows are created active with raw placeholder bytes despite the current `HuellaBiometricaCliente` model requiring inactive/legacy/empty template semantics; `template_format` and prospect-owned biometric flows are not represented; current allergy catalogs and `FichaSeccion.sector` are not consistently set.
- Required by `seed_branch_test_scenarios`, which assumes the branch names `Sucursal Norte` and `Sucursal Sur` and the admin usernames `admin.norte` and `admin.sur` exist.
- The recreation must use a shared seed library (see Recommendation) and must preserve the clean baseline's behavior bit-for-bit.

### Affected Areas
- `backend/accounts/management/commands/seed_client_baseline.py` — preserve current behavior; refactor is allowed only as long as the acceptance criteria above hold.
- `backend/accounts/tests/test_seed_client_baseline.py` — every existing test is a behavioral contract; tests must pass unchanged unless a contract is intentionally changed in the same delta.
- `openspec/changes/add-seed-client-baseline/` — the existing OpenSpec spec and tasks are the canonical contract; any preservation must be a `MODIFIED` scenario set, not a `REMOVED` one.
- `docs/vps-setup-from-scratch.md` (section 5.2 option 1) — operator-facing documentation of the clean baseline.
- `backend/accounts/management/commands/seed_pdf_baseline.py` — out of scope for this change, but listed because its recreation is a future change and its current drift is documented here for that follow-up.
- `backend/catalogs/migrations/0006_seed_sectores_and_reassign_fichaseccion.py` and `backend/operations/migrations/0008_data_migrate_sucursales.py` — they pre-create `Sector` rows and a `Sede Principal` row; the command's idempotency depends on these.
- `backend/{accounts,catalogs,billing,operations}/models.py` — current contracts (`Usuario` name fields, `Rol`, `Sucursal`, `TabletKiosko.set_clave`, catalog editable models, `CatalogoEditableModel` with `nombre`/`codigo` natural keys).

### Approaches
1. **Preserve in place** — keep `seed_client_baseline.py` byte-stable while the next change touches only `seed_pdf_baseline.py`.
   - Pros: Zero risk to the production baseline; tests stay green; OpenSpec untouched.
   - Cons: Does not address the user's intent to "recreate seed_pdf_baseline" or to align both with current models. The duplication between the two commands persists.
   - Effort: Low

2. **Extract a shared seed library and re-implement `seed_pdf_baseline` on top of it, leaving `seed_client_baseline` unchanged** — create a `backend/accounts/management/commands/_seed_baseline.py` (or app-level module) that exposes `seed_roles`, `seed_branches`, `seed_admins`, `seed_staff`, `seed_catalogs`, `seed_form_configuration`, `seed_prospects`, `seed_patients`, `seed_kiosks`, `seed_schedules`. `seed_client_baseline` calls only the ones it already uses; `seed_pdf_baseline` calls the full set and is rewritten in current-model form (specialist branch, sector, `DiaSemana`, biometric state).
   - Pros: Single source of catalog truth; both commands become thin orchestrators; `seed_pdf_baseline` can be made non-destructive and current-model-correct; tests for the clean baseline keep validating the production path.
   - Cons: A refactor that touches both commands must preserve every test in `test_seed_client_baseline.py` and every behavior listed in the acceptance criteria. Effort is medium-to-high and the changes are concentrated in one PR.
   - Effort: Medium

3. **Rewrite `seed_client_baseline` and `seed_pdf_baseline` from scratch on a canonical baseline module, refresh tests and OpenSpec** — broad rewrite of both commands.
   - Pros: Cleanest long-term; removes duplication and fixes model drift in one stroke.
   - Cons: Highest risk to the production command; requires updating or replacing every existing test, every spec scenario, and the VPS guide; almost certainly exceeds the 400-line review budget.
   - Effort: High

### Recommendation
Adopt approach 2. It is the only one that satisfies both the user's intent (recreate `seed_pdf_baseline` on current models) and the preservation requirements of the clean baseline. The implementation must be split into at least two work units so the clean baseline can be merged first and independently verified by the existing test suite:

- **Work unit A (preservation-first)**: extract a shared baseline library that is the single source of catalog literals and seed helpers; have `seed_client_baseline` call the library while keeping its public behavior, validation, prompts, and atomic transaction identical. The 10 end-to-end tests and 3 helper tests pass without modification. This unit is the safety floor.
- **Work unit B (recreate)**: re-implement `seed_pdf_baseline` on top of the shared library, fix model drift, remove the destructive cleanup, and either omit biometric templates or create them in the explicit inactive/legacy shape that current `HuellaBiometricaCliente` requires. New tests are added under `test_seed_pdf_baseline.py`. This unit is the feature.

If chained delivery is not viable within a single work unit, prefer the lightest preservation change first, gate the PDF rewrite behind a follow-up task, and keep the clean baseline behavior frozen in the meantime.

### Risks
- Recreating the clean baseline while changing the public contract, the natural keys, or the defaults will silently break production onboarding scripts and the OpenSpec spec.
- Idempotency depends on stable natural keys (`rol`, `username`, `nombre`, `codigo`, `(grupo, codigo)`). Any refactor that introduces `update_or_create` on a different lookup will create duplicates.
- Hard-coded URL footer in the summary is not configurable. Operators deploy under different domains today and rely on ignoring this line; removing it would change operator-facing output. If it must change, the new behavior must be approved.
- The migration `0008_data_migrate_sucursales` pre-creates a `Sede Principal` row that can interfere with `same_identity` detection. Tests and onboarding scripts already work around this; any refactor must keep the same workaround or document the change.
- The `seed_client_baseline` baseline intentionally excludes the three allergy catalogs. Operators that need them must add them by hand; the 2026-07-31 domain correction makes this exclusion mandatory for both commands.
- The destructive cleanup inside `seed_pdf_baseline` is not in scope here, but the future rewrite of that command must be designed as a separate task with its own safety contract.
- Existing tests assume `DJANGO_USE_LOCAL_DB` and the default SQLite engine. Any refactor that introduces a database-specific path (e.g., PostgreSQL-only `TRUNCATE` or sequences) will break the local test workflow and must be guarded.

### Ready for Proposal
Yes, narrowly. The proposal for this change should:
1. Lock the clean baseline behavior in a `MODIFIED` requirements block of the existing `add-seed-client-baseline` spec, listing each acceptance criterion above as a scenario.
2. Define the shared baseline library as the implementation strategy.
3. Define the recreation of `seed_pdf_baseline` as a separate sub-task with its own scope, model alignment, and tests.
4. Confirm with the operator whether the hard-coded `https://reactproject.site/admin` summary footer should be replaced, parameterized, or kept.
5. Closed by the 2026-07-31 domain correction: the clean baseline MUST NOT seed the three allergy catalogs; it MUST guarantee the evidence-backed aesthetic procedure/service set instead.

---

## Result Contract (this exploration)

### status
`success`

### executive_summary
The clean baseline command `seed_client_baseline` is a self-contained, atomic, non-destructive, idempotent Django management command that creates exactly one principal branch, one general admin (superuser), one tablet kiosk, four roles, the full 13-model operational catalog (with the exact literals verified), and the three `Sector` records. It has 10 value flags, 2 control flags, an interactive mode with sensible defaults and pre-transaction validation, and a 794-line implementation covered by 10 end-to-end + 3 helper tests that pass byte-stable. The recreation of `seed_pdf_baseline` is the second and last work unit in this change and is documented here only to keep it decoupled from the clean baseline during the eventual rewrite.

### artifacts
- `openspec/changes/reform-database-seed-scripts/exploration.md` — this file, updated to narrow scope to the two commands and add a verified deep review of the clean baseline.
- Read-only verification sources (no modifications):
  - `backend/accounts/management/commands/seed_client_baseline.py`
  - `backend/accounts/tests/test_seed_client_baseline.py`
  - `backend/accounts/management/commands/seed_pdf_baseline.py`
  - `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md`
  - `backend/catalogs/migrations/0006_seed_sectores_and_reassign_fichaseccion.py`
  - `backend/operations/migrations/0008_data_migrate_sucursales.py`
  - `docs/vps-setup-from-scratch.md` (section 5.2 option 1)

### next_recommended
1. Run a proposal that locks the clean baseline behavior as a `MODIFIED` block in `add-seed-client-baseline/specs/seed-client-baseline/spec.md`, with the 10 acceptance criteria from this exploration as scenarios.
2. Run a design phase that defines the shared seed library (catalog literals as a single source of truth) and the migration of `seed_client_baseline` to call it without changing public behavior.
3. Run tasks/apply that move `seed_client_baseline` onto the shared library in a small, independently verifiable work unit (the existing test suite is the safety floor).
4. Queue `seed_pdf_baseline` recreation as a follow-up work unit in a separate change (or as a second PR in the same change), with new tests under `test_seed_pdf_baseline.py`.
5. The operator decisions are now recorded: parameterize the hard-coded admin URL, keep all three allergy catalogs unseeded, and guarantee the exact current aesthetic procedure/service set in both commands.

### risks
- Refactor that changes any natural key (`rol`, `username`, `nombre`, `codigo`, `(tipo_servicio, proc_estetico)`, `(grupo, codigo)`) silently breaks idempotency and duplicates rows on re-run.
- Refactor that changes the single `transaction.atomic` boundary loses the all-or-nothing guarantee that `test_transaction_rollback_on_failure` asserts.
- The `seed_client_baseline` write set MUST continue excluding `ProductoAlergia`, `TipoAlergia`, and `GravedadAlergia`; widening that write set would violate the corrected domain requirement. `FichaSeccion`/`FichaCampo` also remain outside its write set.
- The hard-coded URL footer in the summary is not configurable; operators deploy under different domains today and rely on ignoring this line.
- Migration `0008_data_migrate_sucursales` pre-creates a `Sede Principal` row whose `direccion="Direccion Central"` may fail a strict `same_identity` check on a fresh migrate-only database; tests already compensate by clearing `es_principal` in `setUp` and excluding the migration branch by name. Any refactor must keep or explicitly improve this workaround.
- `ServicioConfig.sector` is a new field (migration `0005`) that the command does not set; the command's idempotency leaves operator-edited `sector` values untouched, which is correct today but is not "reconcile to baseline".

### skill_resolution
- Loaded `sdd-explore` from `/home/fabianrivero/.config/opencode/skills/sdd-explore/SKILL.md` and followed Section B (retrieval) + Section C (persistence) from `skills/_shared/sdd-phase-common.md`. The prior exploration artifact was retrieved and rewritten to narrow scope.
- No other skills were required for this research-only phase. The shared `seed_*` baseline work will require `sdd-propose`, `sdd-spec`, `sdd-design`, `sdd-tasks`, `sdd-apply`, `sdd-verify`, and `sdd-archive` in subsequent phases.

---

## Domain Correction: Shared Aesthetic Procedure Set (2026-07-31)

### Correction

The requested shared data are not allergy catalogs. `ProductoAlergia`, `TipoAlergia`, and `GravedadAlergia` MUST remain unseeded by both `seed_client_baseline` and `seed_pdf_baseline`; the audit below remains the evidence for that exclusion.

The evidence-backed shared set is the current aesthetic service graph already present in both commands:

| Model / natural key | Exact current values |
| --- | --- |
| `ProcEsteticosTipo.tipo` | `Laser`; descripcion `Procedimientos laser de la ficha medica.`; orden `1`; activo `True` |
| `ProcEstetico(tipo_p_estetico, proceso)` | `Depilacion definitiva`; descripcion `Procedimiento de depilacion definitiva.`; orden `1`; activo `True` |
| same | `Tratamiento de manchas`; descripcion `Procedimiento para tratamiento de manchas.`; orden `2`; activo `True` |
| same | `Borrado de tatuajes`; descripcion `Procedimiento para borrado de tatuajes.`; orden `3`; activo `True` |
| `ServicioConfig(tipo_servicio, proc_estetico)` | Each procedure linked to the treatment service; prices `850.00`, `650.00`, `1500.00` respectively; activo `True` |

`Tratamiento de manchas` is therefore the unambiguous current entity for the requested pigmentation/dark-spot treatment. Evidence: both commands use that exact `ProcEstetico.proceso`; migration `catalogs/0006_seed_sectores_and_reassign_fichaseccion.py` includes it in `DEP_PROC_NAMES`; current tests already exercise the same procedure graph.

### Exact identity caveat

The commands currently disagree on the treatment `TipoServicio.tipo`: `seed_client_baseline` uses `Tratamiento estetico`, while `seed_pdf_baseline` uses `Tratamiento estético`. Because `TipoServicio.tipo` is unique and part of each `ServicioConfig` relationship, preserving both would create distinct service identities. The corrected specification therefore requires equivalent observable treatment links and records this exact design-time reconciliation risk; it does not guess that accents are interchangeable and does not mandate a shared internal library.

### Required behavior correction

- `seed_client_baseline` MUST guarantee the complete three-procedure set and links within its existing single transaction.
- Missing subsets MUST be completed; stale mutable values at specified natural keys MUST be reconciled; reruns MUST not duplicate records.
- Unrelated and operator custom rows outside specified natural keys MUST remain unchanged; neither command may delete them.
- Any failure during creation or reconciliation MUST roll back every write from that invocation.
- `seed_pdf_baseline` MUST continue/create the same set as part of its demo baseline.
- Cross-command consistency is measured from resulting model identities, values, and relationships, not from whether commands call a common helper.

### Superseded exploration conclusions

The earlier statements at lines 213, 223, and 251 treated allergy seeding as an open question; that question is now closed: allergy catalogs remain unseeded. Earlier preservation language that described the aesthetic set as merely existing behavior is widened by the corrected requirement: the clean baseline must explicitly guarantee that set and remain consistent with the PDF baseline.

---

## Allergy Catalog Audit (2026-07-31)

### Goal

Establish a single evidence-backed truth about the three allergy catalogs (`ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`) before any design or implementation, and remove any invented clinical values from the delta spec.

### Models (authoritative by schema)

- `backend/catalogs/models.py:255-285` — `ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`. Each inherits `common.models.CatalogoEditableModel` (descripcion, orden, activo) plus `nombre = CharField(max_length=120, unique=True)`. Natural key: `nombre`. Default order: `("orden", "nombre")`. DB tables: `productos_alergia`, `tipos_alergia`, `gravedades_alergia`.
- `backend/common/models.py:12-17` — base confirms ordering by `(orden, nombre)` and `activo=True` default.
- `backend/clinical/models.py:65-98` — `AnalisisEsteticoAlergia` is the only consumer FK model; it does not impose any option list of its own. The model enforces `on_delete=PROTECT` and `UniqueConstraint(analisis, producto_alergia, tipo_alergia, gravedad)`.
- `backend/catalogs/migrations/0001_initial.py:65-188` — schema only. No data inserted for these tables.

### Seed commands (exhaustive search)

| Source | Path | Allergy rows? |
| --- | --- | --- |
| `seed_client_baseline.py` | `backend/accounts/management/commands/seed_client_baseline.py` | No — confirmed via grep for `ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`, `producto_alergia`, `tipos_alergia`, `gravedades_alergia`, `alergi` (zero hits in the catalog baseline block at L647-796). |
| `seed_pdf_baseline.py` | `backend/accounts/management/commands/seed_pdf_baseline.py` | No — same grep produced zero hits in the PDF baseline. |
| `seed_production_baseline.py` | `backend/accounts/management/commands/seed_production_baseline.py` | No (matches documented behavior — production baseline intentionally ships zero catalog rows). |
| `seed_branch_test_scenarios.py` | `backend/accounts/management/commands/seed_branch_test_scenarios.py` | Not searched for catalogs directly because it explicitly assumes the baseline already ran; verified by absence of any `ProductoAlergia` import. |
| All migrations (data migrations) | `backend/{catalogs,billing,operations,clinical}/migrations/*.py` | No data migration inserts allergy rows. |
| Fixtures | `*/fixtures/*.json|yaml` | None exist in this repo (confirmed via `glob` of backend apps — only media fixture). |

### Tests

- `backend/accounts/tests/test_seed_client_baseline.py` — no allergy assertions present. The 10 end-to-end tests cover roles, branch, admin, kiosk, sector, and the 12 non-allergy catalog blocks.
- `backend/tests/test_clinic_business_logic.py:27` — uses `GradoDeshidratacion`, not an allergy catalog.
- No other test file references any of the three allergy models or any of their rows.

### Frontend

- `glob` + grep across `frontend/` for `alerg`, `Alerg`, `ALERG`, `Medicamentos|Alimentos|Cosmeticos|Latex|Cutanea|Respiratoria|Digestiva|Sistemica|Leve|Moderada|Severa`, `productoAlergia|tipoAlergia|gravedadAlergia`, etc. — zero hits. The frontend reads allergy options purely from the backend catalog endpoints (when implemented) and ships no embedded list.

### Local database (read-only via `sqlite3` CLI)

- `backend/db.sqlite3` exists and is a regular SQLite 3 file (no Django environment workaround used).
- `SELECT COUNT(*) FROM productos_alergia / tipos_alergia / gravedades_alergia` — `0 / 0 / 0`. All three tables are empty.
- This is consistent with the source evidence (no seeder touches them) and confirms the local DB cannot be used to derive values either.

### Docs

- `docs/vps-setup-from-scratch.md:441-461` — lists the 12 catalog models seeded by both commands AND explicitly states: "**Catálogos NO cargados** (quedan vacíos y hay que popularlos a mano desde el admin si los necesitás): `ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`." This is the only authoritative human-facing statement and it confirms absence, not a values list.

### Candidate lists and verdict

The original delta spec (`specs/seed-client-baseline/spec.md` lines 24-46, prior version) hard-coded invented clinical values:

- `ProductoAlergia`: `Medicamentos`, `Alimentos`, `Cosméticos`, `Látex`, `Otros`.
- `TipoAlergia`: `Cutánea`, `Respiratoria`, `Digestiva`, `Sistémica`, `Otra`.
- `GravedadAlergia`: `Leve`, `Moderada`, `Severa`.

These lists appear nowhere in the codebase, migrations, fixtures, frontend, or local DB. They are not evidence-backed. Per the SDD rule "do not invent clinical catalog values", they MUST NOT be promoted into the spec as canonical literal lists.

### Consumers and consequence of changing values

- Clinical FKs (`backend/clinical/models.py:65-98`) reference these tables with `PROTECT`, so adding a row is safe, but a value rename would orphan existing `AnalisisEsteticoAlergia` rows.
- The frontend reads allergy options from the catalog (no embedded fallback), so a renamed value would silently disappear from UI until the operator re-saves.
- Seed idempotency depends on `update_or_create(nombre=...)`; renaming a canonical value would cause duplicates on rerun.
- Operators that already populated allergy rows manually would see no harm from a seeded list, but ONLY when their values match the canonical set; mismatches would create duplicates.

### Decision (superseded and corrected)

The prior audit correctly proved that no canonical allergy values exist, but its conditional seeding path is superseded by the domain correction above. The final requirement is unconditional:

1. `seed_client_baseline` MUST NOT create or update `ProductoAlergia`, `TipoAlergia`, or `GravedadAlergia` rows.
2. `seed_pdf_baseline` MUST NOT create or update those rows.
3. Existing operator-managed allergy rows MUST remain unchanged.
4. The shared command outcome concerns the exact aesthetic procedure/service set documented above, not allergy data.

The invented allergy lists remain rejected and MUST NOT be promoted into specs, tests, migrations, fixtures, or command literals.
