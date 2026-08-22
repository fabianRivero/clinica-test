from datetime import date, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto, CuotaPlanPago, GastoSucursal, PagoRealizado
from catalogs.models import ProcEstetico, ServicioConfig, Sucursal
from customers.models import Cliente, Prospecto
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    CitaMedica,
    Operacion,
)
from notifications.models import Ticket, TicketMessage
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


SCENARIO_USERNAMES = {
    "paciente.multisucursal",
    "paciente.importable",
    "paciente.importable.libre",
    "paciente.norte",
    "paciente.sur",
}

SCENARIO_SPECIALISTS = {
    "especialista.movible.norte",
    "especialista.movible.sur",
}

EXPENSE_SCENARIO_PREFIX = "[ESCENARIO_GASTOS]"
TICKET_SCENARIO_PREFIX = "[DEMO_TICKET]"


class Command(BaseCommand):
    help = "Carga escenarios locales para probar administracion multi-sucursal."

    @transaction.atomic
    def handle(self, *args, **options):
        branches = self._get_branches()
        roles = self._get_roles()
        services = self._get_services()
        admin_user = Usuario.objects.filter(is_superuser=True).first()

        self._clear_scenarios()
        self._seed_prospects(branches)
        self._seed_clients(roles["CLIENTE"], branches, services, admin_user)
        self._seed_specialists(roles["TRABAJADOR"], branches)
        self._seed_expenses(branches, admin_user)
        self._seed_tickets(branches)

        self.stdout.write(self.style.SUCCESS("Escenarios multi-sucursal cargados correctamente."))
        self.stdout.write(
            "Usuarios demo: "
            + ", ".join(sorted(SCENARIO_USERNAMES | SCENARIO_SPECIALISTS))
        )

    def _get_branches(self):
        norte = Sucursal.objects.filter(nombre="Sucursal Norte").first()
        sur = Sucursal.objects.filter(nombre="Sucursal Sur").first()
        if not norte or not sur:
            raise RuntimeError("Primero ejecuta seed_pdf_baseline para crear Sucursal Norte y Sucursal Sur.")
        return {"norte": norte, "sur": sur}

    def _get_roles(self):
        return {
            "CLIENTE": Rol.objects.get(rol="CLIENTE"),
            "TRABAJADOR": Rol.objects.get(rol="TRABAJADOR"),
        }

    def _get_services(self):
        def service_for(procedure_name):
            return (
                ServicioConfig.objects.filter(
                    proc_estetico__proceso=procedure_name,
                    activo=True,
                )
                .select_related("proc_estetico")
                .first()
            )

        fallback = ServicioConfig.objects.filter(activo=True, proc_estetico__isnull=False).first()
        services = {
            "depilacion": service_for("Depilacion definitiva") or fallback,
            "manchas": service_for("Tratamiento de manchas") or fallback,
            "tatuajes": service_for("Borrado de tatuajes") or fallback,
        }
        if not all(services.values()):
            raise RuntimeError("No hay servicios configurados para crear operaciones demo.")
        return services

    def _clear_scenarios(self):
        scenario_users = Usuario.objects.filter(username__in=SCENARIO_USERNAMES)
        Operacion.objects.filter(paciente__usuario__in=scenario_users).delete()
        Prospecto.objects.filter(telefono__in=["71110001", "71110002", "72220001"]).delete()

        specialists = Especialista.objects.filter(usuario__username__in=SCENARIO_SPECIALISTS)
        AgendaExcepcionEspecialista.objects.filter(especialista__in=specialists).delete()
        AgendaHabitualEspecialista.objects.filter(especialista__in=specialists).delete()
        GastoSucursal.objects.filter(detalles__startswith=EXPENSE_SCENARIO_PREFIX).delete()
        Ticket.objects.filter(asunto__startswith=TICKET_SCENARIO_PREFIX).delete()

    def _seed_prospects(self, branches):
        prospect_specs = [
            ("Prospecto", "Norte Uno", "Demo", "", "71110001", branches["norte"]),
            ("Prospecto", "Norte Dos", "Demo", "", "71110002", branches["norte"]),
            ("Prospecto", "Sur Uno", "Demo", "", "72220001", branches["sur"]),
        ]
        for primer_nombre, segundo_nombre, apellido_paterno, apellido_materno, telefono, branch in prospect_specs:
            Prospecto.objects.update_or_create(
                telefono=telefono,
                defaults={
                    "primer_nombre": primer_nombre,
                    "segundo_nombre": segundo_nombre,
                    "apellido_paterno": apellido_paterno,
                    "apellido_materno": apellido_materno,
                    "sucursal_origen": branch,
                    "estado": Prospecto.Estado.PASAJERO,
                    "observaciones": "Escenario local multi-sucursal.",
                },
            )

    def _seed_clients(self, client_role, branches, services, admin_user):
        multi = self._upsert_client(
            username="paciente.multisucursal",
            password="paciente123456",
            first_name="Paciente",
            last_name="Multisucursal",
            email="paciente.multisucursal@clinic.local",
            ci="90000001",
            phone="79990001",
            branch=branches["norte"],
            role=client_role,
        )
        self._create_operation(
            multi,
            branches["norte"],
            services["depilacion"],
            "Tratamiento activo Norte",
            Decimal("500.00"),
            days_offset=-12,
            paid=False,
            admin_user=admin_user,
            appointment_status=CitaMedica.Estado.CONFIRMADA,
        )
        self._create_operation(
            multi,
            branches["sur"],
            services["manchas"],
            "Tratamiento activo Sur",
            Decimal("650.00"),
            days_offset=-8,
            paid=True,
            admin_user=admin_user,
            appointment_status=CitaMedica.Estado.CONFIRMADA,
        )

        importable = self._upsert_client(
            username="paciente.importable",
            password="paciente123456",
            first_name="Paciente",
            last_name="Importable",
            email="paciente.importable@clinic.local",
            ci="90000002",
            phone="79990002",
            branch=branches["sur"],
            role=client_role,
        )
        self._create_operation(
            importable,
            branches["sur"],
            services["tatuajes"],
            "Cliente importable desde Sur",
            Decimal("420.00"),
            days_offset=3,
            paid=False,
            admin_user=admin_user,
        )

        importable_libre = self._upsert_client(
            username="paciente.importable.libre",
            password="paciente123456",
            first_name="Paciente",
            last_name="Importable Libre",
            email="paciente.importable.libre@clinic.local",
            ci="90000005",
            phone="79990005",
            branch=branches["sur"],
            role=client_role,
        )
        self._create_operation(
            importable_libre,
            branches["sur"],
            services["manchas"],
            "Cliente importable sin reservas pendientes",
            Decimal("280.00"),
            days_offset=-20,
            paid=True,
            admin_user=admin_user,
            status=Operacion.Estado.FINALIZADA,
        )

        norte = self._upsert_client(
            username="paciente.norte",
            password="paciente123456",
            first_name="Paciente",
            last_name="Norte",
            email="paciente.norte@clinic.local",
            ci="90000003",
            phone="79990003",
            branch=branches["norte"],
            role=client_role,
        )
        self._create_operation(
            norte,
            branches["norte"],
            services["depilacion"],
            "Solo visible en Norte",
            Decimal("300.00"),
            days_offset=4,
            paid=False,
            admin_user=admin_user,
        )

        sur = self._upsert_client(
            username="paciente.sur",
            password="paciente123456",
            first_name="Paciente",
            last_name="Sur",
            email="paciente.sur@clinic.local",
            ci="90000004",
            phone="79990004",
            branch=branches["sur"],
            role=client_role,
        )
        self._create_operation(
            sur,
            branches["sur"],
            services["manchas"],
            "Solo visible en Sur",
            Decimal("350.00"),
            days_offset=5,
            paid=False,
            admin_user=admin_user,
        )

        for cliente in (multi, importable, importable_libre, norte, sur):
            cliente.actualizar_estado_automaticamente()

    def _upsert_client(self, *, username, password, first_name, last_name, email, ci, phone, branch, role):
        user, _ = Usuario.objects.update_or_create(
            username=username,
            defaults={
                "primer_nombre": first_name,
                "apellido_paterno": last_name,
                "email": email,
                "rol": role,
                "sucursal": branch,
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
            },
        )
        user.set_password(password)
        user.save()

        cliente, _ = Cliente.objects.update_or_create(
            usuario=user,
            defaults={
                "sucursal_origen": branch,
                "telefono": phone,
                "ci": ci,
                "direccion_domicilio": f"Direccion demo {branch.nombre}",
                "fecha_nacimiento": "1990-01-01",
                "nro_hijos": 0,
                "ocupacion": "Paciente demo",
                "observaciones": "Cliente creado para pruebas multi-sucursal.",
            },
        )
        return cliente

    def _create_operation(
        self,
        cliente,
        branch,
        service,
        detail,
        amount,
        *,
        days_offset,
        paid,
        admin_user,
        status=Operacion.Estado.EN_PROCESO,
        appointment_status=None,
    ):
        start = timezone.localdate()
        operation_kwargs = {
            "paciente": cliente,
            "servicio_config": service,
            "zona_general": "Rostro",
            "zona_especifica": branch.nombre,
            "precio_total": amount,
            "cuotas_totales": 1,
            "sesiones_totales": 2,
            "fecha_inicio": start,
            "fecha_final": start + timedelta(days=days_offset) if status == Operacion.Estado.FINALIZADA else None,
            "estado": status,
            "detalles_op": detail,
            "recomendaciones": "Escenario local de pruebas por sucursal.",
        }
        if any(field.name == "sucursal" for field in Operacion._meta.fields):
            operation_kwargs["sucursal"] = branch

        operacion = Operacion.objects.create(**operation_kwargs)
        cuota = CuotaPlanPago.objects.create(
            operacion=operacion,
            nro_cuota=1,
            fecha_vencimiento=start + timedelta(days=7),
            monto_programado=amount,
            estado=CuotaPlanPago.Estado.PAGADO if paid else CuotaPlanPago.Estado.PENDIENTE,
        )
        if paid and admin_user:
            PagoRealizado.objects.create(
                cuota=cuota,
                monto_pagado=amount,
                comprobante_url="seed_branch_test_pago.pdf",
                estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
                verificado=True,
                verificado_por=admin_user,
                fecha_verificacion=timezone.now(),
                detalles_pago=f"Pago aprobado para {branch.nombre}.",
            )

        appointment_status = appointment_status or (
            CitaMedica.Estado.CONFIRMADA
            if status == Operacion.Estado.FINALIZADA
            else CitaMedica.Estado.PROGRAMADA
        )
        is_confirmed_appointment = appointment_status == CitaMedica.Estado.CONFIRMADA
        CitaMedica.objects.create(
            operacion=operacion,
            sucursal=branch,
            fecha_hora=timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
            + timedelta(days=days_offset),
            estado=appointment_status,
            metodo_confirmacion=(
                CitaMedica.MetodoConfirmacion.BIOMETRICO
                if is_confirmed_appointment
                else ""
            ),
            verif_biometria=is_confirmed_appointment,
            fecha_confirmacion_biometrica=timezone.now() + timedelta(days=days_offset)
            if is_confirmed_appointment
            else None,
            detalles_cita=f"Cita demo en {branch.nombre}.",
        )
        return operacion

    def _seed_specialists(self, worker_role, branches):
        specialty, _ = Especialidad.objects.update_or_create(
            nombre="Multi-sucursal Demo",
            defaults={"activo": True, "orden": 99},
        )
        specs = [
            {
                "username": "especialista.movible.norte",
                "first_name": "Especialista",
                "last_name": "Movible Norte",
                "email": "especialista.movible.norte@clinic.local",
                "ci": "91000001",
                "phone": "78881001",
                "branch": branches["norte"],
            },
            {
                "username": "especialista.movible.sur",
                "first_name": "Especialista",
                "last_name": "Movible Sur",
                "email": "especialista.movible.sur@clinic.local",
                "ci": "91000002",
                "phone": "78881002",
                "branch": branches["sur"],
            },
        ]

        for spec in specs:
            user, _ = Usuario.objects.update_or_create(
                username=spec["username"],
                defaults={
                    "primer_nombre": spec["first_name"],
                    "apellido_paterno": spec["last_name"],
                    "email": spec["email"],
                    "rol": worker_role,
                    "sucursal": spec["branch"],
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password("especialista123456")
            user.save()

            specialist, _ = Especialista.objects.update_or_create(
                usuario=user,
                defaults={
                    "sucursal_base": spec["branch"],
                    "ci": spec["ci"],
                    "telefono": spec["phone"],
                    "observaciones": "Especialista movible para pruebas multi-sucursal.",
                },
            )
            EspecialistaEspecialidad.objects.update_or_create(
                especialista=specialist,
                especialidad=specialty,
                defaults={},
            )
            self._seed_specialist_schedule(specialist, spec["branch"])

    def _seed_specialist_schedule(self, specialist, branch):
        habitual, _ = AgendaHabitualEspecialista.objects.update_or_create(
            especialista=specialist,
            sucursal=branch,
            defaults={
                "fecha_inicio": timezone.localdate(),
                "fecha_fin": timezone.localdate() + timedelta(days=90),
                "hora_inicio": time(8, 0),
                "hora_fin": time(16, 0),
                "activo": True,
                "detalle": f"Horario demo en {branch.nombre}",
            },
        )
        for day in range(1, 6):
            AgendaHabitualDia.objects.update_or_create(
                agenda=habitual,
                dia_semana=day,
                defaults={},
            )

        AgendaExcepcionEspecialista.objects.update_or_create(
            especialista=specialist,
            sucursal=branch,
            fecha=timezone.localdate() + timedelta(days=10),
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
            defaults={
                "hora_inicio": time(12, 0),
                "hora_fin": time(14, 0),
                "activo": True,
                "detalle": f"Excepcion demo para validar limpieza en {branch.nombre}",
            },
        )

    def _get_expense_categories(self):
        category_specs = [
            ("Alquiler", "Gastos de alquiler de ambientes y espacios operativos."),
            ("Servicios", "Agua, electricidad, internet y otros servicios recurrentes."),
            ("Insumos", "Materiales e insumos usados por la sucursal."),
            ("Equipamiento", "Compra o reposicion de equipos y herramientas."),
            ("Marketing", "Publicidad, pauta y materiales comerciales."),
            ("Sueldos", "Pagos administrativos relacionados con personal."),
            ("Mantenimiento", "Reparaciones, limpieza y mantenimiento general."),
            ("Otros", "Gastos administrativos no clasificados."),
        ]
        categories = {}
        for name, description in category_specs:
            category, _ = CategoriaGasto.objects.update_or_create(
                nombre=name,
                defaults={"descripcion": description, "activo": True},
            )
            categories[name] = category
        return categories

    def _seed_expenses(self, branches, admin_user):
        categories = self._get_expense_categories()
        expense_specs = [
            (branches["norte"], date(2026, 4, 3), "Insumos", "Guantes nitrilo caja x100", Decimal("4"), Decimal("48.00"), "Distribuidora Medica Norte"),
            (branches["norte"], date(2026, 4, 12), "Servicios", "Servicio electrico consultorios", Decimal("1"), Decimal("385.50"), "Empresa Electrica"),
            (branches["norte"], date(2026, 4, 24), "Marketing", "Campania abril redes sociales", Decimal("1"), Decimal("620.00"), "Agencia Digital Demo"),
            (branches["norte"], date(2026, 5, 4), "Insumos", "Gel conductor para laser", Decimal("6"), Decimal("35.00"), "Laser Supplies SRL"),
            (branches["norte"], date(2026, 5, 15), "Mantenimiento", "Revision equipo laser", Decimal("1"), Decimal("780.00"), "Tecnicos Laser Norte"),
            (branches["norte"], date(2026, 5, 26), "Alquiler", "Alquiler mensual sucursal norte", Decimal("1"), Decimal("3200.00"), "Inmobiliaria Norte"),
            (branches["sur"], date(2026, 4, 5), "Insumos", "Mascarillas descartables", Decimal("8"), Decimal("22.50"), "Proveedor Clinico Sur"),
            (branches["sur"], date(2026, 4, 18), "Servicios", "Internet sucursal sur", Decimal("1"), Decimal("250.00"), "Telecom Demo"),
            (branches["sur"], date(2026, 4, 28), "Equipamiento", "Lampara auxiliar cabina", Decimal("1"), Decimal("540.00"), "Equipos Esteticos Sur"),
            (branches["sur"], date(2026, 5, 7), "Marketing", "Volantes promocion manchas", Decimal("500"), Decimal("0.85"), "Imprenta Sur"),
            (branches["sur"], date(2026, 5, 16), "Mantenimiento", "Limpieza profunda cabinas", Decimal("1"), Decimal("360.00"), "Servicios Limpieza Sur"),
            (branches["sur"], date(2026, 5, 29), "Alquiler", "Alquiler mensual sucursal sur", Decimal("1"), Decimal("2900.00"), "Inmobiliaria Sur"),
        ]
        for branch, expense_date, category_name, concept, units, unit_cost, provider in expense_specs:
            GastoSucursal.objects.create(
                sucursal=branch,
                categoria=categories[category_name],
                fecha=expense_date,
                concepto=concept,
                unidades=units,
                costo_unidad=unit_cost,
                gasto_total=(units * unit_cost).quantize(Decimal("0.01")),
                proveedor=provider,
                detalles=f"{EXPENSE_SCENARIO_PREFIX} Gasto demo para validar filtros de abril y mayo 2026.",
                registrado_por=admin_user,
            )

    def _seed_tickets(self, branches):
        users = Usuario.objects.in_bulk(
            [
                "admin.general",
                "admin.norte",
                "especialista.movible.norte",
                "especialista.movible.sur",
            ],
            field_name="username",
        )
        missing = [
            username
            for username in ["admin.general", "admin.norte", "especialista.movible.norte", "especialista.movible.sur"]
            if username not in users
        ]
        if missing:
            raise RuntimeError(f"Faltan usuarios para seed de tickets: {', '.join(missing)}")

        specialists = {
            specialist.usuario.username: specialist
            for specialist in Especialista.objects.select_related("usuario").filter(
                usuario__username__in=["especialista.movible.norte", "especialista.movible.sur"]
            )
        }
        if "especialista.movible.norte" not in specialists or "especialista.movible.sur" not in specialists:
            raise RuntimeError("Faltan especialistas movibles para seed de tickets.")

        ticket_specs = [
            {
                "asunto": f"{TICKET_SCENARIO_PREFIX} Ticket abierto Norte",
                "sucursal": branches["norte"],
                "especialista": specialists["especialista.movible.norte"],
                "creado_por": users["admin.norte"],
                "estado": Ticket.Estado.ABIERTO,
                "closed_at": None,
                "mensajes": [
                    ("admin.norte", "Se registra incidente operativo en Norte.", TicketMessage.Estado.RESPONDIDO),
                    ("admin.general", "Escalado y validado desde administracion principal.", TicketMessage.Estado.RESPONDIDO),
                    ("especialista.movible.norte", "Tomado; iniciando diagnostico en cabina Norte.", TicketMessage.Estado.ENVIADO),
                ],
            },
            {
                "asunto": f"{TICKET_SCENARIO_PREFIX} Ticket abierto Sur",
                "sucursal": branches["sur"],
                "especialista": specialists["especialista.movible.sur"],
                "creado_por": users["admin.general"],
                "estado": Ticket.Estado.ABIERTO,
                "closed_at": None,
                "mensajes": [
                    ("admin.general", "Paciente reporta demora de confirmacion en Sur.", TicketMessage.Estado.RESPONDIDO),
                    ("especialista.movible.sur", "Se reviso agenda y se aplicaron ajustes.", TicketMessage.Estado.ENVIADO),
                    ("admin.general", "Monitoreo activo para validar SLA.", TicketMessage.Estado.RESPONDIDO),
                ],
            },
            {
                "asunto": f"{TICKET_SCENARIO_PREFIX} Ticket cerrado para reopen",
                "sucursal": branches["sur"],
                "especialista": specialists["especialista.movible.sur"],
                "creado_por": users["admin.general"],
                "estado": Ticket.Estado.CERRADO,
                "closed_at": timezone.now() - timedelta(days=1),
                "mensajes": [
                    ("admin.general", "Caso resuelto inicialmente y marcado para cierre.", TicketMessage.Estado.RESPONDIDO),
                    ("especialista.movible.sur", "Se confirmo resolucion tecnica en sitio.", TicketMessage.Estado.RESPONDIDO),
                    ("admin.general", "Pendiente validacion final para posible reapertura.", TicketMessage.Estado.ENVIADO),
                ],
            },
        ]

        for spec in ticket_specs:
            ticket, _ = Ticket.objects.update_or_create(
                asunto=spec["asunto"],
                defaults={
                    "sucursal": spec["sucursal"],
                    "especialista": spec["especialista"],
                    "creado_por": spec["creado_por"],
                    "estado": spec["estado"],
                    "closed_at": spec["closed_at"],
                },
            )
            TicketMessage.objects.filter(ticket=ticket).delete()
            for username, contenido, estado in spec["mensajes"]:
                TicketMessage.objects.create(
                    ticket=ticket,
                    autor=users[username],
                    contenido=f"{TICKET_SCENARIO_PREFIX} {contenido}",
                    estado=estado,
                )
