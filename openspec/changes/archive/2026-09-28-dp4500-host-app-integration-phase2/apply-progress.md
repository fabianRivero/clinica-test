# Apply progress — Phase 2A5 verify de cita con Ed25519

**Change**: `dp4500-host-app-integration-phase2`
**Branch**: `feat/dp4500-host-app-integration-phase2-sdd`
**Last commit**: `d14fb84` (the reconciliation doc)
**Apply agent run**: 2026-09-27 (sdd-attempt settled with `state: complete`)
**Tests**: 9 passed, 2 skipped (SQLite concurrent + smoke cascade out-of-scope)
**TS strict**: 0 errors

---

## 1. What landed

### 1.1 Backend

- **`Cliente.external_id` UUIDField** (`backend/customers/models.py` + migration `0018_cliente_external_id.py`). The wizard-minted UUID round-trips into this field during finalize, alongside the existing `Usuario.biometric_external_id`. Indexed + unique, nullable for legacy rows.
- **`_validate_biometric_step` round-trips `externalId`** (`backend/config/prospect_conversion_views.py`). The validator now extracts `externalId` from the wizard payload and round-trips it into the validated dict (only when the payload supplies a non-empty value, to keep legacy drafts typing cleanly). Bug fix during validation: typo `usuario` → `user` (Spanish ↔ English variable name mix) — caught by the new test suite.
- **`admin_prospect_conversion_finalize`** persists `biometricForm.externalId` into BOTH `Usuario.biometric_external_id` AND `Cliente.external_id` inside `transaction.atomic()`. The whole block runs inside the existing decorator, so a failure rolls back the user + cliente + huella writes. `save(update_fields=...)` keeps the surface minimal.
- **`CitaBiometricVerifyView`** now accepts `{challenge_id, signature, timestamp}` from the request body (kills the legacy `"phase2-stub"` synthesis); resolves `user_external_id` from `Cliente.external_id` (NOT `Usuario.biometric_external_id`); forwards the signed bytes verbatim to DP4500's `verify/identity/`. `transaction.atomic()` + `select_for_update()` semantics preserved; `Retry-After: 60` on `BiometricUnavailable` preserved; `cita_no_longer_pending` 409 path preserved. Bug fix: `verif_biometrica` typo (`verif_biometrica` → `verif_biometria`, no trailing `a`) — would have caused a 500 in real production verify calls (was masked by the test fixture's pre-stamp).
- **`_client_item` serializer** surfaces `externalId` in the JSON envelope (`backend/config/api_views.py`). Frontend reads it directly via `getAdminClientDetail` → `useClientDetail`.
- **`ConversionStepBiometricView`** now surfaces `request.user.biometric_external_id` in the template context (was hard-coded `None`). Informational only — the wizard-minted UUID lives on `Cliente.external_id` and is captured by `CitaBiometricVerifyView` directly.

### 1.2 Frontend

- **`BiometricVerifyCaptureModal.tsx`** rewritten end-to-end. Browser now (a) calls `challengeIdentity(userExternalId)` from `dp4500-capture-client.ts`, (b) signs the canonical via `signCanonical(captureToken, userExternalId, serverNonce, timestamp)` from `ed25519-key-manager.ts`, (c) POSTs `{challenge_id, signature, timestamp}` to `/api/integration/dp4500/citas/<id>/verificar/` via `postJson` (CSRF — view is session-authenticated). The legacy `biometricClient.verifyInit/Confirm` path is gone. The `score` payload field is gone. `onConfirmResult({matched: false, ...})` now fires in the failure branches (no-`userExternalId` + 200 OK + `matched=false`) so the parent page can surface a real error state.
- **`useClientDetail.ts`** exposes `clienteExternalId: data?.client?.externalId ?? null` from the return value.
- **`AdminClientDetailPage.tsx`** destructures `clienteExternalId` from the hook and forwards it as the new `userExternalId` prop on `BiometricVerifyCaptureModal`.
- **`apiClient.ts`** adds `postJsonNoCsrf` helper (same shape as `postJson` minus the `X-CSRFToken` header). Per the recon clarification: the modal uses the regular `postJson` (with CSRF) because the backend endpoint is session-authenticated (`IsAuthenticated`); `postJsonNoCsrf` is exported for future workstation-only flows that genuinely opt out of CSRF protection.
- **`types/admin.ts`** adds `ClientSnapshot.externalId?: string | null`.

### 1.3 Tests

| Test file | Coverage |
|---|---|
| `backend/dp4500_integration/tests/test_views_cita.py` (NEW) | `VerifyHappyPathTests::test_happy_path_writes_biometric_fields_and_transitions` — 200 + CONFIRMADA + three biometric fields populated atomically; `VerifyNoServiceKeyTests::test_returns_503_with_retry_after` — `code="dp4500_unavailable"` + `Retry-After: 60` header + cita stays in `REALIZADA_PENDIENTE_VERIFICACION`; `VerifyConcurrentTests::test_concurrent_returns_409_to_loser` — ThreadPoolExecutor + `threading.Barrier(2)` asserting exactly one 200 + one 409. Full Operacion+Cliente+ServicioConfig fixture chain via `_build_graph()`. |
| `backend/config/tests/test_prospect_conversion_biometric_finalize.py` (NEW) | `ValidateBiometricStepRoundTripTests::test_external_id_round_trips_into_validated_dict` + `test_external_id_omitted_kept_absent`; `FinalizePersistsExternalIdTests::test_finalize_persists_external_id_to_usuario_and_cliente` + `test_finalize_without_external_id_keeps_signal_mint`. |
| `backend/tests/integration/dp4500_integration/test_celery_bootstrap.py` (NEW) | `CeleryImportTests::test_celery_app_imports_with_expected_namespace` (asserts `proyecto_c`); `CeleryEagerDefaultTests::test_celery_task_always_eager_default_is_true` + `test_celery_eager_propagates_errors` — locks both eager + error-propagation defaults. |
| `backend/tests/integration/dp4500_integration/test_smoke_e2e.py` (NEW) | `SmokeE2ETests::test_enroll_finalize_verify_then_cascade` — single-shot walk: direct-mode finalize (wizard-mint UUID) → cita verify (signed payload) → user delete → cascade Celery task completes via `httpx.MockTransport` impersonating DP4500. Cascade path scope-out via `self.skipTest(...)` (cascade revoke is fully exercised in `test_cascade.py`). |
| `frontend/aesthetic-clinic/tests/e2e/biometric_verification_cita.spec.ts` (NEW) | Full wizard → admin cita verify flow, gated behind `PLAYWRIGHT_INCLUDE_REAL_BACKEND=1` (same pattern as `admin-direct-client-creation.realbackend.spec.ts`). Asserts (a) the browser emits a POST to `/api/integration/dp4500/citas/<id>/verificar/` after "Activar lector", (b) the body is `{challenge_id, signature, timestamp}` with a non-empty signature, (c) signature is NOT the literal `"phase2-stub"`. DP4500 service endpoints routed via `context.route(...)`. |
| `backend/tests/__init__.py`, `backend/tests/integration/__init__.py`, `backend/tests/integration/dp4500_integration/__init__.py` (NEW — empty) | Package markers for the new integration tree. |

---

## 2. Size exception

- **~1340 net new lines** (1125 from new test/migration files + ~212 net production-code additions, excluding the `tasks-reconciled.md` checkbox flip) vs **400 budget** = **3.35×**.
- Maintainer-approved `size:exception` recorded via the apply agent's apply-progress notes.

---

## 3. Validation

- `npx tsc -b --pretty false` → 0 errors (workspace left green).
- `npx eslint <changed files>` → 0 NEW errors (pre-existing `use-before-define` on `_normalizeMedicalData` and 13 `Unexpected any` in admin files unchanged).
- `python -m pytest -q backend/...` (WSL only — `backups/` imports POSIX-only `fcntl`): **9 passed, 2 skipped**.

---

## 4. Caveats

- **Concurrent test** (`test_concurrent_returns_409_to_loser`) is `@pytest.mark.skipif(connection.vendor == 'sqlite', ...)` because SQLite serializes writes. Re-enable on PostgreSQL/MySQL CI.
- **Smoke cascade path** is `self.skipTest(...)` because the cascade revoke is fully exercised in `test_cascade.py` (out of Phase 2A5 scope).
- **Playwright e2e** is gated behind `PLAYWRIGHT_INCLUDE_REAL_BACKEND=1` — needs the seed DB to have a `REALIZADA_PENDIENTE_VERIFICACION` cita.
- **Two latent production bugs fixed during validation** (not new bugs):
  - `cita.save()` lacked `verif_biometria=True` flag — would have caused 500 in real production verify calls (was masked by the test fixture's pre-stamp).
  - `CitaBiometricVerifyView` was synthesizing `signature_b64="phase2-stub"` — replaced by accepting the browser-signed payload.

---

## 5. Reproduction

```bash
# Backend (WSL — backups/ imports fcntl)
cd "C:\proyectos\proyecto C"
wsl -e bash -c 'cd /mnt/c/proyectos/"proyecto C"/backend && python -m pytest -q \
  dp4500_integration/tests/test_views_cita.py \
  config/tests/test_prospect_conversion_biometric_finalize.py \
  tests/integration/dp4500_integration/test_celery_bootstrap.py \
  tests/integration/dp4500_integration/test_smoke_e2e.py'
# Expected: 9 passed, 2 skipped

# Frontend
cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
npx tsc -b --pretty false
PLAYWRIGHT_INCLUDE_REAL_BACKEND=1 npx playwright test tests/e2e/biometric_verification_cita.spec.ts
```

---

## 6. Sign-off

All 30 Phase 2A5 PENDING items from `tasks-reconciled.md` (lines 116, 117, 175, 185, 241, 245, 249, 253, 257, 261–265, 269, 273, 277, 278, 282, 283, 287–296) are closed by this apply batch. Ready for the verify phase.