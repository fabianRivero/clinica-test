# Exploration: suspend-fingerprint-integration

## Current State

The fingerprint-reader integration is wired across three layers and is currently **active in production paths**. The user reports an OS-level bug on `libgirepository-1.0 1.80.1` that segfaults fprintd typelib loading on the developer host (see `backend/biometric/services/encryption.py:3-22` and `fingerprint-agent/agent/fprintd_bridge.py`). The user wants every fingerprint-reader-related behavior suspended (not deleted) so it can be re-enabled later.

### Layer 1 — Backend Django app `biometric/`

Self-contained app mounted at `/api/biometric/` via `backend/config/urls.py:16` (`include("biometric.urls")`).

| Module | Path | Role |
|---|---|---|
| `apps.py` | `backend/biometric/apps.py` | `BiometricConfig` registered in `INSTALLED_APPS` (`config/settings.py:71`). |
| `models.py` | `backend/biometric/models.py` | `BiometricAttempt` audit log; `AgentToken` per-PC bearer. `HuellaBiometricaCliente` itself lives in `customers/models.py:227`. |
| `urls.py` | `backend/biometric/urls.py` | Routes for enroll / re-enroll / prospect-enroll / verify-init / verify-confirm / confirm-manual / agents CRUD / heartbeat. |
| `views.py` | `backend/biometric/views.py` | Function-based views; `verify_init` calls `agent_client.release()` then `agent_client.match()` against the per-PC agent (lines 818-823) — **the exact OS-bug surface**. |
| `services/encryption.py` | `backend/biometric/services/encryption.py` | **Already a no-op stub** (Fernet disabled); bytes flow raw. Re-enabling Fernet is separate future work. |
| `services/agent_client.py` | `backend/biometric/services/agent_client.py` | `MockAgentClient` + `HttpAgentClient`. `HttpAgentClient.capture/match/release` are the active fingerprint calls. |
| `services/factory.py` | `backend/biometric/services/factory.py` | Selects the client via `AGENT_CLIENT_CLASS` env var (default `HttpAgentClient`). |
| `services/threshold.py` | `backend/biometric/services/threshold.py` | Server-side match score threshold (`BIOMETRIC_MATCH_THRESHOLD`, default 0.85). |
| `services/capture_tokens.py` | `backend/biometric/services/capture_tokens.py` | In-memory capture-token store. |
| `permissions.py` | `backend/biometric/permissions.py` | Role matrix (`ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, agent-token bearer). |
| `log_filters.py` | `backend/biometric/log_filters.py` | `BiometricLogScrubber` filter attached to root logger in `config/settings.py:227-242`. |
| `serializers.py` | `backend/biometric/serializers.py` | Tiny payload helpers. |
| `tests/` | `backend/biometric/tests/` | 10 test files covering endpoints, agent client, encryption, threshold, capture tokens, permissions, etc. |
| `migrations/` | `backend/biometric/migrations/` | `0001_initial`, `0002_agenttoken_token_encrypted`, `0003_biometricattempt_prospecto`. |

### Layer 2 — Backend cross-cutting coupling

The biometric integration is also wired into shared models, serializers, settings, and existing viewsets — **the suspension must touch these or the UI keeps offering the option**.

| File | Lines | Coupling |
|---|---|---|
| `backend/config/urls.py` | 16 | `path("api/biometric/", include("biometric.urls"))` |
| `backend/config/api_urls.py` | 33-34, 97, 213-214, 250-251, 273-274, 281-285 | Wires the **legacy** `admin_confirm_appointment_biometric` + `admin_mark_appointment_pending_biometric` + `admin_prospect_conversion_biometric_step` views. |
| `backend/config/api/viewsets/operaciones.py` | 515-564, 727-730 | `CitasViewSet.confirmar_biometria` (POST /citas/<id>/confirmar-biometria/, sets `metodo_confirmacion=BIOMETRICO`). `OfflineConfirmationViewSet.resolver_conflicto` also writes `MANUAL` for ACCEPT. |
| `backend/config/api/serializers/operaciones.py` | 41-45 | `AppointmentBiometricConfirmSerializer` (template/quality/deviceSerial). |
| `backend/config/api_views.py` | 81, 115, 394, 399, 463, 471-475, 561, 2174, 2194, 2546-2561, 3438-3466, 3579-3651, 4563-4602, 2174 | `admin_confirm_appointment_biometric` (line 3582), `admin_mark_appointment_pending_biometric` (line 3438), `appointment_biometric_status` (line 471-475 sets `canConfirmBiometric`), dashboard counters, biometric-related logger warnings. |
| `backend/config/client_api_views.py` | 388-417 | `_client_appointment_item` computes `canConfirmBiometric` (line 411), `biometricMockTemplate` (line 413, legacy `MOCK` branch), `verificationStatus`/`verificationMethod`. |
| `backend/config/api/viewsets/clientes.py` | 196 | Hard-coded `"canConfirmBiometric": False` already. |
| `backend/config/api/helpers_operations.py` | 183-200 | `appointment_biometric_status(cita)` returns "Validada" / "Pendiente" / "No aplica". |
| `backend/config/prospect_conversion_views.py` | 34-35, 287-332, 1076-1109, 1322-1494 | `_build_initial_client_biometric_data`, `_blank_biometric_data`, `_validate_biometric_step`, `admin_prospect_conversion_biometric_step`. Migration of `HuellaBiometricaCliente` rows during finalize (lines 1453-1495). |
| `backend/customers/models.py` | 227-328 | `HuellaBiometricaCliente` model + `Proveedor` enum (`MOCK_LEGACY`/`SECU_GEN_LEGACY`/`DIGITAL_PERSONA`). |
| `backend/customers/migrations/0010..0012` | — | Encrypted template key, prospecto FK, legacy backfill. |
| `backend/operations/models.py` | 144-147, 175-182, 200-228, 252-257 | `CitaMedica.MetodoConfirmacion` enum (BIOMETRICO/TABLET/MANUAL), `verif_biometria` flag, `fecha_confirmacion_biometrica`, `clean()` enforces `metodo=BIOMETRICO ⇒ verif_biometria=True` for CONFIRMADA, `save()` auto-stamps `fecha_confirmacion_biometrica`. |
| `backend/config/settings.py` | 71, 109-122, 217-254 | `BIOMETRIC_FERNET_KEY`, `BIOMETRIC_MATCH_THRESHOLD`, `BIOMETRIC_CAPTURE_TOKEN_TTL_SECONDS`, `AGENT_CLIENT_CLASS`, the `biometric_scrubber` log filter. |
| `backend/accounts/management/commands/seed_branch_test_scenarios.py` | 352 | Seeds a `BIOMETRICO` metodo_confirmacion in the demo data. |
| `backend/tests/test_appointment_confirmation_flows.py` | 60+ | Existing flows that exercise BIOMETRICO path. |

### Layer 3 — Frontend React/Vite

| File | Lines | Coupling |
|---|---|---|
| `frontend/aesthetic-clinic/src/services/fingerprint/biometricClient.ts` | 1-221 | The **only** frontend fingerprint client. Methods: `enrollInit`, `prospectoEnrollInit`, `verifyInit`, `verifyConfirm`, `listAgents`, `isAgentOnline`. Posts to `/api/biometric/...`. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/BiometricVerifyCaptureModal.tsx` | 1-405 | Drives the verify flow via `biometricClient.verifyInit + verifyConfirm`. Sets `manual_only=true` fallback. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts` | 22-25, 250-296, 670-680 | `biometricClient.listAgents()` polled every 60s; exposes `hasAnyAgent` + `allAgentsOffline`; `openVerifyBiometric(citaId)` opens the modal. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx` | 17, 131-132, 206-214, 333-341, 446-474 | Renders the offline banner, "Confirmar con huella" button, mounts the verify modal. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepBiometric.tsx` | 1-113 | Step 4 of the prospect-conversion wizard; renders `BiometricCaptureModal`. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/BiometricCaptureModal.tsx` | 1-302 | Drives prospect-time capture (`prospectoEnrollInit`); receives `biometricForm` + `onConfirm` callbacks. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx` | 39-42, 126, 269-276 | Step shell + description copy referencing "huella biometrica". |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` | 181, 201 | Renders the "Confirmar con huella" button based on `appointment.canConfirmBiometric`. |
| `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` | 479 | Reads `appointment.biometricStatus` for display. |
| `frontend/aesthetic-clinic/src/types/common.ts` | 77 | `canConfirmBiometric: boolean` field on appointment type. |
| `frontend/aesthetic-clinic/src/types/admin.ts` | 341-342 | `biometricStatus: string`, `canConfirmBiometric: boolean`. |
| `frontend/aesthetic-clinic/src/types/prospectConversion.ts` | 85 | `provider: 'MOCK_LEGACY' \| 'SECU_GEN_LEGACY' \| 'DIGITAL_PERSONA'`. |

### Layer 4 — Fingerprint agent (separate service)

`fingerprint-agent/` is a per-PC Python service. Currently **not running on the user's dev host** (libgirepository broken); installed via `systemd/fingerprint-agent.service` and exposed through `systemd/cloudflared.service`. The user wants the agent itself left intact (code preserved for future reactivation).

### Key validation invariants (constraints we must preserve)

1. `CitaMedica.clean()` (`operations/models.py:200-228`) refuses to save a CONFIRMADA cita without `metodo_confirmacion`. If we ever force a transition to CONFIRMADA while the biometric endpoint is suspended, the manual fallback path MUST set `metodo_confirmacion=MANUAL`.
2. `CitaMedica.save()` (`operations/models.py:230-265`) auto-stamps `fecha_confirmacion_biometrica` when state has `verif_biometria=True`. While suspended, no transition will set `verif_biometria=True`.
3. `HuellaBiometricaCliente` rows with `proveedor=MOCK_LEGACY` may exist for historical clients. `client_api_views._client_appointment_item` exposes `biometricMockTemplate` only for that legacy enum value. Even if we disable biometric capture, the existing template column must stay readable (or empty) so client detail pages don't 500.
4. Encryption is **already disabled** by design (`encryption.py` no-op). Restoring Fernet is explicitly a separate future item, NOT in scope here.
5. The `biometric_scrubber` log filter is **harmless** even when biometric is suspended (it only redacts `biometric.*` records), but removing it would still be a clean reversal-friendly change.

## Affected Areas

These are the files that need **active change** (NOT deletion — see Recommendation). Listed in execution order:

### Backend — suspend endpoints & gates

- `backend/config/urls.py` — keep `path("api/biometric/", include(...))` mounted (URLs themselves stay), but views must return `manual_only`-style responses.
- `backend/biometric/views.py` — gate every active endpoint behind a single suspend flag. Specifically:
  - `verify_init` (725) → return `{"has_fingerprint": false, "manual_only": true, "code": "BIOMETRIC_SUSPENDED"}`.
  - `verify_confirm` (870) → return `{"matched": false, "code": "BIOMETRIC_SUSPENDED"}` and DO NOT transition the cita.
  - `enroll_init` (127) / `enroll_finalize` (284) / `cliente_reenroll_init` (382) / `prospect_enroll_init` (550) → return `503` with `code="BIOMETRIC_SUSPENDED"` (or 200 with `manual_only=true` so the wizard still advances).
  - `agent_create` / `agent_heartbeat` / `agent_delete` → still accept reads/list, but write operations return `BIOMETRIC_SUSPENDED`.
  - `confirm_manual` (1148) → keep working, that IS the fallback path.
- `backend/biometric/services/factory.py` — short-circuit `get_agent_client()` to a stub that raises `AgentUnavailableError` so accidental calls fail closed without contacting the agent.
- `backend/biometric/services/agent_client.py` — leave code intact; add a `SuspendedAgentClient` placeholder that the factory returns while suspended (preserves importability).
- `backend/config/api/viewsets/operaciones.py` — `confirmar_biometria` action (515-564) → keep as-is for backward compat but have it return `400` with `BIOMETRIC_SUSPENDED`; `actualizar_estado` (468-513) keeps its MANUAL path.
- `backend/config/api_views.py` — `admin_confirm_appointment_biometric` (3582-3650) → 400 BIOMETRIC_SUSPENDED. `admin_mark_appointment_pending_biometric` (3438) → keep working (it's the gate into the pending-verification state).
- `backend/config/api_views.py` — operation-detail payload (line 471-475) and `admin_client_detail` payload (line 463) → set `canConfirmBiometric=false` everywhere. `_client_appointment_item` in `client_api_views.py:411` → `canConfirmBiometric=false`. `biometricMockTemplate` (413-417) → return empty string regardless of `proveedor`.
- `backend/config/prospect_conversion_views.py` — biometric step (`admin_prospect_conversion_biometric_step` line 1322, finalize migration lines 1453-1495) → short-circuit: skip the step, treat `template_biometrico` as empty, never call the agent. Migrate `HuellaBiometricaCliente` rows to `activo=False` (or leave alone — see options below).
- `backend/config/api/helpers_operations.py` — `appointment_biometric_status` (183-200) → still safe; the labels are display-only.
- `backend/config/settings.py` — add `BIOMETRIC_SUSPENDED` env var (default `false`). `get_fingerprint_module()` helper returns `None` when suspended so views can short-circuit.
- `backend/operations/models.py` — **no change**. The existing `CitaMedica` model still has `metodo_confirmacion=BIOMETRICO` for already-confirmed rows. Suspending does NOT require removing the enum value (would be a destructive migration).
- `backend/biometric/migrations/` — **no new migration needed**. We are not removing tables or columns.

### Frontend — hide UI affordances

- `frontend/aesthetic-clinic/src/services/fingerprint/biometricClient.ts` — keep the client (preserve imports, don't break type checks); gate `verifyInit/verifyConfirm/prospectoEnrollInit/enrollInit/listAgents` with a local `BIOMETRIC_SUSPENDED` flag that returns `{has_fingerprint:false, manual_only:true, code:"BIOMETRIC_SUSPENDED"}` without making the request.
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/BiometricVerifyCaptureModal.tsx` — keep file; render a "Funcionalidad temporalmente suspendida" message instead of the capture UI when suspended.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/BiometricCaptureModal.tsx` — same treatment.
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/useClientDetail.ts` — stop the `listAgents()` polling loop and remove the `hasAnyAgent` / `allAgentsOffline` derivation (or set them to `false` permanently).
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/AdminClientDetailPage.tsx` — hide "Lector de huellas sin conexion" banner (line 206-214), hide "Confirmar con huella" button (line 333-342), keep the manual fallback. Show only "Confirmar manualmente".
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientAppointmentSection.tsx` — same: hide `canConfirmBiometric` button (line 181-201).
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepBiometric.tsx` — collapse step 4 to a no-op or remove the capture modal entirely (still render the step shell so the wizard stays 4 steps visually).
- `frontend/aesthetic-clinic/src/pages/admin/AdminOperationDetailPage.tsx` — keep displaying `biometricStatus` for historic citas; the value is purely descriptive.

### Out of scope (no change)

- `fingerprint-agent/` — code preserved, never deleted. systemd unit can stay installed; we just don't run it.
- `backend/customers/models.py` — `HuellaBiometricaCliente` model preserved. Existing rows (including MOCK_LEGACY) stay.
- `backend/biometric/services/encryption.py` — stays as the no-op stub.
- Migrations — no schema change.

## Approaches

### 1. Single-feature-flag gate (Recommended)

Add one boolean setting `BIOMETRIC_SUSPENDED` (default `false`). Every entry point checks it as the first thing and short-circuits with the appropriate "manual_only / BIOMETRIC_SUSPENDED" response.

- Pros:
  - Single switch to flip back ON when the OS bug is fixed.
  - Reversible: revert the env var, deploy, done. No code deletion required.
  - Preserves `HuellaBiometricaCliente` rows and `BiometricAttempt` audit log (which is required for retroactive forensics if a cita was already CONFIRMADA via BIOMETRICO).
  - Code stays grep-able: any future contributor can search `BIOMETRIC_SUSPENDED` to find every disabled surface.
  - Lowest review footprint: most changes are 3-line guards.
- Cons:
  - The disabled endpoints still respond to HTTP requests (operationally harmless but visible in API docs).
  - Two code paths to maintain if/when biometric is re-enabled.
- Effort: **Low**

### 2. Hide the entire `biometric/` URL prefix

`backend/config/urls.py` removes `path("api/biometric/", include("biometric.urls"))`. Frontend stops calling. Frontend hides all biometric UI.

- Pros:
  - Smaller diff: one URL change + UI hide.
- Cons:
  - Doesn't stop the legacy `/api/admin/citas/<id>/confirmar-biometria/` endpoint (it lives outside `biometric/`).
  - Frontend `BiometricVerifyCaptureModal` would still be mounted; if a stale tab fires a `verify-init` it'd 404 instead of getting a friendly "manual_only" response.
  - Audit-log table writes still happen from other paths if any are left reachable.
  - Reversing requires re-adding the include line + frontend wiring.
- Effort: **Low–Medium**

### 3. Per-endpoint removal (destructive)

Delete `biometric/views.py`, remove the URL include, drop migrations, delete `HuellaBiometricaCliente` rows, etc.

- Pros:
  - Cleanest surface (smallest code surface).
- Cons:
  - **VIOLATES the user's explicit constraint** ("they do NOT want existing fingerprint code deleted, want it preserved for future reactivation").
  - Destructive schema migration on production data with foreign keys from `BiometricAttempt`.
  - Reversing requires redoing work; high risk of losing the audit log.
- Effort: **High** + permanently destructive.

## Recommendation

**Approach 1 — single feature flag** (`BIOMETRIC_SUSPENDED=true`).

Concretely:

1. **Backend settings** (`backend/config/settings.py`): add `BIOMETRIC_SUSPENDED = env_bool("BIOMETRIC_SUSPENDED", False)`. Expose a module-level accessor `is_fingerprint_suspended()` imported from a new tiny `backend/biometric/feature_flag.py`.
2. **Backend views** (`backend/biometric/views.py`): wrap every active endpoint in a one-line guard that returns a manual-only response when suspended. Keep `confirm_manual` (the fallback path) untouched. Mark each view's docstring with a "SUSPENDED-MODE" note.
3. **Backend factory** (`backend/biometric/services/factory.py`): when suspended, return a `SuspendedAgentClient` whose `capture/match/release` raise `AgentUnavailableError("BIOMETRIC_SUSPENDED")`. Never touch `fprintd`.
4. **Backend legacy views**: `admin_confirm_appointment_biometric` (`config/api_views.py:3582`) and `CitasViewSet.confirmar_biometria` (`config/api/viewsets/operaciones.py:515`) return `400 BIOMETRIC_SUSPENDED`. `admin_mark_appointment_pending_biometric` and `admin_prospect_conversion_biometric_step` short-circuit the biometric portion but keep the surrounding state-transition endpoints working.
5. **Backend payload gating**: `canConfirmBiometric=false` returned from both `api_views._operation_detail` (line 472) and `client_api_views._client_appointment_item` (line 411). `biometricMockTemplate` always returns `""` regardless of `proveedor`.
6. **Frontend client** (`biometricClient.ts`): keep all methods; short-circuit with `manual_only=true` when a `BIOMETRIC_SUSPENDED` flag (read from a build-time env var `VITE_BIOMETRIC_SUSPENDED`) is set.
7. **Frontend UI**: hide the "Confirmar con huella" button, the offline banner, and the prospect-step-4 capture modal. Keep the step 4 shell so the wizard stays at 4 steps but with a "Funcionalidad temporalmente suspendida" notice.
8. **Tests**: add a regression test in `backend/biometric/tests/test_endpoints.py` that every endpoint returns the suspended payload when `BIOMETRIC_SUSPENDED=true`. Existing tests pass when the flag is `false`.
9. **Deployment**: flip the env var in `.env`/production config. Roll back by setting it back to `false`.

### Normal workflow while suspended

- New citas can still be PROGRAMADA → REALIZADA_PENDIENTE_VERIFICACION (manual).
- REALIZADA_PENDIENTE_VERIFICACION → CONFIRMADA goes through the existing manual fallback (`/api/admin/citas/<id>/actualizar/` with `status=CONFIRMADA` writes `metodo_confirmacion=MANUAL`, `verif_biometria=False`).
- The `verify_init` returns `manual_only=true` so any stale UI keeps working and shows the manual path.
- `BiometricAttempt` writes stop (no enroll or verify reaches the agent). The audit log preserves all prior attempts.
- Existing `HuellaBiometricaCliente` rows stay; new rows cannot be created while suspended. Re-enabling reopens the path.

## Risks

1. **Hidden stale-UI calls**: a browser tab opened before the deploy may have the `BiometricVerifyCaptureModal` mounted; the modal needs the `BIOMETRIC_SUSPENDED` guard or it will POST to `verify_init` and get a 200 `manual_only` payload (acceptable) but the loading spinner will run for a frame.
2. **CitaMedica clean() constraint**: if any existing code path force-transitions to `CONFIRMADA` with `metodo=BIOMETRICO` while suspended, Django's full_clean will reject it. Audit shows the only path that writes BIOMETRICO today is `verify_confirm` and `admin_confirm_appointment_biometric`, both of which we suspend — so the risk is bounded, but the test must cover `admin_update_appointment_status` to confirm it writes MANUAL.
3. **`appointment_biometric_status` for historical data**: existing citas with `metodo_confirmacion=BIOMETRICO` will still display "Validada" — that's correct historical truth. No risk, but worth a frontend comment.
4. **Agent not stopped at OS level**: the fingerprint-agent systemd unit may still be running on admin PCs. Leaving it running is harmless (no one calls it), but stopping it via `systemctl disable --now fingerprint-agent` and `cloudflared` on each host is recommended operational hardening.
5. **Encryption no-op stub**: `backend/biometric/services/encryption.py` is **already a no-op** by design. If we mistakenly "fix" it while re-enabling the agent later, we'll re-introduce the Fernet round-trip on stale ciphertext. Document this in the archive step.
6. **Frontend type narrowing**: `frontend/aesthetic-clinic/src/types/common.ts:77` declares `canConfirmBiometric: boolean`. Hard-coding `false` everywhere is fine but a frontend test should assert no UI surface still offers the button.
7. **Review budget**: this change touches ~12 backend files + ~6 frontend files but most edits are <10 lines. The combined diff likely fits under the 400-line review budget as a single PR; if not, split into PR-A (backend gates) and PR-B (frontend UI hide) along the existing module boundaries.

## Ready for Proposal

**Yes.** The exploration surfaces are well understood, no schema changes are required, and a single env-var feature flag cleanly satisfies the "suspend without delete" constraint. The orchestrator should advance to `sdd-propose` with the recommendation above; the proposal should explicitly call out the env-var flag, the legacy-endpoint coverage, and the rollback strategy (flip the flag).

## Cross-Domain Effects

| Domain | Effect |
|---|---|
| `appointment-states` | Unchanged at the model level. `CONFIRMADA` still reachable via MANUAL fallback (`admin_update_appointment_status`). The `CitaMedica.MetodoConfirmacion.BIOMETRICO` enum value remains valid for historical rows. |
| `auth-me` | Unchanged. |
| `customers` | Unchanged. `HuellaBiometricaCliente` model preserved; no migration. |
| `operations` | Unchanged at the model level; no migration to `CitaMedica`. The `verif_biometria` flag stays in the schema. |
| `notifications` | Unchanged. |
| `billing` | Unchanged. |
| `clinical` | Unchanged. |
| `biometric` | Domain is preserved; only the entry-point behaviour changes. The existing canonical spec (`openspec/specs/biometric/spec.md`) stays valid — the requirements describe the **active** behaviour, and we are adding a runtime gate rather than rewriting the requirements. A separate delta spec under this change should describe the suspended-mode behaviour (added by `sdd-spec`). |
