"""Unit tests for the backups service.

Covers filename validation, path-traversal rejection, retention,
engine-branching (PostgreSQL + sqlite3) and the fcntl dump lock.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from backups import services
from backups.models import BackupAuditLog
from backups.services import (
    BACKUP_FILENAME_RE,
    BackupAlreadyRunningError,
    BackupService,
    BackupServiceError,
    _safe_path,
    apply_retention,
    validate_filename,
)


# ---------------------------------------------------------------------------
# Filename validation
# ---------------------------------------------------------------------------


class FilenameValidationTests(SimpleTestCase):
    def test_accepts_canonical_filename(self):
        self.assertTrue(validate_filename("clinica_2026-08-06_120000.dump"))

    def test_accepts_weekly_filename(self):
        self.assertTrue(validate_filename("clinica_2026-08-06_120000.weekly.dump"))

    def test_rejects_empty(self):
        self.assertFalse(validate_filename(""))

    def test_rejects_traversal(self):
        self.assertFalse(validate_filename("../etc/passwd"))
        self.assertFalse(validate_filename(".."))
        self.assertFalse(validate_filename("clinica_2026-08-06_120000.dump.bak"))

    def test_rejects_absolute_path(self):
        self.assertFalse(validate_filename("/etc/passwd"))

    def test_rejects_weird_chars(self):
        self.assertFalse(validate_filename("clinica_2026-08-06_120000.dump; rm -rf"))
        self.assertFalse(validate_filename("clinica_2026-08-06_120000.dump\n"))
        self.assertFalse(validate_filename("clinica 2026-08-06_120000.dump"))
        self.assertFalse(validate_filename("clinica_2026-08-06_120000.DUMP"))

    def test_rejects_wrong_prefix(self):
        self.assertFalse(validate_filename("foo_2026-08-06_120000.dump"))
        self.assertFalse(validate_filename("clinicaX2026-08-06_120000.dump"))

    def test_rejects_when_weekly_in_wrong_place(self):
        self.assertFalse(validate_filename("clinica_weekly_2026-08-06_120000.dump"))


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


class SafePathTests(SimpleTestCase):
    def test_safe_path_rejects_traversal_payload(self):
        with self.assertRaises(ValueError):
            _safe_path(Path("/tmp/backups"), "../etc/passwd")

    def test_safe_path_rejects_absolute(self):
        with self.assertRaises(ValueError):
            _safe_path(Path("/tmp/backups"), "/etc/passwd")

    def test_safe_path_rejects_non_matching(self):
        with self.assertRaises(ValueError):
            _safe_path(Path("/tmp/backups"), "not_a_backup.dump")

    def test_safe_path_returns_resolved_under_root(self):
        tmp = Path("/tmp/abc_backups_test").resolve()
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            result = _safe_path(tmp, "clinica_2026-08-06_120000.dump")
            self.assertEqual(result, tmp / "clinica_2026-08-06_120000.dump")
            self.assertTrue(str(result).startswith(str(tmp)))
        finally:
            for f in tmp.glob("*"):
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
            tmp.rmdir()


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


@override_settings(
    BACKUPS_DIR=Path("/tmp/_unused_retention_dir"),
    BACKUP_KEEP_DAILY=2,
    BACKUP_KEEP_WEEKLY=1,
)
class RetentionTests(SimpleTestCase):
    """Retention is a pure function over the filesystem; SimpleTestCase
    keeps the suite fast and avoids touching the test database."""

    def setUp(self):
        self.tmp = Path("/tmp/_retention_test_dir").resolve()
        if self.tmp.exists():
            for f in self.tmp.glob("*"):
                f.unlink()
        self.tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for f in self.tmp.glob("*"):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        self.tmp.rmdir()

    def _touch(self, name: str, mtime: int) -> Path:
        p = self.tmp / name
        p.write_bytes(b"x")
        os.utime(p, (mtime, mtime))
        return p

    def test_keeps_only_configured_daily_and_weekly(self):
        for i in range(4):
            self._touch(f"clinica_2026-08-0{i + 1}_12000{i}.dump", 1_700_000_000 + i)
        for i in range(3):
            self._touch(
                f"clinica_2026-07-2{i + 1}_120000.weekly.dump",
                1_700_000_000 + 10 + i,
            )

        pruned = apply_retention(self.tmp, keep_daily=2, keep_weekly=1)

        self.assertEqual(len(pruned), 4)
        remaining = sorted(p.name for p in self.tmp.glob("clinica_*.dump"))
        self.assertEqual(len(remaining), 3)

    def test_returns_empty_when_under_threshold(self):
        for i in range(2):
            self._touch(f"clinica_2026-08-0{i + 1}_12000{i}.dump", 1_700_000_000 + i)
        pruned = apply_retention(self.tmp, keep_daily=2, keep_weekly=1)
        self.assertEqual(pruned, [])

    def test_handles_missing_directory(self):
        missing = Path("/tmp/_definitely_missing_dir_xyz")
        if missing.exists():
            missing.rmdir()
        self.assertEqual(apply_retention(missing, keep_daily=2, keep_weekly=1), [])


# ---------------------------------------------------------------------------
# Engine branching
# ---------------------------------------------------------------------------


@override_settings(
    BACKUPS_DIR="/tmp/_unused_dump_branching_dir",
)
class EngineBranchingTests(SimpleTestCase):
    def test_postgresql_branch_constructs_pg_dump_argv(self):
        target = Path("/tmp/pg_test.dump")
        if target.exists():
            target.unlink()

        def fake_run(cmd, *args, **kwargs):
            tmp = Path(cmd[cmd.index("-f") + 1])
            tmp.write_bytes(b"FAKE-PG-DUMP")
            return mock.Mock(returncode=0)

        try:
            with mock.patch.object(services.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(services.shutil, "disk_usage"), \
                 mock.patch.dict(os.environ, {"DJANGO_DB_PASSWORD": "secret"},
                                  clear=False):
                with override_settings(DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.postgresql",
                        "HOST": "db", "PORT": "5432",
                        "USER": "clinica", "NAME": "clinica",
                    }
                }):
                    services._dump_to_path(
                        target,
                        db_config={
                            "ENGINE": "django.db.backends.postgresql",
                            "HOST": "db", "PORT": "5432",
                            "USER": "clinica", "NAME": "clinica",
                        },
                    )
            self.assertTrue(target.exists())
        finally:
            for p in (target, Path(str(target) + ".tmp")):
                if p.exists():
                    p.unlink()

    def test_sqlite_branch_constructs_sqlite3_backup(self):
        target = Path("/tmp/sqlite_test.dump")
        if target.exists():
            target.unlink()

        def fake_run(cmd, *args, **kwargs):
            import re
            m = re.search(r"'(.+?)'", cmd[2])
            tmp = Path(m.group(1))
            tmp.write_bytes(b"FAKE-SQLITE-BACKUP")
            return mock.Mock(returncode=0)

        try:
            with mock.patch.object(services.subprocess, "run", side_effect=fake_run):
                services._dump_to_path(
                    target,
                    db_config={
                        "ENGINE": "django.db.backends.sqlite3",
                        "NAME": "/tmp/test_db.sqlite3",
                    },
                )
            self.assertTrue(target.exists())
        finally:
            for p in (target, Path(str(target) + ".tmp")):
                if p.exists():
                    p.unlink()

    def test_unsupported_engine_raises(self):
        target = Path("/tmp/unknown.dump")
        with self.assertRaises(BackupServiceError):
            services._dump_to_path(
                target,
                db_config={"ENGINE": "django.db.backends.mysql", "NAME": "x"},
            )


# ---------------------------------------------------------------------------
# Lock contention
# ---------------------------------------------------------------------------


@override_settings(BACKUPS_DIR="/tmp/_unused_lock_dir")
class LockContentionTests(SimpleTestCase):
    def test_second_invocation_raises_when_lock_held(self):
        svc = BackupService(backups_dir=Path("/tmp/_lock_test_dir"))
        try:
            svc.backups_dir.mkdir(parents=True, exist_ok=True)
            ctx = services._with_dump_lock(svc.backups_dir)
            ctx.__enter__()
            try:
                with self.assertRaises(BackupAlreadyRunningError):
                    with services._with_dump_lock(svc.backups_dir):
                        pass
            finally:
                ctx.__exit__(None, None, None)
        finally:
            for f in svc.backups_dir.glob("*"):
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
            svc.backups_dir.rmdir()


# ---------------------------------------------------------------------------
# create_backup — happy path uses sqlite (no pg_dump on CI).
# ---------------------------------------------------------------------------


@override_settings(
    BACKUPS_DIR="/tmp/_unused_create_dir",
    BACKUP_KEEP_DAILY=7,
    BACKUP_KEEP_WEEKLY=4,
)
class CreateBackupHappyPathTests(TestCase):
    def setUp(self):
        self.tmp = Path("/tmp/_create_backup_test_dir").resolve()
        if self.tmp.exists():
            for f in self.tmp.glob("*"):
                f.unlink()
        else:
            self.tmp.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for f in self.tmp.glob("*"):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        self.tmp.rmdir()

    def test_create_backup_writes_audit_and_file(self):
        from accounts.models import Usuario

        user = Usuario.objects.create_user(
            username="principal",
            password="test",
            primer_nombre="Test",
            apellido_paterno="Principal",
        )

        def fake_dump(target, db_config=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"FAKE-DUMP")

        svc = BackupService(backups_dir=self.tmp, daily_keep=7, weekly_keep=4)
        with mock.patch.object(services, "_dump_to_path", side_effect=fake_dump):
            target = svc.create_backup(actor="user:1", user=user)

        self.assertTrue(target.exists())
        self.assertTrue(BACKUP_FILENAME_RE.match(target.name))

        rows = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.TRIGGER_DOWNLOAD,
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.user, user)
        self.assertEqual(row.filename, target.name)

    def test_create_backup_prunes_and_audits(self):
        # Pre-seed 9 daily files (keep_daily=2) and 3 weekly (keep_weekly=1).
        for i in range(9):
            p = self.tmp / f"clinica_2026-07-{i + 1:02d}_00000{i}.dump"
            p.write_bytes(b"x")
        for i in range(3):
            p = self.tmp / f"clinica_2026-06-{i + 1:02d}_00000{i}.weekly.dump"
            p.write_bytes(b"x")

        def fake_dump(target, db_config=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"FAKE-DUMP")

        svc = BackupService(backups_dir=self.tmp, daily_keep=2, weekly_keep=1)
        with mock.patch.object(services, "_dump_to_path", side_effect=fake_dump):
            target = svc.create_backup(actor="system:cron")

        # After create_backup: 9 + 1 = 10 dailies (keep 2 → prune 8) +
        # 3 weeklies (keep 1 → prune 2). Total prune rows = 10.
        pruned_rows = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.RETENTION_PRUNE,
        )
        self.assertEqual(pruned_rows.count(), 10)
        self.assertTrue(target.exists())

    def test_filename_is_weekly_on_sunday(self):
        """When called with weekly=True the filename carries the .weekly suffix."""
        from datetime import datetime, timezone

        sunday_filename = BackupService._build_filename(
            datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc),
            weekly=True,
        )
        self.assertTrue(sunday_filename.endswith(".weekly.dump"))