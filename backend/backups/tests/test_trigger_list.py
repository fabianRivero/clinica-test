"""Integration tests for the trigger and list backup endpoints.

Covers:

* trigger streams a download + writes a ``trigger_download`` audit row;
* trigger rate-limit returns 429 + a ``RATE_LIMIT_DENIED`` audit row on
  the second consecutive POST within 60s;
* list returns JSON sorted by ``modified_at`` descending.

Tests use Django ``Client`` against the in-memory sqlite test DB and
a temporary ``BACKUPS_DIR`` so they do not touch the real backups tree.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario
from backups.models import BackupAuditLog


def _fresh_dir(name: str) -> Path:
    """Create (or reset) a temp directory for a single test class."""
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


@override_settings(
    BACKUPS_DIR="/tmp/_unused_trigger_list_setup",
    BACKUP_DAILY_KEEP=7,
    BACKUP_WEEKLY_KEEP=4,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class TriggerListEndpointTests(TestCase):
    """Shared setUp: roles, users, temp BACKUPS_DIR, fake dump."""

    def setUp(self) -> None:
        cache.clear()
        self.tmp = _fresh_dir("_backup_trigger_list_test")
        self.override = override_settings(
            BACKUPS_DIR=str(self.tmp),
            BACKUP_DAILY_KEEP=7,
            BACKUP_WEEKLY_KEEP=4,
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

        def fake_dump(target, db_config=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"FAKE-DUMP-BYTES")

        self._dump_patch = mock.patch(
            "backups.services._dump_to_path", side_effect=fake_dump
        )
        self._dump_patch.start()

    def tearDown(self) -> None:
        self._dump_patch.stop()
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

    # -- trigger ---------------------------------------------------------

    def test_trigger_streams_dump_and_writes_audit(self):
        c = self._login(self.principal)
        response = c.post("/api/admin/backups/trigger/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".dump", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"FAKE-DUMP-BYTES")
        self.assertEqual(
            BackupAuditLog.objects.filter(
                action=BackupAuditLog.Action.TRIGGER_DOWNLOAD,
            ).count(),
            1,
        )

    def test_trigger_rate_limit_returns_429_on_second_hit(self):
        c = self._login(self.principal)
        first = c.post("/api/admin/backups/trigger/")
        second = c.post("/api/admin/backups/trigger/")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(
            BackupAuditLog.objects.filter(
                action=BackupAuditLog.Action.TRIGGER_DOWNLOAD
            ).count(),
            1,
        )
        self.assertEqual(
            BackupAuditLog.objects.filter(
                action=BackupAuditLog.Action.RATE_LIMIT_DENIED
            ).count(),
            1,
        )

    # -- list ------------------------------------------------------------

    def test_list_returns_seeded_files_sorted(self):
        names = [
            "clinica_2026-08-01_120000.dump",
            "clinica_2026-08-02_120000.dump",
            "clinica_2026-08-03_120000.weekly.dump",
        ]
        mtimes = [1_700_000_000, 1_700_086_400, 1_700_172_800]
        for name, mtime in zip(names, mtimes):
            p = self.tmp / name
            p.write_bytes(b"x")
            os.utime(p, (mtime, mtime))

        c = self._login(self.principal)
        response = c.get("/api/admin/backups/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("results", payload)
        result_names = [r["name"] for r in payload["results"]]
        # Weekly (newest mtime) must be first.
        self.assertEqual(result_names[0], "clinica_2026-08-03_120000.weekly.dump")
        self.assertEqual(len(result_names), 3)
        for row in payload["results"]:
            self.assertEqual(
                set(row.keys()),
                {"id", "name", "size", "modified_at", "is_weekly"},
            )