"""Tests for the seed_pdf_baseline management command.

Covers the B1 work unit of the ``reform-database-seed-scripts`` change:

* ``require_dev_or_test`` pre-transaction guard (rejects production, accepts
  development and test).
* Deterministic record counts across consecutive runs.
* Dedicated ``admin.demo`` distinct from the clean-baseline admin.
* AST-level guarantee that the rewritten command never calls ``.delete()``
  on the nine operational tables identified in ``exploration.md``.
* End-to-end reproduction of the demo dataset.
"""

import ast
import io
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.management.commands.seed_pdf_baseline import Command
from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente, HuellaBiometricaCliente, Prospecto
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    CitaMedica,
    DiaBloqueadoAgendaGlobal,
    Operacion,
    TabletKiosko,
)
from staff.models import Especialidad, Especialista  # noqa: F401


# Nine operational tables from exploration.md — the AST no-delete assertion
# must guarantee the rewritten command never calls ``.delete()`` on any of
# these.
OPERATIONAL_TABLES = (
    "Operacion",
    "CitaMedica",
    "CuotaPlanPago",
    "PagoRealizado",
    "HuellaBiometricaCliente",
    "AgendaExcepcionEspecialista",
    "AgendaHabitualDia",
    "AgendaHabitualEspecialista",
    "DiaBloqueadoAgendaGlobal",
)


def _command_source() -> str:
    return Path(Command.__module__.replace(".", "/") + ".py").read_text(
        encoding="utf-8"
    )


def _record_counts() -> dict:
    return {
        "roles": Rol.objects.count(),
        "sucursales": Sucursal.objects.count(),
        "usuarios": Usuario.objects.count(),
        "admins": Usuario.objects.filter(is_superuser=True).count(),
        "especialistas": Especialista.objects.count(),
        "especialidades": Especialidad.objects.count(),
        "tipo_servicios": TipoServicio.objects.count(),
        "proc_tipos": ProcEsteticosTipo.objects.count(),
        "procs": ProcEstetico.objects.count(),
        "servicios": ServicioConfig.objects.count(),
        "prospectos": Prospecto.objects.count(),
        "clientes": Cliente.objects.count(),
        "kioskos": TabletKiosko.objects.count(),
        "agendas": AgendaHabitualEspecialista.objects.count(),
        "dias_agenda": AgendaHabitualDia.objects.count(),
        "operaciones": Operacion.objects.count(),
        "citas": CitaMedica.objects.count(),
        "cuotas": CuotaPlanPago.objects.count(),
        "pagos": PagoRealizado.objects.count(),
        "huellas": HuellaBiometricaCliente.objects.count(),
    }


class EnvGuardTests(TestCase):
    """The pre-transaction env guard rejects prod/staging, accepts dev/test."""

    def test_rejects_production_pre_write(self):
        pre = _record_counts()
        with override_settings(ENVIRONMENT="production"):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_pdf_baseline", stdout=io.StringIO())
        self.assertIn("production", str(ctx.exception))
        self.assertEqual(_record_counts(), pre)

    def test_rejects_staging_pre_write(self):
        pre = _record_counts()
        with override_settings(ENVIRONMENT="staging"):
            with self.assertRaises(CommandError):
                call_command("seed_pdf_baseline", stdout=io.StringIO())
        self.assertEqual(_record_counts(), pre)

    @override_settings(ENVIRONMENT="development")
    def test_accepts_development(self):
        call_command("seed_pdf_baseline", stdout=io.StringIO())
        self.assertGreater(Usuario.objects.count(), 0)

    @override_settings(ENVIRONMENT="test")
    def test_accepts_test(self):
        call_command("seed_pdf_baseline", stdout=io.StringIO())
        self.assertGreater(Usuario.objects.count(), 0)


class DeterministicRecordCountsAcrossRunsTests(TestCase):
    """Two consecutive runs must produce byte-stable record counts."""

    def test_deterministic_record_counts_across_runs(self):
        with override_settings(ENVIRONMENT="development"):
            call_command("seed_pdf_baseline", stdout=io.StringIO())
        first = _record_counts()

        with override_settings(ENVIRONMENT="development"):
            call_command("seed_pdf_baseline", stdout=io.StringIO())
        second = _record_counts()

        self.assertEqual(first, second)


class DemoAdminDistinctFromCleanAdminTests(TestCase):
    """``admin.demo`` coexists with the clean-baseline ``admin.general``."""

    def test_demo_admin_distinct_from_clean_admin(self):
        with override_settings(ENVIRONMENT="development"):
            call_command("seed_pdf_baseline", stdout=io.StringIO())

        self.assertTrue(
            Usuario.objects.filter(username="admin.general").exists()
        )
        self.assertTrue(
            Usuario.objects.filter(username="admin.demo").exists()
        )

        clean = Usuario.objects.get(username="admin.general")
        self.assertTrue(clean.is_superuser)
        self.assertEqual(clean.apellido_paterno, "General")

        demo = Usuario.objects.get(username="admin.demo")
        self.assertTrue(demo.is_superuser)
        self.assertEqual(demo.apellido_paterno, "Demo")
        self.assertNotEqual(clean.pk, demo.pk)

        self.assertGreaterEqual(
            Usuario.objects.filter(is_superuser=True).count(), 2
        )


class NoDeleteCallsOnOperationalTablesTests(TestCase):
    """AST scan: the rewritten command never calls ``.delete()`` on any of
    the nine operational tables identified in ``exploration.md``.

    Scoped to ``seed_pdf_baseline.py`` only — the ``clean_baseline`` library
    is allowed to call ``.delete()`` on its own relationship tables (e.g.
    ``EspecialistaEspecialidad`` cleanup) because that path is governed by
    its own test surface.
    """

    def setUp(self):
        self.tree = ast.parse(_command_source())

    def test_no_delete_calls_on_operational_tables(self):
        offenders = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            target = self._target_text(node.func)
            if not target or not target.endswith(".delete"):
                continue
            for table in OPERATIONAL_TABLES:
                if target.startswith(f"{table}."):
                    offenders.append((table, target))
                    break
        self.assertEqual(
            offenders,
            [],
            f"seed_pdf_baseline.py must not call .delete() on the nine "
            f"operational tables. Offenders: {offenders}",
        )

    @staticmethod
    def _target_text(func):
        if hasattr(ast, "unparse"):
            return ast.unparse(func)
        # Fallback: walk the attribute chain by hand.
        parts = []
        cur = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))


class FullBaselineReproductionTests(TestCase):
    """End-to-end run yields the expected entities."""

    def test_full_baseline_reproduction(self):
        with override_settings(ENVIRONMENT="development"):
            call_command("seed_pdf_baseline", stdout=io.StringIO())

        self.assertEqual(
            set(Rol.objects.values_list("rol", flat=True)),
            {"ADMIN_PRINCIPAL", "ADMIN_SUCURSAL", "TRABAJADOR", "CLIENTE"},
        )

        self.assertEqual(
            set(
                Sucursal.objects.filter(
                    nombre__in=[
                        "Sede Principal",
                        "Sucursal Norte",
                        "Sucursal Sur",
                    ]
                ).values_list("nombre", flat=True)
            ),
            {"Sede Principal", "Sucursal Norte", "Sucursal Sur"},
        )

        for username in (
            "admin.general",
            "admin.norte",
            "admin.sur",
            "admin.demo",
        ):
            self.assertTrue(
                Usuario.objects.filter(username=username).exists(),
                f"Admin {username} missing",
            )

        for username in (
            "lucia.laser",
            "diego.tatuajes",
            "sofia.manchas",
            "rafael.consulta",
        ):
            self.assertTrue(
                Usuario.objects.filter(username=username).exists(),
                f"Specialist {username} missing",
            )

        # Shared aesthetic catalog (cross-command invariant)
        self.assertEqual(ProcEsteticosTipo.objects.filter(tipo="Laser").count(), 1)
        self.assertEqual(ProcEstetico.objects.count(), 3)
        self.assertEqual(ServicioConfig.objects.count(), 4)

        self.assertGreaterEqual(Prospecto.objects.count(), 2)
        self.assertGreaterEqual(
            Cliente.objects.filter(
                usuario__username__in=["paciente.demo", "paciente.inactivo"]
            ).count(),
            2,
        )

        self.assertEqual(
            set(TabletKiosko.objects.values_list("codigo", flat=True))
            & {"KIOSKO-PRINCIPAL", "KIOSKO-NORTE", "KIOSKO-SUR"},
            {"KIOSKO-PRINCIPAL", "KIOSKO-NORTE", "KIOSKO-SUR"},
        )

        self.assertEqual(AgendaHabitualEspecialista.objects.count(), 4)
        self.assertEqual(AgendaHabitualDia.objects.count(), 20)
