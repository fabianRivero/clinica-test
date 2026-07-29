"""Forward/backward migration smoke tests.

We rely on Django's test infrastructure to call ``migrate`` for each
direction. The tests verify the biometric-specific schema is in place
after ``migrate`` and that the rollback removes it cleanly.
"""

from __future__ import annotations

import unittest

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase


MIGRATION_FORWARD_TARGETS = (
    "biometric_agent_tokens",
    "biometric_attempts",
)


class BiometricMigrationsForwardTests(TransactionTestCase):
    """Fresh DB runs every test, so we go straight to the latest state."""

    def test_tables_exist(self):
        existing = set(connection.introspection.table_names())
        for table in MIGRATION_FORWARD_TARGETS:
            self.assertIn(table, existing, msg=f"{table!r} should exist")

    def test_indexes_present(self):
        with connection.cursor() as cursor:
            table_name = "biometric_attempts"
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name=%s",
                [table_name],
            )
            names = {row[0] for row in cursor.fetchall()}
        # Auto-named indexes (sqlite_autoindex_* for unique constraints)
        # plus the two we explicitly named.
        self.assertTrue(
            any("biometric_atts_cita_created" in n for n in names),
            f"cita+created_at index missing. Found: {names}",
        )
        self.assertTrue(
            any("biometric_atts_cliente_op" in n for n in names),
            f"cliente+operation index missing. Found: {names}",
        )


class BiometricMigrationsBackwardTests(TransactionTestCase):
    """Roll back to a state before the biometric migrations; tables gone."""

    def test_rollback_removes_tables(self):
        # Migrate backward to the state just before the biometric
        # migrations, then verify tables no longer exist.
        try:
            call_command("migrate", "biometric", "zero", verbosity=0)
            existing = set(connection.introspection.table_names())
            for table in MIGRATION_FORWARD_TARGETS:
                self.assertNotIn(table, existing)
        finally:
            # Restore forward state so other tests can run.
            call_command("migrate", verbosity=0)
