"""Tests for the catalogs.0007 normalization data migration.

These tests exercise the forward + reverse path against a freshly seeded
SQLite database. They do NOT rely on the migration framework — instead,
they call the migration's Python callables directly with ``apps.get_model``
shims so the assertions stay focused on the data invariants.
"""

import importlib
from decimal import Decimal

from django.apps import apps as global_apps
from django.test import TestCase

from catalogs.models import ServicioConfig, TipoServicio


migration = importlib.import_module(
    "catalogs.migrations.0007_normalize_tipo_servicio_estetico"
)


LEGACY_TIPO = migration.LEGACY_TIPO
CANONICAL_TIPO = migration.CANONICAL_TIPO


class _AppsShim:
    """Minimal shim exposing ``get_model`` for the migration callables."""

    def __init__(self, real_apps):
        self._apps = real_apps

    def get_model(self, app_label, model_name):
        return self._apps.get_model(app_label, model_name)


class NormalizeTipoServicioEsteticoTests(TestCase):
    """Forward + reverse + idempotency for the TipoServicio normalization."""

    def setUp(self):
        self.apps = _AppsShim(global_apps)

    def _seed_legacy_with_servicio_config(self):
        legacy = TipoServicio.objects.create(
            tipo=LEGACY_TIPO,
            descripcion="Legacy description.",
            orden=2,
            activo=True,
        )
        ServicioConfig.objects.create(
            tipo_servicio=legacy,
            proc_estetico=None,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        return legacy

    # -- Forward ----------------------------------------------------------

    def test_forward_reassigns_servicio_config_to_canonical(self):
        legacy = self._seed_legacy_with_servicio_config()

        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)

        canonical = TipoServicio.objects.get(tipo=CANONICAL_TIPO)
        self.assertFalse(TipoServicio.objects.filter(tipo=LEGACY_TIPO).exists())
        self.assertEqual(
            ServicioConfig.objects.get(tipo_servicio=canonical),
            ServicioConfig.objects.first(),
        )
        # No ServicioConfig references the legacy row anymore.
        self.assertFalse(
            ServicioConfig.objects.filter(tipo_servicio=legacy).exists()
        )

    def test_forward_is_noop_when_only_canonical_exists(self):
        TipoServicio.objects.create(
            tipo=CANONICAL_TIPO,
            descripcion="Canonical description.",
            orden=2,
            activo=True,
        )

        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)

        self.assertTrue(TipoServicio.objects.filter(tipo=CANONICAL_TIPO).exists())
        self.assertFalse(TipoServicio.objects.filter(tipo=LEGACY_TIPO).exists())
        self.assertEqual(TipoServicio.objects.count(), 1)

    def test_forward_is_noop_when_neither_row_exists(self):
        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)
        self.assertEqual(TipoServicio.objects.count(), 0)

    def test_forward_is_idempotent_on_second_run(self):
        self._seed_legacy_with_servicio_config()
        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)

        snapshot_count = TipoServicio.objects.count()
        snapshot_configs = list(
            ServicioConfig.objects.values_list("id", "tipo_servicio_id")
        )

        # Second run on the now-canonical DB must be a no-op.
        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)

        self.assertEqual(TipoServicio.objects.count(), snapshot_count)
        self.assertEqual(
            list(
                ServicioConfig.objects.values_list("id", "tipo_servicio_id")
            ),
            snapshot_configs,
        )

    # -- Reverse ----------------------------------------------------------

    def test_reverse_leaves_servicio_config_rows_intact(self):
        """After a successful forward, the legacy row is gone — reverse is a
        no-op and the canonical state (with all ServicioConfig rows intact)
        is preserved."""
        self._seed_legacy_with_servicio_config()
        migration.normalize_tipo_servicio_estetico(self.apps, schema_editor=None)

        config_count = ServicioConfig.objects.count()

        # Reverse: legacy row was deleted by forward, so reverse is a no-op.
        migration.restore_tipo_servicio_estetico(self.apps, schema_editor=None)

        # All ServicioConfig rows still exist (no rows lost).
        self.assertEqual(ServicioConfig.objects.count(), config_count)
        self.assertTrue(TipoServicio.objects.filter(tipo=CANONICAL_TIPO).exists())
        # Legacy row stays absent — forward already deleted it.
        self.assertFalse(
            TipoServicio.objects.filter(tipo=LEGACY_TIPO).exists()
        )

    def test_reverse_restores_legacy_when_both_rows_present(self):
        """If both rows coexist (a hand-crafted DB state), reverse reassigns
        ServicioConfig FKs back to legacy and drops canonical."""
        legacy = TipoServicio.objects.create(
            tipo=LEGACY_TIPO,
            descripcion="Legacy description.",
            orden=2,
            activo=True,
        )
        canonical = TipoServicio.objects.create(
            tipo=CANONICAL_TIPO,
            descripcion="Canonical description.",
            orden=2,
            activo=True,
        )
        ServicioConfig.objects.create(
            tipo_servicio=canonical,
            proc_estetico=None,
            precio_base=Decimal("120.00"),
            activo=True,
        )

        migration.restore_tipo_servicio_estetico(self.apps, schema_editor=None)

        self.assertTrue(TipoServicio.objects.filter(pk=legacy.pk).exists())
        self.assertFalse(TipoServicio.objects.filter(pk=canonical.pk).exists())
        # FK reassigned back to legacy.
        self.assertEqual(ServicioConfig.objects.count(), 1)
        self.assertEqual(
            ServicioConfig.objects.first().tipo_servicio_id, legacy.pk
        )

    def test_reverse_is_noop_when_only_canonical_exists(self):
        """A canonical-only DB (the seed_client_baseline path) must survive
        the reverse untouched — the canonical row was pre-existing, not
        created by the forward migration."""
        canonical = TipoServicio.objects.create(
            tipo=CANONICAL_TIPO,
            descripcion="Canonical description.",
            orden=2,
            activo=True,
        )

        migration.restore_tipo_servicio_estetico(self.apps, schema_editor=None)

        # Canonical row untouched.
        self.assertTrue(TipoServicio.objects.filter(pk=canonical.pk).exists())
        self.assertEqual(TipoServicio.objects.count(), 1)

    def test_reverse_is_noop_when_neither_row_exists(self):
        migration.restore_tipo_servicio_estetico(self.apps, schema_editor=None)
        self.assertEqual(TipoServicio.objects.count(), 0)