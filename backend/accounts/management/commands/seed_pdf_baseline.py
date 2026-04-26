from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

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
)
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    DiaBloqueadoAgendaGlobal,
    DisponibilidadCita,
    FichaCampo,
    FichaSeccion,
    HorarioDisponibilidad,
)
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
        self._normalize_admin_users(roles["ADMINISTRADOR"])
        specialist_users = self._seed_specialist_users(roles["TRABAJADOR"])
        specialties, specialists = self._seed_staff(specialist_users)
        catalogs = self._seed_catalogs()
        self._seed_form_configuration(catalogs)
        self._clear_schedule_configuration()

        self.stdout.write(self.style.SUCCESS("Base PDF minima cargada correctamente."))
        self.stdout.write(
            "Resumen: "
            f"usuarios={Usuario.objects.count()}, "
            f"especialistas={Especialista.objects.count()}, "
            f"especialidades={Especialidad.objects.count()}, "
            f"tipos_servicio={TipoServicio.objects.count()}, "
            f"procedimientos={ProcEstetico.objects.count()}, "
            f"servicios_config={ServicioConfig.objects.count()}, "
            f"horarios_base={HorarioDisponibilidad.objects.count()}, "
            f"agendas_habituales={AgendaHabitualEspecialista.objects.count()}, "
            f"disponibilidades={DisponibilidadCita.objects.count()}"
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

    def _seed_roles(self):
        roles = {}
        for role_name in ("ADMINISTRADOR", "TRABAJADOR", "CLIENTE"):
            role, _ = Rol.objects.update_or_create(rol=role_name, defaults={})
            roles[role_name] = role
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

    def _seed_specialist_users(self, worker_role):
        user_specs = {
            "lucia.laser": {
                "password": "laser123456",
                "primer_nombre": "Lucia",
                "segundo_nombre": "Elena",
                "apellido_paterno": "Suarez",
                "apellido_materno": "Molina",
                "email": "lucia.laser@clinic.local",
            },
            "diego.tatuajes": {
                "password": "tatuajes123456",
                "primer_nombre": "Diego",
                "segundo_nombre": "",
                "apellido_paterno": "Roca",
                "apellido_materno": "Salinas",
                "email": "diego.tatuajes@clinic.local",
            },
            "sofia.manchas": {
                "password": "manchas123456",
                "primer_nombre": "Sofia",
                "segundo_nombre": "",
                "apellido_paterno": "Mendez",
                "apellido_materno": "Rojas",
                "email": "sofia.manchas@clinic.local",
            },
            "rafael.consulta": {
                "password": "consulta123456",
                "primer_nombre": "Rafael",
                "segundo_nombre": "",
                "apellido_paterno": "Quiroga",
                "apellido_materno": "Perez",
                "email": "rafael.consulta@clinic.local",
            },
            "elena.estetica": {
                "password": "estetica123456",
                "primer_nombre": "Elena",
                "segundo_nombre": "Maria",
                "apellido_paterno": "Salvatierra",
                "apellido_materno": "Lopez",
                "email": "elena.estetica@clinic.local",
            },
        }

        users = {}
        for username, spec in user_specs.items():
            user, created = Usuario.objects.update_or_create(
                username=username,
                defaults={
                    "primer_nombre": spec["primer_nombre"],
                    "segundo_nombre": spec["segundo_nombre"],
                    "apellido_paterno": spec["apellido_paterno"],
                    "apellido_materno": spec["apellido_materno"],
                    "email": spec["email"],
                    "rol": worker_role,
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password(spec["password"])
            user.save(update_fields=["password"])
            users[username] = user
        return users

    def _seed_staff(self, users):
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
            "elena": {
                "user": users["elena.estetica"],
                "ci": "8901234",
                "telefono": "75566778",
                "observaciones": "Apoyo clinico para depilacion, manchas y consultas.",
                "specialties": ["dermatologia_laser", "tratamiento_manchas", "consulta_medica"],
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

    def _clear_schedule_configuration(self):
        DisponibilidadCita.objects.all().delete()
        AgendaExcepcionEspecialista.objects.all().delete()
        AgendaHabitualDia.objects.all().delete()
        AgendaHabitualEspecialista.objects.all().delete()
        DiaBloqueadoAgendaGlobal.objects.all().delete()
        HorarioDisponibilidad.objects.all().delete()

