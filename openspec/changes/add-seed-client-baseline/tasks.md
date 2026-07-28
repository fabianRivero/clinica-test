# Tasks: add-seed-client-baseline

Tracked implementation tasks for the `seed_client_baseline` management command.

## 1. Command implementation

- [x] 1.1 Create `backend/accounts/management/commands/seed_client_baseline.py` with module docstring, CLI flags, and handle() entry point
- [x] 1.2 Implement interactive/non-interactive input resolution and validation (non-empty, email, password >= 8, uniqueness)
- [x] 1.3 Implement `_seed_roles` — exactly 4 baseline roles (ADMIN_PRINCIPAL, ADMIN_SUCURSAL, TRABAJADOR, CLIENTE)
- [x] 1.4 Implement `_seed_branch` — principal branch with `es_principal=False` on others
- [x] 1.5 Implement `_seed_admin` — `Usuario.create_user` + `set_password`, ADMIN_PRINCIPAL, is_staff/is_superuser/is_active True
- [x] 1.6 Implement `_seed_kiosk` — `TabletKiosko` with `set_clave()`, linked to principal branch
- [x] 1.7 Implement `_seed_catalogs` — copy exact values from `seed_pdf_baseline._seed_catalogs()` (12 catalog tables) as standalone literals
- [x] 1.8 Implement `_seed_sectors` — 3 Sector records (DEP, MAN, TAT)
- [x] 1.9 Implement main-branch safety check (interactive confirm / `--replace-main-branch`)
- [x] 1.10 Wrap writes in `transaction.atomic`
- [x] 1.11 Print final summary with credentials shown once

## 2. Tests

- [x] 2.1 Create `backend/accounts/tests/` directory with `__init__.py` and `test_seed_client_baseline.py`
- [x] 2.2 test_fresh_db_creates_all_baseline_records
- [x] 2.3 test_idempotent_rerun_no_duplicates
- [x] 2.4 test_non_interactive_skips_prompts
- [x] 2.5 test_non_interactive_missing_flags_aborts
- [x] 2.6 test_weak_password_rejected
- [x] 2.7 test_malformed_email_rejected
- [x] 2.8 test_duplicate_username_rejected
- [x] 2.9 test_replace_main_branch_required_in_non_interactive
- [x] 2.10 test_replace_main_branch_updates
- [x] 2.11 test_transaction_rollback_on_failure

## 3. Verification

- [x] 3.1 `python manage.py check` passes
- [x] 3.2 All new tests pass with `DJANGO_USE_LOCAL_DB=True`
- [x] 3.3 Smoke test: `seed_client_baseline --non-interactive` on SQLite succeeds