import json

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Usuario
from operations.models import Ticket, TicketMessage
from staff.models import Especialista


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _load_payload(request):
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


def _effective_admin_branch(request):
    if request.user.sucursal_id:
        return request.user.sucursal
    selected = request.headers.get("X-Selected-Branch-Id")
    if selected:
        try:
            return request.user.sucursal.__class__.objects.filter(pk=int(selected), activa=True).first()
        except Exception:
            return None
    return None


def _ticket_visible_to_user(ticket, user):
    if _is_admin(user):
        branch = _effective_admin_branch(type("R", (), {"user": user, "headers": {}})())
        if user.es_admin_principal or user.is_superuser:
            return branch is None or ticket.sucursal_id == branch.id
        return user.sucursal_id and ticket.sucursal_id == user.sucursal_id
    return ticket.especialista_id and ticket.especialista.usuario_id == user.id


def _message_item(message):
    return {
        "id": message.id,
        "authorId": message.autor_id,
        "authorName": message.autor.nombre_completo or message.autor.username,
        "authorRole": message.autor.rol.rol if message.autor.rol else "",
        "body": message.contenido,
        "status": message.estado,
        "createdAt": timezone.localtime(message.created_at).isoformat(),
    }


def _ticket_item(ticket):
    return {
        "id": ticket.id,
        "subject": ticket.asunto,
        "status": ticket.estado,
        "branchId": ticket.sucursal_id,
        "branchName": ticket.sucursal.nombre,
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
        if user.es_admin_sucursal and user.sucursal_id:
            qs = qs.filter(sucursal_id=user.sucursal_id)
        elif (user.es_admin_principal or user.is_superuser) and request.headers.get("X-Selected-Branch-Id"):
            qs = qs.filter(sucursal_id=int(request.headers["X-Selected-Branch-Id"]))
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
        if specialist.sucursal_base and not specialist.sucursal_base.especialistas_pueden_abrir_fichas:
            return _json({"detail": "Tu sucursal no permite abrir nuevas fichas."}, status=403)
        branch = specialist.sucursal_base or user.sucursal
    else:
        if not specialist_id:
            return _json({"detail": "specialistId es obligatorio para admin."}, status=400)
        specialist = get_object_or_404(Especialista.objects.select_related("usuario", "sucursal_base"), pk=specialist_id)
        branch = specialist.sucursal_base or user.sucursal

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
        TicketMessage.objects.create(ticket=ticket, autor=user, contenido=message, estado=TicketMessage.Estado.ENVIADO)

    return _json({"detail": "Ficha creada.", "ticket": _ticket_item(ticket)}, status=201)


@require_GET
@_comms_required
def tickets_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related("sucursal", "especialista__usuario", "creado_por"), pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request.user):
        return _json({"detail": "No autorizado."}, status=403)
    messages = TicketMessage.objects.filter(ticket=ticket).select_related("autor", "autor__rol").order_by("created_at")
    return _json({"ticket": _ticket_item(ticket), "messages": [_message_item(m) for m in messages]})


@require_POST
@_comms_required
def tickets_reply(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request.user):
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
        msg = TicketMessage.objects.create(ticket=ticket, autor=request.user, contenido=body, estado=TicketMessage.Estado.ENVIADO)
        TicketMessage.objects.filter(ticket=ticket, estado=TicketMessage.Estado.ENVIADO).exclude(autor=request.user).update(estado=TicketMessage.Estado.RESPONDIDO)

    return _json({"detail": "Respuesta enviada.", "message": _message_item(msg)})


@require_POST
@_comms_required
def tickets_close(request, ticket_id):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin puede cerrar fichas."}, status=403)
    ticket = get_object_or_404(Ticket, pk=ticket_id)
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
    ticket.estado = Ticket.Estado.ABIERTO
    ticket.closed_at = None
    ticket.save(update_fields=["estado", "closed_at", "updated_at"])
    return _json({"detail": "Ficha reabierta.", "ticket": _ticket_item(ticket)})


@require_POST
@_comms_required
def admin_ticket_open_permission(request):
    if not _is_admin(request.user):
        return _json({"detail": "Solo admin."}, status=403)
    payload = _load_payload(request)
    if payload is None or "enabled" not in payload:
        return _json({"detail": "enabled es obligatorio."}, status=400)
    enabled = bool(payload["enabled"])
    branch = request.user.sucursal
    if not branch:
        return _json({"detail": "Admin sin sucursal."}, status=400)
    branch.especialistas_pueden_abrir_fichas = enabled
    branch.save(update_fields=["especialistas_pueden_abrir_fichas", "updated_at"])
    return _json({"detail": "Permiso actualizado.", "enabled": enabled, "branchId": branch.id})
