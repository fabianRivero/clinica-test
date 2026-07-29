"""Tests for the agent's base64 log scrubber."""

from __future__ import annotations

import logging

from agent.logging_config import BiometricLogScrubber, scrub


def _make_filter():
    return BiometricLogScrubber()


def test_scrub_replaces_long_base64_with_redaction():
    long_blob = "A" * 300
    text = f"got payload: {long_blob}; done"
    assert scrub(text) == "got payload: <biometric-redacted>; done"


def test_scrub_keeps_short_tokens():
    """Short tokens (under 256 chars) are NOT redacted."""
    text = "Bearer abcdef1234567890"
    assert scrub(text) == text


def test_scrub_keeps_normal_text():
    text = "Heartbeat returned 204"
    assert scrub(text) == text


def test_filter_redacts_log_message():
    """A real LogRecord carrying a long base64 blob is scrubbed."""
    filt = _make_filter()
    long_blob = "B" * 300
    record = logging.LogRecord(
        name="biometric",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=f"capture: {long_blob}",
        args=None,
        exc_info=None,
    )
    # Filter contract: return True means "let it through" (after mutation).
    assert filt.filter(record) is True
    assert "biometric-redacted" in record.getMessage()
    assert long_blob not in record.getMessage()


def test_filter_redacts_via_args():
    """``%s`` substitution is also covered."""
    filt = _make_filter()
    long_blob = "C" * 300
    record = logging.LogRecord(
        name="biometric",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="capture: %s",
        args=(long_blob,),
        exc_info=None,
    )
    assert filt.filter(record) is True
    rendered = record.getMessage()
    assert "biometric-redacted" in rendered
    assert long_blob not in rendered


def test_filter_passes_short_messages_through_unchanged():
    filt = _make_filter()
    record = logging.LogRecord(
        name="biometric",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Heartbeat ok (204)",
        args=None,
        exc_info=None,
    )
    # Re-pack behavior: when there's nothing to scrub, args are NOT
    # wiped (that would be a behavior change for callers).
    assert filt.filter(record) is True
    assert record.getMessage() == "Heartbeat ok (204)"


def test_filter_does_not_explode_on_broken_message():
    """A record whose getMessage() raises is passed through unmodified."""
    class _Broken:
        def getMessage(self):  # noqa: N802 - std API name
            raise RuntimeError("nope")

    record = logging.LogRecord(
        name="biometric",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ok",
        args=None,
        exc_info=None,
    )
    record.getMessage = _Broken().getMessage  # type: ignore[assignment]
    assert _make_filter().filter(record) is True
