"""Integration tests for the download and delete backup endpoints.

Covers:

* filename regex rejects weird names (spaces, ``;``, ``..``, suffixes);
* path-traversal attempt (``..`` as the literal filename segment)
  returns 404 with a ``DOWNLOAD_DENIED`` audit row;
* download streams the expected bytes + writes a
  ``download_server_backup`` audit row;
* delete returns 204, removes the file, writes a
  ``delete_server_backup`` audit row, and the file disappears from
  subsequent lists;
* delete rate-limit returns 429 on the second consecutive DELETE
  within 10s.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario
from backups.models import BackupAuditLog


def _fresh_dir(name: str) -> Path:
    p = Path(f"/tmp/{name}").resolve()
    if p.exists():
        for f in p.glob("*"):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
    else:
        p.mkdir(parents=True, exist_ok=True)
    return p


def _audit_count(action: str, filename: str | None = None) -> int:
    qs = BackupAuditLog.objects.filter(action=action)
    if filename is not None:
        qs = qs.filter(filename=filename)
    return qs.count()


@override_settings(
    BACKUPS_DIR="/tmp/_unused_download_delete_setup",
    BACKUP_KEEP_DAILY=7,
    BACKUP_KEEP_WEEKLY=4,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class DownloadDeleteEndpointTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.tmp = _fresh_dir("_backup_download_delete_test")
        self.override = override_settings(
            BACKUPS_DIR=str(self.tmp),
            BACKUP_KEEP_DAILY=7,
            BACKUP_KEEP_WEEKLY=4,
            CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        )
        self.override.enable()

        self.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.principal = Usuario.objects.create_user(
            username="principal",
            password="x",
            primer_nombre="P",
            apellido_paterno="Principal",
            rol=self.rol_principal,
        )

    def tearDown(self) -> None:
        self.override.disable()
        cache.clear()
        for f in self.tmp.glob("*"):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        self.tmp.rmdir()

    def _login(self, user) -> Client:
        c = Client(enforce_csrf_checks=False)
        c.force_login(user)
        return c

    def _seed(self, name: str, body: bytes = b"HELLO") -> Path:
        p = self.tmp / name
        p.write_bytes(body)
        return p

    # -- download -------------------------------------------------------

    def test_download_rejects_traversal_payload_with_404(self):
        c = self._login(self.principal)
        # The filename regex rejects any ``..`` segment, so even the
        # bare string ``..`` proves the traversal guard.
        response = c.get("/api/admin/backups/../download/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            _audit_count(BackupAuditLog.Action.DOWNLOAD_DENIED),
            1,
        )

    def test_download_rejects_weird_filenames(self):
        c = self._login(self.principal)
        for bad in [
            "clinica_2026-08-06_120000.dump; rm -rf",
            "..",
            "clinica_2026-08-06_120000.dump.bak",
            "foo..bar",
        ]:
            cache.clear()  # avoid 30s per-user rate-limit collisions
            with self.subTest(name=bad):
                response = c.get(
                    f"/api/admin/backups/{bad}/download/"
                )
                self.assertEqual(response.status_code, 404, msg=bad)

    def test_download_streams_real_file_and_audits(self):
        seeded = self._seed("clinica_2026-08-06_120000.dump", b"HELLO")
        c = self._login(self.principal)
        response = c.get(f"/api/admin/backups/{seeded.name}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            b"".join(response.streaming_content), b"HELLO"
        )
        self.assertEqual(
            _audit_count(
                BackupAuditLog.Action.DOWNLOAD_SERVER_BACKUP, seeded.name
            ),
            1,
        )

    # -- delete ---------------------------------------------------------

    def test_delete_removes_file_and_audits(self):
        seeded = self._seed("clinica_2026-08-06_120000.dump")
        c = self._login(self.principal)
        response = c.delete(f"/api/admin/backups/{seeded.name}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(seeded.exists())
        self.assertEqual(
            _audit_count(
                BackupAuditLog.Action.DELETE_SERVER_BACKUP, seeded.name
            ),
            1,
        )

    def test_deleted_file_no_longer_in_list(self):
        seeded = self._seed("clinica_2026-08-06_120000.dump")
        c = self._login(self.principal)
        self.assertEqual(
            c.delete(f"/api/admin/backups/{seeded.name}/").status_code,
            204,
        )
        cache.clear()  # list endpoint is not rate-limited
        listed = c.get("/api/admin/backups/").json()["results"]
        self.assertEqual([r["name"] for r in listed], [])

    def test_delete_rate_limit_returns_429(self):
        for name in [
            "clinica_2026-08-06_120000.dump",
            "clinica_2026-08-06_120001.dump",
        ]:
            self._seed(name)
        c = self._login(self.principal)
        first = c.delete("/api/admin/backups/clinica_2026-08-06_120000.dump/")
        second = c.delete("/api/admin/backups/clinica_2026-08-06_120001.dump/")
        self.assertEqual(first.status_code, 204)
        self.assertEqual(second.status_code, 429)