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
    ServicioConfig,
    TipoAlergia,
    TipoPiel,
    TipoServicio,
)


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
