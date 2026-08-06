# Proposal: Admin Database Backups

## Intent

Enable `ADMIN_PRINCIPAL` users to create full database dumps on demand and safely list, download, or delete server-side backups from the Spanish admin UI, while operators schedule the same backup logic externally to reduce operational risk and eliminate ad-hoc backup procedures.

## Scope

### In Scope
- Shared backup service and `create_db_backup` management command for PostgreSQL and local SQLite.
- Principal-only list, trigger, streamed download, and delete endpoints with audit and rate limits.
- Operator cron scheduling, configurable retention, and a backup-management admin page.

### Out of Scope
- Restore, off-site replication, application-managed scheduling, per-branch dumps, and application-level encryption.

## Capabilities

### New Capabilities
- `admin-db-backups`: Backup creation, retention, discovery, download, deletion, authorization, and audit behavior.

### Modified Capabilities
- None.

## Approach

Choose **Option A2**: a Django management command and manual-trigger view share one backup service; host cron invokes the command for scheduled backups. This fits the single-server deployment without adding scheduler infrastructure.

- **Option B — internal scheduler:** Rejected because Celery/APScheduler adds broker, worker, monitoring, and duplicate-scheduler risks. It is disproportionate to the current deployment.
- **Option C — cron over HTTP:** Rejected because a long-lived token and public trigger endpoint increase attack surface. It also couples backups to network and application availability.

## Decisions

| Topic | Decision |
|---|---|
| Directory | Operator-set `BACKUPS_DIR`; defaults to `/var/backups/clinica` on Linux |
| Rotation | Keep 7 daily and 4 weekly; settings-configurable |
| Formats | PostgreSQL `pg_dump -Fc`; SQLite `sqlite3 .backup` |
| Naming | `clinica_YYYY-MM-DD_HHMMSS.dump`; weekly uses `.weekly.dump` |
| Engine | Branch on PostgreSQL vs SQLite backend; SQLite is local-dev only |
| Audit | New `BackupAuditLog(user, action, filename, timestamp, ip_address)` |
| Limits | Trigger: 1/60s/admin; delete: 1/30s/admin via Django cache |
| UI | Reports-style layout, table, actions, modals; nav uses `mainAdminOnly` |

## User-facing Changes

At `/cms/backups`, principals see **“Respaldos de base de datos”**, **“Crear respaldo”**, a backups table, **“Descargar”** and **“Eliminar”** actions, confirmation modals, plus Spanish loading, empty, success, and failure states.

## Security & Audit

- Apply `_admin_principal_required` to every endpoint and a main-admin route guard.
- Return opaque IDs; reject user-supplied paths, traversal, and symlinks.
- Stream authenticated downloads; never expose files through `MEDIA_URL`.
- Enforce CSRF, cache limits, exclusive dump locking, restricted filesystem permissions, and disk-space checks.
- Audit trigger/download/delete with actor, filename, timestamp, IP, and relevant metadata.

## Rollback Plan

Remove UI/routes, command/service, settings, cron entry, and audit migration; retain existing dump files for operator-controlled disposal. No clinical data or schema is restored or mutated.

## Affected Areas

- `backend/config/{settings.py,api_urls.py,api_views.py}`
- `backend/operations/{models.py,migrations/,management/commands/create_db_backup.py}`
- `frontend/aesthetic-clinic/src/{App.tsx,layouts/AdminLayout.tsx,pages/admin/backups/,services/api/admin.ts,types/admin.ts}`
- `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts`, operator deployment documentation/scripts

## Open Questions for Spec/Design

- Define weekly classification timing/timezone and whether rotation runs after every successful dump.
- Define disk-space threshold, lock implementation, opaque backup identity/indexing, and partial-file cleanup.
- Confirm production `pg_dump` availability/version and database-role dump permissions.

## Risks

| Risk | Mitigation |
|---|---|
| Sensitive dumps exposed | Principal-only streaming, path validation, strict permissions |
| Disk exhaustion or overlap | Retention, space checks, atomic temp files, exclusive lock |
| Missing/incompatible tools | Deployment preflight and actionable command errors |

## Success Criteria

- [ ] Principals can create, list, download, and delete valid backups; other roles cannot.
- [ ] Cron and UI use identical dump/rotation logic, with auditable outcomes.
