"""Tests for backfill_media (slice 3a)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_USE_LOCAL_DB", "1")
os.environ.setdefault("AWS_STORAGE_BUCKET_NAME", "test-bucket")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import SimpleTestCase, override_settings  # noqa: E402


def _client_error():
    from botocore.exceptions import ClientError
    return ClientError(
        error_response={"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
        operation_name="HeadObject",
    )


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []

    def put_object(self, *, Bucket, Key, Body, **_kwargs):
        self.put_calls.append({"Bucket": Bucket, "Key": Key, "Body": Body})
        self.objects[(Bucket, Key)] = Body

    def head_object(self, *, Bucket, Key, **_kwargs):
        if (Bucket, Key) not in self.objects:
            raise _client_error()
        return {"ContentLength": len(self.objects[(Bucket, Key)])}


def _populate(root: Path, names: list[str]) -> None:
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"x")


def _uploaded_keys(fake: _FakeS3Client) -> set[str]:
    return {c["Key"] for c in fake.put_calls if c["Key"] != "_BACKFILL_COMPLETE"}


class BackfillMediaTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="backfill-test-"))
        self.fake = _FakeS3Client()
        self._bucket_patch = mock.patch.dict(os.environ, {"AWS_STORAGE_BUCKET_NAME": "test-bucket"})
        self._bucket_patch.start()
        self.addCleanup(self._bucket_patch.stop)
        self._client_patch = mock.patch("config.storage_backends.boto3.client", return_value=self.fake)
        self._client_patch.start()
        self.addCleanup(self._client_patch.stop)

    def test_empty_media_root_writes_only_sentinel(self):
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media")
        self.assertEqual({c["Key"]: c["Body"] for c in self.fake.put_calls}, {"_BACKFILL_COMPLETE": b""})

    def test_all_files_uploaded_then_sentinel(self):
        _populate(self.tmp, ["a/foo.pdf", "a/b/bar.pdf", "b/baz.png"])
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media", "--batch-size=2")
        self.assertEqual(_uploaded_keys(self.fake), {"a/foo.pdf", "a/b/bar.pdf", "b/baz.png"})
        self.assertEqual(self.fake.put_calls[-1]["Key"], "_BACKFILL_COMPLETE")

    def test_resume_skips_existing_objects(self):
        _populate(self.tmp, ["keep.pdf", "new.pdf"])
        self.fake.objects[("test-bucket", "keep.pdf")] = b"already-here"
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media", "--resume")
        self.assertEqual(_uploaded_keys(self.fake), {"new.pdf"})

    def test_dry_run_writes_nothing(self):
        _populate(self.tmp, ["a.pdf", "b.pdf"])
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media", "--dry-run")
        self.assertEqual(self.fake.put_calls, [])

    def test_prefix_filter_scopes_walk(self):
        _populate(self.tmp, ["fichas/x.pdf", "tickets/y.pdf"])
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media", "--prefix=fichas/")
        self.assertEqual(_uploaded_keys(self.fake), {"fichas/x.pdf"})
