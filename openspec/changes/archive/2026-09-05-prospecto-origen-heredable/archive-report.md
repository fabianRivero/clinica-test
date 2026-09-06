# Archive Report — prospecto-origen-heredable

## Cycle Metadata

| Field | Value |
|-------|-------|
| Change name | `prospecto-origen-heredable` |
| Source change folder | `openspec/changes/prospecto-origen-heredable/` |
| Archive folder | `openspec/changes/archive/2026-09-05-prospecto-origen-heredable/` |
| Archive date (ISO) | 2026-09-05 |
| Artifact store | `openspec` |
| Review gate | structurally ABSENT (project does not use RDD; `openspec/config.yaml` carries no review config) — archive proceeded under ordinary repository policy |

## Final State

| Metric | Value |
|--------|-------|
| Implementation tasks complete | 11/11 (`- [x]` for tasks 1.1, 1.2, 1.3, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3 — counted 13 `[x]` markers; the 11 implementation tasks listed in `verify-report.md` are all checked) |
| Verify verdict | `pass_with_warnings` |
| CRITICAL findings | 0 |
| Pre-existing baseline issues carried over | yes (build errors in `AdminOperationDetailPage.tsx` and `ReservationModal.tsx`; Playwright `PagoRealizado.full_clean` global-setup bug; lint baseline of 127 problems) — explicitly NOT counted against this change per `verify-report.md` |

The task count `13/13 checked = 0 unchecked` matches the orchestrator's `tasks.md` parse. The orchestrator prompt referenced "11 implementation tasks"; the persisted `tasks.md` actually lists 13 numbered sub-tasks across Phases 1–5, all marked `[x]`. No stale checkboxes. No reconciliation was needed.

## Specs Synced

| Domain | Action | Requirements delta | Notes |
|--------|--------|--------------------|-------|
| `prospecto-origen` | Created | 4 requirements (full NEW spec) | Source had no main spec; mechanical `cp` into `openspec/specs/prospecto-origen/spec.md` |
| `cliente-origen` | Updated | +2 ADDED, 0 MODIFIED, 0 REMOVED | Main spec already existed from change `cliente-origen-recurrente`; appended delta ADDED block |
| `admin-prospect-conversion` | Updated | +1 ADDED, 1 MODIFIED, 0 REMOVED | Main spec existed; replaced `### Requirement: Finalize Dispatcher Per Mode` block with delta's MODIFIED version; appended new `prospect origin non-overwrite contract` requirement |

### Specs Synced — Diff Readbacks

#### prospecto-origen (NEW, mechanical cp)

```text
$ cp openspec/changes/prospecto-origen-heredable/specs/prospecto-origen/spec.md /tmp/temp
$ diff -r openspec/changes/prospecto-origen-heredable/specs/prospecto-origen/spec.md /tmp/temp
(empty)
$ mv /tmp/temp openspec/specs/prospecto-origen/spec.md
$ diff -r openspec/changes/prospecto-origen-heredable/specs/prospecto-origen/spec.md openspec/specs/prospecto-origen/spec.md
(empty)
```

Verbatim `diff -r` output (both invocations):

```text
=== diff -r output (must be empty) ===
=== diff exit code: 0 ===
=== final diff -r against main spec (must be empty) ===
=== final diff exit code: 0 ===
```

Empty diff = pass. ✅

#### cliente-origen (delta ADDED, append)

```text
$ cat openspec/specs/cliente-origen/spec.md \
    <(tail -n +3 openspec/changes/prospecto-origen-heredable/specs/cliente-origen/spec.md) \
    > /tmp/expected.md
$ diff -r /tmp/expected.md openspec/specs/cliente-origen/spec.md
(empty)
```

Verbatim `diff -r` output:

```text
=== diff -r: merged main spec vs expected merged (delta appended to original main) ===
=== diff exit code: 0 ===
```

Empty diff = pass. ✅

#### admin-prospect-conversion (delta MODIFIED + ADDED, block-replace + append)

The merge was constructed via `sed` (shell-only, no Read→Write of artifact content) from the snapshot of the original main spec and the delta. Expected file built with:

```bash
sed -n '1,67p' "$orig_main/spec.md"  >  expected/spec.md   # main: lines 1..67
sed -n '5,61p' "$delta/spec.md"      >> expected/spec.md   # delta MODIFIED block (lines 5..61)
sed -n '106,$p' "$orig_main/spec.md" >> expected/spec.md   # main: lines 106..end
printf '\n' >> expected/spec.md                            # newline boundary (orig main lacks trailing newline)
sed -n '64,79p' "$delta/spec.md"     >> expected/spec.md   # delta ADDED block (lines 64..79)
```

Pre-replacement sanity diff (must be non-empty, confirming the expected change is real):

```text
70c70,72
< The system MUST dispatch finalize to one of three branches based on the draft state and MUST wrap every branch in a single `transaction.atomic()` block that rolls back all writes on any error.
---
> The system MUST dispatch finalize to one of three branches based on the draft state and MUST wrap every branch in a single `transaction.atomic()` block that rolls back all writes on any error. In `mode='prospect'` finalize, the new `Cliente.origen` MUST be set from the source `Prospecto.origen`; in `mode='reactivation'` finalize, the existing `Cliente.origen` MUST NOT be modified under any circumstance.
> 
> (Previously: finalize dispatched per mode inside a single atomic transaction, with no explicit `origen` propagation contract for the prospect branch.)
77a80
> - AND the new `Cliente.origen` equals the source `Prospecto.origen`
86a90
> - AND the live `Cliente.origen` is unchanged regardless of what the draft carries
94a99
> - AND the new `Cliente.origen` equals the `origen` the admin selected on step 1
97a103,116
> #### Scenario: Prospect finalize propagates RECURRENTE_PRE_SISTEMA
> ...
> #### Scenario: Reactivation finalize never overwrites Cliente.origen
> ...
128c147,163
< - AND no `Usuario` or `Cliente` row is created
\ No hay ningún carácter de nueva línea al final del archivo
---
> - AND no `Usuario` or `Cliente` row is created
> ### Requirement: prospect origin non-overwrite contract
> ...
```

The original main spec lacked a trailing newline (`\ No hay ningún carácter de nueva línea al final del archivo`); the merged expected file ends with a newline. This is an intentional structural improvement for the merged spec — without it, the ADDED header would be glued to the last line of the existing main spec.

Final mechanical copy and readback (after `cp expected/spec.md openspec/specs/admin-prospect-conversion/spec.md`):

```text
=== Pre-mv diff -r (must be empty) ===
=== Pre-mv diff exit code: 0 ===
=== Final diff -r: main spec vs expected merged (must be empty) ===
=== Final diff exit code: 0 ===
```

Empty diff = pass. ✅

### Archive Move — Diff Readback

```text
$ snapshot_root="$(mktemp -d /tmp/sdd-archive.XXXXXX)"
$ cp -R openspec/changes/prospecto-origen-heredable "$snapshot_root/source"
$ mkdir -p openspec/changes/archive
$ git mv openspec/changes/prospecto-origen-heredable \
       openspec/changes/archive/2026-09-05-prospecto-origen-heredable
$ [ -e openspec/changes/prospecto-origen-heredable ] && echo "FAIL: source still exists" || true
$ diff -r "$snapshot_root/source" openspec/changes/archive/2026-09-05-prospecto-origen-heredable
```

Verbatim `diff -r` output:

```text
=== MANDATORY diff -r output (must be empty) ===
=== diff exit code: 0 ===
```

Source folder confirmed gone after move. Empty diff = pass. ✅

## Archive Contents

```text
openspec/changes/archive/2026-09-05-prospecto-origen-heredable/
├── archive-report.md            (this file — additive, excluded from diff comparison)
├── design.md
├── proposal.md
├── specs/
│   ├── admin-prospect-conversion/
│   │   └── spec.md
│   ├── cliente-origen/
│   │   └── spec.md
│   └── prospecto-origen/
│       └── spec.md
├── tasks.md                     (all 13 `- [x]` markers preserved)
└── verify-report.md             (verdict: pass_with_warnings, 0 CRITICAL)
```

| Artifact | Status |
|----------|--------|
| `proposal.md` | ✅ present |
| `specs/` (3 domain specs) | ✅ present |
| `design.md` | ✅ present |
| `tasks.md` | ✅ present (13/13 checked, 0 unchecked) |
| `verify-report.md` | ✅ present (`pass_with_warnings`, 0 CRITICAL) |

Active `openspec/changes/` no longer contains `prospecto-origen-heredable`. The archive folder is the audit trail and will not be modified.

## Source of Truth Updated

The following main specs now reflect the new behavior:

- `openspec/specs/prospecto-origen/spec.md` — created (NEW full spec, 4 requirements)
- `openspec/specs/cliente-origen/spec.md` — appended 2 ADDED requirements (`prospect-side origin feeding Cliente.origen`, `future prospect list badge (informational)`)
- `openspec/specs/admin-prospect-conversion/spec.md` — replaced `Finalize Dispatcher Per Mode` block with the new contract; appended `prospect origin non-overwrite contract`

## Final-State Authority Statement

The terminal state recorded in this report reflects:

1. **Highest-ranked: the persisted `tasks.md`** — 13 `- [x]` markers, 0 `- [ ]`. Source-of-truth check confirms the 11 implementation tasks the orchestrator cited (plus 2 additional numbered sub-tasks from Phases 1–5) are all checked.
2. **Highest-ranked: `openspec/changes/.../verify-report.md`** — `critical_findings: 0`, `verdict: pass_with_warnings`. CRITICAL count is 0, satisfying the archive gate.
3. **The orchestrator's launch prompt** confirms `pass_with_warnings` (0 CRITICAL) and authorizes archive.
4. **Intermediate snapshots** (`apply-progress` and `verify-report`) describe state at their time of writing. The `verify-report`'s "PARTIAL" scenarios and pre-existing baseline warnings describe implementation/test coverage gaps at verification time, not pending work. Per Final-State Authority, the cycle closes with all 11 implementation tasks complete; the 8 PARTIAL scenarios carry implementation evidence and no FAILING scenarios, and the 4 pre-existing baseline issues (build errors in untouched files, Playwright global-setup bug, lint baseline) remain as project-wide debt, not as this change's blockers.

No contradiction exists between ranked sources. No stale `pending` or `blocked` claim from `verify-report` is echoed as current state. The cycle is complete.

## Mechanical Copy Contract Compliance

- All three spec syncs performed via shell (`cp`, `cat` redirection, `sed` slicing, `mv`) — no Read→Write of artifact content.
- Archive move performed via `git mv` (fallback `mv`).
- Every copy/move followed by `diff -r`; verbatim output included above; empty diffs confirmed.
- Archive report (`archive-report.md`) is additive-only and was excluded from the source/destination `diff -r` comparison (it did not exist in the source snapshot).

## SDD Cycle Complete

The change `prospecto-origen-heredable` has been fully planned, implemented, verified, and archived. Ready for the next change.
