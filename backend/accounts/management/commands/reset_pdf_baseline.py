"""Destructive orchestrator that resets the PDF demo baseline in one step.

This command is a sibling of ``seed_pdf_baseline`` and ``seed_client_baseline``.
It composes the existing destructive purge (``purge_data_keep_admin --force``)
with the non-destructive PDF demo seed (``seed_pdf_baseline``) inside a single
``transaction.atomic`` boundary, behind the same ``require_dev_or_test()``
pre-write guard used by ``seed_pdf_baseline``.

Why this command exists:

* Manual two-step (``purge_data_keep_admin --force`` then ``seed_pdf_baseline``)
  runs in two transactions. A failure in the seed half leaves the database
  purged with no rollback, losing demo data with no operator-visible error
  pointing at the rollback boundary.
* One-shot destructive-then-seed waveform inside a single transaction gives
  operators a clean atomic boundary: either the database ends up with a fresh
  PDF demo state, or it is unchanged.
* The waveform is idempotent: running it twice in a row produces byte-stable
  record counts.

Hard guarantees:

* Refuses to run outside ``development`` or ``test`` via
  ``require_dev_or_test()``. No override flag. Same guard as ``seed_pdf_baseline``.
* Writes a ``WARNING``-styled destructive-wipe header before any inner command
  so the operator cannot miss what is about to happen.
* Nullifies purge-target foreign keys on preserved superusers before SQLite
  disables FK enforcement, keeping the outer commit integrity check clean.
* Does NOT modify ``seed_pdf_baseline.py``, ``seed_client_baseline.py``,
  ``purge_data_keep_admin.py``, or ``env_guard.py``. Sibling commands stay
  byte-stable; this command composes them via ``call_command`` only.

Run::

    ENVIRONMENT=development python manage.py reset_pdf_baseline

Anything other than ``development`` or ``test`` aborts with ``CommandError``
before any write.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.models import Usuario


class Command(BaseCommand):
    """Destructive orchestrator: purge + reseed PDF demo baseline atomically."""

    help = (
        "Destructive orchestrator: purges business data (preserving admin "
        "users) and re-seeds the PDF demo baseline inside one transaction. "
        "Refuses to run outside development/test. Idempotent across reruns."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # Pre-transaction guard. Raises CommandError when ENVIRONMENT is not
        # in {development, test}. This MUST run before any write so a
        # misconfigured production run aborts cleanly.
        require_dev_or_test()

        preserved_users = Usuario.objects.filter(is_superuser=True)
        preserved_ids = list(preserved_users.values_list("pk", flat=True))
        nullified_count = Usuario.objects.filter(
            pk__in=preserved_ids,
            sucursal_id__isnull=False,
        ).update(sucursal=None)
        self.stdout.write(self.style.WARNING(
            "Pre-purge integrity: nullified sucursal_id for "
            f"{nullified_count} preserved superuser(s)."
        ))

        # Destructive-wipe header. Emitted BEFORE the inner commands so the
        # operator sees the warning before any inner output begins.
        self.stdout.write(self.style.WARNING(
            "=== DESTRUCTIVE WIPE === "
            "All business data (preserving admin users) will be erased and "
            "the PDF demo baseline will be reseeded in a single transaction. "
            "This is not reversible."
        ))

        # Compose the two sibling commands inside the outer atomic block.
        # Both inner transactions become savepoints under our @transaction.atomic;
        # any exception in either step rolls back the entire waveform.
        # ``--force`` skips the inner purge's "Escribe 'SI'" prompt; the
        # WARNING header above is the operator-facing confirmation.
        call_command(
            "purge_data_keep_admin",
            "--force",
            stdout=self.stdout,
        )
        call_command(
            "seed_pdf_baseline",
            stdout=self.stdout,
        )

        self.stdout.write(self.style.SUCCESS(
            "Reset PDF baseline complete."
        ))
