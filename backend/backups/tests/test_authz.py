"""Authz + decorator unit tests for the backups HTTP layer.

These tests live in commit 1 because they exercise only the
``require_admin_principal`` decorator and the URL resolution — they
do NOT depend on the view bodies that land in commits 2 and 3.
"""

from __future__ import annotations

from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AuthzMatrixTests(TestCase):
    """Every endpoint MUST reject anonymous and non-principal callers."""

    def setUp(self) -> None:
        cache.clear()
        self.rol_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        self.rol_cliente = Rol.objects.create(rol="CLIENTE")

        self.principal = Usuario.objects.create_user(
            username="principal",
            password="x",
            primer_nombre="P",
            apellido_paterno="Principal",
            rol=self.rol_principal,
        )
        self.sucursal = Usuario.objects.create_user(
            username="sucursal",
            password="x",
            primer_nombre="S",
            apellido_paterno="Sucursal",
            rol=self.rol_sucursal,
        )
        self.trabajador = Usuario.objects.create_user(
            username="trabajador",
            password="x",
            primer_nombre="T",
            apellido_paterno="Trabajador",
            rol=self.rol_trabajador,
        )
        self.cliente = Usuario.objects.create_user(
            username="cliente",
            password="x",
            primer_nombre="C",
            apellido_paterno="Cliente",
            rol=self.rol_cliente,
        )

    def _login(self, user) -> Client:
        c = Client(enforce_csrf_checks=False)
        c.force_login(user)
        return c

    def test_anonymous_gets_401_on_all_endpoints(self):
        anon = Client()
        for method, path in [
            ("post", "/api/admin/backups/trigger/"),
            ("get", "/api/admin/backups/"),
            ("get", "/api/admin/backups/clinica_2026-08-06_120000.dump/download/"),
            ("delete", "/api/admin/backups/clinica_2026-08-06_120000.dump/"),
        ]:
            with self.subTest(method=method, path=path):
                response = getattr(anon, method)(path)
                self.assertEqual(response.status_code, 401, msg=f"{method} {path}")

    def test_non_principal_gets_403_on_all_endpoints(self):
        for user, label in [
            (self.sucursal, "ADMIN_SUCURSAL"),
            (self.trabajador, "TRABAJADOR"),
            (self.cliente, "CLIENTE"),
        ]:
            c = self._login(user)
            with self.subTest(role=label):
                self.assertEqual(c.get("/api/admin/backups/").status_code, 403)
                self.assertEqual(
                    c.post("/api/admin/backups/trigger/").status_code, 403
                )
                self.assertEqual(
                    c.get(
                        "/api/admin/backups/clinica_2026-08-06_120000.dump/download/"
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    c.delete(
                        "/api/admin/backups/clinica_2026-08-06_120000.dump/"
                    ).status_code,
                    403,
                )


class DecoratorUnitTests(TestCase):
    """Direct unit coverage for require_admin_principal + check_rate_limit."""

    def test_require_admin_principal_returns_403_for_sucursal(self):
        from backups.decorators import require_admin_principal

        class FakeUser:
            is_authenticated = True
            is_superuser = False
            es_admin_principal = False

        @require_admin_principal
        def view(request):
            return "ok"

        request = mock.Mock(user=FakeUser())
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_check_rate_limit_returns_429_on_second_call(self):
        from backups.decorators import check_rate_limit

        cache.clear()
        allowed_first, deny_first = check_rate_limit("unit", 999, 60)
        allowed_second, deny_second = check_rate_limit("unit", 999, 60)
        self.assertTrue(allowed_first)
        self.assertIsNone(deny_first)
        self.assertFalse(allowed_second)
        self.assertEqual(deny_second.status_code, 429)