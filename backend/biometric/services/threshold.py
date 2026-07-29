"""Server-side match threshold decision.

The agent never sees the threshold: it returns a raw score and we
decide whether the score is a match. This module is intentionally a
pure function so it is easy to test in isolation and reuse from
either API views, management commands, or batch jobs.
"""

from __future__ import annotations

import os
from decimal import Decimal


THRESHOLD_ENV = "BIOMETRIC_MATCH_THRESHOLD"
_DEFAULT_THRESHOLD = Decimal("0.85")


def get_threshold() -> Decimal:
    """Return the configured threshold clamped into ``[0, 1]``.

    Falls back to ``0.85`` when the env var is unset, empty, or invalid.
    """
    raw = os.getenv(THRESHOLD_ENV, "").strip()
    if not raw:
        return _DEFAULT_THRESHOLD
    try:
        value = Decimal(raw)
    except Exception:
        return _DEFAULT_THRESHOLD
    if value < Decimal("0") or value > Decimal("1"):
        return _DEFAULT_THRESHOLD
    return value


def decide_match(score: Decimal) -> tuple[bool, str]:
    """Return ``(matched, failure_reason)``.

    A score ``>=`` the configured threshold is treated as a match. The
    comparison uses :class:`decimal.Decimal` to preserve the precision
    configured for the ``BiometricAttempt.score`` column (5 digits,
    4 decimal places).

    Spec requirement 9 (Sensitivity Threshold Policy):

    - ``score >= threshold`` → ``matched=True`` with empty reason.
    - ``score <  threshold`` → ``matched=False`` with the code
      ``"score_below_threshold"`` so the caller can stamp it on the
      ``BiometricAttempt.failure_reason`` column.
    """
    if score is None:
        return False, "score_below_threshold"
    threshold = get_threshold()
    if score >= threshold:
        return True, ""
    return False, "score_below_threshold"


__all__ = [
    "THRESHOLD_ENV",
    "get_threshold",
    "decide_match",
]
