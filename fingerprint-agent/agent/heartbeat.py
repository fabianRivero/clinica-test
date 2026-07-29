"""``POST /heartbeat`` — periodic ping to the backend.

The agent sends a heartbeat to the backend every
``backend.heartbeat_interval_seconds`` (default 60s) so the admin UI
can render the agent's online/offline status. The backend endpoint
``POST /api/biometric/agents/<id>/heartbeat/`` is a no-op that just
updates ``last_seen_at`` and returns 204.

The agent's outbound call uses the same bearer token as the inbound
``/capture``/``/match`` endpoints. We keep this client-server relationship
strictly one-to-one: the agent never embeds any agent secrets in
outbound payloads.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx
from fastapi import Response, status

from agent.errors import BackendError


if TYPE_CHECKING:  # pragma: no cover - type-checking only
    from agent.config import AgentConfig


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heartbeat client
# ---------------------------------------------------------------------------


class HeartbeatClient:
    """Owns the outbound heartbeat loop.

    Spawned as a background task at app startup. Reused across events
    so the same httpx client (with connection pooling) is kept alive
    for the life of the process.
    """

    def __init__(self, config: "AgentConfig") -> None:
        self._config = config
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._stopping = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return bool(self._config.backend_api_base) and self._config.agent_id > 0

    async def start(self) -> None:
        if not self.enabled:
            logger.info("Heartbeat disabled (no backend configured).")
            return
        if self._task is not None:
            return
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers={"Authorization": f"Bearer {self._config.raw_token}"},
        )
        self._stopping.clear()
        self._task = asyncio.create_task(self._run(), name="agent-heartbeat")
        logger.info("Heartbeat task started (interval=%ds)", self._config.heartbeat_interval_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _run(self) -> None:
        url = f"{self._config.backend_api_base}/api/biometric/agents/{self._config.agent_id}/heartbeat/"
        while not self._stopping.is_set():
            try:
                resp = await self._client.post(url)
                if resp.status_code >= 500:
                    logger.warning(
                        "Heartbeat returned %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                else:
                    logger.debug("Heartbeat ok (%d)", resp.status_code)
            except httpx.HTTPError as exc:
                logger.warning("Heartbeat transport error: %s", exc)
            except Exception as exc:  # pragma: no cover - defensive
                logger.exception("Heartbeat unexpected error: %s", exc)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._config.heartbeat_interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def ping_once(self) -> None:
        """Manual ping - exposed through ``POST /heartbeat`` for testing."""
        if not self.enabled:
            raise BackendError("Heartbeat disabled: backend.api_base unset.")
        url = f"{self._config.backend_api_base}/api/biometric/agents/{self._config.agent_id}/heartbeat/"
        try:
            resp = await self._client.post(url)
        except httpx.HTTPError as exc:
            raise BackendError(str(exc), status_code=0) from exc
        if resp.status_code >= 400:
            raise BackendError(
                f"Backend returned {resp.status_code}",
                status_code=resp.status_code,
            )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


def register(app, config: "AgentConfig") -> None:
    """Register the ``POST /heartbeat`` route + the lifecycle hooks."""

    @app.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT, tags=["heartbeat"])
    async def heartbeat() -> Response:
        client: HeartbeatClient = app.state.heartbeat_client
        try:
            await client.ping_once()
        except BackendError as exc:
            logger.warning("Manual heartbeat ping failed: %s", exc)
            # Per spec requirement 11 the heartbeat endpoint always
            # returns 204 even on internal errors. We respect that on
            # the inbound side too.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.on_event("startup")
    async def _startup() -> None:
        client = HeartbeatClient(config)
        app.state.heartbeat_client = client
        await client.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        client = getattr(app.state, "heartbeat_client", None)
        if client is not None:
            await client.stop()


__all__ = ["HeartbeatClient", "register"]
