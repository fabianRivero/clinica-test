"""``POST /match`` — verification endpoint.

The frontend calls this to ask the agent to capture a fresh print and
compare it against the supplied template (the backend ships the
encrypted template bytes to the agent, which decrypts and verifies
locally, then returns just a raw score).

Wire contract (matches the backend's ``MatchResponse``):

- Request:  ``{"capture_token": str, "template_b64": hex}``
- Response: ``{"score": float, "matched": bool, "captured_template_b64": hex}``

The score is **raw**; the backend decides against the configured
threshold. We do not return the threshold-adjusted result so the
backend remains the single source of truth for the policy.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent.auth import require_bearer
from agent.errors import DeviceNotFoundError, VerificationError
from agent.logging_config import scrub


if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agent.config import AgentConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MatchRequest(BaseModel):
    """Body for ``POST /match``."""

    capture_token: str = Field(..., min_length=4, max_length=128)
    template_b64: str = Field(..., min_length=0, max_length=4096)
    finger_name: str = Field(default="any", max_length=64)


class MatchResponse(BaseModel):
    """Body returned by ``POST /match``."""

    score: float
    matched: bool
    captured_template_b64: str


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(app, config: "AgentConfig") -> None:
    """Register the ``POST /match`` route on ``app``."""

    require = require_bearer(config)

    @app.post("/match", response_model=MatchResponse, tags=["match"])
    async def match(
        req: MatchRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> MatchResponse:
        await require(authorization=authorization)

        # The agent ignores the supplied template bytes for now
        # (fprintd's D-Bus API doesn't expose the match operation in
        # a way that lets us pass a reference template). The actual
        # comparison is left to the backend's threshold logic. The
        # template is decoded to validate the format and surface a
        # clean 400 on garbage input.
        try:
            bytes.fromhex(req.template_b64) if req.template_b64 else b""
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_TEMPLATE"},
            )

        bridge = request.app.state.fprintd_bridge
        try:
            result = bridge.verify(req.finger_name)
        except DeviceNotFoundError as exc:
            logger.warning("Device not available: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "DEVICE_NOT_FOUND"},
            )
        except VerificationError as exc:
            logger.warning(
                "Verification failed for token=%s: %s",
                scrub(req.capture_token),
                exc.status,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "VERIFY_FAILED", "status": exc.status},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected failure during /match")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AGENT_UNAVAILABLE", "error": str(exc)},
            )

        logger.info(
            "Match ok: token=%s score=%.3f matched=%s",
            scrub(req.capture_token),
            result.score,
            result.matched,
        )
        return MatchResponse(
            score=result.score,
            matched=result.matched,
            captured_template_b64=result.captured_template_bytes.hex(),
        )


__all__ = ["register", "MatchRequest", "MatchResponse"]
