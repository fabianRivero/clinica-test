"""Tests for the cliente re-enroll endpoint.

This is the test companion for ``cliente_reenroll_init`` in
biometric.views. The endpoint is reachable from the cliente
detail page (not from the prospect-convert flow) and overwrites
the existing ``HuellaBiometricaCliente.template_biometrico`` row
in place via ``update_or_create``.

Behavior under test:
- 200: a previous fingerprint is overwritten; a new ENROLL attempt
  is written with success=True.
- 400: missing consentimiento_aceptado.
- 400: invalid json body.
- 404: cliente not found.
- 400: cliente exists but has no fingerprint on file (NO_FINGERPRINT).
- 503: no agent available.
- 400: agent captures but quality below 50 (LOW_QUALITY).
- 400: agent returns invalid hex (INVALID_TEMPLATE).
- 503: agent unavailable.
- 400: agent operation error.
"""

from __future__ import annotations
import json

import hashlib
import secrets
from decimal import Decimal
from unittest import mock

from django.test import RequestFactory, TestCase

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from biometric.models import AgentToken, BiometricAttempt
from customers.models import Cliente, HuellaBiometricaCliente
from biometric.services.encryption import encrypt_template
from biometric.views import cliente_reenroll_init


def _make_user_and_sucursal():
    rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
    user, _ = Usuario.objects.get_or_create(
        username="admin_reenroll",
        defaults={
            "primer_nombre": "Admin",
            "apellido_paterno": "Test",
            "email": "admin_reenroll@test.local",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
            "rol": rol,
        },
    )
    user.set_password("admin1234")
    user.save()
    sucursal, _ = Sucursal.objects.get_or_create(
        nombre="Sucursal Test Reenroll",
        defaults={"ciudad": "La Paz", "es_principal": True, "activa": True},
    )
    user.sucursal = sucursal
    user.save()
    return user, sucursal


def _make_cliente(sucursal, username="cliente_reenroll"):
    user, _ = Usuario.objects.get_or_create(
        username=username,
        defaults={
            "primer_nombre": "Cliente",
            "apellido_paterno": "Reenroll",
            "email": f"{username}@test.local",
            "is_active": True,
            "rol": Rol.objects.get_or_create(rol="CLIENTE")[0],
        },
    )
    user.set_password("cliente1234")
    user.save()
    cliente, _ = Cliente.objects.get_or_create(
        usuario=user,
        defaults={"sucursal_registro": sucursal, "estado_cliente": "ACTIVO", "fecha_nacimiento": "1990-01-01"},
    )
    return cliente


def _make_agent_token(sucursal):
    raw = secrets.token_urlsafe(32)
    return AgentToken.objects.create(
        name="Agent Test",
        sucursal=sucursal,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        public_url="http://127.0.0.1:8765",
        is_active=True,
    )


def _post(body, cliente_id, user):
    rf = RequestFactory()
    req = rf.post(
        f"/api/biometric/clientes/{cliente_id}/huella/reenroll/",
        body,
        content_type="application/json",
    )
    req.user = user
    return cliente_reenroll_init(req, cliente_id=cliente_id)


class ReenrollTests(TestCase):
    def setUp(self):
        self.user, self.sucursal = _make_user_and_sucursal()
        self.cliente = _make_cliente(self.sucursal)
        self.agent = _make_agent_token(self.sucursal)
        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.DIGITAL_PERSONA,
            template_biometrico=encrypt_template(b"original-template"),
            template_format="DP_PROPRIETARY",
            device_serial="ORIGINAL-DEV",
            calidad_captura=70,
            consentimiento_aceptado=True,
            activo=True,
            registrado_por=self.user,
        )

    def test_happy_path_overwrites_template(self):
        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.capture.return_value = mock.MagicMock(
                quality_score=85,
                device_serial="NEW-DEV",
                template_format="DP_PROPRIETORY",
                template_b64=b"new-fingerprint-payload".hex(),
            )
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["cliente_id"], self.cliente.id)
        self.assertEqual(json.loads(response.content)["calidad_captura"], 85)

        huella = HuellaBiometricaCliente.objects.get(cliente=self.cliente)
        self.assertEqual(huella.device_serial, "NEW-DEV")
        self.assertEqual(huella.calidad_captura, 85)
        self.assertNotIn(huella.template_biometrico, b"original-template")

        attempts = BiometricAttempt.objects.filter(
            cliente=self.cliente, operation="ENROLL"
        )
        self.assertEqual(attempts.count(), 1)
        self.assertTrue(attempts.first().success)

    def test_missing_consent(self):
        with mock.patch("biometric.views.get_agent_client"):
            response = _post(
                {"consentimiento_aceptado": False}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "CONSENT_REQUIRED")
        self.assertEqual(BiometricAttempt.objects.filter(cliente=self.cliente).count(), 0)

    def test_invalid_json(self):
        rf = RequestFactory()
        req = rf.post(
            "/api/biometric/clientes/1/huella/reenroll/",
            "{not json",
            content_type="application/json",
        )
        req.user = self.user
        response = cliente_reenroll_init(req, cliente_id=self.cliente.id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "INVALID_JSON")

    def test_cliente_not_found(self):
        response = _post(
            {"consentimiento_aceptado": True}, 99999, self.user
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.content)["code"], "CLIENTE_NOT_FOUND")

    def test_cliente_without_fingerprint(self):
        other = _make_cliente(self.sucursal, username="cliente_no_huella")
        HuellaBiometricaCliente.objects.filter(cliente=other).delete()
        response = _post(
            {"consentimiento_aceptado": True}, other.id, self.user
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "NO_FINGERPRINT")

    def test_no_agent(self):
        AgentToken.objects.all().delete()
        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_get_client.return_value = mock.MagicMock()
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["code"], "NO_AGENT")
        attempts = BiometricAttempt.objects.filter(
            cliente=self.cliente, success=False
        )
        self.assertEqual(attempts.count(), 1)
        self.assertEqual(attempts.first().failure_reason, "NO_IMAGE")

    def test_low_quality(self):
        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.capture.return_value = mock.MagicMock(
                quality_score=30,
                device_serial="BAD-DEV",
                template_format="DP_PROPRIETORY",
                template_b64=b"junk".hex(),
            )
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "LOW_QUALITY")

    def test_invalid_template(self):
        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.capture.return_value = mock.MagicMock(
                quality_score=80,
                device_serial="OK-DEV",
                template_format="DP_PROPRIETARY",
                template_b64="not-hex-data",
            )
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "INVALID_TEMPLATE")

    def test_agent_unavailable_503(self):
        from biometric.services.agent_client import AgentUnavailableError

        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.capture.side_effect = AgentUnavailableError("agent offline")
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content)["code"], "agent offline")

    def test_agent_operation_error_400(self):
        from biometric.services.agent_client import AgentOperationError

        with mock.patch("biometric.views.get_agent_client") as mock_get_client:
            mock_client = mock.MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.capture.side_effect = AgentOperationError(
                code="LOW_QUALITY",
                status="no_finger",
            )
            response = _post(
                {"consentimiento_aceptado": True}, self.cliente.id, self.user
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.content)["code"], "LOW_QUALITY")
