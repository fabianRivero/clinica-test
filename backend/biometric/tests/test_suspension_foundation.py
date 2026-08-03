"""Foundation contracts for biometric suspension (PR 1).

Change: ``suspend-fingerprint-integration``.

These tests cover the **foundational, slice-agnostic** pieces only:

- The shared response builders (``enrollment_suspended_payload``,
  ``verification_suspended_payload``, ``agent_suspended_payload``)
  return the exact contract shapes the spec demands.
- All three bodies share the canonical ``code=BIOMETRIC_SUSPENDED`` so
  clients have a single switch to detect the suspended mode.

The setting-level wiring (``BIOMETRIC_SUSPENDED`` → factory) is
covered deterministically by ``SuspendedFactoryTests`` in
``test_agent_client.py``: those tests flip the flag via
``override_settings`` and assert the factory returns
:class:`SuspendedAgentClient`, which is the actual observable
contract of the env_bool→setting→factory chain. Re-testing
``env_bool`` in isolation here would duplicate coverage and risk
becoming brittle as Django reload semantics evolve.

Endpoint-level gating and HTTP-503 wiring belong to PR 2 of the same
change (task 2.5). Those tests will sit beside the existing
``test_endpoints.py`` families and are out of scope here.
"""

from __future__ import annotations

import unittest

from django.test import SimpleTestCase

from biometric.serializers import (
    BIOMETRIC_SUSPENDED_CODE,
    BIOMETRIC_SUSPENDED_DETAIL,
    agent_suspended_payload,
    enrollment_suspended_payload,
    verification_suspended_payload,
)


class EnrollmentSuspendedPayloadTests(SimpleTestCase):
    """Enrollment / re-enrollment / finalize / prospect-enrollment share
    one body shape: ``{detail, code, enrollment_available:false}``."""

    def test_shape_matches_spec(self):
        body = enrollment_suspended_payload()
        self.assertEqual(
            set(body.keys()), {"detail", "code", "enrollment_available"}
        )

    def test_code_is_canonical(self):
        body = enrollment_suspended_payload()
        self.assertEqual(body["code"], BIOMETRIC_SUSPENDED_CODE)
        self.assertEqual(body["code"], "BIOMETRIC_SUSPENDED")

    def test_enrollment_available_is_false(self):
        """The flag must be a literal ``False`` so JSON serialisation
        produces ``false`` (not omitted)."""
        body = enrollment_suspended_payload()
        self.assertIs(body["enrollment_available"], False)

    def test_detail_is_human_readable(self):
        body = enrollment_suspended_payload()
        self.assertEqual(body["detail"], BIOMETRIC_SUSPENDED_DETAIL)
        self.assertTrue(body["detail"])  # non-empty


class VerificationSuspendedPayloadTests(SimpleTestCase):
    """Verification / canonical and legacy biometric confirmation share
    ``{detail, code, manual_only:true, matched:false}``."""

    def test_shape_matches_spec(self):
        body = verification_suspended_payload()
        self.assertEqual(
            set(body.keys()), {"detail", "code", "manual_only", "matched"}
        )

    def test_code_is_canonical(self):
        body = verification_suspended_payload()
        self.assertEqual(body["code"], BIOMETRIC_SUSPENDED_CODE)

    def test_manual_only_is_true(self):
        """``manual_only`` must be the literal ``True`` so the frontend
        keeps rendering the manual confirmation path."""
        body = verification_suspended_payload()
        self.assertIs(body["manual_only"], True)

    def test_matched_is_false(self):
        """``matched`` must be the literal ``False`` so a stale caller
        cannot interpret the suspended response as a successful match."""
        body = verification_suspended_payload()
        self.assertIs(body["matched"], False)


class AgentSuspendedPayloadTests(SimpleTestCase):
    """Agent mutation / heartbeat / delete share ``{detail, code}``."""

    def test_shape_matches_spec(self):
        body = agent_suspended_payload()
        self.assertEqual(set(body.keys()), {"detail", "code"})

    def test_code_is_canonical(self):
        body = agent_suspended_payload()
        self.assertEqual(body["code"], BIOMETRIC_SUSPENDED_CODE)

    def test_no_extra_keys(self):
        """Read endpoints (list, history) are NOT gated by the
        foundation contract — keeping the body to ``{detail, code}``
        prevents accidental leakage of operator hints."""
        body = agent_suspended_payload()
        self.assertNotIn("manual_only", body)
        self.assertNotIn("matched", body)
        self.assertNotIn("enrollment_available", body)


class CrossFamilyConsistencyTests(SimpleTestCase):
    """Every family must agree on the canonical code and detail."""

    def test_all_families_share_code(self):
        self.assertEqual(enrollment_suspended_payload()["code"], BIOMETRIC_SUSPENDED_CODE)
        self.assertEqual(verification_suspended_payload()["code"], BIOMETRIC_SUSPENDED_CODE)
        self.assertEqual(agent_suspended_payload()["code"], BIOMETRIC_SUSPENDED_CODE)

    def test_all_families_share_detail(self):
        self.assertEqual(
            enrollment_suspended_payload()["detail"], BIOMETRIC_SUSPENDED_DETAIL
        )
        self.assertEqual(
            verification_suspended_payload()["detail"], BIOMETRIC_SUSPENDED_DETAIL
        )
        self.assertEqual(
            agent_suspended_payload()["detail"], BIOMETRIC_SUSPENDED_DETAIL
        )

    def test_payloads_are_independent_calls(self):
        """Each call must return a fresh dict so callers can mutate
        the body without bleeding across families."""
        a = enrollment_suspended_payload()
        b = enrollment_suspended_payload()
        self.assertIsNot(a, b)
        a["code"] = "MUTATED"
        self.assertEqual(b["code"], BIOMETRIC_SUSPENDED_CODE)


if __name__ == "__main__":  # pragma: no cover - manual debugging
    unittest.main()
