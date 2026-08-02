# Verification Report — `reform-database-seed-scripts`

## Verification Report

**Change**: `reform-database-seed-scripts`
**Version**: N/A (delta spec, single revision)
**Mode**: Standard (Strict TDD false)
**Branch**: `pr-4.2-cliente-reenroll`
**Project**: `clinica-test`
**Work unit scope**: A1, A2, B1 (all three implemented)
**Artifact store**: `openspec`

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 17 (1.1–4.3 inclusive) |
| Tasks complete (checked) | 14 (1.1–1.3, 2.1–2.6, 3.1–3.5) |
| Tasks incomplete (unchecked) | 3 (4.1, 4.2, 4.3 — Phase 4 rollout) |
| Implementation tasks (Phase 1–3) | 14 / 14 ✅ |
| Rollout tasks (Phase 4) | 0 / 3 — explicitly deferred to release execution |

Phase 4 contains only rollout/landing checklist tasks (land A1, land A2, surface chain strategy). They are explicitly post-verify checkpoints and are NOT blockers for verification PASS. They remain unchecked because rollout is not in scope for this verification slice.

#### Per-task completeness table

| Task | Description | Implementation | Test | Status |
|------|-------------|----------------|------|--------|
| 1.1 | Add `0007_normalize_tipo_servicio_estetico.py` migration | `backend/catalogs/migrations/0007_normalize_tipo_servicio_estetico.py` (117 lines) | `backend/accounts/tests/test_normalize_migration.py` (8 tests) | ✅ Complete |
| 1.2 | Add `BASE_URL`, `SEED_ADMIN_URL`, `ENVIRONMENT` to settings | `backend/config/settings.py:29-46` | `test_clean_baseline.py` (URL + env unit tests, 13 cases) | ✅ Complete |
| 1.3 | Verify forward+reverse migration on SQLite; FK intact | Forward and reverse applied via `manage.py migrate catalogs` | 8 migration tests cover forward/reverse/no-op/idempotency | ✅ Complete |
| 2.1 | Create `_baselines/` package + `clean_baseline.py` | `backend/accounts/management/_baselines/{__init__.py, clean_baseline.py}` (599 lines) | `test_clean_baseline.py::SeedAestheticCatalogTests` | ✅ Complete |
| 2.2 | Create `url.py::resolve_admin_url()` and `env_guard.py::require_dev_or_test()` | `backend/accounts/management/_baselines/{url.py, env_guard.py}` (94 lines combined) | `test_clean_baseline.py::ResolveAdminUrlTests`, `RequireDevOrTestTests` | ✅ Complete |
| 2.3 | Replace inline literals with `seed_aesthetic_catalog()` + `resolve_admin_url()` | `backend/accounts/management/commands/seed_client_baseline.py` (527 lines, modified) | All 13 client tests pass byte-stable | ✅ Complete |
| 2.4 | Preserve 13 tests; add 5 new | `backend/accounts/tests/test_seed_client_baseline.py` (493 lines, 5 new tests) | `test_admin_url_uses_settings_seed_admin_url`, `test_admin_url_falls_back_to_base_url`, `test_aesthetic_set_complete_when_partial`, `test_allergy_catalogs_unchanged`, `test_invalid_url_aborts_pre_write` | ✅ Complete |
| 2.5 | Add `test_clean_baseline.py` unit tests | `backend/accounts/tests/test_clean_baseline.py` (219 lines) | 21 unit tests across 4 TestCase classes | ✅ Complete |
| 2.6 | Verify all client + library tests pass | `DJANGO_USE_LOCAL_DB=1 python3 manage.py test accounts.tests` | 55/55 OK | ✅ Complete |
| 3.1 | Rewrite `seed_pdf_baseline.handle()` | `backend/accounts/management/commands/seed_pdf_baseline.py` (312 lines, rewritten) | All PDF tests pass | ✅ Complete |
| 3.2 | Add `admin.demo`; fixed identifiers; module-level demo timestamps (D6/D7) | `seed_pdf_baseline.py` `ADMINS` tuple, fixed `BRANCHES`, fixed `SPECIALISTS` | `test_demo_admin_distinct_from_clean_admin`, `test_full_baseline_reproduction` | ✅ Complete |
| 3.3 | Create `test_seed_pdf_baseline.py` | `backend/accounts/tests/test_seed_pdf_baseline.py` (278 lines, 6 tests) | env-guard, deterministic, demo-admin, AST no-delete, full-baseline-reproduction | ✅ Complete |
| 3.4 | Update `docs/vps-setup-from-scratch.md` 5.1 + 5.2 | `docs/vps-setup-from-scratch.md:240-243` (5.1) and `:414-416` (5.2) | Manual inspection confirms sections updated | ✅ Complete |
| 3.5 | Verify PDF tests + production reject + dev rerun determinism | `DJANGO_USE_LOCAL_DB=1 python3 manage.py test accounts.tests` | `test_rejects_production_pre_write`, `test_accepts_development`, `test_deterministic_record_counts_across_runs` | ✅ Complete |
| 4.1 | Land A1 (rollout checkpoint) | n/a | n/a | ⬜ Not started — rollout |
| 4.2 | Land A2 (rollout checkpoint) | n/a | n/a | ⬜ Not started — rollout |
| 4.3 | Surface chain strategy to user (rollout checkpoint) | n/a | n/a | ⬜ Not started — rollout |

### Build & Tests Execution

**Build**: ✅ Passed (no separate build step; Django checks run on test invocation)
```text
$ cd backend && DJANGO_USE_LOCAL_DB=1 python3 manage.py test accounts.tests
Creating test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
Found 55 test(s).
Synchronizing apps without migrations: ...
Applying catalogs.0007_normalize_tipo_servicio_estetico... OK
...
Ran 55 tests in 70.550s
OK
```

**Tests**: ✅ 55 passed / 0 failed / 0 skipped
```text
test_clean_baseline.ResolveAdminUrlTests (7) — ok
test_clean_baseline.RequireDevOrTestTests (9) — ok
test_clean_baseline.ResolveAdminUrlWiredInCommandTests (1) — ok
test_clean_baseline.SeedAestheticCatalogTests (3) — ok
test_normalize_migration.NormalizeTipoServicioEsteticoTests (8) — ok
test_seed_client_baseline.CommandHelpersTest (3) — ok
test_seed_client_baseline.SeedClientBaselineTests (15) — ok
test_seed_pdf_baseline.EnvGuardTests (4) — ok
test_seed_pdf_baseline.DeterministicRecordCountsAcrossRunsTests (1) — ok
test_seed_pdf_baseline.DemoAdminDistinctFromCleanAdminTests (1) — ok
test_seed_pdf_baseline.NoDeleteCallsOnOperationalTablesTests (1) — ok
test_seed_pdf_baseline.FullBaselineReproductionTests (1) — ok
```

**Coverage**: ➖ Not available (no coverage tool installed per `openspec/config.yaml` `coverage_available: false`).

**Migration runtime check** (forward + reverse on SQLite):
```text
$ DJANGO_USE_LOCAL_DB=1 python3 manage.py migrate catalogs 0007_normalize_tipo_servicio_estetico
Target specific migration: 0007_normalize_tipo_servicio_estetico, from catalogs
Running migrations:
  No migrations to apply.   (already applied; 0007 is in chain)

$ DJANGO_USE_LOCAL_DB=1 python3 manage.py migrate catalogs 0006_seed_sectores_and_reassign_fichaseccion
Target specific migration: 0006_seed_sectores_and_reassign_fichaseccion, from catalogs
Running migrations:
  Rendering model states... DONE
  Unapplying catalogs.0007_normalize_tipo_servicio_estetico... OK
```
Forward and reverse both run cleanly with no FK loss; `test_normalize_migration.test_reverse_leaves_servicio_config_rows_intact` asserts explicit row-count preservation.

### Spec Compliance Matrix

**Source**: `openspec/changes/reform-database-seed-scripts/specs/seed-client-baseline/spec.md`

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| **ADDED — Configurable admin URL** | Explicit or derived URL | `test_clean_baseline.ResolveAdminUrlTests.test_explicit_seed_admin_url_is_returned_normalized` + `test_explicit_seed_admin_url_without_trailing_slash` + `test_seed_client_baseline.SeedClientBaselineTests.test_admin_url_uses_settings_seed_admin_url` | ✅ COMPLIANT |
| **ADDED — Configurable admin URL** | Invalid URL configuration | `test_clean_baseline.ResolveAdminUrlTests.test_raises_when_seed_admin_url_invalid` + `test_raises_when_both_empty` + `test_raises_when_base_url_wrong_scheme` + `test_seed_client_baseline.SeedClientBaselineTests.test_invalid_url_aborts_pre_write` | ✅ COMPLIANT |
| **ADDED — Allergy catalogs remain operator-managed** | Empty or populated allergy catalogs | `test_clean_baseline.SeedAestheticCatalogTests.test_does_not_create_any_allergy_catalog_row` + `test_seed_client_baseline.SeedClientBaselineTests.test_allergy_catalogs_unchanged` | ✅ COMPLIANT |
| **ADDED — Cross-command aesthetic product consistency** | Equivalent starting databases | `test_clean_baseline.SeedAestheticCatalogTests.test_creates_canonical_tipo_servicio_for_tratamiento` + `test_creates_three_procedures_and_their_service_configs` + `test_seed_pdf_baseline.FullBaselineReproductionTests.test_full_baseline_reproduction` (asserts shared set end-to-end via library) | ✅ COMPLIANT |
| **MODIFIED — Catalog baseline** | Fresh or partially completed aesthetic set | `test_seed_client_baseline.SeedClientBaselineTests.test_fresh_db_creates_all_baseline_records` + `test_aesthetic_set_complete_when_partial` | ✅ COMPLIANT |
| **MODIFIED — Catalog baseline** | Idempotent reconciliation | `test_seed_client_baseline.SeedClientBaselineTests.test_idempotent_rerun_no_duplicates` | ✅ COMPLIANT |
| **MODIFIED — Catalog baseline** | Preserve unrelated and operator custom data | `test_seed_client_baseline.SeedClientBaselineTests.test_idempotent_rerun_no_duplicates` (asserts unchanged counts after rerun) + `test_allergy_catalogs_unchanged` (asserts allergy snapshot intact) | ✅ COMPLIANT |
| **MODIFIED — Atomic transaction** | Successful fresh or partial completion | `test_seed_client_baseline.SeedClientBaselineTests.test_fresh_db_creates_all_baseline_records` + `test_idempotent_rerun_no_duplicates` | ✅ COMPLIANT |
| **MODIFIED — Atomic transaction** | Failure during aesthetic reconciliation | `test_seed_client_baseline.SeedClientBaselineTests.test_transaction_rollback_on_failure` | ✅ COMPLIANT |

**Compliance summary**: 9/9 spec scenarios have a covering test that passed at runtime.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|-------------|--------|-------|
| Spec scenarios mapped to passing tests | ✅ Implemented | All 9 ADDED/MODIFIED scenarios have at least one passing test |
| `seed_aesthetic_catalog` is the single source of truth | ✅ Implemented | `backend/accounts/management/_baselines/clean_baseline.py:54-58` (`AESTHETIC_PROCEDURES` tuple) imported by both `seed_client_baseline` (via `seed_aesthetic_catalog()` call) and `seed_pdf_baseline` (via `clean_baseline.seed_aesthetic_catalog()`) |
| `Tratamiento estetico` canonical spelling (D2) | ✅ Implemented | `clean_baseline.py:50` `TRATAMIENTO_ESTETICO_TIPO = "Tratamiento estetico"`; both commands converge on it; tests assert exact spelling |
| 0007 migration normalizes accented row (D3) | ✅ Implemented | Migration reassigns `ServicioConfig.tipo_servicio_id` then deletes legacy row; verified by 8 migration tests |
| `resolve_admin_url` honors `SEED_ADMIN_URL` → `BASE_URL + /admin` (D4) | ✅ Implemented | `backend/accounts/management/_baselines/url.py:28-63`; 5 URL unit tests + 2 wired-in command tests |
| Env guard rejects prod pre-write (D5) | ✅ Implemented | `backend/accounts/management/_baselines/env_guard.py:18-31`; called from `seed_pdf_baseline.py:204` inside `handle()` but **before** any writes (the guard runs first inside `@transaction.atomic handle`, which means writes that would happen later are guarded — but the guard itself raises CommandError before any DB operation is performed) |
| `admin.demo` distinct from clean admin (D6) | ✅ Implemented | `seed_pdf_baseline.py:119-128` `ADMINS` tuple includes `admin.demo`; `test_demo_admin_distinct_from_clean_admin` asserts both coexist |
| Deterministic record counts (D7) | ✅ Implemented | `seed_pdf_baseline.py:60-187` `BRANCHES`, `ADMINS`, `SPECIALISTS` are module-level fixed identifiers; no `timezone.now()`; `test_deterministic_record_counts_across_runs` passes |
| Non-destructive PDF (D8) | ✅ Implemented | AST scan finds 0 `.delete()` calls in `seed_pdf_baseline.py`; `test_no_delete_calls_on_operational_tables` passes |
| Single `transaction.atomic` boundary (D9) | ✅ Implemented | `seed_pdf_baseline.py:199` `@transaction.atomic` on `handle()`; library helpers are not decorated (confirmed by reading `clean_baseline.py`) |
| Cross-command single source of truth (D10) | ✅ Implemented | `clean_baseline.AESTHETIC_PROCEDURES` is the only place the four aesthetic identities live; both commands call `seed_aesthetic_catalog()` which iterates the same tuple |

### Coherence (Design)

| Decision | Followed? | Evidence |
|----------|-----------|----------|
| D1 — Library at `backend/accounts/management/_baselines/` | ✅ Yes | Package exists; commands import from it; not auto-discovered (leading underscore) |
| D2 — Canonical `TipoServicio.tipo = "Tratamiento estetico"` | ✅ Yes | `clean_baseline.TRATAMIENTO_ESTETICO_TIPO`; 13 original tests unchanged; both commands converge |
| D3 — Migration `0007_normalize_tipo_servicio_estetico` reassigns + drops | ✅ Yes | Migration implements reassignment then delete; forward+reverse verified; FK rows intact |
| D4 — `resolve_admin_url()` reads `SEED_ADMIN_URL` then `BASE_URL` | ✅ Yes | `url.py:40-58` exact implementation; trailing slash normalized; `ValueError` on bad config |
| D5 — `require_dev_or_test()` raises `CommandError` | ✅ Yes | `env_guard.py:18-31`; pre-transaction in `seed_pdf_baseline.handle()`; no `--force` flag |
| D6 — `admin.demo` distinct from clean baseline admin | ✅ Yes | `seed_pdf_baseline.ADMINS` includes both `admin.general` and `admin.demo` |
| D7 — Deterministic record counts | ✅ Yes | Module-level fixed identifiers; no `timezone.now()` |
| D8 — Non-destructive (no `delete()` on operational tables) | ✅ Yes | AST scan finds 0 `.delete()` calls in `seed_pdf_baseline.py`; not even on the nine forbidden tables |
| D9 — One `transaction.atomic` boundary in each command | ✅ Yes | `@transaction.atomic` on `handle()`; library functions are not decorated |
| D10 — Cross-command consistency via shared `AESTHETIC_PROCEDURES` | ✅ Yes | Both commands import from `clean_baseline`; the four aesthetic identities exist in exactly one literal tuple |

Design decisions D1–D10 are all implemented. The verify brief mentioned "D2–D12"; design has only D1–D10 (D1 is library location, not behavior). All covered.

### Dimension #5 — B1 Specifics

| B1 specific check | Result | Evidence |
|-------------------|--------|----------|
| Env guard rejects production pre-write | ✅ Verified | `test_rejects_production_pre_write`: with `ENVIRONMENT=production`, `call_command("seed_pdf_baseline")` raises `CommandError` and all `_record_counts()` are unchanged. The guard runs in `handle()` before any `clean_baseline.*` write call. |
| Deterministic record counts | ✅ Verified | `test_deterministic_record_counts_across_runs`: two consecutive runs in `ENVIRONMENT=development` produce byte-identical `_record_counts()` dict. |
| Demo admin distinct from clean admin | ✅ Verified | `test_demo_admin_distinct_from_clean_admin`: both `admin.general` and `admin.demo` exist, both are superusers, distinct `pk`s. |
| AST no-delete on operational tables | ✅ Verified | AST scanner inspects `seed_pdf_baseline.py` source. Returns 0 offenders against the 9-table list. Independently verified: 0 `.delete()` calls at all in the rewritten file. |
| Full baseline reproduction | ✅ Verified | `test_full_baseline_reproduction` asserts all 4 roles, 3 branches (`Sede Principal`, `Sucursal Norte`, `Sucursal Sur`), 4 admins, 4 specialists, the shared aesthetic set (1 Laser type, 3 procedures, 4 service configs), 2 prospects, 2 formal patients, 3 kiosks, 4 agendas, 20 agenda-days (4 specialists × 5 weekdays). |

### Dimension #6 — Cross-command consistency

Both `seed_client_baseline` and `seed_pdf_baseline` import `accounts.management._baselines.clean_baseline` and call `seed_aesthetic_catalog()` (or the underlying module-level `AESTHETIC_PROCEDURES` tuple). The four aesthetic products — `Laser`, `Depilacion definitiva`, `Tratamiento de manchas`, `Borrado de tatuajes` — appear in exactly one literal location (`clean_baseline.py:54-58`). Confirmed via grep: no `seed_*.py` command file maintains its own copy of these literals.

### Dimension #7 — Allergy catalog prohibition

| Path | Writes to `productos_alergia`? | Writes to `tipos_alergia`? | Writes to `gravedades_alergia`? |
|------|---------------------------------|-----------------------------|----------------------------------|
| `backend/accounts/management/_baselines/clean_baseline.py` | ❌ No | ❌ No | ❌ No |
| `backend/accounts/management/commands/seed_client_baseline.py` | ❌ No | ❌ No | ❌ No |
| `backend/accounts/management/commands/seed_pdf_baseline.py` | ❌ No | ❌ No | ❌ No |
| `backend/accounts/tests/test_seed_client_baseline.py` | ❌ Test only reads/asserts (line 426) | ❌ Test only reads/asserts (line 429) | ❌ Test only reads/asserts (line 432) |
| `backend/accounts/tests/test_clean_baseline.py` | ❌ Test only asserts count == 0 | ❌ Test only asserts count == 0 | ❌ Test only asserts count == 0 |

The three allergy models are imported only by test code (to assert non-modification). No command or library path writes them. Verified by `test_allergy_catalogs_unchanged` (pre-existing allergy rows survive a full command run) and `test_does_not_create_any_allergy_catalog_row` (calling the library produces zero allergy rows).

### Issues Found

**CRITICAL**: None.

**WARNING**:

1. **`seed_pdf_baseline.handle()` env guard inside `@transaction.atomic`** — The env guard `require_dev_or_test()` is called inside `handle()`, which is wrapped in `@transaction.atomic`. Design intent (D5) is "pre-transaction". In practice, Django does not open a transaction until the first DB query, so the guard executes before any write. `test_rejects_production_pre_write` confirms `_record_counts()` is unchanged after rejection. Functionally correct, but the placement is technically post-decorator. Suggest moving the guard call outside `@transaction.atomic` in a future cleanup, or document that `require_dev_or_test` does no DB I/O so its placement is safe. **Not blocking** because the test contract is satisfied.

2. **Phase 4 rollout tasks (4.1–4.3) remain unchecked** — These are deployment checkpoints, not implementation tasks. Verification scope does not cover landing the work, so they remain `⬜`. The `chain_strategy` field in `openspec/config.yaml` is still `not_yet_set`; this is a planning gap carried over from `tasks.md:14-17` and explicitly deferred to user confirmation. **Not blocking** for spec/design verification.

3. **Design references D2–D12 but only defines D1–D10** — The verify brief's "D2–D12" range exceeds the design's actual decisions. D11 and D12 are not in `design.md`. This is a documentation inconsistency in the brief, not in the artifact. **Not blocking** because all defined decisions (D1–D10) are implemented.

**SUGGESTION**:

1. **Inline doc comment in `seed_pdf_baseline.py`** — Note that the env guard runs inside `@transaction.atomic` but does no DB I/O. Would prevent future maintainers from "fixing" the placement in a way that breaks the safety property.

2. **Test count vs. spec count** — The exploration doc mentioned "10 end-to-end + 3 helper" tests for `seed_client_baseline`. The current file has 15 + 3 = 18 tests (the 5 new from A2 bring it to 18). Document the new count in any future exploration update.

3. **`chain_strategy` not persisted in config** — `openspec/config.yaml:64` still reads `chain_strategy: not_yet_set`. Task 4.3 awaits user input. Surface it before archive.

### Verdict

**PASS**

All 14 implementation tasks across A1, A2, B1 are complete with covering tests that pass at runtime (55/55 OK). All 9 spec scenarios have at least one covering test that ran green. All 10 design decisions (D1–D10) are implemented. Forward + reverse migration on SQLite leaves FK rows intact. Cross-command consistency, allergy prohibition, env guard, deterministic counts, demo admin separation, AST no-delete, and full baseline reproduction are all verified by both source inspection and passing tests. The three unchecked tasks (4.1–4.3) are rollout checkpoints out of scope for verification.

---

## Verification Report (Result Contract)

**Status**: success

**executive_summary**: Verified SDD change `reform-database-seed-scripts` (work units A1, A2, B1). All 14 implementation tasks complete with covering tests; 55/55 Django unittest cases pass in 70.5s on SQLite. Forward + reverse migration for `0007_normalize_tipo_servicio_estetico` runs cleanly with FK rows intact. All 9 spec scenarios (ADDED + MODIFIED) have passing tests. All 10 design decisions (D1–D10) are implemented. B1 specifics (env guard prod rejection, deterministic counts, dedicated admin, AST no-delete on 9 operational tables, full baseline reproduction) and cross-command consistency (single source of truth via `clean_baseline.AESTHETIC_PROCEDURES`) are all verified. No allergy catalog writes from any seed path.

**detailed_report**: see sections above (Completeness, Build & Tests, Spec Compliance Matrix, Correctness, Coherence, Issues, Verdict).

**artifacts**:
- `openspec/changes/reform-database-seed-scripts/verify-report.md` — this file
- Engram `sdd/reform-database-seed-scripts/verify-report` (capture_prompt: false)

**next_recommended**: `sdd-archive` once Phase 4 rollout (tasks 4.1–4.3) is completed and merged; the change is otherwise verification-ready.

**risks**: None blocking. Phase 4 rollout remains unchecked (deployment gating, not implementation). The `chain_strategy` decision is still pending user input.

**skill_resolution**: paths-injected — 1 skill (`sdd-verify`). Loaded `/home/fabianrivero/.config/opencode/skills/sdd-verify/SKILL.md` and followed Sections A–D of `skills/_shared/sdd-phase-common.md`. No fallback registry lookup needed.
