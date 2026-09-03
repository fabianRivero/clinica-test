# Archive Report: direct-client-creation

## Change

`direct-client-creation` — adds an admin entry point on `/cms/clientes` to create a brand-new `Cliente` + `Usuario` without any prior `Prospecto`, reusing the existing 5-step conversion wizard with a new `mode='direct'`.

## Archived

- **Folder moved to:** `openspec/changes/archive/2026-09-03-direct-client-creation/`
- **Archive date:** 2026-09-03

## Final State (most recent verified evidence)

The final state below is sourced from the most recent `sdd-verify` re-run after remediation; the previous FAIL `verify-report` is superseded and the intermediate `apply-progress` from PR 2 is no longer authoritative for the current build.

- **Backend tests:** 11/11 passing (`DJANGO_USE_LOCAL_DB=1 python3 manage.py test tests.test_direct_client_conversion`)
- **Frontend build:** 0 TypeScript errors (`npm run build`)
- **Django URL contract (live resolve):** the corrected URLs (`/api/admin/clientes/directo/<id>/<step>/`) resolve to the expected views; the prior wrong URLs return 404 as intended
- **E2E tests:** 3/3 mocked + 1/1 no-mock (real backend) passing
- **Critical findings:** 0
- **Verdict:** PASS WITH WARNINGS

## Warnings at close (non-blocking)

- WARNING-1: Frontend `ConversionStepUser` readOnly/password visibility per mode lacks an automated test. Pre-change behavior; the refactor only added a third mode value.
- WARNING-2: 2 PARTIAL scenarios in the `admin-prospect-conversion` spec rely on the broader (unchanged) test suite for prospect/reactivation arms.
- WARNING-3: Spec text says finalize "returns 200" but implementation returns 201 — spec text needs correction in a follow-up; the code is correct.

## Specs Synced

| Domain | Action | Details |
|--------|--------|---------|
| `admin-direct-client-creation` | Created (new main spec) | 6 requirements, 9 scenarios |
| `admin-prospect-conversion` | Created (new main spec) | 5 requirements, 8 scenarios |

Both copies verified via `diff` (empty output = byte-identical).

## SDD Cycle Summary

| Phase | Status | Artifact |
|-------|--------|----------|
| Explore | ✅ Complete | `exploration.md` (304 lines) |
| Propose | ✅ Complete | `proposal.md` (110 lines) |
| Spec | ✅ Complete | `specs/admin-direct-client-creation/spec.md` + `specs/admin-prospect-conversion/spec.md` |
| Design | ✅ Complete | `design.md` (185 lines, 6 architecture decisions, threat matrix N/A) |
| Tasks | ✅ Complete | `tasks.md` (29 tasks, 25 marked `[x]`, 4 unchecked are visual review only) |
| Apply | ✅ Complete | 2 PRs stacked (PR 1 backend + PR 2 frontend) |
| Verify | ✅ Complete (PASS WITH WARNINGS) | `verify-report.md` |
| Archive | ✅ Complete | This report |

## Review Workload Outcome

- Forecast: 350–450 lines, risk Medium
- User decision: stacked PRs (backend → frontend)
- Actual: 2 PRs delivered as planned

## Deviations (recorded for traceability)

1. **Branch fallback for principal admins** (`admin_direct_client_initialize`): chained `get_user_branch(request)` after `_get_branch_for_scope_check(request)` to resolve principal-admin branches. Documented in design §Architecture Decision 6.
2. **No `payment/` URL in the route family**: first-payment fields ride on finalize multipart payload, not a separate URL. Documented in `api_urls.py` inline comment.
3. **Defensive `bytes(template)` coercion on `template_biometrico`**: surfaced and fixed a pre-existing latent bug that affected 7 unrelated tests across the project. Documented in design §Testing Strategy.
4. **One-line `payload["draftId"] = draft.pk` additive to `admin_direct_client_initialize`**: required so the frontend can construct the URL templates that include the `<int:direct_id>` segment. Documented in design §Interfaces / Contracts (`ProspectConversionResponse.draftId`).

## Knowledge Captured

The most valuable lesson from this cycle: a Playwright test that mocks the same URL strings its own client code emits cannot detect frontend-backend contract drift and produces false-positive passes. Django's `resolve()` is decisive runtime proof of URL contract mismatches. The `sdd-verify` phase caught a critical bug (`/api/admin/clientes/directo/<step>/` returned 404 because the service omitted the `<int:direct_id>` segment) that 3 passing E2E tests had silently validated against its own mistake. Future changes that introduce a new URL family MUST include at least one no-mock E2E test.

## Archive Contents

```
openspec/changes/archive/2026-09-03-direct-client-creation/
├── exploration.md
├── proposal.md
├── specs/
│   ├── admin-direct-client-creation/spec.md
│   └── admin-prospect-conversion/spec.md
├── design.md
├── tasks.md
└── verify-report.md
```

Mechanical copy verified — `diff -r` against pre-move snapshot returned empty.