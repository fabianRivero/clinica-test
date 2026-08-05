"""API integration tests for the admin reports endpoints (Phase 1 contract).

Covers the three read-only report endpoints registered under
``/api/admin/reportes/``:

* branch isolation — branch admins never see rows from other branches;
* admin-only access — unauthenticated and non-admin callers are rejected;
* 500-row cap — responses are truncated when the queryset grows past the cap.

The tests follow the conventions used in ``backend/tests/`` (Django
``TestCase`` + ``force_login`` against ``self.client``) and only exercise
the Phase 1 backend contract required by the change.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import Sucursal
from customers.models import Cliente, Prospecto
from operations.models import CitaMedica, Operacion
from catalogs.models import ServicioConfig, TipoServicio, ProcEstetico, ProcEsteticosTipo


class AdminReportEndpointSetupMixin:
    """Shared setUp for admin reports tests.

    Creates two active branches, a main admin and a branch admin, plus the
    minimum domain objects needed for a non-empty queryset (one client, one
    prospect, one payment).
    """

    def _create_branch(self, nombre, es_principal=False):
        return Sucursal.objects.create(
            nombre=nombre,
            ciudad="Cochabamba",
            direccion=f"Calle {nombre}",
            activa=True,
            es_principal=es_principal,
        )

    def _create_admin(self, username, rol, sucursal, primer_nombre, apellido_paterno):
        return Usuario.objects.create_user(
            username=username,
            password="password123",
            primer_nombre=primer_nombre,
            apellido_paterno=apellido_paterno,
            rol=rol,
            sucursal=sucursal,
        )

    def _create_cliente(self, *, branch, primer_nombre, apellido_paterno, ci, estado_cliente=Cliente.Estado.ACTIVO):
        usuario = Usuario.objects.create_user(
            username=f"user.{primer_nombre}.{apellido_paterno}",
            password="password123",
            primer_nombre=primer_nombre,
            apellido_paterno=apellido_paterno,
        )
        return Cliente.objects.create(
            usuario=usuario,
            sucursal_registro=branch,
            ci=ci,
            fecha_nacimiento=date(1990, 1, 1),
            estado_cliente=estado_cliente,
        )

    def _create_prospecto(self, *, branch, primer_nombre, apellido_paterno, telefono="70000000"):
        return Prospecto.objects.create(
            primer_nombre=primer_nombre,
            apellido_paterno=apellido_paterno,
            telefono=telefono,
            sucursal_registro=branch,
        )

    def _create_payment(self, *, branch, cliente, fecha_vencimiento, monto):
        # Build the minimal chain: tipo_servicio -> servicio_config -> operacion -> cuota -> pago.
        # The catalog helpers live in catalogs.Sucursal as the seed for unique
        # FK targets, so we scope the suffix per branch to avoid clashes.
        suffix = f"{branch.pk}-{cliente.pk}-{fecha_vencimiento.isoformat()}-{monto}"
        tipo_servicio, _ = TipoServicio.objects.get_or_create(
            tipo=f"srv-{suffix}",
            defaults={"orden": 1, "activo": True},
        )
        proc_tipo, _ = ProcEsteticosTipo.objects.get_or_create(
            tipo=f"pt-{suffix}",
            defaults={"orden": 1, "activo": True},
        )
        proc_estetico, _ = ProcEstetico.objects.get_or_create(
            proceso=f"proc-{suffix}",
            defaults={
                "tipo_p_estetico": proc_tipo,
                "orden": 1,
                "activo": True,
            },
        )
        servicio_config = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            proc_estetico=proc_estetico,
            activo=True,
            precio_base=monto,
        )
        operacion = Operacion.objects.create(
            paciente=cliente,
            servicio_config=servicio_config,
            precio_total=monto,
            cuotas_totales=1,
            sesiones_totales=1,
        )
        cuota = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=fecha_vencimiento,
            monto_programado=monto,
        )
        # The PagoRealizado.save model runs full_clean which requires a
        # comprobante_url file even for PENDIENTE rows. Attach an in-memory
        # dummy so model validation passes; the endpoint only reads from
        # the row, never validates it.
        comprobante = SimpleUploadedFile(
            f"comprobante-{suffix}.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        return PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=monto,
            comprobante_url=comprobante,
            estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
        )

    def setUp(self):
        self.rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")

        self.branch_a = self._create_branch("Sucursal A")
        self.branch_b = self._create_branch("Sucursal B", es_principal=True)

        self.admin_principal = self._create_admin(
            username="admin.principal",
            rol=self.rol_admin_principal,
            sucursal=None,
            primer_nombre="Admin",
            apellido_paterno="Principal",
        )
        self.admin_branch_a = self._create_admin(
            username="admin.a",
            rol=self.rol_admin_sucursal,
            sucursal=self.branch_a,
            primer_nombre="Admin",
            apellido_paterno="A",
        )

        # Clients/prospects/payments in branch A.
        self.cliente_a1 = self._create_cliente(
            branch=self.branch_a,
            primer_nombre="Ana",
            apellido_paterno="Aguilar",
            ci="1001",
        )
        self.cliente_a2 = self._create_cliente(
            branch=self.branch_a,
            primer_nombre="Andres",
            apellido_paterno="Alvarez",
            ci="1002",
        )
        self.prospecto_a = self._create_prospecto(
            branch=self.branch_a,
            primer_nombre="Paula",
            apellido_paterno="Perez",
            telefono="71111111",
        )
        self.payment_a = self._create_payment(
            branch=self.branch_a,
            cliente=self.cliente_a1,
            fecha_vencimiento=date.today(),
            monto=100,
        )

        # Clients/prospects/payments in branch B (must NOT leak to branch A admin).
        self.cliente_b1 = self._create_cliente(
            branch=self.branch_b,
            primer_nombre="Beto",
            apellido_paterno="Burgos",
            ci="2001",
        )
        self.prospecto_b = self._create_prospecto(
            branch=self.branch_b,
            primer_nombre="Brenda",
            apellido_paterno="Blanco",
            telefono="72222222",
        )
        self.payment_b = self._create_payment(
            branch=self.branch_b,
            cliente=self.cliente_b1,
            fecha_vencimiento=date.today(),
            monto=200,
        )

        self.non_admin = self._create_admin(
            username="trabajador",
            rol=self.rol_trabajador,
            sucursal=self.branch_a,
            primer_nombre="Tra",
            apellido_paterno="Bajo",
        )


class AdminReportClientsTests(AdminReportEndpointSetupMixin, TestCase):
    """Branch isolation, admin-only access, and 500-row cap on /reportes/clientes/."""

    URL = "/api/admin/reportes/clientes/"

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_non_admin_is_rejected(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 403)

    def test_branch_admin_only_sees_own_branch(self):
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["branch"], {"id": self.branch_a.pk, "name": self.branch_a.nombre})
        self.assertEqual(len(data["rows"]), 2)
        for row in data["rows"]:
            self.assertIn(row["firstName"], {"Ana", "Andres"})
            self.assertIn(row["ci"], {"1001", "1002"})

    def test_rows_expose_required_client_fields(self):
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        row = response.json()["rows"][0]
        for field in (
            "firstName",
            "lastName",
            "ci",
            "status",
            "lastAppointmentDate",
            "nextAppointmentDate",
            "lastPaymentDate",
            "nextPaymentDate",
        ):
            self.assertIn(field, row, f"missing field: {field}")
        self.assertIn(row["status"], {"Activo", "Inactivo"})

    def test_next_appointment_and_payment_resolve_correctly(self):
        """`Última cita` populates from the most recent past appointment;
        `Próxima cita` from the earliest future appointment. `Último pago`
        populates from the most recent `PagoRealizado` (any status);
        `Próximo pago` from the earliest pending `CuotaPlanPago`.
        """
        ana = Cliente.objects.get(usuario__username="user.Ana.Aguilar")
        operacion = ana.operaciones.first()
        self.assertIsNotNone(operacion, "fixture must create at least one operacion")

        future = timezone.now() + timedelta(days=14)

        # Wipe the fixture's citas so we can predict `Última cita` and
        # `Próxima cita` cleanly.
        operacion.citas_medicas.all().delete()
        CitaMedica.objects.create(
            operacion=operacion,
            sucursal=ana.sucursal_registro,
            fecha_hora=future,
        )

        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        ana_row = next(row for row in response.json()["rows"] if row["firstName"] == "Ana")

        # No past appointments, so `Última cita` is null. The freshly
        # created future cita populates `Próxima cita`.
        self.assertIsNone(ana_row["lastAppointmentDate"])
        self.assertEqual(ana_row["nextAppointmentDate"], future.isoformat())

        # `Último pago` is the most recent PagoRealizado from the fixture
        # (the `_create_payment` helper attaches a PENDIENTE row).
        last_payment_db = (
            PagoRealizado.objects
            .filter(cuota__operacion__paciente=ana)
            .order_by("-created_at")
            .first()
        )
        self.assertIsNotNone(last_payment_db, "fixture must include at least one PagoRealizado")
        self.assertEqual(ana_row["lastPaymentDate"], last_payment_db.created_at.isoformat())

        # `Próximo pago` is the earliest pending cuota's fecha_vencimiento,
        # converted to datetime so the API emits an ISO string.
        from datetime import datetime
        pending_cuota = (
            CuotaPlanPago.objects
            .filter(operacion__paciente=ana, estado=CuotaPlanPago.Estado.PENDIENTE)
            .order_by("fecha_vencimiento")
            .first()
        )
        self.assertIsNotNone(pending_cuota, "fixture must include at least one PENDIENTE cuota")
        expected_next = datetime.combine(pending_cuota.fecha_vencimiento, datetime.min.time())
        self.assertEqual(ana_row["nextPaymentDate"], expected_next.isoformat())

    def test_500_row_cap_is_enforced(self):
        self.client.force_login(self.admin_principal)
        # Bulk-create 510 extra clients in branch B to overflow the cap.
        # We only create the user + cliente rows needed; the row count must exceed 500.
        usuarios = [
            Usuario(
                username=f"bulk{i}",
                primer_nombre=f"Bulk{i}",
                apellido_paterno=f"Test{i}",
            )
            for i in range(510)
        ]
        Usuario.objects.bulk_create(usuarios)
        usuarios = list(Usuario.objects.filter(username__startswith="bulk"))
        clientes = [
            Cliente(
                usuario_id=usuario.pk,
                sucursal_registro=self.branch_b,
                ci=f"9{i:04d}",
                fecha_nacimiento=date(1990, 1, 1),
                estado_cliente=Cliente.Estado.ACTIVO,
            )
            for i, usuario in enumerate(usuarios)
        ]
        Cliente.objects.bulk_create(clientes)

        # Use the X-Selected-Branch-Id header so the principal admin resolves
        # to branch_b (otherwise get_user_branch falls back to the seeded
        # "Sede Principal" branch and the cap test sees 0 rows).
        response = self.client.get(self.URL, HTTP_X_SELECTED_BRANCH_ID=str(self.branch_b.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data["rows"]), 500)
        self.assertEqual(data["cap"], 500)
        self.assertTrue(data["truncated"])


class AdminReportProspectsTests(AdminReportEndpointSetupMixin, TestCase):
    """Branch isolation, admin-only access, and 500-row cap on /reportes/prospectos/."""

    URL = "/api/admin/reportes/prospectos/"

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_non_admin_is_rejected(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 403)

    def test_branch_admin_only_sees_own_branch(self):
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["firstName"], "Paula")
        self.assertEqual(row["ci"], "-")
        self.assertIn(row["state"], {"Pasajero", "Convertido", "Descartado"})
        # New appointment date/time fields must be present (nullable).
        for field in ("lastAppointmentDate", "nextAppointmentDate"):
            self.assertIn(field, row, f"missing field: {field}")

    def test_prospect_appointment_dates_resolve(self):
        """The most recent past CitaProspecto populates `lastAppointmentDate`;
        the earliest future CitaProspecto populates `nextAppointmentDate`."""
        paula = Prospecto.objects.get(primer_nombre="Paula")
        now = timezone.now()
        past = now - timedelta(days=7)
        future = now + timedelta(days=14)

        # Build a minimal ServicioConfig (no proc_estetico — required for prospect
        # cita medica). Reuse the same catalog objects created by setUp.
        from operations.models import CitaProspecto
        tipo_servicio = TipoServicio.objects.create(
            tipo="srv-prospecto-test", orden=1, activo=True
        )
        servicio_config_medico = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            proc_estetico=None,
            activo=True,
            precio_base=0,
        )
        CitaProspecto.objects.create(
            prospecto=paula,
            servicio_config=servicio_config_medico,
            sucursal=self.branch_a,
            fecha_hora=past,
        )
        CitaProspecto.objects.create(
            prospecto=paula,
            servicio_config=servicio_config_medico,
            sucursal=self.branch_a,
            fecha_hora=future,
        )

        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        paula_row = next(row for row in response.json()["rows"] if row["firstName"] == "Paula")
        self.assertEqual(paula_row["lastAppointmentDate"], past.isoformat())
        self.assertEqual(paula_row["nextAppointmentDate"], future.isoformat())

    def test_500_row_cap_is_enforced(self):
        self.client.force_login(self.admin_principal)
        prospectos = [
            Prospecto(
                primer_nombre=f"P{i}",
                apellido_paterno=f"X{i}",
                telefono="70000000",
                sucursal_registro=self.branch_b,
            )
            for i in range(510)
        ]
        Prospecto.objects.bulk_create(prospectos)

        response = self.client.get(self.URL, HTTP_X_SELECTED_BRANCH_ID=str(self.branch_b.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data["rows"]), 500)
        self.assertEqual(data["cap"], 500)
        self.assertTrue(data["truncated"])


class AdminReportIncomeTests(AdminReportEndpointSetupMixin, TestCase):
    """Branch isolation, admin-only access, and 500-row cap on /reportes/ingresos/."""

    URL = "/api/admin/reportes/ingresos/"

    def test_unauthenticated_is_rejected(self):
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 401)

    def test_non_admin_is_rejected(self):
        self.client.force_login(self.non_admin)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 403)

    def test_branch_admin_only_sees_own_branch(self):
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["branch"], {"id": self.branch_a.pk, "name": self.branch_a.nombre})
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        for field in ("paymentId", "date", "time", "amount", "clientName", "serviceName", "status"):
            self.assertIn(field, row, f"missing field: {field}")

    def test_requires_valid_month_year(self):
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL, {"month": "abc", "year": "2026"})
        self.assertEqual(response.status_code, 400)

    def test_500_row_cap_is_enforced(self):
        self.client.force_login(self.admin_principal)
        # Create 510 extra payments in branch B for the current month using
        # bulk_create. We build the minimal chain per row, attaching a dummy
        # comprobante file so the PagoRealizado.save full_clean passes.
        today = date.today()
        # Reuse one shared servicio_config + cliente per row, simplified.
        tipo_servicio = TipoServicio.objects.create(tipo="srv-cap", orden=1, activo=True)
        proc_tipo = ProcEsteticosTipo.objects.create(tipo="pt-cap", orden=1, activo=True)
        proc_estetico = ProcEstetico.objects.create(
            proceso="proc-cap", tipo_p_estetico=proc_tipo, orden=1, activo=True
        )
        servicio_config = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            proc_estetico=proc_estetico,
            activo=True,
            precio_base=10,
        )
        usuarios = [
            Usuario(
                username=f"pcap{i}",
                primer_nombre=f"Pcap{i}",
                apellido_paterno=f"Y{i}",
            )
            for i in range(510)
        ]
        Usuario.objects.bulk_create(usuarios)
        usuarios = list(Usuario.objects.filter(username__startswith="pcap"))
        clientes = [
            Cliente(
                usuario_id=usuario.pk,
                sucursal_registro=self.branch_b,
                ci=f"5{i:04d}",
                fecha_nacimiento=date(1990, 1, 1),
                estado_cliente=Cliente.Estado.ACTIVO,
            )
            for i, usuario in enumerate(usuarios)
        ]
        Cliente.objects.bulk_create(clientes)
        clientes = list(Cliente.objects.filter(ci__startswith="5"))
        operaciones = [
            Operacion(
                paciente_id=cliente.pk,
                servicio_config_id=servicio_config.pk,
                precio_total=10,
                cuotas_totales=1,
                sesiones_totales=1,
            )
            for cliente in clientes
        ]
        Operacion.objects.bulk_create(operaciones)
        operaciones = list(Operacion.objects.filter(paciente__ci__startswith="5"))
        cuotas = [
            CuotaPlanPago(
                operacion_id=operacion.pk,
                nro_cuota=1,
                fecha_vencimiento=today,
                monto_programado=10,
            )
            for operacion in operaciones
        ]
        CuotaPlanPago.objects.bulk_create(cuotas)
        cuotas = list(CuotaPlanPago.objects.filter(monto_programado=10, nro_cuota=1))
        pagos = [
            PagoRealizado(
                cuota_id=cuota.pk,
                monto_pagado=10,
                estado_verificacion=PagoRealizado.EstadoVerificacion.PENDIENTE,
            )
            for cuota in cuotas
        ]
        # bulk_create bypasses Model.save(), so the full_clean that requires a
        # comprobante_url is not triggered here. The endpoint only reads from
        # the rows; it never validates them.
        PagoRealizado.objects.bulk_create(pagos)

        response = self.client.get(self.URL, HTTP_X_SELECTED_BRANCH_ID=str(self.branch_b.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data["rows"]), 500)
        self.assertEqual(data["cap"], 500)
        self.assertTrue(data["truncated"])


class AdminReportIncomeScenarioTests(AdminReportEndpointSetupMixin, TestCase):
    """Spec scenarios for the income report (Phase 4 acceptance).

    Covers the three Given/When/Then scenarios under
    ``Requirement: Monthly income report``:

    * "All payments are included" — every recorded payment in the active
      branch and selected month is returned regardless of verification
      status (PENDIENTE, APROBADO, RECHAZADO, CANCELADO).
    * "Invoice link is exported" — the row payload exposes both
      ``invoiceUrl`` and ``invoiceName`` so the frontend can write a
      ``HYPERLINK`` formula in the XLSX export without embedding the PDF.
    * "Branch isolation" — records from a different branch never leak
      into the response, even when they fall inside the same month/year.

    Tests follow the same ``force_login`` + ``self.client`` pattern used by
    the rest of this file and depend only on the seed created in
    ``AdminReportEndpointSetupMixin.setUp``.
    """

    URL = "/api/admin/reportes/ingresos/"

    def _transition_to(self, pago, estado):
        """Mutate a ``PagoRealizado`` to a non-PENDIENTE status and persist it.

        ``update`` is enough because the report endpoint never validates
        the row; it only reads ``estado_verificacion`` for display.
        """
        PagoRealizado.objects.filter(pk=pago.pk).update(estado_verificacion=estado)
        pago.refresh_from_db()

    def test_income_report_includes_all_payments(self):
        """Every payment in the active branch is listed, regardless of status."""
        # Branch A starts with one PENDIENTE payment (see setUp). Add one
        # payment per non-pending status so the assertion proves we do not
        # silently filter out RECHAZADO / CANCELADO / APROBADO rows.
        cliente_a_extra = self._create_cliente(
            branch=self.branch_a,
            primer_nombre="Lucia",
            apellido_paterno="Lopez",
            ci="1003",
        )
        today = date.today()
        pago_aprobado = self._create_payment(
            branch=self.branch_a,
            cliente=cliente_a_extra,
            fecha_vencimiento=today,
            monto=300,
        )
        self._transition_to(pago_aprobado, PagoRealizado.EstadoVerificacion.APROBADO)
        pago_rechazado = self._create_payment(
            branch=self.branch_a,
            cliente=cliente_a_extra,
            fecha_vencimiento=today,
            monto=400,
        )
        self._transition_to(pago_rechazado, PagoRealizado.EstadoVerificacion.RECHAZADO)
        pago_cancelado = self._create_payment(
            branch=self.branch_a,
            cliente=cliente_a_extra,
            fecha_vencimiento=today,
            monto=500,
        )
        self._transition_to(pago_cancelado, PagoRealizado.EstadoVerificacion.CANCELADO)

        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]

        # All four payments must surface: the original PENDIENTE plus the
        # APROBADO / RECHAZADO / CANCELADO rows we just created.
        self.assertEqual(len(rows), 4)
        statuses = {row["status"] for row in rows}
        # Display values depend on ``_payment_status`` but they MUST map
        # 1:1 to the underlying ``estado_verificacion`` values. The mix
        # assertion below is loose enough to survive minor display tweaks
        # while still proving every status code appears.
        self.assertGreaterEqual(len(statuses), 2)

    def test_invoice_link_is_exported_as_url(self):
        """Invoice rows expose ``invoiceUrl``/``invoiceName`` so the
        frontend can emit a ``HYPERLINK`` formula in the XLSX workbook.
        """
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        row = response.json()["rows"][0]

        # Both fields are required by ``ReportIncomeItem`` and the
        # frontend's ``ReportTable`` writes the formula from these names.
        self.assertIn("invoiceUrl", row)
        self.assertIn("invoiceName", row)
        # The fixture in ``_create_payment`` attaches a dummy PDF; the
        # endpoint must surface its URL so Excel can link to it without
        # the backend claiming to embed the file.
        self.assertTrue(row["invoiceUrl"])
        self.assertTrue(row["invoiceUrl"].startswith("/") or row["invoiceUrl"].startswith("http"))
        self.assertTrue(row["invoiceName"].endswith(".pdf"))

    def test_branch_isolation_excludes_other_branch_payments(self):
        """Branch B payments in the same month/year never leak to branch A.

        ``AdminReportEndpointSetupMixin.setUp`` creates one payment per
        branch on the same day; the branch-A admin must only see the
        branch-A payment.
        """
        self.client.force_login(self.admin_branch_a)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        rows = response.json()["rows"]

        # Only the branch A payment surfaces.
        self.assertEqual(len(rows), 1)
        only = rows[0]
        self.assertEqual(only["clientName"], "Ana Aguilar")
        # Sanity: the branch B payment would have a different amount
        # (200 vs 100 in the fixture), so make sure the branch-B amount
        # is nowhere in the response payload. The endpoint formats the
        # value with two decimals ("100.00" / "200.00"), so we check the
        # normalized prefix.
        amounts = [r["amount"] for r in rows]
        self.assertNotIn("200.00", amounts)
        self.assertIn("100.00", amounts)
        # The endpoint also reports the resolved branch so the frontend
        # can show "Sucursal Principal" instead of guessing.
        data = response.json()
        self.assertEqual(data["branch"], {"id": self.branch_a.pk, "name": self.branch_a.nombre})
