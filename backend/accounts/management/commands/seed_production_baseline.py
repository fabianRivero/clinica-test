from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Rol, Usuario
from catalogs.models import Sucursal
from operations.models import TabletKiosko


class Command(BaseCommand):
    help = (
        "Carga datos baseline para produccion: "
        "Admin Principal con nombre completo, Sucursal Principal, "
        "y usuario de tablet verificacion para esa sucursal."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("[PROD] Iniciando seed de produccion...")

        roles = self._seed_roles()
        branch = self._seed_main_branch()
        admin = self._seed_admin_general(roles, branch)
        kiosk = self._seed_tablet_kiosk(branch)

        self.stdout.write(self.style.SUCCESS("[PROD] Seed de produccion completado."))
        self.stdout.write("")
        self.stdout.write("Credenciales creadas:")
        self.stdout.write(f"  Admin General: {admin.username} / admin123456")
        self.stdout.write(f"  Nombre: {admin.nombre_completo}")
        self.stdout.write(f"  Sucursal: {branch.nombre}")
        self.stdout.write(f"  Tablet Kiosko: {kiosk.codigo} / tablet-verify-123")
        self.stdout.write(f"  URL Admin: https://reactproject.site/admin")

    def _seed_roles(self):
        roles = {}
        for role_name in ("ADMIN_PRINCIPAL", "ADMIN_SUCURSAL", "TRABAJADOR", "CLIENTE"):
            role, _ = Rol.objects.get_or_create(rol=role_name)
            roles[role_name] = role
        Rol.objects.filter(rol="ADMINISTRADOR").delete()
        return roles

    def _seed_main_branch(self):
        branch, _ = Sucursal.objects.update_or_create(
            nombre="Sede Principal",
            defaults={
                "ciudad": "La Paz",
                "direccion": "Sede administrativa principal",
                "es_principal": True,
                "activa": True,
            },
        )
        Sucursal.objects.exclude(pk=branch.pk).filter(es_principal=True).update(es_principal=False)
        return branch

    def _seed_admin_general(self, roles, branch):
        admin, created = Usuario.objects.update_or_create(
            username="admin.general",
            defaults={
                "primer_nombre": "Administrador",
                "segundo_nombre": "General",
                "apellido_paterno": "del",
                "apellido_materno": "Sistema",
                "email": "admin.general@clinic.local",
                "telefono": "",
                "rol": roles["ADMIN_PRINCIPAL"],
                "sucursal": branch,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("admin123456")
        admin.save()
        action = "creado" if created else "actualizado"
        self.stdout.write(f"  Admin General {action}: {admin.nombre_completo}")
        return admin

    def _seed_tablet_kiosk(self, branch):
        kiosko, created = TabletKiosko.objects.update_or_create(
            codigo="KIOSKO-PRINCIPAL",
            defaults={
                "nombre": f"Tablet {branch.nombre}",
                "sucursal": branch,
                "clave": "tablet-verify-123",
                "activo": True,
            },
        )
        action = "creado" if created else "actualizado"
        self.stdout.write(f"  Tablet Kiosko {action}: {kiosko.codigo}")
        return kiosko
