"""Tests for the threshold policy (spec requirement 9).

Boundary behavior per the spec: a score exactly equal to the
threshold is treated as a match.
"""

from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest import mock

from biometric.services.threshold import decide_match, get_threshold


class ThresholdTests(unittest.TestCase):
    def setUp(self):
        # Lock threshold to a known value via env var.
        os.environ["BIOMETRIC_MATCH_THRESHOLD"] = "0.85"

    def tearDown(self):
        os.environ.pop("BIOMETRIC_MATCH_THRESHOLD", None)

    def test_score_above_threshold_matches(self):
        self.assertEqual(decide_match(Decimal("0.92")), (True, ""))

    def test_score_below_threshold_rejects(self):
        self.assertEqual(
            decide_match(Decimal("0.71")),
            (False, "score_below_threshold"),
        )

    def test_score_at_exact_threshold_matches(self):
        # Spec: score >= threshold -> success. Boundary belongs to match.
        self.assertEqual(decide_match(Decimal("0.85")), (True, ""))

    def test_score_just_below_threshold_rejects(self):
        self.assertEqual(
            decide_match(Decimal("0.8499")),
            (False, "score_below_threshold"),
        )

    def test_score_just_above_threshold_matches(self):
        self.assertEqual(decide_match(Decimal("0.8501")), (True, ""))

    def test_none_score_rejects(self):
        self.assertEqual(decide_match(None), (False, "score_below_threshold"))


class ThresholdConfigTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("BIOMETRIC_MATCH_THRESHOLD", None)

    def tearDown(self):
        os.environ.pop("BIOMETRIC_MATCH_THRESHOLD", None)

    def test_default_threshold_is_0_85(self):
        self.assertEqual(get_threshold(), Decimal("0.85"))

    def test_custom_threshold(self):
        with mock.patch.dict(os.environ, {"BIOMETRIC_MATCH_THRESHOLD": "0.90"}):
            self.assertEqual(get_threshold(), Decimal("0.90"))

    def test_out_of_range_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"BIOMETRIC_MATCH_THRESHOLD": "1.5"}):
            self.assertEqual(get_threshold(), Decimal("0.85"))

    def test_garbage_value_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"BIOMETRIC_MATCH_THRESHOLD": "abc"}):
            self.assertEqual(get_threshold(), Decimal("0.85"))

    def test_empty_string_falls_back_to_default(self):
        with mock.patch.dict(os.environ, {"BIOMETRIC_MATCH_THRESHOLD": ""}):
            self.assertEqual(get_threshold(), Decimal("0.85"))
