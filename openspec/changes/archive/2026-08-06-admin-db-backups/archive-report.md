# Archive Report — `admin-db-backups`

## Summary

| Field | Value |
|-------|-------|
| Change | `admin-db-backups` |
| Branch | `feat/admin-db-backups-core` |
| Archived on | 2026-08-06 |
| Archived to | `openspec/changes/archive/2026-08-06-admin-db-backups/` |
| Source of truth updated | `openspec/specs/admin-db-backups/spec.md` (new domain created) |
| Artifact store | `openspec` |
| Project | `clinica-test` |
| Verification verdict | **PASS WITH WARNINGS** |
| Status | **archived** |

## Commits

16 commits across 5 PRs (PR1 + PR2 + PR3 + PR4 + PR-fix) on a single
stacked branch (off `main`):

| SHA | Title | PR |
|------|-------|----|
| `0a3c783` | `feat(backups): scaffold backups app with BackupAuditLog model and migration` | PR1 |
| `6846143` | `feat(backups): add backup service with engine branching, retention, lock and audit` | PR1 |
| `186456d` | `feat(backups): add create_backup management command and tests` | PR1 |
| `d11305a` | `feat(backups): tighten service, command and tests for PR1 review` | PR1 |
| `1430a39` | `feat(backups): add admin principal authz and rate limit decorators` | PR2 |
| `9d8edaa` | `feat(backups): expose trigger and list backup endpoints` | PR2 |
| `ff76596` | `feat(backups): expose download and delete backup endpoints` | PR2 |
| `834573a` | `feat(backups): add backup types, API client and useBackups hook` | PR3 |
| `a44a3ff` | `feat(backups): add admin backups page and components` | PR3 |
| `9daa469` | `feat(backups): register admin backups nav entry and route` | PR3 |
| `daf2536` | `test(backups): add admin backups e2e spec` | PR3 |
| `fd57f6b` | `docs(backups): add operator helper script and env example` | PR4 |
| `2822e0b` | `docs(backups): add operator runbook` | PR4 |
| `4293b1f` | `fix(backups): align env vars with .env.example and make rate limits configurable` | PR-fix |
| `b387091` | `feat(backups): add age label to list response and table` | PR-fix |
| `2b182ed` | `fix(backups): audit download rate limit denial and rename trigger button` | PR-fix |

All commits use Conventional Commit format. No `Co-Authored-By:` trailer.

## Diff Stats

`git diff --stat main...HEAD` totals:

```
33 files changed, 3299 insertions(+), 1 deletion(-)
```

Backend: 1960 insertions (model, services, decorators, views, urls, command, 5 test files, settings, api_urls, env example).
Frontend: 980 insertions (page, table, modal, hook, types, API client, apiClient helpers, App route, AdminLayout nav, Playwright spec).
Docs + scripts: 201 insertions (`docs/backups.md`, `scripts/backups.sh.example`).

## Test Results

| Suite | Result |
|-------|--------|
| `python3 manage.py test backups` | **42/42 PASS** (9.7s) |
| `npm run build` (frontend/aesthetic-clinic) | **PASS** (940 kB JS / 58 kB CSS gzip-ready) |
| `npx eslint` (changed files) | **0 new errors** (5 pre-existing errors in `src/services/api/admin.ts` lines 91/129/250/522/714 are unrelated and not introduced by this change) |
| Playwright E2E | Spec committed (5 scenarios, 210 lines); runtime execution deferred to manual — see W-6 |

## Spec Compliance

| Requirement | Scenarios | Covered at runtime | Notes |
|-------------|-----------|--------------------|-------|
| Backups navigation and access | 3 | 3 ✅ | AuthzMatrixTests covers principal/non-principal/anonymous |
| On-demand backup trigger (UI stream) | 3 | 3 ✅ | Trigger streams + audit + rate-limit + missing-tool |
| Server-side management command | 2 | 2 ✅ | Cron success + failure paths |
| List server-side backups | 2 | 2 ✅ | Includes C-2 fix (age_label) |
| Download a backup file | 2 | 2 ✅ | Including path-traversal defense |
| Delete a backup file | 2 | 2 ✅ | Including C-3 fix (30s rate limit) |
| Audit log of admin backup actions | 2 | 2 ✅ | Including W-2 fix (download 429 audit row) |
| Retention policy | 2 | 2 ✅ | Daily + weekly independent pruning |
| Role enforcement | 2 | 2 ✅ | Worker + branch admin denied |
| **Total** | **20** | **20** | All scenarios covered |

## Cycle Completion

| Phase | Artifact | Status |
|-------|----------|--------|
| Explore | `openspec/changes/admin-db-backups/explore.md` | present |
| Propose | `openspec/changes/admin-db-backups/proposal.md` | present |
| Spec | `openspec/changes/admin-db-backups/specs/admin-db-backups.md` | present |
| Design | `openspec/changes/admin-db-backups/design.md` | present |
| Tasks | `openspec/changes/admin-db-backups/tasks.md` | 17/26 checked (reconciled — see below) |
| Apply | `openspec/changes/admin-db-backups/apply-progress.md` | 4 PRs + PR-fix all documented |
| Verify | `openspec/changes/admin-db-backups/verify-report.md` | PASS WITH WARNINGS |

### Task Completion Gate (reconciled)

`grep -c '^- \[x\]' tasks.md` → **17** checked.
`grep -c '^- \[ \]' tasks.md` → **9** unchecked (4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6).

The 9 unchecked tasks are Phase 4 (HTTP endpoints) and Phase 5 (frontend) items. The `apply-progress.md` documents for PR2 and PR3 explicitly mark each of these as **completed at runtime** with file-level evidence and test coverage:

- **Phase 4** (4.1, 4.2, 4.3) — PR2 `apply-progress.md` lines 199–203 enumerate each completed task with the file paths and test files that prove it. The four views, URL wiring, authz matrix, rate limits, and integration tests are all live and tested (39/39 backend tests pass after PR2).
- **Phase 5** (5.1, 5.2, 5.3, 5.4, 5.5, 5.6) — PR3 `apply-progress.md` lines 343–352 enumerate each completed task with the file paths and frontend build/test evidence. The frontend build passes and `npx tsc -b` is clean.

The `verify-report.md` further confirms Phase 4 and 5 behavior at runtime (Behavioral Compliance Matrix rows 176–195, Design Coherence rows 240–251, Frontend build PASS). The orchestrator explicitly approved archive-time reconciliation per the exception rule in the `sdd-archive` SKILL.md Task Completion Gate.

**Reconciliation reason**: `sdd-apply` completed the work units for Phase 4 and Phase 5 across PR2 and PR3 but did not flip the `[ ]` to `[x]` in the persisted `tasks.md` artifact. The runtime evidence (42/42 tests, frontend build, ESLint, behavioral compliance matrix) and the four `apply-progress` PRs prove completion. The archived audit trail therefore records the persisted task artifact as **17/26 checked with 9 mechanical reconciliation items** that the orchestrator-approved archive repair reconciles against the apply-progress evidence.

## Critical Findings (closed)

| ID | Title | Closed via |
|----|-------|-----------|
| C-1 | `.env.example` env-var names diverged from `settings.py`; rate-limit envs were dead variables | `4293b1f` — renames `BACKUP_KEEP_DAILY`/`BACKUP_KEEP_WEEKLY` → `BACKUP_DAILY_KEEP`/`BACKUP_WEEKLY_KEEP`, adds `BACKUP_RATE_LIMIT_TRIGGER_SECONDS` (default 60), `BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS` (default 30), `BACKUP_RATE_LIMIT_DELETE_SECONDS` (default 30); views read settings instead of literals |
| C-2 | List endpoint missing spec-mandated `age` ("hace 2 días") field | `b387091` — `_format_age_label(modified_at)` helper returns Spanish phrases (`"recien"`, `"hace N minutos"`, `"hace N horas"`, `"hace N dias"`, `"hace mas de 1 mes"`); `_serialize_entry` emits `age_label`; TS `BackupFile` declares `ageLabel`; `BackupTable` adds "Hace" column; 2 new Django tests + Playwright header assertion |
| C-3 | Delete rate-limit window was `10s` instead of spec-mandated `30s` | `4293b1f` — `check_rate_limit("delete", ..., settings.BACKUP_RATE_LIMIT_DELETE_SECONDS)` with default `30`; test uses `override_settings(BACKUP_RATE_LIMIT_DELETE_SECONDS=30)` for determinism |

## Open Warnings (follow-up tickets)

These WARNINGs are explicitly deferred per the orchestrator's scope decision and recorded here as follow-up backlog items. They do not block the archive.

| ID | Title | Recommended ticket |
|----|-------|--------------------|
| W-1 | Dead setting `BACKUP_LOCK_PATH` (`.lock` filename declared but never consumed) | "backups: remove or wire `BACKUP_LOCK_PATH`" |
| W-4 | Trigger endpoint retains dump after streaming; design said it shouldn't | "backups: decide retention vs streaming; align spec/design/impl" |
| W-5 | Lock filename mismatch (`.lock` vs `.backup.lock`) | Couple to W-1 in a single cleanup ticket |
| W-6 | Playwright E2E spec was committed but never executed | "backups: wire Playwright e2e to CI backend harness" |
| W-7 | `_dump_to_path` SQLite branch interpolates `tmp_path` into single-quoted `.backup` argument | "backups: harden sqlite3 `.backup` invocation" |

SUGGESTIONs (S-1 to S-4: temp path collisions, lock setting cleanup, ES Lint debt, audit metadata shape) are also carried forward as backlog.

## Spec Sync

The `admin-db-backups` domain did not exist in `openspec/specs/` before this change. The delta spec at `openspec/changes/admin-db-backups/specs/admin-db-backups.md` was therefore treated as a full spec (per the OpenSpec convention for new domains) and **copied verbatim** to `openspec/specs/admin-db-backups/spec.md`. The source file inside the change folder was not modified.

| Domain | Action | Details |
|--------|--------|---------|
| `admin-db-backups` | Created (full spec copy) | 9 requirements, 20 scenarios, all preserved |

The copied file is byte-identical to the source delta spec (verified with `diff` — no output).

## Archive Move

The entire change folder was moved with `git mv`:

```
openspec/changes/admin-db-backups/
  → openspec/changes/archive/2026-08-06-admin-db-backups/
```

Archived contents (all original files preserved):

- `explore.md` — pre-change exploration notes
- `proposal.md` — intent, scope, capabilities, risks, success criteria
- `design.md` — design decisions on app structure, engine branching, audit, lock, retention, frontend
- `specs/admin-db-backups.md` — the original delta (now also in `openspec/specs/admin-db-backups/spec.md`)
- `tasks.md` — final task state at archive time (17/26 checked, 9 mechanically reconciled per orchestrator-approved archive repair)
- `apply-progress.md` — 4 PRs + PR-fix cumulative progress logs
- `verify-report.md` — verification report with PASS WITH WARNINGS verdict
- `archive-report.md` — this file

## Source of Truth After Archive

| Spec | Path |
|------|------|
| Admin database backups (canonical) | `openspec/specs/admin-db-backups/spec.md` |

The active change folder is gone from `openspec/changes/admin-db-backups/` and the archive folder contains the complete audit trail.

## Engram Persistence

This archive report is persisted to Engram with:

- topic_key: `sdd/admin-db-backups/archive-report`
- project: `clinica-test`
- type: `architecture`
- capture_prompt: `false`

Three follow-up architecture/pattern observations are also persisted separately:

- Delivery strategy: stacking 4 PRs from a 970-line forecast
- Apply/verify pattern: spec-vs-impl triple-check (env-var names, spec field completeness, rate-limit window values)
- Backup service pattern: `fcntl.flock` + sqlite3/postgres engine branching + audit log

## SDD Cycle Status

**COMPLETE.** The `admin-db-backups` change has been fully explored, proposed, specified, designed, implemented (5 PRs: PR1 backend bootstrap, PR2 HTTP endpoints, PR3 frontend, PR4 docs, PR-fix verify follow-up), verified, and archived. The Spanish admin "Respaldos" feature with on-demand trigger, retention, audit, and operator-runbook cron is now part of the production source of truth at `openspec/specs/admin-db-backups/spec.md`. Ready for the next change.
