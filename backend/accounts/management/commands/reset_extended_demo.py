"""Destructive orchestrator that resets the PDF demo baseline with extended fixtures.

This command is a sibling of ``reset_pdf_baseline``. It composes the same
two inner commands (``purge_data_keep_admin --force`` and
``seed_pdf_baseline``) inside a single ``transaction.atomic`` boundary,
then layers extra demo data on top:

* A 5th specialist user (``valentina.derma``) with the
  ``Dermatologìa laser`` specialty.
* Per-specialist branch REASSIGNMENT so the 5 specialists end up
  distributed 2-2-1 across the three branches: 2 Sede Principal,
  2 Sucursal Norte, 1 Sucursal Sur. The inner seed hard-codes the
  original four to Norte/Sur, so this wrapper overwrites their
  ``sucursal`` after the seed completes.
* Per-specialist ``AgendaHabitualEspecialista`` rows with distinct
  day-of-week and hour ranges (the canonical PDF helper assigns
  Mon-Fri 08:00-18:00 to every specialist, so this command overwrites
  the schedules after the inner seed completes).
* A new ``ProcEstetico`` ``Depilacion 2 x 1`` (Laser type) and a
  matching ``ServicioConfig`` that points to the existing
  ``Sector(codigo='DEP')`` so the demo ficha medica is reused by
  construction (the renderer prefers ``sector`` over ``proc_estetico``).
  Price is slightly below half of the canonical depilacion definitiva
  price (850.00 -> 400.00).
* Ten ``Prospecto`` rows in state ``PASAJERO`` (unconverted),
  distributed 4-3-3 across the three branches.
* Ten ``Prospecto`` rows in state ``CONVERTIDO`` linked 1-to-1 to ten
  ``Cliente`` rows in state ``INACTIVO``, distributed 4-3-3 across the
  three branches. The clients are the only thing created for this
  slice; no ``Operacion`` rows are seeded.
  ``Prospecto.convertido_a_cliente`` and ``fecha_conversion`` are
  populated via ``Prospecto.marcar_como_convertido`` so the two
  invariants the model enforces (estado==CONVERTIDO implies a
  non-null client pointer and a non-null conversion timestamp)
  hold without bypassing the helper.

Hard guarantees:

* Refuses to run outside ``development`` or ``test`` via
  ``require_dev_or_test()``. Same guard as ``reset_pdf_baseline``.
* One outer ``transaction.atomic`` wraps the wipe, the inner seed, and
  the extension layer. Any failure rolls back the entire waveform; the
  database is either freshly seeded with the extended dataset or
  unchanged.
* Does NOT modify ``seed_pdf_baseline.py``, ``seed_client_baseline.py``,
  ``purge_data_keep_admin.py``, or ``env_guard.py``. Sibling commands
  stay byte-stable; this command composes them via ``call_command`` only.
* Idempotent: ``update_or_create`` on every natural key in the
  extension layer. Re-running the command leaves the database in the
  same observable state.

Run::

    ENVIRONMENT=development python manage.py reset_extended_demo
"""

from datetime import time
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.management._baselines.clean_baseline import TRATAMIENTO_ESTETICO_TIPO
from accounts.management._baselines.env_guard import require_dev_or_test
from accounts.models import Rol, Usuario
from catalogs.models import (
    ProcEstetico,
    ProcEsteticosTipo,
    Sector,
    ServicioConfig,
    TipoServicio,
)
from customers.models import Cliente, Prospecto
from operations.models import (
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
)
from staff.models import Especialidad, Especialista, EspecialistaEspecialidad


# -- Extension dataset ---------------------------------------------------------
#
# Specialist distribution: 15 total, 5 per branch, same specialty mix
# in each branch. The inner ``seed_pdf_baseline`` only creates 4
# specialists (lucia/diego/sofia/rafael); the wrapper adds 11 more so
# the final grid is 5 per branch with a consistent specialty mix.
#
# Specialty rows: (specialty_label, username_stem, primer_nombre,
#                  apellido_paterno, apellido_materno, password,
#                  telefono, ci, dias, hora_inicio, hora_fin, detalle)
#
# The 5 specialties are present in the canonical seed (see
# ``clean_baseline.seed_staff``) so the wrappers do NOT create new
# ``Especialidad`` rows — they only link existing ones to the new
# specialists.
SPECIALIST_GRID = (
    # (username, specialty_label, branch_key, primer_nombre,
    #  apellido_paterno, apellido_materno, telefono, ci, password,
    #  observaciones)
    # --- Sede Principal ---
    ("lucia.laser",    "Dermatologìa laser",  "principal", "Ana",      "Fuentes",   "Rios",  "76000001", "9000001", "lucia123456",   "Especialista principal en dermatologia laser."),
    ("diego.tatuajes", "Borrado de tatuajes", "principal", "Tomas",    "Gimenez",   "Paz",   "76000002", "9000002", "diego123456",  "Especialista principal en borrado de tatuajes."),
    ("sofia.manchas",  "Tratamiento de manchas", "principal", "Lucia",  "Mendiola",  "Soto",  "76000003", "9000003", "sofia123456",  "Especialista principal en tratamiento de manchas."),
    ("rafael.consulta", "Consulta médica",    "principal", "Marcos",   "Olivera",   "Vera",  "76000004", "9000004", "rafael123456", "Medico principal para consultas y controles."),
    ("elena.estetica.principal", "Medicina estética", "principal", "Elena", "Paredes", "Cruz",  "76000005", "9000005", "elena123456",  "Especialista principal en medicina estetica."),
    # --- Sucursal Norte ---
    ("camila.derma.norte", "Dermatologìa laser", "A", "Camila", "Quiroga", "Lima", "76000006", "9000006", "camila123456", "Especialista norte en dermatologia laser."),
    ("esteban.tatuajes.norte", "Borrado de tatuajes", "A", "Esteban", "Ramos", "Diaz", "76000007", "9000007", "esteban123456", "Especialista norte en borrado de tatuajes."),
    ("florencia.manchas.norte", "Tratamiento de manchas", "A", "Florencia", "Soria", "Mena", "76000008", "9000008", "florencia123456", "Especialista norte en tratamiento de manchas."),
    ("gabriel.consulta.norte", "Consulta médica", "A", "Gabriel", "Torres", "Acosta", "76000009", "9000009", "gabriel123456", "Medico norte para consultas y controles."),
    ("ines.estetica.norte", "Medicina estética", "A", "Ines", "Urquiza", "Bravo", "76000010", "9000010", "ines123456", "Especialista norte en medicina estetica."),
    # --- Sucursal Sur ---
    ("joaquin.derma.sur", "Dermatologìa laser", "B", "Joaquin", "Vela", "Cardozo", "76000011", "9000011", "joaquin123456", "Especialista sur en dermatologia laser."),
    ("karina.tatuajes.sur", "Borrado de tatuajes", "B", "Karina", "Yanez", "Escalante", "76000012", "9000012", "karina123456", "Especialista sur en borrado de tatuajes."),
    ("lucas.manchas.sur", "Tratamiento de manchas", "B", "Lucas", "Zapata", "Ferreyra", "76000013", "9000013", "lucas123456", "Especialista sur en tratamiento de manchas."),
    ("micaela.consulta.sur", "Consulta médica", "B", "Micaela", "Aguilar", "Galeano", "76000014", "9000014", "micaela123456", "Medico sur para consultas y controles."),
    ("nicolas.estetica.sur", "Medicina estética", "B", "Nicolas", "Bermudez", "Ibarra", "76000015", "9000015", "nicolas123456", "Especialista sur en medicina estetica."),
)

# Per-specialty schedule template: the 5 specialists in each branch
# share the same weekly pattern (so the demo reads "branch X has
# specialists A, B, C, D, E with the canonical horario of each
# specialty"). dia_semana uses operations.models.DiaSemana
# (0=Domingo .. 6=Sábado).
SPECIALTY_SCHEDULE = {
    "Dermatologìa laser": {
        "dias": [1, 2, 3, 4, 5],     # Lun-Vie
        "hora_inicio": time(9, 0),
        "hora_fin": time(18, 0),
        "detalle": "Horario Lun-Vie 09:00 - 18:00",
    },
    "Borrado de tatuajes": {
        "dias": [2, 3, 4, 5, 6],     # Mar-Sab
        "hora_inicio": time(10, 0),
        "hora_fin": time(19, 0),
        "detalle": "Horario Mar-Sab 10:00 - 19:00",
    },
    "Tratamiento de manchas": {
        "dias": [3, 4, 5, 6, 0],     # Mie-Dom
        "hora_inicio": time(11, 0),
        "hora_fin": time(20, 0),
        "detalle": "Horario Mie-Dom 11:00 - 20:00",
    },
    "Consulta médica": {
        "dias": [1, 3, 5],           # Lun, Mie, Vie
        "hora_inicio": time(8, 0),
        "hora_fin": time(14, 0),
        "detalle": "Horario Lun-Mie-Vie 08:00 - 14:00",
    },
    "Medicina estética": {
        "dias": [2, 4, 6],           # Mar, Jue, Sab
        "hora_inicio": time(14, 0),
        "hora_fin": time(20, 0),
        "detalle": "Horario Mar-Jue-Sab 14:00 - 20:00",
    },
}

# Branch alias for the username derivation in ``_overwrite_schedules``.
_BRANCH_ALIAS = {"principal": "principal", "A": "norte", "B": "sur"}


def especialista_stem(specialty_label):
    """Map a specialty label to the username stem used in the grid.

    Examples::

        "Dermatologìa laser"       -> "derma1"
        "Borrado de tatuajes"      -> "tatuajes1"
        "Tratamiento de manchas"   -> "manchas1"
        "Consulta médica"          -> "consulta1"
        "Medicina estética"        -> "estetica1"
    """
    mapping = {
        "Dermatologìa laser":     "derma1",
        "Borrado de tatuajes":    "tatuajes1",
        "Tratamiento de manchas": "manchas1",
        "Consulta médica":        "consulta1",
        "Medicina estética":      "estetica1",
    }
    return mapping[specialty_label]

# 2x1 depilacion promo. Same Laser type and Tratamiento estetico
# service type as the canonical depilacion, distinct ProcEstetico,
# sector DEP so the existing ficha medica is reused.
DEPILACION_2X1 = {
    "proc_estetico": {
        "proceso": "Depilacion 2 x 1",
        "descripcion": "Promocion 2x1 de depilacion definitiva con la misma ficha medica.",
        "orden": 4,
    },
    "servicio": {
        "precio_base": Decimal("400.00"),
    },
}

# Ten unconverted prospects (PASAJERO), distributed 4-3-3 across the
# three branches: 4 Sede Principal, 3 Sucursal Norte, 3 Sucursal Sur.
PROSPECTOS_PASAJEROS = [
    # (primer_nombre, apellido_paterno, telefono, branch_key)
    # Sede Principal (4)
    ("Lucia", "Aguilar", "70111001", "principal"),
    ("Joaquin", "Fuentes", "70111002", "principal"),
    ("Renata", "Lagos", "70111003", "principal"),
    ("Tomas", "Morales", "70111004", "principal"),
    # Sucursal Norte (3)
    ("Mateo", "Beltran", "70111005", "A"),
    ("Sebastian", "Duran", "70111006", "A"),
    ("Antonella", "Ibarra", "70111007", "A"),
    # Sucursal Sur (3)
    ("Camila", "Castro", "70111008", "B"),
    ("Isabella", "Espinoza", "70111009", "B"),
    ("Maximiliano", "Jaramillo", "70111010", "B"),
]

# Ten converted prospects, distributed 4-3-3 across the three branches:
# 4 Sede Principal, 3 Sucursal Norte, 3 Sucursal Sur. Each row
# materialises a Prospecto in state CONVERTIDO, a linked Usuario
# (CLIENTE rol), and a Cliente in state INACTIVO. The conversion
# linkage is established via ``Prospecto.marcar_como_convertido`` so
# the model's state invariants are respected.
PROSPECTOS_CONVERTIDOS = [
    # (prospect_nombre, prospect_apellido, prospect_telefono,
    #  username, ci, telefono, fecha_nacimiento, branch_key, direccion)
    # Sede Principal (4)
    ("Carla", "Salazar", "70112001", "cliente.inactivo.1", "10000001",
     "71111001", "1985-11-04", "principal", "Calle 1, Zona Norte"),
    ("Felipe", "Vargas", "70112002", "cliente.inactivo.2", "10000002",
     "71111002", "1993-01-22", "principal", "Calle 2, Zona Norte"),
    ("Ines", "Zapata", "70112003", "cliente.inactivo.3", "10000003",
     "71111003", "1986-04-03", "principal", "Calle 3, Zona Norte"),
    ("Lucia", "Aguayo", "70112004", "cliente.inactivo.4", "10000004",
     "71111004", "1990-08-19", "principal", "Calle 4, Zona Norte"),
    # Sucursal Norte (3)
    ("Andres", "Quispe", "70112005", "cliente.inactivo.5", "10000005",
     "71111005", "1988-03-12", "A", "Calle 5, Zona Norte"),
    ("Daniel", "Ticona", "70112006", "cliente.inactivo.6", "10000006",
     "71111006", "1990-05-18", "A", "Calle 6, Zona Norte"),
    ("Javier", "Aliaga", "70112007", "cliente.inactivo.7", "10000007",
     "71111007", "1994-10-27", "A", "Calle 7, Zona Norte"),
    # Sucursal Sur (3)
    ("Beatriz", "Ramirez", "70112008", "cliente.inactivo.8", "10000008",
     "71111008", "1992-07-25", "B", "Calle 8, Zona Sur"),
    ("Elena", "Urbina", "70112009", "cliente.inactivo.9", "10000009",
     "71111009", "1987-09-30", "B", "Calle 9, Zona Sur"),
    ("Hector", "Yucra", "70112010", "cliente.inactivo.10", "10000010",
     "71111010", "1991-12-15", "B", "Calle 10, Zona Sur"),
]


class Command(BaseCommand):
    """Reset the PDF baseline and layer the extended demo fixtures on top.

    !! DANGER: DESTRUCTIVE ORCHESTRATOR - DEMO/STAGING ONLY !!

    This command wipes ALL business data (preserving only superuser
    accounts) and reseeds the database in a single transaction. It is
    intended for demo resets, staging reproductions, and manual
    acceptance flows. NEVER run it against a production database that
    holds real patient data.

    The env guard (``require_dev_or_test``) only blocks the command when
    ``settings.ENVIRONMENT`` is explicitly set to a non-dev/test value;
    if the env var is missing, the default is ``"development"`` and the
    guard passes silently. This is by design for local convenience but
    makes accidental destructive runs trivial. Treat any successful
    invocation of this command as a **decision that required a human**.

    REMOVAL PLAN
    ============
    This command was created ad-hoc to load extended demo fixtures
    (5th specialist, custom schedules, Depilacion 2x1 service, 10+10
    prospects/clients) for a one-off demo dataset. The owner marked it
    as a temporary command that should be removed once the demo is no
    longer in active use.

    To remove safely:

    1. Confirm no current demo/staging environment still depends on it
       (check with the team / ticket).
    2. Delete the file
       ``backend/accounts/management/commands/reset_extended_demo.py``.
    3. Re-run the project's seed regression tests to make sure nothing
       else in the codebase imports from this module
       (it does not, by construction: it only composes existing
       commands and uses standard Django ORM helpers).
    4. If a follow-up spec is required (e.g. promoting any of the
       extended fixtures to ``seed_pdf_baseline``), open a separate
       change rather than resurrecting this command.

    Do NOT add new dependencies to this command. Do NOT call it from
    any deploy / cron / migration script. Do NOT extend its blast
    radius without re-evaluating the removal plan.
    """

    help = (
        "!! DESTRUCTIVE - DEMO/STAGING ONLY !! "
        "Purges business data (preserving admin users), re-seeds the PDF "
        "demo baseline, and applies the extended demo fixtures (5 "
        "specialists distributed 2-2-1 across branches, per-specialist "
        "schedules, Depilacion 2x1 service, 10 unconverted + 10 "
        "converted prospects both distributed 4-3-3 across branches). "
        "Refuses to run outside development/test UNLESS "
        "--i-know-what-im-doing is passed AND DJANGO_ENVIRONMENT != "
        "production. Idempotent across reruns. See module docstring for "
        "removal plan."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--i-know-what-im-doing",
            action="store_true",
            help=(
                "Required safety latch. Acknowledges that this command "
                "will erase all business data and reseed the database. "
                "Without this flag the command raises CommandError before "
                "any work, regardless of the ENVIRONMENT value."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options.get("i_know_what_im_doing"):
            raise CommandError(
                "Refusing to run without --i-know-what-im-doing. This "
                "command erases all business data and reseeds the "
                "database. Re-run with the flag to acknowledge."
            )
        # Pre-transaction guard. Raises CommandError when ENVIRONMENT is not
        # in {development, test}. This MUST run before any write.
        require_dev_or_test()

        preserved_users = Usuario.objects.filter(is_superuser=True)
        preserved_ids = list(preserved_users.values_list("pk", flat=True))
        nullified_count = Usuario.objects.filter(
            pk__in=preserved_ids,
            sucursal_id__isnull=False,
        ).update(sucursal=None)
        self.stdout.write(self.style.WARNING(
            "Pre-purge integrity: nullified sucursal_id for "
            f"{nullified_count} preserved superuser(s)."
        ))

        # Destructive-wipe header. Emitted BEFORE the inner commands so the
        # operator sees the warning before any inner output begins.
        self.stdout.write(self.style.WARNING(
            "=== DESTRUCTIVE WIPE + EXTENDED DEMO LAYER === "
            "All business data (preserving admin users) will be erased; the "
            "PDF demo baseline will be reseeded; and the extended demo "
            "fixtures will be layered on top, all in a single transaction. "
            "This is not reversible."
        ))

        # ---- Inner commands (composed) -----------------------------------
        call_command(
            "purge_data_keep_admin",
            "--force",
            stdout=self.stdout,
        )
        call_command(
            "seed_pdf_baseline",
            stdout=self.stdout,
        )

        # ---- Extension layer --------------------------------------------
        # All helpers below participate in the outer @transaction.atomic.
        # None owns its own atomic block; a mid-layer failure rolls back
        # the whole waveform including the inner seed.
        branches = self._resolve_branches()
        roles = self._resolve_roles()

        # Reassign the 4 inner-seed specialists and create the 11
        # additional grid specialists so the 5-per-branch distribution
        # is in place before schedules get overwritten.
        self._reassign_specialist_branches(branches)
        specialists_by_username = self._add_grid_specialists(branches, roles)
        self._overwrite_schedules(specialists_by_username)
        self._add_depilacion_2x1()
        self._add_unconverted_prospects(branches)
        self._add_converted_prospects(branches, roles)

        self._print_summary()

    # -- Extension helpers ---------------------------------------------------

    def _resolve_branches(self):
        """Build the {principal, A, B} alias dict the inner seed uses."""
        from catalogs.models import Sucursal  # local import to keep top tidy
        branches_by_name = {b.nombre: b for b in Sucursal.objects.all()}
        principal_branch = next(
            b for b in branches_by_name.values() if b.es_principal
        )
        return {
            "principal": principal_branch,
            "A": branches_by_name.get("Sucursal Norte"),
            "B": branches_by_name.get("Sucursal Sur"),
        }

    def _resolve_roles(self):
        return {r.rol: r for r in Rol.objects.all()}

    def _reassign_specialist_branches(self, branches):
        """Reassign the 4 inner-seed specialists to fit the 5x3 grid.

        The canonical seed hard-codes the original four to Norte/Sur.
        This wrapper overwrites their ``Usuario.sucursal`` so the four
        canonical usernames occupy four of the fifteen slots in the
        grid. The remaining 11 specialists are created in their target
        branch directly by ``_add_grid_specialists``.

        Mapping (4 originals -> 4 slots in the grid):

        * ``lucia.laser`` (Dermatologia laser) -> Sede Principal
        * ``diego.tatuajes`` (Borrado de tatuajes) -> Sucursal Norte
        * ``sofia.manchas`` (Tratamiento de manchas) -> Sucursal Sur
        * ``rafael.consulta`` (Consulta medica) -> Sucursal Norte

        The remaining 11 specialists come from ``SPECIALIST_GRID``
        minus the four canonical usernames.
        """
        canonical_branch_assignment = {
            "lucia.laser": "principal",
            "diego.tatuajes": "A",
            "sofia.manchas": "B",
            "rafael.consulta": "A",
        }
        for username, branch_key in canonical_branch_assignment.items():
            Usuario.objects.filter(username=username).update(
                sucursal=branches[branch_key]
            )

    def _add_grid_specialists(self, branches, roles):
        """Reconcile the 15 specialists in the grid.

        The inner ``seed_pdf_baseline`` already created 4 specialists
        (lucia, diego, sofia, rafael). The grid has 15 rows, four of
        which reuse those canonical usernames and 11 are new. We
        iterate the grid and use ``update_or_create`` on
        ``Usuario.username``:

        * For the 4 canonical usernames the existing Usuario row is
          updated in place with the new branch, name, password, etc.
        * For the 11 new usernames a fresh ``Usuario`` +
          ``Especialista`` + ``EspecialistaEspecialidad`` is created.

        Net result: 15 ``Especialista`` rows, 5 per branch, with
        one specialist per (branch, specialty) slot.
        """
        worker_role = roles["TRABAJADOR"]

        for row in SPECIALIST_GRID:
            (username, specialty, branch_key, primer_nombre,
             apellido_paterno, apellido_materno, telefono, ci,
             password, observaciones) = row

            user, _ = Usuario.objects.update_or_create(
                username=username,
                defaults={
                    "primer_nombre": primer_nombre,
                    "segundo_nombre": "",
                    "apellido_paterno": apellido_paterno,
                    "apellido_materno": apellido_materno,
                    "email": f"{username}@clinic.local",
                    "rol": worker_role,
                    "sucursal": branches[branch_key],
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])

            specialist, _ = Especialista.objects.update_or_create(
                usuario=user,
                defaults={
                    "ci": ci,
                    "telefono": telefono,
                    "observaciones": observaciones,
                    "sucursal_base": branches[branch_key],
                },
            )
            desired = list(Especialidad.objects.filter(nombre=specialty))
            EspecialistaEspecialidad.objects.filter(
                especialista=specialist
            ).exclude(especialidad__in=desired).delete()
            for esp in desired:
                EspecialistaEspecialidad.objects.get_or_create(
                    especialista=specialist, especialidad=esp
                )

        # Distribution report. Filter on ``sucursal_base`` (the
        # Especialista field the admin view uses) instead of
        # ``usuario__sucursal`` so the report matches what the
        # ``/cms/equipo/gestionar`` page actually shows.
        distribution = {
            branch_key: Especialista.objects.filter(
                sucursal_base=branch
            ).count()
            for branch_key, branch in branches.items()
        }
        self.stdout.write(self.style.SUCCESS(
            f"Especialistas creados: {Especialista.objects.count()} "
            f"(Sede Principal={distribution['principal']}, "
            f"Sucursal Norte={distribution['A']}, "
            f"Sucursal Sur={distribution['B']})"
        ))

        return {
            info.usuario.username: info
            for info in Especialista.objects.select_related("usuario").all()
        }

    def _overwrite_schedules(self, specialists_by_username):
        """Replace each specialist's agenda with the per-specialty schedule.

        The inner seed (``clean_baseline.seed_schedules``) creates a
        single Mon-Fri 08:00-18:00 agenda per specialist via
        ``update_or_create`` on (especialista, sucursal). We mutate the
        existing row in place and replace the day's set with the
        per-specialty template from ``SPECIALTY_SCHEDULE``.
        """
        for username, specialist in specialists_by_username.items():
            # Look up the specialist's primary specialty to find the
            # schedule template. The grid assigns one specialty per
            # specialist, so .first() is correct.
            esp_link = (
                EspecialistaEspecialidad.objects
                .filter(especialista=specialist)
                .select_related("especialidad")
                .first()
            )
            if esp_link is None:
                raise RuntimeError(
                    f"Specialist {username!r} has no linked specialty; "
                    f"cannot derive a schedule template."
                )
            specialty_label = esp_link.especialidad.nombre
            template = SPECIALTY_SCHEDULE.get(specialty_label)
            if template is None:
                raise RuntimeError(
                    f"No schedule template for specialty {specialty_label!r}."
                )
            agenda, _ = AgendaHabitualEspecialista.objects.update_or_create(
                especialista=specialist,
                sucursal=specialist.usuario.sucursal,
                defaults={
                    "fecha_inicio": "2024-01-01",
                    "fecha_fin": "2099-12-31",
                    "hora_inicio": template["hora_inicio"],
                    "hora_fin": template["hora_fin"],
                    "detalle": template["detalle"],
                },
            )
            AgendaHabitualDia.objects.filter(agenda=agenda).delete()
            for dia in template["dias"]:
                AgendaHabitualDia.objects.create(agenda=agenda, dia_semana=dia)
            self.stdout.write(
                f"Horario {username}: {template['detalle']}"
            )

    def _add_depilacion_2x1(self):
        """Create ProcEstetico + ServicioConfig for the 2x1 promo.

        Reuses the Laser procedure type and the Tratamiento estetico
        service type produced by the inner seed. Sector=DEP so the
        renderer reads the existing PUNTO_D sections.
        """
        procedure_type = ProcEsteticosTipo.objects.get(tipo="Laser")
        tratamiento_tipo = TipoServicio.objects.get(tipo=TRATAMIENTO_ESTETICO_TIPO)
        sector_dep = Sector.objects.get(codigo="DEP")

        proc, _ = ProcEstetico.objects.update_or_create(
            tipo_p_estetico=procedure_type,
            proceso=DEPILACION_2X1["proc_estetico"]["proceso"],
            defaults={
                "descripcion": DEPILACION_2X1["proc_estetico"]["descripcion"],
                "orden": DEPILACION_2X1["proc_estetico"]["orden"],
                "activo": True,
            },
        )
        servicio, _ = ServicioConfig.objects.update_or_create(
            tipo_servicio=tratamiento_tipo,
            proc_estetico=proc,
            defaults={
                "precio_base": DEPILACION_2X1["servicio"]["precio_base"],
                "sector": sector_dep,
                "activo": True,
            },
        )
        self.stdout.write(self.style.SUCCESS(
            f"Servicio 2x1 creado: {proc.proceso} - "
            f"precio_base={servicio.precio_base} sector={sector_dep.codigo}"
        ))

    def _add_unconverted_prospects(self, branches):
        """Create 10 Prospecto rows in state PASAJERO.

        Distribution across branches comes from the
        ``PROSPECTOS_PASAJEROS`` table (4 Principal, 3 Norte, 3 Sur).
        """
        created = 0
        per_branch = {"principal": 0, "A": 0, "B": 0}
        for primer_nombre, apellido_paterno, telefono, branch_key in PROSPECTOS_PASAJEROS:
            Prospecto.objects.update_or_create(
                primer_nombre=primer_nombre,
                apellido_paterno=apellido_paterno,
                defaults={
                    "segundo_nombre": "",
                    "apellido_materno": "",
                    "telefono": telefono,
                    "sucursal_registro": branches[branch_key],
                    "estado": Prospecto.Estado.PASAJERO,
                },
            )
            created += 1
            per_branch[branch_key] += 1
        self.stdout.write(self.style.SUCCESS(
            f"Prospectos sin convertir (PASAJERO): {created} "
            f"(Principal={per_branch['principal']}, "
            f"Norte={per_branch['A']}, "
            f"Sur={per_branch['B']})"
        ))

    def _add_converted_prospects(self, branches, roles):
        """Create 10 Prospecto + Cliente pairs.

        Each iteration:
        1. Upserts the CLIENTE Usuario.
        2. Upserts the Cliente row in state INACTIVO.
        3. Upserts the Prospecto in state PASAJERO first, then promotes
           it to CONVERTIDO via ``marcar_como_convertido`` so the model's
           invariants are respected (estado==CONVERTIDO implies
           non-null ``convertido_a_cliente`` and ``fecha_conversion``).
        """
        cliente_role = roles["CLIENTE"]
        created = 0
        per_branch = {"principal": 0, "A": 0, "B": 0}
        for (
            primer_nombre, apellido_paterno, telefono,
            username, ci, telefono_cliente, fecha_nacimiento,
            branch_key, direccion,
        ) in PROSPECTOS_CONVERTIDOS:
            branch = branches[branch_key]
            user, _ = Usuario.objects.update_or_create(
                username=username,
                defaults={
                    "primer_nombre": primer_nombre,
                    "segundo_nombre": "",
                    "apellido_paterno": apellido_paterno,
                    "apellido_materno": "",
                    "email": f"{username}@clinic.local",
                    "rol": cliente_role,
                    "sucursal": branch,
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                },
            )
            user.set_password("cliente123456")
            user.save(update_fields=["password"])

            cliente, _ = Cliente.objects.update_or_create(
                usuario=user,
                defaults={
                    "sucursal_origen": branch,
                    "ci": ci,
                    "estado_cliente": Cliente.Estado.INACTIVO,
                    "fecha_nacimiento": fecha_nacimiento,
                    "direccion_domicilio": direccion,
                    "telefono": telefono_cliente,
                },
            )

            prospect, _ = Prospecto.objects.update_or_create(
                primer_nombre=primer_nombre,
                apellido_paterno=apellido_paterno,
                defaults={
                    "segundo_nombre": "",
                    "apellido_materno": "",
                    "telefono": telefono,
                    "sucursal_registro": branch,
                    "estado": Prospecto.Estado.PASAJERO,
                },
            )
            prospect.marcar_como_convertido(cliente)
            created += 1
            per_branch[branch_key] += 1
        self.stdout.write(self.style.SUCCESS(
            f"Prospectos convertidos + clientes INACTIVOS: {created} "
            f"(Principal={per_branch['principal']}, "
            f"Norte={per_branch['A']}, "
            f"Sur={per_branch['B']})"
        ))

    # -- Summary -------------------------------------------------------------

    def _print_summary(self):
        from catalogs.models import Sucursal
        self.stdout.write(self.style.SUCCESS(
            "Reset PDF baseline + extended demo fixtures complete."
        ))
        # Group specialists by branch and print the per-branch list.
        branches = list(Sucursal.objects.filter(activa=True).order_by(
            "-es_principal", "nombre"
        ))
        per_branch_lines = []
        for branch in branches:
            specialists_in_branch = Especialista.objects.filter(
                sucursal_base=branch
            ).select_related("usuario").order_by("usuario__username")
            usernames = ", ".join(
                s.usuario.username for s in specialists_in_branch
            )
            per_branch_lines.append(
                f"  {branch.nombre} ({specialists_in_branch.count()}): {usernames}"
            )
        self.stdout.write(
            "Resumen extendido: "
            f"especialistas={Especialista.objects.count()}, "
            f"prospectos_pasajeros={Prospecto.objects.filter(estado=Prospecto.Estado.PASAJERO).count()}, "
            f"prospectos_convertidos={Prospecto.objects.filter(estado=Prospecto.Estado.CONVERTIDO).count()}, "
            f"clientes_inactivos={Cliente.objects.filter(estado_cliente=Cliente.Estado.INACTIVO).count()}, "
            f"procedimientos_esteticos={ProcEstetico.objects.count()}, "
            f"servicios_config={ServicioConfig.objects.count()}"
        )
        self.stdout.write("Distribucion de especialistas por sucursal:")
        for line in per_branch_lines:
            self.stdout.write(line)
