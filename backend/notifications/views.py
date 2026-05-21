from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from notifications.models import Notification, NotificationReadAudit


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _serialize(item):
    return {
        "id": item.id,
        "type": item.type,
        "title": item.title,
        "message": item.message,
        "actionUrl": item.action_url,
        "payload": item.payload,
        "isRead": item.is_read,
        "createdAt": item.created_at.isoformat(),
    }


@require_GET
def my_notifications(request):
    if not request.user.is_authenticated:
        return _json({"detail": "Autenticacion requerida."}, status=401)
    items = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:100]
    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    latest = list(items[:3])
    return _json({"items": [_serialize(item) for item in items], "latest": [_serialize(item) for item in latest], "unreadCount": unread_count})


@require_POST
def mark_all_notifications_read(request):
    if not request.user.is_authenticated:
        return _json({"detail": "Autenticacion requerida."}, status=401)
    now = timezone.now()
    unread = Notification.objects.filter(recipient=request.user, is_read=False)
    ids = list(unread.values_list("id", flat=True))
    unread.update(is_read=True, read_at=now)
    NotificationReadAudit.objects.bulk_create([NotificationReadAudit(notification_id=pk, user=request.user) for pk in ids], ignore_conflicts=True)
    return _json({"detail": "Notificaciones marcadas como leidas."})
