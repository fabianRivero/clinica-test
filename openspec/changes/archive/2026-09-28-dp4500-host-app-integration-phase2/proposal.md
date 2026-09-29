# Proposal: Host-app integration — Phase 2 (Clinic side)

**Change name**: `dp4500-host-app-integration-phase2`
**Artifact store**: openspec (this repo, the clinic)
**Status**: draft (predecessors: Phase 1 service API in dp4500 estandar, plan §2026-09-27)
**Predecessors**:
- `docs/plans/2026-09-27-biometric-web-integration.md` — two-system architecture plan.
- Phase 1 in the sibling DP4500 estandar repo: `openspec/changes/dp4500-host-app-integration-phase1/`. The service API surface is the contract this proposal depends on.

This proposal opens a **new** change directory in this repo (the clinic,
`C:\proyectos\proyecto C`). Phase 2 mirrors Phase 1's SDD structure but
focuses on the host-app side: how the clinic consumes the DP4500 service
API for two flows (enrollment + cita verification) without ever seeing
fingerprint bytes.

---

## 1. Why

### Problem statement

The clinic today has no real biometric verification on its cita
workflow. Two workflows that need it:

1. **Step 4 of the prospect → cliente conversion wizard**: capture
   the new client's fingerprint so future citas can be verified.
2. **Cita verification at check-in** (`CitaMedica.estado` transitions
   from `REALIZADA_PENDIENTE_VERIFICACION` → `CONFIRMADA`): today the
   receptionist clicks "Confirmar manualmente" because there is no
   biometric path.

Phase 1 of the host-app integration landed the **service side** in the
sibling repo: `C:\proyectos\DP4500 estandar\`. Five REST endpoints +
auth + audit chain are operational there. This proposal covers the
**host side** — the glue that lets the clinic call those endpoints.

### Motivation

- **No fingerprint bytes cross the host boundary.** The clinic's
  Django ORM stores `biometric_challenge_id`, `biometric_match_confidence`,
  and metadata — never template bytes. GDPR Article 9 stays in DP4500.
- **Explicit separation of capture from verification.** The wizard's
  step 4 enrolls (one-time); the cita verification later is a separate
  use case that re-uses the identity-challenge machinery.
- **Per-branch service keys.** Each `Sucursal` of the clinic has its
  own `ServiceAPIKey` against DP4500 — blast radius is per branch, not
  per clinic, not per environment.
- **Soft-delete with retry.** Operators never get blocked by DP4500
  being down; the cascade hook stores a "pending cascade" mark and
  retries in the background, alerting after N retries.

### Business value

- Real biometric verification on cita check-in, per branch, no
  operator blocking.
- Every cita verification produces an audit row with the calling
  branch's `external_system` set (Phase 1 invariant preserved).
- Granular blast radius: a compromised PC only compromises one
  branch's key, which can be revoked without affecting other branches.
- Clean migration path to Phase 4 (real capture client + mTLS) — the
  data model and HTTP client survive unchanged.

---

## 2. What changes

Six concrete deliverables, all in this repo.

### 2.1. New `biometric/` Django app

A small app that wraps the DP4500 HTTP client. Layered:

```
biometric/
├── apps.py
├── client.py                    # Single HTTPClient class (httpx-based)
│                                 #   with .enroll(...), .verify(...), .delete_template(...)
├── views.py                     # Two clinical views, thin over client
├── urls.py                      # /citas/<id>/verificar/, /wizard/enroll/
├── exceptions.py                # BiometricUnavailable, BiometricEnrollConflict,
│                                 # BiometricMismatch, BiometricRateLimited ...
├── migrations/0001_initial.py
├── templates/biometric/
│   └── capture_pending.html      # Stub UI; Phase 4 will replace
└── tests/
    ├── test_client.py           # httpx MockTransport cases
    ├── test_views.py
    └── test_cascade.py
```

The app **does no crypto**. It translates HTTP errors from DP4500 into
domain-level exceptions, surfaces them to views, and stores nothing
about fingerprints beyond the `challenge_id` / `match_confidence`
metadata that DP4500 returns.

### 2.2. `users.User.biometric_external_id`

A new field on the existing User model:

```python
biometric_external_id = models.UUIDField(null=True, blank=True, unique=True)
```

- Nullable so existing User rows (no biometric yet) load cleanly.
- Unique so we never mint two Credentials in DP4500 for the same UUID.
- Generated client-side in a `pre_save` signal: if the field is
  empty, set it to `uuid.uuid4()`.
- Indexed implicitly via `unique=True`.

Migration `users/migrations/00XX_user_biometric_external_id.py`.

### 2.3. `citas.CitaMedica` biometric fields

Three nullable fields on the existing `CitaMedica` model:

```python
biometric_challenge_id = models.CharField(max_length=64, null=True, blank=True)
biometric_match_confidence = models.DecimalField(
    max_digits=5, decimal_places=4, null=True, blank=True,
)
biometric_verified_at = models.DateTimeField(null=True, blank=True)
```

Migration `citas/migrations/00XX_citamedica_biometric_fields.py`.

The view that runs verification sets all three together inside a
`transaction.atomic()`. On failure (mismatch, timeout, etc.) the
fields stay NULL and the cita remains `REALIZADA_PENDIENTE_VERIFICACION`.

### 2.4. `Sucursal.dp4500_service_key`

The clinic has multiple branches (sucursales). Each branch has its own
`ServiceAPIKey` against DP4500 (decision 3 from the Phase 2 lockin
session). Store the reference on the branch itself:

```python
dp4500_service_key = models.ForeignKey(
    "accounts.ServiceAPIKey",          # refers to the DP4500 model
    on_delete=models.PROTECT,           # never cascade-delete a key
    null=True, blank=True,             # branches without biometric yet stay None
    related_name="+",
)
```

Yes — `accounts.ServiceAPIKey` is a model in the *DP4500* Django project,
not this one. Phase 2 stores the reference by id (CharField) rather
than by FK to avoid cross-project ORM coupling. Migration:

```python
dp4500_service_key_id = models.CharField(max_length=64, null=True, blank=True)
# Validated against DP4500 at request time (not at ORM time).
```

Per-branch validation: when a request hits the new biometric views,
look up the User's `sucursal`, read its `dp4500_service_key_id`,
look up the raw token from a secure store (see §2.6).

### 2.5. Cascade-revoke hook on User.delete()

When a `User` is deleted (any reason — operator, GDPR request,
re-activation recovery, etc.), the clinic must ask DP4500 to revoke
the matching template. The blast-radius goal is: a DP4500 outage
never blocks the local delete.

**Mechanism (decisions from the lock-in session):**

1. `signals.py` adds `post_delete` for `User`:
   ```python
   @receiver(post_delete, sender=User)
   def cascade_revoke_on_user_delete(sender, instance, **kwargs):
       if instance.biometric_external_id is None:
           return  # nothing to revoke
       # Synchronously store a "pending cascade" marker (avoid the
       # "lost on retry" failure mode of pure Celery).
       PendingCascade.objects.create(
           user_external_id=str(instance.biometric_external_id),
           sucursal_id=instance.sucursal_id,
       )
       # Asynchronously enqueue the actual delete call.
       cascade_revoke_template.delay(
           str(instance.biometric_external_id),
           instance.sucursal_id,
       )
   ```

2. `tasks.py` (Celery) holds `cascade_revoke_template`:
   ```python
   @shared_task(bind=True, max_retries=5, default_retry_delay=30)
   def cascade_revoke_template(self, user_external_id, sucursal_id):
       try:
           biometric_client.delete_template(user_external_id, sucursal_id)
       except BiometricUnavailable:
           # DP4500 is down: keep retrying; the PendingCascade row
           # tracks the pending state regardless of retry outcome.
           raise self.retry(exc=BiometricUnavailable)
       except BiometricGone:
           # Already gone on DP4500 side — mark locally as completed.
           PendingCascade.objects.filter(...).update(status="completed")
   ```

3. `PendingCascade` model (small, in `biometric/models.py`):
   ```python
   class PendingCascade(models.Model):
       user_external_id = models.UUIDField()
       sucursal_id = models.IntegerField()
       status = models.CharField(max_length=16, default="pending")
       attempts = models.PositiveIntegerField(default=0)
       created_at = models.DateTimeField(auto_now_add=True)
       last_attempt_at = models.DateTimeField(null=True, blank=True)
       completed_at = models.DateTimeField(null=True, blank=True)
   ```

4. `manage.py reconcile_pending_cascades` management command for
   manual reconciliation when Celery is unavailable.

### 2.6. Settings + secure token store

Add the following to `settings.py`:

```python
DP4500_BASE_URL = os.getenv("DP4500_BASE_URL", "http://localhost:8000")
DP4500_TIMEOUT_SECONDS = int(os.getenv("DP4500_TIMEOUT_SECONDS", "5"))
DP4500_KEY_STORE_BACKEND = os.getenv("DP4500_KEY_STORE_BACKEND", "env")
```

For Phase 2, the only supported backend is `env`, which reads the
service key per-sucursal from env vars keyed by `DP4500_SERVICE_KEY_SUCURSAL_{id}`.
Phase 4 adds vault support via a `KEY_STORE_BACKEND=vault` pluggable
interface (not in Phase 2 scope).

Per-env config (illustrative):

```bash
# dev / staging / prod — one env var per branch
DP4500_BASE_URL=https://dp4500-prod.clinica.internal
DP4500_SERVICE_KEY_SUCURSAL_42=SeK_abcdef...
DP4500_SERVICE_KEY_SUCURSAL_43=SeK_xyz123...
```

### 2.7. Tests

- `tests/test_client.py` — `httpx.MockTransport` covers: ok responses
  per endpoint, 503 with `code: NO_AGENT`, 503 with
  `code: BIOMETRIC_SUSPENDED`, 409 with `code: ENROLL_CONFLICT`,
  timeouts.
- `tests/test_views.py` — happy enroll + happy verify paths, plus
  the "DP4500 down" + "no template on file" + "mismatch" branches.
- `tests/test_cascade.py` — soft-delete locally + retry the cascade
  under simulated DP4500 downtime (httpx MockTransport returning 503).
- `tests/test_models.py` — `biometric_external_id` UUID generation
  via the pre_save signal; uniqueness over users.

Test target: 100% line coverage on the new `biometric/` app;
>80% branch coverage on `views.py`.

---

## 3. Scope

### In scope (Phase 2)

- The new `biometric/` Django app + its tests.
- `users.User.biometric_external_id` field + pre_save signal + migration.
- `citas.CitaMedica` biometric fields + migration.
- `Sucursal.dp4500_service_key_id` field + per-branch key lookup.
- Cascade hook on `User.delete()` with Celery retry.
- Settings module additions (`DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`,
  `DP4500_KEY_STORE_BACKEND`).
- One management command: `reconcile_pending_cascades`.
- SDD artifacts (proposal + 4 specs + design + tasks + archive-report).

### Out of scope (deferred to later phases)

- **Phase 3 — Capture client decision (Q1)**: how the fingerprint
  actually gets captured (browser Web SDK, Electron child process,
  hybrid). For Phase 2, the enroll view renders a "captura
  pendiente" stub that blocks until Phase 4. Once Phase 3 lands,
  the view is wired to the real capture client behind the same
  client.py interface. No data-model change required.
- **Phase 4 — Production hardening**: mTLS, DPIA §9 sign-off, KMS HA,
  HID agent per workstation, vault-backed key store.
- **Action authorization** (`/service/challenge/action/` +
  `/service/verify/action/`). Phase 2 covers identity only. Action
  flow waits for the third use case to surface.
- **History of biometric attempts per cita**. The single-row
  approach (set fields on match; null on mismatch) is enough for
  Phase 2. Phase 4 may extract a `BiometricVerification` table if
  audit demands per-attempt traceability.
- **Manual confirmation fallback UI** when biometric is suspended.
  The current "Confirmar manualmente" button stays as-is; Phase 4 may
  add a banner that explains why.

---

## 4. Decisions locked in this session

| # | Decision | Source |
|---|---|---|
| Q1 — Capture UI | Deferred to Phase 4; Phase 2 implements stubs | session 2026-09-27 |
| Cascade failure mode | Soft-delete local + Celery retry; alert after N retries | session 2026-09-27 |
| Key granularity | One ServiceAPIKey per Sucursal per environment | session 2026-09-27 |
| `user_external_id` shape | UUID, persisted on `Usuario` | session 2026-09-27 (Q2) |
| Cascade delete contract | Hook on `User.delete()` → `DELETE /service/templates/<uuid>/` | session 2026-09-27 (Q3) |
| Data model | Three nullable fields on `CitaMedica` (no separate table) | session 2026-09-27 |
| Key storage | `Sucursal.dp4500_service_key_id` (cross-project ref by id) | derived from granularity decision |
| Phase 2 scope | Identity challenge only (enrollment + cita verification); action authorization is Phase 4+ | derived |

---

## 5. Open items

These surface during proposal review and lock in `spec.md`:

1. Where does `PendingCascade` live — `biometric/models.py` or
   `users/models.py`? Decision needed at design time; Phase 2's
   lock-in says "the FK tracking is in the biometric app for cohesion".
2. Retry policy details — max retries, exponential backoff vs fixed
   `default_retry_delay`, alert threshold. Defaults proposed in §2.5
   but the exact numbers belong in the Celery config.
3. Whether the `manage.py reconcile_pending_cascades` command should
   be cron-driven or run manually — depends on the clinic's existing
   cron infra (out of Phase 2 scope to add new cron, but the command
   is there).
4. Which `User.delete()` triggers fire — soft delete via a `deleted_at`
   column, hard delete via `User.objects.delete()`, or both? Affects
   whether the cascade hook needs two entry points.
5. Whether `CitaMedica.biometric_*` fields should survive a cascade
   re-issuance (UUID-stable) or be cleared on each new capture cycle
   (UUID-rotation). Default: UUID stable, fields cleared only when
   the User is re-enrolled from scratch.

---

## 6. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Celery worker not running → cascade retries never fire | high | Manage command `reconcile_pending_cascades` runs the same logic, can be cron-driven separately from Celery |
| Cross-project FK (`Sucursal.dp4500_service_key_id`) drifts from DP4500 if a key is deleted on the DP4500 side | medium | On every request, validate the key against `DP4500_GET /api/admin/service-keys/{id}/` (Phase 4 endpoint); for Phase 2, fall back to `BiometricUnavailable` and surface to the operator |
| `httpx` timeout (5s default) thrashes under DP4500 load | medium | Per-request timeout + circuit breaker (Phase 4 polish) |
| Two concurrent enroll calls for the same prospect → two templates minted in DP4500 | medium | Phase 1's partial unique index on `user_external_id` already prevents this server-side; the client surfaces `409 ENROLL_CONFLICT` to the operator |
| The `manage.py reconcile_pending_cascades` is run manually and forgotten | low | Optional Phase 4 cron; log alert after 24h pending |
| Service key drift across releases (key rotated but env var stale) | low | On `BIOMETRIC_GONE` (404 from DELETE), the clinic treats as success and clears the pending row anyway |

---

## 7. Success criteria

Phase 2 is complete when:

1. The `biometric/` app exists with `client.py`, `views.py`, `urls.py`,
   `exceptions.py`, `templates/biometric/capture_pending.html`, and
   `tests/` reaching 100% line coverage on `client.py` and >80%
   branch coverage on `views.py`.
2. `users.User.biometric_external_id` is on the model with the pre_save
   signal generating UUID on first save.
3. `citas.CitaMedica` carries the three biometric fields with no
   nullable constraint.
4. `Sucursal.dp4500_service_key_id` (CharField, nullable) is on the
   model and loaded via `DP4500_KEY_STORE_BACKEND=env`.
5. `signals.py` exposes `post_delete` for `User` that
   synchronously records a `PendingCascade` row and asynchronously
   enqueues the Celery retry task.
6. `settings.py` adds `DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`,
   `DP4500_KEY_STORE_BACKEND`.
7. Migrations apply cleanly on a fresh DB and on the demo DB without
   data loss.
8. The smoke run: `./manage.py runserver` + HTTP POST to
   `/api/biometric/cliente/<uuid>/enroll/` (Phase 2 endpoint) →
   succeeds when DP4500 returns `201`; surfaces `503 BIOMETRIC_SUSPENDED`
   when Phase 1's flag is on; surfaces `409 ENROLL_CONFLICT` when the
   external_id already has an active template.
9. The cascade test: deleting a User whose UUID has a template at
   DP4500 succeeds locally; a `PendingCascade` row exists; the Celery
   task eventually issues `DELETE`; the row's status flips to
   `completed`. Run twice — second is a no-op.

---

## 8. References

- `docs/plans/2026-09-27-biometric-web-integration.md` — the plan (§Phase 2).
- The Phase 1 SDD artifacts (sibling repo):
  `C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1\`
  — especially `design.md` §3 (`Service API authentication`),
  §4 (`Cross-system identity linking`), §5 (`Cross-system audit
  provenance`), §6 (`Service endpoint contracts`).
- `backend/users/models.py` (this repo) — User model.
- `backend/operations/models.py` (this repo) — `CitaMedica` model and
  `REALIZADA_PENDIENTE_VERIFICACION` state.
- `backend/catalogs/models.py` (this repo) — `Sucursal` model.

---

## 9. Predecessor artifact chain

`docs/plans/2026-09-27-biometric-web-integration.md`
  ↓
`C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1\{proposal,specs/*,design,tasks,archive-report}.md`
  ↓
**`openspec/changes/dp4500-host-app-integration-phase2/proposal.md`** (this file)
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/specs/*/spec.md` (next)
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/design.md`
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/tasks.md`
  ↓
apply → verify → archive

---

**Awaiting user review before proceeding to spec.md.**