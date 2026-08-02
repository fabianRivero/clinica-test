# Proposal: reset-pdf-baseline

## Intent

Operators today run two separate steps to land a fresh PDF demo state: `purge_data_keep_admin --force` then `seed_pdf_baseline`. They run in two transactions, so a mid-seed failure leaves the DB purged with no rollback. This change adds a single destructive orchestrator command, **`reset_pdf_baseline`**, that performs the wipe-then-seed waveform inside one `transaction.atomic` boundary behind the existing `require_dev_or_test()` env guard. Idempotent: reruns converge to the same demo state.

## Scope

**In Scope**: new `reset_pdf_baseline` command with `@transaction.atomic handle`; pre-write `require_dev_or_test()` guard; outer atomic wraps `call_command("purge_data_keep_admin", "--force", stdout=self.stdout)` then `call_command("seed_pdf_baseline", stdout=self.stdout)`; destructive-wipe stdout header; tests (env guard, no-op on empty DB, rollback, idempotent rerun); OpenSpec delta spec for new `seed-orchestrators` capability.

**Out of Scope**: modifying `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, `env_guard.py` (siblings stay byte-stable); new dependencies; audit trails; dry-run flags; production support.

## Capabilities

**New**: `seed-orchestrators` — orchestrator commands composing baseline steps inside one `transaction.atomic` boundary behind `require_dev_or_test()`. Houses the `reset_pdf_baseline` contract.

**Modified**: None.

## Approach

Thin `BaseCommand` with `@transaction.atomic handle`: (1) `require_dev_or_test()` pre-write guard; (2) print destructive-wipe `WARNING` header; (3) `call_command("purge_data_keep_admin", "--force", stdout=self.stdout)`; (4) `call_command("seed_pdf_baseline", stdout=self.stdout)`. Outer atomic composes inner blocks as savepoints; mid-seed failure rolls back the purge. `call_command(..., stdout=self.stdout)` forwards inner output. No CLI flags; one-shot.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/accounts/management/commands/reset_pdf_baseline.py` | New | Orchestrator command. |
| `backend/accounts/tests/test_reset_pdf_baseline.py` | New | Env guard, idempotent, no-op-on-empty, rollback tests. |
| `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, `env_guard.py` | Unchanged | Siblings and shared helpers. |
| `openspec/specs/seed-orchestrators/spec.md` | New | Source-of-truth spec. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Nested atomic breaks all-or-nothing. | Low | Savepoint semantics; rollback test verifies. |
| Inner env guard fires twice. | Low | Identical `CommandError`; idempotent. |
| `call_command` swallows stdout. | Medium | Pass `stdout=self.stdout`; print header first. |
| Test harness masks atomic rollback. | Medium | `TransactionTestCase` for rollback test. |
| Accidental run on production DB. | Low | `require_dev_or_test()` rejects unconditionally. |

## Rollback Plan

(1) Stop using `reset_pdf_baseline`; revert to manual two-step ritual — both commands stay byte-stable. (2) Outer atomic ensures no partial state on failure. (3) Delete `reset_pdf_baseline.py` + `test_reset_pdf_baseline.py`; no migrations to revert. (4) Pre-implementation: delete `openspec/changes/reset-pdf-baseline/`.

## Dependencies

`django.core.management.call_command`, `django.db.transaction` (stdlib); `accounts.management._baselines.env_guard.require_dev_or_test` (existing); existing `seed_pdf_baseline` and `purge_data_keep_admin` commands. No new third-party deps.

## Success Criteria

- [ ] `reset_pdf_baseline` runs end-to-end on dev DB with demo data.
- [ ] Rejects `ENVIRONMENT=production|staging|<empty>` with `CommandError` pre-write.
- [ ] Runs cleanly on empty DB; final state equals fresh `seed_pdf_baseline`.
- [ ] Two consecutive runs produce byte-stable record counts.
- [ ] Mid-seed failure rolls back the purge; DB returns to pre-purge state.
- [ ] Stdout shows destructive-wipe header, then purge and seed summaries.
- [ ] New tests pass; no existing test in `test_seed_pdf_baseline.py` or `test_seed_client_baseline.py` modified.
- [ ] `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py` source byte-stable (no diff).

## Review Workload Forecast

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low
Estimated changed lines: ~240 (90 command + 150 tests).
