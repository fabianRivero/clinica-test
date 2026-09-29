# Proposal: Host-app integration — Phase 4 (Production-readiness)

**Change name**: `dp4500-host-app-integration-phase4-production-readiness`
**Artifact store**: openspec (this repo, the clinic)
**Status**: draft (will be locked after `sdd-tasks`)
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd` at `4ff5ca7`
**Predecessors (archived)**: Phase 1 (`DP4500 estandar/.../2026-09-13-dp4500-biometric-auth/`), Phase 2 + 2A4/5/6/7 (`.../2026-09-28-dp4500-host-app-integration-phase2*/`), Phase 3 + 3.1 (`.../2026-09-28-dp4500-host-app-integration-phase3-capture-client/` + commit `4ff5ca7`).

---

## 1. Title

**Phase 4 — Production-readiness** (KMS storage + key rotation + mTLS + DPIA v2.0 + vault + fingerprint-agent fallback).

---

## 2. Status

Draft (will be locked after `sdd-tasks`).

---

## 3. Background / Context

Phases 1–3.1 can capture, enroll, verify, revoke, and cascade-revoke end-to-end across both repos. The system is **not yet production-grade**. Six specific gaps block `BIOMETRIC_AUTH_ENABLED=true`:

1. **Placeholder bytes for service-flow KMS envelope.** `enroll_service_identity.py:114-123` writes 12 random nonce + 16 zero tag + 32 zero `wrapped_dek`. Knox-flow already wires real KMS at `finalize_enrollment.py:115-128`.
2. **`ServiceAPIKey.rotation` schema without endpoint.** `models.py:200-206` carries `rotated_from`; no HTTP endpoint drives rotation in the same transaction.
3. **Plaintext HTTP transport.** No mTLS client-cert validation in `apps/biometric/api/views/service/`.
4. **DPIA v1.0** was signed for Phase 1 only; §9 trigger list (lines 233-239) does not cover Phase 2 cross-system identity, Phase 3 Web SDK capture, or Phase 4 vault/KMS/mTLS.
5. **Vault backend is a TODO stub** at `apps/biometric/infrastructure/kms/vault_adapter.py`; only `env` resolver at `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:273-281` ships.
6. **`fingerprint-agent` fallback** documented at `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172` but not implemented.

Per session-2026-09-27 (Engram obs #53): **all six ship in ONE SDD cycle**. Per explore recommendation: cycle ships as **3 chained PRs** (1500-2500 line delta exceeds the 400-line review budget cap).

---

## 4. Q1 Decision (re-confirmed)

Phase 4 keeps Phase 3's Q1 (browser Web SDK direct) as **default**. `fingerprint-agent` becomes the **fallback** for environments where the SDK's WebChannel host is unavailable on the operator's real workstation. The NO_AGENT placeholder at `frontend/.../useConversionWizard.ts:842-859` remains the terminal fallback.

---

## 5. Scope

### 5.1 In scope (6 deliverables)

1. **KMS-backed envelope** for `BiometricTemplate.encrypted_fmd` on the service-flow path (`enroll_service_identity.py:114-150`).
2. **`ServiceAPIKey` rotation endpoint + Celery cron + audit** (`POST /api/biometric/service/keys/<id>/rotate/`, `migrate_service_api_keys`, `CELERY_BEAT_SCHEDULE`).
3. **mTLS** between workstation (browser or `fingerprint-agent`) and DP4500 (`client_cert_middleware.py`, `ServiceAPIKeyAuthentication` mTLS check, `client_cert_fingerprint` schema, runbook).
4. **DPIA v2.0** covering Phase 2/3/4 surface changes; unsigned 2.0 ships in `verify-report.md` as path + SHA-256 + signature-pending checklist.
5. **Vault backend** for `ServiceAPIKey` rotation secrets: implement `VaultKmsAdapter.wrap_dek/unwrap_dek/rotate/current_key_version`; add `vault_service_key_resolver()` to the plugin dispatch at `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:279-281`.
6. **`fingerprint-agent` fallback** for wizard capture path: Windows Python service on `127.0.0.1:8765` + `dp4500-capture-client.ts` fall-through.

### 5.2 Out of scope (post-Phase-4)

- Real hardware physical install (HID Authentication Device Client bootstrap, USB driver setup, workstation cert provisioning per PC).
- Ongoing DPIA renewal cadence (180-day review cycle per `DP4500-DPIA.md:6`).
- Production cron infrastructure outside test env (cron daemon, systemd, k8s CronJob — platform team).
- Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing.
- `Cliente.external_id` UUIDField finalize (per Phase 2A4 `explore-reconciliation.md §3.7` Disposition: "Reasign").
- Cross-repo merge of `feat/dp4500-host-app-integration-phase2-sdd` to main.
- `reconcile_pending_cascades` cron-driven automation (management command exists).

---

## 6. Affected components

### 6.1 DP4500 estandar (deliverables 1, 2, 3, 4, 5)

| Path | Change |
|---|---|
| `backend/apps/biometric/application/use_cases/enroll_service_identity.py:114-150` | REPLACE placeholder writes with real KMS envelope (mirror `finalize_enrollment.py:115-138`) |
| `backend/apps/biometric/infrastructure/kms/vault_adapter.py` | IMPLEMENT `wrap_dek`/`unwrap_dek`/`rotate`/`current_key_version` (Vault Transit) |
| `backend/apps/accounts/api/views/rotate_service_api_key.py` (NEW) | NEW DRF view: rotation in single `transaction.atomic()` |
| `backend/apps/accounts/management/commands/migrate_service_api_keys.py` (NEW) | NEW operator-facing wrapper (shares `_rotate_in_transaction`) |
| `backend/apps/accounts/management/commands/seed_vault_service_keys.py` (NEW) | NEW dev-env bootstrap helper |
| `backend/apps/accounts/models.py:194-206` | ADD `client_cert_fingerprint` (CharField, nullable, indexed) |
| `backend/apps/accounts/migrations/000X_service_api_key_client_cert.py` (NEW) | NEW migration |
| `backend/apps/accounts/management/commands/create_service_api_key.py:38-55` | ADD `--client-cert-fp` flag |
| `backend/apps/accounts/vault.py` (NEW) | NEW `vault_service_key_resolver()` + `get_service_key_resolver()` dispatch |
| `backend/apps/biometric/api/middleware/client_cert_middleware.py` (NEW) | NEW middleware reading `HTTP_X_SSL_CLIENT_FINGERPRINT` |
| `backend/apps/biometric/api/permissions.py` (or `apps/accounts/auth/auth.py`) | ADD mTLS check to `ServiceAPIKeyAuthentication` |
| `backend/apps/biometric/api/urls.py` | ADD `/service/keys/<id>/rotate/` route |
| `backend/config/settings/base.py` | ADD `DP4500_REQUIRE_MTLS`, `ACCOUNTS_KEY_STORE_BACKEND`, `VAULT_ADDR`, `VAULT_TOKEN` |
| `backend/config/celery.py` | ADD `CELERY_BEAT_SCHEDULE` for `migrate_service_api_keys` |
| `docs/dpia/DP4500-DPIA.md` | BUMP 1.0 → 2.0; EXTEND §3, §8, §9 |
| `scripts/check_dpia_present.py` + `scripts/test_check_dpia.py` | BUMP expected version 1.0 → 2.0 |
| `docs/runbooks/{mtls-provisioning,vault-provisioning}.md` (NEW) | NEW operator runbooks |
| `docs/runbooks/kms-rotation.md` | EXTEND with service-flow migration steps |
| `tests/integration/biometric/test_service_flow_kms_envelope.py` (NEW) | NEW integration test |
| `tests/integration/accounts/test_rotate_service_api_key.py` (NEW) | NEW integration test |
| `tests/integration/biometric/test_mtls_required.py` (NEW) | NEW integration test |
| `tests/integration/accounts/test_vault_service_key_resolver.py` (NEW) | NEW integration test |

### 6.2 proyecto C (deliverable 6 only)

| Path | Change |
|---|---|
| `frontend/aesthetic-clinic/fingerprint-agent/` (NEW) | NEW Python service: `server.py`, `sdk_bridge.py`, `pyproject.toml`, `README.md` |
| `frontend/aesthetic-clinic/fingerprint-agent/installer/` (NEW) | NEW Windows installer (PyInstaller or Wix MSI) |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts:333-549` | EXTEND `captureFingerprint()` with `fetch('http://127.0.0.1:8765/capture')` fall-through on `BiometricHardwareError` |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` | ADD "fingerprint-agent install" section |
| `frontend/aesthetic-clinic/tests/e2e/fingerprint-agent.spec.ts` (NEW) | NEW Playwright e2e with mocked agent |

### 6.3 Untouched

- `frontend/.../ed25519-key-manager.ts` (Phase 2A2).
- `frontend/.../useConversionWizard.ts:701-865` — NO_AGENT at 842-859 is the **terminal** fallback; Phase 4's agent fall-through is INSIDE `dp4500-capture-client.ts`.
- All Phase 1/2/2A6/2A7/3 archived artifacts.
- `openspec/specs/` main specs — Phase 4 may add delta specs under `openspec/changes/dp4500-host-app-integration-phase4-production-readiness/specs/`.

---

## 7. Open questions

1. **DPIA sign-off chain (multi-day regulatory, parallel to merge).** §9 sign-off block at `DP4500-DPIA.md:241-247` lists 5 roles; prose at line 251 says "four". Phase 4 **resolves to 5**: DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair ("Comité de Privacidad" → "Privacy WG chair"). **Not a pre-condition for SDD archive** — see §9 Verification gate.
2. **mTLS cert authority choice** — internal CA vs Let's Encrypt client certs. Phase 4 ships the Django hook; platform team picks at prod cutover.
3. **Vault cluster topology** — single-node dev vs HA prod. Phase 4 ships the adapter; HA is platform-team.
4. **`fingerprint-agent` opt-in flag name** — likely `VITE_DP4500_AGENT_FALLBACK_ENABLED`; finalize in `design.md`.

---

## 8. Rollback plan

Cycle is **NOT reversible as a single commit** — chain is forward-only. Each deliverable has a feature flag.

| Deliverable | Feature flag (default) | Rollback path |
|---|---|---|
| 1 — KMS envelope | `BIOMETRIC_KMS_BACKEND` (shipped) | Revert `enroll_service_identity.py:114-150` to placeholder bytes; Knox-flow unchanged. CI warns. |
| 2 — Rotation + cron | Route in `urls.py` | Disable `/service/keys/<id>/rotate/` route; `create_service_api_key --rotated-from` CLI still works. Drop `CELERY_BEAT_SCHEDULE` entry. |
| 3 — mTLS | `DP4500_REQUIRE_MTLS=false` | Set `false`; middleware becomes no-op. `client_cert_fingerprint` is nullable. |
| 4 — DPIA v2.0 | n/a (document) | Revert to v1.0; `scripts/check_dpia_present.py` fails CI intentionally until re-bumped. |
| 5 — Vault backend | `ACCOUNTS_KEY_STORE_BACKEND=env` | Set `env`; resolver falls back. `VaultKmsAdapter` remains wired but factory skips. |
| 6 — fingerprint-agent | `VITE_DP4500_AGENT_FALLBACK_ENABLED=false` | Set `false`; fall-through branch skipped; Phase 3 SDK-direct returns. Agent is opt-in per PC. |

**Master rollback**: revert 3 chained PRs in reverse order (PR C → PR B → PR A). DPIA sign-off status unaffected by code rollback.

---

## 9. Success criteria

Phase 4 is complete when **all** hold:

- [ ] `python -m pytest` (DP4500 estandar) exits 0 for `test_service_flow_kms_envelope`, `test_rotate_service_api_key`, `test_mtls_required`, `test_vault_service_key_resolver`.
- [ ] `npx tsc -b --pretty false` + `npx eslint` (proyecto C frontend) exit 0 for the `fingerprint-agent` wiring in `dp4500-capture-client.ts`.
- [ ] **End-to-end (rotation)**: `POST /api/biometric/service/keys/<id>/rotate/` creates new key, marks old `is_active=False`, sets `rotated_from=<old>`, emits `BiometricAuditEvent` with `event_type=service.api_key_rotated`; `migrate_service_api_keys` exercises the same `_rotate_in_transaction`.
- [ ] **End-to-end (mTLS)**: workstation cert handshake against `/api/biometric/service/*` succeeds when `DP4500_REQUIRE_MTLS=true`; without cert → 401 `mtls_required` or `client_cert_mismatch`.
- [ ] **DPIA v2.0** exists at `DP4500 estandar/docs/dpia/DP4500-DPIA.md` with signature-pending checklist (unsigned is OK — see §7 + §9 Verification gate). `scripts/check_dpia_present.py` exits 0.
- [ ] **Vault backend** exposes `vault_service_key_resolver(sucursal_id)` consumed by `get_service_key_resolver()` plugin dispatch at `archive/2026-09-28-dp4500-host-app-integration-phase2/design.md:279-281`.
- [ ] **Frontend fall-through**: when WebChannel host unavailable, `captureFingerprint()` falls through to `fetch('http://127.0.0.1:8765/capture')`; agent 503 → NO_AGENT terminal fallback at `useConversionWizard.ts:842-859`.
- [ ] **Total changed lines**: 1500-2500 (chain PRs required, see §10).

### Verification gate (archive vs production)

- **Archive gate**: all 6 deliverables merged + DPIA v2.0 unsigned in repo + signature-pending checklist in `verify-report.md`.
- **Production gate**: DPIA v2.0 signed by all 5 roles (DPO + CTO + Legal Counsel + Security Lead + Privacy WG chair). `BIOMETRIC_AUTH_ENABLED=true` flip is BLOCKED on signed DPIA, not on code merge. Signature collection is a parallel workstream (typically 1-3 weeks).

---

## 10. Delivery strategy

**Chain PRs are mandatory** — total estimated delta 1500-2500 lines; 400-line `review_budget_lines` cap from `openspec/config.yaml:64` exceeded by ~4×.

| PR | Repo(s) | WUs | Lines (est.) | Depends on |
|---|---|---|---|---|
| **PR A** — KMS storage + DPIA v2.0 | DP4500 estandar | WU-4.1 (KMS envelope), WU-4.5 (DPIA v2.0 + script bump) | ~500 | — |
| **PR B** — Rotation + Vault | DP4500 estandar | WU-4.2 (rotation endpoint), WU-4.3 (cron), WU-4.6 (vault backend) | ~600 | PR A |
| **PR C** — mTLS + fingerprint-agent + frontend | DP4500 estandar + proyecto C | WU-4.4 (mTLS), WU-4.7 (agent service), WU-4.8 (installer), WU-4.9 (frontend fall-through), WU-4.10 (e2e + runbook) | ~700 | PR A, PR B |

PR C gated on PR A + PR B; PR B gated on PR A. Cycle closes when all three merge and `verify-report.md` documents cross-repo test commands.

---

## 11. References

- `openspec/changes/dp4500-host-app-integration-phase4-production-readiness/explore.md` (this cycle).
- `archive/2026-09-28-dp4500-host-app-integration-phase2/{proposal,design}.md` (Phase 2 — `env_key_resolver` at `design.md:273-281`).
- `archive/2026-09-28-dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md:172` (Phase 3 fallback contract).
- `DP4500 estandar/openspec/changes/archive/2026-09-13-dp4500-biometric-auth/` (Phase 1 — KMS envelope at `finalize_enrollment.py:115-138`; audit precedent at `revoke_external_credential.py:53-64`; DPIA v1.0 template).
- `DP4500 estandar/docs/dpia/DP4500-DPIA.md` (DPIA v1.0 — §9 trigger list lines 233-239; sign-off block lines 241-247).
- `openspec/config.yaml:64` (`review_budget_lines: 400` — drives the 3-PR chain).

---

## 12. Predecessor artifact chain

```
Phase 1 → Phase 2 + 2A4/5/6/7 → Phase 3 + 3.1
  ↓
explore.md (this cycle)
  ↓
proposal.md  ← THIS FILE
  ↓
specs/*/spec.md
  ↓
design.md → tasks.md
  ↓
apply → verify → archive (3 chained PRs)
```

---

**Awaiting user review before proceeding to `spec.md`.**
