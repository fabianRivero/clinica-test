"""``POST /release`` — reset the fprintd device state.

The backend calls this endpoint immediately before each ``/match`` so
``VerifyStart`` runs against a freshly Claim-ed device. fprintd's
internal ``VerifyStatus`` state leaks across ``VerifyStart`` calls
while the device stays Claim-ed: the second ``VerifyStart`` returns
``verify-no-match`` within milliseconds instead of waiting the full
``verify_timeout_seconds`` for a finger contact, which is what makes
the operator feel that the retry "didn't even try" on the second
attempt.

The bridge's own ``_reset_claim`` (called at the top of
``FprintdBridge.verify``) covers this in-process; this endpoint exists
so the backend can request the same reset explicitly without round-
tripping through the verify operation. Failures are deliberately
swallowed at the HTTP layer — a failed reset must never propagate as
an error to the caller, the bridge's defensive reset is the fallback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Header, Request
from pydantic import BaseModel

from agent.auth import require_bearer


if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agent.config import AgentConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReleaseRequest(BaseModel):
    """Body for ``POST /release``.

    The endpoint accepts an empty body; the schema is here so the
    FastAPI OpenAPI document stays accurate.
    """

    pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(app, config: "AgentConfig") -> None:
    """Register the ``POST /release`` route on ``app``."""

    require = require_bearer(config)

    @app.post("/release", tags=["release"])
    async def release(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> dict[str, str]:
        await require(authorization=authorization)

        bridge = request.app.state.fprintd_bridge
        # ``InMemoryBridge.release`` is a no-op, ``FprintdBridge.release``
        # performs the actual ``Release`` D-Bus call. Either way, the
        # bridge's ``_reset_claim`` runs at the top of the next
        # ``verify()`` so the reset is always applied even when this
        # endpoint is missing or fails.
        try:
            bridge.release()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("bridge.release() raised (ignored): %s", exc)
            # Fall through to a 200 anyway: the bridge's defensive
            # ``_reset_claim`` will cover the next verify.
        return {"status": "ok"}


__all__ = ["register", "ReleaseRequest"]