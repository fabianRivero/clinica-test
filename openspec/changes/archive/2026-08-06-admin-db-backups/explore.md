# Exploration: `admin-db-backups`

## Context

System administrators (only `ADMIN_PRINCIPAL`) need the ability to (1) trigger a database backup dump on demand from the admin UI, (2) have automatic scheduled backups written to the server machine, and (3) list/download/delete those server-side backups from the same admin UI. Out of scope for v1: restoring a database from a backup (too risky for v1). The project today ships no backup tooling, no cron jobs, and no scheduled tasks — only ad-hoc seed scripts under `scripts/` (`biometric_suspension.sh`, `deploy.sh.example`).

The codebase is Django 5.2 + DRF on the backend and React 19 + Vite + TypeScript on the frontend (`openspec/config.yaml:6-10`). Database is PostgreSQL in production (`backend/config/settings.py:150-162`) with env-driven connection params (`DJANGO_DB_NAME`, `DJANGO_DB_USER`, `DJANGO_DB_PASSWORD`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT`, `DJANGO_DB_SSLMODE`), with a SQLite fallback (`USE_LOCAL_DB`) for local-only work.

The most relevant existing feature to mirror is `admin-reports` (spec at `openspec/specs/admin-reports/spec.md`), which provides the canonical branch-scoped admin pattern: server-filtered read-only datasets, page header + table layout, loading/error/empty states, and downloads surfaced as XLSX through `ReportLayout`. The Reports feature does **not** cover arbitrary binary file downloads, so the backup feature will introduce that capability.

## Existing patterns the new feature must mirror

### Authentication and role enforcement

- **`@_admin_principal_required` decorator** — `backend/config/api_views.py:140-150`. Returns `401` when unauthenticated, `403` when the user is not `superuser` or `es_admin_principal`. Used everywhere a write operation is restricted to the main admin (lines 4474, 4502, 4634, 4915, etc.). This is the decorator the new backup endpoints MUST use.
- **`@admin_required` decorator** — `backend/config/api_helpers.py:47-68`. Looser version that allows any admin (principal or branch). Sufficient for read-only listing; the new feature SHOULD use `@_admin_principal_required` for list/delete/download as well because the spec scopes the feature to `ADMIN_PRINCIPAL` only.
- **`AdminPrincipalRequired` DRF permission class** — `backend/config/api/permissions.py:30-42`. Same gate, DRF-style. Useful if any endpoint switches to a `ViewSet`.
- **`Usuario.es_admin_principal` property** — `backend/accounts/models.py:63-65`. Source of truth for role checks (resolved through `tiene_rol("ADMIN_PRINCIPAL")` against the `Rol` table).
- **Branch isolation** — `get_user_branch()` in `backend/config/api_helpers.py:75-100`. Honors `X-Selected-Branch-Id` / `branchId` for main admins; falls back to their `sucursal`. The backup feature is global (one database, one filesystem), so branch context is NOT needed; endpoints can ignore `get_user_branch`.

### Frontend admin structure

- **`AdminLayout.tsx`** — `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx:9-98`. Defines `fullNavigation` with grouped children. Main-admin-only groups are tagged `mainAdminOnly: true` and filtered out for branch admins at line 148-149. The new feature's nav group MUST be `mainAdminOnly: true` because it is restricted to `ADMIN_PRINCIPAL`.
- **Reports nav group** — `AdminLayout.tsx:42-49` shows the precedent (`Clientes`, `Prospectos`, `Ingresos`, `Gastos` under `Reportes`).
- **Route registration** — `frontend/aesthetic-clinic/src/App.tsx:148-152` shows the `reportes` group routes nested under `/cms` inside the `<RequireRole allowedRoles={['ADMINISTRADOR']}>` guard. The new feature should follow the same nesting, optionally add a more restrictive `RequireRole` that checks `isMainAdmin`.
- **`ReportLayout` + `ReportTable` + page wrapper** — `frontend/aesthetic-clinic/src/pages/admin/reports/ReportLayout.tsx` provides loading/error/empty states, optional month/year period picker, and an XLSX export hook. Backup management can reuse the loading/error/empty primitives but does NOT need month/year pickers or XLSX export.
- **`PageHeader` + `SectionCard`** — used widely for admin pages, e.g. inside `ReportLayout.tsx:4-5`. Pages emit a `PageHeader` title plus a `SectionCard` body.

### URL routing

- **Backend root URL conf** — `backend/config/urls.py:11` mounts `/api/admin/` from `config.api_urls`.
- **Admin URL conf** — `backend/config/api_urls.py:130-133` registers `reportes/*` (clients, prospects, income). The new feature MUST register under the same `api_urls.py` to keep all admin endpoints in one tree, ideally grouped with a comment block like the existing `# Admin Reports — branch-scoped, read-only datasets (Phase 1 contract).` at line 130.
- **API client pattern** — `frontend/aesthetic-clinic/src/services/api/admin.ts:316-325` shows `getAdminReportIncome`/`getAdminReportProspects`/`getAdminReportClients` helpers. They use `requestJson<T>(url)`. Download endpoints will need a new helper (e.g. `downloadAdminBackup(backupId)`) that hits a `Blob` endpoint and triggers a browser save.

### Database configuration

- **`backend/config/settings.py:140-162`** — `USE_LOCAL_DB` toggles SQLite fallback; otherwise uses the PostgreSQL env vars above. This is critical: SQLite can be dumped by simply copying the file (`db.sqlite3`), but PostgreSQL requires `pg_dump` to be present on the server machine, and the credentials used by Django must be sufficient to dump the schema (typically `READ` on all tables, `SELECT` on system catalogs).
- **`MEDIA_ROOT = BASE_DIR / "media"`** at `settings.py:203` is the conventional writable directory used today for uploads. Backup dumps could reuse `MEDIA_ROOT` (e.g. `MEDIA_ROOT/backups/`) so the existing `staticfiles`+`MEDIA` setup is preserved. Note `MEDIA_URL = "/media/"` is only served when `DEBUG=True` (see `urls.py:20-21`), which means downloads in production MUST go through an authenticated endpoint, never via the static URL.

### Logging / audit precedent

- **`BranchAdminAuditLog`** — referenced in `backend/config/api_views.py:239-246` (`_log_branch_admin_audit`). Every admin-principal action that mutates branch state is recorded (actor, action, detail, metadata). The backup feature SHOULD emit analogous audit entries: `BACKUP_CREATE`, `BACKUP_DOWNLOAD`, `BACKUP_DELETE`, each recording actor, filename, byte size, and (for download/delete) the IP address.

### Test conventions

- Backend uses Django's built-in unittest (`python manage.py test` per `openspec/config.yaml:39`); pytest is NOT installed.
- Frontend uses Playwright for E2E (`npx playwright test`). The reports feature has `tests/e2e/admin_reports.spec.ts` covering happy-path + branch isolation + role enforcement; the backup feature should ship at least one Playwright spec for the principal-only gate.

## Approach options for the backup mechanism

### Option A — Django management command + external cron (RECOMMENDED)

Add a `python manage.py create_db_backup` command that runs `pg_dump` (or `sqlite3 .backup` when `USE_LOCAL_DB`) into a versioned filename like `backup_<UTC-timestamp>.sql[ite3]` inside a dedicated directory (e.g. `MEDIA_ROOT/backups/`). Schedule it via:

- **A1:** External host cron / systemd timer calling `python manage.py create_db_backup`. Operator manages schedule; no new infrastructure. Best fit for a single-VM deployment.
- **A2:** A small new view `POST /api/admin/backups/run/` that just shells out the same logic as the management command (used for the manual trigger). The scheduled job still uses the management command externally.

**Pros**
- Minimal new infrastructure; reuses Django's process management.
- The manual trigger endpoint and the scheduled job share the exact same code path → no drift.
- Backups land on the server's local filesystem where the operator already runs cron.
- The same code path works for both PostgreSQL (via `subprocess.run(["pg_dump", ...])`) and SQLite (via Python's `sqlite3.Connection.iterdump()` or a file copy).
- Easy to test: invoke the management command in a unittest with `call_command`.

**Cons**
- Requires `pg_dump` binary on the server (Debian/Ubuntu: `postgresql-client` package) and read-only DB credentials that include `SELECT` on all schemas; if the app uses a less-permissioned role this needs upgrading.
- Backup files live on a single machine — no off-site redundancy unless the operator ships them elsewhere.
- Concurrent runs can collide (two dumps writing to the same timestamp filename); needs a lock (e.g. `filelock` or `fcntl.flock`) or a UUID suffix.

**Effort:** Low–Medium.

### Option B — Internal scheduler driven by Django (Celery beat / APScheduler / django-q)

Spin up Celery + a beat schedule (or APScheduler in-process) that runs the dump every N hours; same management command as Option A as the task body. Manual trigger still POSTs to a view that enqueues the task synchronously or fires a job.

**Pros**
- No external cron configuration; schedule lives in code (env-driven interval).
- Same Python process can also send notifications, prune old dumps, etc.
- Plays nicely with horizontal scaling (multiple Django workers, one beat scheduler).

**Cons**
- Adds a hard infrastructure dependency: Redis/RabbitMQ broker + Celery worker process. The current deployment (single VM, env-driven DB, no broker) does NOT have this; introducing it is a sizable operational change.
- Beat misconfiguration (two beat processes) can trigger overlapping dumps.
- Adds two long-running processes that need monitoring and restart-on-failure.

**Effort:** Medium–High.

### Option C — External cron POSTs to an authenticated HTTP endpoint

A single `POST /api/admin/backups/run/` view is exposed; an external cron job POSTs to it with a long-lived service token (`X-Backup-Token` header) that the view validates before triggering the dump.

**Pros**
- Schedule is "wherever cron runs" — works on managed Kubernetes, serverless, etc.
- The dump itself runs inside the Django process, so it can reuse the already-loaded DB config and write under `MEDIA_ROOT`.
- Single code path (the view) for manual AND scheduled runs.

**Cons**
- Requires shipping a separate, dedicated secret (`DJANGO_BACKUP_TOKEN`) and being careful not to log it.
- An open HTTP endpoint is an attractive attack surface even with a token; needs rate limiting and IP allowlisting if reachable from the public internet.
- Couples the cron schedule to the application's network availability (cron needs network access to the app).

**Effort:** Low.

### Recommended: Option A2 (manual trigger view + external cron calling the management command)

This is the lowest-friction path that:
- Reuses existing Django primitives (`management.base.BaseCommand`).
- Gives admins a single button in the UI for on-demand dumps.
- Lets the operator schedule via the same OS-level cron they already use for other maintenance.
- Leaves room to migrate to Option B later without changing the dump code itself (just change the schedule).

## Security considerations

### Path traversal

Filenames MUST be server-generated from a timestamp + UUID prefix, never derived from user input. The list endpoint MUST return opaque IDs (UUIDs or DB row PKs) instead of filenames, and the download endpoint MUST look up the row by ID and use the stored filesystem path — never accept a `?filename=` query parameter. Symlinks inside the backups directory MUST be rejected (resolve with `Path.resolve()` and assert the parent is the configured backups root).

### Role enforcement

Every endpoint MUST be gated by `@_admin_principal_required` (`backend/config/api_views.py:140`). The UI route MUST be inside a guard that checks `user.isMainAdmin` (analogous to the `mainAdminOnly` filter in `AdminLayout.tsx:147-150`). A unit test that confirms a branch-admin session receives 403 on each endpoint is mandatory.

### Audit logging

Mirror `_log_branch_admin_audit` (`api_views.py:239-246`). Emit three event types:
- `BACKUP_CREATE` — actor, filename, byte size, trigger source (`manual` / `scheduled`).
- `BACKUP_DOWNLOAD` — actor, filename, byte size, client IP.
- `BACKUP_DELETE` — actor, filename, byte size.

Store in the same audit table (`BranchAdminAuditLog` or a sibling). Include trigger source so an external cron POST can be distinguished from a UI click if Option C is ever adopted.

### Rate limiting

- The manual trigger endpoint SHOULD be rate-limited to ~1 request per minute per actor to prevent admins from accidentally filling the disk. Django's `django.views.decorators.http` does not ship rate limiting — either add `django-ratelimit` (new dependency) or use the existing `cache` framework (already imported via `cache.get` / `cache.set` at `api_views.py:186-196`).
- Download endpoint SHOULD be rate-limited at ~10 requests per minute per actor.

### CSRF

All endpoints are session-authenticated (cookie-based via Django sessions), so the standard `@csrf_protect` flow applies. `@require_POST` endpoints with session auth MUST NOT be marked `@csrf_exempt`. The scheduled-token endpoint (Option C) MUST use a separate token check rather than session auth, and SHOULD be POST-only.

### Transport / encryption at rest

`pg_dump` produces plaintext SQL containing every patient record. Backups MUST live under a directory whose filesystem permissions are locked down to the Django service user (no world-read). If the operator wants encryption at rest, that is operational (full-disk encryption) and out of scope for the application. Document the storage path in the deployment guide.

### Disk-space safety

Before running `pg_dump`, check available disk space (`shutil.disk_usage`) and refuse if free space is below, say, 2x the most recent dump's size. Apply a retention policy (e.g. keep last N + last 14 days) and refuse to start a new dump if the post-retention free-space projection is below threshold.

### Concurrent dump safety

Wrap the dump with a `FileLock` (or `fcntl.flock`) so a manually triggered dump mid-schedule does not corrupt the file. Lock the directory, not the file.

## Out of scope for v1

Explicit non-goals so the proposal/spec stays bounded:

- **Restore from backup** — explicit user instruction. No UI, no endpoint, no DB-layer restore command.
- **Encryption of dump files** (GPG, age, etc.).
- **Off-site sync / replication** to S3, Supabase Storage, or any other remote. (Note: `STORAGE_PROVIDER` already supports Supabase/S3 for user uploads, but backup dumps are a different concern and not in scope.)
- **Per-branch dumps** — the system has one logical PostgreSQL database across all branches (`sucursal_registro` is just a column). A branch-scoped logical dump (filtering rows by `sucursal_registro`) is out of scope; v1 dumps the whole database.
- **PITR / WAL archiving** — full dumps only.
- **Compression** beyond what `pg_dump` provides natively (e.g. `-Fc` custom format). Custom-format `pg_dump` output is acceptable but reading it back requires `pg_restore` — only relevant if restore later becomes in scope.
- **Multi-tenant backup isolation** — single global namespace.
- **Email/SMS notifications on backup success or failure** — operator inspects logs / audit table.

## Open questions

1. **Deployment shape.** Is there an existing cron / systemd timer set up at the OS level on the target VM? If yes, A2 slots in trivially. If not, we either add cron configuration or pivot to Option B/C.
2. **Database role permissions.** What role does the app use to connect (`DJANGO_DB_USER`)? Does it have `SELECT` on every schema? For `pg_dump` we typically need either the schema owner role or a role with `pg_read_all_data` (PG14+). The proposal will need to call out a migration step.
3. **`pg_dump` availability on the server.** Is the `postgresql-client` package installed in the runtime image? If not, this is a deployment-image change (Dockerfile or Ansible).
4. **Audit table reuse.** Should backups reuse `BranchAdminAuditLog` (visible in the "Sucursales → Historial" page) or get a dedicated `BackupAuditLog` table? Dedicated table is cleaner because the existing one is branch-scoped.
5. **Retention policy defaults.** Operator preference for `keep_last_n` (e.g. 10) and `keep_last_days` (e.g. 14)? Needs to be env-driven, but default values should be chosen with the user.
6. **Max dump size threshold.** Should we refuse to expose dumps larger than, say, 1 GB to the UI? Or just stream them? Streaming with `FileResponse` + `as_attachment=True` (Django built-in) is the natural answer but adds memory pressure to the gunicorn worker.
7. **Local-dev support.** When `USE_LOCAL_DB=True` (SQLite), the management command should still work (file copy or `sqlite3 .backup`). Should the UI be hidden in `USE_LOCAL_DB` mode to avoid confusing devs? Or always shown because backups are useful even locally?
8. **Backups directory location.** `MEDIA_ROOT/backups/` is the natural choice and reuses existing patterns. Confirm there's no existing convention to override.
9. **Playwright coverage.** The team has Playwright E2E for reports — should backups get the same depth (load → list → trigger → wait → download → delete), or are unit tests of the management command + API enough?

## Verification of locked decisions

| Decision | Status | Evidence |
|---|---|---|
| `ADMIN_PRINCIPAL` is the only role allowed | ✓ Confirmed via task description | Task explicitly restricts to "system administrators (only `ADMIN_PRINCIPAL`)" |
| PostgreSQL in production, SQLite as local fallback | ✓ Verified | `backend/config/settings.py:140-162` |
| `@_admin_principal_required` is the right gate | ✓ Verified | `backend/config/api_views.py:140-150` — exactly matches the role check the user requested |
| `AdminLayout.tsx` has `mainAdminOnly` filter for nav | ✓ Verified | `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx:147-150` |
| Admin reports are branch-scoped read-only endpoints mounted under `/api/admin/reportes/*` | ✓ Verified | `backend/config/api_urls.py:130-133` |
| Frontend has `ReportLayout` for loading/error/empty states | ✓ Verified | `frontend/aesthetic-clinic/src/pages/admin/reports/ReportLayout.tsx` |
| Audit logging pattern exists for principal-only operations | ✓ Verified | `backend/config/api_views.py:239-246` (`_log_branch_admin_audit`) |
| No existing backup / `pg_dump` / cron code in repo | ✓ Verified | `grep -rn "pg_dump\|sqlite3.*backup\|cron" scripts/ backend/` returns no application-level hits |
| Celery / beat NOT configured | ✓ Verified | No `celery`, `@periodic_task`, or `CELERY_*` in `backend/config/settings.py` |

## Sensible defaults (proposed, for the proposal phase to confirm)

| Behaviour | Value | Source / rationale |
|---|---|---|
| Manual trigger rate limit | 1 req / 60 s per actor | Prevent accidental disk fill |
| Download rate limit | 10 req / 60 s per actor | Reasonable UX without abuse |
| Concurrent-run guard | `FileLock` on `MEDIA_ROOT/backups/.lock` | Single global lock |
| Backup filename | `backup_<UTC-ISO>_<short-uuid>.sql` | Sortable + unique |
| Audit table | New `BackupAuditLog` (not reusing `BranchAdminAuditLog`) | BranchAdminAuditLog is branch-scoped; backups are global |
| Storage directory | `MEDIA_ROOT/backups/` | Reuses existing media root convention |
| Retention default | Keep last 10 + last 14 days | Env-overridable |
| Min free disk before dump | 2x previous dump size | `shutil.disk_usage` |
| Postgres dump format | Custom (`-Fc`) — default; documented as future-restore-friendly | Standard `pg_dump` invocation |
| SQLite dump | `shutil.copy2(db.sqlite3, target)` + `.backup` semantics | Works when `USE_LOCAL_DB=True` |
| UI nav placement | "Respaldo de base de datos" under a new `Backups` group, `mainAdminOnly: true` | Mirrors Catalogs/AdminsSucursal precedent |
| UI routes | `/cms/backups` (list), `/cms/backups/crear` (no separate page; modal) | Single page with action buttons is simpler |
| Manual trigger UI | Button + confirm modal + status polling (3 s) until `running → ready/failed` | Matches other admin-action patterns |

## Affected areas (preliminary)

### Backend
- `backend/config/settings.py` — add `BACKUP_DIR`, `BACKUP_TOKEN` (if Option C), `BACKUP_KEEP_LAST_N`, `BACKUP_KEEP_LAST_DAYS` env-driven settings.
- `backend/config/api_views.py` — new block: `_admin_backups_list`, `_admin_backup_create_view`, `_admin_backup_download_view`, `_admin_backup_delete_view`; new audit helper `_log_backup_audit` and model `BackupAuditLog`.
- `backend/config/api_urls.py` — register `backups/` routes (mirroring `reportes/` placement).
- `backend/config/migrations/` — new `BackupAuditLog` migration.
- `backend/operations/management/commands/create_db_backup.py` — new management command (or a new `backups` app).

### Frontend
- `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx:9-98` — add `Backups` group with `mainAdminOnly: true`.
- `frontend/aesthetic-clinic/src/App.tsx:148-152` — add `backups` route nested under `/cms`.
- `frontend/aesthetic-clinic/src/pages/admin/backups/` — new directory: `AdminBackupsPage.tsx`, `BackupRow.tsx`, `useBackups.ts`.
- `frontend/aesthetic-clinic/src/services/api/admin.ts` — add `getAdminBackups`, `createAdminBackup`, `downloadAdminBackup`, `deleteAdminBackup` helpers.
- `frontend/aesthetic-clinic/src/types/admin.ts` — add `Backup` type.
- `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts` — new Playwright spec covering role gate + happy path.

### Infrastructure / docs
- `scripts/` — example crontab entry (`0 3 * * * python manage.py create_db_backup`).
- `docs/` — operator runbook: where backups live, retention, restore (out-of-app) instructions.

## Recommendation

**Yes — ready to propose.** The user description is specific enough to write a concrete proposal:

- One management command (`create_db_backup`) shared by manual and scheduled triggers.
- One view for manual trigger (rate-limited, audit-logged).
- One view each for list / download / delete (audit-logged).
- One Playwright spec + one Django unit test class.
- New `BackupAuditLog` model + migration.
- New `Backups` nav group (`mainAdminOnly: true`) with one page (list + actions).
- Open questions 1, 2, 3, 5, 7, 9 should be raised with the user before locking the proposal.
