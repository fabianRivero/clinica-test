"""Tests for the seed_client_baseline management command."""

import io
from decimal import Decimal
from unittest import mock

from django.contrib.auth.hashers import identify_hasher
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management.commands.seed_client_baseline import Command
from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GravedadAlergia,
    GrosorPiel,
    GrupoOpciones,
    ImplanteInjerto,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    ProductoAlergia,
    Sector,
    ServicioConfig,
    Sucursal,
    TipoAlergia,
    TipoPiel,
    TipoServicio,
)
from operations.models import TabletKiosko


VALID_FLAGS = {
    "branch_name": "Sede Central",
    "branch_city": "La Paz",
    "branch_address": "Av. Principal #123",
    "admin_username": "admin.central",
    "admin_password": "supersecret123",
    "admin_first_name": "Maria",
    "admin_last_name": "Gutierrez",
    "admin_email": "maria.gutierrez@clinic.local",
    "kiosk_code": "KIOSKO-CENTRAL",
    "kiosk_password": "tablet-secret-123",
}


def _run_with(extra_overrides=None):
    """Invoke the command non-interactively with a complete flag set."""
    flags = dict(VALID_FLAGS)
    if extra_overrides:
        flags.update(extra_overrides)
    call_command("seed_client_baseline", "--non-interactive", **flags)


class SeedClientBaselineTests(TestCase):
    """End-to-end tests for the seed_client_baseline command."""

    MIGRATION_BRANCH_NAME = "Sede Principal"

    def setUp(self):
        # A data migration creates a default "Sede Principal" branch with
        # direccion "Direccion Central". Tests that need a "fresh" database
        # clear the principal flag on it; assertions filter it out by name.
        Sucursal.objects.filter(es_principal=True).update(es_principal=False)

    def _command_branches(self):
        """Branches excluding the one injected by the data migration."""
        return Sucursal.objects.exclude(nombre=self.MIGRATION_BRANCH_NAME)

    # -- 2.2 fresh database ------------------------------------------------

    def test_fresh_db_creates_all_baseline_records(self):
        _run_with()

        # Roles
        expected_roles = {
            "ADMIN_PRINCIPAL",
            "ADMIN_SUCURSAL",
            "TRABAJADOR",
            "CLIENTE",
        }
        self.assertEqual(
            set(Rol.objects.values_list("rol", flat=True)), expected_roles
        )

        # Branch
        branch = Sucursal.objects.get(nombre="Sede Central")
        self.assertTrue(branch.es_principal)
        self.assertTrue(branch.activa)
        self.assertEqual(Sucursal.objects.filter(es_principal=True).count(), 1)

        # Admin
        admin = Usuario.objects.get(username="admin.central")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_active)
        self.assertEqual(admin.rol.rol, "ADMIN_PRINCIPAL")
        self.assertEqual(admin.sucursal, branch)
        # Password was hashed.
        self.assertTrue(admin.check_password("supersecret123"))

        # Kiosk
        kiosk = TabletKiosko.objects.get(codigo="KIOSKO-CENTRAL")
        self.assertTrue(kiosk.activo)
        self.assertEqual(kiosk.sucursal, branch)
        # Clave was hashed.
        self.assertNotEqual(kiosk.clave, "tablet-secret-123")
        identify_hasher(kiosk.clave)  # valid hash format
        self.assertTrue(kiosk.check_clave("tablet-secret-123"))

        # Catalogs
        self.assertEqual(TipoServicio.objects.count(), 2)
        self.assertEqual(CategoriaGasto.objects.count(), 8)
        self.assertEqual(ProcEsteticosTipo.objects.count(), 1)
        self.assertEqual(ProcEstetico.objects.count(), 3)
        self.assertEqual(ServicioConfig.objects.count(), 4)
        self.assertEqual(AntecedenteMedico.objects.count(), 6)
        self.assertEqual(ImplanteInjerto.objects.count(), 5)
        self.assertEqual(CirugiaEstetica.objects.count(), 7)
        self.assertEqual(GrupoOpciones.objects.count(), 2)
        self.assertEqual(OpcionCatalogo.objects.count(), 4)
        self.assertEqual(TipoPiel.objects.count(), 6)
        self.assertEqual(GradoDeshidratacion.objects.count(), 3)
        self.assertEqual(GrosorPiel.objects.count(), 5)
        self.assertEqual(PatologiaCutanea.objects.count(), 28)

        # Sectors
        self.assertEqual(Sector.objects.count(), 3)
        self.assertEqual(
            set(Sector.objects.values_list("codigo", flat=True)),
            {"DEP", "MAN", "TAT"},
        )

        # Spot-check a couple of exact values.
        self.assertTrue(
            ServicioConfig.objects.filter(
                proc_estetico__proceso="Depilacion definitiva",
                precio_base=Decimal("850.00"),
            ).exists()
        )
        self.assertTrue(
            PatologiaCutanea.objects.filter(nombre="Vitiligo").exists()
        )

    # -- 2.3 idempotent re-run --------------------------------------------

    def test_idempotent_rerun_no_duplicates(self):
        _run_with()
        role_count = Rol.objects.count()
        tipo_servicio_count = TipoServicio.objects.count()
        sector_count = Sector.objects.count()
        patologia_count = PatologiaCutanea.objects.count()

        _run_with()

        self.assertEqual(Rol.objects.count(), role_count)
        self.assertEqual(TipoServicio.objects.count(), tipo_servicio_count)
        self.assertEqual(Sector.objects.count(), sector_count)
        self.assertEqual(PatologiaCutanea.objects.count(), patologia_count)

        # Branch and admin updated in place, not duplicated. Filter out the
        # data-migration branch — only the command's branch should exist.
        self.assertEqual(self._command_branches().count(), 1)
        self.assertEqual(Usuario.objects.filter(is_superuser=True).count(), 1)
        self.assertEqual(TabletKiosko.objects.count(), 1)

    # -- 2.4 non-interactive skips prompts ---------------------------------

    def test_non_interactive_skips_prompts(self):
        with mock.patch("builtins.input") as mock_input:
            _run_with()
            mock_input.assert_not_called()

    # -- 2.5 missing non-interactive flags ---------------------------------

    def test_non_interactive_missing_flags_aborts(self):
        incomplete = dict(VALID_FLAGS)
        incomplete.pop("admin_password")
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "seed_client_baseline",
                "--non-interactive",
                **incomplete,
            )
        self.assertIn("--admin-password", str(ctx.exception))

        # No records were created.
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(self._command_branches().count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(TabletKiosko.objects.count(), 0)

    # -- 2.6 weak password ------------------------------------------------

    def test_weak_password_rejected(self):
        with self.assertRaises(CommandError) as ctx:
            _run_with({"admin_password": "short"})
        self.assertIn("admin_password", str(ctx.exception).lower())
        self.assertEqual(Usuario.objects.count(), 0)

    # -- 2.7 malformed email ----------------------------------------------

    def test_malformed_email_rejected(self):
        with self.assertRaises(CommandError) as ctx:
            _run_with({"admin_email": "not-an-email"})
        self.assertIn("admin_email", str(ctx.exception))
        self.assertEqual(Usuario.objects.count(), 0)

    # -- 2.8 duplicate username -------------------------------------------

    def test_duplicate_username_rejected(self):
        # Pre-create a non-superuser with the desired username.
        Usuario.objects.create_user(
            username="admin.central",
            password="unrelated123",
            primer_nombre="Other",
            apellido_paterno="User",
            email="other@clinic.local",
        )
        with self.assertRaises(CommandError) as ctx:
            _run_with()
        self.assertIn("admin_username", str(ctx.exception))

        # The pre-existing user is untouched.
        u = Usuario.objects.get(username="admin.central")
        self.assertFalse(u.is_superuser)
        self.assertEqual(u.email, "other@clinic.local")

    # -- 2.9 replace-main-branch required ----------------------------------

    def test_replace_main_branch_required_in_non_interactive(self):
        Sucursal.objects.create(
            nombre="Old Principal",
            ciudad="Old City",
            direccion="Old Address",
            es_principal=True,
            activa=True,
        )
        with self.assertRaises(CommandError) as ctx:
            _run_with()  # new branch_name="Sede Central" -> different data
        self.assertIn("--replace-main-branch", str(ctx.exception))
        # Old principal untouched.
        self.assertTrue(
            Sucursal.objects.filter(
                nombre="Old Principal", es_principal=True
            ).exists()
        )

    # -- 2.10 replace-main-branch updates --------------------------------

    def test_replace_main_branch_updates(self):
        Sucursal.objects.create(
            nombre="Old Principal",
            ciudad="Old City",
            direccion="Old Address",
            es_principal=True,
            activa=True,
        )
        Sucursal.objects.create(
            nombre="Other Branch",
            ciudad="Other City",
            direccion="Other Address",
            es_principal=False,
            activa=True,
        )

        call_command(
            "seed_client_baseline",
            "--non-interactive",
            "--replace-main-branch",
            **VALID_FLAGS,
        )

        # The new branch is now principal; the old one is not.
        self.assertTrue(
            Sucursal.objects.filter(
                nombre="Sede Central", es_principal=True
            ).exists()
        )
        self.assertFalse(
            Sucursal.objects.filter(
                nombre="Old Principal", es_principal=True
            ).exists()
        )
        # Other branches explicitly demoted.
        self.assertFalse(
            Sucursal.objects.filter(
                nombre="Other Branch", es_principal=True
            ).exists()
        )
        # Exactly one principal.
        self.assertEqual(
            Sucursal.objects.filter(es_principal=True).count(), 1
        )

    # -- 2.11 transaction rollback on failure ----------------------------

    def test_transaction_rollback_on_failure(self):
        # Simulate a failure in catalog seeding by patching one of the
        # catalog managers to raise mid-flight. We patch after the branch
        # and admin have been created so we can verify they roll back too.
        original_update_or_create = ProcEstetico.objects.update_or_create

        def boom(*args, **kwargs):
            # Let the first call (ProcEsteticosTipo) succeed; fail on
            # ProcEstetico to inject an error mid-transaction.
            if kwargs.get("proceso") is not None:
                raise RuntimeError("simulated catalog failure")
            return original_update_or_create(*args, **kwargs)

        with mock.patch.object(
            ProcEstetico.objects, "update_or_create", side_effect=boom
        ):
            with self.assertRaises(RuntimeError):
                _run_with()

        # Nothing this invocation could have created should remain.
        # (Branches / sectors from data migrations are filtered out.)
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(self._command_branches().count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(TabletKiosko.objects.count(), 0)
        self.assertEqual(TipoServicio.objects.count(), 0)
        # ProcEsteticosTipo was the first insert (before the boom); if the
        # transaction actually rolled back, it must be absent.
        self.assertEqual(ProcEsteticosTipo.objects.count(), 0)

    # -- Work Unit A2 new tests ------------------------------------------

    @override_settings(SEED_ADMIN_URL="https://admin.example.com/admin/")
    def test_admin_url_uses_settings_seed_admin_url(self):
        """SEED_ADMIN_URL takes precedence and trailing slashes are normalized."""
        out = io.StringIO()
        call_command(
            "seed_client_baseline",
            "--non-interactive",
            stdout=out,
            **VALID_FLAGS,
        )
        self.assertIn(
            "URL Admin:     https://admin.example.com/admin",
            out.getvalue(),
        )

    @override_settings(
        SEED_ADMIN_URL="",
        BASE_URL="https://app.example.com/",
    )
    def test_admin_url_falls_back_to_base_url(self):
        """When SEED_ADMIN_URL is empty, BASE_URL + /admin is used."""
        out = io.StringIO()
        call_command(
            "seed_client_baseline",
            "--non-interactive",
            stdout=out,
            **VALID_FLAGS,
        )
        self.assertIn(
            "URL Admin:     https://app.example.com/admin",
            out.getvalue(),
        )

    def test_aesthetic_set_complete_when_partial(self):
        """Even when only the Laser type + one procedure exist, a successful
        command run must complete the canonical aesthetic set without
        duplicating any natural key."""
        # Pre-create the type and the depilacion procedure so the catalog
        # baseline starts "partially completed". The command must fill the
        # gap (manchas, tatuajes) and reconcile prices.
        procedure_type = ProcEsteticosTipo.objects.create(
            tipo="Laser",
            descripcion="Procedimientos laser de la ficha medica.",
            orden=1,
            activo=True,
        )
        existing_proc = ProcEstetico.objects.create(
            tipo_p_estetico=procedure_type,
            proceso="Depilacion definitiva",
            descripcion="Procedimiento de depilacion definitiva.",
            orden=1,
            activo=True,
        )

        _run_with()

        self.assertEqual(ProcEsteticosTipo.objects.count(), 1)
        self.assertEqual(ProcEsteticosTipo.objects.get().pk, procedure_type.pk)
        self.assertEqual(ProcEstetico.objects.count(), 3)
        self.assertTrue(
            ProcEstetico.objects.filter(
                proceso="Depilacion definitiva"
            ).exists()
        )
        self.assertTrue(
            ProcEstetico.objects.filter(
                proceso="Tratamiento de manchas"
            ).exists()
        )
        self.assertTrue(
            ProcEstetico.objects.filter(
                proceso="Borrado de tatuajes"
            ).exists()
        )
        # Existing procedure was reused, not duplicated, and reconciled.
        existing_proc.refresh_from_db()
        self.assertEqual(existing_proc.tipo_p_estetico_id, procedure_type.pk)
        self.assertEqual(ServicioConfig.objects.count(), 4)
        self.assertEqual(
            ServicioConfig.objects.get(
                proc_estetico__proceso="Depilacion definitiva"
            ).precio_base,
            Decimal("850.00"),
        )

    def test_allergy_catalogs_unchanged(self):
        """Allergy catalogs MUST NOT be created or modified by the command.

        Regression guard for the spec requirement 'Allergy catalogs remain
        operator-managed' (proposal.md, success criteria).
        """
        ProductoAlergia.objects.create(
            nombre="Penicilina", descripcion="Allergy.", orden=1, activo=True
        )
        TipoAlergia.objects.create(
            nombre="Medicamento", descripcion="Type.", orden=1, activo=True
        )
        GravedadAlergia.objects.create(
            nombre="Leve", descripcion="Severity.", orden=1, activo=True
        )
        snapshot = (
            list(ProductoAlergia.objects.values_list("id", flat=True)),
            list(TipoAlergia.objects.values_list("id", flat=True)),
            list(GravedadAlergia.objects.values_list("id", flat=True)),
        )

        _run_with()

        self.assertEqual(
            list(ProductoAlergia.objects.values_list("id", flat=True)),
            snapshot[0],
        )
        self.assertEqual(
            list(TipoAlergia.objects.values_list("id", flat=True)),
            snapshot[1],
        )
        self.assertEqual(
            list(GravedadAlergia.objects.values_list("id", flat=True)),
            snapshot[2],
        )

    @override_settings(
        SEED_ADMIN_URL="not-a-valid-url",
        BASE_URL="also-bad",
    )
    def test_invalid_url_aborts_pre_write(self):
        """When both SEED_ADMIN_URL and BASE_URL are unusable, the command
        aborts before any baseline row is written."""
        with self.assertRaises(CommandError) as ctx:
            _run_with()
        self.assertIn("SEED_ADMIN_URL", str(ctx.exception))

        # Nothing should have been written.
        self.assertEqual(Rol.objects.count(), 0)
        self.assertEqual(self._command_branches().count(), 0)
        self.assertEqual(Usuario.objects.count(), 0)
        self.assertEqual(TabletKiosko.objects.count(), 0)
        self.assertEqual(TipoServicio.objects.count(), 0)
        self.assertEqual(ProcEsteticosTipo.objects.count(), 0)


class CommandHelpersTest(TestCase):
    """Targeted tests for individual helper methods."""

    def test_flag_for(self):
        self.assertEqual(Command._flag_for("admin_password"), "--admin-password")
        self.assertEqual(Command._flag_for("branch_name"), "--branch-name")

    def test_prompt_confirm_accepts_yes(self):
        with mock.patch("builtins.input", return_value="y"):
            self.assertTrue(Command._prompt_confirm("ok?"))
        with mock.patch("builtins.input", return_value="yes"):
            self.assertTrue(Command._prompt_confirm("ok?"))

    def test_prompt_confirm_rejects_other(self):
        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(Command._prompt_confirm("ok?"))
        with mock.patch("builtins.input", return_value=""):
            self.assertFalse(Command._prompt_confirm("ok?"))