# Reconciliation: dp4500-host-app-integration-phase2 plan vs reality

**Prepared**: 2026-09-27
**Branch under review**: `feat/dp4500-host-app-integration-phase2-sdd` at `71f518b`
**Companion branch** (DP4500 estandar): `feat/dp4500-host-app-integration-phase1-apply` at `7f89a35` (now merged to `main`)
**Purpose**: Working analysis — not a formal `explore.md`. Drives the upcoming proposal/design/tasks reconciliation so the SDD artifacts match what is actually in the codebase after Phase 2A4.

This file is read-only for the orchestrator. It does NOT modify the SDD artifacts.

---

## 1. What was actually built (Phase 2A4)

Both repos shipped end-to-end wire contracts for the Phase 2A2 / 2A3 / 2A4 milestones. Commits below are the final state at `71f518b` (clinic) + `7f89a35` (DP4500).

### Clinic (this repo, `feat/dp4500-host-app-integration-phase2-sdd`)

- **`backend/dp4500_integration/`** — new sibling app per apply-blockers option (b).
  - `client.py` (HTTPClient, httpx wrapper) with `identity_challenge`, `identity_verify`, `delete_template`.
  - `exceptions.py` — `BiometricUnavailable`, `BiometricSuspended`, `BiometricMismatch`, `BiometricVerifyFailed`, `BiometricEnrollConflict`.
  - `key_resolver.py` — `env_key_resolver(sucursal_id) -> str | None` reading `DP4500_SERVICE_KEY_SUCURSAL_<id>`.
  - `models.py` — `PendingCascade` + `BiometricEnrollmentRecord`.
  - `signals.py` — `post_delete` on `Usuario` writes `PendingCascade` + enqueues Celery task. Best-effort (sync insert + enqueue both wrap their exceptions).
  - `tasks.py` — Celery `@shared_task(bind=True, max_retries=5, default_retry_delay=30)` with `_do_cascade()` helper; `_cascade_revoke_template_on_failure` hook flips `status="failed"` after retries exhaust.
  - `views.py` — `ConversionStepBiometricView` (GET/POST `wizard/prospecto/<id>/step-4/`, stub render + `BiometricEnrollmentRecord` write) and `CitaBiometricVerifyView` (POST `citas/<id>/verificar/`, runs challenge+verify inside `transaction.atomic()` with `select_for_update()`, writes the three `CitaMedica.biometric_*` fields on match, signature is the literal `"phase2-stub"` per ADR-0004).
  - `urls.py` mounted at `/api/integration/dp4500/`.
  - `templates/integration/capture_pending.html` — Phase 2 stub UI (Spanish copy, "Continuar sin captura" / "Cancelar").
  - `management/commands/reconcile_pending_cascades.py` — `--dry-run` + `--limit` flags.
  - `tests/test_client.py` (17+1 skip), `test_model_fields.py` (11), `test_cascade.py` (8), `test_e2e_views.py` (3). Total 42 passed, 1 skipped.
- **`backend/accounts/`** — `Usuario.biometric_external_id` UUIDField (`null, unique, db_index`) added via migration `0005_usuario_biometric_external_id`; `pre_save` signal `assign_biometric_external_id` mints UUID on first INSERT (preserves on UPDATE).
- **`backend/operations/`** — three new nullable fields on `CitaMedica`: `biometric_challenge_id` (CharField 64), `biometric_match_confidence` (Decimal 5,4), `biometric_verified_at` (DateTime). Migration `0031_citamedica_biometric_challenge_id_and_more`.
- **`backend/catalogs/`** — `Sucursal.dp4500_service_key_id` CharField(64, nullable) with `RegexValidator(r'^[A-Za-z0-9_.\-]{1,64}$', ...)`. Migration `0011_sucursal_dp4500_service_key_id`.
- **`backend/config/`** — `celery.py` Celery app (`proyecto_c` namespace); `settings.py` adds `CELERY_BROKER_URL=filesystem:///tmp/dp4500-celery` (default), `CELERY_TASK_ALWAYS_EAGER=True` (test default), `DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS=5`, `DP4500_KEY_STORE_BACKEND=env`. `manage.py` imports the Celery app at module load.
- **`backend/requirements.txt`** — `celery>=5.3` + `kombu>=5.3` added.
- **`frontend/aesthetic-clinic/src/services/biometric/ed25519-key-manager.ts`** — WebCrypto Ed25519 keypair manager; private key stored non-extractable in IndexedDB (`dp4500-signing:keys:signing-key-v1`); `publicKeyToBase64Url` + `signCanonical(...)` helpers.
- **`frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts`** — `enrollIdentity(...)`, `challengeIdentity(...)`, `verifyIdentity(...)`, `captureAndVerify(...)`. Reads `VITE_DP4500_SERVICE_API_KEY` at module load. `BiometricSuspendError` class.
- **`frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts`** — `handleConfirmCapture` mints `crypto.randomUUID()` as `user_external_id`, calls `enrollIdentity(externalId, '', signingKey, fingerprintHex, 'DP_PROPRIETARY')` best-effort. Also has a `NO_AGENT` fallback path that mints UUID + enrolls anyway when the physical reader is absent (Phase 2A4 dev escape hatch). UUID is persisted in `biometricForm.externalId`.
- **`frontend/aesthetic-clinic/src/types/prospectConversion.ts`** — `ProspectConversionBiometricData.externalId?: string` added; comment notes the finalize handler MUST persist this as `cliente.external_id` (Phase 2A5+).
- **`frontend/aesthetic-clinic/vite.config.ts`** — dual-backend proxy: `/api/biometric/service/* → VITE_DP4500_PROXY_TARGET (default 127.0.0.1:8000)` first (most-specific), everything else `/api/* + /media/* → VITE_API_PROXY_TARGET (default 127.0.0.1:8000)`.
- **`.env.example`** — documents `VITE_DP4500_SERVICE_API_KEY` + remediation hint.

### DP4500 estandar (companion repo, `feat/dp4500-host-app-integration-phase1-apply` at `7f89a35`)

- **`feat(biometric): add POST /service/identity/enroll/ + EnrollServiceIdentity use case`** (`dc0e838`) — server-side endpoint backing the Phase 2A enroll.
- **`fix(biometric): emit server_nonce as urlsafe base64 so the verify canonical matches`** (`75a481a`) — wire contract bugfix; canonical is now byte-exact with the client's `signCanonical` output.
- **`feat(biometric): allow empty template_b64 in service enroll (Phase 2A4 placeholder)`** (`7f89a35`) — Phase 2A4 placeholder; `user_external_id`, `client_pubkey_b64`, `client_pubkey_fingerprint` remain strictly required; `template_b64` may be empty. New test `test_identity_enroll_view_empty_template_b64_phase2a4_placeholder` locks the contract.

### Validated end-to-end (per commit messages)

> "Phase 2A4 host-app integration: validate the DP4500 enroll wire contract end-to-end from the conversion wizard step 4. Ed25519 pubkey + UUID mint + audit ack verified in browser (201 from /api/biometric/service/identity/enroll/ with a real BiometricTemplate row persisted)."

---

## 2. What the plan said

### Proposal (`proposal.md`)

| § | Plan says | Reality |
|---|---|---|
| §2.1 | `apps/biometric/` Django app with `client.py`, `views.py`, `urls.py`, `exceptions.py`, `migrations/0001_initial.py`, `templates/biometric/capture_pending.html`, `tests/` | Actually lives at `backend/dp4500_integration/` per apply-blockers §1 (option b). Template path is `templates/integration/capture_pending.html`. Everything else is in place. ✅ |
| §2.2 | `users.User.biometric_external_id` UUIDField nullable, unique, generated by `pre_save` signal on first INSERT. Model file: `apps/users/models.py` | Field exists on `accounts.Usuario.biometric_external_id`; signal lives in `accounts/signals.py` and is loaded LAST from `accounts/apps.py::AccountsConfig.ready()`. The **plan did NOT predict** that the frontend would also mint a UUID via `crypto.randomUUID()` and persist it in `biometricForm.externalId` as the source of truth. ⚠ |
| §2.3 | `citas.CitaMedica` gets `biometric_challenge_id` (CharField 64, nullable), `biometric_match_confidence` (Decimal 5,4, nullable), `biometric_verified_at` (DateTime, nullable). Model file: `apps/citas/models.py` | All three fields exist on `operations.CitaMedica`. Migration `0031` applies cleanly. ✅ |
| §2.4 | `Sucursal.dp4500_service_key` FK to `accounts.ServiceAPIKey` in DP4500; documented later as `dp4500_service_key_id` CharField (not FK, by id) | Field exists as `Sucursal.dp4500_service_key_id` CharField(64, nullable) with `RegexValidator`. Per-branch lookup goes through `env_key_resolver(sucursal_id)` reading `DP4500_SERVICE_KEY_SUCURSAL_<id>`. **Plan did NOT anticipate** that the frontend would use a SINGLE global `VITE_DP4500_SERVICE_API_KEY` env var instead of per-sucursal lookup. ⚠ |
| §2.5 | `post_delete` signal → sync `PendingCascade.objects.create` + Celery `.delay()`. Celery `@shared_task(bind=True, max_retries=5, default_retry_delay=30)`. `PendingCascade` lives in `biometric/models.py`. `reconcile_pending_cascades` mgmt command | All implemented. App is `dp4500_integration` (not `biometric`). Signal + Celery + mgmt command all in place. ✅ |
| §2.6 | `DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`, `DP4500_KEY_STORE_BACKEND` env vars | All in `config/settings.py`. ✅ |
| §2.7 | Tests: 100% line coverage on `client.py`, >80% branch coverage on `views.py` | `test_client.py` (17+1 skip), `test_cascade.py` (8), `test_model_fields.py` (11), `test_e2e_views.py` (3). Total 42 + 1 skip; archive-report claims targets met. ✅ |
| §3 (in-scope) | Wizard step 4 stub, `CitaMedica` 3 biometric fields, `Sucursal.dp4500_service_key_id`, cascade hook + Celery retry, settings, mgmt command, SDD artifacts | Everything in scope landed. ✅ |
| §3 (out-of-scope) | Phase 3 capture client; Phase 4 mTLS / DPIA / vault; action authorization; per-cita biometric history; cron for reconcile | All deferred as planned. ✅ |
| §4 (decisions) | One `ServiceAPIKey` per `Sucursal` per environment | **Mismatched reality**: clinic uses ONE `VITE_DP4500_SERVICE_API_KEY` for all workstations (per-deployment, not per-sucursal). The backend `env_key_resolver` does per-sucursal lookup, but no `DP4500_SERVICE_KEY_SUCURSAL_<id>` env vars are documented in `.env.example` and the frontend can't switch keys per branch. ⚠ |

### Design (`design.md`)

| § | Plan says | Reality |
|---|---|---|
| §1.2 components | `biometric.HTTPClient`, `biometric.key_resolver`, `biometric.views`, `biometric.urls`, `biometric.models`, `biometric.tasks`, `biometric.signals`, `biometric.templates.biometric/capture_pending.html`, `users.User.biometric_external_id`, `users.signals.assign_biometric_external_id`, `citas.CitaMedica.{biometric_*}`, `catalogs.Sucursal.dp4500_service_key_id` | All exist under `dp4500_integration/` (renamed app) and `accounts/` (renamed app). Layout updated per apply-blockers §1. ✅ |
| §2 module layout | `backend/apps/biometric/` nested layout | Repo uses flat `backend/<appname>/`; new sibling app is `backend/dp4500_integration/`. Already documented in `apply-blockers.md`. ✅ |
| §3 service client | `HTTPClient(base_url, timeout_seconds, key_resolver)`, `identity_challenge`, `identity_verify`, `delete_template`, dataclasses `IdentityChallenge`, `IdentityVerifyMatch`, `IdentityVerifyNoMatch`, exception hierarchy | All implemented exactly as designed. ✅ |
| §3.5 error mapping | 422 `signature_invalid` → `BiometricMismatch`; 422 `INVALID_TOKEN` → `BiometricVerifyFailed("challenge_expired_or_invalid")`; 503 `BIOMETRIC_SUSPENDED` → `BiometricSuspended`; 503 `NO_AGENT` → `BiometricUnavailable("no_agent")`; 404 on DELETE → silent (idempotent); 5xx → `BiometricUnavailable`; timeout → `BiometricUnavailable("timeout")` | `client._classify_failure()` implements the table exactly. ✅ |
| §4 cita verify | `CitaBiometricVerifyView` runs challenge+verify inside `transaction.atomic()` with `select_for_update()`; on match writes all 3 fields; signature = `"phase2-stub"`; 503 with `Retry-After: 60`; concurrency returns 409 `cita_no_longer_pending` | All in `views.py::CitaBiometricVerifyView`. ✅ |
| §5 wizard step 4 | `ConversionStepBiometricView` renders `capture_pending.html`, exposes `biometric_external_id` (read-only), "Continuar sin captura" + "Cancelar" buttons. Phase 2 stub | View is in place but `biometric_external_id` is hard-coded to `None` (line 74 in `views.py`) — the wizard's prospect → User transition is not wired in this commit; UUID flow goes through `biometricForm.externalId` instead. ⚠ |
| §6 cascade revoke | `PendingCascade` model + signal + Celery task + on_failure hook + reconciliation command; `sucursal_id = IntegerField` (not FK); `attempts`, `last_error_code`, `completed_at`, status enum | All implemented exactly. ✅ |
| §7.1 `users.User.biometric_external_id` | UUIDField nullable, unique, db_index; pre_save signal sets on first INSERT | Implemented. **But the frontend mints a separate UUID via `crypto.randomUUID()`**; the two are NOT yet linked at the data-model level (the pre_save UUID on `Usuario` and the wizard-minted UUID in `biometricForm.externalId` are independent until the finalize handler reconciles them — see Phase 2A5 below). ⚠ |
| §7.2 `citas.CitaMedica` biometric fields | Three nullable fields | All present. ✅ |
| §7.3 `catalogs.Sucursal.dp4500_service_key_id` | CharField(64, nullable); cross-project reference by id; raw token in env vars | Field present; `RegexValidator` enforces `^[A-Za-z0-9_.\-]{1,64}$`. ✅ |
| §7.4 `biometric.PendingCascade` | Same as §6 | Implemented. ✅ |
| §7.5 `BiometricEnrollmentRecord` | FK to User, `user_external_id`, `wizard_id`, `enrollment_strategy`, `advanced_at`, `advanced_by`, `cancelled_at` | Implemented. ✅ |
| §8 settings | `DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`, `DP4500_KEY_STORE_BACKEND` | All in `config/settings.py`. ✅ |
| §9 migrations | 4 migrations: `accounts/0005`, `citas/00XX`, `catalogs/00XX`, `biometric/0001` | All present (under repo-actual app names: `accounts/0005`, `operations/0031`, `catalogs/0011`, `dp4500_integration/0001`). ✅ |
| §10 tests | 100% line on `client.py`, ≥90% on `views.py`+`signals.py`, ≥80% on `tasks.py` | `test_client.py` covers the status mapping; `test_e2e_views.py` covers URL routing only — the `CitaBiometricVerifyView` happy-path is NOT covered end-to-end (archive-report §3.3 acknowledged this). ⚠ |
| §13 ADRs | 5 ADRs (CharField not FK, env-only backend, capture swap, signature stub, cross-project reference) | All 5 ADRs locked in `design.md`. ✅ |

### Tasks (`tasks.md`)

All three commits' work units were completed. Two important deviations:

1. **WU-1.1.12**: `test_bearer_token_does_not_appear_in_logs` is in `test_client.py`; pass.
2. **WU-3.2** (`CitaBiometricVerifyView` e2e) is only covered at the URL-routing level in `test_e2e_views.py`. The happy-path fixture chain (Operacion + Cliente + ServicioConfig) is acknowledged as deferred to Phase 4 in archive-report §3.3.

---

## 3. Mismatches (numbered, with disposition)

### 1. UUID source: backend pre_save signal vs frontend `crypto.randomUUID()`

**Plan said** (§proposal §2.2, §design §7.1): `Usuario.biometric_external_id` is generated by a `pre_save` signal on first INSERT. The pre_save signal is the source of truth; the frontend reads it back when needed.

**Reality**: The frontend mints the UUID via `crypto.randomUUID()` in `useConversionWizard.handleConfirmCapture` (lines 780, 811, 843 of `useConversionWizard.ts`) and persists it in `biometricForm.externalId`. The `Usuario.biometric_external_id` UUID is generated by the signal on User insert but is **not yet used** as the cross-system handle. The two UUIDs are independent.

**Consequence**: The DP4500 enroll endpoint currently receives the **frontend-minted** UUID (passed in the enroll body), not the backend-minted one. The backend-minted UUID sits in the `Usuario` row but is not surfaced to the wizard, the DP4500 client, or the `CitaBiometricVerifyView` (which calls `usuario.biometric_external_id` — but the comment block at views.py:170-184 shows it's reading it correctly).

**Disposition**: **Reasign**. The frontend-minted UUID is the right model for Opción A (capture is workstation- and operator-driven; the UUID is a stable identifier the workstation will sign against for every cita check-in). The pre_save signal stays as a defensive fallback for users that bypass the wizard (e.g. admin-created accounts). Phase 2A5 reconciles them by persisting `biometricForm.externalId` into `Usuario.biometric_external_id` during finalize (the latter is regenerated by the signal if not yet set; if it's already set from a previous capture, the finalize handler must overwrite-or-keep it).

### 2. Service-key granularity: per-sucursal vs single global key

**Plan said** (§proposal §4, decision "Key granularity = One ServiceAPIKey per Sucursal per environment"): Each `Sucursal` has its own `dp4500_service_key_id` reference; raw token via `DP4500_SERVICE_KEY_SUCURSAL_<id>` env var.

**Reality**: The frontend uses a single `VITE_DP4500_SERVICE_API_KEY` env var (per-deployment, not per-sucursal). The `frontend/aesthetic-clinic/.env.example` documents a single key. The Vite proxy is a single target. The backend's `env_key_resolver` reads `DP4500_SERVICE_KEY_SUCURSAL_<id>` but no `.env.example` documents it; production deployment relies on the frontend key.

**Consequence**: Cross-branch blast radius is the whole deployment, not a single branch. An operator PC that has the key compromised compromises all branches.

**Disposition**: **Reasign**, with explicit acknowledgement. Single-key is acceptable for Phase 2A4 dev/demo; per-sucursal keys are an explicit ops policy decision that requires frontend routing changes (which key for which `sucursal_id` is a per-request decision). Phase 2A5 should keep the backend's per-sucursal `env_key_resolver` but also document the single-key fallback path used today. The SDD should be updated to reflect: "key granularity is configurable per deployment; default is a single workstation key for dev, per-sucursal for prod."

### 3. Python `HTTPClient` (backend) vs TypeScript `dp4500-capture-client` (frontend)

**Plan said** (§proposal §2.1, §design §1.2): `biometric.HTTPClient` is the thin httpx wrapper. The capture flow goes through it.

**Reality**: Both exist. The Python `HTTPClient` exists at `backend/dp4500_integration/client.py` and is exercised by `CitaBiometricVerifyView` (challenge + verify on cita check-in) and by `cascade_revoke_template` (DELETE on user delete). The TypeScript `dp4500-capture-client.ts` exists at `frontend/.../services/biometric/dp4500-capture-client.ts` and is exercised by `useConversionWizard.handleConfirmCapture` (enroll). The two coexist because they target different operations: the Python client is server-to-server (challenge/verify/delete from inside the clinic backend), the TS client is browser-to-server (enroll/challenge/verify from the operator's workstation).

**Consequence**: Plan §2.1 described only the Python client; the frontend `dp4500-capture-client.ts` is a Phase 2A2 addition that the SDD did not predict.

**Disposition**: **Reasign**. The two clients are complementary, not redundant. SDD should be updated to describe BOTH, with a clear contract table: which operation goes through which client, who calls what, who reads what from `VITE_DP4500_SERVICE_API_KEY` vs `DP4500_SERVICE_KEY_SUCURSAL_<id>`.

### 4. Celery + cascade revoke

**Plan said** (§proposal §2.5, §design §6): Adopt Celery, `@shared_task` with `max_retries=5, default_retry_delay=30`, `PendingCascade` rows, `reconcile_pending_cascades` mgmt command.

**Reality**: All implemented exactly as designed. `config/celery.py`, `requirements.txt`, `tasks.py`, `signals.py`, `models.py`, `management/commands/reconcile_pending_cascades.py` are all in place.

**Disposition**: **Keep**.

### 5. `CitaMedica` biometric fields

**Plan said** (§proposal §2.3, §design §7.2): Three nullable fields on `CitaMedica`.

**Reality**: Implemented exactly as designed at `operations/models.py:482-493`.

**Disposition**: **Keep**.

### 6. Phase 2A5 (verify de cita con Ed25519) — NOT STARTED

**Plan said** (§proposal §3 out-of-scope, §tasks out-of-scope §3.3 e2e fixtures): The cita verify view's full e2e fixture chain is deferred to Phase 4; the wire contract for verify is wired with stub signature.

**Reality**: `CitaBiometricVerifyView` exists at `backend/dp4500_integration/views.py:115-247`, but the frontend `BiometricVerifyCaptureModal.tsx` STILL calls the legacy `biometricClient.verifyInit()` / `verifyConfirm()` (lines 178, 193 of `BiometricVerifyCaptureModal.tsx`). The frontend never invokes `verifyIdentity()` from `dp4500-capture-client.ts` on the cita verify path. Phase 2A5 is not started.

Additionally, the `Cliente` model has NO `external_id` field today. The `biometricForm.externalId` is persisted in the wizard's draft (`draft.datos_biometria["externalId"]` would be the expected shape, but `_validate_biometric_step` in `prospect_conversion_views.py:1314-1340` does NOT extract or store `externalId`), and the finalize handler does NOT promote it to `Usuario.biometric_external_id` or `Cliente.external_id`.

**Disposition**: **Reasign** as the open Phase 2A5 work item. See §4 below.

### 7. `Cliente.external_id` UUIDField

**Plan said**: Implicit — `user_external_id` shape is UUID, persisted on `Usuario` (decision Q2, §proposal §4).

**Reality**: `Cliente` model has no `external_id` field. Only `Usuario.biometric_external_id` exists. The plan's decision was that the UUID lives on `Usuario` (the underlying auth user) and the frontend UUID flows there via the signal — but the implementation reality (frontend-minted UUID) needs a separate storage path.

**Disposition**: **Reasign**. Phase 2A5 must decide: (a) promote `biometricForm.externalId` to `Usuario.biometric_external_id` on finalize (current path; already partially set by the pre_save signal); OR (b) add a new `Cliente.external_id` UUIDField and persist the wizard-minted UUID there; OR (c) keep both — the pre_save signal provides a defensive UUID for non-wizard users; the wizard persists `biometricForm.externalId` to the User row. The simplest is (a); it needs the finalize handler to detect the conflict and pick the right value (prefer the pre-saved one if it exists, else write the wizard-minted one).

### 8. URL contract for cita verify view

**Plan said** (§design §4.1, §spec §cita-biometric-verification): `POST /api/biometric/citas/<cita_id>/verificar/`.

**Reality**: The Python endpoint is mounted at `POST /api/integration/dp4500/citas/<cita_id>/verificar/` (per apply-blockers §1 option b — different namespace from legacy `/api/biometric/...`).

**Disposition**: **Keep**. The legacy URL stays for the fprintd flow; the new namespace is the canonical Phase 2 path. Frontend rewrite (Phase 2A5) must point the cita verify modal at `/api/integration/dp4500/citas/<id>/verificar/` (or, for Opción A, drive the flow through `verifyIdentity()` client-side and post the result to the new endpoint to record `CitaMedica.biometric_*`).

### 9. Stub signature

**Plan said** (ADR-0004 in §design §13): Phase 2 view passes `"phase2-stub"` as `signature_b64`; real Ed25519 lands in Phase 4.

**Reality**: Confirmed at `views.py:201` (`signature_b64="phase2-stub"`).

**Disposition**: **Reasign for Phase 2A5**. The frontend now has the Ed25519 keypair + `signCanonical()` machinery (2432af7). The Phase 2A5 path can sign the canonical in the browser and POST the signed payload to a slightly different endpoint (or to the same endpoint with the real signature), and the server-side stub check (DP4500's `ConsumeServiceIdentityChallenge`) needs to verify it. The DP4500 server-side commit `de64ad4` already does real Ed25519 verify, so the wire is ready — the clinic's Python `CitaBiometricVerifyView` just needs to receive the signed payload from the browser (not generate a stub locally).

### 10. Frontend `biometricForm.externalId` typing

**Plan said**: `ProspectConversionBiometricData` is the draft's biometric payload.

**Reality**: `ProspectConversionBiometricData.externalId?: string` added (line 162 of `prospectConversion.ts`); comment notes the finalize handler MUST persist this as `cliente.external_id`. The `_validate_biometric_step` in `prospect_conversion_views.py:1314-1340` does NOT include `externalId` in the returned dict — it strips it on the way into the draft.

**Disposition**: **Reasign** for Phase 2A5. The validate function must round-trip `externalId` so the finalize handler can read it back and persist it on `Usuario.biometric_external_id`.

### 11. `models.Meta.db_table` naming

**Plan said** (§design §6.1): `PendingCascade.Meta.db_table = "biometric_pendingcascade"`.

**Reality**: `PendingCascade.Meta.db_table = "dp4500_integration_pending_cascade"` (and `BiometricEnrollmentRecord.Meta.db_table = "dp4500_integration_enrollment_record"`) per `models.py:56, 101`.

**Disposition**: **Keep** — rename reflects the actual app name (`dp4500_integration` per apply-blockers §1).

### 12. `User.delete()` semantics — hard vs soft delete

**Plan said** (§proposal §5 open item 4, §design §12.4): Hook fires on any `.delete()`; soft-delete via `deleted_at` is the call site's responsibility.

**Reality**: The signal is connected to `Usuario` (`accounts.models.Usuario`). The hook fires on `post_delete`, so it fires on hard delete only (the cascade path is not aware of soft-delete patterns). The current `accounts/models.py` does NOT have a `deleted_at` field, so soft-delete isn't relevant today.

**Disposition**: **Keep**.

### 13. ADR-0004: signature stub — now superseded by Phase 2A2/A3 work

**Plan said** (§design §13 ADR-0004): Phase 2 signature is a stub; real Ed25519 lands with the capture client in Phase 4.

**Reality**: The frontend now has the full Ed25519 machinery (`ed25519-key-manager.ts`, `dp4500-capture-client.verifyIdentity()`). The backend server-side (DP4500 estandar `de64ad4`) does real Ed25519 verify. The clinic's Python `CitaBiometricVerifyView` is the only place still passing `"phase2-stub"`.

**Disposition**: **Cancel** the ADR-0004 stub claim for Phase 2A5. The wire is ready; only the clinic view's signature-generation step needs to switch from `"phase2-stub"` to "browser-signed canonical."

---

## 4. Open work for Phase 2A5 (verify de cita con Ed25519)

### 4.1 Scope

Wire the existing Ed25519 + `dp4500-capture-client.verifyIdentity()` machinery on the browser side into the cita verify modal, and stop the clinic backend's Python view from generating the `"phase2-stub"` signature locally. Add `Cliente.external_id` persistence so the verify path can look up the user by the wizard-minted UUID.

### 4.2 Backend (`backend/clinic`)

**Files to touch**:

1. **`backend/accounts/models.py`** — confirm `Usuario.biometric_external_id` is the canonical storage for the wizard-minted UUID (it is; no schema change needed). Document in the field's `help_text` that wizard-minted UUIDs override the pre_save-minted one during finalize.
2. **`backend/customers/models.py`** — add `Cliente.external_id` UUIDField nullable + unique + db_index (the cross-system handle surfaced to DP4500). Migration in `customers/migrations/`.
3. **`backend/config/prospect_conversion_views.py`**:
   - `_validate_biometric_step` (line 1314): round-trip `externalId` into the returned dict so it lands in `draft.datos_biometria["externalId"]`.
   - `admin_prospect_conversion_finalize` (~line 1940, in the section that creates the `Usuario` + `Cliente` from the prospect): after creating the Usuario, set `usuario.biometric_external_id = draft.datos_biometria.get("externalId") or usuario.biometric_external_id`. On the same atomic block, set `cliente.external_id = <same UUID>`. Both writes happen inside the same `transaction.atomic()` as the rest of finalize.
4. **`backend/dp4500_integration/views.py`** (`CitaBiometricVerifyView`):
   - Read the request body (current implementation synthesizes `signature_b64="phase2-stub"` and `timestamp=now()`). Phase 2A5: accept `signature_b64` and `timestamp` from the request body (the browser computes them via `signCanonical(...)`).
   - Resolve `user_external_id` from `Cliente.external_id` (new field) — NOT from `Usuario.biometric_external_id` — so the value matches the wizard's mint.
   - Keep the `transaction.atomic()` + `select_for_update()` semantics; keep the 503 `Retry-After: 60` on `BiometricUnavailable`; keep the 422 `biometric_mismatch` path.
5. **`backend/dp4500_integration/tests/test_e2e_views.py`** — extend the e2e to cover the happy-path cita verify (Operacion + Cliente + ServicioConfig fixture chain, archive-report §3.3 acknowledgement).
6. **`backend/config/tests/`** — new test for `_validate_biometric_step` round-tripping `externalId`; new test for finalize persisting `externalId` into `Usuario.biometric_external_id` AND `Cliente.external_id`.

**Contracts (no schema break)**:

- Request: `POST /api/integration/dp4500/citas/<cita_id>/verificar/` with empty body. Backend runs challenge + verify internally (current behavior).
- OR (preferred Phase 2A5 path): frontend drives the flow. Browser fetches `challengeIdentity(user_external_id)`, signs the canonical in-browser, posts the result to `POST /api/integration/dp4500/citas/<cita_id>/verificar/` with `{challenge_id, signature, timestamp}`. Backend records the result and writes `CitaMedica.biometric_*`. (Server-side validation stays in DP4500.)

**DP4500 endpoints needed** (already exist from Phase 1+):

- `POST /api/biometric/service/challenge/identity/<uuid>/` — already used by `dp4500-capture-client.challengeIdentity()`.
- `POST /api/biometric/service/verify/identity/` — already used by `dp4500-capture-client.verifyIdentity()`.
- `POST /api/biometric/service/identity/enroll/` — already used by `dp4500-capture-client.enrollIdentity()`.
- `DELETE /api/biometric/service/templates/<uuid>/` — used by cascade Celery task; no change needed.

**Test plan**:

- Backend unit: `_validate_biometric_step` round-trips `externalId`; finalize sets `Cliente.external_id` and `Usuario.biometric_external_id`; cita verify view accepts a signed payload from the browser and records `CitaMedica.biometric_*`.
- Backend e2e (httpx MockTransport impersonating DP4500): enroll → finalize → cita verify with a real signed payload → cita transitions to CONFIRMADA + three biometric fields populated.
- Frontend manual smoke: in dev, run the wizard, then on the cita admin page click "Confirmar por huella" and observe the verify round-trip through `dp4500-capture-client.verifyIdentity()`.

### 4.3 Frontend (`frontend/aesthetic-clinic`)

**Files to touch**:

1. **`frontend/aesthetic-clinic/src/pages/admin/client-detail/BiometricVerifyCaptureModal.tsx`**:
   - Replace `biometricClient.verifyInit(citaId)` (legacy, line 178) with the DP4500 path. The browser must call `challengeIdentity(userExternalId)` from `dp4500-capture-client.ts`, then `verifyIdentity(captureToken, userExternalId, serverNonce)`, then post the result to the new clinic backend endpoint.
   - The `userExternalId` is `cliente.external_id` (the wizard-minted UUID). The current modal does not have it; it must come from `useClientDetail` (the parent) or be fetched when the modal opens.
   - Drop the `score` payload field — DP4500's verify endpoint takes `{challenge_id, signature, timestamp}` only.
2. **`frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts`**:
   - Surface `cliente.external_id` to the modal so it has the UUID without an extra round-trip.
   - Pass `externalId` as a new prop to `BiometricVerifyCaptureModal`.
3. **`frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts`**:
   - Already exposes `challengeIdentity`, `verifyIdentity`. No change needed.
4. **`frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx`**:
   - Read `cliente.external_id` from the client detail response; pass it to the modal.
5. **`frontend/aesthetic-clinic/src/services/api/apiClient.ts`** (or a new helper):
   - Add a `postJsonNoCsrf` helper that POSTs to the new `/api/integration/dp4500/citas/<id>/verificar/` endpoint. The clinic backend endpoint receives the verify result and writes the audit fields.

**Contracts**:

- The browser flow is now: capture → enroll → finalize (server-side, persists UUID) → cita verify (challenge → sign → verify → POST to clinic endpoint with the signed payload).
- The clinic backend's `CitaBiometricVerifyView` switches from "synthesize signature locally + call DP4500" to "receive signed payload + call DP4500 with the same payload" — same wire contract for DP4500, different code path on the clinic side.

**Test plan**:

- Playwright e2e: full wizard (capture → enroll → finalize) → admin cita verify click → `BiometricVerifyCaptureModal` opens → "Activar lector" → `challengeIdentity` + `verifyIdentity` round-trip → server records `CitaMedica.biometric_*` and transitions to CONFIRMADA.
- Vitest unit (if added): mock `dp4500-capture-client` and assert `BiometricVerifyCaptureModal` calls `verifyIdentity` with the correct canonical and posts the result.

---

## 5. Recommendation: edits needed in proposal.md / design.md / tasks.md

The orchestrator should drive these edits in this order (single `apply-blockers → proposal/design/tasks update` PR):

### 5.1 `proposal.md`

1. **§2.2 (User.biometric_external_id)**: Add a sentence describing the Opción A dual-UUID reality: "The wizard's frontend mints the UUID via `crypto.randomUUID()` and persists it in `biometricForm.externalId`. The pre_save signal provides a defensive fallback for users that bypass the wizard (e.g. admin-created accounts). Phase 2A5 reconciles the two paths during finalize."
2. **§2.4 (Sucursal.dp4500_service_key)**: Add a subsection "Frontend key model" describing `VITE_DP4500_SERVICE_API_KEY` (single key per deployment, read at module load in `dp4500-capture-client.ts`). Mark per-sucursal lookup as a deployment-time decision; Phase 2A4 uses single-key, Phase 2A5 documents the per-sucursal path the backend already supports.
3. **§2.1 (new biometric/ app)**: Rename path references from `apps/biometric/` to `dp4500_integration/`. Add a paragraph describing the complementary frontend `dp4500-capture-client.ts` (browser-side enroll/challenge/verify) and the role split (Python client = server-to-server challenge/verify/delete; TS client = browser-to-server enroll/challenge/verify).
4. **§3 (out-of-scope)**: Add a new bullet "Phase 2A5 — Cita verify with Ed25519 in the browser". Note that the Ed25519 + `dp4500-capture-client` machinery exists today; Phase 2A5 is the integration step.
5. **§4 (decisions)**: Update "Key granularity" row to "Configurable: single-key per deployment (Phase 2A4 default) OR per-sucursal via `DP4500_SERVICE_KEY_SUCURSAL_<id>` (production)".

### 5.2 `design.md`

1. **§1.2 components table**: Add a row for `frontend/.../services/biometric/dp4500-capture-client.ts` and `frontend/.../services/biometric/ed25519-key-manager.ts`. Mark the Python `HTTPClient` as "server-to-server (challenge/verify/delete from the clinic backend)"; mark the TS client as "browser-to-server (enroll/challenge/verify from the operator's workstation)".
2. **§2 module layout**: Update to mention the frontend addition. Add a `frontend/aesthetic-clinic/src/services/biometric/` row.
3. **§3 service client design**: Add a §3.6 "Browser client (dp4500-capture-client.ts)" subsection that points to the TS file and lists the surface (`enrollIdentity`, `challengeIdentity`, `verifyIdentity`, `captureAndVerify`).
4. **§4 cita verification view**: Update the sequence diagram to reflect that the signature comes from the browser (not from the backend synthesizing `"phase2-stub"`). The view now accepts `{challenge_id, signature, timestamp}` in the request body and forwards to DP4500. Note the `Cliente.external_id` migration for Phase 2A5.
5. **§5 wizard step 4 view**: Note that the view is a placeholder; the real wizard lives in `useConversionWizard.handleConfirmCapture` (frontend), which mints the UUID client-side and persists it in `biometricForm.externalId`. The Phase 2 Django view is a stub for the back-office admin path; the wizard frontend is the source of truth for the operator UX.
6. **§7.1 (User.biometric_external_id)**: Document the dual-UUID reality. Pre_save provides a defensive UUID; the wizard-minted UUID overrides during finalize.
7. **§7 (data model)**: Add a new §7.6 "Cliente.external_id (Phase 2A5)" with the field definition and migration plan.
8. **§13 ADR-0004 (signature stub)**: Mark as superseded by Phase 2A2/A3. The browser now signs the canonical; the backend view forwards it.
9. **§13 ADR (new)**: Add ADR-0006 "Frontend-minted UUID is the source of truth" documenting the dual-UUID pattern and the rationale.
10. **§15 references**: Add the new files (`dp4500-capture-client.ts`, `ed25519-key-manager.ts`).

### 5.3 `tasks.md`

1. **§"Out-of-scope tasks"**: Add a section "Phase 2A5 (verify de cita con Ed25519)" with the work-unit table for the cita verify browser rewrite + `Cliente.external_id` migration. This is the next change to ship — not a one-line commit; budget 200-400 lines.
2. **§"Pre-apply checklist"**: Drop the items that are now moot (the original Phase 2 checklist is archived). Replace with a Phase 2A5 checklist:
   - `Cliente.external_id` migration applies cleanly.
   - `_validate_biometric_step` round-trips `externalId`.
   - Finalize handler sets `Usuario.biometric_external_id` AND `Cliente.external_id` from `biometricForm.externalId`.
   - `CitaBiometricVerifyView` accepts a signed payload from the browser and forwards to DP4500.
   - `BiometricVerifyCaptureModal.tsx` calls `dp4500-capture-client.verifyIdentity` and posts the result to the new clinic endpoint.
   - Playwright e2e covers enroll → finalize → cita verify with the new path.

### 5.4 Specs (only if the spec wording drifts from reality)

The four specs are mostly aligned with reality. Two minor drifts:

- **`specs/dp4500-service-client/spec.md`**: The spec describes the Python `HTTPClient` only. Add a sentence: "The browser-side counterpart lives at `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` and exposes the same wire contract for the enroll / challenge / verify trio."
- **`specs/wizard-biometric-enrollment/spec.md`**: §"Step 4 advances only with biometric_external_id" assumes the backend signal is the source. Update: "Step 4 advances once the operator confirms a capture. The frontend mints `crypto.randomUUID()` and persists it in `biometricForm.externalId`; the backend's `pre_save` signal provides a defensive UUID for non-wizard users; the finalize handler reconciles the two into `Usuario.biometric_external_id` AND `Cliente.external_id` (Phase 2A5)."

The other two specs (`cita-biometric-verification`, `cascade-biometric-revoke`) match the implementation closely. Only `cita-biometric-verification` needs a small clarification about signature sourcing (browser vs backend stub).

### 5.5 Archive-report

`archive-report.md` is already finalized for Phase 2A4. Do NOT edit it. The Phase 2A5 archive-report will be a separate file when Phase 2A5 ships.

---

## 6. Quick-reference: what changed where

| Concern | Plan | Reality | Disposition |
|---|---|---|---|
| UUID source | Backend pre_save | Frontend `crypto.randomUUID()` + pre_save fallback | Reasign (dual-source, finalize reconciles) |
| Service key | Per-sucursal `DP4500_SERVICE_KEY_SUCURSAL_<id>` | Single `VITE_DP4500_SERVICE_API_KEY` | Reasign (configurable; backend per-sucursal stays; default is single-key) |
| Client surface | Python `HTTPClient` only | Python `HTTPClient` + TS `dp4500-capture-client` | Reasign (both documented) |
| Celery + cascade | Adopt Celery, `@shared_task` | Implemented as designed | Keep |
| `CitaMedica` biometric fields | Three nullable fields | Implemented as designed | Keep |
| `Cliente.external_id` | Implicit on `Usuario` only | `Cliente.external_id` does NOT exist | Reasign (add in Phase 2A5) |
| Cita verify view | Mounted at `/api/biometric/...` | Mounted at `/api/integration/dp4500/...` | Keep (legacy URL stays for fprintd flow) |
| Stub signature | `"phase2-stub"` | Still `"phase2-stub"` in `CitaBiometricVerifyView` | Cancel for Phase 2A5 (use browser-signed canonical) |
| Verify modal | Backend Python via `HTTPClient` | Frontend legacy `biometricClient.verifyInit/Confirm` | Reasign (Phase 2A5 rewrites to `dp4500-capture-client.verifyIdentity`) |
| `Cliente` model UUID | Not in plan | Needed for Opción A | Reasign (add in Phase 2A5) |
| `biometricForm.externalId` typing | Not in plan | Optional `externalId?: string` added | Reasign (validate + persist on finalize) |
| ADR-0004 signature stub | Phase 4 | Wire is ready; Phase 2A5 uses it | Cancel the ADR-0004 claim |

---

## 7. Ready for next phase

**Yes** — the proposal/design/tasks updates listed in §5 are sufficient to drive a new change directory (`dp4500-host-app-integration-phase2a5`) or to amend the existing one in-place. The orchestrator should:

1. Confirm the disposition for each mismatch in §3 with the user.
2. Land the proposal/design/tasks edits per §5 as a docs-only PR.
3. Open a new apply phase for Phase 2A5 (cita verify with Ed25519 + `Cliente.external_id` migration + finalize handler persistence).
4. Hold the original `archive-report.md` as final; the new archive will be a separate file.

**Blocked** if the user wants to keep "per-sucursal" as a hard requirement (Disposition §3.2) — that needs frontend routing changes that are not currently scoped.