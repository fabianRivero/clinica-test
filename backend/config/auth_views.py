import json

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST


def _json(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={"ensure_ascii": False})


def _dashboard_path(user):
    if user.is_superuser or user.es_administrador:
        return "/admin"
    if user.es_trabajador:
        return "/trabajador"
    if user.es_cliente:
        return "/cliente"
    return "/"


def _serialize_user(user):
    role_name = user.rol.rol if user.rol else ""
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.nombre_completo or user.username,
        "email": user.email,
        "role": role_name,
        "dashboardPath": _dashboard_path(user),
        "isAdmin": bool(user.is_superuser or user.es_administrador),
        "isWorker": bool(user.es_trabajador),
        "isClient": bool(user.es_cliente),
    }


@ensure_csrf_cookie
@require_GET
def auth_csrf(request):
    return _json({"detail": "CSRF cookie establecida."})


@require_GET
def auth_me(request):
    if not request.user.is_authenticated:
        return _json({"detail": "No autenticado."}, status=401)
    return _json({"user": _serialize_user(request.user)})


@require_POST
def auth_login(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return _json({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return _json({"detail": "Usuario y contraseña son obligatorios."}, status=400)

    user = authenticate(request, username=username, password=password)
    if not user:
        return _json({"detail": "Credenciales invalidas."}, status=401)
    if not user.is_active:
        return _json({"detail": "La cuenta esta inactiva."}, status=403)

    django_login(request, user)
    return _json({"user": _serialize_user(user)})


@require_POST
def auth_logout(request):
    django_logout(request)
    return _json({"detail": "Sesion cerrada correctamente."})
