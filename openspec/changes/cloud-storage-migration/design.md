# Design: Cloud Storage Migration

## 1. Context

This change moves user-uploaded files (clinical PDFs, operation photos, payment receipts, ticket attachments) from the Django app-server's `MEDIA_ROOT` to a private AWS S3 bucket in `sa-east-1`, accessed only through short-lived presigned URLs minted by an authenticated Django endpoint. It solves two defects: local-disk exhaustion (MEDIA_ROOT on app-server) and unauthenticated media access (production clinical PDFs reachable without auth because `static(MEDIA_URL, …)` at `backend/config/urls.py:30` only fires in DEBUG). It does **NOT** solve: CDN strategy (CloudFront is an optional v1.1 upgrade per Gate 3), catalog-image hosting (separate change), or `biometric.FingerprintAgent` capture (already isolated, per proposal §Out of Scope).

## 2. Architecture Overview

```
                         WRITES                                  READS
   Django model.save()                       Browser <img>/<a>
        │                                          │
        ▼                                          ▼
   Boto3Storage._save() ──► boto3.client('s3')     GET /api/media/signed-url/?path=…
        │                       │                   │   (JWT/cookie auth, audit fail-closed)
        ▼                       ▼                   ▼
   AWS S3 bucket ──────► sa-east-1 ◄─── boto3.generate_presigned_url()
   proactiva                              │
        │                                ▼
        │                          15-min HTTPS URL
        ▼
   LazyLocalFallbackStorage ◄─── reads also consult MEDIA_ROOT
        │
        ▼
   S3 server access logs ─► CloudWatch metrics + billing alarm
   audit_log table (Postgres) ◄── every successful signed URL generation
```

## 3. Component Inventory

### 3.1 `Boto3Storage` (Django storage backend)

- **Purpose**: Primary S3-backed `django.core.files.storage.Storage` subclass.
- **File**: `backend/config/storage_backends.py` (rewritten; replaces `SupabaseStorage` lines 12–78 and removes `LocalStorage` lines 80–111).
- **Key responsibilities**: env-driven boto3 client init; CRUD methods; reject public URL escape hatch (raise `NotImplementedError` on `url()` per media-storage spec).
- **Key interface** (signatures only):
  - `class Boto3Storage(Storage)`
  - `def _save(self, name: str, content: "django.core.files.base.File") -> str`
  - `def _open(self, name: str, mode: str = "rb") -> "ContentFile"`
  - `def delete(self, name: str) -> None`
  - `def exists(self, name: str) -> bool`
  - `def size(self, name: str) -> int`
  - `def modification_time(self, name: str) -> "datetime"`
  - `def url(self, name: str) -> str  # raises NotImplementedError; minting goes through signed-url endpoint only`
- **Dependencies**: env vars (§7); used by `LazyLocalFallbackStorage` and configured by `STORAGES["default"]` in `settings.py:192`.

### 3.2 `LazyLocalFallbackStorage` (Django storage backend)

- **Purpose**: Wraps `Boto3Storage` and falls back to `MEDIA_ROOT` for legacy keys not yet in the bucket during the 30-day cutover.
- **File**: `backend/config/storage_backends.py` (new class in the same module).
- **Key responsibilities**: on `exists()`/`_open()`, check bucket via `head_object`; on miss, consult `MEDIA_ROOT`; on local-served, enqueue async upload (Celery or in-process thread per media-storage spec).
- **Key interface**:
  - `class LazyLocalFallbackStorage(Boto3Storage)`
  - overrides `_open`, `exists`; delegates `_save`/`delete`/`size`/`modification_time` to inner `Boto3Storage`.
- **Dependencies**: `Boto3Storage`; `MEDIA_ROOT`; Celery or thread-pool (apply phase selects based on `celery.py` presence at `backend/config/celery.py`); configured by `STORAGE_PROVIDER=s3` during transition, swapped to `Boto3Storage` directly after sentinel exists.

### 3.3 `backfill_media` management command

- **Purpose**: One-shot upload of `MEDIA_ROOT` → bucket keys, batched, resumable, idempotent.
- **File**: `backend/config/management/commands/backfill_media.py` (apply creates the package — confirmed no `management/commands` dir currently).
- **Key responsibilities**: walk `MEDIA_ROOT`; upload batched (default 100); skip keys confirmed present via `head_object`; emit progress every batch; write zero-byte `_BACKFILL_COMPLETE` sentinel at bucket root.
- **Key interface**:
  - `class Command(BaseCommand)`
  - `def add_arguments(self, parser)`
  - `def handle(self, *args, **options)`
  - Args: `--batch-size=100`, `--dry-run`, `--prefix=…`, `--resume`, `--verify`.
- **Dependencies**: `Boto3Storage` (or boto3 client directly for sentinel); logs to stdout; cron schedule (operator-managed).

### 3.4 `GET /api/media/signed-url/` endpoint

- **Purpose**: Authenticated presigned URL minting with per-resource authorization and fail-closed audit.
- **File**: `backend/config/api_views.py` (new function-based view, following the function-view pattern of `api_views.py`); mounted in `backend/config/api_urls.py`.
- **Key responsibilities**: `IsAuthenticated`; path sanitization (reject `..`, leading `/`, `\`, paths outside allowlist); authorization per prefix table (§6); call `generate_presigned_url`; write audit row; return JSON.
- **Key interface** (per media-signed-url-endpoint spec):
  - `def media_signed_url(request) -> JsonResponse`
  - Request: `GET /api/media/signed-url/?path=<relative_path>`
  - Response: `200 { url, expires_at, ttl_seconds } | 400 | 401 | 403 | 503`.
- **Dependencies**: boto3 client (env-driven); `AuditLog` model + writer (§3.5); DRF auth (existing JWT/cookie in repo).

### 3.5 `AuditLog` model + writer service

- **Purpose**: Persist every successful signed URL generation (HIPAA audit trail, Gate 6).
- **Files**: `backend/audit/models.py` (new app `audit` — apply creates) and `backend/audit/services.py` (function `write_audit_log(...)`).
- **Key responsibilities**: write row inside transaction; raise on DB failure (caller converts to 503); queryable by `user_id`, `resource_path`, `timestamp`.
- **Key interface**:
  - `class AuditLog(models.Model)` — fields §4.
  - `def write_audit_log(*, user_id, resource_path, resource_type, action, authorization_rule, expires_at, client_ip, user_agent) -> None  # raises AuditWriteFailure`
- **Dependencies**: Postgres (existing `DATABASES`); no other models.

### 3.6 Frontend `useSignedUrl(path)` helper (React hook)

- **Purpose**: Replace every `<img src="/media/...">` / `<a href="/media/...">` with a hook that mints and caches short-lived signed URLs.
- **File**: `frontend/aesthetic-clinic/src/services/media.ts` (proposed; closest match to existing `src/services/` directory — `src/lib/media.ts` from the prompt **does not exist**, verify with grep in apply).
- **Key responsibilities**: in-memory cache keyed by `resource_path`; lifetime `min(ttl - 60s, 300s)`; 30 s backoff on 503 (per media-signed-url-endpoint spec); no `localStorage`/`sessionStorage`.
- **Key interface** (signatures only):
  - `export function useSignedUrl(path: string): { url: string | null; loading: boolean; error: Error | null }`
  - `export async function fetchSignedUrl(path: string): Promise<SignedUrl>`  (internal)
  - `interface SignedUrl { url: string; expires_at: string; ttl_seconds: number }`
- **Dependencies**: existing auth helper (cookies/JWT) — verify exact module in apply.

### 3.7 Owner setup runbook

- **Purpose**: Owner provisions AWS resources before apply can do live tests (Gate 4 blocker).
- **File**: `sdd/proyecto-c/runbook-aws-s3-setup.md` (proposed; apply creates or links from existing repo doc).
- **Key responsibilities**: AWS account, BAA, bucket, IAM, credentials, verification step.
- **Dependencies**: AWS account; 1Password vault.

## 4. Data Model

New `audit_log` table — model class + migration outline (apply creates migration; no SQL here):

```python
class AuditLog(models.Model):
    id            = models.BigAutoField(primary_key=True)
    user_id       = models.IntegerField(db_index=True)
    user_role     = models.CharField(max_length=80)
    resource_path = models.CharField(max_length=512, db_index=True)
    resource_type = models.CharField(max_length=120)        # e.g. "clinical.FichaClinica.documento_escaneado_pdf"
    action        = models.CharField(max_length=40)         # e.g. "signed_url_get"
    client_ip     = models.GenericIPAddressField(null=True)
    user_agent    = models.CharField(max_length=512, blank=True)
    expires_at    = models.DateTimeField()
    created_at    = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["resource_path", "created_at"]),
        ]
```

Indexes target the spec's audit query patterns (`user_id`, `resource_path`, `timestamp`); `created_at` is `auto_now_add` so range queries work. Retention 90 days (Gate 6) — apply phase decides on archive/cron-delete, not in this design.

**No other models change.** `FileField.name` keeps relative paths (spec §media-storage: "no migration required"). Existing `upload_to` strings (`fichas_clinicas/%Y/%m/`, `tickets_adjuntos/%Y/%m/`, `citas/...`, `fotos_operacion/...`, `comprobantes_pagos/%Y/%m/`, `comprobantes_citas/%Y/%m/`) remain the bucket-key roots.

## 5. API Contract

```
GET /api/media/signed-url/?path=<relative_path>
Authorization: <existing JWT or session cookie>

→ 200 OK
  {
    "url":          "https://proyecto-c-clinical-prod.s3.sa-east-1.amazonaws.com/...?X-Amz-Signature=...",
    "expires_at":   "2026-10-01T15:15:00Z",
    "ttl_seconds":  900
  }

→ 400 Bad Request       (malformed path; path outside allowlist; SIGV4 TTL > 604800 cap)
→ 401 Unauthorized      (no/invalid auth — no audit row written)
→ 403 Forbidden         (auth ok, resource not allowed for this user — no audit row written)
→ 503 Service Unavailable  (audit log write failed — fail-closed; URL not issued)
```

Response field names match media-signed-url-endpoint spec §Signed URL Endpoint. `expires_at` is ISO-8601 UTC.

## 6. Authorization Rules

The role model is `accounts.Usuario.rol` → FK to `accounts.Rol` with values `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE` (per `accounts/models.py:83-104` and tests). There is **no `ESPECIALISTA` role string** — `staff.Especialista` is a separate model with `OneToOneField` to `Usuario` (`staff/models.py:19`), so the design uses `user.especialista` as a reverse accessor. The spec's `especialista_assigned` rule means `user.especialista` resolved against the `Operacion.especialista` FK.

| Resource prefix | Authorized | Reference |
|---|---|---|
| `fichas_clinicas/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` of ficha's `operacion.sucursal` OR cliente with `user.especialista is None` AND `user.cliente.id == ficha.cliente.id` (verify) | `Usuario.rol` (`accounts/models.py:26-32, 83-104`); ficha → operacion → sucursal per `clinical/models.py:110-114`; cliente FK verify with grep in apply |
| `citas/.../antes/`, `citas/.../despues/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` of `operacion.sucursal` OR `operacion.especialista.usuario == request.user` | `Usuario.rol`; `Operacion.especialista` is FK to `staff.Especialista` → reverse `.usuario` per `staff/models.py:19` |
| `fotos_operacion/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` of `operacion.sucursal` OR `operacion.especialista.usuario == request.user` | Same as above; `OperacionFoto.operacion` per `operations/models.py:644-649` |
| `comprobantes_pagos/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` of cliente's sucursal OR cliente OR specialist who registered payment | `billing/models.py:135-139`; specialist verify with grep in apply |
| `comprobantes_citas/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` of cliente's sucursal OR cliente OR specialist who registered payment | `billing/models.py:311-315`; specialist verify with grep in apply |
| `tickets_adjuntos/` | `ADMIN_PRINCIPAL` OR `ADMIN_SUCURSAL` OR `Ticket.creado_por == request.user` OR `Ticket.especialista.usuario == request.user` | `notifications/models.py:61-72` (`creado_por`, `especialista` FK) |

Unmatched rule → 403. Path → resolve a no DB row → deny unless `ADMIN_PRINCIPAL` (per spec §Per-Resource Authorization). Audit row records which rule matched.

**Ambiguity flag**: `cliente_self` access for `fichas_clinicas/` — the spec says `user.cliente.id == ficha.cliente.id`, but `FichaClinica.operacion.cliente` accessor needs grep verification in apply. Same for specialist-who-registered-payment on `comprobantes_*`.

## 7. Storage Backend Design

### `Boto3Storage` signatures

```python
class Boto3Storage(Storage):
    def __init__(self) -> None: ...
    def _save(self, name: str, content) -> str: ...
    def _open(self, name: str, mode: str = "rb"): ...
    def delete(self, name: str) -> None: ...
    def exists(self, name: str) -> bool: ...
    def size(self, name: str) -> int: ...
    def modification_time(self, name: str): ...
    def url(self, name: str) -> str:  # raises NotImplementedError
```

### `_save` correctness fix (existing bug at `storage_backends.py:41-46`)

The current code does `content.open()` followed by `content.read()` and `content.close()`. Django's `FileField` save path passes a `FieldFile` whose underlying file is **already open**; calling `.open()` again raises `ValueError: I/O operation on closed file` or double-wraps and returns empty bytes. The fix: do not call `.open()` at all; instead, **if `content` has a real underlying `.file` attribute that is open, read from it; otherwise read via `content.read()`** which handles both `FieldFile` and `UploadedFile`. Pseudocode:

```python
def _save(self, name, content):
    data = content.file.read() if getattr(content, "file", None) else content.read()
    client.put_object(Bucket=BUCKET, Key=name, Body=data)
    return name
```

Apply phase writes the RED test that captures the double-open behavior on the existing code, then implements the fix in `Boto3Storage`.

### `LazyLocalFallbackStorage` wrapping

`LazyLocalFallbackStorage(Boto3Storage)` overrides `_open` and `exists`. On `exists(key)`: try `super().exists(key)` (which calls `head_object`); on `False`, return `(MEDIA_ROOT / key).exists()`. On `_open(key)`: try bucket; on `ClientError`/`NoSuchKey`, open local file and enqueue async upload (thread or Celery task). Delete always hits the bucket only.

### Env vars

| Variable | Default | Purpose |
|---|---|---|
| `STORAGE_PROVIDER` | `local` | `local` → `FileSystemStorage`; `s3` → `LazyLocalFallbackStorage` during cutover, `Boto3Storage` after sentinel. Removes legacy `supabase` value (apply removes line 203 comment). |
| `AWS_ACCESS_KEY_ID` | — | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | — | IAM secret |
| `AWS_STORAGE_BUCKET_NAME` | — | Bucket name (e.g. `proyecto-c-clinical-prod`) |
| `AWS_S3_REGION_NAME` | `sa-east-1` | Per proposal Gate 2 |
| `AWS_S3_ENDPOINT_URL` | (unset) | Optional non-AWS S3-compatible endpoint (e.g. R2); unset = AWS |
| `MEDIA_SIGNED_URL_TTL_SECONDS` | `900` | Default TTL; cap 604800 (SigV4 max, research §"Presigned URL support") |
| `MEDIA_LOCAL_FALLBACK_ENABLED` | `true` | During transition; set `false` after 30-day cutover to swap to `Boto3Storage` directly |

## 8. Backfill Command Design

### CLI surface

```
python manage.py backfill_media [--batch-size=100] [--dry-run] [--prefix=...] [--resume] [--verify]
```

### Pseudocode outline

```python
# Pseudocode — NOT real code. Apply phase implements.
def handle(*, batch_size, dry_run, prefix, resume, verify):
    files = walk(MEDIA_ROOT, prefix=prefix)              # generator of file paths
    buffer = []
    for path in files:
        key = relative_key(path)                          # strip MEDIA_ROOT, keep upload_to path
        if resume and head_object(BUCKET, key).exists():  # skip uploaded
            continue
        buffer.append((key, path))
        if len(buffer) >= batch_size:
            upload_batch(buffer, dry_run)
            buffer.clear()
    if buffer: upload_batch(buffer, dry_run)
    if not dry_run: put_object(BUCKET, "_BACKFILL_COMPLETE", b"")
    log.info("backfill complete: uploaded=%d skipped=%d", ...)
```

### Resumability via `head_object`

`--resume` calls `head_object(Bucket=BUCKET, Key=key)` for each candidate; if the call succeeds, the file is already in the bucket and we skip. `ClientError`/`NoSuchKey` → upload. This makes the command safely re-runnable after a partial failure (media-storage spec §Resumable re-run).

### Sentinel

`_BACKFILL_COMPLETE` is a zero-byte object at the bucket root. Presence signals a clean cutover baseline. Operators swap `LazyLocalFallbackStorage` → `Boto3Storage` once sentinel exists AND all `MEDIA_ROOT` files are confirmed uploaded (per media-storage spec §Lazy Local Fallback).

### Schedule

Nightly cron after cutover until sentinel exists: `0 2 * * * python manage.py backfill_media --resume`. Apply phase writes the cron entry; operator confirms.

## 9. Security

### Path sanitization regex / rules

- Reject if any segment equals `..` or `.`.
- Reject if starts with `/` or contains `\`.
- Reject if, after stripping the bucket root, the path is not in allowlist `{fichas_clinicas/, tickets_adjuntos/, citas/, fotos_operacion/, comprobantes_pagos/, comprobantes_citas/}`.
- Decode percent-escapes **before** checks (avoid `%2e%2e` bypass).
- Length cap 512 chars (matches `AuditLog.resource_path`).

### HTTPS enforcement

`boto3.client.generate_presigned_url` returns `https://` URLs by default. Endpoint URL in `boto3` client must be `https://`; reject `http://` at startup.

### IAM policy JSON outline (bucket-scoped)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BucketList",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::proyecto-c-clinical-<env>",
      "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
    },
    {
      "Sid": "BucketObjectRW",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::proyecto-c-clinical-<env>/*",
      "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
    },
    {
      "Sid": "DenyNonSaEast1",
      "Effect": "Deny",
      "Action": "s3:*",
      "Resource": "*",
      "Condition": { "StringNotEquals": { "aws:RequestedRegion": "sa-east-1" } }
    }
  ]
}
```

### Audit log fail-closed

`write_audit_log` raises `AuditWriteFailure` on any DB error. Endpoint catches → returns 503 (media-signed-url-endpoint spec §Audit Log).

### No public-URL escape hatch

`Boto3Storage.url()` raises `NotImplementedError`; presigned URLs are minted only through the endpoint which enforces auth + audit (media-storage spec §Scenario: No public URL is ever returned).

## 10. Observability

- **Structured log per signed URL generation** (JSON): `event=signed_url_issued`, `user_id`, `resource_path`, `resource_type`, `authorization_rule`, `expires_at`, `client_ip`, `user_agent`, `ttl_seconds`, `request_id`.
- **S3 server access logs**: bucket-level delivery to dedicated logs bucket (`proyecto-c-clinical-<env>-logs`) — fields `BucketOwner`, `Bucket`, `Time`, `RemoteIP`, `Requester`, `RequestID`, `Operation`, `Key`, `RequestURI`, `HTTPStatus`, `ErrorCode`, `BytesSent`, `ObjectSize`, `TotalTime`, `TurnAroundTime`, `Referer`, `UserAgent`, `VersionId` (research §AWS S3 access logs).
- **CloudWatch metrics**: `SignedUrlGeneration` (count, namespace `proyecto-c/media`) incremented on every successful mint; `SignedUrlGenerationError` (count) on 401/403/503.
- **Billing alarm at $30/mo** (per Gate 7): CloudWatch billing alarm on `EstimatedCharges` for AWS account, threshold 30 USD.

## 11. Frontend Integration Plan

- **Helper path proposal**: `frontend/aesthetic-clinic/src/services/media.ts` (matches existing `src/services/` directory; `src/lib/media.ts` from the prompt **does not exist** — apply verifies final path with grep).
- **Hook signature** (signatures only):
  ```typescript
  export function useSignedUrl(path: string): { url: string | null; loading: boolean; error: Error | null }
  ```
- **Cache contract**: in-memory `Map<path, { url, expiresAt }>` keyed by bucket-relative path; lifetime `min(ttl - 60, 300)` seconds (media-signed-url-endpoint spec §Frontend Cache Contract); 30 s backoff on 503; no `localStorage`/`sessionStorage`.
- **Component patterns to migrate** (examples; apply grep audits exhaustively):
  - `<img src={comprobante_url}>` patterns in client portal pages — verify with grep.
  - `<a href={documento_url}>` for clinical PDFs — verify with grep.
  - Operation-gallery `<img>` and ticket-attachment `<a>` patterns — verify with grep.
  - Apply phase enumerates all matches and replaces each with `useSignedUrl(path)`.

## 12. Owner Setup Runbook

Markdown checklist the owner follows before apply can do live tests:

1. Create AWS account (https://aws.amazon.com/).
2. Sign the AWS Business Associate Addendum (BAA) for HIPAA — https://aws.amazon.com/compliance/hipaa-eligible-services-reference/ (Gate 1, Gate 4).
3. Create S3 bucket `proyecto-c-clinical-<env>` in `sa-east-1` (replace `<env>` with `dev` / `staging` / `prod`).
4. Enable **all four** public-access-block flags on the bucket (BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets).
5. Enable **Versioning** on the bucket (Gate 7).
6. Enable **Server Access Logging** to a dedicated logs bucket `proyecto-c-clinical-<env>-logs`.
7. Create IAM user `proyecto-c-app-<env>` with programmatic access only.
8. Attach the inline policy from §9 to the user.
9. Store access key + secret in 1Password vault **"Propietario del Sistema / AWS"**.
10. Verify with `aws s3 ls s3://proyecto-c-clinical-<env> --profile proyecto-c-test --region sa-east-1` from a developer machine using a separate `proyecto-c-test` IAM user (no app creds on dev laptops).

Apply Task #1 in `tasks.md` MUST block on this runbook being complete.

## 13. Test Strategy

| Layer | What to Test | Approach |
|---|---|---|
| **Backend pytest (WSL)** | All 4 endpoint scenarios (auth-ok, 401, 400-malformed, 400-outside-allowlist, 403, 503-on-audit-fail, TTL-clamp); 4 storage backend methods (`_save`/`_open`/`delete`/`exists`) with `boto3.client` mocked; `_save` regression test capturing the double-open bug; `backfill_media` states (empty, full, partial-failure-resume). | `cd backend && python -m pytest -k media_` from WSL; mocks: `boto3.client`, `boto3.generate_presigned_url`; per `openspec/config.yaml` strict TDD. |
| **Frontend e2e (Windows)** | Happy path: cliente logs in, opens PDF of own ficha → image loads via signed URL. Forbidden path: cliente attempts to open PDF of another cliente → 403 + `<img>` broken/error state. Cache hit: same path re-rendered → no endpoint call. | `npx playwright test` from `frontend/aesthetic-clinic/`. |
| **Manual smoke** | Step 10 of §12 — `aws s3 ls` against the dev bucket. | Operator runs once after credentials in place. |

RED tests for the `_save` correctness fix MUST be written before the apply implementation changes `Boto3Storage` (per `openspec/config.yaml` strict_tdd: true).

## 14. Rollback Plan

- **Tier 1 (immediate)**: Set `STORAGE_PROVIDER=local` → redeploy. `STORAGES["default"]` falls back to `FileSystemStorage`. Frontend signed-URL endpoint returns 503; feature flag in helper falls back to `/media/...` (proposal §Rollback Plan step 2).
- **Tier 2 (within 30 days)**: `LazyLocalFallbackStorage` still active; `MEDIA_ROOT` retained; reads fall back to local until bucket catches up (media-storage spec §Scenario: Rollback via env var).
- **Tier 3 (after 30 days)**: No DB migration needed — `FileField.name` is already a relative path (media-storage spec §ADDED Requirements, "no migration required"). New `audit_log` table is additive; dropping it is a separate migration if rollback persists.
- **Rollback drill**: dry-run in staging before applying to prod. Apply phase writes a staging drill task.

## 15. Risks

| ID | Risk | Likelihood | Mitigation |
|---|---|---|---|
| C1 | Bugs in `storage_backends.py` (public `url()`, double-open in `_save`, dead `LocalStorage`) make refactor risky | High | Rewrite the class; pytest coverage including regression test for `_save` bug; remove dead code. |
| C2 | Backfill of ~200 GB may saturate network / take hours | Medium | Batched (100/batch) resumable script; nightly cron; maintenance window optional; `--dry-run` and `--resume` flags. |
| C3 | Frontend hard-codes `/media/...` in many places | Medium | Single `useSignedUrl` hook + grep audit before sign-off. |
| **D1** | `Boto3Storage.url()` regression — accidental return of public URL re-opens the privacy bug | Medium | `url()` raises `NotImplementedError`; test asserts raise; lint rule. |
| **D2** | Audit log table write contention under load (every signed URL is a DB write) | Medium | Index on `(user_id, created_at)` and `(resource_path, created_at)`; benchmark in apply; consider batched async audit (out of scope for v1, flagged for v1.1). |
| **D3** | IAM policy JSON typos silently block all uploads at runtime | Medium | Owner runbook §12 step 10 (`aws s3 ls` smoke test) catches missing perms; apply phase adds a CI step that JSON-validates the policy file. |
| **D4** | `MEDIA_LOCAL_FALLBACK_ENABLED=false` flipped before sentinel exists → 503 storm on legacy reads | Low | Sentinel `_BACKFILL_COMPLETE` must exist + manual operator confirmation before flip; documented in §8. |
| **D5** | Role-mapping ambiguity (`user.especialista`, `user.cliente`, specialist-who-registered-payment) blocks authorization tests | Medium | Marked as "verify with owner during apply" in §6; apply phase greps and resolves. |
| **D6** | SigV4 TTL > 7 days silently produces a URL that AWS rejects | Low | Endpoint clamps `ttl_seconds` to 604800 before calling `generate_presigned_url`; test asserts clamp. |
| W1 | Engram writes failing; mirror authoritative | Medium | Mirror at `sdd/proyecto-c/design-cloud-storage-migration.md` retained (this file). |
| W2 | Backend pytest is WSL-only | Low | Tests run from WSL per `openspec/config.yaml`; frontend e2e unaffected. |

## Threat Matrix

`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The backfill management command is an internal Django CLI tool, not a shell-facing boundary; signed-URL endpoint is a DRF view; storage backends are library code.`

## Migration / Rollout

- **Phase 0 — Owner setup** (§12): apply Task #1 BLOCKER; cannot run live tests until complete.
- **Phase 1 — Backend foundation**: rewrite `storage_backends.py`, wire `STORAGES["default"]`, create `audit` app + model + migration, add env vars to `.env.example`. RED tests first.
- **Phase 2 — Endpoint**: implement `media_signed_url` view, mount in `api_urls.py`, RED tests.
- **Phase 3 — Backfill command**: implement `backfill_media`, RED tests for empty/full/resume. NOT yet run against prod.
- **Phase 4 — Frontend**: `useSignedUrl` hook, Playwright e2e for happy + forbidden paths.
- **Phase 5 — Cutover** (operator-driven, not in apply):
  1. `STORAGE_PROVIDER=s3` + `MEDIA_LOCAL_FALLBACK_ENABLED=true` → deploy.
  2. Run `python manage.py backfill_media --resume` (nightly cron until sentinel exists).
  3. After sentinel + 30-day window: `MEDIA_LOCAL_FALLBACK_ENABLED=false`.
  4. Delete `MEDIA_ROOT` after 30 days post-cutover.
- **Phase 6 — Verify**: backend pytest on WSL, frontend Playwright on Windows, manual `aws s3 ls` smoke (Gate 4 step 10).
- **Phase 7 — Archive**: openspec archive phase syncs delta specs to canonical specs.

## Open Questions

- [ ] `fichas_clinicas/` cliente-self rule: confirm `FichaClinica.operacion.cliente` accessor with grep in apply.
- [ ] `comprobantes_*` specialist-who-registered-payment: identify which FK on `billing.models` resolves to the registering specialist — verify with grep in apply.
- [ ] Final frontend helper path: `src/services/media.ts` proposed; confirm with grep in apply (no `src/lib/` directory exists).
- [ ] Async upload during lazy fallback: Celery task vs in-process thread — apply decides based on whether `celery.py` is already wired in the prod deployment.
- [ ] 90-day audit retention: apply phase decides archive/cron-delete strategy.

## File Changes (summary)

| File | Action | Description |
|---|---|---|
| `backend/config/storage_backends.py` | Rewrite | Replace `SupabaseStorage` + `LocalStorage` with `Boto3Storage` + `LazyLocalFallbackStorage`; fix `_save` double-open bug; raise `NotImplementedError` in `url()`. |
| `backend/config/settings.py` (lines 192–209) | Modify | Drive `STORAGES["default"]` from `STORAGE_PROVIDER`; add new env vars; remove `supabase` from comments. |
| `backend/config/urls.py` | Modify | Remove `static(MEDIA_URL, ...)` line 30 (or gate on DEBUG only — already DEBUG-only per current code; verify behavior). |
| `backend/config/api_views.py` | Modify | Add `media_signed_url` view. |
| `backend/config/api_urls.py` | Modify | Mount `media-signed-url` route. |
| `backend/audit/models.py` | Create | `AuditLog` model + migration. |
| `backend/audit/services.py` | Create | `write_audit_log` writer; `AuditWriteFailure` exception. |
| `backend/config/management/commands/backfill_media.py` | Create | New management command (apply creates the package). |
| `backend/tests/test_media_signed_url.py` | Create | Endpoint scenarios + TTL clamp + audit-fail 503. |
| `backend/tests/test_storage_backends.py` | Create | 4 storage methods + `_save` regression. |
| `backend/tests/test_backfill_media.py` | Create | Empty/full/resume states. |
| `frontend/aesthetic-clinic/src/services/media.ts` | Create | `useSignedUrl` hook + cache. |
| `frontend/aesthetic-clinic/tests/` | Create | Playwright happy + forbidden paths. |
| `frontend/**/components/**/*.tsx` | Modify | Replace `/media/...` references with `useSignedUrl(path)` (grep audit in apply). |
| `sdd/proyecto-c/runbook-aws-s3-setup.md` | Create | Owner §12 checklist (apply creates or links). |
| `.env.example` | Modify | Document all 8 env vars from §7. |