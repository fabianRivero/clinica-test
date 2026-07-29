"""``POST /capture`` — enrollment capture endpoint.

The frontend calls this *after* the backend has handed out a
``capture_token`` (and the wizard's UX told the agent to start
capturing). The agent runs an enrollment via fprintd, returns the
freshly captured template bytes (hex-encoded for compatibility with
the backend's existing storage path), and reports a quality score.

Wire contract (matches the backend's existing ``CaptureResponse``):

- Request:  ``{"capture_token": str, "finger_name": str, "quality_required": int}``
- Response: ``{"template_b64": hex, "quality_score": int, "device_serial": str, "width": int, "height": int}``

The ``template_b64`` field name is historical — PR #1 used hex
encoding and the backend views still do ``bytes.fromhex`` on it. We
keep that contract stable so the swap to this real client is
non-breaking.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from agent.auth import require_bearer
from agent.errors import EnrollmentError
from agent.logging_config import scrub


if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agent.config import AgentConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CaptureRequest(BaseModel):
    """Body for ``POST /capture``."""

    capture_token: str = Field(..., min_length=4, max_length=128)
    finger_name: str = Field(default="any", max_length=64)
    quality_required: int = Field(default=60, ge=0, le=100)


class CaptureResponse(BaseModel):
    """Body returned by ``POST /capture``."""

    template_b64: str
    quality_score: int
    device_serial: str
    width: int
    height: int


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(app, config: "AgentConfig") -> None:
    """Register the ``POST /capture`` route on ``app``.

    The route is built at registration time so the bearer token
    (loaded from the config) is captured by closure.
    """

    require = require_bearer(config)

    @app.post("/capture", response_model=CaptureResponse, tags=["capture"])
    async def capture(
        req: CaptureRequest,
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> CaptureResponse:
        # Validate the bearer token first.
        await require(authorization=authorization)

        bridge = request.app.state.fprintd_bridge
        try:
            result = bridge.enroll(req.finger_name)
        except EnrollmentError as exc:
            logger.warning(
                "Enrollment failed for token=%s: %s",
                scrub(req.capture_token),
                exc.status,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "ENROLL_FAILED", "status": exc.status},
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected failure during /capture")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"code": "AGENT_UNAVAILABLE", "error": str(exc)},
            )

        if result.quality_score < req.quality_required:
            logger.info(
                "Low quality capture: %d < %d (token=%s)",
                result.quality_score,
                req.quality_required,
                scrub(req.capture_token),
            )
            # We still return the template — the backend decides
            # whether to reject based on its own threshold. Returning
            # an empty template here lets the backend raise LOW_QUALITY
            # without ever shipping the captured bytes to disk.
            return CaptureResponse(
                template_b64="",
                quality_score=result.quality_score,
                device_serial=result.device_serial,
                width=0,
                height=0,
            )

        logger.info(
            "Capture ok: token=%s quality=%d device=%s",
            scrub(req.capture_token),
            result.quality_score,
            result.device_serial,
        )
        return CaptureResponse(
            template_b64=result.template_bytes.hex(),
            quality_score=result.quality_score,
            device_serial=result.device_serial,
            width=256,
            height=364,
        )


__all__ = ["register", "CaptureRequest", "CaptureResponse"]
