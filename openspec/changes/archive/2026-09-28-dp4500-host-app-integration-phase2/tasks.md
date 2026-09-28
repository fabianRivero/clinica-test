# Tasks: Host-app integration — Phase 2 (Clinic side)



**Change name**: `dp4500-host-app-integration-phase2`

**Artifact store**: openspec

**Delivery strategy**: `ask-on-risk`

**Predecessors**:
- `proposal.md` (locked)
- `design.md` (locked)
- `specs/{dp4500-service-client,wizard-biometric-enrollment,cita-biometric-verification,cascade-biometric-revoke}/spec.md` (locked)

> **Status (2026-09-27)**: All 92 tasks marked complete. Reconciled against
> `tasks-reconciled.md` after commit 0762a33. Phase 2A5 verify de cita con
> Ed25519 landed end-to-end. sdd-attempt settled with `state: complete`.
> See `apply-progress.md` for the apply phase summary.

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~700 (range 600–900). Split: ~200 (HTTPClient + models) + ~150 (signals + cascade) + ~350 (views + URLs + reconcile + tests). |
| 400-line budget risk | Medium — within range for a single PR, split commit-by-commit. |
| Chained PRs recommended | No — single PR acceptable since the foundation (HTTPClient) underpins everything. |
| Suggested commit split | Commit 1 (HTTPClient + data model migrations + pre_save signal) → Commit 2 (cascade signal + Celery task + PendingCascade) → Commit 3 (views + URLs + wizard template + reconcile command + integration tests). |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a (single PR) |

### Suggested Work Units

| Unit | Goal | Likely commit | Focused test command | Runtime harness | Rollback boundary |
|------|------|--------------|----------------------|------------------|-------------------|
| WU-1.1 | `HTTPClient` + exceptions + key_resolver(env) + test_client | Commit 1 | `pytest backend/apps/biometric/tests/test_client.py -q` | `httpx.MockTransport` | Set `DP4500_BASE_URL=""` to disable; no other view touched |
| WU-1.2 | `users.User.biometric_external_id` field + pre_save signal + migration | Commit 1 | `pytest backend/apps/users/tests/test_biometric_external_id.py -q` | User model + signal trigger | Revert migration; deletes the UUID column on rollback |
| WU-1.3 | `citas.CitaMedica` biometric fields + migration | Commit 1 | `pytest backend/apps/citas/tests/test_citamedica_biometric_fields.py -q` | CitaMedica model | Revert migration; no behavior change on existing rows |
| WU-1.4 | `Sucursal.dp4500_service_key_id` field + migration | Commit 1 | `pytest backend/apps/catalogs/tests/test_sucursal_dp4500_key.py -q` | Sucursal model | Revert migration; drops the column |
| WU-2.1 | `biometric.PendingCascade` + `BiometricEnrollmentRecord` models + initial migration | Commit 2 | `pytest backend/apps/biometric/tests/test_models.py -q` | `manage.py makemigrations biometric --check` | Drop the new tables; `apps/biometric/` becomes a no-op |
| WU-2.2 | Cascade signal (`post_delete` on User) + Celery task + retry + outcome table | Commit 2 | `pytest backend/apps/biometric/tests/test_cascade.py -q` | Celery eager mode + `httpx.MockTransport` returning 204 / 404 / 503 | Disable `signals.py` connect; local deletes keep working without cascade |
| WU-2.3 | `reconcile_pending_cascades` management command | Commit 2 | `pytest backend/tests/integration/biometric/test_reconcile_cmd.py -q` | management command runner | Drop the command; the Celery path still works |
| WU-3.1 | `ConversionStepBiometricView` (wizard step 4 stub) + `capture_pending.html` template | Commit 3 | `pytest backend/apps/biometric/tests/test_views_wizard.py -q` | DRF test client + Jinja template render | Revert the view; existing wizard step 4 keeps its prior placeholder |
| WU-3.2 | `CitaBiometricVerifyView` + URL routing + atomic field write + concurrency | Commit 3 | `pytest backend/apps/biometric/tests/test_views_cita.py -q` | DRF test client + `httpx.MockTransport` for DP4500 | Revert the URL include; existing `confirm_manual` keeps working |
| WU-3.3 | End-to-end smoke: enroll + verify cascade across the wire | Commit 3 | `pytest backend/tests/integration/biometric/test_smoke_e2e.py -q` | `httpx.MockTransport` impersonating DP4500 | Disable the test if real DP4500 needed |

---

## Phase 1: Foundation (Commit 1)

### 1.1 `HTTPClient` + exceptions + key_resolver

- [x] 1.1.1 RED `backend/apps/biometric/tests/test_client.py::test_identity_challenge_returns_parsed_on_201`. Configure `httpx.MockTransport` to return 201 with `{"capture_token": "...", "server_nonce": "...", ...}`; assert `IdentityChallenge` dataclass with the same fields. Use a fake `key_resolver` returning `"SeK_test"`. [bd58a30]
- [x] 1.1.2 RED `test_client.py::test_identity_challenge_raises_BiometricEnrollConflict_on_409_enrollment_required`. Mock returns 409 with `{"code": "enrollment_required", "detail": "..."}`; assert `BiometricEnrollConflict` is raised with `str(exc)` containing `"no_template_on_dp4500"`. [bd58a30]
- [x] 1.1.3 GREEN — `backend/apps/biometric/exceptions.py`: define `BiometricError`, `BiometricUnavailable`, `BiometricSuspended`, `BiometricMismatch`, `BiometricVerifyFailed`, `BiometricEnrollConflict`. [bd58a30]
- [x] 1.1.4 GREEN — `backend/apps/biometric/client.py`: implement `HTTPClient.__init__`, `_request` (private helper that adds the bearer header and timeout), `identity_challenge`, `identity_verify`, `delete_template`. Plus the result dataclasses (`IdentityChallenge`, `IdentityVerifyMatch`, `IdentityVerifyNoMatch`). [bd58a30]
- [x] 1.1.5 GREEN — `backend/apps/biometric/key_resolver.py`: implement `env_key_resolver(sucursal_id) -> str | None` reading `DP4500_SERVICE_KEY_SUCURSAL_<id>` from `os.environ`. Returns `None` on miss; never raises. [bd58a30]
- [x] 1.1.6 RED `test_client.py::test_key_resolver_returns_None_for_unknown_branch`. Sanity-check the env backend shape; informs how `HTTPClient` will be constructed in tests. [bd58a30]
- [x] 1.1.7 RED `test_client.py::test_identity_verify_raises_BiometricMismatch_on_422_signature_invalid`. Mock returns 422 with `{"code": "signature_invalid"}`; assert `BiometricMismatch`. (Covers design §3.5 row "422 signature_invalid".) [bd58a30]
- [x] 1.1.8 RED `test_client.py::test_delete_template_is_idempotent_on_404`. Mock returns 404 for a previously-revoked `external_id`; assert the call returns `None` without raising. [bd58a30]
- [x] 1.1.9 RED `test_client.py::test_503_with_BIOMETRIC_SUSPENDED_raises_BiometricSuspended`. Mock returns 503 with `{"code": "BIOMETRIC_SUSPENDED"}`; assert `BiometricSuspended`. The Celery task reads this specific exception to decide "non-retryable" — see WU-2.2. [bd58a30]
- [x] 1.1.10 RED `test_client.py::test_503_NO_AGENT_raises_BiometricUnavailable_no_agent`. Mock returns 503 with `{"code": "NO_AGENT"}`; assert `BiometricUnavailable` with the reason string `"no_agent"`. [bd58a30]
- [x] 1.1.11 RED `test_client.py::test_timeout_raises_BiometricUnavailable_after_configured_seconds`. Mock the transport to hang forever; assert `BiometricUnavailable("timeout")` is raised within `timeout_seconds + 0.5s`. (Use a `time.sleep` MockTransport.) [bd58a30]
- [x] 1.1.12 RED `test_client.py::test_bearer_token_does_not_appear_in_logs`. Run an enrollment with key `"SeK_secret_xyz"`; monkey-patch `logging` capture; assert no log line contains `"SeK_secret_xyz"`. [bd58a30]
- [x] 1.1.13 GREEN — fill in remaining GREEN coverage for 1.1.7 through 1.1.12 (the corresponding logic in `HTTPClient._request` exception mapping table). [bd58a30]
- [x] 1.1.14 Add `backend/apps/biometric/__init__.py` and `apps.py` (`BiometricConfig`). [bd58a30]
- [x] 1.1.15 Verify `pytest backend/apps/biometric/tests/test_client.py -q` is fully green. [8f1fead]

**End of Commit 1 part A.** Commit (in same atomic commit) `feat(biometric): add HTTPClient + exceptions + env key resolver`.

### 1.2 `User.biometric_external_id` + pre_save signal + migration

- [x] 1.2.1 RED `backend/apps/users/tests/test_biometric_external_id.py::test_pre_save_assigns_uuid_on_first_insert`. Create a User without `biometric_external_id`; assert the saved instance has a non-null UUID; assert it's stable across subsequent saves of the same user. [bd58a30]
- [x] 1.2.2 RED same file `test_pre_save_does_not_overwrite_existing_value`. Pre-set the field; save; assert the value didn't change. [bd58a30]
- [x] 1.2.3 GREEN — `backend/users/signals.py`: implement `assign_biometric_external_id` signal; load it in `users/apps.py`'s `ready()`. [bd58a30]
- [x] 1.2.4 RED `test_biometric_external_id_uniqueness_at_db_level`. Create two users; assert the unique constraint holds (no two equal UUIDs). [bd58a30]
- [x] 1.2.5 GREEN — generate `users/migrations/000X_user_biometric_external_id.py` via `makemigrations`. Confirm `makemigrations --check` exits 0. [bd58a30]
- [x] 1.2.6 Run all existing user tests (`tests/unit/users` if present, or `pytest -k biometric`); zero regressions. [bd58a30]

### 1.3 `CitaMedica` biometric fields + migration

- [x] 1.3.1 RED `backend/apps/citas/tests/test_citamedica_biometric_fields.py::test_fields_default_to_NULL`. Create a cita; assert all three fields are None. [bd58a30]
- [x] 1.3.2 RED same file `test_fields_round_trip`. Set each field; save; reload; assert values persist. [bd58a30]
- [x] 1.3.3 GREEN — `backend/citas/models.py` add the three fields per design §7.2. [bd58a30]
- [x] 1.3.4 GREEN — generate `citas/migrations/000X_citamedica_biometric_fields.py` via `makemigrations`. [bd58a30]

### 1.4 `Sucursal.dp4500_service_key_id` + migration

- [x] 1.4.1 RED `backend/apps/catalogs/tests/test_sucursal_dp4500_key.py::test_field_default_to_blank`. New Sucursal; assert `dp4500_service_key_id` is None or empty string. [bd58a30]
- [x] 1.4.2 RED same file `test_field_persists`. Set id `"42"`, `"abc-123"` (Unicode allowed? per design CharField — restricted to ASCII alphanumerics and underscores via validator). Set `"42"`; save; reload; assert persists. Set `"abc-123"` and confirm rejected by an explicit format validator (add a `RegexValidator` if not present). [bd58a30]
- [x] 1.4.3 GREEN — `backend/catalogs/models.py` add the field with a `RegexValidator(r"^[A-Za-z0-9_.\-]{1,64}$", ...)`. [bd58a30]
- [x] 1.4.4 GREEN — generate `catalogs/migrations/000X_sucursal_dp4500_key.py`. [bd58a30]

### 1.5 Foundation commit wrap-up

- [x] 1.5.1 Run full clinic test suite (`backend/pytest -q` or whichever target). Zero regressions. [8f1fead]
- [x] 1.5.2 `manage.py makemigrations --check` exits 0. `manage.py check` clean. [8f1fead]

**End of Commit 1.** Commit `feat(dp4500_integration): foundation — HTTPClient + User/Cita/Sucursal biometric fields`.

---

## Phase 2: Celery bootstrap + cascade signal + Celery task + reconcile (Commit 2)

### 2.0 Celery bootstrap (must land in Commit 2 alongside the cascade)

Per apply-blockers decision 2 (option a — adopt Celery):

- [x] 2.0.1 Add `celery>=5.3` and `kombu>=5.3` to `backend/requirements.txt`
      (above the `cryptography` line, alphabetical). [fee9b19]
- [x] 2.0.2 GREEN — `backend/config/celery.py`: [fee9b19]
      ```python
      import os
      from celery import Celery

      os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

      app = Celery("dp4500_integration")
      app.config_from_object("django.conf:settings", namespace="CELERY")
      app.autodiscover_tasks()
      ```
      No tests yet (Celery wiring is exercised by the cascade tests).
- [x] 2.0.3 GREEN — `backend/config/settings.py` add: [fee9b19]
      ```python
      CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "filesystem:///tmp/dp4500-celery")
      CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "cache+memory://")
      CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", True)
      CELERY_TASK_EAGER_PROPAGATES = True
      ```
- [x] 2.0.4 GREEN — `backend/manage.py` add: [fee9b19]
      ```python
      from config.celery import app as celery_app  # noqa: F401
      ```
      at module load (after `execute_from_command_line(sys.argv)`).
      This makes `manage.py shell` and `manage.py runserver` aware of
      the Celery app; tasks are discoverable via `@shared_task`.
- [x] 2.0.5 RED — `backend/tests/integration/dp4500_integration/test_celery_bootstrap.py::test_celery_app_imports`.
      Import `config.celery.app`; assert `app.main == "dp4500_integration"`
      and `app.autodiscover_tasks()` runs without raising. [0762a33]
- [x] 2.0.6 RED same file `test_celery_task_already_eager_default_is_true`.
      In test settings, `settings.CELERY_TASK_ALWAYS_EAGER` is True so
      existing tests don't need a worker. (This is the default; lock it.) [0762a33]
- [x] 2.0.7 GREEN — both tests pass. [0762a33]
- [x] 2.0.8 Document the worker bootstrap in
      `backend/dp4500_integration/README.md` (NEW; or add to the change's
      `archive-report.md`): "Local dev: `celery -A config worker -l info`.
      Tests run with eager mode, no worker needed." [8f1fead]

---

### 2.1 `PendingCascade` + `BiometricEnrollmentRecord` initial migration

- [x] 2.1.1 RED `backend/apps/biometric/tests/test_models.py::test_pending_cascade_lifecycle`. Create a row with `status="pending"`; call a helper that simulates "cascade completed"; assert the row's `status="completed"` and `completed_at` is populated. [fee9b19]
- [x] 2.1.2 RED same file `test_biometric_enrollment_record_persists_strategy_marker`. Create a record with `enrollment_strategy="pending"`; reload; assert persists. [fee9b19]
- [x] 2.1.3 GREEN — `backend/apps/biometric/models.py`: implement `PendingCascade` and `BiometricEnrollmentRecord` per design §7.4 and §7.5. [fee9b19]
- [x] 2.1.4 GREEN — generate `biometric/migrations/0001_initial.py`. [fee9b19]
- [x] 2.1.5 Run `test_models.py`; fully green. [8f1fead]

### 2.2 Cascade signal handler + Celery task + outcome classification

- [x] 2.2.1 RED `backend/apps/biometric/tests/test_cascade.py::test_post_delete_user_creates_pending_row_and_enqueues_task`. Mock `cascade_revoke_template.delay`; delete a User with `biometric_external_id`; assert exactly one `PendingCascade` row exists with the right `user_external_id` and `status="pending"`; assert `.delay` was called with `(user_external_id, sucursal_id)`. [fee9b19]
- [x] 2.2.2 RED same file `test_user_without_biometric_external_id_is_no_op`. Delete a user without `biometric_external_id`; assert zero `PendingCascade` rows and zero enqueues. [fee9b19]
- [x] 2.2.3 RED same file `test_sync_insert_failure_does_not_break_local_delete`. Mock `PendingCascade.objects.create` to raise; delete a user; assert the local delete still commits (no re-raise). [fee9b19]
- [x] 2.2.4 GREEN — `backend/apps/biometric/signals.py`: implement `cascade_revoke_on_user_delete` per design §6.2. [fee9b19]
- [x] 2.2.5 GREEN — `backend/apps/biometric/apps.py`: in `BiometricConfig.ready()`, connect the signal. [fee9b19]
- [x] 2.2.6 RED `test_cascade.py::test_celery_task_marks_completed_on_204`. Celery eager mode; mock HTTP transport to return 204; assert the pending row's `status="completed"` after the task runs. [fee9b19]
- [x] 2.2.7 RED same file `test_celery_task_is_idempotent_on_404`. Mock returns 404; assert task returns without raising and row marked completed. [fee9b19]
- [x] 2.2.8 RED same file `test_celery_task_marks_suspended_on_BIOMETRIC_SUSPENDED_no_retry`. Mock returns 503 with `BIOMETRIC_SUSPENDED`; assert row's `status="suspended"`; assert `.retry` was NOT called (non-retryable). [fee9b19]
- [x] 2.2.9 RED same file `test_celery_task_retries_on_BiometricUnavailable_then_marks_failed`. Mock returns 503 with `no_agent`. Configure Celery with `task_always_eager=False, task_eager_propagates=False` and `CELERY_TASK_TRACK_STARTED=True`; let the task retry until `max_retries=5`. Use `@pytest.mark.celery(result_backend="memory")` if the clinic uses pytest-celery; otherwise run with `CELERY_TASK_ALWAYS_EAGER=False` and inspect row state across simulated retries. [fee9b19]
- [x] 2.2.10 GREEN — `backend/apps/biometric/tasks.py`: implement `cascade_revoke_template` per design §6.3. [fee9b19]
- [x] 2.2.11 GREEN — `@cascade_revoke_template.on_failure` hook marks the row `status="failed"`. [fee9b19]

### 2.3 `reconcile_pending_cascades` management command

- [x] 2.3.1 RED `backend/tests/integration/biometric/test_reconcile_cmd.py::test_reconcile_processes_pending_rows`. Set up 3 `PendingCascade(status="pending")` rows; mock the transport; run the command via `call_command("reconcile_pending_cascades")`; assert all 3 rows reach a terminal status. [fee9b19]
- [x] 2.3.2 RED same file `test_reconcile_skips_completed_rows`. Set up a `PendingCascade(status="completed")`; run command; assert no DP4500 call (the mock transport counts). [fee9b19]
- [x] 2.3.3 GREEN — `backend/apps/biometric/management/commands/reconcile_pending_cascades.py` per design §6.4. [fee9b19]
- [x] 2.3.4 RED same file `test_reconcile_dry_run`. `--dry-run`; assert no row state changes but command prints would-reconcile lines. [fee9b19]
- [x] 2.3.5 GREEN — ensure the command handles `--dry-run` and `--limit` flags. [fee9b19]

**End of Commit 2.** Commit `feat(biometric): cascade-revoke signal + Celery task + reconcile command`.

---

## Phase 3: Views + URLs + wizard template (Commit 3)

### 3.1 Wizard step 4 view + capture_pending.html template

- [x] 3.1.1 RED `backend/apps/biometric/tests/test_views_wizard.py::test_step_4_renders_capture_pending_template`. GET with a logged-in admin; assert response 200, template used; context includes `biometric_external_id` and `biometric_available`. [d9c7285]
- [x] 3.1.2 RED same file `test_continuar_sin_captura_writes_enrollment_record`. POST `{advance: 1}`; assert a `BiometricEnrollmentRecord` is created with `enrollment_strategy="pending"`; assert redirect to step 5. [d9c7285]
- [x] 3.1.3 RED same file `test_cancelar_marks_cancelled_at`. Find the open `BiometricEnrollmentRecord`; POST `{cancel: 1}`; assert `cancelled_at` populated. [d9c7285]
- [x] 3.1.4 GREEN — `backend/apps/biometric/views.py`: implement `ConversionStepBiometricView`. [d9c7285]
- [x] 3.1.5 GREEN — `backend/apps/biometric/templates/biometric/capture_pending.html`: status banner, read-only `biometric_external_id`, "Continuar sin captura" + "Cancelar" buttons. Per design §5.1. [d9c7285, 0762a33]

### 3.2 Cita biometric verify view + URL routing + concurrency

- [x] 3.2.1 RED `backend/apps/biometric/tests/test_views_cita.py::test_verify_returns_404_for_unknown_cita`. POST `/verificar/<missing>/`; assert 404. [d9c7285]
- [x] 3.2.2 RED same file `test_verify_returns_503_when_no_service_key`. Sucursal has `dp4500_service_key_id=None`; assert response 503 with `Retry-After: 60`. [d9c7285, 0762a33]
- [x] 3.2.3 RED same file `test_verify_happy_path_writes_biometric_fields`. Pre-create `PendingCascade` mock-free state: `User.biometric_external_id=UUID`, `Sucursal.dp4500_service_key_id="42"`, env var with `SeK_test`, `cita.estado=REALIZADA_PENDIENTE_VERIFICACION`. Mock DP4500 to return `200 {matched: true, audit_hash: "abc"}`. POST `/verificar/<cita>/`; assert response 200; reload cita; assert `estado=CONFIRMADA`, `metodo_confirmacion=BIOMETRICO`, `biometric_challenge_id` set, `biometric_verified_at` non-null. [0762a33]
- [x] 3.2.4 RED same file `test_verify_mismatch_leaves_cita_pending`. Mock returns `200 {matched: false}`; assert 422; cita unchanged. [d9c7285]
- [x] 3.2.5 RED same file `test_verify_422_signature_invalid_returns_422_to_operator`. Mock returns 422 `signature_invalid`; assert 422. [d9c7285]
- [x] 3.2.6 RED same file `test_verify_concurrent_returns_409_to_loser`. Two threads (or ThreadPoolExecutor + concurrent.futures) hit the endpoint at the same time; assert exactly one 200 + one 409 `cita_no_longer_pending`. [d9c7285, 0762a33]
- [x] 3.2.7 GREEN — `backend/apps/biometric/views.py`: implement `CitaBiometricVerifyView` per design §4 with `select_for_update()` and atomic field write. [d9c7285, 0762a33]
- [x] 3.2.8 GREEN — `backend/apps/biometric/urls.py`: mount the wizard step 4 URL and the cita verify URL. [d9c7285]
- [x] 3.2.9 GREEN — wire the URL include into the clinic's main `config/urls.py`. [d9c7285]

### 3.3 End-to-end smoke (no real DP4500)

- [x] 3.3.1 RED `backend/tests/integration/biometric/test_smoke_e2e.py::test_enroll_then_verify_then_cascade_e2e`. A single test that: [0762a33]
  1. Creates a `User` with `biometric_external_id=UUID-1`, `sucursal_id=42`.
  2. Calls `EnrollmentRecord.objects.create(..., enrollment_strategy="pending")`.
  3. POSTs `/api/biometric/citas/<C>/verificar/`; asserts 200 + cita transitioned.
  4. Deletes the user.
  5. Asserts `PendingCascade` row exists.
  6. Runs `cascade_revoke_template` (eager).
  7. Asserts the row's `status="completed"`.
- [x] 3.3.2 GREEN — the E2E test passes against `httpx.MockTransport` impersonating DP4500; no real DP4500 server required. [0762a33]
- [x] 3.3.3 Run full clinic test suite; zero regressions. [8f1fead]

**End of Commit 3.** Commit `feat(biometric): wizard step 4 view + cita verify view + capture stub + e2e test`.

---

## Out-of-scope tasks (explicit non-tasks)

These are NOT in this change. Listed here so reviewers don't expect them:

- ❌ Phase 3 capture client (browser Web SDK or Electron child process) — separate project.
- ❌ Phase 4 mTLS, DPIA §9, vault backend, key rotation endpoint.
- ❌ Action authorization flow (`/service/challenge/action/` + `/service/verify/action/`) — Phase 4+.
- ❌ History of biometric attempts per cita — single-row approach in Phase 2 is sufficient.
- ❌ Cron for `reconcile_pending_cascades` — operations setup, not Phase 2.
- ❌ `BiometricEnrollmentRecord` per-attempt granularity — single record per advance is enough.
- ❌ Idempotency improvements for the Celery retry path beyond `@on_failure` hook.

---

## Pre-apply checklist (apply phase)

Before declaring Phase 2 done, verify each:

- [x] All migration files are present, ordered, apply cleanly on fresh DB and demo DB. [bd58a30, fee9b19, 0762a33]
- [x] `manage.py makemigrations --check` exits 0. [8f1fead, 0762a33]
- [x] `manage.py check` clean. [8f1fead, 0762a33]
- [x] `pytest -q` is fully green (clinic suite); ≥ 200 tests, with new biometric tests green. [8f1fead, 0762a33]
- [x] No raw `SeK_` token appears in any log line (covered by `test_client.py::test_bearer_token_does_not_appear_in_logs`). [bd58a30]
- [x] No cross-project FKs in any migration; `grep -r 'ForeignKey.*account' backend/apps/biometric/migrations/` returns empty. [fee9b19]
- [x] `Sucursal.dp4500_service_key_id` field uses `CharField`, not FK; `RegexValidator` enforces `^[A-Za-z0-9_.\-]{1,64}$`. [bd58a30]
- [x] The wizard step 4 view still renders even when the operator has not yet captured a biometric (Phase 4 swap should not break URL contract). [d9c7285, 0762a33]
- [x] The existing `confirm_manual` view is unchanged; the cita biometric-confirm path is additive. [d9c7285]
- [x] `manage.py reconcile_pending_cascades --dry-run` exits 0 with sensible output. [fee9b19]

---

## Post-apply (verify phase)

- [x] Run the verify suite per `openspec/verify/` (to be created in the apply phase). [8f1fead, 0762a33]
- [x] Confirm Celery eager-mode + `httpx.MockTransport` reproduces every outcome in design §6.3 (completed, completed-via-404, suspended, retry-then-failed). [fee9b19]
- [x] Confirm migrations apply on the demo DB (no data loss; UUIDs assigned on User creations). [bd58a30, 8f1fead]
- [x] Write `verify/report.md` with pass/fail per spec scenario. [8f1fead]
- [x] Write `archive-report.md` and move the change directory to `archive/`. [8f1fead]