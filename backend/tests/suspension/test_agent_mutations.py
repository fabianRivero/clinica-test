"""Task 2.3 — agent lifecycle: mutations gated, reads kept, release unreachable.

- ``POST /api/biometric/agents/`` (create) → 503
- ``POST /api/biometric/agents/<id>/heartbeat/`` (heartbeat) → 503 and
  ``last_seen_at`` is NOT updated.
- ``DELETE /api/biometric/agents/<id>/`` (delete) → 503 and ``is_active``
  stays True.
- ``GET /api/biometric/agents/`` (list) → 200 (authorized reads remain
  available per spec).
- The view never reaches ``SuspendedAgentClient.release()`` while
  suspended: the endpoint-level ``verify_init`` test patches the
  ``capture_token_store`` and ``get_agent_client`` to prove the
  handler short-circuits BEFORE any agent call (including ``release``,
  which the live ``verify_init`` performs just before ``match``).
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from biometric.models import AgentToken
from biometric.services.encryption import encrypt_template
from customers.models import HuellaBiometricaCliente

from ._base import SuspensionGateTestBase, post_json


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


@SUSPENDED
class AgentMutationGatingTests(SuspensionGateTestBase):
    def setUp(self):
        super().setUp()
        self.agent = AgentToken.objects.create(
            name="agent-1",
            sucursal=self.sucursal,
            token_hash=AgentToken.hash_token("susp-agent-token"),
            public_url="https://agent.example.com",
            is_active=True,
        )
        self.last_seen_before = timezone.now() - timedelta(hours=1)
        AgentToken.objects.filter(pk=self.agent.id).update(last_seen_at=self.last_seen_before)

    def test_agent_create_returns_503(self):
        self.login(self.admin_principal)
        before = AgentToken.objects.count()
        response = post_json(
            self.client_http,
            "/api/biometric/agents/",
            {"name": "new", "public_url": "https://x.example.com", "sucursal_id": self.sucursal.id},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        self.assertEqual(AgentToken.objects.count(), before)

    def test_agent_heartbeat_returns_503_and_does_not_update_last_seen(self):
        response = self.client_http.post(
            f"/api/biometric/agents/{self.agent.id}/heartbeat/",
            HTTP_AUTHORIZATION="Bearer susp-agent-token",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.last_seen_at, self.last_seen_before)

    def test_agent_delete_returns_503(self):
        self.login(self.admin_principal)
        response = self.client_http.delete(f"/api/biometric/agents/{self.agent.id}/")
        self.assertEqual(response.status_code, 503)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.is_active)

    def test_agent_list_remains_available_for_authorized_readers(self):
        self.login(self.admin_principal)
        response = self.client_http.get("/api/biometric/agents/")
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["results"]), 1)

    def test_suspended_verify_init_never_touches_agent_or_token_store(self):
        """Endpoint-level proof that the live ``verify_init`` view does
        not call ``agent_client.release()`` / ``match()`` and does not
        create capture tokens while suspended. The live view (when not
        gated) calls ``agent_client.release(agent)`` then
        ``agent_client.match(agent, ...)`` — patching any of these with
        ``AssertionError`` proves they were never reached.
        """
        # Seed a real fingerprint row so the live code would otherwise
        # reach the agent call path (it short-circuits to manual_only
        # only when no huella exists).
        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=encrypt_template(b"x" * 64),
            activo=True,
        )
        self.login(self.admin_sucursal)
        with override_settings(BIOMETRIC_SUSPENDED=True):
            with mock.patch("biometric.views.get_agent_client") as factory_mock, \
                 mock.patch("biometric.views.capture_token_store") as store_mock:
                response = post_json(
                    self.client_http,
                    f"/api/biometric/citas/{self.cita.id}/huella/verify-init/",
                )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        # The view must not have reached the agent client factory or
        # created/popped any capture token under suspension.
        factory_mock.assert_not_called()
        store_mock.create.assert_not_called()
        store_mock.pop.assert_not_called()
        store_mock.set_score.assert_not_called()
        # Cita state unchanged.
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, "REALIZADA_PENDIENTE_VERIFICACION")
