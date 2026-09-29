# Exploration: dp4500-host-app-integration-phase4-production-readiness

**Prepared**: 2026-09-28
**Branch under review**: `feat/dp4500-host-app-integration-phase2-sdd` at `4ff5ca7` (clean working tree)
**Companion archive**: all earlier phases archived:

| Phase | Where | Commit |
|---|---|---|
| 1 (DP4500 estandar) | `DP4500 estandar/openspec/changes/archive/2026-09-13-dp4500-biometric-auth/` | merged 2026-09-13 |
| 2A4 / 2A5 | `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` | archived at `71f518b` |
| 2A6 (cascade revoke) | `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a6-cascade-revoke/` | archived |
| 2A7 (cascade e2e) | `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2a7-cascade-e2e/` | archived |
| 3 (capture client) | `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/` | `787ddde` + `549a622` + `52c209f` |
| 3.1 (quality handshake) | direct commit on the same branch | `4ff5ca7` (HEAD, no SDD cycle) |

**Purpose**: Define the scope of Phase 4 — the **production-readiness** phase of the dp4500-host-app-integration SDD cycle. Phase 4 covers the security, ops, and compliance work that all earlier phases explicitly deferred as "Phase 4 work". Per the user's session-2026-09-27 decision: **all six deliverables ship in ONE SDD cycle** (not split into Phase 4a/4b/4c).

This file is read-only for the orchestrator. It does NOT modify the SDD artifacts (other than being the artifact itself).

---

## 1. Goal

Phase 4 = **production-readiness for the full dp4500-host-app-integration cycle**. The system can capture, enroll, verify, revoke, and cascade-revoke biometric templates end-to-end (Phases 1-3.1); it is not yet *production-grade*. Phase 4 closes six specific gaps that block flipping `BIOMETRIC_AUTH_ENABLED=true` in a real environment:

1. **KMS-backed envelope** for `BiometricTemplate.encrypted_fmd` (the Knox-flow path already wires the KMS adapter at `finalize_enrollment.py:115-128`; the service-flow path still writes placeholder bytes at `enroll_service_identity.py:120-123`).
2. **ServiceAPIKey rotation** (the `rotated_from` self-FK column is in place at `apps/accounts/models.py:200-206`; the rotation endpoint and cron are not).
3. **mTLS** between the operator's workstation (browser or `fingerprint-agent`) and DP4500's `/api/biometric/service/*` endpoints (no TLS client-cert validation exists yet in `apps/biometric/api/views/service/`).
4. **DPIA update** to cover the Phase 2 cross-system identity handle (`Cliente.external_id` / `User.biometric_external_id`), the Phase 3 DigitalPersona Web SDK capture surface, and the Phase 4 vault/KMS/mTLS hardening — and sign it.
5. **Vault for `ServiceAPIKey` rotation secrets** (replace the `env_key_resolver` Phase 2 backend with a vault-backed resolver; the Phase 2 design already documents the plugin interface at `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:279-281`).
6. **`fingerprint-agent` fallback** for the workstation capture path — Phase 3 wired the browser Web SDK directly; the Q1 decision locked `fingerprint-agent` as the Phase 4 fallback if the SDK-direct path proves unworkable on an operator's real workstation (per `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172`).

The Phase 2 archive's proposal (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/proposal.md:281`) already enumerates the Phase 4 deferrals; the Phase 3 explore (§8) inherits them. Phase 4 does not re-litigate that list — it ships it.

---

## 2. What's already implemented (in earlier phases — DO NOT regress)

### 2.1 Cross-system identity (Phase 2A4 / 2A5 / 2A6 / 2A7)

| Surface | Where | Status |
|---|---|---|
| `User.biometric_external_id` (UUID, unique, indexed) | `backend/apps/users/models.py` (clinic side) — Phase 2A4 | ✅ |
| `Cliente.external_id` cross-system handle | Phase 2A4 | ✅ |
| `CitaMedica.{biometric_challenge_id, biometric_match_confidence, biometric_verified_at}` | `apps/citas/models.py` (clinic side) — Phase 2A4 | ✅ |
| `Sucursal.dp4500_service_key_id` (CharField, NOT FK — per ADR-0001) | `apps/catalogs/models.py` (clinic side) — Phase 2A4 | ✅ |
| `PendingCascade` model + cascade signal handler + Celery task | `apps/biometric/{models,signals,tasks}.py` (clinic side) — Phase 2A4 | ✅ |
| `cascade_revoke_template` Celery task (`max_retries=5, default_retry_delay=30s`) + `on_failure` hook | `apps/biometric/tasks.py` (clinic side) — Phase 2A4 | ✅ |
| `reconcile_pending_cascades` management command | `apps/biometric/management/commands/` (clinic side) — Phase 2A4 | ✅ |
| Wire contract: `POST /service/{identity/enroll,challenge/identity/<uuid>,verify/identity,templates/<external_id>}/` | `DP4500 estandar/backend/apps/biometric/api/views/` (DP4500 side) — Phase 1 | ✅ |
| Ed25519 signature verify on the wire (real, not stub) | `consume_service_identity_challenge.py` — Phase 2A5 server commit `de64ad4` | ✅ |
| URL-safe base64 server_nonce wire-contract fix | Phase 2A5 (`75a481a`) | ✅ |
| `RevokeExternalCredential` use case emitting `service.cascade_revoke` audit events per affected template | `DP4500 estandar/backend/apps/biometric/application/use_cases/revoke_external_credential.py:52-64` — Phase 1 / Phase 2A6 wire-up | ✅ |

### 2.2 Capture client (Phase 3 + 3.1)

| Surface | Where | Status |
|---|---|---|
| Vendored `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `frontend/aesthetic-clinic/node_modules` (5-10 MB) | Phase 3 WU-3.1 | ✅ |
| `captureFingerprint()` wrapper in `dp4500-capture-client.ts` with dynamic `<script>` injection + 30s timeout | `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts:333-549` — Phase 3 | ✅ |
| Two-event handshake: `onSamplesAcquired` + `onQualityReported` resolved together | `dp4500-capture-client.ts:466-532` — Phase 3.1 | ✅ |
| NO_AGENT fallback (Phase 2A4 placeholder contract preserved verbatim) | `useConversionWizard.ts:842-859` — Phase 3 carve-out | ✅ |
| `BiometricHardwareError`, `BiometricQualityTooLow` typed errors | `dp4500-capture-client.ts:279-304` | ✅ |
| 10 Vitest unit tests for the wrapper | Phase 3 | ✅ |
| Operator workstation validation guide | `HOW_TO_RUN.md` — Phase 3.1 | ✅ |

### 2.3 KMS envelope for the Knox flow (Phase 1, already live)

| Surface | Where | Status |
|---|---|---|
| `AwsKmsAdapter` (`boto3`-based, KEK never in Django memory) | `DP4500 estandar/backend/apps/biometric/infrastructure/kms/aws_kms_adapter.py` — Phase 1 | ✅ |
| `FakeKmsAdapter` (test-only, in-process KEK) | `apps/biometric/infrastructure/kms/fake_kms_adapter.py:20-52` — Phase 1 | ✅ |
| `LocalStackKmsAdapter` (LocalStack-backed e2e) | `apps/biometric/infrastructure/kms/localstack_kms_adapter.py:26-27` — Phase 1 | ✅ |
| `VaultKmsAdapter` (stub-only, gated by `BIOMETRIC_KMS_BACKEND=vault`) | `apps/biometric/infrastructure/kms/vault_adapter.py` — Phase 1 | ⚠ stub only — Phase 4 must implement |
| `DekCache` (LRU(maxsize=256, ttl=300s) keyed on `(key_version, template_id)`) | `apps/biometric/infrastructure/kms/dek_cache.py:23-66` — Phase 1 | ✅ |
| `kms_factory.get_kms()` selecting adapter from `BIOMETRIC_KMS_BACKEND` | `apps/biometric/infrastructure/kms/kms_factory.py:32-70` — Phase 1 | ✅ |
| `key_version` per `BiometricTemplate` row + `uniq_nonce_per_key_version` defense-in-depth constraint | `apps/biometric/infrastructure/persistence/models.py:115, 130-131` — Phase 1 | ✅ |
| `migrate_biometric_key_version` management command (idempotent) | `apps/biometric/management/commands/migrate_biometric_key_version.py` — Phase 1 | ✅ |
| `docs/runbooks/kms-rotation.md` | DP4500 estandar repo — Phase 1 | ✅ |
| Knox flow uses the real KMS envelope (call to `kms.wrap_dek` at `finalize_enrollment.py:118-128`) | Phase 1 | ✅ |

### 2.4 `ServiceAPIKey` rotation schema (column exists, endpoint does not)

| Surface | Where | Status |
|---|---|---|
| `ServiceAPIKey` model with `name, key_hash, created_at, last_used_at, is_active, rotated_from` | `DP4500 estandar/backend/apps/accounts/models.py:168-227` — Phase 1 | ✅ |
| `rotated_from` self-FK column for the rotation audit trail | `models.py:200-206` — Phase 1 | ✅ |
| `create_service_api_key` management command with `--rotated-from` flag | `apps/accounts/management/commands/create_service_api_key.py:32-111` — Phase 1 | ✅ (mint-only; no endpoint) |
| `hash_token(raw)` SHA-256 hex digest | `models.py:208-213` — Phase 1 | ✅ |
| `POST /api/biometric/service/keys/<id>/rotate/` endpoint | (does not exist) | ❌ Phase 4 |
| Celery rotation cron (`migrate_service_api_keys` management command + `celery_beat`) | (does not exist) | ❌ Phase 4 |

### 2.5 Out of scope for Phase 4 (explicit deferrals inherited)

- Real hardware physical install on the operator PC (HID Authentication Device Client bootstrap).
- Ongoing DPIA renewal cadence (covered by §6 of `DPIA.md` after Phase 4 ships).
- Cron infrastructure outside the test environment (production cron daemon, systemd unit, k8s CronJob) — Phase 4 ships the management command and Celery wiring only.
- Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing (per Phase 2A4 `explore-reconciliation.md` §3.2 Disposition: "Reasign") — out of scope for Phase 4.
- Cita verify path browser-signed canonical integration polish (already shipped in Phase 2A5).
- Cron-driven `reconcile_pending_cascades` automation (the management command exists; the cron schedule does not — out of scope).

---

## 3. Q1 — Scope decision: all 6 deliverables in ONE SDD cycle

### 3.1 The decision

Per the user's session-2026-09-27 note (Engram observation #53, "Session checkpoint — Phase 4 deferred to next session"): Phase 4 ships **all six deliverables in one SDD cycle**. The change folder is named `dp4500-host-app-integration-phase4-production-readiness` to make this explicit.

### 3.2 Why one cycle (not split into 4a/4b/4c)

- **Each deliverable has a different domain owner** (KMS → platform/security; mTLS → infra; DPIA → legal/privacy; vault → platform; `ServiceAPIKey` rotation → backend; `fingerprint-agent` → frontend). Splitting would force cross-team sequencing on unrelated deliverables.
- **The verify gate is end-to-end**: the DPIA sign-off blocks production rollout regardless of whether the code merges, so splitting code-only cycles from the DPIA cycle creates artificial gates. One cycle keeps the gate at the end.
- **The branch already carries 18+ commits ahead of main**; another 6 commits land cleanly under the existing `feat/dp4500-host-app-integration-phase2-sdd` lineage.

### 3.3 What this means for the proposal

- The proposal's §Scope MUST list all six deliverables as in-scope and MUST explicitly tag the DPIA sign-off chain as the **production-block gate** (not the code-merge gate).
- The tasks.md MUST mark the DPIA WU as the **last** WU in the cycle, with `verify-report.md` documenting the signed DPIA attachment.
- The verify gate is "all six WUs merged + DPIA signed", not "code-green". A merged cycle without a signed DPIA is **not production-ready** even if all code merges.

---

## 4. Open work for Phase 4 (the 6 deliverables)

### 4.1 Deliverable 1 — KMS-backed envelope for the service-flow path

**Problem.** `enroll_service_identity.py:114-123` writes the service-flow rows with placeholder bytes:
```python
placeholder_nonce = secrets.token_bytes(12)   # 12 random bytes
placeholder_tag = b"\x00" * 16                # 16 zero bytes
placeholder_dek = b"\x00" * 32                # 32 zero bytes
```
These rows pass the `NOT NULL` constraints on `BiometricTemplate.{server_aead_nonce, server_aead_tag, wrapped_dek}` (per `models.py:108-111`) and the `uniq_nonce_per_key_version` defense-in-depth (per `models.py:129-131`), but the `wrapped_dek` is **not actually wrapped** — it is 32 zero bytes, so the ciphertext is effectively unwrappable. This is a Phase 2A4 placeholder, documented in the comment at `enroll_service_identity.py:100-103` ("encryption pipeline replaces this with KMS-bound storage").

**What Phase 4 must do.** Replace the placeholder writes in `enroll_service_identity.py:114-150` with the same KMS envelope path that `finalize_enrollment.py:115-138` already uses:

```python
kms = self._kms()                                            # via KmsFactory.get_kms()
version = kms.current_key_version()                           # via BIOMETRIC_ACTIVE_KEK_VERSION
plaintext_dek = secrets.token_bytes(32)
wrapped_dek = kms.wrap_dek(plaintext_dek, version)            # AwsKmsAdapter.generate_data_key()
server_env = aesgcm_encrypt(plaintext_dek, template_raw,     # AES-GCM with 96-bit nonce
                            aad=str(user_external_id).encode("utf-8"))
# ... persist:
BiometricTemplate.objects.update_or_create(
    ...,
    defaults={
        "encrypted_fmd": server_env.ciphertext,
        "server_aead_nonce": server_env.nonce,
        "server_aead_tag": server_env.tag,
        "wrapped_dek": wrapped_dek,
        "key_version": version,
        ...
    },
)
# ... emit one BiometricAuditEvent with event_type="service.enrollment_kms_unavailable"
#     on KMS failure (mirror of finalize_enrollment.py:121-127).
```

**Files affected.**
- `DP4500 estandar/backend/apps/biometric/application/use_cases/enroll_service_identity.py` (lines 114-150) — replace placeholder writes.
- `DP4500 estandar/backend/apps/biometric/application/dto/dto.py:39,56-57` (`client_encrypted_fmd` field) — verify it carries base64url-encoded bytes that the use case can pass into `aesgcm_encrypt`.
- `DP4500 estandar/backend/apps/biometric/infrastructure/crypto/aesgcm.py` — verify the envelope accepts the Phase 2A4 `b""` placeholder for the dev/dev-without-hardware path (the value should round-trip through `encrypt`/`decrypt` even when empty; if not, the path must keep using `b""` and the placeholder envelope only for non-empty templates).
- `DP4500 estandar/backend/apps/biometric/infrastructure/kms/vault_adapter.py` — `wrap_dek`/`unwrap_dek` are TODO-only stubs (per `enroll_service_identity.py` line 23 mention); Phase 4 may either implement them or ship `aws_kms` as the only production backend and gate `vault` as a future option.
- New tests: `DP4500 estandar/backend/tests/integration/biometric/test_service_flow_kms_envelope.py` — assert that a service-flow enrollment with `template_b64` non-empty produces a row with non-zero `wrapped_dek` and an `encrypted_fmd` that round-trips through `kms.unwrap_dek + aesgcm_decrypt`.

**Effort:** Medium (1-2 days; mirror of the existing Knox-flow code).

---

### 4.2 Deliverable 2 — `ServiceAPIKey` rotation endpoint + cron

**Problem.** The `rotated_from` self-FK column exists at `apps/accounts/models.py:200-206` and the `create_service_api_key --rotated-from` flag is wired at `apps/accounts/management/commands/create_service_api_key.py:48-54,64-72`, but no HTTP endpoint exists to drive rotation in the same transaction that creates the next key. The docstring at `apps/accounts/models.py:185-188` is explicit: *"Rotation should deactivate the previous key in the same transaction that creates the next one (Phase 4)."* The Phase 1 design flagged `POST /api/biometric/service/keys/<id>/rotate/` as Phase 4 (`openspec/changes/dp4500-host-app-integration-phase1/tasks.md:259`).

**What Phase 4 must do.**
1. **Endpoint**: `POST /api/biometric/service/keys/<id>/rotate/` — DRF view behind `IsServiceAPIKey` auth. Body: `{"name": "<new-key-name>"}`. Response: `{"new_key_id": <int>, "raw_token": "<43-char urlsafe-base64>", "rotated_from": <int>}` (the raw token is shown ONCE). Inside the same `transaction.atomic()` block: (a) mint a fresh raw token via `secrets.token_urlsafe(32)`; (b) `ServiceAPIKey.objects.create(name=..., key_hash=..., rotated_from=<old>)`; (c) `<old>.is_active = False; <old>.save(update_fields=["is_active"])`; (d) emit a `service.api_key_rotated` `BiometricAuditEvent` with `external_system=requesting_service_key.name` and `metadata_json={"new_key_id": new.pk, "old_key_id": old.pk}`.
2. **Audit emission**: the rotation is a privileged action. The audit row MUST carry `requesting_service_key.name` in `external_system` (per the Phase 2A6 `service.cascade_revoke` precedent at `revoke_external_credential.py:53-64`) so the trail can be reconstructed by `external_system` + `occurred_at`.
3. **Management command**: `migrate_service_api_keys` — invokes the same rotation logic for every key older than `--age-days` (default 90). Idempotent (skips already-rotated keys). Shares `_rotate_in_transaction(old, new_name)` with the DRF view so behavior is identical.
4. **Celery beat schedule**: schedule `migrate_service_api_keys` daily in `config/celery.py`. Phase 4 ships the wiring; the cron daemon itself is the platform team's concern (per §3.2 deferral).
5. **Vault handshake**: when `ACCOUNTS_KEY_STORE_BACKEND=vault` is set, the endpoint reads the previous raw token out of vault before rotation (so the operator can do a controlled cutover), then DELETEs it from vault after the new key is active. The DRF response does NOT echo the previous raw token.

**Files affected.**
- `DP4500 estandar/backend/apps/accounts/models.py:168-227` — no schema change; rotation logic is in a new view.
- New: `DP4500 estandar/backend/apps/accounts/api/views/rotate_service_api_key.py` — DRF view.
- New: `DP4500 estandar/backend/apps/accounts/management/commands/migrate_service_api_keys.py` — operator-facing wrapper.
- `DP4500 estandar/backend/apps/biometric/api/urls.py` — add the route (under `/api/biometric/service/keys/<id>/rotate/` per Phase 1 design).
- `DP4500 estandar/backend/apps/biometric/infrastructure/persistence/models.py` (`BiometricAuditEvent` insert path) — reuse the existing `BiometricAuditEvent.objects.create(...)` pattern.
- `DP4500 estandar/backend/config/celery.py` — add `CELERY_BEAT_SCHEDULE` entry for `migrate_service_api_keys`.
- New tests: `tests/integration/accounts/test_rotate_service_api_key.py` — covers: rotation in transaction, audit emission, double-rotate idempotency, raw token in response (only once).

**Effort:** Medium (2-3 days; endpoint + audit + cron + tests).

---

### 4.3 Deliverable 3 — mTLS between workstation (browser or `fingerprint-agent`) and DP4500

**Problem.** A `grep -r 'ssl\|tls\|client_cert\|verify_mode\|SSLContext' apps/biometric` returns **no matches** — there is zero TLS client-cert validation in `apps/biometric/api/views/service/`. The Phase 1 design flagged mTLS as Phase 4 (`openspec/changes/dp4500-host-app-integration-phase1/design.md:881,905`): *"Phase 1 = bearer only (no mTLS); Phase 4 adds mTLS."* Phase 2's `HTTPClient` at `apps/biometric/client.py` (per `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:188-230`) issues plain `Authorization: Bearer <key>` over the same TLS connection the browser already negotiates with nginx (or the Vite proxy in dev).

**What Phase 4 must do.**
1. **Nginx-side mTLS terminator** (out of scope for the SDD change itself; Phase 4 documents the operator runbook; production config is the platform team's). The Django-side work is to read the validated client-cert fingerprint from the request and bind it into the audit chain.
2. **Django middleware**: `apps/biometric/api/middleware/client_cert_middleware.py` — reads `HTTP_X_SSL_CLIENT_FINGERPRINT` (or `HTTP_X_FORWARDED_CLIENT_CERT_FINGERPRINT` behind a load balancer) and attaches it to `request.dp4500_client_cert_fp`. The middleware is wired into `MIDDLEWARE` only when `DP4500_REQUIRE_MTLS=true` in settings.
3. **ServiceAPIKey authentication**: `apps/biometric/api/permissions.py` (or the `ServiceAPIKeyAuthentication` class) — when `DP4500_REQUIRE_MTLS=true`, ALSO verify that the request's `dp4500_client_cert_fp` matches the SHA-256 fingerprint registered for the calling `ServiceAPIKey`. Otherwise 401 with code `mtls_required` (or `client_cert_mismatch`).
4. **`ServiceAPIKey.client_cert_fingerprint` schema**: add `client_cert_fingerprint = models.CharField(max_length=128, null=True, blank=True, db_index=True)` to `apps/accounts/models.py:194-206`. Migration `000X_service_api_key_client_cert.py`. Nullable so dev/Vite-proxy requests without mTLS still work.
5. **`create_service_api_key` flag**: add `--client-cert-fp <hex>` to `apps/accounts/management/commands/create_service_api_key.py:38-55` so the operator can pin the cert at mint time.
6. **Cert rotation**: when the operator's workstation cert rotates (every 90 days per the Phase 1 design), the rotation endpoint from §4.2 also updates `client_cert_fingerprint` in the same atomic step.

**Files affected.**
- New: `DP4500 estandar/backend/apps/biometric/api/middleware/client_cert_middleware.py`.
- `DP4500 estandar/backend/apps/biometric/api/permissions.py` (or `apps/accounts/auth/auth.py`) — add mTLS check to `ServiceAPIKeyAuthentication.authenticate`.
- `DP4500 estandar/backend/apps/accounts/models.py:194-206` — add `client_cert_fingerprint` field.
- `DP4500 estandar/backend/apps/accounts/migrations/000X_service_api_key_client_cert.py` — `AddField`.
- `DP4500 estandar/backend/apps/accounts/management/commands/create_service_api_key.py` — `--client-cert-fp` flag.
- `DP4500 estandar/backend/config/settings/base.py` — add `DP4500_REQUIRE_MTLS` (default `false` for dev, `true` for prod).
- New: `DP4500 estandar/backend/docs/runbooks/mtls-provisioning.md` — operator runbook.

**Effort:** High (3-5 days; middleware + permission + migration + runbook + cert provisioning + tests). **Infra-heavy**: nginx config + cert issuance (internal CA or Let's Encrypt for client certs) is the bottleneck.

---

### 4.4 Deliverable 4 — DPIA update + sign-off

**Problem.** The DPIA at `DP4500 estandar/docs/dpia/DP4500-DPIA.md` is signed at version 1.0 (PR3 cut, 2026-09-13). The §9 sign-off block names **DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair** (5 roles; the document text at lines 249-252 explicitly says "Until all four roles are signed, BIOMETRIC_AUTH_ENABLED MUST remain false in production" — the document text disagrees with itself; we will resolve this to "all 5 roles" in the Phase 4 update). The §9 re-sign trigger list (lines 233-239) covers: KMS choice, biometric sample format, encryption parameters, retention schedule, incident response. Phase 2A's `Cliente.external_id` cross-system handle, Phase 3's browser Web SDK capture surface, and Phase 4's vault/KMS/mTLS hardening are **not** in the §9 trigger list as drafted — they need to be added.

**What Phase 4 must do.**
1. **DPIA §9 trigger list update** — add: (a) introduction of cross-system identity handle (`User.biometric_external_id` / `Cliente.external_id`); (b) capture mechanism shift (browser-side Web SDK vs Phase 1's Electron renderer); (c) vault/KMS adapter swap; (d) mTLS addition.
2. **DPIA §3 data inventory** — extend with: `Sucursal.dp4500_service_key_id` (clinic-side reference); `BiometricTemplate.wrapped_dek` ownership (KMS, not DBA role); `vault_secret_ref` (where the rotation secret lives, if `ACCOUNTS_KEY_STORE_BACKEND=vault`).
3. **DPIA §8 data flows** — update the diagram to reflect (a) the clinic → DP4500 bearer+TLS handshake (no mTLS yet at the time of the original DPIA), and (b) the post-Phase-4 mTLS path. The cleartext-FMD-never-leaves-the-renderer invariant is unchanged.
4. **§9 sign-off block** — bump version to 2.0 (Phase 4 cut). The five sign-off roles per the Phase 1 template are:
   - **Data Protection Officer (DPO)**
   - **Chief Technology Officer (CTO)**
   - **Legal Counsel**
   - **Security Lead**
   - **Privacy WG chair**

   The user's session-2026-09-27 note (Engram obs #53) lists the chain as "DPO + CTO + Legal + Comité de Privacidad" — the **Comité de Privacidad is the Privacy WG**; we keep all five sign-off roles per the Phase 1 template, and **map the user's "Comité de Privacidad" reference to "Privacy WG chair"**.
5. **Sign-off process** — Phase 4 ships the **unsigned** DPIA 2.0 in this cycle's `verify-report.md` (as a path reference + checksum). The **signature collection** happens after code merge, on a separate regulatory timeline. The proposal's §Verification gate marks the DPIA as "ready for signature"; the actual `BIOMETRIC_AUTH_ENABLED=true` flip requires the signed DPIA, not the merge commit.

**Files affected.**
- `DP4500 estandar/docs/dpia/DP4500-DPIA.md` — bump version 1.0 → 2.0; extend §3 / §8 / §9.
- `DP4500 estandar/scripts/check_dpia_present.py` — bump expected version from `1.0` to `2.0` (per Phase 1 task 5.4.1 at `archive/2026-09-13-dp4500-biometric-auth/tasks.md`).
- `DP4500 estandar/scripts/test_check_dpia.py` — same version bump.
- Phase 4 `verify-report.md` — attaches the **unsigned** DPIA 2.0 + the signature-pending checklist.

**Effort:** Low code-side (1 day for the markdown + script bump), but **multi-day regulatory**: the DPO + CTO + Legal + Privacy WG chair signatures are out-of-band events that can each take 2-5 business days. Phase 4 acknowledges this in the proposal's §Risks.

---

### 4.5 Deliverable 5 — Vault for `ServiceAPIKey` rotation secrets

**Problem.** The Phase 2 design (§3.4 `env_key_resolver` at `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:273-281`) defines the plugin interface:
```python
def env_key_resolver(sucursal_id: int) -> str | None:
    raw = os.environ.get(f"DP4500_SERVICE_KEY_SUCURSAL_{sucursal_id}")
    return raw
```
Phase 2 only ships the `env` backend. The `DP4500_KEY_STORE_BACKEND` setting at `config/settings.py:728` (`backend/apps/dp4500_integration` legacy path; equivalent in DP4500 estandar `config/settings/base.py`) defaults to `"env"`. Phase 4 adds `vault` as a second backend.

**What Phase 4 must do.**
1. **Vault adapter stub promotion to implementation**: `DP4500 estandar/backend/apps/biometric/infrastructure/kms/vault_adapter.py` is currently a TODO stub (`wrap_dek`/`unwrap_dek` raise `NotImplementedError` per Phase 1 verification at `archive/2026-09-13-dp4500-biometric-auth/verify/verify-report.md`). Phase 4 fills in the Vault Transit engine call (`vault read transit/decrypt/<key_name>` and `vault write transit/encrypt/<key_name>`). The KMS adapter's existing KEK-never-in-memory invariant (Phase 1 ADR-07) MUST be preserved — Vault returns ciphertext directly to boto3-style wire bytes.
2. **Service-key vault resolver**: `apps/accounts/vault.py` — `vault_service_key_resolver(sucursal_id: int) -> str | None` reads `vault kv get secret/clinic/dp4500/service-key-<sucursal_id>` and returns the `raw_token`. Falls back to `env` resolver if `VAULT_ADDR` is unset (dev). Plugin dispatch via `get_service_key_resolver()` selected by `ACCOUNTS_KEY_STORE_BACKEND` setting.
3. **Rotation-vault handshake**: when the rotation endpoint from §4.2 fires, it (a) writes the new raw token to Vault under `secret/clinic/dp4500/service-key-<id>`; (b) DELETEs the old raw token from Vault; (c) fails the rotation transaction if either Vault call fails (so the rotation is atomic across DB + Vault).
4. **Test vault fixture**: `tests/integration/conftest.py` — `vault_test_container` fixture uses `vault:latest` Docker image with Transit + KV engines pre-enabled. Only loaded under `pytest -m vault` marker so the dev CI does not require Docker.
5. **Operator runbook**: `docs/runbooks/vault-provisioning.md` — how to unseal Vault, rotate the Transit root token, audit the `secret/clinic/dp4500/*` reads.

**Files affected.**
- `DP4500 estandar/backend/apps/biometric/infrastructure/kms/vault_adapter.py` — implement `wrap_dek`/`unwrap_dek`/`rotate`/`current_key_version`.
- New: `DP4500 estandar/backend/apps/accounts/vault.py` — `vault_service_key_resolver` + `get_service_key_resolver()`.
- `DP4500 estandar/backend/config/settings/base.py` — add `ACCOUNTS_KEY_STORE_BACKEND` setting (default `env`); add `VAULT_ADDR`, `VAULT_TOKEN` env vars.
- New: `DP4500 estandar/backend/apps/accounts/management/commands/seed_vault_service_keys.py` — bootstrap helper for the dev env (writes one key per known Sucursal under `secret/clinic/dp4500/service-key-<id>`).
- New: `DP4500 estandar/docs/runbooks/vault-provisioning.md` — operator runbook.

**Effort:** Medium (2-3 days; Vault adapter impl + resolver + rotation handshake + runbook). **Infra-heavy**: Vault cluster provisioning is the bottleneck.

---

### 4.6 Deliverable 6 — `fingerprint-agent` fallback for the wizard capture path

**Problem.** Phase 3 wired the browser Web SDK directly via dynamic `<script>` injection at `dp4500-capture-client.ts:333-549`. The probe page's `fingerprint-probe.html:80-88` "Hallazgo del probe" notes that the SDK is a WebChannel wrapper (`Fingerprint.WebApi` → `WebSdk.WebChannelClient`) and may require a local relay (HID Authentication Device Client, desktop client, or a custom relay) running on the operator's workstation. If Phase 3's verify-report surfaces a "no sample on the real workstation" gap, Phase 4 ships the `fingerprint-agent` proxy as the fallback path. The Phase 3 spec explicitly locks this as the Phase 4 fallback at `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172`: "the original 2026-07-29 `fingerprint-agent` pattern is the **Phase 4 fallback** (not the default)."

**What Phase 4 must do.**
1. **`fingerprint-agent` Windows binary**: a tiny Python service that wraps the DP4500 SDK on `127.0.0.1:8765` and exposes a REST surface:
   - `POST /capture` → `{templateB64, qualityScore, deviceSerial, width, height}` (mirrors Phase 3 `captureFingerprint()`).
   - `POST /match` → `{matched: bool, score: float}`.
   - `GET /health` → `{status: "ready"}` after WebSDK init; otherwise `{status: "initializing"}`.
2. **Operator PC bootstrap**: Windows installer (MSI or `python -m pip install fingerprint-agent` + a Windows service wrapper). The agent binds to `127.0.0.1` only (no inbound port; loopback is the trust boundary). The agent speaks to the HID Authentication Device Client via the same WebChannel the browser SDK uses.
3. **Frontend wiring**: `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts::captureFingerprint()` — when the direct Web SDK path throws `BiometricHardwareError` after the 30s timeout (or when the SDK script fails to load at line 633), fall through to `fetch('http://127.0.0.1:8765/capture')`. If the agent returns `503 service_unavailable`, the wizard falls through to the Phase 2A4 NO_AGENT placeholder path (`useConversionWizard.ts:842-859`) — **the placeholder MUST remain the terminal fallback**.
4. **Two-path handshake preserved**: the agent exposes the same `onSamplesAcquired + onQualityReported` two-event handshake that Phase 3.1 wired. The frontend wrapper does not need to change; it just calls `fetch` instead of `startAcquisition()`.
5. **Audit emission**: the agent emits `device.captured` audit events locally (in `fingerprint-agent`'s own log, NOT the clinic's DB — the clinic does not see fingerprint bytes). The clinic's `BiometricAuditEvent.external_system` field stays at the `ServiceAPIKey.name` of the workstation.
6. **Local-only trust boundary**: the agent listens on `127.0.0.1` ONLY. CORS preflight is a no-op. No cloudflared tunnel, no inbound port.

**Files affected.**
- New: `frontend/aesthetic-clinic/fingerprint-agent/` — Python service (`fingerprint_agent/server.py`, `fingerprint_agent/sdk_bridge.py`, `fingerprint_agent/pyproject.toml`, `fingerprint_agent/README.md`).
- New: `frontend/aesthetic-clinic/fingerprint-agent/installer/` — Windows installer (PyInstaller or `wix` MSI).
- `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` — extend `captureFingerprint()` to fall through to `fetch('http://127.0.0.1:8765/capture')` on `BiometricHardwareError`. Keep `BiometricQualityTooLow` and the NO_AGENT fallback unchanged.
- New: `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (Playwright) — test the fall-through path with a mocked agent.
- New: `frontend/aesthetic-clinic/HOW_TO_RUN.md` — add the "fingerprint-agent install" section (operator runbook).

**Effort:** High (3-5 days; Python service + Windows installer + frontend fall-through + e2e tests). **Infra-heavy**: each operator PC needs the agent installed + the HID Authentication Device Client running.

---

## 5. Risks (Phase 4 caveats)

### R1 — DPIA sign-off is multi-day regulatory work, not engineering

**Severity:** high (production-block).

The DPIA sign-off requires **5 signatures** per the Phase 1 template at `DP4500 estandar/docs/dpia/DP4500-DPIA.md:241-247`:
- **Data Protection Officer (DPO)**
- **Chief Technology Officer (CTO)**
- **Legal Counsel**
- **Security Lead**
- **Privacy WG chair** (the user's session-2026-09-27 note calls this "Comité de Privacidad" — same body)

The signatures are out-of-band events. In typical enterprise cycles each signature can take 2-5 business days; the full chain can take 1-3 weeks even with all signatures green-lit on the first pass. The proposal must mark the **DPIA signature collection as a parallel workstream**, not as a pre-condition for code merge. The code merge + `BIOMETRIC_AUTH_ENABLED=true` flip are sequential gates; the signature is the latter.

**Mitigation:**
- (a) The proposal's §Verification gate marks the DPIA as "unsigned 2.0 ready for signature", not "signed".
- (b) The proposal's §Out-of-Scope explicitly lists "ongoing DPIA renewal cadence" — the 180-day review cadence is post-Phase-4.
- (c) The proposal surfaces a `BLOCKED-BY-DPIA-SIGNOFF` banner in the apply checklist so the operator cannot flip `BIOMETRIC_AUTH_ENABLED=true` without the signed attachment.

### R2 — mTLS + vault + KMS key rotation are infra-heavy

**Severity:** medium (production-readiness, but well-understood).

Each of deliverables 2, 3, 5 has an infra dependency that the engineering team does NOT own:
- **mTLS** (§4.3): nginx config + internal CA + workstation cert provisioning. The platform team owns this. Phase 4 ships the Django middleware + the permission; production deployment requires the platform team's nginx + cert work.
- **Vault** (§4.5): Vault cluster (HA recommended) + Transit engine + KV engine. The platform team owns this. Phase 4 ships the adapter + the resolver; production deployment requires the platform team's Vault cluster.
- **KMS rotation** (§4.1 + Phase 1 `docs/runbooks/kms-rotation.md`): the AWS KMS alias + IAM policy + cross-region replication. The platform team owns this. Phase 4 ships the `migrate_biometric_key_version` management command + the service-flow envelope swap; production cutover requires the platform team's AWS KMS work.

**Mitigation:**
- (a) Each deliverable's `verify-report.md` section marks "infra-dependent" WUs explicitly.
- (b) Phase 4 is gated on `BIOMETRIC_AUTH_ENABLED=false` staying default until ALL six deliverables merge + DPIA signs.
- (c) The proposal commits to a runbook per infra dependency (`docs/runbooks/{mtls-provisioning,vault-provisioning,kms-rotation}.md`).

### R3 — `fingerprint-agent` requires operator workstation setup

**Severity:** medium (operator-driven, not engineering).

The `fingerprint-agent` is a Windows-side Python service + the HID Authentication Device Client. Each operator workstation needs both installed before the Phase 3 Web SDK path can be replaced. There is no headless / unattended install path that works across all Windows builds; each PC needs the bootstrap manual run.

**Mitigation:**
- (a) The Phase 3 SDK-direct path remains the **default**. The `fingerprint-agent` fallback fires only when Phase 3's verify-report surfaces a "no sample on the real workstation" gap (per the Phase 3 spec at `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172`).
- (b) If the verify-report says "Phase 3 works on real hardware", deliverable 6 ships as a **documented-but-disabled** code path (the agent code is committed, the frontend wiring is feature-flagged off, the operator can opt in per-PC). This avoids forcing the workstation setup on operators who already have the HID Authentication Device Client running.
- (c) The `fingerprint-agent` MSI installer is a self-contained `pip install` + `python -m fingerprint_agent` invocation; the operator runbook in `HOW_TO_RUN.md` walks through it step-by-step.

### R4 — Cross-repo scope confusion

**Severity:** low (already mitigated by convention).

The Phase 4 deliverables split across two repos:
- **`DP4500 estandar`** (the Django host) — deliverables 1, 2, 3, 4, 5. The mTLS, vault, KMS, and rotation work lives here.
- **`proyecto C`** (the clinic) — deliverable 6 only (`fingerprint-agent` is a frontend-side proxy). No clinic-side backend changes for Phase 4.

The SDD change folder lives in `proyecto C` (per the user's session-2026-09-27 decision: "the change lives in proyecto C; DP4500 estandar files are referenced but the SDD artifacts live here"). The Phase 4 `verify-report.md` runs the DP4500 estandar tests via the WSL bash pattern from Phase 2A7 (Engram obs #53 §"WSL bash for clinic backend pytest").

**Mitigation:** the proposal §Scope explicitly states which deliverable lives in which repo. The verify-report documents the cross-repo test commands verbatim.

### R5 — `ServiceAPIKey.rotation` is in two places (model hook + endpoint)

**Severity:** low (architectural).

The `models.py:200-206` `rotated_from` self-FK is the schema hook. The endpoint from §4.2 is the rotation hook. Phase 4 must ensure both hooks are exercised in the same transaction: the endpoint sets `rotated_from=<old>` AND sets `<old>.is_active=False` in one `transaction.atomic()`. The Celery cron (`migrate_service_api_keys`) reuses the endpoint's `_rotate_in_transaction(old, new_name)` so the two paths are identical.

**Mitigation:** the proposal's §Design mandates a single `_rotate_in_transaction(old, new_name)` helper shared by the DRF view, the management command, and the Celery task. The tests assert that `rotated_from` is set AND `<old>.is_active=False` in the same transaction (use `transaction.set_rollback(True)` mid-test to assert atomicity).

---

## 6. Affected areas

| Path | Repo | Change | Why |
|---|---|---|---|
| `backend/apps/biometric/application/use_cases/enroll_service_identity.py:114-150` | DP4500 estandar | REPLACE placeholder writes with real KMS envelope | Deliverable 1 |
| `backend/apps/biometric/infrastructure/kms/vault_adapter.py` | DP4500 estandar | IMPLEMENT `wrap_dek`/`unwrap_dek`/`rotate`/`current_key_version` | Deliverable 5 |
| `backend/apps/accounts/api/views/rotate_service_api_key.py` (NEW) | DP4500 estandar | NEW DRF view | Deliverable 2 |
| `backend/apps/accounts/management/commands/migrate_service_api_keys.py` (NEW) | DP4500 estandar | NEW operator-facing wrapper | Deliverable 2 |
| `backend/apps/accounts/management/commands/seed_vault_service_keys.py` (NEW) | DP4500 estandar | NEW bootstrap helper | Deliverable 5 |
| `backend/apps/accounts/models.py:194-206` | DP4500 estandar | ADD `client_cert_fingerprint` field | Deliverable 3 |
| `backend/apps/accounts/migrations/000X_service_api_key_client_cert.py` (NEW) | DP4500 estandar | NEW migration | Deliverable 3 |
| `backend/apps/accounts/management/commands/create_service_api_key.py:38-55` | DP4500 estandar | ADD `--client-cert-fp` flag | Deliverable 3 |
| `backend/apps/accounts/vault.py` (NEW) | DP4500 estandar | NEW resolver + plugin dispatch | Deliverable 5 |
| `backend/apps/biometric/api/middleware/client_cert_middleware.py` (NEW) | DP4500 estandar | NEW middleware | Deliverable 3 |
| `backend/apps/biometric/api/permissions.py` (or `apps/accounts/auth/auth.py`) | DP4500 estandar | ADD mTLS check | Deliverable 3 |
| `backend/apps/biometric/api/urls.py` | DP4500 estandar | ADD `/service/keys/<id>/rotate/` route | Deliverable 2 |
| `backend/config/settings/base.py` | DP4500 estandar | ADD `DP4500_REQUIRE_MTLS`, `ACCOUNTS_KEY_STORE_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN` settings | Deliverables 3, 5 |
| `backend/config/celery.py` | DP4500 estandar | ADD `CELERY_BEAT_SCHEDULE` for `migrate_service_api_keys` | Deliverable 2 |
| `docs/dpia/DP4500-DPIA.md` | DP4500 estandar | BUMP version 1.0 → 2.0; EXTEND §3, §8, §9 | Deliverable 4 |
| `scripts/check_dpia_present.py` | DP4500 estandar | BUMP expected version | Deliverable 4 |
| `scripts/test_check_dpia.py` | DP4500 estandar | BUMP expected version | Deliverable 4 |
| `docs/runbooks/mtls-provisioning.md` (NEW) | DP4500 estandar | NEW operator runbook | Deliverable 3 |
| `docs/runbooks/vault-provisioning.md` (NEW) | DP4500 estandar | NEW operator runbook | Deliverable 5 |
| `docs/runbooks/kms-rotation.md` (existing — verify completeness) | DP4500 estandar | EXTEND with service-flow migration steps | Deliverable 1 |
| `frontend/aesthetic-clinic/fingerprint-agent/` (NEW) | proyecto C | NEW Python service | Deliverable 6 |
| `frontend/aesthetic-clinic/fingerprint-agent/installer/` (NEW) | proyecto C | NEW Windows installer | Deliverable 6 |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts:333-549` | proyecto C | EXTEND `captureFingerprint()` with agent fall-through | Deliverable 6 |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` | proyecto C | ADD "fingerprint-agent install" section | Deliverable 6 |
| `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (NEW) | proyecto C | NEW Playwright e2e | Deliverable 6 |
| `tests/integration/biometric/test_service_flow_kms_envelope.py` (NEW) | DP4500 estandar | NEW integration test | Deliverable 1 |
| `tests/integration/accounts/test_rotate_service_api_key.py` (NEW) | DP4500 estandar | NEW integration test | Deliverable 2 |
| `tests/integration/biometric/test_mtls_required.py` (NEW) | DP4500 estandar | NEW integration test | Deliverable 3 |
| `tests/integration/accounts/test_vault_service_key_resolver.py` (NEW) | DP4500 estandar | NEW integration test | Deliverable 5 |

**NOT affected (Phase 4 leaves alone):**
- `frontend/aesthetic-clinic/src/services/biometric/ed25519-key-manager.ts` — unchanged (Phase 2A2).
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts:701-865` — unchanged (the NO_AGENT fallback at lines 842-859 is carved out as the terminal fallback; Phase 4's `fingerprint-agent` fall-through is INSIDE `dp4500-capture-client.ts`, not in the wizard).
- All Phase 1/2/2A6/2A7/3 archived artifacts — unchanged.
- `openspec/specs/` — unchanged. Phase 4 may add delta specs under `openspec/changes/dp4500-host-app-integration-phase4-production-readiness/specs/` (per OpenSpec convention), but it does not modify the main `openspec/specs/*/spec.md` files.

---

## 7. Recommendation for proposal / design / tasks

### 7.1 Spec delta (proposal §Scope)

- **In Scope** (all 6 deliverables):
  1. KMS-backed envelope for `BiometricTemplate.encrypted_fmd` on the service-flow path (§4.1).
  2. `ServiceAPIKey` rotation endpoint + Celery cron + audit emission (§4.2).
  3. mTLS between workstation (browser or `fingerprint-agent`) and DP4500 (§4.3).
  4. DPIA update to v2.0 covering Phase 2/3/4 surface changes; sign-off chain (§4.4).
  5. Vault backend for `ServiceAPIKey` rotation secrets (§4.5).
  6. `fingerprint-agent` fallback for the wizard capture path (§4.6).
- **Out of Scope** (explicit deferrals, post-Phase-4):
  - Real hardware physical install on the operator PC (HID Authentication Device Client bootstrap).
  - Ongoing DPIA renewal cadence (covered by §6 of `DPIA.md` after Phase 4 ships).
  - Cron infrastructure outside the test environment (production cron daemon, systemd unit, k8s CronJob).
  - Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing.
  - Cross-repo merge of `feat/dp4500-host-app-integration-phase2-sdd` to main (user decision deferred until both fronts stable).

### 7.2 Design patterns to lock in

| # | Pattern | Source | What to follow |
|---|---|---|---|
| **P1** | **KMS envelope parity** | Phase 1 `finalize_enrollment.py:115-138` | The service-flow use case (`enroll_service_identity.py:114-150`) MUST mirror the Knox-flow envelope (fresh DEK + `kms.wrap_dek` + AES-GCM + DEK cache put) verbatim. No shortcut. |
| **P2** | **Single rotation transaction** | Phase 4 §4.2 design | The `_rotate_in_transaction(old, new_name)` helper is the only path that touches `ServiceAPIKey` writes. DRF view, management command, and Celery task all call it. The helper sets `rotated_from=<old>` AND `<old>.is_active=False` AND emits the audit row in one `transaction.atomic()`. |
| **P3** | **mTLS opt-in via setting** | Phase 4 §4.3 design | `DP4500_REQUIRE_MTLS=true` flips the middleware + permission on. Default `false` so dev/Vite-proxy continues to work. Production deployment flips it AFTER nginx + cert work is done by the platform team. |
| **P4** | **DPIA version-bump script check** | Phase 1 task 5.4.1 (`scripts/check_dpia_present.py`) | Bump the script's expected version 1.0 → 2.0. CI fails if the DPIA version regresses. |
| **P5** | **Audit-chain participation** | Phase 1 `revoke_external_credential.py:53-64` precedent | Every Phase 4 privileged action (rotation, vault migration, mTLS check failure) emits one `BiometricAuditEvent` with `external_system=requesting_service_key.name` so the trail is reconstructable by `external_system + occurred_at`. |
| **P6** | **NO_AGENT is the terminal fallback** | Phase 3 spec §X.Y "Real capture error path" | The Phase 4 `fingerprint-agent` fall-through in `dp4500-capture-client.ts` sits BETWEEN the direct Web SDK path and the NO_AGENT placeholder. NO_AGENT (`useConversionWizard.ts:842-859`) remains the canonical terminal fallback when both the SDK and the agent fail. |
| **P7** | **Phase 2 plugin interface reused** | Phase 2 `design.md:279-281` | The `get_service_key_resolver()` plugin dispatch is the canonical way to add new resolvers (vault, future AWS Secrets Manager, future HashiCorp Boundary). Phase 4 only adds `vault_service_key_resolver`; no parallel dispatch surface. |
| **P8** | **Verify-report gates Phase 4 archive** | Phase 3 explore §7.4 P4 | The verify-report is the single gate. All six deliverables must merge + the DPIA must be marked "unsigned 2.0 ready for signature" before archive. The signed DPIA is a separate production-block gate. |

### 7.3 Tasks artifact (tasks.md §Suggested Work Units)

| Unit | Goal | Files touched | Lines estimate | Rollback boundary |
|---|---|---|---|---|
| **WU-4.1** | KMS-backed envelope for service-flow enrollment | `enroll_service_identity.py:114-150`, new `test_service_flow_kms_envelope.py` | ~80 lines (mirror `finalize_enrollment.py:115-138`) | Revert to placeholder bytes; Knox-flow path unchanged. |
| **WU-4.2** | `ServiceAPIKey` rotation endpoint | NEW `apps/accounts/api/views/rotate_service_api_key.py`, `urls.py`, new `test_rotate_service_api_key.py` | ~150-200 lines (view + audit + atomicity) | Disable the route in `urls.py`; the `create_service_api_key --rotated-from` CLI still works. |
| **WU-4.3** | `migrate_service_api_keys` management command + Celery beat schedule | NEW `apps/accounts/management/commands/migrate_service_api_keys.py`, `config/celery.py` | ~80 lines | Disable the beat schedule; the command is idempotent so re-running is safe. |
| **WU-4.4** | mTLS middleware + permission + `client_cert_fingerprint` schema | NEW `client_cert_middleware.py`, modify `permissions.py`/`models.py:194-206`, new migration, modify `create_service_api_key.py:38-55`, new `test_mtls_required.py` | ~200-300 lines + new migration | Keep `DP4500_REQUIRE_MTLS=false`; the middleware is a no-op. |
| **WU-4.5** | DPIA v2.0 + script version bump + runbook skeleton | `DP4500-DPIA.md`, `check_dpia_present.py`, `test_check_dpia.py` | ~100-150 lines of DPIA markdown + ~10 lines of script bump | Revert to v1.0; the script check fails the CI gate (intentional). |
| **WU-4.6** | Vault backend for `ServiceAPIKey` rotation secrets | modify `vault_adapter.py`, NEW `apps/accounts/vault.py`, modify `settings/base.py`, NEW `seed_vault_service_keys.py`, new `test_vault_service_key_resolver.py`, NEW `docs/runbooks/vault-provisioning.md` | ~250-400 lines + runbook | Set `ACCOUNTS_KEY_STORE_BACKEND=env`; the resolver falls back. |
| **WU-4.7** | `fingerprint-agent` Python service | NEW `frontend/aesthetic-clinic/fingerprint-agent/` | ~300-500 lines (Python service + SDK bridge + REST) | Feature-flagged off; the frontend falls back to NO_AGENT. |
| **WU-4.8** | `fingerprint-agent` Windows installer | NEW `frontend/aesthetic-clinic/fingerprint-agent/installer/` | ~100-150 lines (PyInstaller spec + Wix MSI XML) | Operator opt-in only; not auto-installed. |
| **WU-4.9** | Frontend `captureFingerprint()` fall-through wiring | `dp4500-capture-client.ts:333-549` | ~30-50 lines (try Web SDK, catch `BiometricHardwareError`, try `fetch('http://127.0.0.1:8765/capture')`, fall through to NO_AGENT) | Revert to Phase 3.1; the SDK-only path returns. |
| **WU-4.10** | E2E + HOW_TO_RUN update for the agent | NEW `tests/e2e/fingerprint-agent.spec.ts`, `HOW_TO_RUN.md` extension | ~150-200 lines (Playwright spec + operator runbook section) | Delete the spec; revert the runbook section. |

**Net line estimate**: ~1300-2200 lines across both repos. This is **well over the 400-line `review_budget_lines` cap from `openspec/config.yaml:64`**, so **chain PRs are required**. Suggested split (3 chained PRs):
- **PR A** (DP4500 estandar, ~500 lines): WU-4.1 (KMS envelope) + WU-4.5 (DPIA v2.0). Backend-only.
- **PR B** (DP4500 estandar, ~600 lines): WU-4.2 (rotation endpoint) + WU-4.3 (cron) + WU-4.6 (vault backend). Backend-only.
- **PR C** (both repos, ~700 lines): WU-4.4 (mTLS middleware) + WU-4.7 (agent service) + WU-4.8 (agent installer) + WU-4.9 (frontend wiring) + WU-4.10 (e2e + runbook). Frontend + backend, gated on PR A + PR B merging first.

### 7.4 Pre-apply + Post-apply checklist

- **Pre-apply**:
  - `BiometricTemplate.{encrypted_fmd, server_aead_nonce, server_aead_tag, wrapped_dek}` columns are NOT NULL (per `models.py:108-111`); the service-flow placeholder bytes are 12 random + 16 zero + 32 zero.
  - `VaultKmsAdapter.wrap_dek` / `unwrap_dek` / `rotate` / `current_key_version` are TODO-only stubs (per Phase 1 verify report); Phase 4 fills them in.
  - `apps/accounts/models.py:200-206` already has `rotated_from` self-FK; no migration needed for the rotation schema.
  - `apps/biometric/api/views/service/__init__.py` is empty; the `/service/keys/<id>/rotate/` route is a new file.
  - The DPIA §9 sign-off block has 5 rows (DPO + CTO + Legal + Security Lead + Privacy WG chair); the user's "Comité de Privacidad" reference maps to "Privacy WG chair".
  - The frontend `VITE_DP4500_SERVICE_API_KEY` env var is set; the wizard's NO_AGENT fallback at `useConversionWizard.ts:842-859` is untouched.
  - Celery beat is NOT enabled in the dev environment (`openspec/config.yaml:72` `CELERY_TASK_ALWAYS_EAGER=True` for clinic); the rotation cron only fires in production.
- **Post-apply**:
  - `pytest DP4500 estandar/backend/tests/integration/biometric -q` passes (KMS envelope + cascade + mTLS).
  - `pytest DP4500 estandar/backend/tests/integration/accounts -q` passes (rotation + vault).
  - `cd "C:/proyectos/proyecto C/frontend/aesthetic-clinic" && npm run lint` passes.
  - `cd "C:/proyectos/proyecto C/frontend/aesthetic-clinic" && npm run test` passes (Vitest).
  - `cd "C:/proyectos/proyecto C/frontend/aesthetic-clinic" && npx playwright test tests/e2e/fingerprint-agent.spec.ts` passes (e2e for the agent fall-through).
  - `scripts/check_dpia_present.py` exits 0 (DPIA v2.0 is present).
  - `verify-report.md` documents:
    - The unsigned DPIA 2.0 attachment (path + SHA-256 checksum).
    - The signature-pending checklist (5 roles, multi-day process).
    - The cross-repo test commands run during verify.
    - The `BIOMETRIC_AUTH_ENABLED=true` flip is BLOCKED on the signed DPIA, not on the code merge.

---

## 8. Out of scope (post-Phase-4)

Per the Phase 2A4 archive and the Phase 3 explore §8:

- **Real hardware physical install** on the operator PC (HID Authentication Device Client bootstrap, USB driver setup, workstation cert provisioning per PC). The `fingerprint-agent` installer (§4.6) automates the agent side; the HID Authentication Device Client is still operator-driven.
- **Ongoing DPIA renewal cadence**. The 180-day review cycle per `DP4500-DPIA.md:6` is post-Phase-4.
- **Cron infrastructure outside the test environment**. Production cron daemon, systemd unit, k8s CronJob — all platform-team concerns. Phase 4 ships the management command + Celery beat wiring; production deployment requires the platform team's scheduler.
- **Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing**. The Phase 2A4 env-var pattern (`DP4500_SERVICE_KEY_SUCURSAL_<id>`) works for the dev environment; production per-sucursal routing is a separate cycle.
- **`Cliente.external_id` UUIDField finalize**. The Phase 2A4 schema carries the cross-system handle; the finalize handler persistence polish is deferred (per `explore-reconciliation.md §3.7` Disposition: "Reasign").
- **Cross-repo merge of `feat/dp4500-host-app-integration-phase2-sdd` to main**. The branch has 18+ commits ahead of main; the user deferred the merge until both fronts stable (per Engram obs #53 §"Pending optional cleanups").

---

## 9. Ready for proposal

**Yes.** The change is well-scoped (6 deliverables, each with file paths + line numbers + effort estimate), has explicit risks with mitigations (R1: DPIA sign-off timeline; R2: infra dependencies; R3: operator workstation setup; R4: cross-repo scope; R5: rotation atomicity), and reuses Phase 1/2/3 patterns (KMS envelope parity at `finalize_enrollment.py:115-138`; cascade-revoke audit emission at `revoke_external_credential.py:53-64`; NO_AGENT terminal fallback at `useConversionWizard.ts:842-859`).

The orchestrator should proceed to `sdd-propose` with the following guidance:

- **All 6 deliverables in one SDD cycle** — do not let the proposal re-split into 4a/4b/4c. The user's session-2026-09-27 decision locks the single-cycle scope.
- **Chain PRs are required** — the total is 1300-2200 lines across both repos, well over the 400-line review budget. The suggested 3-PR split is in §7.3.
- **DPIA sign-off is a parallel workstream, not a pre-condition for code merge** — the proposal's §Verification gate marks the DPIA as "unsigned 2.0 ready for signature", not "signed". The signed DPIA is a separate production-block gate that does not block the SDD cycle's archive.
- **The DPIA sign-off chain is DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair** (5 roles, per the Phase 1 template at `DP4500-DPIA.md:241-247`). The user's "Comité de Privacidad" reference maps to "Privacy WG chair".
- **Cross-repo scope is documented** — deliverables 1/2/3/4/5 live in `DP4500 estandar`; deliverable 6 lives in `proyecto C`. The SDD change folder is in `proyecto C/openspec/changes/dp4500-host-app-integration-phase4-production-readiness/` (per the session-2026-09-27 decision).
- **NO_AGENT placeholder is carved out** — the proposal must explicitly state "NO_AGENT placeholder preserved as terminal fallback" in §Scope to avoid drift during apply. The fallback at `useConversionWizard.ts:842-859` MUST survive the apply.
- **`fingerprint-agent` is opt-in, not auto-installed** — Phase 4 ships the agent + installer + frontend wiring, but the operator chooses when to install per PC. The frontend wiring is feature-flagged off by default; the Phase 3 SDK-direct path is the default until the operator opts in.
- **Rollback path per deliverable** — each WU has a clean revert boundary (see §7.3). The WUs are loosely coupled; a partial rollback leaves the rest of the system intact.