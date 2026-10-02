"""``backfill_media`` management command (slice 3).

Walks ``MEDIA_ROOT``, uploads each file to the configured S3 bucket in
batches, and writes a zero-byte ``_BACKFILL_COMPLETE`` sentinel at the
bucket root when the pass finishes. CLI flags: ``--batch-size=N``,
``--dry-run``, ``--prefix=...``, ``--resume``, ``--verify``. Errors on
a single file are logged and the run continues.
"""

from __future__ import annotations

import logging
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand

from config.storage_backends import _bucket_name, _get_s3_client  # noqa: WPS437

logger = logging.getLogger(__name__)
_SENTINEL_KEY = "_BACKFILL_COMPLETE"


class Command(BaseCommand):
    help = "Upload every file under MEDIA_ROOT to the configured S3 bucket."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--prefix", type=str, default="")
        parser.add_argument("--resume", action="store_true")
        parser.add_argument("--verify", action="store_true")

    def handle(self, *args, **options):
        # ``--verify`` is accepted but unused in slice 3; slice 4 wires it
        # to a byte-by-byte comparison against the local source.
        batch_size, dry_run, prefix, resume = (
            options["batch_size"],
            options["dry_run"],
            options["prefix"],
            options["resume"],
        )
        media_root = Path(settings.MEDIA_ROOT)
        client = _get_s3_client()
        bucket = _bucket_name()

        uploaded = skipped = errors = 0
        batch: list[tuple[str, Path]] = []

        for abs_path in sorted(media_root.rglob("*")):
            if not abs_path.is_file():
                continue
            key = abs_path.relative_to(media_root).as_posix()
            if prefix and not key.startswith(prefix):
                continue
            if resume and not dry_run and self._already_uploaded(client, bucket, key):
                skipped += 1
                continue
            batch.append((key, abs_path))
            if len(batch) >= batch_size:
                ok, err = self._flush_batch(client, bucket, batch, dry_run)
                uploaded += ok
                errors += err
                batch.clear()
        if batch:
            ok, err = self._flush_batch(client, bucket, batch, dry_run)
            uploaded += ok
            errors += err
        if not dry_run:
            client.put_object(Bucket=bucket, Key=_SENTINEL_KEY, Body=b"")
        self.stdout.write(
            f"backfill complete: uploaded={uploaded} skipped={skipped} "
            f"errors={errors} dry_run={dry_run}"
        )

    def _already_uploaded(self, client, bucket: str, key: str) -> bool:
        try:
            client.head_object(Bucket=bucket, Key=key)
        except ClientError:
            return False
        return True

    def _flush_batch(self, client, bucket, batch, dry_run):
        if dry_run:
            for key, _ in batch:
                self.stdout.write(f"would upload: {key}")
            return 0, 0
        ok = err = 0
        for key, abs_path in batch:
            try:
                with open(abs_path, "rb") as handle:
                    client.put_object(Bucket=bucket, Key=key, Body=handle.read())
                ok += 1
            except Exception as exc:  # noqa: BLE001 — log + continue
                err += 1
                logger.error("backfill_failed: key=%s err=%s", key, exc)
        return ok, err
