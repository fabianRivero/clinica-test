# Tasks: Cloud Storage Migration

Change: `cloud-storage-migration`
PR strategy: `single-pr`
Artifact store: `hybrid` (openspec + engram mirror)
Pace: `auto`
Backend tests run on WSL per `openspec/config.yaml`.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (backend) | ~520 (storage_backends.py rewrite ~180 + settings ~25 + urls ~3 + api_views.py + api_urls.py ~30 + audit app ~120 + management/commands package ~15 + 3 test files ~250) |
| Estimated changed lines (frontend) | ~120 (useSignedUrl helper ~80 + component replacements ~30 + cache util ~10) |
| Estimated changed lines (docs/env) | ~90 (runbook ~70 + .env.example ~15 + urls/static note ~5) |
| Total estimated changed lines | ~730 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes — but PR strategy is single-pr; orchestrator must surface the choice to the user before apply** |
| Decision needed before apply | **Yes** (high budget risk; user must confirm `size:exception` or accept the slice split) |
| Delivery strategy | `single-pr` (received); will require `size:exception` approval or a slice re-plan |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units (if user chooses chained-PR override)

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Storage foundation: rewrite `storage_backends.py`, wire `STORAGES["default"]`, RED tests for `_save`/`_open`/`delete`/`exists`. | PR 1 | `wsl -e bash -c "cd backend && python -m pytest -k storage_backends -v"` | Mocked boto3 client; no live AWS needed | Revert PR 1 → `STORAGE_PROVIDER=local` keeps app on `FileSystemStorage` |
| 2 | Audit + endpoint: `audit` app, `AuditLog` model + migration, `media_signed_url` view + route, RED tests for 200/401/403/400/503/TTL-clamp. | PR 2 | `wsl -e bash -c "cd backend && python -m pytest -k media_signed_url -v"` | Mocked `boto3.client.generate_presigned_url` + mocked DB write for 503 path | Revert PR 2 → endpoint absent, `Boto3Storage.url()` still raises; no signed URLs issued |
| 3 | Backfill command + frontend: `backfill_media`, `useSignedUrl` helper, Playwright e2e (happy + forbidden). | PR 3 | `wsl -e bash -c "cd backend && python -m pytest -k backfill_media -v"` and `cd frontend/aesthetic-clinic && npm run test:e2e -- signed-url` | `--dry-run` first against a fixture bucket | Revert PR 3 → no backfill cron scheduled; frontend uses `/media/...` fallback |
| 4 | Rollout (ops-only): runbook finalization, `.env.example`, smoke tests against dev bucket, `STORAGE_PROVIDER=s3` rollout, `_BACKFILL_COMPLETE` sentinel monitoring. | PR 4 (or owner-driven post-merge) | `aws s3 ls s3://proyecto-c-clinical-dev --profile test` | Real bucket | Revert PR 4 = `STORAGE_PROVIDER=local` env flip |

## Skills to load

These skills are mandatory for the apply phase:

- `work-unit-commits` — SDD requires it when there are 2+ non-trivial files; this change touches many files across backend + frontend + ops.
- `sdd-apply` — loaded by the apply phase itself.

---

## Phase 0: Owner Setup (BLOCKER — pre-apply)

- [ ] **0.1** Owner provisions AWS per runbook `sdd/proyecto-c/runbook-aws-s3-setup.md` (BLOCKED on owner). Bucket `proyecto-c-clinical-<env>` in `sa-east-1`; all four public-access-block flags; Versioning ON; server access logs to dedicated logs bucket; IAM user with bucket-scoped policy; credentials stored in 1Password vault.
  - Files: `sdd/proyecto-c/runbook-aws-s3-setup.md` (create; check-in markdown checklist).
  - Verify: `aws s3 ls s3://proyecto-c-clinical-dev --profile proyecto-c-test` succeeds from a developer machine (owner runs).
  - Depends on: none (owner-driven).
  - Estimated lines: ~70 (markdown).
- [ ] **0.2** Update `.env.example` with the 8 new env vars from design §7 (`STORAGE_PROVIDER`, `AWS_*`, `MEDIA_SIGNED_URL_TTL_SECONDS`, `MEDIA_LOCAL_FALLBACK_ENABLED`); remove the `supabase` block.
  - Files: `backend/.env.example` (modify).
  - Verify: `grep -E "STORAGE_PROVIDER|AWS_S3_REGION_NAME|MEDIA_SIGNED_URL_TTL_SECONDS|MEDIA_LOCAL_FALLBACK_ENABLED" backend/.env.example`.
  - Depends on: none.
  - Estimated lines: ~15.

---

## Phase 1: Backend Storage Foundation

- [ ] **1.1** RED test for `Boto3Storage._save` capturing the double-open bug at `storage_backends.py:43`.
  - Files: `backend/tests/test_storage_backends.py` (create).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_storage_backends.py::test_save_handles_already_open_fieldfile -v"` fails against current code.
  - Depends on: 0.1 (or proceed with mocked boto3; live not required for this test).
  - Estimated lines: ~25.
- [ ] **1.2** Rewrite `backend/config/storage_backends.py`: replace `SupabaseStorage` (lines 12–73) + `LocalStorage` (lines 80–111) with `Boto3Storage` + `LazyLocalFallbackStorage`. Implement `_save`, `_open`, `delete`, `exists`, `size`, `modification_time`; `url()` raises `NotImplementedError`. Fix double-open bug per design §7 pseudocode.
  - Files: `backend/config/storage_backends.py` (rewrite).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_storage_backends.py -v"` — all storage backend tests pass.
  - Depends on: 1.1.
  - Estimated lines: ~180 (replace 112-line file with new module; net delta ~+70).
- [ ] **1.3** RED tests for `LazyLocalFallbackStorage.exists` / `_open` (bucket miss → local hit; bucket miss + local miss → `FileNotFoundError`).
  - Files: `backend/tests/test_storage_backends.py` (extend).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_storage_backends.py -k lazy_fallback -v"` fails before implementation.
  - Depends on: 1.2.
  - Estimated lines: ~50.
- [ ] **1.4** Wire `STORAGES["default"]` driven by `STORAGE_PROVIDER` at `backend/config/settings.py:192–206`. Local → `FileSystemStorage`; s3 → `LazyLocalFallbackStorage` when `MEDIA_LOCAL_FALLBACK_ENABLED=true`, else `Boto3Storage`. Remove legacy `supabase` comment.
  - Files: `backend/config/settings.py` (modify lines 192–206).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_storage_backends.py::test_storages_default_switches_by_provider -v"`.
  - Depends on: 1.2.
  - Estimated lines: ~25.
- [ ] **1.5** Verify backend serializer `.url` callers (`backend/config/api_views.py` lines 439, 444, 446, 657, 658, 1011, 1019, 1079, 5162, 8308; `backend/config/client_api_views.py` lines 418, 430, 561, 562; `backend/config/ticket_views.py` line 171). After this change `FieldFile.url` raises `NotImplementedError` for s3 provider. Apply MUST either: (a) switch these serializers to return relative paths (frontend resolves via signed-url endpoint), or (b) keep `.url` only when `STORAGE_PROVIDER == "local"`. The design did not enumerate this — apply chooses (a) per design §11 "Frontend stays live through cutover because URLs come from the new endpoint", and updates serializers accordingly.
  - Files: `backend/config/api_views.py`, `backend/config/client_api_views.py`, `backend/config/ticket_views.py` (modify `.url` call sites).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/ -k 'payment or ticket or operation_photos or appointment_notes' -v"` — all consumer tests still pass with relative paths.
  - Depends on: 1.2.
  - Estimated lines: ~30 (replace `.url` with `.name` in known-safe cases; verify each).
  - Open follow-up surfaced for the orchestrator: design did not enumerate serializer changes; flagged here.

---

## Phase 2: Audit App

- [ ] **2.1** RED test for `AuditLog` model fields and `write_audit_log` failure mode (`AuditWriteFailure` raised on DB error → endpoint returns 503).
  - Files: `backend/audit/tests/test_audit_log.py` (create).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest audit/tests/test_audit_log.py -v"` fails before implementation.
  - Depends on: none.
  - Estimated lines: ~30.
- [ ] **2.2** Create `backend/audit/` Django app: `models.py` (`AuditLog` per design §4), `services.py` (`write_audit_log` + `AuditWriteFailure`), `admin.py`, `apps.py`, `migrations/__init__.py`, `tests/__init__.py`. Generate migration with `python manage.py makemigrations audit`. Add `audit` to `INSTALLED_APPS` in `settings.py`.
  - Files: `backend/audit/models.py`, `backend/audit/services.py`, `backend/audit/admin.py`, `backend/audit/apps.py`, `backend/audit/__init__.py`, `backend/audit/migrations/__init__.py`, `backend/audit/migrations/0001_initial.py`, `backend/audit/tests/__init__.py` (all create); `backend/config/settings.py` (modify `INSTALLED_APPS`).
  - Verify: `wsl -e bash -c "cd backend && python manage.py makemigrations audit --dry-run --check"` reports no pending migrations; `python -c "from audit.models import AuditLog; print(AuditLog._meta.db_table)"` prints `audit_log`.
  - Depends on: 2.1.
  - Estimated lines: ~120 (model ~40, service ~30, app skeleton ~30, migration ~20).

---

## Phase 3: Signed-URL Endpoint

- [ ] **3.1** RED tests for `/api/media/signed-url/`: 401 unauth; 400 malformed path (`..`, `\`, leading `/`); 400 outside allowlist; 200 happy path (cliente self); 403 cliente cross; 200 especialista assigned; 403 especialista non-assigned; 200 admin principal wildcard; 403 stale key no row; TTL clamp to 604800; 503 on audit failure.
  - Files: `backend/tests/test_media_signed_url.py` (create).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_media_signed_url.py -v"` fails before implementation.
  - Depends on: 2.1.
  - Estimated lines: ~150.
- [ ] **3.2** Implement `media_signed_url` view in `backend/config/api_views.py`: `IsAuthenticated`; path sanitization; allowlist; per-prefix authorization helpers (use `accounts.Rol` lookup per design §6; `staff.Especialista` reverse via `user.especialista`); call `boto3.client.generate_presigned_url` with TTL clamped to 604800; call `write_audit_log` BEFORE returning URL; 503 on `AuditWriteFailure`.
  - Files: `backend/config/api_views.py` (add view).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_media_signed_url.py -v"` — all 11 scenarios pass.
  - Depends on: 3.1, 2.2, 1.2.
  - Estimated lines: ~120.
- [ ] **3.3** Wire `media-signed-url` route in `backend/config/api_urls.py` (path `media/signed-url/`).
  - Files: `backend/config/api_urls.py` (modify).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_media_signed_url.py -k route_resolution -v"`.
  - Depends on: 3.2.
  - Estimated lines: ~5.
- [ ] **3.4** GREEN: `write_audit_log` service in `backend/audit/services.py` (fail-closed). Implement to make 2.1 + 3.1 tests pass.
  - Files: `backend/audit/services.py` (modify).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest audit/tests/test_audit_log.py tests/test_media_signed_url.py -v"`.
  - Depends on: 3.2.
  - Estimated lines: ~25.

---

## Phase 4: Backfill Management Command

- [ ] **4.1** RED tests for `backfill_media` command: empty MEDIA_ROOT (sentinel written); full MEDIA_ROOT (1000 files uploaded with batched logging); resume after partial failure (skip uploaded via `head_object`); `--dry-run` (no upload, no sentinel); `--prefix` scope.
  - Files: `backend/tests/test_backfill_media.py` (create).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_backfill_media.py -v"` fails before implementation.
  - Depends on: none.
  - Estimated lines: ~80.
- [ ] **4.2** Create package directories `backend/config/management/__init__.py` and `backend/config/management/commands/__init__.py` (confirmed empty in current repo).
  - Files: `backend/config/management/__init__.py`, `backend/config/management/commands/__init__.py` (create).
  - Verify: `Test-Path "backend/config/management/commands"` (PowerShell).
  - Depends on: none.
  - Estimated lines: ~2.
- [ ] **4.3** Implement `backfill_media` command at `backend/config/management/commands/backfill_media.py` per pseudocode in design §8: walk MEDIA_ROOT, batch (default 100), `--resume` via `head_object`, write `_BACKFILL_COMPLETE` sentinel at bucket root on success.
  - Files: `backend/config/management/commands/backfill_media.py` (create).
  - Verify: `wsl -e bash -c "cd backend && python -m pytest tests/test_backfill_media.py -v"` — all 5 scenarios pass.
  - Depends on: 4.1, 4.2, 1.2.
  - Estimated lines: ~110.

---

## Phase 5: Frontend `useSignedUrl` Helper

- [ ] **5.1** Create `frontend/aesthetic-clinic/src/services/media.ts` with `useSignedUrl(path)` hook + internal `fetchSignedUrl(path)` per design §3.6. In-memory `Map<path, { url, expiresAt }>` cache; lifetime `min(ttl - 60, 300)` s; 30 s backoff on 503; no `localStorage`/`sessionStorage`. (Verified: `src/lib/` does not exist; `src/services/` does — final path is `src/services/media.ts`.)
  - Files: `frontend/aesthetic-clinic/src/services/media.ts` (create).
  - Verify: `Test-Path "frontend/aesthetic-clinic/src/services/media.ts"`; `grep -n "useSignedUrl" frontend/aesthetic-clinic/src/services/media.ts`.
  - Depends on: none.
  - Estimated lines: ~80.
- [ ] **5.2** Replace `<img src={...}>` and `<a href={...}>` callsites referencing bucket-relative media paths with `useSignedUrl(path)`. Apply MUST grep audit exhaustively — no literal `/media/...` strings exist in current `src/`, but backend serializers now return bucket-relative paths (`comprobantes_pagos/2026/10/x.pdf`); every component that renders these MUST use the hook. Apply grep: `grep -rE "src=\{|href=\{" frontend/aesthetic-clinic/src --include="*.tsx" --include="*.ts" -l` then update each callsite that renders a media path.
  - Files: `frontend/aesthetic-clinic/src/**/*.{ts,tsx}` (modify; grep-driven list).
  - Verify: `grep -rE "src=\"/media/|href=\"/media/" frontend/aesthetic-clinic/src --include="*.tsx" --include="*.ts"` returns zero matches; `grep -rn "useSignedUrl" frontend/aesthetic-clinic/src --include="*.tsx" -l | wc -l` ≥ number of original callsites.
  - Depends on: 5.1.
  - Estimated lines: ~30.
- [ ] **5.3** Add Playwright e2e: happy path (cliente logs in, opens own ficha PDF → image loads via signed URL); forbidden path (cliente attempts another cliente's PDF → 403 + broken image state); cache hit (same path re-rendered → no endpoint call).
  - Files: `frontend/aesthetic-clinic/tests/e2e/signed-url.spec.ts` (create).
  - Verify: `cd frontend/aesthetic-clinic && npm run test:e2e -- signed-url`.
  - Depends on: 5.2, 3.3.
  - Estimated lines: ~100.

---

## Phase 6: Cutover & Verification

- [ ] **6.1** Document `.env` env-var wiring in deployment (placeholder; owner-driven). Cron entry `0 2 * * * python manage.py backfill_media --resume` until sentinel exists. CloudWatch billing alarm at $30/mo. Add `sdd/proyecto-c/runbook-aws-s3-setup.md` ops follow-ups section.
  - Files: `sdd/proyecto-c/runbook-aws-s3-setup.md` (extend).
  - Verify: `grep -E "billing alarm|cron|backfill_media" sdd/proyecto-c/runbook-aws-s3-setup.md`.
  - Depends on: 0.1.
  - Estimated lines: ~20.
- [ ] **6.2** Manual smoke against real dev bucket (owner-driven, post-credentials). `aws s3 ls s3://proyecto-c-clinical-dev --profile test` succeeds; upload a test file via Django admin and confirm bucket write.
  - Files: (none; manual run).
  - Verify: `aws s3 ls s3://proyecto-c-clinical-dev/test-upload.txt --profile test` (owner runs).
  - Depends on: 0.1, 6.1, 4.3.
  - Estimated lines: 0.
- [ ] **6.3** Rollback drill in staging: set `STORAGE_PROVIDER=local`, redeploy, confirm `FileSystemStorage` serves all reads; signed-URL endpoint returns 503; frontend falls back to `/media/...` via feature flag in helper.
  - Files: (none; manual).
  - Verify: `wsl -e bash -c "cd backend && STORAGE_PROVIDER=local python -m pytest tests/test_storage_backends.py::test_local_fallback -v"`.
  - Depends on: 6.2, 1.4.
  - Estimated lines: 0.

---

## Open Follow-Ups

1. **Backend serializer `.url` migration** — design did not enumerate this; ~10 callsites in `api_views.py`, `client_api_views.py`, `ticket_views.py`. Captured in Task 1.5 as a verify-with-grep task. Apply MUST choose: relative paths + frontend hook (recommended), or `STORAGE_PROVIDER`-gated `.url`.
2. **`FichaClinica.operacion.cliente` accessor** — design §6 ambiguity. Apply verifies with `grep -n "class FichaClinica\|cliente" backend/clinical/models.py` in Task 3.2.
3. **`comprobantes_*` specialist-who-registered-payment FK** — design §6 ambiguity. Apply verifies with grep in Task 3.2.
4. **Async upload in lazy fallback** — Celery task vs thread; apply decides based on `backend/config/celery.py` presence in Task 1.2.
5. **90-day audit retention** — design §4 leaves retention to apply; archive/cron-delete strategy captured as future task in Phase 7 (post-apply), not blocking.
6. **Frontend helper path** — `src/lib/` does not exist, `src/services/` does. Final path `src/services/media.ts` per Task 5.1.

---

## Total Tasks

16 (T0.1–T6.3). Estimated total lines changed: **~730** (range 700–780 depending on serializer migration choice in 1.5). 400-line budget risk: **High**. Chained PRs recommended: **Yes** (orchestrator must surface to user before apply despite `single-pr` strategy).