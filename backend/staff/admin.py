from django.contrib import admin

from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


admin.site.register(Especialidad)
admin.site.register(Especialista)
admin.site.register(EspecialistaEspecialidad)

# Register your models here.
