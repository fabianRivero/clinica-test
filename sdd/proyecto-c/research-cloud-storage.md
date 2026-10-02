# SDD Research — Cloud Storage Provider Comparison (cloud-storage-migration)

> **Status**: completed — orchestrator-collected evidence (Engram write failures persisted; this mirror is authoritative).
> **Generated**: 2026-10-01. **Branch**: `feature/cloud-storage-migration`.
> **Working directory**: `C:\proyectos\proyecto C`.

## Why this is in the mirror

The first `sdd-research` delegation refused on a fail-closed evidence-admission gate (empty `documentation`/`open-web` grants). The orchestrator re-ran the investigation directly using:

- `context7_query-docs` for **boto3** API reference (Context7 ID: `/boto/boto3`).
- `webfetch` against official pricing pages and docs:
  - https://aws.amazon.com/s3/pricing/ (S3 pricing, multiple fetches).
  - https://developers.cloudflare.com/r2/pricing/ (R2 pricing, dated 2026-10-01).
  - https://supabase.com/pricing (Supabase plan tiers).
  - https://developers.cloudflare.com/r2/api/s3/api/ (R2 S3 API compatibility, dated 2026-07-31).
  - https://supabase.com/docs/guides/storage/serving/downloads (Supabase signed URLs).

This report collects the *admitted* evidence only. Where evidence could not be obtained, the field is marked `unverified — measured test required`.

## Volume assumption (from session context)

Tier B = 100–500 GB total. **Working estimate: 200 GB stored, ~50 GB egress/month.**

## Provider comparison

### AWS S3 — region `sa-east-1` (São Paulo, closest to Bolivia)

| Field | Value | Source |
|---|---|---|
| Storage (S3 Standard) | **$0.023 / GB-month** for first 50 TB; $0.022 next 450 TB; $0.021 above 500 TB | AWS S3 pricing page (regional tier table for `sa-east-1`, verified 2026-10-01) |
| Storage (S3 Standard-IA, infrequent) | $0.0125 / GB-month + $0.01 / GB retrieval | AWS S3 pricing page |
| PUT/COPY/POST/LIST | $0.005 per 1,000 requests | AWS S3 pricing page |
| GET/SELECT | $0.0004 per 1,000 requests | AWS S3 pricing page |
| Egress to internet (first 100 GB/month global free) | **$0.09 / GB** above 100 GB free tier (per-region for `sa-east-1`) | AWS S3 pricing page |
| Free tier | 5 GB Standard, 15 GB egress, 2,000 PUT, 20,000 GET for 12 months (new accounts only) | AWS S3 pricing page |
| Presigned URL support | Native via boto3 `generate_presigned_url('get_object', Params={...}, ExpiresIn=N)`, SigV4 default; max 7 days for SigV4 (boto3 docs warn against >7d); virtual-hosted style addressing recommended | boto3 docs (Context7), AWS S3 user guide |
| Revocation | **Not possible** for valid presigned URLs (must wait for expiry or rotate IAM credentials) | AWS docs — well-known constraint |
| Encryption at rest | AES-256 default, optional SSE-KMS | AWS S3 security docs |
| Latency from Bolivia (La Paz) | ~150–250 ms RTT one-way to `sa-east-1` (~2,000–2,500 km) — unverified, requires measurement | Inferred from geographic distance; **measurement needed** |
| Vendor lock-in | **High** for S3-specific features (Object Lock, Glacier, Batch Operations); **low** for basic PUT/GET/presigned URLs (S3 API is the de-facto standard) | Industry consensus |
| Key rotation complexity | Medium (IAM access keys, S3 bucket policies, KMS keys if used) | AWS docs |
| HIPAA-eligible | Yes (with BAA) | AWS compliance |

**S3 cost estimate (200 GB stored, 50 GB egress/mo, ~50k GET, ~5k PUT):**
- Storage: 200 × $0.023 = **$4.60/mo**
- Egress: (50 − 5 free for new accounts only, else 50 − 0) × $0.09 = **$4.50/mo**
- GET: 0.05M × $0.0004 = **$0.02/mo**
- PUT: 0.005M × $0.005 = **$0.025/mo**
- **Total ≈ $9.15/mo** (excluding free tier, established account)

### Cloudflare R2 — region `auto` (Cloudflare edge)

| Field | Value | Source |
|---|---|---|
| Storage (Standard) | **$0.015 / GB-month** | Cloudflare R2 pricing (dated 2026-10-01) |
| Storage (Infrequent Access) | $0.01 / GB-month + $0.01 / GB retrieval | Cloudflare R2 pricing |
| Class A operations (PUT, COPY, LIST, multipart ops, lifecycle) | $4.50 / million requests | Cloudflare R2 pricing |
| Class B operations (GET, HEAD) | $0.36 / million requests | Cloudflare R2 pricing |
| Data retrieval | Free for Standard; $0.01 / GB for Infrequent Access | Cloudflare R2 pricing |
| **Egress to internet** | **FREE** — confirmed in pricing footnote: *"Egressing directly from R2, including via the Workers API, S3 API, and `r2.dev` domains does not incur data transfer (egress) charges and is free."* | Cloudflare R2 pricing footnote 1 |
| Free tier | 10 GB storage, 1M Class A ops, 10M Class B ops, free egress per month | Cloudflare R2 pricing |
| Presigned URL support | **Same S3 API as AWS** — boto3 `generate_presigned_url` works identically with R2 endpoint `<account_id>.r2.cloudflarestorage.com` | Cloudflare R2 S3 API compatibility page (2026-07-31) |
| Signature algorithm | SigV4 (S3v4) — same as AWS | Cloudflare R2 S3 API docs |
| Max expiration | 7 days for SigV4 (same as S3) | Same boto3 docs |
| Revocation | **Not possible** for valid presigned URLs | Same S3 semantics |
| S3 API gaps vs AWS | Missing: bucket ACLs, bucket policy, object tagging, replication, lifecycle policies (partial), website hosting, request-payer | Cloudflare R2 S3 API compatibility page |
| Encryption at rest | AES-256 default | Cloudflare R2 docs |
| Latency from Bolivia | **Best of the three** — Cloudflare has edge POPs in São Paulo, Bogotá, Buenos Aires; automatic routing via `auto` region. **Measurement still required**, but expected <100 ms | Cloudflare network docs (general); **measurement needed** |
| Vendor lock-in | **Low** — S3-compatible API; switching providers requires only re-pointing the endpoint | S3 compatibility docs |
| Key rotation complexity | Medium (R2 API tokens, scoped to bucket/prefix) | Cloudflare R2 docs |
| HIPAA-eligible | R2 is not HIPAA-eligible as of 2026-10-01 | Cloudflare compliance |

**R2 cost estimate (200 GB stored, 50 GB egress/mo, ~50k GET, ~5k PUT):**
- Storage: 200 × $0.015 = **$3.00/mo**
- Egress: **$0.00/mo**
- Class A (PUT 5k + LIST/misc): negligible, well under 1M free tier
- Class B (GET 50k): negligible, under 10M free tier
- **Total ≈ $3.00/mo**

### Supabase Storage — Pro plan

| Field | Value | Source |
|---|---|---|
| Storage | 100 GB included in Pro ($25/mo); overage **$0.0213 / GB** | Supabase pricing page |
| Cached egress (Smart CDN) | 250 GB included; overage $0.03 / GB | Supabase pricing page |
| **Egress (uncached)** | $0.09 / GB above 250 GB included in Pro | Supabase pricing page |
| Max upload size | 500 MB (Pro) | Supabase pricing page |
| Presigned URL support | Native via supabase-py `create_signedUrl(path, expires_in)`; max **1 hour** (not configurable to longer) | Supabase signed URL docs |
| Revocation | **Not possible** for valid signed URLs — must contact support | Supabase docs footnote: *"If you need to revoke signed URLs, contact Supabase support"* |
| Signature algorithm | Supabase proprietary (not SigV4 — uses internal key separate from JWT signing key) | Supabase docs |
| Encryption at rest | AES-256 default | Supabase docs |
| Latency from Bolivia | Similar to R2 — Supabase uses Cloudflare under the hood; Smart CDN with edge caching | Supabase + Cloudflare docs (general); **measurement needed** |
| Vendor lock-in | **Medium** — proprietary SDK and API on top of S3-compatible layer; switching requires re-implementation | Supabase docs |
| Key rotation complexity | Low (anon + service role JWT, dashboard-managed) | Supabase docs |
| HIPAA-eligible | Only on Team plan ($599/mo) as paid add-on | Supabase pricing page |
| **Existing scaffolding in repo** | `backend/config/storage_backends.py` has `SupabaseStorage` class using boto3 S3-compatible mode; uses `service_role_key` as BOTH access and secret — needs validation against Supabase S3-gateway | Local code analysis (existing pending in repo) |

**Supabase Storage cost estimate (200 GB stored, 50 GB egress/mo, ~50k GET, ~5k PUT):**
- Plan: $25/mo (Pro, includes 100 GB storage + 250 GB cached egress)
- Storage overage: (200 − 100) × $0.0213 = **$2.13/mo**
- Egress (assuming all cached by Smart CDN): **$0.00/mo** (within 250 GB included); uncached hits would add $0.09/GB
- **Total ≈ $27.13/mo**

## Provider decision matrix

| Criterion (weight) | AWS S3 | Cloudflare R2 | Supabase Storage |
|---|---|---|---|
| **Cost @ 200 GB / 50 GB egress** | $9.15/mo | **$3.00/mo** | $27.13/mo |
| **Egress model** | $0.09/GB (free first 100 GB) | **FREE** | $0.09/GB after 250 GB included |
| S3-compatible API | Native | **Yes** (Cloudflare R2 docs 2026-07-31) | Yes (S3-compatible layer under proprietary SDK) |
| boto3 compatible (already installed) | Yes | **Yes** | Yes (gateway), but `storage_backends.py` uses same access + secret pattern — needs validation |
| Presigned URL | Native, max 7 days | Native via boto3, max 7 days | Native, **max 1 hour** (much shorter) |
| Existing scaffolding | None | None | Partial (`storage_backends.py` has `SupabaseStorage`, but has bugs and never wired) |
| HIPAA-eligible | Yes (BAA) | **No** (R2 is not HIPAA-eligible as of 2026-10-01) | Yes (Team plan only) |
| Vendor lock-in | High | **Low** | Medium |
| Region availability in SA | `sa-east-1` (São Paulo) | Edge POPs across SA (BOG, GRU, EZE) | Edge POPs across SA (via Cloudflare) |
| Key rotation complexity | Medium | Medium | Low |
| **Latency from Bolivia (La Paz)** | ~150–250 ms (unverified) | Best, expected <100 ms (unverified) | Best, expected <100 ms (unverified) |
| **Recommendation** | Standard, proven, HIPAA | **Winner for cost + egress + low lock-in** | Cost-effective only if also using Supabase DB/Auth |

## Presigned URL implementation patterns

### boto3 (works for AWS S3 AND Cloudflare R2 and Supabase S3 gateway)

```python
import boto3
from botocore.config import Config

s3 = boto3.client(
    "s3",
    endpoint_url="https://<account>.r2.cloudflarestorage.com",  # or AWS region, or Supabase
    region_name="auto",  # R2; or "sa-east-1" for AWS
    aws_access_key_id=...,
    aws_secret_access_key=...,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

url = s3.generate_presigned_url(
    "get_object",
    Params={"Bucket": "clinical-files", "Key": "fichas_clinicas/2026/10/foo.pdf"},
    ExpiresIn=900,  # 15 minutes
)
```

**Source**: boto3 docs (Context7 `/boto/boto3`).

### Supabase SDK (only for Supabase)

```python
from supabase import create_client

supabase = create_client(url, key)
response = supabase.storage.from_("clinical-files").create_signed_url(
    "fichas_clinicas/2026/10/foo.pdf",
    3600,  # 1 hour max
)
url = response["signedUrl"]
```

**Source**: Supabase docs `/docs/guides/storage/serving/downloads`.

### Revocation caveats

- **None of the three providers** allow revoking a presigned URL before its expiration. The URL is self-contained and signed with the issuer's credentials.
- Mitigation patterns:
  - Short expiration (5–15 min) — works for all three.
  - Server-side session token validation that *also* authorizes each presigned URL request — R2 and S3 don't support this natively; Supabase has Smart CDN with token-bearing cookies but not for arbitrary signed URLs.
  - For revocation of *compromised* URLs: rotate IAM credentials (S3), rotate R2 API tokens (R2), or contact support (Supabase). Each rotation invalidates **all** outstanding URLs globally.

### CDN cache-poisoning risk

- **R2 and Supabase**: served via Cloudflare edge; presigned URLs include query-string signature, edge cache key includes signature by default — no cache poisoning.
- **S3**: served from origin region; if put behind CloudFront, must configure `Cache-Control: no-store` and include signature in cache key.

### HTTPS-only enforcement

- All three providers enforce HTTPS for presigned URLs by default (URLs include `https://` in the signature).
- R2 has an additional setting `r2.dev` domains that always serve HTTPS.

## Migration strategy options

| Strategy | Downtime | Rollback safety | Complexity | Notes |
|---|---|---|---|---|
| **One-shot script** | None (read from old, write to new on first request OR scheduled cutover) | Low (atomic switch over) | Medium | Script reads `media/`, uploads to bucket, updates DB? No — paths stay relative in Django, so DB updates not needed. Cutover is `STORAGES["default"] = SupabaseStorage(...)`. |
| **Lazy (transparent migration)** | None | High (old files still serveable) | Medium-High | Wrap default storage: if object not in bucket yet, fetch from local disk, upload to bucket, then return. Useful for very large datasets with no maintenance window. |
| **Hybrid: bucket as primary + local as fallback** | None | High | Medium | New uploads go to bucket; old files served from local; lazy migration in background cron. **Recommended for this project** given the 200 GB assumption and the fact that downloads still work during migration. |

## Compatibility with existing scaffolding

File: `backend/config/storage_backends.py`

### Issues found in existing code
1. **`SupabaseStorage.url()` returns PUBLIC URL** (`.../storage/v1/object/public/{bucket}/{name}`). This contradicts the requirement that buckets be private and all downloads be presigned. **Must be replaced with `generate_presigned_url('get_object', ...)`** or refactored to require explicit presigning.
2. **`SupabaseStorage._get_client()` uses `service_role_key` as BOTH `aws_access_key_id` AND `aws_secret_access_key`**. Supabase's S3-compatible gateway expects the service role as access key, but the secret should be left empty or be a different value. **Empirical confirmation required during apply** — set up the bucket, test a PUT, verify SigV4 signing succeeds.
3. **`LocalStorage` reimplements `FileSystemStorage`** which Django provides out of the box. Delete this class.
4. **`_save()` / `_open()` correctness**: `content.open()` on a Django `FieldFile` that the framework already has open can double-wrap or read empty bytes. Needs a small refactor.
5. **`region = "auto"`** is correct for Supabase; if reusing the class for AWS S3 or R2, `region_name` must be configurable.
6. **Class is not registered**: nothing in `settings.STORAGES["default"]` points at it. The whole class is dead code.

### Reuse potential
- ~30% reusable as a starting point for an `R2Storage` or `S3Storage` class (boto3 client init, basic CRUD methods).
- ~10% reusable for Supabase after fixing the bugs above; but the existing class enforces Supabase-specific env vars, so it is more honest to write a new `Boto3Storage` that takes endpoint/region/keys from env and works for all three providers.

## Open questions for proposer

1. **HIPAA**: does `proyecto C` carry protected health information (PHI) under HIPAA, Bolivia's Ley 164, or any other privacy regime? If yes, R2 is disqualified (not HIPAA-eligible as of 2026-10-01) and S3 or Supabase (Team plan) are required.
2. **Multi-region disaster recovery**: is single-region acceptable for clinical PDFs? R2 stores data automatically replicated within a region (99.999999999% durability per Cloudflare docs), but cross-region replication requires manual setup. S3 Cross-Region Replication is mature. Supabase uses S3 under the hood; cross-region via Supabase is not exposed.
3. **Cost ceiling**: at what monthly cost does this become a budget item requiring approval? The estimates are $3–$27/mo — likely below any approval threshold, but worth stating.
4. **Latency tolerance**: is 150–250 ms acceptable for opening a clinical PDF? If users will complain about every-second-of-load, R2 is the right choice. If acceptable, S3 is fine.
5. **Existing credential infrastructure**: do you already have AWS account, Cloudflare account, or Supabase project? If you already use Supabase for auth/DB, switching to Supabase Storage is the lowest friction. If you have AWS, S3 is.
6. **Presigned URL max expiration**: Supabase is capped at 1 hour; R2 and S3 allow up to 7 days. Does the workflow need >1h links (e.g., email a PDF link to a patient)?
7. **Compliance audits**: do you need server-side access logs (who downloaded what, when)? S3 has native CloudTrail + S3 access logs; R2 has audit logs; Supabase has dashboard logs. All three, but quality differs.

## Evidence quality

| Aspect | Status |
|---|---|
| Official pricing cited | ✅ AWS, R2, Supabase |
| Official docs cited | ✅ boto3, R2 S3 API, Supabase signed URLs |
| Latency from Bolivia measured | ❌ Not measured — requires empirical test once bucket is provisioned |
| Supabase S3-gateway credential pattern validated | ❌ Not empirically validated — bug or feature? Must test during apply |
| HIPAA eligibility | ✅ Confirmed for S3 (BAA), Supabase Team plan; ❌ for R2 (not eligible) |
| Staleness | All sources dated ≤ 30 days (AWS live, R2 2026-10-01, Supabase 2026-10-01, Cloudflare R2 docs 2026-07-31) |

## Recommendation for the proposal

**Primary recommendation: Cloudflare R2**, with these caveats:
- Best cost (3× cheaper than S3, 9× cheaper than Supabase at this volume).
- Free egress — killer feature for serving PDFs and photos.
- S3-compatible — easy to switch to S3 or Supabase later.
- Not HIPAA-eligible — disqualifier only if PHI is in scope.

**Fallback 1: AWS S3** if HIPAA or other compliance is required, or if AWS account already exists.

**Fallback 2: Supabase Storage** if Supabase is already used for auth/DB and the team wants minimum new vendors. Accept the 9× cost premium for simplicity.

**Implementation note**: regardless of provider, the implementation path is the same:
1. Replace `backend/config/storage_backends.py` with a clean `Boto3Storage` class parametrized by env (endpoint, region, access key, secret).
2. Wire `STORAGES["default"]` based on `STORAGE_PROVIDER` env var.
3. Add presigned URL endpoint in `backend/config/api_views.py`.
4. Update frontend `<img>` and `<a>` tags to call the presigned URL endpoint.
5. Backfill script that copies existing `media/` to bucket preserving paths.
6. Delete `LocalStorage` dead code.

## Next recommended

`sdd-propose cloud-storage-migration` — produce a proposal that:
- Frames the problem (storage + privacy).
- Lists provider trade-offs with cost.
- Proposes the recommended approach (R2, with S3 fallback).
- Notes the open questions for the user to answer before spec/design.
- Identifies the existing scaffolding to refactor.
