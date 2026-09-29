"""Focused cascade smoke e2e test (Phase 2A7, isolated from wizard chain).

Pipeline under test:
    Usuario.delete()
        -> post_delete signal (signals.py:29-66)
        -> PendingCascade.objects.create(status=pending)
        -> cascade_revoke_template.delay(ext_id, sucursal_id)   (mocked)
    cascade_revoke_template.run(ext_id, sucursal_id)             (direct)
        -> _do_cascade (tasks.py:39-65)
        -> HTTPClient.delete_template -> MockTransport 204
        -> STATUS_COMPLETED

Reuses the four Phase 2A6 patterns from design.md:

- **Pattern A** -- mock.patch.dict(os.environ, ...) for
  DP4500_SERVICE_KEY_SUCURSAL_<id> (lazy read at tasks.py:34-36).
- **Pattern B** -- contextlib.ExitStack over TWO mock.patch calls
  (dp4500_integration.views.HTTPClient AND
  dp4500_integration.tasks.HTTPClient; Phase 2A6 failure F1;
  apply-progress.md §4 line 58). Each ``from X import Y`` captures
  a per-module reference at import time.
- **Pattern C** -- patch the bound attribute
  dp4500_integration.signals.cascade_revoke_template.delay (NOT the
  module; signals.py:23 captures the task symbol at import time;
  Phase 2A6 failure F2; proven at test_cascade.py:115-117).
- **Pattern D** -- direct cascade_revoke_template.run(...) invocation
  AFTER Usuario.delete() with both HTTPClient import sites still
  patched. Mirrors test_cascade.py:252-261 (proven Phase 2A6).
"""
from __future__ import annotations

import os
import uuid
from contextlib import ExitStack
from unittest import mock

import httpx
from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from dp4500_integration.client import HTTPClient
from dp4500_integration.models import PendingCascade
from dp4500_integration.tasks import cascade_revoke_template


def _patch_dp4500_handler(handler):
    """Return a TUPLE of two mock.patch objects.

    First patches ``dp4500_integration.views.HTTPClient`` (views.py:33
    import site); second patches ``dp4500_integration.tasks.HTTPClient``
    (tasks.py:14 import site). Both share the same factory so the
    MockTransport routes identically across the cascade task.

    Phase 2A6 failure F1 rationale: ``from X import Y`` captures a
    per-module reference at import time, so patching only one import
    site leaves the other reaching the real network. Call sites MUST
    wrap this tuple in ``contextlib.ExitStack`` so all patches enter
    and exit atomically.
    """
    def factory(*args, **kwargs):
        client = HTTPClient(
            base_url="https://dp4500.test",
            timeout_seconds=5,
            key_resolver=lambda _: "SeK_smoke_test",
        )
        client._client = httpx.Client(transport=httpx.MockTransport(handler))
        return client
    return (
        mock.patch("dp4500_integration.views.HTTPClient", side_effect=factory),
        mock.patch("dp4500_integration.tasks.HTTPClient", side_effect=factory),
    )


def _make_graph():
    """Build branch + roles + admin + enrolled-user with explicit UUID.

    No FK dependents on the enrolled user (no CitaMedica, no Operacion,
    no Cliente) -- the reverse-FK ordering failure F5 from Phase 2A6
    does not apply here.
    """
    sucursal = Sucursal.objects.create(
        nombre="Smoke-Cascade-Branch",
        activa=True,
        dp4500_service_key_id="smoke-key-001",
    )
    rol_admin, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
    rol_cliente, _ = Rol.objects.get_or_create(rol="CLIENTE")

    admin = Usuario.objects.create_user(
        username="cascade.smoke.admin",
        password="pw-smoke-admin",
        primer_nombre="Cascade",
        apellido_paterno="Smoke",
        email="cascade.smoke.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    external_id = uuid.uuid4()
    enrolled = Usuario(
        username="cascade.smoke.enrolled",
        primer_nombre="Enrolled",
        apellido_paterno="Smoke",
        email="cascade.smoke.enrolled@example.com",
        rol=rol_cliente,
        sucursal=sucursal,
        biometric_external_id=external_id,
    )
    enrolled.set_password("pw-smoke-enrolled")
    enrolled.save()

    return {
        "sucursal": sucursal,
        "external_id": external_id,
        "admin": admin,
        "enrolled": enrolled,
    }


class SmokeCascadeTests(TestCase):
    """End-to-end coverage of the cascade pipeline in isolation.

    Canonical cascade location alongside the unit-level coverage in
    backend/dp4500_integration/tests/test_cascade.py (WU-2A6.1/2/3).
    The smoke e2e chain in test_smoke_e2e.py keeps its
    ``self.skipTest(...)`` at the cascade sub-step.
    """

    def test_cascade_signal_then_task_marks_completed(self):
        # 1. Build the graph.
        graph = _make_graph()

        # 2. Pattern A -- env var injection for the per-sucursal bearer.
        with mock.patch.dict(
            os.environ,
            {
                f"DP4500_SERVICE_KEY_SUCURSAL_{graph['sucursal'].id}": (
                    "SeK_smoke_test"
                ),
            },
            clear=False,
        ):
            # 3. Pattern B + C in one ExitStack. Both HTTPClient import
            # sites patched (Pattern B); bound ``.delay`` attribute
            # patched (Pattern C). MockTransport routes only the
            # cascade DELETE; any other URL/method raises loudly.
            with ExitStack() as stack:
                for patcher in _patch_dp4500_handler(self._delete_handler):
                    stack.enter_context(patcher)
                with mock.patch(
                    "dp4500_integration.signals.cascade_revoke_template.delay",
                ) as mock_delay:
                    client = Client()
                    client.force_login(graph["admin"])

                    # 4. Fire post_delete. Patched .delay intercepts
                    # the Celery enqueue; sync PendingCascade insert
                    # runs for real (source of truth for retries).
                    graph["enrolled"].delete()

                    # 5. Signal assertions.
                    mock_delay.assert_called_once_with(
                        str(graph["external_id"]),
                        graph["sucursal"].id,
                    )
                    self.assertEqual(PendingCascade.objects.count(), 1)
                    pending_row = PendingCascade.objects.first()
                    self.assertEqual(
                        pending_row.status,
                        PendingCascade.STATUS_PENDING,
                    )

                    # 6. Pattern D -- drive task body synchronously.
                    cascade_revoke_template.run(
                        str(graph["external_id"]),
                        graph["sucursal"].id,
                    )

        # 7. Task body assertions.
        row = PendingCascade.objects.get(user_external_id=graph["external_id"])
        self.assertEqual(row.status, PendingCascade.STATUS_COMPLETED)
        self.assertEqual(row.attempts, 1)
        self.assertIsNotNone(row.completed_at)

    @staticmethod
    def _delete_handler(request):
        """MockTransport route: cascade DELETE -> 204; anything else fails."""
        url = str(request.url)
        if request.method == "DELETE" and "/templates/" in url:
            return httpx.Response(204, request=request)
        raise AssertionError(
            f"Unexpected {request.method} {url} in cascade smoke handler",
        )