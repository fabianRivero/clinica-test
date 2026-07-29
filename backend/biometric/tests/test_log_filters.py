"""Tests for the biometric log scrubber (spec requirement 15).

The application MUST keep template material out of log lines. The
scrubber must replace any contiguous base64-like blob over 256
characters with ``<biometric-template-redacted>``.
"""

from __future__ import annotations

import logging
import unittest

from biometric.log_filters import BiometricLogScrubber


def _make_record(msg, args=()):
    record = logging.LogRecord(
        name="biometric.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )
    return record


class BiometricLogScrubberTests(unittest.TestCase):
    def setUp(self):
        self.filter = BiometricLogScrubber()

    def test_long_base64_blob_redacted(self):
        blob = "A" * 500
        record = _make_record("captured template: %s", (blob,))
        self.filter.filter(record)
        rendered = record.getMessage()
        self.assertIn("<biometric-template-redacted>", rendered)
        self.assertNotIn(blob, rendered)

    def test_short_base64_blob_left_alone(self):
        short = "ABCDEFGHIJ"  # 10 chars, well under the threshold
        record = _make_record("short token: %s", (short,))
        self.filter.filter(record)
        self.assertIn(short, record.getMessage())

    def test_non_alnum_blob_unchanged(self):
        not_base64 = "*" * 500  # long but no [A-Za-z0-9+/=]
        record = _make_record("noise: %s", (not_base64,))
        self.filter.filter(record)
        # '*' isn't in the class, so it shouldn't be touched.
        self.assertEqual(record.getMessage(), "noise: " + not_base64)

    def test_filter_returns_true(self):
        record = _make_record("plain message")
        self.assertTrue(self.filter.filter(record))

    def test_handles_exception_in_get_message(self):
        class Bad:
            def __str__(self):
                raise RuntimeError("boom")

        record = logging.LogRecord(
            name="biometric.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="ok",
            args=(Bad(),),
            exc_info=None,
        )
        # The filter swallows errors and lets the record through.
        self.assertTrue(self.filter.filter(record))

    def test_msg_only_redacted(self):
        long_msg = "X" * 300
        record = _make_record(long_msg)
        self.filter.filter(record)
        self.assertIn("<biometric-template-redacted>", record.getMessage())
