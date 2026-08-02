"""Shared baseline helpers used by the seed commands.

This package lives next to the management commands that own the baseline
behaviour. Each helper:

* uses ``update_or_create`` on stable natural keys (idempotent),
* does NOT own a ``transaction.atomic`` block — the caller (the seed
  command) is responsible for the transaction boundary,
* does NOT seed allergy catalogs (``ProductoAlergia``, ``TipoAlergia``,
  ``GravedadAlergia``).

Work Unit A2 (reform-database-seed-scripts) introduces the library. Only
``seed_aesthetic_catalog`` is consumed by ``seed_client_baseline`` today;
the remaining helpers exist for ``seed_pdf_baseline`` (Work Unit B1) and
any other command that needs to reproduce the canonical baseline.
"""

from decimal import Decimal

from accounts.models import Rol, Usuario
from billing.models import CategoriaGasto
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GrosorPiel,
    GrupoOpciones,
    ImplanteInjerto,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    Sector,
    ServicioConfig,
    Sucursal,
    TipoPiel,
    TipoServicio,
)
from clinical.models import FichaCampo, FichaSeccion
from customers.models import Cliente, Prospecto
from operations.models import (
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    TabletKiosko,
)
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


# Canonical TipoServicio.tipo spelling shared by both seed commands.
TRATAMIENTO_ESTETICO_TIPO = "Tratamiento estetico"

# Aesthetic catalog (ProcEsteticosTipo) — single source of truth.
AESTHETIC_TIPO = "Laser"
AESTHETIC_PROCEDURES = (
    ("depilacion", "Depilacion definitiva", "Procedimiento de depilacion definitiva.", 1, Decimal("850.00")),
    ("manchas", "Tratamiento de manchas", "Procedimiento para tratamiento de manchas.", 2, Decimal("650.00")),
    ("tatuajes", "Borrado de tatuajes", "Procedimiento para borrado de tatuajes.", 3, Decimal("1500.00")),
)


def seed_roles():
    """Create the four baseline roles if absent.

    Returns a ``{rol_name: Rol}`` dict.
    """
    roles = {}
    for name in ("ADMIN_PRINCIPAL", "ADMIN_SUCURSAL", "TRABAJADOR", "CLIENTE"):
        role, _ = Rol.objects.update_or_create(rol=name)
        roles[name] = role
    return roles


def seed_branches(branches):
    """Create or update a list of branch rows.

    ``branches`` is an iterable of dicts with keys ``nombre``, ``ciudad``,
    ``direccion``, ``es_principal``, ``activa``. The principal branch is
    demoted on every call to keep the invariant ``exactly one principal``.

    Returns a ``{nombre: Sucursal}`` dict.
    """
    by_name = {}
    principal = None
    for spec in branches:
        branch, _ = Sucursal.objects.update_or_create(
            nombre=spec["nombre"],
            defaults={
                "ciudad": spec.get("ciudad", ""),
                "direccion": spec.get("direccion", ""),
                "es_principal": bool(spec.get("es_principal", False)),
                "activa": bool(spec.get("activa", True)),
            },
        )
        by_name[spec["nombre"]] = branch
        if branch.es_principal:
            principal = branch
    if principal is not None:
        Sucursal.objects.exclude(pk=principal.pk).filter(
            es_principal=True
        ).update(es_principal=False)
    return by_name


def seed_admins(admins):
    """Create or update a list of admin users.

    ``admins`` is an iterable of dicts with the standard ``Usuario`` fields
    plus ``rol`` and ``sucursal`` foreign keys and ``password``. Passwords
    are hashed on every call so the helper can repair stale hashes.

    Returns a ``{username: Usuario}`` dict.
    """
    by_username = {}
    for spec in admins:
        user, _ = Usuario.objects.update_or_create(
            username=spec["username"],
            defaults={
                "primer_nombre": spec.get("primer_nombre", ""),
                "segundo_nombre": spec.get("segundo_nombre", ""),
                "apellido_paterno": spec.get("apellido_paterno", ""),
                "apellido_materno": spec.get("apellido_materno", ""),
                "email": spec.get("email", ""),
                "telefono": spec.get("telefono", ""),
                "rol": spec["rol"],
                "sucursal": spec["sucursal"],
                "is_active": spec.get("is_active", True),
                "is_staff": spec.get("is_staff", True),
                "is_superuser": spec.get("is_superuser", False),
            },
        )
        password = spec.get("password")
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        by_username[spec["username"]] = user
    return by_username


def seed_staff(specialists, branches):
    """Create specialties, specialists, and their ``EspecialistaEspecialidad`` links.

    ``specialists`` is an iterable of dicts with the shape:

    * ``user``: an already-persisted ``Usuario`` (the TRABAJADOR).
    * ``ci``, ``telefono``, ``observaciones``: ``Especialista`` fields.
    * ``specialties``: list of specialty name strings to link.

    Returns ``(specialties_by_name, specialists_by_key)``. Used by B1.
    """
    specialty_specs = {
        "Dermatologìa laser": ("Evaluación y tratamientos laser.", 1),
        "Borrado de tatuajes": ("Atención de tatuajes con equipo laser.", 2),
        "Tratamiento de manchas": ("Protocolos de manchas y pigmentación.", 3),
        "Consulta médica": ("Valoración inicial y controles.", 4),
        "Medicina estética": ("Seguimiento clínico de procedimientos.", 5),
    }
    specialties = {}
    for name, (desc, order) in specialty_specs.items():
        specialty, _ = Especialidad.objects.update_or_create(
            nombre=name,
            defaults={"descripcion": desc, "orden": order, "activo": True},
        )
        specialties[name] = specialty

    specialists_by_key = {}
    for spec in specialists:
        specialist, _ = Especialista.objects.update_or_create(
            usuario=spec["user"],
            defaults={
                "ci": spec.get("ci", ""),
                "telefono": spec.get("telefono", ""),
                "observaciones": spec.get("observaciones", ""),
            },
        )
        desired = [specialties[name] for name in spec.get("specialties", [])]
        EspecialistaEspecialidad.objects.filter(especialista=specialist).exclude(
            especialidad__in=desired
        ).delete()
        for specialty in desired:
            EspecialistaEspecialidad.objects.get_or_create(
                especialista=specialist, especialidad=specialty
            )
        specialists_by_key[spec["user"].username] = specialist

    return specialties, specialists_by_key


def seed_aesthetic_catalog():
    """Seed the canonical aesthetic set: Laser type, three procedures, services.

    Creates / reconciles:

    * ``TipoServicio`` rows for ``"Cita de consulta"`` and the canonical
      ``TRATAMIENTO_ESTETICO_TIPO``.
    * ``ProcEsteticosTipo(tipo="Laser")``.
    * Three ``ProcEstetico`` rows under Laser + one ``ServicioConfig`` per
      procedure priced 850/650/1500 respectively.
    * One ``ServicioConfig`` for the consulta type at 120.00.

    Also seeds the 8 ``CategoriaGasto``, 6 ``AntecedenteMedico``, 5
    ``ImplanteInjerto``, 7 ``CirugiaEstetica``, two ``GrupoOpciones`` and
    their ``OpcionCatalogo`` children, plus ``TipoPiel``/``Grado``/
    ``GrosorPiel``/``PatologiaCutanea`` catalogs that ``seed_client_baseline``
    owns.

    Returns a dict mapping each top-level catalog key to its rows.
    """
    tipo_servicio_specs = {
        "consulta": (
            "Cita de consulta",
            "Reserva para valoracion o control medico.",
            1,
        ),
        "tratamiento": (
            TRATAMIENTO_ESTETICO_TIPO,
            "Procedimientos de la ficha medica.",
            2,
        ),
    }
    tipo_servicio_by_key = {}
    for key, (name, description, order) in tipo_servicio_specs.items():
        item, _ = TipoServicio.objects.update_or_create(
            tipo=name,
            defaults={
                "descripcion": description,
                "orden": order,
                "activo": True,
            },
        )
        tipo_servicio_by_key[key] = item

    for name, description in (
        ("Alquiler", "Gastos de alquiler de ambientes y espacios operativos."),
        ("Servicios", "Agua, electricidad, internet y otros servicios recurrentes."),
        ("Insumos", "Materiales e insumos usados por la sucursal."),
        ("Equipamiento", "Compra o reposicion de equipos y herramientas."),
        ("Marketing", "Publicidad, pauta y materiales comerciales."),
        ("Sueldos", "Pagos administrativos relacionados con personal."),
        ("Mantenimiento", "Reparaciones, limpieza y mantenimiento general."),
        ("Otros", "Gastos administrativos no clasificados."),
    ):
        CategoriaGasto.objects.update_or_create(
            nombre=name,
            defaults={"descripcion": description, "activo": True},
        )

    procedure_type, _ = ProcEsteticosTipo.objects.update_or_create(
        tipo=AESTHETIC_TIPO,
        defaults={
            "descripcion": "Procedimientos laser de la ficha medica.",
            "orden": 1,
            "activo": True,
        },
    )

    procedure_by_key = {}
    servicio_by_key = {}
    for key, name, description, order, price in AESTHETIC_PROCEDURES:
        procedure, _ = ProcEstetico.objects.update_or_create(
            tipo_p_estetico=procedure_type,
            proceso=name,
            defaults={
                "descripcion": description,
                "orden": order,
                "activo": True,
            },
        )
        procedure_by_key[key] = procedure
        servicio, _ = ServicioConfig.objects.update_or_create(
            tipo_servicio=tipo_servicio_by_key["tratamiento"],
            proc_estetico=procedure,
            defaults={"precio_base": price, "activo": True},
        )
        servicio_by_key[key] = servicio

    ServicioConfig.objects.update_or_create(
        tipo_servicio=tipo_servicio_by_key["consulta"],
        proc_estetico=None,
        defaults={"precio_base": Decimal("120.00"), "activo": True},
    )

    for order, name in enumerate(
        ["Diabetes", "Asma", "Hipertension", "Cancer", "Otro", "Ninguna"],
        start=1,
    ):
        AntecedenteMedico.objects.update_or_create(
            nombre=name,
            defaults={
                "descripcion": f"Opcion de antecedente: {name}.",
                "orden": order,
                "activo": True,
            },
        )

    for order, name in enumerate(
        ["Menton", "Mejillas", "Nariz", "Otro", "Ninguno"], start=1
    ):
        ImplanteInjerto.objects.update_or_create(
            nombre=name,
            defaults={
                "descripcion": f"Opcion de implante o injerto: {name}.",
                "orden": order,
                "activo": True,
            },
        )

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
        CirugiaEstetica.objects.update_or_create(
            nombre=name,
            defaults={
                "descripcion": f"Opcion de cirugia o tratamiento estetico: {name}.",
                "orden": order,
                "activo": True,
            },
        )

    si_no_group, _ = GrupoOpciones.objects.update_or_create(
        codigo="SI_NO",
        defaults={
            "nombre": "Si / No",
            "descripcion": "Opciones binarias de la ficha medica.",
            "activo": True,
        },
    )
    for order, (code, label) in enumerate((("SI", "Si"), ("NO", "No")), start=1):
        OpcionCatalogo.objects.update_or_create(
            grupo=si_no_group,
            codigo=code,
            defaults={
                "nombre": label,
                "valor": label,
                "orden": order,
                "activo": True,
            },
        )

    depth_group, _ = GrupoOpciones.objects.update_or_create(
        codigo="PROFUNDIDAD_TATUAJE",
        defaults={
            "nombre": "Profundidad del tatuaje",
            "descripcion": "Opciones del punto de borrado de tatuajes.",
            "activo": True,
        },
    )
    for order, (code, label) in enumerate(
        (("SUPERFICIAL", "Superficial"), ("PROFUNDA", "Profunda")), start=1
    ):
        OpcionCatalogo.objects.update_or_create(
            grupo=depth_group,
            codigo=code,
            defaults={
                "nombre": label,
                "valor": label,
                "orden": order,
                "activo": True,
            },
        )

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
        ["Fina", "Media fina", "Media", "Media gruesa", "Gruesa"], start=1
    ):
        GrosorPiel.objects.update_or_create(
            nombre=name,
            defaults={
                "descripcion": f"Grosor de piel: {name}.",
                "orden": order,
                "activo": True,
            },
        )

    for order, name in enumerate(
        [
            "Eritema", "Telangiectasias", "Papulas", "Melasma",
            "Hiperpigmentaciones", "Ampollas", "Couperosis", "Pustulas",
            "Arrugas", "Estrellas vasculares", "Vesiculas", "Cicatrices",
            "Quistes", "Micosis", "Dermatitis", "Angiomas", "Costra",
            "Millium", "Efelides", "Hirsutismo", "Comedones", "Verruga",
            "Rosacea", "Queratosis", "Urticaria", "Eczema", "Nodulos",
            "Vitiligo",
        ],
        start=1,
    ):
        PatologiaCutanea.objects.update_or_create(
            nombre=name,
            defaults={
                "descripcion": f"Patologia cutanea: {name}.",
                "orden": order,
                "activo": True,
            },
        )

    return {
        "tipo_servicio": tipo_servicio_by_key,
        "procedure_type": procedure_type,
        "procedures": procedure_by_key,
        "services": servicio_by_key,
    }


# Demo FichaCampo seed scope: only the two PUNTO_D sections under the
# depilacion and manchas procedures, plus the PUNTO_E section under the
# tatuajes procedure. The literal specs match the historical
# ``seed_pdf_baseline.py`` so the deterministic demo dataset is byte-stable
# across refactors.
DEPILATION_FIELDS = (
    ("BRONCEADO", "Bronceado", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("ISOTRETINOINA", "Isotretinoina", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("DESODORANTES", "Desodorantes", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("INFLAMATORIOS", "Antiinflamatorios", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("TIPO_DEPILACION", "Tipo de depilacion", FichaCampo.TipoCampo.TEXTO, None),
    ("DESORDEN_HORMONAL", "Desorden hormonal", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("DIABETES_METFORMINA", "Diabetes (Metformina)", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("HIPOTIROIDISMO", "Hipotiroidismo", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("KETOCONAZOL", "Ketoconazol", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("DIURETICOS", "Diureticos", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("TIPO_VELLO", "Tipo de vello", FichaCampo.TipoCampo.TEXTO, None),
    ("COLOR_VELLO", "Color", FichaCampo.TipoCampo.TEXTO, None),
    ("GROSOR_VELLO", "Grosor", FichaCampo.TipoCampo.TEXTO, None),
)

TATTOO_FIELDS = (
    ("TIEMPO_ANTIGUEDAD", "Tiempo de antiguedad", FichaCampo.TipoCampo.TEXTO, None),
    ("PROFUNDIDAD_TATUAJE", "Profundidad del tatuaje", FichaCampo.TipoCampo.SELECCION, "PROFUNDIDAD_TATUAJE"),
    ("COLOR_TATUAJE", "Color del tatuaje", FichaCampo.TipoCampo.TEXTO, None),
    ("TIPO_CICATRIZACION", "Tipo de cicatrizacion", FichaCampo.TipoCampo.TEXTO, None),
    ("PROTECTOR_SOLAR", "Protector solar", FichaCampo.TipoCampo.SELECCION, "SI_NO"),
    ("OTROS_CUIDADOS", "Otros cuidados", FichaCampo.TipoCampo.TEXTO, None),
    ("TIPO_COLOR_PIEL", "Tipo de color de piel", FichaCampo.TipoCampo.TEXTO, None),
    ("AREA_CORPORAL", "Area corporal", FichaCampo.TipoCampo.TEXTO, None),
    ("AREA_FACIAL", "Area facial", FichaCampo.TipoCampo.TEXTO, None),
)


def seed_form_configuration(procedures):
    """Seed the three Sector rows, the matching ``FichaSeccion`` headers, and
    the demo ``FichaCampo`` rows for the PDF baseline.

    ``procedures`` is a dict keyed by ``"depilacion"``, ``"manchas"``,
    ``"tatuajes"`` (matching the ``AESTHETIC_PROCEDURES`` keys).

    The contract covers:

    * Three ``Sector`` rows identified by their ``codigo`` (``DEP``, ``MAN``,
      ``TAT``).
    * Three ``FichaSeccion`` rows identified by ``(proc_estetico, codigo)``:
      ``PUNTO_D`` under both the depilacion and manchas procedures (each
      belongs to the ``DEP`` sector; the ``MAN`` sector is the historical
      home for the manchas procedure but the helper only references it
      via the seeded sector), and ``PUNTO_E`` under the tattoos procedure
      (linked to the ``TAT`` sector).
    * Per-section ``FichaCampo`` rows identified by ``(seccion, codigo)``:
      the 13 depilation fields are written TWICE — once for the depilacion
      ``PUNTO_D`` section and once for the manchas ``PUNTO_D`` section — so
      each section owns its own independent field instances; the 9
      tatuaje fields are written once for the tattoos ``PUNTO_E`` section.
    * Field defaults: ``es_multiple`` matches ``MULTISELECCION`` (none of
      the demo fields use it), ``permite_detalle=False``, ``requerido=False``,
      ``activo=True``.
    * Group references reuse the ``GrupoOpciones`` rows already produced by
      ``seed_aesthetic_catalog`` (``SI_NO`` and ``PROFUNDIDAD_TATUAJE``);
      this helper does NOT create new groups or options.

    The helper is idempotent — every write uses ``update_or_create`` on
    the natural key, so re-running ``seed_pdf_baseline`` reconciles stale
    mutable values without duplicating rows.

    Used by B1.
    """
    sector_specs = [
        ("DEP", "Depilacion",
         "Secciones de ficha clinica para servicios de depilacion y manchas.",
         1),
        ("MAN", "Manchas",
         "Secciones de ficha clinica para servicios especializados en manchas.",
         2),
        ("TAT", "Tatuajes",
         "Secciones de ficha clinica para servicios de borrado de tatuajes.",
         3),
    ]
    sectors = {}
    for codigo, nombre, descripcion, orden in sector_specs:
        sector, _ = Sector.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": nombre,
                "descripcion": descripcion,
                "orden": orden,
                "activo": True,
            },
        )
        sectors[codigo] = sector

    section_lookup = {}
    for proc_key in ("depilacion", "manchas"):
        section, _ = FichaSeccion.objects.update_or_create(
            proc_estetico=procedures[proc_key],
            codigo="PUNTO_D",
            defaults={
                "nombre": "Depilacion definitiva / Manchas",
                "orden": 1,
                "activo": True,
                "sector": sectors["DEP"],
            },
        )
        section_lookup[(proc_key, "PUNTO_D")] = section
    tattoos_section, _ = FichaSeccion.objects.update_or_create(
        proc_estetico=procedures["tatuajes"],
        codigo="PUNTO_E",
        defaults={
            "nombre": "Borrado de tatuajes",
            "orden": 1,
            "activo": True,
            "sector": sectors["TAT"],
        },
    )
    section_lookup[("tatuajes", "PUNTO_E")] = tattoos_section

    # Resolve the demo GrupoOpciones rows AFTER section creation so the
    # helper does not depend on any catalog row existence before its primary
    # writes. Missing groups would raise IntegrityError on field write,
    # which is the desired loud failure.
    grupo_codigos = {group_code for _, _, _, group_code in DEPILATION_FIELDS}
    grupo_codigos.update(
        group_code for _, _, _, group_code in TATTOO_FIELDS
    )
    grupo_codigos.discard(None)
    grupos_by_codigo = {
        group.codigo: group
        for group in GrupoOpciones.objects.filter(codigo__in=grupo_codigos)
    }
    missing = grupo_codigos - set(grupos_by_codigo)
    if missing:
        raise GrupoOpciones.DoesNotExist(
            f"seed_form_configuration requires GrupoOpciones rows {sorted(missing)} "
            "produced by seed_aesthetic_catalog; they were not found."
        )

    for proc_key in ("depilacion", "manchas"):
        section = section_lookup[(proc_key, "PUNTO_D")]
        for order, (code, label, field_type, group_code) in enumerate(
            DEPILATION_FIELDS, start=1
        ):
            group = grupos_by_codigo.get(group_code) if group_code else None
            FichaCampo.objects.update_or_create(
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
            )

    for order, (code, label, field_type, group_code) in enumerate(
        TATTOO_FIELDS, start=1
    ):
        group = grupos_by_codigo.get(group_code) if group_code else None
        FichaCampo.objects.update_or_create(
            seccion=tattoos_section,
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
        )


def seed_prospects(branches):
    """Create the two demo prospects. Used by B1."""
    specs = [
        {"primer_nombre": "Juan", "apellido_paterno": "Perez",
         "telefono": "70000001", "sucursal": branches["A"]},
        {"primer_nombre": "Maria", "apellido_paterno": "Gomez",
         "telefono": "70000002", "sucursal": branches["B"]},
    ]
    out = []
    for spec in specs:
        prospect, _ = Prospecto.objects.get_or_create(
            primer_nombre=spec["primer_nombre"],
            apellido_paterno=spec["apellido_paterno"],
            defaults={
                "segundo_nombre": "",
                "apellido_materno": "",
                "telefono": spec["telefono"],
                "sucursal_registro": spec["sucursal"],
                "estado": Prospecto.Estado.PASAJERO,
            },
        )
        out.append(prospect)
    return out


def seed_formal_patients(role, branches):
    """Create the two demo formal patients. Used by B1."""
    out = []
    for username, branch_key, ci, phone, address, dob in (
        ("paciente.demo", "A", "12345678", "78888888",
         "Zona Central, Edif. Demo", "1990-01-01"),
        ("paciente.inactivo", "B", "87654321", "76666666",
         "Zona Sur, Calle Inactiva", "1985-05-15"),
    ):
        user, _ = Usuario.objects.update_or_create(
            username=username,
            defaults={
                "primer_nombre": username.split(".")[1].capitalize(),
                "apellido_paterno": "Demo",
                "email": f"{username}@clinic.local",
                "rol": role,
                "sucursal": branches[branch_key],
                "is_active": True,
            },
        )
        user.set_password("paciente123456")
        user.save()
        cliente, _ = Cliente.objects.update_or_create(
            usuario=user,
            defaults={
                "telefono": phone,
                "ci": ci,
                "direccion_domicilio": address,
                "fecha_nacimiento": dob,
                "estado_cliente": Cliente.Estado.INACTIVO,
            },
        )
        out.append(cliente)
    return out


def seed_schedules(specialists):
    """Seed Mon-Fri 08:00-18:00 schedules for each specialist. Used by B1."""
    from datetime import time
    start_time = time(8, 0)
    end_time = time(18, 0)
    for specialist in specialists.values():
        habit, _ = AgendaHabitualEspecialista.objects.update_or_create(
            especialista=specialist,
            sucursal=specialist.usuario.sucursal,
            defaults={
                "fecha_inicio": "2024-01-01",
                "fecha_fin": "2099-12-31",
                "hora_inicio": start_time,
                "hora_fin": end_time,
                "detalle": "Horario base 08:00 - 18:00",
            },
        )
        for day in range(5):
            AgendaHabitualDia.objects.update_or_create(
                agenda=habit, dia_semana=day, defaults={}
            )


def seed_tablet_kiosks(branches):
    """Create the tablet kiosk for each branch. Used by B1.

    ``branches`` is a dict keyed by ``"principal"``, ``"A"``, ``"B"``.
    Returns a list of ``{branch, codigo, clave}`` dicts.
    """
    kiosks = []
    for key, branch in branches.items():
        if key == "principal":
            suffix = "PRINCIPAL"
        elif key == "A":
            suffix = "NORTE"
        else:
            suffix = "SUR"
        codigo = f"KIOSKO-{suffix}"
        clave = f"tablet-{suffix.lower()}-123"
        kiosko, _ = TabletKiosko.objects.update_or_create(
            codigo=codigo,
            defaults={
                "nombre": f"Tablet {branch.nombre}",
                "sucursal": branch,
                "clave": clave,
                "activo": True,
            },
        )
        kiosks.append({"branch": branch.nombre, "codigo": kiosko.codigo, "clave": clave})
    return kiosks