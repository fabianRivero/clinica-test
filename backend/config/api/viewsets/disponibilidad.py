"""
Availability ViewSet for DRF migration.
Domain 9 of Phase 6 — Disponibilidad (Availability Management).

9 endpoints in a single ViewSet:
- GET  /disponibilidad/                            → list all availability data
- POST /disponibilidad/habitual/crear/            → create habitual schedule
- POST /disponibilidad/habitual/<int:rule_id>/actualizar/  → update rule
- POST /disponibilidad/habitual/<int:rule_id>/eliminar/    → delete rule
- POST /disponibilidad/excepciones/crear/         → create specialist exception
- POST /disponibilidad/excepciones/<int:exception_id>/eliminar/ → delete exception
- POST /disponibilidad/global/gestionar/          → manage global branch closure day
- POST /disponibilidad/concurrencia/             → check concurrency at time
- GET  /disponibilidad/sucursales/               → list branches
"""

from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from catalogs.models import Sucursal
from operations.models import (
    AgendaExcepcionEspecialista,
    AgendaHabitualDia,
    AgendaHabitualEspecialista,
)
from operations.scheduling import get_concurrency, get_specialists_present
from staff.models import Especialista

from config.api.permissions import AdminRequired
from config.api.serializers.disponibilidad import (
    HabitualScheduleCreateSerializer,
    HabitualScheduleUpdateSerializer,
    SpecialistExceptionCreateSerializer,
    GlobalDayManageSerializer,
    ConcurrencyCheckSerializer,
)
from config.api_helpers import get_user_branch


def _specialists_for_branch(branch):
    qs = Especialista.objects.select_related("usuario").filter(usuario__is_active=True)
    if branch:
        qs = qs.filter(sucursal_base=branch)
    return qs.order_by("usuario__primer_nombre", "usuario__apellido_paterno")


def _validate_branch_specialists(branch, specialist_ids):
    valid_ids = set(
        _specialists_for_branch(branch).filter(pk__in=specialist_ids).values_list("id", flat=True)
    )
    requested_ids = {int(item) for item in specialist_ids}
    if requested_ids != valid_ids:
        raise ValueError("Solo puedes gestionar especialistas de la sucursal activa.")


class DisponibilidadViewSet(viewsets.ViewSet):
    """
    DRF ViewSet for availability/scheduling management.

    Endpoints:
    - GET  /disponibilidad/                            → list all availability data
    - POST /disponibilidad/habitual/crear/            → create habitual schedule
    - POST /disponibilidad/habitual/<int:rule_id>/actualizar/  → update rule
    - POST /disponibilidad/habitual/<int:rule_id>/eliminar/    → delete rule
    - POST /disponibilidad/excepciones/crear/         → create specialist exception
    - POST /disponibilidad/excepciones/<int:exception_id>/eliminar/ → delete exception
    - POST /disponibilidad/global/gestionar/          → manage global branch day
    - POST /disponibilidad/concurrencia/             → check concurrency
    - GET  /disponibilidad/sucursales/               → list branches
    """

    permission_classes = [AdminRequired]

    def list(self, request):
        """
        GET /disponibilidad/
        Returns full availability data: branches, specialists, habitual rules, exceptions, global blocks.
        """
        branch = get_user_branch(request)

        # Branches
        branches = list(Sucursal.objects.filter(activa=True).values("id", "nombre", "es_principal"))

        # Specialists
        specialists = []
        for sp in _specialists_for_branch(branch):
            specialists.append({
                "id": sp.id,
                "label": f"{sp.usuario.primer_nombre} {sp.usuario.apellido_paterno}",
                "secondaryLabel": sp.usuario.email,
            })

        # Weekday options
        from operations.models import DiaSemana
        weekday_options = [{"value": d.value, "label": d.label} for d in DiaSemana]

        # Global blocks (branch closures)
        global_blocks = []
        branch_block_qs = AgendaExcepcionEspecialista.objects.filter(
            activo=True,
            tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
            detalle__startswith="[CIERRE_SUCURSAL]",
        )
        if branch:
            branch_block_qs = branch_block_qs.filter(sucursal=branch)
        seen_block_dates = set()
        for gb in branch_block_qs.order_by("-fecha", "id"):
            if gb.fecha in seen_block_dates:
                continue
            seen_block_dates.add(gb.fecha)
            global_blocks.append({
                "id": gb.pk,
                "date": str(gb.fecha),
                "dateLabel": gb.fecha.strftime("%d/%m/%Y"),
                "active": gb.activo,
                "detail": gb.detalle.replace("[CIERRE_SUCURSAL]", "").strip(),
            })

        # Habitual rules
        habitual_rules = []
        rules = AgendaHabitualEspecialista.objects.filter(activo=True).prefetch_related("dias")
        if branch:
            rules = rules.filter(sucursal=branch, especialista__sucursal_base=branch)
        for r in rules:
            habitual_rules.append({
                "id": r.id,
                "specialistId": r.especialista_id,
                "branchId": r.sucursal_id,
                "startDate": str(r.fecha_inicio),
                "endDate": str(r.fecha_fin) if r.fecha_fin else None,
                "weekdayCodes": list(r.dias.values_list("dia_semana", flat=True)),
                "weekdayLabels": [DiaSemana(d).label for d in r.dias.values_list("dia_semana", flat=True)],
                "startTime": r.hora_inicio.strftime("%H:%M") if r.hora_inicio else "00:00",
                "endTime": r.hora_fin.strftime("%H:%M") if r.hora_fin else "00:00",
                "detail": r.detalle,
                "active": r.activo,
            })

        # Exceptions
        exceptions = []
        exs = AgendaExcepcionEspecialista.objects.filter(activo=True).exclude(
            detalle__startswith="[CIERRE_SUCURSAL]"
        )
        if branch:
            exs = exs.filter(sucursal=branch, especialista__sucursal_base=branch)
        for e in exs:
            exceptions.append({
                "id": e.id,
                "specialistId": e.especialista_id,
                "branchId": e.sucursal_id,
                "date": str(e.fecha),
                "dateLabel": e.fecha.strftime("%d/%m/%Y"),
                "type": e.tipo_excepcion,
                "typeLabel": "Bloqueo" if e.tipo_excepcion == "BLOQUEAR" else "Hora Extra",
                "startTime": e.hora_inicio.strftime("%H:%M") if e.hora_inicio else "00:00",
                "endTime": e.hora_fin.strftime("%H:%M") if e.hora_fin else "00:00",
                "detail": e.detalle,
                "active": e.activo,
            })

        return Response({
            "metrics": [],
            "branches": branches,
            "filters": {
                "specialists": specialists,
                "weekdayOptions": weekday_options,
            },
            "habitualRules": habitual_rules,
            "exceptions": exceptions,
            "globalBlocks": global_blocks,
        })

    @action(detail=False, methods=["post"], url_path="habitual/crear")
    def crear_habitual(self, request):
        """
        POST /disponibilidad/habitual/crear/
        Create habitual schedule rule(s) for one or more specialists.
        """
        serializer = HabitualScheduleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        specialist_ids = data.get("specialistIds") or []
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]

        if not specialist_ids:
            return Response({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return Response({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)

        try:
            _validate_branch_specialists(branch, specialist_ids)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        with transaction.atomic():
            for sp_id in specialist_ids:
                agenda = AgendaHabitualEspecialista.objects.create(
                    especialista_id=sp_id,
                    sucursal_id=data["branchId"],
                    fecha_inicio=data["startDate"],
                    fecha_fin=data.get("endDate") or None,
                    hora_inicio=data.get("startTime"),
                    hora_fin=data.get("endTime"),
                    detalle=data.get("detail", ""),
                )
                for d in data.get("weekdayCodes", []):
                    AgendaHabitualDia.objects.create(agenda=agenda, dia_semana=d)

        return Response({"detail": "Agenda(s) habitual(es) creada(s) exitosamente"})

    @action(detail=True, methods=["post"], url_path="habitual/(?P<rule_id>[0-9]+)/actualizar")
    def actualizar_habitual(self, request, rule_id=None):
        """
        POST /disponibilidad/habitual/<int:rule_id>/actualizar/
        Update a habitual schedule rule.
        """
        serializer = HabitualScheduleUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        branch = get_user_branch(request)

        try:
            agenda = AgendaHabitualEspecialista.objects.get(pk=rule_id, sucursal=branch)
        except AgendaHabitualEspecialista.DoesNotExist:
            return Response({"detail": "No encontramos la agenda solicitada."}, status=404)

        if agenda.especialista.sucursal_base_id != branch.pk:
            return Response({"detail": "Solo puedes gestionar especialistas de la sucursal activa."}, status=400)

        if "branchId" in data and int(data["branchId"]) != branch.pk:
            return Response({"detail": "No puedes mover una agenda a otra sucursal desde esta pantalla."}, status=400)

        with transaction.atomic():
            if "startDate" in data:
                agenda.fecha_inicio = data["startDate"]
            if "endDate" in data:
                agenda.fecha_fin = data["endDate"] or None
            if "startTime" in data:
                agenda.hora_inicio = data["startTime"]
            if "endTime" in data:
                agenda.hora_fin = data["endTime"]
            if "detail" in data:
                agenda.detalle = data["detail"]
            if "active" in data:
                agenda.activo = data["active"]
            agenda.save()

            if "weekdayCodes" in data:
                agenda.dias.all().delete()
                for d in data["weekdayCodes"]:
                    AgendaHabitualDia.objects.create(agenda=agenda, dia_semana=d)

        return Response({"detail": "Agenda habitual actualizada exitosamente"})

    @action(detail=True, methods=["post"], url_path="habitual/(?P<rule_id>[0-9]+)/eliminar")
    def eliminar_habitual(self, request, rule_id=None):
        """
        POST /disponibilidad/habitual/<int:rule_id>/eliminar/
        Delete a habitual schedule rule.
        """
        branch = get_user_branch(request)
        deleted, _ = AgendaHabitualEspecialista.objects.filter(pk=rule_id, sucursal=branch).delete()
        if deleted == 0:
            return Response({"detail": "No encontramos la agenda solicitada."}, status=404)
        return Response({"detail": "Agenda eliminada"})

    @action(detail=False, methods=["post"], url_path="excepciones/crear")
    def crear_excepcion(self, request):
        """
        POST /disponibilidad/excepciones/crear/
        Create specialist exceptions (block hours or extra hours).
        Supports both specific dates and date ranges with weekday filters.
        """
        serializer = SpecialistExceptionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        specialist_ids = data.get("specialistIds") or []
        if not specialist_ids and data.get("specialistId"):
            specialist_ids = [data["specialistId"]]

        if not specialist_ids:
            return Response({"detail": "Debes seleccionar al menos un especialista."}, status=400)

        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Debes seleccionar una sucursal activa."}, status=400)
        if int(data.get("branchId") or 0) != branch.pk:
            return Response({"detail": "La sucursal enviada no coincide con la sucursal activa."}, status=400)

        try:
            _validate_branch_specialists(branch, specialist_ids)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        dates = set(data.get("dates") or [])

        range_start = data.get("rangeStartDate") or ""
        range_end = data.get("rangeEndDate") or ""
        weekday_codes = data.get("weekdayCodes") or []

        if range_start or range_end or weekday_codes:
            if not (range_start and range_end and weekday_codes):
                return Response(
                    {"detail": "Para usar rango debes enviar fecha inicio, fecha fin y dias de semana."},
                    status=400,
                )
            start_date = datetime.strptime(range_start, "%Y-%m-%d").date()
            end_date = datetime.strptime(range_end, "%Y-%m-%d").date()
            if start_date > end_date:
                return Response({"detail": "La fecha inicio no puede ser mayor que la fecha fin."}, status=400)

            weekdays = {int(w) for w in weekday_codes}
            cursor = start_date
            while cursor <= end_date:
                django_weekday = cursor.weekday() + 1
                if django_weekday in weekdays:
                    dates.add(cursor.strftime("%Y-%m-%d"))
                cursor += timedelta(days=1)

        if not dates:
            return Response({"detail": "Debes enviar al menos una fecha valida."}, status=400)

        with transaction.atomic():
            for sp_id in specialist_ids:
                for d_str in sorted(dates):
                    AgendaExcepcionEspecialista.objects.create(
                        especialista_id=sp_id,
                        sucursal_id=data["branchId"],
                        fecha=d_str,
                        hora_inicio=data.get("startTime") or None,
                        hora_fin=data.get("endTime") or None,
                        tipo_excepcion=data["type"],
                        detalle=data.get("detail", ""),
                    )

        return Response({"detail": "Excepcion(es) creada(s)"})

    @action(detail=True, methods=["post"], url_path="excepciones/(?P<exception_id>[0-9]+)/eliminar")
    def eliminar_excepcion(self, request, exception_id=None):
        """
        POST /disponibilidad/excepciones/<int:exception_id>/eliminar/
        Delete a specialist exception.
        """
        branch = get_user_branch(request)
        deleted, _ = AgendaExcepcionEspecialista.objects.filter(
            pk=exception_id, sucursal=branch
        ).delete()
        if deleted == 0:
            return Response({"detail": "No encontramos la excepcion solicitada."}, status=404)
        return Response({"detail": "Excepcion eliminada"})

    @action(detail=False, methods=["post"], url_path="global/gestionar")
    def gestionar_dia_global(self, request):
        """
        POST /disponibilidad/global/gestionar/
        Block or unblock an entire branch for a given date (applies to all specialists).
        """
        serializer = GlobalDayManageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        branch = get_user_branch(request)
        if not branch:
            return Response({"detail": "Debes seleccionar una sucursal activa."}, status=400)

        specialists = list(_specialists_for_branch(branch))
        detail = f"[CIERRE_SUCURSAL] {data.get('detail', '')}".strip()

        with transaction.atomic():
            if data["action"] == "BLOQUEAR":
                if not specialists:
                    return Response(
                        {"detail": "No hay especialistas activos en esta sucursal para aplicar el cierre."},
                        status=400,
                    )
                for specialist in specialists:
                    AgendaExcepcionEspecialista.objects.update_or_create(
                        especialista=specialist,
                        sucursal=branch,
                        fecha=data["date"],
                        tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
                        detalle__startswith="[CIERRE_SUCURSAL]",
                        defaults={
                            "hora_inicio": None,
                            "hora_fin": None,
                            "activo": True,
                            "detalle": detail,
                        },
                    )
            else:
                AgendaExcepcionEspecialista.objects.filter(
                    sucursal=branch,
                    fecha=data["date"],
                    tipo_excepcion=AgendaExcepcionEspecialista.TipoExcepcion.BLOQUEAR,
                    detalle__startswith="[CIERRE_SUCURSAL]",
                ).update(activo=False)

        return Response({"detail": "Dia de cierre de sucursal actualizado"})

    @action(detail=False, methods=["post"], url_path="concurrencia")
    def concurrencia(self, request):
        """
        POST /disponibilidad/concurrencia/
        Check appointment concurrency and specialists present at a given time.
        """
        serializer = ConcurrencyCheckSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": "Datos inválidos.", "errors": serializer.errors}, status=400)

        data = serializer.validated_data
        fecha = datetime.strptime(data["fecha"], "%Y-%m-%d").date()
        hora_inicio = datetime.strptime(data["hora_inicio"], "%H:%M").time()

        # Window: 1 hour before and 1 hour after
        dt_inicio = datetime.combine(fecha, hora_inicio)
        dt_ventana_inicio = dt_inicio - timedelta(hours=1)
        dt_ventana_fin = dt_inicio + timedelta(hours=1)
        hora_ventana_inicio = dt_ventana_inicio.time()
        hora_ventana_fin = dt_ventana_fin.time()

        concurrency = get_concurrency(
            data["sucursal_id"], fecha, hora_ventana_inicio, hora_ventana_fin
        )
        presentes = get_specialists_present(
            data["sucursal_id"], fecha, hora_inicio, hora_inicio
        )

        especialistas = []
        for esp in Especialista.objects.filter(id__in=presentes).select_related("usuario"):
            especialistas.append({
                "id": esp.id,
                "usuario__primer_nombre": esp.usuario.primer_nombre,
                "usuario__apellido_paterno": esp.usuario.apellido_paterno,
                "especialidad": ", ".join(
                    esp.especialidades_rel.values_list("especialidad__nombre", flat=True)
                ),
            })

        return Response({
            "concurrency": concurrency,
            "presentes": especialistas,
            "hora_inicio": hora_ventana_inicio.strftime("%H:%M"),
            "hora_fin": hora_ventana_fin.strftime("%H:%M"),
            "hora_seleccionada": hora_inicio.strftime("%H:%M"),
        })

    @action(detail=False, methods=["get"], url_path="sucursales")
    def sucursales(self, request):
        """
        GET /disponibilidad/sucursales/
        List all active branches.
        """
        sucursales = list(Sucursal.objects.filter(activa=True).values("id", "nombre", "es_principal"))
        return Response({"branches": sucursales})
