# Cloud Storage Migration — Proposal

## Intent

Two defects must be resolved before load compounds:

1. **Local storage exhaustion** — `MEDIA_ROOT = BASE_DIR / "media"` ties user uploads (images, clinical PDFs) to app-server disk.
2. **Unauthenticated media access** — `MEDIA_URL` served by `static()` only in DEBUG; in production clinical PDFs are reachable without auth.

Move user uploads to an S3-compatible bucket behind presigned URLs + an authenticated endpoint that mints them. Provider is the open question (Confirmation Gates).

## Evidence

Provider comparison (AWS S3, Cloudflare R2, Supabase Storage) at `sdd/proyecto-c/research-cloud-storage.md` — cost, S3-API compatibility, HIPAA, latency, lock-in.

## Recommended approach

- **Primary:** Cloudflare R2 — private bucket, presigned URLs 5–15 min.
- **Fallback:** AWS S3 `sa-east-1` if HIPAA-eligibility required.
- **Disqualified:** Supabase Storage (9× cost, ≤1h URL cap) unless already used for auth/DB.

## Why this approach

R2 is ~3× cheaper than S3 and ~9× cheaper than Supabase at the working volume (200 GB / 50 GB egress). Egress is free — dominant cost driver for PDFs/photos. S3-compatible API means switching to S3 = change `endpoint_url` only. boto3 is already installed.

## Scope

### In Scope
- Refactor `backend/config/storage_backends.py` → clean `Boto3Storage` parametrized by env.
- Wire `STORAGES["default"]` via `STORAGE_PROVIDER` env var.
- New `GET /api/media/signed-url/` endpoint with permission check + presigned URL.
- Management command: backfill `media/` to bucket, preserve relative paths.
- Frontend: replace `<img src={comprobante_url}>` with signed-URL proxy (≤15 min cache).
- Delete dead `LocalStorage` class.
- Backend pytest (WSL) with `boto3.client.generate_presigned_url` mocked.

### Out of Scope
- Catalog images already public (separate change).
- `biometric.FingerprintAgent` capture (already isolated).
- CDN beyond R2/Cloudflare native edge.

## PR Strategy (updated 2026-10-01 after tasks forecast)

Original cache: `single-pr`. **Overridden** by user after tasks forecast showed ~730 lines (high risk of exceeding 400-line budget).

**Final strategy: chained PRs, stacked-to-main, 4 slices.**

| Slice | PR # | Scope | Estimated lines | Target branch |
|-------|------|-------|-----------------|---------------|
| 1 — Storage foundation | PR #1 | `Boto3Storage` + `LazyLocalFallbackStorage` rewrite, STORAGES wiring, backend pytest | ~180 | `main` |
| 2 — Audit + endpoint | PR #2 | `audit_log` model + migration, signed-url view, per-resource auth, backend pytest | ~220 | `main` |
| 3 — Backfill + frontend | PR #3 | `backfill_media` command, `useSignedUrl` hook, frontend migration | ~180 | `main` |
| 4 — Rollout | PR #4 | Owner runbook, env wiring, smoke test, rollback drill | ~90 | `main` |

Each slice merges independently to `main`. If slice N fails, revert that PR; slices 1..N-1 stay in production.

## Capabilities

> Contract with `sdd-spec`. Each new capability → full spec at `openspec/changes/cloud-storage-migration/specs/<name>/spec.md`.

### New Capabilities
- `media-storage`: S3-compatible object storage, private bucket, presigned URL issuance, lazy/hybrid migration from local `media/`.
- `media-signed-url-endpoint`: authenticated Django endpoint minting short-lived presigned URLs for patient/clinical files.

### Modified Capabilities
- None. No existing spec governs the current local media pipeline.

## Approach

Hybrid migration (research recommendation): new uploads write to bucket; legacy files served from local with lazy upload-on-first-read; background cron completes backfill; local `media/` retained 30 days post-cutover, then deleted. Frontend stays live through cutover because URLs come from the new endpoint.

## Affected Areas

- `backend/config/storage_backends.py` — rewritten (replace buggy `SupabaseStorage` + dead `LocalStorage` with `Boto3Storage`).
- `backend/config/settings.py` — `STORAGES["default"]` driven by `STORAGE_PROVIDER`.
- `backend/config/api_views.py` — new `GET /api/media/signed-url/` w/ `IsAuthenticated` + object ACL.
- `backend/config/management/commands/backfill_media.py` — new; `media/` → bucket, batched, resumable.
- `frontend/**` consuming `/media/...` — modified; helper + grep audit, cache ≤15 min.

## Risks

| ID | Risk | Likelihood | Mitigation |
|----|------|------------|------------|
| C1 | Bugs in `storage_backends.py` (public `url()`, `service_role_key` reused) make refactor risky | High | Rewrite the class; pytest coverage. |
| C2 | Backfill of ~200 GB may saturate network / take hours | Medium | Maintenance window + batched resumable script. |
| C3 | Frontend hard-codes `/media/...` in many places | Medium | Single helper + grep audit before sign-off. |
| W1 | R2 is not HIPAA-eligible | Medium | S3 fallback = one env var. |
| W2 | Engram writes failing; mirror authoritative | Medium | Mirror in `sdd/proyecto-c/` retained. |
| W3 | Backend pytest is WSL-only | Low | Tests use WSL; frontend e2e unaffected. |

## Rollback Plan

1. Set `STORAGE_PROVIDER=local` → `STORAGES["default"]` falls back to `FileSystemStorage`.
2. Frontend falls back to `/media/...` when signed-URL endpoint returns 503 (feature flag).
3. Local `media/` retained 30 days post-cutover before deletion.
4. No DB migration required (paths stay relative in Django `FileField`).

## Dependencies

- boto3 (already installed).
- Provider account + bucket credentials — see Gate 4.
- WSL for backend pytest (per `openspec/config.yaml`).

## Success Criteria

- [ ] New uploads land in the bucket, not local disk.
- [ ] Clinical PDFs reachable only via signed-URL endpoint after auth check.
- [ ] Backfill completes 200 GB within maintenance window, resumable on failure.
- [ ] Backend pytest passes on WSL with boto3 mocked.
- [ ] Frontend e2e (Playwright) passes on Windows.
- [ ] Monthly cost within budget ceiling from Gate 7.

## Confirmation Gates (user answered 2026-10-01)

| # | Gate | Answer | Decision |
|---|------|--------|----------|
| 1 | HIPAA / PHI scope | **Yes** — clinical PDFs + patient data → regulated | **AWS S3 (HIPAA-eligible with BAA). R2 disqualified.** |
| 2 | Multi-region DR | Unknown → default single-region; scale to multi-region only if dueño requests | Single-region `sa-east-1` for v1; document upgrade path. |
| 3 | Latency tolerance | Unknown → default S3 direct; add CloudFront if dueño reports slowness | S3 direct for v1; CloudFront is an optional v1.1 upgrade. |
| 4 | Existing credentials | Dueño does NOT have AWS/Cloudflare/Supabase credentials yet | **Blocker: setup task required.** Apply phase Task #1 = "Owner provisions AWS account, creates S3 bucket, creates IAM user with bucket-scoped policy, shares credentials with team via 1Password/secret manager". Until then, develop with mocked boto3. |
| 5 | Presigned URL max expiration | Unknown → default 15 min, configurable per-resource | Configurable via `MEDIA_SIGNED_URL_TTL_SECONDS` env var; default 900s. Document 7-day SigV4 ceiling. |
| 6 | Compliance audit logs | **Yes** | Backend logs each presigned URL generation (user, resource, timestamp, IP, expires_at). S3 server access logs enabled on bucket as defense-in-depth. Both retained 90 days. |
| 7 | Budget ceiling | **Scenario A — low traffic**: 200 GB storage + 100 GB egress ≈ ~$5/mo storage, $0 egress (under 100 GB free tier) = **~$5/mo** | Plus **S3 Versioning ON** = +$5/mo → **~$10/mo total**. CloudWatch billing alarm at $30/mo. |

## Budget Scenarios (for owner review)

Working assumption: 200 GB stored, downloads vary by scenario. Region `sa-east-1`.

| Scenario | Storage | Egress/month | Estimated monthly cost (USD) | Use case |
|----------|---------|--------------|------------------------------|----------|
| **A — Low traffic** | 200 GB × $0.023 = $4.60 | 100 GB (100 GB free) → $0.00 | **~$5/mo** | Internal-only downloads; few staff users |
| **B — Medium traffic** | 200 GB × $0.023 = $4.60 | 500 GB × $0.09 = $45.00 | **~$50/mo** | Patients + staff downloading receipts/PDFs |
| **C — High traffic** | 200 GB × $0.023 = $4.60 | 1 TB × $0.09 = $90.00 | **~$95/mo** | Viral content / many external downloads |

**Optional add-ons (orthogonal to scenario):**
- **CloudFront CDN in front**: +$0.085/GB egress (vs $0.09 direct) — but lower latency (~30-50 ms RTT from La Paz). Adds ~$5-10/mo at scenario B.
- **S3 Intelligent-Tiering**: free tier movement; ~20-30% storage savings after 6 months of stable dataset.
- **S3 Versioning**: +$0.023/GB-month for previous versions — turn ON for clinical PDFs (defense against accidental deletion), budget +$5/mo at 200 GB.

**Recommendation to owner**: budget for **Scenario B + Versioning ON + no CloudFront** initially ≈ **$60/mo**. Set up CloudWatch billing alarm at $80/mo as safety net.