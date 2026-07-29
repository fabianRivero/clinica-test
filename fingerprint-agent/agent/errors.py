"""Custom exceptions for the fingerprint agent.

Centralized so the HTTP layer can map them to clean status codes
without inspecting string messages.
"""

from __future__ import annotations


class AgentError(RuntimeError):
    """Base class for all agent errors."""


class AuthError(AgentError):
    """Raised when the bearer token is missing or invalid."""


class DeviceNotFoundError(AgentError):
    """Raised when no DigitalPersona 4500-like device is visible on D-Bus."""


class EnrollmentError(AgentError):
    """Raised when fprintd reports an enroll failure."""

    def __init__(self, message: str, status: str = "") -> None:
        super().__init__(message)
        self.status = status


class VerificationError(AgentError):
    """Raised when fprintd reports a verify failure."""

    def __init__(self, message: str, status: str = "") -> None:
        super().__init__(message)
        self.status = status


class BackendError(AgentError):
    """Raised when the upstream backend is unreachable."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


__all__ = [
    "AgentError",
    "AuthError",
    "BackendError",
    "DeviceNotFoundError",
    "EnrollmentError",
    "VerificationError",
]
