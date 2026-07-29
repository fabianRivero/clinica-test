"""Logging filters for the biometric module.

The spec requires that base64-like template material never appears in
logs. Anything that looks like a long base64 blob (over 256 chars) is
scrubbed to a sentinel before the record reaches a handler.

We deliberately redact in-place on both ``record.msg`` and ``record.args``
because ``getMessage()`` is called by every Django log handler at flush
time and we cannot rely on the handler doing the substitution.
"""

from __future__ import annotations

import logging
import re

# A base64-like blob: 256+ chars of [A-Za-z0-9+/=]. We deliberately allow
# common base64 chars (including padding `=`) so URLs and short tokens are
# left alone.
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/=]{256,}")
_REDACTION = "<biometric-template-redacted>"


class BiometricLogScrubber(logging.Filter):
    """Replaces long base64-like blobs in log records.

    The filter is safe for the default ``logging.Filter`` protocol:
    returning ``True`` means "let this record through". We mutate the
    record in-place rather than dropping it.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 - std API name
        try:
            msg = record.getMessage()
        except Exception:
            return True

        scrubbed = _BASE64_BLOB.sub(_REDACTION, msg)
        if scrubbed == msg:
            return True

        # Re-pack the record so that ``getMessage()`` returns the
        # scrubbed text from now on.
        record.msg = scrubbed
        record.args = ()
        return True


class BiometricOnlyLogScrubber(BiometricLogScrubber):
    """Variant that only redacts records from the ``biometric`` logger.

    Apply this on a per-logger basis when you don't want the global
    behavior. Otherwise prefer attaching :class:`BiometricLogScrubber`
    to the root handler.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if not record.name.startswith("biometric"):
            return True
        return super().filter(record)


__all__ = ["BiometricLogScrubber", "BiometricOnlyLogScrubber"]
