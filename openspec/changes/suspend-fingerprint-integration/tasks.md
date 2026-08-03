# Tasks: Suspend Fingerprint Integration

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 650–900 additions/deletions across ~22 backend/frontend/config/test surfaces |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 foundation/contracts → PR 2 backend gates and conversion → PR 3 frontend/rollout and remaining tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Central flag/contracts and no-contact agent | PR 1 | Independent foundation; include factory/client tests and no schema changes |
| 2 | Backend endpoint, payload, and conversion gates | PR 2 | Depends on PR 1; include canonical/legacy and prospect/reactivation tests |
| 3 | Frontend suppression and operational rollout | PR 3 | Depends on PR 2; include Playwright zero-request coverage and rollback docs |

## Phase 1: Foundation and Contracts

- [x] 1.1 Add `BIOMETRIC_SUSPENDED` via `env_bool` in `backend/config/settings.py`, example deployment value in `backend/.env.example`, and shared response builders/contracts in `backend/biometric/serializers.py`; preserve all models, enums, routes, and data.
- [x] 1.2 Add `SuspendedAgentClient` and factory short-circuit in `backend/biometric/services/agent_client.py` and `factory.py`; ensure capture/match/release raise `AgentUnavailableError("BIOMETRIC_SUSPENDED")` without imports, token decryption, URL resolution, or sockets.
- [x] 1.3 Add deterministic foundation tests in `backend/biometric/tests/test_agent_client.py` (suspended client + factory short-circuit) and a new `backend/biometric/tests/test_suspension_foundation.py` (shared response-builder contracts); prove no network/importlib/httpx traffic and that flag-off returns the active `HttpAgentClient`/`MockAgentClient` per existing selection rules. Endpoint-level gated behavior (HTTP 503 schemas, auth-before-gate, canonical/legacy routes) is explicitly deferred to task 2.5.

## Phase 2: Backend Gates and Conversion

- [ ] 2.1 Gate canonical enrollment, re-enrollment, finalize, verification init/confirm, and prospect enrollment in `backend/biometric/views.py` after auth/permissions but before validation, tokens, agent contact, or writes; return family-specific HTTP 503 contracts.
- [ ] 2.2 Gate both legacy routes in `backend/config/api_views.py` (slash function) and `backend/config/api/viewsets/operaciones.py` (DRF no-slash action), preserving URL precedence and auth-before-gate semantics.
- [ ] 2.3 Gate agent create/heartbeat/delete while retaining authorized list/history reads; force `last_seen_at` and activity unchanged, and suppress `canConfirmBiometric` plus template fields in `api_views._operation_detail` and `client_api_views._appointment_item`.
- [ ] 2.4 Split conversion behavior in `backend/config/prospect_conversion_views.py`: new prospects use blank biometric data and skip capture/attempt migration; existing-client reactivation redacts templates, leaves `datos_biometria` byte-for-byte unchanged, and skips biometric upsert.
- [ ] 2.5 Add backend regression coverage for auth-before-gate, canonical and both legacy routes, unchanged heartbeat timestamps, historical template redaction, new prospect versus reactivation, manual confirmation (`MANUAL`, `false`) versus unaffected tablet (`TABLET`, `false`), and **proof that `agent_client.release()` is unreachable while suspended (so views cannot accidentally 500 by calling `release` on the suspended client)** in existing biometric, prospect, conversion, and appointment test modules.

## Phase 3: Frontend and Rollout

- [ ] 3.1 Add typed `VITE_BIOMETRIC_SUSPENDED` handling in `frontend/aesthetic-clinic/src/services/fingerprint/biometricClient.ts` and client-detail components/hooks; hide biometric controls, polling, modals, warnings, and calls while retaining manual confirmation.
- [ ] 3.2 Update prospect conversion components/hooks (`ConversionStepBiometric.tsx`, `BiometricCaptureModal.tsx`, `useConversionWizard.ts`, `AdminProspectConvertPage.tsx`) to complete new-prospect flow without biometric requests and keep reactivation semantics distinct.
- [ ] 3.3 Inject the frontend flag in `backend/build.sh`, document backend/frontend values and systemd disable/restore commands in `scripts/deploy.sh.example` and `frontend/aesthetic-clinic/.env`; preserve units/files and provide flag-off rollback.
- [ ] 3.4 Add Playwright coverage in `frontend/aesthetic-clinic/tests/e2e/biometric_verification.spec.ts` and `biometric_enrollment.spec.ts` proving zero biometric/agent requests, hidden UI, manual/conversion usability, and flag-off rollback eligibility.

## Phase 4: Verification

- [ ] 4.1 Run targeted Django tests, frontend typecheck/lint, and Playwright specs; confirm no migration/deletion and verify every requirement scenario, including zero network calls and unchanged historical state.
- [ ] 4.2 Record deployment validation: backend flag first, frontend rebuild second, `systemctl disable --now fingerprint-agent cloudflared`, then reverse both services and run the flag-off matrix.
