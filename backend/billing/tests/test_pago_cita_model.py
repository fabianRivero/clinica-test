"""Tests for ``PagoCita`` model rules.

Exercises the same patterns as ``test_pago_realizado_clean`` but for the
new sibling table:

* XOR — exactly one of ``cita_medica`` / ``cita_cliente_libre`` must
  be set. Enforced in ``clean()`` AND as a DB-level ``CheckConstraint``;
  the model-layer rule surfaces in the form-validation path, the DB
  rule is the safety net for bulk imports.
* VIRTUAL / FISICO / MIXTO amount rules are delegated to the shared
  ``_validate_metodo_pago_amounts`` helper, so these tests double as a
  contract test for that helper.
* Receipt upload lands under ``comprobantes_citas/YYYY/MM/`` — never
  under ``comprobantes_pagos/`` (the cuota path). The test exercises
  ``save()`` so the storage layer is hit.

Tests skip ``save()`` and call ``clean()`` directly for the rule-level
checks (mirrors ``PagoRealizadoCleanTests``) and use ``save()`` only for
the receipt-path integration check.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import PagoCita
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente, Prospecto
from operations.models import CitaClienteLibre, CitaMedica, CitaProspecto, Operacion


def _build_graph():
    """Return the minimum fixture graph for ``PagoCita`` tests.

    Both cita kinds get their own branch so we can verify that the XOR
    rule is enforced on the cita-side FK regardless of branch.
    """
    branch = Sucursal.objects.create(nombre="Sucursal Test", activa=True)
    branch_libre = Sucursal.objects.create(
        nombre="Sucursal Libre", activa=True
    )

    rol = Rol.objects.create(rol="ADMIN_SUCURSAL")
    admin = Usuario.objects.create_user(
        username="admin.test",
        password="password123",
        rol=rol,
        sucursal=branch,
    )

    tipo = TipoServicio.objects.create(tipo="Consulta")
    proc_tipo = ProcEsteticosTipo.objects.create(tipo="General")
    proc = ProcEstetico.objects.create(
        tipo_p_estetico=proc_tipo, proceso="Consulta"
    )
    service_with_proc = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=proc,
        precio_base=Decimal("200.00"),
    )
    service_free = ServicioConfig.objects.create(
        tipo_servicio=tipo,
        proc_estetico=None,
        precio_base=Decimal("180.00"),
    )

    cliente_user = Usuario.objects.create_user(
        username="paciente.test",
        password="password123",
    )
    cliente_user.sucursal = branch
    cliente_user.save()
    cliente = Cliente.objects.create(
        usuario=cliente_user,
        sucursal_origen=branch,
        fecha_nacimiento=timezone.localdate().replace(
            year=timezone.localdate().year - 30
        ),
        estado_cliente=Cliente.Estado.ACTIVO,
    )
    operacion = Operacion.objects.create(
        paciente=cliente,
        servicio_config=service_with_proc,
        precio_total=Decimal("200.00"),
        cuotas_totales=1,
        sesiones_totales=1,
        estado=Operacion.Estado.EN_PROCESO,
    )

    cita_medica = CitaMedica.objects.create(
        operacion=operacion,
        sucursal=branch,
        fecha_hora=datetime(2026, 9, 1, 10, 0, tzinfo=dt_timezone.utc),
        estado=CitaMedica.Estado.PROGRAMADA,
        precio=Decimal("200.00"),
    )
    cita_libre = CitaClienteLibre.objects.create(
        cliente=cliente,
        servicio_config=service_free,
        sucursal=branch_libre,
        fecha_hora=datetime(2026, 9, 2, 11, 0, tzinfo=dt_timezone.utc),
        estado=CitaClienteLibre.Estado.PROGRAMADA,
        precio=Decimal("180.00"),
    )

    # Prospecto + CitaProspecto for the 3-way XOR tests. Uses
    # ``service_free`` (no proc_estetico) so it matches the
    # CitaProspecto.clean() rule ``proc_estetico must be null``.
    prospecto = Prospecto.objects.create(
        primer_nombre="Prospecto",
        apellido_paterno="Test",
        telefono="70000000",
        estado=Prospecto.Estado.PASAJERO,
        sucursal_registro=branch,
    )
    cita_prospecto = CitaProspecto.objects.create(
        prospecto=prospecto,
        servicio_config=service_free,
        sucursal=branch,
        fecha_hora=datetime(2026, 9, 3, 12, 0, tzinfo=dt_timezone.utc),
        estado=CitaProspecto.Estado.PROGRAMADA,
        precio=Decimal("150.00"),
    )
    return {
        "branch": branch,
        "branch_libre": branch_libre,
        "admin": admin,
        "cliente": cliente,
        "operacion": operacion,
        "service_free": service_free,
        "cita_medica": cita_medica,
        "cita_libre": cita_libre,
        "prospecto": prospecto,
        "cita_prospecto": cita_prospecto,
    }


class PagoCitaModelTests(TestCase):
    """Unit + light integration tests for ``PagoCita`` model rules."""

    @staticmethod
    def _receipt(name="receipt.pdf"):
        return SimpleUploadedFile(
            name, b"%PDF-test", content_type="application/pdf"
        )

    def setUp(self):
        self.g = _build_graph()

    # -------------------------------------------------------------------------
    # XOR rule
    # -------------------------------------------------------------------------

    def test_clean_xor_requires_exactly_one_cita_fk(self):
        # Both FKs set → fail.
        both = PagoCita(
            cita_medica=self.g["cita_medica"],
            cita_cliente_libre=self.g["cita_libre"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            both.clean()
        self.assertIn("__all__", ctx.exception.message_dict)

        # Neither FK set → fail.
        neither = PagoCita(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            neither.clean()
        self.assertIn("__all__", ctx.exception.message_dict)

    def test_clean_xor_passes_when_only_cita_medica_set(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
        )
        payment.clean()  # must not raise

    def test_clean_xor_passes_when_only_cita_cliente_libre_set(self):
        payment = PagoCita(
            cita_cliente_libre=self.g["cita_libre"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
        )
        payment.clean()  # must not raise

    # -------------------------------------------------------------------------
    # VIRTUAL branch (receipt optional for admin, amount match required)
    # -------------------------------------------------------------------------

    def test_clean_virtual_receipt_is_optional(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="",
        )
        payment.clean()  # must not raise

    def test_clean_virtual_requires_amount_match(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("80.00"),
            monto_fisico=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_virtual", ctx.exception.message_dict)

    def test_clean_virtual_rejects_nonzero_fisico(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("5.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_fisico", ctx.exception.message_dict)

    # -------------------------------------------------------------------------
    # FISICO branch
    # -------------------------------------------------------------------------

    def test_clean_fisico_receipt_is_optional(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
        )
        payment.clean()  # must not raise

    def test_clean_fisico_requires_amount_match(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("80.00"),
            monto_virtual=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_fisico", ctx.exception.message_dict)

    def test_clean_fisico_rejects_nonzero_virtual(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("5.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_virtual", ctx.exception.message_dict)

    # -------------------------------------------------------------------------
    # MIXTO branch
    # -------------------------------------------------------------------------

    def test_clean_mixto_requires_both_positive(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.MIXTO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_pagado", ctx.exception.message_dict)

    def test_clean_mixto_requires_sum_match(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.MIXTO,
            monto_fisico=Decimal("40.00"),
            monto_virtual=Decimal("50.00"),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_pagado", ctx.exception.message_dict)

    def test_clean_mixto_with_valid_breakdown_passes(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.MIXTO,
            monto_fisico=Decimal("40.00"),
            monto_virtual=Decimal("60.00"),
        )
        payment.clean()  # must not raise

    # -------------------------------------------------------------------------
    # Receipt upload path (integration: save() round-trip)
    # -------------------------------------------------------------------------

    def test_receipt_uploads_to_comprobantes_citas_path(self):
        payment = PagoCita(
            cita_medica=self.g["cita_medica"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            comprobante_url=self._receipt(),
        )
        # Bypass the FK signal chain by calling save() directly — the
        # test is about the upload_to path, not the cross-row cascade.
        payment.save()
        try:
            self.assertTrue(bool(payment.comprobante_url))
            stored_name = payment.comprobante_url.name
            self.assertTrue(
                stored_name.startswith("comprobantes_citas/"),
                f"expected comprobantes_citas/ prefix, got {stored_name!r}",
            )
            self.assertNotIn(
                "comprobantes_pagos/",
                stored_name,
                "PagoCita must not use the cuota receipt path",
            )
            # Path layout: comprobantes_citas/YYYY/MM/<file>.
            parts = stored_name.split("/")
            self.assertEqual(parts[0], "comprobantes_citas")
            self.assertEqual(len(parts[1]), 4)  # YYYY
            self.assertEqual(len(parts[2]), 2)  # MM
        finally:
            payment.delete()


class PagoCitaProspectoTests(TestCase):
    """Cover the 3-way XOR introduced by the CitaProspecto follow-on.

    ``PagoCita`` now accepts exactly one of three cita FKs. These tests
    lock the contract so future refactors can't silently regress the
    prospect cobro surface.
    """

    def setUp(self):
        self.g = _build_graph()

    def test_clean_xor_passes_with_only_cita_prospecto_set(self):
        payment = PagoCita(
            cita_prospecto=self.g["cita_prospecto"],
            monto_pagado=Decimal("150.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("150.00"),
            monto_virtual=Decimal("0"),
        )
        payment.clean()  # must not raise

    def test_clean_xor_rejects_cita_prospecto_alongside_cita_medica(self):
        both = PagoCita(
            cita_medica=self.g["cita_medica"],
            cita_prospecto=self.g["cita_prospecto"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            both.clean()
        self.assertIn("__all__", ctx.exception.message_dict)

    def test_clean_xor_rejects_cita_prospecto_alongside_cita_cliente_libre(self):
        both = PagoCita(
            cita_cliente_libre=self.g["cita_libre"],
            cita_prospecto=self.g["cita_prospecto"],
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
        )
        with self.assertRaises(ValidationError) as ctx:
            both.clean()
        self.assertIn("__all__", ctx.exception.message_dict)

    def test_save_persists_cita_prospecto_and_satisfies_db_constraint(self):
        payment = PagoCita(
            cita_prospecto=self.g["cita_prospecto"],
            monto_pagado=Decimal("150.00"),
            metodo_pago=PagoCita.MetodoPago.FISICO,
            monto_fisico=Decimal("150.00"),
            monto_virtual=Decimal("0"),
        )
        payment.save()
        try:
            self.assertEqual(payment.cita_prospecto_id, self.g["cita_prospecto"].pk)
            # The reverse manager on CitaProspecto is ``pagos_cita`` —
            # confirms the over-payment helper will pick up this row.
            self.assertIn(payment, self.g["cita_prospecto"].pagos_cita.all())
        finally:
            payment.delete()