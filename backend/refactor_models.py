import os
import re

filepath = "operations/models.py"

with open(filepath, "r") as f:
    content = f.read()

# 1. CitaMedica
content = content.replace("""    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="citas_medicas",
    )
    medico = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="citas_medicas",
    )
    disponibilidad = models.ForeignKey(
        "operations.DisponibilidadCita",
        on_delete=models.SET_NULL,
        related_name="citas_origen",
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField()""", """    operacion = models.ForeignKey(
        "operations.Operacion",
        on_delete=models.CASCADE,
        related_name="citas_medicas",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_medicas",
    )
    fecha_hora = models.DateTimeField()""")

content = content.replace("""        if self.disponibilidad_id:
            if self.medico_id and self.disponibilidad.especialista_id != self.medico_id:
                errors["disponibilidad"] = (
                    "La disponibilidad seleccionada pertenece a un especialista diferente."
                )
            if self.fecha_hora and self.disponibilidad.fecha_hora != self.fecha_hora:
                errors["fecha_hora"] = (
                    "La fecha y hora de la cita deben coincidir con la disponibilidad asignada."
                )

        if errors:
            raise ValidationError(errors)""", """        if errors:
            raise ValidationError(errors)""")

# 2. CitaProspecto
content = content.replace("""    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_prospectos",
    )
    medico = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="citas_prospectos",
    )
    disponibilidad = models.ForeignKey(
        "operations.DisponibilidadCita",
        on_delete=models.SET_NULL,
        related_name="citas_prospectos_origen",
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField()""", """    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_prospectos",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_prospectos",
    )
    fecha_hora = models.DateTimeField()""")

content = content.replace("""        if self.disponibilidad_id:
            if self.medico_id and self.disponibilidad.especialista_id != self.medico_id:
                errors["disponibilidad"] = (
                    "La disponibilidad seleccionada pertenece a un especialista diferente."
                )
            if self.fecha_hora and self.disponibilidad.fecha_hora != self.fecha_hora:
                errors["fecha_hora"] = (
                    "La fecha y hora de la cita deben coincidir con la disponibilidad asignada."
                )
            if self.servicio_config_id and not self.disponibilidad.tipos_servicio.filter(
                pk=self.servicio_config.tipo_servicio_id
            ).exists():
                errors["disponibilidad"] = "El cupo seleccionado no corresponde al servicio de cita medica."

        if errors:
            raise ValidationError(errors)""", """        if errors:
            raise ValidationError(errors)""")

# 3. CitaClienteLibre
content = content.replace("""    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_clientes_libres",
    )
    medico = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.PROTECT,
        related_name="citas_clientes_libres",
    )
    disponibilidad = models.ForeignKey(
        "operations.DisponibilidadCita",
        on_delete=models.SET_NULL,
        related_name="citas_clientes_libres_origen",
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField()""", """    servicio_config = models.ForeignKey(
        "catalogs.ServicioConfig",
        on_delete=models.PROTECT,
        related_name="citas_clientes_libres",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="citas_clientes_libres",
    )
    fecha_hora = models.DateTimeField()""")

content = content.replace("""        if self.disponibilidad_id:
            if self.medico_id and self.disponibilidad.especialista_id != self.medico_id:
                errors["disponibilidad"] = (
                    "La disponibilidad seleccionada pertenece a un especialista diferente."
                )
            if self.fecha_hora and self.disponibilidad.fecha_hora != self.fecha_hora:
                errors["fecha_hora"] = (
                    "La fecha y hora de la cita deben coincidir con la disponibilidad asignada."
                )
            if self.servicio_config_id and not self.disponibilidad.tipos_servicio.filter(
                pk=self.servicio_config.tipo_servicio_id
            ).exists():
                errors["disponibilidad"] = "El cupo seleccionado no corresponde al servicio de cita medica."

        if errors:
            raise ValidationError(errors)""", """        if errors:
            raise ValidationError(errors)""")

# 4. AgendaHabitualEspecialista
content = content.replace("""class AgendaHabitualEspecialista(TimeStampedModel):
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="agendas_habituales",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)
    horarios = models.ManyToManyField(
        "operations.HorarioDisponibilidad",
        blank=True,
        related_name="agendas_habituales",
    )""", """class AgendaHabitualEspecialista(TimeStampedModel):
    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="agendas_habituales",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="agendas_habituales",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)""")


# 5. AgendaExcepcionEspecialista
content = content.replace("""class AgendaExcepcionEspecialista(TimeStampedModel):
    class TipoExcepcion(models.TextChoices):
        AGREGAR = "AGREGAR", "Agregar disponibilidad"
        BLOQUEAR = "BLOQUEAR", "Bloquear disponibilidad"

    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="excepciones_agenda",
    )
    fecha = models.DateField()
    tipo_excepcion = models.CharField(max_length=10, choices=TipoExcepcion.choices)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)
    horarios = models.ManyToManyField(
        "operations.HorarioDisponibilidad",
        blank=True,
        related_name="excepciones_agenda",
    )""", """class AgendaExcepcionEspecialista(TimeStampedModel):
    class TipoExcepcion(models.TextChoices):
        AGREGAR = "AGREGAR", "Agregar disponibilidad"
        BLOQUEAR = "BLOQUEAR", "Bloquear disponibilidad"

    especialista = models.ForeignKey(
        "staff.Especialista",
        on_delete=models.CASCADE,
        related_name="excepciones_agenda",
    )
    sucursal = models.ForeignKey(
        "catalogs.Sucursal",
        on_delete=models.CASCADE,
        related_name="excepciones_agenda",
    )
    fecha = models.DateField()
    hora_inicio = models.TimeField(null=True, blank=True)
    hora_fin = models.TimeField(null=True, blank=True)
    tipo_excepcion = models.CharField(max_length=10, choices=TipoExcepcion.choices)
    activo = models.BooleanField(default=True)
    detalle = models.CharField(max_length=255, blank=True)""")

# Remove HorarioDisponibilidad
content = re.sub(r'class HorarioDisponibilidad\(CatalogoEditableModel\):.*?(?=class AgendaHabitualEspecialista)', '', content, flags=re.DOTALL)

# Remove DisponibilidadCita
content = re.sub(r'class DisponibilidadCita\(TimeStampedModel\):.*?(?=class FichaClinica)', '', content, flags=re.DOTALL)

with open(filepath, "w") as f:
    f.write(content)

print("Done")
