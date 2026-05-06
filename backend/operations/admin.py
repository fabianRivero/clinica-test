from django.contrib import admin

from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    CitaMedica,
    CitaClienteLibre,
    DiaBloqueadoAgendaGlobal,
    DisponibilidadCita,
    FichaAntecedenteMedico,
    FichaCampo,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    FichaSeccion,
    HorarioDisponibilidad,
    Operacion,
)


@admin.register(Operacion)
class OperacionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "paciente",
        "servicio_config",
        "precio_total",
        "sesiones_totales",
        "estado",
        "fecha_inicio",
    )
    list_filter = ("estado", "servicio_config__tipo_servicio")
    search_fields = ("paciente__usuario__primer_nombre", "paciente__usuario__apellido_paterno")


@admin.register(CitaMedica)
class CitaMedicaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "operacion",
        "medico",
        "fecha_hora",
        "estado",
        "verif_biometria",
        "fecha_confirmacion_biometrica",
    )
    list_filter = ("estado", "verif_biometria")
    search_fields = (
        "operacion__paciente__usuario__primer_nombre",
        "operacion__paciente__usuario__apellido_paterno",
        "medico__usuario__primer_nombre",
    )


@admin.register(CitaClienteLibre)
class CitaClienteLibreAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "servicio_config", "medico", "fecha_hora", "estado")
    list_filter = ("estado", "servicio_config")
    search_fields = (
        "cliente__usuario__primer_nombre",
        "cliente__usuario__apellido_paterno",
        "medico__usuario__primer_nombre",
    )


@admin.register(DisponibilidadCita)
class DisponibilidadCitaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "especialista",
        "horario_base",
        "fecha_hora",
        "activo",
        "estado_resumen",
    )
    list_filter = ("activo", "especialista")
    search_fields = (
        "especialista__usuario__primer_nombre",
        "especialista__usuario__apellido_paterno",
        "detalle",
    )


@admin.register(HorarioDisponibilidad)
class HorarioDisponibilidadAdmin(admin.ModelAdmin):
    list_display = ("id", "hora_inicio", "hora_fin", "activo")
    list_filter = ("activo",)


@admin.register(AgendaHabitualEspecialista)
class AgendaHabitualEspecialistaAdmin(admin.ModelAdmin):
    list_display = ("id", "especialista", "fecha_inicio", "fecha_fin", "activo")
    list_filter = ("activo", "especialista")


@admin.register(AgendaExcepcionEspecialista)
class AgendaExcepcionEspecialistaAdmin(admin.ModelAdmin):
    list_display = ("id", "especialista", "fecha", "tipo_excepcion", "activo")
    list_filter = ("activo", "tipo_excepcion", "especialista")


@admin.register(DiaBloqueadoAgendaGlobal)
class DiaBloqueadoAgendaGlobalAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "activo", "detalle")
    list_filter = ("activo",)


@admin.register(FichaClinica)
class FichaClinicaAdmin(admin.ModelAdmin):
    list_display = ("id", "operacion", "fecha_ficha", "consentimiento_aceptado")
    list_filter = ("consentimiento_aceptado",)


for model in (
    FichaAntecedenteMedico,
    FichaImplanteInjerto,
    FichaCirugiaEstetica,
    FichaSeccion,
    FichaCampo,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    AgendaHabitualDia,
):
    admin.site.register(model)

# Register your models here.
