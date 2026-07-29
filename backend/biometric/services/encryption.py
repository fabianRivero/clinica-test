"""Fernet-based encryption helpers for fingerprint templates.

Design constraint: a **single** Fernet key loaded from
``BIOMETRIC_FERNET_KEY``. No rotation, no key-id column. The
``Fernet`` instance is built once at module import time and reused so
we do not pay the key-validation cost on every capture.

Security posture:

- Fail-fast: a missing or malformed key raises
  ``ImproperlyConfigured`` so the app refuses to start (spec
  requirement "Missing key fails fast at startup").
- ``encrypt_template`` is one-way: ciphertext is opaque bytes; no
  plaintext is ever persisted or logged.
- ``decrypt_template`` propagates ``InvalidToken`` verbatim so the
  upper layer can detect "key rotated, re-enroll required" without
  ever seeing the plaintext.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)


def _build_fernet() -> Fernet:
    """Construct a :class:`Fernet` from the ``BIOMETRIC_FERNET_KEY`` env
    variable.

    Raises :class:`ImproperlyConfigured` when the variable is missing
    or does not decode into a valid Fernet key. The error message is
    intentionally verbose because it is only ever seen at boot
    (subsequent calls reuse the cached instance).
    """
    raw = os.getenv("BIOMETRIC_FERNET_KEY", "").strip()
    if not raw:
        logger.error(
            "BIOMETRIC_FERNET_KEY is not set; the biometric app will refuse "
            "to encrypt or decrypt templates. Generate a key with "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'` and set the env var."
        )
        raise ImproperlyConfigured(
            "BIOMETRIC_FERNET_KEY is required for the biometric app to "
            "start. Set it in the environment before launching Django."
        )
    try:
        key = raw.encode("utf-8")
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        logger.error("BIOMETRIC_FERNET_KEY is malformed: %s", exc)
        raise ImproperlyConfigured(
            "BIOMETRIC_FERNET_KEY is not a valid Fernet key (must be a "
            "url-safe base64-encoded 32-byte key)."
        ) from exc


# Single Fernet instance, built at import time. If the key is missing /
# malformed this raises ImproperlyConfigured and the app refuses to
# import (fail-fast).
FERNET: Fernet = _build_fernet()


def encrypt_template(plaintext: bytes) -> bytes:
    """Encrypt raw template bytes, returning a Fernet token.

    The plaintext is never stored beyond the in-memory call site.
    """
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError("encrypt_template expects bytes; got %r" % type(plaintext).__name__)
    return FERNET.encrypt(bytes(plaintext))


def decrypt_template(ciphertext: bytes) -> bytes:
    """Decrypt a Fernet token back to raw template bytes.

    Raises :class:`cryptography.fernet.InvalidToken` if the ciphertext
    was encrypted with a different key (handled at the view layer as a
    fail-closed "re-enroll required" outcome).
    """
    if not isinstance(ciphertext, (bytes, bytearray)):
        raise TypeError("decrypt_template expects bytes; got %r" % type(ciphertext).__name__)
    try:
        return FERNET.decrypt(bytes(ciphertext))
    except InvalidToken:
        # Re-raise verbatim per spec requirement "Wrong key fails closed".
        logger.warning(
            "Fernet decryption failed: ciphertext was not produced by the "
            "current BIOMETRIC_FERNET_KEY. Re-enrollment is required."
        )
        raise


__all__ = [
    "FERNET",
    "encrypt_template",
    "decrypt_template",
    "InvalidToken",
]
