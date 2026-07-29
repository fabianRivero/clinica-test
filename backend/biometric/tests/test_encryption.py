"""Tests for the encryption service.

Cover the spec scenarios for requirement 1 (Encrypted Template
Storage):

- round-trip encrypt+decrypt yields original bytes (Scenario:
  Template persisted encrypted / Round-trip decryption succeeds).
- wrong key raises :class:`InvalidToken` and never leaks plaintext
  (Scenario: Wrong key fails closed).
- missing or malformed key raises :class:`ImproperlyConfigured` at
  module import (Scenario: Missing key fails fast at startup).

Each test reloads the module under controlled environment variables
because the service module binds its :class:`Fernet` instance at
import time.
"""

from __future__ import annotations

import importlib
import os
import unittest
from unittest import mock

from cryptography.fernet import Fernet, InvalidToken

from django.core.exceptions import ImproperlyConfigured


def _reload(monkeypatched_environ: dict[str, str] | None = None):
    """Reload ``biometric.services.encryption`` under a controlled env."""
    saved = {k: os.environ.get(k) for k in (
        "BIOMETRIC_FERNET_KEY",
    )}
    try:
        if monkeypatched_environ is None:
            os.environ.pop("BIOMETRIC_FERNET_KEY", None)
        else:
            for k, v in monkeypatched_environ.items():
                os.environ[k] = v
        return importlib.reload(importlib.import_module(
            "biometric.services.encryption"
        ))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _ensure_key_loaded():
    """Force a fresh key and reload so tests that run after a fail-fast
    test still have a working Fernet instance.
    """
    os.environ["BIOMETRIC_FERNET_KEY"] = Fernet.generate_key().decode()
    return importlib.reload(importlib.import_module(
        "biometric.services.encryption"
    ))


class EncryptionRoundTripTests(unittest.TestCase):
    """Scenarios: Template persisted encrypted, Round-trip decryption."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ["BIOMETRIC_FERNET_KEY"] = Fernet.generate_key().decode()
        cls.enc = importlib.import_module("biometric.services.encryption")

    def test_round_trip(self):
        original = b"fingerprint-template-payload-x" * 8
        ciphertext = self.enc.encrypt_template(original)
        self.assertIsInstance(ciphertext, bytes)
        self.assertNotEqual(ciphertext, original)
        self.assertEqual(self.enc.decrypt_template(ciphertext), original)

    def test_encrypt_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            self.enc.encrypt_template("not bytes")  # type: ignore[arg-type]

    def test_decrypt_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            self.enc.decrypt_template("cipher")  # type: ignore[arg-type]


class EncryptionWrongKeyTests(unittest.TestCase):
    """Scenario: Wrong key fails closed."""

    def setUp(self):
        self.key_a = Fernet.generate_key()
        self.key_b = Fernet.generate_key()
        os.environ["BIOMETRIC_FERNET_KEY"] = self.key_b.decode()
        self.enc = importlib.reload(importlib.import_module(
            "biometric.services.encryption"
        ))
        self.ciphertext_a = Fernet(self.key_a).encrypt(b"original-template-123")

    def test_wrong_key_raises_invalid_token(self):
        with self.assertRaises(InvalidToken):
            self.enc.decrypt_template(self.ciphertext_a)

    def test_exception_message_omits_plaintext(self):
        try:
            self.enc.decrypt_template(self.ciphertext_a)
        except InvalidToken as exc:
            self.assertNotIn("original-template-123", str(exc))
        else:
            self.fail("InvalidToken was not raised")


class EncryptionFailFastTests(unittest.TestCase):
    """Scenario: Missing key fails fast at startup."""

    def setUp(self):
        # Each test relocates a key after, so other tests stay clean.
        self._previous = os.environ.get("BIOMETRIC_FERNET_KEY")

    def tearDown(self):
        _ensure_key_loaded()

    def test_missing_key_raises_improperly_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(importlib.import_module(
                    "biometric.services.encryption"
                ))

    def test_malformed_key_raises_improperly_configured(self):
        with mock.patch.dict(
            os.environ, {"BIOMETRIC_FERNET_KEY": "not-a-fernet-key"}
        ):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(importlib.import_module(
                    "biometric.services.encryption"
                ))
