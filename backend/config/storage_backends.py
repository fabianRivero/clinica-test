"""Storage backends for cloud-storage-migration (slice 1 + slice 2 of 4).

Slice 1 ships the foundation:

* :class:`Boto3Storage` — primary Django ``Storage`` subclass backed by
  ``boto3.client('s3')``. Reads, writes, deletes, and metadata queries go
  straight to the private AWS S3 bucket configured via ``AWS_*`` env vars.
  ``url()`` raises :class:`NotImplementedError` so callers cannot mint public
  URLs through the default storage; signed URLs MUST go through the
  ``/api/media/signed-url/`` endpoint added in slice 2.
* :class:`LazyLocalFallbackStorage` — :class:`Boto3Storage` subclass that
  reads from ``MEDIA_ROOT`` when the bucket is missing a key during the
  30-day cutover window. Toggleable via ``MEDIA_LOCAL_FALLBACK_ENABLED``.
  The async upload enqueueing that pushes legacy files back to the bucket
  is deferred to slice 3 (``backfill_media`` management command plus
  Celery task); slice 1 only logs the fallback for observability.

Slice 2 adds :meth:`Boto3Storage.generate_presigned_url` so the
``/api/media/signed-url/`` endpoint can mint SigV4 presigned GET URLs
without bypassing the storage abstraction. The helper is intentionally
minimal: the endpoint is responsible for path sanitization, per-prefix
authorization, TTL clamping, and the fail-closed audit write.

The legacy ``SupabaseStorage`` and ``LocalStorage`` classes were removed:

* ``SupabaseStorage`` — buggy ``_save`` double-open bug at line 43 of the
  prior implementation; ``url()`` returned an unauthenticated public URL
  which is the privacy defect this change exists to fix. Replaced by
  ``Boto3Storage``.
* ``LocalStorage`` — pure reimplementation of Django's built-in
  ``FileSystemStorage`` with the same double-open bug. Removed in favor
  of pointing ``STORAGES["default"]["BACKEND"]`` straight at
  ``django.core.files.storage.FileSystemStorage`` when
  ``STORAGE_PROVIDER=local``.

Env vars consumed by this module (declared in ``config/settings.py``):

* ``STORAGE_PROVIDER`` — ``local`` | ``s3`` (string).
* ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` — IAM credentials.
* ``AWS_STORAGE_BUCKET_NAME`` — bucket name (e.g.
  ``proyecto-c-clinical-prod``).
* ``AWS_S3_REGION_NAME`` — defaults to ``sa-east-1``.
* ``AWS_S3_ENDPOINT_URL`` — optional, for non-AWS S3-compatible endpoints
  (Cloudflare R2, Supabase S3 gateway, MinIO).
* ``MEDIA_LOCAL_FALLBACK_ENABLED`` — defaults to ``True``; when ``False``
  and ``STORAGE_PROVIDER=s3``, slice 1's wiring chooses ``Boto3Storage``
  directly (no fallback).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import Storage


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

_AWS_REGION_DEFAULT = "sa-east-1"


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bucket_name() -> str:
    """Return the configured bucket name or raise an explicit error.

    We raise ``ImproperlyConfigured`` so the app fails fast at boot when
    ``STORAGE_PROVIDER=s3`` is selected without credentials, rather than
    crashing deep inside a boto3 call later.
    """
    bucket = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "AWS_STORAGE_BUCKET_NAME must be set when STORAGE_PROVIDER=s3."
        )
    return bucket


def _client_config() -> Config:
    """Return the botocore ``Config`` for the boto3 S3 client."""
    return Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    )


def _get_s3_client():
    """Build a fresh boto3 S3 client from current env vars.

    A new client per call is intentional for slice 1: tests mock
    ``boto3.client`` directly, and any caller that needs connection pooling
    can construct its own client. Future slices may add module-level
    caching if needed.
    """
    endpoint_url = os.getenv("AWS_S3_ENDPOINT_URL") or None
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        region_name=os.getenv("AWS_S3_REGION_NAME", _AWS_REGION_DEFAULT),
        config=_client_config(),
    )


# ---------------------------------------------------------------------------
# Boto3Storage — primary S3 backend
# ---------------------------------------------------------------------------


class Boto3Storage(Storage):
    """Django ``Storage`` subclass backed by ``boto3.client('s3')``.

    Implements the contract documented in design §3.1 + §7:

    * ``_save(name, content)`` — uploads the bytes of ``content`` to the
      bucket under ``name`` and returns ``name``. Fixes the
      ``content.open()`` double-open bug present in the prior
      ``SupabaseStorage._save`` implementation by reading from the
      already-open underlying file when one exists, falling back to
      ``content.read()`` otherwise (design §7 pseudocode).
    * ``_open(name, mode='rb')`` — downloads the object and returns a
      ``ContentFile`` wrapper.
    * ``delete(name)`` — removes the object; idempotent (404 swallowed).
    * ``exists(name)`` — ``head_object`` lookup.
    * ``size(name)`` — ``ContentLength`` from ``head_object``.
    * ``modification_time(name)`` — ``LastModified`` from ``head_object``,
      converted to a naive ``datetime`` in UTC (Django's contract).
    * ``url(name)`` — raises ``NotImplementedError``. Signed URLs are
      minted only through ``/api/media/signed-url/`` (slice 2) so audit
      logging is non-bypassable.
    """

    def __init__(self, **settings: Any) -> None:
        # ``**settings`` accepted for Django compatibility (Django's
        # storages framework may pass dict options). We only need the
        # env-driven config.
        self._bucket = _bucket_name()

    # ---- Django Storage contract ---------------------------------------

    def _open(self, name: str, mode: str = "rb") -> ContentFile:
        client = _get_s3_client()
        response = client.get_object(Bucket=self._bucket, Key=name)
        # ``StreamingBody`` read returns the full payload; we wrap it so
        # downstream code can call ``.read()``/``.chunks()`` on the
        # returned ``ContentFile`` exactly like a local File.
        return ContentFile(response["Body"].read(), name=name)

    def _save(self, name: str, content: Any) -> str:
        client = _get_s3_client()
        # The double-open bug fix: Django's FileField save path passes a
        # FieldFile whose underlying file is already open; calling
        # ``content.open()`` raises ``ValueError`` on already-open files,
        # and ``content.read()`` after a stale ``.close()`` would return
        # empty bytes. Read from the live underlying file when present,
        # else from ``content`` directly. See design §7.
        if getattr(content, "file", None) is not None:
            data = content.file.read()
        else:
            data = content.read()
        client.put_object(Bucket=self._bucket, Key=name, Body=data)
        return name

    def delete(self, name: str) -> None:
        client = _get_s3_client()
        # Idempotent: missing object is fine. ``delete_object`` on a
        # non-existent key is a no-op on the AWS side, but we still
        # catch ClientError so tests / dev buckets behave identically.
        try:
            client.delete_object(Bucket=self._bucket, Key=name)
        except ClientError as exc:
            # ``NoSuchKey`` / 404 — surface a more useful Django exception
            # for callers that branch on storage errors.
            status = exc.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if status not in (404,):
                raise

    def exists(self, name: str) -> bool:
        client = _get_s3_client()
        try:
            client.head_object(Bucket=self._bucket, Key=name)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if status in (404,):
                return False
            # Any other ClientError: treat as missing to preserve the
            # previous ``SupabaseStorage.exists`` semantics (returns False
            # on any exception). Tests assert this behavior.
            return False
        return True

    def url(self, name: str) -> str:
        # Per media-storage spec: no public URL escape hatch. Slices 2+
        # introduce signed-URL minting through an authenticated endpoint.
        raise NotImplementedError(
            "Boto3Storage.url() is disabled; mint signed URLs through "
            "/api/media/signed-url/ (slice 2)."
        )

    def generate_presigned_url(self, name: str, ttl_seconds: int) -> str:
        """Return a SigV4 presigned S3 GET URL for ``name``.

        Added in slice 2 so the ``/api/media/signed-url/`` endpoint can
        mint short-lived URLs through the storage abstraction without
        reaching into boto3 directly. The endpoint still owns path
        sanitization, TTL clamping, authorization, and the fail-closed
        audit row — this helper is a thin pass-through to
        ``boto3.client.generate_presigned_url`` so the audit code path
        can rely on the storage backend being the single place that
        knows the bucket name and region.

        Caller is responsible for:

        * validating that ``name`` is an allowed relative path
          (path allowlist + ``..``/leading ``/``/``\\`` rejection).
        * logging the access (audit) BEFORE calling this method — the
          fail-closed contract is that no URL is minted without a
          persisted audit row.
        * clamping ``ttl_seconds`` to a safe upper bound (SigV4 max is
          7 days / 604800 seconds; the endpoint clamps to that value
          before calling here).

        ``ttl_seconds`` is passed through unchanged so the endpoint can
        decide what "safe" means for its caller (e.g. the request's
        ``ttl`` query param bounded by ``MEDIA_SIGNED_URL_TTL_SECONDS``).
        """
        client = _get_s3_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": name},
            ExpiresIn=ttl_seconds,
        )

    def size(self, name: str) -> int:
        client = _get_s3_client()
        response = client.head_object(Bucket=self._bucket, Key=name)
        return int(response["ContentLength"])

    def modification_time(self, name: str) -> datetime:
        client = _get_s3_client()
        response = client.head_object(Bucket=self._bucket, Key=name)
        last_modified: datetime = response["LastModified"]
        # Django expects a naive ``datetime`` in the project's
        # ``TIME_ZONE`` (America/La_Paz per settings.py). The S3 client
        # returns timezone-aware UTC; convert to naive UTC to keep the
        # conversion deterministic — Django re-localizes on demand.
        if last_modified.tzinfo is not None:
            last_modified = last_modified.astimezone(timezone.utc).replace(
                tzinfo=None
            )
        return last_modified


# ---------------------------------------------------------------------------
# LazyLocalFallbackStorage — S3 with MEDIA_ROOT fallback for cutover
# ---------------------------------------------------------------------------


class LazyLocalFallbackStorage(Boto3Storage):
    """S3-backed storage that falls back to ``MEDIA_ROOT`` on bucket miss.

    During the 30-day cutover window (design §7 / media-storage spec
    §"Lazy Local Fallback During Cutover"), some legacy files may still
    live only on the app server's local disk. This class overrides
    ``_open`` and ``exists`` to:

    1. Query the bucket via ``head_object`` (delegating to the parent
       class).
    2. If the key is missing in the bucket AND
       ``MEDIA_LOCAL_FALLBACK_ENABLED`` is true, consult ``MEDIA_ROOT``.
    3. When a read is served from ``MEDIA_ROOT``, emit a single
       ``logger.info`` line so operators can see which legacy keys are
       being served locally during the window.

    Slice 3 will replace the log line with an async upload task that
    pushes the legacy file back into the bucket so subsequent reads hit
    the fast path. For slice 1 the goal is correctness only: legacy
    reads must succeed and bucket reads must still be the default.

    Writes (``_save``), ``delete``, ``size``, ``modification_time``, and
    ``url`` are NOT overridden. Writes always target the bucket so the
    bucket is the source of truth for new content; deletes only ever
    remove the bucket object (local copy may persist until the 30-day
    cleanup, by design).
    """

    def __init__(self, **settings: Any) -> None:
        super().__init__()
        self._local_fallback_enabled: bool = _env_flag(
            "MEDIA_LOCAL_FALLBACK_ENABLED", True
        )

    # ---- helpers -------------------------------------------------------

    def _local_path(self, name: str):
        """Resolve ``name`` against ``MEDIA_ROOT``."""
        from django.conf import settings

        return settings.MEDIA_ROOT / name

    def _serve_from_local(self, name: str) -> bool:
        """Return True iff fallback is enabled AND the local file exists."""
        if not self._local_fallback_enabled:
            return False
        return self._local_path(name).exists()

    # ---- overridden read paths ---------------------------------------

    def _open(self, name: str, mode: str = "rb") -> ContentFile:
        # Try the bucket first via ``super().exists`` so we don't mask
        # bucket-resident files behind a stale local copy. Only on a
        # confirmed bucket miss do we consult MEDIA_ROOT. Using
        # ``super().exists`` (NOT ``self.exists``) avoids a recursion:
        # ``self.exists`` also falls back to local, which would route us
        # back to the bucket read on the next branch.
        if super().exists(name):
            return super()._open(name, mode=mode)
        if self._serve_from_local(name):
            local_path = self._local_path(name)
            logger.info(
                "storage_fallback_local: serving %s from MEDIA_ROOT "
                "(bucket miss; fallback enabled)",
                name,
            )
            with open(local_path, "rb") as handle:
                return ContentFile(handle.read(), name=name)
        # Both bucket and local miss — surface the standard Django
        # ``FileNotFoundError`` per media-storage spec.
        raise FileNotFoundError(
            f"File '{name}' does not exist in bucket or MEDIA_ROOT."
        )

    def exists(self, name: str) -> bool:
        # Delegate to the parent for the bucket check first. The parent
        # already returns ``False`` on 404 and any other ClientError, so
        # the fallback logic reduces to "bucket miss → local check".
        if super().exists(name):
            return True
        return self._serve_from_local(name)