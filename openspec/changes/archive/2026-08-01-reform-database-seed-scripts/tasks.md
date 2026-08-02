# Tasks: Reform Database Seed Scripts

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | A1 ~50 / A2 ~180 / B1 ~340 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | A1 → A2 → B1 (stacked-to-main) |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| A1 | Data migration + settings | PR 1 | base=main; <80 lines; no behavior change |
| A2 | Library + URL/env helpers + 5 new tests | PR 2 | base=main; <200 lines; 13 existing tests green |
| B1 | `seed_pdf_baseline` rewrite + tests | PR 3 | base=main; <400 lines; env guard + deterministic |

## Phase 1: Work Unit A1 — Migration + Settings

- [x] 1.1 Add `catalogs/migrations/0007_normalize_tipo_servicio_estetico.py`: rename `Tratamiento estético` → `Tratamiento estetico` and reassign `ServicioConfig.tipo_servicio_id` in one transaction; no-op when canonical.
- [x] 1.2 In `backend/config/settings.py`, add `BASE_URL`, `SEED_ADMIN_URL`, `ENVIRONMENT` from `DJANGO_*` env vars (defaults per D4/D5).
- [x] 1.3 Verify: `python manage.py migrate` forward+reverse on SQLite; FK reassignment intact; 13 client tests green.

## Phase 2: Work Unit A2 — Library + URL/Env Helpers + Client Tests

- [x] 2.1 Create `backend/accounts/management/_baselines/__init__.py` + `clean_baseline.py` exposing `seed_roles`, `seed_branches`, `seed_admins`, `seed_staff`, `seed_aesthetic_catalog`, `seed_form_configuration`, `seed_prospects`, `seed_formal_patients`, `seed_schedules`, `seed_tablet_kiosks` as `update_or_create`; no `@transaction.atomic`.
- [x] 2.2 Create `_baselines/url.py::resolve_admin_url()` (D4) and `env_guard.py::require_dev_or_test()` (D5).
- [x] 2.3 In `commands/seed_client_baseline.py`, replace inline aesthetic literals with `clean_baseline.seed_aesthetic_catalog()` and footer URL with `resolve_admin_url()`; keep CLI/validation/prompts/transaction.
- [x] 2.4 In `tests/test_seed_client_baseline.py`, preserve 13 existing tests; add `test_admin_url_uses_settings_seed_admin_url`, `test_admin_url_falls_back_to_base_url`, `test_aesthetic_set_complete_when_partial`, `test_allergy_catalogs_unchanged`, `test_invalid_url_aborts_pre_write`.
- [x] 2.5 Add `tests/test_clean_baseline.py` with unit tests for `resolve_admin_url` (explicit/fallback/invalid) and `require_dev_or_test` (rejects prod/staging, accepts dev/test).
- [x] 2.6 Verify: `python manage.py test accounts.tests.test_seed_client_baseline accounts.tests.test_clean_baseline` — 13/13 + new tests pass; `seed_client_baseline --non-interactive ...` end-to-end.

## Phase 3: Work Unit B1 — PDF Rewrite + Env Guard + New Tests

- [x] 3.1 Rewrite `commands/seed_pdf_baseline.py` `handle()`: `require_dev_or_test` pre-transaction, then `clean_baseline` helpers per D6/D9/D10 inside one `transaction.atomic`; remove `_clear_business_data`, `_clear_schedule_configuration`, and the `ADMINISTRADOR` purge.
- [x] 3.2 Add `admin.demo` to admin tuple (D6); use fixed identifiers (`prospecto.demo1`, `cliente.demo1`, `KIOSKO-DEMO-PRINCIPAL`) and module-level demo timestamps (D7); no `timezone.now()` outside constants.
- [x] 3.3 Create `tests/test_seed_pdf_baseline.py`: `test_env_guard_rejects_production` (CommandError pre-write, no rows), `test_env_guard_accepts_development_and_test`, `test_deterministic_record_counts_across_runs`, `test_demo_admin_distinct_from_clean_admin`, `test_no_delete_calls_on_operational_tables` (AST on nine tables), `test_full_baseline_reproduction`.
- [x] 3.4 Update `docs/vps-setup-from-scratch.md` 5.2: one short paragraph on `SEED_ADMIN_URL`/`BASE_URL` override and one on the `ENVIRONMENT` guard.
- [x] 3.5 Verify: `python manage.py test accounts.tests.test_seed_pdf_baseline` passes; `ENVIRONMENT=production python manage.py seed_pdf_baseline` aborts pre-write; rerun on dev yields identical record counts.

## Phase 4: Rollout

- [x] 4.1 Land A1; confirm migration reverse on SQLite leaves FK rows intact. *(Marked complete by `sdd-archive` reconciliation: A1 is operationally merged per `verify-report.md`; forward+reverse migration on SQLite verified with FK rows intact.)*
- [x] 4.2 Land A2; confirm 13/13 client tests green before opening B1. *(Marked complete by `sdd-archive` reconciliation: A2 is operationally merged per `verify-report.md`; 55/55 tests green including the original 13 client tests.)*
- [x] 4.3 Surface chain strategy (stacked-to-main vs feature-branch-chain) to user before apply; cache in `openspec/config.yaml` `persistence.chain_strategy` and update `Chain strategy` line. *(Resolved: user chose `stacked-to-main`; `openspec/config.yaml:64` updated to `chain_strategy: stacked-to-main`; forecast line above updated.)*
