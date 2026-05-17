from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Rol, Usuario
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GrosorPiel,
    GrupoOpciones,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    ServicioConfig,
    TipoPiel,
    TipoServicio,
    ImplanteInjerto,
    Sucursal,
)
from customers.models import Prospecto, Cliente, HuellaBiometricaCliente
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    DiaBloqueadoAgendaGlobal,
    FichaCampo,
    FichaSeccion,
    Operacion,
    CitaMedica,
    TabletKiosko,
)
from billing.models import CategoriaGasto, CuotaPlanPago, PagoRealizado
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


class Command(BaseCommand):
    help = (
        "Carga una base minima alineada al PDF de ficha medica: "
        "admin preservado, 5 especialistas sin horarios establecidos, "
        "servicios limitados a consulta y los 3 procedimientos del documento."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        roles = self._seed_roles()
        branches = self._seed_branches()
        self._seed_admins(roles, branches)
        specialist_users = self._seed_specialist_users(roles["TRABAJADOR"], branches)
        specialties, specialists = self._seed_staff(specialist_users, branches)
        catalogs = self._seed_catalogs()
        self._seed_form_configuration(catalogs)
        self._seed_prospects(branches)
        self._clear_business_data()
        self._seed_formal_patients(roles["CLIENTE"], branches)
        self._clear_schedule_configuration()
        self._seed_schedules(specialists)
        kiosk_credentials = self._seed_tablet_kiosks(branches)

        self.stdout.write(self.style.SUCCESS("Base PDF minima cargada correctamente."))
        self.stdout.write(
            "Resumen: "
            f"usuarios={Usuario.objects.count()}, "
            f"especialistas={Especialista.objects.count()}, "
            f"especialidades={Especialidad.objects.count()}, "
            f"tipos_servicio={TipoServicio.objects.count()}, "
            f"procedimientos={ProcEstetico.objects.count()}, "
            f"servicios_config={ServicioConfig.objects.count()}, "
            f"agendas_habituales={AgendaHabitualEspecialista.objects.count()}"
        )
        self.stdout.write(
            "Especialistas creados: "
            + ", ".join(
                f"{specialist.usuario.username} ({specialist.usuario.nombre_completo})"
                for specialist in specialists.values()
            )
        )
        self.stdout.write(
            "Especialidades disponibles: "
            + ", ".join(specialty.nombre for specialty in specialties.values())
        )
        self.stdout.write("Credenciales de tablet kiosko para pruebas:")
        for cred in kiosk_credentials:
            self.stdout.write(
                f"- {cred['branch']}: codigo={cred['codigo']} clave={cred['clave']}"
            )

    def _seed_roles(self):
        roles = {}
        for role_name in ("ADMIN_PRINCIPAL", "ADMIN_SUCURSAL", "TRABAJADOR", "CLIENTE"):
            role, _ = Rol.objects.update_or_create(rol=role_name, defaults={})
            roles[role_name] = role
        # Eliminar rol legacy ADMINISTRADOR si existe
        Rol.objects.filter(rol="ADMINISTRADOR").delete()
        return roles

    def _normalize_admin_users(self, admin_role):
        for admin_user in Usuario.objects.filter(is_superuser=True):
            changed_fields = []
            if admin_user.rol_id != admin_role.id:
                admin_user.rol = admin_role
                changed_fields.append("rol")
            if not admin_user.is_staff:
                admin_user.is_staff = True
                changed_fields.append("is_staff")
            if not admin_user.is_active:
                admin_user.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                changed_fields.append("updated_at")
                admin_user.save(update_fields=changed_fields)

    def _seed_branches(self):
        main_branch, _ = Sucursal.objects.update_or_create(
            nombre="Sede Principal",
            defaults={
                "ciudad": "La Paz",
                "direccion": "Sede administrativa principal",
                "es_principal": True,
                "activa": True,
            }
        )
        branch_a, _ = Sucursal.objects.update_or_create(
            nombre="Sucursal Norte",
            defaults={
                "ciudad": "La Paz",
                "direccion": "Avenida Siempre Viva 123",
                "es_principal": False,
                "activa": True
            }
        )
        branch_b, _ = Sucursal.objects.update_or_create(
            nombre="Sucursal Sur",
            defaults={
                "ciudad": "Santa Cruz",
                "direccion": "Calle Falsa 456",
                "es_principal": False,
                "activa": True
            }
        )
        Sucursal.objects.exclude(pk=main_branch.pk).filter(es_principal=True).update(es_principal=False)
        return {"principal": main_branch, "A": branch_a, "B": branch_b}

    def _seed_admins(self, roles, branches):
        # Admin General (principal)
        admin_gen, created = Usuario.objects.update_or_create(
            username="admin.general",
            defaults={
                "primer_nombre": "Admin",
                "apellido_paterno": "General",
                "email": "admin.general@clinic.local",
                "rol": roles["ADMIN_PRINCIPAL"],
                "sucursal": branches["principal"],
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin_gen.set_password("admin123456")
        admin_gen.save()

        # Admin Sucursal (solo ve datos de su sucursal)
        admin_suc, created = Usuario.objects.update_or_create(
            username="admin.sucursal",
            defaults={
                "primer_nombre": "Admin",
                "apellido_paterno": "Sucursal Sur",
                "email": "admin.sucursal@clinic.local",
                "rol": roles["ADMIN_SUCURSAL"],
                "sucursal": branches["B"],
                "is_active": True,
                "is_staff": True,
                "is_superuser": False,
            },
        )
        admin_suc.set_password("admin123456")
        admin_suc.save()

    def _seed_specialist_users(self, worker_role, branches):
        user_specs = {
            "lucia.laser": {
                "password": "laser123456",
                "primer_nombre": "Lucia",
                "segundo_nombre": "Elena",
                "apellido_paterno": "Suarez",
                "apellido_materno": "Molina",
                "email": "lucia.laser@clinic.local",
                "branch": branches["A"],
            },
            "diego.tatuajes": {
                "password": "tatuajes123456",
                "primer_nombre": "Diego",
                "segundo_nombre": "",
                "apellido_paterno": "Roca",
                "apellido_materno": "Salinas",
                "email": "diego.tatuajes@clinic.local",
                "branch": branches["A"],
            },
            "sofia.manchas": {
                "password": "manchas123456",
                "primer_nombre": "Sofia",
                "segundo_nombre": "",
                "apellido_paterno": "Mendez",
                "apellido_materno": "Rojas",
                "email": "sofia.manchas@clinic.local",
                "branch": branches["B"],
            },
            "rafael.consulta": {
                "password": "consulta123456",
                "primer_nombre": "Rafael",
                "segundo_nombre": "",
                "apellido_paterno": "Quiroga",
                "apellido_materno": "Perez",
                "email": "rafael.consulta@clinic.local",
                "branch": branches["B"],
            },
        }

        users = {}
        for username, spec in user_specs.items():
            user, created = Usuario.objects.update_or_create(
                username=username,
                defaults={
                    "primer_nombre": spec["primer_nombre"],
                    "segundo_nombre": spec.get("segundo_nombre", ""),
                    "apellido_paterno": spec["apellido_paterno"],
                    "apellido_materno": spec.get("apellido_materno", ""),
                    "email": spec["email"],
                    "rol": worker_role,
                    "sucursal": spec["branch"],
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password(spec["password"])
            user.save(update_fields=["password"])
            users[username] = user
        return users

    def _seed_staff(self, users, branches):
        specialty_specs = {
            "dermatologia_laser": {
                "nombre": "Dermatologia laser",
                "descripcion": "Evaluacion y tratamientos laser.",
                "orden": 1,
            },
            "borrado_tatuajes": {
                "nombre": "Borrado de tatuajes",
                "descripcion": "Atencion de tatuajes con equipo laser.",
                "orden": 2,
            },
            "tratamiento_manchas": {
                "nombre": "Tratamiento de manchas",
                "descripcion": "Protocolos de manchas y pigmentacion.",
                "orden": 3,
            },
            "consulta_medica": {
                "nombre": "Consulta medica",
                "descripcion": "Valoracion inicial y controles.",
                "orden": 4,
            },
            "medicina_estetica": {
                "nombre": "Medicina estetica",
                "descripcion": "Seguimiento clinico de procedimientos.",
                "orden": 5,
            },
        }

        specialties = {}
        for key, spec in specialty_specs.items():
            specialty, _ = Especialidad.objects.update_or_create(
                nombre=spec["nombre"],
                defaults={
                    "descripcion": spec["descripcion"],
                    "orden": spec["orden"],
                    "activo": True,
                },
            )
            specialties[key] = specialty

        specialist_specs = {
            "lucia": {
                "user": users["lucia.laser"],
                "ci": "4567890",
                "telefono": "70111222",
                "observaciones": "Especialista en depilacion definitiva y protocolos laser.",
                "specialties": ["dermatologia_laser", "medicina_estetica"],
            },
            "diego": {
                "user": users["diego.tatuajes"],
                "ci": "5678901",
                "telefono": "72233445",
                "observaciones": "Especialista en borrado de tatuajes.",
                "specialties": ["borrado_tatuajes", "consulta_medica"],
            },
            "sofia": {
                "user": users["sofia.manchas"],
                "ci": "6789012",
                "telefono": "73344556",
                "observaciones": "Especialista en manchas y evaluacion estetica.",
                "specialties": ["tratamiento_manchas", "medicina_estetica"],
            },
            "rafael": {
                "user": users["rafael.consulta"],
                "ci": "7890123",
                "telefono": "74455667",
                "observaciones": "Medico para consultas y controles.",
                "specialties": ["consulta_medica", "medicina_estetica"],
            },
        }

        specialists = {}
        for key, spec in specialist_specs.items():
            specialist, _ = Especialista.objects.update_or_create(
                usuario=spec["user"],
                defaults={
                    "ci": spec["ci"],
                    "telefono": spec["telefono"],
                    "observaciones": spec["observaciones"],
                },
            )

            desired_specialties = [specialties[name] for name in spec["specialties"]]
            EspecialistaEspecialidad.objects.filter(especialista=specialist).exclude(
                especialidad__in=desired_specialties
            ).delete()
            for specialty in desired_specialties:
                EspecialistaEspecialidad.objects.get_or_create(
                    especialista=specialist,
                    especialidad=specialty,
                )

            specialists[key] = specialist

        return specialties, specialists

    def _seed_catalogs(self):
        catalogs = {
            "tipo_servicio": {},
            "tipo_procedimiento": {},
            "procedimiento": {},
            "servicio_config": {},
            "antecedente": {},
            "implante": {},
            "cirugia": {},
            "grupo": {},
            "opcion": {},
        }

        service_type_specs = {
            "consulta": ("Cita de consulta", "Reserva para valoracion o control medico.", 1),
            "tratamiento": ("Tratamiento estetico", "Procedimientos de la ficha medica.", 2),
        }
        for key, (name, description, order) in service_type_specs.items():
            item, _ = TipoServicio.objects.update_or_create(
                tipo=name,
                defaults={"descripcion": description, "orden": order, "activo": True},
            )
            catalogs["tipo_servicio"][key] = item

        expense_category_specs = [
            ("Alquiler", "Gastos de alquiler de ambientes y espacios operativos."),
            ("Servicios", "Agua, electricidad, internet y otros servicios recurrentes."),
            ("Insumos", "Materiales e insumos usados por la sucursal."),
            ("Equipamiento", "Compra o reposicion de equipos y herramientas."),
            ("Marketing", "Publicidad, pauta y materiales comerciales."),
            ("Sueldos", "Pagos administrativos relacionados con personal."),
            ("Mantenimiento", "Reparaciones, limpieza y mantenimiento general."),
            ("Otros", "Gastos administrativos no clasificados."),
        ]
        for name, description in expense_category_specs:
            CategoriaGasto.objects.update_or_create(
                nombre=name,
                defaults={"descripcion": description, "activo": True},
            )

        procedure_type, _ = ProcEsteticosTipo.objects.update_or_create(
            tipo="Laser",
            defaults={
                "descripcion": "Procedimientos laser de la ficha medica.",
                "orden": 1,
                "activo": True,
            },
        )
        catalogs["tipo_procedimiento"]["laser"] = procedure_type

        procedure_specs = {
            "depilacion": (
                "Depilacion definitiva",
                "Procedimiento de depilacion definitiva.",
                1,
                Decimal("850.00"),
            ),
            "manchas": (
                "Tratamiento de manchas",
                "Procedimiento para tratamiento de manchas.",
                2,
                Decimal("650.00"),
            ),
            "tatuajes": (
                "Borrado de tatuajes",
                "Procedimiento para borrado de tatuajes.",
                3,
                Decimal("1500.00"),
            ),
        }
        for key, (name, description, order, price) in procedure_specs.items():
            procedure, _ = ProcEstetico.objects.update_or_create(
                tipo_p_estetico=procedure_type,
                proceso=name,
                defaults={
                    "descripcion": description,
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["procedimiento"][key] = procedure
            service_config, _ = ServicioConfig.objects.update_or_create(
                tipo_servicio=catalogs["tipo_servicio"]["tratamiento"],
                proc_estetico=procedure,
                defaults={"precio_base": price, "activo": True},
            )
            catalogs["servicio_config"][key] = service_config

        consulta_config, _ = ServicioConfig.objects.update_or_create(
            tipo_servicio=catalogs["tipo_servicio"]["consulta"],
            proc_estetico=None,
            defaults={"precio_base": Decimal("120.00"), "activo": True},
        )
        catalogs["servicio_config"]["consulta"] = consulta_config

        for order, name in enumerate(
            ["Diabetes", "Asma", "Hipertension", "Cancer", "Otro", "Ninguna"],
            start=1,
        ):
            item, _ = AntecedenteMedico.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Opcion de antecedente: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["antecedente"][name] = item

        for order, name in enumerate(
            ["Menton", "Mejillas", "Nariz", "Otro", "Ninguno"],
            start=1,
        ):
            item, _ = ImplanteInjerto.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Opcion de implante o injerto: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["implante"][name] = item

        for order, name in enumerate(
            [
                "Blefaroplastia",
                "Rinoplastia",
                "Bichectomia",
                "Rinomodelacion",
                "Lifting",
                "Botox",
                "Ninguna",
            ],
            start=1,
        ):
            item, _ = CirugiaEstetica.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Opcion de cirugia o tratamiento estetico: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["cirugia"][name] = item

        si_no_group, _ = GrupoOpciones.objects.update_or_create(
            codigo="SI_NO",
            defaults={
                "nombre": "Si / No",
                "descripcion": "Opciones binarias de la ficha medica.",
                "activo": True,
            },
        )
        catalogs["grupo"]["SI_NO"] = si_no_group
        for order, (code, label) in enumerate((("SI", "Si"), ("NO", "No")), start=1):
            option, _ = OpcionCatalogo.objects.update_or_create(
                grupo=si_no_group,
                codigo=code,
                defaults={
                    "nombre": label,
                    "valor": label,
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["opcion"][f"SI_NO_{code}"] = option

        depth_group, _ = GrupoOpciones.objects.update_or_create(
            codigo="PROFUNDIDAD_TATUAJE",
            defaults={
                "nombre": "Profundidad del tatuaje",
                "descripcion": "Opciones del punto de borrado de tatuajes.",
                "activo": True,
            },
        )
        catalogs["grupo"]["PROFUNDIDAD_TATUAJE"] = depth_group
        for order, (code, label) in enumerate(
            (("SUPERFICIAL", "Superficial"), ("PROFUNDA", "Profunda")),
            start=1,
        ):
            option, _ = OpcionCatalogo.objects.update_or_create(
                grupo=depth_group,
                codigo=code,
                defaults={
                    "nombre": label,
                    "valor": label,
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["opcion"][f"PROFUNDIDAD_{code}"] = option

        for order, name in enumerate(
            ["Piel normal", "Mixta", "Seca", "Grasa", "Desvitalizada", "Hidratada"],
            start=1,
        ):
            TipoPiel.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Tipo de piel: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )

        for order, name in enumerate(["Leve", "Medio", "Alto"], start=1):
            GradoDeshidratacion.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Grado de deshidratacion: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )

        for order, name in enumerate(
            ["Fina", "Media fina", "Media", "Media gruesa", "Gruesa"],
            start=1,
        ):
            GrosorPiel.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Grosor de piel: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )

        patologia_names = [
            "Eritema",
            "Telangiectasias",
            "Papulas",
            "Melasma",
            "Hiperpigmentaciones",
            "Ampollas",
            "Couperosis",
            "Pustulas",
            "Arrugas",
            "Estrellas vasculares",
            "Vesiculas",
            "Cicatrices",
            "Quistes",
            "Micosis",
            "Dermatitis",
            "Angiomas",
            "Costra",
            "Millium",
            "Efelides",
            "Hirsutismo",
            "Comedones",
            "Verruga",
            "Rosacea",
            "Queratosis",
            "Urticaria",
            "Eczema",
            "Nodulos",
            "Vitiligo",
        ]
        for order, name in enumerate(patologia_names, start=1):
            PatologiaCutanea.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Patologia cutanea: {name}.",
                    "orden": order,
                    "activo": True,
                },
            )

        return catalogs

    def _seed_form_configuration(self, catalogs):
        def sync_section(proc_key, code, name, order):
            return FichaSeccion.objects.update_or_create(
                proc_estetico=catalogs["procedimiento"][proc_key],
                codigo=code,
                defaults={"nombre": name, "orden": order, "activo": True},
            )[0]

        def sync_field(section, code, label, field_type, order, group=None):
            return FichaCampo.objects.update_or_create(
                seccion=section,
                codigo=code,
                defaults={
                    "etiqueta": label,
                    "tipo_campo": field_type,
                    "grupo_opciones": group,
                    "es_multiple": field_type == FichaCampo.TipoCampo.MULTISELECCION,
                    "permite_detalle": False,
                    "requerido": False,
                    "orden": order,
                    "activo": True,
                },
            )[0]

        depilation_fields = [
            ("BRONCEADO", "Bronceado", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("ISOTRETINOINA", "Isotretinoina", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("DESODORANTES", "Desodorantes", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("INFLAMATORIOS", "Antiinflamatorios", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("TIPO_DEPILACION", "Tipo de depilacion", FichaCampo.TipoCampo.TEXTO, None),
            ("DESORDEN_HORMONAL", "Desorden hormonal", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("DIABETES_METFORMINA", "Diabetes (Metformina)", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("HIPOTIROIDISMO", "Hipotiroidismo", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("KETOCONAZOL", "Ketoconazol", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("DIURETICOS", "Diureticos", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("TIPO_VELLO", "Tipo de vello", FichaCampo.TipoCampo.TEXTO, None),
            ("COLOR_VELLO", "Color", FichaCampo.TipoCampo.TEXTO, None),
            ("GROSOR_VELLO", "Grosor", FichaCampo.TipoCampo.TEXTO, None),
        ]

        for proc_key in ("depilacion", "manchas"):
            section = sync_section(proc_key, "PUNTO_D", "Depilacion definitiva / Manchas", 1)
            for order, (code, label, field_type, group) in enumerate(depilation_fields, start=1):
                sync_field(section, code, label, field_type, order, group)

        tattoo_section = sync_section("tatuajes", "PUNTO_E", "Borrado de tatuajes", 1)
        tattoo_fields = [
            ("TIEMPO_ANTIGUEDAD", "Tiempo de antiguedad", FichaCampo.TipoCampo.TEXTO, None),
            (
                "PROFUNDIDAD_TATUAJE",
                "Profundidad del tatuaje",
                FichaCampo.TipoCampo.SELECCION,
                catalogs["grupo"]["PROFUNDIDAD_TATUAJE"],
            ),
            ("COLOR_TATUAJE", "Color del tatuaje", FichaCampo.TipoCampo.TEXTO, None),
            ("TIPO_CICATRIZACION", "Tipo de cicatrizacion", FichaCampo.TipoCampo.TEXTO, None),
            ("PROTECTOR_SOLAR", "Protector solar", FichaCampo.TipoCampo.SELECCION, catalogs["grupo"]["SI_NO"]),
            ("OTROS_CUIDADOS", "Otros cuidados", FichaCampo.TipoCampo.TEXTO, None),
            ("TIPO_COLOR_PIEL", "Tipo de color de piel", FichaCampo.TipoCampo.TEXTO, None),
            ("AREA_CORPORAL", "Area corporal", FichaCampo.TipoCampo.TEXTO, None),
            ("AREA_FACIAL", "Area facial", FichaCampo.TipoCampo.TEXTO, None),
        ]
        for order, (code, label, field_type, group) in enumerate(tattoo_fields, start=1):
            sync_field(tattoo_section, code, label, field_type, order, group)

    def _seed_prospects(self, branches):
        prospect_specs = [
            {"nombres": "Juan", "apellidos": "Perez", "telefono": "70000001", "sucursal": branches["A"]},
            {"nombres": "Maria", "apellidos": "Gomez", "telefono": "70000002", "sucursal": branches["B"]},
        ]
        for spec in prospect_specs:
            Prospecto.objects.get_or_create(
                nombres=spec["nombres"],
                apellidos=spec["apellidos"],
                defaults={
                    "telefono": spec["telefono"],
                    "sucursal_registro": spec["sucursal"],
                    "estado": Prospecto.Estado.PASAJERO,
                }
            )

    def _seed_formal_patients(self, client_role, branches):
        # Paciente INACTIVO (Demo con historial completo)
        user_demo, _ = Usuario.objects.update_or_create(
            username="paciente.demo",
            defaults={
                "primer_nombre": "Paciente",
                "apellido_paterno": "Demo",
                "email": "paciente.demo@clinic.local",
                "rol": client_role,
                "sucursal": branches["A"],
                "is_active": True,
            },
        )
        user_demo.set_password("paciente123456")
        user_demo.save()

        cliente_demo, _ = Cliente.objects.update_or_create(
            usuario=user_demo,
            defaults={
                "telefono": "78888888",
                "ci": "12345678",
                "direccion_domicilio": "Zona Central, Edif. Demo",
                "fecha_nacimiento": "1990-01-01",
                "estado_cliente": Cliente.Estado.INACTIVO,
            }
        )

        # Crear o normalizar prospecto de origen. convertido_a_cliente es OneToOne,
        # asi que debe ser la clave de idempotencia del seed.
        Prospecto.objects.update_or_create(
            convertido_a_cliente=cliente_demo,
            defaults={
                "nombres": "Paciente",
                "apellidos": "Demo",
                "telefono": "78888888",
                "sucursal_registro": branches["A"],
                "estado": Prospecto.Estado.CONVERTIDO,
                "fecha_conversion": timezone.now() - timezone.timedelta(days=40),
            }
        )

        # Simular historial pasado para que sea Inactivo legalmente
        fecha_pasada = timezone.now() - timezone.timedelta(days=30)
        
        # Operacion finalizada
        op = Operacion.objects.create(
            paciente=cliente_demo,
            servicio_config=ServicioConfig.objects.filter(proc_estetico__proceso="Depilacion definitiva").first(),
            precio_total=Decimal("850.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=fecha_pasada.date(),
            fecha_final=fecha_pasada.date(),
            estado=Operacion.Estado.FINALIZADA,
            detalles_op="Tratamiento demo completado"
        )

        # Cita realizada y confirmada
        CitaMedica.objects.create(
            operacion=op,
            sucursal=branches["A"],
            fecha_hora=fecha_pasada,
            estado=CitaMedica.Estado.CONFIRMADA,
            verif_biometria=True,
            fecha_confirmacion_biometrica=fecha_pasada,
            detalles_cita="Sesion completada satisfactoriamente"
        )

        # Pago de cuota realizado
        cuota = CuotaPlanPago.objects.create(
            operacion=op,
            nro_cuota=1,
            fecha_vencimiento=fecha_pasada.date(),
            monto_programado=Decimal("850.00"),
            estado=CuotaPlanPago.Estado.PAGADO
        )

        # Registro de pago aprobado
        admin_user = Usuario.objects.filter(is_superuser=True).first()
        PagoRealizado.objects.create(
            cuota=cuota,
            monto_pagado=Decimal("850.00"),
            comprobante_url="seed_comprobante.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado=True,
            verificado_por=admin_user,
            fecha_verificacion=fecha_pasada,
            detalles_pago="Pago total en efectivo"
        )

        # Forzar actualizacion de estado
        cliente_demo.actualizar_estado_automaticamente()

        # 3. Tratamiento NUEVO (Pendiente para hoy para probar Dashboard)
        op_hoy = Operacion.objects.create(
            paciente=cliente_demo,
            servicio_config=ServicioConfig.objects.filter(proc_estetico__proceso="Depilacion definitiva").first(),
            precio_total=Decimal("200.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=timezone.now().date(),
            estado=Operacion.Estado.EN_PROCESO,
            detalles_op="Nueva consulta de seguimiento"
        )

        CuotaPlanPago.objects.create(
            operacion=op_hoy,
            nro_cuota=1,
            fecha_vencimiento=timezone.now().date(),
            monto_programado=Decimal("200.00"),
            estado=CuotaPlanPago.Estado.PENDIENTE
        )

        # Cita para hoy
        CitaMedica.objects.create(
            operacion=op_hoy,
            sucursal=branches["A"],
            fecha_hora=timezone.now().replace(hour=10, minute=0, second=0, microsecond=0),
            estado=CitaMedica.Estado.PROGRAMADA
        )

        cliente_demo.actualizar_estado_automaticamente()

        # Huella biometrica del paciente demo
        admin_user = Usuario.objects.filter(is_superuser=True).first()
        HuellaBiometricaCliente.objects.update_or_create(
            cliente=cliente_demo,
            defaults={
                "proveedor": HuellaBiometricaCliente.Proveedor.MOCK,
                "template_biometrico": "MOCK_TEMPLATE_DEMO_abc123def456",
                "device_serial": "MOCK-DEVICE-001",
                "calidad_captura": 85,
                "consentimiento_aceptado": True,
                "activo": True,
                "registrado_por": admin_user,
                "fecha_registro": fecha_pasada,
            }
        )

        # --- SEGUNDO PACIENTE INACTIVO ---
        user_inactivo, _ = Usuario.objects.update_or_create(
            username="paciente.inactivo",
            defaults={
                "primer_nombre": "Carlos",
                "apellido_paterno": "Inactivo",
                "email": "carlos.inactivo@clinic.local",
                "rol": client_role,
                "sucursal": branches["B"],
                "is_active": True,
            },
        )
        user_inactivo.set_password("paciente123456")
        user_inactivo.save()

        cliente_inactivo, _ = Cliente.objects.update_or_create(
            usuario=user_inactivo,
            defaults={
                "telefono": "76666666",
                "ci": "87654321",
                "direccion_domicilio": "Zona Sur, Calle Inactiva",
                "fecha_nacimiento": "1985-05-15",
                "estado_cliente": Cliente.Estado.INACTIVO,
            }
        )

        # Operacion de Manchas finalizada hace 6 meses
        fecha_manchas = timezone.now() - timezone.timedelta(days=180)
        op_manchas = Operacion.objects.create(
            paciente=cliente_inactivo,
            servicio_config=ServicioConfig.objects.filter(proc_estetico__proceso="Tratamiento de manchas").first(),
            precio_total=Decimal("650.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            fecha_inicio=fecha_manchas.date(),
            fecha_final=fecha_manchas.date(),
            estado=Operacion.Estado.FINALIZADA,
            detalles_op="Tratamiento de manchas completado hace meses"
        )

        CitaMedica.objects.create(
            operacion=op_manchas,
            sucursal=branches["B"],
            fecha_hora=fecha_manchas,
            estado=CitaMedica.Estado.CONFIRMADA,
            verif_biometria=True,
            detalles_cita="Alta medica por manchas"
        )

        cuota_m = CuotaPlanPago.objects.create(
            operacion=op_manchas,
            nro_cuota=1,
            fecha_vencimiento=fecha_manchas.date(),
            monto_programado=Decimal("650.00"),
            estado=CuotaPlanPago.Estado.PAGADO
        )

        admin_user = Usuario.objects.filter(is_superuser=True).first()
        PagoRealizado.objects.create(
            cuota=cuota_m,
            monto_pagado=Decimal("650.00"),
            comprobante_url="seed_carlos_comprobante.pdf",
            estado_verificacion=PagoRealizado.EstadoVerificacion.APROBADO,
            verificado=True,
            verificado_por=admin_user,
            fecha_verificacion=fecha_manchas,
            detalles_pago="Pago de tratamiento previo de manchas"
        )

        cliente_inactivo.actualizar_estado_automaticamente()

        # Huella biometrica de Carlos
        HuellaBiometricaCliente.objects.update_or_create(
            cliente=cliente_inactivo,
            defaults={
                "proveedor": HuellaBiometricaCliente.Proveedor.MOCK,
                "template_biometrico": "MOCK_TEMPLATE_CARLOS_xyz789ghi012",
                "device_serial": "MOCK-DEVICE-002",
                "calidad_captura": 90,
                "consentimiento_aceptado": True,
                "activo": True,
                "registrado_por": admin_user,
                "fecha_registro": fecha_manchas,
            }
        )

    def _seed_tablet_kiosks(self, branches):
        kiosks = []
        for key, branch in branches.items():
            if key == "principal":
                code_suffix = "PRINCIPAL"
            elif key == "A":
                code_suffix = "NORTE"
            else:
                code_suffix = "SUR"
            codigo = f"KIOSKO-{code_suffix}"
            clave = f"tablet-{code_suffix.lower()}-123"
            kiosko, _ = TabletKiosko.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": f"Tablet {branch.nombre}",
                    "sucursal": branch,
                    "clave": clave,
                    "activo": True,
                },
            )
            kiosks.append(
                {
                    "branch": branch.nombre,
                    "codigo": kiosko.codigo,
                    "clave": clave,
                }
            )
        return kiosks

    def _seed_schedules(self, specialists):
        from datetime import time
        start_time = time(8, 0)
        end_time = time(18, 0)
        
        for specialist in specialists.values():
            # Agenda habitual de Lunes a Viernes (0 a 4)
            habitual, _ = AgendaHabitualEspecialista.objects.update_or_create(
                especialista=specialist,
                sucursal=specialist.usuario.sucursal,
                defaults={
                    "fecha_inicio": "2024-01-01",
                    "fecha_fin": "2099-12-31",
                    "hora_inicio": start_time,
                    "hora_fin": end_time,
                    "detalle": "Horario base 08:00 - 18:00",
                }
            )
            for day in range(5):
                AgendaHabitualDia.objects.update_or_create(
                    agenda=habitual,
                    dia_semana=day,
                    defaults={}
                )

    def _clear_schedule_configuration(self):
        AgendaExcepcionEspecialista.objects.all().delete()
        AgendaHabitualDia.objects.all().delete()
        AgendaHabitualEspecialista.objects.all().delete()
        DiaBloqueadoAgendaGlobal.objects.all().delete()

    def _clear_business_data(self):
        HuellaBiometricaCliente.objects.all().delete()
        PagoRealizado.objects.all().delete()
        CuotaPlanPago.objects.all().delete()
        CitaMedica.objects.all().delete()
        Operacion.objects.all().delete()

