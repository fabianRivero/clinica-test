from django.contrib import admin

from billing.models import CategoriaGasto, ConfiguracionPagoQR, CuotaPlanPago, GastoSucursal, PagoRealizado


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


@admin.register(ConfiguracionPagoQR)
class ConfiguracionPagoQRAdmin(admin.ModelAdmin):
    list_display = ("id", "sucursal", "instrucciones", "updated_at")
    list_filter = ("sucursal",)
    readonly_fields = ("sucursal",)
    search_fields = ("sucursal__nombre",)

    def has_change_permission(self, request, obj=None):
        if not obj:
            return True
        from config.api_helpers import get_user_branch
        branch = get_user_branch(request)
        if not branch:
            return False
        return obj.sucursal_id == branch.id

    def has_view_permission(self, request, obj=None):
        return True

    def get_queryset(self, request):
        from config.api_helpers import get_user_branch
        qs = super().get_queryset(request)
        branch = get_user_branch(request)
        if branch:
            qs = qs.filter(sucursal=branch)
        return qs

    def save_model(self, request, obj, form, change):
        from config.api_helpers import get_user_branch
        branch = get_user_branch(request)
        if branch:
            obj.sucursal = branch
        super().save_model(request, obj, form, change)

# Register your models here.
