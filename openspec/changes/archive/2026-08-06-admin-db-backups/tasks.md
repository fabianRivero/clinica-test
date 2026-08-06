# Tasks: Admin Database Backups

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~970 (added ~880, modified ~90) |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | PR 1 (Bootstrap + Service Core + Command) → PR 2 (HTTP Endpoints) → PR 3 (Frontend) → PR 4 (Docs + Final Verification) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (orchestrator must ask user before apply) |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | New `backups` app, service core, management command (no HTTP exposure) | PR 1 | Base branch: `main`. Includes `BackupAuditLog` model + migration, `services.py` with engine branching/lock/retention, `create_backup` command, and unit tests. Landing this lets operators wire cron without exposing UI. |
| 2 | HTTP endpoints + authz + rate limits + audit on view layer | PR 2 | Base branch: `main`. Adds views, urls, decorator wiring, path-traversal defense, integration tests. Depends on PR 1. |
| 3 | Frontend page (nav + route + page + table + modals + API client + types) | PR 3 | Base branch: `main`. Depends on PR 2 (needs endpoints to call). Includes Playwright spec. |
| 4 | Operator docs (`scripts/backup_cron.example`, `docs/backups.md`) + final verification (full backend test suite + Playwright) | PR 4 | Base branch: `main`. Depends on PR 3. |

> **Note for orchestrator**: because the change crosses backend + frontend + docs and includes a migration, a clean 4-PR stacked split is feasible (each unit compiles and tests independently against a feature branch that includes prior units). Feature Branch Chain is also viable if the team prefers a single integration branch before main.

---

## Phase 1: Bootstrap (new Django app + audit model)

- [x] **1.1 Create the `backups` Django app skeleton**
  - Files: `backend/backups/__init__.py`, `backend/backups/apps.py`, `backend/backups/models.py` (empty), `backend/backups/services.py` (empty), `backend/backups/views.py` (empty), `backend/backups/urls.py` (empty), `backend/backups/tests/__init__.py`
  - What to do: Run `python manage.py startapp backups` (or hand-author the files), strip generated scaffolding, and ensure the app is import-clean.
  - Verification: `python -c "import django; django.setup(); from backups.apps import BackupsConfig"` from `backend/`.
  - Estimated: ~25 lines added.

- [x] **1.2 Register `backups` in `INSTALLED_APPS`**
  - Files: `backend/config/settings.py` (modify the `INSTALLED_APPS` block).
  - What to do: Append `"backups.apps.BackupsConfig"` next to `"operations"` / `"notifications"`. Do NOT yet add `BACKUPS_DIR` settings — those live in Phase 2 with the service that consumes them.
  - Verification: `python manage.py check` succeeds.
  - Estimated: ~2 lines modified.

- [x] **1.3 Add `BackupAuditLog` model**
  - Files: `backend/backups/models.py` (modify).
  - What to do: Implement `BackupAuditLog(TimeStampedModel)` per design §"Authentication, Authorization, and Audit" with `Action` TextChoices (`trigger_download`, `download_server_backup`, `delete_server_backup`, `retention_prune`, `rate_limit_denied`), `user` FK (`SET_NULL`, nullable), `filename` (255), `ip_address` (GenericIPAddressField), `metadata` (JSONField default dict), `Meta.db_table = "backup_audit_logs"`, ordering `("-created_at",)`. Extend `Action` with `download_denied` and `delete_denied` for traversal failures (align with spec §"Audit log of admin backup actions").
  - Verification: `python manage.py makemigrations --dry-run backups` shows exactly one migration pending, no others.
  - Estimated: ~50 lines added.

- [x] **1.4 Generate and review the initial migration**
  - Files: `backend/backups/migrations/0001_backupauditlog.py` (create via makemigrations).
  - What to do: Run `python manage.py makemigrations backups`; inspect the generated file to confirm `db_table`, FK `on_delete=SET_NULL`, and JSONField default `dict` are correct; add a `Migration` header comment noting this is the audit-only initial migration (no DB-shaped backup records).
  - Verification: `python manage.py migrate --plan` shows `backup_audit_logs` will be created; `python manage.py sqlmigrate backups 0001` looks sane.
  - Estimated: ~40 lines added (mostly auto-generated).

---

## Phase 2: Backup service core

- [x] **2.1 Add backup-related settings**
  - Files: `backend/config/settings.py` (modify).
  - What to do: Add `BACKUPS_DIR = env("BACKUPS_DIR", default=str(BASE_DIR / "backups"))`, `BACKUP_KEEP_DAILY = int(env("BACKUP_KEEP_DAILY", default=7))`, `BACKUP_KEEP_WEEKLY = int(env("BACKUP_KEEP_WEEKLY", default=4))`, `BACKUP_DUMP_TIMEOUT = int(env("BACKUP_DUMP_TIMEOUT", default=1800))`, `BACKUP_LOCK_PATH = Path(BACKUPS_DIR) / ".lock"`. Create `BACKUPS_DIR` at startup if missing (`Path(BACKUPS_DIR).mkdir(parents=True, exist_ok=True)` guarded with try/except for read-only filesystems).
  - Verification: `python manage.py check`; `python -c "from django.conf import settings; print(settings.BACKUPS_DIR)"` prints the resolved path.
  - Estimated: ~12 lines added.

- [x] **2.2 Implement `services.py` engine branching and dump core**
  - Files: `backend/backups/services.py` (modify).
  - What to do: Implement `_dump_to_path(target: Path)`, `BackupBusy`, `BackupError`, and `BackupService.dump(actor: str) -> Path`. Branch on `settings.DATABASES["default"]["ENGINE"]` exactly per design §"Database Engine Branching — Exact Pattern". Use `subprocess.run(check=True, timeout=settings.BACKUP_DUMP_TIMEOUT)`, write to `.tmp` file first, atomic `Path.replace()` to the final name `clinica_<UTC>.dump`, delete `.tmp` on any failure. Inject `PGPASSWORD` via `env=`, never argv. `shutil.disk_usage` precheck refuses if `free < 2 * last_dump_size` (or `free < 1 GiB` if no prior dump).
  - Verification: `python -c "from backups.services import _dump_to_path, BackupService; print('ok')"` imports cleanly.
  - Estimated: ~120 lines added.

- [x] **2.3 Implement retention algorithm and audit helper**
  - Files: `backend/backups/services.py` (modify).
  - What to do: Implement `apply_retention(backups_dir, keep_daily, keep_weekly) -> list[Path]` per design §"Retention Algorithm" — split files into daily vs weekly by suffix `.weekly.dump`, sort by `st_mtime`, prune overflow, return pruned list. Implement `log_backup_audit(*, request=None, user=None, action, filename, ip_address=None, metadata=None)` that opens a `transaction.atomic()` and writes a `BackupAuditLog` row. Implement `_client_ip(request)` reading `X-Forwarded-For` first then `REMOTE_ADDR`. Each pruned file produces a `retention_prune` audit row.
  - Verification: `python manage.py shell -c "from backups.services import apply_retention, log_backup_audit; print('ok')"`.
  - Estimated: ~80 lines added.

- [x] **2.4 Implement concurrency lock with `fcntl.flock`**
  - Files: `backend/backups/services.py` (modify).
  - What to do: Add `_with_dump_lock(fn)` helper per design §"Concurrency Lock". Open `LOCK_PATH` with `O_CREAT | O_RDWR` + `0o600`, `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, propagate `BlockingIOError` as `BackupBusy`. Wrap the entire `dump → rename → audit → retention` sequence inside this lock in the public `BackupService.create_backup(actor, request=None)` method.
  - Verification: Unit test: while holding the lock, a second invocation raises `BackupBusy` (covered in 2.6).
  - Estimated: ~35 lines added.

- [x] **2.5 Implement rate-limit helper**
  - Files: `backend/backups/services.py` (modify).
  - What to do: Implement `rate_limit(scope: str, user_id: int, ttl_seconds: int) -> bool` per design §"Rate Limiting" using the existing Django cache. Return `True` if allowed, `False` if denied. On denial, write a `rate_limit_denied` audit row when `request` is provided.
  - Verification: `python manage.py shell` — call `rate_limit("test", 1, 1)` twice in a row, second returns False.
  - Estimated: ~25 lines added.

- [x] **2.6 Unit tests for the service (engine branching, retention, lock, rate limit)**
  - Files: `backend/backups/tests/test_services.py` (create).
  - What to do: Use `@override_settings(BACKUPS_DIR=tmp_path)` (the standard `tmp_path` fixture). Mock `subprocess.run` per engine branch — assert the right argv for `pg_dump -Fc --no-owner --no-privileges ...` and the right argv for `sqlite3 .backup`. Test retention: seed 8 dailies + 5 weeklies, assert pruning to 7 + 4 and that each prune produces an audit row. Test lock: in a thread, hold the lock, assert second call raises `BackupBusy`. Test rate limit: two calls within TTL → second False, audit row written.
  - Verification: `python manage.py test backups.tests.test_services -v 2` passes.
  - Estimated: ~180 lines added.

---

## Phase 3: Management command

- [x] **3.1 Implement `create_backup` management command**
  - Files: `backend/backups/management/__init__.py`, `backend/backups/management/commands/__init__.py`, `backend/backups/management/commands/create_backup.py` (create).
  - What to do: Implement `Command.handle()` that calls `BackupService.create_backup(actor="system:cron")`. On any `BackupError` / `CalledProcessError` / `OSError`, log to stderr, write a `trigger_failed` audit row (extend `Action.choices`), and `sys.exit(1)`. Support an optional `--actor-label` flag that defaults to `"system:cron"` for future flexibility. Do NOT accept any path arguments (cron is operator-controlled).
  - Verification: `python manage.py create_backup --help` lists the command; in CI with sqlite engine, `python manage.py create_backup` exits 0 and creates one file under `BACKUPS_DIR`.
  - Estimated: ~60 lines added.

- [x] **3.2 Tests for the management command**
  - Files: `backend/backups/tests/test_commands.py` (create).
  - What to do: Use `call_command("create_backup", "--actor-label", "system:test")` with overridden `BACKUPS_DIR`. Test happy path produces a file + audit row. Test missing binary: patch `subprocess.run` to raise `FileNotFoundError` and assert `SystemExit(1)` + failure audit row. Test `BackupBusy` exits with a non-zero code distinct from generic error (use `mock.patch` on the service).
  - Verification: `python manage.py test backups.tests.test_commands -v 2` passes.
  - Estimated: ~70 lines added.

---

## Phase 4: HTTP endpoints (views, urls, rate limit, traversal guard, audit)

- [ ] **4.1 Implement the four views**
  - Files: `backend/backups/views.py` (modify).
  - What to do: Implement `admin_backup_list` (GET, glob `BACKUPS_DIR` for `clinica_*.dump`, return JSON list of `{id, filename, sizeBytes, createdAt, ageLabel}` per design §"List flow"). Implement `admin_backup_trigger` (POST, rate-limit 1/60s, run `BackupService.create_backup`, return `FileResponse` streaming the freshly-created dump — do NOT retain it for the list if it was just streamed; spec note clarifies "trigger streams the dump, not retains it"). Implement `admin_backup_download` (GET, regex allowlist + `Path.resolve()` containment per design §"Path-Traversal Defense", stream with `FileResponse`). Implement `admin_backup_delete` (DELETE, regex allowlist + resolve containment, rate-limit 1/30s, `Path.unlink()`). All four views import and reuse the `@_admin_principal_required` decorator from `config.api_views` and return JSON for errors (Spanish strings: `"No encontrado."`, `"Límite de velocidad excedido."`, `"Acceso denegado."`).
  - Verification: `python -c "from backups.views import admin_backup_list, admin_backup_trigger, admin_backup_download, admin_backup_delete; print('ok')"`.
  - Estimated: ~220 lines added.

- [ ] **4.2 Wire URL conf and mount in `config/api_urls.py`**
  - Files: `backend/backups/urls.py` (create), `backend/config/api_urls.py` (modify).
  - What to do: Define `app_name = "backups"` and the four routes exactly per design §"HTTP Endpoints" table: `POST trigger/`, `GET ""` (list), `GET <str:filename>/download/`, `DELETE <str:filename>/`. In `api_urls.py`, add `path("admin/backups/", include("backups.urls"))` next to the existing `operations` / `notifications` includes. Keep consistent trailing-slash style with siblings.
  - Verification: `python manage.py show_urls | grep backups` lists the four routes.
  - Estimated: ~25 lines added, ~3 lines modified.

- [ ] **4.3 Integration tests for views (authz matrix, rate limits, traversal)**
  - Files: `backend/backups/tests/test_views.py` (create).
  - What to do: Use Django `Client` + `pytest`-style or `unittest.TestCase`. Cases: anonymous → 401 on trigger/list/download/delete; `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE` → 403 (no audit row for the 403 cases per spec); principal happy path for each endpoint. Trigger rate limit: two POSTs within 60s → second 429 + audit row. Delete rate limit: two DELETEs within 30s → second 429 + audit row. Path traversal: GET `/api/admin/backups/..%2Fetc%2Fpasswd/download/` → 404 + `download_denied` audit row. Symlink outside `BACKUPS_DIR` → 404. Missing file → 404. Successful download streams expected byte count. CSRF: trigger requires CSRF token (session-auth POST); missing → 403.
  - Verification: `python manage.py test backups.tests.test_views -v 2` passes.
  - Estimated: ~250 lines added.

---

## Phase 5: Frontend page (route, nav, page component, actions, modals)

- [ ] **5.1 Add `Backup` type and API client functions**
  - Files: `frontend/aesthetic-clinic/src/types/admin.ts` (modify), `frontend/aesthetic-clinic/src/services/api/admin.ts` (modify).
  - What to do: In `types/admin.ts`, export `interface Backup { id: string; filename: string; sizeBytes: number; createdAt: string; ageLabel: string }` and a `BackupListResponse = Backup[]`. In `services/api/admin.ts`, add `listAdminBackups(): Promise<Backup[]>` (GET `/api/admin/backups/`), `triggerAdminBackup(): Promise<Blob>` (POST `/api/admin/backups/trigger/` + session cookie, returns blob; caller triggers `saveAs`), `deleteAdminBackup(filename: string): Promise<void>` (DELETE `/api/admin/backups/${filename}/`). Use the existing `apiClient` instance. Add a `triggerAdminBackupDownloadLink(filename: string): string` that returns `/api/admin/backups/${filename}/download/` for plain `<a>` GETs.
  - Verification: `npx tsc --noEmit` passes.
  - Estimated: ~35 lines added.

- [ ] **5.2 Add "Respaldos" nav group**
  - Files: `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` (modify).
  - What to do: Add a new group after `Reportes` per design §"Frontend" with `label: 'Respaldos'`, `mainAdminOnly: true`, and `children: [{ to: '/cms/backups', label: 'Respaldos de base de datos' }]`. Mirror the structure of existing `mainAdminOnly` entries.
  - Verification: `npm run lint` and render smoke in dev: the entry is visible only for principal role fixtures.
  - Estimated: ~10 lines modified.

- [ ] **5.3 Add `/cms/backups` route**
  - Files: `frontend/aesthetic-clinic/src/App.tsx` (modify).
  - What to do: Inside the `/cms` subtree, add `<Route path="backups" element={<AdminBackupsPage />} />` between `reportes` and `catalogos`. Lazy-import the page (`React.lazy`) to avoid bloating the initial bundle, matching the pattern used by siblings.
  - Verification: `npx tsc --noEmit`; `npm run build` succeeds.
  - Estimated: ~5 lines modified.

- [ ] **5.4 Create `useBackups` hook**
  - Files: `frontend/aesthetic-clinic/src/pages/admin/backups/useBackups.ts` (create).
  - What to do: SWR- or `useQuery`-style hook (mirror whatever the rest of the admin pages use) returning `{ backups, isLoading, error, refresh }`. Expose `trigger()` and `remove(filename)` actions that call the API client and trigger `refresh()`. Use Spanish error messages: `"No se pudieron cargar los respaldos."`, `"No se pudo generar el respaldo."`.
  - Verification: `npx tsc --noEmit` passes.
  - Estimated: ~55 lines added.

- [ ] **5.5 Create `BackupTable.tsx`**
  - Files: `frontend/aesthetic-clinic/src/pages/admin/backups/BackupTable.tsx` (create).
  - What to do: Mirror `ReportTable.tsx` styling. Columns: `Nombre`, `Tamaño`, `Fecha (UTC)`, `Hace`, `Acciones`. Actions per row: `<a href={downloadLink(id)} download>Descargar</a>` and a button that opens the delete confirmation modal. Format size with `formatBytes`; format date with the existing `formatDate(utc)` helper; render `ageLabel` verbatim (server supplies Spanish).
  - Verification: `npx tsc --noEmit`; visual smoke in dev.
  - Estimated: ~75 lines added.

- [ ] **5.6 Create `AdminBackupsPage.tsx`**
  - Files: `frontend/aesthetic-clinic/src/pages/admin/backups/AdminBackupsPage.tsx` (create).
  - What to do: Compose `PageHeader` (eyebrow `Respaldos`, title `Respaldos de base de datos`, subtitle in Spanish describing retention and disk usage) + `SectionCard` with the primary `Crear respaldo` button + `DataState` (loading / error / empty) + `BackupTable`. Use the project's existing modal primitive for two confirm modals: trigger confirm (text per design §"Frontend" Confirm modal (trigger); buttons `Cancelar` / `Crear y descargar`) and delete confirm (text per design; dynamic filename + `Cancelar` / `Eliminar`). On trigger success, `saveAs(blob, <UTC>.dump)` using `file-saver` (or project equivalent) so the browser saves the file.
  - Verification: `npx tsc --noEmit`; `npm run build` succeeds.
  - Estimated: ~160 lines added.

---

## Phase 6: Operator documentation

- [x] **6.1 Create `scripts/backup_cron.example`**
  - Files: `scripts/backup_cron.example` (create).
  - What to do: Provide the cron line exactly per design §"Deployment Notes (Operator Runbook)" plus a comment header explaining variables to substitute (`/path/to/venv/bin/python`, `/app/backend/manage.py`, log path) and a one-line note on the systemd-timer alternative.
  - Verification: file is non-empty; no placeholders left ambiguous.
  - Estimated: ~15 lines added.

- [x] **6.2 Create `docs/backups.md` runbook**
  - Files: `docs/backups.md` (create).
  - What to do: Short operator-facing runbook covering: (1) install `postgresql-client` and verify `pg_dump --version` ≥ server major; (2) DB role permissions one-liner (`GRANT pg_read_all_data TO <role>`) and the alternative of using a dedicated read-only `backup_user`; (3) `BACKUPS_DIR` mount + ownership (`chmod 700`) — explicitly call out that the path must NOT be exposed via nginx or `MEDIA_URL`; (4) retention defaults (`BACKUP_KEEP_DAILY=7`, `BACKUP_KEEP_WEEKLY=4`) with `BACKUPS_DIR` env override; (5) cron install + systemd timer alternative; (6) troubleshooting: `pg_dump` missing → exit 1 + audit row + check `PATH`; lock contention → `BackupBusy` 409; (7) restore command (`pg_restore --clean --if-exists -d <db> <dump>`) marked OUT OF SCOPE for the application.
  - Verification: rendered preview reads cleanly; covers all design §"Deployment Notes" bullets.
  - Estimated: ~80 lines added.

---

## Phase 7: Verification

- [x] **7.1 Full backend test suite**
  - Files: none (verification task).
  - What to do: Run `python manage.py test backups -v 2` and the full suite `python manage.py test` to confirm no regressions. Confirm `python manage.py check --deploy` reports no new warnings related to the new app.
  - Verification: all tests pass; `manage.py check` clean.
  - Estimated: 0 lines (verification only).

- [x] **7.2 Playwright E2E spec for the trigger/list flow**
  - Files: `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts` (create).
  - What to do: Test scenarios from design §"Testing Strategy" — row "(E2E)": (a) principal sees nav entry and `/cms/backups` loads with empty state when `BACKUPS_DIR` is empty; (b) clicking `Crear respaldo` opens the trigger modal, confirms, and triggers a file download (intercept the response, assert `Content-Disposition: attachment`); (c) after a successful trigger, the table shows the new file with size and age; (d) clicking `Eliminar` opens the delete modal, confirms, file disappears; (e) branch admin (`ADMIN_SUCURSAL`) does NOT see the nav entry and gets 403 on direct navigation.
  - Verification: `npx playwright test admin_backups.spec.ts` passes against a local backend with `BACKUPS_DIR` pointed at a scratch directory.
  - Estimated: ~110 lines added.

- [x] **7.3 Lint and typecheck verification**
  - Files: none.
  - What to do: Run `npm run lint`, `npx tsc --noEmit`, and a backend `flake8` / `ruff` (whatever the repo enforces). Update `backend/requirements.txt` if the linter auto-import list demands it.
  - Verification: both linters exit 0.
  - Estimated: 0 lines (verification only).

---

## Implementation Order

The phases MUST run in numerical order because of hard dependencies:

1. **Phase 1 (Bootstrap)** → unblocks model registration and migration.
2. **Phase 2 (Service core)** → depends on Phase 1's model for audit rows; depends on Phase 1.4's migration for tests.
3. **Phase 3 (Command)** → depends on Phase 2's service.
4. **Phase 4 (Endpoints)** → depends on Phase 2's service and Phase 1's model.
5. **Phase 5 (Frontend)** → depends on Phase 4's live endpoints; can begin scaffolding in parallel with Phase 3 using TypeScript mocks against the agreed API shape.
6. **Phase 6 (Docs)** → can land any time after Phase 3 (operators need the command reference even without the UI).
7. **Phase 7 (Verification)** → strictly last; gates the PR.

## Files Touched (cumulative)

| File | Action | Phase |
|---|---|---|
| `backend/backups/{apps,models,services,views,urls}.py` | create | 1, 2, 4 |
| `backend/backups/migrations/0001_backupauditlog.py` | create | 1 |
| `backend/backups/management/commands/create_backup.py` | create | 3 |
| `backend/backups/tests/{test_services,test_views,test_commands}.py` | create | 2, 3, 4 |
| `backend/config/settings.py` | modify | 1, 2 |
| `backend/config/api_urls.py` | modify | 4 |
| `frontend/aesthetic-clinic/src/App.tsx` | modify | 5 |
| `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` | modify | 5 |
| `frontend/aesthetic-clinic/src/pages/admin/backups/*` | create | 5 |
| `frontend/aesthetic-clinic/src/services/api/admin.ts` | modify | 5 |
| `frontend/aesthetic-clinic/src/types/admin.ts` | modify | 5 |
| `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts` | create | 7 |
| `scripts/backup_cron.example` | create | 6 |
| `docs/backups.md` | create | 6 |
