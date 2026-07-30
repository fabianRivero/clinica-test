"""Normalize biometric template data on existing conversion drafts.

BEFORE commit c046991 ("fix(biometric): disable Fernet template
encryption for local testing"), the ``ProspectoConversionBorrador.datos_biometria.template``
field stored the template as raw bytes (Fernet ciphertext bytes,
or the literal "pending-enrollment" string for never-enrolled
drafts). When that was rendered to JSON for the reactivation /
finalize endpoints, the bytes broke ``json.dumps`` and Django returned
500 (TypeError: Object of type bytes is not JSON serializable).

The earlier fix added ``_normalize_biometric_draft_data`` which
handles the case at read time. This command is the data-only half:
it walks every existing draft and rewrites the ``template`` field to
a stable base64 string so the runtime normalizer becomes a
no-op for any row it touches.

The command is idempotent. Running it twice is safe: rows whose
``template`` is already a base64 string (or is the literal
"pending-enrollment" placeholder) are left alone.

Usage:
    python manage.py normalize_draft_templates
    python manage.py normalize_draft_templates --dry-run
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from django.core.management.base import BaseCommand

from customers.models import ProspectoConversionBorrador

logger = logging.getLogger(__name__)


def _normalize_template(value: Any) -> str | None:
    """Convert a stored template value to a stable base64 string."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return None


class Command(BaseCommand):
    help = "Rewrite stale bytes-typed template values in conversion drafts to base64."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without modifying any row.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        verb = "Would update" if dry_run else "Updated"
        considered = 0
        changed = 0
        for draft in ProspectoConversionBorrador.objects.all().iterator():
            considered += 1
            bio = draft.datos_biometria or {}
            if "template" not in bio:
                continue
            original = bio["template"]
            normalized = _normalize_template(original)
            if normalized is None or normalized == original:
                continue
            changed += 1
            self.stdout.write(
                f"{verb} draft id={draft.id} cliente_id={draft.cliente_id} "
                f"prospecto_id={draft.prospecto_id}"
            )
            if not dry_run:
                bio["template"] = normalized
                draft.datos_biometria = bio
                draft.save(update_fields=["datos_biometria", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Drafts considered: {considered}. Drafts changed: {changed}."
            )
        )
