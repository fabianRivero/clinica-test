from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Usuario
from billing.models import CategoriaGasto
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

        expense_categories = [
            ("Alquiler", "Gastos de alquiler de ambientes y espacios operativos."),
            ("Servicios", "Agua, electricidad, internet y otros servicios recurrentes."),
            ("Insumos", "Materiales e insumos usados por la sucursal."),
            ("Equipamiento", "Compra o reposicion de equipos y herramientas."),
            ("Marketing", "Publicidad, pauta y materiales comerciales."),
            ("Sueldos", "Pagos administrativos relacionados con personal."),
            ("Mantenimiento", "Reparaciones, limpieza y mantenimiento general."),
            ("Otros", "Gastos administrativos no clasificados."),
        ]
        for name, description in expense_categories:
            CategoriaGasto.objects.update_or_create(
                nombre=name,
                defaults={"descripcion": description, "activo": True},
            )

        action = "creada" if created else "actualizada"
        self.stdout.write(self.style.SUCCESS(f"Sede Principal {action} correctamente."))
        if admin_user:
            self.stdout.write("admin.general asignado a Sede Principal.")
        else:
            self.stdout.write(self.style.WARNING("No se encontro admin.general para reasignar."))
        self.stdout.write("Categorias base de gasto normalizadas.")
