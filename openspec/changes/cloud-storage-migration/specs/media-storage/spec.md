# media-storage — Specification

## Purpose

Store user-uploaded files (clinical PDFs, operation photos, payment receipts, ticket attachments) in a private AWS S3 bucket (`sa-east-1`) instead of local app-server disk, with a one-shot backfill and a 30-day lazy-read fallback. Greenfield: the current `LocalStorage` and the buggy `SupabaseStorage` at `backend/config/storage_backends.py:60` are dead code, and `STORAGES["default"]` at `backend/config/settings.py:192` ignores `STORAGE_PROVIDER`.

---

## ADDED Requirements

### Requirement: Object Storage Backend

The system SHALL store uploads in a private AWS S3 bucket in `sa-east-1` when `STORAGE_PROVIDER=s3`. Bucket SHALL have all four public-access-block flags enabled. `STORAGES["default"]["BACKEND"]` SHALL be `Boto3Storage` (Django `Storage` subclass) when `STORAGE_PROVIDER=s3`. The backend SHALL expose `_save`, `_open`, `delete`, `exists`, `size`, `modification_time`. Provider switching SHALL require only env vars (`AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) — no code changes — because boto3 S3 client is API-compatible with any S3 endpoint (research §"boto3 works for AWS S3 AND Cloudflare R2 and Supabase S3 gateway"). The backend SHALL NOT expose any public-URL method. `LocalStorage` (`backend/config/storage_backends.py:80-111`) and `SupabaseStorage.url()` (lines 60-66) SHALL be removed. Bucket SHALL have **S3 Versioning ON** (proposal Gate 7).

#### Scenario: New upload writes to bucket when provider is s3

- GIVEN `STORAGE_PROVIDER=s3` and valid AWS credentials
- WHEN the system saves a file via `FichaClinica.documento_escaneado_pdf` at `backend/clinical/models.py:120` (`upload_to="fichas_clinicas/%Y/%m/"`)
- THEN the file SHALL be uploaded to the bucket under key `fichas_clinicas/YYYY/MM/foo.pdf`
- AND `FieldFile.name` SHALL remain that relative path (no DB change)
- AND no bytes SHALL be written to `MEDIA_ROOT`

#### Scenario: No public URL is ever returned

- GIVEN any caller invokes `default_storage.url(name)` for an existing object
- THEN the backend SHALL raise `NotImplementedError` or return a SigV4 presigned URL
- AND the URL SHALL expire per `MEDIA_SIGNED_URL_TTL_SECONDS`

#### Scenario: Provider switch via env var only

- GIVEN bucket/region/credentials are env-driven
- WHEN an operator changes `AWS_S3_ENDPOINT_URL` to a non-AWS S3-compatible endpoint
- THEN the same code SHALL continue to function without modification

#### Scenario: STORAGE_PROVIDER=local fallback

- GIVEN `STORAGE_PROVIDER=local` (default per `backend/config/settings.py:206`)
- WHEN the system saves a file
- THEN `FileSystemStorage` SHALL handle the save and the file SHALL land in `MEDIA_ROOT`
- AND no S3 client SHALL be instantiated

---

### Requirement: Backfill Management Command

`python manage.py backfill_media` SHALL read every file under `MEDIA_ROOT` and upload it to the bucket, preserving relative paths as object keys. The command SHALL be batched (default 100 files per batch), resumable (skip keys already present via `head_object`), idempotent (re-run uploads only missing), observable (log start, per-batch, completion counts), and SHALL write a zero-byte sentinel `_BACKFILL_COMPLETE` at the bucket root on successful full pass. The command SHALL NOT touch any DB row: per `backend/clinical/models.py:121`, `FieldFile.name` already stores the relative path and SHALL be the bucket key — no migration required.

#### Scenario: First run uploads everything

- GIVEN `MEDIA_ROOT` contains 1000 files across all six upload prefixes
- WHEN an operator runs `python manage.py backfill_media`
- THEN all 1000 files SHALL be uploaded under matching relative keys
- AND progress SHALL be logged every 100 files
- AND `_BACKFILL_COMPLETE` SHALL appear at the bucket root

#### Scenario: Resumable re-run after partial failure

- GIVEN a prior run uploaded 600 of 1000 files and crashed
- WHEN the operator runs `python manage.py backfill_media` again
- THEN the 600 existing files SHALL be skipped (verified by `head_object`)
- AND only the remaining 400 SHALL be uploaded

#### Scenario: Empty MEDIA_ROOT

- GIVEN `MEDIA_ROOT` is empty
- WHEN the operator runs `python manage.py backfill_media`
- THEN the command SHALL exit successfully
- AND `_BACKFILL_COMPLETE` SHALL still be written
- AND no errors SHALL be raised

---

### Requirement: Lazy Local Fallback During Cutover

During the 30-day post-cutover transition, `STORAGES["default"]` SHALL be `LazyLocalFallbackStorage`, a subclass wrapping the S3 backend that falls back to `MEDIA_ROOT` when a key is missing in the bucket. On `exists()`/`open()`: query bucket via `head_object`, fall back to `MEDIA_ROOT` if absent; if served from local, enqueue async upload (Celery or in-process thread) so the next read goes to the bucket. Fallback SHALL be active only when `STORAGE_PROVIDER=s3`. After the 30-day window — once `_BACKFILL_COMPLETE` exists and all `MEDIA_ROOT` files are confirmed uploaded — operators MAY swap to `Boto3Storage` directly. `MEDIA_ROOT` SHALL be retained ≥30 days post-cutover for rollback (proposal Rollback Plan §3).

#### Scenario: Read of a legacy file falls back to local

- GIVEN `STORAGE_PROVIDER=s3`, bucket missing `fichas_clinicas/2026/09/old.pdf`
- AND `MEDIA_ROOT/fichas_clinicas/2026/09/old.pdf` exists
- WHEN the backend serves that path
- THEN the file SHALL be served from `MEDIA_ROOT`
- AND an async upload task SHALL be enqueued to push it to the bucket
- AND the response SHALL be functionally equivalent to a bucket read

#### Scenario: Missing file raises standard exception

- GIVEN bucket missing `fichas_clinicas/2026/09/missing.pdf` AND no local copy
- WHEN the backend serves that path
- THEN the backend SHALL raise `FileNotFoundError` (NOT silently return empty bytes)

#### Scenario: Rollback via env var

- GIVEN production on `STORAGE_PROVIDER=s3` with `LazyLocalFallbackStorage` active
- WHEN operator sets `STORAGE_PROVIDER=local` and redeploys
- THEN `STORAGES["default"]` SHALL resolve to `FileSystemStorage`
- AND all reads SHALL go directly to `MEDIA_ROOT` with no S3 calls

---

## Capabilities (delta)

### New Capabilities

- `object-storage`
- `object-storage-backfill`
- `object-storage-lazy-read`

### Modified Capabilities

None.
