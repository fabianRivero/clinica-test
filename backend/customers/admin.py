from django.contrib import admin

from customers.models import Cliente, HuellaBiometricaCliente, Prospecto


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "estado_cliente", "telefono")
    list_filter = ("estado_cliente",)
    search_fields = (
        "usuario__username",
        "usuario__primer_nombre",
        "usuario__apellido_paterno",
        "telefono",
        "ci",
    )


@admin.register(HuellaBiometricaCliente)
class HuellaBiometricaClienteAdmin(admin.ModelAdmin):
    list_display = (
        "cliente",
        "proveedor",
        "device_serial",
        "calidad_captura",
        "consentimiento_aceptado",
        "activo",
        "fecha_registro",
    )
    list_filter = ("proveedor", "activo", "consentimiento_aceptado")
    search_fields = (
        "cliente__usuario__username",
        "cliente__usuario__primer_nombre",
        "cliente__usuario__apellido_paterno",
        "device_serial",
    )
    readonly_fields = ("created_at", "updated_at", "fecha_registro")


@admin.register(Prospecto)
class ProspectoAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nombres",
        "apellidos",
        "telefono",
        "estado",
        "registrado_por",
        "fecha_conversion",
    )
    list_filter = ("estado",)
    search_fields = ("nombres", "apellidos", "telefono")

# Register your models here.
