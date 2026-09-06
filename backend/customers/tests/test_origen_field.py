"""Backend tests for the new ``Cliente.origen`` field.

Spec under test: ``openspec/changes/cliente-origen-recurrente/specs/cliente-origen/spec.md``
and the modified ``admin-client-profile-editing`` write-once rule.

Four concerns, four test classes:

* ``ClienteOrigenFieldTests`` — direct model coverage: defaults to
  ``NUEVO`` on construction, ``Origen`` exposes the two expected values,
  ``full_clean()`` rejects anything outside the enumeration.
* ``ClienteOrigenMigrationBackfillTests`` — asserts the ``0015_cliente_origen``
  migration actually exists, depends on ``0014_cliente_cliente_codigo``,
  and that the column at the DB layer carries the ``NUEVO`` default so a
  row inserted without the column gets backfilled (this is the schema
  contract that protects a real production rollout with existing
  ``clientes`` rows).
* ``ClienteOrigenPerfilEndpointTests`` — PATCH
  ``/api/admin/clientes/<pk>/perfil/`` with an ``origen`` key MUST
  return 400 and MUST leave the live ``Cliente.origen`` untouched, per
  the ``admin-client-profile-editing`` write-once rule.
* ``ClienteOrigenSerializerExposesOrigenTests`` — every Cliente-shaped
  payload (search serializer, profile envelope, search endpoint) MUST
  carry the literal ``origen`` value per the spec scenario "origin
  values exposed in API serialization".

Style follows ``backend/tests/test_admin_client_profile.py``
(``TestCase`` + ``django.test.Client`` + session auth).
"""

from __future__ import annotations

import json
from datetime import date

from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.test.utils import override_settings

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from customers.models import Cliente


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Minimum role/branch/admin/cliente graph for the perfil tests."""
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    sucursal = Sucursal.objects.create(nombre="Origen-Centro", activa=True)

    admin = Usuario.objects.create_user(
        username="origen.admin",
        password="pw12345!",
        primer_nombre="Ana",
        apellido_paterno="Origen",
        email="origen.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    cliente_user = Usuario.objects.create_user(
        username="origen.cliente1",
        password="pw12345!",
        primer_nombre="Juan",
        apellido_paterno="Perez",
        email="juan@origen.com",
        telefono="7000-1111",
        rol=rol_cliente,
        sucursal=sucursal,
    )
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=sucursal,
        ci="11111",
        telefono="7000-1111",
        fecha_nacimiento=date(1990, 1, 1),
    )
    return {
        "rol_admin": rol_admin,
        "rol_cliente": rol_cliente,
        "sucursal": sucursal,
        "admin": admin,
        "cliente": cliente,
        "cliente_user": cliente_user,
    }


# ---------------------------------------------------------------------------
# Class A — model field semantics
# ---------------------------------------------------------------------------


class ClienteOrigenFieldTests(TestCase):
    """``Cliente.origen`` exposes the contract from the spec."""

    def test_origen_choices_match_spec(self):
        """``Origen`` exposes exactly ``NUEVO`` and ``RECURRENTE_PRE_SISTEMA``."""
        choices = dict(Cliente.Origen.choices)
        self.assertEqual(
            set(choices.keys()),
            {"NUEVO", "RECURRENTE_PRE_SISTEMA"},
        )
        self.assertEqual(choices["NUEVO"], "Nuevo")
        self.assertEqual(
            choices["RECURRENTE_PRE_SISTEMA"],
            "Recurrente pre-sistema",
        )

    def test_default_origen_is_nuevo(self):
        """New ``Cliente`` rows default to ``NUEVO`` per the spec."""
        rol_cliente = Rol.objects.create(rol="CLIENTE")
        sucursal = Sucursal.objects.create(nombre="Origen-Default", activa=True)
        user = Usuario.objects.create_user(
            username="default.user",
            password="pw12345!",
            primer_nombre="Def",
            apellido_paterno="Ault",
            rol=rol_cliente,
            sucursal=sucursal,
        )
        cliente = Cliente.objects.create(
            usuario=user,
            sucursal_origen=sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )
        self.assertEqual(cliente.origen, Cliente.Origen.NUEVO)

    def test_explicit_recurrente_persists(self):
        """Explicit ``RECURRENTE_PRE_SISTEMA`` survives the round trip."""
        rol_cliente = Rol.objects.create(rol="CLIENTE")
        sucursal = Sucursal.objects.create(nombre="Origen-Recurrente", activa=True)
        user = Usuario.objects.create_user(
            username="recurrente.user",
            password="pw12345!",
            primer_nombre="Rec",
            apellido_paterno="Urrente",
            rol=rol_cliente,
            sucursal=sucursal,
        )
        cliente = Cliente.objects.create(
            usuario=user,
            sucursal_origen=sucursal,
            fecha_nacimiento=date(1985, 5, 5),
            origen=Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )
        cliente.refresh_from_db()
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_full_clean_rejects_unknown_value(self):
        """``full_clean()`` rejects values outside the enumeration."""
        g = _build_graph()
        g["cliente"].origen = "ALGOTRO"
        with self.assertRaises(ValidationError) as ctx:
            g["cliente"].full_clean()
        # The field-level error must mention ``origen`` — the change spec
        # pins this as the rejection path for unknown values.
        self.assertIn("origen", ctx.exception.message_dict)


# ---------------------------------------------------------------------------
# Class B — migration backfill
# ---------------------------------------------------------------------------


class ClienteOrigenMigrationBackfillTests(TestCase):
    """The ``0015_cliente_origen`` migration backfills every existing row.

    The contract is that the column ``origen`` is added with a Python
    default of ``"NUEVO"`` so any pre-existing ``clientes`` row gets
    the literal value on apply — Django's ``AddField`` for non-null
    ``CharField`` with a default is implemented as a table rebuild
    that copies every row into ``new__<table>`` while assigning the
    default to the new column. We assert three things:

    1. The migration is on disk.
    2. The migration depends on the prior
       ``0014_cliente_cliente_codigo`` migration.
    3. The ``AddField`` operation carries ``default="NUEVO"`` so the
       rebuild emits ``'NUEVO'`` for every copied row.
    """

    def test_migration_module_exists(self):
        """``0015_cliente_origen`` is present on disk."""
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations.get(("customers", "0015_cliente_origen"))
        self.assertIsNotNone(
            migration,
            "0015_cliente_origen must exist on disk",
        )

    def test_migration_depends_on_previous(self):
        """``0015_cliente_origen`` chains to ``0014_cliente_cliente_codigo``."""
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations[("customers", "0015_cliente_origen")]
        deps_names = [name for app, name in migration.dependencies if app == "customers"]
        self.assertIn(
            "0014_cliente_cliente_codigo",
            deps_names,
            f"0015 must depend on 0014; got deps={migration.dependencies!r}",
        )

    def test_migration_addfield_carries_nuevo_default(self):
        """The ``AddField`` carries ``default="NUEVO"`` so the rebuild backfills."""
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.operations import AddField

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations[("customers", "0015_cliente_origen")]
        add_field_ops = [op for op in migration.operations if isinstance(op, AddField)]
        self.assertEqual(
            len(add_field_ops),
            1,
            "0015_cliente_origen must contain exactly one AddField",
        )
        op = add_field_ops[0]
        field = op.field
        self.assertEqual(op.name, "origen")
        # ``default`` + ``db_default`` on a non-null field trigger
        # Django's table-rebuild path that emits
        # ``SELECT 'NUEVO' FROM old_table`` in SQL. ``db_default`` also
        # keeps ``bulk_create`` paths (which skip the Python-side
        # default) covered at the SQL layer — important because the
        # project's test suite builds ``Cliente`` rows via
        # ``bulk_create``.
        self.assertEqual(field.default, "NUEVO")
        self.assertEqual(field.db_default, "NUEVO")
        self.assertFalse(field.null, "origen must be NOT NULL")


# ---------------------------------------------------------------------------
# Class C — perfil endpoint rejects ``origen``
# ---------------------------------------------------------------------------


class ClienteOrigenPerfilEndpointTests(TestCase):
    """PATCH ``/api/admin/clientes/<pk>/perfil/`` MUST NOT accept ``origen``."""

    @classmethod
    def setUpTestData(cls):
        cls.g = _build_graph()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.g["admin"])

    def test_patch_origen_returns_400_and_preserves_stored_value(self):
        """PATCH carrying ``origen`` returns 400 and the live row is intact.

        Spec — ``cliente-origen`` › "write-once origin" and the modified
        ``admin-client-profile-editing`` "Editable Fields" scenario.
        """
        cliente = self.g["cliente"]
        # Sanity: existing row carries the default ``NUEVO``.
        self.assertEqual(cliente.origen, Cliente.Origen.NUEVO)

        response = self.http.patch(
            f"/api/admin/clientes/{cliente.id}/perfil/",
            data=json.dumps({"origen": "RECURRENTE_PRE_SISTEMA"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        # The serializer rejects the unknown ``origen`` key through the
        # same path it uses for every other non-13-field input — the
        # body must mention the offending key.
        combined = json.dumps(body)
        self.assertIn("origen", combined)

        cliente.refresh_from_db()
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.NUEVO,
            "live origen must not change when perfil PATCH carries it",
        )
    def test_patch_without_origen_preserves_recurrente_value(self):
        """PATCH omitting ``origen`` leaves a ``RECURRENTE_PRE_SISTEMA`` row intact."""
        cliente = self.g["cliente"]
        cliente.origen = Cliente.Origen.RECURRENTE_PRE_SISTEMA
        cliente.save(update_fields=["origen", "updated_at"])

        response = self.http.patch(
            f"/api/admin/clientes/{cliente.id}/perfil/",
            data=json.dumps({"telefono": "7000-9999"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        cliente.refresh_from_db()
        self.assertEqual(cliente.telefono, "7000-9999")
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
            "origen must be preserved when perfil PATCH omits the field",
        )


# ---------------------------------------------------------------------------
# Class D — serializers expose ``origen``
# ---------------------------------------------------------------------------


class ClienteOrigenSerializerExposesOrigenTests(TestCase):
    """Every Cliente-shaped payload MUST surface the literal ``origen``.

    Spec — ``cliente-origen`` › "origin values exposed in API serialization".
    Without this contract, the frontend cannot render the reporting
    visibility badge (Requirement 3 / reporting visibility scenario).
    """

    @classmethod
    def setUpTestData(cls):
        cls.g = _build_graph()

        # A second client with the alternative ``origen`` so we exercise
        # both code paths in the same call.
        cls.cliente_recurrente = Cliente.objects.create(
            usuario=Usuario.objects.create_user(
                username="origen.cliente2",
                password="pw12345!",
                primer_nombre="Maria",
                apellido_paterno="Recurrente",
                email="maria@origen.com",
                telefono="7000-2222",
                rol=cls.g["rol_cliente"],
                sucursal=cls.g["sucursal"],
            ),
            sucursal_origen=cls.g["sucursal"],
            ci="22222",
            telefono="7000-2222",
            fecha_nacimiento=date(1985, 5, 5),
            origen=Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_client_search_serializer_includes_origen_field(self):
        """``ClientSearchSerializer.to_representation`` returns the literal value."""
        from config.api.serializers.clientes import ClientSearchSerializer

        nuevo = ClientSearchSerializer(self.g["cliente"]).data
        self.assertEqual(nuevo["origen"], Cliente.Origen.NUEVO)

        recurrente = ClientSearchSerializer(self.cliente_recurrente).data
        self.assertEqual(
            recurrente["origen"],
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_search_endpoint_returns_origen_in_payload(self):
        """``/clientes/buscar-global/`` payloads include ``origen``.

        The endpoint now routes through ``ClientSearchSerializer`` so
        the spec contract is verified end-to-end (HTTP layer +
        serializer layer).
        """
        self.http = Client()
        self.http.force_login(self.g["admin"])

        # The endpoint requires a query of at least 3 characters.
        response = self.http.get(
            "/api/admin/clientes/buscar-global/?q=Maria",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("clients", body)
        self.assertGreaterEqual(
            len(body["clients"]),
            1,
            "search must return at least the recurring cliente",
        )
        # Every returned row MUST carry the literal ``origen``.
        for row in body["clients"]:
            self.assertIn("origen", row)
            self.assertIn(
                row["origen"],
                {"NUEVO", "RECURRENTE_PRE_SISTEMA"},
                f"unexpected origen literal: {row['origen']!r}",
            )

    def test_build_initial_client_user_data_includes_origen(self):
        """``_build_initial_client_user_data`` envelope includes ``origen``.

        The perfil endpoint uses this helper as the response shape, so
        the assertion covers both the modal hydration and the PATCH
        response envelope.
        """
        from config.prospect_conversion_views import _build_initial_client_user_data

        payload = _build_initial_client_user_data(self.cliente_recurrente)
        self.assertIn("origen", payload)
        self.assertEqual(
            payload["origen"],
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_perfil_endpoint_response_envelope_includes_origen(self):
        """PATCH ``/perfil/`` response envelope surfaces the live ``origen``.

        The serializer rejects writes to ``origen`` (write-once contract)
        but the response envelope MUST carry the current stored value so
        the modal can re-hydrate from one source of truth.
        """
        self.http = Client()
        self.http.force_login(self.g["admin"])

        response = self.http.patch(
            f"/api/admin/clientes/{self.cliente_recurrente.id}/perfil/",
            data=json.dumps({"telefono": "7000-3333"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("client", body)
        self.assertEqual(
            body["client"].get("origen"),
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )