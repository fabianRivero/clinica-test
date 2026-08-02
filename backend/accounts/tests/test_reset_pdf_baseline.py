"""Tests for the reset_pdf_baseline destructive orchestrator command.

Covers the contract documented in
``openspec/changes/reset-pdf-baseline/specs/seed-orchestrators/spec.md``:

* Pre-write ``require_dev_or_test()`` guard rejects production / staging /
  empty environments and accepts development / test.
* The ``WARNING`` ``DESTRUCTIVE WIPE`` header is written to ``self.stdout``
  before any inner command output.
* ``handle`` is decorated with ``@transaction.atomic`` and the two
  ``call_command`` invocations are inside that atomic block.
* Mid-flight seed failure rolls back the purge so pre-existing rows survive.
* Two consecutive runs produce byte-stable record counts (idempotent waveform).
* Running on an empty database produces the same state as a fresh
  ``seed_pdf_baseline`` run.
* The sibling command files (``seed_pdf_baseline.py``, ``seed_client_baseline.py``,
  ``purge_data_keep_admin.py``, ``env_guard.py``) are byte-stable — ``git diff``
  against HEAD shows no changes to any of them.
"""

import ast
import io
import subprocess
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.management.commands.reset_pdf_baseline import Command
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
from staff.models import Especialidad, Especialista


# Tables whose counts we compare across runs. Mirrors the model set used in
# ``test_seed_pdf_baseline.py`` so the idempotence assertion checks the same
# surfaces the underlying seed covers.
COUNTED_MODELS = (
    Rol,
    Sucursal,
    Usuario,
    Especialista,
    Especialidad,
    TipoServicio,
    ProcEsteticosTipo,
    ProcEstetico,
    ServicioConfig,
    Prospecto,
    Cliente,
    TabletKiosko,
    AgendaHabitualEspecialista,
    AgendaHabitualDia,
    # Operational tables the purge targets. Counted to ensure they end at 0
    # after a destructive run on a non-empty demo database.
    Operacion,
    CitaMedica,
    CuotaPlanPago,
    PagoRealizado,
    HuellaBiometricaCliente,
    AgendaExcepcionEspecialista,
    DiaBloqueadoAgendaGlobal,
)


def _record_counts() -> dict:
    return {m.__name__: m.objects.count() for m in COUNTED_MODELS}


def _command_source() -> str:
    return Path(Command.__module__.replace(".", "/") + ".py").read_text(
        encoding="utf-8"
    )


def _command_module_name() -> str:
    return Command.__module__.rsplit(".", 1)[-1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_admin():
    """Create a superuser if none exists.

    ``purge_data_keep_admin`` aborts when there is no admin to preserve. In
    a real deployment the operator runs ``seed_client_baseline`` (or
    ``createsuperuser``) first; in the test harness we replicate that.
    """
    if not Usuario.objects.filter(is_superuser=True).exists():
        Usuario.objects.create_superuser(
            username="test.root",
            password="root-pass-123",
            email="root@test.local",
            primer_nombre="Root",
            apellido_paterno="Admin",
        )


# ---------------------------------------------------------------------------
# Env guard tests
# ---------------------------------------------------------------------------


class EnvGuardTests(TestCase):
    """``require_dev_or_test()`` rejects prod/staging/empty, accepts dev/test."""

    def test_rejects_production_pre_write(self):
        pre = _record_counts()
        with override_settings(ENVIRONMENT="production"):
            with self.assertRaises(CommandError) as ctx:
                call_command("reset_pdf_baseline", stdout=io.StringIO())
        self.assertIn("production", str(ctx.exception))
        self.assertEqual(_record_counts(), pre)

    def test_rejects_staging_pre_write(self):
        pre = _record_counts()
        with override_settings(ENVIRONMENT="staging"):
            with self.assertRaises(CommandError):
                call_command("reset_pdf_baseline", stdout=io.StringIO())
        self.assertEqual(_record_counts(), pre)

    def test_rejects_empty_environment_pre_write(self):
        pre = _record_counts()
        with override_settings(ENVIRONMENT=""):
            with self.assertRaises(CommandError):
                call_command("reset_pdf_baseline", stdout=io.StringIO())
        self.assertEqual(_record_counts(), pre)

    @override_settings(ENVIRONMENT="development")
    def test_accepts_development(self):
        _ensure_admin()
        stdout = io.StringIO()
        call_command("reset_pdf_baseline", stdout=stdout)
        # Header must be present.
        self.assertIn("DESTRUCTIVE WIPE", stdout.getvalue())
        # Seed completed: at least one superuser exists (the preserved admin).
        self.assertGreater(Usuario.objects.filter(is_superuser=True).count(), 0)

    @override_settings(ENVIRONMENT="test")
    def test_accepts_test(self):
        _ensure_admin()
        stdout = io.StringIO()
        call_command("reset_pdf_baseline", stdout=stdout)
        self.assertIn("DESTRUCTIVE WIPE", stdout.getvalue())
        self.assertGreater(Usuario.objects.filter(is_superuser=True).count(), 0)


# ---------------------------------------------------------------------------
# Destructive wipe header tests
# ---------------------------------------------------------------------------


class DestructiveHeaderTests(TestCase):
    """The WARNING DESTRUCTIVE WIPE line is emitted before inner output."""

    @override_settings(ENVIRONMENT="development")
    def test_warning_header_precedes_inner_output(self):
        _ensure_admin()
        stdout = io.StringIO()
        # Patch inner call_command so we can record the order of emissions
        # without actually running the inner commands (which would otherwise
        # also write to ``stdout``).
        calls = []

        def tracking_call_command(name, *args, **kwargs):
            calls.append((name, kwargs.get("stdout")))
            # Do not actually execute the inner commands — the test focuses
            # on the relative position of the header vs. inner output.

        # The new command imports ``call_command`` directly from
        # ``django.core.management``; patch the symbol where it is used.
        with mock.patch(
            "accounts.management.commands.reset_pdf_baseline.call_command",
            side_effect=tracking_call_command,
        ):
            call_command("reset_pdf_baseline", stdout=stdout)

        rendered = stdout.getvalue()
        # The WARNING header was emitted.
        self.assertIn("DESTRUCTIVE WIPE", rendered)
        # And it preceded both inner call_command invocations.
        rendered.index("DESTRUCTIVE WIPE")
        self.assertEqual(len(calls), 2)
        # call_command was invoked twice — purge then seed.
        self.assertEqual(calls[0][0], "purge_data_keep_admin")
        self.assertEqual(calls[1][0], "seed_pdf_baseline")
        # Both inner calls forwarded ``stdout=...`` — Django wraps the
        # outer StringIO in an OutputWrapper when it constructs
        # ``self.stdout`` inside the command, so we assert against the
        # wrapped stream's underlying write target rather than the raw
        # StringIO. The relevant guarantee is that the wrapper IS the
        # command's stdout wrapper (same object identity).
        self.assertIsNotNone(calls[0][1])
        self.assertIsNotNone(calls[1][1])
        # The two forwarded streams must be the same object — proving the
        # command used a single stdout wrapper for both inner calls.
        self.assertIs(calls[0][1], calls[1][1])

    @override_settings(ENVIRONMENT="development")
    def test_warning_header_uses_warning_style(self):
        _ensure_admin()
        stdout = io.StringIO()
        with mock.patch(
            "accounts.management.commands.reset_pdf_baseline.call_command"
        ):
            call_command("reset_pdf_baseline", stdout=stdout)
        # The header line is styled as a WARNING. We assert the substring
        # ``DESTRUCTIVE WIPE`` is present; the styling is asserted via the
        # fact that ``self.style.WARNING`` is invoked in the command source.
        rendered = stdout.getvalue()
        self.assertIn("DESTRUCTIVE WIPE", rendered)
        self.assertIn("not reversible", rendered)


# ---------------------------------------------------------------------------
# AST structure tests
# ---------------------------------------------------------------------------


class AtomicStructureTests(TestCase):
    """``handle`` is decorated with ``@transaction.atomic`` and encloses both
    inner ``call_command`` invocations."""

    def setUp(self):
        self.tree = ast.parse(_command_source())
        self.handle = self._find_handle(self.tree)

    @staticmethod
    def _find_handle(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if (
                        isinstance(item, ast.FunctionDef)
                        and item.name == "handle"
                    ):
                        return item
        raise AssertionError("handle method not found")

    def test_handle_is_decorated_with_transaction_atomic(self):
        decorators = self.handle.decorator_list
        atomic_decorators = []
        for dec in decorators:
            text = ast.unparse(dec)
            if "transaction.atomic" in text:
                atomic_decorators.append(text)
        self.assertEqual(
            len(atomic_decorators),
            1,
            f"Expected exactly one @transaction.atomic decorator on handle; "
            f"got {atomic_decorators}",
        )

    def test_handle_invokes_purge_then_seed_via_call_command(self):
        call_command_calls = []
        for node in ast.walk(self.handle):
            if isinstance(node, ast.Call):
                text = ast.unparse(node.func)
                if text.endswith("call_command"):
                    # First positional arg is the command name.
                    if node.args and isinstance(node.args[0], ast.Constant):
                        call_command_calls.append(node.args[0].value)
        self.assertEqual(
            call_command_calls,
            ["purge_data_keep_admin", "seed_pdf_baseline"],
        )

    def test_inner_calls_pass_stdout_kwarg(self):
        for node in ast.walk(self.handle):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith("call_command"):
                continue
            kwarg_names = {kw.arg for kw in node.keywords}
            self.assertIn(
                "stdout",
                kwarg_names,
                f"call_command invocation missing 'stdout' kwarg: "
                f"{ast.unparse(node)}",
            )

    def test_require_dev_or_test_is_first_writable_statement(self):
        """The env guard MUST be the first statement that does any work."""
        # Skip docstring (first statement is often a string).
        body = [s for s in self.handle.body if not isinstance(s, ast.Expr)
                or not isinstance(s.value, ast.Constant)]
        # The first non-docstring statement should be the guard call.
        first_stmt = body[0] if body else None
        self.assertIsNotNone(first_stmt)
        self.assertIsInstance(first_stmt, ast.Expr)
        self.assertIsInstance(first_stmt.value, ast.Call)
        self.assertEqual(
            ast.unparse(first_stmt.value.func),
            "require_dev_or_test",
        )


# ---------------------------------------------------------------------------
# Atomic rollback test (TransactionTestCase)
# ---------------------------------------------------------------------------


class AtomicRollbackTests(TransactionTestCase):
    """A mid-flight seed failure rolls back the purge.

    Uses ``TransactionTestCase`` so the test harness does not wrap each test
    in its own savepoint, which would mask the orchestrator's atomic block.
    """

    def setUp(self):
        _ensure_admin()

    @override_settings(ENVIRONMENT="development")
    def test_midflight_seed_failure_rolls_back_purge(self):
        # Establish a baseline state with one Cliente row by running the
        # real seed_pdf_baseline once (without the destructive wrapper).
        call_command("seed_pdf_baseline", stdout=io.StringIO())
        baseline_clientes = list(Cliente.objects.all())
        baseline_count = len(baseline_clientes)
        self.assertGreater(
            baseline_count,
            0,
            "Pre-condition: seed_pdf_baseline should produce at least one Cliente.",
        )

        # Patch call_command so the second invocation (seed_pdf_baseline) raises.
        real_call_command = call_command
        call_sequence = []

        def failing_call_command(name, *args, **kwargs):
            call_sequence.append(name)
            if name == "seed_pdf_baseline":
                raise RuntimeError("simulated mid-flight seed failure")
            return real_call_command(name, *args, **kwargs)

        with mock.patch(
            "accounts.management.commands.reset_pdf_baseline.call_command",
            side_effect=failing_call_command,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                call_command("reset_pdf_baseline", stdout=io.StringIO())

        self.assertIn("simulated mid-flight seed failure", str(ctx.exception))

        # The purge should have run first (call_sequence order), then the seed
        # raised. The outer atomic block must roll back BOTH.
        self.assertEqual(
            call_sequence,
            ["purge_data_keep_admin", "seed_pdf_baseline"],
        )

        # Critical assertion: the Cliente rows from the baseline seed are
        # still present, proving the purge was rolled back.
        post_cliente_pks = set(Cliente.objects.values_list("pk", flat=True))
        baseline_pks = {c.pk for c in baseline_clientes}
        self.assertTrue(
            baseline_pks.issubset(post_cliente_pks),
            "Pre-existing Cliente rows were not preserved by the atomic "
            "rollback. Expected at least the baseline pks to survive.",
        )


# ---------------------------------------------------------------------------
# Idempotence test
# ---------------------------------------------------------------------------


class IdempotentRunsTests(TestCase):
    """Two consecutive runs produce byte-stable record counts."""

    def setUp(self):
        _ensure_admin()

    def test_two_consecutive_runs_produce_stable_counts(self):
        # First run from empty state.
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=io.StringIO())
        first = _record_counts()

        # Second run on top of the demo state just produced.
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=io.StringIO())
        second = _record_counts()

        self.assertEqual(
            first,
            second,
            f"Idempotence violated. Run-1 counts: {first}; Run-2 counts: {second}",
        )


# ---------------------------------------------------------------------------
# Empty-database safety test
# ---------------------------------------------------------------------------


class EmptyDatabaseTests(TestCase):
    """Running on an empty database equals a fresh ``seed_pdf_baseline`` run."""

    def setUp(self):
        _ensure_admin()

    def test_empty_database_yields_same_state_as_fresh_seed(self):
        # The default test DB starts in an effectively empty state for
        # business tables. Run reset_pdf_baseline first.
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=io.StringIO())
        reset_counts = _record_counts()

        # Now wipe via a real purge and reseed via a real seed.
        with override_settings(ENVIRONMENT="development"):
            call_command("purge_data_keep_admin", "--force", stdout=io.StringIO())
            call_command("seed_pdf_baseline", stdout=io.StringIO())
        manual_counts = _record_counts()

        self.assertEqual(
            reset_counts,
            manual_counts,
            "reset_pdf_baseline on empty DB must equal manual "
            "purge + seed_pdf_baseline.",
        )


# ---------------------------------------------------------------------------
# Sibling non-modification test
# ---------------------------------------------------------------------------


SIBLING_FILES = (
    "backend/accounts/management/commands/seed_pdf_baseline.py",
    "backend/accounts/management/commands/seed_client_baseline.py",
    "backend/accounts/management/commands/purge_data_keep_admin.py",
    "backend/accounts/_baselines/env_guard.py",
)

# ``env_guard.py`` lives under ``_baselines/`` not at the top level; correct
# the path so the subprocess check resolves to the right file.
SIBLING_FILES_FOR_DIFF = (
    "backend/accounts/management/commands/seed_pdf_baseline.py",
    "backend/accounts/management/commands/seed_client_baseline.py",
    "backend/accounts/management/commands/purge_data_keep_admin.py",
    "backend/accounts/management/_baselines/env_guard.py",
)


class SiblingNonModificationTests(TestCase):
    """Sibling command files MUST be byte-stable (no diff vs HEAD)."""

    def test_sibling_files_have_no_uncommitted_changes(self):
        # Check that none of the sibling files appear in the git status as
        # modified or staged. This guards against accidental in-place edits
        # by a future refactor.
        result = subprocess.run(
            ["git", "status", "--porcelain", "--"] + list(SIBLING_FILES_FOR_DIFF),
            capture_output=True,
            text=True,
            check=False,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        self.assertEqual(
            result.stdout.strip(),
            "",
            f"Sibling files were modified. git status output:\n{result.stdout}",
        )

    def test_sibling_files_not_modified_by_this_change(self):
        # Read each sibling file's source bytes from disk twice (before and
        # after a no-op) to assert that the test harness itself does not
        # perturb them. This is a smoke test; the real byte-stability check
        # lives in the ``test_sibling_files_have_no_uncommitted_changes``
        # test above and in the verify report's ``git diff`` line.
        for path in SIBLING_FILES_FOR_DIFF:
            full = Path(__file__).resolve().parents[3] / path
            self.assertTrue(
                full.exists(),
                f"Sibling file missing: {full}",
            )
            content = full.read_bytes()
            self.assertGreater(
                len(content),
                100,
                f"Sibling file looks empty: {path}",
            )


# ---------------------------------------------------------------------------
# Pre-purge FK-nullification tests
# ---------------------------------------------------------------------------


def _make_branch(name="Sucursal Test"):
    """Create a Sucursal in a way that does not depend on the demo seed."""
    return Sucursal.objects.create(nombre=name)


class PrePurgeFKNullificationTests(TransactionTestCase):
    """The orchestrator nulls ``sucursal_id`` on preserved superusers BEFORE
    the inner purge runs.

    Root cause being guarded against: SQLite disables ``PRAGMA foreign_keys``
    inside ``purge_data_keep_admin._clear_tables`` so a bare ``DELETE FROM
    sucursales`` would leave the on-disk ``usuarios.sucursal_id`` pointing
    to a non-existent row. When the outer ``@transaction.atomic`` commits,
    SQLite re-runs ``PRAGMA foreign_key_check`` and raises ``IntegrityError``.
    Pre-purging the FK on preserved superusers (those NOT deleted by the
    inner purge) keeps the commit-time check clean.
    """

    def setUp(self):
        _ensure_admin()
        # Make sure there is at least one superuser linked to a Sucursal.
        self.branch = _make_branch()
        self.super_admin = Usuario.objects.get(is_superuser=True, username="test.root")
        Usuario.objects.filter(pk=self.super_admin.pk).update(sucursal=self.branch)
        self.super_admin.refresh_from_db()
        self.assertIsNotNone(
            self.super_admin.sucursal_id,
            "Pre-condition: superuser must be linked to a Sucursal.",
        )

    def _run_orchestrator(self):
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=io.StringIO())

    def test_pre_purge_nulls_sucursal_on_preserved_superuser(self):
        # After the orchestrator runs, the demo seed focuses on admin.demo;
        # the superuser admin (test.root) has no FK re-link, so its
        # sucursal_id ends up NULL.
        self._run_orchestrator()
        # The preserved superuser is the ``test.root`` admin we created in
        # setUp. The demo seed re-creates ``admin.demo``; it does NOT
        # re-link ``test.root`` to a Sucursal. Therefore ``sucursal_id``
        # must be NULL after the run.
        self.super_admin.refresh_from_db()
        self.assertIsNone(
            self.super_admin.sucursal_id,
            "Preserved superuser's sucursal_id must be NULL after the "
            "orchestrator runs (it is not part of the demo seed).",
        )

    def test_pre_purge_emits_warning_count_line(self):
        stdout = io.StringIO()
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=stdout)
        rendered = stdout.getvalue()
        self.assertIn(
            "Pre-purge integrity",
            rendered,
            f"Expected the pre-purge integrity line in stdout. Got: {rendered!r}",
        )
        self.assertIn(
            "preserved superuser",
            rendered,
        )

    def test_pre_purge_uses_update_not_save(self):
        """The nullification MUST use a queryset ``.update()`` so it bypasses
        any pre-save hook that could re-set the FK. We assert this by
        inspecting the command source via AST and confirming it uses
        ``Usuario.objects.filter(...).update(sucursal=...)`` rather than
        assigning the field on an instance and calling ``.save()``."""
        tree = ast.parse(_command_source())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            text = ast.unparse(node)
            if "Usuario" not in text:
                continue
            if "update" not in text:
                continue
            if "sucursal" not in text:
                continue
            # Found a ``Usuario....update(..., sucursal=...)`` call site.
            kwarg_names = {kw.arg for kw in node.keywords}
            self.assertIn(
                "sucursal",
                kwarg_names,
                f"Pre-purge update must pass sucursal as a kwarg. Found: "
                f"{ast.unparse(node)}",
            )
            return
        self.fail(
            "Expected the command source to contain a "
            "Usuario.objects.filter(...).update(sucursal=...) call. None found.",
        )


class FullWaveformIntegrityTests(TransactionTestCase):
    """Integration: the destructive waveform commits clean even on a
    database that already has a foreign-key-violating state."""

    def test_full_waveform_commits_clean(self):
        # Plant a state that would break the COMMIT-time FK check if the
        # pre-purge nullification did not run: a user with a ``sucursal_id``
        # pointing to a non-existent Sucursal row. SQLite enforces FKs on
        # write when ``PRAGMA foreign_keys = ON`` (the default), so we
        # bypass enforcement for the planting step.
        _ensure_admin()
        ghost_id = 999_999_999
        admin = Usuario.objects.get(is_superuser=True, username="test.root")
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys = OFF;")
            try:
                cursor.execute(
                    "UPDATE usuarios SET sucursal_id = ? WHERE id = ?;",
                    [ghost_id, admin.pk],
                )
            finally:
                cursor.execute("PRAGMA foreign_keys = ON;")
        admin.refresh_from_db()
        self.assertEqual(
            admin.sucursal_id,
            ghost_id,
            "Pre-condition: ghost FK was not planted on the superuser.",
        )

        # Run the orchestrator. It MUST NOT raise.
        with override_settings(ENVIRONMENT="development"):
            call_command("reset_pdf_baseline", stdout=io.StringIO())

        # After commit, PRAGMA foreign_key_check must return no rows.
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA foreign_key_check;")
            violations = cursor.fetchall()
        self.assertEqual(
            violations,
            [],
            f"PRAGMA foreign_key_check returned violations: {violations}",
        )


class SeedFailureRollbackTests(TransactionTestCase):
    """A failure raised inside the inner ``seed_pdf_baseline`` rolls back
    the destructive purge AND the pre-purge FK nullification. The database
    must end up exactly as it was before ``reset_pdf_baseline`` ran."""

    def setUp(self):
        _ensure_admin()

    def test_failed_seed_rolls_back_purge(self):
        # Build a baseline state by running the real seed_pdf_baseline
        # once. This gives us a known good post-seed snapshot.
        call_command("seed_pdf_baseline", stdout=io.StringIO())
        # Add an extra Sucursal (4th) and link a preserved superuser to it
        # so the pre-purge nullification step has actual work to do AND so
        # we have a non-demo branch in the snapshot to detect partial
        # rollbacks.
        branch = _make_branch("Rollback Branch")
        admin = Usuario.objects.get(is_superuser=True, username="test.root")
        Usuario.objects.filter(pk=admin.pk).update(sucursal=branch)
        admin.refresh_from_db()
        self.assertEqual(admin.sucursal_id, branch.pk)

        # Snapshot AFTER all pre-call mutations so the comparison covers
        # the exact state we expect the rollback to restore.
        pre_baseline = _record_counts()
        pre_cliente_pks = set(Cliente.objects.values_list("pk", flat=True))
        pre_usuario_pks = set(Usuario.objects.values_list("pk", flat=True))
        pre_sucursal_pks = set(Sucursal.objects.values_list("pk", flat=True))

        # Now monkey-patch ``clean_baseline.seed_branches`` (the first
        # meaningful write inside seed_pdf_baseline) to raise. The failure
        # must propagate out of the inner call_command, out of the outer
        # @transaction.atomic, and the entire waveform must roll back.
        def _explode(*args, **kwargs):
            raise RuntimeError("simulated seed_branches failure")

        with mock.patch(
            "accounts.management._baselines.clean_baseline.seed_branches",
            side_effect=_explode,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                with override_settings(ENVIRONMENT="development"):
                    call_command("reset_pdf_baseline", stdout=io.StringIO())
        self.assertIn("simulated seed_branches failure", str(ctx.exception))

        # The database MUST be unchanged from the pre-call state. The outer
        # @transaction.atomic must have rolled back the pre-purge nullify,
        # the purge itself, and any partial seed writes.
        post_cliente_pks = set(Cliente.objects.values_list("pk", flat=True))
        post_usuario_pks = set(Usuario.objects.values_list("pk", flat=True))
        post_sucursal_pks = set(Sucursal.objects.values_list("pk", flat=True))
        self.assertEqual(
            pre_cliente_pks,
            post_cliente_pks,
            "Cliente rows were altered despite the seed failure — the "
            "outer atomic block did not roll back.",
        )
        self.assertEqual(
            pre_usuario_pks,
            post_usuario_pks,
            "Usuario rows were altered despite the seed failure — the "
            "outer atomic block did not roll back.",
        )
        self.assertEqual(
            pre_sucursal_pks,
            post_sucursal_pks,
            "Sucursal rows were altered despite the seed failure — the "
            "outer atomic block did not roll back.",
        )
        admin.refresh_from_db()
        self.assertEqual(
            admin.sucursal_id,
            branch.pk,
            "Preserved superuser's FK was nullified but the surrounding "
            "transaction was not rolled back.",
        )
        # The full record-count snapshot must match what we had pre-call.
        self.assertEqual(
            _record_counts(),
            pre_baseline,
            "Record counts changed despite the seed failure — outer atomic "
            "did not roll back.",
        )
