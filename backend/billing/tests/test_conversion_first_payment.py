"""Tests for the optional first-payment block of the conversion /
reactivation finalize view (``admin_prospect_conversion_finalize``).

The view services two routes — prospect conversion and client
reactivation — so we cover the payment branch through the
reactivation flow (which is simpler to set up). The branch covers:

* ``VIRTUAL`` + receipt → APROBADO ``PagoRealizado`` with
  ``monto_virtual == monto_pagado`` and ``monto_fisico == 0``.
* ``FISICO`` without receipt → APROBADO row with
  ``monto_fisico == monto_pagado`` and ``monto_virtual == 0``.
  Confirms comprobante is optional at the view layer.
* ``MIXTO`` with a valid breakdown → APROBADO row with both sides
  populated and ``monto_fisico + monto_virtual == monto_pagado``.
* ``MIXTO`` with a mismatched breakdown → 400 from the model's
  ``clean()`` (sums do not match).
* ``VIRTUAL`` without receipt → 400 from the model's ``clean()``
  (``metodo_pago == VIRTUAL`` requires ``comprobante_url``).
* Over-payment: cuota already covered by an APROBADO row → 400 from
  ``assert_not_over_payment``; no new row, conversion rolled back.
* No payment when only ``primerPagoDetalle`` is sent (no amount, no
  receipt) — helper exits silently and no ``PagoRealizado`` row is
  created.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.hashers import make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    GradoDeshidratacion,
    GrosorPiel,
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from customers.models import Cliente, ProspectoConversionBorrador
from operations.models import Operacion


def _make_full_draft(*, cliente, usuario, servicio, today, catalog_ids):
    """Build a draft ready for the conversion finalize view."""
    return ProspectoConversionBorrador.objects.create(
        cliente=cliente,
        prospecto=None,
        iniciado_por=usuario,
        datos_usuario={
            "primerNombre": cliente.usuario.primer_nombre,
            "apellidoPaterno": cliente.usuario.apellido_paterno,
            "username": cliente.usuario.username,
            "passwordHash": make_password("pw"),
            "fechaNacimiento": "1990-01-01",
            "ci": "12345",
        },
        datos_operacion={
            "serviceConfigId": servicio.id,
            "zonaGeneral": "Zona",
            "zonaEspecifica": "Detalle",
            "precioTotal": "100.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(today),
            "estado": Operacion.Estado.EN_PROCESO,
            "fechasVencimientoCuotas": [str(today)],
        },
        datos_ficha={
            "fechaFicha": str(today),
            "motivoConsulta": "consulta",
            "observaciones": "",
            "consentimientoAceptado": True,
            "firmaPacienteCi": "12345",
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
        datos_biometria={"provider": "MOCK", "template": "BASE64", "quality": 80},
        paso_usuario_completado=True,
        paso_operacion_completado=True,
        paso_ficha_completado=True,
        paso_biometria_completado=True,
        paso_actual=ProspectoConversionBorrador.Paso.BIOMETRIA,
    )


def _finalize_url(cliente_id):
    return f"/api/admin/clientes/{cliente_id}/reactivar/finalizar/"


class _ConversionFirstPaymentGraph:
    """Build the minimum role/branch/user/cliente graph the view needs."""

    @staticmethod
    def build():
        rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        rol_cliente = Rol.objects.create(rol="CLIENTE")
        sucursal = Sucursal.objects.create(nombre="Conversion-Centro", activa=True)
        admin = Usuario.objects.create_user(
            username="conv.admin",
            password="pw12345!",
            primer_nombre="Adm",
            apellido_paterno="Pri",
            rol=rol_admin,
            sucursal=sucursal,
        )
        client_user = Usuario.objects.create_user(
            username="conv.cliente",
            password="pw12345!",
            primer_nombre="Cli",
            apellido_paterno="Ente",
            rol=rol_cliente,
            sucursal=sucursal,
        )
        cliente = Cliente.objects.create(
            usuario=client_user,
            sucursal_origen=sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )
        tipo = TipoServicio.objects.create(tipo="Consulta", activo=True)
        servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo, precio_base=Decimal("100"), activo=True
        )
        return {
            "rol_admin": rol_admin,
            "rol_cliente": rol_cliente,
            "sucursal": sucursal,
            "admin": admin,
            "cliente": cliente,
            "servicio": servicio,
        }


class ConversionFirstPaymentTests(TestCase):
    """End-to-end coverage of the first-payment block in finalize."""

    def setUp(self):
        self.http = Client()
        graph = _ConversionFirstPaymentGraph.build()
        self.admin = graph["admin"]
        self.cliente = graph["cliente"]
        self.servicio = graph["servicio"]
        self.today = date.today()
        # Medical catalogs are reused across multiple drafts within a
        # single test (the over-payment test creates two drafts); create
        # them once at the class level instead of inside _make_full_draft.
        self.catalog_ids = {
            "tipo_piel": TipoPiel.objects.create(nombre="Normal", activo=True).id,
            "grado_deshidratacion": GradoDeshidratacion.objects.create(
                nombre="Bajo", activo=True
            ).id,
            "grosor_piel": GrosorPiel.objects.create(nombre="Medio", activo=True).id,
        }

    def _login(self):
        self.http.force_login(self.admin)

    def _post_finalize(self, draft, **extra_fields):
        pdf = SimpleUploadedFile("doc.pdf", b"%PDF-1.4 fake", content_type="application/pdf")
        data = {"documento_escaneado_pdf": pdf}
        data.update(extra_fields)
        return self.http.post(_finalize_url(self.cliente.id), data=data)

    # ------------------------- Happy paths -------------------------

    def test_virtual_with_receipt_creates_aprobado_pago(self):
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        receipt = SimpleUploadedFile(
            "receipt.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="VIRTUAL",
            primerPagoMonto="100.00",
            primerPagoMontoVirtual="100.00",
            primerPagoComprobante=receipt,
        )
        self.assertEqual(response.status_code, 201)
        pagos = PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente)
        self.assertEqual(pagos.count(), 1)
        pago = pagos.first()
        self.assertEqual(pago.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        self.assertEqual(pago.monto_pagado, Decimal("100.00"))
        self.assertEqual(pago.monto_virtual, Decimal("100.00"))
        self.assertEqual(pago.monto_fisico, Decimal("0"))
        self.assertEqual(
            pago.estado_verificacion, PagoRealizado.EstadoVerificacion.APROBADO
        )
        self.assertEqual(pago.verificado_por_id, self.admin.id)
        self.assertIsNotNone(pago.fecha_verificacion)
        self.assertTrue(bool(pago.comprobante_url))

    def test_fisico_without_receipt_is_optional_and_creates_pago(self):
        """Comprobante must be optional: a FISICO payment with no file
        still creates an APROBADO row (the model's clean() allows it)."""
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMonto="60.00",
            primerPagoMontoFisico="60.00",
        )
        self.assertEqual(response.status_code, 201)
        pago = PagoRealizado.objects.get(cuota__operacion__paciente=self.cliente)
        self.assertEqual(pago.metodo_pago, PagoRealizado.MetodoPago.FISICO)
        self.assertEqual(pago.monto_pagado, Decimal("60.00"))
        self.assertEqual(pago.monto_fisico, Decimal("60.00"))
        self.assertEqual(pago.monto_virtual, Decimal("0"))
        self.assertFalse(bool(pago.comprobante_url))

    def test_mixto_with_valid_breakdown_creates_pago(self):
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        receipt = SimpleUploadedFile(
            "receipt.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="MIXTO",
            primerPagoMonto="100.00",
            primerPagoMontoFisico="60.00",
            primerPagoMontoVirtual="40.00",
            primerPagoComprobante=receipt,
        )
        self.assertEqual(response.status_code, 201)
        pago = PagoRealizado.objects.get(cuota__operacion__paciente=self.cliente)
        self.assertEqual(pago.metodo_pago, PagoRealizado.MetodoPago.MIXTO)
        self.assertEqual(pago.monto_pagado, Decimal("100.00"))
        self.assertEqual(pago.monto_fisico, Decimal("60.00"))
        self.assertEqual(pago.monto_virtual, Decimal("40.00"))

    # ------------------------- Error paths -------------------------

    def test_mixto_with_mismatched_breakdown_returns_400(self):
        """When the breakdown doesn't sum to ``monto_pagado`` the model's
        ``clean()`` raises; the view surfaces it as 400."""
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="MIXTO",
            primerPagoMonto="100.00",
            primerPagoMontoFisico="60.00",
            primerPagoMontoVirtual="30.00",  # 60 + 30 != 100
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())
        # No row was created.
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente).exists()
        )
        # The whole conversion rolled back: no cliente state change, no borrador.
        self.cliente.refresh_from_db()
        self.assertTrue(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    def test_virtual_without_receipt_returns_400_from_model_clean(self):
        """VIRTUAL without a receipt must hit ``PagoRealizado.clean`` and
        come back as 400 — comprobante is optional at the view layer but
        the model still requires it for VIRTUAL payments."""
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="VIRTUAL",
            primerPagoMonto="100.00",
            primerPagoMontoVirtual="100.00",
            # No primerPagoComprobante
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente).exists()
        )

    def test_over_payment_returns_400_from_helper(self):
        """When the cuota is already fully covered, ``assert_not_over_payment``
        raises; the helper surfaces it and no new row is created.

        Drives the helper directly because the view creates the cuota
        during finalize, so we cannot pre-populate it via finalize
        itself. The over-payment path is the same code branch the view
        uses; only the calling context differs.
        """
        operacion = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            precio_total=Decimal("100"),
            sesiones_totales=1,
            estado=Operacion.Estado.EN_PROCESO,
        )
        cuota = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=self.today,
            monto_programado=Decimal("100.00"),
        )
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado_por=self.admin,
            fecha_verificacion=__import__("django.utils.timezone", fromlist=["now"]).now(),
        )

        from config.prospect_conversion_views import (
            _register_first_payment_from_request,
        )
        from rest_framework.exceptions import ValidationError as DRFValidationError

        class FakeRequest:
            POST = {
                "primerPagoMetodo": "FISICO",
                "primerPagoMonto": "100.00",
                "primerPagoMontoFisico": "100.00",
            }
            FILES = {}

        with self.assertRaises(DRFValidationError) as ctx:
            _register_first_payment_from_request(FakeRequest(), operacion)
        self.assertIn("El pago supera el saldo pendiente de la cuota.", str(ctx.exception))
        # The new row was not created.
        self.assertEqual(cuota.pagos_realizados.count(), 1)

    def test_no_cuotas_totales_with_first_payment_creates_cuota_and_pago(self):
        """When the admin skips step 2 (no cuotasTotales, no due dates)
        but registers a first payment in step 5, the finalize view must
        auto-create a single ``CuotaPlanPago`` so the payment has
        somewhere to land. The cuota's monto_programado is set to the
        residual balance (``precioTotal - pago``), so partial payments
        leave the cuota covering exactly the saldo pendiente and full
        payments collapse the cuota to ``pago``. Without this fallback
        the operation would render as "0 cuota(s)" in
        /cms/operaciones/<id> and the payment would be silently dropped.
        """
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        # Override the draft to mirror "admin skipped step 2 cuotas".
        draft.datos_operacion["cuotasTotales"] = None
        draft.datos_operacion["fechasVencimientoCuotas"] = []
        draft.save(update_fields=["datos_operacion"])
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMontoFisico="100.00",
            primerPagoDetalle="Pago en consultorio.",
        )
        self.assertEqual(response.status_code, 201)
        operacion = Operacion.objects.get(paciente=self.cliente)
        cuotas = CuotaPlanPago.objects.filter(operacion=operacion)
        self.assertEqual(cuotas.count(), 1)
        self.assertEqual(cuotas.first().monto_programado, Decimal("100.00"))
        self.assertEqual(
            PagoRealizado.objects.filter(cuota__operacion=operacion).count(), 1
        )

    def test_no_cuotas_totales_partial_first_payment_creates_cuota_with_saldo(self):
        """When the admin skips step 2 and registers a partial first
        payment in step 5, the auto-created cuota reflects exactly the
        paid amount and resolves to PAGADO immediately. The admin can
        later add additional cuotas for the residual balance via
        /cms/operaciones/<id>.
        """
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        draft.datos_operacion["cuotasTotales"] = None
        draft.datos_operacion["fechasVencimientoCuotas"] = []
        draft.save(update_fields=["datos_operacion"])
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="MIXTO",
            primerPagoMontoFisico="20.00",
            primerPagoMontoVirtual="10.00",
        )
        self.assertEqual(response.status_code, 201)
        operacion = Operacion.objects.get(paciente=self.cliente)
        cuotas = CuotaPlanPago.objects.filter(operacion=operacion)
        self.assertEqual(cuotas.count(), 1)
        # Cuota mirrors the paid amount, not the full precio_total.
        self.assertEqual(cuotas.first().monto_programado, Decimal("30.00"))
        self.assertEqual(cuotas.first().estado, CuotaPlanPago.Estado.PAGADO)
        pago = PagoRealizado.objects.get(cuota=cuotas.first())
        self.assertEqual(pago.monto_pagado, Decimal("30.00"))

    def test_no_payment_when_no_amount_signal_and_no_receipt(self):
        """When only ``primerPagoDetalle`` is sent (no amount, no receipt)
        the helper should silently skip and no ``PagoRealizado`` row is
        created."""
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoDetalle="Solo una nota, sin pago.",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente).exists()
        )

    def test_invalid_payment_method_returns_400(self):
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="INVALID_METHOD",
            primerPagoMonto="100.00",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("detail", response.json())
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente).exists()
        )

    # ------------------------- Rebalance: Path A (fecha coincide) ----------

    def test_rebalance_path_a_fecha_coincide_reemplaza_cuota(self):
        """When ``fecha_pago`` matches the ``fecha_vencimiento`` of an
        existing cuota, that cuota absorbs the paid amount and the other
        cuotas keep their nro/fecha but get their ``monto_programado``
        re-scaled so the totals still match ``precioTotal``.

        Scenario: 700 total, 2 cuotas on self.today and today+9 days.
        The admin pays 400 today. Expected:

          * cuota 1 (self.today) → monto_programado = 400 (paid today).
          * cuota 2 (today+9)   → monto_programado = 300 (700 − 400).

        Both totals add up to 700; the second cuota absorbs the saldo
        restante so the plan still reflects the full price.
        """
        future = date.fromordinal(self.today.toordinal() + 9)
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        draft.datos_operacion["precioTotal"] = "700.00"
        draft.datos_operacion["cuotasTotales"] = 2
        draft.datos_operacion["fechasVencimientoCuotas"] = [
            str(self.today),
            str(future),
        ]
        draft.save(update_fields=["datos_operacion"])
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMonto="400.00",
            primerPagoMontoFisico="400.00",
        )
        self.assertEqual(response.status_code, 201)
        operacion = Operacion.objects.get(paciente=self.cliente)
        cuotas = list(
            CuotaPlanPago.objects.filter(operacion=operacion).order_by("nro_cuota")
        )
        self.assertEqual(len(cuotas), 2)
        # Cuota 1 keeps its fecha_vencimiento and nro_cuota, monto = pago.
        self.assertEqual(cuotas[0].nro_cuota, 1)
        self.assertEqual(cuotas[0].fecha_vencimiento, self.today)
        self.assertEqual(cuotas[0].monto_programado, Decimal("400.00"))
        self.assertEqual(cuotas[0].estado, CuotaPlanPago.Estado.PAGADO)
        # Cuota 2 absorbs the saldo restante and keeps its fecha_vencimiento.
        self.assertEqual(cuotas[1].nro_cuota, 2)
        self.assertEqual(cuotas[1].fecha_vencimiento, future)
        self.assertEqual(cuotas[1].monto_programado, Decimal("300.00"))
        self.assertEqual(cuotas[1].estado, CuotaPlanPago.Estado.PENDIENTE)
        # PagoRealizado lands on cuota 1.
        pago = PagoRealizado.objects.get(cuota=cuotas[0])
        self.assertEqual(pago.monto_pagado, Decimal("400.00"))

    # ------------------------- Rebalance: Path B (fecha no coincide) ------

    def test_rebalance_path_b_fecha_no_coincide_inserta_cuota(self):
        """When ``fecha_pago`` does NOT match any existing cuota's
        ``fecha_vencimiento``, a new cuota #1 is inserted with that
        fecha and the original cuotas are renumbered 2..N+1 with their
        ``monto_programado`` re-scaled.

        Scenario: 700 total, 2 cuotas on today+4 and today+9 days.
        The admin pays 400 today. Expected:

          * New cuota #1 (self.today) → monto_programado = 400 (paid).
          * Original cuota (today+4)  → renumbered to 2, monto = 150.
          * Original cuota (today+9)  → renumbered to 3, monto = 150.

        Totals: 400 + 150 + 150 = 700.
        """
        d1 = date.fromordinal(self.today.toordinal() + 4)
        d2 = date.fromordinal(self.today.toordinal() + 9)
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        draft.datos_operacion["precioTotal"] = "700.00"
        draft.datos_operacion["cuotasTotales"] = 2
        draft.datos_operacion["fechasVencimientoCuotas"] = [
            str(d1),
            str(d2),
        ]
        draft.save(update_fields=["datos_operacion"])
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMonto="400.00",
            primerPagoMontoFisico="400.00",
        )
        self.assertEqual(response.status_code, 201)
        operacion = Operacion.objects.get(paciente=self.cliente)
        cuotas = list(
            CuotaPlanPago.objects.filter(operacion=operacion).order_by("nro_cuota")
        )
        self.assertEqual(len(cuotas), 3)
        # New cuota #1 holds the paid amount on today's date.
        self.assertEqual(cuotas[0].nro_cuota, 1)
        self.assertEqual(cuotas[0].fecha_vencimiento, self.today)
        self.assertEqual(cuotas[0].monto_programado, Decimal("400.00"))
        self.assertEqual(cuotas[0].estado, CuotaPlanPago.Estado.PAGADO)
        # Originals renumbered to 2, 3 with equal split of the saldo.
        self.assertEqual(cuotas[1].nro_cuota, 2)
        self.assertEqual(cuotas[1].fecha_vencimiento, d1)
        self.assertEqual(cuotas[1].monto_programado, Decimal("150.00"))
        self.assertEqual(cuotas[2].nro_cuota, 3)
        self.assertEqual(cuotas[2].fecha_vencimiento, d2)
        self.assertEqual(cuotas[2].monto_programado, Decimal("150.00"))
        # PagoRealizado lands on the new cuota #1.
        pago = PagoRealizado.objects.get(cuota=cuotas[0])
        self.assertEqual(pago.monto_pagado, Decimal("400.00"))

    # ------------------------- Rebalance: hard cap -----------------------

    def test_rebalance_blocks_payment_greater_than_precio_total(self):
        """The first payment must never exceed ``operacion.precio_total``.
        Otherwise the saldo_restante would be negative and the rebalance
        would produce nonsensical quotas. The view must surface a 400.
        """
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        future = date.fromordinal(self.today.toordinal() + 30)
        draft.datos_operacion["precioTotal"] = "100.00"
        draft.datos_operacion["cuotasTotales"] = 2
        draft.datos_operacion["fechasVencimientoCuotas"] = [
            str(self.today),
            str(future),
        ]
        draft.save(update_fields=["datos_operacion"])
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMonto="500.00",
            primerPagoMontoFisico="500.00",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("precio total", response.json().get("detail", "").lower())
        # No cuota / no pago created.
        self.assertFalse(
            PagoRealizado.objects.filter(cuota__operacion__paciente=self.cliente).exists()
        )
        # Conversion rolled back — borrador still exists.
        self.assertTrue(
            ProspectoConversionBorrador.objects.filter(pk=draft.id).exists()
        )

    # ------------------------- Rebalance: single-cuota legacy -----------

    def test_single_cuota_plan_does_not_rebalance(self):
        """When step 2 only produced ONE cuota (either because the admin
        chose ``cuotasTotales=1`` or because the fallback path auto-
        created a single cuota), the rebalance helper is a no-op and the
        legacy behaviour is preserved: the cuota's ``monto_programado``
        equals the paid amount and the cuota resolves to PAGADO.
        """
        draft = _make_full_draft(
            cliente=self.cliente,
            usuario=self.admin,
            servicio=self.servicio,
            today=self.today,
            catalog_ids=self.catalog_ids,
        )
        # Single cuota, precio 100, paid 100. Should NOT touch the cuota.
        self._login()
        response = self._post_finalize(
            draft,
            primerPagoMetodo="FISICO",
            primerPagoMonto="100.00",
            primerPagoMontoFisico="100.00",
        )
        self.assertEqual(response.status_code, 201)
        operacion = Operacion.objects.get(paciente=self.cliente)
        cuotas = list(CuotaPlanPago.objects.filter(operacion=operacion))
        self.assertEqual(len(cuotas), 1)
        self.assertEqual(cuotas[0].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[0].estado, CuotaPlanPago.Estado.PAGADO)