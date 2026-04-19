from django.contrib.auth.models import AbstractUser
from django.db import models

from common.models import TimeStampedModel


class Rol(TimeStampedModel):
    rol = models.CharField(max_length=80, unique=True)

    class Meta:
        db_table = "roles"
        ordering = ("rol",)

    def __str__(self):
        return self.rol


class Usuario(AbstractUser, TimeStampedModel):
    first_name = None
    last_name = None

    primer_nombre = models.CharField(max_length=80)
    segundo_nombre = models.CharField(max_length=80, blank=True)
    apellido_paterno = models.CharField(max_length=80)
    apellido_materno = models.CharField(max_length=80, blank=True)
    rol = models.ForeignKey(
        "accounts.Rol",
        on_delete=models.SET_NULL,
        related_name="usuarios",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "usuarios"
        ordering = ("username",)

    @property
    def nombre_completo(self):
        partes = [
            self.primer_nombre,
            self.segundo_nombre,
            self.apellido_paterno,
            self.apellido_materno,
        ]
        return " ".join(parte for parte in partes if parte)

    def get_full_name(self):
        return self.nombre_completo

    def tiene_rol(self, nombre_rol):
        return bool(self.rol and self.rol.rol == nombre_rol)

    @property
    def es_administrador(self):
        return self.tiene_rol("ADMINISTRADOR")

    @property
    def es_trabajador(self):
        return self.tiene_rol("TRABAJADOR")

    @property
    def es_cliente(self):
        return self.tiene_rol("CLIENTE")

    def __str__(self):
        return self.nombre_completo or self.username

# Create your models here.
