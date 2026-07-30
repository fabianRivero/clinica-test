"""Tests for the Fprint2Bridge (libfprint via GObject Introspection).

The orchestrator's dev machine has a corrupted libgirepository that
segfaults on Fprint-2.0 typelib load. These tests therefore mock
the entire ``gi.repository`` namespace before importing
``agent.fprint2_bridge``, so they run cleanly in CI and on dev
machines without working typelibs.
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# Helpers: build a fake Fprint 2.0 typelib in memory.
# ---------------------------------------------------------------------------


def _install_fake_gi(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Replace the bits of ``gi.repository.Fprint`` the bridge uses.

    Returns a dict with the ``MagicMock`` instances the tests can
    inspect, so the bridge's real API surface is exercised.
    """
    mocks: dict = {}

    class _Enum:
        """Tiny stand-in for GEnum."""

        def __init__(self, value: int, name: str) -> None:
            self.value = value
            self.name = name

        def __eq__(self, other: object) -> bool:
            if isinstance(other, _Enum):
                return self.value == other.value
            return self.value == other

        def __hash__(self) -> int:
            return hash(self.value)

        def __repr__(self) -> str:
            return self.name

    class _DeviceAction:
        ENROLL = _Enum(0, "ENROLL")
        VERIFY = _Enum(1, "VERIFY")
        IDENTIFY = _Enum(2, "IDENTIFY")

    class _Print:
        IGNORE = _Enum(0, "IGNORE")
        UNSAVE = _Enum(1, "UNSAVE")
        SAVE = _Enum(2, "SAVE")

    class _FingerMatchResult:
        RESULT_NO_MATCH = _Enum(0, "NO_MATCH")
        RESULT_MATCH = _Enum(1, "MATCH")
        RESULT_RETRY = _Enum(-1, "RETRY")
        RESULT_UNKNOWN = _Enum(-2, "UNKNOWN")

    class _Context:
        @classmethod
        def new(cls) -> "_Context":
            return _Context()

        def get_devices(self) -> list:
            return [device]

    class _Device:
        # configurable per-test
        open_result: BaseException | None = None
        claim_result: BaseException | None = None
        enroll_result: tuple | BaseException = (None, None)
        verify_result: tuple | BaseException = (None, None)
        release_result: BaseException | None = None

        def open_sync(self, _cancellable) -> None:
            if self.open_result is not None:
                raise self.open_result

        def claim_sync(self, _cancellable) -> None:
            if self.claim_result is not None:
                raise self.claim_result

        def release_sync(self, _cancellable) -> None:
            if self.release_result is not None:
                raise self.release_result

        def get_property(self, name: str) -> str:
            if name == "name":
                return "Digital Persona U.are.U 4000/4000B/4500"
            return ""

        def enroll_async(self, finger_name, on_progress, on_done, cancellable, user_data) -> None:
            # Synchronously drive the callbacks so the loop.quit() runs.
            if isinstance(self.enroll_result, BaseException):
                on_done(self, None, self.enroll_result, user_data)
                return
            result, error = self.enroll_result
            on_progress(self, _DeviceAction.ENROLL, 1.0, error, user_data)
            on_done(self, result, error, user_data)

        def verify_async(self, print_ignore, finger_name, cancellable, callback, user_data) -> None:
            if isinstance(self.verify_result, BaseException):
                callback(self, None, self.verify_result, user_data)
                return
            match_obj, error = self.verify_result
            callback(self, match_obj, error, user_data)

        def verify_finish(self, _res) -> object:
            # verify_finish returns whatever verify_result holds as
            # the "match" object.
            return self.verify_result[0]

    device = _Device()
    device._Device = _Device  # type: ignore[attr-defined]
    mocks["device"] = device

    fprint_module = types.ModuleType("gi.repository.Fprint")
    fprint_module.Context = _Context
    fprint_module.Device = _Device
    fprint_module.DeviceAction = _DeviceAction
    fprint_module.Print = _Print
    fprint_module.FingerMatchResult = _FingerMatchResult
    # Mark the typelib as available.
    fprint_module.__getattr__ = lambda _name: None  # type: ignore[attr-defined]

    gi_module = types.ModuleType("gi")
    gi_module.require_version = mock.MagicMock()
    repository_module = types.ModuleType("gi.repository")
    repository_module.Fprint = fprint_module
    # Make sure Fprint is accessible via getattr on the submodule.
    repository_module.__getattr__ = lambda name: getattr(  # type: ignore[attr-defined]
        {"Fprint": fprint_module, "GLib": mock.MagicMock()}.get(name, mock.MagicMock()),
        name,
    )
    glib_module = types.ModuleType("gi.repository.GLib")
    glib_module.MainLoop = mock.MagicMock()

    monkeypatch.setitem(sys.modules, "gi", gi_module)
    monkeypatch.setitem(sys.modules, "gi.repository", repository_module)
    monkeypatch.setitem(sys.modules, "gi.repository.Fprint", fprint_module)
    monkeypatch.setitem(sys.modules, "gi.repository.GLib", glib_module)

    return mocks


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_gi(monkeypatch: pytest.MonkeyPatch) -> dict:
    return _install_fake_gi(monkeypatch)


def test_enroll_happy_path(fake_gi: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    # Reload to ensure the module picks up the fake gi before its
    # top-level gi.require_version runs.
    importlib.reload(bridge_mod)

    fake_gi["device"].enroll_result = (mock.MagicMock(name="EnrollResult"), None)
    bridge = bridge_mod.Fprint2Bridge(username="fingerprint-agent")
    result = bridge.enroll("right-index-finger")
    assert result.template_bytes is not None
    assert len(result.template_bytes) == 256
    assert result.quality_score == 85
    assert "Digital Persona" in result.device_serial
    assert bridge_mod._GI_AVAILABLE is True


def test_enroll_failure_emits_error(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    fake_gi["device"].enroll_result = RuntimeError("user cancelled")
    bridge = bridge_mod.Fprint2Bridge()
    with pytest.raises(bridge_mod.EnrollmentError):
        bridge.enroll()


def test_enroll_completes_via_callback(fake_gi: dict) -> None:
    """The progress callback should be invoked and the loop should quit on done."""
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    progress_calls: list = []
    done_calls: list = []

    # Replace the GLib MainLoop to record calls
    glib = sys.modules["gi.repository.GLib"]
    glib.MainLoop = mock.MagicMock()
    glib.MainLoop.return_value.run = lambda self: None
    glib.MainLoop.return_value.quit = lambda self: None

    # Track progress and done callbacks by patching enroll_async on the device
    device = fake_gi["device"]
    original_enroll_async = device.enroll_async

    def tracking_enroll_async(finger_name, on_progress, on_done, cancellable, user_data):
        progress_calls.append((finger_name, on_progress, on_done))
        # Simulate a successful completion path
        on_progress(device, bridge_mod.Fprint.DeviceAction.ENROLL, 1.0, None, user_data)
        on_done(device, mock.MagicMock(name="EnrollResult"), None, user_data)

    device.enroll_async = tracking_enroll_async  # type: ignore[method-assign]

    bridge = bridge_mod.Fprint2Bridge()
    bridge.enroll("right-index-finger")
    assert len(progress_calls) == 1
    assert progress_calls[0][0] == "right-index-finger"

    # Restore for other tests
    device.enroll_async = original_enroll_async  # type: ignore[method-assign]


def test_verify_match(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    match_obj = mock.MagicMock()
    match_obj.get_property.return_value = bridge_mod.Fprint.FingerMatchResult.RESULT_MATCH
    fake_gi["device"].verify_result = (match_obj, None)
    bridge = bridge_mod.Fprint2Bridge()
    result = bridge.verify(b"placeholder-template-bytes", finger_name="right-index-finger")
    assert result.matched is True
    assert result.score == 0.92


def test_verify_no_match(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    match_obj = mock.MagicMock()
    match_obj.get_property.return_value = bridge_mod.Fprint.FingerMatchResult.RESULT_NO_MATCH
    fake_gi["device"].verify_result = (match_obj, None)
    bridge = bridge_mod.Fprint2Bridge()
    result = bridge.verify(b"template", finger_name="right-index-finger")
    assert result.matched is False
    assert result.score == 0.18


def test_verify_retry_raises(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    match_obj = mock.MagicMock()
    match_obj.get_property.return_value = bridge_mod.Fprint.FingerMatchResult.RESULT_RETRY
    fake_gi["device"].verify_result = (match_obj, None)
    bridge = bridge_mod.Fprint2Bridge()
    with pytest.raises(bridge_mod.VerificationError) as exc_info:
        bridge.verify(b"template")
    assert exc_info.value.status == "verify-retry"


def test_verify_error_propagates(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    fake_gi["device"].verify_result = RuntimeError("libfprint broken")
    bridge = bridge_mod.Fprint2Bridge()
    with pytest.raises(bridge_mod.VerificationError):
        bridge.verify(b"template")


def test_template_bytes_is_logged_but_does_not_control_match(fake_gi: dict) -> None:
    """Two verifies with different template_bytes both rely on the
    device's INTERNAL print store. The bridge must accept the bytes
    for forward-compat but the match result is independent of them.
    """
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    match_obj = mock.MagicMock()
    match_obj.get_property.return_value = bridge_mod.Fprint.FingerMatchResult.RESULT_MATCH
    fake_gi["device"].verify_result = (match_obj, None)
    bridge = bridge_mod.Fprint2Bridge()

    r1 = bridge.verify(b"template-A", finger_name="right-index-finger")
    r2 = bridge.verify(b"template-B", finger_name="right-index-finger")
    assert r1.matched == r2.matched == True
    assert r1.score == r2.score == 0.92


def test_release_swallows_errors(fake_gi: dict) -> None:
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    fake_gi["device"].release_result = RuntimeError("not claimed")
    bridge = bridge_mod.Fprint2Bridge()
    # Should not raise even though release_sync would.
    bridge.release()
    # No exception means the test passed.


def test_safe_claim_releases_then_re_claims(fake_gi: dict) -> None:
    """When claim_sync raises the first time, _safe_claim retries
    release+claim, and the constructor should not raise.
    """
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    call_count = {"n": 0}

    def claim_twice(_cancellable):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("busy")

    fake_gi["device"].claim_sync = claim_twice  # type: ignore[method-assign]
    # Constructor should swallow the first failure and retry, succeeding.
    bridge = bridge_mod.Fprint2Bridge()
    assert bridge is not None
    assert call_count["n"] == 2


def test_fails_when_typelib_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a working typelib, importing the module and constructing
    the bridge should fail with a clear error.
    """
    # Strip the fake modules so the bridge's gi import raises ImportError.
    for name in [
        "agent.fprint2_bridge",
        "gi.repository.Fprint",
        "gi.repository.GLib",
        "gi.repository",
        "gi",
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    import builtins
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "gi" or name.startswith("gi."):
            raise ImportError("Fprint typelib not available")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)
    assert bridge_mod._GI_AVAILABLE is False
    with pytest.raises(RuntimeError) as exc_info:
        bridge_mod.Fprint2Bridge()
    assert "Fprint-2.0 typelib not available" in str(exc_info.value)


def test_does_not_find_dp4500_raises_runtime_error(fake_gi: dict) -> None:
    """If no device matches, the bridge should fail at construction
    time, not at enroll/verify time.
    """
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    # Override the Context.get_devices to return no devices.
    bridge_mod.Fprint.Context.get_devices = lambda self: []

    with pytest.raises(RuntimeError) as exc_info:
        bridge_mod.Fprint2Bridge()
    assert "DigitalPersona 4500 not found" in str(exc_info.value)


def test_fingerprint_username_is_optional(fake_gi: dict) -> None:
    """Fprint2Bridge should construct with the default username."""
    bridge_mod = importlib.import_module("agent.fprint2_bridge")
    importlib.reload(bridge_mod)

    bridge = bridge_mod.Fprint2Bridge()
    assert bridge._username == "fingerprint-agent"
