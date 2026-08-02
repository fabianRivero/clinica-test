# Proposal: Reform Database Seed Scripts

## Intent

`seed_client_baseline` hard-codes `https://reactproject.site/admin`; its current aesthetic service set is also created by `seed_pdf_baseline`, but the commands disagree on the exact `TipoServicio` identity (`Tratamiento estetico` versus `Tratamiento estético`). `seed_pdf_baseline` mixes bootstrap and demo writes, deletes operational rows, has no environment guard, and is misaligned with current models. This change locks the clean baseline, fixes URL output, makes both commands converge on the evidence-backed aesthetic procedures, and rebuilds the demo command with explicit environment and admin separation. Allergy catalogs remain unseeded.

## Scope

### In Scope
- Lock `seed_client_baseline` with one `MODIFIED` delta (URL-derived and exact aesthetic-product outcomes); zero `REMOVED`.
- Require both commands to create the current `Laser` procedure type; `Depilacion definitiva`, `Tratamiento de manchas`, and `Borrado de tatuajes`; and their treatment-service links with the current descriptions, order, active state, and prices.
- Explicitly keep `ProductoAlergia`, `TipoAlergia`, and `GravedadAlergia` unseeded by both commands.
- Replace hard-coded admin URL footer with a value derived from project configuration (settings flag with env override); never a hard-coded domain.
- Rebuild `seed_pdf_baseline` on current models: deterministic PDF/demo scenarios, dedicated demo administrator, non-destructive, full clean baseline first then demo layer.
- Enforce environment guard on `seed_pdf_baseline`: allowed only when `ENVIRONMENT ∈ {development, test}`; reject all others with `CommandError` pre-write — no confirmation prompt can override.

### Out of Scope
`seed_production_baseline`, `seed_branch_test_scenarios`, `ensure_main_branch`, `purge_data_keep_admin`, fixtures, wrappers. `ServicioConfig.sector` reconciliation. Docs beyond a short note in `docs/vps-setup-from-scratch.md` 5.2.

## Capabilities

### Modified
- `seed-client-baseline`: derive admin URL from config; guarantee the evidence-backed three aesthetic procedures and service links; prohibit allergy catalog seeding; preserve prompts, validation, atomic transaction, idempotency, and non-destructive semantics.

### New
- `seed-pdf-baseline`: rebuilt deterministic demo command with environment guard, dedicated demo admin, full clean-baseline reproduction, non-destructive seeding.

## Approach

The design may extract `backend/accounts/management/commands/_seed_baseline/` for roles, branches, admins, kiosks, catalogs, and sectors, but the specification requires only equivalent observable outcomes. `seed_client_baseline` keeps its public surface, validation, prompts, and transaction boundary while guaranteeing the current aesthetic set. `seed_pdf_baseline` is rewritten around its demo baseline, form configuration, prospects, patients, schedules, and a pre-transaction environment guard. URL output reads `settings.SEED_ADMIN_URL` (defaulting to `BASE_URL + "/admin"`) with env override. Neither command writes allergy catalogs.

## Affected Areas

- `backend/accounts/management/commands/seed_client_baseline.py` — Modified: preserve its CLI/transaction contract; replace hard-coded URL; guarantee aesthetic outcomes.
- `backend/accounts/management/commands/seed_pdf_baseline.py` — Rewritten: current-model alignment, env guard, dedicated demo admin, non-destructive.
- Optional internal baseline helper module — New only if selected during design; not part of the observable specification contract.
- `backend/accounts/tests/test_seed_client_baseline.py` — Modified: preserve 13 tests; add URL, exact aesthetic-set, partial-completion, preservation, allergy-exclusion, and rollback scenarios.
- `backend/accounts/tests/test_seed_pdf_baseline.py` — New: env-guard, deterministic scenarios, dedicated admin, non-destructive.
- `docs/vps-setup-from-scratch.md` 5.2 — Modified: short note on URL config + PDF env guard.

## Risks

- **Refactor changes a natural key** (Med): keep `update_or_create` lookups byte-stable; 13 existing tests are the safety floor.
- **Operator runs `seed_pdf_baseline` in production** (High): hard `CommandError` pre-transaction when env ∉ {development, test}; no confirmation override; logged rejection.
- **Aesthetic service identities drift** (Med): preserve the exact procedure type, procedure, service-link, description, order, active-state, and price evidence; resolve the accented/unaccented treatment-service identity during design without creating a duplicate.
- **URL change breaks operator muscle memory** (Low): document `SEED_ADMIN_URL`; fallback prints `BASE_URL/admin`.
- **PDF recreation exceeds 400-line budget** (Med): split into chained PRs (A) shared library + clean-baseline refactor; (B) PDF rewrite + new tests.

## Rollback Plan

**Clean baseline**: revert the commit that changes URL output and aesthetic reconciliation; the pre-change command remains in git and existing tests are the safety floor; no data migration is required. **PDF baseline**: retain a git-recoverable legacy implementation until replacement tests pass; on rollback, restore that implementation. The environment guard makes accidental production calls fail before writes. If URL derivation misbehaves, set `SEED_ADMIN_URL` to the previous URL through configuration.

## Dependencies

- `backend/{accounts,catalogs,billing,operations,clinical}/models.py` — current contracts.
- Migrations `catalogs/0006_seed_sectores_and_reassign_fichaseccion.py` and `operations/0008_data_migrate_sucursales.py` — pre-seed `Sector` and `Sede Principal`; idempotency depends on these staying unchanged.
- Django settings access for `SEED_ADMIN_URL` / `ENVIRONMENT`; no new third-party dependency.

## Success Criteria

- `python manage.py test accounts.tests.test_seed_client_baseline` passes unchanged (13/13).
- `seed_client_baseline` summary footer URL derives from settings/env, never a hard-coded domain.
- `seed_client_baseline` creates the `Laser` procedure type, the exact three procedures, and their treatment-service links idempotently while preserving unrelated/operator custom data.
- Neither command creates or updates `ProductoAlergia`, `TipoAlergia`, or `GravedadAlergia` records.
- `seed_pdf_baseline` in `ENVIRONMENT=production` exits with `CommandError` pre-write; no confirmation prompt.
- `seed_pdf_baseline` creates a dedicated demo administrator distinct from the clean-baseline admin, reproduces the full clean baseline, then seeds deterministic PDF scenarios, and never calls `delete()` on operational tables.
- Both commands yield the same evidence-backed aesthetic procedure and service-link set; no shared internal library is required by the behavioral contract.
- `test_seed_pdf_baseline.py` covers env-guard rejection (prod), env-guard pass (dev/test), deterministic record counts across two runs, dedicated admin distinct from clean baseline, and no `delete()` on the nine operational tables.
- Work Unit A (clean-baseline refactor) under 200 changed lines; Work Unit B (PDF rewrite) under 400; chained PRs if needed.