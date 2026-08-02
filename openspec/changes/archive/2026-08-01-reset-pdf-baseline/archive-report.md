# Archive Report: reset-pdf-baseline

## Summary

| Field | Value |
|-------|-------|
| Change | `reset-pdf-baseline` |
| Archived to | `openspec/changes/archive/2026-08-01-reset-pdf-baseline/` |
| Date | 2026-08-01 |
| Verdict | **PASS** (verified before archive) |

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `seed-orchestrators` | Created | 7 ADDED requirements, 13 scenarios. Source-of-truth spec lives at `openspec/specs/seed-orchestrators/spec.md`. |

The delta was pure ADDED (no existing spec to modify); the delta spec was copied verbatim into `openspec/specs/seed-orchestrators/spec.md`.

## Archive Contents

- `proposal.md` ✅
- `exploration.md` ✅
- `design.md` ✅
- `specs/seed-orchestrators/spec.md` ✅
- `tasks.md` ✅ (16/16 tasks complete)
- `verify-report.md` ✅ (verdict PASS)

## Source of Truth Updated

The following spec now reflects the new behavior:

- `openspec/specs/seed-orchestrators/spec.md` — new capability with 7 requirements documenting the `reset_pdf_baseline` contract.

## Code Artifacts Preserved

- `backend/accounts/management/commands/reset_pdf_baseline.py` — NEW (88 lines)
- `backend/accounts/tests/test_reset_pdf_baseline.py` — NEW (462 lines, 16 tests)
- `docs/vps-setup-from-scratch.md` — updated with one row in baseline commands table
- Sibling files (`seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, `env_guard.py`) — BYTE-STABLE (no diff)

## Test Status at Archive

- 16/16 new tests in `accounts.tests.test_reset_pdf_baseline` PASS
- 8/8 sibling tests in `accounts.tests.test_seed_pdf_baseline` PASS

## Engram Observation IDs

| Artifact | ID |
|----------|-----|
| explore | 447 |
| proposal | 448 |
| spec | 449 |
| design | 450 |
| tasks | 451 |
| apply-progress | 452 |
| verify-report | 453 |

## SDD Cycle Complete

The change has been fully planned, implemented, verified, and archived. The `reset_pdf_baseline` orchestrator command is now part of the project. The new `seed-orchestrators` capability is the source-of-truth spec for future orchestrator commands.

Ready for the next change.
