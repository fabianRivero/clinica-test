# Design: Host-app integration — Phase 2 (Clinic side)

**Change name**: `dp4500-host-app-integration-phase2`
**Artifact store**: openspec (this repo, the clinic)
**Status**: ready-for-tasks
**Predecessors**:
- `proposal.md` (locked)
- `specs/dp4500-service-client/spec.md` (locked)
- `specs/wizard-biometric-enrollment/spec.md` (locked)
- `specs/cita-biometric-verification/spec.md` (locked)
- `specs/cascade-biometric-revoke/spec.md` (locked)
- Phase 1 in the sibling repo: `C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1\`. The service API surface is the contract.

---

## 1. Architecture overview

Phase 2 inverts the Phase 1 stance: where Phase 1 opened a new server
surface, Phase 2 closes the loop from the **client** side. The clinic
Django backend issues HTTP calls into DP4500's `/api/biometric/service/*`,
mapping responses to domain exceptions and persisting audit-link
metadata on local rows. No fingerprint bytes — only `challenge_id`,
`match_confidence`, and audit hashes.

### 1.1 System diagram (Phase 2 delta)

```
+----------------------------------+      +-----------------------------------+
| Clinic Django (this repo)        |      | DP4500 estandar (Phase 1)        |
|                                  |      |                                   |
|  [USER + biometric_external_id]  |      |   POST /service/challenge/        |
|       |                          |      |        identity/<external_id>/    |
|       v                          |      |   POST /service/verify/identity/  |
|  ConversionStepBiometric (UI)    | HTTP |                                   |
|       | step 4                    | ---->|   DELETE /service/templates/      |
|       v                          | Bearer|        <external_id>/              |
|  BiometricEnrollmentRecord       |      |        (race-safe revoke)          |
|       |                          |      |                                   |
|       v                          |      |   +-----------------------------+   |
|  POST /verificar/                |      |   | BiometricTemplate            |   |
|       | cita/                    |      |   |    user_external_id          |   |
|       v                          |      |   | BiometricAuditEvent          |   |
|  CitaMedica update               |      |   |    external_system           |   |
|       | biometrica=ok            |      |   +-----------------------------+   |
|       v                          |      |                                   |
|  signals.post_delete(User)       |      |                                   |
|       |                          |      |                                   |
|       v                          |      |                                   |
|  PendingCascade row              |      |                                   |
|       | + Celery task            |      |                                   |
|       v                          |      |                                   |
|  cascade_revoke_template()      |      |                                   |
|       | HTTP DELETE              |      |                                   |
|       v                          |      |                                   |
|  Retry on BiometricUnavailable  |      |                                   |
|  (Celery, max 5x, 30s delay)     |      |                                   |
+----------------------------------+      +-----------------------------------+
```

### 1.2 Components added by Phase 2

| Component | Role | Where |
|---|---|---|
| `biometric.HTTPClient` | Thin httpx wrapper. Translates wire statuses → domain exceptions. No crypto. | `apps/biometric/client.py` |
| `biometric.key_resolver` (env-var backend for Phase 2) | Resolves `sucursal_id` → raw bearer token. Phase 4 adds vault. | same file |
| `biometric.views` | Wizard step 4 view + cita verification view. Thin over `HTTPClient`. | `apps/biometric/views.py` |
| `biometric.urls` | Two URL patterns. | `apps/biometric/urls.py` |
| `biometric.models.PendingCascade` | Persistent retry queue keyed on `user_external_id`. | `apps/biometric/models.py` |
| `biometric.models.BiometricEnrollmentRecord` | Local audit-trail for wizard step 4 advances. | same file |
| `biometric.tasks.cascade_revoke_template` | Celery task — calls `HTTPClient.delete_template`, classifies outcome, updates `PendingCascade`. | `apps/biometric/tasks.py` |
| `biometric.signals.cascade_revoke_on_user_delete` | `post_delete` signal handler — synchronously inserts `PendingCascade`, enqueues the Celery task. | `apps/biometric/signals.py` |
| `biometric.templates.biometric/capture_pending.html` | Stub UI for step 4 (Phase 4 replaces). | `apps/biometric/templates/biometric/capture_pending.html` |
| `users.User.biometric_external_id` | New UUID column on User. | `apps/users/models.py` |
| `users.signals.assign_biometric_external_id` | `pre_save` signal that sets the UUID on first save. | `apps/users/signals.py` |
| `citas.CitaMedica.{biometric_*}` | New nullable fields. | `apps/citas/models.py` |
| `catalogs.Sucursal.dp4500_service_key_id` | CharField reference (not FK — see §6.1). | `apps/catalogs/models.py` |
| Settings additions | `DP4500_BASE_URL`, `DP4500_TIMEOUT_SECONDS`, `DP4500_KEY_STORE_BACKEND`. | `config/settings.py` |
| `reconcile_pending_cascades` management command | Operator override when Celery is unavailable. | `apps/biometric/management/commands/reconcile_pending_cascades.py` |

### 1.3 Trust boundaries

1. **Clinic ↔ DP4500** — Bearer `ServiceAPIKey` per sucursal. mTLS is
   Phase 4. Per-spec §service-client: bearer scheme is exact, raw
   token never logged, no other auth headers.
2. **Clinic ORM ↔ DB** — Fernet-encrypted templates are NOT stored
   here. The `biometric_external_id` UUID + `biometric_*` metadata
   live alongside the cita / user rows; the encryption key (Fernet
   from the DP4500 side) is never imported.
3. **Celery worker ↔ DB** — synchronous reads/writes against the same
   `PendingCascade` rows. Cellery retries at most 5× with 30s delay
   (Phase 2 default); Phase 4 may tune.
4. **Operator UI ↔ Clinic Django** — existing clinic session + DRF
   auth. The phase-2 wizard view checks `request.user` per the
   existing pattern in `ConversionStepBiometricView`.

### 1.4 Invariants added by Phase 2

1. **`User.biometric_external_id` is generated once and stable.**
   `pre_save` sets it on the first `INSERT`; subsequent `UPDATE`s
   preserve the value.
2. **No fingerprint bytes in the clinic DB.** Not in `User`,
   not in `CitaMedica`, not in `PendingCascade`, not in any new
   table. Phase 4 cannot relax this.
3. **`PendingCascade` outlives branch renames.** `sucursal_id` is
   `IntegerField`, not FK. If a Sucursal is renamed or deleted, the
   pending rows remain (orphan-resilient) for `reconcile_pending_cascades`.
4. **CitaMedica biometric fields are atomic.** All three NULL OR
   all three populated; partial writes are not allowed.
5. **The cascade hook is best-effort.** If the sync `PendingCascade`
   insert fails, the User delete still commits (per spec
   cascade-revoke §0). Recovery path is the management command.
6. **No cross-project FK.** The clinic's ORM never imports
   `dp4500 estandar` models. Reference is by id (CharField) only.

### 1.5 Non-changes (explicit)

- The clinic's existing `CitaMedica` model
  (`REALIZADA_PENDIENTE_VERIFICACION` state machine, `metodo_confirmacion`,
  etc.) is preserved. Phase 2 ADDS three nullable fields; no other
  field is renamed, dropped, or restricted.
- The existing `Sucursal` model gets one new optional column; the
  existing per-sucursal auth / isolation rules are unchanged.
- The clinic's `confirm_manual` endpoint keeps working; biometric
  failure does not disable it.
- The clinic's prospect-convert wizard steps 1, 2, 3, 5 are unchanged.
  Phase 2 only touches step 4.

---

## 2. Module layout

```
backend/
├── apps/
│   ├── biometric/                       # NEW
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── client.py                    # HTTPClient
│   │   ├── exceptions.py                # BiometricSuspended, BiometricMismatch, …
│   │   ├── models.py                    # PendingCascade, BiometricEnrollmentRecord
│   │   ├── views.py                     # ConversionStepBiometricView + CitaVerifyView
│   │   ├── urls.py
│   │   ├── signals.py                   # post_delete handler
│   │   ├── tasks.py                     # Celery: cascade_revoke_template
│   │   ├── migrations/
│   │   │   └── 0001_*.py
│   │   ├── management/commands/
│   │   │   └── reconcile_pending_cascades.py
│   │   ├── templates/biometric/
│   │   │   └── capture_pending.html
│   │   └── tests/
│   │       ├── test_client.py
│   │       ├── test_views.py
│   │       ├── test_cascade.py
│   │       └── test_models.py
│   ├── users/                           # MODIFIED
│   │   ├── models.py                    # ADD biometric_external_id
│   │   ├── signals.py                   # NEW pre_save handler
│   │   └── migrations/000X_user_biometric_external_id.py
│   ├── citas/                           # MODIFIED
│   │   ├── models.py                    # ADD 3 biometric fields
│   │   └── migrations/000X_citamedica_biometric_fields.py
│   ├── catalogs/                        # MODIFIED
│   │   ├── models.py                    # ADD Sucursal.dp4500_service_key_id
│   │   └── migrations/000X_sucursal_dp4500_key.py
│   └── config/settings.py                # MODIFIED (add DP4500_* settings)
└── tests/integration/
    └── test_biometric_integration.py    # NEW: end-to-end smoke via httpx MockTransport
```

---

## 3. Service client design

The `biometric.HTTPClient` class is a thin httpx wrapper. It does no
key management beyond calling the injected `key_resolver`, no retry
beyond surfacing the exception, and no templating beyond minor JSON
shaping.

### 3.1 Class shape

```python
class HTTPClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: int,
        key_resolver: Callable[[int], str | None],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self._key_resolver = key_resolver
        self._client = httpx.Client(timeout=timeout_seconds)

    def identity_challenge(
        self, *, user_external_id: str, sucursal_id: int,
    ) -> IdentityChallenge:
        """POST /service/challenge/identity/<external_id>/ with empty body."""
        ...

    def identity_verify(
        self, *, user_external_id: str, challenge_id: str,
        signature_b64: str, timestamp: str, sucursal_id: int,
    ) -> IdentityVerifyResult:
        """POST /service/verify/identity/ with {challenge_id, signature, timestamp}."""
        ...

    def delete_template(
        self, *, user_external_id: str, sucursal_id: int,
    ) -> None:
        """DELETE /service/templates/<external_id>/ (idempotent)."""
        ...
```

Each method:
1. Resolves the key via `self._key_resolver(sucursal_id)`.
2. On `None` key: raises `BiometricUnavailable("no_service_key")`.
3. Issues the HTTP request via `self._client`.
4. Decodes the JSON; classifies the status → domain exception OR
   returns the parsed result.

### 3.2 Domain result types

```python
@dataclass(frozen=True)
class IdentityChallenge:
    capture_token: str
    server_nonce: str      # base64-encoded
    ttl_seconds: int
    has_fingerprint: bool
    server_pubkey_jwk: dict

@dataclass(frozen=True)
class IdentityVerifyMatch:
    matched: bool = True
    audit_hash: str = ""

@dataclass(frozen=True)
class IdentityVerifyNoMatch:
    matched: bool = False
    audit_hash: str = ""
```

### 3.3 Exception hierarchy

```python
class BiometricError(Exception): ...
class BiometricUnavailable(BiometricError): ...   # dp4500 down, 5xx, timeout
class BiometricSuspended(BiometricError): ...    # 503 BIOMETRIC_SUSPENDED
class BiometricMismatch(BiometricError): ...     # 422 signature_invalid
class BiometricVerifyFailed(BiometricError): ... # 422 INVALID_TOKEN (challenge expired)
class BiometricEnrollConflict(BiometricError): ... # 409 enrollment_required
```

### 3.4 key_resolver (env backend)

```python
def env_key_resolver(sucursal_id: int) -> str | None:
    raw = os.environ.get(f"DP4500_SERVICE_KEY_SUCURSAL_{sucursal_id}")
    return raw  # or None
```

The resolver is a separate module `biometric/key_resolver.py`. Phase 4
adds a `vault_key_resolver()` and a plugin interface (`get_key_resolver()`
returns one based on `settings.DP4500_KEY_STORE_BACKEND`).

### 3.5 Error code mapping

| HTTP | Body `code` | Exception |
|---|---|---|
| 200/201 | (any) | return parsed result |
| 401 | — | `BiometricUnavailable("auth_failed")` |
| 403 | `cross_sucursal_forbidden` | impossible (we own the branch's key) |
| 404 | `not_found` (DELETE) | idempotent: return `None` |
| 404 | `not_found` (other) | `BiometricVerifyFailed("not_found")` |
| 409 | `cita_no_longer_pending` | `BiometricMismatch` (caller maps) |
| 409 | `ENROLL_CONFLICT` | `BiometricEnrollConflict` |
| 409 | `enrollment_required` | `BiometricEnrollConflict("no_template_on_dp4500")` |
| 422 | `INVALID_TOKEN` | `BiometricVerifyFailed("challenge_invalid")` |
| 422 | `signature_invalid` | `BiometricMismatch` |
| 503 | `BIOMETRIC_SUSPENDED` | `BiometricSuspended` |
| 503 | `NO_AGENT` | `BiometricUnavailable("no_agent")` |
| 503 | other | `BiometricUnavailable(f"http_503:{code}")` |
| 5xx | — | `BiometricUnavailable(f"http_{status}")` |
| timeout | — | `BiometricUnavailable("timeout")` |
| other | — | `BiometricUnavailable(f"unexpected:{type(e).__name__}")` |

---

## 4. Cita verification view

`CitaBiometricVerifyView` runs the full challenge+verify dance, then
mutates the cita inside a `transaction.atomic()` block with `select_for_update()`.

### 4.1 Sequence

```
Operator click "Confirmar por huella"
  │
  ▼
POST /api/biometric/citas/<cita_id>/verificar/
  │
  ├─ 404 if cita not found
  ├─ 409 if sucursal has no DP4500_SERVICE_KEY_SUCURSAL_<id>
  │   └─ Then it's "manual fallback only" — the operator falls back
  │      to confirm_manual.
  │
  ├─ cita = CitaMedica.objects.select_for_update().get(pk=cita_id)
  │
  ├─ 409 if cita.estado != REALIZADA_PENDIENTE_VERIFICACION
  │
  ├─ challenge = client.identity_challenge(user_external_id=cliente.biometric_external_id,
  │                                        sucursal_id=cita.sucursal_id)
  │   └─ 422 on BiometricMismatch etc → propagate up
  │
  ├─ verify = client.identity_verify(user_external_id=...,
  │                                   challenge_id=challenge.capture_token,
  │                                   signature_b64=<from stub>,
  │                                   timestamp=<now iso>,
  │                                   sucursal_id=cita.sucursal_id)
  │
  ├─ If verify.matched:
  │     cita.estado = CONFIRMADA
  │     cita.metodo_confirmacion = BIOMETRICO
  │     cita.biometric_challenge_id = challenge.capture_token
  │     cita.biometric_match_confidence = Decimal(str(verify.score)) if available else None
  │     cita.biometric_verified_at = now()
  │     cita.save()
  │
  └─ else: leave cita unchanged, return 422 + code=biometric_mismatch
```

Phase 2 stubs `signature_b64` and `timestamp` — they are placeholders
that satisfy Phase 1's `ConsumeServiceIdentityChallenge` (which
treats the body as a payload to record; Ed25519 verification lands
with the capture client in Phase 4). The signature is `"phase2-stub"`,
the timestamp is `now().isoformat()`.

### 4.2 Concurrency

Two concurrent verifies for the same cita serialize on the
`select_for_update()` lock. The loser sees
`cita.estado != REALIZADA_PENDIENTE_VERIFICACION` and returns 409.

### 4.3 Admin UI hook (existing pattern)

The clinic's existing `BiometricVerifyCaptureModal.tsx` already calls
`biometricClient.verifyInit()` + `verifyConfirm()`. Phase 2 swaps those
to call the clinic's new endpoints
(`/api/biometric/citas/<id>/verificar/`), which in turn call the
DP4500 service API. The frontend signature does not change.

---

## 5. Wizard step 4 (enrollment) view

The view `ConversionStepBiometricView` (inherits the existing
`ConversionStepBiometric` pattern; Phase 2 keeps the class name and
adds hooks for the stub UI).

### 5.1 Render

```python
class ConversionStepBiometricView(FormView):
    template_name = "biometric/capture_pending.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["biometric_external_id"] = self.prospect.user.biometric_external_id
        ctx["biometric_available"] = biometri_client.probe_status(
            sucursal_id=self.prospect.user.sucursal_id,
        )
        return ctx

    def form_valid(self, form):
        BiometricEnrollmentRecord.objects.create(
            user=self.prospect.user,
            user_external_id=self.prospect.user.biometric_external_id,
            enrollment_strategy="pending",
            advanced_at=timezone.now(),
            advanced_by=self.request.user,
            wizard_id=self.kwargs["wizard_id"],
        )
        return redirect(self.get_success_url())
```

The capture_pending.html template shows:
- A status banner ("Disponible" / "No disponible temporalmente").
- The `biometric_external_id` (read-only).
- A "Continuar sin captura" button (POST).
- A "Cancelar" link back to step 3.

### 5.2 Why no real capture in Phase 2

The plan defers Q1 (capture strategy: browser Web SDK vs Electron
child process) to Phase 4. Phase 2 ships the stub so the wizard is
navigable end-to-end while we settle the real capture architecture.
Phase 4 replaces the template with a real capture flow; the URL
contract is unchanged so no DB migration is needed.

---

## 6. Cascade-revoke design

### 6.1 Data model: `PendingCascade`

```python
class PendingCascade(models.Model):
    user_external_id = models.UUIDField()
    # Intentionally NOT FK to Sucursal: branch renames must not
    # cascade-delete pending rows. See §1.4 invariant 3.
    sucursal_id = models.IntegerField()

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_SUSPENDED = "suspended"
    STATUS_FAILED = "failed"
    status = models.CharField(
        max_length=16,
        default=STATUS_PENDING,
        choices=(
            (STATUS_PENDING, "Pending cascade"),
            (STATUS_COMPLETED, "Completed (DP4500 returned 204 or 404)"),
            (STATUS_SUSPENDED, "DP4500 returned BIOMETRIC_SUSPENDED; not retryable"),
            (STATUS_FAILED, "Exhausted retries"),
        ),
    )

    attempts = models.PositiveSmallIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "biometric_pendingcascade"
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user_external_id"]),
        ]
```

### 6.2 Signal handler

```python
# apps/biometric/signals.py
@receiver(post_delete, sender=User)
def cascade_revoke_on_user_delete(sender, instance, **kwargs):
    if not instance.biometric_external_id:
        return
    try:
        pending = PendingCascade.objects.create(
            user_external_id=instance.biometric_external_id,
            sucursal_id=instance.sucursal_id,
            status=PendingCascade.STATUS_PENDING,
        )
    except Exception as exc:                                     # noqa: BLE001
        logger.error("Failed to record PendingCascade for %s: %s",
                     instance.biometric_external_id, exc)
        return                                                     # best-effort

    try:
        cascade_revoke_template.delay(
            str(instance.biometric_external_id),
            instance.sucursal_id,
        )
    except Exception as exc:                                     # noqa: BLE001
        logger.error("Failed to enqueue cascade_revoke_template: %s", exc)
        # The PendingCascade row is the source of truth; the
        # management command can re-attempt the enqueue.
```

The handler is connected in `biometric.apps.BiometricConfig.ready()`
(symmetric to the project pattern). The two `try/except`s are
defensive — the local delete is the operator's intent and must not
be undone by signal-side failures.

### 6.3 Celery task

```python
# apps/biometric/tasks.py
@shared_task(bind=True, max_retries=5, default_retry_delay=30)
def cascade_revoke_template(self, user_external_id: str, sucursal_id: int):
    from biometric.client import HTTPClient              # late import: Celery boot
    from biometric.exceptions import (
        BiometricSuspended, BiometricUnavailable,
    )
    from biometric.models import PendingCascade

    pending = PendingCascade.objects.filter(
        user_external_id=user_external_id,
        sucursal_id=sucursal_id,
        status=PendingCascade.STATUS_PENDING,
    ).first()
    if pending is None:
        # Already completed by a previous attempt / reconciliation.
        return
    pending.attempts = (pending.attempts or 0) + 1
    pending.last_attempt_at = timezone.now()

    client = _build_client(sucursal_id)
    try:
        client.delete_template(user_external_id=user_external_id, sucursal_id=sucursal_id)
    except BiometricSuspended as exc:
        pending.status = PendingCascade.STATUS_SUSPENDED
        pending.last_error_code = "BIOMETRIC_SUSPENDED"
        pending.save()
        return                                                       # non-retryable
    except BiometricUnavailable as exc:
        pending.last_error_code = str(exc)[:64]
        pending.save()
        raise self.retry(exc=exc)                                   # retry with backoff
    except Exception as exc:                                       # noqa: BLE001
        pending.last_error_code = f"unexpected:{type(exc).__name__}"[:64]
        pending.save()
        raise self.retry(exc=exc)
    else:
        pending.status = PendingCascade.STATUS_COMPLETED
        pending.completed_at = timezone.now()
        pending.save()
```

The Celery auto-retry policy is the `max_retries=5, default_retry_delay=30`
on the decorator; after the 5th failure the row's `status` flips to
`FAILED` (set in the Celery `on_failure` hook below).

```python
@shared_task(...)
def cascade_revoke_template(self, ...):
    ...

@cascade_revoke_template.on_failure
def _mark_failed(self, exc, task_id, args, kwargs, einfo):
    PendingCascade.objects.filter(
        user_external_id=kwargs.get("user_external_id"),
        sucursal_id=kwargs.get("sucursal_id"),
        status=PendingCascade.STATUS_PENDING,
    ).update(
        status=PendingCascade.STATUS_FAILED,
        last_error_code=f"celery:{type(exc).__name__}"[:64],
    )
```

### 6.4 Reconciliation command

```python
# apps/biometric/management/commands/reconcile_pending_cascades.py
class Command(BaseCommand):
    help = "Run the cascade revoke for every pending PendingCascade row."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Process at most N rows (for staged rollouts).",
        )

    def handle(self, *args, **opts):
        qs = PendingCascade.objects.filter(status=PendingCascade.STATUS_PENDING)
        if opts["limit"]:
            qs = qs[:opts["limit"]]
        for row in qs:
            if opts["dry_run"]:
                self.stdout.write(f"[dry-run] would reconcile {row.pk}")
                continue
            # Synchronously invoke the same logic as the Celery task
            # (without retry — this is the manual override; the user
            # can re-run if DP4500 is still down).
            try:
                _do_cascade(row)
                row.status = PendingCascade.STATUS_COMPLETED
                row.completed_at = timezone.now()
                row.save()
            except Exception as exc:
                self.stderr.write(f"row {row.pk}: {exc}")
                return 1
        return 0
```

The command and the Celery task share `_do_cascade()` so the behaviour
is identical between the two entry points.

---

## 7. Data model additions

### 7.1 `users.User.biometric_external_id`

```python
# apps/users/models.py (existing User model)
class User(AbstractUser):
    ...
    biometric_external_id = models.UUIDField(
        null=True, blank=True, unique=True, db_index=True,
        help_text=(
            "Stable opaque identity issued by DP4500. Generated by the "
            "pre_save signal on first INSERT; never reassigned."
        ),
    )
```

Pre-save signal:

```python
# apps/users/signals.py
@receiver(pre_save, sender=User)
def assign_biometric_external_id(sender, instance, **kwargs):
    if instance.pk is None and instance.biometric_external_id is None:
        instance.biometric_external_id = uuid.uuid4()
```

The signal lives in `apps/users/signals.py` (new module). The User app
loads it via `apps.py`'s `ready()`.

### 7.2 `citas.CitaMedica` biometric fields

```python
# apps/citas/models.py (existing CitaMedica model)
class CitaMedica(TimeStampedModel):
    ...
    # Phase 2 biometric verification outcome. All three NULL = no
    # biometric check ran (manual or pending); all three populated =
    # a successful biometric verification moved the cita to CONFIRMADA.
    biometric_challenge_id = models.CharField(
        max_length=64, null=True, blank=True,
        help_text="DP4500 capture_token returned by the challenge endpoint.",
    )
    biometric_match_confidence = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Match score from DP4500's verify response.",
    )
    biometric_verified_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Local clock at the moment of the verify response.",
    )
```

### 7.3 `catalogs.Sucursal.dp4500_service_key_id`

```python
# apps/catalogs/models.py (existing Sucursal model)
class Sucursal(TimeStampedModel):
    ...
    # Phase 2 cross-project reference: the id of the ServiceAPIKey
    # row in DP4500's accounts_service_api_key table that this branch
    # uses to authenticate against the service API.
    #
    # CharField, NOT ForeignKey: DP4500's models live in a different
    # Django project. The raw bearer token is stored in env vars
    # (Phase 2) or vault (Phase 4) — this column is only the reference id.
    dp4500_service_key_id = models.CharField(
        max_length=64, null=True, blank=True,
        help_text=(
            "id of the ServiceAPIKey in DP4500 (cross-project reference)."
        ),
    )
```

The raw token is stored separately (env var `DP4500_SERVICE_KEY_SUCURSAL_<id>`).
The `dp4500_service_key_id` column only carries the integer pk of the
DP4500 row, for visibility / debugging. The two values are paired
out-of-band (the operator mints the key and stores both the integer
pk and the raw token in the clinic's secret store).

### 7.4 `biometric.PendingCascade`

Already specified in §6.1.

### 7.5 `biometric.BiometricEnrollmentRecord`

```python
class BiometricEnrollmentRecord(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="biometric_enrollment_records",
    )
    user_external_id = models.UUIDField()
    wizard_id = models.CharField(max_length=64)             # unique wizard session id
    enrollment_strategy = models.CharField(
        max_length=16, default="pending",
        choices=(
            ("pending", "Phase 2 stub: capture not yet wired"),
            ("mock", "Phase 2 dev: dev-only mock capture"),
            ("websdk", "Phase 4: browser Web SDK"),
            ("electron", "Phase 4: Electron child process"),
        ),
    )
    advanced_at = models.DateTimeField(null=True, blank=True)
    advanced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="enrollment_advances",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "biometric_enrollment_record"
        indexes = [
            models.Index(fields=["user", "wizard_id"]),
            models.Index(fields=["enrollment_strategy", "advanced_at"]),
        ]
```

---

## 8. Settings + environment

```python
# config/settings.py (additions)
DP4500_BASE_URL = os.getenv("DP4500_BASE_URL", "http://localhost:8000")
DP4500_TIMEOUT_SECONDS = int(os.getenv("DP4500_TIMEOUT_SECONDS", "5"))
DP4500_KEY_STORE_BACKEND = os.getenv("DP4500_KEY_STORE_BACKEND", "env")
# Phase 2 supports only "env". Phase 4 adds "vault".
```

Per-branch env vars (illustrative):

```bash
DP4500_BASE_URL=https://dp4500-prod.clinica.internal
DP4500_SERVICE_KEY_SUCURSAL_42=SeK_abcdef...
DP4500_SERVICE_KEY_SUCURSAL_43=SeK_xyz123...
```

The clinic's deployment script is responsible for populating these.
A missing env var for a branch that tries to use biometric results in
`BiometricUnavailable("no_service_key")` at request time — the
operator sees a clear banner.

---

## 9. Migrations

Three new migrations, all backwards compatible:

| App | Migration | Operations |
|---|---|---|
| `users` | `000X_user_biometric_external_id.py` | `AddField(name='biometric_external_id', field=UUIDField(null=True, blank=True, unique=True))` |
| `citas` | `000X_citamedica_biometric_fields.py` | `AddField` × 3 (all nullable) |
| `catalogs` | `000X_sucursal_dp4500_key.py` | `AddField(name='dp4500_service_key_id', field=CharField(max_length=64, null=True, blank=True))` |
| `biometric` | `0001_initial.py` | `CreateModel` × 2 (PendingCascade, BiometricEnrollmentRecord) |

`makemigrations --check` exits 0; `migrate` succeeds on fresh and demo DBs.

---

## 10. Test strategy

### 10.1 Unit tests (pytest, no external I/O)

- `tests/test_client.py` — `httpx.MockTransport` covers 12+ status /
  code combinations per endpoint (200 / 201 / 4xx with each `code` /
  5xx / timeout). Fast, deterministic, full coverage of the exception
  mapping table.
- `tests/test_models.py` — `PendingCascade` lifecycle
  (create → completed), `BiometricEnrollmentRecord` fields.
- `tests/test_signals.py` — pre_save on User; post_delete on User;
  sync-insert failure does NOT roll back the local delete.

### 10.2 Integration tests

- `tests/test_views.py` — DRF test client driving the wizard step 4
  GET + POST, and the cita verify POST.
- `tests/test_cascade.py` — end-to-end via Celery eager mode: User
  delete → PendingCascade row + Celery task → DP4500 mock returns 204
  → row marked completed. Same test exercises the retry path with
  `httpx.MockTransport` raising 503.

### 10.3 Coverage targets

- 100% line coverage on `biometric/client.py`.
- ≥ 90% line coverage on `biometric/views.py` and `biometric/signals.py`.
- ≥ 80% line coverage on `biometric/tasks.py` (Celery retry paths).

### 10.4 Test data hygiene

- Each test mints its own `ServiceAPIKey` via the DP4500 `manage.py
  create_service_api_key` command (executed via subprocess in the
  test fixture).
- Each test's HTTP mock transport is constructed fresh per request
  to avoid state leaks between tests.
- Per-sucursal key isolation is verified in a dedicated test: branch
  A's key cannot impersonate branch B.

---

## 11. Risks revisited

| Risk (from proposal §6) | Mitigation in this design |
|---|---|
| Celery worker not running | `reconcile_pending_cascades` shares `_do_cascade()` with the task; manual override is identical work. |
| Cross-project FK drift (Sucursal.dp4500_service_key_id stale) | CharField, not FK — drift is detected by runtime errors from DP4500 (401/404). Phase 4 adds a periodic probe. |
| `httpx` timeout thrashing | Per-request timeout (Phase 4 circuit breaker). |
| Concurrent enroll same prospect | DP4500's partial unique index prevents duplicates server-side; client surfaces 409 `BiometricEnrollConflict`. |
| Manual reconcile forgotten | PendingCascade rows have `status="pending"` for ≤24h before the admin banner alerts. Phase 4 cron automates the alert. |
| Service key rotation stale | On `BIOMETRIC_GONE`, treat as success (the template is gone, the desired postcondition is met, clear the pending row). |
| Phase 4 capture change disrupts Phase 2 data | The clinic's `biometric/` app exposes a stable HTTP API; the capture client behind the stub template can be swapped without DB migration. |
| `User.delete()` semantics differ across call sites | The signal fires on `post_delete`, which runs after the local delete commits. Soft-delete (the `deleted_at` pattern) is the responsibility of the call site, not the signal. Phase 2 documents this. |

---

## 12. Open items (decision required before tasks.md)

These mirror proposal §5; the design review may resolve some.

1. **`PendingCascade.sucursal_id` type** — proposal §5.1 hints IntegerField;
   this design locks it. Decision: `IntegerField`, no FK. **Locked.**
2. **Retry policy numbers** — `max_retries=5, default_retry_delay=30s` are
   Phase 2 defaults. Production tuning (Phase 4) may use exponential
   backoff. **Locked at defaults for Phase 2.**
3. **Reconcile command cron** — out of Phase 2 scope. **Deferred.**
4. **Soft-delete vs hard-delete hook coverage** — the signal covers both
   (any `.delete()` call). A future model with `deleted_at` would need
   a separate handler. **Locked at any-delete() for Phase 2.**
5. **CitaMedica UUID stability** — `biometric_external_id` is stable
   across re-enrollments. **Locked.**

---

## 13. ADR-style decisions log

### ADR-0001: `Sucursal.dp4500_service_key_id` is `CharField`, not FK

Per §1.4 invariant 6. Cross-project FKs would couple the clinic's
ORM to DP4500's models. The reference is by integer pk, stored in a
CharField for forward compat (Phase 4 may store a UUID instead).

### ADR-0002: Phase 2 supports only the `env` key-store backend

Per §8. The `vault` backend is Phase 4 polish. Keeping Phase 2's
backend count to 1 keeps the spec and code under 100KB and gives
operators a minimal mental model: one env var per branch.

### ADR-0003: Phase 4 capture swap is a template-only change

The `capture_pending.html` template is the single touch-point. The
URL contract (`/wizard/enroll/`), the underlying `BiometricEnrollmentRecord`
writes, and the `biometric_external_id` flow all stay constant. Phase 4
replaces the template body with the real capture client and adds an
optional `enrollment_strategy` value; no DB migration.

### ADR-0004: Signature is a Phase 2 stub

DP4500's `ConsumeServiceIdentityChallenge` accepts `{challenge_id,
signature, timestamp}` but currently treats the signature as a
well-formed payload (Phase 1 verification is also stubbed per
Phase 1's `service-biometric-operations` spec). Phase 2 mirrors that.
Real Ed25519 lands with the capture client in Phase 4 and Phase 1's
`service-biometric-operations` upgrade.

### ADR-0005: Cross-project reference stored as `dp4500_service_key_id`, not ForeignKey

Echo of ADR-0001. Reinforces that no `apps.biometric.*` model imports
`accounts.ServiceAPIKey` (which lives in DP4500's `apps/accounts/`).
The clinic reads the raw token out-of-band from env/vault; the integer
pk is for debugging and visibility only.

---

## 14. Cross-cutting concerns (unchanged)

- Knox session authentication across the clinic (existing).
- The clinic's `apps/biometric/admin.py` (NEW) registers
  `PendingCascade` and `BiometricEnrollmentRecord` as read-only
  admin views so operators can triage rows.
- The clinic's `mypy.ini` / `ruff.toml` settings apply to the new
  `biometric/` app the same as everywhere else.

---

## 15. References

- `docs/plans/2026-09-27-biometric-web-integration.md` — the plan (§Phase 2).
- Phase 1 SDD artifacts at `C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1\`,
  especially `design.md` §3 (`Service API authentication`), §4 (`Cross-system
  identity linking`), §6 (`Service endpoint contracts`).
- `backend/users/models.py` (this repo) — User model.
- `backend/citas/models.py` (this repo) — `CitaMedica` and
  `REALIZADA_PENDIENTE_VERIFICACION`.
- `backend/catalogs/models.py` (this repo) — `Sucursal`.
- `openspec/changes/dp4500-biometric-auth/specs/biometric-authentication/spec.md`
  (sibling's Phase 1 spec) for the wire contract being consumed.

---

## 16. Predecessor artifact chain

`docs/plans/2026-09-27-biometric-web-integration.md`
  ↓
`C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1\{proposal,specs/*,design,tasks,archive-report}.md`
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/proposal.md`
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/specs/{dp4500-service-client,wizard-biometric-enrollment,cita-biometric-verification,cascade-biometric-revoke}/spec.md`
  ↓
**`openspec/changes/dp4500-host-app-integration-phase2/design.md`** (this file)
  ↓
`openspec/changes/dp4500-host-app-integration-phase2/tasks.md` (next)
  ↓
apply → verify → archive

---

**Design locked (5 ADRs). Ready for tasks.md.**