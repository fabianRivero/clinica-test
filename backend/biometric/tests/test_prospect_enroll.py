"""End-to-end tests for the prospect enroll endpoint.

The conversion wizard captures the fingerprint at step 4, before the
prospect has been promoted to a ``Cliente``. The new endpoint
``/api/biometric/prospectos/<id>/huella/enroll/`` persists the row
against the prospect so the finalize handler can re-attach it to the
newly-created cliente atomically.

Wire contract (matches ``backend/biometric/views.py``):

- POST ``{consentimiento_aceptado: bool}`` → 201 with
  ``{cliente_id: null, prospecto_id, huella_id, device_serial,
  template_format, calidad_captura, proveedor, attempt_id}``.
- 400 ``CONSENT_REQUIRED`` when consent is missing.
- 404 ``PROSPECTO_NOT_FOUND`` when the prospect id is unknown.
- 503 ``NO_AGENT`` when no ``AgentToken`` is configured.
- 400 ``LOW_QUALITY`` when the agent returns quality < 50.
"""

from __future__ import annotations

import json
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Rol, Usuario
from biometric.models import AgentToken, BiometricAttempt
from biometric.services.capture_tokens import capture_token_store
from catalogs.models import Sucursal
from customers.models import HuellaBiometricaCliente, Prospecto


def _payload(data):
    return json.dumps(data)


class ProspectEnrollEndpointBase(TestCase):
    """Shared setUp: roles, branches, users and a prospect."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")

        cls.sucursal_a = Sucursal.objects.create(nombre="SucA-Prospect", activa=True)

        cls.user_principal = Usuario.objects.create_user(
            username="prospect.principal",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="P",
            rol=cls.rol_principal,
            sucursal=None,
        )
        cls.user_sucursal_a = Usuario.objects.create_user(
            username="prospect.sucursal.a",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="A",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_a,
        )

        cls.prospect = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spect",
            telefono="7000-0000",
            sucursal_registro=cls.sucursal_a,
            registrado_por=cls.user_principal,
        )

    def setUp(self):
        capture_token_store.reset()
        self._agent_patch = mock.patch.dict(
            "os.environ",
            {
                "AGENT_CLIENT_CLASS": "biometric.services.agent_client.MockAgentClient",
                "AGENT_QUALITY_SCORE": "80",
                "AGENT_FAIL_WITH": "",
            },
        )
        self._agent_patch.start()
        # Active agent for the happy path.
        self.agent = AgentToken.objects.create(
            name="Prospect agent",
            sucursal=self.sucursal_a,
            token_hash="7" * 64,
            public_url="https://agent.example.com",
            is_active=True,
        )

    def tearDown(self):
        self._agent_patch.stop()
        capture_token_store.reset()

    def post(self, url, payload=None, user=None):
        body = _payload(payload or {})
        if user is not None:
            self.client.force_login(user)
        return self.client.post(url, body, content_type="application/json")

    @property
    def url(self):
        return reverse(
            "biometric:prospecto-huella-enroll",
            kwargs={"prospect_id": self.prospect.id},
        )


class ProspectEnrollHappyPathTests(ProspectEnrollEndpointBase):
    def test_prospect_enroll_happy_path(self):
        response = self.post(
            self.url,
            {"consentimiento_aceptado": True},
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIsNone(data["cliente_id"])
        self.assertEqual(data["prospecto_id"], self.prospect.id)
        self.assertIn("huella_id", data)
        self.assertEqual(data["calidad_captura"], 80)
        self.assertEqual(data["proveedor"], "DIGITAL_PERSONA")
        # Bytes persisted. Encryption is currently disabled for
        # local testing (see biometric/services/encryption.py) so
        # the template is the raw bytes the agent returned, not a
        # Fernet ciphertext.
        huella = HuellaBiometricaCliente.objects.get(prospecto=self.prospect)
        self.assertIsNotNone(huella.template_biometrico)
        self.assertGreater(len(bytes(huella.template_biometrico)), 0)
        self.assertIsNone(huella.cliente)
        # Audit log entry.
        attempt = BiometricAttempt.objects.get(prospecto=self.prospect)
        self.assertEqual(attempt.operation, "ENROLL")
        self.assertTrue(attempt.success)
        self.assertEqual(attempt.cliente, None)


class ProspectEnrollValidationTests(ProspectEnrollEndpointBase):
    def test_prospect_enroll_requires_authentication(self):
        response = self.client.post(
            self.url,
            data=_payload({"consentimiento_aceptado": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)

    def test_prospect_enroll_no_consent(self):
        response = self.post(
            self.url,
            {"consentimiento_aceptado": False},
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "CONSENT_REQUIRED")

    def test_prospect_enroll_prospect_not_found(self):
        url = reverse(
            "biometric:prospecto-huella-enroll",
            kwargs={"prospect_id": 99999},
        )
        response = self.post(
            url,
            {"consentimiento_aceptado": True},
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], "PROSPECTO_NOT_FOUND")


class ProspectEnrollFailureTests(ProspectEnrollEndpointBase):
    def test_prospect_enroll_no_agent(self):
        AgentToken.objects.all().delete()
        response = self.post(
            self.url,
            {"consentimiento_aceptado": True},
            user=self.user_principal,
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "NO_AGENT")
        self.assertTrue(
            BiometricAttempt.objects.filter(
                prospecto=self.prospect,
                operation="ENROLL",
                failure_reason="NO_IMAGE",
            ).exists()
        )

    def test_prospect_enroll_low_quality(self):
        with mock.patch.dict("os.environ", {"AGENT_QUALITY_SCORE": "10"}):
            response = self.post(
                self.url,
                {"consentimiento_aceptado": True},
                user=self.user_principal,
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "LOW_QUALITY")
        self.assertTrue(
            BiometricAttempt.objects.filter(
                prospecto=self.prospect,
                operation="ENROLL",
                failure_reason="LOW_QUALITY",
            ).exists()
        )

    def test_prospect_enroll_agent_offline_returns_503(self):
        with mock.patch.dict("os.environ", {"AGENT_FAIL_WITH": "NO_IMAGE"}):
            response = self.post(
                self.url,
                {"consentimiento_aceptado": True},
                user=self.user_principal,
            )
        self.assertEqual(response.status_code, 503)
        self.assertTrue(
            BiometricAttempt.objects.filter(
                prospecto=self.prospect,
                operation="ENROLL",
                failure_reason="NO_IMAGE",
            ).exists()
        )


class ProspectEnrollIdempotencyTests(ProspectEnrollEndpointBase):
    def test_prospect_enroll_idempotent(self):
        # First capture.
        first = self.post(
            self.url,
            {"consentimiento_aceptado": True},
            user=self.user_principal,
        )
        self.assertEqual(first.status_code, 201, first.content)
        first_huella_id = first.json()["huella_id"]

        # Second capture should UPDATE the same row, not duplicate.
        second = self.post(
            self.url,
            {"consentimiento_aceptado": True},
            user=self.user_principal,
        )
        self.assertEqual(second.status_code, 201, second.content)
        self.assertEqual(second.json()["huella_id"], first_huella_id)
        self.assertEqual(
            HuellaBiometricaCliente.objects.filter(prospecto=self.prospect).count(),
            1,
        )
        # Two success attempts logged.
        self.assertEqual(
            BiometricAttempt.objects.filter(
                prospecto=self.prospect, operation="ENROLL", success=True
            ).count(),
            2,
        )


class HuellaCheckConstraintTests(TestCase):
    """Direct DB tests for the ``huella_exactly_one_owner`` constraint."""

    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="SucX", activa=True)
        cls.user = Usuario.objects.create_user(
            username="ck.user",
            password="pw12345!",
            primer_nombre="U",
            apellido_paterno="P",
            rol=cls.rol_principal,
        )
        cls.cliente_user = Usuario.objects.create_user(
            username="ck.cliente",
            password="pw12345!",
            primer_nombre="C",
            apellido_paterno="L",
            rol=cls.rol_cliente,
            fecha_nacimiento="1990-01-01",
        )
        from customers.models import Cliente

        cls.cliente = Cliente.objects.create(
            usuario=cls.cliente_user,
            fecha_nacimiento=cls.cliente_user.fecha_nacimiento,
            sucursal_origen=cls.sucursal,
        )
        cls.prospecto = Prospecto.objects.create(
            primer_nombre="Pr",
            apellido_paterno="O",
            sucursal_registro=cls.sucursal,
        )

    def test_check_constraint_rejects_both_set(self):
        """Row with cliente AND prospecto set must violate the constraint."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HuellaBiometricaCliente.objects.create(
                    cliente=self.cliente,
                    prospecto=self.prospecto,
                    proveedor="DIGITAL_PERSONA",
                    consentimiento_aceptado=True,
                    activo=True,
                )

    def test_check_constraint_rejects_neither_set(self):
        """Row with neither cliente nor prospecto must violate the constraint."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HuellaBiometricaCliente.objects.create(
                    proveedor="DIGITAL_PERSONA",
                    consentimiento_aceptado=True,
                    activo=True,
                )

    def test_check_constraint_accepts_prospecto_only(self):
        huella = HuellaBiometricaCliente.objects.create(
            prospecto=self.prospecto,
            proveedor="DIGITAL_PERSONA",
            consentimiento_aceptado=True,
            activo=True,
        )
        self.assertIsNone(huella.cliente)
        self.assertEqual(huella.prospecto_id, self.prospecto.id)

    def test_unique_together_prospecto_prevents_duplicates(self):
        HuellaBiometricaCliente.objects.create(
            prospecto=self.prospecto,
            proveedor="DIGITAL_PERSONA",
            consentimiento_aceptado=True,
            activo=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HuellaBiometricaCliente.objects.create(
                    prospecto=self.prospecto,
                    proveedor="DIGITAL_PERSONA",
                    consentimiento_aceptado=True,
                    activo=True,
                )


class FinalizeAttachesProspectHuellaTests(TestCase):
    """The finalize handler must move the prospect-bound huella + attempts
    onto the freshly-created ``Cliente`` atomically.

    We exercise the re-attach query directly to keep this test focused on
    the new transition logic. The full multi-step finalize flow is
    covered by ``config.tests.test_prospect_conversion``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")
        cls.sucursal = Sucursal.objects.create(nombre="SucZ", activa=True)
        cls.user = Usuario.objects.create_user(
            username="finalize.user",
            password="pw12345!",
            primer_nombre="U",
            apellido_paterno="F",
            rol=cls.rol_principal,
        )
        cls.prospecto = Prospecto.objects.create(
            primer_nombre="Pro",
            apellido_paterno="Spec",
            sucursal_registro=cls.sucursal,
        )
        cls.cliente_user = Usuario.objects.create_user(
            username="finalize.cliente",
            password="pw12345!",
            primer_nombre="C",
            apellido_paterno="L",
            rol=cls.rol_cliente,
            fecha_nacimiento="1990-01-01",
        )
        from customers.models import Cliente

        cls.cliente = Cliente.objects.create(
            usuario=cls.cliente_user,
            fecha_nacimiento=cls.cliente_user.fecha_nacimiento,
            sucursal_origen=cls.sucursal,
        )

    def test_finalize_attaches_prospect_huella_to_new_cliente(self):
        # Pre-condition: a huella + 2 BiometricAttempts sit on the prospect.
        huella = HuellaBiometricaCliente.objects.create(
            prospecto=self.prospecto,
            proveedor="DIGITAL_PERSONA",
            template_biometrico=b"\x00\x01\x02",
            consentimiento_aceptado=True,
            activo=True,
            device_serial="PC-001",
        )
        BiometricAttempt.objects.create(
            prospecto=self.prospecto,
            usuario=self.user,
            operation="ENROLL",
            success=True,
            score=Decimal("0.80"),
        )
        BiometricAttempt.objects.create(
            prospecto=self.prospecto,
            usuario=self.user,
            operation="ENROLL",
            success=False,
            failure_reason="LOW_QUALITY",
        )

        # Re-attach (same query as finalize).
        with transaction.atomic():
            HuellaBiometricaCliente.objects.filter(
                prospecto=self.prospecto, cliente__isnull=True
            ).update(cliente=self.cliente, prospecto=None)
            BiometricAttempt.objects.filter(
                prospecto=self.prospecto, cliente__isnull=True
            ).update(cliente=self.cliente, prospecto=None)

        huella.refresh_from_db()
        self.assertEqual(huella.cliente_id, self.cliente.id)
        self.assertIsNone(huella.prospecto_id)
        self.assertEqual(
            BiometricAttempt.objects.filter(cliente=self.cliente).count(),
            2,
        )
        self.assertEqual(
            BiometricAttempt.objects.filter(prospecto=self.prospecto).count(),
            0,
        )