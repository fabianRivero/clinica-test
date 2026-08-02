# Verify Report: reset-pdf-baseline

## Summary

| Field | Value |
|-------|-------|
| Change | `reset-pdf-baseline` |
| Mode | Standard (Strict TDD = false) |
| Date | 2026-08-01 |
| Verdict | **PASS** |

## Completeness

| Artifact | Status |
|----------|--------|
| `proposal.md` | done (507 words) |
| `specs/seed-orchestrators/spec.md` | done (688 words, 7 requirements, 13 scenarios) |
| `design.md` | done (638 words) |
| `tasks.md` | done (16/16 tasks marked `[x]`) |
| `exploration.md` | done (supplementary) |

## Test Evidence

```
$ python3 manage.py test accounts.tests.test_reset_pdf_baseline
................
Ran 16 tests in 54.420s
OK

$ python3 manage.py test accounts.tests.test_seed_pdf_baseline
........
Ran 8 tests in 36.919s
OK

$ git diff --name-only HEAD -- backend/accounts/management/commands/seed_pdf_baseline.py \
    backend/accounts/management/commands/seed_client_baseline.py \
    backend/accounts/management/commands/purge_data_keep_admin.py \
    backend/accounts/management/_baselines/env_guard.py
(empty)
```

| Test class | Tests | Status |
|------------|-------|--------|
| `EnvGuardTests` | 5 (production, staging, empty, dev, test) | PASS |
| `DestructiveHeaderTests` | 2 (precedes inner output; uses WARNING style) | PASS |
| `AtomicStructureTests` | 4 (`@transaction.atomic` decorator; call_command order; `stdout` kwarg; guard first statement) | PASS |
| `AtomicRollbackTests` (TransactionTestCase) | 1 (mid-flight seed failure rolls back purge) | PASS |
| `IdempotentRunsTests` | 1 (two consecutive runs = byte-stable counts) | PASS |
| `EmptyDatabaseTests` | 1 (empty DB + run = manual purge + seed) | PASS |
| `SiblingNonModificationTests` | 2 (no uncommitted changes; files exist with content) | PASS |
| **Total new** | **16** | **PASS** |
| Sibling `test_seed_pdf_baseline` | 8 (unmodified) | PASS |

## Spec Compliance Matrix

| Requirement | Scenarios | Test Coverage | Verdict |
|-------------|-----------|---------------|---------|
| Orchestrator Command Identifier | 1 | `AtomicStructureTests.test_handle_invokes_*` (AST confirms import path) | COMPLIANT |
| Pre-Write Environment Guard | 5 | `EnvGuardTests` (5/5) | COMPLIANT |
| Destructive Wipe Notification | 1 | `DestructiveHeaderTests` (2/2) | COMPLIANT |
| Single Transaction Boundary | 2 | `AtomicStructureTests` (decorator + call_command order + stdout kwarg) + `AtomicRollbackTests` | COMPLIANT |
| Idempotent Destructive-Then-Seed Waveform | 1 | `IdempotentRunsTests` | COMPLIANT |
| No-Op Safety on Empty Database | 1 | `EmptyDatabaseTests` | COMPLIANT |
| Sibling Command Non-Modification | 1 | `SiblingNonModificationTests` + `git diff` evidence above | COMPLIANT |

13 of 13 spec scenarios covered by passing tests.

## Correctness

| File | Lines | Status |
|------|-------|--------|
| `backend/accounts/management/commands/reset_pdf_baseline.py` | 88 | Created, matches design code skeleton |
| `backend/accounts/tests/test_reset_pdf_baseline.py` | 462 | Created, all 16 tests pass |
| `docs/vps-setup-from-scratch.md` | +1 row | Baseline commands table updated |

## Design Coherence

| Decision | Implementation matches? |
|----------|--------------------------|
| Compose via `call_command`, not import-and-call | Yes — `call_command` is imported and used for both inner commands |
| Pass `--force` to `purge_data_keep_admin` | Yes — `--force` literal present in the call |
| Use `@transaction.atomic` decorator | Yes — `handle` is decorated; AST test confirms |
| Forward stdout via `stdout=self.stdout` | Yes — both inner calls pass it; AST test confirms kwarg |
| Use `TransactionTestCase` for rollback test | Yes — `AtomicRollbackTests(TransactionTestCase)` |

All design decisions honored.

## Issues

### CRITICAL
None.

### WARNING
None.

### SUGGESTION
- The `WARNING` header text could include a count of admin users that will be preserved (small UX improvement, deferred — not in spec).
- A `--dry-run` flag would be a useful follow-up (deferred — out of scope).

## Final Verdict

**PASS** — implementation matches specs, design, and tasks. All 16 new tests pass; all 8 sibling tests pass unmodified; sibling source files are byte-stable.
