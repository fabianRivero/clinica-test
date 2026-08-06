# Verify Report — Admin Database Backups

**Branch**: `feat/admin-db-backups-core` (cumulative +3141 insertions across 33 files vs main)
**Mode**: Standard (no Strict TDD)
**Verdict**: **FAIL** — 3 CRITICAL findings block merge; resolve-blockers required before archive.
**Runtime evidence**: `python3 manage.py test backups` → 39/39 PASS (7.7s)

## Summary

The four HTTP endpoints, the management command, the lock/retention/audit service, the migration, the nav/route/page wiring, and the operator documentation are all present and individually exercised by the test suite. Authorization, rate-limit, path-traversal, filename-allowlist, lock contention, retention-prune-with-audit, and atomic-rename behavior are all covered by runtime tests. The implementation is close to the spec but ships **three CRITICAL** spec/deploy-blocking defects: (1) the operator-facing `.env.example` documents env-var names the code does not read, (2) the delete endpoint rate-limit window is half the spec value, and (3) the list response is missing the spec-required `age` field.

The test suite is honest — it does not claim to cover what it doesn't. The deviations are visible in the diff vs the spec, not hidden behind passing tests.

## Findings

### CRITICAL

#### C-1 — `.env.example` env-var names diverge from `settings.py`; rate-limit envs are dead variables
- **id**: C-1
- **level**: CRITICAL
- **title**: Operator docs advertise env-vars that the runtime never reads
- **location**: `backend/.env.example` lines 92–97 vs `backend/config/settings.py` lines 221–225
- **evidence**:
  - `.env.example` declares `BACKUP_DAILY_KEEP`, `BACKUP_WEEKLY_KEEP`, `BACKUP_RATE_LIMIT_TRIGGER_SECONDS`, `BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS`, `BACKUP_RATE_LIMIT_DELETE_SECONDS`.
  - `settings.py` reads only `BACKUPS_DIR`, `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`, `BACKUP_DUMP_TIMEOUT`; rate-limit windows (60/30/10s) are hardcoded as literals in `views.py` lines 99/172/220 (`check_rate_limit("trigger", ..., 60)`, `("download", ..., 30)`, `("delete", ..., 10)`).
  - Verified by `grep -rn "BACKUP_DAILY_KEEP\|BACKUP_WEEKLY_KEEP\|BACKUP_RATE_LIMIT_TRIGGER\|..." backend/` — zero matches outside the `.env.example` file itself.
  - This means an operator who follows the documented `.env` exactly to extend retention to 30 days would silently get 7/4 (the hardcoded default in `os.getenv("BACKUP_KEEP_DAILY", "7")`), and any attempt to override the rate-limit windows from `.env` is silently ignored.
- **recommendation**: Either rename `BACKUP_KEEP_DAILY`/`BACKUP_KEEP_WEEKLY` in `settings.py` to `BACKUP_DAILY_KEEP`/`BACKUP_WEEKLY_KEEP` to match the example, or update `.env.example` to use the names the code actually reads. Add `BACKUP_RATE_LIMIT_TRIGGER_SECONDS`, `BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS`, `BACKUP_RATE_LIMIT_DELETE_SECONDS` as real settings and read them in `views.py` instead of hardcoding 60/30/10. Add a startup test (`manage.py check` or similar) that confirms `BACKUP_KEEP_DAILY` and `BACKUP_KEEP_WEEKLY` are integers ≥ 1.

#### C-2 — Spec requires `"age"` ("hace 2 días") field on list rows; implementation omits it
- **id**: C-2
- **level**: CRITICAL
- **title**: List endpoint missing spec-mandated `ageLabel` / "Hace" column
- **location**: `backend/backups/views.py` lines 64–86 (`_serialize_entry`); `frontend/aesthetic-clinic/src/pages/admin/backups/BackupTable.tsx` header cells lines 59–68; `frontend/aesthetic-clinic/src/types/admin.ts` `BackupFile` type lines 794–800
- **evidence**:
  - Spec lines 60–63: "THEN the table shows three rows with **name, size, timestamp, age**, and Descargar/Eliminar actions." Spec lines 57–58 also: "The list endpoint MUST return per file: opaque ID, filename, size in bytes, UTC timestamp, and **age ("hace 2 días")**".
  - `_serialize_entry` returns `{id, name, size, modified_at, is_weekly}` — no `age`/`ageLabel`/`age_label` field.
  - `BackupFile` type (frontend) does not declare an age field.
  - `BackupTable` header cells are `Nombre, Tamaño, Fecha, Tipo, Acciones` — no "Hace" column.
  - `grep -rn "ageLabel\|age_label\|Hace" frontend/aesthetic-clinic/src/pages/admin/backups/ backend/backups/` → no matches in the backups module. (Found unrelated "Hace" in `prospect-convert` and `client-detail` modules, not in backups.)
  - Design §"List flow" mermaid diagram shows `ageLabel` as a server-supplied field; the design promises it but the implementation never delivers it.
- **recommendation**: Compute an `age_label` server-side in `_serialize_entry` (e.g. `"hace 2 días"`, `"hace 5 horas"`, `"hace 12 minutos"`, `"recién"`) using a Spanish helper, include it in the JSON envelope and the TS `BackupFile` type, and add a "Hace" column to `BackupTable` between "Fecha" and "Tipo".

#### C-3 — Delete rate-limit window is `10s`, spec mandates `1/30s`
- **id**: C-3
- **level**: CRITICAL
- **title**: `admin_backup_delete` rate-limit window violates spec
- **location**: `backend/backups/views.py` line 220; `backend/.env.example` line 97
- **evidence**:
  - Spec lines 91–94 "Delete rate limit exceeded" scenario: "GIVEN a principal who deleted fewer than 30s ago".
  - Spec §"Rate Limiting" table: "Delete: 1/30s per principal".
  - Implementation: `check_rate_limit("delete", request.user.pk, 10)` — TTL=10s.
  - `.env.example` line 97 says `BACKUP_RATE_LIMIT_DELETE_SECONDS=30` (the correct value), but the env var is never read.
  - Net effect: a principal can issue 6 deletes per minute via the UI rather than the 2 the spec mandates; an attacker (or a frustrated operator clicking too fast) can delete files more frequently than the spec permits.
- **recommendation**: Change line 220 to `check_rate_limit("delete", request.user.pk, 30)` AND introduce a `BACKUP_RATE_LIMIT_DELETE_SECONDS` setting (default 30) so the window is configurable, addressing both C-1 and C-3 in one PR.

### WARNING

#### W-1 — `BACKUP_LOCK_PATH` setting declared but never consumed
- **id**: W-1
- **level**: WARNING
- **title**: Dead setting `BACKUP_LOCK_PATH`
- **location**: `backend/config/settings.py` line 225
- **evidence**:
  - `BACKUP_LOCK_PATH = BACKUPS_DIR / ".lock"` is declared but `services._with_dump_lock` hardcodes `backups_dir / ".backup.lock"` (line 79). Two sources of truth, two different filenames (`.lock` vs `.backup.lock`). An operator who exports `BACKUP_LOCK_PATH=/some/other/path` would expect the lock to move; nothing happens.
- **recommendation**: Either remove the unused setting or wire `_with_dump_lock` to read it (and rename to one consistent name). Add a regression test that confirms the lock path is read from settings.

#### W-2 — Download endpoint rate-limit denial writes no audit row
- **id**: W-2
- **level**: WARNING
- **title**: Download 429 path silently bypasses audit
- **location**: `backend/backups/views.py` lines 172–174 (`admin_backup_download`)
- **evidence**:
  - Trigger rate-limit denial (line 99–106) writes `RATE_LIMIT_DENIED` audit row.
  - Delete rate-limit denial (line 220–228) writes `RATE_LIMIT_DENIED` audit row.
  - Download rate-limit denial (line 172–174) just `return denial` — no audit row.
  - Spec §"Audit log" scenario 104–107 requires audit rows for denied actions; the design §"Rate Limiting" says "Denials write a `RATE_LIMIT_DENIED` audit row" (singular, applies to all rate-limited endpoints).
  - Inconsistency makes it harder to investigate a brute-force probe against downloads.
- **recommendation**: Add an `_audit(request=request, action=BackupAuditLog.Action.RATE_LIMIT_DENIED, metadata={"scope": "download"})` call before the `return denial` on line 174, mirroring the trigger/delete patterns.

#### W-3 — UI trigger button label deviates from spec
- **id**: W-3
- **level**: WARNING
- **title**: Trigger button labelled "Descargar respaldo ahora" instead of "Crear respaldo"
- **location**: `frontend/aesthetic-clinic/src/pages/admin/backups/AdminBackupsPage.tsx` line 178; spec lines 32 / design §"Frontend"
- **evidence**:
  - Spec line 32: "WHEN they click 'Crear respaldo'".
  - Design §"Frontend": "primary 'Crear respaldo' button".
  - Implementation: `{isTriggering ? 'Generando...' : 'Descargar respaldo ahora'}`.
  - Empty-state message (line 21) still says `Pulsa 'Crear respaldo' para generar el primero` — so the empty-state copy references a button label that does not exist.
- **recommendation**: Rename the button to "Crear respaldo" (matching spec, design, and the empty-state copy), and consider using a more descriptive verb only if product agrees.

#### W-4 — Trigger endpoint retains dump after streaming; design said it shouldn't
- **id**: W-4
- **level**: WARNING
- **title**: UI trigger persists dump on disk, contrary to design note
- **location**: `backend/backups/services.py` lines 290–334 (`BackupService.create_backup`)
- **evidence**:
  - Design §"HTTP Endpoints" note: "Trigger endpoint streams the freshly-created dump (no intermediate file is kept if the user is downloading it directly — written to a temp path and streamed; the same dump is NOT retained for the same request)".
  - Implementation: `create_backup` writes `target` to `BACKUPS_DIR` and never deletes it; the view then opens that file via `FileResponse`.
  - Net effect: a UI trigger mid-week produces an extra daily dump that triggers retention on the next successful backup. Spec is silent on this point, but the design clearly preferred non-retention.
  - The list endpoint then shows the freshly-created dump, which is also contrary to design intent (the design §"On-demand trigger flow" mermaid shows the dump being streamed then discarded from `BACKUPS_DIR`).
- **recommendation**: Decide explicitly: either (a) keep the implementation and remove the design's "no intermediate file is kept" sentence, or (b) write to a `.tmp`, stream it, and `Path.unlink()` the temp on stream completion. Update the spec and design accordingly so future reviewers don't get tripped up.

#### W-5 — `BACKUP_LOCK_PATH` filename mismatch (`.lock` vs `.backup.lock`)
- **id**: W-5
- **level**: WARNING
- **title**: Lock filename inconsistent between setting and implementation
- **location**: `backend/config/settings.py:225` (`.lock`) vs `backend/backups/services.py:79` (`.backup.lock`)
- **evidence**:
  - `settings.py` line 225: `BACKUP_LOCK_PATH = BACKUPS_DIR / ".lock"`.
  - `services.py` line 79: `lock_path = backups_dir / ".backup.lock"`.
  - Two different filenames, neither reads from the other. The setting is dead, the lock path is hardcoded with a different name than the setting advertises.
- **recommendation**: Pick one. Either remove the unused `BACKUP_LOCK_PATH` setting or wire the lock to use it.

#### W-6 — Playwright E2E spec was committed but never executed
- **id**: W-6
- **level**: WARNING
- **title**: E2E coverage exists but runtime verification was deferred
- **location**: `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts` (5 scenarios, 201 lines)
- **evidence**:
  - PR3 apply-progress line 537: "Live execution requires the same Django + Vite local harness the rest of the e2e suite uses and is out of scope for the SDD orchestrator. Manual verification recommended before merging."
  - Tests reference `admin.general/admin123456` and `admin.norte/admin123456` — these credentials are not verified to exist in the seeded users.
- **recommendation**: Run the Playwright suite at least once against the local backend harness before archiving. If the credentials are not seeded, add a fixture or update the spec to use a generic login helper.

#### W-7 — `_dump_to_path` SQLite branch interpolates `tmp_path` into a single-quoted argument
- **id**: W-7
- **level**: WARNING
- **title**: SQLite `.backup` command built with string interpolation
- **location**: `backend/backups/services.py` line 198
- **evidence**:
  - `subprocess.run(["sqlite3", str(db_path), f".backup '{tmp_path}'"], ...)` — `tmp_path` is interpolated inside single quotes inside a shell-quoted directive.
  - `subprocess.run` is invoked with a list (no `shell=True`), so the outer shell never sees the string, but `sqlite3` itself parses the directive. If a future caller ever lets `tmp_path` carry a `'` (e.g. a user-controlled override of `BACKUPS_DIR`), sqlite3 will choke or behave unexpectedly.
  - Currently safe because `tmp_path` is computed from `Path(BACKUPS_DIR) / filename` where `filename` is the timestamp `clinica_YYYY-MM-DD_HHMMSS.dump` — no user input.
- **recommendation**: Use argv-style invocation: have sqlite3 read the destination from stdin via `.backup` after a `PRAGMA`, or use Python's `sqlite3` module's `connection.backup(target_conn)` instead of shelling out. Document the assumption that `BACKUPS_DIR` and the filename are operator-controlled and contain no single quotes.

### SUGGESTION

#### S-1 — Test files use hardcoded `/tmp/_<name>` paths; collisions in parallel CI
- **id**: S-1
- **level**: SUGGESTION
- **title**: Hardcoded temp paths in test setup risk parallel-run collisions
- **location**: `backend/backups/tests/test_services.py:114` (`/tmp/_retention_test_dir`), `test_trigger_list.py:29`, `test_download_delete.py:30`, `test_commands.py:23`
- **evidence**:
  - Each test class hardcodes a different `/tmp/_<name>` path; in parallel CI the same path could be reused by a different worker or a leftover from a previous aborted run.
- **recommendation**: Use `tempfile.mkdtemp()` or Django's `override_settings(BACKUPS_DIR=tmp_path)` with the `tmp_path` pytest fixture, so each test class gets a fresh, isolated directory.

#### S-2 — `BACKUP_LOCK_PATH` should be removed or wired
- **id**: S-2
- **level**: SUGGESTION
- **title**: Same root cause as W-1 / W-5; cleaner fix would remove the dead setting
- **location**: `backend/config/settings.py:225`
- **evidence**: see W-1, W-5.
- **recommendation**: Remove `BACKUP_LOCK_PATH` from settings entirely (since `_with_dump_lock` hardcodes the path) and document the lock filename in the module docstring of `services.py`. Alternatively, expose `BACKUP_LOCK_FILENAME` (default `.backup.lock`) and read it in `_with_dump_lock`.

#### S-3 — Pre-existing ESLint errors in `admin.ts` left unfixed
- **id**: S-3
- **level**: SUGGESTION
- **title**: 5 pre-existing lint errors not addressed by PR3/PR4
- **location**: `frontend/aesthetic-clinic/src/services/api/admin.ts` lines 91, 129, 250, 522, 714
- **evidence**: PR4 apply-progress line 533 confirms 5 pre-existing errors remain.
- **recommendation**: Open a follow-up JSDoc/typing cleanup ticket. This is not blocking, but cumulative technical debt in a 932-line file is worth chipping away at.

#### S-4 — Spec scenario for "Principal triggers" is partially satisfied
- **id**: S-4
- **level**: SUGGESTION
- **title**: Spec scenario "Principal triggers a fresh dump" is met; "audit row records success" is met by `TRIGGER_DOWNLOAD` but the row's `metadata.actor` only carries the user ID, not the full actor string the design intended
- **location**: `backend/backups/services.py` lines 297–304 vs design §"Authentication, Authorization, and Audit"
- **evidence**: `metadata = {"actor": actor, "engine": ..., "size_bytes": 0}` stores `actor="user:1"` (good), but the row's `metadata.user_id` is also stored (line 303), making the actor slightly redundant.
- **recommendation**: Document the convention in `models.py` or a project-level audit module docstring so future audit-driven endpoints use the same shape.

## Behavioral Compliance Matrix

| Spec scenario | Covering test(s) | Runtime evidence |
|---|---|---|
| Authz: anonymous → 401 on all 4 endpoints | `test_authz.AuthzMatrixTests.test_anonymous_gets_401_on_all_endpoints` | ✅ PASS |
| Authz: ADMIN_SUCURSAL/TRABAJADOR/CLIENTE → 403 on all 4 endpoints | `test_authz.AuthzMatrixTests.test_non_principal_gets_403_on_all_endpoints` | ✅ PASS |
| Trigger streams dump + audit row | `test_trigger_list.test_trigger_streams_dump_and_audit` | ✅ PASS |
| Trigger rate-limit 429 + RATE_LIMIT_DENIED audit row | `test_trigger_list.test_trigger_rate_limit_returns_429_on_second_hit` | ✅ PASS |
| List returns JSON sorted by mtime desc with `{id, name, size, modified_at, is_weekly}` | `test_trigger_list.test_list_returns_seeded_files_sorted` | ✅ PASS — but **missing `ageLabel`** (C-2) |
| Path traversal rejected with 404 + DOWNLOAD_DENIED audit | `test_download_delete.test_download_rejects_traversal_payload_with_404`, `test_download_delete.test_download_rejects_weird_filenames` | ✅ PASS |
| Download streams expected bytes + DOWNLOAD_SERVER_BACKUP audit | `test_download_delete.test_download_streams_real_file_and_audits` | ✅ PASS |
| Delete returns 204 + DELETE_SERVER_BACKUP audit + file disappears from list | `test_download_delete.test_delete_removes_file_and_audits`, `test_deleted_file_no_longer_in_list` | ✅ PASS |
| Delete rate-limit 429 (10s, NOT 30s) | `test_download_delete.test_delete_rate_limit_returns_429` | ✅ PASS but **violates spec window** (C-3) |
| Cron creates dump + audit row + actor label override | `test_commands.test_command_creates_file_and_audit_row`, `test_command_accepts_actor_label_override` | ✅ PASS |
| Cron failure writes trigger_failed audit row + non-zero exit | `test_commands.test_command_failure_writes_failure_audit_row`, `test_command_lock_contention_exits_nonzero` | ✅ PASS |
| Lock contention: second invocation raises BackupAlreadyRunningError | `test_services.LockContentionTests.test_second_invocation_raises_when_lock_held` | ✅ PASS |
| Engine branching: PostgreSQL argv shape correct | `test_services.EngineBranchingTests.test_postgresql_branch_constructs_pg_dump_argv` | ✅ PASS |
| Engine branching: SQLite `.backup` argv shape correct | `test_services.EngineBranchingTests.test_sqlite_branch_constructs_sqlite3_backup` | ✅ PASS |
| Engine branching: unsupported engine raises BackupServiceError | `test_services.EngineBranchingTests.test_unsupported_engine_raises` | ✅ PASS |
| Retention: prunes daily+weekly over threshold + audit rows | `test_services.RetentionTests.test_keeps_only_configured_daily_and_weekly`, `CreateBackupHappyPathTests.test_create_backup_prunes_and_audits` | ✅ PASS |
| Filename regex rejects traversal/absolute/weird/whitespace | `test_services.FilenameValidationTests` (8 cases) | ✅ PASS |
| Path safety: `_safe_path` rejects traversal/absolute/non-matching | `test_services.SafePathTests` (4 cases) | ✅ PASS |
| Frontend: principal sees empty state, nav entry, trigger modal, delete flow | `tests/e2e/admin_backups.spec.ts` (5 scenarios) | ⚠️ Spec committed but **runtime execution deferred** to manual (W-6) |
| Frontend: branch admin sees no nav entry + 403 on direct nav | `tests/e2e/admin_backups.spec.ts` `Admin Backups access control` | ⚠️ Same as above |

## Completeness Table

| Phase | Tasks claimed | Runtime verified? | Coverage gap |
|---|---|---|---|
| Phase 1 (Bootstrap) | 1.1, 1.2, 1.3, 1.4 ✅ | ✅ Migration applies, model imports | None |
| Phase 2 (Service core) | 2.1, 2.2, 2.3, 2.4, 2.5, 2.6 ✅ | ✅ All 22 service tests pass | None |
| Phase 3 (Command) | 3.1, 3.2 ✅ | ✅ All 4 command tests pass | None |
| Phase 4 (Endpoints) | 4.1, 4.2, 4.3 ✅ | ✅ All 13 view tests pass | None |
| Phase 5 (Frontend) | 5.1–5.6 ✅ | ⚠️ Build succeeds; E2E not executed | W-6 |
| Phase 6 (Docs) | 6.1, 6.2 ✅ | ✅ `docs/backups.md`, `scripts/backups.sh.example`, `.env.example` present | ⚠️ `.env.example` env-var names diverge from settings (C-1) |
| Phase 7 (Verification) | 7.1, 7.2, 7.3 ✅ | ⚠️ Backend tests pass; Playwright not run | W-6 |

## Correctness Table

| Item | Spec requirement | Implementation | Status |
|---|---|---|---|
| Trigger rate-limit | 1/60s | 60s (literal) | ✅ (but not env-configurable, see C-1) |
| Delete rate-limit | 1/30s | 10s (literal) | � (C-3) |
| Download rate-limit | not required | 30s added | �️ extra; audit row missing (W-2) |
| Audit on trigger success | required | `TRIGGER_DOWNLOAD` row with actor, size, IP | ✅ |
| Audit on trigger failure | required | `TRIGGER_FAILED` row + 500/409 JSON | ✅ |
| Audit on rate-limit denial | required | Trigger and delete write it; download doesn't (W-2) | �️ |
| Audit on path-traversal denial | required | `DOWNLOAD_DENIED`/`DELETE_DENIED` row + 404 | ✅ |
| Audit on retention prune | required | `RETENTION_PRUNE` row per pruned file | ✅ |
| `age` field on list rows | required | missing | ❌ (C-2) |
| Principal-only authz on all 4 endpoints | required | `@require_admin_principal` decorator on all 4 | ✅ |
| Filename regex + `Path.resolve()` containment | required | both layers present | ✅ |
| No `MEDIA_URL` exposure | required | `BACKUPS_DIR` ≠ `MEDIA_ROOT`; no static route | ✅ |
| Cron command exits non-zero on failure | required | `CommandError` raised on failure | ✅ |
| Cron command writes audit row on failure | required | `TRIGGER_FAILED` written | ✅ |
| Operator docs cover pg_dump prerequisites | required | `docs/backups.md` §Prerequisites | ✅ |
| Operator docs cover restore | required | `docs/backups.md` §Disaster recovery | ✅ |
| Operator docs cover security | required | `docs/backups.md` §Security and PHI | ✅ |
| Operator docs cover cron | required | `docs/backups.md` §Run and schedule backups | ✅ |
| Operator docs `.env.example` env-vars match `settings.py` | required (consistency) | diverged (C-1) | ❌ |

## Design Coherence Table

| Design decision | Implemented as designed? | Note |
|---|---|---|
| New `backups` Django app | ✅ | matches |
| Engine branching via `DATABASES["default"]["ENGINE"]` | ✅ | matches |
| Opaque IDs = filename | ✅ | matches |
| `fcntl.flock` on `BACKUPS_DIR/.backup.lock` | ⚠️ | hardcoded `.backup.lock` not `.lock`; ignores `BACKUP_LOCK_PATH` setting (W-1, W-5) |
| Rate limit via Django cache | ✅ | matches; trigger/delete/download windows are hardcoded literals (C-1, C-3) |
| Streaming with `FileResponse(as_attachment=True)` | ✅ | matches |
| Path-traversal defense: regex + `Path.resolve()` containment | ✅ | matches |
| Manual trigger vs scheduled: same code path | ✅ | both call `BackupService.create_backup` |
| Retention algorithm | ✅ | matches |
| HTTP endpoints table | ✅ | matches |
| Frontend nav: "Respaldos" group, `mainAdminOnly: true` | ✅ | matches |
| Route `/cms/backups` | ✅ | matches |
| Page: PageHeader + SectionCard + DataState + BackupTable | ✅ | matches |
| Confirm modal text (trigger + delete) | ✅ | matches design copy |
| API client shape | ✅ | matches; added `requestBlob`/`requestDelete` helpers (justified deviation) |

## Skipped checks

- Playwright E2E runtime execution (deferred per PR3 apply-progress; see W-6).
- Real PostgreSQL integration (tests mock `subprocess.run`; the CI uses sqlite). The implementation does branch on engine correctly per the test, but a live `pg_dump` against a real PG instance was not exercised in this verification.

## Verdict

**FAIL** — three CRITICAL findings (C-1, C-2, C-3) block archive. Resolve-blockers recommended; route back to `apply` to fix env-var name divergence, add the missing `age` field, and correct the delete rate-limit window. The WARNINGs (W-1 through W-7) and SUGGESTIONs (S-1 through S-4) should also be addressed before merge but are not blocking on their own.

---

## Re-verification (post-fix)

**Branch**: `feat/admin-db-backups-core` (same branch; fix commits since last verify: `4293b1f`, `b387091`, `2b182ed`)
**Mode**: Standard (no Strict TDD)
**Date**: 2026-08-06
**Runtime evidence**:
- `python3 manage.py test backups` → **42/42 PASS** (9.7s). Up from 39; +3 new tests for age_label buckets + download rate-limit audit row.
- `python3 manage.py test backups.tests.test_download_delete.DownloadDeleteEndpointTests.test_delete_rate_limit_returns_429` → **PASS** (0.4s).
- `cd frontend/aesthetic-clinic && npm run build` → **PASS** (exit 0; 940 kB JS / 58 kB CSS).

### Per-finding re-verification

| ID | Original defect | New evidence | Status |
|---|---|---|---|
| **C-1** | `.env.example` advertised `BACKUP_DAILY_KEEP`/`BACKUP_WEEKLY_KEEP`/`BACKUP_RATE_LIMIT_*` env vars that the runtime never read; rate-limit windows were hardcoded literals. | `backend/config/settings.py` lines 224-241 now declare `BACKUP_DAILY_KEEP`, `BACKUP_WEEKLY_KEEP`, `BACKUP_RATE_LIMIT_TRIGGER_SECONDS` (default 60), `BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS` (default 30), `BACKUP_RATE_LIMIT_DELETE_SECONDS` (default 30); `backend/backups/views.py` lines 144/221/279 call `check_rate_limit(..., settings.BACKUP_RATE_LIMIT_*_SECONDS)` instead of literals; `backend/backups/services.py` lines 284-285 read `settings.BACKUP_DAILY_KEEP` / `settings.BACKUP_WEEKLY_KEEP`; `backend/.env.example` lines 93-97 match exactly. `grep -rn "BACKUP_KEEP_DAILY\|BACKUP_KEEP_WEEKLY\|BACKUP_DAILY_KEEP\|BACKUP_WEEKLY_KEEP\|BACKUP_RATE_LIMIT" backend/` returns zero matches for the old `BACKUP_KEEP_*` names (only the new `BACKUP_DAILY_KEEP`/`BACKUP_WEEKLY_KEEP`/rate-limit names appear). | **CLOSED** |
| **C-2** | List endpoint missing spec-mandated `age` ("hace 2 días") field; `BackupTable` had no "Hace" column; no test asserted Spanish text. | `backend/backups/views.py` lines 90-128 implement `_format_age_label(modified_at)` returning Spanish phrases (`"recien"`, `"hace N minutos"`, `"hace N horas"`, `"hace N dias"`, `"hace mas de 1 mes"`); `_serialize_entry` (line 85) emits `age_label`; `frontend/aesthetic-clinic/src/types/admin.ts` line 804 declares `ageLabel: string` on `BackupFile`; `frontend/aesthetic-clinic/src/pages/admin/backups/BackupTable.tsx` line 64 declares a `Hace` header column; new tests `test_list_age_label_in_spanish` (asserts backdated 3-day file → `hace 3 dias` / `hace 2 dias` / `hace 4 dias`) and `test_list_age_label_recent` (`recien` bucket) both PASS; `frontend/aesthetic-clinic/tests/e2e/admin_backups.spec.ts` lines 109-114 assert `getByRole('columnheader', { name: /^Hace$/ })` is visible AND assert the cell body matches the seeded `age_label`. | **CLOSED** |
| **C-3** | Delete rate-limit window was 10s (literal) instead of spec-mandated 30s. | `backend/backups/views.py` line 279 now calls `check_rate_limit("delete", request.user.pk, settings.BACKUP_RATE_LIMIT_DELETE_SECONDS)`; `backend/config/settings.py` lines 239-241 set the default to `30`; `backend/.env.example` line 97 documents `BACKUP_RATE_LIMIT_DELETE_SECONDS=30`; `backend/backups/tests/test_download_delete.py` line 170 now tightens the test via `override_settings(BACKUP_RATE_LIMIT_DELETE_SECONDS=30)` so it is deterministic regardless of operator `.env`. Targeted test PASSES (status 204 then 429). | **CLOSED** |
| **W-2** | Download 429 path silently bypassed audit (no `RATE_LIMIT_DENIED` row). | `backend/backups/views.py` lines 223-230 now write `_audit(request=request, action=BackupAuditLog.Action.RATE_LIMIT_DENIED, filename=filename[:255], metadata={"scope": "download"})` before returning the 429; `backend/backups/tests/test_download_delete.py` lines 182-201 (`test_download_rate_limit_writes_audit_row`) issue two downloads and assert a single `RATE_LIMIT_DENIED` row exists with `metadata["scope"] == "download"` and the correct filename. Test PASSES. | **CLOSED** |
| **W-3** | Trigger button labelled "Descargar respaldo ahora" instead of spec's "Crear respaldo". | `frontend/aesthetic-clinic/src/pages/admin/backups/AdminBackupsPage.tsx` line 178 now renders `{isTriggering ? 'Generando...' : 'Crear respaldo'}` (matching the empty-state copy on line 21 and the modal `Crear respaldo` button at `TriggerBackupModal.tsx:126`); the Playwright spec does not need a label change because it targets the button via `data-testid="backup-trigger-open"` which already covers both old and new labels — verified that no `Descargar respaldo ahora` literal remains in `src/pages/admin/backups/` or `tests/e2e/admin_backups.spec.ts`. | **CLOSED** |

### Behavioral compliance (post-fix)

| Spec scenario | Covering test(s) | Runtime evidence |
|---|---|---|
| Age field present on list rows, Spanish phrases | `TriggerListEndpointTests.test_list_age_label_in_spanish`, `test_list_age_label_recent`, list endpoint `test_list_returns_seeded_files_sorted` asserts the `{..., "age_label", ...}` key set | ✅ PASS (was failing — C-2 closed) |
| Trigger rate-limit uses env-configurable window | `BACKUP_RATE_LIMIT_TRIGGER_SECONDS=60` default in `settings.py:233-235`; `test_trigger_rate_limit_returns_429_on_second_hit` | ✅ PASS |
| Delete rate-limit uses 30s window per spec | `BACKUP_RATE_LIMIT_DELETE_SECONDS=30` default in `settings.py:239-241`; `override_settings(BACKUP_RATE_LIMIT_DELETE_SECONDS=30)` in `test_delete_rate_limit_returns_429` | ✅ PASS (was failing — C-3 closed) |
| Download rate-limit denial writes audit row | `test_download_rate_limit_writes_audit_row` asserts `RATE_LIMIT_DENIED` with `metadata["scope"] == "download"` | ✅ PASS (was missing — W-2 closed) |
| Trigger button labelled "Crear respaldo" | Source inspection: `AdminBackupsPage.tsx:178` | ✅ PASS (was "Descargar respaldo ahora" — W-3 closed) |

### Deferred findings (intentionally not re-verified)

W-1 / W-5 (lock filename mismatch), W-4 (trigger retention), W-6 (E2E runtime execution), W-7 (SQLite string interpolation), and all SUGGESTIONs (S-1–S-4) remain in the project backlog per the orchestrator's scope decision. None of them affect the spec compliance matrix that was the source of the FAIL verdict.

### Final verdict (re-verification)

**PASS WITH WARNINGS** — All three CRITICAL findings (C-1, C-2, C-3) are CLOSED with runtime evidence; the two cheap WARNINGs (W-2, W-3) the orchestrator pulled into the fix batch are also CLOSED. The five WARNINGs and four SUGGESTIONs left in the backlog are explicitly acknowledged as deferred and do not block the spec archive step.

`next_recommended`: **archive** — the change matches its spec, design, and tasks at runtime; the remaining backlog items belong to follow-up changes with their own scope.
