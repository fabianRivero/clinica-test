"""Resolve the admin URL footer for seed command summaries.

The admin URL is derived from project configuration (decision D4):

1. ``settings.SEED_ADMIN_URL`` is honored first when set. Trailing
   slashes are normalized away so the operator gets a clean URL.
2. Otherwise ``settings.BASE_URL`` is the fallback, with ``/admin``
   appended and slash-duplication removed.

A ``ValueError`` is raised when neither source is a valid absolute
``http(s)://`` URL — the caller (a management command) translates that
into a ``CommandError`` before any write happens.
"""

from urllib.parse import urlparse

from django.conf import settings


def _normalize(base: str, suffix: str = "") -> str:
    """Strip trailing slashes and append ``suffix`` cleanly."""
    base = base.rstrip("/")
    if suffix:
        return f"{base}/{suffix.lstrip('/')}"
    return base


def resolve_admin_url() -> str:
    """Return the normalized admin URL or raise ``ValueError``.

    Order of resolution:

    * If ``settings.SEED_ADMIN_URL`` is a non-empty string that parses
      as an absolute ``http`` or ``https`` URL, return it with trailing
      slashes trimmed.
    * Else, if ``settings.BASE_URL`` is a non-empty absolute ``http(s)://``
      URL, return ``BASE_URL + "/admin"`` with normalized slashes.
    * Else, raise ``ValueError`` so the caller can abort pre-write.
    """
    explicit = (getattr(settings, "SEED_ADMIN_URL", "") or "").strip()
    if explicit:
        parsed = urlparse(explicit)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return _normalize(explicit)
        raise ValueError(
            "SEED_ADMIN_URL is not an absolute http(s) URL: "
            f"{explicit!r}"
        )

    base = (getattr(settings, "BASE_URL", "") or "").strip()
    if base:
        parsed = urlparse(base)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return _normalize(base, "/admin")
        raise ValueError(
            "BASE_URL is not an absolute http(s) URL: "
            f"{base!r}"
        )

    raise ValueError(
        "Admin URL could not be resolved: both SEED_ADMIN_URL and "
        "BASE_URL are empty."
    )