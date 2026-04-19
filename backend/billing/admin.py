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


admin.site.register(CuotaPlanPago)

# Register your models here.
