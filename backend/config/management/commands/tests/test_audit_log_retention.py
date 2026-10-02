"""Tests for ``audit_log_retention`` management command (slice 4)."""

from __future__ import annotations

import os
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_USE_LOCAL_DB", "1")
os.environ.setdefault("AWS_STORAGE_BUCKET_NAME", "test-bucket")
import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402

from audit.models import AuditLog  # noqa: E402


class AuditLogRetentionTests(TestCase):
    def _make(self, days_ago: int) -> AuditLog:
        return AuditLog.objects.create(
            user=None,
            user_role="CLIENTE",
            action=AuditLog.Action.SIGNED_URL_ISSUED,
            resource_path=f"fichas_clinicas/2026/10/old-{days_ago}.pdf",
            resource_type="clinical.FichaClinica.documento_escaneado_pdf",
            client_ip="127.0.0.1",
            user_agent="test",
            expires_at=None,
        )

    def test_deletes_rows_older_than_cutoff(self):
        old = self._make(days_ago=100)
        AuditLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=100)
        )
        call_command("audit_log_retention", "--days=90")
        self.assertFalse(AuditLog.objects.filter(pk=old.pk).exists())

    def test_keeps_rows_newer_than_cutoff(self):
        fresh = self._make(days_ago=10)
        AuditLog.objects.filter(pk=fresh.pk).update(
            created_at=timezone.now() - timedelta(days=10)
        )
        call_command("audit_log_retention", "--days=90")
        self.assertTrue(AuditLog.objects.filter(pk=fresh.pk).exists())
