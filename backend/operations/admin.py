from django.contrib import admin

from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
    CitaMedica,
    CitaClienteLibre,
    DiaBloqueadoAgendaGlobal,
    Operacion,
    OperacionFoto,
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
        "sucursal",
        "fecha_hora",
        "estado",
        "verif_biometria",
        "fecha_confirmacion_biometrica",
    )
    list_filter = ("estado", "verif_biometria", "sucursal")
    search_fields = (
        "operacion__paciente__usuario__primer_nombre",
        "operacion__paciente__usuario__apellido_paterno",
    )


@admin.register(CitaClienteLibre)
class CitaClienteLibreAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "servicio_config", "sucursal", "fecha_hora", "estado")
    list_filter = ("estado", "servicio_config", "sucursal")
    search_fields = (
        "cliente__usuario__primer_nombre",
        "cliente__usuario__apellido_paterno",
    )




@admin.register(AgendaExcepcionEspecialista)
class AgendaExcepcionEspecialistaAdmin(admin.ModelAdmin):
    list_display = ("id", "especialista", "fecha", "tipo_excepcion", "activo")
    list_filter = ("activo", "tipo_excepcion", "especialista")


@admin.register(DiaBloqueadoAgendaGlobal)
class DiaBloqueadoAgendaGlobalAdmin(admin.ModelAdmin):
    list_display = ("id", "fecha", "activo", "detalle")
    list_filter = ("activo",)


@admin.register(OperacionFoto)
class OperacionFotoAdmin(admin.ModelAdmin):
    list_display = ("id", "operacion", "kind", "uploaded_at")
    list_filter = ("kind",)
    search_fields = ("operacion__paciente__usuario__primer_nombre",)


for model in (
    AgendaHabitualDia,
):
    admin.site.register(model)
