from django.contrib import admin

from clinical.models import AnalisisEstetico, AnalisisEsteticoAlergia, PatologiaPorAnalisis


@admin.register(AnalisisEstetico)
class AnalisisEsteticoAdmin(admin.ModelAdmin):
    list_display = ("id", "paciente", "fecha_analisis", "tipo_piel", "grado_deshidratacion", "grosor_piel")
    list_filter = ("tipo_piel", "grado_deshidratacion", "grosor_piel")


admin.site.register(PatologiaPorAnalisis)
admin.site.register(AnalisisEsteticoAlergia)

# Register your models here.
