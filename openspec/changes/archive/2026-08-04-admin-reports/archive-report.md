# Archive Report — `admin-reports`

## Summary

| Field | Value |
|-------|-------|
| Change | `admin-reports` |
| Archived on | 2026-08-04 |
| Archived to | `openspec/changes/archive/2026-08-04-admin-reports/` |
| Source of truth updated | `openspec/specs/admin-reports/spec.md` (new domain created) |
| Artifact store | `openspec` |
| Project | `clinica-test` |
| Status | **archived** |

## Spec Sync

The `admin-reports` domain did not exist in `openspec/specs/` before this change.
The delta spec at `openspec/changes/admin-reports/specs/admin-reports/spec.md`
was therefore treated as a full spec (per the OpenSpec convention for new
domains) and **copied verbatim** to
`openspec/specs/admin-reports/spec.md`. The source file inside the change
folder was not modified.

| Domain | Action | Details |
|--------|--------|---------|
| `admin-reports` | Created (full spec copy) | 6 requirements, 9 scenarios, all preserved |

The copied file is byte-identical to the source delta spec (verified with
`diff` — no output).

## Cycle Completion

| Phase | Artifact | Status |
|-------|----------|--------|
| Explore | `openspec/changes/admin-reports/exploration.md` | present |
| Propose | `openspec/changes/admin-reports/proposal.md` | present |
| Spec | `openspec/changes/admin-reports/specs/admin-reports/spec.md` | present |
| Design | `openspec/changes/admin-reports/design.md` | present |
| Tasks | `openspec/changes/admin-reports/tasks.md` | 20 / 20 checked |
| Verify | `openspec/changes/admin-reports/verify-report.md` | PASS WITH WARNINGS — no CRITICAL issues |

### Task Completion Gate

`grep -c '^- \[x\]' tasks.md` → **20** checked.
`grep -c '^- \[ \]' tasks.md` → **0** unchecked.

All 20 implementation tasks across Phase 1 (4), Phase 2 (4), Phase 3 (6),
Phase 4 (4), and Phase 5 (2) are checked `[x]`. The verify report's
"21 tasks total" claim was an arithmetic error in the report itself
(4 + 4 + 6 + 4 + 2 = 20), but the underlying completion state is
correct: zero unchecked tasks. The gate **passes**.

### CRITICAL Gate

The verify report explicitly states `**CRITICAL**: None.` and verdict
`PASS WITH WARNINGS`. No CRITICAL issues block the archive.

### Known Warnings Carried Forward

The following WARNING-class items from the verify report are NOT
remediated by this archive and remain as known follow-ups. They are
documented here for traceability.

1. **E2E strict-mode locator failure** — `tests/e2e/admin_reports.spec.ts:223`
   matches two headings (`<h1>` from `PageHeader` + `<h2>` from
   `SectionCard`) for `/cms/reportes/clientes`. 5 of 6 Playwright tests
   pass; the failing test exercises the duplicate-title contract, not a
   missing feature. Recommended fix: tighten the locator to `.first()` /
   `exact: true`, or drop the redundant `<SectionCard title>` for
   non-period reports.
2. **Three unused type imports** in
   `frontend/aesthetic-clinic/src/services/api/admin.ts:37, 39, 41`
   (`ReportClientResponse`, `ReportIncomeResponse`, `ReportProspectResponse`).
   Lint `no-unused-vars` errors. Mechanical cleanup.
3. **No direct E2E coverage for the "API failure" spec scenario**. Source
   (`ReportLayout.tsx:199-203`) handles `error && !data` correctly; no
   Playwright test forces a 500/403 to assert the `<DataState tone="danger">`.
   WARNING-class spec-coverage gap.
4. **One new lint warning** —
   `pages/admin/reports/ReportLayout.tsx:100` `useCallback` with
   unnecessary deps (`branchId`, `month`, `year`). Functional but noisy.

None of these block the archive per the strict-vs-OpenSpec policy in
`sdd-archive` SKILL.md.

## Archive Move

The entire change folder was moved with `git mv`:

```
openspec/changes/admin-reports/
  → openspec/changes/archive/2026-08-04-admin-reports/
```

Archived contents (all six original files preserved):

- `proposal.md` — intent, scope, capabilities, risks, success criteria
- `exploration.md` — pre-change exploration notes
- `design.md` — design decisions D1–D5
- `specs/admin-reports/spec.md` — the original delta (now also in
  `openspec/specs/admin-reports/spec.md`)
- `tasks.md` — final task state at archive time (all 20 checked)
- `verify-report.md` — verification report with PASS WITH WARNINGS verdict
- `archive-report.md` — this file

## Source of Truth After Archive

| Spec | Path |
|------|------|
| Admin reports (canonical) | `openspec/specs/admin-reports/spec.md` |

The change folder is gone from `openspec/changes/` and the archive folder
contains the complete audit trail.

## Engram Persistence

This archive report is persisted to Engram with:

- topic_key: `sdd/admin-reports/archive-report`
- project: `clinica-test`
- type: `architecture`
- capture_prompt: `false`

## SDD Cycle Status

**COMPLETE.** The `admin-reports` change has been fully explored,
proposed, specified, designed, implemented (Phases 1–5 including
cleanup), verified, and archived. The Reports navigation group with
client, prospect, income, and expense tables is now part of the
production source of truth at `openspec/specs/admin-reports/spec.md`.
Ready for the next change.