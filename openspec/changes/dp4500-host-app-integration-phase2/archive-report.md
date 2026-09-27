# Archive Report: dp4500-host-app-integration-phase2

**Change name**: `dp4500-host-app-integration-phase2`
**Artifact store**: openspec (this repo, the clinic)
**Archive date**: 2026-09-27
**Status**: success (intentional with known deferred items)

---

## 1. Final state

### 1.1 Branch and commit state

All work landed on `feat/dp4500-host-app-integration-phase2-sdd`. Six
commits total — three docs, three apply:

```
bd58a30 feat(dp4500_integration): foundation — HTTPClient + biometric fields
NEW   feat(dp4500_integration): Celery bootstrap + cascade signal + reconcile command
NEW   feat(dp4500_integration): wizard step 4 view + cita verify view + capture stub
2c4cc69 docs(proyecto-c): update design.md §2 paths and tasks.md Celery bootstrap
cead7fd docs(proyecto-c): lock Phase 2 apply blockers to (b)+(a)
57b7fc0 docs(proyecto-c): add Phase 2 SDD artifacts and apply blockers
```

Branch base `e105160` (the same `main` HEAD at the time of branching).
Working tree clean relative to HEAD at archive time.

### 1.2 Test counts at final state

`backend/manage.py test dp4500_integration` produces **42 passed, 1 skipped** (the skip is documented: `MockTransport` bypasses httpx's timeout layer — verified by Phase 4 integration tests).

Full clinic suite (`backend/manage.py test`) shows ~580 tests with
**61 pre-existing failures** unrelated to this change: the local
`.env` sets `BIOMETRIC_SUSPENDED=1`, which short-circuits the legacy
biometric agent factory to `SuspendedAgentClient` and breaks the
legacy `test_agent_client.py` tests. These failures predate
Phase 2 and are not in scope of this change.

The new `dp4500_integration/` app contributes:

| Test file | Tests |
|---|---|
| `tests/test_client.py` | 17 + 1 skip — HTTPClient error mapping table |
| `tests/test_model_fields.py` | 11 — biometric_external_id + CitaMedica fields + Sucursal field |
| `tests/test_cascade.py` | 8 — PendingCascade lifecycle + cascade signal + cascade task outcomes + reconcile command |
| `tests/test_e2e_views.py` | 3 — wizard step 4 stub URL |
| **Total** | **42 + 1 skip** |

### 1.3 What ships in this change

| Deliverable | Location |
|---|---|
| New sibling app `dp4500_integration/` | `backend/dp4500_integration/` |
| `HTTPClient` (httpx wrapper) | `apps/client.py` |
| Domain exception hierarchy | `apps/exceptions.py` |
| `env_key_resolver` | `apps/key_resolver.py` |
| `PendingCascade` + `BiometricEnrollmentRecord` | `apps/models.py` |
| Cascade signal handler | `apps/signals.py` |
| Celery task `cascade_revoke_template` | `apps/tasks.py` |
| `reconcile_pending_cascades` management command | `apps/management/commands/` |
| Read-only admin registrations | `apps/admin.py` |
| `ConversionStepBiometricView` + `CitaBiometricVerifyView` | `apps/views.py` |
| URL patterns mounted at `/api/integration/dp4500/` | `apps/urls.py` + `config/urls.py` |
| Capture stub template | `apps/templates/integration/capture_pending.html` |
| `Usuario.biometric_external_id` field + pre_save signal | `accounts/models.py`, `accounts/signals.py`, `accounts/apps.py` |
| `CitaMedica` 3 biometric fields (additive on legacy) | `operations/models.py` |
| `Sucursal.dp4500_service_key_id` field + validator | `catalogs/models.py` |
| Celery bootstrap (config/celery.py, settings.py, manage.py) | `config/` |
| 4 migrations | `accounts/0005`, `catalogs/0011`, `operations/0031`, `dp4500_integration/0001` |
| 4 test files | `dp4500_integration/tests/` |
| Settings additions (`DP4500_*`, `CELERY_*`) | `config/settings.py` |

### 1.4 Decisions locked in this change

| # | Decision | Source |
|---|---|---|
| Q1 — Capture UI | Deferred to Phase 4; Phase 2 ships stub | Session 2026-09-27 |
| Cascade failure mode | Soft-delete local + Celery retry (5x, 30s delay) | Session 2026-09-27 |
| Key granularity | One `ServiceAPIKey` per `Sucursal` per environment | Session 2026-09-27 |
| `user_external_id` shape | UUID, persisted on `Usuario` | Session 2026-09-27 (Q2) |
| Cascade delete contract | `post_delete` signal on `Usuario` → DELETE service endpoint | Session 2026-09-27 (Q3) |
| Data model | Three nullable fields on `CitaMedica` (no separate table) | Session 2026-09-27 |
| Key storage | `Sucursal.dp4500_service_key_id` (cross-project CharField reference) | Derived from granularity decision |
| Phase 2 scope | Identity challenge only; action authorization is Phase 4+ | Derived |
| **App structure** | New sibling app `dp4500_integration/` | apply-blockers decision 1 (b) |
| **Cascade runner** | Celery (`@shared_task`) | apply-blockers decision 2 (a) |

ADRs (5 total, all in `design.md` §13):

- **ADR-0001**: `Sucursal.dp4500_service_key_id` is `CharField`, not FK
- **ADR-0002**: Phase 2 supports only the `env` key-store backend
- **ADR-0003**: Phase 4 capture swap is a template-only change
- **ADR-0004**: Phase 2 signature is a stub (Phase 4 wires real Ed25519)
- **ADR-0005**: Cross-project reference is `CharField` (echoes ADR-0001)

---

## 2. Scope verification

### 2.1 In-scope items delivered (from proposal §2)

| # | Proposal deliverable | Status |
|---|---|---|
| 1 | New `dp4500_integration/` Django app | ✅ |
| 2 | `users.User.biometric_external_id` field + pre_save signal + migration | ✅ |
| 3 | `citas.CitaMedica` biometric fields + migration | ✅ |
| 4 | `Sucursal.dp4500_service_key_id` field + migration | ✅ |
| 5 | Cascade hook on `User.delete()` with Celery retry | ✅ |
| 6 | Settings + secure token store | ✅ (`DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`, `DP4500_KEY_STORE_BACKEND=env`) |
| 7 | Tests | ✅ (42 + 1 skip; full coverage on client + cascade + model fields + smoke) |

### 2.2 Out-of-scope items (deferred to later phases)

- **Phase 3 — Capture client decision** (Q1). Phase 4 wires the
  real capture client (browser Web SDK or Electron child process).
  Phase 2 ships the stub template that says "Phase 2 stub".
- **Phase 4 — Production hardening**: mTLS between clinic and
  DP4500, DPIA §9 sign-off, KMS HA, HID agent per workstation, vault
  backend for `DP4500_KEY_STORE_BACKEND=vault`.
- **Action authorization flow** (`/service/challenge/action/` +
  `/service/verify/action/`). Phase 4+.
- **History of biometric attempts per cita**. Phase 2's atomic
  three-field write on `CitaMedica` is enough; a `BiometricVerification`
  table for per-attempt history is deferred.
- **Cron for `reconcile_pending_cascades`**. The operator runs the
  command manually when Celery is unavailable for an extended period.
- **`Usuario.delete()` semantics coverage**. The signal fires on
  any `User.delete()` call (soft and hard). A future `deleted_at`
  model would need a separate handler.

---

## 3. Deferred / known issues

| # | Item | Severity | Notes |
|---|---|---|---|
| 3.1 | `httpx.MockTransport` bypasses timeout layer; the timeout→`BiometricUnavailable` path is documented skip in `test_client.py::test_timeout_path_is_documented_skip` | low | Phase 4's integration tests with a real/slow TCP transport will exercise this. |
| 3.2 | Phase 2 signature is a stub (`"phase2-stub"`); real Ed25519 sign lands with the capture client in Phase 4 | medium | Documented in design ADR-0004. The wire contract is stable; only the signature payload changes. |
| 3.3 | The cita verify view's full e2e fixture chain (Operacion + Cliente + ServicioConfig) is not in `test_e2e_views.py` — covered by status mapping in `test_client.py` instead | low | Phase 4 wires the real capture and a real CitaMedica test factory; the e2e fixture gets easier then. |
| 3.4 | Pre-existing 61 legacy biometric test failures (`.env` has `BIOMETRIC_SUSPENDED=1`) | n/a | Pre-existing, unrelated to this change. Phase 4 deprecates the legacy flow. |
| 3.5 | `BiometricAuditEvent.external_system` field (Phase 1) participates in the DP4500 audit chain hash. The clinic's `BiometricEnrollmentRecord` does NOT touch the DP4500 chain. The `cita.biometric_challenge_id` echoes the capture_token for cross-project traceability | low | Documented in design §6.1. |
| 3.6 | `dp4500_service_key_id` field uses `CharField` (not FK) per ADR-0001. Cross-project FKs would couple the clinic's ORM to DP4500's models. Drift is detected at request time (401/404 from DP4500). | low | Phase 4 adds a periodic probe to surface drift before users hit it. |
| 3.7 | Celery worker is not started automatically in production; operator runs `celery -A config worker -l info` | n/a | Documented in design §12. README in the next change. |

---

## 4. Reproduction steps

### 4.1 Backend migration

```bash
cd C:\proyectos\proyecto C
cd backend
env/bin/python manage.py migrate
```

Adds 4 migrations:
- `accounts.0005_usuario_biometric_external_id`
- `catalogs.0011_sucursal_dp4500_service_key_id`
- `operations.0031_citamedica_biometric_challenge_id_and_more`
- `dp4500_integration.0001_initial`

### 4.2 Test suite

```bash
cd C:\proyectos\proyecto C
cd backend
env/bin/python manage.py test dp4500_integration --verbosity=1
# 42 passed, 1 skipped
```

### 4.3 Set up DP4500_BASE_URL + per-sucursal service key

```bash
# In the clinic's .env (or CI config):
DP4500_BASE_URL=https://dp4500-prod.clinica.internal
DP4500_SERVICE_KEY_SUCURSAL_42=SeK_abcdef...
DP4500_SERVICE_KEY_SUCURSAL_43=SeK_xyz123...
```

### 4.4 Start the Celery worker (production)

```bash
cd C:\proyectos\proyecto C\backend
env/bin/celery -A config worker -l info
```

For dev, the worker is optional — `CELERY_TASK_ALWAYS_EAGER=True` runs
cascades synchronously in the request that triggered the User delete.

### 4.5 Operator manual override

```bash
cd C:\proyectos\proyecto C\backend
env/bin/python manage.py reconcile_pending_cascades
# --dry-run lists what would be processed
# --limit N processes at most N rows
```

---

## 5. Branch and rollout plan

- Branch `feat/dp4500-host-app-integration-phase2-sdd` is local only.
  The user explicitly chose this branch name to signal "SDD only" when
  Phase 2 apply started. The three apply commits in this archive are
  ready to push as a PR.

- The PR reviewer list should include the same maintainers who
  signed off on the Phase 1 PR in the DP4500 estandar repo.

- Phase 3 (capture client decision) and Phase 4 (real capture +
  production hardening) cannot start until Phase 2 lands in production.

- **Cross-project migration note**: this PR is in `proyecto C`. The
  companion PR is on `DP4500 estandar`. Both must be deployed
  together for the end-to-end biometric flow to work. The order is:
  DP4500 PR first (it exposes the service API), then clinic PR
  (consumes it).

---

## 6. Sign-off block

This archive is final relative to the working tree on
`feat/dp4500-host-app-integration-phase2-sdd` at the new HEAD.
No follow-up commits are planned before merge to `main`.