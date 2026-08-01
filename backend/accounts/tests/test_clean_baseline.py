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

from accounts.management._baselines.clean_baseline import seed_aesthetic_catalog
from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.management._baselines.url import resolve_admin_url
from catalogs.models import (
    GravedadAlergia,
    ProductoAlergia,
    TipoAlergia,
    TipoServicio,
)
from catalogs.models import Sucursal


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