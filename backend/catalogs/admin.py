from django.contrib import admin

from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    GradoDeshidratacion,
    GravedadAlergia,
    GrosorPiel,
    GrupoOpciones,
    ImplanteInjerto,
    OpcionCatalogo,
    PatologiaCutanea,
    ProcEstetico,
    ProcEsteticosTipo,
    ProductoAlergia,
    Sector,
    ServicioConfig,
    TipoAlergia,
    TipoPiel,
    TipoServicio,
)


@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "activo", "orden")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo")
    ordering = ("orden", "nombre")


for model in (
    TipoServicio,
    ProcEsteticosTipo,
    ProcEstetico,
    ServicioConfig,
    AntecedenteMedico,
    ImplanteInjerto,
    CirugiaEstetica,
    GrupoOpciones,
    OpcionCatalogo,
    TipoPiel,
    GradoDeshidratacion,
    GrosorPiel,
    PatologiaCutanea,
    ProductoAlergia,
    TipoAlergia,
    GravedadAlergia,
):
    admin.site.register(model)

# Register your models here.
