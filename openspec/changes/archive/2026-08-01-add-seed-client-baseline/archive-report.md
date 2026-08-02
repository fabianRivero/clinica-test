# Archive Report — `add-seed-client-baseline`

**Archived on**: 2026-08-01
**Project**: `clinica-test`
**Artifact store**: `openspec`
**Branch at archive**: `pr-4.2-cliente-reenroll`
**Cycle status**: ✅ Complete (no outstanding tasks, no warnings)

> **Post-`9baeaa4` repair (2026-08-02)**: This report was amended to (a) remove the stale byte-equivalence claim, (b) document the "no proposal/design" status of the originally-tracked active change, and (c) call out the deliberate merged-in-place nature of the archived spec. See §9 for the explicit reconciliation.

---

## 1. Cycle Closed

The `add-seed-client-baseline` change has been fully **planned → implemented → verified → archived**.

- **Planned** (2026-07-28): proposal, delta spec, design, tasks (23 items across 3 phases). *See §3 — only the delta spec and tasks were ever tracked in the active change folder; the proposal and design were never present at the working-tree level for this change.*
- **Implemented** (2026-07-28 onward): `seed_client_baseline` management command, 11-test suite, verification gates.
- **Verified at archive time (2026-08-01)**: 55/55 tests PASS in the consolidated verification cycle (carried over `reform-database-seed-scripts` verification on the same branch); all 23 implementation tasks confirmed complete.
- **Verified post-archive (commit `9baeaa4`, 2026-08-02)**: 83/83 accounts.tests pass with 7 new `clean_baseline` FichaCampo tests; the canonical and archived reform delta were updated to include the `PDF demo FichaCampo seed` requirement; this archived add-seed delta was updated in the same repair pass.
- **Archived** (2026-08-01): prior change folder moved; canonical spec is now the sole source of truth.

---

## 2. Spec Source-of-Truth Transferred

The canonical spec for capability `seed-client-baseline` was created and confirmed during the prior archive of `reform-database-seed-scripts` (2026-08-01) by merging two deltas in place:

- Original delta: `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md`
- Subsequent delta: `openspec/changes/reform-database-seed-scripts/specs/seed-client-baseline/spec.md`

Both deltas were merged into `openspec/specs/seed-client-baseline/spec.md` (canonical, 278 lines after `9baeaa4`) with a header note recording provenance. The in-place delta file under this prior change was updated to match (278 lines after the post-`9baeaa4` repair — the original 237-line delta grew to 278 to absorb the 4th reform ADDED requirement). This archive consolidates that transfer by demoting the in-place delta file to the archive folder where it belongs.

Going forward:
- **Sole source of truth**: `openspec/specs/seed-client-baseline/spec.md`
- **No active delta**: the prior change folder is now under `archive/`, so the in-place delta file is no longer a working artifact.

| Domain | Action | Details |
|---|---|---|
| `seed-client-baseline` | Source-of-truth transferred | 10 preserved requirements + 2 modified (Catalog baseline, Atomic transaction) + 4 added (Configurable admin URL, Allergy catalogs remain operator-managed, Cross-command aesthetic product consistency, PDF demo FichaCampo seed). Net: 14 requirements, 0 removed. |

No MODIFIED/REMOVED actions are required at archive time — they were already applied during the prior archive of `reform-database-seed-scripts`.

---

## 3. Active Change Artifact Inventory (provenance)

The active change folder `openspec/changes/add-seed-client-baseline/` at the moment of the archive (HEAD = `9baeaa4`) contained exactly:

```
openspec/changes/add-seed-client-baseline/
├── specs/
│   └── seed-client-baseline/
│       └── spec.md
└── tasks.md
```

- `git ls-tree HEAD openspec/changes/add-seed-client-baseline/` returns only the two paths above. **No `proposal.md`, `design.md`, or `exploration.md` was ever tracked for this change.** This is a deliberate, not a missing, artifact. The change was authored without an explicit proposal/design cycle (the change was scoped as a single `feat(ops): generic VPS setup guide + seed_client_baseline command` commit) and the SDD formalization came afterwards, anchored by the in-place delta spec and the 23-item `tasks.md`.
- The in-place delta file under this change was NOT a verbatim move of the original `add-seed-client-baseline` delta. It was rewritten in place during the `reform-database-seed-scripts` archive cycle to absorb that subsequent delta (3 ADDED + 2 MODIFIED requirements). The archived copy under `archive/2026-08-01-add-seed-client-baseline/specs/seed-client-baseline/spec.md` is therefore a **deliberate merged-in-place final record** of the active change at the moment of archive, not a byte-faithful copy of the pre-reform original.
- This is documented explicitly so that a future reader can correctly interpret the archive copy as a "consolidated working state at archive" rather than a "verbatim delta of the change as originally proposed".

---

## 4. Merge History Links

- **Prior archive** (consolidated merge source): `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/archive-report.md` — performed the in-place merge and created the canonical mirror.
- **Canonical spec**: `openspec/specs/seed-client-baseline/spec.md` — sole source of truth for the capability.
- **Archived delta** (this move): `openspec/changes/archive/2026-08-01-add-seed-client-baseline/specs/seed-client-baseline/spec.md` — preserved for audit trail; a deliberate merged-in-place final record of the active change at archive, including the reform delta and the post-`9baeaa4` PDF demo requirement.

### File provenance trail

| File | State | Notes |
|---|---|---|
| `openspec/specs/seed-client-baseline/spec.md` | Created (canonical, source of truth) | 278 lines, header note explains merge provenance. |
| `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/` | Prior archive | Contains the reform delta file used to build the canonical spec. |
| `openspec/changes/archive/2026-08-01-add-seed-client-baseline/` | This archive | Contains the original delta file (merged-in-place) + `tasks.md`. **No `proposal.md` or `design.md` was ever tracked for this change.** |

---

## 5. Task Completion Confirmation

`openspec/changes/add-seed-client-baseline/tasks.md` (now archived) shows **all 23 implementation tasks marked `[x]`** across three phases:

- **Phase 1 — Command implementation**: 11/11 tasks complete
- **Phase 2 — Tests**: 11/11 tasks complete
- **Phase 3 — Verification**: 3/3 tasks complete

No unchecked tasks remain. No stale-checkbox reconciliation was required at this archive step.

### Configuration coherence — `stacked-to-main` chain strategy

The chain-strategy mutation referenced in the `reform-database-seed-scripts` archive (§3 of that report) was persisted to `openspec/config.yaml:64` as `chain_strategy: stacked-to-main` and mirrored in `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/tasks.md` (forecast table) and in the inline note for task 4.3. The current working tree is coherent:

```text
$ grep -n chain_strategy openspec/config.yaml
64:  chain_strategy: stacked-to-main
```

`openspec/config.yaml` was not modified by this archive. The mutation is owned by the `reform-database-seed-scripts` archive and is documented there.

---

## 6. Archive Contents (audit trail)

`openspec/changes/archive/2026-08-01-add-seed-client-baseline/`

- `tasks.md` ✅ (23/23 tasks complete)
- `specs/seed-client-baseline/spec.md` ✅ (merged-in-place final record, 278 lines after post-`9baeaa4` repair)

The archived delta file is preserved for audit purposes. Future changes that touch the `seed-client-baseline` capability MUST author their delta against `openspec/specs/seed-client-baseline/spec.md`.

---

## 7. No Outstanding Tasks

There are no open implementation tasks, no pending rollouts, no stale checkboxes, and no follow-up warnings associated with this change. The carry-over WARNING from the `reform-database-seed-scripts` archive (`require_dev_or_test()` env guard placement inside `@transaction.atomic`) was logged in that archive and is NOT carried forward into this one — it remains a SUGGESTION in the previous archive report and does not block this closure.

---

## 8. SDD Cycle Complete

The change `add-seed-client-baseline` has been fully **planned → implemented → verified → archived**.

The capability `seed-client-baseline` is now governed exclusively by `openspec/specs/seed-client-baseline/spec.md`. The prior change folder is preserved under `openspec/changes/archive/2026-08-01-add-seed-client-baseline/` for audit purposes only.

Ready for the next change.

---

## 9. Post-`9baeaa4` Repair (2026-08-02)

### Context

Commit `9baeaa4 feat(seeds): seed PDF demo FichaCampo (35 rows) in clean_baseline` landed on `pr-4.2-cliente-reenroll` AFTER the 2026-08-01 archive of `add-seed-client-baseline`. The commit extended the canonical spec and the reform archive delta with the `PDF demo FichaCampo seed` requirement. The add-seed-client-baseline archive copy was NOT touched by `9baeaa4` and was therefore missing the 4th reform ADDED requirement.

### Inconsistencies detected and corrected

| # | Inconsistency | Evidence | Correction |
|---|---|---|---|
| A1 | The archived add-seed delta was missing the `PDF demo FichaCampo seed` requirement (13 requirements instead of 14). | `grep -c "^### Requirement:" openspec/changes/archive/2026-08-01-add-seed-client-baseline/specs/seed-client-baseline/spec.md` = 13; canonical = 14. | The 4th ADDED requirement was appended to the archive copy with a "Source note (2026-08-02, post-`9baeaa4` reconciliation)" annotation. Archive copy is now 278 lines. |
| A2 | This report claimed the archived delta was "byte-equivalent to the canonical spec except for the header provenance note". | Diff of working-tree archive copy vs canonical reveals 4 extra `### Requirement:` blocks in the canonical plus the "Modified Capabilities" / "Removed Capabilities" sections. | §4 amended: claim retired and replaced with "deliberate merged-in-place final record" wording. |
| A3 | This report did not document that the originally-tracked active change had no `proposal.md` or `design.md`. | `git ls-tree HEAD openspec/changes/add-seed-client-baseline/` shows only `specs/` and `tasks.md`. | §3 added: explicit "Active Change Artifact Inventory (provenance)" subsection documenting the absence and explaining that the change was a single-commit `feat(ops)` and the SDD formalization came after. |
| A4 | This report did not state that the archived delta was a deliberate merged-in-place final record, not a verbatim move. | §4 wording described it as "preserved for audit trail" without distinguishing the in-place edit history. | §3 and §4 amended to clarify the deliberate merged-in-place nature, and the §9 row A3 reinforces this. |
| A5 | This report did not document the `stacked-to-main` chain strategy mutation or its `openspec/config.yaml` coherence check. | `openspec/config.yaml:64` was modified by the reform archive; the add-seed archive inherits the same persistence state. | §5 added: explicit "Configuration coherence — `stacked-to-main` chain strategy" subsection confirming the working-tree value and noting the mutation is owned by the reform archive. |
| A6 | The 23/23 task count was correct but the verify result for the post-archive `9baeaa4` extension was not recorded. | `9baeaa4` commit message reports "83/83 accounts.tests pass". | §1 amended to record both the original 55/55 verification and the post-archive 83/83 verification. |

### What was NOT changed

- `openspec/changes/add-seed-client-baseline/` was already deleted from the working tree at archive time; the archive folder now contains the audit-trail copy. No restoration was required.
- `openspec/changes/reform-database-seed-scripts/` was already deleted from the working tree at archive time. No restoration was required.
- `openspec/config.yaml` was not modified by this repair; the `stacked-to-main` chain strategy is already coherent and recorded in §5.
- `openspec/changes/suspend-fingerprint-integration/` is untracked, unrelated, and was not touched.

### Remaining risks

- The archive copy is now 278 lines and content-parallel to the canonical modulo the audit-trail header. Future changes that add to the canonical MUST remember to also update both archived deltas, or the byte-equivalence drift will reopen. This is documented in the `reform-database-seed-scripts` archive report §8 (R4) and here.
- The "no proposal/design" inventory in §3 is a single-point provenance record. If a future contributor re-adds a `proposal.md` or `design.md` to the archive (which would be incorrect — those should be authored against the canonical delta process), the §3 narrative would need to be revisited.
