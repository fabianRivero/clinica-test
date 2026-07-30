"""Tests for the encryption service.

CURRENT BEHAVIOUR (temporary for local testing):
``encrypt_template`` and ``decrypt_template`` are no-ops that return
the input bytes unchanged. The Fernet encryption that previously
protected biometric templates at rest is currently disabled at the
user's request (see encryption.py for context).

Production deployments must re-enable Fernet and update these
tests to assert real encryption. Until then, the tests verify the
no-op identity contract: the bytes are passed through unchanged
and the absence of a key does not raise.
"""

from __future__ import annotations

import importlib
import os
import unittest


def _reload():
    """Reload the encryption module under the current environment."""
    return importlib.reload(importlib.import_module(
        "biometric.services.encryption"
    ))


class EncryptionNoOpRoundTripTests(unittest.TestCase):
    """Encryption is currently disabled. The helpers are identity
    functions on the input bytes; the wire protocol carries the
    bytes raw (no Fernet wrapping)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Make sure the key is absent so the no-op branch is exercised.
        os.environ.pop("BIOMETRIC_FERNET_KEY", None)
        cls.enc = importlib.import_module("biometric.services.encryption")

    def setUp(self):
        # Each test reloads the module in case a previous test left
        # a key in the environment.
        os.environ.pop("BIOMETRIC_FERNET_KEY", None)
        self.enc = _reload()

    def test_encrypt_returns_input_unchanged(self):
        original = b"fingerprint-template-payload-x" * 8
        out = self.enc.encrypt_template(original)
        self.assertIsInstance(out, bytes)
        self.assertEqual(out, original)

    def test_decrypt_returns_input_unchanged(self):
        original = b"fingerprint-template-payload-x" * 8
        out = self.enc.decrypt_template(original)
        self.assertIsInstance(out, bytes)
        self.assertEqual(out, original)

    def test_encrypt_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            self.enc.encrypt_template("not bytes")  # type: ignore[arg-type]

    def test_decrypt_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            self.enc.decrypt_template("cipher")  # type: ignore[arg-type]


class EncryptionKeyOptionalTests(unittest.TestCase):
    """With Fernet disabled, the key is no longer required at boot.
    These tests assert the relaxed contract."""

    def setUp(self):
        os.environ.pop("BIOMETRIC_FERNET_KEY", None)

    def test_missing_key_does_not_raise(self):
        # Importing the module without a key must not raise
        # ImproperlyConfigured (it used to when Fernet was active).
        try:
            _reload()
        except Exception as exc:  # pragma: no cover
            self.fail(f"Reload should not raise, got: {exc}")

    def test_malformed_key_does_not_raise(self):
        os.environ["BIOMETRIC_FERNET_KEY"] = "not-a-fernet-key"
        try:
            _reload()
        except Exception as exc:  # pragma: no cover
            self.fail(f"Reload with malformed key should not raise, got: {exc}")
        # Clean up for the next test.
        os.environ.pop("BIOMETRIC_FERNET_KEY", None)
