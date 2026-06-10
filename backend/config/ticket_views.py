import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from config.api_helpers import json_response
from notifications.models import Ticket, TicketMessage
from staff.models import Especialista
from accounts.models import Rol, Usuario
from notifications.models import Notification
from notifications.services import create_notification


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
            return json_response({"detail": "Autenticacion requerida."}, status=401)
        if not (user.es_administrador or user.es_trabajador or user.is_superuser):
            return json_response({"detail": "No tienes permisos."}, status=403)
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




def _can_manage_ticket_status(user, ticket):
    if not _is_admin(user):
        return False
    if ticket.destinatario_admin_id:
        return bool(user.es_admin_principal or user.is_superuser)
    return True

def _ticket_visible_to_user(ticket, request):
    user = request.user
    if _is_admin(user):
        branch = _admin_branch(request)
        if ticket.destinatario_admin_id:
            return ticket.creado_por_id == user.id or ticket.destinatario_admin_id == user.id
        if user.es_admin_principal or user.is_superuser:
            return branch is None or ticket.sucursal_id == branch.id
        return user.sucursal_id and ticket.sucursal_id == user.sucursal_id
    return ticket.especialista_id and ticket.especialista.usuario_id == user.id





def _branch_admin_items(request):
    user = request.user
    qs = Usuario.objects.select_related("sucursal").filter(is_active=True, rol__rol="ADMIN_SUCURSAL")
    if user.es_admin_sucursal and user.sucursal_id:
        qs = qs.filter(sucursal_id=user.sucursal_id)
    items = []
    for admin in qs.order_by("sucursal__nombre", "username"):
        items.append({
            "adminId": admin.id,
            "adminName": admin.nombre_completo or admin.username,
            "branchId": admin.sucursal_id,
            "branchName": admin.sucursal.nombre if admin.sucursal_id else "",
            "enabled": bool(admin.is_active),
        })
    return items


def _main_admin_items():
    qs = Usuario.objects.select_related("sucursal").filter(is_active=True, rol__rol="ADMIN_PRINCIPAL")
    return [
        {
            "adminId": admin.id,
            "adminName": admin.nombre_completo or admin.username,
            "branchId": admin.sucursal_id,
            "branchName": admin.sucursal.nombre if admin.sucursal_id else "",
            "enabled": bool(admin.is_active),
        }
        for admin in qs.order_by("username")
    ]
def _notify_ticket_message(ticket, author, body):
    participant_ids = set(
        TicketMessage.objects.filter(ticket=ticket)
        .exclude(autor_id=author.id)
        .values_list("autor_id", flat=True)
    )
    if ticket.creado_por_id and ticket.creado_por_id != author.id:
        participant_ids.add(ticket.creado_por_id)
    specialist_user_id = ticket.especialista.usuario_id if ticket.especialista_id else None
    if specialist_user_id and specialist_user_id != author.id:
        participant_ids.add(specialist_user_id)
    if ticket.destinatario_admin_id and ticket.destinatario_admin_id != author.id:
        participant_ids.add(ticket.destinatario_admin_id)

    recipients = Usuario.objects.filter(id__in=participant_ids, is_active=True)
    for recipient in recipients:
        if recipient.es_trabajador:
            notif_type = Notification.Type.SPECIALIST_MESSAGE_FROM_ADMIN if author.es_administrador else Notification.Type.SPECIALIST_MESSAGE_FROM_ADMIN
            title = "Nuevo mensaje en ficha"
            message = f"Tienes un mensaje del administrador en la ficha con asunto \"{ticket.asunto}\"."
            action_url = "/trabajador/mensajes/fichas"
        elif recipient.es_administrador or recipient.is_superuser:
            if author.es_trabajador:
                notif_type = Notification.Type.ADMIN_MESSAGE_FROM_SPECIALIST
                title = "Nuevo mensaje en ficha"
                especialista_nombre = author.nombre_completo or author.username
                message = f"Tienes un mensaje del especialista {especialista_nombre} en la ficha con asunto \"{ticket.asunto}\"."
            elif author.es_admin_principal:
                notif_type = Notification.Type.ADMIN_MESSAGE_FROM_GENERAL_ADMIN
                title = "Nuevo mensaje en ficha"
                message = f"Tienes un mensaje del administrador general en la ficha con asunto \"{ticket.asunto}\"."
            else:
                notif_type = Notification.Type.ADMIN_MESSAGE_FROM_ADMIN
                title = "Nuevo mensaje en ficha"
                admin_nombre = author.nombre_completo or author.username
                sucursal_nombre = author.sucursal.nombre if author.sucursal else "Sin sucursal"
                message = f"Tienes un mensaje del administrador {admin_nombre} de la sucursal {sucursal_nombre} en la ficha con asunto \"{ticket.asunto}\"."
            action_url = f"/cms/mensajes/fichas/{ticket.id}"
        else:
            continue

        create_notification(
            recipient=recipient,
            branch=ticket.sucursal,
            type=notif_type,
            title=title,
            message=message,
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
        "adminRecipientId": ticket.destinatario_admin_id,
        "adminRecipientName": ticket.destinatario_admin.nombre_completo if ticket.destinatario_admin_id else "",
        "createdBy": ticket.creado_por.nombre_completo if ticket.creado_por_id else "",
        "updatedAt": timezone.localtime(ticket.updated_at).isoformat(),
        "closedAt": timezone.localtime(ticket.closed_at).isoformat() if ticket.closed_at else None,
    }


@require_GET
@_comms_required
def tickets_list(request):
    user = request.user
    qs = Ticket.objects.select_related("sucursal", "especialista__usuario", "creado_por", "destinatario_admin").order_by("-updated_at")
    if _is_admin(user):
        # Tickets admin↔admin must be visible to both participants regardless of selected branch.
        admin_qs = qs.filter(destinatario_admin__isnull=False).filter(creado_por=user) | qs.filter(destinatario_admin=user)
        specialist_qs = qs.filter(destinatario_admin__isnull=True)
        branch = _admin_branch(request)
        if branch:
            specialist_qs = specialist_qs.filter(sucursal=branch)
        qs = (admin_qs | specialist_qs).distinct()
    else:
        qs = qs.filter(especialista__usuario=user)

    status_filter = request.GET.get("status")
    if status_filter in {Ticket.Estado.ABIERTO, Ticket.Estado.CERRADO}:
        qs = qs.filter(estado=status_filter)

    return json_response({"tickets": [_ticket_item(t) for t in qs]})


@require_POST
@_comms_required
def tickets_create(request):
    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "JSON invalido."}, status=400)

    subject = (payload.get("subject") or "").strip()
    message = (payload.get("message") or "").strip()
    specialist_id = payload.get("specialistId")
    admin_recipient_id = payload.get("adminRecipientId")
    if not subject or not message:
        return json_response({"detail": "Asunto y mensaje son obligatorios."}, status=400)

    user = request.user
    if user.es_trabajador:
        specialist = getattr(user, "especialista", None)
        if not specialist:
            return json_response({"detail": "Perfil de especialista no encontrado."}, status=400)
        if specialist.sucursal_base and (
            not specialist.sucursal_base.especialistas_pueden_abrir_fichas or not specialist.puede_abrir_fichas
        ):
            return json_response({"detail": "No tienes permiso para abrir nuevas fichas."}, status=403)
        branch = specialist.sucursal_base or user.sucursal
    else:
        specialist = None
        admin_recipient = None
        if specialist_id:
            specialist = get_object_or_404(Especialista.objects.select_related("usuario", "sucursal_base"), pk=specialist_id)
            branch = specialist.sucursal_base or _admin_branch(request) or user.sucursal
        elif admin_recipient_id:
            admin_recipient = get_object_or_404(Usuario.objects.select_related("rol", "sucursal"), pk=admin_recipient_id, is_active=True)
            is_branch_to_main = user.es_admin_sucursal and admin_recipient.es_admin_principal
            is_main_to_branch = user.es_admin_principal and admin_recipient.es_admin_sucursal
            if not (is_branch_to_main or is_main_to_branch):
                return json_response({"detail": "No tienes permiso para crear fichas con este administrador."}, status=403)
            branch = user.sucursal or admin_recipient.sucursal or _admin_branch(request)
        else:
            return json_response({"detail": "specialistId o adminRecipientId es obligatorio para admin."}, status=400)

    if not branch:
        return json_response({"detail": "No se pudo determinar la sucursal de la ficha."}, status=400)

    with transaction.atomic():
        ticket = Ticket.objects.create(
            asunto=subject,
            estado=Ticket.Estado.ABIERTO,
            sucursal=branch,
            especialista=specialist,
            destinatario_admin=admin_recipient if not specialist else None,
            creado_por=user,
        )
        attachment = request.FILES.get('attachment')
        TicketMessage.objects.create(ticket=ticket, autor=user, contenido=message, adjunto=attachment, estado=TicketMessage.Estado.ENVIADO)
        _notify_ticket_message(ticket, user, message)

    return json_response({"detail": "Ficha creada.", "ticket": _ticket_item(ticket)}, status=201)


@require_GET
@_comms_required
def tickets_detail(request, ticket_id):
    ticket = get_object_or_404(Ticket.objects.select_related("sucursal", "especialista__usuario", "creado_por", "destinatario_admin"), pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return json_response({"detail": "No autorizado."}, status=403)
    messages = TicketMessage.objects.filter(ticket=ticket).select_related("autor", "autor__rol").order_by("created_at")
    return json_response({"ticket": _ticket_item(ticket), "messages": [_message_item(m) for m in messages]})


@require_POST
@_comms_required
def tickets_reply(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _ticket_visible_to_user(ticket, request):
        return json_response({"detail": "No autorizado."}, status=403)
    if ticket.estado == Ticket.Estado.CERRADO:
        return json_response({"detail": "La ficha esta cerrada."}, status=400)

    payload = _load_payload(request)
    if payload is None:
        return json_response({"detail": "JSON invalido."}, status=400)
    body = (payload.get("message") or "").strip()
    if not body:
        return json_response({"detail": "El mensaje es obligatorio."}, status=400)

    with transaction.atomic():
        attachment = request.FILES.get('attachment')
        msg = TicketMessage.objects.create(ticket=ticket, autor=request.user, contenido=body, adjunto=attachment, estado=TicketMessage.Estado.ENVIADO)
        _notify_ticket_message(ticket, request.user, body)

    return json_response({"detail": "Respuesta enviada.", "message": _message_item(msg)})


@require_POST
@_comms_required
def tickets_close(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _can_manage_ticket_status(request.user, ticket):
        return json_response({"detail": "No tienes permiso para cerrar esta ficha."}, status=403)
    if not _ticket_visible_to_user(ticket, request):
        return json_response({"detail": "No autorizado."}, status=403)
    ticket.estado = Ticket.Estado.CERRADO
    ticket.closed_at = timezone.now()
    ticket.save(update_fields=["estado", "closed_at", "updated_at"])
    return json_response({"detail": "Ficha cerrada.", "ticket": _ticket_item(ticket)})


@require_POST
@_comms_required
def tickets_reopen(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)
    if not _can_manage_ticket_status(request.user, ticket):
        return json_response({"detail": "No tienes permiso para reabrir esta ficha."}, status=403)
    if not _ticket_visible_to_user(ticket, request):
        return json_response({"detail": "No autorizado."}, status=403)
    ticket.estado = Ticket.Estado.ABIERTO
    ticket.closed_at = None
    ticket.save(update_fields=["estado", "closed_at", "updated_at"])
    return json_response({"detail": "Ficha reabierta.", "ticket": _ticket_item(ticket)})


@require_GET
@_comms_required
def admin_ticket_open_permission_status(request):
    if not _is_admin(request.user):
        return json_response({"detail": "Solo admin."}, status=403)
    branch = _admin_branch(request)
    if not branch:
        return json_response({"detail": "No se pudo determinar sucursal."}, status=400)
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
    return json_response({
        "branchId": branch.id,
        "branchName": branch.nombre,
        "branchDefaultEnabled": bool(branch.especialistas_pueden_abrir_fichas),
        "specialists": items,
        "branchAdmins": _branch_admin_items(request),
        "mainAdmins": _main_admin_items(),
        "summary": summary,
    })


@require_POST
@_comms_required
def admin_ticket_open_permission(request):
    if not _is_admin(request.user):
        return json_response({"detail": "Solo admin."}, status=403)
    payload = _load_payload(request)
    if payload is None or "enabled" not in payload:
        return json_response({"detail": "enabled es obligatorio."}, status=400)
    enabled = bool(payload["enabled"])
    branch = _admin_branch(request)
    if not branch:
        return json_response({"detail": "No se pudo determinar sucursal."}, status=400)

    admin_user_id = payload.get("adminUserId")
    if request.user.es_admin_principal and admin_user_id:
        admin_user = get_object_or_404(Usuario, pk=int(admin_user_id), rol__rol="ADMIN_SUCURSAL")
        admin_user.is_active = enabled
        admin_user.save(update_fields=["is_active", "updated_at"])
        return json_response({"detail": "Permiso actualizado.", "enabled": enabled, "adminUserId": admin_user.id})

    if request.user.es_admin_principal and payload.get("target") == "branch_admins":
        Usuario.objects.filter(rol__rol="ADMIN_SUCURSAL").update(is_active=enabled)
        return json_response({"detail": "Permisos actualizados para administradores de sucursal.", "enabled": enabled})

    specialist_id = payload.get("specialistId")
    admin_recipient_id = payload.get("adminRecipientId")
    if specialist_id:
        specialist = get_object_or_404(Especialista, pk=int(specialist_id), sucursal_base=branch)
        specialist.puede_abrir_fichas = enabled
        specialist.save(update_fields=["puede_abrir_fichas", "updated_at"])
        return json_response({"detail": "Permiso actualizado.", "enabled": enabled, "specialistId": specialist.id})

    branch.especialistas_pueden_abrir_fichas = enabled
    branch.save(update_fields=["especialistas_pueden_abrir_fichas", "updated_at"])
    Especialista.objects.filter(sucursal_base=branch).update(puede_abrir_fichas=enabled)
    return json_response({"detail": "Permisos actualizados para toda la sucursal.", "enabled": enabled, "branchId": branch.id})
