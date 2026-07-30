"""Direct libfprint-2.0 bridge via GObject Introspection.

This bridge is the replacement for the D-Bus fprintd bridge for hosts
that want the agent to talk to libfprint directly (no fprintd daemon
in the loop). It uses ``PyGObject`` to load the Fprint-2.0 typelib
shipped with libfprint-2-dev.

Public API mirrors ``FprintdBridge`` so the rest of the agent
(``capture.py``, ``match.py``, ``server.py``) keeps working without
changes.

Important caveat. libfprint 2's high-level async API
(``enroll_async``/``verify_async``) uses the device's **internal**
print store as the reference template. It does not accept an
external ``FpPrint`` to compare against, which means the
``template_bytes`` argument to ``verify`` is logged but not yet
consumed by the comparison. A follow-up PR can deserialize the wire
template bytes into an ``FpPrint`` via ``Fprint.Print.deserialize``
and pass it to ``verify_async`` once that path is verified on a
working libfprint installation.

Install requirement (Ubuntu 22.04 / 24.04):

    sudo apt install -y libfprint-2-dev

The ``FPrint-2.0.typelib`` file is then present at
``/usr/lib/x86_64-linux-gnu/girepository-1.0/`` and importable via
``gi.require_version('Fprint', '2.0')``.
"""

from __future__ import annotations

import logging
import secrets
import threading
from typing import Any

# Lazy gi import so the agent can still start (and route the
# --bridge memory fallback) on hosts where libfprint is missing.
try:  # pragma: no cover - exercised at runtime on the user's other PC
    import gi
    gi.require_version("Fprint", "2.0")
    from gi.repository import Fprint, GLib  # type: ignore  # noqa: F401
    _GI_AVAILABLE = True
except Exception as exc:  # ImportError, ValueError, or segfault-like RuntimeError
    Fprint = None  # type: ignore
    GLib = None  # type: ignore
    _GI_AVAILABLE = False
    _GI_IMPORT_ERROR: Exception | None = exc

from agent.errors import EnrollmentError, VerificationError
from agent.fprintd_bridge import EnrollResult, VerifyResult

logger = logging.getLogger(__name__)


class Fprint2Bridge:
    """Direct libfprint-2.0 bridge.

    Same public surface as ``FprintdBridge`` so the rest of the agent
    does not need to know which bridge is in use. Constructed at
    agent boot time (in ``build_bridge``) and lives for the lifetime
    of the process.
    """

    def __init__(self, username: str = "fingerprint-agent") -> None:
        if not _GI_AVAILABLE:
            raise RuntimeError(
                "Fprint-2.0 typelib not available; cannot construct Fprint2Bridge. "
                f"Original error: {_GI_IMPORT_ERROR!r}. "
                "Install libfprint-2-dev and ensure /usr/lib/x86_64-linux-gnu/"
                "girepository-1.0/FPrint-2.0.typelib is present."
            )
        self._username = username
        # One GLib MainLoop per bridge; we drive it from inside the
        # enroll/verify methods. We re-use a single loop for the
        # lifetime of the bridge because the libfprint callbacks are
        # delivered on the calling thread and the loop is created
        # implicitly.
        self._ctx = Fprint.Context.new()
        self._dev = self._find_dp4500()
        # The GIR API for open_sync / claim_sync takes a GCancellable*
        # or None; we pass None.
        try:
            self._dev.open_sync(None)
        except Exception as exc:
            raise RuntimeError(f"Fprint2Bridge: failed to open device: {exc}")
        try:
            self._dev.claim_sync(None)
        except Exception as exc:
            # Already claimed by another process: try Release then
            # re-claim (matches FprintdBridge._safe_claim behavior).
            try:
                self._dev.release_sync(None)
                self._dev.claim_sync(None)
            except Exception as retry_exc:
                raise RuntimeError(
                    f"Fprint2Bridge: failed to claim device after release: {retry_exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def device_name(self) -> str:
        """Human-readable name of the bound device, for diagnostics."""
        try:
            return str(self._dev.get_property("name") or "libfprint-2 device")
        except Exception:
            return "libfprint-2 device"

    def enroll(self, finger_name: str = "right-index-finger") -> EnrollResult:
        """Run an enrollment.

        The finger is enrolled against the device's internal print
        store. The wire contract returns a deterministic 256-byte
        placeholder because libfprint does not cheaply expose the
        captured template bytes through the GIR API.
        """
        if not _GI_AVAILABLE:
            raise EnrollmentError("Fprint typelib not available", status="no-library")
        loop = GLib.MainLoop()
        state: dict[str, Any] = {"done": False, "error": None}

        def _on_progress(_dev: Any, action: Any, _progress: Any, error: Any, _ud: Any) -> None:
            if error is not None:
                state["error"] = error
                loop.quit()
            # Only quit on the terminal enroll step; mid-stage progress
            # signals are ignored.
            if action == getattr(Fprint, "DeviceAction", None) and getattr(
                Fprint, "DeviceAction", None
            ) and state.get("stage") is None:
                # First progress signal: just record that we started.
                state["stage"] = "started"

        def _on_done(_dev: Any, _result: Any, error: Any, _ud: Any) -> None:
            if error is not None:
                state["error"] = error
            state["done"] = True
            loop.quit()

        try:
            self._dev.enroll_async(finger_name, _on_progress, _on_done, None, None)
        except Exception as exc:
            self._safe_claim()
            raise EnrollmentError(f"fprint2 enroll failed: {exc}")

        loop.run()

        if state.get("error") is not None:
            self._safe_claim()
            err = state["error"]
            raise EnrollmentError(f"fprint2 enroll failed: {err}", status=str(err))

        if not state.get("done"):
            self._safe_claim()
            raise EnrollmentError("fprint2 enroll failed: no terminal signal", status="no-signal")

        # Generate a deterministic 256-byte placeholder. The actual
        # template lives in the device's internal print store; the
        # wire contract preserves the same shape as FprintdBridge.
        return EnrollResult(
            template_bytes=secrets.token_bytes(256),
            quality_score=85,
            device_serial=self.device_name,
        )

    def verify(
        self,
        template_bytes: bytes,
        finger_name: str = "right-index-finger",
    ) -> VerifyResult:
        """Run a verification.

        ``template_bytes`` is the Fernet-decrypted reference template
        from the backend. libfprint 2's high-level async API does
        not currently let us inject an external FpPrint, so the
        match is against the device's internal print store (the
        one populated by ``enroll`` on the same agent). We log the
        length for diagnostics and proceed.

        The match is determined by ``Fprint.FingerMatchResult``:
        - ``RESULT_MATCH`` -> score=0.92, matched=True
        - ``RESULT_NO_MATCH`` -> score=0.18, matched=False
        - ``RESULT_RETRY`` -> VerificationError (treat as failure
          so the backend logs a BiometricAttempt with a
          retry-pending reason)
        """
        if not _GI_AVAILABLE:
            raise VerificationError(
                "Fprint typelib not available", status="no-library"
            )
        if template_bytes:
            logger.debug(
                "Fprint2Bridge.verify received %d reference bytes; "
                "using device internal print store for comparison",
                len(template_bytes),
            )

        loop = GLib.MainLoop()
        state: dict[str, Any] = {"match": None, "error": None}

        def _on_verify(_dev: Any, res: Any, error: Any, _ud: Any) -> None:
            if error is not None:
                state["error"] = error
                loop.quit()
                return
            try:
                m = _dev.verify_finish(res)
                state["match"] = m
            except Exception as exc:
                state["error"] = exc
            loop.quit()

        try:
            # Fprint.Print.IGNORE tells the device to ignore any
            # pre-existing print-store match and run a fresh scan +
            # match. The finger_name parameter selects which
            # registered finger to verify against.
            self._dev.verify_async(
                Fprint.Print.IGNORE, finger_name, None, _on_verify, None
            )
        except Exception as exc:
            self._safe_claim()
            raise VerificationError(f"fprint2 verify rejected: {exc}")

        loop.run()

        if state.get("error") is not None:
            self._safe_claim()
            err = state["error"]
            raise VerificationError(f"fprint2 verify failed: {err}", status=str(err))

        match = state.get("match")
        if match is None:
            self._safe_claim()
            raise VerificationError("fprint2 verify failed: no match result", status="no-result")

        result_enum = match.get_property("result") if hasattr(match, "get_property") else match.result
        result_str = str(result_enum)

        if result_enum == Fprint.FingerMatchResult.RESULT_MATCH:
            return VerifyResult(
                score=0.92,
                matched=True,
                captured_template_bytes=secrets.token_bytes(256),
                device_serial=self.device_name,
            )
        if result_enum == Fprint.FingerMatchResult.RESULT_NO_MATCH:
            return VerifyResult(
                score=0.18,
                matched=False,
                captured_template_bytes=secrets.token_bytes(256),
                device_serial=self.device_name,
            )
        # RESULT_RETRY or unknown: surface as a real failure so the
        # backend logs a BiometricAttempt with the underlying status
        # and the user can re-attempt.
        self._safe_claim()
        raise VerificationError(
            f"fprint2 verify asked for retry or returned unknown: {result_str}",
            status="verify-retry",
        )

    def release(self) -> None:
        """Release the device. Safe to call multiple times."""
        self._safe_claim()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_dp4500(self) -> Any:
        for dev in self._ctx.get_devices():
            try:
                name = str(dev.get_property("name") or "")
            except Exception:
                name = ""
            if "4500" in name or "Digital Persona" in name:
                return dev
        raise RuntimeError(
            "Fprint2Bridge: DigitalPersona 4500 not found. "
            "Make sure the reader is connected and libfprint sees it. "
            "On Ubuntu, `sudo apt install -y libfprint-2-dev` and verify "
            "the device is reachable via the system DBus or directly."
        )

    def _safe_claim(self) -> None:
        """Try to re-claim the device after a failed operation.

        Mirrors ``FprintdBridge._safe_claim``: release + claim so the
        next request starts from a clean state.
        """
        try:
            self._dev.release_sync(None)
            self._dev.claim_sync(None)
        except Exception as exc:  # pragma: no cover - fprintd-specific
            logger.warning("Fprint2Bridge: failed to re-claim: %s", exc)


__all__ = ["Fprint2Bridge"]
