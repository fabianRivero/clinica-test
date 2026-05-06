from django.contrib import admin

from billing.models import CuotaPlanPago, PagoRealizado


@admin.register(PagoRealizado)
class PagoRealizadoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cuota",
        "monto_pagado",
        "estado_verificacion",
        "verificado",
        "verificado_por",
        "fecha_verificacion",
    )
    list_filter = ("estado_verificacion", "verificado")
    search_fields = (
        "cuota__operacion__paciente__usuario__primer_nombre",
        "cuota__operacion__paciente__usuario__apellido_paterno",
        "comprobante_url",
    )


@admin.register(CuotaPlanPago)
class CuotaPlanPagoAdmin(admin.ModelAdmin):
    list_display = ("operacion", "nro_cuota", "monto_programado", "fecha_vencimiento", "estado")
    list_filter = ("estado",)
    search_fields = ("operacion__paciente__usuario__username",)

# Register your models here.
