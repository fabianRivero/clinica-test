"""Tests for the ``create_backup`` management command."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from backups.models import BackupAuditLog
from backups.services import (
    BACKUP_FILENAME_RE,
    BackupAlreadyRunningError,
    BackupService,
)


@override_settings(BACKUPS_DIR="/tmp/_unused_cmd_dir")
class CreateBackupCommandTests(TestCase):
    """End-to-end invocation of ``python manage.py create_backup``."""

    def setUp(self):
        self.tmp = Path("/tmp/_create_backup_cmd_test").resolve()
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

    def test_command_creates_file_and_audit_row(self):
        out = StringIO()
        err = StringIO()

        def fake_dump(target, db_config=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"FAKE-CMD-DUMP")

        with override_settings(BACKUPS_DIR=str(self.tmp)), \
             mock.patch(
                 "backups.services._dump_to_path",
                 side_effect=fake_dump,
             ):
            call_command("create_backup", stdout=out, stderr=err)

        produced = list(self.tmp.glob("clinica_*.dump"))
        self.assertEqual(len(produced), 1, msg=f"dir contents: {list(self.tmp.iterdir())}")
        self.assertTrue(BACKUP_FILENAME_RE.match(produced[0].name))

        rows = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.TRIGGER_DOWNLOAD,
        )
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.filename, produced[0].name)
        self.assertEqual(row.metadata.get("actor"), "system:cron")
        self.assertIn(str(produced[0]), out.getvalue())

    def test_command_accepts_actor_label_override(self):
        out = StringIO()

        def fake_dump(target, db_config=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"FAKE-CMD-DUMP")

        with override_settings(BACKUPS_DIR=str(self.tmp)), \
             mock.patch(
                 "backups.services._dump_to_path",
                 side_effect=fake_dump,
             ):
            call_command(
                "create_backup",
                "--actor-label",
                "system:test",
                stdout=out,
            )

        row = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.TRIGGER_DOWNLOAD,
        ).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.metadata.get("actor"), "system:test")

    def test_command_failure_writes_failure_audit_row(self):
        err = StringIO()
        out = StringIO()

        def boom(target, db_config=None):
            raise FileNotFoundError("pg_dump missing")

        with override_settings(BACKUPS_DIR=str(self.tmp)), \
             mock.patch("backups.services._dump_to_path", side_effect=boom):
            with self.assertRaises(CommandError):
                call_command("create_backup", stdout=out, stderr=err)

        failure_rows = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.TRIGGER_FAILED,
        )
        self.assertEqual(failure_rows.count(), 1)

    def test_command_lock_contention_exits_nonzero(self):
        err = StringIO()
        out = StringIO()

        with override_settings(BACKUPS_DIR=str(self.tmp)), \
             mock.patch.object(
                 BackupService,
                 "create_backup",
                 side_effect=BackupAlreadyRunningError("Ya hay un respaldo en curso."),
             ):
            with self.assertRaises(CommandError) as ctx:
                call_command("create_backup", stdout=out, stderr=err)

        # Django's CommandError exposes ``returncode`` only when invoked
        # from the CLI; in-process, the exception itself carries the
        # contract — we just confirm it fired and the audit row exists.
        self.assertIn("progress", str(ctx.exception).lower())
        denial_rows = BackupAuditLog.objects.filter(
            action=BackupAuditLog.Action.TRIGGER_FAILED,
        )
        self.assertEqual(denial_rows.count(), 1)