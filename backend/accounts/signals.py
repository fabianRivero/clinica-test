"""Signal handlers for the accounts app.

Phase 2 of dp4500-host-app-integration-phase2: a pre_save handler on
Usuario that mints ``biometric_external_id`` on first INSERT.

Loaded by ``accounts/apps.py::AccountsConfig.ready()``. The handler is
registered LAST so it runs LAST in Django's signal chain — after any
pre_save that mutates ``pk`` — to ensure ``instance.pk is None`` is a
reliable INSERT marker.
"""
from __future__ import annotations

import uuid

from django.db.models.signals import pre_save
from django.dispatch import receiver

from accounts.models import Usuario


@receiver(pre_save, sender=Usuario)
def assign_biometric_external_id(sender, instance, **kwargs):
    """Mint a UUID on first INSERT; preserve on UPDATE.

    Django emits pre_save before INSERT or UPDATE. On INSERT the
    instance's ``pk`` is None; on UPDATE it carries the existing value.
    We only generate when ``pk is None AND biometric_external_id is
    None`` (defensive: never overwrite a value that already exists).
    """
    if instance.pk is None and instance.biometric_external_id is None:
        instance.biometric_external_id = uuid.uuid4()
