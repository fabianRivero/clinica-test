"""Tests for the AgentToken model helpers (PR #2 additions)."""

from __future__ import annotations

import hashlib

from django.test import TestCase

from biometric.models import AgentToken
from biometric.services.encryption import encrypt_template
from catalogs.models import Sucursal


class AgentTokenEncryptedTests(TestCase):
    """Cover the new ``token_encrypted`` field and ``decrypt_raw_token``."""

    def setUp(self):
        self.sucursal = Sucursal.objects.create(nombre="SucAT", activa=True)

    def _make_agent(self, raw: str) -> AgentToken:
        return AgentToken.objects.create(
            name="agent",
            sucursal=self.sucursal,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            public_url="https://agent.example.com",
            is_active=True,
            token_encrypted=encrypt_template(raw.encode("utf-8")),
        )

    def test_decrypt_raw_token_round_trip(self):
        raw = "raw-token-abc"
        agent = self._make_agent(raw)
        self.assertEqual(agent.decrypt_raw_token(), raw)

    def test_decrypt_raw_token_missing_blob_raises(self):
        raw = "raw-token-abc"
        agent = AgentToken.objects.create(
            name="agent",
            sucursal=self.sucursal,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            public_url="https://agent.example.com",
            is_active=True,
            # token_encrypted intentionally omitted.
        )
        with self.assertRaises(RuntimeError):
            agent.decrypt_raw_token()

    def test_decrypt_raw_token_wrong_key_raises(self):
        raw = "raw-token-abc"
        agent = AgentToken.objects.create(
            name="agent",
            sucursal=self.sucursal,
            token_hash=hashlib.sha256(raw.encode()).hexdigest(),
            public_url="https://agent.example.com",
            is_active=True,
            token_encrypted=b"not-a-real-fernet-token",
        )
        with self.assertRaises(RuntimeError):
            agent.decrypt_raw_token()
