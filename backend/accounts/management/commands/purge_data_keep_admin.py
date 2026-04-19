from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Vacía los datos de negocio preservando usuarios administradores."

    excluded_models = {
        "accounts.Rol",
        "accounts.Usuario",
        "auth.Group",
        "auth.Permission",
        "contenttypes.ContentType",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            action="append",
            dest="usernames",
            help="Usuario a preservar. Puedes pasar el argumento varias veces.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ejecuta la limpieza sin pedir confirmación interactiva.",
        )

    def handle(self, *args, **options):
        user_model = apps.get_model(settings.AUTH_USER_MODEL)
        usernames = options.get("usernames") or []

        if usernames:
            preserved_users = list(user_model.objects.filter(username__in=usernames))
            encontrados = {user.username for user in preserved_users}
            faltantes = [username for username in usernames if username not in encontrados]
            if faltantes:
                raise CommandError(
                    "No se encontraron los usuarios a preservar: "
                    + ", ".join(sorted(faltantes))
                )
        else:
            preserved_users = list(user_model.objects.filter(is_superuser=True))

        if not preserved_users:
            raise CommandError(
                "No se encontró ningún administrador para preservar. "
                "Usa --username <usuario> o crea primero un superusuario."
            )

        preserved_ids = [user.pk for user in preserved_users]
        preserved_names = ", ".join(user.username for user in preserved_users)

        if not options["force"]:
            self.stdout.write(
                "Se eliminarán los datos de negocio y todos los usuarios no preservados."
            )
            self.stdout.write(f"Se conservarán: {preserved_names}")
            confirmacion = input("Escribe 'SI' para continuar: ").strip()
            if confirmacion != "SI":
                self.stdout.write(self.style.WARNING("Operación cancelada."))
                return

        tables_to_clear = self._get_tables_to_clear()

        with transaction.atomic():
            self._clear_tables(tables_to_clear)
            deleted_users, _ = user_model.objects.exclude(pk__in=preserved_ids).delete()

        self.stdout.write(self.style.SUCCESS("Base de datos vaciada correctamente."))
        self.stdout.write(f"Usuarios preservados: {preserved_names}")
        self.stdout.write(f"Usuarios eliminados: {deleted_users}")
        self.stdout.write(
            "Tablas limpiadas: " + ", ".join(sorted(tables_to_clear))
        )

    def _get_tables_to_clear(self):
        tables = set()
        for model in apps.get_models():
            if model._meta.proxy or not model._meta.managed:
                continue

            label = f"{model._meta.app_label}.{model.__name__}"
            if label in self.excluded_models:
                continue

            tables.add(model._meta.db_table)

        if not tables:
            raise CommandError("No se encontraron tablas para limpiar.")

        return tables

    def _clear_tables(self, tables):
        quoted_tables = [connection.ops.quote_name(table) for table in sorted(tables)]

        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(
                    "TRUNCATE TABLE "
                    + ", ".join(quoted_tables)
                    + " RESTART IDENTITY CASCADE;"
                )
                return

            if connection.vendor == "sqlite":
                cursor.execute("PRAGMA foreign_keys = OFF;")
                for table in quoted_tables:
                    cursor.execute(f"DELETE FROM {table};")

                try:
                    for table in sorted(tables):
                        cursor.execute(
                            "DELETE FROM sqlite_sequence WHERE name = ?;",
                            [table],
                        )
                except Exception:
                    pass
                finally:
                    cursor.execute("PRAGMA foreign_keys = ON;")
                return

            raise CommandError(
                f"El comando no está preparado para el motor '{connection.vendor}'."
            )
