from django.contrib import admin

from customers.models import Cliente, Prospecto


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("id", "usuario", "estado_cliente", "telefono", "cod_biometrico")
    list_filter = ("estado_cliente",)
    search_fields = (
        "usuario__username",
        "usuario__primer_nombre",
        "usuario__apellido_paterno",
        "telefono",
        "ci",
    )


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
