from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Rol, Usuario
from billing.models import CuotaPlanPago, PagoRealizado
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GravedadAlergia,
    GrosorPiel,
    GrupoOpciones,
    ImplanteInjerto,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    ProductoAlergia,
    ServicioConfig,
    TipoAlergia,
    TipoPiel,
    TipoServicio,
)
from clinical.models import AnalisisEstetico, AnalisisEsteticoAlergia, PatologiaPorAnalisis
from customers.models import Cliente, Prospecto
from operations.models import (
    CitaMedica,
    DisponibilidadCita,
    FichaAntecedenteMedico,
    FichaCampo,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    FichaSeccion,
    Operacion,
)
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


class Command(BaseCommand):
    help = "Carga una base demo amplia para la clinica estetica."

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        now = timezone.now()

        roles = self._seed_roles()
        users = self._seed_users(roles)
        specialties, specialists = self._seed_staff(users)
        catalogs = self._seed_catalogs()
        self._seed_form_configuration(catalogs)
        clients = self._seed_clients(users)
        self._seed_prospects(today, users, clients)
        operations = self._seed_operations(today, now, clients, specialists, catalogs, users)
        self._seed_availability(today, specialists, catalogs, operations)
        self._seed_analyses(today, clients, catalogs)

        for client in clients.values():
            client.actualizar_estado_automaticamente()

        self.stdout.write(self.style.SUCCESS("Datos demo ampliados cargados correctamente."))
        self.stdout.write(
            "Credenciales clave: "
            "admin/admin123456 | doctor.laser/doctor123456 | paciente.demo/paciente123456"
        )
        self.stdout.write(
            "Resumen: "
            f"usuarios={Usuario.objects.count()}, "
            f"clientes={Cliente.objects.count()}, "
            f"prospectos={Prospecto.objects.count()}, "
            f"especialistas={Especialista.objects.count()}, "
            f"operaciones={Operacion.objects.count()}, "
            f"citas={CitaMedica.objects.count()}, "
            f"cuotas={CuotaPlanPago.objects.count()}, "
            f"pagos={PagoRealizado.objects.count()}, "
            f"analisis={AnalisisEstetico.objects.count()}"
        )
        self.stdout.write(
            "Estados clave: "
            f"clientes_activos={Cliente.objects.filter(estado_cliente=Cliente.Estado.ACTIVO).count()}, "
            f"clientes_inactivos={Cliente.objects.filter(estado_cliente=Cliente.Estado.INACTIVO).count()}, "
            f"prospectos_pasajeros={Prospecto.objects.filter(estado=Prospecto.Estado.PASAJERO).count()}, "
            f"prospectos_convertidos={Prospecto.objects.filter(estado=Prospecto.Estado.CONVERTIDO).count()}, "
            f"prospectos_descartados={Prospecto.objects.filter(estado=Prospecto.Estado.DESCARTADO).count()}, "
            f"ops_en_proceso={Operacion.objects.filter(estado=Operacion.Estado.EN_PROCESO).count()}, "
            f"ops_finalizadas={Operacion.objects.filter(estado=Operacion.Estado.FINALIZADA).count()}, "
            f"ops_canceladas={Operacion.objects.filter(estado=Operacion.Estado.CANCELADA).count()}, "
            f"ops_borrador={Operacion.objects.filter(estado=Operacion.Estado.BORRADOR).count()}"
        )
        self.stdout.write(
            "Operaciones demo creadas: " + ", ".join(operation.detalles_op for operation in operations.values())
        )
        self.stdout.write(
            "Especialidades disponibles: " + ", ".join(specialty.nombre for specialty in specialties.values())
        )

    def _set_password(self, user, password):
        user.set_password(password)
        user.save(update_fields=["password"])

    def _stamp_instance(self, instance, created_at, updated_at=None):
        model = instance.__class__
        model.objects.filter(pk=instance.pk).update(
            created_at=created_at,
            updated_at=updated_at or created_at,
        )
        instance.created_at = created_at
        instance.updated_at = updated_at or created_at

    def _aware_datetime(self, target_date, hour, minute=0):
        return timezone.make_aware(datetime.combine(target_date, time(hour=hour, minute=minute)))

    def _seed_roles(self):
        roles = {}
        for role_name in ("ADMINISTRADOR", "TRABAJADOR", "CLIENTE"):
            role, _ = Rol.objects.update_or_create(rol=role_name, defaults={})
            roles[role_name] = role
        return roles

    def _seed_users(self, roles):
        user_specs = {
            "admin": {
                "username": "admin",
                "password": "admin123456",
                "primer_nombre": "Fabian",
                "segundo_nombre": "",
                "apellido_paterno": "Rivero",
                "apellido_materno": "",
                "email": "admin@clinic.local",
                "rol": roles["ADMINISTRADOR"],
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
            "admin_support": {
                "username": "admin.soporte",
                "password": "soporte123456",
                "primer_nombre": "Natalia",
                "segundo_nombre": "",
                "apellido_paterno": "Sanchez",
                "apellido_materno": "Flores",
                "email": "admin.soporte@clinic.local",
                "rol": roles["ADMINISTRADOR"],
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
            },
            "doctor_laser": {
                "username": "doctor.laser",
                "password": "doctor123456",
                "primer_nombre": "Lucia",
                "segundo_nombre": "Elena",
                "apellido_paterno": "Suarez",
                "apellido_materno": "Molina",
                "email": "doctor.laser@clinic.local",
                "rol": roles["TRABAJADOR"],
                "is_active": True,
            },
            "doctor_tattoo": {
                "username": "doctor.tatuaje",
                "password": "tatuaje123456",
                "primer_nombre": "Diego",
                "segundo_nombre": "",
                "apellido_paterno": "Roca",
                "apellido_materno": "Salinas",
                "email": "doctor.tatuaje@clinic.local",
                "rol": roles["TRABAJADOR"],
                "is_active": True,
            },
            "esteticista_manchas": {
                "username": "esteticista.manchas",
                "password": "manchas123456",
                "primer_nombre": "Sofia",
                "segundo_nombre": "",
                "apellido_paterno": "Mendez",
                "apellido_materno": "Rojas",
                "email": "esteticista.manchas@clinic.local",
                "rol": roles["TRABAJADOR"],
                "is_active": True,
            },
            "recepcion_demo": {
                "username": "recepcion.demo",
                "password": "recepcion123456",
                "primer_nombre": "Paola",
                "segundo_nombre": "",
                "apellido_paterno": "Medina",
                "apellido_materno": "Lopez",
                "email": "recepcion.demo@clinic.local",
                "rol": roles["TRABAJADOR"],
                "is_active": True,
            },
            "doctor_inactivo": {
                "username": "doctor.inactivo",
                "password": "inactivo123456",
                "primer_nombre": "Martin",
                "segundo_nombre": "",
                "apellido_paterno": "Ferreira",
                "apellido_materno": "Vega",
                "email": "doctor.inactivo@clinic.local",
                "rol": roles["TRABAJADOR"],
                "is_active": False,
            },
            "paciente_demo": {
                "username": "paciente.demo",
                "password": "paciente123456",
                "primer_nombre": "Maria",
                "segundo_nombre": "Fernanda",
                "apellido_paterno": "Rojas",
                "apellido_materno": "Quispe",
                "email": "paciente.demo@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_tatuaje": {
                "username": "paciente.tatuaje",
                "password": "tatuajecliente123",
                "primer_nombre": "Luciana",
                "segundo_nombre": "",
                "apellido_paterno": "Arteaga",
                "apellido_materno": "Mora",
                "email": "paciente.tatuaje@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_finalizada": {
                "username": "paciente.finalizada",
                "password": "finalizada123",
                "primer_nombre": "Valeria",
                "segundo_nombre": "",
                "apellido_paterno": "Cuellar",
                "apellido_materno": "Vargas",
                "email": "paciente.finalizada@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_cancelada": {
                "username": "paciente.cancelada",
                "password": "cancelada123",
                "primer_nombre": "Jimena",
                "segundo_nombre": "",
                "apellido_paterno": "Vaca",
                "apellido_materno": "Salazar",
                "email": "paciente.cancelada@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_borrador": {
                "username": "paciente.borrador",
                "password": "borrador123",
                "primer_nombre": "Andrea",
                "segundo_nombre": "",
                "apellido_paterno": "Serrano",
                "apellido_materno": "Mendez",
                "email": "paciente.borrador@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_inactiva": {
                "username": "paciente.inactiva",
                "password": "inactiva123",
                "primer_nombre": "Monica",
                "segundo_nombre": "",
                "apellido_paterno": "Ibanez",
                "apellido_materno": "Pardo",
                "email": "paciente.inactiva@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
            "paciente_limpieza": {
                "username": "paciente.limpieza",
                "password": "limpieza123456",
                "primer_nombre": "Camila",
                "segundo_nombre": "",
                "apellido_paterno": "Nuñez",
                "apellido_materno": "Beltran",
                "email": "paciente.limpieza@clinic.local",
                "rol": roles["CLIENTE"],
                "is_active": True,
            },
        }

        users = {}
        for key, spec in user_specs.items():
            defaults = {
                "primer_nombre": spec["primer_nombre"],
                "segundo_nombre": spec["segundo_nombre"],
                "apellido_paterno": spec["apellido_paterno"],
                "apellido_materno": spec["apellido_materno"],
                "email": spec["email"],
                "rol": spec["rol"],
                "is_active": spec["is_active"],
                "is_staff": spec.get("is_staff", False),
                "is_superuser": spec.get("is_superuser", False),
            }
            user, _ = Usuario.objects.update_or_create(
                username=spec["username"],
                defaults=defaults,
            )
            self._set_password(user, spec["password"])
            users[key] = user

        return users

    def _seed_staff(self, users):
        specialty_specs = {
            "dermatologia_laser": {
                "nombre": "Dermatologia laser",
                "descripcion": "Procedimientos con equipos laser y evaluacion de piel.",
                "orden": 1,
                "activo": True,
            },
            "medicina_estetica": {
                "nombre": "Medicina estetica",
                "descripcion": "Valoracion y acompanamiento clinico de tratamientos.",
                "orden": 2,
                "activo": True,
            },
            "borrado_tatuajes": {
                "nombre": "Borrado de tatuajes",
                "descripcion": "Procedimientos laser especializados para tatuajes.",
                "orden": 3,
                "activo": True,
            },
            "cosmetologia_clinica": {
                "nombre": "Cosmetologia clinica",
                "descripcion": "Apoyo estetico facial y protocolos complementarios.",
                "orden": 4,
                "activo": True,
            },
            "evaluacion_estetica": {
                "nombre": "Evaluacion estetica",
                "descripcion": "Analisis estetico, seguimiento y recomendaciones.",
                "orden": 5,
                "activo": True,
            },
            "microblading": {
                "nombre": "Microblading",
                "descripcion": "Especialidad inactiva para mostrar catalogos deshabilitados.",
                "orden": 6,
                "activo": False,
            },
        }

        specialties = {}
        for key, spec in specialty_specs.items():
            specialty, _ = Especialidad.objects.update_or_create(
                nombre=spec["nombre"],
                defaults={
                    "descripcion": spec["descripcion"],
                    "orden": spec["orden"],
                    "activo": spec["activo"],
                },
            )
            specialties[key] = specialty

        specialist_specs = {
            "lucia": {
                "user": users["doctor_laser"],
                "ci": "4567890",
                "telefono": "70111222",
                "observaciones": "Especialista principal en depilacion y protocolos laser.",
                "specialties": ["dermatologia_laser", "medicina_estetica"],
            },
            "diego": {
                "user": users["doctor_tattoo"],
                "ci": "5678901",
                "telefono": "72233445",
                "observaciones": "Especialista en borrado de tatuajes y seguimiento de cicatrizacion.",
                "specialties": ["borrado_tatuajes", "evaluacion_estetica"],
            },
            "sofia": {
                "user": users["esteticista_manchas"],
                "ci": "6789012",
                "telefono": "73344556",
                "observaciones": "Acompana tratamientos faciales, manchas y seguimiento de piel.",
                "specialties": ["cosmetologia_clinica", "evaluacion_estetica"],
            },
            "martin": {
                "user": users["doctor_inactivo"],
                "ci": "6899123",
                "telefono": "74422110",
                "observaciones": "Especialista inactivo conservado para demostrar historico y catalogos.",
                "specialties": ["microblading"],
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
            "tipo_piel": {},
            "deshidratacion": {},
            "grosor": {},
            "patologia": {},
            "producto_alergia": {},
            "tipo_alergia": {},
            "gravedad_alergia": {},
        }

        for key, spec in {
            "consulta": ("Consulta medica", "Valoracion inicial o controles de criterio medico.", 1, True),
            "tratamiento": ("Tratamiento estetico", "Sesiones o protocolos principales.", 2, True),
            "control": ("Control post procedimiento", "Controles posteriores o seguimiento.", 3, True),
            "evaluacion": ("Evaluacion diagnostica", "Ingreso y tamizaje de pacientes.", 4, True),
        }.items():
            item, _ = TipoServicio.objects.update_or_create(
                tipo=spec[0],
                defaults={"descripcion": spec[1], "orden": spec[2], "activo": spec[3]},
            )
            catalogs["tipo_servicio"][key] = item

        for key, spec in {
            "laser": ("Laser", "Procedimientos con tecnologia laser.", 1, True),
            "facial": ("Facial", "Protocolos correctivos faciales.", 2, True),
            "corporal": ("Corporal", "Tratamientos corporales complementarios.", 3, True),
            "plasma": ("Plasma", "Tecnologia no activa en la demo.", 4, False),
        }.items():
            item, _ = ProcEsteticosTipo.objects.update_or_create(
                tipo=spec[0],
                defaults={"descripcion": spec[1], "orden": spec[2], "activo": spec[3]},
            )
            catalogs["tipo_procedimiento"][key] = item

        procedure_specs = {
            "depilacion": ("laser", "Depilacion definitiva", "Depilacion laser por zonas.", 1, True),
            "manchas": ("laser", "Tratamiento de manchas", "Correccion de manchas con protocolo laser.", 2, True),
            "tatuajes": ("laser", "Borrado de tatuajes", "Borrado de tatuajes con sesiones laser.", 3, True),
            "peeling": ("facial", "Peeling quimico", "Protocolo facial correctivo.", 4, True),
            "limpieza": ("facial", "Limpieza profunda", "Mantenimiento facial cosmetologico.", 5, True),
            "radiofrecuencia": ("corporal", "Radiofrecuencia corporal", "Catalogo inactivo de prueba.", 6, False),
        }
        for key, spec in procedure_specs.items():
            item, _ = ProcEstetico.objects.update_or_create(
                tipo_p_estetico=catalogs["tipo_procedimiento"][spec[0]],
                proceso=spec[1],
                defaults={"descripcion": spec[2], "orden": spec[3], "activo": spec[4]},
            )
            catalogs["procedimiento"][key] = item

        service_specs = {
            "consulta_general": ("consulta", None, Decimal("120.00"), True),
            "depilacion": ("tratamiento", "depilacion", Decimal("850.00"), True),
            "manchas": ("tratamiento", "manchas", Decimal("650.00"), True),
            "tatuajes": ("tratamiento", "tatuajes", Decimal("1500.00"), True),
            "peeling": ("tratamiento", "peeling", Decimal("480.00"), True),
            "limpieza": ("tratamiento", "limpieza", Decimal("320.00"), True),
            "control_dep": ("control", "depilacion", Decimal("100.00"), True),
            "evaluacion_peeling": ("evaluacion", "peeling", Decimal("180.00"), True),
            "radiofrecuencia": ("tratamiento", "radiofrecuencia", Decimal("900.00"), False),
        }
        for key, spec in service_specs.items():
            item, _ = ServicioConfig.objects.update_or_create(
                tipo_servicio=catalogs["tipo_servicio"][spec[0]],
                proc_estetico=catalogs["procedimiento"].get(spec[1]),
                defaults={"precio_base": spec[2], "activo": spec[3]},
            )
            catalogs["servicio_config"][key] = item

        antecedent_specs = [
            "Diabetes",
            "Asma",
            "Hipertension",
            "Cancer",
            "Tiroides",
            "Lupus",
            "Embarazo",
            "Epilepsia",
            "Otro",
        ]
        for order, name in enumerate(antecedent_specs, start=1):
            item, _ = AntecedenteMedico.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Antecedente medico demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["antecedente"][name.lower().replace(" ", "_")] = item

        implant_specs = ["Menton", "Mejillas", "Nariz", "Labios", "Pomulos", "Otro"]
        for order, name in enumerate(implant_specs, start=1):
            item, _ = ImplanteInjerto.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Implante o injerto demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["implante"][name.lower()] = item

        surgery_specs = [
            "Blefaroplastia",
            "Rinoplastia",
            "Bichectomia",
            "Rinomodelacion",
            "Lifting",
            "Botox",
            "Lipoescultura",
        ]
        for order, name in enumerate(surgery_specs, start=1):
            item, _ = CirugiaEstetica.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Cirugia o procedimiento previo demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["cirugia"][name.lower()] = item

        option_groups = {
            "SI_NO": {
                "nombre": "Si / No",
                "descripcion": "Respuestas binarias.",
                "activo": True,
                "opciones": [
                    ("SI", "Si", "SI", 1, True),
                    ("NO", "No", "NO", 2, True),
                ],
            },
            "PROFUNDIDAD_TATUAJE": {
                "nombre": "Profundidad tatuaje",
                "descripcion": "Profundidad observada del tatuaje.",
                "activo": True,
                "opciones": [
                    ("SUPERFICIAL", "Superficial", "SUPERFICIAL", 1, True),
                    ("MEDIA", "Media", "MEDIA", 2, True),
                    ("PROFUNDA", "Profunda", "PROFUNDA", 3, True),
                ],
            },
            "COLOR_PIEL": {
                "nombre": "Color de piel",
                "descripcion": "Tono general de piel.",
                "activo": True,
                "opciones": [
                    ("BLANCA", "Blanca", "BLANCA", 1, True),
                    ("TRIGUENA", "Triguena", "TRIGUENA", 2, True),
                    ("MORENA", "Morena", "MORENA", 3, True),
                    ("OSCURA", "Oscura", "OSCURA", 4, True),
                    ("OLIVA", "Oliva", "OLIVA", 5, False),
                ],
            },
            "REACCIONES_PIEL": {
                "nombre": "Reacciones de piel",
                "descripcion": "Reacciones post procedimiento o exposicion.",
                "activo": True,
                "opciones": [
                    ("ENROJECIMIENTO", "Enrojecimiento", "ENROJECIMIENTO", 1, True),
                    ("PICAZON", "Picazon", "PICAZON", 2, True),
                    ("DESCAMACION", "Descamacion", "DESCAMACION", 3, True),
                    ("EDEMA", "Edema", "EDEMA", 4, True),
                    ("ARDOR", "Ardor", "ARDOR", 5, True),
                    ("NO_REGISTRADA", "No registrada", "NO_REGISTRADA", 6, False),
                ],
            },
            "SENSIBILIDAD_DOLOR": {
                "nombre": "Sensibilidad al dolor",
                "descripcion": "Percepcion reportada por paciente.",
                "activo": True,
                "opciones": [
                    ("BAJA", "Baja", "BAJA", 1, True),
                    ("MEDIA", "Media", "MEDIA", 2, True),
                    ("ALTA", "Alta", "ALTA", 3, True),
                ],
            },
            "FRECUENCIA_SOL": {
                "nombre": "Frecuencia de exposicion solar",
                "descripcion": "Habito de exposicion solar.",
                "activo": True,
                "opciones": [
                    ("BAJA", "Baja", "BAJA", 1, True),
                    ("MEDIA", "Media", "MEDIA", 2, True),
                    ("ALTA", "Alta", "ALTA", 3, True),
                ],
            },
        }

        for code, spec in option_groups.items():
            group, _ = GrupoOpciones.objects.update_or_create(
                codigo=code,
                defaults={
                    "nombre": spec["nombre"],
                    "descripcion": spec["descripcion"],
                    "activo": spec["activo"],
                },
            )
            catalogs["grupo"][code] = group
            for option_code, option_name, option_value, order, active in spec["opciones"]:
                option, _ = OpcionCatalogo.objects.update_or_create(
                    grupo=group,
                    codigo=option_code,
                    defaults={
                        "nombre": option_name,
                        "valor": option_value,
                        "orden": order,
                        "activo": active,
                    },
                )
                catalogs["opcion"][(code, option_code)] = option

        for order, name in enumerate(("Seca", "Normal", "Grasa", "Mixta", "Sensible"), start=1):
            item, _ = TipoPiel.objects.update_or_create(
                nombre=f"Piel {name.lower()}",
                defaults={
                    "descripcion": f"Tipo de piel {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["tipo_piel"][name.lower()] = item

        for order, name in enumerate(("Ninguna", "Leve", "Media", "Alta"), start=1):
            item, _ = GradoDeshidratacion.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Grado de deshidratacion {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["deshidratacion"][name.lower()] = item

        for order, name in enumerate(("Fina", "Media", "Gruesa"), start=1):
            item, _ = GrosorPiel.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Grosor de piel {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["grosor"][name.lower()] = item

        pathology_specs = [
            "Melasma",
            "Rosacea",
            "Acne",
            "Arrugas",
            "Fotoenvejecimiento",
            "Dermatitis",
            "Manchas postinflamatorias",
        ]
        for order, name in enumerate(pathology_specs, start=1):
            item, _ = PatologiaCutanea.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Patologia cutanea demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["patologia"][name.lower().replace(" ", "_")] = item

        allergy_products = ["Lidocaina", "Acido glicolico", "Acido salicilico", "Vitamina C", "Aloe vera"]
        for order, name in enumerate(allergy_products, start=1):
            item, _ = ProductoAlergia.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Producto alergeno demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["producto_alergia"][name.lower().replace(" ", "_")] = item

        allergy_types = ["Irritacion", "Urticaria", "Dermatitis de contacto", "Ardor", "Edema"]
        for order, name in enumerate(allergy_types, start=1):
            item, _ = TipoAlergia.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Tipo de alergia demo: {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["tipo_alergia"][name.lower().replace(" ", "_")] = item

        for order, name in enumerate(("Leve", "Moderada", "Grave"), start=1):
            item, _ = GravedadAlergia.objects.update_or_create(
                nombre=name,
                defaults={
                    "descripcion": f"Gravedad alergica {name.lower()}",
                    "orden": order,
                    "activo": True,
                },
            )
            catalogs["gravedad_alergia"][name.lower()] = item

        return catalogs

    def _seed_form_configuration(self, catalogs):
        removed_depilation_codes = (
            "ULTIMA_EXPOSICION_SOL",
            "AUTORIZA_FOTOGRAFIAS",
            "REACCIONES_PREVIAS",
            "FRECUENCIA_EXPOSICION_SOL",
        )

        def sync_field(seccion, codigo, etiqueta, tipo_campo, orden, grupo=None, es_multiple=False):
            return FichaCampo.objects.update_or_create(
                seccion=seccion,
                codigo=codigo,
                defaults={
                    "etiqueta": etiqueta,
                    "tipo_campo": tipo_campo,
                    "grupo_opciones": grupo,
                    "es_multiple": es_multiple,
                    "permite_detalle": False,
                    "requerido": False,
                    "orden": orden,
                    "activo": True,
                },
            )[0]

        def sync_section(proc_key, codigo, nombre, orden):
            return FichaSeccion.objects.update_or_create(
                proc_estetico=catalogs["procedimiento"][proc_key],
                codigo=codigo,
                defaults={"nombre": nombre, "orden": orden, "activo": True},
            )[0]

        for proc_key in ("depilacion", "manchas"):
            section = sync_section(proc_key, "PUNTO_D", "Depilacion definitiva / Manchas", 1)
            sync_field(section, "BRONCEADO", "Bronceado", FichaCampo.TipoCampo.SELECCION, 1, catalogs["grupo"]["SI_NO"])
            sync_field(section, "ISOTRETINOINA", "Isotretinoina", FichaCampo.TipoCampo.SELECCION, 2, catalogs["grupo"]["SI_NO"])
            sync_field(section, "DESODORANTES", "Desodorantes", FichaCampo.TipoCampo.SELECCION, 3, catalogs["grupo"]["SI_NO"])
            sync_field(section, "INFLAMATORIOS", "Antiinflamatorios", FichaCampo.TipoCampo.SELECCION, 4, catalogs["grupo"]["SI_NO"])
            sync_field(section, "DESORDEN_HORMONAL", "Desorden hormonal", FichaCampo.TipoCampo.SELECCION, 5, catalogs["grupo"]["SI_NO"])
            sync_field(section, "DIABETES", "Diabetes (Metformina)", FichaCampo.TipoCampo.SELECCION, 6, catalogs["grupo"]["SI_NO"])
            sync_field(section, "HIPOTIROIDISMO", "Hipotiroidismo", FichaCampo.TipoCampo.SELECCION, 7, catalogs["grupo"]["SI_NO"])
            sync_field(section, "KETOCONAZOL", "Ketoconazol", FichaCampo.TipoCampo.SELECCION, 8, catalogs["grupo"]["SI_NO"])
            sync_field(section, "DIURETICOS", "Diureticos", FichaCampo.TipoCampo.SELECCION, 9, catalogs["grupo"]["SI_NO"])
            sync_field(section, "TIPO_VELLO", "Tipo de vello", FichaCampo.TipoCampo.TEXTO, 10)
            sync_field(section, "COLOR_VELLO", "Color de vello", FichaCampo.TipoCampo.TEXTO, 11)
            sync_field(section, "GROSOR_VELLO", "Grosor de vello", FichaCampo.TipoCampo.TEXTO, 12)
            FichaCampo.objects.filter(seccion=section, codigo__in=removed_depilation_codes).update(activo=False)

        tattoo_section = sync_section("tatuajes", "PUNTO_E", "Borrado de tatuajes", 1)
        sync_field(tattoo_section, "MESES_ANTIGUEDAD", "Meses de antiguedad", FichaCampo.TipoCampo.NUMERO, 1)
        sync_field(
            tattoo_section,
            "PROFUNDIDAD_TATUAJE",
            "Profundidad del tatuaje",
            FichaCampo.TipoCampo.SELECCION,
            2,
            catalogs["grupo"]["PROFUNDIDAD_TATUAJE"],
        )
        sync_field(tattoo_section, "COLOR_TATUAJE", "Color del tatuaje", FichaCampo.TipoCampo.TEXTO, 3)
        sync_field(tattoo_section, "TIPO_CICATRIZACION", "Tipo de cicatrizacion", FichaCampo.TipoCampo.TEXTO, 4)
        sync_field(
            tattoo_section,
            "PROTECTOR_SOLAR",
            "Usa protector solar",
            FichaCampo.TipoCampo.SELECCION,
            5,
            catalogs["grupo"]["SI_NO"],
        )
        sync_field(tattoo_section, "OTROS_CUIDADOS", "Otros cuidados", FichaCampo.TipoCampo.TEXTO, 6)
        sync_field(
            tattoo_section,
            "COLOR_PIEL",
            "Color de piel",
            FichaCampo.TipoCampo.SELECCION,
            7,
            catalogs["grupo"]["COLOR_PIEL"],
        )
        sync_field(tattoo_section, "ZONA_GENERAL", "Zona general del tatuaje", FichaCampo.TipoCampo.TEXTO, 8)
        sync_field(tattoo_section, "ZONA_ESPECIFICA", "Zona especifica del tatuaje", FichaCampo.TipoCampo.TEXTO, 9)
        sync_field(tattoo_section, "FUE_RETOCADO", "Fue retocado", FichaCampo.TipoCampo.BOOLEANO, 10)
        sync_field(tattoo_section, "FECHA_ULTIMO_RETOQUE", "Fecha del ultimo retoque", FichaCampo.TipoCampo.FECHA, 11)
        sync_field(
            tattoo_section,
            "SENSIBILIDAD_DOLOR",
            "Sensibilidad al dolor",
            FichaCampo.TipoCampo.SELECCION,
            12,
            catalogs["grupo"]["SENSIBILIDAD_DOLOR"],
        )

        peeling_section = sync_section("peeling", "PEELING_BASE", "Evaluacion de peeling", 1)
        sync_field(
            peeling_section,
            "USO_RETINOL",
            "Uso de retinol",
            FichaCampo.TipoCampo.SELECCION,
            1,
            catalogs["grupo"]["SI_NO"],
        )
        sync_field(
            peeling_section,
            "NIVEL_SENSIBILIDAD",
            "Nivel de sensibilidad",
            FichaCampo.TipoCampo.SELECCION,
            2,
            catalogs["grupo"]["SENSIBILIDAD_DOLOR"],
        )
        sync_field(
            peeling_section,
            "REACCIONES_PREVIAS",
            "Reacciones previas",
            FichaCampo.TipoCampo.MULTISELECCION,
            3,
            catalogs["grupo"]["REACCIONES_PIEL"],
            es_multiple=True,
        )
        sync_field(peeling_section, "ULTIMA_EXPOSICION_SOL", "Ultima exposicion solar", FichaCampo.TipoCampo.FECHA, 4)
        sync_field(peeling_section, "OBJETIVO_TRATAMIENTO", "Objetivo del tratamiento", FichaCampo.TipoCampo.TEXTO, 5)

        limpieza_section = sync_section("limpieza", "LIMPIEZA_BASE", "Evaluacion de limpieza profunda", 1)
        sync_field(
            limpieza_section,
            "PIEL_REACTIVA",
            "Piel reactiva",
            FichaCampo.TipoCampo.SELECCION,
            1,
            catalogs["grupo"]["SI_NO"],
        )
        sync_field(
            limpieza_section,
            "EXTRACCIONES_RECIENTES",
            "Extracciones recientes",
            FichaCampo.TipoCampo.SELECCION,
            2,
            catalogs["grupo"]["SI_NO"],
        )
        sync_field(
            limpieza_section,
            "NIVEL_SENSIBILIDAD",
            "Nivel de sensibilidad",
            FichaCampo.TipoCampo.SELECCION,
            3,
            catalogs["grupo"]["SENSIBILIDAD_DOLOR"],
        )
        sync_field(
            limpieza_section,
            "PRODUCTOS_ACTUALES",
            "Productos actuales",
            FichaCampo.TipoCampo.TEXTO,
            4,
        )
        sync_field(
            limpieza_section,
            "AUTORIZA_FOTOGRAFIAS",
            "Autoriza fotografias",
            FichaCampo.TipoCampo.BOOLEANO,
            5,
        )
        sync_field(
            limpieza_section,
            "REACCIONES_PREVIAS",
            "Reacciones previas",
            FichaCampo.TipoCampo.MULTISELECCION,
            6,
            catalogs["grupo"]["REACCIONES_PIEL"],
            es_multiple=True,
        )
        sync_field(
            limpieza_section,
            "OBJETIVO_TRATAMIENTO",
            "Objetivo del tratamiento",
            FichaCampo.TipoCampo.TEXTO,
            7,
        )

    def _seed_clients(self, users):
        client_specs = {
            "maria": {
                "user": users["paciente_demo"],
                "ci": "7894561",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0001",
                "fecha_nacimiento": date(1992, 6, 14),
                "nro_hijos": 1,
                "direccion_domicilio": "Zona Sur, Calle 12 #45",
                "telefono": "76543210",
                "ocupacion": "Arquitecta",
                "observaciones": "Cliente demo principal para depilacion.",
            },
            "luciana": {
                "user": users["paciente_tatuaje"],
                "ci": "8123456",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0002",
                "fecha_nacimiento": date(1989, 10, 9),
                "nro_hijos": 2,
                "direccion_domicilio": "Equipetrol, Edificio Terra 5B",
                "telefono": "72100122",
                "ocupacion": "Abogada",
                "observaciones": "Cliente demo enfocada en borrado de tatuajes.",
            },
            "valeria": {
                "user": users["paciente_finalizada"],
                "ci": "9345678",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0003",
                "fecha_nacimiento": date(1995, 2, 21),
                "nro_hijos": 0,
                "direccion_domicilio": "Norte, Condominio Magnolia",
                "telefono": "73455667",
                "ocupacion": "Ingeniera comercial",
                "observaciones": "Cliente con tratamiento finalizado.",
            },
            "jimena": {
                "user": users["paciente_cancelada"],
                "ci": "8456123",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0004",
                "fecha_nacimiento": date(1991, 8, 30),
                "nro_hijos": 3,
                "direccion_domicilio": "Av. Alemana, Condominio Nativa",
                "telefono": "71122334",
                "ocupacion": "Docente",
                "observaciones": "Cliente con operacion cancelada.",
            },
            "andrea": {
                "user": users["paciente_borrador"],
                "ci": "7567894",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0005",
                "fecha_nacimiento": date(1998, 1, 17),
                "nro_hijos": 0,
                "direccion_domicilio": "Zona Oeste, Calle Libertad",
                "telefono": "74566778",
                "ocupacion": "Disenadora grafica",
                "observaciones": "Cliente con venta en borrador.",
            },
            "monica": {
                "user": users["paciente_inactiva"],
                "ci": "6987452",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0006",
                "fecha_nacimiento": date(1987, 12, 4),
                "nro_hijos": 2,
                "direccion_domicilio": "Zona Centro, Barrio Urubo",
                "telefono": "75677889",
                "ocupacion": "Empresaria",
                "observaciones": "Cliente inactiva con historial clinico.",
            },
            "camila": {
                "user": users["paciente_limpieza"],
                "ci": "7345211",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0007",
                "fecha_nacimiento": date(1996, 11, 11),
                "nro_hijos": 0,
                "direccion_domicilio": "Barrio Sirari, Torre Magnolia",
                "telefono": "70998877",
                "ocupacion": "Auditora",
                "observaciones": "Cliente demo de limpieza profunda con varios comprobantes por cuota.",
            },
        }

        clients = {}
        for key, spec in client_specs.items():
            client, _ = Cliente.objects.update_or_create(
                usuario=spec["user"],
                defaults={
                    "ci": spec["ci"],
                    "estado_cliente": spec["estado_cliente"],
                    "cod_biometrico": spec["cod_biometrico"],
                    "fecha_nacimiento": spec["fecha_nacimiento"],
                    "nro_hijos": spec["nro_hijos"],
                    "direccion_domicilio": spec["direccion_domicilio"],
                    "telefono": spec["telefono"],
                    "ocupacion": spec["ocupacion"],
                    "observaciones": spec["observaciones"],
                },
            )
            clients[key] = client

        return clients

    def _seed_prospects(self, today, users, clients):
        prospect_specs = {
            "carla": {
                "nombres": "Carla",
                "apellidos": "Flores",
                "telefono": "70000001",
                "estado": Prospecto.Estado.PASAJERO,
                "observaciones": "Consulta por depilacion definitiva en piernas y axilas.",
                "registrado_por": users["recepcion_demo"],
                "convertido": None,
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=1), time(15, 30))),
            },
            "angela": {
                "nombres": "Angela",
                "apellidos": "Rocha",
                "telefono": "",
                "estado": Prospecto.Estado.PASAJERO,
                "observaciones": "Llego a preguntar por tratamiento de manchas. Aun no desea dejar telefono.",
                "registrado_por": users["recepcion_demo"],
                "convertido": None,
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=12), time(11, 0))),
            },
            "maria": {
                "nombres": "Maria Fernanda",
                "apellidos": "Rojas Quispe",
                "telefono": clients["maria"].telefono,
                "estado": Prospecto.Estado.CONVERTIDO,
                "observaciones": "Prospecto convertido a cliente de depilacion definitiva.",
                "registrado_por": users["doctor_laser"],
                "convertido": clients["maria"],
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=90), time(9, 20))),
            },
            "luciana": {
                "nombres": "Luciana",
                "apellidos": "Arteaga Mora",
                "telefono": clients["luciana"].telefono,
                "estado": Prospecto.Estado.CONVERTIDO,
                "observaciones": "Ingreso por borrado de tatuajes luego de una valoracion previa.",
                "registrado_por": users["doctor_tattoo"],
                "convertido": clients["luciana"],
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=40), time(17, 10))),
            },
            "natalia": {
                "nombres": "Natalia",
                "apellidos": "Mendez",
                "telefono": "69912344",
                "estado": Prospecto.Estado.DESCARTADO,
                "observaciones": "Solicito presupuesto y no continuo con el tratamiento.",
                "registrado_por": users["recepcion_demo"],
                "convertido": None,
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=18), time(13, 45))),
            },
            "camila": {
                "nombres": "Camila",
                "apellidos": "Nuñez Beltran",
                "telefono": clients["camila"].telefono,
                "estado": Prospecto.Estado.CONVERTIDO,
                "observaciones": "Se convirtio luego de una prueba facial y compra de limpieza profunda.",
                "registrado_por": users["esteticista_manchas"],
                "convertido": clients["camila"],
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=14), time(10, 10))),
            },
            "raul": {
                "nombres": "Raul",
                "apellidos": "Montaño",
                "telefono": "78800123",
                "estado": Prospecto.Estado.PASAJERO,
                "observaciones": "Solicita paquete facial y aun espera una promocion especial.",
                "registrado_por": users["recepcion_demo"],
                "convertido": None,
                "created_at": timezone.make_aware(datetime.combine(today - timedelta(days=25), time(16, 5))),
            },
        }

        for spec in prospect_specs.values():
            defaults = {
                "telefono": spec["telefono"],
                "estado": spec["estado"],
                "observaciones": spec["observaciones"],
                "registrado_por": spec["registrado_por"],
                "convertido_a_cliente": spec["convertido"],
                "fecha_conversion": spec["created_at"] if spec["estado"] == Prospecto.Estado.CONVERTIDO else None,
            }

            if spec["convertido"]:
                prospect = (
                    Prospecto.objects.filter(convertido_a_cliente=spec["convertido"]).first()
                    or Prospecto.objects.filter(
                        nombres=spec["nombres"],
                        apellidos=spec["apellidos"],
                    ).first()
                )
                if prospect:
                    for field, value in defaults.items():
                        setattr(prospect, field, value)
                    prospect.nombres = spec["nombres"]
                    prospect.apellidos = spec["apellidos"]
                    prospect.save()
                else:
                    prospect = Prospecto.objects.create(
                        nombres=spec["nombres"],
                        apellidos=spec["apellidos"],
                        **defaults,
                    )
            else:
                prospect, _ = Prospecto.objects.update_or_create(
                    nombres=spec["nombres"],
                    apellidos=spec["apellidos"],
                    defaults=defaults,
                )
            self._stamp_instance(prospect, spec["created_at"], spec["created_at"] + timedelta(hours=1))
            if spec["estado"] == Prospecto.Estado.CONVERTIDO and spec["convertido"]:
                prospect.convertido_a_cliente = spec["convertido"]
                prospect.estado = Prospecto.Estado.CONVERTIDO
                prospect.fecha_conversion = spec["created_at"] + timedelta(days=2)
                prospect.save(
                    update_fields=[
                        "convertido_a_cliente",
                        "estado",
                        "fecha_conversion",
                        "updated_at",
                    ]
                )

    def _prepare_ficha(self, operation, fecha_ficha, motivo_consulta, observaciones, firma_ci):
        ficha, _ = FichaClinica.objects.update_or_create(
            operacion=operation,
            defaults={
                "fecha_ficha": fecha_ficha,
                "motivo_consulta": motivo_consulta,
                "observaciones": observaciones,
                "firma_paciente_ci": firma_ci,
                "firma_paciente_url": f"firmas/demo-operacion-{operation.pk}.png",
                "consentimiento_aceptado": True,
            },
        )
        ficha.antecedentes.all().delete()
        ficha.implantes.all().delete()
        ficha.cirugias.all().delete()
        ficha.respuestas_campos.all().delete()
        return ficha

    def _set_field_response(
        self,
        ficha,
        codigo,
        *,
        valor_texto="",
        valor_numero=None,
        valor_fecha=None,
        valor_booleano=None,
        detalle="",
        option_codes=None,
    ):
        campo = FichaCampo.objects.get(
            codigo=codigo,
            seccion__proc_estetico=ficha.operacion.servicio_config.proc_estetico,
            activo=True,
        )
        respuesta, _ = FichaRespuestaCampo.objects.update_or_create(
            ficha=ficha,
            campo=campo,
            defaults={
                "valor_texto": valor_texto,
                "valor_numero": valor_numero,
                "valor_fecha": valor_fecha,
                "valor_booleano": valor_booleano,
                "detalle": detalle,
            },
        )

        if option_codes:
            options = list(
                OpcionCatalogo.objects.filter(
                    grupo=campo.grupo_opciones,
                    codigo__in=option_codes,
                )
            )
            for option in options:
                FichaRespuestaOpcion.objects.get_or_create(respuesta=respuesta, opcion=option)

    def _add_antecedente(self, ficha, antecedente, tipo, detalle=""):
        FichaAntecedenteMedico.objects.get_or_create(
            ficha=ficha,
            antecedente=antecedente,
            tipo_antecedente=tipo,
            defaults={"detalle": detalle},
        )

    def _add_implante(self, ficha, implante, detalle=""):
        FichaImplanteInjerto.objects.get_or_create(
            ficha=ficha,
            implante=implante,
            defaults={"detalle": detalle},
        )

    def _add_cirugia(self, ficha, cirugia, hace_cuanto_tiempo="", detalle=""):
        FichaCirugiaEstetica.objects.get_or_create(
            ficha=ficha,
            cirugia=cirugia,
            defaults={"hace_cuanto_tiempo": hace_cuanto_tiempo, "detalle": detalle},
        )

    def _add_cita(self, operation, specialist, dt, estado, detalles, verif_biometria=False):
        return CitaMedica.objects.create(
            operacion=operation,
            medico=specialist,
            fecha_hora=dt,
            estado=estado,
            verif_biometria=verif_biometria,
            detalles_cita=detalles,
        )

    def _upsert_availability_slot(
        self,
        specialist,
        dt,
        *,
        service_types=None,
        procedure_types=None,
        procedures=None,
        active=True,
        detail="",
        appointment=None,
    ):
        slot, _ = DisponibilidadCita.objects.update_or_create(
            especialista=specialist,
            fecha_hora=dt,
            defaults={"activo": active, "detalle": detail},
        )
        slot.tipos_servicio.set(service_types or [])
        slot.tipos_proc_estetico.set(procedure_types or [])
        slot.procedimientos_esteticos.set(procedures or [])
        if appointment and appointment.disponibilidad_id != slot.pk:
            appointment.disponibilidad = slot
            appointment.save(update_fields=["disponibilidad"])
        return slot

    def _add_cuota(self, operation, nro_cuota, fecha_vencimiento, payments):
        cuota = CuotaPlanPago.objects.create(
            operacion=operation,
            nro_cuota=nro_cuota,
            fecha_vencimiento=fecha_vencimiento,
            estado=CuotaPlanPago.Estado.PENDIENTE,
        )

        for payment_spec in payments:
            payment = PagoRealizado.objects.create(
                cuota=cuota,
                monto_pagado=payment_spec["monto_pagado"],
                comprobante_url=payment_spec["comprobante_url"],
                estado_verificacion=payment_spec["estado_verificacion"],
                verificado=payment_spec["estado_verificacion"] == PagoRealizado.EstadoVerificacion.APROBADO,
                verificado_por=payment_spec.get("verificado_por"),
                fecha_verificacion=payment_spec.get("fecha_verificacion"),
                detalles_pago=payment_spec.get("detalles_pago", ""),
                observacion_verificacion=payment_spec.get("observacion_verificacion", ""),
            )
            if payment_spec.get("created_at"):
                self._stamp_instance(payment, payment_spec["created_at"], payment_spec["created_at"])

        cuota.actualizar_estado_por_pagos()
        return cuota

    def _seed_operations(self, today, now, clients, specialists, catalogs, users):
        operation_specs = {
            "depilacion_activa": {
                "paciente": clients["maria"],
                "servicio_config": catalogs["servicio_config"]["depilacion"],
                "zona_general": "Axilas",
                "zona_especifica": "Ambas axilas",
                "precio_total": Decimal("850.00"),
                "cuotas_totales": 2,
                "sesiones_totales": 4,
                "fecha_inicio": today - timedelta(days=45),
                "fecha_final": None,
                "estado": Operacion.Estado.EN_PROCESO,
                "detalles_op": "[DEMO-A1] Depilacion definitiva en axilas con seguimiento mensual.",
                "recomendaciones": "Evitar cera, rasurar 24 horas antes y usar protector solar.",
                "created_at": now - timedelta(days=45),
            },
            "tatuaje_bloqueado": {
                "paciente": clients["luciana"],
                "servicio_config": catalogs["servicio_config"]["tatuajes"],
                "zona_general": "Brazo",
                "zona_especifica": "Antebrazo derecho",
                "precio_total": Decimal("1500.00"),
                "cuotas_totales": 3,
                "sesiones_totales": 3,
                "fecha_inicio": today - timedelta(days=60),
                "fecha_final": None,
                "estado": Operacion.Estado.EN_PROCESO,
                "detalles_op": "[DEMO-B1] Borrado de tatuaje con sesiones consumidas y reserva bloqueada.",
                "recomendaciones": "No exponer la zona a calor extremo ni retirar costras.",
                "created_at": now - timedelta(days=60),
            },
            "manchas_finalizada": {
                "paciente": clients["valeria"],
                "servicio_config": catalogs["servicio_config"]["manchas"],
                "zona_general": "Rostro",
                "zona_especifica": "Mejillas y frente",
                "precio_total": Decimal("1300.00"),
                "cuotas_totales": 2,
                "sesiones_totales": 4,
                "fecha_inicio": today - timedelta(days=180),
                "fecha_final": today - timedelta(days=30),
                "estado": Operacion.Estado.FINALIZADA,
                "detalles_op": "[DEMO-C1] Tratamiento de manchas completado con alta clinica.",
                "recomendaciones": "Mantener rutina despigmentante y control semestral.",
                "created_at": now - timedelta(days=180),
            },
            "depilacion_cancelada": {
                "paciente": clients["jimena"],
                "servicio_config": catalogs["servicio_config"]["depilacion"],
                "zona_general": "Piernas",
                "zona_especifica": "Pierna completa",
                "precio_total": Decimal("1700.00"),
                "cuotas_totales": 1,
                "sesiones_totales": 2,
                "fecha_inicio": today - timedelta(days=90),
                "fecha_final": today - timedelta(days=60),
                "estado": Operacion.Estado.CANCELADA,
                "detalles_op": "[DEMO-D1] Tratamiento cancelado por falta de continuidad y criterios medicos.",
                "recomendaciones": "Requiere nueva valoracion antes de reactivar cualquier reserva.",
                "created_at": now - timedelta(days=90),
            },
            "peeling_borrador": {
                "paciente": clients["andrea"],
                "servicio_config": catalogs["servicio_config"]["peeling"],
                "zona_general": "Rostro",
                "zona_especifica": "Zona T",
                "precio_total": Decimal("480.00"),
                "cuotas_totales": 1,
                "sesiones_totales": 1,
                "fecha_inicio": today + timedelta(days=5),
                "fecha_final": None,
                "estado": Operacion.Estado.BORRADOR,
                "detalles_op": "[DEMO-E1] Venta en borrador para peeling quimico facial.",
                "recomendaciones": "Completar valoracion y firma antes de activar el tratamiento.",
                "created_at": now - timedelta(days=4),
            },
            "limpieza_activa": {
                "paciente": clients["camila"],
                "servicio_config": catalogs["servicio_config"]["limpieza"],
                "zona_general": "Rostro",
                "zona_especifica": "Mejillas, menton y zona T",
                "precio_total": Decimal("320.00"),
                "cuotas_totales": 2,
                "sesiones_totales": 2,
                "fecha_inicio": today - timedelta(days=12),
                "fecha_final": None,
                "estado": Operacion.Estado.EN_PROCESO,
                "detalles_op": "[DEMO-F1] Limpieza profunda activa con varias respuestas y pagos sobre una misma cuota.",
                "recomendaciones": "Evitar exfoliantes durante 72 horas y reforzar hidratacion.",
                "created_at": now - timedelta(days=12),
            },
            "consulta_historial": {
                "paciente": clients["monica"],
                "servicio_config": catalogs["servicio_config"]["consulta_general"],
                "zona_general": "Consulta",
                "zona_especifica": "Valoracion integral",
                "precio_total": Decimal("120.00"),
                "cuotas_totales": 1,
                "sesiones_totales": 1,
                "fecha_inicio": today - timedelta(days=22),
                "fecha_final": today - timedelta(days=22),
                "estado": Operacion.Estado.FINALIZADA,
                "detalles_op": "[DEMO-G1] Consulta general cerrada para demostrar servicios sin procedimiento asociado.",
                "recomendaciones": "Mantener controles anuales y actualizar antecedentes clinicos.",
                "created_at": now - timedelta(days=22),
            },
        }

        operations = {}
        for key, spec in operation_specs.items():
            operation, _ = Operacion.objects.update_or_create(
                paciente=spec["paciente"],
                servicio_config=spec["servicio_config"],
                detalles_op=spec["detalles_op"],
                defaults={
                    "zona_general": spec["zona_general"],
                    "zona_especifica": spec["zona_especifica"],
                    "precio_total": spec["precio_total"],
                    "cuotas_totales": spec["cuotas_totales"],
                    "sesiones_totales": spec["sesiones_totales"],
                    "fecha_inicio": spec["fecha_inicio"],
                    "fecha_final": spec["fecha_final"],
                    "estado": spec["estado"],
                    "recomendaciones": spec["recomendaciones"],
                },
            )
            self._stamp_instance(operation, spec["created_at"], spec["created_at"] + timedelta(hours=6))
            operation.citas_medicas.all().delete()
            operation.cuotas_plan_pagos.all().delete()
            operations[key] = operation

        self._seed_operation_depilacion(today, now, operations["depilacion_activa"], catalogs, specialists, users)
        self._seed_operation_tatuaje(today, now, operations["tatuaje_bloqueado"], catalogs, specialists, users)
        self._seed_operation_manchas(today, now, operations["manchas_finalizada"], catalogs, specialists, users)
        self._seed_operation_cancelada(today, now, operations["depilacion_cancelada"], catalogs, specialists, users)
        self._seed_operation_borrador(today, now, operations["peeling_borrador"], catalogs, specialists, users)
        self._seed_operation_limpieza(today, now, operations["limpieza_activa"], catalogs, specialists, users)
        self._seed_operation_consulta(today, now, operations["consulta_historial"], specialists, users)

        return operations

    def _seed_operation_depilacion(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=42),
            "Desea reducir vello axilar y mejorar tolerancia al rasurado.",
            "Paciente apta para protocolo demo de depilacion.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=42), now - timedelta(days=42))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["diabetes"],
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            "Madre con antecedente controlado.",
        )
        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["asma"],
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            "Asma leve durante la adolescencia.",
        )
        self._add_cirugia(
            ficha,
            catalogs["cirugia"]["botox"],
            "8 meses",
            "Botox facial sin complicaciones.",
        )

        self._set_field_response(ficha, "BRONCEADO", option_codes=["NO"])
        self._set_field_response(ficha, "ISOTRETINOINA", option_codes=["NO"])
        self._set_field_response(ficha, "DESODORANTES", option_codes=["SI"], detalle="Uso diario.")
        self._set_field_response(ficha, "INFLAMATORIOS", option_codes=["NO"])
        self._set_field_response(
            ficha,
            "DESORDEN_HORMONAL",
            option_codes=["SI"],
            detalle="SOP en seguimiento ginecologico.",
        )
        self._set_field_response(ficha, "DIABETES", option_codes=["NO"])
        self._set_field_response(ficha, "HIPOTIROIDISMO", option_codes=["NO"])
        self._set_field_response(ficha, "KETOCONAZOL", option_codes=["NO"])
        self._set_field_response(ficha, "DIURETICOS", option_codes=["NO"])
        self._set_field_response(ficha, "TIPO_VELLO", valor_texto="Terminal")
        self._set_field_response(ficha, "COLOR_VELLO", valor_texto="Oscuro")
        self._set_field_response(ficha, "GROSOR_VELLO", valor_texto="Medio")

        self._add_cita(
            operation,
            specialists["lucia"],
            self._aware_datetime(today - timedelta(days=25), 10, 0),
            CitaMedica.Estado.CONFIRMADA,
            "Sesion 1 confirmada con biometria.",
            verif_biometria=True,
        )
        self._add_cita(
            operation,
            specialists["lucia"],
            self._aware_datetime(today + timedelta(days=7), 16, 0),
            CitaMedica.Estado.PROGRAMADA,
            "Sesion 2 programada.",
        )
        self._add_cita(
            operation,
            specialists["lucia"],
            self._aware_datetime(today + timedelta(days=14), 16, 30),
            CitaMedica.Estado.CANCELADA,
            "Reprogramacion solicitada por la paciente.",
        )

        self._add_cuota(
            operation,
            1,
            today + timedelta(days=5),
            [
                {
                    "monto_pagado": Decimal("425.00"),
                    "comprobante_url": "comprobantes/demo-depilacion-cuota-1.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.PENDIENTE,
                    "detalles_pago": "Transferencia reportada por la paciente y pendiente de revision.",
                    "created_at": now - timedelta(days=2),
                }
            ],
        )
        self._add_cuota(operation, 2, today + timedelta(days=35), [])

    def _seed_operation_tatuaje(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=58),
            "Desea aclarar y retirar tatuaje en antebrazo derecho.",
            "Paciente con antecedente de rinomodelacion y tatuaje retocado.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=58), now - timedelta(days=58))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["cancer"],
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            "Antecedente en abuelo materno.",
        )
        self._add_implante(ficha, catalogs["implante"]["nariz"], "Rinomodelacion previa sin eventos.")
        self._add_cirugia(
            ficha,
            catalogs["cirugia"]["rinoplastia"],
            "2 anos",
            "Paciente refiere buena cicatrizacion posterior.",
        )

        self._set_field_response(ficha, "MESES_ANTIGUEDAD", valor_numero=Decimal("48"))
        self._set_field_response(ficha, "PROFUNDIDAD_TATUAJE", option_codes=["MEDIA"])
        self._set_field_response(ficha, "COLOR_TATUAJE", valor_texto="Negro y rojo")
        self._set_field_response(ficha, "TIPO_CICATRIZACION", valor_texto="Lenta")
        self._set_field_response(ficha, "PROTECTOR_SOLAR", option_codes=["SI"])
        self._set_field_response(
            ficha,
            "OTROS_CUIDADOS",
            valor_texto="Uso crema regeneradora y evita friccion en la zona.",
        )
        self._set_field_response(ficha, "COLOR_PIEL", option_codes=["TRIGUENA"])
        self._set_field_response(ficha, "ZONA_GENERAL", valor_texto="Brazo")
        self._set_field_response(ficha, "ZONA_ESPECIFICA", valor_texto="Antebrazo derecho")
        self._set_field_response(ficha, "FUE_RETOCADO", valor_booleano=True)
        self._set_field_response(ficha, "FECHA_ULTIMO_RETOQUE", valor_fecha=today - timedelta(days=540))
        self._set_field_response(ficha, "SENSIBILIDAD_DOLOR", option_codes=["ALTA"])

        self._add_cita(
            operation,
            specialists["diego"],
            self._aware_datetime(today - timedelta(days=40), 9, 0),
            CitaMedica.Estado.CONFIRMADA,
            "Sesion 1 confirmada con biometria.",
            verif_biometria=True,
        )
        self._add_cita(
            operation,
            specialists["diego"],
            self._aware_datetime(today - timedelta(days=5), 10, 30),
            CitaMedica.Estado.REALIZADA_PENDIENTE_BIOMETRIA,
            "Sesion 2 realizada, esperando verificacion biometrica.",
        )
        self._add_cita(
            operation,
            specialists["diego"],
            self._aware_datetime(today + timedelta(days=10), 11, 0),
            CitaMedica.Estado.PROGRAMADA,
            "Sesion 3 programada.",
        )
        self._add_cita(
            operation,
            specialists["diego"],
            self._aware_datetime(today - timedelta(days=18), 9, 45),
            CitaMedica.Estado.NO_ASISTIO,
            "Paciente no asistio a control intermedio.",
        )
        self._add_cita(
            operation,
            specialists["diego"],
            self._aware_datetime(today + timedelta(days=18), 11, 30),
            CitaMedica.Estado.CANCELADA,
            "Reserva extra cancelada por falta de cupo.",
        )

        self._add_cuota(
            operation,
            1,
            today - timedelta(days=30),
            [
                {
                    "monto_pagado": Decimal("500.00"),
                    "comprobante_url": "comprobantes/demo-tatuaje-cuota-1.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.APROBADO,
                    "verificado_por": users["admin"],
                    "fecha_verificacion": now - timedelta(days=29),
                    "detalles_pago": "Transferencia confirmada por administracion.",
                    "observacion_verificacion": "Monto correcto y acreditado.",
                    "created_at": now - timedelta(days=31),
                }
            ],
        )
        self._add_cuota(
            operation,
            2,
            today - timedelta(days=2),
            [
                {
                    "monto_pagado": Decimal("500.00"),
                    "comprobante_url": "comprobantes/demo-tatuaje-cuota-2.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.RECHAZADO,
                    "verificado_por": users["admin_support"],
                    "fecha_verificacion": now - timedelta(days=1),
                    "detalles_pago": "Comprobante ilegible.",
                    "observacion_verificacion": "El comprobante no muestra titular ni referencia completa.",
                    "created_at": now - timedelta(days=3),
                }
            ],
        )
        self._add_cuota(operation, 3, today + timedelta(days=25), [])

    def _seed_operation_manchas(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=175),
            "Desea aclarar melasma y manchas postinflamatorias.",
            "Tratamiento concluido con buena adherencia.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=175), now - timedelta(days=175))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["hipertension"],
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            "Padre hipertenso controlado.",
        )
        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["asma"],
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            "Asma ocasional sin medicacion continua.",
        )
        self._add_cirugia(
            ficha,
            catalogs["cirugia"]["blefaroplastia"],
            "3 anos",
            "Sin eventos posteriores relevantes.",
        )

        self._set_field_response(ficha, "BRONCEADO", option_codes=["NO"])
        self._set_field_response(ficha, "ISOTRETINOINA", option_codes=["NO"])
        self._set_field_response(ficha, "DESODORANTES", option_codes=["NO"])
        self._set_field_response(ficha, "INFLAMATORIOS", option_codes=["SI"], detalle="Ibuprofeno eventual.")
        self._set_field_response(ficha, "DESORDEN_HORMONAL", option_codes=["NO"])
        self._set_field_response(ficha, "DIABETES", option_codes=["NO"])
        self._set_field_response(ficha, "HIPOTIROIDISMO", option_codes=["SI"], detalle="Levotiroxina diaria.")
        self._set_field_response(ficha, "KETOCONAZOL", option_codes=["NO"])
        self._set_field_response(ficha, "DIURETICOS", option_codes=["NO"])
        self._set_field_response(ficha, "TIPO_VELLO", valor_texto="Fino")
        self._set_field_response(ficha, "COLOR_VELLO", valor_texto="Castano")
        self._set_field_response(ficha, "GROSOR_VELLO", valor_texto="Fino")

        for offset in (150, 120, 90, 60):
            self._add_cita(
                operation,
                specialists["sofia"],
                self._aware_datetime(today - timedelta(days=offset), 8, 30),
                CitaMedica.Estado.CONFIRMADA,
                f"Sesion completada hace {offset} dias.",
                verif_biometria=True,
            )

        self._add_cuota(
            operation,
            1,
            today - timedelta(days=140),
            [
                {
                    "monto_pagado": Decimal("650.00"),
                    "comprobante_url": "comprobantes/demo-manchas-cuota-1.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.APROBADO,
                    "verificado_por": users["admin"],
                    "fecha_verificacion": now - timedelta(days=139),
                    "detalles_pago": "Pago correcto del primer tramo.",
                    "observacion_verificacion": "Aprobado sin observaciones.",
                    "created_at": now - timedelta(days=140),
                }
            ],
        )
        self._add_cuota(
            operation,
            2,
            today - timedelta(days=100),
            [
                {
                    "monto_pagado": Decimal("650.00"),
                    "comprobante_url": "comprobantes/demo-manchas-cuota-2.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.APROBADO,
                    "verificado_por": users["admin_support"],
                    "fecha_verificacion": now - timedelta(days=99),
                    "detalles_pago": "Segundo pago aprobado.",
                    "observacion_verificacion": "Pago final acreditado.",
                    "created_at": now - timedelta(days=100),
                }
            ],
        )

    def _seed_operation_cancelada(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=88),
            "Desea depilacion de pierna completa, pero presento baja adherencia.",
            "Operacion cancelada luego de ausencias y reprogramaciones.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=88), now - timedelta(days=88))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["tiroides"],
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            "Tratamiento hormonal irregular.",
        )
        self._add_implante(ficha, catalogs["implante"]["labios"], "Relleno temporal realizado hace 1 ano.")

        self._set_field_response(ficha, "BRONCEADO", option_codes=["SI"], detalle="Exposicion solar frecuente.")
        self._set_field_response(ficha, "ISOTRETINOINA", option_codes=["NO"])
        self._set_field_response(ficha, "DESODORANTES", option_codes=["SI"])
        self._set_field_response(ficha, "INFLAMATORIOS", option_codes=["SI"])
        self._set_field_response(ficha, "DESORDEN_HORMONAL", option_codes=["SI"], detalle="Ciclos irregulares.")
        self._set_field_response(ficha, "DIABETES", option_codes=["NO"])
        self._set_field_response(ficha, "HIPOTIROIDISMO", option_codes=["SI"])
        self._set_field_response(ficha, "KETOCONAZOL", option_codes=["NO"])
        self._set_field_response(ficha, "DIURETICOS", option_codes=["SI"], detalle="Diuretico por 2 semanas.")
        self._set_field_response(ficha, "TIPO_VELLO", valor_texto="Grueso")
        self._set_field_response(ficha, "COLOR_VELLO", valor_texto="Negro")
        self._set_field_response(ficha, "GROSOR_VELLO", valor_texto="Grueso")

        self._add_cita(
            operation,
            specialists["lucia"],
            self._aware_datetime(today - timedelta(days=55), 17, 0),
            CitaMedica.Estado.NO_ASISTIO,
            "No asistio a la primera reserva.",
        )
        self._add_cita(
            operation,
            specialists["lucia"],
            self._aware_datetime(today - timedelta(days=48), 17, 30),
            CitaMedica.Estado.CANCELADA,
            "Reserva cancelada por administracion tras falta de seguimiento.",
        )

        self._add_cuota(
            operation,
            1,
            today - timedelta(days=25),
            [
                {
                    "monto_pagado": Decimal("1700.00"),
                    "comprobante_url": "comprobantes/demo-cancelada-cuota-1.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.RECHAZADO,
                    "verificado_por": users["admin_support"],
                    "fecha_verificacion": now - timedelta(days=24),
                    "detalles_pago": "Transferencia no conciliada.",
                    "observacion_verificacion": "El banco devolvio el pago por datos incorrectos.",
                    "created_at": now - timedelta(days=26),
                }
            ],
        )

    def _seed_operation_borrador(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=2),
            "Busca mejorar textura y luminosidad facial con peeling suave.",
            "Venta en borrador aun pendiente de aprobacion definitiva.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=2), now - timedelta(days=2))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["otro"],
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            "Piel reactiva a productos con fragancia.",
        )
        self._add_cirugia(
            ficha,
            catalogs["cirugia"]["bichectomia"],
            "1 ano",
            "Recuperacion sin complicaciones.",
        )

        self._set_field_response(ficha, "USO_RETINOL", option_codes=["SI"], detalle="Uso nocturno 3 veces por semana.")
        self._set_field_response(ficha, "NIVEL_SENSIBILIDAD", option_codes=["MEDIA"])
        self._set_field_response(
            ficha,
            "REACCIONES_PREVIAS",
            option_codes=["PICAZON", "DESCAMACION"],
            detalle="Peeling previo con descamacion moderada.",
        )
        self._set_field_response(ficha, "ULTIMA_EXPOSICION_SOL", valor_fecha=today - timedelta(days=6))
        self._set_field_response(
            ficha,
            "OBJETIVO_TRATAMIENTO",
            valor_texto="Unificar tono, reducir comedones cerrados y mejorar textura.",
        )

        self._add_cuota(operation, 1, today + timedelta(days=12), [])

    def _seed_operation_limpieza(self, today, now, operation, catalogs, specialists, users):
        ficha = self._prepare_ficha(
            operation,
            today - timedelta(days=11),
            "Busca mejorar textura, puntos negros y luminosidad general.",
            "Operacion activa de limpieza profunda para mostrar pagos multiples sobre una misma cuota.",
            operation.paciente.ci,
        )
        self._stamp_instance(ficha, now - timedelta(days=11), now - timedelta(days=11))

        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["asma"],
            FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            "Madre con asma alergica controlada.",
        )
        self._add_antecedente(
            ficha,
            catalogs["antecedente"]["otro"],
            FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            "Refiere migraña ocasional y piel reactiva a fragancias intensas.",
        )
        self._add_implante(
            ficha,
            catalogs["implante"]["mejillas"],
            "Bioestimulador reabsorbible aplicado hace 10 meses.",
        )

        self._set_field_response(ficha, "PIEL_REACTIVA", option_codes=["SI"], detalle="Se enrojece con cambios de clima.")
        self._set_field_response(ficha, "EXTRACCIONES_RECIENTES", option_codes=["NO"])
        self._set_field_response(ficha, "NIVEL_SENSIBILIDAD", option_codes=["MEDIA"])
        self._set_field_response(
            ficha,
            "PRODUCTOS_ACTUALES",
            valor_texto="Gel limpiador suave, niacinamida nocturna y protector solar FPS 50.",
        )
        self._set_field_response(ficha, "AUTORIZA_FOTOGRAFIAS", valor_booleano=True)
        self._set_field_response(
            ficha,
            "REACCIONES_PREVIAS",
            option_codes=["ENROJECIMIENTO", "DESCAMACION"],
            detalle="Eritema leve posterior a una limpieza previa realizada fuera de la clinica.",
        )
        self._set_field_response(
            ficha,
            "OBJETIVO_TRATAMIENTO",
            valor_texto="Reducir comedones, brillo en zona T y mejorar textura de mejillas.",
        )

        self._add_cita(
            operation,
            specialists["sofia"],
            self._aware_datetime(today - timedelta(days=6), 15, 30),
            CitaMedica.Estado.CANCELADA,
            "Primera reserva cancelada por reagendar protocolo facial.",
        )
        self._add_cita(
            operation,
            specialists["sofia"],
            self._aware_datetime(today + timedelta(days=4), 14, 30),
            CitaMedica.Estado.PROGRAMADA,
            "Sesion de limpieza programada y confirmada administrativamente.",
        )

        self._add_cuota(
            operation,
            1,
            today - timedelta(days=3),
            [
                {
                    "monto_pagado": Decimal("160.00"),
                    "comprobante_url": "comprobantes/demo-limpieza-cuota-1-rechazado.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.RECHAZADO,
                    "verificado_por": users["admin_support"],
                    "fecha_verificacion": now - timedelta(days=6),
                    "detalles_pago": "Primer comprobante registrado con referencia incompleta.",
                    "observacion_verificacion": "El numero de operacion no coincide con el extracto bancario.",
                    "created_at": now - timedelta(days=7),
                },
                {
                    "monto_pagado": Decimal("160.00"),
                    "comprobante_url": "comprobantes/demo-limpieza-cuota-1-pendiente.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.PENDIENTE,
                    "detalles_pago": "Segundo comprobante subido para la misma cuota y aun en revision.",
                    "created_at": now - timedelta(days=1),
                },
            ],
        )
        self._add_cuota(operation, 2, today + timedelta(days=18), [])

    def _seed_operation_consulta(self, today, now, operation, specialists, users):
        self._add_cita(
            operation,
            specialists["sofia"],
            self._aware_datetime(today - timedelta(days=22), 9, 15),
            CitaMedica.Estado.CONFIRMADA,
            "Consulta diagnostica completada y cerrada.",
            verif_biometria=True,
        )

        self._add_cuota(
            operation,
            1,
            today - timedelta(days=22),
            [
                {
                    "monto_pagado": Decimal("120.00"),
                    "comprobante_url": "comprobantes/demo-consulta-cuota-1.jpg",
                    "estado_verificacion": PagoRealizado.EstadoVerificacion.APROBADO,
                    "verificado_por": users["admin"],
                    "fecha_verificacion": now - timedelta(days=21),
                    "detalles_pago": "Pago unico de consulta general.",
                    "observacion_verificacion": "Consulta cerrada y conciliada.",
                    "created_at": now - timedelta(days=22),
                }
            ],
        )

    def _seed_availability(self, today, specialists, catalogs, operations):
        treatment_service = catalogs["tipo_servicio"]["tratamiento"]
        laser_type = catalogs["tipo_procedimiento"]["laser"]
        facial_type = catalogs["tipo_procedimiento"]["facial"]
        depilacion = catalogs["procedimiento"]["depilacion"]
        manchas = catalogs["procedimiento"]["manchas"]
        tatuajes = catalogs["procedimiento"]["tatuajes"]
        limpieza = catalogs["procedimiento"]["limpieza"]

        depilacion_cita = operations["depilacion_activa"].citas_medicas.filter(
            estado=CitaMedica.Estado.PROGRAMADA
        ).order_by("fecha_hora").first()
        limpieza_cita = operations["limpieza_activa"].citas_medicas.filter(
            estado=CitaMedica.Estado.PROGRAMADA
        ).order_by("fecha_hora").first()

        self._upsert_availability_slot(
            specialists["lucia"],
            self._aware_datetime(today + timedelta(days=7), 16, 0),
            procedure_types=[laser_type],
            procedures=[depilacion],
            detail="Horario reservado para la siguiente sesion de depilacion demo.",
            appointment=depilacion_cita,
        )
        self._upsert_availability_slot(
            specialists["lucia"],
            self._aware_datetime(today + timedelta(days=9), 10, 30),
            procedure_types=[laser_type],
            detail="Cupo abierto para cualquier procedimiento laser.",
        )
        self._upsert_availability_slot(
            specialists["lucia"],
            self._aware_datetime(today + timedelta(days=12), 18, 0),
            service_types=[treatment_service],
            procedures=[depilacion, manchas],
            detail="Bloque de tratamiento para depilacion o manchas.",
        )
        self._upsert_availability_slot(
            specialists["diego"],
            self._aware_datetime(today + timedelta(days=6), 11, 0),
            procedures=[tatuajes],
            detail="Horario exclusivo para borrado de tatuajes.",
        )
        self._upsert_availability_slot(
            specialists["diego"],
            self._aware_datetime(today + timedelta(days=8), 15, 30),
            procedure_types=[laser_type],
            procedures=[tatuajes],
            detail="Cupo laser enfocado a sesiones de tatuaje.",
        )
        self._upsert_availability_slot(
            specialists["sofia"],
            self._aware_datetime(today + timedelta(days=4), 14, 30),
            procedures=[limpieza],
            detail="Horario ya tomado para limpieza profunda demo.",
            appointment=limpieza_cita,
        )
        self._upsert_availability_slot(
            specialists["sofia"],
            self._aware_datetime(today + timedelta(days=5), 9, 30),
            procedure_types=[laser_type],
            procedures=[manchas],
            detail="Horario disponible para tratamiento de manchas.",
        )
        self._upsert_availability_slot(
            specialists["sofia"],
            self._aware_datetime(today + timedelta(days=11), 13, 30),
            procedure_types=[facial_type],
            procedures=[limpieza],
            detail="Horario cosmetologico facial de apoyo.",
        )
        self._upsert_availability_slot(
            specialists["lucia"],
            self._aware_datetime(today - timedelta(days=2), 9, 0),
            procedure_types=[laser_type],
            procedures=[depilacion],
            detail="Horario pasado para exponer estados expirados.",
        )
        self._upsert_availability_slot(
            specialists["diego"],
            self._aware_datetime(today + timedelta(days=13), 17, 0),
            procedure_types=[laser_type],
            procedures=[tatuajes],
            active=False,
            detail="Horario pausado manualmente por administracion.",
        )

    def _seed_analyses(self, today, clients, catalogs):
        analysis_specs = [
            {
                "client": clients["maria"],
                "fecha": today - timedelta(days=180),
                "tipo_piel": catalogs["tipo_piel"]["sensible"],
                "deshidratacion": catalogs["deshidratacion"]["alta"],
                "grosor": catalogs["grosor"]["fina"],
                "observaciones": "Analisis inicial con piel sensible y deshidratacion alta.",
                "patologias": ["rosacea", "dermatitis"],
                "alergias": [
                    ("acido_glicolico", "irritacion", "leve", "Eritema leve durante 12 horas."),
                ],
            },
            {
                "client": clients["maria"],
                "fecha": today,
                "tipo_piel": catalogs["tipo_piel"]["mixta"],
                "deshidratacion": catalogs["deshidratacion"]["media"],
                "grosor": catalogs["grosor"]["media"],
                "observaciones": "Mejora de sensibilidad general, aun con manchas residuales.",
                "patologias": ["melasma", "arrugas"],
                "alergias": [
                    ("lidocaina", "irritacion", "moderada", "Enrojecimiento y ardor por 24 horas."),
                ],
            },
            {
                "client": clients["luciana"],
                "fecha": today - timedelta(days=10),
                "tipo_piel": catalogs["tipo_piel"]["grasa"],
                "deshidratacion": catalogs["deshidratacion"]["leve"],
                "grosor": catalogs["grosor"]["gruesa"],
                "observaciones": "Analisis previo a segunda sesion de tatuaje.",
                "patologias": ["acne", "manchas_postinflamatorias"],
                "alergias": [],
            },
            {
                "client": clients["valeria"],
                "fecha": today - timedelta(days=45),
                "tipo_piel": catalogs["tipo_piel"]["seca"],
                "deshidratacion": catalogs["deshidratacion"]["ninguna"],
                "grosor": catalogs["grosor"]["fina"],
                "observaciones": "Seguimiento final con buena respuesta al protocolo despigmentante.",
                "patologias": ["fotoenvejecimiento"],
                "alergias": [
                    ("vitamina_c", "urticaria", "leve", "Urticaria puntual con serum concentrado."),
                ],
            },
            {
                "client": clients["andrea"],
                "fecha": today - timedelta(days=3),
                "tipo_piel": catalogs["tipo_piel"]["normal"],
                "deshidratacion": catalogs["deshidratacion"]["leve"],
                "grosor": catalogs["grosor"]["media"],
                "observaciones": "Analisis previo a activacion del peeling.",
                "patologias": [],
                "alergias": [],
            },
            {
                "client": clients["monica"],
                "fecha": today - timedelta(days=15),
                "tipo_piel": catalogs["tipo_piel"]["mixta"],
                "deshidratacion": catalogs["deshidratacion"]["media"],
                "grosor": catalogs["grosor"]["media"],
                "observaciones": "Cliente inactiva con historial clinico util para reportes.",
                "patologias": ["melasma"],
                "alergias": [
                    ("aloe_vera", "dermatitis_de_contacto", "grave", "Brotes extensos al usar gel casero."),
                ],
            },
            {
                "client": clients["jimena"],
                "fecha": today - timedelta(days=85),
                "tipo_piel": catalogs["tipo_piel"]["sensible"],
                "deshidratacion": catalogs["deshidratacion"]["alta"],
                "grosor": catalogs["grosor"]["gruesa"],
                "observaciones": "Analisis previo a la operacion cancelada, con varios factores de sensibilidad.",
                "patologias": ["rosacea", "fotoenvejecimiento"],
                "alergias": [
                    ("acido_salicilico", "ardor", "moderada", "Ardor persistente luego de limpieza intensa."),
                    ("lidocaina", "edema", "leve", "Edema localizado que resolvio en pocas horas."),
                ],
            },
            {
                "client": clients["camila"],
                "fecha": today - timedelta(days=9),
                "tipo_piel": catalogs["tipo_piel"]["normal"],
                "deshidratacion": catalogs["deshidratacion"]["leve"],
                "grosor": catalogs["grosor"]["media"],
                "observaciones": "Analisis reciente para limpieza profunda y control de sensibilidad.",
                "patologias": ["acne"],
                "alergias": [
                    ("vitamina_c", "irritacion", "leve", "Cosquilleo y rubor al usar concentraciones altas."),
                ],
            },
        ]

        for spec in analysis_specs:
            analysis, _ = AnalisisEstetico.objects.update_or_create(
                paciente=spec["client"],
                fecha_analisis=spec["fecha"],
                defaults={
                    "tipo_piel": spec["tipo_piel"],
                    "grado_deshidratacion": spec["deshidratacion"],
                    "grosor_piel": spec["grosor"],
                    "observaciones": spec["observaciones"],
                },
            )
            self._stamp_instance(
                analysis,
                timezone.make_aware(datetime.combine(spec["fecha"], time(9, 0))),
                timezone.make_aware(datetime.combine(spec["fecha"], time(9, 15))),
            )
            analysis.patologias_rel.all().delete()
            analysis.alergias.all().delete()

            for pathology_key in spec["patologias"]:
                PatologiaPorAnalisis.objects.get_or_create(
                    analisis=analysis,
                    patologia=catalogs["patologia"][pathology_key],
                )

            for product_key, allergy_type_key, severity_key, detail in spec["alergias"]:
                AnalisisEsteticoAlergia.objects.get_or_create(
                    analisis=analysis,
                    producto_alergia=catalogs["producto_alergia"][product_key],
                    tipo_alergia=catalogs["tipo_alergia"][allergy_type_key],
                    gravedad=catalogs["gravedad_alergia"][severity_key],
                    defaults={"detalle_reaccion": detail},
                )
