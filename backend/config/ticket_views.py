import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from operations.models import Ticket, TicketMessage
from staff.models import Especialista
from accounts.models import Usuario
from notifications.models import Notification
from notifications.services import create_notification


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _load_payload(request):
    content_type = request.META.get("CONTENT_TYPE", "")
    if "multipart/form-data" in content_type:
        return request.POST.dict()
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return None


def _comms_required(view_func):
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            return _json({"detail": "Autenticacion requerida."}, status=401)
        if not (user.es_administrador or user.es_trabajador or user.is_superuser):
            return _json({"detail": "No tienes permisos."}, status=403)
        return view_func(request, *args, **kwargs)

    return wrapped


def _is_admin(user):
    return user.is_superuser or user.es_administrador


def _admin_branch(request):
    user = request.user
    if user.es_admin_sucursal and user.sucursal_id:
        return user.sucursal
    selected = request.headers.get("X-Selected-Branch-Id")
    if selected:
        from catalogs.models import Sucursal
        return Sucursal.objects.filter(pk=int(selected), activa=True).first()
    return user.sucursal


def _ticket_visible_to_user(ticket, request):
    user = request.user
    if _is_admin(user):
        branch = _admin_branch(request)
        if user.es_admin_principal or user.is_superuser:
            return branch is None or ticket.sucursal_id == branch.id
        return user.sucursal_id and ticket.sucursal_id == user.sucursal_id
    return ticket.especialista_id and ticket.especialista.usuario_id == user.id



def _notify_ticket_message(ticket, author, body):
    participant_ids = set(
        TicketMessage.objects.filter(ticket=ticket)
        .exclude(autor_id=author.id)
        .values_list("autor_id", flat=True)
    )
    if ticket.creado_por_id and ticket.creado_por_id != author.id:
        participant_ids.add(ticket.creado_por_id)
    specialist_user_id = getattr(ticket.especialista, "usuario_id", None)
    if specialist_user_id and specialist_user_id != author.id:
        participant_ids.add(specialist_user_id)

    recipients = Usuario.objects.filter(id__in=participant_ids, is_active=True)
    for recipient in recipients:
        if recipient.es_trabajador:
            notif_type = Notification.Type.SPECIALIST_MESSAGE_FROM_ADMIN if author.es_administrador else Notification.Type.SPECIALIST_MESSAGE_FROM_ADMIN
            title = "Nueva respuesta en ficha"
            action_url = "/trabajador/mensajes/fichas"
        elif recipient.es_administrador or recipient.is_superuser:
            notif_type = (
                Notification.Type.ADMIN_MESSAGE_FROM_SPECIALIST
                if author.es_trabajador
                else (Notification.Type.ADMIN_MESSAGE_FROM_GENERAL_ADMIN if author.es_admin_principal else Notification.Type.ADMIN_MESSAGE_FROM_ADMIN)
            )
            title = "Nueva respuesta en ficha"
            action_url = f"/admin/mensajes/fichas/{ticket.id}"
        else:
            continue

        create_notification(
            recipient=recipient,
            branch=ticket.sucursal,
            type=notif_type,
            title=title,
            message=body[:180],
            action_url=action_url,
            source_event="ticket.message",
            source_entity_type="ticket",
            source_entity_id=ticket.id,
            created_by_type="specialist" if author.es_trabajador else "admin",
            created_by_id=author.id,
        )


def _message_item(message):
    return {
        "id": message.id,
        "authorId": message.autor_id,
        "authorName": message.autor.nombre_completo or message.autor.username,
        "authorRole": message.autor.rol.rol if message.autor.rol else "",
        "body": message.contenido,
        "status": message.estado,
        "createdAt": timezone.localtime(message.created_at).isoformat(),
        "attachmentUrl": message.adjunto.url if message.adjunto else None,
        "attachmentName": message.adjunto.name.split("/")[-1] if message.adjunto else None,
    }


def _ticket_item(ticket):
    return {
        "id": ticket.id,
        "subject": ticket.asunto,
        "status": ticket.estado,
        "branchId": ticket.sucursal_id,
        "branchName": ticket.sucursal.nombre,
        "specialistId": ticket.especialista_id,
        "specialistName": ticket.especialista.usuario.nombre_completo if ticket.especialista_id else "",
        "createdBy": ticket.creado_por.nombre_completo if ticket.creado_por_id else "",
        "updatedAt": timezone.localtime(ticket.updated_at).isoformat(),
        "closedAt": timezone.localtime(ticket.closed_at).isoformat() if ticket.closed_at else None,
    }


@require_GET
@_comms_required
def tickets_list(request):
    user = request.user
    qs = Ticket.objects.select_related("sucursal", "especialista__usuario", "creado_por").order_by("-updated_at")
    if _is_admin(user):
        branch = _admin_branch(request)
        if branch:
            qs = qs.filter(sucursal=branch)
    else:
        qs = qs.filter(especialista__usuario=user)

    status_filter = request.GET.get("status")
    if status_filter in {Ticket.Estado.ABIERTO, Ticket.Estado.CERRADO}:
        qs = qs.filter(estado=status_filter)

    return _json({"tickets": [_ticket_item(t) for t in qs]})


@require_POST
@_comms_required
def tickets_create(request):
    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "JSON invalido."}, status=400)

    subject = (payload.get("subject") or "").strip()
    message = (payload.get("message") or "").strip()
    specialist_id = payload.get("specialistId")
    if not subject or not message:
        return _json({"detail": "Asunto y mensaje son obligatorios."}, status=400)

    user = request.user
    if user.es_trabajador:
        specialist = getattr(user, "especialista", None)
        if not specialist:
            return _json({"detail": "Perfil de especialista no encontrado."}, status=400)
        if specialist.sucursal_base and (
            not specialist.sucursal_base.especialistas_pueden_abrir_fichas or not specialist.puede_abrir_fichas
        ):
            return _json({"detail": "No tienes permiso para abrir nuevas fichas."}, status=403)
        branch = specialist.sucursal_base or user.sucursal
    else:
        if not specialist_id:
            return _json({"detail": "specialistId es obligatorio para admin."}, status=400)
        specialist = get_object_or_404(Especialista.objects.select_related("usuario", "sucursal_base"), pk=specialist_id)
        branch = specialist.sucursal_base or _admin_branch(request) or user.sucursal

    if not branch:
        return _json({"detail": "No se pudo determinar la sucursal de la ficha."}, status=400)

    with transaction.atomic():
        ticket = Ticket.objects.create(
            asunto=subject,
            estado=Ticket.Estado.ABIERTO,
            sucursal=branch,
            especialista=specialist,
            creado_por=user,
        )
        attachment = request.FILES.get('attachment')
        TicketMessage.objects.create(ticket=ticket, autor=user, contenido=message, adjunto=attachment, estado=TicketMessage.Estado.ENVIADO)
        _notify_ticket_message(ticket, user, message)

    return _json({"detail": "Ficha creada.", "ticket": _ticket_item(ticket)}, status=201)


@require_GET
@_comms_required
def tickets_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related("sucursal", "especialista__usuario", "creado_por"), pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return _json({"detail": "No autorizado."}, status=403)
    messages = TicketMessage.objects.filter(ticket=ticket).select_related("autor", "autor__rol").order_by("created_at")
    return _json({"ticket": _ticket_item(ticket), "messages": [_message_item(m) for m in messages]})


@require_POST
@_comms_required
def tickets_reply(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return _json({"detail": "No autorizado."}, status=403)
    if ticket.estado == Ticket.Estado.CERRADO:
        return _json({"detail": "La ficha esta cerrada."}, status=400)

    payload = _load_payload(request)
    if payload is None:
        return _json({"detail": "JSON invalido."}, status=400)
    body = (payload.get("message") or "").strip()
    if not body:
        return _json({"detail": "El mensaje es obligatorio."}, status=400)

    with transaction.atomic():
        attachment = request.FILES.get('attachment')
        msg = TicketMessage.objects.create(ticket=ticket, autor=request.user, contenido=body, adjunto=attachment, estado=TicketMessage.Estado.ENVIADO)
        _notify_ticket_message(ticket, request.user, body)

    return _json({"detail": "Respuesta enviada.", "message": _message_item(msg)})


@require_POST
@_comms_required
def tickets_close(request, ticket_id):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin puede cerrar fichas."}, status=403)
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return _json({"detail": "No autorizado."}, status=403)
    ticket.estado = Ticket.Estado.CERRADO
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=["estado", "closed_at", "updated_at"])
    return _json({"detail": "Ficha cerrada.", "ticket": _ticket_item(ticket)})


@require_POST
@_comms_required
def tickets_reopen(request, ticket_id):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin puede reabrir fichas."}, status=403)
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return _json({"detail": "No autorizado."}, status=403)
    ticket.estado = Ticket.Estado.ABIERTO
    ticket.closed_at = None
    ticket.save(update_fields=["estado", "closed_at", "updated_at"])
    return _json({"detail": "Ficha reabierta.", "ticket": _ticket_item(ticket)})


@require_GET
@_comms_required
def admin_ticket_open_permission_status(request):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin."}, status=403)
    branch = _admin_branch(request)
    if not branch:
        return _json({"detail": "No se pudo determinar sucursal."}, status=400)
    specialists = list(
        Especialista.objects.select_related("usuario").filter(sucursal_base=branch, usuario__is_active=True)
    )
    items = [
        {
            "specialistId": s.id,
            "specialistName": s.usuario.nombre_completo,
            "enabled": bool(s.puede_abrir_fichas),
        }
        for s in specialists
    ]
    enabled_count = sum(1 for i in items if i["enabled"])
    if items and enabled_count == len(items):
        summary = "ALL_ENABLED"
    elif items and enabled_count == 0:
        summary = "ALL_BLOCKED"
    else:
        summary = "MIXED"
    return _json({
        "branchId": branch.id,
        "branchName": branch.nombre,
        "branchDefaultEnabled": bool(branch.especialistas_pueden_abrir_fichas),
        "specialists": items,
        "summary": summary,
    })


@require_POST
@_comms_required
def admin_ticket_open_permission(request):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin."}, status=403)
    payload = _load_payload(request)
    if payload is None or "enabled" not in payload:
        return _json({"detail": "enabled es obligatorio."}, status=400)
    enabled = bool(payload["enabled"])
    branch = _admin_branch(request)
    if not branch:
        return _json({"detail": "No se pudo determinar sucursal."}, status=400)

    specialist_id = payload.get("specialistId")
    if specialist_id:
        specialist = get_object_or_404(Especialista, pk=int(specialist_id), sucursal_base=branch)
        specialist.puede_abrir_fichas = enabled
        specialist.save(update_fields=["puede_abrir_fichas", "updated_at"])
        return _json({"detail": "Permiso actualizado.", "enabled": enabled, "specialistId": specialist.id})

    branch.especialistas_pueden_abrir_fichas = enabled
    branch.save(update_fields=["especialistas_pueden_abrir_fichas", "updated_at"])
    Especialista.objects.filter(sucursal_base=branch).update(puede_abrir_fichas=enabled)
    return _json({"detail": "Permisos actualizados para toda la sucursal.", "enabled": enabled, "branchId": branch.id})
