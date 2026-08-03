"""Task 2.2 — both legacy biometric confirmation routes are gated.

Two URLs reach the same administrative confirm-with-biometric behaviour:

- ``POST /api/admin/citas/<id>/confirmar-biometria/`` → the function
  view ``admin_confirm_appointment_biometric`` (slash route declared
  in ``config/api_urls.py``).
- ``POST /api/admin/citas/citas/<id>/confirmar-biometria`` → the DRF
  action ``CitasViewSet.confirmar_biometria`` (no-slash, mounted under
  the ``citas/`` router include).

URL precedence must remain intact: the slash function wins for the
trailing-slash URL; the DRF action covers the no-slash URL. Both must
return HTTP 503 ``BIOMETRIC_SUSPENDED`` after the existing auth/perm
gate and BEFORE any serializer or write.
"""

from __future__ import annotations

from django.test import override_settings
from django.urls import resolve

from biometric.services.encryption import encrypt_template
from customers.models import HuellaBiometricaCliente
from operations.models import CitaMedica, EventoConfirmacionCita

from ._base import SuspensionGateTestBase, post_json


SUSPENDED = override_settings(BIOMETRIC_SUSPENDED=True)


@SUSPENDED
class LegacyRouteGatingTests(SuspensionGateTestBase):
    def setUp(self):
        super().setUp()
        # Plant a legacy MOCK template so the gate sits BEFORE the
        # template equality check (which would 400 in the live build).
        HuellaBiometricaCliente.objects.create(
            cliente=self.cliente,
            proveedor=HuellaBiometricaCliente.Proveedor.MOCK_LEGACY,
            template_biometrico=encrypt_template(b"TEMPLATE_OK"),
            activo=True,
        )
        self.legacy_url = f"/api/admin/citas/{self.cita.id}/confirmar-biometria/"
        # The DRF router is mounted under path("citas/", include(...))
        # with trailing_slash=False, so the no-slash form resolves.
        self.drf_url = f"/api/admin/citas/citas/{self.cita.id}/confirmar-biometria"

    def test_legacy_function_route_resolves_to_function(self):
        match = resolve(self.legacy_url)
        self.assertEqual(match.func.__name__, "admin_confirm_appointment_biometric")

    def test_drf_action_route_resolves_to_viewset_action(self):
        match = resolve(self.drf_url)
        view = match.func
        cls = getattr(view, "cls", view.__class__)
        self.assertEqual(cls.__name__, "CitasViewSet")
        self.assertTrue(callable(getattr(cls, "confirmar_biometria", None)))

    def test_legacy_function_route_returns_503(self):
        self.login(self.admin_principal)
        response = post_json(
            self.client_http,
            self.legacy_url,
            {"template": "TEMPLATE_OK", "quality": 80},
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)
        self.assertFalse(self.cita.verif_biometria)
        self.assertEqual(EventoConfirmacionCita.objects.filter(cita=self.cita).count(), 0)

    def test_drf_action_route_returns_503(self):
        self.login(self.admin_principal)
        response = post_json(
            self.client_http, self.drf_url, {"template": "TEMPLATE_OK", "quality": 80}
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "BIOMETRIC_SUSPENDED")
        self.cita.refresh_from_db()
        self.assertEqual(self.cita.estado, CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION)

    def test_legacy_function_route_rejects_unauthorized_before_gate(self):
        # No login at all — auth check must precede the 503.
        response = post_json(
            self.client_http,
            self.legacy_url,
            {"template": "TEMPLATE_OK", "quality": 80},
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 503)

    def test_drf_action_route_rejects_unauthorized_before_gate(self):
        # No login at all — auth check must precede the 503.
        response = post_json(
            self.client_http, self.drf_url, {"template": "TEMPLATE_OK", "quality": 80}
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotEqual(response.status_code, 503)
