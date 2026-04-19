from django.conf import settings
from django.db import models

from common.models import CatalogoEditableModel, TimeStampedModel


class Especialidad(CatalogoEditableModel):
    nombre = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "especialidades"
        ordering = ("orden", "nombre")

    def __str__(self):
        return self.nombre


class Especialista(TimeStampedModel):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="especialista",
    )
    ci = models.CharField(max_length=30, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    observaciones = models.TextField(blank=True)

    class Meta:
        db_table = "especialistas"
        ordering = ("usuario__primer_nombre", "usuario__apellido_paterno")

    def __str__(self):
        return self.usuario.nombre_completo


class EspecialistaEspecialidad(TimeStampedModel):
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="especialidades_rel",
    )
    especialidad = models.ForeignKey(
        "staff.Especialidad",
        on_delete=models.CASCADE,
        related_name="especialistas_rel",
    )

    class Meta:
        db_table = "especialista_especialidades"
        constraints = [
            models.UniqueConstraint(
                fields=("especialista", "especialidad"),
                name="uniq_especialista_especialidad",
            )
        ]

    def __str__(self):
        return f"{self.especialista} - {self.especialidad}"

# Create your models here.
