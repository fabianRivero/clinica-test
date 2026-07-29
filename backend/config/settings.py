import os
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DB_ENGINE = os.getenv("DJANGO_DB_ENGINE", "django.db.backends.postgresql")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
)
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
if DEBUG:
    ALLOWED_HOSTS = sorted({*ALLOWED_HOSTS, "127.0.0.1", "localhost", "testserver"})

CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
)


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts.apps.AccountsConfig",
    "customers",
    "staff",
    "catalogs",
    "operations",
    "billing",
    "clinical",
    "notifications",
    "biometric.apps.BiometricConfig",
    "corsheaders",
]                      

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Biometric integration (DigitalPersona 4500, PR #1)
#
# Fail-fast is enforced in ``biometric.services.encryption`` at module
# import time: a missing or malformed ``BIOMETRIC_FERNET_KEY`` raises
# ``ImproperlyConfigured`` and the app refuses to start (spec
# requirement 1, "Missing key fails fast at startup").
# ---------------------------------------------------------------------------
BIOMETRIC_FERNET_KEY = os.getenv("BIOMETRIC_FERNET_KEY", "")
BIOMETRIC_MATCH_THRESHOLD = os.getenv("BIOMETRIC_MATCH_THRESHOLD", "0.85")
BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS = os.getenv(
    "BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS", "300"
)
AGENT_CLIENT_CLASS = os.getenv(
    "AGENT_CLIENT_CLASS",
    "biometric.services.agent_client.HttpAgentClient",
)

USE_LOCAL_DB = env_bool("DJANGO_USE_LOCAL_DB", False)

if USE_LOCAL_DB:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": DB_ENGINE,
            "NAME": os.getenv("DJANGO_DB_NAME", "postgres"),
            "USER": os.getenv("DJANGO_DB_USER", ""),
            "PASSWORD": os.getenv("DJANGO_DB_PASSWORD", ""),
            "HOST": os.getenv("DJANGO_DB_HOST", ""),
            "PORT": os.getenv("DJANGO_DB_PORT", ""),
            "OPTIONS": {
                "sslmode": os.getenv("DJANGO_DB_SSLMODE", "require"),
            } if DB_ENGINE == "django.db.backends.postgresql" else {},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "es-bo"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ---------------------------------------------------------------------------
# Storage configuration — choose provider via STORAGE_PROVIDER env var
# Values: "local" | "supabase" | "s3"
# Cloud uploads are handled directly in the view (boto3), not via STORAGES.
# ---------------------------------------------------------------------------
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")  # default to local dev

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.Usuario"

LOGIN_URL = "/admin/login/"

CORS_ALLOWED_ORIGINS = env_list(
    "DJANGO_CORS_ALLOWED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174",
)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = (
    *default_headers,
    "x-selected-branch-id",
)

# CSRF and Session Configuration for production
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_HTTPONLY = env_bool("DJANGO_CSRF_COOKIE_HTTPONLY", False)
CSRF_COOKIE_SAMESITE = os.getenv("DJANGO_CSRF_COOKIE_SAMESITE", "None" if not DEBUG else "Lax")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)
SESSION_COOKIE_SAMESITE = os.getenv("DJANGO_SESSION_COOKIE_SAMESITE", "None" if not DEBUG else "Lax")

# ---------------------------------------------------------------------------
# Logging configuration
#
# The biometric scrubber (``biometric.log_filters.BiometricLogScrubber``)
# is attached to every handler so any log line emitted from the
# ``biometric.*`` namespace has long base64-like blobs replaced with
# ``<biometric-template-redacted>`` before reaching the handler. This
# is the application-level mitigation for spec requirement 15,
# "Application logs scrubbed".
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "biometric_scrubber": {
            "()": "biometric.log_filters.BiometricLogScrubber",
        },
    },
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["biometric_scrubber"],
            "formatter": "default",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "biometric": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
