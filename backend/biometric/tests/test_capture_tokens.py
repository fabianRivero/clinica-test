"""Tests for the in-process capture token store."""

from __future__ import annotations

import os
import time
import unittest
from unittest import mock

from biometric.services.capture_tokens import (
    CaptureTokenStore,
    capture_token_store,
)


class CaptureTokenStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = CaptureTokenStore()
        self.store.reset()

    def test_create_and_pop(self):
        token = self.store.create({"kind": "enroll", "cliente_id": 1})
        self.assertEqual(len(token), 32)
        entry = self.store.pop(token)
        self.assertEqual(entry["kind"], "enroll")
        self.assertEqual(entry["cliente_id"], 1)
        # Single-use: popping again returns None.
        self.assertIsNone(self.store.pop(token))

    def test_peek_does_not_consume(self):
        token = self.store.create({"k": 1})
        self.assertEqual(self.store.peek(token), {"k": 1})
        self.assertEqual(self.store.pop(token), {"k": 1})

    def test_unknown_token(self):
        self.assertIsNone(self.store.pop("never-issued"))
        self.assertIsNone(self.store.peek("never-issued"))

    def test_ttl_expiry(self):
        token = self.store.create({"k": 1}, ttl_seconds=1)
        # Force expiry by stubbing monotonic to be well past the deadline.
        future = time.monotonic() + 10
        with mock.patch("biometric.services.capture_tokens.time.monotonic", return_value=future):
            self.assertIsNone(self.store.pop(token))


class ModuleSingletonTests(unittest.TestCase):
    def setUp(self):
        capture_token_store.reset()

    def test_singleton_can_be_reset(self):
        token = capture_token_store.create({"k": "singleton"})
        self.assertEqual(capture_token_store.pop(token), {"k": "singleton"})


class EnvTtlTests(unittest.TestCase):
    def test_default_ttl_is_300(self):
        os.environ.pop("BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS", None)
        from biometric.services.capture_tokens import _ttl_seconds
        self.assertEqual(_ttl_seconds(), 300)

    def test_env_override(self):
        with mock.patch.dict(
            os.environ, {"BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS": "12"}
        ):
            from biometric.services.capture_tokens import _ttl_seconds
            self.assertEqual(_ttl_seconds(), 12)
