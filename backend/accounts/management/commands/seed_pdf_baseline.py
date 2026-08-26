"""Seed command that creates the PDF demo dataset on top of the shared baseline.

This command is a thin orchestrator over :mod:`accounts.management._baselines.clean_baseline`
plus a small, deterministic demo layer. It replaces the legacy implementation that
mutated production-shaped tables (Operacion, CitaMedica, CuotaPlanPago, PagoRealizado,
HuellaBiometricaCliente) with ``Model.delete()`` and ``timezone.now()``-driven
fixtures. The reform change (reform-database-seed-scripts, decisions D6-D10) makes
the command:

* **Non-destructive.** It never calls ``Model.delete()`` on any operational table.
  Pre-existing rows from prior runs become orphans only if the natural keys change,
  which they do not. The nine operational tables identified in ``exploration.md``
  are off-limits.
* **Pre-transaction guarded.** ``require_dev_or_test()`` rejects every
  ``ENVIRONMENT`` value outside ``{development, test}`` with a hard
  ``CommandError`` before the transaction opens. There is no confirmation
  override; the operator must explicitly opt into rejection by setting
  ``DJANGO_ENVIRONMENT=production``.
* **Shared-source-of-truth.** The aesthetic catalog (Laser, three procedures,
  treatment service links) is reproduced via
  ``clean_baseline.seed_aesthetic_catalog()`` so this command and
  ``seed_client_baseline`` always converge.
* **Deterministic.** Every identifier is a fixed literal; iteration order is
  stable. The resulting record counts are byte-stable across reruns.
* **Single all-or-nothing transaction.** All writes from one invocation commit
  together. Library helpers participate in the caller's transaction; they do
  not own their own ``transaction.atomic``.

Run::

    ENVIRONMENT=development python manage.py seed_pdf_baseline

Or, with ``DJANGO_ENVIRONMENT=development`` set in the environment, the command
runs without the explicit prefix. Anything other than ``development`` or
``test`` aborts the command with ``CommandError`` before any write.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.management._baselines import clean_baseline
from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.models import Usuario
from catalogs.models import (
    Maquinaria,
    ProcEstetico,
    ServicioConfig,
    TipoServicio,
)
from operations.models import (
    AgendaHabitualEspecialista,
    TabletKiosko,
)
from staff.models import Especialidad, Especialista


# --- Deterministic demo data --------------------------------------------------

# Three baseline branches keyed by friendly name. ``principal`` is the only
# es_principal row; the helper demotes any pre-existing principal.
BRANCHES = [
    {
        "nombre": "Sede Principal",
        "ciudad": "La Paz",
        "direccion": "Sede administrativa principal",
        "es_principal": True,
        "activa": True,
    },
    {
        "nombre": "Sucursal Norte",
        "ciudad": "La Paz",
        "direccion": "Avenida Siempre Viva 123",
        "es_principal": False,
        "activa": True,
    },
    {
        "nombre": "Sucursal Sur",
        "ciudad": "Santa Cruz",
        "direccion": "Calle Falsa 456",
        "es_principal": False,
        "activa": True,
    },
]

# Admin tuple: the clean-baseline admin (admin.general) plus the two
# branch-scoped admins used by the legacy command, plus the dedicated demo
# administrator mandated by decision D6. ``admin.demo`` is distinct from
# ``admin.general`` so tests can assert both usernames coexist.
ADMINS = (
    {
        "username": "admin.general",
        "primer_nombre": "Admin",
        "apellido_paterno": "General",
        "email": "admin.general@clinic.local",
        "rol_key": "ADMIN_PRINCIPAL",
        "branch_key": "principal",
        "is_superuser": True,
        "password": "admin123456",
    },
    {
        "username": "admin.norte",
        "primer_nombre": "Admin",
        "apellido_paterno": "Norte",
        "email": "admin.norte@clinic.local",
        "rol_key": "ADMIN_SUCURSAL",
        "branch_key": "A",
        "is_superuser": False,
        "password": "admin123456",
    },
    {
        "username": "admin.sur",
        "primer_nombre": "Admin",
        "apellido_paterno": "Sur",
        "email": "admin.sur@clinic.local",
        "rol_key": "ADMIN_SUCURSAL",
        "branch_key": "B",
        "is_superuser": False,
        "password": "admin123456",
    },
    {
        "username": "admin.demo",
        "primer_nombre": "Admin",
        "apellido_paterno": "Demo",
        "email": "admin.demo@clinic.local",
        "rol_key": "ADMIN_PRINCIPAL",
        "branch_key": "principal",
        "is_superuser": True,
        "password": "admin123456",
    },
)

# Specialist users. Passwords are fixed (legacy fixture), branch assignment is
# stable, and specialty links are deterministic.
SPECIALISTS = (
    {
        "username": "lucia.laser",
        "password": "laser123456",
        "primer_nombre": "Lucia",
        "segundo_nombre": "Elena",
        "apellido_paterno": "Suarez",
        "apellido_materno": "Molina",
        "email": "lucia.laser@clinic.local",
        "branch_key": "A",
        "ci": "4567890",
        "telefono": "70111222",
        "observaciones": "Especialista en depilacion definitiva y protocolos laser.",
        "specialties": ("Dermatologìa laser", "Medicina estética"),
    },
    {
        "username": "diego.tatuajes",
        "password": "tatuajes123456",
        "primer_nombre": "Diego",
        "apellido_paterno": "Roca",
        "apellido_materno": "Salinas",
        "email": "diego.tatuajes@clinic.local",
        "branch_key": "A",
        "ci": "5678901",
        "telefono": "72233445",
        "observaciones": "Especialista en borrado de tatuajes.",
        "specialties": ("Borrado de tatuajes", "Consulta médica"),
    },
    {
        "username": "sofia.manchas",
        "password": "manchas123456",
        "primer_nombre": "Sofia",
        "apellido_paterno": "Mendez",
        "apellido_materno": "Rojas",
        "email": "sofia.manchas@clinic.local",
        "branch_key": "B",
        "ci": "6789012",
        "telefono": "73344556",
        "observaciones": "Especialista en manchas y evaluacion estetica.",
        "specialties": ("Tratamiento de manchas", "Medicina estética"),
    },
    {
        "username": "rafael.consulta",
        "password": "consulta123456",
        "primer_nombre": "Rafael",
        "apellido_paterno": "Quiroga",
        "apellido_materno": "Perez",
        "email": "rafael.consulta@clinic.local",
        "branch_key": "B",
        "ci": "7890123",
        "telefono": "74455667",
        "observaciones": "Medico para consultas y controles.",
        "specialties": ("Consulta médica", "Medicina estética"),
    },
)


# Deterministic demo Maquinaria catalog. Items are keyed on (nombre, sucursal)
# so the same rows are produced on every re-run. ``sucursal=None`` means global
# (visible to admin principal across all branches); the rest are scoped to the
# principal branch so admin_sucursal users see them on the principal branch.
MAQUINARIA_ITEMS = (
    {
        "nombre": "Laser diodo Alma",
        "marca": "Alma",
        "descripcion": "Equipo laser de diodo para depilacion definitiva.",
        "cantidad_total": 2,
        "sucursal": "principal",
    },
    {
        "nombre": "Camilla electrica",
        "marca": "Lemi",
        "descripcion": "Camilla electrica multiposicion para procedimientos esteticos.",
        "cantidad_total": 3,
        "sucursal": "principal",
    },
    {
        "nombre": "Equipo de ultrasonido",
        "marca": "BTL",
        "descripcion": "Equipo de ultrasonido focalizado para tratamientos esteticos.",
        "cantidad_total": 1,
        "sucursal": "principal",
    },
    {
        "nombre": "Lampara lupa",
        "marca": "Dazor",
        "descripcion": "Lampara con lupa para procedimientos faciales.",
        "cantidad_total": 4,
        "sucursal": None,
    },
    {
        "nombre": "Bano de parafina",
        "marca": "Sibel",
        "descripcion": "Equipo de bano de parafina para tratamientos de manos.",
        "cantidad_total": 2,
        "sucursal": None,
    },
)


class Command(BaseCommand):
    """Create the PDF demo dataset on top of the shared baseline."""

    help = (
        "Seeds the PDF demo dataset (shared clean baseline plus branches, "
        "admins, specialists, prospects, formal patients, schedules, and "
        "kiosks). Non-destructive; refuses to run outside development/test."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # Pre-transaction guard. Raises CommandError when ENVIRONMENT is not
        # in {development, test}. This MUST run before any write so the
        # operator gets a clean failure on a misconfigured production run.
        require_dev_or_test()

        roles = clean_baseline.seed_roles()
        branches_by_name = clean_baseline.seed_branches(BRANCHES)

        # The library B1 helpers (``seed_prospects``, ``seed_formal_patients``,
        # ``seed_tablet_kiosks``) expect an aliased ``{principal, A, B}`` dict
        # while ``seed_branches`` returns ``{nombre: Sucursal}``. Build the
        # alias mapping here so both contracts are honored with one DB read.
        principal_branch = next(
            b for b in branches_by_name.values() if b.es_principal
        )
        branch_a = branches_by_name.get("Sucursal Norte")
        branch_b = branches_by_name.get("Sucursal Sur")
        branches = {
            "principal": principal_branch,
            "A": branch_a,
            "B": branch_b,
        }

        admin_specs = [
            {**spec, "rol": roles[spec["rol_key"]], "sucursal": branches[spec["branch_key"]]}
            for spec in ADMINS
        ]
        clean_baseline.seed_admins(admin_specs)

        worker_role = roles["TRABAJADOR"]
        specialist_specs_for_library = []
        for spec in SPECIALISTS:
            user, _ = Usuario.objects.update_or_create(
                username=spec["username"],
                defaults={
                    "primer_nombre": spec["primer_nombre"],
                    "segundo_nombre": spec.get("segundo_nombre", ""),
                    "apellido_paterno": spec["apellido_paterno"],
                    "apellido_materno": spec.get("apellido_materno", ""),
                    "email": spec["email"],
                    "rol": worker_role,
                    "sucursal": branches[spec["branch_key"]],
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password(spec["password"])
            user.save(update_fields=["password"])
            specialist_specs_for_library.append(
                {
                    "user": user,
                    "ci": spec["ci"],
                    "telefono": spec["telefono"],
                    "observaciones": spec["observaciones"],
                    "specialties": list(spec["specialties"]),
                }
            )

        specialties, specialists_by_key = clean_baseline.seed_staff(
            specialist_specs_for_library, branches
        )

        catalogs = clean_baseline.seed_aesthetic_catalog()
        clean_baseline.seed_form_configuration(catalogs["procedures"])
        clean_baseline.seed_prospects(branches)
        clean_baseline.seed_formal_patients(roles["CLIENTE"], branches)

        clean_baseline.seed_schedules(specialists_by_key)
        kiosks = clean_baseline.seed_tablet_kiosks(branches)
        self._seed_maquinaria(branches)

        self._print_summary(branches_by_name, specialists_by_key, specialties, kiosks)

    # -- Maquinaria --------------------------------------------------------

    def _seed_maquinaria(self, branches):
        """Seed the demo Maquinaria catalog.

        Uses ``update_or_create`` keyed on ``(nombre, sucursal)`` so reruns are
        idempotent. ``sucursal=None`` produces a global row visible to admin
        principal across every branch; the rest are scoped to the principal
        branch so admin_sucursal users see them in their catalog list.
        """
        principal = branches["principal"]
        for spec in MAQUINARIA_ITEMS:
            branch_key = spec["sucursal"]
            sucursal = branches.get(branch_key) if branch_key else None
            if branch_key and sucursal is None:
                # Misconfigured key — fall back to principal to avoid an FK error.
                sucursal = principal
            Maquinaria.objects.update_or_create(
                nombre=spec["nombre"],
                sucursal=sucursal,
                defaults={
                    "marca": spec["marca"],
                    "descripcion": spec["descripcion"],
                    "cantidad_total": spec["cantidad_total"],
                    "activo": True,
                },
            )

    # -- Summary ------------------------------------------------------------

    def _print_summary(self, branches, specialists, specialties, kiosks):
        self.stdout.write(self.style.SUCCESS(
            "Base PDF demo cargada correctamente."
        ))
        self.stdout.write(
            "Resumen: "
            f"usuarios={Usuario.objects.count()}, "
            f"especialistas={Especialista.objects.count()}, "
            f"especialidades={Especialidad.objects.count()}, "
            f"tipos_servicio={TipoServicio.objects.count()}, "
            f"procedimientos={ProcEstetico.objects.count()}, "
            f"servicios_config={ServicioConfig.objects.count()}, "
            f"agendas_habituales={AgendaHabitualEspecialista.objects.count()}, "
            f"maquinaria={Maquinaria.objects.count()}"
        )
        self.stdout.write(
            "Sucursales activas: "
            + ", ".join(
                f"{b.nombre} ({b.ciudad})"
                for b in branches.values()
            )
        )
        self.stdout.write(
            "Especialistas creados: "
            + ", ".join(
                f"{info.usuario.username} ({info.usuario.nombre_completo})"
                for info in specialists.values()
            )
        )
        self.stdout.write(
            "Especialidades disponibles: "
            + ", ".join(specialty.nombre for specialty in specialties.values())
        )
        self.stdout.write("Credenciales de tablet kiosko para pruebas:")
        for cred in kiosks:
            self.stdout.write(
                f"- {cred['branch']}: codigo={cred['codigo']} clave={cred['clave']}"
            )
