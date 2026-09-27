"""Service-key resolver for the dp4500_integration client.

Phase 2 supports only the ``env`` backend: ``DP4500_SERVICE_KEY_SUCURSAL_<id>``
in os.environ. Phase 4 adds ``vault``.

The resolver is invoked once per HTTP call. It MUST NOT log or persist
the raw key (the client side does no logging of the key; this
function returns it for the Authorization header and that is the only
use).
"""
from __future__ import annotations

import os


def env_key_resolver(sucursal_id: int) -> str | None:
    """Return the raw bearer token for ``sucursal_id`` from os.environ.

    Returns ``None`` if no env var is set. Never raises. Never logs.
    """
    return os.environ.get(f"DP4500_SERVICE_KEY_SUCURSAL_{sucursal_id}")
