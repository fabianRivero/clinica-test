"""Tests for ``POST /api/admin/operaciones/<id>/actualizar-precio/``.

Covers the two modes the endpoint supports today:

* Without ``quotas``: classic redistribution of the remaining balance
  across the new quota count (legacy behaviour).
* With ``quotas`` (``[{nroCuota, montoProgramado, fechaVencimiento}, ...]``):
  per-quota edit. Only unpaid, unverified quotas can be edited; paid
  quotas and quotas with pending payment receipts are locked. The sum
  of edited pending amounts + already paid amounts must equal the new
  ``priceTotal`` exactly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    ProcEsteticosTipo,
    ProcEstetico,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from customers.models import Cliente
from operations.models import Operacion


def post_json(client, url, payload):
    return client.post(
        url, data=__import__("json").dumps(payload), content_type="application/json"
    )


class OperationPricePlanUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.sucursal = Sucursal.objects.create(nombre="Central", activa=True)
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("120.00"),
            activo=True,
        )
        cls.admin = Usuario.objects.create_user(
            username="admin.price", password="pw12345!",
            primer_nombre="Adm", apellido_paterno="Pri",
            rol=cls.rol_admin, sucursal=cls.sucursal,
        )
        cls.user = Usuario.objects.create_user(username="paciente.price", password="pw12345!")
        cls.cliente = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def setUp(self):
        self.client_http = Client()
        self.client_http.force_login(self.admin)
        self.operation = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.service,
            precio_total=Decimal("300.00"),
            cuotas_totales=3,
            sesiones_totales=5,
            fecha_inicio=timezone.localdate(),
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.url = f"/api/admin/operaciones/{self.operation.pk}/actualizar-precio/"

    def _make_cuota(self, nro, monto, fecha):
        return CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=nro,
            monto_programado=monto,
            fecha_vencimiento=fecha,
        )

    # ------------------------------------------------------------------
    # Legacy mode (sin lista de quotas -> redistribucion automatica)
    # ------------------------------------------------------------------

    def test_sin_lista_redistribuye_saldo_entre_cuotas(self):
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        response = post_json(
            self.client_http, self.url,
            {"priceTotal": "450.00", "quotaCount": 3},
        )
        self.assertEqual(response.status_code, 200, response.content)

        cuotas = list(
            self.operation.cuotas_plan_pagos.order_by("nro_cuota")
        )
        self.assertEqual(len(cuotas), 3)
        total = sum((c.monto_programado for c in cuotas), Decimal("0.00"))
        self.assertEqual(total, Decimal("450.00"))

    # ------------------------------------------------------------------
    # Modo edicion por cuota
    # ------------------------------------------------------------------

    def test_edicion_por_cuota_aplica_montos_y_fechas(self):
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        new_date_1 = today + timedelta(days=10)
        new_date_2 = today + timedelta(days=40)
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "120.00", "fechaVencimiento": new_date_1.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "80.00", "fechaVencimiento": new_date_2.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        cuotas = list(
            self.operation.cuotas_plan_pagos.order_by("nro_cuota")
        )
        self.assertEqual(cuotas[0].monto_programado, Decimal("120.00"))
        self.assertEqual(cuotas[0].fecha_vencimiento, new_date_1)
        self.assertEqual(cuotas[1].monto_programado, Decimal("80.00"))
        self.assertEqual(cuotas[1].fecha_vencimiento, new_date_2)
        # La cuota 3 no fue editada explicitamente pero su monto se
        # mantiene para que la suma cierre.
        self.assertEqual(cuotas[2].monto_programado, Decimal("100.00"))

    def test_edicion_permite_suma_menor_a_precio_total(self):
        """La regla de suma exacta se relajo: el admin puede editar una o
        varias cuotas sin redistribuir el saldo completo. Si cada item
        es valido (no Pagado, sin comprobante PENDIENTE, monto >=0) y
        la suma de los montos NO SUPERA el precio total, el guardado
        pasa aunque la suma de las pendientes no cierre exactamente.
        El saldo restante queda "descubierto" hasta que se agreguen
        mas cuotas. Sumas que EXCEDAN el precio total se rechazan
        (cubierto por ``test_batch_rechazado_si_suma_supera_precio_total``)."""
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    # Suma: 100 + 80 + 60 = 240, < 300. Aceptado.
                    {"nroCuota": 1, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "80.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "60.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        # Suma: 240 != 300, pero <= 300. Se permite (saldo restante 60
        # queda sin asignar).
        self.assertEqual(response.status_code, 200, response.content)

        # Los montos se aplican tal cual.
        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(cuotas[0].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[1].monto_programado, Decimal("80.00"))
        self.assertEqual(cuotas[2].monto_programado, Decimal("60.00"))

    def test_batch_rechazado_si_suma_supera_precio_total(self):
        """Si la suma de los montos editados supera al precio total,
        el backend rechaza con 400. Esto evita que el admin meta
        "sobrecuota" sin querer."""
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))
        # precio total: 300. Cambiamos la cuota 1 a 200 -> suma 400 > 300.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "200.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("supera", body.get("detail", "").lower())
        self.assertIn("quotas", body.get("errors", {}))
        # Ninguna cuota se persiste.
        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(cuotas[0].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[1].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[2].monto_programado, Decimal("100.00"))

    def test_caso_una_sola_cuota_cambio_de_monto(self):
        """Reproduce el caso reportado: una sola cuota de Bs 500 sobre un
        precio total de Bs 850. Cambiar el monto a 600 sin ajustar el
        resto ahora pasa (antes fallaba con "suma no cuadra")."""
        today = timezone.localdate()
        self.operation.precio_total = Decimal("850.00")
        self.operation.save(update_fields=["precio_total", "updated_at"])
        self._make_cuota(1, Decimal("500.00"), today)

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "850.00",
                "quotaCount": 1,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "600.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuota = self.operation.cuotas_plan_pagos.get(nro_cuota=1)
        self.assertEqual(cuota.monto_programado, Decimal("600.00"))

    def test_edicion_rechazada_si_cuota_ya_pagada(self):
        today = timezone.localdate()
        pagada = self._make_cuota(1, Decimal("100.00"), today)
        pagada.estado = CuotaPlanPago.Estado.PAGADO
        pagada.save()
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        errors = response.json().get("errors", {})
        self.assertIn("quotas.0.nroCuota", errors)

    def test_edicion_rechazada_si_cuota_tiene_comprobante_pendiente(self):
        today = timezone.localdate()
        cuota_con_pago = self._make_cuota(1, Decimal("100.00"), today)
        PagoRealizado.objects.create(
            cuota=cuota_con_pago,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        # El bloqueo ahora es por cuota: la 1 (con comprobante
        # pendiente) se rechaza con error en ``quotas.0.nroCuota``.
# El backend aborta toda la operacion si hay cualquier item con
        # error, asi que ninguna cuota se persiste.
        self.assertEqual(response.status_code, 400)
        errors = response.json().get("errors", {})
        self.assertIn("quotas.0.nroCuota", errors)

        # Verificamos que ninguna cuota fue modificada: los montos
        # originales siguen igual.
        from billing.models import CuotaPlanPago as _C
        self.assertEqual(_C.objects.get(operacion=self.operation, nro_cuota=1).monto_programado, Decimal("100.00"))
        self.assertEqual(_C.objects.get(operacion=self.operation, nro_cuota=2).monto_programado, Decimal("100.00"))
        self.assertEqual(_C.objects.get(operacion=self.operation, nro_cuota=3).monto_programado, Decimal("100.00"))

    def test_edicion_con_comprobante_rechazado_es_permitida(self):
        """Un comprobante RECHAZADO no bloquea la edicion: la cuota
        sigue pendiente (no fue aprobada) y no hay revision abierta."""
        today = timezone.localdate()
        cuota_con_rechazo = self._make_cuota(1, Decimal("100.00"), today)
        PagoRealizado.objects.create(
            cuota=cuota_con_rechazo,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO,
            verificado_por=self.admin,
            fecha_verificacion=timezone.now(),
        )
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        # Editamos la cuota 1 (la del comprobante rechazado). El admin
        # puede cambiarle el monto: la regla nueva lo permite.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "300.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "120.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                    {"nroCuota": 3, "montoProgramado": "80.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        cuota_1 = CuotaPlanPago.objects.get(operacion=self.operation, nro_cuota=1)
        self.assertEqual(cuota_1.monto_programado, Decimal("120.00"))
        # La cuota sigue Pendiente (no paso a PAGADA por tener un
        # comprobante rechazado).
        self.assertEqual(cuota_1.estado, CuotaPlanPago.Estado.PENDIENTE)

    def test_edicion_con_pagos_aprobados_respeta_lo_pagado(self):
        today = timezone.localdate()
        cuota_pagada = self._make_cuota(1, Decimal("100.00"), today)
        PagoRealizado.objects.create(
            cuota=cuota_pagada,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado_por=self.admin,
            fecha_verificacion=timezone.now(),
        )
        cuota_pagada.estado = CuotaPlanPago.Estado.PAGADO
        cuota_pagada.save()
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        # Ya hay Bs 100 pagados; subir el precio total a 350 y mantener
        # la cuota 2/3 igual deberia sumar: 100 pagado + 250 pendiente = 350.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "350.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 2, "montoProgramado": "150.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        cuotas = {c.nro_cuota: c for c in self.operation.cuotas_plan_pagos.all()}
        self.assertEqual(cuotas[1].estado, CuotaPlanPago.Estado.PAGADO)
        self.assertEqual(cuotas[1].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[2].monto_programado, Decimal("150.00"))
        self.assertEqual(cuotas[3].monto_programado, Decimal("100.00"))

    def test_patient_id_se_expone_en_detalle(self):
        """Asegura que el detail ahora expone ``patientId`` para que el
        frontend pueda llamar al endpoint de reserva sin tener que
        navegar al detalle del cliente."""
        detail_url = f"/api/admin/operaciones/{self.operation.pk}/"
        response = self.client_http.get(detail_url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["operation"]["patientId"], self.cliente.pk)

    # ------------------------------------------------------------------
    # Agregar cuotas nuevas (nroCuota > maximo existente)
    # ------------------------------------------------------------------

    def test_agregar_cuota_nueva_crea_la_fila(self):
        """Si el item trae un nroCuota mayor al maximo existente, se
        crea una nueva CuotaPlanPago con esos valores."""
        today = timezone.localdate()
        # Estado inicial: 3 cuotas de Bs 100 (total 300).
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        # Subimos el precio a 400 para poder meter una cuota 4 de Bs 100.
        new_due_date = today + timedelta(days=90)
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "400.00",
                "quotaCount": 4,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                    {"nroCuota": 4, "montoProgramado": "100.00", "fechaVencimiento": new_due_date.isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(len(cuotas), 4)
        self.assertEqual(cuotas[3].nro_cuota, 4)
        self.assertEqual(cuotas[3].monto_programado, Decimal("100.00"))
        self.assertEqual(cuotas[3].fecha_vencimiento, new_due_date)
        # El contador de la operacion refleja el nuevo total.
        self.assertEqual(self.operation.cuotas_totales, 4)
        self.assertEqual(self.operation.precio_total, Decimal("400.00"))

    def test_agregar_cuota_sin_hueco_de_numeracion_es_rechazado(self):
        """Para mantener la numeracion consistente, el nuevo ``nroCuota``
        debe ser exactamente ``max_existing + 1``. Un hueco (p.ej.
        ``nroCuota=10`` cuando el maximo es 3) es rechazado."""
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "400.00",
                "quotaCount": 4,
                "quotas": [
                    {"nroCuota": 1, "montoProgramado": "100.00", "fechaVencimiento": today.isoformat()},
                    {"nroCuota": 2, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                    {"nroCuota": 3, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                    {"nroCuota": 10, "montoProgramado": "100.00", "fechaVencimiento": (today + timedelta(days=90)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        errors = response.json().get("errors", {})
        self.assertIn("quotas.3.nroCuota", errors)

    # ------------------------------------------------------------------
    # Flujo "agregar 1 sola cuota" (sin exigir suma exacta)
    # ------------------------------------------------------------------

    def test_agregar_una_sola_cuota_sin_exigir_suma(self):
        """Modo "agregar 1 sola cuota": el admin manda UN solo item
        nuevo. El backend lo crea aunque la suma no cierre contra el
        precio total (el admin ira agregando mas cuotas despues)."""
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        # Subimos el precio total a 500 manualmente; ya hay 2 cuotas de
        # 100 (200 programado). Agregamos una cuota 3 de 150 (suma
        # parcial 350, no cierra contra 500).
        self.operation.precio_total = Decimal("500.00")
        self.operation.save(update_fields=["precio_total", "updated_at"])

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "500.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 3, "montoProgramado": "150.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(len(cuotas), 3)
        self.assertEqual(cuotas[2].nro_cuota, 3)
        self.assertEqual(cuotas[2].monto_programado, Decimal("150.00"))
        # cuotas_totales sube automaticamente con el nuevo nro maximo.
        self.assertEqual(self.operation.cuotas_totales, 3)
        # Modo single-add: no tocamos precio_total aunque el admin envio
        # priceTotal (la operacion ya estaba en 500; si subimos a 500
        # sigue igual).
        self.assertEqual(self.operation.precio_total, Decimal("500.00"))

    def test_agregar_dos_cuotas_seguidas_primera_suma_bajo_precio(self):
        """El admin agrega una primera cuota y luego otra, en
        llamadas separadas. Cada llamada es single-add."""
        today = timezone.localdate()
        # Inicial: 1 cuota, precio total 500.
        self._make_cuota(1, Decimal("100.00"), today)

        # Primera llamada: agregar cuota 2 de 200.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "500.00",
                "quotaCount": 2,
                "quotas": [
                    {"nroCuota": 2, "montoProgramado": "200.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        # Segunda llamada: agregar cuota 3 de 150.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "500.00",
                "quotaCount": 3,
                "quotas": [
                    {"nroCuota": 3, "montoProgramado": "150.00", "fechaVencimiento": (today + timedelta(days=60)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        # Suma actual: 100 + 200 + 150 = 450 (< 500, pero single-add
        # lo permite).
        total = sum(c.monto_programado for c in cuotas)
        self.assertEqual(total, Decimal("450.00"))
        self.assertEqual(self.operation.cuotas_totales, 3)

    def test_agregar_cuota_individual_con_monto_mayor_a_precio_rechazado(self):
        """Aunque sea single-add, el monto no puede superar el precio
        total del tratamiento."""
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)

        # precio total 500. Cuota nueva de 600.
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "500.00",
                "quotaCount": 2,
                "quotas": [
                    {"nroCuota": 2, "montoProgramado": "600.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("quotas.0.montoProgramado", body.get("errors", {}))

    def test_single_add_rechazado_si_suma_con_existentes_supera_precio(self):
        """Reproduce el caso reportado: precio total 850, ya hay una
        cuota pendiente de Bs 600. Agregar una nueva de Bs 300
        dejaria la suma en 900 > 850, asi que el backend rechaza."""
        today = timezone.localdate()
        self.operation.precio_total = Decimal("850.00")
        self.operation.save(update_fields=["precio_total", "updated_at"])
        self._make_cuota(1, Decimal("600.00"), today)

        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "850.00",
                "quotaCount": 2,
                "quotas": [
                    {"nroCuota": 2, "montoProgramado": "300.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIn("supera", body.get("detail", "").lower())
        self.assertIn("quotas", body.get("errors", {}))
        # La cuota 1 no se modifica; la 2 no se crea.
        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(len(cuotas), 1)
        self.assertEqual(cuotas[0].monto_programado, Decimal("600.00"))

    def test_single_add_permitido_si_suma_no_supera_precio(self):
        """El opuesto: con precio 850 y cuota 1 de 600, agregar una
        nueva de Bs 250 (suma 850) pasa. Bs 250 con el mismo
        tratamiento pasa. Bs 251 fallaria."""
        today = timezone.localdate()
        self.operation.precio_total = Decimal("850.00")
        self.operation.save(update_fields=["precio_total", "updated_at"])
        self._make_cuota(1, Decimal("600.00"), today)

        # Caso borderline: exactamente 850 (suma total == precio).
        response = post_json(
            self.client_http, self.url,
            {
                "priceTotal": "850.00",
                "quotaCount": 2,
                "quotas": [
                    {"nroCuota": 2, "montoProgramado": "250.00", "fechaVencimiento": (today + timedelta(days=30)).isoformat()},
                ],
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.operation.refresh_from_db()
        self.assertEqual(self.operation.cuotas_plan_pagos.count(), 2)


# ---------------------------------------------------------------------------
# Tests del endpoint ``POST /api/admin/operaciones/<id>/eliminar-cuota/``
# ---------------------------------------------------------------------------


class OperationDeleteQuotaTests(TestCase):
    """Elimina UNA cuota del plan. Reglas:
    - No PAGADA, no comprobante PENDIENTE.
    - Compacata la numeracion para mantener la regla "cuotas nuevas =
      max + 1" sin huecos.
    """

    @classmethod
    def setUpTestData(cls):
        cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        cls.sucursal = Sucursal.objects.create(nombre="Delete-Centro", activa=True)
        cls.tipo = TipoServicio.objects.create(tipo="Tratamiento", activo=True)
        cls.tipo_proc = ProcEsteticosTipo.objects.create(tipo="Corporal", activo=True)
        cls.proc = ProcEstetico.objects.create(
            tipo_p_estetico=cls.tipo_proc, proceso="Limpieza", activo=True
        )
        cls.service = ServicioConfig.objects.create(
            tipo_servicio=cls.tipo,
            proc_estetico=cls.proc,
            precio_base=Decimal("100.00"),
            activo=True,
        )
        cls.admin = Usuario.objects.create_user(
            username="admin.delete.quota", password="pw12345!",
            primer_nombre="Adm", apellido_paterno="Del",
            rol=cls.rol_admin, sucursal=None,
        )
        cls.user = Usuario.objects.create_user(username="op.delete.user", password="pw12345!")
        cls.customer = Cliente.objects.create(
            usuario=cls.user,
            sucursal_origen=cls.sucursal,
            fecha_nacimiento=date(1990, 1, 1),
        )

    def setUp(self):
        self.client_http = Client()
        self.client_http.force_login(self.admin)
        self.operation = Operacion.objects.create(
            paciente=self.customer,
            servicio_config=self.service,
            precio_total=Decimal("500.00"),
            cuotas_totales=5,
            sesiones_totales=1,
            fecha_inicio=timezone.localdate(),
            estado=Operacion.Estado.EN_PROCESO,
        )
        self.url = f"/api/admin/operaciones/{self.operation.pk}/eliminar-cuota/"
        today = timezone.localdate()
        self._make_cuota(1, Decimal("100.00"), today)
        self._make_cuota(2, Decimal("100.00"), today + timedelta(days=30))
        self._make_cuota(3, Decimal("100.00"), today + timedelta(days=60))
        self._make_cuota(4, Decimal("100.00"), today + timedelta(days=90))
        self._make_cuota(5, Decimal("100.00"), today + timedelta(days=120))

    def _make_cuota(self, nro, monto, fecha):
        return CuotaPlanPago.objects.create(
            operacion=self.operation,
            nro_cuota=nro,
            monto_programado=monto,
            fecha_vencimiento=fecha,
        )

    def test_eliminar_cuota_del_medio_compacga_numeracion(self):
        """Eliminar la cuota #2 compacta: las demas se renumeran
        (3 -> 2, 4 -> 3, 5 -> 4) y cuotas_totales baja a 4."""
        response = post_json(self.client_http, self.url, {"nroCuota": 2})
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual(len(cuotas), 4)
        # La nro 1 sigue igual.
        self.assertEqual(cuotas[0].nro_cuota, 1)
        self.assertEqual(cuotas[0].id, CuotaPlanPago.objects.get(operacion=self.operation, nro_cuota=1).id)
        # 3 -> 2, 4 -> 3, 5 -> 4 (compactacion).
        self.assertEqual([c.nro_cuota for c in cuotas], [1, 2, 3, 4])
        # ``cuotas_totales`` se decrementa al nuevo maximo.
        self.assertEqual(self.operation.cuotas_totales, 4)

    def test_eliminar_ultima_cuota_no_compacga(self):
        """Eliminar la ultima cuota (nro max) no afecta a las demas;
        solo decrementa el contador."""
        response = post_json(self.client_http, self.url, {"nroCuota": 5})
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual([c.nro_cuota for c in cuotas], [1, 2, 3, 4])
        self.assertEqual(self.operation.cuotas_totales, 4)

    def test_eliminar_primera_cuota_compacga(self):
        """Eliminar la #1 renumera todas las demas."""
        response = post_json(self.client_http, self.url, {"nroCuota": 1})
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual([c.nro_cuota for c in cuotas], [1, 2, 3, 4])
        self.assertEqual(self.operation.cuotas_totales, 4)

    def test_eliminar_cuota_pagada_bloqueada(self):
        today = timezone.localdate()
        cuota_pagada = CuotaPlanPago.objects.get(operacion=self.operation, nro_cuota=2)
        PagoRealizado.objects.create(
            cuota=cuota_pagada,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado_por=self.admin,
            fecha_verificacion=timezone.now(),
        )
        # Forzar estado PAGADO para que coincida con el estado final
        # despues del pago aprobado.
        cuota_pagada.estado = CuotaPlanPago.Estado.PAGADO
        cuota_pagada.save()

        response = post_json(self.client_http, self.url, {"nroCuota": 2})
        self.assertEqual(response.status_code, 400)
        self.assertIn("pagada", response.json().get("detail", "").lower())

    def test_eliminar_cuota_con_comprobante_pendiente_bloqueada(self):
        today = timezone.localdate()
        cuota = CuotaPlanPago.objects.get(operacion=self.operation, nro_cuota=3)
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )

        response = post_json(self.client_http, self.url, {"nroCuota": 3})
        self.assertEqual(response.status_code, 400)
        self.assertIn("revision", response.json().get("detail", "").lower())

    def test_eliminar_cuota_con_comprobante_rechazado_es_permitido(self):
        """Un comprobante RECHAZADO NO bloquea la eliminacion: la cuota
        sigue pendiente y no hay revision abierta."""
        today = timezone.localdate()
        cuota = CuotaPlanPago.objects.get(operacion=self.operation, nro_cuota=3)
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("100.00"),
            comprobante_url=SimpleUploadedFile("c.pdf", b"%PDF-test", content_type="application/pdf"),
            estado_verificacion=PagoRealizado.EstadoVerificacion.RECHAZADO,
            verificado_por=self.admin,
            fecha_verificacion=timezone.now(),
        )

        response = post_json(self.client_http, self.url, {"nroCuota": 3})
        self.assertEqual(response.status_code, 200, response.content)

        self.operation.refresh_from_db()
        cuotas = list(self.operation.cuotas_plan_pagos.order_by("nro_cuota"))
        self.assertEqual([c.nro_cuota for c in cuotas], [1, 2, 3, 4])

    def test_eliminar_cuota_inexistente_404(self):
        response = post_json(self.client_http, self.url, {"nroCuota": 99})
        self.assertEqual(response.status_code, 404)

    def test_eliminar_sin_nro_cuota_es_400(self):
        response = post_json(self.client_http, self.url, {})
        self.assertEqual(response.status_code, 400)

    def test_eliminar_sobre_operacion_finalizada_bloqueada(self):
        """Solo operaciones EN_PROCESO permiten eliminar cuotas."""
        self.operation.estado = Operacion.Estado.FINALIZADA
        self.operation.save()

        response = post_json(self.client_http, self.url, {"nroCuota": 1})
        self.assertEqual(response.status_code, 400)
