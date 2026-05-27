from django.contrib import admin

from clinical.models import (
    AnalisisEstetico,
    AnalisisEsteticoAlergia,
    FichaAntecedenteMedico,
    FichaCampo,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
    FichaSeccion,
    PatologiaPorAnalisis,
)


@admin.register(AnalisisEstetico)
class AnalisisEsteticoAdmin(admin.ModelAdmin):
    list_display = ("id", "paciente", "fecha_analisis", "tipo_piel", "grado_deshidratacion", "grosor_piel")
    list_filter = ("tipo_piel", "grado_deshidratacion", "grosor_piel")


@admin.register(FichaClinica)
class FichaClinicaAdmin(admin.ModelAdmin):
    list_display = ("id", "operacion", "fecha_ficha", "consentimiento_aceptado")
    list_filter = ("consentimiento_aceptado",)


admin.site.register(PatologiaPorAnalisis)
admin.site.register(AnalisisEsteticoAlergia)

for model in (
    FichaAntecedenteMedico,
    FichaImplanteInjerto,
    FichaCirugiaEstetica,
    FichaSeccion,
    FichaCampo,
    FichaRespuestaCampo,
    FichaRespuestaOpcion,
):
    admin.site.register(model)
