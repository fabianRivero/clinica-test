from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Usuario
from catalogs.models import Sucursal


class Command(BaseCommand):
    help = "Crea o normaliza Sede Principal sin tocar datos clinicos."

    @transaction.atomic
    def handle(self, *args, **options):
        main_branch, created = Sucursal.objects.update_or_create(
            nombre="Sede Principal",
            defaults={
                "ciudad": "La Paz",
                "direccion": "Sede administrativa principal",
                "es_principal": True,
                "activa": True,
            },
        )
        Sucursal.objects.exclude(pk=main_branch.pk).filter(es_principal=True).update(es_principal=False)

        for branch_name in ("Sucursal Norte", "Sucursal Sur"):
            Sucursal.objects.filter(nombre=branch_name).update(es_principal=False, activa=True)

        admin_user = Usuario.objects.filter(username="admin.general").first()
        if admin_user:
            admin_user.sucursal = main_branch
            admin_user.save(update_fields=["sucursal", "updated_at"])

        action = "creada" if created else "actualizada"
        self.stdout.write(self.style.SUCCESS(f"Sede Principal {action} correctamente."))
        if admin_user:
            self.stdout.write("admin.general asignado a Sede Principal.")
        else:
            self.stdout.write(self.style.WARNING("No se encontro admin.general para reasignar."))
