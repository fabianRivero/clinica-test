# Tasks: Production-readiness (Phase 4 of dp4500-host-app-integration-phase2)

**Change name**: `dp4500-host-app-integration-phase4-production-readiness`
**Artifact store**: openspec
**Delivery strategy**: `chain` (3 chained PRs required per design.md §4)
**Chain strategy**: `stacked-to-main` (PR A → PR B → PR C in sequence)
**Predecessors**: proposal.md + design.md + 4 delta specs (locked)

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1500-2500 across 3 chained PRs. |
| 400-line budget risk | **HIGH** — each PR is over the cap. |
| Chained PRs recommended | **YES** — PR A → PR B → PR C. |
| Suggested commit split | Per-PR with RED/GREEN pairs. |
| Delivery strategy | `chain` |
| Chain strategy | `stacked-to-main` |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 4.A.1 | KMS-backed envelope for `BiometricTemplate.encrypted_fmd` on service-flow path | PR A | `pytest backend/tests/integration/biometric/test_service_flow_kms_envelope.py -q` | Django test DB + `BIOMETRIC_KMS_BACKEND=simulator` | Revert `enroll_service_identity.py:114-150` to placeholder bytes; Knox-flow unchanged. |
| 4.A.2 | DPIA v2.0 + script version bump | PR A | `python scripts/check_dpia_present.py`; `pytest scripts/test_check_dpia.py -q` | Standalone script + pytest | Revert DPIA to v1.0; `scripts/check_dpia_present.py` fails CI intentionally. |
| 4.B.1 | `ServiceAPIKey` rotation endpoint + atomicity + audit | PR B | `pytest backend/tests/integration/accounts/test_rotate_service_api_key.py -q` | DRF test client + `transaction.set_rollback(True)` | Disable `/service/keys/<id>/rotate/` route in `urls.py`; `--rotated-from` CLI still works. |
| 4.B.2 | `migrate_service_api_keys` management command + Celery beat schedule | PR B | `pytest backend/tests/integration/biometric/tasks/test_rotate_via_celery.py -q` | Celery eager mode | Disable beat schedule; command is idempotent. |
| 4.B.3 | Migration management command (`migrate_service_api_keys`) | PR B | `pytest backend/tests/unit/accounts/management/test_migrate_service_keys.py -q` | management command runner | Drop the command; DRF path still works. |
| 4.B.4 | Vault backend for `ServiceAPIKey` rotation secrets | PR B | `pytest backend/tests/unit/accounts/test_vault.py -q` | Mock `hvac` client | Set `ACCOUNTS_KEY_STORE_BACKEND=env`; resolver falls back. |
| 4.C.1 | mTLS middleware + `client_cert_fingerprint` schema | PR C | `pytest backend/tests/integration/biometric/api/test_mtls.py -q` | DRF test client + `cryptography`-generated cert | Keep `DP4500_REQUIRE_MTLS=false`; middleware no-op. |
| 4.C.2 | `fingerprint-agent` Python service (backend) | PR C | `pytest fingerprint-agent/tests/test_capture_endpoint.py -q` | FastAPI TestClient + `pytest-asyncio` | Feature-flagged off; frontend falls back to NO_AGENT. |
| 4.C.3 | Frontend `captureFingerprint()` agent fall-through | PR C | `cd frontend/aesthetic-clinic && npx vitest run src/services/biometric/__tests__/dp4500-capture-client.test.ts` | Vitest + MSW | Revert to Phase 3.1; SDK-only path returns. |

---

## Phase 4 PR A — KMS + DPIA (~190-240 lines)

### 4.A.1 KMS-backed envelope (Deliverable #1)

- [x] 4.A.1.1 RED `tests/unit/biometric/infrastructure/test_kms_envelope.py::test_kms_wrap_dek_roundtrip`. Set `BIOMETRIC_KMS_BACKEND=simulator`. Generate a 32-byte DEK. Call `kms.wrap_dek(dek)`. Assert ciphertext is non-empty AND decrypts back to the original DEK.
- [x] 4.A.1.2 RED same file `::test_enroll_persists_kms_envelope_not_placeholder`. Set `BIOMETRIC_KMS_BACKEND=simulator`. Call `EnrollServiceIdentity().execute(...)`. Assert `BiometricTemplate.wrapped_dek != b'\x00' * 32` (not the placeholder bytes). Assert `BiometricTemplate.server_aead_nonce` is non-empty (not the placeholder 12-byte zero nonce).
- [x] 4.A.1.3 GREEN: edit `apps/biometric/application/use_cases/enroll_service_identity.py:114-150` to use `kms.wrap_dek(dek)` + AES-GCM with the fresh DEK.
- [x] 4.A.1.4 RED `tests/unit/biometric/infrastructure/test_kms_envelope.py::test_kms_unavailable_raises`. Set `BIOMETRIC_KMS_BACKEND=unavailable`. Generate a DEK. Assert `kms.wrap_dek(dek)` raises `BiometricUnavailable('kms_unavailable')`.

### 4.A.2 DPIA v2.0 (Deliverable #4)

- [x] 4.A.2.1 RED `docs/dpia/DP4500-DPIA.md::version_check`. Run `scripts/check_dpia_present.py`. Assert it accepts the v1.0 + flags v2.0 unsigned as "ready for signature".
- [x] 4.A.2.2 GREEN: edit `docs/dpia/DP4500-DPIA.md` to bump v1.0 → v2.0. Extend §3 (data inventory: cross-system handle `Cliente.external_id`), §8 (security controls: browser Web SDK + Vault + mTLS), §9 (compliance: signature-pending checklist with 5 roles).
- [x] 4.A.2.3 GREEN: edit `scripts/check_dpia_present.py` to expect v2.0 + unsigned (not v1.0 + signed).

**End of PR A. Commit: `feat(dp4500): KMS-backed enrollment storage + DPIA v2.0 (Phase 4 PR A)`.**

---

## Phase 4 PR B — Rotation + Vault (~568-668 lines)

### 4.B.1 ServiceAPIKey rotation endpoint (Deliverable #2)

- [ ] 4.B.1.1 RED `tests/integration/biometric/api/test_service_key_rotate.py::test_rotate_endpoint_creates_new_key`. Authenticate as admin. POST `/api/biometric/service/keys/<id>/rotate/`. Assert response 201 with `{ok: true, key_id: <new>, rotated_from: <old>, audit_hash: <hex>}`.
- [ ] 4.B.1.2 RED same file `::test_rotate_endpoint_rejects_unauthenticated`. POST without bearer token. Assert 401.
- [ ] 4.B.1.3 RED same file `::test_rotate_endpoint_rejects_old_key_replay`. POST with the rotated (now-inactive) key. Assert 401 with `code: service_key_inactive`.
- [ ] 4.B.1.4 GREEN: edit `apps/biometric/api/views/service/__init__.py` to add `ServiceAPIKeyRotateView`. Use `_rotate_in_transaction(old, new_name)` helper.

### 4.B.2 Rotation Celery task

- [ ] 4.B.2.1 RED `tests/integration/biometric/tasks/test_rotate_via_celery.py::test_rotate_task_emits_audit_with_external_system`. Eager mode. Call `rotate_service_api_keys()`. Assert `BiometricAuditEvent.objects.filter(external_system='<key_name>', event_type='SERVICE_KEY_ROTATION').count() == 1`.

### 4.B.3 Migration management command

- [ ] 4.B.3.1 RED `tests/unit/accounts/management/test_migrate_service_keys.py::test_migrate_creates_marker_for_legacy_key`. Create a legacy ServiceAPIKey (no rotation metadata). Run `migrate_service_api_keys`. Assert a marker row exists with `rotated_from=None`.

### 4.B.4 Vault backend (Deliverable #5)

- [ ] 4.B.4.1 RED `tests/unit/accounts/test_vault.py::test_vault_service_key_resolver_returns_key_for_known_sucursal`. Pre-populate vault with a known key. Call `vault_service_key_resolver(sucursal_id)`. Assert returns the known key.
- [ ] 4.B.4.2 RED same file `::test_vault_service_key_resolver_falls_back_to_env`. Vault empty. Set env var `DP4500_SERVICE_KEY_SUCURSAL_<id>=<key>`. Call resolver. Assert returns the env key.
- [ ] 4.B.4.3 RED same file `::test_vault_service_key_resolver_rotates`. Vault has expired key. Assert resolver triggers rotation.
- [ ] 4.B.4.4 GREEN: implement `apps/accounts/vault.py` with `vault_service_key_resolver()` + `get_service_key_resolver()` plugin dispatch.

**End of PR B. Commit: `feat(dp4500): ServiceAPIKey rotation + Vault backend (Phase 4 PR B)`.**

---

## Phase 4 PR C — mTLS + Agent + Frontend (~803-923 lines)

### 4.C.1 mTLS middleware (Deliverable #3)

- [ ] 4.C.1.1 RED `tests/integration/biometric/api/test_mtls.py::test_mtls_match_succeeds`. Generate a test client cert. Configure `DP4500_REQUIRE_MTLS=True`. POST `/api/biometric/service/identity/enroll/` with cert + matching fingerprint. Assert 201.
- [ ] 4.C.1.2 RED same file `::test_mtls_missing_returns_401`. No cert. Assert 401 with `code: mtls_required`.
- [ ] 4.C.1.3 RED same file `::test_mtls_mismatch_returns_401`. Cert with different fingerprint. Assert 401 with `code: client_cert_mismatch`.
- [ ] 4.C.1.4 GREEN: implement `apps/biometric/api/middleware/client_cert_middleware.py` + `client_cert_fingerprint` CharField on `ServiceAPIKey`.

### 4.C.2 Fingerprint-agent service (Deliverable #6 — backend)

- [ ] 4.C.2.1 RED `fingerprint-agent/tests/test_capture_endpoint.py::test_capture_returns_204_with_template_b64`. POST `/capture` with valid payload. Assert 204 + `{template_b64, quality_score, device_serial}`.
- [ ] 4.C.2.2 RED same file `::test_capture_returns_503_when_no_reader`. Service has no reader. Assert 503.
- [ ] 4.C.2.3 GREEN: implement `fingerprint-agent/main.py` + `fingerprint-agent/Dockerfile` + `fingerprint-agent/install-windows.ps1`.

### 4.C.3 Frontend fall-through (Deliverable #6 — frontend)

- [x] 4.C.3.1 RED `frontend/.../__tests__/dp4500-capture-client.test.ts::captureFingerprint_falls_through_to_fingerprint_agent_on_SDK_timeout`. Mock `window.Fingerprint.WebApi` to never resolve `onAcquisitionStarted`. Mock `fetch` to call the local agent. Assert `captureFingerprint()` calls the agent and resolves with the agent's response.
- [x] 4.C.3.2 RED same file `::captureFingerprint_falls_through_to_NO_AGENT_when_agent_disabled`. Feature flag `DP4500_USE_FINGERPRINT_AGENT=false`. Mock SDK to timeout. Assert `captureFingerprint()` rejects with `BiometricHardwareError` (terminal NO_AGENT fallback).
- [x] 4.C.3.3 RED same file `::captureFingerprint_returns_503_when_agent_unavailable`. Agent returns 503. Assert `captureFingerprint()` rejects with `BiometricUnavailable('service_unavailable')`.
- [x] 4.C.3.4 GREEN: extend `dp4500-capture-client.ts::captureFingerprint()` with the agent fall-through path. Feature flag `DP4500_USE_FINGERPRINT_AGENT` defaults to `false`.

**End of PR C. Commit: `feat(dp4500): mTLS workstation auth + fingerprint-agent fallback (Phase 4 PR C)`.**

---

## Pre-apply (verify phase)

- [ ] All 3 PRs merged to main.
- [ ] DPIA v2.0 unsigned with signature-pending checklist.
- [ ] `BIOMETRIC_AUTH_ENABLED=true` NOT yet flipped (waits for DPIA signatures).
- [ ] `DP4500_REQUIRE_MTLS=false` in dev, `true` in prod (env-flagged).
- [ ] No production cron setup required for tests; rotation Celery beat deferred to platform team.

## Post-apply (archive phase)

- [ ] Write `archive-report.md` covering the 3 chained PRs, the 6 deliverables, the DPIA sign-off chain (5 roles), and the test counts.