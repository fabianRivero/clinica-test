"""Unit tests for the ``_baselines`` library helpers.

These tests exercise the URL helper, the env guard, and the catalog helper
without going through a management command. The URL and env helpers do not
need the database; the catalog helper does, but stays inside its own
transactional isolation.
"""

import io

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management._baselines.clean_baseline import (
    seed_aesthetic_catalog,
    seed_form_configuration,
)
from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.management._baselines.url import resolve_admin_url
from catalogs.models import (
    GravedadAlergia,
    GrupoOpciones,
    ProductoAlergia,
    TipoAlergia,
    TipoServicio,
)
from catalogs.models import Sucursal
from clinical.models import FichaCampo, FichaSeccion


class ResolveAdminUrlTests(TestCase):
    """URL derivation: explicit, fallback, invalid."""

    def test_explicit_seed_admin_url_is_returned_normalized(self):
        with override_settings(
            SEED_ADMIN_URL="https://admin.example.com/admin/",
            BASE_URL="https://app.example.com",
        ):
            self.assertEqual(
                resolve_admin_url(), "https://admin.example.com/admin"
            )

    def test_explicit_seed_admin_url_without_trailing_slash(self):
        with override_settings(
            SEED_ADMIN_URL="https://admin.example.com/admin",
            BASE_URL="https://app.example.com",
        ):
            self.assertEqual(
                resolve_admin_url(), "https://admin.example.com/admin"
            )

    def test_fallback_to_base_url_when_seed_admin_url_empty(self):
        with override_settings(
            SEED_ADMIN_URL="", BASE_URL="https://app.example.com"
        ):
            self.assertEqual(
                resolve_admin_url(), "https://app.example.com/admin"
            )

    def test_fallback_appends_single_slash_when_base_has_trailing_slash(self):
        with override_settings(
            SEED_ADMIN_URL="", BASE_URL="https://app.example.com/"
        ):
            self.assertEqual(
                resolve_admin_url(), "https://app.example.com/admin"
            )

    @override_settings(SEED_ADMIN_URL="", BASE_URL="")
    def test_raises_when_both_empty(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_admin_url()
        self.assertIn("empty", str(ctx.exception).lower())

    @override_settings(
        SEED_ADMIN_URL="not-a-url", BASE_URL="also-not-a-url"
    )
    def test_raises_when_seed_admin_url_invalid(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_admin_url()
        self.assertIn("SEED_ADMIN_URL", str(ctx.exception))

    @override_settings(SEED_ADMIN_URL="", BASE_URL="ftp://nope.example.com")
    def test_raises_when_base_url_wrong_scheme(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_admin_url()
        self.assertIn("BASE_URL", str(ctx.exception))


class RequireDevOrTestTests(TestCase):
    """Environment guard: rejects prod/staging, accepts dev/test."""

    def test_accepts_development(self):
        require_dev_or_test("development")

    def test_accepts_test(self):
        require_dev_or_test("test")

    def test_accepts_uppercase_dev_or_test(self):
        require_dev_or_test("DEVELOPMENT")
        require_dev_or_test("Test")

    def test_rejects_production(self):
        with self.assertRaises(CommandError) as ctx:
            require_dev_or_test("production")
        self.assertIn("production", str(ctx.exception))

    def test_rejects_staging(self):
        with self.assertRaises(CommandError):
            require_dev_or_test("staging")

    def test_rejects_empty(self):
        with self.assertRaises(CommandError):
            require_dev_or_test("")

    @override_settings(ENVIRONMENT="production")
    def test_reads_settings_environment_when_no_arg_rejects_prod(self):
        with self.assertRaises(CommandError):
            require_dev_or_test()

    @override_settings(ENVIRONMENT="development")
    def test_reads_settings_environment_when_no_arg_accepts_dev(self):
        require_dev_or_test()

    @override_settings(ENVIRONMENT="test")
    def test_reads_settings_environment_when_no_arg_accepts_test(self):
        require_dev_or_test()

    @override_settings(ENVIRONMENT="")
    def test_reads_settings_environment_when_empty_rejects(self):
        with self.assertRaises(CommandError):
            require_dev_or_test()


class SeedAestheticCatalogTests(TestCase):
    """The aesthetic helper produces the canonical set and never allergies."""

    def test_creates_canonical_tipo_servicio_for_tratamiento(self):
        seed_aesthetic_catalog()
        self.assertTrue(
            TipoServicio.objects.filter(tipo="Tratamiento estetico").exists()
        )
        self.assertTrue(
            TipoServicio.objects.filter(tipo="Cita de consulta").exists()
        )

    def test_creates_three_procedures_and_their_service_configs(self):
        seed_aesthetic_catalog()
        self.assertEqual(
            TipoServicio.objects.filter(tipo="Tratamiento estetico").count(), 1
        )
        from decimal import Decimal

        from catalogs.models import ProcEstetico, ServicioConfig

        self.assertEqual(ProcEstetico.objects.count(), 3)
        self.assertEqual(ServicioConfig.objects.count(), 4)
        self.assertEqual(
            ServicioConfig.objects.get(
                proc_estetico__proceso="Depilacion definitiva"
            ).precio_base,
            Decimal("850.00"),
        )
        self.assertEqual(
            ServicioConfig.objects.get(
                proc_estetico__proceso="Tratamiento de manchas"
            ).precio_base,
            Decimal("650.00"),
        )
        self.assertEqual(
            ServicioConfig.objects.get(
                proc_estetico__proceso="Borrado de tatuajes"
            ).precio_base,
            Decimal("1500.00"),
        )

    def test_does_not_create_any_allergy_catalog_row(self):
        seed_aesthetic_catalog()
        self.assertEqual(ProductoAlergia.objects.count(), 0)
        self.assertEqual(TipoAlergia.objects.count(), 0)
        self.assertEqual(GravedadAlergia.objects.count(), 0)


class ResolveAdminUrlWiredInCommandTests(TestCase):
    """``resolve_admin_url`` is the source of truth for the footer URL."""

    def setUp(self):
        # The data migration creates a default principal branch — clear the
        # flag so the command can proceed without --replace-main-branch.
        Sucursal.objects.filter(es_principal=True).update(es_principal=False)

    def test_command_footer_matches_resolve_admin_url(self):
        out = io.StringIO()
        with override_settings(
            SEED_ADMIN_URL="https://ops.example.com/admin",
            BASE_URL="http://localhost:8000",
        ):
            expected = resolve_admin_url()
            call_command(
                "seed_client_baseline",
                "--non-interactive",
                "--branch-name",
                "Sede Test",
                "--branch-city",
                "Test City",
                "--branch-address",
                "Test Address",
                "--admin-username",
                "admin.test",
                "--admin-password",
                "supersecret123",
                "--admin-first-name",
                "Test",
                "--admin-last-name",
                "User",
                "--admin-email",
                "test.user@clinic.local",
                "--kiosk-code",
                "KIOSKO-TEST",
                "--kiosk-password",
                "tablet-secret-123",
                stdout=out,
            )
        self.assertIn(f"URL Admin:     {expected}", out.getvalue())


class SeedFormConfigurationTests(TestCase):
    """``seed_form_configuration`` mirrors the historical PDF baseline and is
    idempotent across re-runs.

    The fixture contract: 2 PUNTO_D sections (depilacion + manchas) each
    owning 13 FichaCampo rows, plus 1 PUNTO_E section with 9 rows. The
    historical literal spec (``BRONCEADO`` first, ``GROSOR_VELLO`` last)
    MUST be preserved byte-for-byte.
    """

    # Expected codigos in the exact historical order for the 13 depilation
    # fields shared by both PUNTO_D sections.
    DEPILATION_CODIGOS = (
        "BRONCEADO", "ISOTRETINOINA", "DESODORANTES", "INFLAMATORIOS",
        "TIPO_DEPILACION", "DESORDEN_HORMONAL", "DIABETES_METFORMINA",
        "HIPOTIROIDISMO", "KETOCONAZOL", "DIURETICOS", "TIPO_VELLO",
        "COLOR_VELLO", "GROSOR_VELLO",
    )

    TATTOO_CODIGOS = (
        "TIEMPO_ANTIGUEDAD", "PROFUNDIDAD_TATUAJE", "COLOR_TATUAJE",
        "TIPO_CICATRIZACION", "PROTECTOR_SOLAR", "OTROS_CUIDADOS",
        "TIPO_COLOR_PIEL", "AREA_CORPORAL", "AREA_FACIAL",
    )

    def _seed_all(self):
        """Seed the aesthetic catalog + form configuration."""
        catalogs = seed_aesthetic_catalog()
        seed_form_configuration(catalogs["procedures"])
        return catalogs

    def _get_punto_d_section(self, procedure):
        return FichaSeccion.objects.get(
            proc_estetico=procedure, codigo="PUNTO_D"
        )

    def _get_punto_e_section(self, procedure):
        return FichaSeccion.objects.get(
            proc_estetico=procedure, codigo="PUNTO_E"
        )

    def test_seed_form_configuration_creates_thirteen_fields_in_punto_d(self):
        """The depilacion PUNTO_D section owns 13 active fields in the
        historical literal order."""
        catalogs = self._seed_all()
        section = self._get_punto_d_section(
            catalogs["procedures"]["depilacion"]
        )
        fields = list(
            FichaCampo.objects.filter(seccion=section, activo=True)
            .order_by("orden")
        )
        self.assertEqual(len(fields), 13)
        self.assertEqual(
            tuple(field.codigo for field in fields),
            self.DEPILATION_CODIGOS,
        )

    def test_seed_form_configuration_creates_thirteen_fields_in_manchas_section(self):
        """The manchas PUNTO_D section owns its own 13 fields with the same
        codigos but distinct FK ids (independent instance)."""
        catalogs = self._seed_all()
        dep_section = self._get_punto_d_section(
            catalogs["procedures"]["depilacion"]
        )
        man_section = self._get_punto_d_section(
            catalogs["procedures"]["manchas"]
        )
        self.assertNotEqual(dep_section.id, man_section.id)
        man_fields = list(
            FichaCampo.objects.filter(seccion=man_section, activo=True)
            .order_by("orden")
        )
        self.assertEqual(len(man_fields), 13)
        self.assertEqual(
            tuple(field.codigo for field in man_fields),
            self.DEPILATION_CODIGOS,
        )
        # Every codigo appears in both sections, but each section owns its
        # own independent row (FK target differs).
        dep_ids = set(
            FichaCampo.objects.filter(seccion=dep_section).values_list(
                "id", flat=True
            )
        )
        man_ids = set(
            FichaCampo.objects.filter(seccion=man_section).values_list(
                "id", flat=True
            )
        )
        self.assertTrue(dep_ids.isdisjoint(man_ids))

    def test_seed_form_configuration_creates_nine_fields_in_punto_e(self):
        """The tatuajes PUNTO_E section owns 9 fields in literal order."""
        catalogs = self._seed_all()
        section = self._get_punto_e_section(
            catalogs["procedures"]["tatuajes"]
        )
        fields = list(
            FichaCampo.objects.filter(seccion=section, activo=True)
            .order_by("orden")
        )
        self.assertEqual(len(fields), 9)
        self.assertEqual(
            tuple(field.codigo for field in fields),
            self.TATTOO_CODIGOS,
        )

    def test_field_types_match_historical(self):
        """Each codigo maps to the literal historical tipo_campo."""
        self._seed_all()
        # Type map mirrors the historical depilation_fields list.
        depilacion_types = {
            "BRONCEADO": FichaCampo.TipoCampo.SELECCION,
            "ISOTRETINOINA": FichaCampo.TipoCampo.SELECCION,
            "DESODORANTES": FichaCampo.TipoCampo.SELECCION,
            "INFLAMATORIOS": FichaCampo.TipoCampo.SELECCION,
            "TIPO_DEPILACION": FichaCampo.TipoCampo.TEXTO,
            "DESORDEN_HORMONAL": FichaCampo.TipoCampo.SELECCION,
            "DIABETES_METFORMINA": FichaCampo.TipoCampo.SELECCION,
            "HIPOTIROIDISMO": FichaCampo.TipoCampo.SELECCION,
            "KETOCONAZOL": FichaCampo.TipoCampo.SELECCION,
            "DIURETICOS": FichaCampo.TipoCampo.SELECCION,
            "TIPO_VELLO": FichaCampo.TipoCampo.TEXTO,
            "COLOR_VELLO": FichaCampo.TipoCampo.TEXTO,
            "GROSOR_VELLO": FichaCampo.TipoCampo.TEXTO,
        }
        for codigo, expected_type in depilacion_types.items():
            field = FichaCampo.objects.get(
                seccion__codigo="PUNTO_D",
                seccion__proc_estetico__proceso="Depilacion definitiva",
                codigo=codigo,
            )
            self.assertEqual(
                field.tipo_campo,
                expected_type,
                f"{codigo} expected {expected_type}, got {field.tipo_campo}",
            )
        # Tattoo type map mirrors the historical tattoo_fields list.
        tattoo_types = {
            "TIEMPO_ANTIGUEDAD": FichaCampo.TipoCampo.TEXTO,
            "PROFUNDIDAD_TATUAJE": FichaCampo.TipoCampo.SELECCION,
            "COLOR_TATUAJE": FichaCampo.TipoCampo.TEXTO,
            "TIPO_CICATRIZACION": FichaCampo.TipoCampo.TEXTO,
            "PROTECTOR_SOLAR": FichaCampo.TipoCampo.SELECCION,
            "OTROS_CUIDADOS": FichaCampo.TipoCampo.TEXTO,
            "TIPO_COLOR_PIEL": FichaCampo.TipoCampo.TEXTO,
            "AREA_CORPORAL": FichaCampo.TipoCampo.TEXTO,
            "AREA_FACIAL": FichaCampo.TipoCampo.TEXTO,
        }
        for codigo, expected_type in tattoo_types.items():
            field = FichaCampo.objects.get(
                seccion__codigo="PUNTO_E",
                seccion__proc_estetico__proceso="Borrado de tatuajes",
                codigo=codigo,
            )
            self.assertEqual(
                field.tipo_campo,
                expected_type,
                f"{codigo} expected {expected_type}, got {field.tipo_campo}",
            )

    def test_field_groups_resolved_for_si_no_and_profundidad(self):
        """SELECCION fields point to the right GrupoOpciones; TEXTO fields are
        nullable.
        """
        self._seed_all()
        si_no = GrupoOpciones.objects.get(codigo="SI_NO")
        profundidad = GrupoOpciones.objects.get(codigo="PROFUNDIDAD_TATUAJE")

        # Every PUNTO_D SELECCION field in the depilacion section points to
        # SI_NO (matches historical grouping); TEXTO fields stay nullable.
        for codigo in (
            "BRONCEADO", "ISOTRETINOINA", "DESODORANTES", "INFLAMATORIOS",
            "DESORDEN_HORMONAL", "DIABETES_METFORMINA", "HIPOTIROIDISMO",
            "KETOCONAZOL", "DIURETICOS",
        ):
            field = FichaCampo.objects.get(
                seccion__codigo="PUNTO_D",
                seccion__proc_estetico__proceso="Depilacion definitiva",
                codigo=codigo,
            )
            self.assertEqual(field.grupo_opciones_id, si_no.id)
        for codigo in ("TIPO_DEPILACION", "TIPO_VELLO", "COLOR_VELLO", "GROSOR_VELLO"):
            field = FichaCampo.objects.get(
                seccion__codigo="PUNTO_D",
                seccion__proc_estetico__proceso="Depilacion definitiva",
                codigo=codigo,
            )
            self.assertIsNone(field.grupo_opciones)

        # PUNTO_E: PROFUNDIDAD_TATUAJE -> PROFUNDIDAD_TATUAJE group; PROTECTOR_SOLAR
        # -> SI_NO; the rest are TEXTO with no group.
        profundidad_field = FichaCampo.objects.get(
            seccion__codigo="PUNTO_E",
            seccion__proc_estetico__proceso="Borrado de tatuajes",
            codigo="PROFUNDIDAD_TATUAJE",
        )
        self.assertEqual(profundidad_field.grupo_opciones_id, profundidad.id)
        protector_field = FichaCampo.objects.get(
            seccion__codigo="PUNTO_E",
            seccion__proc_estetico__proceso="Borrado de tatuajes",
            codigo="PROTECTOR_SOLAR",
        )
        self.assertEqual(protector_field.grupo_opciones_id, si_no.id)
        for codigo in (
            "TIEMPO_ANTIGUEDAD", "COLOR_TATUAJE", "TIPO_CICATRIZACION",
            "OTROS_CUIDADOS", "TIPO_COLOR_PIEL", "AREA_CORPORAL",
            "AREA_FACIAL",
        ):
            field = FichaCampo.objects.get(
                seccion__codigo="PUNTO_E",
                seccion__proc_estetico__proceso="Borrado de tatuajes",
                codigo=codigo,
            )
            self.assertIsNone(field.grupo_opciones)

    def test_seed_form_configuration_idempotent(self):
        """Re-running the helper updates rows in place; no duplicates."""
        # First run through the command so we exercise the public surface.
        with override_settings(ENVIRONMENT="test"):
            call_command("seed_pdf_baseline")
        first_count = FichaCampo.objects.count()
        self.assertEqual(first_count, 13 + 13 + 9)

        # Second run must not change the count.
        with override_settings(ENVIRONMENT="test"):
            call_command("seed_pdf_baseline")
        self.assertEqual(FichaCampo.objects.count(), first_count)
        # Each section's row count is stable across runs.
        self.assertEqual(
            FichaSeccion.objects.filter(codigo="PUNTO_D").count(), 2
        )
        self.assertEqual(
            FichaSeccion.objects.filter(codigo="PUNTO_E").count(), 1
        )

    def test_seed_form_configuration_updates_stale_values(self):
        """Pre-existing rows with stale mutable values are reconciled by
        ``(seccion, codigo)``; the count does not grow.
        """
        catalogs = self._seed_all()
        section = self._get_punto_d_section(
            catalogs["procedures"]["depilacion"]
        )
        # Force a stale etiqueta and orden so we can confirm the helper
        # restores both.
        stale = FichaCampo.objects.get(seccion=section, codigo="BRONCEADO")
        stale.etiqueta = "ETIQUETA OBSOLETA"
        stale.orden = 99
        stale.save(update_fields=["etiqueta", "orden"])

        # Run the helper again with the same procedures.
        seed_form_configuration(catalogs["procedures"])

        refreshed = FichaCampo.objects.get(seccion=section, codigo="BRONCEADO")
        self.assertEqual(refreshed.id, stale.id)
        self.assertEqual(refreshed.etiqueta, "Bronceado")
        self.assertEqual(refreshed.orden, 1)
        # Count is unchanged (no duplicate row created).
        self.assertEqual(
            FichaCampo.objects.filter(seccion=section).count(), 13
        )