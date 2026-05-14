from django.contrib import admin

from billing.models import CategoriaGasto, CuotaPlanPago, GastoSucursal, PagoRealizado


@admin.register(CategoriaGasto)
class CategoriaGastoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "orden", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "descripcion")


@admin.register(GastoSucursal)
class GastoSucursalAdmin(admin.ModelAdmin):
    list_display = ("fecha", "sucursal", "categoria", "concepto", "gasto_total", "proveedor")
    list_filter = ("sucursal", "categoria", "fecha")
    search_fields = ("concepto", "proveedor", "detalles")


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
