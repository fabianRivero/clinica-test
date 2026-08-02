# Tasks: reset-pdf-baseline

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250 (88 command + 462 tests) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

## Phase 1: Foundation

- [x] 1.1 Create `backend/accounts/management/commands/reset_pdf_baseline.py` with `Command(BaseCommand)` and `@transaction.atomic handle`.
- [x] 1.2 Add imports: `call_command`, `BaseCommand`, `transaction`, `require_dev_or_test`.

## Phase 2: Core Implementation

- [x] 2.1 Call `require_dev_or_test()` as the first statement of `handle`.
- [x] 2.2 Emit `WARNING`-styled header containing the literal `DESTRUCTIVE WIPE` to `self.stdout`.
- [x] 2.3 Invoke `call_command("purge_data_keep_admin", "--force", stdout=self.stdout)`.
- [x] 2.4 Invoke `call_command("seed_pdf_baseline", stdout=self.stdout)`.
- [x] 2.5 Emit a final `SUCCESS`-styled `Reset PDF baseline complete.` line.

## Phase 3: Tests — Env Guard and Stdout

- [x] 3.1 Create `backend/accounts/tests/test_reset_pdf_baseline.py` with imports + `_record_counts()` helper.
- [x] 3.2 Add `EnvGuardTests` covering `production`, `staging`, empty, `development`, `test` (5 scenarios).
- [x] 3.3 Add `DestructiveHeaderTests` asserting the `WARNING` `DESTRUCTIVE WIPE` line precedes inner output.

## Phase 4: Tests — Atomic and AST Guards

- [x] 4.1 Add `AtomicStructureTests` parsing source via `ast`: `@transaction.atomic` on `handle`; both `call_command` calls inside.
- [x] 4.2 Add `AtomicRollbackTests(TransactionTestCase)` that mocks `call_command("seed_pdf_baseline")` to raise and asserts pre-call rows survive.

## Phase 5: Tests — Idempotence, No-Op, and Sibling Non-Modification

- [x] 5.1 Add `IdempotentRunsTests`: two consecutive runs produce byte-stable `_record_counts()` snapshots.
- [x] 5.2 Add `EmptyDatabaseTests`: empty DB + run equals a fresh `seed_pdf_baseline` run.
- [x] 5.3 Add `SiblingNonModificationTests`: `git diff` shows no changes to the four sibling files.

## Phase 6: Verification

- [x] 6.1 Run `python manage.py test backend.accounts.tests.test_reset_pdf_baseline`; all green.
- [x] 6.2 Run `python manage.py test backend.accounts.tests.test_seed_pdf_baseline`; all green (sibling untouched).
- [x] 6.3 Run `git diff HEAD -- backend/accounts/management/commands/seed_pdf_baseline.py seed_client_baseline.py purge_data_keep_admin.py _baselines/env_guard.py`; output empty.

## Phase 7: Cleanup

- [x] 7.1 Add a row to the baseline commands table in `docs/vps-setup-from-scratch.md` (around L269) describing `reset_pdf_baseline` as a destructive orchestrator.
- [x] 7.2 Write the verify report at `openspec/changes/reset-pdf-baseline/verify-report.md`.
