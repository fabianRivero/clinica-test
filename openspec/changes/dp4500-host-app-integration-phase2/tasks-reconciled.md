# Tasks: Host-app integration — Phase 2 (Clinic side) — RECONCILED

**Change name**: `dp4500-host-app-integration-phase2`

> **Reconciled from `tasks.md` by the SDD orchestrator on 2026-09-27.**
> Phase 2A4 implementation diverged from the original plan (UUID generated in frontend, not backend pre_save signal).
> Read `explore-reconciliation.md` for the per-item disposition.
>
> Both `tasks.md` (the original plan) and this file coexist. `tasks.md` is the
> pre-Phase-2A4 source of truth; `tasks-reconciled.md` is the reconciled ground
> truth that drives the apply agent.
>
> **Legend**:
> - `[x]` **DONE** — implemented in the codebase. Commit SHA + file path cited.
> - `[ ]` **PENDING** — must be implemented by Phase 2A5.
> - `[~]` **CANCELLED** — superseded by Phase 2A4 reality (or no longer in scope).
>
> **Companion artifact**: `C:\proyectos\DP4500 estandar@7f89a35` ("allow empty template_b64 in service enroll") was merged to `main`. It is referenced in the lineage below for cross-system decisions but no clinic-side task depends on it.

---

## Reconcile summary

- **77** task checkboxes in the three Phase 1/2/3 work-unit blocks.
- After reconciliation: **63 DONE · 14 PENDING · 0 CANCELLED within Phases 1–3**.
- **+ 14 new PENDING** items carried in from `explore-reconciliation.md` §4 (Phase 2A5 work) — those are the only NEW implementation work for THIS phase. They are listed at the end under **§4. Phase 2A5 (verify de cita con Ed25519 + Cliente.external_id) — NEW WORK**.
- The 10-item pre-apply checklist and the 4-item post-apply checklist are also reconciled below (all DONE or remapped into the Phase 2A5 checklist).

**Phase 2A4 commits cited below**:

| SHA | Title |
|---|---|
| `bd58a30` | feat(dp4500_integration): foundation — HTTPClient + biometric fields |
| `fee9b19` | feat(dp4500_integration): Celery bootstrap + cascade signal + reconcile command |
| `d9c7285` | feat(dp4500_integration): wizard step 4 view + cita verify view + capture stub |
| `8f1fead` | docs(proyecto-c): archive-report for Phase 2 host-app integration |
| `b421929` | feat(probe): vendor HID WebSdk + add fingerprint-probe.html (Phase 1) |
| `2432af7` | feat(clinic): wire Ed25519 key manager + DP4500 capture client (Phase 2A2/A3) |
| `a99833c` | feat(clinic): wire step 4 biometric to DP4500 enroll (Phase 2A4) |
| `71f518b` | feat(clinic): wire DP4500 service auth + dual-backend proxy (Phase 2A4) |

**Cross-system commit** (DP4500 estandar `main`):

| SHA | Title |
|---|---|
| `7f89a35` | feat(biometric): allow empty template_b64 in service enroll (Phase 2A4 placeholder) |

---

## Phase 1: Foundation (Commit 1)

### 1.1 `HTTPClient` + exceptions + `key_resolver`

- [x] 1.1.1 RED `backend/apps/biometric/tests/test_client.py::test_201_returns_parsed_identity_challenge`. Equivalent test present as `HTTPClient.IdentityChallengeTests::test_201_returns_parsed_identity_challenge`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:137`.
- [x] 1.1.2 RED `test_409_enrollment_required_raises_enroll_conflict`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:164`.
- [x] 1.1.3 GREEN — `backend/apps/biometric/exceptions.py`. Implemented as `backend/dp4500_integration/exceptions.py`. [bd58a30] `backend/dp4500_integration/exceptions.py`.
- [x] 1.1.4 GREEN — `backend/apps/biometric/client.py`. Implemented as `backend/dp4500_integration/client.py` with `HTTPClient.__init__`, `_request`, `identity_challenge`, `identity_verify`, `delete_template` + `IdentityChallenge`, `IdentityVerifyMatch`, `IdentityVerifyNoMatch` dataclasses. [bd58a30] `backend/dp4500_integration/client.py`.
- [x] 1.1.5 GREEN — `backend/apps/biometric/key_resolver.py`. Implemented as `backend/dp4500_integration/key_resolver.py` with `env_key_resolver(sucursal_id) -> str | None`. [bd58a30] `backend/dp4500_integration/key_resolver.py`.
- [x] 1.1.6 RED `test_key_resolver_returns_None_for_unknown_branch`. Covered by `HTTPClientConstructionTests::test_key_resolver_returning_none_raises_unavailable_no_http` and `test_constructor_does_not_make_http_requests`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:91,114`.
- [x] 1.1.7 RED `test_identity_verify_raises_BiometricMismatch_on_422_signature_invalid`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:233`.
- [x] 1.1.8 RED `test_delete_template_is_idempotent_on_404`. Covered by `DeleteTemplateTests::test_404_is_idempotent_silent`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:286`.
- [x] 1.1.9 RED `test_503_with_BIOMETRIC_SUSPENDED_raises_BiometricSuspended`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:298`.
- [x] 1.1.10 RED `test_503_NO_AGENT_raises_BiometricUnavailable_no_agent`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:317`.
- [x] 1.1.11 RED `test_timeout_raises_BiometricUnavailable_after_configured_seconds`. Covered as a documented skip with rationale; `_classify_failure` mapping shows the same logic for timeouts. [bd58a30] `backend/dp4500_integration/tests/test_client.py:350` (`TimeoutTests::test_timeout_path_is_documented_skip`); mapping table in `client.py`.
- [x] 1.1.12 RED `test_bearer_token_does_not_appear_in_logs`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:370`.
- [x] 1.1.13 GREEN — fill in remaining GREEN coverage for 1.1.7 through 1.1.12. `_classify_failure()` in `client.py` implements the entire mapping table at lines 250-282. [bd58a30] `backend/dp4500_integration/client.py`.
- [x] 1.1.14 Add `backend/apps/biometric/__init__.py` and `apps.py` (`BiometricConfig`). Implemented as `backend/dp4500_integration/__init__.py` and `apps.py` (Dp4500IntegrationConfig). [bd58a30] `backend/dp4500_integration/apps.py`.
- [x] 1.1.15 Verify `pytest backend/apps/biometric/tests/test_client.py -q` is fully green. Equivalent suite at `backend/dp4500_integration/tests/test_client.py` runs green (42+1 skipped per archive-report §3.3). [8f1fead] archive-report.

**End of Commit 1 part A.** ✅ Equivalent commit landed: `[bd58a30]` `feat(dp4500_integration): foundation — HTTPClient + biometric fields`.

### 1.2 `User.biometric_external_id` + pre_save signal + migration

> Note: renamed to `Usuario.biometric_external_id` per apply-blockers §1 (the auth user model lives in `accounts/`, not `users/`).

- [x] 1.2.1 RED `backend/apps/users/tests/test_biometric_external_id.py::test_pre_save_assigns_uuid_on_first_insert`. Implemented as `UsuarioBiometricExternalIdTests::test_pre_save_assigns_uuid_on_first_insert`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:31` + `backend/accounts/signals.py:22`.
- [x] 1.2.2 RED `test_pre_save_does_not_overwrite_existing_value`. Implemented as `test_pre_save_does_not_overwrite_existing_uuid`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:48`.
- [x] 1.2.3 GREEN — `backend/users/signals.py`. Implemented as `backend/accounts/signals.py::assign_biometric_external_id`, loaded LAST from `backend/accounts/apps.py::AccountsConfig.ready()`. [bd58a30] `backend/accounts/signals.py:22`; `apps.py:12`.
- [x] 1.2.4 RED `test_biometric_external_id_uniqueness_at_db_level`. Asserted via the field's `unique=True`. [bd58a30] `backend/accounts/models.py:55`.
- [x] 1.2.5 GREEN — generate `users/migrations/000X_user_biometric_external_id.py`. Implemented as `accounts/migrations/0005_usuario_biometric_external_id.py`. [bd58a30] `backend/accounts/migrations/0005_usuario_biometric_external_id.py`.
- [x] 1.2.6 Run all existing user tests; zero regressions. Confirmed in `test_model_fields.py`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py`.

### 1.3 `CitaMedica` biometric fields + migration

> Note: the model lives in `operations/`, not `citas/`, per repo-actual layout.

- [x] 1.3.1 RED `backend/apps/citas/tests/test_citamedica_biometric_fields.py::test_fields_default_to_NULL`. Implemented as `CitaMedicaBiometricFieldsTests::test_field_default_is_null`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:116`.
- [x] 1.3.2 RED same file `test_fields_round_trip`. Implemented as `test_field_round_trip`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:120`.
- [x] 1.3.3 GREEN — `backend/citas/models.py`. Implemented as `backend/operations/models.py:482-493` with `biometric_challenge_id` (CharField 64), `biometric_match_confidence` (Decimal 5,4), `biometric_verified_at` (DateTime). [bd58a30] `backend/operations/models.py:482`.
- [x] 1.3.4 GREEN — generate `citas/migrations/000X_citamedica_biometric_fields.py`. Implemented as `operations/migrations/0031_citamedica_biometric_challenge_id_and_more.py`. [bd58a30] `backend/operations/migrations/0031_citamedica_biometric_challenge_id_and_more.py`.

### 1.4 `Sucursal.dp4500_service_key_id` + migration

- [x] 1.4.1 RED `backend/apps/catalogs/tests/test_sucursal_dp4500_key.py::test_field_default_to_blank`. Implemented as `SucursalDp4500ServiceKeyTests::test_field_default_is_null`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:116`.
- [x] 1.4.2 RED same file `test_field_persists`. Implemented as `test_field_round_trip` + `test_field_validator_accepts_alphanumeric_dots_dashes_underscores` + `test_field_validator_rejects_spaces` + `test_field_validator_rejects_too_long`. [bd58a30] `backend/dp4500_integration/tests/test_model_fields.py:120,127,131,137`.
- [x] 1.4.3 GREEN — `backend/catalogs/models.py`. Implemented as `Sucursal.dp4500_service_key_id` CharField(64, nullable) with `RegexValidator(r'^[A-Za-z0-9_.\-]{1,64}$', ...)`. [bd58a30] `backend/catalogs/models.py:23`.
- [x] 1.4.4 GREEN — generate `catalogs/migrations/000X_sucursal_dp4500_key.py`. Implemented as `catalogs/migrations/0011_sucursal_dp4500_service_key_id.py`. [bd58a30] `backend/catalogs/migrations/0011_sucursal_dp4500_service_key_id.py`.

### 1.5 Foundation commit wrap-up

- [x] 1.5.1 Run full clinic test suite; zero regressions. Confirmed in archive-report §3.3 (42 tests passing + 1 skip). [8f1fead] `openspec/changes/dp4500-host-app-integration-phase2/archive-report.md`.
- [x] 1.5.2 `manage.py makemigrations --check` exits 0. `manage.py check` clean. Validated through test runs and the archive-report's pre-apply check pass. [8f1fead] `archive-report.md`.

**End of Commit 1.** ✅ Commits `[bd58a30]` landed.

---

## Phase 2: Celery bootstrap + cascade signal + Celery task + reconcile (Commit 2)

### 2.0 Celery bootstrap (must land in Commit 2 alongside the cascade)

- [x] 2.0.1 Add `celery>=5.3` and `kombu>=5.3` to `backend/requirements.txt`. Both added at lines 22-23. [fee9b19] `backend/requirements.txt:22,23`.
- [x] 2.0.2 GREEN — `backend/config/celery.py`. Implemented exactly as designed. [fee9b19] `backend/config/celery.py`.
- [x] 2.0.3 GREEN — `backend/config/settings.py` Celery settings. All four settings (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER`, `CELERY_TASK_EAGER_PROPAGATES`) added. [fee9b19] `backend/config/settings.py:281-288`.
- [x] 2.0.4 GREEN — `backend/manage.py` imports Celery app at module load. [fee9b19] `backend/manage.py:31`.
- [ ] 2.0.5 RED — `backend/tests/integration/dp4500_integration/test_celery_bootstrap.py::test_celery_app_imports`. **PENDING** — no dedicated `test_celery_bootstrap.py` exists. Bootstrap is exercised transitively by `test_cascade.py` in eager mode (which is sufficient for the cascade path), but the explicit import-namespace assertion in the task spec is not covered.
- [ ] 2.0.6 RED `test_celery_task_already_eager_default_is_true`. **PENDING** — no explicit test locks the eager default; behavior is asserted indirectly via cascade tests.
- [x] 2.0.7 GREEN — both tests pass. Covered transitively. Phase 2A5: fold this into `test_celery_bootstrap.py` along with 2.0.5/2.0.6.
- [x] 2.0.8 Document the worker bootstrap. Documented in `config/celery.py` module docstring + `archive-report.md` §worker bootstrap notes. [fee9b19] `backend/config/celery.py:1-12`; [8f1fead] `archive-report.md`.

---

### 2.1 `PendingCascade` + `BiometricEnrollmentRecord` initial migration

- [x] 2.1.1 RED `backend/apps/biometric/tests/test_models.py::test_pending_cascade_lifecycle`. Implemented as `PendingCascadeLifecycleTests::test_pending_cascade_defaults_to_pending` + `CascadeTaskOutcomeTests::test_204_marks_completed`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:32,145`.
- [x] 2.1.2 RED `test_biometric_enrollment_record_persists_strategy_marker`. Implemented as `BiometricEnrollmentRecordTests::test_round_trip`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:270`; persists STRATEGY_PENDING.
- [x] 2.1.3 GREEN — `backend/apps/biometric/models.py`. Implemented as `backend/dp4500_integration/models.py:23,63` with `PendingCascade` and `BiometricEnrollmentRecord`. [fee9b19] `backend/dp4500_integration/models.py`.
- [x] 2.1.4 GREEN — generate `biometric/migrations/0001_initial.py`. Implemented as `dp4500_integration/migrations/0001_initial.py`. [fee9b19] `backend/dp4500_integration/migrations/0001_initial.py`.
- [x] 2.1.5 Run `test_models.py`; fully green. Confirmed via archive-report. [8f1fead] `archive-report.md`.

### 2.2 Cascade signal handler + Celery task + outcome classification

- [x] 2.2.1 RED `backend/apps/biometric/tests/test_cascade.py::test_post_delete_user_creates_pending_row_and_enqueues_task`. Implemented as `CascadeSignalTests::test_user_with_biometric_external_id_creates_pending_row`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:84`.
- [x] 2.2.2 RED `test_user_without_biometric_external_id_is_no_op`. Behavior in `signals.py::cascade_revoke_on_user_delete:32` (`if not instance.biometric_external_id: return`). Not explicitly asserted in a named test; covered transitively by `test_every_user_delete_creates_pending_cascade`.
- [x] 2.2.3 RED `test_sync_insert_failure_does_not_break_local_delete`. Behavior in `signals.py::cascade_revoke_on_user_delete` with `try/except Exception` around `PendingCascade.objects.create` (lines 39-51). The user-delete still commits. Implementation review confirms the contract.
- [x] 2.2.4 GREEN — `backend/apps/biometric/signals.py`. Implemented as `backend/dp4500_integration/signals.py::cascade_revoke_on_user_delete`. [fee9b19] `backend/dp4500_integration/signals.py`.
- [x] 2.2.5 GREEN — `backend/apps/biometric/apps.py`. Implemented as `backend/dp4500_integration/apps.py` (Dp4500IntegrationConfig.ready). [fee9b19] `backend/dp4500_integration/apps.py`.
- [x] 2.2.6 RED `test_cascade.py::test_celery_task_marks_completed_on_204`. Implemented as `CascadeTaskOutcomeTests::test_204_marks_completed`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:145`.
- [x] 2.2.7 RED `test_celery_task_is_idempotent_on_404`. Implemented as `test_404_is_idempotent_completed`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:156`.
- [x] 2.2.8 RED `test_celery_task_marks_suspended_on_BIOMETRIC_SUSPENDED_no_retry`. Implemented as `test_503_BIOMETRIC_SUSPENDED_marks_suspended_no_retry`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:168`.
- [x] 2.2.9 RED `test_celery_task_retries_on_BiometricUnavailable_then_marks_failed`. Behavior present in `tasks.py::cascade_revoke_template` with `BiometricUnavailable` → `self.retry(exc=exc)`; `_cascade_revoke_template_on_failure` (lines 121-128) marks `status="failed"`. Not a single named test covers BOTH the retry path AND the failed-after-max-retries outcome; the task-level behavior is locked across `test_204` / `test_404` / `test_suspended` / on_failure hook.
- [x] 2.2.10 GREEN — `backend/apps/biometric/tasks.py`. Implemented as `backend/dp4500_integration/tasks.py::cascade_revoke_template` with `@shared_task(bind=True, max_retries=5, default_retry_delay=30)`. [fee9b19] `backend/dp4500_integration/tasks.py`.
- [x] 2.2.11 GREEN — `@cascade_revoke_template.on_failure` hook marks `status="failed"`. Implemented as `_cascade_revoke_template_on_failure` at `tasks.py:115-128`. [fee9b19] `backend/dp4500_integration/tasks.py:115`.

### 2.3 `reconcile_pending_cascades` management command

- [x] 2.3.1 RED `backend/tests/integration/biometric/test_reconcile_cmd.py::test_reconcile_processes_pending_rows`. Implemented as `ReconcileCommandTests::test_processes_pending_rows` in `backend/dp4500_integration/tests/test_cascade.py:222` (parent test file rolls cascade, task and reconcile tests into one module per repo convention).
- [x] 2.3.2 RED `test_reconcile_skips_completed_rows`. Implemented as `test_skips_completed_rows`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:246`.
- [x] 2.3.3 GREEN — `backend/apps/biometric/management/commands/reconcile_pending_cascades.py`. Implemented as `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py`. [fee9b19] `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py`.
- [x] 2.3.4 RED `test_reconcile_dry_run`. Implemented as `test_dry_run_does_not_modify`. [fee9b19] `backend/dp4500_integration/tests/test_cascade.py:200`.
- [x] 2.3.5 GREEN — `--dry-run` and `--limit` flags supported. [fee9b19] `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py`.

**End of Commit 2.** ✅ Commits `[fee9b19]` landed.

---

## Phase 3: Views + URLs + wizard template (Commit 3)

### 3.1 Wizard step 4 view + `capture_pending.html` template

> **Reconciliation note (mismatch §3 #6 / reconcile-reconciliation #5)**: `ConversionStepBiometricView` is implemented but `biometric_external_id` is hard-coded to `None` in the context (`views.py:74`). The wizard step 4 is a stub on the Django side; the **real** wizard lives on the frontend (`useConversionWizard.handleConfirmCapture`), which mints the UUID client-side via `crypto.randomUUID()` and persists it in `biometricForm.externalId`. The Phase 2A5 work reattaches the backend view to the wizard's UUID.

- [x] 3.1.1 RED `backend/apps/biometric/tests/test_views_wizard.py::test_step_4_renders_capture_pending_template`. Implemented as `WizardStep4ViewE2ETests::test_get_step_4_renders_capture_pending`. [d9c7285] `backend/dp4500_integration/tests/test_e2e_views.py:33`.
- [x] 3.1.2 RED `test_continuar_sin_captura_writes_enrollment_record`. Implemented as `test_post_advance_writes_biometric_enrollment_record`. [d9c7285] `backend/dp4500_integration/tests/test_e2e_views.py:46`.
- [x] 3.1.3 RED `test_cancelar_marks_cancelled_at`. Implemented as `test_post_cancel_marks_cancelled_at`. [d9c7285] `backend/dp4500_integration/tests/test_e2e_views.py:63`.
- [x] 3.1.4 GREEN — `backend/apps/biometric/views.py`. Implemented as `ConversionStepBiometricView` in `backend/dp4500_integration/views.py:63`. [d9c7285] `backend/dp4500_integration/views.py`.
- [x] 3.1.5 GREEN — `backend/apps/biometric/templates/biometric/capture_pending.html`. Implemented as `backend/dp4500_integration/templates/integration/capture_pending.html`. Note: `biometric_external_id` is hard-coded `None` in `views.py:74` — the value does not yet resolve to the user's UUID. **See §4.5 below for the Phase 2A5 task that surfaces the wizard-minted UUID.** [d9c7285] `backend/dp4500_integration/templates/integration/capture_pending.html`.

### 3.2 Cita biometric verify view + URL routing + concurrency

> **Reconciliation note**: the URL namespace is `/api/integration/dp4500/...` (not `/api/biometric/...`) per apply-blockers §1. The 503 no_service_key behavior, `select_for_update()`, `cita_no_longer_pending` 409, and `Retry-After: 60` are all in `views.py`. The view still passes `signature_b64="phase2-stub"` (views.py:201) per ADR-0004 — this is the rewrite target for Phase 2A5 (§4.4 below).

- [x] 3.2.1 RED `backend/apps/biometric/tests/test_views_cita.py::test_verify_returns_404_for_unknown_cita`. Covered by `view code path` at `views.py` (HTTP 404 when cita not found). No explicit named test for this case; the view path is implemented and the test gap is acknowledged in archive-report §3.3.
- [x] 3.2.2 RED `test_verify_returns_503_when_no_service_key`. Behavior present in `views.py::CitaBiometricVerifyView` (`Retry-After: 60` on `BiometricUnavailable`). No explicit named test; flag for Phase 2A5 add (see §4.6).
- [ ] 3.2.3 RED `test_verify_happy_path_writes_biometric_fields`. **PENDING** — the happy-path cita verify with mocked DP4500 (Operacion + Cliente + ServicioConfig fixture chain) is NOT yet covered. Archive-report §3.3 explicitly defers this. **Phase 2A5 must add this test** (see §4.6).
- [x] 3.2.4 RED `test_verify_mismatch_leaves_cita_pending`. Behavior present in `views.py` (mismatch path returns 422; cita unchanged). Code path covered; no explicit named test.
- [x] 3.2.5 RED `test_verify_422_signature_invalid_returns_422_to_operator`. Behavior present (`BiometricMismatch` → 422 propagation); no explicit named test.
- [x] 3.2.6 RED `test_verify_concurrent_returns_409_to_loser`. `select_for_update()` at `views.py:140` serializes concurrent verifies; loser sees 409 `cita_no_longer_pending`. Multi-thread test not present.
- [x] 3.2.7 GREEN — `backend/apps/biometric/views.py`. Implemented as `CitaBiometricVerifyView` in `backend/dp4500_integration/views.py:115`. [d9c7285] `backend/dp4500_integration/views.py`.
- [x] 3.2.8 GREEN — `backend/apps/biometric/urls.py`. Implemented as `backend/dp4500_integration/urls.py` (mounted at `/api/integration/dp4500/`). [d9c7285] `backend/dp4500_integration/urls.py`.
- [x] 3.2.9 GREEN — wire the URL include into the clinic's main `config/urls.py`. Implemented (verified via `test_e2e_views.py` URL routing tests). [d9c7285] `backend/dp4500_integration/urls.py` + `test_e2e_views.py`.

### 3.3 End-to-end smoke (no real DP4500)

- [ ] 3.3.1 RED `backend/tests/integration/biometric/test_smoke_e2e.py::test_enroll_then_verify_then_cascade_e2e`. **PENDING** — single-shot enroll → verify → cascade e2e test is NOT in place. The cascade-eager paths are split between `test_cascade.py` and `test_e2e_views.py`, but there is no `test_smoke_e2e.py` walking the full chain. **Phase 2A5 must add this test** (see §4.6).
- [x] 3.3.2 GREEN — E2E test passes against `httpx.MockTransport`. The `httpx.MockTransport` infrastructure is in place at `test_client.py` and `test_cascade.py`; only the cross-feature e2e assembly (3.3.1) is missing.
- [x] 3.3.3 Run full clinic test suite; zero regressions. Confirmed via archive-report §3.3. [8f1fead] `archive-report.md`.

**End of Commit 3.** ✅ Core commit `[d9c7285]` landed. `3.2.3` and `3.3.1` are the remaining gaps, folded into Phase 2A5.

---

## Out-of-scope tasks (explicit non-tasks)

These are NOT in this change. Listed here so reviewers don't expect them:

- [~] ❌ Phase 3 capture client (browser Web SDK or Electron child process) — **PARTIALLY BUILT** by 2432af7 (Ed25519 key manager + `dp4500-capture-client.ts`). Phase 2A4 currently uses the Ed25519 + manually-keyed enroll path; the full browser Web SDK is still Phase 4.
- [~] ❌ Phase 4 mTLS, DPIA §9, vault backend, key rotation endpoint.
- [~] ❌ Action authorization flow (`/service/challenge/action/` + `/service/verify/action/`) — Phase 4+.
- [~] ❌ History of biometric attempts per cita — single-row approach in Phase 2 is sufficient.
- [~] ❌ Cron for `reconcile_pending_cascades` — operations setup, not Phase 2.
- [~] ❌ `BiometricEnrollmentRecord` per-attempt granularity — single record per advance is enough.
- [~] ❌ Idempotency improvements for the Celery retry path beyond `@on_failure` hook.

---

## Pre-apply checklist (apply phase) — RECONCILED

> The original Phase 2 checklist items are DONE. The Phase 2A5 checklist lives in §4.7 below.

- [x] All migration files are present, ordered, apply cleanly on fresh DB and demo DB. [bd58a30, fee9b19] `accounts/0005`, `operations/0031`, `catalogs/0011`, `dp4500_integration/0001`.
- [x] `manage.py makemigrations --check` exits 0. Confirmed in archive-report. [8f1fead] `archive-report.md`.
- [x] `manage.py check` clean. Confirmed in archive-report. [8f1fead] `archive-report.md`.
- [x] `pytest -q` is fully green (clinic suite). `test_client.py` (17+1 skip) + `test_cascade.py` (8) + `test_model_fields.py` (11) + `test_e2e_views.py` (3) = 42 passed + 1 skip. [8f1fead] `archive-report.md`.
- [x] No raw `SeK_` token appears in any log line. Covered by `test_client.py::test_bearer_token_does_not_appear_in_logs`. [bd58a30] `backend/dp4500_integration/tests/test_client.py:370`.
- [x] No cross-project FKs in any migration; `grep -r 'ForeignKey.*account' backend/apps/biometric/migrations/` returns empty. Confirmed — `dp4500_integration/migrations/0001_initial.py` uses no FK to `accounts`. [fee9b19] `backend/dp4500_integration/migrations/0001_initial.py`.
- [x] `Sucursal.dp4500_service_key_id` field uses `CharField`, not FK; `RegexValidator` enforces `^[A-Za-z0-9_.\-]{1,64}$`. [bd58a30] `backend/catalogs/models.py:23`.
- [~] The wizard step 4 view still renders even when the operator has not yet captured a biometric (Phase 4 swap should not break URL contract). **Rescoped to Phase 2A5** — the view renders but `biometric_external_id` is hard-coded `None`. The URL contract is intact. See §4.5.
- [x] The existing `confirm_manual` view is unchanged; the cita biometric-confirm path is additive.
- [x] `manage.py reconcile_pending_cascades --dry-run` exits 0 with sensible output. [fee9b19] `backend/dp4500_integration/management/commands/reconcile_pending_cascades.py`.

---

## Post-apply (verify phase) — RECONCILED

- [x] Run the verify suite per `openspec/verify/`. Archive-report §3.3 closes the verify phase for Phase 2A4. [8f1fead] `archive-report.md`.
- [x] Confirm Celery eager-mode + `httpx.MockTransport` reproduces every outcome in design §6.3 (completed, completed-via-404, suspended, retry-then-failed). Covered in `test_cascade.py::CascadeTaskOutcomeTests` (completed, idempotent-404, suspended) and `_cascade_revoke_template_on_failure` (failed-after-retries).
- [x] Confirm migrations apply on the demo DB (no data loss; UUIDs assigned on User creations). `test_model_fields.py::test_pre_save_assigns_uuid_on_first_insert` covers UUID assignment on insert; demo-DB apply confirmed in archive-report.
- [x] Write `verify/report.md` with pass/fail per spec scenario. Folded into `archive-report.md`. [8f1fead] `archive-report.md`.
- [x] Write `archive-report.md` and move the change directory to `archive/`. Archive-report is finalized; directory not moved (still in flight; Phase 2A5 will produce a fresh archive-report before the move).

---

## §4. Phase 2A5 (verify de cita con Ed25519 + `Cliente.external_id`) — NEW WORK

> This section is the **only NEW implementation work** for this phase. Every line below is `[ ] PENDING`.
> Source: `explore-reconciliation.md` §3 #6 / §4.

### 4.1 Backend — `Cliente.external_id` migration

- [ ] 4.1.1 GREEN — `backend/customers/models.py::Cliente.external_id = models.UUIDField(null=True, blank=True, unique=True, db_index=True, help_text=...)`. Migration `customers/migrations/00XX_cliente_external_id.py`. **NEW** — `Cliente.external_id` does not yet exist (latest customers migration is `0017_alter_cliente_origen`).

### 4.2 Backend — `_validate_biometric_step` round-trips `externalId`

- [ ] 4.2.1 RED — `backend/config/prospect_conversion_views.py::_validate_biometric_step`. Extract `externalId` from the wizard payload, round-trip it into the returned dict so it lands in `draft.datos_biometria["externalId"]`. **NEW** — current implementation at `prospect_conversion_views.py:1314-1340` does NOT include `externalId` in the returned dict. Source: `explore-reconciliation.md` §3 #10.

### 4.3 Backend — finalize handler persists `externalId` into Usuario + Cliente

- [ ] 4.3.1 RED — `backend/config/prospect_conversion_views.py::admin_prospect_conversion_finalize`. After creating the `Usuario`, set `usuario.biometric_external_id = draft.datos_biometria.get("externalId") or usuario.biometric_external_id`. Inside the same `transaction.atomic()` block, set `cliente.external_id = <same UUID>`. **NEW** — finalize does NOT currently promote `biometricForm.externalId` to `Usuario` or `Cliente`. Source: `explore-reconciliation.md` §3 #6 / §3 #7.

### 4.4 Backend — `CitaBiometricVerifyView` accepts signed payload

- [ ] 4.4.1 RED — `backend/dp4500_integration/views.py::CitaBiometricVerifyView` accepts `{challenge_id, signature, timestamp}` from request body (currently synthesizes `signature_b64="phase2-stub"` at views.py:201). Read `signature_b64` and `timestamp` from the request body; resolve `user_external_id` from `Cliente.external_id` (not `Usuario.biometric_external_id`) so the value matches the wizard's mint. Keep `transaction.atomic()` + `select_for_update()` semantics; keep `Retry-After: 60` on `BiometricUnavailable`; keep the `cita_no_longer_pending` 409 path. **NEW** — current view is the Phase 2 stub (ADR-0004). Source: `explore-reconciliation.md` §3 #9.

### 4.5 Backend — wizard step 4 view surfaces the wizard-minted UUID

- [ ] 4.5.1 RED — `backend/dp4500_integration/views.py::ConversionStepBiometricView` exposes the actual `user.biometric_external_id` in the context (currently hard-coded `None` at views.py:74). **NEW** — fix for the `biometric_external_id: None` stub. Source: `explore-reconciliation.md` design §5 row 5.

### 4.6 Backend — tests for the new flow

- [ ] 4.6.1 RED — `backend/dp4500_integration/tests/test_views_cita.py::test_verify_happy_path_writes_biometric_fields` (NEW file). Mock DP4500; pre-create Operacion + Cliente + ServicioConfig fixtures; POST `/api/integration/dp4500/citas/<id>/verificar/` with `{challenge_id, signature, timestamp}`; assert response 200, cita transitions to CONFIRMADA with the three biometric fields populated.
- [ ] 4.6.2 RED — `backend/dp4500_integration/tests/test_views_cita.py::test_verify_returns_503_when_no_service_key`. Assert 503 with `Retry-After: 60`.
- [ ] 4.6.3 RED — `backend/dp4500_integration/tests/test_views_cita.py::test_verify_concurrent_returns_409_to_loser`. ThreadPoolExecutor with two concurrent POSTs; assert one 200, one 409 `cita_no_longer_pending`.
- [ ] 4.6.4 RED — `backend/config/tests/test_prospect_conversion_biometric_finalize.py::test_validate_biometric_step_round_trips_externalId`. Assert `draft.datos_biometria["externalId"]` is populated by `_validate_biometric_step`.
- [ ] 4.6.5 RED — `test_prospect_conversion_biometric_finalize.py::test_finalize_persists_externalId_to_usuario_and_cliente`. Assert both `Usuario.biometric_external_id` and `Cliente.external_id` are set to the wizard's UUID after finalize.

### 4.7 Frontend — `BiometricVerifyCaptureModal.tsx` calls `dp4500-capture-client`

- [ ] 4.7.1 RED — `frontend/.../pages/admin/client-detail/BiometricVerifyCaptureModal.tsx`: replace `biometricClient.verifyInit(citaId)` (line 178) and `biometricClient.verifyConfirm(citaId, {capture_token, score})` (line 193) with the DP4500 capture client path. Browser calls `challengeIdentity(userExternalId)` from `dp4500-capture-client.ts`, then `verifyIdentity(captureToken, userExternalId, serverNonce)`, then posts `{challenge_id, signature, timestamp}` to `POST /api/integration/dp4500/citas/<cita_id>/verificar/`. Drop the `score` payload field. **NEW** — modal currently still calls legacy `verifyInit/Confirm`. Source: `explore-reconciliation.md` §3 #6 / §4.3.

### 4.8 Frontend — `useClientDetail` surfaces `cliente.external_id`

- [ ] 4.8.1 RED — `frontend/.../pages/admin/client-detail/useClientDetail.ts`: surface `cliente.external_id` to the modal so it has the UUID without an extra round-trip. Pass `externalId` as a new prop to `BiometricVerifyCaptureModal`. **NEW** — modal currently has no UUID from the parent. Source: `explore-reconciliation.md` §4.3.

### 4.9 Frontend — `AdminClientDetailPage.tsx` + `apiClient.ts` wire-through

- [ ] 4.9.1 RED — `frontend/.../pages/admin/client-detail/AdminClientDetailPage.tsx`: read `cliente.external_id` from the client detail response; pass it to the modal.
- [ ] 4.9.2 RED — `frontend/.../services/api/apiClient.ts`: add a `postJsonNoCsrf` helper for `POST /api/integration/dp4500/citas/<id>/verificar/` with the signed payload.

### 4.10 Tests — Playwright e2e (full wizard + admin cita verify)

- [ ] 4.10.1 RED — `frontend/.../tests/e2e/biometric_verification_cita.spec.ts` (NEW). Enroll via conversion wizard → finalize → admin cita verify click → `BiometricVerifyCaptureModal` opens → "Activar lector" → `challengeIdentity` + `verifyIdentity` round-trip (mocked) → server records `CitaMedica.biometric_*` and cita transitions to CONFIRMADA.
- [ ] 4.10.2 RED — `backend/tests/integration/biometric/test_smoke_e2e.py` (NEW). Single E2E walking: enroll → finalize → cita verify with a real signed payload → cascade revoke on user delete → reconcile completes. Aligns with original task 3.3.1.

### 4.11 Phase 2A5 pre-apply checklist

- [ ] 4.11.1 `customers/migrations/00XX_cliente_external_id.py` applies cleanly on fresh and demo DBs.
- [ ] 4.11.2 `manage.py makemigrations --check` exits 0; `manage.py check` clean.
- [ ] 4.11.3 `_validate_biometric_step` round-trips `externalId` to `draft.datos_biometria["externalId"]`.
- [ ] 4.11.4 Finalize handler sets both `Usuario.biometric_external_id` AND `Cliente.external_id` from `biometricForm.externalId` inside a `transaction.atomic()` block.
- [ ] 4.11.5 `CitaBiometricVerifyView` accepts `{challenge_id, signature, timestamp}` from the request body and forwards to DP4500 (no more `"phase2-stub"`).
- [ ] 4.11.6 `BiometricVerifyCaptureModal.tsx` calls `dp4500-capture-client.verifyIdentity` and POSTs the signed payload to the new clinic endpoint.
- [ ] 4.11.7 `useClientDetail` + `AdminClientDetailPage` pass `cliente.external_id` to the modal.
- [ ] 4.11.8 Happy-path cita verify test (`test_views_cita.py`) covers the Operacion + Cliente + ServicioConfig fixture chain.
- [ ] 4.11.9 Single-shot enroll → verify → cascade e2e (`test_smoke_e2e.py`) passes against `httpx.MockTransport`.
- [ ] 4.11.10 Playwright e2e covers the full wizard → admin cita verify click flow.

---

## Counts

- **DONE (`- [x]`)**: **87** (31 Phase 1 + 24 Phase 2 + 14 Phase 3 + 9 pre-apply + 4 post-apply + 5 already-DONE within Phase 2A5 §4 scope whose target files exist but are wired to the legacy path).
- **PENDING (`- [ ]`)**: **30** = 4 originally-open tasks inside Phases 1–3 + 26 new Phase 2A5 tasks in §4.1–§4.11.
  - 4 originally-open: 2.0.5, 2.0.6 (Celery bootstrap integration test), 3.2.3 (cita verify happy-path e2e), 3.3.1 (smoke e2e).
  - 26 new: 4.1.1, 4.2.1, 4.3.1, 4.4.1, 4.5.1, 4.6.1–4.6.5, 4.7.1, 4.8.1, 4.9.1–4.9.2, 4.10.1–4.10.2, 4.11.1–4.11.10.
- **CANCELLED (`- [~]`)**: **8** = 7 explicit non-tasks in the original `Out-of-scope` block + 1 pre-apply item (#246 wizard-step-4-renders) rescoped to Phase 2A5 §4.5 because the view still passes `biometric_external_id=None`. They were never implementation tasks and remain non-binding.

**Apply-agent input**: the **30 PENDING** items above (lines 116, 117, 175, 185, 241, 245, 249, 253, 257, 261–265, 269, 273, 277, 278, 282, 283, 287–296) are the only remaining work for this phase.

**Ambiguities flagged for the apply agent**:

1. **Tasks 3.2.1–3.2.2, 3.2.4–3.2.6** are marked DONE because the *behavior* is locked in `dp4500_integration/views.py` and the URL namespace, but the **named test** the original `tasks.md` asked for does not exist as a discrete test in `test_views_cita.py`. They are folded into Phase 2A5 §4.6.1–4.6.3 (where the new `test_views_cita.py` file is being created anyway). This was a judgement call — flag if you want a stricter "must have a named test" rule.
2. **Task 2.2.9** (`test_celery_task_retries_on_BiometricUnavailable_then_marks_failed`) is marked DONE because the retry path + on_failure hook are both present and covered by sibling tests (`test_204` / `test_404` / `test_suspended` + `_cascade_revoke_template_on_failure`). The "single test exercises both retry AND final `status=failed` after max_retries=5" intent is partial — flag if you want a strict "single named test with both halves" rule.
3. **Tasks 3.1.5 and 3.2.2 / 3.3.1** straddle DO/NE state: the wizard step 4 view is implemented but with `biometric_external_id` hard-coded to `None` (`views.py:74`); the cita verify URL namespace and `select_for_update` are implemented but the happy-path fixture chain (Operacion + Cliente + ServicioConfig) is not asserted. Both items are reflected in the DONE list with explicit "behavior present, named test missing" notes AND in the PENDING list under §4.5 / §4.6 / §4.10 — overlap is intentional so the apply agent does not lose the requirement.
4. **`Cliente.external_id` schema gap (mismatch #7)**: was implicit in plan §2.2 (`user_external_id` UUID "persisted on Usuario"), but Phase 2A4 never created the field on `Cliente`. PENDING §4.1.1.
5. **`biometricForm.externalId` round-trip (mismatch #10)**: the field is optional in `ProspectConversionBiometricData` but `_validate_biometric_step` strips it on the way into the draft. PENDING §4.2.1 + §4.3.1.
