from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from accounts.models import Usuario
from notifications.models import Notification


def create_notification(*, recipient, type, title, message, branch=None, action_url="", payload=None, created_by_type="system", created_by_id=None, source_event="", source_entity_type="", source_entity_id=None, metadata=None):
    return Notification.objects.create(
        recipient=recipient,
        branch=branch,
        type=type,
        title=title,
        message=message,
        action_url=action_url,
        payload=payload or {},
        created_by_type=created_by_type,
        created_by_id=created_by_id,
        source_event=source_event,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        metadata=metadata or {},
    )


def admins_for_specialist_branch(sucursal):
    return Usuario.objects.filter(Q(rol__rol="ADMIN_SUCURSAL") | Q(rol__rol="ADMIN_PRINCIPAL"), sucursal=sucursal, is_active=True)


def specialists_for_admin_branch(sucursal):
    return Usuario.objects.filter(rol__rol="TRABAJADOR", sucursal=sucursal, is_active=True)


def delete_old_notifications(days=180):
    cutoff = timezone.now() - timedelta(days=days)
    return Notification.objects.filter(created_at__lt=cutoff).delete()
