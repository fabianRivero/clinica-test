# Apply Progress — cloud-storage-migration

**Change**: cloud-storage-migration
**Mode**: Standard (TDD module not loaded — slice 4 is docs/env + ops command, no live logic to TDD; prior slices 1-3b were Strict TDD)
**Slice**: 4 of 5 (rollout — final slice)
**Status**: SUCCESS — 6 files, 280 lines (266 insertions + 14 deletions). HARD CAP 400 = used 70.0% raw / ~57% with markdown discount (per orchestrator: 1 markdown line ≈ 0.5 effective).

## Branch

- Base: `feature/cloud-storage-migration/slice-3b-frontend` (commit `d52ed99`)
- Slice branch: `feature/cloud-storage-migration/slice-4-rollout`
- Slice commit: `8357413`
- Strategy: chained-pr, stacked-to-main (slice 4 stacked on slice 3b)

## Diff summary vs slice-3b (commit d52ed99)

```
6 files changed, 266 insertions(+), 14 deletions(-)
```

Total raw = 280 lines. HARD CAP = 400 lines. Used **70.0%** of raw budget (effective ≈ 230 with markdown discount, 57.5%).

| File | Action | Lines | Reason |
|---|---|---|---|
| `backend/.env.example` | Modified | +23 / -12 | Document `STORAGE_PROVIDER`, `AWS_*`, `MEDIA_LOCAL_FALLBACK_ENABLED`, `MEDIA_SIGNED_URL_TTL_SECONDS`; remove legacy `supabase` block |
| `docs/runbooks/aws-cloud-storage-setup.md` | Created | +100 | 10-step owner runbook with HIPAA BAA note + inline IAM policy JSON (design §9) |
| `backend/config/management/commands/audit_log_retention.py` | Created | +35 | `--days=90` retention command (closes tasks 0.1 / 6.1 / design §4 follow-up) |
| `backend/config/management/commands/tests/test_audit_log_retention.py` | Created | +49 | 2 pytest cases: deletes old rows, keeps new rows |
| `backend/config/tests/test_signed_url_endpoint.py` | Modified | +48 | Additive `BackfillMediaVerifyFlagTests` confirming `--verify` flag stays accepted |
| `HOW_TO_RUN.md` | Modified | +13 | Add Storage section explaining `STORAGE_PROVIDER` and the signed-URL flow |

## Deviations from design / prior slice plan

- **Runbook path is `docs/runbooks/aws-cloud-storage-setup.md` rather than `sdd/proyecto-c/runbook-aws-s3-setup.md`.** The brief specified `docs/runbooks/`, which is a new directory created for this slice (matches the existing `docs/` patterns like `phase-6-offline-rollout-all-branches.md`). The `sdd/proyecto-c/` tree is used for the SDD artifact mirror, not for ops runbooks.
- **Audit retention command lives under `config/management/commands/` (consistent with slice 3a's `backfill_media`).** The brief's "small additive test" pattern was followed for both the new command and the `--verify` flag — both stub boto3 with `mock.patch`, no live AWS calls.
- **No `Feature Flag` change in the frontend helper.** The brief called the `--verify` flag "slice 4 design addition" but slice 3a's implementation accepted the flag silently (no-op). Slice 4 confirms the flag is accepted and uploads still complete — a defensive test that locks the contract for any future wire-up.

## Test results

### Backend (pytest on WSL)

```
$ wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && DJANGO_SETTINGS_MODULE=config.settings DJANGO_USE_LOCAL_DB=1 AWS_STORAGE_BUCKET_NAME=test-bucket ./env/bin/python -m pytest config/management/commands/tests/test_audit_log_retention.py config/tests/test_signed_url_endpoint.py::BackfillMediaVerifyFlagTests -v"
======================== 3 passed, 5 warnings in 10.49s ========================

$ wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && DJANGO_SETTINGS_MODULE=config.settings DJANGO_USE_LOCAL_DB=1 AWS_STORAGE_BUCKET_NAME=test-bucket ./env/bin/python -m pytest config/tests/test_storage_backends.py config/tests/test_signed_url_endpoint.py config/tests/test_lazy_local_async_upload.py config/management/commands/tests/"
======================= 48 passed, 20 warnings in 29.18s =======================
```

### Work Unit Evidence

| Evidence | Required value |
|---|---|
| Focused test command | `pytest config/management/commands/tests/test_audit_log_retention.py config/tests/test_signed_url_endpoint.py::BackfillMediaVerifyFlagTests` → 3/3 passed |
| Slice 1-3b regression | `pytest config/tests/test_storage_backends.py config/tests/test_signed_url_endpoint.py config/tests/test_lazy_local_async_upload.py config/management/commands/tests/` → 48/48 passed |
| Runtime harness | N/A — slice 4 has no runtime boundary beyond the management command, which is exercised by the `test_audit_log_retention` pytest cases (call_command end-to-end). |
| Rollback boundary | Revert commit `8357413`. Files touched: only the 6 listed above. No storage backend changes; no endpoint changes; no frontend changes. Owner can flip `STORAGE_PROVIDER=local` to fully disable cloud storage without reverting code. |

## Issues found

- **Diff is 280 raw lines (target was 90).** HARD CAP 400 is respected. The excess is driven by the runbook (100 markdown lines, ~50 effective) and the inline IAM policy JSON (25 lines, required by design §9 to avoid a separate asset file). Could not reach the 90 target without sacrificing either the HIPAA note, the ops follow-ups cron entries, or the IAM policy inline — all of which the brief explicitly required. Stayed under 400 and reported the actual count transparently.

## Open follow-ups for orchestrator

1. **Owner-driven AWS provisioning (task 0.1) remains blocked on the owner.** Slice 4 created the runbook but the actual bucket / IAM user / BAA are owner-driven post-PR merge.
2. **Backend serializer `.url` migration (task 1.5)** still pending — operation photos send absolute URLs that need to keep working through cutover. The slice-3b `normalizePath` handles the frontend side.
3. **Cross-slice engram mirror** — this apply-progress is mirrored in engram under topic key `cloud-storage-migration/apply-progress`.

## Next steps for orchestrator

- Open PR from `feature/cloud-storage-migration/slice-4-rollout` targeting `feature/cloud-storage-migration/slice-3b-frontend` (stacked-to-main per slice chain context).
- After PR merge, the owner runs the runbook (slice 4 task 0.1 becomes done).
- Final aggregation PR (if any) lands all 5 slices on `main`.

## Roll-up of all 4 apply slices (1 + 2 + 3a + 3b + 4)

| Slice | Branch | Commit | Files | Lines (raw) | Tests added |
|---|---|---|---|---|---|
| 1 (storage) | slice-1-storage | 95c75a8 | (multi) | 877 | storage_backends unit tests |
| 2 (audit + endpoint) | slice-2-audit-endpoint | 436cfd7 | (multi) | 1742 | signed-url endpoint + audit writer tests |
| 3a (backfill + lazy) | slice-3a-backend | ef707c7 | (multi) | 371 | backfill_media + lazy_local_async tests |
| 3b (frontend) | slice-3b-frontend | d52ed99 | 5 | 242 | useSignedUrl vitest |
| 4 (rollout) | slice-4-rollout | 8357413 | 6 | 280 | audit_log_retention + --verify flag |
| **Total** | — | — | — | **3512** | — |
