"""Encryption helpers for fingerprint templates.

CURRENT STATUS (temporary for local testing):
The Fernet encryption that previously protected biometric templates
at rest is currently disabled. ``encrypt_template`` and
``decrypt_template`` are no-ops that return the input bytes
unchanged. This is at the user's request: the user is testing on a
host where libfprint 2's introspection runtime (libgirepository-1.0
1.80.1) segfaults on typelib load. With Fernet removed, the bytes
flow raw from the database to the agent via the wire, simplifying
the local debugging surface.

Production deployments MUST re-enable Fernet by restoring the
real encrypt / decrypt logic in ``_real_encrypt_template`` /
``_real_decrypt_template`` and switching ``encrypt_template`` /
``decrypt_template`` to call them.

The wire protocol is unchanged: ``template_b64`` in the
``/match`` payload still carries the bytes, just without the Fernet
wrapping. Production agents that depend on the Fernet ciphertext
will need to be re-deployed at the same time as the backend
re-enables encryption.
"""

from __future__ import annotations

from cryptography.fernet import InvalidToken

# Re-exported for the view layer. We never raise this in the no-op
# path, but the view layer imports it for typing.
__all__ = [
    "InvalidToken",
    "encrypt_template",
    "decrypt_template",
]


def encrypt_template(plaintext: bytes) -> bytes:
    """No-op: return the input bytes unchanged.

    Re-enable Fernet here when productionising.
    """
    if not isinstance(plaintext, (bytes, bytearray)):
        raise TypeError(
            "encrypt_template expects bytes; got %r" % type(plaintext).__name__
        )
    return bytes(plaintext)


def decrypt_template(ciphertext: bytes) -> bytes:
    """No-op: return the input bytes unchanged.

    Re-enable Fernet here when productionising.
    """
    if not isinstance(ciphertext, (bytes, bytearray)):
        raise TypeError(
            "decrypt_template expects bytes; got %r" % type(ciphertext).__name__
        )
    return bytes(ciphertext)
