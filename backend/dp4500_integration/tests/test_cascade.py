"""Tests for the cascade signal + Celery task + reconcile command.

Phase 2 of dp4500-host-app-integration-phase2. Uses httpx.MockTransport
to simulate DP4500 responses. Test settings have
``CELERY_TASK_ALWAYS_EAGER=True`` so ``.delay()`` runs synchronously.
"""
from __future__ import annotations

import json
import threading
from unittest import mock

import httpx
from django.db.utils import IntegrityError
from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from dp4500_integration.client import HTTPClient
from dp4500_integration.models import (
    BiometricEnrollmentRecord,
    PendingCascade,
)
from dp4500_integration.tasks import (
    _cascade_revoke_template_on_failure,
    cascade_revoke_template,
)


# --------------------------------------------------------------------------
# PendingCascade lifecycle
# --------------------------------------------------------------------------


class PendingCascadeLifecycleTests(TestCase):
    def test_pending_cascade_defaults_to_pending(self):
        pc = PendingCascade.objects.create(
            user_external_id="11111111-2222-3333-4444-555555555555",
            sucursal_id=42,
        )
        self.assertEqual(pc.status, PendingCascade.STATUS_PENDING)
        self.assertEqual(pc.attempts, 0)
        self.assertEqual(pc.last_error_code, "")
        self.assertIsNone(pc.completed_at)
        self.assertIsNone(pc.last_attempt_at)


# --------------------------------------------------------------------------
# Cascade signal fires on User.delete
# --------------------------------------------------------------------------


class CascadeSignalTests(TestCase):
    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre="Suc-Cascade")
        rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
        self.rol = rol

    def test_every_user_delete_creates_pending_cascade(self):
        """The pre_save signal mints a UUID on first INSERT; every Usuario
        therefore has a biometric_external_id by the time it is deleted.
        The post_delete cascade fires unconditionally for every delete.

        (Originally the test asserted ``objects.count() == 0`` assuming
        the signal would skip when biometric_external_id was None — but
        Commit 1's pre_save signal ensures every User has a UUID on
        first save. The cascade is therefore always triggered.)
        """
        u = Usuario(
            username="any_user",
            primer_nombre="Alice",
            apellido_paterno="Test",
            rol=self.rol,
            sucursal=self.sucursal,
        )
        u.set_password("Sup3rSecret!")
        u.save()
        self.assertIsNotNone(u.biometric_external_id)

        with mock.patch(
            "dp4500_integration.tasks.HTTPClient",
        ) as mock_client_class:
            mock_client_class.return_value.delete_template.return_value = None
            u.delete()

        self.assertEqual(PendingCascade.objects.count(), 1)

    def test_user_with_biometric_external_id_creates_pending_row(self):
        u = Usuario(
            username="with_bio",
            primer_nombre="Bob",
            apellido_paterno="Test",
            rol=self.rol,
            sucursal=self.sucursal,
        )
        u.set_password("Sup3rSecret!")
        u.save()
        self.assertIsNotNone(u.biometric_external_id)
        ext_id = u.biometric_external_id

        # Patch the HTTPClient at the call-site so we don't make real
        # network calls, AND patch the captured task reference at the
        # signal import-site so ``.delay()`` does not touch the broker.
        # Even with ``CELERY_TASK_ALWAYS_EAGER=True``, ``.delay()`` on a
        # ``bind=True`` task with the filesystem broker still attempts
        # a connection — patching ``.delay`` directly makes the test
        # hermetic. The cascade task's effect on the row is verified
        # in ``CascadeTaskOutcomeTests``; here we only assert the
        # signal side (row created, .delay called with right args).
        with mock.patch(
            "dp4500_integration.tasks.HTTPClient",
        ) as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.delete_template.return_value = None
            with mock.patch(
                "dp4500_integration.signals.cascade_revoke_template.delay",
            ) as mock_delay:
                u.delete()

        self.assertEqual(PendingCascade.objects.count(), 1)
        row = PendingCascade.objects.first()
        self.assertEqual(str(row.user_external_id), str(ext_id))
        self.assertEqual(row.sucursal_id, self.sucursal.id)
        # The signal enqueued the task with the right payload.
        mock_delay.assert_called_once_with(str(ext_id), self.sucursal.id)
        # Row is PENDING at this point because we intercepted .delay();
        # the row's terminal status is asserted by the
        # ``CascadeTaskOutcomeTests`` class via ``cascade_revoke_template.run(...)``.
        self.assertEqual(row.status, PendingCascade.STATUS_PENDING)

    def test_user_without_biometric_external_id_is_no_op(self):
        """WU-2A6.1 (closes verify-report PARTIAL G1 / spec §6.6).

        When ``biometric_external_id is NULL``, the post_delete signal
        must short-circuit without inserting a ``PendingCascade`` row and
        without enqueueing the Celery task. See
        ``signals.py:32-33``.
        """
        u = Usuario(
            username="no_bio_user",
            primer_nombre="Dan",
            apellido_paterno="Nullbio",
            rol=self.rol,
            sucursal=self.sucursal,
        )
        u.set_password("Sup3rSecret!")
        u.save()
        # ``assign_biometric_external_id`` minted a UUID on first save;
        # bypass it by writing through the queryset manager (no signals
        # fired on ``.update()``).
        Usuario.objects.filter(pk=u.pk).update(biometric_external_id=None)
        u.refresh_from_db()
        self.assertIsNone(u.biometric_external_id)

        # Patch the bound ``.delay`` attribute on the task module — NOT
        # the module itself — because ``signals.py`` captures
        # ``cascade_revoke_template`` at import time and calls
        # ``.delay(...)`` on the captured reference.
        with mock.patch(
            "dp4500_integration.signals.cascade_revoke_template.delay",
        ) as mock_delay:
            u.delete()

        self.assertEqual(PendingCascade.objects.count(), 0)
        mock_delay.assert_not_called()

    def test_sync_insert_failure_does_not_rollback_local_delete(self):
        """WU-2A6.2 (closes verify-report PARTIAL G2 / spec §6.7).

        When ``PendingCascade.objects.create(...)`` raises
        ``IntegrityError`` the signal handler must log at ERROR level
        and let the local User delete commit; the Celery task must NOT
        be enqueued. See ``signals.py:48`` (broad ``except Exception``
        on the sync insert block).
        """
        u = Usuario(
            username="sync_fail_user",
            primer_nombre="Eve",
            apellido_paterno="Test",
            rol=self.rol,
            sucursal=self.sucursal,
        )
        u.set_password("Sup3rSecret!")
        u.save()
        self.assertIsNotNone(u.biometric_external_id)
        user_pk = u.pk

        # Patch at the import-site used by ``signals.py`` — NOT the
        # model class. ``signals.py`` calls
        # ``PendingCascade.objects.create(...)`` so the patch must be
        # attached to the same manager.
        with mock.patch(
            "dp4500_integration.signals.PendingCascade.objects.create",
            side_effect=IntegrityError("unique violation"),
        ) as mock_create:
            with self.assertLogs(
                "dp4500_integration.signals", level="ERROR",
            ) as cm:
                with mock.patch(
                    "dp4500_integration.signals.cascade_revoke_template.delay",
                ) as mock_delay:
                    u.delete()

        # Local delete committed even though sync insert failed.
        self.assertFalse(Usuario.objects.filter(pk=user_pk).exists())
        self.assertEqual(PendingCascade.objects.count(), 0)
        mock_delay.assert_not_called()
        mock_create.assert_called_once()
        # The ERROR log fires from ``signals.py:49-54`` with the
        # prefix ``"Failed to record PendingCascade for
        # user_external_id="`` — match the unique trailing fragment
        # ``"Cascade will not run"`` which is fixed in the source.
        self.assertTrue(
            any(
                "Cascade will not run" in record.getMessage()
                for record in cm.records
            ),
            f"Expected an ERROR log mentioning 'Cascade will not run', "
            f"got: {[r.getMessage() for r in cm.records]}",
        )


# --------------------------------------------------------------------------
# Cascade task outcome classification
# --------------------------------------------------------------------------


def _patch_dp4500_with_handler(handler):
    """Patch the HTTPClient in tasks._do_cascade to use a MockTransport."""
    def _factory(*args, **kwargs):
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: "SeK_test",
        )
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        return client
    return mock.patch(
        "dp4500_integration.tasks.HTTPClient",
        side_effect=_factory,
    )


class CascadeTaskOutcomeTests(TestCase):
    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre="Suc-Outcomes")
        self.pending = PendingCascade.objects.create(
            user_external_id="11111111-2222-3333-4444-555555555555",
            sucursal_id=self.sucursal.id,
        )

    def test_204_marks_completed(self):
        def handler(request):
            return httpx.Response(204, request=request)
        with _patch_dp4500_with_handler(handler):
            cascade_revoke_template.run(
                str(self.pending.user_external_id), self.pending.sucursal_id,
            )
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingCascade.STATUS_COMPLETED)
        self.assertIsNotNone(self.pending.completed_at)

    def test_404_is_idempotent_completed(self):
        def handler(request):
            return httpx.Response(
                404, json={"code": "not_found"}, request=request,
            )
        with _patch_dp4500_with_handler(handler):
            cascade_revoke_template.run(
                str(self.pending.user_external_id), self.pending.sucursal_id,
            )
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingCascade.STATUS_COMPLETED)

    def test_503_BIOMETRIC_SUSPENDED_marks_suspended_no_retry(self):
        """BiometricSuspended is caught by ``_do_cascade`` and translated
        to ``STATUS_SUSPENDED`` directly — the task returns normally
        with the row marked suspended; Celery auto-retry is NOT invoked
        (suspended is a terminal state per design §6.3).
        """
        def handler(request):
            return httpx.Response(
                503, json={"code": "BIOMETRIC_SUSPENDED"}, request=request,
            )
        with _patch_dp4500_with_handler(handler):
            cascade_revoke_template.run(
                str(self.pending.user_external_id), self.pending.sucursal_id,
            )
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingCascade.STATUS_SUSPENDED)
        # Attempts counter was incremented (the run happened once).
        self.assertEqual(self.pending.attempts, 1)
        # No auto-retry was scheduled (BiometricSuspended is terminal).
        # ``last_error_code`` defaults to empty string, not NULL.
        self.assertEqual(self.pending.last_error_code, "")

    def test_max_retries_exhausted_marks_failed(self):
        """WU-2A6.3 (closes verify-report PARTIAL G3 / spec §6.10).

        When Celery exhausts its retries, the on_failure hook must
        transition the ``PendingCascade`` row from ``pending`` to
        ``failed`` and stamp ``last_error_code`` with the
        ``celery:<exception-class>`` prefix. See ``tasks.py:113-128``.

        Invocation strategy: call the on_failure hook directly with a
        ``MaxRetriesExceededError`` instead of looping through Celery's
        broker — this isolates the hook from the in-process retry
        semantics that ``CELERY_TASK_ALWAYS_EAGER=True`` modifies.
        """
        from celery.exceptions import MaxRetriesExceededError

        from dp4500_integration.exceptions import BiometricUnavailable

        # Simulate the cascade task having attempted at least once
        # BEFORE the on_failure hook fires. The on_failure hook itself
        # does NOT increment attempts — that happens inside the task
        # body at ``tasks.py:91``. The spec asserts ``attempts == 1``
        # reflects the row state at the moment the hook runs, so we
        # bring the row to attempts=1 here.
        self.pending.attempts = 1
        self.pending.save(update_fields=["attempts"])

        # Patch the bound ``retry`` so any task-run path that touches
        # it cannot recurse; the on_failure hook itself does not call
        # ``retry``, so this is defensive.
        with mock.patch(
            "dp4500_integration.tasks.cascade_revoke_template.retry",
            side_effect=MaxRetriesExceededError("5 retries"),
        ):
            # Also patch ``HTTPClient.delete_template`` to raise the
            # exception that would have triggered the retry chain.
            with mock.patch(
                "dp4500_integration.tasks.HTTPClient.delete_template",
                side_effect=BiometricUnavailable("no_agent"),
            ):
                exc = MaxRetriesExceededError("5 retries")
                task_self = mock.Mock()
                task_self.request.retries = 5
                _cascade_revoke_template_on_failure(
                    task_self,            # self
                    exc,                  # exc
                    "test-task-id",       # task_id
                    (),                   # args
                    {                     # kwargs
                        "user_external_id": str(self.pending.user_external_id),
                        "sucursal_id": self.pending.sucursal_id,
                    },
                    None,                 # einfo
                )

        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, PendingCascade.STATUS_FAILED)
        self.assertEqual(self.pending.attempts, 1)
        self.assertTrue(
            self.pending.last_error_code.startswith("celery:"),
            f"Expected last_error_code to start with 'celery:', "
            f"got: {self.pending.last_error_code!r}",
        )


# --------------------------------------------------------------------------
# reconcile_pending_cascades management command
# --------------------------------------------------------------------------


class ReconcileCommandTests(TestCase):
    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre="Suc-Reconcile")

    def test_dry_run_does_not_modify(self):
        PendingCascade.objects.create(
            user_external_id="11111111-2222-3333-4444-555555555555",
            sucursal_id=self.sucursal.id,
            status=PendingCascade.STATUS_PENDING,
        )
        from django.core.management import call_command
        from io import StringIO

        def handler(request):
            return httpx.Response(204, request=request)

        with _patch_dp4500_with_handler(handler):
            out = StringIO()
            call_command(
                "reconcile_pending_cascades", "--dry-run", stdout=out,
            )
        # Row unchanged.
        row = PendingCascade.objects.first()
        self.assertEqual(row.status, PendingCascade.STATUS_PENDING)
        self.assertIn("[dry-run]", out.getvalue())

    def test_processes_pending_rows(self):
        for i in range(3):
            PendingCascade.objects.create(
                user_external_id=f"00000000-0000-0000-0000-{i:012d}",
                sucursal_id=self.sucursal.id,
                status=PendingCascade.STATUS_PENDING,
            )

        from django.core.management import call_command
        from io import StringIO

        def handler(request):
            return httpx.Response(204, request=request)

        with _patch_dp4500_with_handler(handler):
            out = StringIO()
            call_command("reconcile_pending_cascades", stdout=out)
        # All rows completed.
        completed = PendingCascade.objects.filter(
            status=PendingCascade.STATUS_COMPLETED
        ).count()
        self.assertEqual(completed, 3)
        self.assertIn("processed=3", out.getvalue())

    def test_skips_completed_rows(self):
        PendingCascade.objects.create(
            user_external_id="11111111-2222-3333-4444-555555555555",
            sucursal_id=self.sucursal.id,
            status=PendingCascade.STATUS_COMPLETED,
        )
        from django.core.management import call_command
        from io import StringIO

        def handler(request):
            raise AssertionError("HTTP should not be called for completed rows")

        with _patch_dp4500_with_handler(handler):
            out = StringIO()
            call_command("reconcile_pending_cascades", stdout=out)
        self.assertIn("processed=0", out.getvalue())


# --------------------------------------------------------------------------
# BiometricEnrollmentRecord
# --------------------------------------------------------------------------


class BiometricEnrollmentRecordTests(TestCase):
    def test_round_trip(self):
        rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
        user = Usuario.objects.create_user(
            username="enrollment_user",
            password="Sup3rSecret!",
            primer_nombre="Carol",
            apellido_paterno="Test",
            rol=rol,
        )
        rec = BiometricEnrollmentRecord.objects.create(
            user=user,
            user_external_id=user.biometric_external_id,
            wizard_id="wizard-abc",
            enrollment_strategy=BiometricEnrollmentRecord.STRATEGY_PENDING,
        )
        rec.refresh_from_db()
        self.assertEqual(rec.user_external_id, user.biometric_external_id)
        self.assertEqual(rec.wizard_id, "wizard-abc")
        self.assertEqual(
            rec.enrollment_strategy,
            BiometricEnrollmentRecord.STRATEGY_PENDING,
        )
        self.assertIsNone(rec.advanced_at)
        self.assertIsNone(rec.cancelled_at)
