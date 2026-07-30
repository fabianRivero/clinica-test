"""Unit tests for the defensive ``_reset_claim`` helper on
:class:`agent.fprintd_bridge.FprintdBridge`.

These tests never touch the real fprintd D-Bus — they build a tiny
fake ``_dev`` object that records the calls we make against it. The
``FprintdBridge.__init__`` is monkey-patched out so we can exercise
just ``_reset_claim`` in isolation. This is the second line of
defence: when the backend's ``agent_client.release()`` POST fails
(or is skipped because the agent is offline), ``verify()`` will
still issue a ``Release`` + ``Claim`` cycle on the bridge before
``VerifyStart``.
"""

from __future__ import annotations

import types

import pytest


class _FakeDev:
    """Records every ``Release`` / ``Claim`` call and can simulate
    fprintd's ``NotClaimed`` error on demand."""

    def __init__(self, *, raise_not_claimed_on_release: bool = False):
        self.calls: list[tuple[str, tuple]] = []
        self._raise_not_claimed_on_release = raise_not_claimed_on_release

    def Release(self) -> None:
        self.calls.append(("Release", ()))
        if self._raise_not_claimed_on_release:
            raise Exception(
                "net.reactivated.Fprint.Error.NotClaimed: not claimed"
            )

    def Claim(self, username: str) -> None:
        self.calls.append(("Claim", (username,)))


def _bridge_with(dev: _FakeDev) -> object:
    """Build an ``FprintdBridge``-like object without invoking its
    real ``__init__`` (which needs fprintd + dbus). We splice in the
    minimum state ``_reset_claim`` reads."""

    from agent.fprintd_bridge import FprintdBridge

    bridge = FprintdBridge.__new__(FprintdBridge)
    bridge.username = "test-agent"
    bridge._dev = dev
    return bridge


def test_reset_claim_issues_release_then_claim():
    dev = _FakeDev()
    bridge = _bridge_with(dev)
    bridge._reset_claim()  # type: ignore[attr-defined]
    assert dev.calls == [("Release", ()), ("Claim", ("test-agent",))]


def test_reset_claim_swallows_not_claimed():
    """``Release`` legitimately raises ``NotClaimed`` when the
    device was already unclaimed (e.g. right after a fresh enroll).
    The helper must swallow that error so ``Claim`` still runs."""
    dev = _FakeDev(raise_not_claimed_on_release=True)
    bridge = _bridge_with(dev)
    bridge._reset_claim()  # type: ignore[attr-defined]
    # Claim must have been issued even though Release raised.
    assert ("Claim", ("test-agent",)) in dev.calls


def test_reset_claim_logs_other_release_errors(caplog):
    """Any ``Release`` error that is NOT ``NotClaimed`` is logged
    but never re-raised."""

    class _Dev(_FakeDev):
        def Release(self) -> None:
            self.calls.append(("Release", ()))
            raise RuntimeError("fprintd is on fire")

    dev = _Dev()
    bridge = _bridge_with(dev)
    with caplog.at_level("DEBUG", logger="agent.fprintd_bridge"):
        bridge._reset_claim()  # type: ignore[attr-defined]
    # ``Claim`` must still run.
    assert ("Claim", ("test-agent",)) in dev.calls


def test_reset_claim_swallows_claim_error(caplog):
    """A ``Claim`` failure is logged but never re-raised — the verify
    call must still proceed to ``VerifyStart``."""

    class _Dev(_FakeDev):
        def Claim(self, username: str) -> None:
            self.calls.append(("Claim", (username,)))
            raise RuntimeError("claim denied")

    dev = _Dev()
    bridge = _bridge_with(dev)
    with caplog.at_level("WARNING", logger="agent.fprintd_bridge"):
        # Must NOT raise.
        bridge._reset_claim()  # type: ignore[attr-defined]
    assert ("Claim", ("test-agent",)) in dev.calls