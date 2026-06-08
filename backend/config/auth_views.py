import json
import logging

from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from config.api_helpers import json_response

logger = logging.getLogger(__name__)


def _dashboard_path(user):
    if user.is_superuser or user.es_administrador:
        return "/cms"
    if user.es_trabajador:
        return "/trabajador"
    if user.es_cliente:
        return "/cliente"
    return "/"


def _serialize_user(user):
    role_name = user.rol.rol if user.rol else ""
    # Ambos tipos de admin se exponen como ADMINISTRADOR al frontend
    frontend_role = "ADMINISTRADOR" if (user.is_superuser or user.es_administrador) else role_name
    return {
        "id": user.id,
        "username": user.username,
        "fullName": user.nombre_completo or user.username,
        "email": user.email,
        "role": frontend_role,
        "dashboardPath": _dashboard_path(user),
        "isAdmin": bool(user.is_superuser or user.es_administrador),
        "isMainAdmin": bool(user.is_superuser or user.es_admin_principal),
        "isWorker": bool(user.es_trabajador),
        "isClient": bool(user.es_cliente),
        "branchId": user.sucursal_id,
        "branchName": user.sucursal.nombre if user.sucursal else "",
    }


@ensure_csrf_cookie
@require_GET
def auth_csrf(request):
    return json_response({"detail": "CSRF cookie establecida.", "csrfToken": get_token(request)})


@require_GET
def auth_me(request):
    if not request.user.is_authenticated:
        return json_response({"detail": "No autenticado."}, status=401)
    return json_response({"user": _serialize_user(request.user)})


@require_POST
def auth_login(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return json_response({"detail": "El cuerpo de la solicitud no es JSON valido."}, status=400)

    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return json_response({"detail": "Usuario y contraseña son obligatorios."}, status=400)

    user = authenticate(request, username=username, password=password)
    if not user:
        return json_response({"detail": "Credenciales invalidas."}, status=401)
    if not user.is_active:
        return json_response({"detail": "La cuenta esta inactiva."}, status=403)

    try:
        django_login(request, user)
        return json_response({"user": _serialize_user(user)})
    except Exception:
        logger.exception("Fallo el login para el usuario '%s'.", username)
        return json_response({"detail": "Ocurrio un error interno al iniciar sesion."}, status=500)


@require_POST
def auth_logout(request):
    django_logout(request)
    return json_response({"detail": "Sesion cerrada correctamente."})
