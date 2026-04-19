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
    help = "Carga datos demo para la clinica estetica."

    @transaction.atomic
    def handle(self, *args, **options):
        hoy = timezone.localdate()

        admin_role, _ = Rol.objects.get_or_create(rol="ADMINISTRADOR")
        worker_role, _ = Rol.objects.get_or_create(rol="TRABAJADOR")
        client_role, _ = Rol.objects.get_or_create(rol="CLIENTE")

        admin_user, _ = Usuario.objects.update_or_create(
            username="admin",
            defaults={
                "primer_nombre": "Fabian",
                "segundo_nombre": "",
                "apellido_paterno": "Admin",
                "apellido_materno": "",
                "email": "admin@clinic.local",
                "rol": admin_role,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        admin_user.set_password("admin123456")
        admin_user.save()

        especialista_user, _ = Usuario.objects.update_or_create(
            username="doctor.laser",
            defaults={
                "primer_nombre": "Lucia",
                "segundo_nombre": "",
                "apellido_paterno": "Suarez",
                "apellido_materno": "",
                "email": "doctor.laser@clinic.local",
                "rol": worker_role,
                "is_active": True,
            },
        )
        especialista_user.set_password("doctor123456")
        especialista_user.save()

        paciente_user, _ = Usuario.objects.update_or_create(
            username="paciente.demo",
            defaults={
                "primer_nombre": "Maria",
                "segundo_nombre": "",
                "apellido_paterno": "Rojas",
                "apellido_materno": "Quispe",
                "email": "paciente.demo@clinic.local",
                "rol": client_role,
                "is_active": True,
            },
        )
        paciente_user.set_password("paciente123456")
        paciente_user.save()

        paciente, _ = Cliente.objects.update_or_create(
            usuario=paciente_user,
            defaults={
                "ci": "7894561",
                "estado_cliente": Cliente.Estado.INACTIVO,
                "cod_biometrico": "BIO-0001",
                "fecha_nacimiento": date(1992, 6, 14),
                "nro_hijos": 1,
                "direccion_domicilio": "Zona Sur, Calle 12 #45",
                "telefono": "76543210",
                "ocupacion": "Arquitecta",
                "observaciones": "Paciente demo para pruebas del sistema.",
            },
        )

        especialista, _ = Especialista.objects.update_or_create(
            usuario=especialista_user,
            defaults={
                "ci": "4567890",
                "telefono": "70111222",
                "observaciones": "Especialista principal para equipos laser.",
            },
        )

        prospecto_abierto, _ = Prospecto.objects.update_or_create(
            nombres="Carla",
            apellidos="Flores",
            defaults={
                "telefono": "70000001",
                "estado": Prospecto.Estado.PASAJERO,
                "observaciones": "Consulto por depilacion definitiva.",
                "registrado_por": especialista_user,
                "convertido_a_cliente": None,
                "fecha_conversion": None,
            },
        )

        prospecto_convertido, _ = Prospecto.objects.update_or_create(
            nombres="Maria",
            apellidos="Rojas Quispe",
            defaults={
                "telefono": paciente.telefono,
                "estado": Prospecto.Estado.CONVERTIDO,
                "observaciones": "Prospecto convertido a cliente demo.",
                "registrado_por": especialista_user,
                "convertido_a_cliente": paciente,
                "fecha_conversion": timezone.now(),
            },
        )
        if prospecto_convertido.convertido_a_cliente_id != paciente.id:
            prospecto_convertido.marcar_como_convertido(paciente)

        derma, _ = Especialidad.objects.get_or_create(
            nombre="Dermatologia laser",
            defaults={"descripcion": "Procedimientos con laser estetico.", "orden": 1},
        )
        med_est, _ = Especialidad.objects.get_or_create(
            nombre="Medicina estetica",
            defaults={"descripcion": "Valoracion y tratamientos esteticos.", "orden": 2},
        )
        EspecialistaEspecialidad.objects.get_or_create(especialista=especialista, especialidad=derma)
        EspecialistaEspecialidad.objects.get_or_create(especialista=especialista, especialidad=med_est)

        consulta, _ = TipoServicio.objects.get_or_create(
            tipo="Consulta medica",
            defaults={"descripcion": "Valoracion inicial", "orden": 1},
        )
        tratamiento, _ = TipoServicio.objects.get_or_create(
            tipo="Tratamiento estetico",
            defaults={"descripcion": "Sesiones esteticas", "orden": 2},
        )

        laser, _ = ProcEsteticosTipo.objects.get_or_create(
            tipo="Laser",
            defaults={"descripcion": "Tecnologia laser", "orden": 1},
        )

        depilacion, _ = ProcEstetico.objects.get_or_create(
            tipo_p_estetico=laser,
            proceso="Depilacion definitiva",
            defaults={"descripcion": "Depilacion laser", "orden": 1},
        )
        manchas, _ = ProcEstetico.objects.get_or_create(
            tipo_p_estetico=laser,
            proceso="Tratamiento de manchas",
            defaults={"descripcion": "Correccion de manchas con laser", "orden": 2},
        )
        tatuajes, _ = ProcEstetico.objects.get_or_create(
            tipo_p_estetico=laser,
            proceso="Borrado de tatuajes",
            defaults={"descripcion": "Borrado de tatuajes con laser", "orden": 3},
        )

        config_dep, _ = ServicioConfig.objects.update_or_create(
            tipo_servicio=tratamiento,
            proc_estetico=depilacion,
            defaults={"precio_base": Decimal("850.00"), "activo": True},
        )
        ServicioConfig.objects.update_or_create(
            tipo_servicio=tratamiento,
            proc_estetico=manchas,
            defaults={"precio_base": Decimal("650.00"), "activo": True},
        )
        config_tattoo, _ = ServicioConfig.objects.update_or_create(
            tipo_servicio=tratamiento,
            proc_estetico=tatuajes,
            defaults={"precio_base": Decimal("1500.00"), "activo": True},
        )
        ServicioConfig.objects.update_or_create(
            tipo_servicio=consulta,
            proc_estetico=None,
            defaults={"precio_base": Decimal("120.00"), "activo": True},
        )

        for orden, nombre in enumerate(["Diabetes", "Asma", "Hipertension", "Cancer", "Otro"], start=1):
            AntecedenteMedico.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": f"Antecedente {nombre.lower()}", "orden": orden},
            )

        for orden, nombre in enumerate(["Menton", "Mejillas", "Nariz", "Otro"], start=1):
            ImplanteInjerto.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": f"Implante o injerto en {nombre.lower()}", "orden": orden},
            )

        for orden, nombre in enumerate(
            ["Blefaroplastia", "Rinoplastia", "Bichectomia", "Rinomodelacion", "Lifting", "Botox"],
            start=1,
        ):
            CirugiaEstetica.objects.get_or_create(
                nombre=nombre,
                defaults={"descripcion": f"Procedimiento previo {nombre.lower()}", "orden": orden},
            )

        grupo_si_no, _ = GrupoOpciones.objects.get_or_create(
            codigo="SI_NO",
            defaults={"nombre": "Si / No", "descripcion": "Respuesta binaria", "activo": True},
        )
        opcion_si, _ = OpcionCatalogo.objects.get_or_create(
            grupo=grupo_si_no,
            codigo="SI",
            defaults={"nombre": "Si", "valor": "SI", "orden": 1, "activo": True},
        )
        opcion_no, _ = OpcionCatalogo.objects.get_or_create(
            grupo=grupo_si_no,
            codigo="NO",
            defaults={"nombre": "No", "valor": "NO", "orden": 2, "activo": True},
        )

        grupo_profundidad, _ = GrupoOpciones.objects.get_or_create(
            codigo="PROFUNDIDAD_TATUAJE",
            defaults={"nombre": "Profundidad tatuaje", "descripcion": "Opciones de profundidad", "activo": True},
        )
        superficial, _ = OpcionCatalogo.objects.get_or_create(
            grupo=grupo_profundidad,
            codigo="SUPERFICIAL",
            defaults={"nombre": "Superficial", "valor": "SUPERFICIAL", "orden": 1, "activo": True},
        )
        OpcionCatalogo.objects.get_or_create(
            grupo=grupo_profundidad,
            codigo="PROFUNDA",
            defaults={"nombre": "Profunda", "valor": "PROFUNDA", "orden": 2, "activo": True},
        )

        grupo_color_piel, _ = GrupoOpciones.objects.get_or_create(
            codigo="COLOR_PIEL",
            defaults={"nombre": "Color de piel", "descripcion": "Tono de piel", "activo": True},
        )
        blanca, _ = OpcionCatalogo.objects.get_or_create(
            grupo=grupo_color_piel,
            codigo="BLANCA",
            defaults={"nombre": "Blanca", "valor": "BLANCA", "orden": 1, "activo": True},
        )
        OpcionCatalogo.objects.get_or_create(
            grupo=grupo_color_piel,
            codigo="TRIGUENA",
            defaults={"nombre": "Triguena", "valor": "TRIGUENA", "orden": 2, "activo": True},
        )
        OpcionCatalogo.objects.get_or_create(
            grupo=grupo_color_piel,
            codigo="MORENA",
            defaults={"nombre": "Morena", "valor": "MORENA", "orden": 3, "activo": True},
        )

        def crear_campo(seccion, codigo, etiqueta, tipo_campo, orden, grupo=None):
            return FichaCampo.objects.get_or_create(
                seccion=seccion,
                codigo=codigo,
                defaults={
                    "etiqueta": etiqueta,
                    "tipo_campo": tipo_campo,
                    "grupo_opciones": grupo,
                    "es_multiple": False,
                    "permite_detalle": False,
                    "requerido": False,
                    "orden": orden,
                    "activo": True,
                },
            )[0]

        for procedimiento in (depilacion, manchas):
            seccion, _ = FichaSeccion.objects.get_or_create(
                proc_estetico=procedimiento,
                codigo="PUNTO_D",
                defaults={"nombre": "Depilacion definitiva / Manchas", "orden": 1, "activo": True},
            )
            crear_campo(seccion, "BRONCEADO", "Bronceado", FichaCampo.TipoCampo.SELECCION, 1, grupo_si_no)
            crear_campo(seccion, "ISOTRETINOINA", "Isotretinoina", FichaCampo.TipoCampo.SELECCION, 2, grupo_si_no)
            crear_campo(seccion, "DESODORANTES", "Desodorantes", FichaCampo.TipoCampo.SELECCION, 3, grupo_si_no)
            crear_campo(seccion, "INFLAMATORIOS", "Inflamatorios", FichaCampo.TipoCampo.SELECCION, 4, grupo_si_no)
            crear_campo(seccion, "DESORDEN_HORMONAL", "Desorden hormonal", FichaCampo.TipoCampo.SELECCION, 5, grupo_si_no)
            crear_campo(seccion, "DIABETES", "Diabetes (Metformina)", FichaCampo.TipoCampo.SELECCION, 6, grupo_si_no)
            crear_campo(seccion, "HIPOTIROIDISMO", "Hipotiroidismo", FichaCampo.TipoCampo.SELECCION, 7, grupo_si_no)
            crear_campo(seccion, "KETOCONAZOL", "Ketoconazol", FichaCampo.TipoCampo.SELECCION, 8, grupo_si_no)
            crear_campo(seccion, "DIURETICOS", "Diureticos", FichaCampo.TipoCampo.SELECCION, 9, grupo_si_no)
            crear_campo(seccion, "TIPO_VELLO", "Tipo de vello", FichaCampo.TipoCampo.TEXTO, 10)
            crear_campo(seccion, "COLOR_VELLO", "Color de vello", FichaCampo.TipoCampo.TEXTO, 11)
            crear_campo(seccion, "GROSOR_VELLO", "Grosor de vello", FichaCampo.TipoCampo.TEXTO, 12)

        seccion_tatuajes, _ = FichaSeccion.objects.get_or_create(
            proc_estetico=tatuajes,
            codigo="PUNTO_E",
            defaults={"nombre": "Borrado de tatuajes", "orden": 1, "activo": True},
        )
        crear_campo(seccion_tatuajes, "MESES_ANTIGUEDAD", "Meses de antiguedad", FichaCampo.TipoCampo.NUMERO, 1)
        crear_campo(
            seccion_tatuajes,
            "PROFUNDIDAD_TATUAJE",
            "Profundidad del tatuaje",
            FichaCampo.TipoCampo.SELECCION,
            2,
            grupo_profundidad,
        )
        crear_campo(seccion_tatuajes, "COLOR_TATUAJE", "Color del tatuaje", FichaCampo.TipoCampo.TEXTO, 3)
        crear_campo(seccion_tatuajes, "TIPO_CICATRIZACION", "Tipo de cicatrizacion", FichaCampo.TipoCampo.TEXTO, 4)
        crear_campo(seccion_tatuajes, "PROTECTOR_SOLAR", "Usa protector solar", FichaCampo.TipoCampo.SELECCION, 5, grupo_si_no)
        crear_campo(seccion_tatuajes, "OTROS_CUIDADOS", "Otros cuidados", FichaCampo.TipoCampo.TEXTO, 6)
        crear_campo(seccion_tatuajes, "COLOR_PIEL", "Color de piel", FichaCampo.TipoCampo.SELECCION, 7, grupo_color_piel)
        crear_campo(seccion_tatuajes, "ZONA_GENERAL", "Zona general del tatuaje", FichaCampo.TipoCampo.TEXTO, 8)
        crear_campo(seccion_tatuajes, "ZONA_ESPECIFICA", "Zona especifica del tatuaje", FichaCampo.TipoCampo.TEXTO, 9)

        operacion_dep, _ = Operacion.objects.update_or_create(
            paciente=paciente,
            servicio_config=config_dep,
            defaults={
                "zona_general": "Axilas",
                "zona_especifica": "Ambas axilas",
                "precio_total": Decimal("850.00"),
                "cuotas_totales": 2,
                "sesiones_totales": 4,
                "fecha_inicio": hoy,
                "fecha_final": None,
                "estado": Operacion.Estado.EN_PROCESO,
                "detalles_op": "Plan de depilacion definitiva en axilas.",
                "recomendaciones": "Evitar sol directo y depilacion con cera.",
            },
        )
        operacion_tattoo, _ = Operacion.objects.update_or_create(
            paciente=paciente,
            servicio_config=config_tattoo,
            defaults={
                "zona_general": "Brazo",
                "zona_especifica": "Antebrazo derecho",
                "precio_total": Decimal("1500.00"),
                "cuotas_totales": 3,
                "sesiones_totales": 3,
                "fecha_inicio": hoy - timedelta(days=7),
                "fecha_final": None,
                "estado": Operacion.Estado.EN_PROCESO,
                "detalles_op": "Borrado de tatuaje negro pequeno.",
                "recomendaciones": "No exponer la zona a calor extremo.",
            },
        )

        for operacion in (operacion_dep, operacion_tattoo):
            FichaClinica.objects.update_or_create(
                operacion=operacion,
                defaults={
                    "fecha_ficha": hoy,
                    "motivo_consulta": f"Valoracion previa para {operacion.servicio_config.proc_estetico}.",
                    "observaciones": "Ficha demo cargada automaticamente.",
                    "firma_paciente_ci": paciente.ci,
                    "firma_paciente_url": "firmas/paciente-demo.png",
                    "consentimiento_aceptado": True,
                },
            )

        ficha_dep = operacion_dep.ficha_clinica
        ficha_tattoo = operacion_tattoo.ficha_clinica

        diabetes = AntecedenteMedico.objects.get(nombre="Diabetes")
        asma = AntecedenteMedico.objects.get(nombre="Asma")
        FichaAntecedenteMedico.objects.get_or_create(
            ficha=ficha_dep,
            antecedente=diabetes,
            tipo_antecedente=FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            defaults={"detalle": "Madre con antecedente controlado."},
        )
        FichaAntecedenteMedico.objects.get_or_create(
            ficha=ficha_dep,
            antecedente=asma,
            tipo_antecedente=FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            defaults={"detalle": "Asma leve en infancia."},
        )

        implante_nariz = ImplanteInjerto.objects.get(nombre="Nariz")
        FichaImplanteInjerto.objects.get_or_create(
            ficha=ficha_tattoo,
            implante=implante_nariz,
            defaults={"detalle": "Rinomodelacion previa sin complicaciones."},
        )

        botox = CirugiaEstetica.objects.get(nombre="Botox")
        FichaCirugiaEstetica.objects.get_or_create(
            ficha=ficha_tattoo,
            cirugia=botox,
            defaults={"hace_cuanto_tiempo": "8 meses", "detalle": "Aplicacion preventiva en frente."},
        )

        def registrar_respuesta_opcion(ficha, campo_codigo, opcion, detalle=""):
            campo = FichaCampo.objects.get(
                codigo=campo_codigo,
                seccion__proc_estetico=ficha.operacion.servicio_config.proc_estetico,
            )
            respuesta, _ = FichaRespuestaCampo.objects.update_or_create(
                ficha=ficha,
                campo=campo,
                defaults={"detalle": detalle},
            )
            FichaRespuestaOpcion.objects.get_or_create(respuesta=respuesta, opcion=opcion)

        def registrar_respuesta_texto(ficha, campo_codigo, valor_texto="", valor_numero=None):
            campo = FichaCampo.objects.get(
                codigo=campo_codigo,
                seccion__proc_estetico=ficha.operacion.servicio_config.proc_estetico,
            )
            defaults = {"valor_texto": valor_texto, "valor_numero": valor_numero}
            FichaRespuestaCampo.objects.update_or_create(
                ficha=ficha,
                campo=campo,
                defaults=defaults,
            )

        registrar_respuesta_opcion(ficha_dep, "BRONCEADO", opcion_no)
        registrar_respuesta_opcion(ficha_dep, "ISOTRETINOINA", opcion_no)
        registrar_respuesta_opcion(ficha_dep, "DESODORANTES", opcion_si, "Usa desodorante diario.")
        registrar_respuesta_opcion(ficha_dep, "DIABETES", opcion_no)
        registrar_respuesta_texto(ficha_dep, "TIPO_VELLO", "Terminal")
        registrar_respuesta_texto(ficha_dep, "COLOR_VELLO", "Oscuro")
        registrar_respuesta_texto(ficha_dep, "GROSOR_VELLO", "Medio")

        registrar_respuesta_texto(ficha_tattoo, "MESES_ANTIGUEDAD", valor_numero=Decimal("24"))
        registrar_respuesta_opcion(ficha_tattoo, "PROFUNDIDAD_TATUAJE", superficial)
        registrar_respuesta_texto(ficha_tattoo, "COLOR_TATUAJE", "Negro")
        registrar_respuesta_texto(ficha_tattoo, "TIPO_CICATRIZACION", "Normal")
        registrar_respuesta_opcion(ficha_tattoo, "PROTECTOR_SOLAR", opcion_no)
        registrar_respuesta_texto(ficha_tattoo, "OTROS_CUIDADOS", "Uso crema cicatrizante el primer mes.")
        registrar_respuesta_opcion(ficha_tattoo, "COLOR_PIEL", blanca)
        registrar_respuesta_texto(ficha_tattoo, "ZONA_GENERAL", "Brazo")
        registrar_respuesta_texto(ficha_tattoo, "ZONA_ESPECIFICA", "Antebrazo derecho")

        def aware_datetime(day_offset, hour):
            return timezone.make_aware(datetime.combine(hoy + timedelta(days=day_offset), time(hour=hour)))

        CitaMedica.objects.update_or_create(
            operacion=operacion_dep,
            fecha_hora=aware_datetime(3, 10),
            defaults={
                "medico": especialista,
                "estado": CitaMedica.Estado.PROGRAMADA,
                "verif_biometria": False,
                "fecha_confirmacion_biometrica": None,
                "detalles_cita": "Primera sesion de depilacion.",
            },
        )
        CitaMedica.objects.update_or_create(
            operacion=operacion_tattoo,
            fecha_hora=aware_datetime(-2, 9),
            defaults={
                "medico": especialista,
                "estado": CitaMedica.Estado.CONFIRMADA,
                "verif_biometria": True,
                "fecha_confirmacion_biometrica": timezone.now(),
                "detalles_cita": "Sesion 1 validada con biometria.",
            },
        )
        CitaMedica.objects.update_or_create(
            operacion=operacion_tattoo,
            fecha_hora=aware_datetime(5, 9),
            defaults={
                "medico": especialista,
                "estado": CitaMedica.Estado.PROGRAMADA,
                "verif_biometria": False,
                "fecha_confirmacion_biometrica": None,
                "detalles_cita": "Sesion 2 pendiente.",
            },
        )

        for operacion, montos in (
            (operacion_dep, [Decimal("425.00"), Decimal("425.00")]),
            (operacion_tattoo, [Decimal("500.00"), Decimal("500.00"), Decimal("500.00")]),
        ):
            for idx, monto in enumerate(montos, start=1):
                cuota, _ = CuotaPlanPago.objects.update_or_create(
                    operacion=operacion,
                    nro_cuota=idx,
                    defaults={
                        "fecha_vencimiento": hoy + timedelta(days=30 * idx),
                        "estado": CuotaPlanPago.Estado.PENDIENTE,
                    },
                )
                if operacion == operacion_tattoo and idx == 1:
                    PagoRealizado.objects.update_or_create(
                        cuota=cuota,
                        comprobante_url="comprobantes/tattoo-cuota-1.jpg",
                        defaults={
                            "monto_pagado": monto,
                            "estado_verificacion": PagoRealizado.EstadoVerificacion.APROBADO,
                            "verificado": True,
                            "verificado_por": admin_user,
                            "fecha_verificacion": timezone.now(),
                            "detalles_pago": "Transferencia bancaria directa.",
                            "observacion_verificacion": "Comprobante validado por administracion.",
                        },
                    )
                elif operacion == operacion_dep and idx == 1:
                    PagoRealizado.objects.update_or_create(
                        cuota=cuota,
                        comprobante_url="comprobantes/depilacion-cuota-1.jpg",
                        defaults={
                            "monto_pagado": monto,
                            "estado_verificacion": PagoRealizado.EstadoVerificacion.PENDIENTE,
                            "verificado": False,
                            "verificado_por": None,
                            "fecha_verificacion": None,
                            "detalles_pago": "Cliente subio comprobante para validacion.",
                            "observacion_verificacion": "",
                        },
                    )

        piel_normal, _ = TipoPiel.objects.get_or_create(
            nombre="Piel normal",
            defaults={"descripcion": "Piel equilibrada", "orden": 1},
        )
        GradoDeshidratacion.objects.get_or_create(
            nombre="Leve",
            defaults={"descripcion": "Deshidratacion leve", "orden": 1},
        )
        deshidratacion_media, _ = GradoDeshidratacion.objects.get_or_create(
            nombre="Media",
            defaults={"descripcion": "Deshidratacion media", "orden": 2},
        )
        grosor_medio, _ = GrosorPiel.objects.get_or_create(
            nombre="Media",
            defaults={"descripcion": "Grosor de piel medio", "orden": 1},
        )

        analisis, _ = AnalisisEstetico.objects.update_or_create(
            paciente=paciente,
            fecha_analisis=hoy,
            defaults={
                "tipo_piel": piel_normal,
                "grado_deshidratacion": deshidratacion_media,
                "grosor_piel": grosor_medio,
                "observaciones": "Analisis inicial para trazabilidad de prueba.",
            },
        )

        arrugas, _ = PatologiaCutanea.objects.get_or_create(
            nombre="Arrugas",
            defaults={"descripcion": "Presencia de lineas y arrugas", "orden": 1},
        )
        melasma, _ = PatologiaCutanea.objects.get_or_create(
            nombre="Melasma",
            defaults={"descripcion": "Pigmentacion facial", "orden": 2},
        )
        PatologiaPorAnalisis.objects.get_or_create(analisis=analisis, patologia=arrugas)
        PatologiaPorAnalisis.objects.get_or_create(analisis=analisis, patologia=melasma)

        lidocaina, _ = ProductoAlergia.objects.get_or_create(
            nombre="Lidocaina",
            defaults={"descripcion": "Anestesico topico", "orden": 1},
        )
        irritacion, _ = TipoAlergia.objects.get_or_create(
            nombre="Irritacion",
            defaults={"descripcion": "Reaccion irritativa", "orden": 1},
        )
        moderada, _ = GravedadAlergia.objects.get_or_create(
            nombre="Moderada",
            defaults={"descripcion": "Reaccion de intensidad media", "orden": 1},
        )
        AnalisisEsteticoAlergia.objects.get_or_create(
            analisis=analisis,
            producto_alergia=lidocaina,
            tipo_alergia=irritacion,
            gravedad=moderada,
            defaults={"detalle_reaccion": "Enrojecimiento y ardor durante 24 horas."},
        )

        paciente.actualizar_estado_automaticamente()

        self.stdout.write(self.style.SUCCESS("Datos demo cargados correctamente."))
        self.stdout.write("Credenciales admin: usuario=admin / contrasena=admin123456")
        self.stdout.write(f"Prospecto abierto de ejemplo: {prospecto_abierto}")
