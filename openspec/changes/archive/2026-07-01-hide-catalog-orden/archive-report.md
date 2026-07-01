# Archive Report: hide-catalog-orden

**Archived**: 2026-07-01
**Change**: hide-catalog-orden
**Project**: clinica-test
**Mode**: openspec

---

## Spec Sync Summary

### `medical-form-section-editor/spec.md` — Updated

| Action | Detail |
|--------|--------|
| REQ-11 removed | Manual reorder via PATCH `{orden: N}` removed (Reason: server-managed orden replaces manual assignment; Migration: auto-assign on create, preserve on update) |
| REQ-9 updated | `orden` removed from updatable fields; update preserves existing orden |
| REQ-1, REQ-2, REQ-3 updated | `orden` removed from create payload contract; auto-assign added to scenario notes |
| REQ-4, REQ-5, REQ-6, REQ-7, REQ-8, REQ-10 | Unchanged |
| Scenarios updated | "Edit section preserves orden" and "Update payload with order field is ignored" added; "Reorder section" removed |

### `catalog-orden-auto-assigned/spec.md` — Created (new canonical spec)

| Action | Detail |
|--------|--------|
| New spec created | Directory `openspec/specs/catalog-orden-auto-assigned/` |
| Promoted from delta | Delta wrapper removed; standard canonical format with `## Purpose` and `## Requirements` |
| Requirements | 6 requirements: Auto-Assign on Create, Preserve on Update, Hidden in Metadata, Hidden in Values, Hidden in Form Fields, List Ordering Unchanged |

---

## Archive Contents

| File | Status |
|------|--------|
| `proposal.md` | ✅ preserved |
| `tasks.md` | ✅ preserved |
| `verify-report.md` | ✅ preserved |
| `specs/medical-form-section-editor/` | ✅ preserved (delta + originals in archive) |
| `specs/catalog-orden-auto-assigned/` | ✅ preserved |
| `design.md` | Not present in this change |

---

## Canonical Specs Updated

- `openspec/specs/medical-form-section-editor/spec.md` — REQ-11 removed, REQ-1/2/3/9 updated, new scenarios added
- `openspec/specs/catalog-orden-auto-assigned/spec.md` — New canonical spec created

## SDD Cycle Complete

All phases completed: propose → spec → design → tasks → apply → verify → **archive**.
The change is fully planned, implemented, verified, and archived.
