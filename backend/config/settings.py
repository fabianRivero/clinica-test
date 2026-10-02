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

# ---------------------------------------------------------------------------
# Seed baseline configuration (reform-database-seed-scripts, decisions D4/D5)
#
# BASE_URL is the deployment's public origin. It is used as the fallback for
# the admin URL footer emitted by ``seed_client_baseline`` when no explicit
# ``SEED_ADMIN_URL`` is configured. Never hard-code a domain here.
#
# SEED_ADMIN_URL, when set, overrides ``BASE_URL + "/admin"``. Leave empty in
# dev/test so the helper falls back to BASE_URL.
#
# ENVIRONMENT gates non-production seed commands (notably
# ``seed_pdf_baseline``). Defaults to ``development`` so unset deployments
# continue to allow the demo seed; set ``DJANGO_ENVIRONMENT=production`` to
# reject it pre-transaction.
# ---------------------------------------------------------------------------
BASE_URL = os.getenv("DJANGO_BASE_URL", "http://localhost:8000")
SEED_ADMIN_URL = os.getenv("DJANGO_SEED_ADMIN_URL", "")
ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "development")
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
    "backups.apps.BackupsConfig",
    "corsheaders",
    # Cloud-storage-migration (slice 2 of 4): audit trail backing the
    # ``/api/media/signed-url/`` endpoint. Append-only model +
    # fail-closed writer; see ``audit.services.write_audit_log``.
    "audit.apps.AuditConfig",
    # Phase 2 of dp4500-host-app-integration-phase2. Sibling app to
    # the legacy biometric/ app; hosts the HTTPClient + cascade signal
    # + Celery tasks. Deprecated separately (Phase 4 will deprecate
    # the legacy biometric/ app, not this one).
    "dp4500_integration.apps.Dp4500IntegrationConfig",
    # Cloud-storage-migration (slice 3 of 4): registers the project
    # package as an app so ``config/management/commands/`` (e.g.
    # ``backfill_media``) is auto-discovered.
    "config",
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

# ---------------------------------------------------------------------------
# Biometric suspension (change `suspend-fingerprint-integration`).
#
# Central, reversible flag that the biometric factory inspects BEFORE
# dynamic class loading. When ``True`` the factory returns a
# :class:`biometric.services.agent_client.SuspendedAgentClient` whose
# capture/match/release raise :class:`AgentUnavailableError` with code
# ``BIOMETRIC_SUSPENDED`` without importing ``httpx``, decrypting tokens,
# resolving URLs or opening sockets. Endpoint-level gates (added in
# PR #2 of the same change) short-circuit before any agent contact or
# database write while this flag is enabled.
#
# Default is ``False``; flip to ``True`` in ``backend/.env`` to suspend.
# ---------------------------------------------------------------------------
BIOMETRIC_SUSPENDED = env_bool("BIOMETRIC_SUSPENDED", False)

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
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")  # default to local dev

# ---------------------------------------------------------------------------
# Storage provider switching (cloud-storage-migration, slice 1 of 4).
#
# ``STORAGE_PROVIDER`` drives ``STORAGES["default"]["BACKEND"]``:
#   * "local" (default) — Django's FileSystemStorage (no S3 client).
#   * "s3" with ``MEDIA_LOCAL_FALLBACK_ENABLED`` true (default) — the
#     LazyLocalFallbackStorage wrapper that reads from MEDIA_ROOT on a
#     bucket miss during the 30-day cutover window.
#   * "s3" with ``MEDIA_LOCAL_FALLBACK_ENABLED`` false — the raw
#     Boto3Storage; used after the bucket is fully populated.
#
# The env vars below (AWS_*, MEDIA_LOCAL_FALLBACK_ENABLED) are read by
# ``config.storage_backends`` when the corresponding backend is wired.
# Other call sites in this codebase (``api.viewsets.payments`` et al.)
# also read ``STORAGE_PROVIDER`` directly — that behavior is preserved
# by leaving the variable as a plain ``os.getenv`` value here.
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = os.getenv("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "sa-east-1")
AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL", "") or None
MEDIA_LOCAL_FALLBACK_ENABLED = (
    os.getenv("MEDIA_LOCAL_FALLBACK_ENABLED", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)

if STORAGE_PROVIDER == "s3":
    if MEDIA_LOCAL_FALLBACK_ENABLED:
        _default_storage_backend = "config.storage_backends.LazyLocalFallbackStorage"
    else:
        _default_storage_backend = "config.storage_backends.Boto3Storage"
else:
    _default_storage_backend = "django.core.files.storage.FileSystemStorage"

STORAGES = {
    "default": {
        "BACKEND": _default_storage_backend,
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Database backups (admin-db-backups, PR #1)
#
# BACKUPS_DIR holds server-side dumps created by ``BackupService`` and the
# ``create_backup`` management command. Operators may override the path via
# the ``BACKUPS_DIR`` env var; on Linux the convention is
# ``/var/backups/clinica`` (see design §"Deployment Notes"). The directory is
# created at startup if missing so cron / systemd-timer invocations never see
# a missing path; failures on read-only filesystems are tolerated so the
# web app still boots (the service raises ``BackupServiceError`` instead).
#
# BACKUP_DAILY_KEEP / BACKUP_WEEKLY_KEEP mirror the retention rule from the
# spec: keep the last 7 daily + 4 weekly dumps, prune the rest. The dump
# command timeout caps a single pg_dump / sqlite3 .backup at 30 minutes.
# The rate-limit windows are operator-overridable so a deployment can relax
# them without a code change (see ``.env.example`` for the canonical names).
# ---------------------------------------------------------------------------
BACKUPS_DIR = Path(os.getenv("BACKUPS_DIR", str(BASE_DIR / "backups")))
BACKUP_DAILY_KEEP = int(os.getenv("BACKUP_DAILY_KEEP", "7"))
BACKUP_WEEKLY_KEEP = int(os.getenv("BACKUP_WEEKLY_KEEP", "4"))
BACKUP_DUMP_TIMEOUT = int(os.getenv("BACKUP_DUMP_TIMEOUT", "1800"))
BACKUP_LOCK_PATH = BACKUPS_DIR / ".lock"
# ---------------------------------------------------------------------------
# Backup rate-limit windows (seconds, per principal). Operator-overridable via
# the same env vars documented in ``.env.example``. Defaults match the spec
# table (trigger 1/60s, download 1/30s, delete 1/30s).
# ---------------------------------------------------------------------------
BACKUP_RATE_LIMIT_TRIGGER_SECONDS = int(
    os.getenv("BACKUP_RATE_LIMIT_TRIGGER_SECONDS", "60")
)
BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS = int(
    os.getenv("BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS", "30")
)
BACKUP_RATE_LIMIT_DELETE_SECONDS = int(
    os.getenv("BACKUP_RATE_LIMIT_DELETE_SECONDS", "30")
)
try:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only filesystems (e.g. ephemeral CI): service raises at runtime.
    pass

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
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", not DEBUG)

# ---------------------------------------------------------------------------
# Phase 2 of dp4500-host-app-integration-phase2: Celery + DP4500 settings.
# ---------------------------------------------------------------------------

# Filesystem broker by default (no broker service required for local dev).
# Set CELERY_BROKER_URL=redis://... in production.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "filesystem:///tmp/dp4500-celery")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")
# When True (default in tests), \`.delay()\` runs the task synchronously
# in-process. Set to False in production so the worker handles the
# cascade-revoke background task.
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)
CELERY_TASK_EAGER_PROPAGATES = True

# DP4500 service API connection settings (consumed by
# dp4500_integration.client.HTTPClient).
DP4500_BASE_URL = os.getenv("DP4500_BASE_URL", "http://localhost:8000")
DP4500_TIMEOUT_SECONDS = int(os.getenv("DP4500_TIMEOUT_SECONDS", "5"))
# Phase 2 supports only "env" (per-branch env var lookup). Phase 4 adds
# "vault".
DP4500_KEY_STORE_BACKEND = os.getenv("DP4500_KEY_STORE_BACKEND", "env")
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
