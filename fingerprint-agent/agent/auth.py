"""Bearer-token authentication for the agent's HTTP endpoints.

The agent has a single shared bearer token (see ``config.ini``). Every
protected endpoint validates ``Authorization: Bearer <token>`` using
a constant-time comparison to avoid timing attacks. The token is loaded
once at boot and held in memory.

We expose a FastAPI dependency so each route can declare its
requirement as ``Depends(require_bearer)``. ``/health`` is intentionally
NOT protected.
"""

from __future__ import annotations

import hmac
from typing import Callable

from fastapi import Header, HTTPException, status

from agent.config import AgentConfig
from agent.errors import AuthError


def _extract_bearer(authorization: str | None) -> str:
    """Parse the Authorization header and return the raw token.

    Returns ``""`` if the header is missing, malformed, or empty.
    Mirrors RFC 7235 (case-insensitive scheme).
    """
    if not authorization:
        return ""
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def _validate(expected: str, authorization: str | None) -> bool:
    """Constant-time comparison of the bearer token against ``expected``."""
    provided = _extract_bearer(authorization)
    if not provided or not expected:
        return False
    # hmac.compare_digest requires the two operands to be of the same
    # type. We coerce both to bytes for a stable comparison.
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def require_bearer(config: AgentConfig) -> Callable:
    """Build a FastAPI dependency that enforces ``Authorization: Bearer``.

    Usage::

        from fastapi import Depends
        from agent.auth import require_bearer

        @router.post("/capture", dependencies=[Depends(require_bearer(config))])
        async def capture(req: CaptureRequest): ...

    Raises :class:`HTTPException` 401 on any failure.
    """

    expected = config.raw_token

    async def _dep(authorization: str | None = Header(default=None)) -> None:
        if not _validate(expected, authorization):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _dep


def check_authorization(config: AgentConfig, authorization: str | None) -> None:
    """Imperative variant used by code paths that don't go through FastAPI.

    Raises :class:`AuthError` on invalid input. Useful for tests and
    scripts that bypass the HTTP layer.
    """
    if not _validate(config.raw_token, authorization):
        raise AuthError("Invalid or missing bearer token.")


__all__ = ["check_authorization", "require_bearer"]
