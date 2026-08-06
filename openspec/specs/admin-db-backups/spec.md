# Admin Database Backups Specification

## Purpose

Define how `ADMIN_PRINCIPAL` creates, lists, downloads, and deletes database backups via the Spanish admin UI, and how operators schedule identical backups via a Django management command. All actions MUST be principal-gated, rate-limited, auditable, and retention-managed.

## Requirements

### Requirement: Backups navigation and access
The UI MUST expose "Respaldos de base de datos" under main-admin nav at `/cms/backups`; the route and every backup endpoint MUST require `ADMIN_PRINCIPAL` and SHALL NOT reveal backup existence to others.

#### Scenario: Principal opens Backups
- GIVEN an authenticated `ADMIN_PRINCIPAL`
- WHEN they select the Backups entry
- THEN the page renders the create action, the table, and Spanish loading/empty/success/error states.

#### Scenario: Non-principal denied
- GIVEN an `ADMIN_SUCURSAL`, `TRABAJADOR`, or `CLIENTE`
- WHEN they request `/cms/backups` or `/api/admin/backups/*`
- THEN access is denied (403) with no backup metadata.

#### Scenario: Anonymous denied
- GIVEN an unauthenticated request
- THEN the system returns 401 (JSON) or redirects to login (HTML) with no audit row.

### Requirement: On-demand backup trigger (UI stream)
The system MUST expose an authenticated trigger running the shared backup service and streaming the dump (`pg_dump`/`sqlite3 .backup`) via `Content-Disposition: attachment`; a rate limit of 1/60s per principal MUST be enforced via Django cache.

#### Scenario: Principal triggers a fresh dump
- GIVEN a principal with no trigger in the last 60s and a healthy engine
- WHEN they click "Crear respaldo"
- THEN a fresh dump streams as `clinica_<UTC>.dump` and an audit row records success.

#### Scenario: Rate limit exceeded
- GIVEN a principal who triggered fewer than 60s ago
- WHEN they trigger again
- THEN the request is rejected (429), no dump is produced, and an audit row records the denial.

#### Scenario: Missing tool
- GIVEN `pg_dump` is unavailable
- WHEN the principal triggers
- THEN an actionable Spanish error returns, no partial file remains, and an audit row records the failure.

### Requirement: Server-side management command
The system MUST provide `python manage.py create_backup` using the shared service; it MUST require no input, exit non-zero on failure for cron alerting, and audit as `actor="system:cron"`.

#### Scenario: Cron creates a daily dump
- GIVEN host cron invokes `create_backup`
- WHEN the cron entry runs
- THEN a new dump appears in `BACKUPS_DIR`, retention is applied, and an audit row records the creation.

#### Scenario: Command fails without binary
- GIVEN `pg_dump` is missing on PATH
- WHEN cron runs `create_backup`
- THEN the command exits non-zero, no partial file remains, and an audit row records the failure.

### Requirement: List server-side backups
The list endpoint MUST return per file: opaque ID, filename, size in bytes, UTC timestamp, and age ("hace 2 días"); IDs MUST be resolved server-side and client-supplied paths MUST be rejected.

#### Scenario: Principal lists backups
- GIVEN three files in `BACKUPS_DIR`
- WHEN the principal loads the page
- THEN the table shows three rows with name, size, timestamp, age, and Descargar/Eliminar actions.

#### Scenario: Empty directory
- GIVEN `BACKUPS_DIR` has no files
- WHEN the principal loads the page
- THEN a Spanish empty state renders and the create action stays enabled.

### Requirement: Download a backup file
The download endpoint MUST stream the file as an attachment with its real filename; it MUST reject IDs resolving outside `BACKUPS_DIR`, paths with `..`, absolute prefixes, or symlinks, and MUST enforce CSRF.

#### Scenario: Principal downloads a backup
- GIVEN an existing backup file
- WHEN the principal clicks "Descargar"
- THEN the file streams as an attachment with the original filename and matching `Content-Type`.

#### Scenario: Path traversal rejected
- GIVEN an ID resolving to `..`, absolute components, or a symlink outside `BACKUPS_DIR`
- WHEN the download is requested
- THEN the response is 404 with no filesystem disclosure, and an audit row records the rejection.

### Requirement: Delete a backup file
The delete endpoint MUST remove the file by opaque ID after UI confirmation, enforce 1 delete per 30s per principal, reject traversal/symlinks as in download, and MUST NOT expose files via `MEDIA_URL`.

#### Scenario: Principal deletes a backup
- GIVEN an existing backup file
- WHEN the principal confirms the deletion modal
- THEN the file is removed, the list refreshes, and an audit row records the deletion.

#### Scenario: Delete rate limit exceeded
- GIVEN a principal who deleted fewer than 30s ago
- WHEN they delete again
- THEN the request is rejected (429), the file is preserved, and an audit row records the denial.

### Requirement: Audit log of admin backup actions
The system MUST persist `BackupAuditLog(user, action, filename, timestamp, ip_address, metadata)` for every trigger, download, delete, retention pruning, and rate-limit denial; the table MUST be append-only at the API level and MUST NOT include dump contents.

#### Scenario: Successful trigger audited
- GIVEN a successful trigger
- WHEN it completes
- THEN an audit row exists with actor, action `trigger`, filename, timestamp, IP, and dump size.

#### Scenario: Denied download audited
- GIVEN a path-traversal attempt
- WHEN the endpoint rejects it
- THEN an audit row exists with action `download_denied`, the supplied ID, and the actor.

### Requirement: Retention policy
After every successful creation (UI or command), the system MUST apply 7 daily and 4 weekly retention (settings-configurable); files past the threshold MUST be pruned and each MUST produce an audit row.

#### Scenario: Daily file older than threshold pruned
- GIVEN 8 daily files exist and retention is 7
- WHEN a new backup succeeds
- THEN the oldest daily file is removed and an audit row records `retention_prune`.

#### Scenario: Weekly retained independently
- GIVEN 5 weekly files exist and retention is 4
- WHEN a new backup succeeds
- THEN the oldest weekly file is pruned while all daily files remain.

### Requirement: Role enforcement
The system MUST apply `_admin_principal_required` (or an equivalent principal-only guard) to every UI route, every `/api/admin/backups/*` endpoint, and any authenticated dispatch path; `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE`, and anonymous identities MUST receive 403/401 and MUST NOT trigger any side effect.

#### Scenario: Worker cannot list
- GIVEN an authenticated `TRABAJADOR`
- WHEN they call `GET /api/admin/backups/`
- THEN the response is 403 with no metadata and no audit row.

#### Scenario: Branch admin cannot trigger
- GIVEN an authenticated `ADMIN_SUCURSAL`
- WHEN they call the trigger endpoint
- THEN the response is 403 and no dump is produced.