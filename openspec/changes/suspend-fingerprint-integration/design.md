# Design: Suspend Fingerprint Integration

## Technical Approach

Add Django `BIOMETRIC_SUSPENDED` via `env_bool` and Vite `VITE_BIOMETRIC_SUSPENDED`. Every mutating handler performs its existing authentication/authorization first, then a shared gate before validation, capture-token creation, agent lookup/contact, or writes. Preserve routes, schemas, drafts, fingerprints, attempts, and history. Administrative fallback is `MANUAL`; existing tablet confirmation is an unaffected non-biometric `TABLET` transition.

## Architecture Decisions

| Decision | Rejected | Rationale |
|---|---|---|
| Backend gate plus build-time UI suppression | Frontend-only/removing routes | Stale clients fail closed; rollback preserves contracts. |
| HTTP 503 with family adapters | One universal body | 503 expresses temporary unavailability while schemas remain semantically correct. |
| Authorized agent list/history remain readable | Block all reads | Status metadata is administrative; templates remain secret. |
| Separate prospect and reactivation bypasses | Empty fingerprint upsert | Existing records/drafts must never be erased or overwritten. |

## Routes and Data Flow

| Family | Concrete route/symbol | Suspended behavior |
|---|---|---|
| Canonical enrollment | POST `/api/biometric/clientes/{id}/huella/enroll/`, `reenroll/`, `enroll/finalize/`; POST `/prospectos/{id}/huella/enroll/` in `biometric.views` | 503 enrollment body; no token, agent, fingerprint, attempt, or draft write. |
| Canonical verification | POST `/api/biometric/citas/{id}/huella/verify-init/`, `verify-confirm/` | 503 verification body; no match/attempt/transition. `/confirm-manual/` remains active and writes `MANUAL`, `false`. |
| Agent lifecycle | GET/POST `/api/biometric/agents/`; POST `/{id}/heartbeat/`; DELETE `/{id}/` | GET remains scoped; POST/heartbeat/DELETE return agent error, preserving rows and `last_seen_at`. |
| Legacy function | POST `/api/admin/citas/{id}/confirmar-biometria/` → `api_views.admin_confirm_appointment_biometric` | 503 before template lookup/write. |
| Legacy DRF action | POST `/api/admin/citas/{id}/confirmar-biometria` → `CitasViewSet.confirmar_biometria` | 503 DRF response before serializer/write. |
| Payload-only | `api_views._operation_detail`, `client_api_views._appointment_item` | Not routes: force `canConfirmBiometric=false` and template field empty; retain descriptive status. |

`api_urls.py` declares the slash route before `path("citas/", include(...))`; therefore `/confirmar-biometria/` resolves to the function, while the router's no-trailing-slash URL resolves to DRF. Both are active and tested.

```text
request -> auth/permission -> suspension adapter -> 503
                                      X agent/token/DB/state
manual update -> CONFIRMADA + MANUAL + false
```

## Interfaces / Contracts

`biometric.serializers` provides data builders; thin adapters emit `json_response` for function views and DRF `Response` for the ViewSet, always HTTP 503 and `code="BIOMETRIC_SUSPENDED"`.

| Family | Body |
|---|---|
| Enrollment/conversion mutation | `{detail, code, enrollment_available:false}` |
| Verification/legacy confirmation | `{detail, code, manual_only:true, matched:false}` |
| Agent mutation/heartbeat | `{detail, code}` |

Unauthorized requests retain 401/403 and disclose no suspension/data. `SuspendedAgentClient.capture()` and `.match()` deterministically raise `AgentUnavailableError("BIOMETRIC_SUSPENDED")`; `.release()` raises the same exception (unlike active client's best-effort release). None imports `httpx`, decrypts tokens, resolves URLs, or opens sockets. The factory returns it before dynamic class loading.

## Conversion and Data Preservation

For a **new prospect**, suspended initialization/serialization uses `_blank_biometric_data()` with empty template; step 4 marks the draft complete without capture, and finalize skips prospect fingerprint/attempt migration and fallback creation. Existing draft/history rows remain untouched.

For **existing-client reactivation**, `_build_initial_client_biometric_data()` must never read/base64 `template_biometrico` while suspended; serialize only descriptive metadata with `template:""`. Step 4 completes without replacing `datos_biometria`; finalize skips `HuellaBiometricaCliente.update_or_create`. Historical fingerprint and draft data remain byte-for-byte unchanged and unexposed.

## Concrete File Changes

| Files | Change |
|---|---|
| `backend/config/settings.py`, `backend/.env.example` | Backend flag. |
| `backend/biometric/views.py`, `serializers.py`, `services/{agent_client,factory}.py` | Gates, adapters/builders, suspended protocol. |
| `backend/config/api_views.py`, `client_api_views.py`, `api/viewsets/operaciones.py` | Both legacy gates and payload affordances. |
| `backend/config/prospect_conversion_views.py` | Safe prospect/reactivation initialization, serialization, step, finalize. |
| `frontend/aesthetic-clinic/src/services/fingerprint/biometricClient.ts`, client-detail and prospect-convert components/hooks | Typed flag; no controls, polling, modals, or capture calls; manual notice. |
| `frontend/aesthetic-clinic/.env`, `backend/build.sh`, `scripts/deploy.sh.example` | Concrete build injection: export/set `VITE_BIOMETRIC_SUSPENDED=true` before existing `npm run build`; document deploy value. No mechanism currently exists. |
| Existing Django biometric/appointment/prospect tests and two biometric Playwright specs | Matrix below. |

## Deterministic Test Matrix

| Scenario | Proof (also repeat flag=false for family rollback) |
|---|---|
| Canonical enroll/re-enroll/finalize/prospect-enroll | 503 schema; zero token/agent/row/attempt writes. |
| Canonical verify-init/confirm | 503 verification schema; unchanged appointment/history. |
| Function legacy slash + DRF legacy no-slash | Correct resolver/symbol, 503, unchanged state/event. |
| Unauthorized canonical/legacy/agent | Existing 401/403 precedes gate. |
| Agent create/heartbeat/delete + list | Mutations 503; row/activity/`last_seen_at` unchanged; authorized list metadata readable. |
| Historical payload/reactivation | Status retained; templates omitted; fingerprint/draft unchanged. |
| New prospect conversion | Completes without fingerprint/attempt creation. |
| Manual/tablet | Admin manual writes `MANUAL`; tablet still writes `TABLET`; both `false`. |
| Frontend build flag | Playwright counters prove zero biometric/agent requests, hidden warnings/modals, usable manual/conversion paths. |
| Suspended client/factory | Exact exceptions and mocks prove zero network/class loading. |

## Migration / Rollout

No database migration. Deploy backend flag first, then frontend built with the Vite flag. On reader hosts run `systemctl disable --now fingerprint-agent cloudflared`, retaining units/files/config/logs. Rollback flags, rebuild/deploy, then `systemctl enable --now` both services and run flag-off matrix.

## Open Questions

None.
