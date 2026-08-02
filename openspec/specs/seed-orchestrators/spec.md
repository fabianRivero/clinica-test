# Delta for seed-orchestrators

## ADDED Requirements

### Requirement: Orchestrator Command Identifier

`reset_pdf_baseline` MUST be invokable as `python manage.py reset_pdf_baseline`. It MUST live in `backend/accounts/management/commands/reset_pdf_baseline.py` with `BaseCommand` as its base.

#### Scenario: Command registered and importable
- GIVEN the `accounts` app is installed
- WHEN an operator imports `accounts.management.commands.reset_pdf_baseline.Command`
- THEN the import resolves without `ImportError`
- AND `Command.__bases__` includes `BaseCommand`

### Requirement: Pre-Write Environment Guard

`reset_pdf_baseline.handle` MUST call `require_dev_or_test()` first, before any write or `call_command`. If `settings.ENVIRONMENT` is not in `{"development", "test"}` (case-insensitive, whitespace-stripped), the command MUST raise `CommandError` and write no rows.

#### Scenario: Rejects production pre-write
- GIVEN `settings.ENVIRONMENT == "production"`
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command raises `CommandError` whose message contains `"production"`
- AND record counts are unchanged from the pre-call snapshot

#### Scenario: Rejects staging pre-write
- GIVEN `settings.ENVIRONMENT == "staging"`
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command raises `CommandError` and record counts are unchanged

#### Scenario: Rejects empty environment pre-write
- GIVEN `settings.ENVIRONMENT` is unset or empty
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command raises `CommandError` and record counts are unchanged

#### Scenario: Accepts development
- GIVEN `settings.ENVIRONMENT == "development"` and demo data is present
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command completes without raising

#### Scenario: Accepts test
- GIVEN `settings.ENVIRONMENT == "test"` and demo data is present
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command completes without raising

### Requirement: Destructive Wipe Notification

`reset_pdf_baseline` MUST write a destructive-wipe warning header to `self.stdout` before any inner command. The header MUST use `self.style.WARNING` and MUST contain the literal phrase `DESTRUCTIVE WIPE`.

#### Scenario: Warning header precedes inner commands
- GIVEN a development environment with demo data
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN `self.stdout` receives a `WARNING`-styled line containing `DESTRUCTIVE WIPE` before any line from `purge_data_keep_admin` or `seed_pdf_baseline`

### Requirement: Single Transaction Boundary

`reset_pdf_baseline.handle` MUST be wrapped in one `transaction.atomic` block enclosing `call_command("purge_data_keep_admin", "--force", stdout=self.stdout)` and `call_command("seed_pdf_baseline", stdout=self.stdout)`. Both calls MUST pass `stdout=self.stdout`.

#### Scenario: Atomic block encloses both inner commands
- GIVEN the source of `reset_pdf_baseline.py`
- WHEN inspected via `ast.parse` or static reading
- THEN the function decorated with `@transaction.atomic` is `handle`
- AND `handle` calls `call_command("purge_data_keep_admin", "--force", stdout=...)` then `call_command("seed_pdf_baseline", stdout=...)`
- AND both calls are inside the same atomic block

#### Scenario: Mid-flight failure rolls back the purge
- GIVEN `settings.ENVIRONMENT == "test"` and demo data including a `Cliente` row exists
- WHEN `call_command("seed_pdf_baseline")` is patched via `unittest.mock.patch` to raise `RuntimeError("boom")`
- AND an operator runs `python manage.py reset_pdf_baseline`
- THEN the command re-raises `RuntimeError`
- AND the pre-call `Cliente` rows are still present (the purge rolled back)

### Requirement: Idempotent Destructive-Then-Seed Waveform

Two consecutive `reset_pdf_baseline` runs on the same development database MUST produce byte-stable record counts across `Rol`, `Sucursal`, `Usuario`, `Especialista`, `Especialidad`, `TipoServicio`, `ProcEsteticosTipo`, `ProcEstetico`, `ServicioConfig`, `Prospecto`, `Cliente`, `TabletKiosko`, `AgendaHabitualEspecialista`, and `AgendaHabitualDia`.

#### Scenario: Two consecutive runs converge
- GIVEN `settings.ENVIRONMENT == "development"` and demo data exists
- WHEN an operator runs `python manage.py reset_pdf_baseline` twice in sequence
- THEN the post-run-1 record-count snapshot equals the post-run-2 record-count snapshot

### Requirement: No-Op Safety on Empty Database

When the database has no demo data, `reset_pdf_baseline` MUST complete without raising and MUST leave the database in the same state as a fresh `seed_pdf_baseline` run.

#### Scenario: Empty database runs cleanly
- GIVEN `settings.ENVIRONMENT == "development"` and only `accounts.Rol`, `accounts.Usuario`, `auth.Group`, `auth.Permission`, `contenttypes.ContentType` are non-empty
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command completes without raising
- AND `Rol`, `Sucursal`, `Usuario`, `ProcEstetico`, `ServicioConfig`, `TabletKiosko` counts match a fresh `seed_pdf_baseline` run on the same empty database

### Requirement: Sibling Command Non-Modification

`reset_pdf_baseline` MUST NOT modify the source of `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, or `env_guard.py`. It MUST compose them via `call_command` only.

#### Scenario: Sibling command sources are byte-stable
- GIVEN the pre-change source bytes of `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, `env_guard.py`
- WHEN this change is applied
- THEN `git diff` against the parent commit shows no changes to any sibling file
- AND each sibling's post-change bytes equal its pre-change bytes

### Requirement: Pre-Purge Foreign-Key Nullification

`reset_pdf_baseline.handle` MUST nullify the `sucursal_id` (and any other foreign key on `Usuario` that points to a table the inner purge is about to clear) on every preserved superuser BEFORE invoking `call_command("purge_data_keep_admin", "--force", ...)`. The nullification MUST be performed via a queryset `Usuario.objects.filter(pk__in=preserved_ids).update(sucursal=None)` so the assignment is one statement and bypasses any pre-save hook. The selection of preserved users MUST mirror the selection used by `purge_data_keep_admin` when no `--username` is passed (i.e., `is_superuser=True`). The command MUST emit a `WARNING`-styled line indicating how many preserved superusers had their `sucursal_id` nullified.

#### Scenario: Preserved superuser has sucursal_id nullified before the inner purge runs
- GIVEN a development environment where a superuser has `sucursal_id` pointing to a `Sucursal` row
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN before the inner `purge_data_keep_admin` is invoked, the preserved superuser's `sucursal_id` is set to `NULL` via a queryset update
- AND the command emits a `WARNING`-styled line containing "Pre-purge integrity" and the count of nullified superusers

#### Scenario: Full waveform commits clean on a FK-violating state
- GIVEN a database state where a preserved superuser's `sucursal_id` points to a non-existent `Sucursal` row
- WHEN an operator runs `python manage.py reset_pdf_baseline`
- THEN the command completes without raising `IntegrityError`
- AND after the run, `PRAGMA foreign_key_check` returns no rows

#### Scenario: Failed seed rolls back the pre-purge nullification
- GIVEN a preserved superuser linked to a `Sucursal` row
- WHEN the inner `seed_pdf_baseline` raises (e.g., a library helper is patched to raise)
- THEN the outer `transaction.atomic` rolls back the pre-purge FK nullification
- AND the preserved superuser's `sucursal_id` is restored to its pre-call value
- AND the database is unchanged from the pre-call snapshot
