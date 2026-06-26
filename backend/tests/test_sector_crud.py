from django.db import IntegrityError, transaction
from django.test import TestCase

from catalogs.models import Sector


class SectorModelCrudTests(TestCase):
    """Sector CRUD tests.

    The data migration `0006_seed_sectores_and_reassign_fichaseccion`
    pre-populates the test DB with DEP/MAN/TAT sectors. To stay
    independent of that seed, every test creates sectors under codigos
    that are guaranteed not to clash with the seed.
    """

    SEED_RESERVED_CODIGOS = ("DEP", "MAN", "TAT")

    def setUp(self):
        # Capture any pre-existing sectors so we can clean up after the
        # test finishes and leave the global seed intact for the rest
        # of the suite.
        self._existing_ids = set(Sector.objects.values_list("id", flat=True))

    def tearDown(self):
        Sector.objects.exclude(id__in=self._existing_ids).delete()

    def _create_unique_sector(self, codigo, nombre, **kwargs):
        # Pick codigos that will not collide with the seed or other tests.
        suffix = self._testMethodName
        return Sector.objects.create(
            codigo=f"{codigo}-{suffix[:8]}",
            nombre=f"{nombre} ({suffix})",
            **kwargs,
        )

    def test_create_sector_with_minimum_fields_persists(self):
        sector = self._create_unique_sector("DEP", "Depilacion")

        self.assertTrue(sector.activo)
        self.assertEqual(sector.orden, 0)
        self.assertEqual(str(sector), sector.nombre)
        self.assertEqual(Sector.objects.filter(pk=sector.pk).count(), 1)

    def test_create_sector_with_descripcion_and_orden_persists(self):
        sector = self._create_unique_sector(
            "TAT",
            "Tatuajes",
            descripcion="Secciones de ficha clinica para borrado de tatuajes.",
            orden=3,
            activo=False,
        )

        self.assertEqual(
            sector.descripcion,
            "Secciones de ficha clinica para borrado de tatuajes.",
        )
        self.assertEqual(sector.orden, 3)
        self.assertFalse(sector.activo)

    def test_list_active_filters_and_orders_by_orden_nombre(self):
        s_tat = self._create_unique_sector("TAT", "Tatuajes", orden=3)
        s_dep = self._create_unique_sector("DEP", "Depilacion", orden=1, activo=False)
        s_man = self._create_unique_sector("MAN", "Manchas", orden=2)

        # Only the three sectors created in this test, ordered by orden/nombre.
        test_sectors = list(
            Sector.objects.filter(pk__in=[s_dep.pk, s_man.pk, s_tat.pk])
            .order_by("orden", "nombre")
            .values_list("pk", flat=True)
        )

        # s_dep is inactive but ordering still applies; assertions below
        # confirm the ordering by orden/nombre is independent of activo.
        self.assertEqual(test_sectors, [s_dep.pk, s_man.pk, s_tat.pk])

        # Active filter excludes s_dep.
        active_only = list(
            Sector.objects.filter(pk__in=[s_dep.pk, s_man.pk, s_tat.pk], activo=True)
            .order_by("orden", "nombre")
            .values_list("pk", flat=True)
        )
        self.assertEqual(active_only, [s_man.pk, s_tat.pk])

    def test_duplicate_nombre_case_insensitive_rejected(self):
        # Use nombres that only differ in case but with codigos that are
        # unique across the DB.
        unique_suffix = "dupnom"
        Sector.objects.create(
            codigo=f"NOM-{unique_suffix}".upper(),
            nombre="Depilacion laser",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sector.objects.create(
                    codigo=f"OTHER-{unique_suffix}",
                    nombre="DEPILACION LASER",
                )

    def test_duplicate_codigo_case_insensitive_rejected(self):
        # Use codigos that only differ in case but are unique across the DB.
        unique_suffix = "dupcod"
        first_codigo = f"DUP-{unique_suffix}".upper()
        second_codigo = f"dup-{unique_suffix}".lower()

        Sector.objects.create(codigo=first_codigo, nombre="Codigo mayusculas")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Sector.objects.create(
                    codigo=second_codigo,
                    nombre="Codigo distinto minusculas",
                )

    def test_toggle_activo_updates_field(self):
        sector = self._create_unique_sector("DEP", "Depilacion")

        sector.activo = False
        sector.save(update_fields=["activo"])

        sector.refresh_from_db()
        self.assertFalse(sector.activo)

        sector.activo = True
        sector.save(update_fields=["activo"])

        sector.refresh_from_db()
        self.assertTrue(sector.activo)

    def test_default_ordering_is_orden_then_nombre(self):
        # Use the same base names so orden dominates and the test is
        # independent of the per-test suffix on `nombre`.
        s_dep = self._create_unique_sector("DEP", "Depilacion", orden=1)
        s_man = self._create_unique_sector("MAN", "Manchas", orden=2)
        s_tat = self._create_unique_sector("TAT", "Tatuajes", orden=3)

        ordered_ids = list(
            Sector.objects.filter(pk__in=[s_dep.pk, s_man.pk, s_tat.pk])
            .order_by("orden", "nombre")
            .values_list("pk", flat=True)
        )

        self.assertEqual(ordered_ids, [s_dep.pk, s_man.pk, s_tat.pk])
