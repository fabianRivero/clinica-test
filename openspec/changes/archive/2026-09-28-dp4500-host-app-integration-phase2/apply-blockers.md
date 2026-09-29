# Apply blockers for Phase 2

This change (`dp4500-host-app-integration-phase2`) locked the full SDD
(proposal + 4 specs + design + tasks) but **did not apply**. The two
apply-blocking items below are the things that stop the implementation
in `proyecto C` from being a clean TDD cycle.

Resolve these by reviewing the locked decisions below; they are
authoritative for the apply phase.

---

## 1. Backend app structure mismatch — **LOCKED: option (b)**

The SDD artifacts reference `apps/biometric/{client,models,views,...}.py`.
This repo (`proyecto C`) uses a flat `backend/<appname>/` layout, not a
nested `backend/apps/<appname>/` layout. The existing
`backend/biometric/` app already hosts the legacy fprintd-based biometric
flow.

**Locked decision (review session 2026-09-27, option b):** Create a new
sibling app `backend/dp4500_integration/`. Phase 2 code lives there.
The legacy `backend/biometric/` stays untouched and gets deprecated
cleanly in Phase 4.

**Implication for `design.md` §2 (Module layout):**

Replace `apps/biometric/` paths with `dp4500_integration/`:

```
backend/
├── dp4500_integration/                # NEW sibling app
│   ├── apps.py
│   ├── client.py                       # HTTPClient (Phase 2 §3)
│   ├── views.py                        # wizard step 4 + cita verify
│   ├── urls.py
│   ├── exceptions.py
│   ├── models.py                       # PendingCascade + BiometricEnrollmentRecord
│   ├── signals.py                      # post_delete → cascade hook
│   ├── tasks.py                        # Celery: cascade_revoke_template
│   ├── migrations/
│   └── templates/integration/
├── users/                              # MODIFIED: + biometric_external_id, pre_save signal
├── operations/                         # MODIFIED: + 3 biometric fields on CitaMedica
├── catalogs/                          # MODIFIED: + dp4500_service_key_id on Sucursal
└── ...
```

`INSTALLED_APPS` gains `"dp4500_integration.apps.Dp4500IntegrationConfig"`.
URL include at `/api/integration/dp4500/` (or similar) to keep it
distinct from the legacy `/api/biometric/`.

---

## 2. Cascade hook requires a Celery-equivalent — **LOCKED: option (a)**

The design (§6) specifies `@shared_task` for the cascade revoke use
case. This repo does not have Celery installed; there is no worker
infrastructure.

**Locked decision (review session 2026-09-27, option a):** Adopt
Celery. Add `celery>=5.3` + `kombu>=5.3` + a broker (filesystem for
dev, Redis for prod) to `requirements.txt`. Configure `CELERY_*`
settings in `config/settings.py`. Document a worker bootstrap step.

**Implication for `tasks.md` §2.2:**

Tasks 2.2.x as-written are Celery-shaped and require no design
changes. Add a new task to Commit 1 (or Commit 2):

- **2.2.0 NEW** `backend/config/celery.py` — Celery app instance bound
  to the Django settings module.
- **2.2.0.1** `backend/dp4500_integration/tasks.py` imports the
  Celery app for `@shared_task` discovery.
- **2.2.0.2** `manage.py` — import the Celery app at module load so
  `manage.py shell` picks it up.
- **2.2.0.3** `requirements.txt` — `celery>=5.3`, `kombu>=5.3`.
- **2.2.0.4** `config/settings.py` — `CELERY_BROKER_URL` (default
  `filesystem:///tmp/dp4500-celery`), `CELERY_RESULT_BACKEND`,
  `CELERY_TASK_ALWAYS_EAGER` for tests (so existing tests that exercise
  the cascade use eager mode without needing a worker).
- **2.2.0.5** Doc — short runbook section explaining how the operator
  starts a worker locally: `celery -A config worker -l info`.

---

## 3. `BiometricExternalId` UUID generation timing — verification only

The design (§7.1) places a `pre_save` signal on User that generates the
UUID on `INSERT`. The existing `User` model in this repo
(`backend/accounts/models.py`) already has extensive `pre_save` and
`post_save` signals. The implementer must verify:

- The signal order: which signal runs first when an `INSERT` with no
  primary key hits `User.objects.create()`? Django evaluates
  `pre_save` before the row is persisted; the `pk` attribute is set
  in `__init__` for `Model.__init__`, not in `pre_save`. The design
  assumes `instance.pk is None` is a reliable INSERT signal — it is,
  but worth verifying against the actual clinic's User model.

**Action item**: open `backend/accounts/apps.py` and `backend/accounts/signals.py`
during Commit 1 of apply. If the existing `User` model already has a
pre_save signal chain, ensure `assign_biometric_external_id` runs
*after* any signal that mutates `pk` (which is unusual but worth
checking). The implementation order is: import the new signal module
last in `apps.py.ready()`, so it registers last and runs last.

---

## Resolution plan

When the apply phase begins, follow these steps:

1. **Update `design.md` §2 (Module layout)** to use `dp4500_integration/`
   instead of `apps/biometric/`. This is a documentation-only change
   that should land as a follow-up commit on the same branch.
2. **Add Celery bootstrap tasks** to `tasks.md` (§2.2.0.* above) and
   update the `Pre-apply checklist` to include `manage.py check` for
   `djcelery` / Celery autodiscovery.
3. **Verify the pre_save timing** during Commit 1 of apply.
4. Proceed with the existing `tasks.md` work units (which assume the
   locked decisions above).
