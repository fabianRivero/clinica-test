"""Backend tests for the new ``Prospecto.origen`` field.

Spec under test: ``openspec/changes/prospecto-origen-heredable/specs/prospecto-origen/spec.md``.

Three concerns, three test classes:

* ``ProspectoOrigenFieldTests`` — direct model coverage: defaults to
  ``NUEVO`` on construction, ``Origen`` exposes the two expected values,
  ``full_clean()`` rejects anything outside the enumeration.
* ``ProspectoOrigenMigrationBackfillTests`` — asserts the
  ``0016_prospecto_origen`` migration exists, depends on
  ``0015_cliente_origen``, and that the column carries the ``NUEVO``
  default so a row inserted without the column gets backfilled (this
  is the schema contract that protects a real production rollout with
  existing ``prospectos`` rows).
* ``ProspectoOrigenMarcarComoConvertidoTests`` — the
  ``marcar_como_convertido`` admin lifecycle MUST NOT touch the
  ``origen`` field; conversion is metadata-only, not a state-machine
  input.

Style follows ``backend/customers/tests/test_origen_field.py``
(``TestCase`` + ``django.test.Client`` + session auth).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from accounts.models import Rol, Usuario
from catalogs.models import (
    GradoDeshidratacion,
    GrosorPiel,
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from customers.models import Cliente, Prospecto, ProspectoConversionBorrador


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_graph():
    """Minimum role/branch/admin graph for the prospect lifecycle tests.

    Includes a ``ServicioConfig`` and the catalog entries the finalize
    endpoint requires so the conversion finalize tests can build a
    fully-populated draft without re-creating fixtures per test class.
    """
    rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    sucursal = Sucursal.objects.create(nombre="Prospecto-Origen-Centro", activa=True)

    admin = Usuario.objects.create_user(
        username="prospecto_origen.admin",
        password="pw12345!",
        primer_nombre="Ana",
        apellido_paterno="Prospecto",
        email="prospecto_origen.admin@example.com",
        rol=rol_admin,
        sucursal=sucursal,
    )

    tipo_servicio = TipoServicio.objects.create(tipo="Prospecto-Limpieza", activo=True)
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo_servicio,
        activo=True,
        precio_base=Decimal("100.00"),
    )
    tipo_piel = TipoPiel.objects.create(nombre="Normal", activo=True)
    grado = GradoDeshidratacion.objects.create(nombre="Bajo", activo=True)
    grosor = GrosorPiel.objects.create(nombre="Medio", activo=True)

    return {
        "rol_admin": rol_admin,
        "rol_cliente": rol_cliente,
        "sucursal": sucursal,
        "admin": admin,
        "servicio": servicio,
        "catalog_ids": {
            "tipo_piel": tipo_piel.id,
            "grado_deshidratacion": grado.id,
            "grosor_piel": grosor.id,
        },
    }


def _make_prospect_draft(*, prospecto, admin, servicio, catalog_ids, today, **user_extras):
    """Build a fully-populated ``mode='prospect'`` conversion draft."""
    user_payload = {
        "primerNombre": prospecto.primer_nombre,
        "apellidoPaterno": prospecto.apellido_paterno,
        "username": f"prospecto_origen.{prospecto.pk}",
        "email": f"prospecto_origen.{prospecto.pk}@example.com",
        "passwordHash": make_password("pw-prospecto-origen"),
        "fechaNacimiento": "1990-01-01",
        "ci": "7777777",
    }
    user_payload.update(user_extras)

    return ProspectoConversionBorrador.objects.create(
        prospecto=prospecto,
        cliente=None,
        iniciado_por=admin,
        datos_usuario=user_payload,
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Cara",
            "zonaEspecifica": "Mejilla",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": "EN_PROCESO",
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta-prospecto-origen",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "7777777",
            "analisisEstetico": {
                "tipoPielId": str(catalog_ids["tipo_piel"]),
                "gradoDeshidratacionId": str(catalog_ids["grado_deshidratacion"]),
                "grosorPielId": str(catalog_ids["grosor_piel"]),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria={"template": "", "quality": 0, "provider": "MOCK_LEGACY"},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _make_reactivation_draft(*, cliente, admin, servicio, catalog_ids, today, **user_extras):
    """Build a fully-populated ``mode='reactivation'`` conversion draft."""
    user_payload = {
        "primerNombre": cliente.usuario.primer_nombre,
        "apellidoPaterno": cliente.usuario.apellido_paterno,
        "username": cliente.usuario.username,
        "observacionesCliente": "obs-reactivacion-origen",
    }
    user_payload.update(user_extras)

    return ProspectoConversionBorrador.objects.create(
        prospecto=None,
        cliente=cliente,
        iniciado_por=admin,
        datos_usuario=user_payload,
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Cara",
            "zonaEspecifica": "Mejilla",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": "EN_PROCESO",
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta-reactivacion-origen",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": cliente.ci or "",
            "analisisEstetico": {
                "tipoPielId": str(catalog_ids["tipo_piel"]),
                "gradoDeshidratacionId": str(catalog_ids["grado_deshidratacion"]),
                "grosorPielId": str(catalog_ids["grosor_piel"]),
                "patologiaIds": [],
            },
            "antecedentes": [],
            "implantes": [],
            "cirugias": [],
            "fieldResponses": {},
        },
        datos_biometria={"template": "", "quality": 0, "provider": "MOCK_LEGACY"},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


# ---------------------------------------------------------------------------
# Class A — model field semantics
# ---------------------------------------------------------------------------


class ProspectoOrigenFieldTests(TestCase):
    """``Prospecto.origen`` exposes the contract from the spec."""

    def test_origen_choices_match_spec(self):
        """``Origen`` exposes exactly ``NUEVO`` and ``RECURRENTE_PRE_SISTEMA``."""
        choices = dict(Prospecto.Origen.choices)
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
        """New ``Prospecto`` rows default to ``NUEVO`` per the spec."""
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Def",
            apellido_paterno="Ault",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
        )
        self.assertEqual(prospecto.origen, Prospecto.Origen.NUEVO)

    def test_explicit_recurrente_persists(self):
        """Explicit ``RECURRENTE_PRE_SISTEMA`` survives the round trip."""
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Rec",
            apellido_paterno="Urrente",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
            origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )
        prospecto.refresh_from_db()
        self.assertEqual(
            prospecto.origen,
            Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_full_clean_rejects_unknown_value(self):
        """``full_clean()`` rejects values outside the enumeration."""
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Bad",
            apellido_paterno="Origen",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
        )
        prospecto.origen = "ALGOTRO"
        with self.assertRaises(ValidationError) as ctx:
            prospecto.full_clean()
        self.assertIn("origen", ctx.exception.message_dict)

    def test_resaving_preserves_original_origin(self):
        """Re-saving without an explicit ``origen`` keeps the stored value.

        Spec — ``prospecto-origen`` › "write-once prospect origin" › "Re-saving
        preserves the original origin".
        """
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Stable",
            apellido_paterno="Origen",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
            origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )
        # ``update_fields`` omits ``origen``; the value must be preserved.
        prospecto.observaciones = "nota nueva"
        prospecto.save(update_fields=["observaciones", "updated_at"])
        prospecto.refresh_from_db()
        self.assertEqual(
            prospecto.origen,
            Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )


# ---------------------------------------------------------------------------
# Class B — migration backfill
# ---------------------------------------------------------------------------


class ProspectoOrigenMigrationBackfillTests(TestCase):
    """The ``0016_prospecto_origen`` migration backfills every existing row.

    Mirrors the contract asserted by
    ``backend/customers/tests/test_origen_field.py`` for
    ``0015_cliente_origen``: the column is added with a Python default
    of ``"NUEVO"`` so the table rebuild emits ``'NUEVO'`` for every
    copied row. ``db_default`` keeps ``bulk_create`` paths covered at
    the SQL layer.
    """

    def test_migration_module_exists(self):
        """``0016_prospecto_origen`` is present on disk."""
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations.get(("customers", "0016_prospecto_origen"))
        self.assertIsNotNone(
            migration,
            "0016_prospecto_origen must exist on disk",
        )

    def test_migration_depends_on_previous(self):
        """``0016_prospecto_origen`` chains to ``0015_cliente_origen``."""
        from django.db.migrations.loader import MigrationLoader

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations[("customers", "0016_prospecto_origen")]
        deps_names = [name for app, name in migration.dependencies if app == "customers"]
        self.assertIn(
            "0015_cliente_origen",
            deps_names,
            f"0016 must depend on 0015; got deps={migration.dependencies!r}",
        )

    def test_migration_addfield_carries_nuevo_default(self):
        """The ``AddField`` carries ``default="NUEVO"`` and ``db_default``."""
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.operations import AddField

        loader = MigrationLoader(None, ignore_no_migrations=True)
        migration = loader.disk_migrations[("customers", "0016_prospecto_origen")]
        add_field_ops = [op for op in migration.operations if isinstance(op, AddField)]
        self.assertEqual(
            len(add_field_ops),
            1,
            "0016_prospecto_origen must contain exactly one AddField",
        )
        op = add_field_ops[0]
        field = op.field
        self.assertEqual(op.name, "origen")
        self.assertEqual(field.default, "NUEVO")
        self.assertEqual(field.db_default, "NUEVO")
        self.assertFalse(field.null, "origen must be NOT NULL")


# ---------------------------------------------------------------------------
# Class C — ``marcar_como_convertido`` leaves ``origen`` untouched
# ---------------------------------------------------------------------------


class ProspectoOrigenMarcarComoConvertidoTests(TestCase):
    """``marcar_como_convertido`` MUST NOT touch the ``origen`` field.

    Spec — ``prospecto-origen`` › "write-once prospect origin".
    Conversion is metadata-only, not a state-machine input; the field
    was tagged on creation and the lifecycle method cannot silently
    re-tag the prospect when the admin converts it into a Cliente.
    """

    def test_marcar_como_convertido_preserves_recurrente(self):
        """``marcar_como_convertido`` keeps ``RECURRENTE_PRE_SISTEMA`` intact."""
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Convertir",
            apellido_paterno="Recurrente",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
            origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )

        cliente_user = Usuario.objects.create_user(
            username="prospecto_origen.cliente1",
            password="pw12345!",
            primer_nombre="Convertir",
            apellido_paterno="Recurrente",
            email="convertir@example.com",
            rol=g["rol_cliente"],
            sucursal=g["sucursal"],
        )
        cliente = Cliente.objects.create(
            usuario=cliente_user,
            sucursal_origen=g["sucursal"],
            fecha_nacimiento="1990-01-01",
        )

        prospecto.marcar_como_convertido(cliente)
        prospecto.refresh_from_db()

        self.assertEqual(prospecto.estado, Prospecto.Estado.CONVERTIDO)
        self.assertEqual(
            prospecto.origen,
            Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
            "marcar_como_convertido must not change the prospect origen",
        )

    def test_marcar_como_convertido_preserves_nuevo(self):
        """``marcar_como_convertido`` keeps the ``NUEVO`` default intact."""
        g = _build_graph()
        prospecto = Prospecto.objects.create(
            primer_nombre="Convertir",
            apellido_paterno="Nuevo",
            registrado_por=g["admin"],
            sucursal_registro=g["sucursal"],
        )
        # Sanity: default lands on ``NUEVO``.
        self.assertEqual(prospecto.origen, Prospecto.Origen.NUEVO)

        cliente_user = Usuario.objects.create_user(
            username="prospecto_origen.cliente2",
            password="pw12345!",
            primer_nombre="Convertir",
            apellido_paterno="Nuevo",
            email="convertir2@example.com",
            rol=g["rol_cliente"],
            sucursal=g["sucursal"],
        )
        cliente = Cliente.objects.create(
            usuario=cliente_user,
            sucursal_origen=g["sucursal"],
            fecha_nacimiento="1990-01-01",
        )

        prospecto.marcar_como_convertido(cliente)
        prospecto.refresh_from_db()

        self.assertEqual(
            prospecto.origen,
            Prospecto.Origen.NUEVO,
            "marcar_como_convertido must not change the prospect origen",
        )


# ---------------------------------------------------------------------------
# Class D — ``admin_crear_prospecto`` accepts / validates ``origen``
# ---------------------------------------------------------------------------


class AdminCrearProspectoOrigenTests(TestCase):
    """``POST /api/admin/prospectos/crear/`` honors the ``origen`` contract.

    Spec — ``prospecto-origen`` › "creation-time origin selection in
    admin UI" and "origen field semantics" › "New Prospecto created
    with each value" / "Unknown origin value rejected on creation".
    """

    @classmethod
    def setUpTestData(cls):
        cls.g = _build_graph()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.g["admin"])

    def _base_payload(self, **overrides):
        payload = {
            "primerNombre": "Ana",
            "apellidoPaterno": "Prueba",
            "estado": "PASAJERO",
        }
        payload.update(overrides)
        return payload

    def test_create_with_recurrente_persists(self):
        """Payload carrying ``RECURRENTE_PRE_SISTEMA`` stores the value."""
        response = self.http.post(
            "/api/admin/prospectos/crear/",
            data=json.dumps(
                self._base_payload(origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA)
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        prospect = Prospecto.objects.get()
        self.assertEqual(
            prospect.origen,
            Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )

    def test_create_with_nuevo_persists(self):
        """Payload carrying ``NUEVO`` stores the value explicitly."""
        response = self.http.post(
            "/api/admin/prospectos/crear/",
            data=json.dumps(self._base_payload(origen=Prospecto.Origen.NUEVO)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        prospect = Prospecto.objects.get()
        self.assertEqual(prospect.origen, Prospecto.Origen.NUEVO)

    def test_create_without_origen_defaults_to_nuevo(self):
        """Omitting ``origen`` defaults to ``NUEVO`` per the spec."""
        response = self.http.post(
            "/api/admin/prospectos/crear/",
            data=json.dumps(self._base_payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        prospect = Prospecto.objects.get()
        self.assertEqual(prospect.origen, Prospecto.Origen.NUEVO)

    def test_unknown_origen_returns_400_and_no_row_inserted(self):
        """Unknown ``origen`` value is rejected with 400 and zero rows."""
        before = Prospecto.objects.count()
        response = self.http.post(
            "/api/admin/prospectos/crear/",
            data=json.dumps(self._base_payload(origen="ALGOTRO")),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("origen", json.dumps(body))
        self.assertEqual(
            Prospecto.objects.count(),
            before,
            "no Prospecto row must be inserted when origen is rejected",
        )


# ---------------------------------------------------------------------------
# Class E — prospect conversion finalize propagates ``Prospecto.origen``
# ---------------------------------------------------------------------------


class ProspectFinalizeOrigenTests(TestCase):
    """``admin_prospect_conversion_finalize`` copies ``Prospecto.origen``.

    Spec — ``admin-prospect-conversion › Finalize Dispatcher Per Mode``
    and ``prospecto-origen › propagation at prospect finalize``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "ficha.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return self.http.post(
            f"/api/admin/prospectos/{draft.prospecto_id}/conversion/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def test_recurrente_prospect_produces_recurrente_cliente(self):
        """A ``RECURRENTE_PRE_SISTEMA`` prospect yields a matching ``Cliente``."""
        prospecto = Prospecto.objects.create(
            primer_nombre="Ana",
            apellido_paterno="Recurrente",
            telefono="7000-1111",
            sucursal_registro=self.graph["sucursal"],
            registrado_por=self.graph["admin"],
            origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )
        draft = _make_prospect_draft(
            prospecto=prospecto,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente = Cliente.objects.get(usuario__username=f"prospecto_origen.{prospecto.pk}")
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
            "Cliente.origen MUST equal the source Prospecto.origen",
        )

    def test_nuevo_prospect_produces_nuevo_cliente(self):
        """A ``NUEVO`` prospect yields a matching ``NUEVO`` cliente."""
        prospecto = Prospecto.objects.create(
            primer_nombre="Jose",
            apellido_paterno="Nuevo",
            telefono="7000-2222",
            sucursal_registro=self.graph["sucursal"],
            registrado_por=self.graph["admin"],
        )
        # Sanity: model default lands on ``NUEVO``.
        self.assertEqual(prospecto.origen, Prospecto.Origen.NUEVO)

        draft = _make_prospect_draft(
            prospecto=prospecto,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente = Cliente.objects.get(usuario__username=f"prospecto_origen.{prospecto.pk}")
        self.assertEqual(cliente.origen, Cliente.Origen.NUEVO)

    def test_prospect_branch_ignores_draft_origen_field(self):
        """The prospect branch MUST NOT fall back to ``datos_usuario.origen``.

        Even when the draft's user payload carries a conflicting ``origen``
        value, the source ``Prospecto.origen`` is the sole source of
        truth for the new ``Cliente``.
        """
        prospecto = Prospecto.objects.create(
            primer_nombre="Con",
            apellido_paterno="Flicto",
            telefono="7000-3333",
            sucursal_registro=self.graph["sucursal"],
            registrado_por=self.graph["admin"],
            origen=Prospecto.Origen.RECURRENTE_PRE_SISTEMA,
        )
        draft = _make_prospect_draft(
            prospecto=prospecto,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            origen=Cliente.Origen.NUEVO,  # conflicting value on the draft
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente = Cliente.objects.get(usuario__username=f"prospecto_origen.{prospecto.pk}")
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
            "draft's datos_usuario.origen MUST NOT override Prospecto.origen",
        )


# ---------------------------------------------------------------------------
# Class F — reactivation finalize never overwrites ``Cliente.origen``
# ---------------------------------------------------------------------------


class ReactivationFinalizeOrigenTests(TestCase):
    """``mode='reactivation'`` finalize MUST leave ``Cliente.origen`` alone.

    Spec — ``admin-prospect-conversion › prospect origin non-overwrite
    contract`` and ``prospecto-origen › reactivation non-overwrite
    guarantee``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.graph = _build_graph()
        cls.today = date.today()

    def setUp(self):
        self.http = Client()
        self.http.force_login(self.graph["admin"])

    def _finalize(self, draft):
        pdf = SimpleUploadedFile(
            "ficha.pdf", b"%PDF-1.4 fake", content_type="application/pdf"
        )
        return self.http.post(
            f"/api/admin/clientes/{draft.cliente_id}/reactivar/finalizar/",
            data={"documento_escaneado_pdf": pdf},
        )

    def _build_cliente(self, *, origen):
        """Build a ``Cliente`` carrying ``origen``."""
        user = Usuario.objects.create_user(
            username=f"reactivar.{origen.lower()}",
            password="pw12345!",
            primer_nombre="React",
            apellido_paterno=origen.title(),
            email=f"reactivar.{origen.lower()}@example.com",
            rol=self.graph["rol_cliente"],
            sucursal=self.graph["sucursal"],
        )
        return Cliente.objects.create(
            usuario=user,
            sucursal_origen=self.graph["sucursal"],
            fecha_nacimiento=date(1990, 1, 1),
            origen=origen,
        )

    def test_reactivation_keeps_nuevo_unchanged(self):
        """A draft carrying a different ``origen`` MUST NOT change the live row."""
        cliente = self._build_cliente(origen=Cliente.Origen.NUEVO)
        draft = _make_reactivation_draft(
            cliente=cliente,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            origen=Cliente.Origen.RECURRENTE_PRE_SISTEMA,  # conflicting draft value
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente.refresh_from_db()
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.NUEVO,
            "reactivation finalize MUST NOT touch Cliente.origen",
        )

    def test_reactivation_keeps_recurrente_unchanged(self):
        """A draft carrying ``NUEVO`` MUST NOT change a recurrente row."""
        cliente = self._build_cliente(origen=Cliente.Origen.RECURRENTE_PRE_SISTEMA)
        draft = _make_reactivation_draft(
            cliente=cliente,
            admin=self.graph["admin"],
            servicio=self.graph["servicio"],
            catalog_ids=self.graph["catalog_ids"],
            today=self.today,
            origen=Cliente.Origen.NUEVO,
        )

        with override_settings(BIOMETRIC_SUSPENDED=True):
            response = self._finalize(draft)

        self.assertEqual(response.status_code, 201, response.content)
        cliente.refresh_from_db()
        self.assertEqual(
            cliente.origen,
            Cliente.Origen.RECURRENTE_PRE_SISTEMA,
        )
