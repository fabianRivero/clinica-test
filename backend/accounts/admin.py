from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import Rol, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = (
        "username",
        "primer_nombre",
        "apellido_paterno",
        "rol",
        "is_staff",
        "is_active",
    )
    list_filter = ("rol", "is_staff", "is_superuser", "is_active")
    search_fields = (
        "username",
        "primer_nombre",
        "segundo_nombre",
        "apellido_paterno",
        "apellido_materno",
        "email",
    )
    ordering = ("username",)
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Datos personales",
            {
                "fields": (
                    "primer_nombre",
                    "segundo_nombre",
                    "apellido_paterno",
                    "apellido_materno",
                    "email",
                    "rol",
                )
            },
        ),
        (
            "Permisos",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Auditoria",
            {"fields": ("last_login", "date_joined", "created_at", "updated_at")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "primer_nombre",
                    "segundo_nombre",
                    "apellido_paterno",
                    "apellido_materno",
                    "email",
                    "rol",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


admin.site.register(Rol)

# Register your models here.
