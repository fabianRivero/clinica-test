# Design: DigitalPersona 4500 Fingerprint Integration

## 1. Goals and Non-Goals

**Goals.** Replace the string-equality mock (`customers/models.py:227-261`, `config/api_views.py:3580-3650`) with a DP4500 capture path via per-PC `fingerprint-agent` exposed through Cloudflare Tunnel. Encrypt templates at rest with Fernet; server decides match against `BIOMETRIC_MATCH_THRESHOLD`. Reuse existing `CitaMedica` columns. One template per client, cross-sucursal. Per-PC hashed `AgentToken` + 60s heartbeat.

**Non-goals (v1).** Windows/macOS agents, biometric login, multi-finger, quality-based auto re-enrollment, tablet biometrics, analytics dashboards.

## 2. Architecture

```
+--- Admin PC (sucursal) ---+              +---------- DROPLET ----------+
| DP4500 <-> fprintd         |  TLS / CF    | Browser (React)            |
|        \  D-Bus            |  Tunnel      |   |  HTTPS  /api/             |
| fingerprint-agent          |------------->| Django + DRF               |
|  127.0.0.1:8765            |              |  customers/ (extend)       |
|  /capture /match /health   |              |  biometric/  (NEW)         |
|  /heartbeat -> BE          |              |  operations/ verify-*      |
+----------------------------+              |       |  SQL                |
                                            | PostgreSQL / SQLite        |
                                            +---------------------------+
```

## 3. Components

### 3.1 New / changed files

| Path | Action |
|---|---|
| `fingerprint-agent/{server.py, requirements.txt, README.md, Dockerfile, cloudflared-example.yml, config.ini.example, systemd/*.service}` | Create |
| `fingerprint-agent/tests/test_dbus_capture.py` | Create (smoke, skipped in CI) |
| `backend/biometric/{models, services, views, permissions, serializers, urls, management, tests}/` | Create |
| `backend/biometric/services/{encryption, agent_client, threshold}.py` | Create |
| `backend/biometric/management/commands/seed_demo_biometric_template.py` | Create (optional demo helper) |
| `backend/biometric/tests/{test_encryption, test_agent_client, test_agent_token, test_enrollment_flow, test_verification_flow, test_permissions}.py` | Create |
| `backend/customers/migrations/{0010_huellabiometrica_dp4500, 0011_template_binary}.py` | Create |
| `backend/accounts/migrations/0011_add_recepcionista_role.py` | Create (see 16.1) |
| `backend/config/{api_urls, settings}.py` | Modify |
| `frontend/.../services/fingerprint/biometricClient.ts` (+ test) | Create |
| `frontend/.../services/fingerprint/mockFingerprint.ts` | **Delete** |
| `frontend/.../pages/admin/prospect-convert/{ConversionStepBiometric, useConversionWizard}.{tsx,ts}` | Modify |
| `frontend/.../pages/admin/client-detail/{ClientAppointmentSection, useClientDetail, AdminClientDetailPage}.{tsx,ts}` | Modify |

### 3.2 Apps touched
`customers` (extend), `operations` (replace `admin_confirm_appointment_biometric`), `accounts` (add role), `config` (env, URLs), `biometric` (new).

## 4. Data Model

### 4.1 `HuellaBiometricaCliente` extensions

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `cliente` | OneToOne | NO | — | Keep; spec calls it `unique_together(cliente)`. |
| `proveedor` | CharField(20) | NO | `MOCK_LEGACY` | Add `DIGITAL_PERSONA`; rename MOCK/SECU_GEN to `_LEGACY`. |
| `template_biometrico` | BinaryField | NO | — | Was TextField. Legacy rows -> NULL. |
| `template_format` | CharField(20) | NO | `UNKNOWN` | `DP_PROPRIETARY/ANSI_378/ISO_19794_2/UNKNOWN`. |
| `encrypted_template_key_id` | CharField(40) | YES | NULL | |
| `last_match_at` | DateTime | YES | NULL | |
| `last_match_score` | Decimal(5,4) | YES | NULL | |
| existing fields | — | — | — | `device_serial, calidad_captura, consentimiento_aceptado, activo, registrado_por, fecha_registro, updated_at` (TimeStampedModel). |

Constraints: explicit `Meta.unique_together = ("cliente",)`. NO `sucursal_id`, NO `dedo`.

Migration: `0010` adds fields + enum; `0011` backfills legacy rows to `proveedor=_LEGACY`, `activo=False`, `template_biometrico=NULL`.

### 4.2 `BiometricAttempt` (new)

| Field | Type | Notes |
|---|---|---|
| `id` | BigAuto | PK |
| `cita` | FK CitaMedica SET_NULL | NULL for enroll |
| `usuario` | FK Usuario SET_NULL | |
| `cliente` | FK Cliente CASCADE | |
| `operation` | CharField(16) | `ENROLL`/`VERIFY` |
| `success` | Bool | |
| `score` | Decimal(5,4) | Raw for verify, quality/100 for enroll |
| `failure_reason` | CharField(32) | `NO_IMAGE/LOW_QUALITY/BELOW_THRESHOLD/DECRYPT_FAILED/AGENT_OFFLINE` |
| `agent_pc` | FK AgentToken SET_NULL | |
| `created_at` | auto_now_add | Composite index `(cita, created_at)` |

### 4.3 `AgentToken` (new)

| Field | Type | Notes |
|---|---|---|
| `id, name, sucursal(FK PROTECT), token_hash(unique), public_url, is_active, last_seen_at, created_at, created_by(FK SET_NULL)` | standard | `token_hash = sha256(raw_token).hexdigest()`; raw NEVER persisted. |

## 5. Encryption

| Decision | Choice | Why |
|---|---|---|
| Algorithm | `cryptography.fernet.Fernet` (single key) | Spec confirmed one key, no rotation. Simpler. |
| Storage | env `BIOMETRIC_FERNET_KEY` (string) | Single value; DB defeats encryption; Vault overkill. |
| Scope | ONLY `template_biometrico` bytes | Metadata is not biometric. |
| Validation | App fails to start if `BIOMETRIC_FERNET_KEY` missing/invalid | Fail-fast at boot, not at first capture. |
| Failure | `InvalidToken` -> row unusable, UI "re-enroll required" | Fail-closed per spec. |

## 6. Agent Protocol

| Aspect | Spec |
|---|---|
| Bind | `127.0.0.1:8765` ONLY. |
| Public | `cloudflared` -> `https://agent-<id>.clinica.app` (stored in `AgentToken.public_url`). |
| Auth | Per-PC static token in `config.ini` (chmod 600); `Authorization: Bearer <token>` required on `/capture`, `/match`. Backend never sends secrets to agent. |
| Endpoints | `POST /capture` -> `{template_b64, quality_score, device_serial, width, height}`; `POST /match` -> `{score, captured_template_b64}` (RAW score only); `GET /health`; `POST /heartbeat` -> BE updates `last_seen_at`. |
| Capture (Linux) | `SystemBus` -> `find_dp4500` -> `Claim` -> `EnrollStart("any")` -> loop `EnrollStatus` -> `EnrollStop` -> base64 + `image-quality/100`. |
| Match (Linux) | `Claim` -> `VerifyStart("any")` -> wait `VerifyStatus` -> `discovered_print_data.match_score/100`. |
| Wire format | Plaintext over TLS. `cloudflared` = security boundary. Trade-off: avoids distributing Fernet keys to every PC. |

## 7. Backend Endpoints

All under `/api/admin/fingerprint/...` except cliente/cita scoped. Errors: `{detail, code}`. Roles: A=ADMIN_PRINCIPAL, B=ADMIN_SUCURSAL, R=RECEPCIONISTA.

| Method | Path | Body | Response | Codes | Roles |
|---|---|---|---|---|---|
| POST | `/api/clientes/{id}/huella/enroll-init/` | `{consentimiento_aceptado:true}` | `{agent_url, capture_token, agent_token_hint}` | 200,400 `CONSENT_REQUIRED`,401,403,404,503 | A,B |
| POST | `/api/clientes/{id}/huella/enroll-finalize/` | `{capture_token, template_b64, quality_score, device_serial, template_format}` | `{ok, key_id}` | 200,400 `LOW_QUALITY`,401,403,404,409 `ALREADY_ENROLLED` | A,B |
| POST | `/api/citas/{id}/huella/verify-init/` | `{}` | `{agent_url, capture_token, agent_token_hint}` | 200,400 `INVALID_STATE`,400 `NO_FINGERPRINT`,401,403,404,503 | A,B,R |
| POST | `/api/citas/{id}/huella/verify-confirm/` | `{capture_token, score, captured_template_b64, agent_pc_id}` | `{matched, score, threshold_used, appointment}` | 200,400 `INVALID_STATE`,401,403,404,503 | A,B,R |
| POST | `/api/admin/fingerprint/agents/` | `{name, sucursal_id, public_url}` | `{id, name, token, token_hint}` (token ONCE) | 201,401,403 | A |
| GET | `/api/admin/fingerprint/agents/` | — | `{results:[...]}` (no token_hash) | 200,401,403 | A (all), B (own) |
| GET | `/api/admin/fingerprint/agents/{id}/` | — | `{...}` | 200,401,403,404 | A,B (own) |
| POST | `/api/admin/fingerprint/agents/{id}/heartbeat/` | `{agent_token}` | 204 always | 204 | agent |
| DELETE | `/api/admin/fingerprint/agents/{id}/` | — | 204 | 204,401,403,404 | A |

Permissions in `biometric/permissions.py`: `IsAdminPrincipal`, `IsAdminSucursalOrPrincipal`, `IsRecepcionistaOrAbove`, all after `IsAuthenticated`.

## 8. Encryption Envelope

Plaintext over TLS. `cloudflared` is trust boundary; agent holds no Fernet keys. Log scrubber in `settings.py` strips base64 > 256 chars from any record touching `biometric.*` modules (spec: "Application logs scrubbed").

## 9. Sequence Diagrams

Three ASCII diagrams (enrollment, verify happy path, manual fallback) live in the companion doc `openspec/changes/add-digital-persona-4500-integration/sequences.md` (referenced for reviewer convenience; design rationale captured above).

## 10. Frontend

| File | Change |
|---|---|
| `biometricClient.ts` (NEW) | `enrollInit/enrollFinalize/verifyInit/verifyConfirm`; returns `{agent_url, capture_token}`. |
| `mockFingerprint.ts` | DELETE. |
| `ConversionStepBiometric.tsx`, `useConversionWizard.ts` | Replace mock imports; rename button + copy. |
| `ClientAppointmentSection.tsx`, `useClientDetail.ts`, `AdminClientDetailPage.tsx` | Same; add "Enroll fingerprint" CTA when `!has_fingerprint`. |

UX states: idle / capturing / success / fail / offline banner. Agent errors: retry once, then manual fallback. Low quality: prompt retry, not error.

## 11. Permissions Matrix

| Action | A | B | R | W | C |
|---|---|---|---|---|---|
| View has_huella | Y | Y | Y | N | N |
| View ciphertext | Y | N | N | N | N |
| Enroll huella | Y | Y | N | N | N |
| Delete huella | Y | Y | N | N | N |
| Verify cita | Y | Y | Y | N | N |
| Manual confirm | Y | Y | Y | Y (own) | N |
| Create AgentToken | Y | N | N | N | N |
| List AgentTokens | Y all | Y own | N | N | N |
| Delete AgentToken | Y | N | N | N | N |

## 12. Risks

| Risk | Mitigation |
|---|---|
| Tunnel URL public; UUID enumeration | UUID v4 capture_token (122 bits), 5-min TTL; Bearer gate. |
| Agent token stolen from PC disk | Backend has own auth; rotate via DELETE+create. |
| DB template theft | Fernet at rest; key in env. |
| Cross-sucursal privacy | Filter by `cliente_id`; audit ciphertext reads. |
| Tunnel downtime | UI banner; manual path stays. |
| fprintd crash mid-capture | Agent `Release+Claim` reset; UI retry. |
| Quality variance | Tunable threshold; no retry cap. |
| Legacy MOCK strings | Backfill to MOCK_LEGACY + activo=False; re-enroll required. |
| Fernet key leak from env | Env only; if leaked, manually regenerate and re-enroll all clients (no rotation machinery). |
| Agent on shared PC | Bind 127.0.0.1; Bearer required; config.ini chmod 600. |
| Heartbeat false-offline | 5-min threshold; agent retries with backoff. |

## 13. Testing

| Layer | Coverage |
|---|---|
| Unit | Encryption round-trip; token hashing; migrations up/down; permissions; scrubber regex. |
| Integration (SQLite) | Full enroll with mocked agent; full verify (above/below threshold); cross-sucursal; 6 attempts -> 6 rows. |
| E2E / smoke | Real fprintd (skipped in CI); React component test with mocked fetch. |
| Manual QA | cloudflared setup; offline fallback; 5 failed attempts still allows manual; no template strings in logs. |

## 14. Deployment

| Stage | Steps |
|---|---|
| Backend | Set `BIOMETRIC_FERNET_KEY=<key>`, `BIOMETRIC_MATCH_THRESHOLD=0.85`; `migrate` runs 0010/0011 + biometric/0001..0003 (legacy backfill); staff trained on Django admin. |
| Agent (per PC) | Python 3.10+, `pip install -r requirements.txt`, write `/etc/fingerprint-agent/config.ini`, systemd unit, cloudflared systemd unit, `tunnel login` once. |
| Rollout | (1) Deploy backend (compatible with old mock). (2) Agent on pilot PC. (3) Swap `mockFingerprint.ts`. (4) One client MOCK->DIGITAL_PERSONA proof. (5) All PCs in parallel. (6) Deprecate MOCK_LEGACY in admin UI. |

## 15. Future Work

Windows/macOS agent; biometric login; multi-finger; quality auto re-enroll; analytics; `/agents/{id}/rotate/`.

## 16. Open Questions

1. **`RECEPCIONISTA` role missing.** Spec assumes it; current roles are A/B/W/C. **Default: add role in this change.**
2. **Agent URL per sucursal:** prefer same-sucursal, fallback any active. **Default.**
3. **Multiple PCs per sucursal:** UI picks most-recently-seen. **Default.**
4. **Tablet biometrics (Touch ID / Android BiometricPrompt):** keep separate (kiosk path). **Default per cross-domain table.**
5. **Key rotation cadence:** none. Single key, manually replaced if leaked. **Default per design decision.**
6. **Template size:** `BinaryField` = `bytea` (no length cap). **Default.**
7. **`last_seen_at` display:** relative + absolute; admin-only. **Default.**
8. **`SECU_GEN` legacy rows:** same procedure as MOCK. **Default.**

---

## Spec Scenario Cross-Reference

| Requirement | Section |
|---|---|
| Encrypted Template Storage | 4.1, 5, 8 |
| HuellaBiometricaCliente Updates | 4.1, 11 |
| BiometricAttempt Audit Log | 4.2, 7 |
| AgentToken Lifecycle | 4.3, 7 |
| Enrollment Wizard Integration | 6, 7, 10 |
| Verification Flow | 6, 7, 10 |
| Cross-Sucursal Reuse | 4.1, 11, 13 |
| Manual Fallback | 7, 10 |
| Sensitivity Threshold | 5, 7 |
| Agent Registration | 4.3, 7 |
| Heartbeat / Offline | 7, 12 |
| No Retry Limit | 4.2, 13 |
| Permissions | 7, 11 |
| Privacy of Template | 5, 8, 13 |
| Frontend replace mock | 3.1, 10 |