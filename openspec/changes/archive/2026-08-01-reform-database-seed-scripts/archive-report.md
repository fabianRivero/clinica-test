# Archive Report — `reform-database-seed-scripts`

**Archived on**: 2026-08-01
**Project**: `clinica-test`
**Artifact store**: `openspec`
**Branch at archive**: `pr-4.2-cliente-reenroll`
**Cycle status**: ✅ Complete (intentional with one non-blocking warning, see §6)

> **Post-`9baeaa4` repair (2026-08-02)**: This report was amended to reflect the additional `PDF demo FichaCampo seed` requirement introduced by commit `9baeaa4` AFTER the original archive. See §8 for the explicit reconciliation.

---

## 1. Spec Merge Summary

### Decision: merge-in-place into the prior unarchived change

The prior change `add-seed-client-baseline` is still active in `openspec/changes/` and its delta spec at `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` is therefore the working source of truth for the `seed-client-baseline` capability. There was no pre-existing canonical spec at `openspec/specs/seed-client-baseline/spec.md`.

I selected the **merge-in-place** approach over the **create-new-canonical** approach for the following reasons:

1. **Traceability**: the delta's MODIFIED requirements (Catalog baseline, Atomic transaction) reference the exact requirement names already declared in the prior delta. Applying them in place preserves a single requirement/scenario chain per capability.
2. **No orphan delta**: leaving the prior change intact and creating a separate `openspec/specs/seed-client-baseline/spec.md` would leave two divergent delta sources for the same capability.
3. **Forward-compatibility**: the prior change will be archived in a separate SDD cycle. After that archive, `openspec/specs/seed-client-baseline/spec.md` becomes the canonical mirror, but the in-place merge does not preclude that — it just keeps the two files synchronized today.

Both the prior delta file **and** a new canonical mirror at `openspec/specs/seed-client-baseline/spec.md` were updated so future changes can reference either path. At the moment of the original archive (2026-08-01), the two files were byte-equivalent in their merged form. **The byte-equivalence claim became stale after commit `9baeaa4` and is corrected below in §8.**

### Spec resolutions (original archive, 2026-08-01)

| Delta requirement | Section action | Resolved into |
|---|---|---|
| **ADDED — Configurable admin URL** | Appended | `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` (under "ADDED Requirements (from `reform-database-seed-scripts`)") and mirrored at `openspec/specs/seed-client-baseline/spec.md` |
| **ADDED — Allergy catalogs remain operator-managed** | Appended | Same locations as above |
| **ADDED — Cross-command aesthetic product consistency** | Appended | Same locations as above |
| **MODIFIED — Catalog baseline** | Replaced in place | Replaces the original "Catalog baseline" requirement (3 scenarios → 3 scenarios: Fresh or partially completed aesthetic set, Idempotent reconciliation, Preserve unrelated and operator custom data) |
| **MODIFIED — Atomic transaction** | Replaced in place | Replaces the original "Atomic transaction" requirement (3 scenarios → 2 scenarios: Successful fresh or partial completion, Failure during aesthetic reconciliation) |
| All other original requirements (Role baseline, Branch creation, Admin general creation, Tablet kiosk creation, Interactive mode, Non-interactive mode, Safety check on existing main branch, Output summary) | Preserved unchanged | — |

**Net delta at original archive**: +3 requirements, 2 requirements modified, 0 requirements removed, 10 requirements preserved. No REMOVED actions were specified in the delta, so no `(Reason: ...)` / `(Migration: ...)` notes were required.

---

## 2. Rollout Reconciliation (Phase 4)

The `verify-report.md` reports a PASS verdict with 14/14 implementation tasks complete and 3 rollout tasks (4.1, 4.2, 4.3) explicitly marked as deployment checkpoints out of scope for verification. The orchestrator authorized a `sdd-archive` time reconciliation of these checkboxes under the **stale-checkbox exception** (per `sdd-archive` skill §"Task Completion Gate"), backed by `verify-report.md` proof.

| Task | Status before | Status after | Reconciliation reason (proof) |
|---|---|---|---|
| 4.1 Land A1; confirm migration reverse on SQLite leaves FK rows intact | `[ ]` | `[x]` | `verify-report.md` §"Per-task completeness table" row 1.1–1.3 confirms migration file shipped, forward+reverse applied via `manage.py migrate catalogs`, `test_reverse_leaves_servicio_config_rows_intact` passes. |
| 4.2 Land A2; confirm 13/13 client tests green before opening B1 | `[ ]` | `[x]` | `verify-report.md` "Build & Tests" confirms `55/55 OK` including the preserved 13 original `test_seed_client_baseline` tests; "Verdict" PASS. |
| 4.3 Surface chain strategy to user | `[ ]` | `[x]` | User chose `stacked-to-main`; `openspec/config.yaml:64` updated from `chain_strategy: not_yet_set` → `stacked-to-main`; the `Chain strategy:` line in the `tasks.md` forecast table is also updated. |

The archive audit trail will not contain stale unchecked implementation tasks for completed work after this reconciliation. The unchecked rollout box for 4.3 is closed with a recorded governance resolution (chain strategy).

---

## 3. Configuration Update

`openspec/config.yaml:64`

```diff
 persistence:
   mode: openspec
   project: clinica-test
   delivery_strategy: ask-on-risk
   review_budget_lines: 400
-  chain_strategy: not_yet_set
+  chain_strategy: stacked-to-main
```

`openspec/changes/reform-database-seed-scripts/tasks.md` (forecast table)

```diff
 | Suggested split | A1 → A2 → B1 (stacked-to-main) |
 | Delivery strategy | ask-on-risk |
-| Chain strategy | pending |
+| Chain strategy | stacked-to-main |

 Decision needed before apply: Yes
 Chained PRs recommended: Yes
-Chain strategy: pending
+Chain strategy: stacked-to-main
 400-line budget risk: Medium
```

---

## 4. Files Touched by This Archive

| File | Action | Reason |
|---|---|---|
| `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` | Modified (merge) | In-place merge of delta from `reform-database-seed-scripts`: 2 MODIFIED requirements replaced, 3 ADDED requirements appended, header provenance note added. |
| `openspec/specs/seed-client-baseline/spec.md` | Created (canonical mirror) | New canonical spec for the capability so future changes can reference the source of truth. At the moment of the original archive (2026-08-01) this file was byte-equivalent to the in-place merged delta above (with an updated header). After commit `9baeaa4` the canonical was extended with the `PDF demo FichaCampo seed` ADDED requirement and a trailing "Modified Capabilities" / "Removed Capabilities" summary; the two files are no longer byte-equivalent. See §8 for the full reconciliation. |
| `openspec/config.yaml` | Modified (line 64) | Persist `chain_strategy: stacked-to-main`. |
| `openspec/changes/reform-database-seed-scripts/tasks.md` | Modified (rollout checkboxes + forecast) | Mark 4.1, 4.2, 4.3 as `[x]` with explicit reconciliation reason; update `Chain strategy` line. |
| `openspec/changes/reform-database-seed-scripts/` → `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/` | Moved (folder) | Standard archive move. |

---

## 5. Archive Contents (audit trail)

`openspec/changes/archive/2026-08-01-reform-database-seed-scripts/`

- `proposal.md` ✅
- `exploration.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (17/17 tasks complete after reconciliation)
- `verify-report.md` ✅ (PASS, 55/55 tests)
- `specs/seed-client-baseline/spec.md` ✅ (delta spec; the merged full canonical lives at `openspec/specs/seed-client-baseline/spec.md`)

---

## 6. Issues Carried Forward (non-blocking)

The `verify-report.md` raised one WARNING that is not blocking the archive:

> **`seed_pdf_baseline.handle()` env guard inside `@transaction.atomic`** — The env guard `require_dev_or_test()` is called inside `handle()`, which is wrapped in `@transaction.atomic`. Design intent (D5) is "pre-transaction". In practice, Django does not open a transaction until the first DB query, so the guard executes before any write. `test_rejects_production_pre_write` confirms `_record_counts()` is unchanged after rejection. **Not blocking** because the test contract is satisfied.

Recommendation: in a future cleanup, either move the env guard call outside `@transaction.atomic` or add an inline doc comment that `require_dev_or_test` does no DB I/O so its placement is safe. Tracked as a SUGGESTION in `verify-report.md` §"Issues Found".

---

## 7. SDD Cycle Complete

The change has been fully **planned → implemented → verified → archived**.

- **Planned**: proposal, exploration, design (D1–D10), tasks (17 items), delta spec.
- **Implemented**: 14/14 implementation tasks across work units A1, A2, B1.
- **Verified at archive time (2026-08-01)**: 55/55 tests PASS in 70.5s; all 9 spec scenarios (3 ADDED + 2×3 MODIFIED scenarios) have covering tests; all 10 design decisions (D1–D10) implemented; forward+reverse migration on SQLite verified.
- **Post-archive verification (commit `9baeaa4`, 2026-08-02)**: 83/83 accounts.tests pass with the 7 new `clean_baseline` FichaCampo tests. The archived canonical and delta copies were updated in the same commit to include the new `PDF demo FichaCampo seed` requirement.
- **Archived**: delta merged into `seed-client-baseline` canonical spec, rollout reconciled, folder moved to `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/`.

The capability `seed-client-baseline` is now governed by `openspec/specs/seed-client-baseline/spec.md` (mirror) and the in-place merged delta at `openspec/changes/add-seed-client-baseline/specs/seed-client-baseline/spec.md` (to be archived in a separate cycle).

Ready for the next change.

---

## 8. Post-`9baeaa4` Repair (2026-08-02)

### Context

Commit `9baeaa4 feat(seeds): seed PDF demo FichaCampo (35 rows) in clean_baseline` landed on `pr-4.2-cliente-reenroll` AFTER the 2026-08-01 archive of `reform-database-seed-scripts`. The commit:

- Added 35 demo `FichaCampo` rows to `clean_baseline.py` and 7 covering tests (83/83 accounts.tests pass).
- Created the canonical spec at `openspec/specs/seed-client-baseline/spec.md` with a header note recording the prior in-place merge.
- Created the archived delta copy at `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/specs/seed-client-baseline/spec.md` containing the new ADDED requirement (PDF demo FichaCampo seed) so the archived delta is a faithful representation of the merged state.

The two spec files committed by `9baeaa4` are 109 lines and 278 lines respectively. They are **not** byte-equivalent: the canonical is the merged full spec (header + 10 original + 4 reform ADDED + 2 MODIFIED + Modified/Removed summary sections), while the archived reform delta retains its delta-only header and 6 reform delta requirements (3 ADDED + 2 MODIFIED + 1 ADDED post-9baeaa4).

### Inconsistencies detected and corrected by this repair

| # | Inconsistency | Evidence | Correction |
|---|---|---|---|
| R1 | This report claimed "byte-equivalent in their merged form" for `add-seed-client-baseline` and the canonical mirror. | `9baeaa4` introduces 109-line archived delta and 278-line canonical; the two diverge by header, original requirements, and trailing summary sections. | §1 amended: "At the moment of the original archive" qualifier added; byte-equivalence claim explicitly retired in §8. |
| R2 | This report did not record the `PDF demo FichaCampo seed` ADDED requirement. | `git show 9baeaa4 -- openspec/.../spec.md` shows the requirement was committed to both the canonical and the reform archive copy. | `openspec/changes/archive/2026-08-01-reform-database-seed-scripts/specs/seed-client-baseline/spec.md` was updated to include the requirement with a source note dated 2026-08-02. Net spec resolutions now read 4 ADDED + 2 MODIFIED. |
| R3 | The reform archived spec carried a "Delta for Seed Client Baseline" header that did not record the post-9baeaa4 reconciliation. | Inline audit requirement per `openspec-convention.md` "delta spec sections" rules and the SDD audit trail contract. | The PDF demo requirement is annotated with a "Source note (2026-08-02, post-`9baeaa4` reconciliation)" blockquote explaining when and why it was appended. |
| R4 | The `add-seed-client-baseline` archive copy at `openspec/changes/archive/2026-08-01-add-seed-client-baseline/specs/seed-client-baseline/spec.md` was missing the `PDF demo FichaCampo seed` requirement (only 3 reform ADDED, not 4). | Diff of working-tree archive copy vs `git show 9baeaa4:openspec/specs/seed-client-baseline/spec.md` reveals the gap. | The 4th ADDED requirement was added to the add-seed archive copy with a parallel "Source note (2026-08-02, post-`9baeaa4` reconciliation)" annotation. The archive copy is now 278 lines and contains the same 14 requirements as the canonical (header + 10 original + 4 reform ADDED + 2 MODIFIED + Modified/Removed summary sections, plus the merge note header for the audit trail). |
| R5 | The "add-seed-client-baseline" archive report (separate file) repeated the byte-equivalence claim and did not document the "no proposal/design" status of the active change or that the archived spec was a deliberately merged-in-place final record. | `git ls-tree HEAD openspec/changes/add-seed-client-baseline/` returns only `specs/` and `tasks.md` — no `proposal.md` or `design.md` was ever tracked. | See the `2026-08-01-add-seed-client-baseline` archive report §3 and §6, amended in this same repair pass. |

### Net spec resolutions after post-`9baeaa4` repair

- **Original `reform-database-seed-scripts` delta (3 ADDED + 2 MODIFIED)**: unchanged in content; still authoritative for what that change contributed.
- **Post-`9baeaa4` delta (1 ADDED — `PDF demo FichaCampo seed`)**: appended to both archived copies and the canonical, all three with explicit source notes.
- **Archived add-seed-client-baseline** is now 278 lines, matching the canonical in requirement count and content (modulo the audit-trail header).

### What was NOT changed

- `openspec/changes/reform-database-seed-scripts/` was already absent from the working tree at archive time (commit 7b107bc only tracked the `add-seed-client-baseline` partial set); the active change folder is properly deleted. No restoration was required.
- `openspec/changes/add-seed-client-baseline/` is also already deleted; the archive folder now contains the audit-trail copy. No restoration was required.
- `openspec/config.yaml` `chain_strategy: stacked-to-main` is intact and coherent with the archived `tasks.md` forecast table; no `config.yaml` edit was necessary.
- `openspec/changes/suspend-fingerprint-integration/` is untracked, unrelated, and was not touched.

### Remaining risks

- The add-seed-client-baseline archive copy is now 278 lines; a future reviewer could read the two archived files (`add-seed-client-baseline` and `reform-database-seed-scripts`) and believe the audit trail is "duplicated". This is intentional: each archive is the audit trail for the change that contributed it. The header notes explicitly point readers to the canonical for the merged source of truth.
- The reform archived delta carries 6 reform requirements (3 ADDED + 2 MODIFIED + 1 post-9baeaa4 ADDED) but its delta header and "MODIFIED Requirements" section were authored for the original 3 ADDED + 2 MODIFIED set. This is a known limitation of representing a delta after the fact and is documented in the source note on the PDF demo requirement.
