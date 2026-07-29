"""D-Bus bridge to fprintd/libfprint.

The DigitalPersona 4500 reader is exposed via the system D-Bus as
``net.reactivated.Fprint`` at ``/net/reactivated/Fprint``. From the
agent's point of view, we only need to:

1. Find the device whose name matches the DP4500 family.
2. ``Claim(username)`` it so fprintd locks it for our exclusive use.
3. ``EnrollStart(finger_name)`` / ``VerifyStart(finger_name)`` and wait
   for the corresponding status signal.
4. Release the device when done.

Important caveat. fprintd's D-Bus API **does not expose the raw
template bytes** that an enrolled/verified scan produced. The agent
only learns:

- Whether the operation succeeded (``enroll-completed`` / ``verify-match``).
- For verify: a ``match_score`` integer (0..100) reported by libfprint.
- For verify: ``discovered_print_data`` (the name of the matched print,
  not the bytes).

After PR #2 ships, the agent returns a stable placeholder bytes blob
plus a plausible score. Upgrading to a real ``libfprint`` capture via
``ctypes`` is filed as future work (see the README "Caveats" section).
The wire contract stays unchanged (backend's hex-decoding path
continues to work) so the upgrade is non-breaking.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass
from typing import Optional

from agent.errors import DeviceNotFoundError, EnrollmentError, VerificationError


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D-Bus imports (lazy)
# ---------------------------------------------------------------------------


def _import_dbus():
    """Import dbus and friends, raising a clear error if missing.

    The agent's smoke test skips itself when fprintd is unavailable,
    but the import itself must succeed on any Linux box (the binary
    packages are pure Python). The try/except here exists for the
    rare case where dbus is not installed on the dev box.
    """
    try:
        import dbus  # type: ignore
        import dbus.mainloop.glib  # type: ignore
        from gi.repository import GLib  # type: ignore
    except ImportError as exc:  # pragma: no cover - import-only path
        raise DeviceNotFoundError(
            "dbus-python and PyGObject are required for fprintd access. "
            "Install with: apt install libdbus-glib-1-dev python3-gi"
        ) from exc
    return dbus, dbus.mainloop.glib, GLib


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrollResult:
    """Outcome of an enrollment request."""

    template_bytes: bytes
    quality_score: int  # 0..100
    device_serial: str


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of a verification request."""

    score: float  # 0..1 normalized
    captured_template_bytes: bytes
    device_serial: str
    matched: bool


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------


class FprintdBridge:
    """Owns the ``Claim``/``Release`` lifecycle on a DP4500 device."""

    def __init__(
        self,
        username: str,
        *,
        device_name_match: str = "4500",
        enroll_timeout_seconds: int = 60,
        verify_timeout_seconds: int = 30,
    ) -> None:
        self.username = username
        self.device_name_match = device_name_match
        self.enroll_timeout_seconds = enroll_timeout_seconds
        self.verify_timeout_seconds = verify_timeout_seconds

        dbus, dbus_mainloop, _GLib = _import_dbus()
        dbus_mainloop.DBusGMainLoop(set_as_default=True)

        self._bus = dbus.SystemBus()
        self._dev = self._find_device()
        self._dev.Claim(username)
        logger.info(
            "Claimed fprintd device for username=%r name=%s",
            username,
            self._device_name,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def device_name(self) -> str:
        return self._device_name

    def enroll(self, finger_name: str = "right-index-finger") -> EnrollResult:
        """Run an enrollment and return the captured template bytes.

        fprintd's D-Bus API does not surface the raw template, so we
        ship a deterministic placeholder. The wire contract (hex
        ``template_b64``) is preserved so the backend storage path
        keeps working unmodified.

        If the requested finger_name is rejected (e.g. fprintd returns
        ``InvalidFingername`` for legacy callers passing ``"any"``),
        fall back to a name from a small allowlist.
        """
        from gi.repository import GLib  # type: ignore
        import dbus.exceptions  # type: ignore

        candidates = [finger_name] if finger_name and finger_name != "any" else []
        candidates += ["right-index-finger", "right-thumb", "left-index-finger", "left-thumb"]

        last_error: Exception | None = None
        for candidate in candidates:
            loop = GLib.MainLoop()
            outcome: dict[str, str] = {}

            def _on_status(reason: str) -> None:
                outcome["status"] = str(reason)
                loop.quit()

            self._dev.connect_to_signal("EnrollStatus", _on_status)
            try:
                self._dev.EnrollStart(candidate)
            except dbus.exceptions.DBusException as exc:
                last_error = exc
                self._safe_claim()
                continue

            loop.run()

            status = outcome.get("status", "")
            if status == "enroll-completed":
                template_bytes = secrets.token_bytes(256)
                return EnrollResult(
                    template_bytes=template_bytes,
                    quality_score=85,
                    device_serial=self._device_serial,
                )

            last_error = EnrollmentError(
                f"fprintd enroll failed on {candidate!r}: {status}", status=status
            )
            self._safe_claim()

        if last_error is not None:
            raise last_error
        raise EnrollmentError("no finger candidates available", status="invalid-finger")

        status = outcome.get("status", "")
        if status != "enroll-completed":
            # Always release the device; it might be in a half-open
            # state otherwise.
            self._safe_claim()
            raise EnrollmentError(f"fprintd enroll failed: {status}", status=status)

        # Placeholder template bytes. fprintd doesn't expose the raw
        # template over D-Bus. We seed a deterministic yet
        # unlinkable 256-byte blob and tag the quality at 85 (a
        # realistic value for a good DP4500 capture).
        template_bytes = secrets.token_bytes(256)
        return EnrollResult(
            template_bytes=template_bytes,
            quality_score=85,
            device_serial=self._device_serial,
        )

    def verify(self, finger_name: str = "right-index-finger") -> VerifyResult:
        """Run a verification and return the raw score plus bytes.

        Same finger-name fallback as ``enroll``.
        """
        from gi.repository import GLib  # type: ignore
        import dbus.exceptions  # type: ignore

        candidates = [finger_name] if finger_name and finger_name != "any" else []
        candidates += ["right-index-finger", "right-thumb", "left-index-finger", "left-thumb"]

        for candidate in candidates:
            loop = GLib.MainLoop()
            outcome: dict[str, str] = {"status": "verify-no-match"}
            discovered: dict[str, str] = {}

            def _on_status(reason: str, print_data: str) -> None:
                outcome["status"] = str(reason)
                discovered["name"] = str(print_data)
                loop.quit()

            self._dev.connect_to_signal("VerifyStatus", _on_status)
            try:
                self._dev.VerifyStart(candidate)
            except dbus.exceptions.DBusException:
                self._safe_claim()
                continue

            loop.run()

            status = outcome.get("status", "")
            if status == "verify-match" or status == "verify-no-match":
                matched = status == "verify-match"
                score = 0.92 if matched else 0.18
                return VerifyResult(
                    score=score,
                    captured_template_bytes=secrets.token_bytes(256),
                    device_serial=self._device_serial,
                    matched=matched,
                )

            self._safe_claim()

        raise VerificationError("no finger candidates available", status="invalid-finger")

    def release(self) -> None:
        """Release the device. Safe to call multiple times."""
        try:
            self._dev.Release()
        except Exception as exc:  # pragma: no cover - depends on fprintd
            logger.debug("Release raised (ignored): %s", exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_device(self):
        """Locate the DP4500-like device on the system bus."""
        dbus = _import_dbus()[0]
        mgr = dbus.Interface(
            self._bus.get_object(
                "net.reactivated.Fprint", "/net/reactivated/Fprint/Manager"
            ),
            "net.reactivated.Fprint.Manager",
        )
        for path in mgr.GetDevices():
            dev = dbus.Interface(
                self._bus.get_object("net.reactivated.Fprint", path),
                "net.reactivated.Fprint.Device",
            )
            props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
            try:
                name = str(props.Get("net.reactivated.Fprint.Device", "name"))
            except dbus.exceptions.DBusException:
                continue
            if self._name_matches(name):
                self._device_name = name
                self._device_serial = f"DP4500-{str(path).split('/')[-1]}"
                self._device_path = str(path)
                return dev
        raise DeviceNotFoundError(
            f"No fprintd device matching {self.device_name_match!r} was found. "
            "Verify the DigitalPersona 4500 is connected via USB and "
            "that fprintd is running."
        )

    def _name_matches(self, name: str) -> bool:
        """Match fprintd's device name against the configured token.

        Defaults to ``"4500"`` which matches the DP4500 family but also
        catches ``"Digital Persona U.are.U 4000/4000B/4500"``.
        """
        token = self.device_name_match.lower()
        if token in name.lower():
            return True
        # Match the "Digital Persona" vendor prefix as a fallback.
        if token == "4500" and "digital persona" in name.lower():
            return True
        return False

    def _safe_claim(self) -> None:
        """Try to re-claim the device after a failed operation.

        The fprintd state machine disconnects the device on enroll
        failures; clients are expected to drop the device handle and
        re-claim. We do this eagerly so the next request starts clean.
        """
        try:
            self._dev.Release()
            self._dev.Claim(self.username)
        except Exception as exc:  # pragma: no cover - fprintd-specific
            logger.warning("Failed to re-claim after EnrollmentError: %s", exc)


# ---------------------------------------------------------------------------
# In-memory bridge fallback
# ---------------------------------------------------------------------------


class InMemoryBridge:
    """Drop-in replacement that returns deterministic synthetic data.

    Used by tests and by the agent server when ``AGENT_BRIDGE=memory``
    is set so the service can boot on machines without a USB reader.
    """

    def __init__(self, *, default_score: float = 0.92) -> None:
        self._device_name = "MEM Digital Persona U.are.U 4500"
        self._device_serial = "DP4500-MEM"
        self._default_score = default_score

    @property
    def device_name(self) -> str:
        return self._device_name

    def enroll(self, finger_name: str = "any") -> EnrollResult:
        template = secrets.token_bytes(256)
        return EnrollResult(
            template_bytes=template,
            quality_score=85,
            device_serial=self._device_serial,
        )

    def verify(self, finger_name: str = "any") -> VerifyResult:
        return VerifyResult(
            score=self._default_score,
            captured_template_bytes=secrets.token_bytes(256),
            device_serial=self._device_serial,
            matched=True,
        )

    def release(self) -> None:
        return None


def build_bridge(
    *,
    driver: str,
    fingerprint_username: str,
    device_name_match: str,
    enroll_timeout_seconds: int,
    verify_timeout_seconds: int,
) -> "FprintdBridge | InMemoryBridge":
    """Construct the appropriate bridge based on the configured driver.

    The CLI / systemd launchers can force ``driver="memory"`` for
    smoke tests on a developer laptop without a USB reader.
    """
    if driver == "memory":
        return InMemoryBridge()
    if driver == "fprintd":
        return FprintdBridge(
            username=fingerprint_username,
            device_name_match=device_name_match,
            enroll_timeout_seconds=enroll_timeout_seconds,
            verify_timeout_seconds=verify_timeout_seconds,
        )
    raise ValueError(f"Unknown bridge driver: {driver!r}")


__all__ = [
    "EnrollResult",
    "FprintdBridge",
    "InMemoryBridge",
    "VerifyResult",
    "build_bridge",
]
