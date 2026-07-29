"""Tests for the biometric permission predicates.

Covers the matrix in design §11 (PR #1 only contains the rows marked
Y/A for the orchestrator-supplied subset). It also exercises the
agent-token permission used by the heartbeat endpoint.
"""

from __future__ import annotations

from django.test import TestCase

from accounts.models import Rol, Usuario
from biometric.models import AgentToken
from biometric.permissions import (
    ADMIN_PRINCIPAL,
    AuthSubject,
    is_admin_and_owns_sucursal,
    is_admin_principal,
    is_admin_principal_or_sucursal,
    is_admin_sucursal,
    is_agent_token,
)
from catalogs.models import Sucursal


class PermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_principal = Rol.objects.create(rol=ADMIN_PRINCIPAL)
        cls.rol_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        cls.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        cls.rol_cliente = Rol.objects.create(rol="CLIENTE")

        cls.sucursal_a = Sucursal.objects.create(nombre="SucA-Perm", activa=True)
        cls.sucursal_b = Sucursal.objects.create(nombre="SucB-Perm", activa=True)

        cls.user_principal = Usuario.objects.create_user(
            username="perm.principal",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Princ",
            rol=cls.rol_principal,
            sucursal=None,
        )
        cls.user_sucursal_a = Usuario.objects.create_user(
            username="perm.sucursal.a",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="A",
            rol=cls.rol_sucursal,
            sucursal=cls.sucursal_a,
        )
        cls.user_trabajador = Usuario.objects.create_user(
            username="perm.trabajador",
            password="pw12345!",
            primer_nombre="Trab",
            apellido_paterno="X",
            rol=cls.rol_trabajador,
            sucursal=cls.sucursal_a,
        )

    def test_admin_principal_predicate(self):
        self.assertTrue(is_admin_principal(
            AuthSubject(user=self.user_principal)
        ))
        self.assertFalse(is_admin_principal(
            AuthSubject(user=self.user_sucursal_a)
        ))
        self.assertFalse(is_admin_principal(AuthSubject(user=None)))

    def test_admin_sucursal_predicate(self):
        self.assertTrue(is_admin_sucursal(
            AuthSubject(user=self.user_sucursal_a)
        ))
        self.assertFalse(is_admin_sucursal(
            AuthSubject(user=self.user_principal)
        ))

    def test_admin_principal_or_sucursal_predicate(self):
        self.assertTrue(is_admin_principal_or_sucursal(
            AuthSubject(user=self.user_principal)
        ))
        self.assertTrue(is_admin_principal_or_sucursal(
            AuthSubject(user=self.user_sucursal_a)
        ))
        self.assertFalse(is_admin_principal_or_sucursal(
            AuthSubject(user=self.user_trabajador)
        ))

    def test_admin_and_owns_sucursal(self):
        # Principal: always allowed regardless of branch.
        self.assertTrue(is_admin_and_owns_sucursal(
            AuthSubject(user=self.user_principal), self.sucursal_a
        ))
        # Branch admin on their branch: allowed.
        self.assertTrue(is_admin_and_owns_sucursal(
            AuthSubject(user=self.user_sucursal_a), self.sucursal_a
        ))
        # Branch admin on someone else's branch: denied.
        self.assertFalse(is_admin_and_owns_sucursal(
            AuthSubject(user=self.user_sucursal_a), self.sucursal_b
        ))
        # Worker: denied.
        self.assertFalse(is_admin_and_owns_sucursal(
            AuthSubject(user=self.user_trabajador), self.sucursal_a
        ))

    def test_agent_token_predicate(self):
        self.assertFalse(is_agent_token(AuthSubject(user=None, agent_token_id=None)))
        self.assertFalse(is_agent_token(AuthSubject(user=self.user_principal, agent_token_id=None)))
        self.assertTrue(is_agent_token(
            AuthSubject(user=None, agent_token_id=123)
        ))


class AgentTokenHashTests(TestCase):
    """``AgentToken.hash_token`` is the predicate used by auth lookup."""

    @classmethod
    def setUpTestData(cls):
        cls.sucursal = Sucursal.objects.create(nombre="FP-Hash", activa=True)

    def test_hash_is_sha256_hex(self):
        import hashlib
        token = "abcdef-12345-foo"
        self.assertEqual(
            AgentToken.hash_token(token),
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
        )

    def test_fingerprint_is_first_eight(self):
        agent = AgentToken.objects.create(
            name="fp-test",
            sucursal=self.sucursal,
            token_hash="f" * 64,
            public_url="https://example.com",
            is_active=True,
        )
        self.assertEqual(agent.token_fingerprint, "f" * 8)
