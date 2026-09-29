# Design: Host-app integration — Phase 4 (Production-readiness)

**Change name**: `dp4500-host-app-integration-phase4-production-readiness`
**Artifact store**: openspec (this repo, the clinic)
**Status**: Draft (will lock after `sdd-tasks`)
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd` at `4ff5ca7`
**Predecessors (all archived)**:
- `proposal.md` (this cycle)
- `explore.md` (this cycle)
- 4 delta specs in `specs/`: `biometric-template-storage/spec.md`, `service-api-authentication/spec.md`, `wizard-biometric-enrollment/spec.md`, `cascade-biometric-revoke/spec.md`
- Phase 1: `DP4500 estandar/.../2026-09-13-dp4500-biometric-auth/`
- Phase 2 + 2A4/5/6/7: `archive/2026-09-28-dp4500-host-app-integration-phase2*/`
- Phase 3 + 3.1: `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/` + commit `4ff5ca7`

---

## 1. Title

**Phase 4 — Production-readiness** (KMS storage + key rotation + mTLS + DPIA + vault + fingerprint-agent fallback).

---

## 2. Status

Draft (will lock after `sdd-tasks`).

---

## 3. Architecture Decisions

### 3.1 KMS-backed envelope (Deliverable #1)

| Field | Value |
|---|---|
| **Choice** | Replace placeholder bytes at `enroll_service_identity.py:114-150` with KMS envelope mirroring Knox-flow `finalize_enrollment.py:115-138`. Fresh DEK + `kms.wrap_dek` + AES-GCM + DEK cache put. |
| **Alternatives considered** | (a) Keep placeholders (rejected — service-flow templates are unwrappable); (b) Implement a service-specific envelope (rejected — diverges from Knox-flow audit pattern). |
| **Rationale** | Mirroring Knox-flow keeps KMS parity, reuses the Phase 1 `KmsFactory.get_kms()` selection, and keeps the `key_version` invariant single-sourced. Setting `BIOMETRIC_KMS_BACKEND` (default `simulator` for dev, `aws_kms` for prod) selects the adapter without code branches. |

### 3.2 `ServiceAPIKey` rotation (Deliverable #2)

| Field | Value |
|---|---|
| **Choice** | NEW `POST /api/biometric/service/keys/<id>/rotate/` DRF view + NEW `migrate_service_api_keys` management command + NEW Celery beat schedule. Reuses Phase 1 `ServiceAPIKey.rotation` self-FK schema (`models.py:200-206`). Single `_rotate_in_transaction(old, new_name)` helper shared by all three callers. |
| **Alternatives considered** | (a) Endpoint-only (rejected — cron is platform-team-routable); (b) Command-only (rejected — operators need HTTP for prod hot-swap); (c) Two independent helpers (rejected — risks divergence between DRF and CLI atomicity). |
| **Rationale** | One helper guarantees `rotated_from=<old>` AND `<old>.is_active=False` AND audit emit land in one `transaction.atomic()` regardless of caller. Audit emission MUST carry `external_system=<rotating_key_name>` (Phase 2A6 precedent at `revoke_external_credential.py:53-64`). `CELERY_BEAT_SCHEDULE` entry wires the management command for daily execution; the cron daemon itself is the platform team's concern. |

### 3.3 mTLS workstation ↔ DP4500 (Deliverable #3)

| Field | Value |
|---|---|
| **Choice** | NEW `apps/biometric/api/middleware/client_cert_middleware.py` (reads `HTTP_X_SSL_CLIENT_FINGERPRINT`); NEW `client_cert_fingerprint` CharField on `ServiceAPIKey`; mTLS check added to `ServiceAPIKeyAuthentication`. Setting `DP4500_REQUIRE_MTLS` defaults `False` in dev, `True` in prod. |
| **Alternatives considered** | (a) TLS check inside the auth class only (rejected — middleware is the canonical place to attach the cert fp to `request`); (b) Hardcoded `True` (rejected — breaks Vite-proxy dev workflow); (c) Per-endpoint opt-in (rejected — uniform handshake is the threat model). |
| **Rationale** | Middleware-first lets the permission class read `request.dp4500_client_cert_fp` consistently. The `client_cert_fingerprint` schema is nullable so dev/Vite-proxy requests without mTLS still work. Without cert → 401 with `code: mtls_required`; fingerprint mismatch → 401 with `code: client_cert_mismatch`. Nginx-side mTLS terminator is out of scope (platform-team runbook at `docs/runbooks/mtls-provisioning.md`). |

### 3.4 Vault backend (Deliverable #5)

| Field | Value |
|---|---|
| **Choice** | Implement `apps/biometric/infrastructure/kms/vault_adapter.py` (existing TODO stub from Phase 1 — `wrap_dek`/`unwrap_dek`/`rotate`/`current_key_version` raise `NotImplementedError`). NEW `apps/accounts/vault.py` with `vault_service_key_resolver()`. Reuse the existing `vault_key_resolver()` plugin dispatch at `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:279-281` — extend with `ACCOUNTS_KEY_STORE_BACKEND` setting (default `env`). |
| **Alternatives considered** | (a) Skip Vault, ship `aws_kms` only (rejected — Phase 2 plugin dispatch explicitly anticipates `vault`); (b) New dispatch surface (rejected — `get_service_key_resolver()` is the canonical interface). |
| **Rationale** | The Phase 2 plugin interface is the documented extension point. Vault Transit returns ciphertext directly to boto3-style wire bytes, preserving the Phase 1 ADR-07 KEK-never-in-memory invariant. Rotation handshake: when `ACCOUNTS_KEY_STORE_BACKEND=vault`, the rotation endpoint writes the new raw token to Vault under `secret/clinic/dp4500/service-key-<id>` AND DELETEs the old raw token — both inside the same `transaction.atomic()` so the rotation is atomic across DB + Vault. |

### 3.5 DPIA v2.0 update (Deliverable #4)

| Field | Value |
|---|---|
| **Choice** | Update `C:\Proyectos\DP4500 estandar\docs\dpia\DP4500-DPIA.md` from v1.0 → v2.0. Extend §3 (data inventory — add `Sucursal.dp4500_service_key_id`, `BiometricTemplate.wrapped_dek` ownership, `vault_secret_ref`), §8 (security controls — add mTLS, vault, KMS adapter swap), §9 (compliance trigger list + 5-role sign-off block). Bump `scripts/check_dpia_present.py` expected version 1.0 → 2.0. |
| **Alternatives considered** | (a) New DPIA document (rejected — version-bump is canonical); (b) Block merge on signatures (rejected — verification gate is "all 6 deliverables merged + DPIA unsigned 2.0 ready for signature"; signatures are a parallel regulatory workstream). |
| **Rationale** | Ships UNSIGNED with a signature-pending checklist in `verify-report.md`. Production gate (`BIOMETRIC_AUTH_ENABLED=true` flip) is BLOCKED on signed DPIA, not on code merge. Sign-off chain: DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair (5 roles; the user's "Comité de Privacidad" maps to "Privacy WG chair"). |

### 3.6 Fingerprint-agent fallback (Deliverable #6)

| Field | Value |
|---|---|
| **Choice** | NEW `frontend/aesthetic-clinic/fingerprint-agent/` Python service on `127.0.0.1:8765` exposing `POST /capture`, `POST /match`, `GET /health`. Windows installer (MSI or PowerShell script) at `frontend/aesthetic-clinic/fingerprint-agent/installer/`. Frontend fall-through in `dp4500-capture-client.ts::captureFingerprint()` (lines 333-549): when WebChannel host unavailable OR explicit feature flag `DP4500_USE_FINGERPRINT_AGENT=true`, fall through to `fingerprint-agent` HTTP POST /capture. |
| **Alternatives considered** | (a) Make agent the default (rejected — Phase 3 spec at `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172` locks SDK-direct as default); (b) Cloud-side proxy (rejected — fingerprint bytes must not leave the workstation); (c) Skip agent entirely (rejected — fallback must exist for workstations where the SDK WebChannel host is unavailable). |
| **Rationale** | Feature flag defaults OFF (`DP4500_USE_FINGERPRINT_AGENT=false`) — the SDK-direct path stays default. Agent binds to `127.0.0.1` ONLY (no inbound port; loopback is the trust boundary). The Phase 2A4 NO_AGENT placeholder at `useConversionWizard.ts:842-859` remains the **terminal** fallback — the Phase 4 agent fall-through sits between direct Web SDK and NO_AGENT. |

---

## 4. Chained PR Strategy

Per the proposal's §10 — total estimated delta **1500-2500 lines** exceeds the 400-line `review_budget_lines` cap from `openspec/config.yaml:64` (~4×). Chain PRs mandatory.

### PR A — KMS + DPIA (~500 lines)

**Repo**: DP4500 estandar (backend-only).

| WU | Deliverable | Files | Lines |
|---|---|---|---|
| WU-4.1 | KMS envelope | `enroll_service_identity.py:114-150`, new `tests/integration/biometric/test_service_flow_kms_envelope.py` | ~80 |
| WU-4.5 | DPIA v2.0 + script bump | `DP4500-DPIA.md`, `check_dpia_present.py`, `test_check_dpia.py` | ~100-150 |

**Gate**: None (first in chain).

### PR B — Rotation + Vault (~600 lines)

**Repo**: DP4500 estandar (backend-only).

| WU | Deliverable | Files | Lines |
|---|---|---|---|
| WU-4.2 | Rotation endpoint + audit | NEW `apps/accounts/api/views/rotate_service_api_key.py`, `urls.py`, new `test_rotate_service_api_key.py` | ~150-200 |
| WU-4.3 | Cron + Celery beat | NEW `apps/accounts/management/commands/migrate_service_api_keys.py`, `config/celery.py` | ~80 |
| WU-4.6 | Vault backend | modify `vault_adapter.py`, NEW `apps/accounts/vault.py`, modify `settings/base.py`, NEW `seed_vault_service_keys.py`, new `test_vault_service_key_resolver.py`, NEW `docs/runbooks/vault-provisioning.md` | ~250-400 |

**Gate**: PR A merged.

### PR C — mTLS + Agent + Frontend (~700 lines)

**Repo**: DP4500 estandar + proyecto C (cross-repo).

| WU | Deliverable | Files | Lines |
|---|---|---|---|
| WU-4.4 | mTLS middleware + schema | NEW `client_cert_middleware.py`, modify `permissions.py`/`models.py:194-206`, new migration, modify `create_service_api_key.py:38-55`, new `test_mtls_required.py`, NEW `docs/runbooks/mtls-provisioning.md` | ~200-300 |
| WU-4.7 | Agent Python service | NEW `frontend/aesthetic-clinic/fingerprint-agent/{server.py,sdk_bridge.py,pyproject.toml,README.md}` | ~300-500 |
| WU-4.8 | Agent Windows installer | NEW `frontend/aesthetic-clinic/fingerprint-agent/installer/` | ~100-150 |
| WU-4.9 | Frontend fall-through wiring | `dp4500-capture-client.ts:333-549` | ~30-50 |
| WU-4.10 | E2E + HOW_TO_RUN | NEW `tests/e2e/fingerprint-agent.spec.ts`, `HOW_TO_RUN.md` extension | ~150-200 |

**Gate**: PR A + PR B merged.

**Master rollback**: revert 3 chained PRs in reverse order (PR C → PR B → PR A). DPIA sign-off status unaffected by code rollback.

---

## 5. Cross-repo Boundaries

Per deliverable, the file locations are explicit to prevent scope confusion:

| Deliverable | Repo | File paths |
|---|---|---|
| **#1 KMS envelope** | DP4500 estandar | `backend/apps/biometric/application/use_cases/enroll_service_identity.py:114-150` + `backend/apps/biometric/infrastructure/kms/{kms_factory.py, fake_kms_adapter.py}` (reused) |
| **#2 Rotation + cron** | DP4500 estandar | `backend/apps/accounts/api/views/rotate_service_api_key.py` (NEW) + `backend/apps/accounts/management/commands/migrate_service_api_keys.py` (NEW) + `backend/apps/biometric/api/urls.py` (modify) + `backend/config/celery.py` (modify) |
| **#3 mTLS** | DP4500 estandar | `backend/apps/biometric/api/middleware/client_cert_middleware.py` (NEW) + `backend/apps/accounts/models.py:194-206` (modify) + `backend/apps/accounts/migrations/000X_service_api_key_client_cert.py` (NEW) + `backend/apps/biometric/api/permissions.py` (modify) |
| **#4 DPIA** | DP4500 estandar | `docs/dpia/DP4500-DPIA.md` (modify) + `scripts/check_dpia_present.py` (modify) + `scripts/test_check_dpia.py` (modify) |
| **#5 Vault** | DP4500 estandar | `backend/apps/biometric/infrastructure/kms/vault_adapter.py` (modify) + `backend/apps/accounts/vault.py` (NEW) + `backend/config/settings/base.py` (modify) |
| **#6 Fingerprint-agent** | proyecto C | `frontend/aesthetic-clinic/fingerprint-agent/` (NEW directory tree) + `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts:333-549` (modify) + `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (NEW) + `frontend/aesthetic-clinic/HOW_TO_RUN.md` (modify) |

**No clinic-side backend changes** (proyecto C's `apps/biometric/*` is untouched for Phase 4). The frontend changes are entirely contained in `frontend/aesthetic-clinic/`.

---

## 6. Test Surface

Per the 4 delta specs:

| PR | Test files | Scenarios covered |
|---|---|---|
| **PR A** | `tests/integration/biometric/test_service_flow_kms_envelope.py` (NEW) | `biometric-template-storage` ADDED §1.1 "Service-flow envelope is real KMS" — assert non-zero `wrapped_dek`, AES-GCM round-trip, `key_version` parity with Knox-flow, audit emit on KMS failure. `tests/scripts/test_check_dpia.py` — bumped expected version 1.0 → 2.0. |
| **PR B** | `tests/integration/accounts/test_rotate_service_api_key.py` (NEW) + `tests/integration/accounts/test_vault_service_key_resolver.py` (NEW) | `service-api-authentication` ADDED §1.1 "Rotation in single transaction" (atomicity via `transaction.set_rollback(True)`), §1.2 "Audit emission carries `external_system=<key_name>`", §1.3 "Rotation idempotency", §1.4 "Vault handshake writes new + deletes old". `cascade-biometric-revoke` ADDED §1.1 "Rotation-key overlap on cascade audit chain". |
| **PR C** | `tests/integration/biometric/test_mtls_required.py` (NEW) + `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (NEW) | `service-api-authentication` ADDED §1.5 "mTLS handshake required when `DP4500_REQUIRE_MTLS=true`" (test cert → 200, no cert → 401 `mtls_required`, fingerprint mismatch → 401 `client_cert_mismatch`). `wizard-biometric-enrollment` ADDED §1.1 "Agent fall-through on `BiometricHardwareError`" (Playwright with mocked agent: SDK 30s timeout → fetch agent → success → audit; agent 503 → NO_AGENT terminal fallback). |

**Total new tests**: 5 (4 backend pytest + 1 Playwright e2e).

---

## 7. Test Patterns

Concrete enough for the apply phase to follow.

### Pattern A — KMS envelope swap

Mock the KMS backend via the Phase 1 `KmsFactory.get_kms()` selection. In the test, override `BIOMETRIC_KMS_BACKEND=fake` and inject a `FakeKmsAdapter` from `apps/biometric/infrastructure/kms/fake_kms_adapter.py:20-52`:

```python
def test_service_flow_envelope_uses_kms(monkeypatch, fake_kms):
    monkeypatch.setattr(settings, "BIOMETRIC_KMS_BACKEND", "fake")
    monkeypatch.setattr("apps.biometric.infrastructure.kms.kms_factory.get_kms", lambda: fake_kms)
    record = EnrollServiceIdentityUseCase()(user_external_id=uuid4(), template_b64=b"...")
    record.refresh_from_db()
    assert record.wrapped_dek != b"\x00" * 32  # not placeholder
    roundtrip = aesgcm_decrypt(fake_kms.unwrap_dek(record.wrapped_dek, record.key_version),
                                record.encrypted_fmd, record.server_aead_nonce,
                                aad=str(record.user_external_id).encode())
    assert roundtrip == expected_fmd_bytes
```

### Pattern B — Rotation endpoint

DRF test client setup; assert response shape per spec:

```python
@pytest.mark.django_db
def test_rotate_endpoint_creates_new_deactivates_old(api_client, active_service_key):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {active_service_key.raw_token}")
    resp = api_client.post(f"/api/biometric/service/keys/{active_service_key.pk}/rotate/",
                            {"name": "clinic-prod-v2"}, format="json")
    assert resp.status_code == 201
    assert set(resp.json()) == {"new_key_id", "raw_token", "rotated_from"}
    assert len(resp.json()["raw_token"]) == 43  # urlsafe-base64(32 bytes)
    active_service_key.refresh_from_db()
    assert active_service_key.is_active is False
    new = ServiceAPIKey.objects.get(pk=resp.json()["new_key_id"])
    assert new.rotated_from_id == active_service_key.pk
    audit = BiometricAuditEvent.objects.filter(event_type="service.api_key_rotated").get()
    assert audit.external_system == active_service_key.name
```

### Pattern C — mTLS handshake

Generate test client certs with `cryptography` in pytest fixtures:

```python
@pytest.fixture
def mtls_test_cert(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "test-workstation")]))
            .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, "test-ca")]))
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow()).not_valid_after(datetime.utcnow() + timedelta(days=1))
            .sign(private_key=key, algorithm=hashes.SHA256(), backend=default_backend()))
    fp = cert.fingerprint(hashes.SHA256()).hex()
    (tmp_path / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"fp": fp, "pem": cert.public_bytes(serialization.Encoding.PEM)}

def test_mtls_required_returns_401_when_cert_missing(api_client, settings):
    settings.DP4500_REQUIRE_MTLS = True
    resp = api_client.post("/api/biometric/service/keys/1/rotate/", {}, format="json")
    assert resp.status_code == 401
    assert resp.json()["code"] == "mtls_required"
```

### Pattern D — Vault resolver plugin dispatch

Test that `ACCOUNTS_KEY_STORE_BACKEND=vault` selects `vault_service_key_resolver` and `env` selects `env_key_resolver`:

```python
def test_vault_resolver_dispatch(monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNTS_KEY_STORE_BACKEND", "vault")
    monkeypatch.setattr("vault_client.secrets.kv.v2.read_secret")  # mock hvac
    resolver = get_service_key_resolver()
    assert resolver.__name__ == "vault_service_key_resolver"
    assert resolver(sucursal_id=42) == expected_token

def test_env_resolver_fallback(monkeypatch):
    monkeypatch.setattr(settings, "ACCOUNTS_KEY_STORE_BACKEND", "env")
    monkeypatch.setenv("DP4500_SERVICE_KEY_SUCURSAL_42", "tok-42")
    resolver = get_service_key_resolver()
    assert resolver(42) == "tok-42"
```

Use `pytest -m vault` marker to gate the real Vault testcontainer fixture (avoids Docker dependency in dev CI).

### Pattern E — Fingerprint-agent HTTP client (frontend)

Mock the local agent via MSW (Mock Service Worker) in Vitest + Playwright:

```typescript
// Vitest unit test
vi.mocked(global.fetch).mockResolvedValueOnce(
  new Response(JSON.stringify({ templateB64: "...", qualityScore: 87, deviceSerial: "X", width: 256, height: 360 }), { status: 200 })
);
const result = await captureFingerprint({ /* ... */ });
expect(result.templateB64).toBe("...");

// Playwright e2e with feature flag
await page.addInitScript(() => { window.__DP4500_USE_FINGERPRINT_AGENT__ = true; });
// WebSDK path throws BiometricHardwareError → agent fall-through fires → success
```

---

## 8. Risks

Per the explore.md R1-R5:

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | DPIA sign-off is multi-day regulatory work (5 signatures, 1-3 weeks each) | High (production-block) | Ship unsigned DPIA 2.0 + signature-pending checklist in `verify-report.md`. `BIOMETRIC_AUTH_ENABLED=true` flip BLOCKED on signed DPIA, not on code merge. Signature collection is a parallel workstream. |
| **R2** | mTLS + Vault + KMS rotation are infra-heavy (nginx config, Vault cluster, AWS KMS — all platform-team owned) | Medium | Each deliverable's `verify-report.md` section marks infra-dependent WUs explicitly. Runbooks at `docs/runbooks/{mtls-provisioning,vault-provisioning,kms-rotation}.md`. |
| **R3** | `fingerprint-agent` requires per-PC operator workstation setup (HID Authentication Device Client + Python service) | Medium | SDK-direct stays default; `DP4500_USE_FINGERPRINT_AGENT` defaults `false`; agent is opt-in per PC. NO_AGENT terminal fallback preserved. |
| **R4** | Cross-repo scope confusion (5 deliverables in DP4500 estandar, 1 in proyecto C) | Low (already mitigated by §5 explicit split) | §5 table lists every file path per deliverable + repo. Verify-report documents cross-repo test commands verbatim. |
| **R5** | `ServiceAPIKey.rotation` schema + endpoint tied via shared helper | Low | Single `_rotate_in_transaction(old, new_name)` helper consumed by DRF view, management command, AND Celery task. Tests assert atomicity via `transaction.set_rollback(True)` mid-test. |

---

## 9. Dependencies

Per-PR file list with line counts (estimates from explore §7.3).

### PR A — KMS + DPIA

| File | Lines |
|---|---|
| `backend/apps/biometric/application/use_cases/enroll_service_identity.py` (modify, lines 114-150) | ~30 |
| `backend/tests/integration/biometric/test_service_flow_kms_envelope.py` (NEW) | ~50 |
| `docs/dpia/DP4500-DPIA.md` (modify, extend §3, §8, §9) | ~100-150 |
| `scripts/check_dpia_present.py` (modify) | ~5 |
| `scripts/test_check_dpia.py` (modify) | ~5 |
| **Subtotal** | **~190-240** |

### PR B — Rotation + Vault

| File | Lines |
|---|---|
| `backend/apps/accounts/api/views/rotate_service_api_key.py` (NEW) | ~80 |
| `backend/apps/biometric/api/urls.py` (modify) | ~3 |
| `backend/apps/accounts/management/commands/migrate_service_api_keys.py` (NEW) | ~60 |
| `backend/config/celery.py` (modify) | ~10 |
| `backend/apps/biometric/infrastructure/kms/vault_adapter.py` (modify — implement 4 methods) | ~150-200 |
| `backend/apps/accounts/vault.py` (NEW) | ~40 |
| `backend/config/settings/base.py` (modify) | ~5 |
| `backend/apps/accounts/management/commands/seed_vault_service_keys.py` (NEW) | ~30 |
| `backend/docs/runbooks/vault-provisioning.md` (NEW) | ~50-100 |
| `backend/tests/integration/accounts/test_rotate_service_api_key.py` (NEW) | ~80 |
| `backend/tests/integration/accounts/test_vault_service_key_resolver.py` (NEW) | ~60 |
| **Subtotal** | **~568-668** |

### PR C — mTLS + Agent + Frontend

| File | Lines |
|---|---|
| `backend/apps/biometric/api/middleware/client_cert_middleware.py` (NEW) | ~40 |
| `backend/apps/biometric/api/permissions.py` (modify — add mTLS check) | ~20 |
| `backend/apps/accounts/models.py` (modify, lines 194-206) | ~5 |
| `backend/apps/accounts/migrations/000X_service_api_key_client_cert.py` (NEW) | ~15 |
| `backend/apps/accounts/management/commands/create_service_api_key.py` (modify, lines 38-55) | ~10 |
| `backend/config/settings/base.py` (modify — add `DP4500_REQUIRE_MTLS`) | ~3 |
| `backend/docs/runbooks/mtls-provisioning.md` (NEW) | ~50-100 |
| `backend/tests/integration/biometric/test_mtls_required.py` (NEW) | ~80 |
| `frontend/aesthetic-clinic/fingerprint-agent/server.py` (NEW) | ~80 |
| `frontend/aesthetic-clinic/fingerprint-agent/sdk_bridge.py` (NEW) | ~120 |
| `frontend/aesthetic-clinic/fingerprint-agent/pyproject.toml` (NEW) | ~20 |
| `frontend/aesthetic-clinic/fingerprint-agent/README.md` (NEW) | ~80 |
| `frontend/aesthetic-clinic/fingerprint-agent/installer/` (NEW — PyInstaller spec + Wix MSI XML) | ~100-150 |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` (modify, lines 333-549) | ~30-50 |
| `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (NEW) | ~120 |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` (modify — add agent install section) | ~30 |
| **Subtotal** | **~803-923** |

**Total estimated delta**: **~1561-1831 lines** (within the 1500-2500 budget).

---

## 10. Success Criteria

Phase 4 is closed when **all** hold:

- [ ] `python -m pytest` (DP4500 estandar) exits 0 for `test_service_flow_kms_envelope`, `test_rotate_service_api_key`, `test_mtls_required`, `test_vault_service_key_resolver`.
- [ ] `npx tsc -b --pretty false` + `npx eslint` (proyecto C frontend) exits 0 for the `fingerprint-agent` wiring in `dp4500-capture-client.ts`.
- [ ] **End-to-end (rotation)**: `POST /api/biometric/service/keys/<id>/rotate/` creates new key, marks old `is_active=False`, sets `rotated_from=<old>`, emits `BiometricAuditEvent` with `event_type=service.api_key_rotated`. `migrate_service_api_keys` exercises the same `_rotate_in_transaction`.
- [ ] **End-to-end (mTLS)**: workstation cert handshake against `/api/biometric/service/*` succeeds when `DP4500_REQUIRE_MTLS=true`; without cert → 401 `mtls_required`; fingerprint mismatch → 401 `client_cert_mismatch`.
- [ ] **DPIA v2.0** exists at `DP4500 estandar/docs/dpia/DP4500-DPIA.md` with signature-pending checklist (unsigned is OK). `scripts/check_dpia_present.py` exits 0.
- [ ] **Vault backend** exposes `vault_service_key_resolver(sucursal_id)` consumed by `get_service_key_resolver()` plugin dispatch at `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:279-281`.
- [ ] **Frontend fall-through**: when WebChannel host unavailable OR `DP4500_USE_FINGERPRINT_AGENT=true`, `captureFingerprint()` calls `fetch('http://127.0.0.1:8765/capture')`; agent 503 → NO_AGENT terminal fallback at `useConversionWizard.ts:842-859`.
- [ ] **Total changed lines**: 1500-2500 (3 chained PRs required).

### Verification gates

- **Archive gate** (this cycle): all 6 deliverables merged + DPIA v2.0 unsigned in repo + signature-pending checklist in `verify-report.md`.
- **Production gate** (post-archive): DPIA v2.0 signed by all 5 roles (DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair). `BIOMETRIC_AUTH_ENABLED=true` flip is BLOCKED on signed DPIA, not on code merge. Signature collection is a parallel workstream (typically 1-3 weeks).

---

## 11. Open Questions

None blocking. Resolved during exploration:
- **DPIA sign-off chain** (proposal §7 Q1): resolved to 5 roles (DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair; "Comité de Privacidad" → "Privacy WG chair").
- **mTLS cert authority** (proposal §7 Q2): platform-team decision at prod cutover (internal CA vs Let's Encrypt); Phase 4 ships the Django hook only.
- **Vault cluster topology** (proposal §7 Q3): platform-team decision at prod cutover (single-node dev vs HA prod); Phase 4 ships the adapter + resolver.
- **Fingerprint-agent feature flag name** (proposal §7 Q4): locked to `DP4500_USE_FINGERPRINT_AGENT` (defaults `false`).

---

## 12. References

- `proposal.md` (this cycle).
- `explore.md` (this cycle).
- 4 delta specs in `specs/`.
- `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:273-281` — `vault_key_resolver` plugin dispatch contract.
- `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172` — fingerprint-agent as Phase 4 fallback (not default).
- `DP4500 estandar/openspec/changes/archive/2026-09-13-dp4500-biometric-auth/` — Phase 1 KMS envelope at `finalize_enrollment.py:115-138`; audit precedent at `revoke_external_credential.py:53-64`; DPIA v1.0 template.
- `DP4500 estandar/docs/dpia/DP4500-DPIA.md` — DPIA v1.0 (§9 trigger list lines 233-239; sign-off block lines 241-247).
- `openspec/config.yaml:64` — `review_budget_lines: 400` (drives the 3-PR chain).