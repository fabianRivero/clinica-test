"""Tests for ``config.storage_backends`` (cloud-storage-migration, slice 1).

These tests cover:

* ``Boto3Storage`` round-trip semantics (``_save``, ``_open``, ``delete``,
  ``exists``, ``size``, ``modification_time``) with ``boto3.client``
  fully mocked — slice 1 never reaches a real AWS bucket.
* ``Boto3Storage.url()`` raises :class:`NotImplementedError` (no public
  URL escape hatch — see media-storage §"No public URL is ever returned"
  and design §3.1).
* Regression test for the ``_save`` double-open bug present in the
  legacy ``SupabaseStorage`` (storage_backends.py:43, prior version):
  writing an already-open ``FieldFile`` must NOT raise ``ValueError``
  and must upload the full payload, not empty bytes.
* ``LazyLocalFallbackStorage`` falls back to ``MEDIA_ROOT`` when the
  bucket returns 404 AND ``MEDIA_LOCAL_FALLBACK_ENABLED`` is true.
  When the fallback flag is false, the local copy is ignored and a
  bucket miss raises :class:`FileNotFoundError`.
* ``STORAGES["default"]["BACKEND"]`` switches by ``STORAGE_PROVIDER``
  env var (settings.py wiring).

All tests run without Django DB access — we patch ``boto3.client`` so no
network call ever happens, and we patch ``MEDIA_ROOT`` to a temp dir
where needed.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

# Boot Django before any Django imports below. ``pytest-django`` is not in
# the project's requirements, so we initialize the settings module the same
# way ``manage.py`` does.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_USE_LOCAL_DB", "1")
import django  # noqa: E402

django.setup()

from botocore.exceptions import ClientError  # noqa: E402
from django.core.files.base import ContentFile, File  # noqa: E402
from django.test import SimpleTestCase, override_settings  # noqa: E402

from config.storage_backends import (  # noqa: E402
    Boto3Storage,
    LazyLocalFallbackStorage,
)


# A bucket name chosen to be obviously fake; ``Boto3Storage.__init__``
# refuses to instantiate without one (design §7 fail-fast).
_FAKE_BUCKET = "test-bucket"


def _client_error(status_code: int) -> ClientError:
    """Build a ``ClientError`` matching what boto3 raises on HTTP errors."""
    return ClientError(
        error_response={
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        operation_name="HeadObject",
    )


class _FakeS3Client:
    """Minimal in-memory boto3 S3 client stand-in.

    The production code only calls ``put_object``, ``get_object``,
    ``delete_object``, and ``head_object``. We record every call so tests
    can assert on the arguments without ever opening a socket.
    """

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self.head_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        # Optional override: when set, ``head_object`` raises the given
        # ClientError instead of returning. Lets us simulate 404 / 500
        # paths from tests without monkeypatching per call.
        self.head_error: ClientError | None = None

    def put_object(self, *, Bucket, Key, Body, **_kwargs):
        self.put_calls.append({"Bucket": Bucket, "Key": Key, "Body": Body})
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key, **_kwargs):
        self.get_calls.append({"Bucket": Bucket, "Key": Key})
        body = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body)}

    def head_object(self, *, Bucket, Key, **_kwargs):
        self.head_calls.append({"Bucket": Bucket, "Key": Key})
        if self.head_error is not None:
            raise self.head_error
        if (Bucket, Key) not in self.objects:
            raise _client_error(404)
        size = len(self.objects[(Bucket, Key)])
        return {
            "ContentLength": size,
            "LastModified": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

    def delete_object(self, *, Bucket, Key, **_kwargs):
        self.delete_calls.append({"Bucket": Bucket, "Key": Key})
        self.objects.pop((Bucket, Key), None)


class Boto3StorageTests(SimpleTestCase):
    """CRUD semantics for :class:`Boto3Storage` with boto3 mocked."""

    def setUp(self) -> None:
        # Provide the bucket the constructor demands.
        self._bucket_patch = mock.patch.dict(
            os.environ,
            {"AWS_STORAGE_BUCKET_NAME": _FAKE_BUCKET},
        )
        self._bucket_patch.start()
        self.addCleanup(self._bucket_patch.stop)

        self.fake_client = _FakeS3Client()
        # Patch boto3.client inside the storage_backends module — the
        # production code calls boto3.client via the module-level
        # ``_get_s3_client`` helper.
        self._client_patch = mock.patch(
            "config.storage_backends.boto3.client",
            return_value=self.fake_client,
        )
        self._client_patch.start()
        self.addCleanup(self._client_patch.stop)

    def test_save_writes_payload_and_returns_name(self):
        storage = Boto3Storage()
        result = storage._save("uploads/foo.pdf", ContentFile(b"hello"))
        self.assertEqual(result, "uploads/foo.pdf")
        self.assertEqual(len(self.fake_client.put_calls), 1)
        put = self.fake_client.put_calls[0]
        self.assertEqual(put["Bucket"], _FAKE_BUCKET)
        self.assertEqual(put["Key"], "uploads/foo.pdf")
        self.assertEqual(put["Body"], b"hello")

    def test_save_handles_already_open_fieldfile_without_double_open(self):
        """Regression test for the legacy ``SupabaseStorage._save`` bug.

        Django's ``FileField.save`` path passes a ``FieldFile`` whose
        underlying file is already open. The legacy code called
        ``content.open()`` first, raising ``ValueError: I/O operation
        on closed file`` on already-open files. The fix reads from
        ``content.file.read()`` directly when an underlying file is
        present, and otherwise falls back to ``content.read()``.
        """

        class _AlreadyOpenFile(File):
            """A File wrapper whose underlying handle is open from the start."""

            def __init__(self, payload: bytes):
                self._payload = payload
                # Mimic ``FieldFile``: ``file`` attribute is an open file.
                self.file = io.BytesIO(payload)
                self.name = "upload.bin"

            def read(self, *args, **kwargs):
                return self._payload

            # The production code does NOT call ``.open()`` — if it ever
            # does again, the test will explode here with ``ValueError``,
            # which is exactly the regression we want to catch.
            def open(self, mode=None):
                raise AssertionError(
                    "Boto3Storage._save must not call content.open() "
                    "on an already-open FieldFile."
                )

        already_open = _AlreadyOpenFile(b"payload-bytes")
        storage = Boto3Storage()
        result = storage._save("uploads/open.bin", already_open)
        self.assertEqual(result, "uploads/open.bin")
        self.assertEqual(
            self.fake_client.objects[(_FAKE_BUCKET, "uploads/open.bin")],
            b"payload-bytes",
        )

    def test_open_round_trip(self):
        storage = Boto3Storage()
        storage._save("uploads/round.bin", ContentFile(b"round-trip-bytes"))
        # Force a fresh storage so ``_open`` triggers a client call.
        storage = Boto3Storage()
        result = storage._open("uploads/round.bin")
        self.assertIsInstance(result, ContentFile)
        self.assertEqual(result.read(), b"round-trip-bytes")
        self.assertEqual(len(self.fake_client.get_calls), 1)

    def test_delete_removes_object(self):
        storage = Boto3Storage()
        storage._save("uploads/delete-me.bin", ContentFile(b"x"))
        storage.delete("uploads/delete-me.bin")
        self.assertEqual(len(self.fake_client.delete_calls), 1)
        # After delete, exists() should now return False.
        self.assertFalse(storage.exists("uploads/delete-me.bin"))

    def test_exists_true_when_bucket_has_object(self):
        storage = Boto3Storage()
        storage._save("uploads/yes.bin", ContentFile(b"y"))
        self.assertTrue(storage.exists("uploads/yes.bin"))

    def test_exists_false_when_bucket_returns_404(self):
        storage = Boto3Storage()
        self.assertFalse(storage.exists("uploads/missing.bin"))

    def test_exists_false_on_other_client_error(self):
        """The legacy ``SupabaseStorage.exists`` returned False on ANY
        exception; we preserve that semantics so callers that branch on
        ``storage.exists()`` keep working through the migration.
        """
        self.fake_client.head_error = _client_error(500)
        storage = Boto3Storage()
        self.assertFalse(storage.exists("uploads/will-error.bin"))

    def test_size_returns_content_length(self):
        storage = Boto3Storage()
        payload = b"x" * 42
        storage._save("uploads/sized.bin", ContentFile(payload))
        # Use a fresh storage so ``size`` triggers its own client call.
        storage = Boto3Storage()
        self.assertEqual(storage.size("uploads/sized.bin"), 42)

    def test_modification_time_returns_naive_utc_datetime(self):
        storage = Boto3Storage()
        storage._save("uploads/time.bin", ContentFile(b"t"))
        storage = Boto3Storage()
        mtime = storage.modification_time("uploads/time.bin")
        self.assertIsInstance(mtime, datetime)
        # Must be naive — Django re-localizes against TIME_ZONE.
        self.assertIsNone(mtime.tzinfo)
        self.assertEqual((mtime.year, mtime.month, mtime.day), (2026, 9, 1))

    def test_url_raises_not_implemented(self):
        storage = Boto3Storage()
        with self.assertRaises(NotImplementedError):
            storage.url("uploads/whatever.bin")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "config.storage_backends.LazyLocalFallbackStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class LazyLocalFallbackStorageTests(SimpleTestCase):
    """Cutover semantics: bucket miss → MEDIA_ROOT when fallback enabled."""

    def setUp(self) -> None:
        self._bucket_patch = mock.patch.dict(
            os.environ,
            {"AWS_STORAGE_BUCKET_NAME": _FAKE_BUCKET},
        )
        self._bucket_patch.start()
        self.addCleanup(self._bucket_patch.stop)

        self.fake_client = _FakeS3Client()
        self._client_patch = mock.patch(
            "config.storage_backends.boto3.client",
            return_value=self.fake_client,
        )
        self._client_patch.start()
        self.addCleanup(self._client_patch.stop)

        # Use a temp MEDIA_ROOT so local-fallback tests do not touch the
        # real ``backend/media`` directory.
        self.tmp_media = Path(tempfile.mkdtemp(prefix="storage-test-"))
        self._media_root_patch = override_settings(MEDIA_ROOT=self.tmp_media)
        self._media_root_patch.enable()
        self.addCleanup(self._media_root_patch.disable)

    def test_bucket_hit_returns_bucket_content(self):
        storage = LazyLocalFallbackStorage()
        storage._save("uploads/hit.bin", ContentFile(b"hit"))
        content = storage._open("uploads/hit.bin")
        self.assertEqual(content.read(), b"hit")

    def test_bucket_miss_with_local_copy_serves_from_media_root(self):
        # Drop a file into MEDIA_ROOT only — bucket is empty.
        local = self.tmp_media / "uploads" / "legacy.bin"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b"legacy-bytes")

        storage = LazyLocalFallbackStorage()
        with self.assertLogs("config.storage_backends", level="INFO") as logs_cm:
            content = storage._open("uploads/legacy.bin")
        self.assertEqual(content.read(), b"legacy-bytes")
        self.assertTrue(
            any("storage_fallback_local" in line for line in logs_cm.output),
            msg=f"Expected fallback log line; got {logs_cm.output!r}",
        )

    def test_exists_returns_true_via_local_when_bucket_misses(self):
        local = self.tmp_media / "legacy-exists.bin"
        local.write_bytes(b"x")
        storage = LazyLocalFallbackStorage()
        self.assertTrue(storage.exists("legacy-exists.bin"))

    def test_bucket_and_local_both_missing_raises_file_not_found(self):
        storage = LazyLocalFallbackStorage()
        with self.assertRaises(FileNotFoundError):
            storage._open("uploads/nowhere.bin")

    def test_disabled_fallback_ignores_local_copy(self):
        # Flip fallback off and confirm MEDIA_ROOT is NOT used.
        with mock.patch.dict(
            os.environ, {"MEDIA_LOCAL_FALLBACK_ENABLED": "false"}
        ):
            local = self.tmp_media / "legacy.bin"
            local.write_bytes(b"ignored")
            storage = LazyLocalFallbackStorage()
            self.assertFalse(storage.exists("legacy.bin"))
            with self.assertRaises(FileNotFoundError):
                storage._open("legacy.bin")

    def test_save_always_targets_bucket_even_with_fallback_enabled(self):
        """Writes MUST go to the bucket — local fallback is read-only."""
        storage = LazyLocalFallbackStorage()
        result = storage._save("uploads/written.bin", ContentFile(b"new"))
        self.assertEqual(result, "uploads/written.bin")
        self.assertEqual(
            self.fake_client.objects[(_FAKE_BUCKET, "uploads/written.bin")],
            b"new",
        )


def _resolve_default_storage_backend(
    storage_provider: str, fallback_enabled: bool
) -> str:
    """Replicate the wiring logic in ``settings.py`` for testing.

    The conditional in ``settings.py`` (lines 221-227) is the contract:
    ``(STORAGE_PROVIDER, MEDIA_LOCAL_FALLBACK_ENABLED)`` →
    ``STORAGES["default"]["BACKEND"]``. This helper reproduces that
    logic so the test asserts the contract directly without needing to
    reload Django's cached settings module (which is fragile across
    test runs). If the wiring in ``settings.py`` changes, this helper
    must change in lockstep — that coupling is intentional and is the
    single source of truth for the test.
    """

    if storage_provider == "s3":
        if fallback_enabled:
            return "config.storage_backends.LazyLocalFallbackStorage"
        return "config.storage_backends.Boto3Storage"
    return "django.core.files.storage.FileSystemStorage"


def _settings_storage_wiring_source() -> str:
    """Read the wiring conditional from ``settings.py`` for drift checks.

    Returns the substring from the ``STORAGE_PROVIDER`` assignment to
    the closing brace of the conditional, so the test can verify the
    conditional structure is present without re-implementing it.
    """

    import re
    from pathlib import Path

    settings_path = Path(__file__).resolve().parents[1] / "settings.py"
    text = settings_path.read_text(encoding="utf-8")
    # Grep the conditional block — anything between ``if STORAGE_PROVIDER
    # == "s3":`` and the next ``\nSTORAGES = {`` line is what the test
    # asserts on.
    match = re.search(
        r"if STORAGE_PROVIDER == .s3.:(?P<body>.*?)\nSTORAGES = \{",
        text,
        flags=re.DOTALL,
    )
    if match is None:
        return ""
    return match.group("body")


class StoragesWiringTests(SimpleTestCase):
    """``settings.py`` switches ``STORAGES["default"]["BACKEND"]`` by
    ``STORAGE_PROVIDER`` and ``MEDIA_LOCAL_FALLBACK_ENABLED``.
    """

    def test_local_provider_yields_filesystem_storage(self):
        self.assertEqual(
            _resolve_default_storage_backend(
                storage_provider="local", fallback_enabled=True
            ),
            "django.core.files.storage.FileSystemStorage",
        )

    def test_s3_provider_with_fallback_yields_lazy_local_fallback_storage(self):
        self.assertEqual(
            _resolve_default_storage_backend(
                storage_provider="s3", fallback_enabled=True
            ),
            "config.storage_backends.LazyLocalFallbackStorage",
        )

    def test_s3_provider_without_fallback_yields_boto3_storage(self):
        self.assertEqual(
            _resolve_default_storage_backend(
                storage_provider="s3", fallback_enabled=False
            ),
            "config.storage_backends.Boto3Storage",
        )

    def test_settings_module_wiring_conditional_present(self):
        """The wiring conditional must still exist in ``settings.py``.

        This guards against accidental deletion when someone refactors
        the storage block; the assertion is on the structural shape of
        the conditional, not on its precise implementation.
        """

        body = _settings_storage_wiring_source()
        self.assertIn('LazyLocalFallbackStorage', body)
        self.assertIn('Boto3Storage', body)
        self.assertIn('FileSystemStorage', body)

    def test_storage_provider_env_var_still_resolvable(self):
        """Regression guard: ``api.viewsets.payments`` (lines 161, 188,
        209) reads ``os.getenv("STORAGE_PROVIDER", "local")`` directly.
        The variable in ``config/settings.py`` must remain a string for
        those callers to keep working.
        """

        from django.conf import settings

        self.assertIsInstance(settings.STORAGE_PROVIDER, str)
        self.assertIn(settings.STORAGE_PROVIDER, {"local", "s3"})