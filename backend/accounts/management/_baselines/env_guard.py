"""Environment guard for non-production seed commands.

``require_dev_or_test`` enforces decision D5: the value of
``settings.ENVIRONMENT`` MUST be ``"development"`` or ``"test"`` for the
PDF demo command to proceed. Anything else (production, staging, an
empty value, etc.) raises ``CommandError`` before the transaction opens.

There is no confirmation override — the rejection is hard.
"""

from django.conf import settings
from django.core.management.base import CommandError


_ALLOWED_ENVS = {"development", "test"}


def require_dev_or_test(env_value=None) -> None:
    """Raise ``CommandError`` unless ``env_value`` is dev or test.

    ``env_value`` defaults to ``settings.ENVIRONMENT`` so callers usually
    pass nothing.
    """
    if env_value is None:
        env_value = getattr(settings, "ENVIRONMENT", None)
    if (env_value or "").strip().lower() not in _ALLOWED_ENVS:
        raise CommandError(
            "ENVIRONMENT must be one of "
            f"{sorted(_ALLOWED_ENVS)} to run this command; "
            f"got {env_value!r}."
        )