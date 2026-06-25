from decimal import Decimal

from django.test import TestCase

from catalogs.models import GrupoOpciones, ProcEstetico, ProcEsteticosTipo, Sector, ServicioConfig, TipoServicio
from clinical.models import FichaCampo, FichaSeccion
from config.prospect_conversion_views import _serialize_medical_config


class MedicalFormBySectorTests(TestCase):
    """End-to-end coverage of the sector-first filter inside
    `_serialize_medical_config`.

    The data migration `0006_seed_sectores_and_reassign_fichaseccion`
    pre-populates the test DB with DEP/MAN/TAT sectors. We reuse those
    sectors (instead of recreating them) and create the dependent
    ProcEstetico/FichaSeccion/FichaCampo records in setUp so the test
    is self-contained.
    """

    @classmethod
    def setUpTestData(cls):
        # Reuse the sectors seeded by the data migration.
        cls.dep_sector = Sector.objects.get(codigo="DEP")
        cls.tat_sector = Sector.objects.get(codigo="TAT")
        cls.man_sector = Sector.objects.get(codigo="MAN")

        si_no = GrupoOpciones.objects.create(codigo="SI_NO", nombre="Si / No")

        # ProcEstetico requires a ProcEsteticosTipo FK.
        procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Laser sector test",
        )

        cls.dep_proc = ProcEstetico.objects.create(
            tipo_p_estetico=procedure_type,
            proceso="Depilacion definitiva",
        )
        cls.tat_proc = ProcEstetico.objects.create(
            tipo_p_estetico=procedure_type,
            proceso="Borrado de tatuajes",
        )
        cls.new_dep_proc = ProcEstetico.objects.create(
            tipo_p_estetico=procedure_type,
            proceso="Depilacion dia de la madre",
        )

        cls.dep_section = FichaSeccion.objects.create(
            proc_estetico=cls.dep_proc,
            sector=cls.dep_sector,
            codigo="PUNTO_D",
            nombre="Depilacion definitiva / Manchas",
            orden=1,
        )
        FichaCampo.objects.create(
            seccion=cls.dep_section,
            codigo="BRONCEADO",
            etiqueta="Bronceado",
            tipo_campo=FichaCampo.TipoCampo.SELECCION,
            grupo_opciones=si_no,
            orden=1,
        )
        FichaCampo.objects.create(
            seccion=cls.dep_section,
            codigo="TIPO_VELLO",
            etiqueta="Tipo de vello",
            tipo_campo=FichaCampo.TipoCampo.TEXTO,
            orden=2,
        )

        cls.tat_section = FichaSeccion.objects.create(
            proc_estetico=cls.tat_proc,
            sector=cls.tat_sector,
            codigo="PUNTO_E",
            nombre="Borrado de tatuajes",
            orden=1,
        )
        FichaCampo.objects.create(
            seccion=cls.tat_section,
            codigo="TIEMPO_ANTIGUEDAD",
            etiqueta="Tiempo de antiguedad",
            tipo_campo=FichaCampo.TipoCampo.TEXTO,
            orden=1,
        )

        # Legacy section: same procedure as dep_section but no sector
        # assignment. Used by the fallback test.
        cls.legacy_dep_proc = ProcEstetico.objects.create(
            tipo_p_estetico=procedure_type,
            proceso="Legacy depilacion",
        )
        cls.legacy_section = FichaSeccion.objects.create(
            proc_estetico=cls.legacy_dep_proc,
            sector=None,
            codigo="PUNTO_LEGACY",
            nombre="Seccion legacy",
            orden=1,
        )

        tratamiento = TipoServicio.objects.create(tipo="Tratamiento sector test")

        # Existing service "Depilacion definitiva" — points to the
        # seeded procedure and the DEP sector.
        cls.existing_dep_service = ServicioConfig.objects.create(
            tipo_servicio=tratamiento,
            proc_estetico=cls.dep_proc,
            sector=cls.dep_sector,
            precio_base=Decimal("850.00"),
            activo=True,
        )

        # New service that points to a different ProcEstetico but same DEP sector.
        cls.new_dep_service = ServicioConfig.objects.create(
            tipo_servicio=tratamiento,
            proc_estetico=cls.new_dep_proc,
            sector=cls.dep_sector,
            precio_base=Decimal("900.00"),
            activo=True,
        )

        cls.tat_service = ServicioConfig.objects.create(
            tipo_servicio=tratamiento,
            proc_estetico=cls.tat_proc,
            sector=cls.tat_sector,
            precio_base=Decimal("1500.00"),
            activo=True,
        )

        cls.consulta_service = ServicioConfig.objects.create(
            tipo_servicio=TipoServicio.objects.create(tipo="Consulta sector test"),
            proc_estetico=None,
            sector=None,
            precio_base=Decimal("120.00"),
            activo=True,
        )

    def _serialize(self, service):
        return _serialize_medical_config(service)

    def _section_signature(self, medical_config):
        return [
            (s["code"], s["name"], tuple((f["code"], f["label"]) for f in s["fields"]))
            for s in medical_config["sections"]
        ]

    def test_two_services_with_same_sector_share_section_set(self):
        config_existing = self._serialize(self.existing_dep_service)
        config_new = self._serialize(self.new_dep_service)

        self.assertEqual(
            self._section_signature(config_existing),
            self._section_signature(config_new),
        )
        # Only the DEP section is surfaced — not the legacy or tat sections.
        self.assertEqual(len(config_existing["sections"]), 1)
        section_codes = {s["code"] for s in config_existing["sections"]}
        self.assertEqual(section_codes, {"PUNTO_D"})

    def test_new_service_with_sector_returns_identical_sections_to_existing_dep_service(self):
        existing_config = self._serialize(self.existing_dep_service)
        new_config = self._serialize(self.new_dep_service)

        self.assertEqual(
            self._section_signature(existing_config),
            self._section_signature(new_config),
        )

        # The shared section must surface the seeded field set.
        shared_section = existing_config["sections"][0]
        self.assertEqual(shared_section["code"], "PUNTO_D")
        field_codes = {f["code"] for f in shared_section["fields"]}
        self.assertEqual(field_codes, {"BRONCEADO", "TIPO_VELLO"})

    def test_sector_filtering_takes_precedence_over_procedure(self):
        # If a service had both sector=TAT and a proc from a different
        # service family, the sector must win (per design decision).
        cross_proc = ProcEstetico.objects.create(
            tipo_p_estetico=self.dep_proc.tipo_p_estetico,
            proceso="Consulta medica cross",
        )
        weird_service = ServicioConfig.objects.create(
            tipo_servicio=TipoServicio.objects.create(tipo="Otro tipo"),
            proc_estetico=cross_proc,
            sector=self.tat_sector,
            precio_base=Decimal("100.00"),
            activo=True,
        )

        config = self._serialize(weird_service)

        section_codes = [s["code"] for s in config["sections"]]
        self.assertEqual(section_codes, ["PUNTO_E"])

    def test_service_with_null_sector_and_null_proc_returns_empty_sections(self):
        config = self._serialize(self.consulta_service)

        self.assertEqual(config["sections"], [])
        self.assertIsNone(config["procedureId"])
        self.assertEqual(config["procedureName"], "")

    def test_service_with_null_sector_falls_back_to_legacy_procedure_filter(self):
        # A legacy service that only has proc_estetico assigned (no sector)
        # must still see the proc-based section.
        legacy_service = ServicioConfig.objects.create(
            tipo_servicio=TipoServicio.objects.create(tipo="Legacy tipo"),
            proc_estetico=self.legacy_dep_proc,
            sector=None,
            precio_base=Decimal("100.00"),
            activo=True,
        )

        config = self._serialize(legacy_service)

        section_codes = [s["code"] for s in config["sections"]]
        self.assertEqual(section_codes, ["PUNTO_LEGACY"])

    def test_inactive_sector_sections_are_excluded(self):
        inactive_section = FichaSeccion.objects.create(
            proc_estetico=self.dep_proc,
            sector=self.dep_sector,
            codigo="PUNTO_INACTIVO",
            nombre="Seccion inactiva",
            activo=False,
        )

        config = self._serialize(self.existing_dep_service)

        section_codes = [s["code"] for s in config["sections"]]
        self.assertIn("PUNTO_D", section_codes)
        self.assertNotIn("PUNTO_INACTIVO", section_codes)
