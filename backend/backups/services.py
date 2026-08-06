"""Backup service: dump + retention + lock + audit.

Single source of truth for creating and pruning database backups.
The HTTP layer (PR #2) and the ``create_backup`` management
command both call into ``BackupService``.
"""

from __future__ import annotations

import fcntl
import logging
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from .models import BackupAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class BackupServiceError(Exception):
    """Base class for any backup-service failure."""


class BackupAlreadyRunningError(BackupServiceError):
    """Another dump is already holds the directory lock."""


class BackupInvalidFilenameError(BackupServiceError):
    """A filename failed the allowlist / path-containment check."""


# ---------------------------------------------------------------------------
# Filename helpers
# ---------------------------------------------------------------------------


# Strict anchored regex. ``fullmatch`` rejects ``..``, absolute
# prefixes, shell metacharacters and stray whitespace (e.g. trailing
# ``\n`` from a mis-encoded HTTP header).
BACKUP_FILENAME_RE = re.compile(
    r"^clinica_\d{4}-\d{2}-\d{2}_\d{6}(\.weekly)?\.dump$"
)


def validate_filename(filename: str) -> bool:
    if not isinstance(filename, str) or not filename:
        return False
    return bool(BACKUP_FILENAME_RE.fullmatch(filename))


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


@contextmanager
def _with_dump_lock(backups_dir: Path):
    """Exclusive fcntl lock on ``BACKUPS_DIR/.backup.lock``.

    Used to wrap the dump/rename/audit/retention sequence so a manual
    trigger mid-cron is rejected with ``BackupAlreadyRunningError``
    instead of stomping on the in-flight dump.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    lock_path = backups_dir / ".backup.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise BackupAlreadyRunningError(
                "Ya hay un respaldo en curso."
            ) from exc
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


def _safe_path(backups_dir: Path, filename: str) -> Path:
    """Resolve *filename* under *backups_dir* and reject escapes.

    Two layers: regex allowlist, then ``Path.resolve()`` containment
    catches symlinks and any residual escape that slipped through.
    """
    if not validate_filename(filename):
        raise ValueError(f"Nombre de archivo invalido: {filename!r}")
    candidate = (backups_dir / filename).resolve()
    root = backups_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Ruta fuera de BACKUPS_DIR: {filename!r}") from exc
    return candidate


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def apply_retention(backups_dir: Path, keep_daily: int, keep_weekly: int) -> list[Path]:
    """Prune files outside the daily/weekly retention window.

    Files are classified by suffix (``.weekly.dump`` vs ``.dump``),
    sorted by ``st_mtime`` descending and trimmed to the configured
    counts. Each pruned file is reported via the returned list; the
    caller is responsible for the audit row.
    """
    if not backups_dir.exists():
        return []

    daily: list[Path] = []
    weekly: list[Path] = []
    for entry in backups_dir.glob("clinica_*.dump"):
        if entry.name.endswith(".weekly.dump"):
            weekly.append(entry)
        else:
            daily.append(entry)

    daily.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    weekly.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    pruned: list[Path] = []
    for old in daily[keep_daily:]:
        try:
            old.unlink()
            pruned.append(old)
        except FileNotFoundError:
            continue
    for old in weekly[keep_weekly:]:
        try:
            old.unlink()
            pruned.append(old)
        except FileNotFoundError:
            continue
    return pruned


# ---------------------------------------------------------------------------
# Engine branching
# ---------------------------------------------------------------------------


def _dump_to_path(target: Path, db_config: dict | None = None) -> None:
    """Run the engine-specific dump command, writing into *target*.

    Atomic on success: the dump is written to ``<target>.tmp`` and
    ``Path.replace()``d onto *target*. On any subprocess error the
    temp file is removed and the original ``CalledProcessError`` is
    re-raised.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    cfg = db_config if db_config is not None else settings.DATABASES["default"]
    engine = cfg["ENGINE"]

    tmp_path = target.with_suffix(target.suffix + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        if engine.endswith("postgresql"):
            env = {**os.environ, "PGPASSWORD": os.getenv("DJANGO_DB_PASSWORD", "")}
            cmd = [
                "pg_dump", "-Fc",
                "--no-owner", "--no-privileges",
                "-h", os.getenv("DJANGO_DB_HOST", "") or cfg.get("HOST", ""),
                "-p", os.getenv("DJANGO_DB_PORT", "") or str(cfg.get("PORT", "")),
                "-U", os.getenv("DJANGO_DB_USER", "") or cfg.get("USER", ""),
                "-d", os.getenv("DJANGO_DB_NAME", "") or cfg.get("NAME", ""),
                "-f", str(tmp_path),
            ]
            subprocess.run(cmd, env=env, check=True, timeout=settings.BACKUP_DUMP_TIMEOUT)
        elif engine.endswith("sqlite3"):
            db_path = cfg.get("NAME") or str(settings.BASE_DIR / "db.sqlite3")
            subprocess.run(
                ["sqlite3", str(db_path), f".backup '{tmp_path}'"],
                check=True,
                timeout=settings.BACKUP_DUMP_TIMEOUT,
            )
        else:
            raise BackupServiceError(f"Motor de base de datos no soportado: {engine}")
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    tmp_path.replace(target)


# ---------------------------------------------------------------------------
# Audit + IP helpers
# ---------------------------------------------------------------------------


def _client_ip(request) -> str | None:
    """Best-effort client IP extraction (honours X-Forwarded-For)."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR") or None


def log_backup_audit(
    *,
    action: str,
    filename: str = "",
    request=None,
    user=None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> BackupAuditLog | None:
    """Persist an audit row inside a single atomic transaction."""
    if ip_address is None:
        ip_address = _client_ip(request)
    try:
        with transaction.atomic():
            return BackupAuditLog.objects.create(
                user=user,
                action=action,
                filename=filename[:255],
                ip_address=ip_address,
                metadata=metadata or {},
            )
    except Exception:  # pragma: no cover - audit must never crash
        logger.exception("Failed to persist BackupAuditLog row")
        return None


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def rate_limit(scope: str, user_id: int, ttl_seconds: int) -> bool:
    """Return True if the action is allowed, False if it was just used."""
    key = f"backup_ratelimit:{scope}:{user_id}"
    if cache.get(key):
        return False
    cache.set(key, 1, ttl_seconds)
    return True


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


class BackupService:
    """Engine-aware dump, retention and audit facade."""

    def __init__(self, backups_dir: Path | None = None,
                 daily_keep: int | None = None,
                 weekly_keep: int | None = None) -> None:
        self.backups_dir = Path(backups_dir or settings.BACKUPS_DIR)
        self.daily_keep = int(daily_keep if daily_keep is not None else settings.BACKUP_KEEP_DAILY)
        self.weekly_keep = int(weekly_keep if weekly_keep is not None else settings.BACKUP_KEEP_WEEKLY)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    # -- public --------------------------------------------------------

    def create_backup(self, actor: str = "system:cron", *, request=None,
                      user=None, weekly: bool | None = None) -> Path:
        """Create a fresh dump, prune, audit and return the final path."""
        is_weekly = self._is_weekly_today() if weekly is None else bool(weekly)
        timestamp = datetime.now(timezone.utc)
        filename = self._build_filename(timestamp, weekly=is_weekly)
        target = (self.backups_dir / filename).resolve()
        metadata = {
            "actor": actor,
            "engine": settings.DATABASES["default"]["ENGINE"],
            "size_bytes": 0,
        }
        if user is not None:
            metadata["user_id"] = user.id

        with _with_dump_lock(self.backups_dir):
            self._check_disk_space()
            _dump_to_path(target)

            try:
                size = target.stat().st_size
            except OSError:
                size = 0
            metadata["size_bytes"] = size

            pruned = apply_retention(
                self.backups_dir, self.daily_keep, self.weekly_keep
            )
            for old in pruned:
                log_backup_audit(
                    action=BackupAuditLog.Action.RETENTION_PRUNE,
                    filename=old.name,
                    request=request,
                    user=user,
                    metadata={"actor": actor},
                )

            log_backup_audit(
                action=BackupAuditLog.Action.TRIGGER_DOWNLOAD,
                filename=filename,
                request=request,
                user=user,
                metadata=metadata,
            )
            return target

    def apply_retention(self) -> int:
        """Return how many files were pruned by this invocation."""
        pruned = apply_retention(self.backups_dir, self.daily_keep, self.weekly_keep)
        return len(pruned)

    def _safe_path(self, filename: str) -> Path:
        """Public wrapper around the module-level resolver."""
        return _safe_path(self.backups_dir, filename)

    # -- helpers -------------------------------------------------------

    @staticmethod
    def _build_filename(timestamp: datetime, *, weekly: bool) -> str:
        suffix = ".weekly.dump" if weekly else ".dump"
        return f"clinica_{timestamp.strftime('%Y-%m-%d_%H%M%S')}{suffix}"

    @staticmethod
    def _is_weekly_today() -> bool:
        """Sunday (weekday 6) is the weekly snapshot."""
        return datetime.now().weekday() == 6

    def _check_disk_space(self) -> None:
        try:
            usage = shutil.disk_usage(self.backups_dir)
        except OSError as exc:
            raise BackupServiceError(
                f"No se pudo inspeccionar el espacio en disco: {exc}"
            ) from exc
        last_size = self._last_dump_size()
        threshold = max(2 * last_size, 1024 ** 3) if last_size else 1024 ** 3
        if usage.free < threshold:
            raise BackupServiceError(
                "Espacio en disco insuficiente para generar un respaldo."
            )

    def _last_dump_size(self) -> int:
        existing = sorted(
            self.backups_dir.glob("clinica_*.dump"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not existing:
            return 0
        try:
            return existing[0].stat().st_size
        except OSError:
            return 0


__all__ = [
    "BACKUP_FILENAME_RE",
    "BackupAlreadyRunningError",
    "BackupInvalidFilenameError",
    "BackupService",
    "BackupServiceError",
    "apply_retention",
    "log_backup_audit",
    "rate_limit",
    "validate_filename",
]