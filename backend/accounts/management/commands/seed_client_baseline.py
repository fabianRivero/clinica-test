"""Seed command that initializes a real client deployment baseline.

This command creates the minimum data a production client needs to operate:
the four baseline roles, a single principal branch, an admin general linked to
that branch with full permissions, a tablet kiosk for branch verification, and
the complete operational catalog (types of service, expense categories,
aesthetic procedures, service pricing, medical-history options, option groups,
and form sectors).

It exists alongside ``seed_production_baseline`` (fixed minimal data) and
``seed_pdf_baseline`` (demo data with destructive cleanup unsuitable for
production). It does NOT touch ``seed_production_baseline`` or
``seed_pdf_baseline`` at runtime — catalog data is reproduced here as
standalone Python literals.

Usage examples:

    # Interactive mode — prompts for every value with sensible defaults.
    python manage.py seed_client_baseline

    # Non-interactive mode — all required flags supplied.
    python manage.py seed_client_baseline \\
        --non-interactive \\
        --branch-name "Sede Central" \\
        --branch-city "La Paz" \\
        --branch-address "Av. Principal #123" \\
        --admin-username "admin.central" \\
        --admin-password "supersecret123" \\
        --admin-first-name "Maria" \\
        --admin-last-name "Gutierrez" \\
        --admin-email "maria.gutierrez@clinic.local" \\
        --kiosk-code "KIOSKO-CENTRAL" \\
        --kiosk-password "tablet-secret-123"

    # Replace an existing principal branch in non-interactive mode.
    python manage.py seed_client_baseline --non-interactive --replace-main-branch \\
        --branch-name "Sede Nueva" ...
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from accounts.management._baselines.clean_baseline import seed_aesthetic_catalog
from accounts.management._baselines.url import resolve_admin_url
from accounts.models import Rol, Usuario
from catalogs.models import (
    PatologiaCutanea,
    ProcEstetico,
    Sector,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from operations.models import TabletKiosko


REQUIRED_FLAG_FIELDS = (
    "branch_name",
    "branch_city",
    "branch_address",
    "admin_username",
    "admin_password",
    "admin_first_name",
    "admin_last_name",
    "admin_email",
    "kiosk_code",
    "kiosk_password",
)


class Command(BaseCommand):
    """Initialize a real client deployment with prompted credentials."""

    help = (
        "Seeds a real client deployment baseline: roles, principal branch, "
        "admin general, tablet kiosk, and the full operational catalog."
    )

    # -- CLI flags ---------------------------------------------------------

    def add_arguments(self, parser):
        parser.add_argument("--branch-name", dest="branch_name", default=None)
        parser.add_argument("--branch-city", dest="branch_city", default=None)
        parser.add_argument("--branch-address", dest="branch_address", default=None)

        parser.add_argument("--admin-username", dest="admin_username", default=None)
        parser.add_argument("--admin-password", dest="admin_password", default=None)
        parser.add_argument("--admin-first-name", dest="admin_first_name", default=None)
        parser.add_argument("--admin-last-name", dest="admin_last_name", default=None)
        parser.add_argument("--admin-email", dest="admin_email", default=None)

        parser.add_argument("--kiosk-code", dest="kiosk_code", default=None)
        parser.add_argument("--kiosk-password", dest="kiosk_password", default=None)

        parser.add_argument(
            "--non-interactive",
            dest="non_interactive",
            action="store_true",
            help="Suppress all prompts; require every value flag.",
        )
        parser.add_argument(
            "--replace-main-branch",
            dest="replace_main_branch",
            action="store_true",
            help="Allow replacing an existing principal branch.",
        )

    # -- Entry point -------------------------------------------------------

    def handle(self, *args, **options):
        # Cache the parsed options so helpers (notably the safety check) can
        # read flags without re-wiring argparse.
        self._options_cache = dict(options)
        self._summary_passwords = {}

        non_interactive = self._resolve_non_interactive(options)

        values = self._collect_inputs(options, non_interactive)

        # Pre-flight validation runs BEFORE the transaction so failures abort
        # cleanly without partial state. Uniqueness checks against existing
        # rows are validations, not writes.
        self._validate_values(values)

        # Resolve the admin URL up-front so a misconfiguration aborts the
        # command before any baseline row is written. The same value is
        # reused in the summary footer.
        try:
            self._admin_url = resolve_admin_url()
        except ValueError as exc:
            raise CommandError(
                f"Invalid admin URL configuration: {exc}"
            ) from exc

        existing_branch = Sucursal.objects.filter(
            es_principal=True, activa=True
        ).first()
        if existing_branch is not None:
            self._handle_existing_main_branch(
                existing_branch, values, non_interactive
            )

        self.stdout.write("[CLIENT] Starting client baseline seed...")

        with transaction.atomic():
            roles = self._seed_roles()
            branch = self._seed_branch(values)
            admin = self._seed_admin(roles, branch, values)
            kiosk = self._seed_kiosk(branch, values)
            self._seed_catalogs()
            self._seed_sectors()

        self._print_summary(roles, branch, admin, kiosk)

    # -- Mode + input collection ------------------------------------------

    def _resolve_non_interactive(self, options):
        if options.get("non_interactive"):
            return True
        all_required_present = all(
            options.get(field) not in (None, "") for field in REQUIRED_FLAG_FIELDS
        )
        return all_required_present

    def _collect_inputs(self, options, non_interactive):
        values = {
            "branch_name": options.get("branch_name"),
            "branch_city": options.get("branch_city"),
            "branch_address": options.get("branch_address"),
            "admin_username": options.get("admin_username"),
            "admin_password": options.get("admin_password"),
            "admin_first_name": options.get("admin_first_name"),
            "admin_last_name": options.get("admin_last_name"),
            "admin_email": options.get("admin_email"),
            "kiosk_code": options.get("kiosk_code"),
            "kiosk_password": options.get("kiosk_password"),
        }

        if non_interactive:
            missing = [
                self._flag_for(field)
                for field in REQUIRED_FLAG_FIELDS
                if not values.get(field)
            ]
            if missing:
                raise CommandError(
                    "Non-interactive mode requires every value flag. "
                    "Missing: " + ", ".join(missing)
                )
            return values

        # Defaults pulled from any existing principal branch record so the
        # operator can simply press enter on a re-run.
        existing = Sucursal.objects.filter(
            es_principal=True, activa=True
        ).first()
        existing_admin = Usuario.objects.filter(is_superuser=True).first()
        existing_kiosk = (
            TabletKiosko.objects.filter(sucursal=existing).first()
            if existing is not None
            else None
        )

        defaults = {
            "branch_name": existing.nombre if existing else "Sede Principal",
            "branch_city": existing.ciudad if existing else "",
            "branch_address": existing.direccion if existing else "",
            "admin_username": (
                existing_admin.username if existing_admin else "admin.general"
            ),
            "admin_password": "",
            "admin_first_name": (
                existing_admin.primer_nombre if existing_admin else "Administrador"
            ),
            "admin_last_name": (
                existing_admin.apellido_paterno if existing_admin else "General"
            ),
            "admin_email": (
                existing_admin.email
                if existing_admin
                else "admin.general@clinic.local"
            ),
            "kiosk_code": (
                existing_kiosk.codigo if existing_kiosk else "KIOSKO-PRINCIPAL"
            ),
            "kiosk_password": "",
        }

        prompts = [
            ("branch_name", "Branch name"),
            ("branch_city", "Branch city"),
            ("branch_address", "Branch address"),
            ("admin_username", "Admin username"),
            ("admin_password", "Admin password"),
            ("admin_first_name", "Admin first name"),
            ("admin_last_name", "Admin last name"),
            ("admin_email", "Admin email"),
            ("kiosk_code", "Kiosk code"),
            ("kiosk_password", "Kiosk password"),
        ]

        for field, label in prompts:
            values[field] = self._prompt(label, defaults[field])

        return values

    def _prompt(self, label, default):
        suffix = f" [{default}]" if default else ""
        raw = input(f"{label}{suffix}: ").strip()
        return raw or (default or "")

    @staticmethod
    def _flag_for(field_name):
        return "--" + field_name.replace("_", "-")

    # -- Validation --------------------------------------------------------

    def _validate_values(self, values):
        errors = []

        for field in REQUIRED_FLAG_FIELDS:
            if not values.get(field):
                errors.append(f"{field} must not be empty.")

        # Email format.
        if values.get("admin_email"):
            try:
                validate_email(values["admin_email"])
            except DjangoValidationError:
                errors.append("admin_email is not a valid email address.")

        # Password strength.
        if values.get("admin_password"):
            try:
                validate_password(values["admin_password"])
            except DjangoValidationError as exc:
                errors.append(
                    "admin_password is too weak: " + "; ".join(exc.messages)
                )

        if values.get("kiosk_password") and len(values["kiosk_password"]) < 8:
            errors.append("kiosk_password must be at least 8 characters.")

        # Uniqueness — reject only when the existing row is a DIFFERENT record
        # than the one we are about to create/update. The principal branch
        # will be looked up by name; kiosk and admin by their unique keys.
        admin_username = values.get("admin_username")
        if admin_username:
            colliding = Usuario.objects.filter(username=admin_username).first()
            if colliding is not None and not colliding.is_superuser:
                errors.append(
                    "admin_username belongs to an existing user that is "
                    "not the target admin general."
                )

        kiosk_code = values.get("kiosk_code")
        if kiosk_code:
            kiosk_collisions = TabletKiosko.objects.filter(
                codigo=kiosk_code
            ).count()
            # Allow at most one matching kiosk — we update it in place.
            if kiosk_collisions > 1:
                errors.append(
                    "kiosk_code is not unique across existing kiosks."
                )

        if errors:
            raise CommandError(
                "Validation failed:\n - " + "\n - ".join(errors)
            )

    # -- Existing main branch safety check ---------------------------------

    def _handle_existing_main_branch(self, existing, values, non_interactive):
        self.stdout.write(self.style.WARNING(
            "An active principal branch already exists:"
        ))
        self.stdout.write(f"  Nombre:    {existing.nombre}")
        self.stdout.write(f"  Ciudad:    {existing.ciudad}")
        self.stdout.write(f"  Direccion: {existing.direccion}")
        self.stdout.write(f"  Activa:    {existing.activa}")

        same_identity = (
            existing.nombre == values["branch_name"]
            and existing.ciudad == values["branch_city"]
            and existing.direccion == values["branch_address"]
        )

        if non_interactive:
            if same_identity:
                # Idempotent re-run with identical data — proceed.
                return
            if not self._options_cache.get("replace_main_branch"):
                raise CommandError(
                    "A principal branch already exists. Re-run with "
                    "--replace-main-branch to replace it."
                )
            return

        if same_identity:
            answer = self._prompt_confirm(
                "The principal branch matches the supplied data. Continue? [Y/n]"
            )
            if not answer:
                raise CommandError("Aborted by operator.")
            return

        answer = self._prompt_confirm(
            "Replace the existing principal branch and demote all others? [y/N]"
        )
        if not answer:
            raise CommandError("Aborted by operator.")

    @staticmethod
    def _prompt_confirm(message):
        raw = input(message).strip().lower()
        return raw in ("y", "yes")

    # -- Seeding -----------------------------------------------------------

    def _seed_roles(self):
        roles = {}
        for role_name in (
            "ADMIN_PRINCIPAL",
            "ADMIN_SUCURSAL",
            "TRABAJADOR",
            "CLIENTE",
        ):
            role, _ = Rol.objects.update_or_create(rol=role_name)
            roles[role_name] = role
        return roles

    def _seed_branch(self, values):
        branch, created = Sucursal.objects.update_or_create(
            nombre=values["branch_name"],
            defaults={
                "ciudad": values["branch_city"],
                "direccion": values["branch_address"],
                "es_principal": True,
                "activa": True,
            },
        )
        Sucursal.objects.exclude(pk=branch.pk).filter(
            es_principal=True
        ).update(es_principal=False)
        self.stdout.write(
            f"  Branch {'created' if created else 'updated'}: {branch.nombre}"
        )
        return branch

    def _seed_admin(self, roles, branch, values):
        admin, created = Usuario.objects.update_or_create(
            username=values["admin_username"],
            defaults={
                "primer_nombre": values["admin_first_name"],
                "segundo_nombre": "",
                "apellido_paterno": values["admin_last_name"],
                "apellido_materno": "",
                "email": values["admin_email"],
                "telefono": "",
                "rol": roles["ADMIN_PRINCIPAL"],
                "sucursal": branch,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password(values["admin_password"])
        admin.save()
        self._summary_passwords["admin"] = values["admin_password"]
        self.stdout.write(
            f"  Admin {'created' if created else 'updated'}: "
            f"{admin.nombre_completo}"
        )
        return admin

    def _seed_kiosk(self, branch, values):
        kiosk, created = TabletKiosko.objects.update_or_create(
            codigo=values["kiosk_code"],
            defaults={
                "nombre": f"Tablet {branch.nombre}",
                "sucursal": branch,
                "activo": True,
            },
        )
        kiosk.set_clave(values["kiosk_password"])
        kiosk.save()
        self._summary_passwords["kiosk"] = values["kiosk_password"]
        self.stdout.write(
            f"  Kiosk {'created' if created else 'updated'}: {kiosk.codigo}"
        )
        return kiosk

    def _seed_catalogs(self):
        # The full catalog baseline (TipoServicio, CategoriaGasto, the Laser
        # procedure type, the three aesthetic procedures + ServicioConfig
        # links, AntecedenteMedico, ImplanteInjerto, CirugiaEstetica,
        # GrupoOpciones, OpcionCatalogo, TipoPiel, GradoDeshidratacion,
        # GrosorPiel, PatologiaCutanea) lives in the shared library so the
        # PDF demo command can converge on the same canonical set.
        seed_aesthetic_catalog()
        self.stdout.write("  Catalog baseline seeded.")

    def _seed_sectors(self):
        sector_specs = [
            (
                "DEP",
                "Depilacion",
                (
                    "Secciones de ficha clinica para servicios de "
                    "depilacion y manchas."
                ),
                1,
            ),
            (
                "MAN",
                "Manchas",
                (
                    "Secciones de ficha clinica para servicios "
                    "especializados en manchas."
                ),
                2,
            ),
            (
                "TAT",
                "Tatuajes",
                (
                    "Secciones de ficha clinica para servicios de "
                    "borrado de tatuajes."
                ),
                3,
            ),
        ]
        for codigo, nombre, descripcion, orden in sector_specs:
            Sector.objects.update_or_create(
                codigo=codigo,
                defaults={
                    "nombre": nombre,
                    "descripcion": descripcion,
                    "orden": orden,
                    "activo": True,
                },
            )
        self.stdout.write("  Sectors seeded.")

    # -- Summary -----------------------------------------------------------

    def _print_summary(self, roles, branch, admin, kiosk):
        self.stdout.write(self.style.SUCCESS(
            "[CLIENT] Client baseline seed completed."
        ))
        self.stdout.write("")
        self.stdout.write("Summary:")
        self.stdout.write(
            "  Roles:     "
            f"{Rol.objects.filter(rol__in=('ADMIN_PRINCIPAL', 'ADMIN_SUCURSAL', 'TRABAJADOR', 'CLIENTE')).count()} "
            "baseline roles"
        )
        self.stdout.write(f"  Branch:    {branch.nombre} ({branch.ciudad})")
        self.stdout.write(
            f"  Admin:     {admin.username} ({admin.email})"
        )
        self.stdout.write(f"  Kiosk:     {kiosk.codigo}")
        self.stdout.write(
            f"  Catalogs:  {TipoServicio.objects.count()} service types, "
            f"{ProcEstetico.objects.count()} procedures, "
            f"{ServicioConfig.objects.count()} service configs, "
            f"{PatologiaCutanea.objects.count()} pathologies, "
            f"{Sector.objects.count()} sectors"
        )
        self.stdout.write("")
        self.stdout.write("Final credentials (shown once):")
        self.stdout.write(
            f"  Admin general: {admin.username} / "
            f"{self._summary_passwords.get('admin', '<hidden>')}"
        )
        self.stdout.write(f"  Admin email:   {admin.email}")
        self.stdout.write(f"  Admin name:    {admin.nombre_completo}")
        self.stdout.write(f"  Kiosk code:    {kiosk.codigo}")
        self.stdout.write(
            f"  Kiosk secret:  "
            f"{self._summary_passwords.get('kiosk', '<hidden>')}"
        )
        self.stdout.write(f"  URL Admin:     {self._admin_url}")