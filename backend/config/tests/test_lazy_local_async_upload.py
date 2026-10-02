"""Tests for LazyLocalFallbackStorage async upload (slice 3a)."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_USE_LOCAL_DB", "1")
os.environ.setdefault("AWS_STORAGE_BUCKET_NAME", "test-bucket")
import django  # noqa: E402

django.setup()

from django.test import SimpleTestCase, override_settings  # noqa: E402

from config.storage_backends import LazyLocalFallbackStorage  # noqa: E402

_FAKE_BUCKET = "test-bucket"


def _client_error():
    from botocore.exceptions import ClientError
    return ClientError(
        error_response={
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "config.storage_backends.LazyLocalFallbackStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class LazyLocalFallbackAsyncUploadTests(SimpleTestCase):
    def setUp(self):
        self._bucket_patch = mock.patch.dict(os.environ, {"AWS_STORAGE_BUCKET_NAME": _FAKE_BUCKET})
        self._bucket_patch.start()
        self.addCleanup(self._bucket_patch.stop)
        self.fake = _FakeS3Client()
        self._client_patch = mock.patch("config.storage_backends.boto3.client", return_value=self.fake)
        self._client_patch.start()
        self.addCleanup(self._client_patch.stop)
        self.tmp_media = Path(tempfile.mkdtemp(prefix="async-up-"))
        self._media_root_patch = override_settings(MEDIA_ROOT=self.tmp_media)
        self._media_root_patch.enable()
        self.addCleanup(self._media_root_patch.disable)

    def _wait_for_put(self, key: str, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for call in self.fake.put_calls:
                if call["Key"] == key:
                    return True
            time.sleep(0.01)
        return False

    def test_local_hit_enqueues_background_upload(self):
        local = self.tmp_media / "legacy.pdf"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"legacy-bytes")
        storage = LazyLocalFallbackStorage()
        with self.assertLogs("config.storage_backends", level="INFO") as cm:
            content = storage._open("legacy.pdf")
        self.assertEqual(content.read(), b"legacy-bytes")
        self.assertTrue(self._wait_for_put("legacy.pdf"), f"no put; got {self.fake.put_calls}")
        put = next(c for c in self.fake.put_calls if c["Key"] == "legacy.pdf")
        self.assertEqual(put["Body"], b"legacy-bytes")
        self.assertTrue(any("async_upload_enqueued" in line for line in cm.output))

    def test_async_upload_swallows_put_object_errors(self):
        local = self.tmp_media / "broken.pdf"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"bytes")
        storage = LazyLocalFallbackStorage()
        with mock.patch(
            "config.storage_backends._upload_local_to_bucket",
            side_effect=RuntimeError("boom"),
        ):
            content = storage._open("broken.pdf")
        self.assertEqual(content.read(), b"bytes")

    def test_async_upload_thread_is_daemon(self):
        local = self.tmp_media / "daemon.pdf"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"x")
        storage = LazyLocalFallbackStorage()
        captured: dict = {}
        real_thread = threading.Thread

        class _CapturingThread(real_thread):  # type: ignore[misc]
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                captured["instance"] = self

        with mock.patch("config.storage_backends.threading.Thread", _CapturingThread):
            storage._open("daemon.pdf")
        thread = captured.get("instance")
        self.assertIsNotNone(thread, msg="expected _open to spawn a Thread")
        self.assertTrue(thread.daemon)
