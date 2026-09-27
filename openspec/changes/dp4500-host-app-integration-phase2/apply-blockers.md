# Apply blockers for Phase 2

This change (`dp4500-host-app-integration-phase2`) locked the full SDD
(proposal + 4 specs + design + tasks) but **did not apply**. The three
apply-blocking items below are the things that stop the implementation
in `proyecto C` from being a clean TDD cycle.

Resolve these in another session, then continue with the tasks list
in `tasks.md`.

---

## 1. Backend app structure mismatch

The SDD artifacts reference `apps/biometric/{client,models,views,...}.py`.
This repo (`proyecto C`) uses a flat `backend/<appname>/` layout, not a
nested `backend/apps/<appname>/` layout. The existing
`backend/biometric/` app already hosts the legacy fprintd-based biometric
flow.

**Options to resolve:**

- **(a) Extend the existing `biometric/` app.** Add `client.py`,
  `host_models.py`, `host_signals.py`, `host_tasks.py`, `host_views.py`,
  `host_urls.py` under `backend/biometric/`. Pro: minimal churn.
  Con: namespace mixing with the legacy code; reviewers see one
  confusingly-large app.
- **(b) New sibling app.** Create `backend/dp4500_integration/` (or
  similar) to host the Phase 2 code separately from the legacy biometric
  app. Pro: clean separation; Phase 4 deprecation of `biometric/` is
  easier. Con: `INSTALLED_APPS` change; URL routing changes.
- **(c) Defer apply.** Land the SDD in a docs-only commit and pick a
  structural option once it is decided.

**Locked decision**: NONE. Reviewer picks.

---

## 2. Cascade hook requires a Celery-equivalent for "best-effort with retry"

The design (§6) specifies `@shared_task` for the cascade revoke use
case. This repo does not have Celery installed; there is no worker
infrastructure. Three paths forward:

- **(a) Adopt Celery.** Add `celery>=5.3` + `kombu>=5.3` to
  `requirements.txt`. Configure a broker (Redis or filesystem),
  configure `CELERY_*` settings, document a worker bootstrap.
  Estimated: half a day of plumbing, including a minimal dev-mode
  worker that the existing `manage.py runserver` can spawn in a
  thread for local testing. Pros: design-compliant; the long-term
  path. Con: ops overhead, more dependencies.
- **(b) Threading-based fire-and-forget.** In the `post_delete` signal
  handler, spawn `threading.Thread(target=cascade_revoke_template(...),
  daemon=True).start()`. The thread does the HTTP call with manual
  retry; on permanent failure, it updates `PendingCascade` to
  `status="failed"`. Pros: zero new dependencies; works in this repo
  as-is. Con: threads die with the request process; not safe for
  multi-worker WSGI deployments; harder to observe/monitor.
- **(c) Synchronous cascade.** Drop the PendingCascade row entirely.
  The signal handler calls `client.delete_template(...)` directly. On
  BiometricUnavailable, log and continue (orphan at DP4500).
  Pros: simplest. Con: **violates §1.4 invariant 5** ("signal-side
  failure does NOT roll back the local delete"). The local delete
  succeeds even on DP4500 outage, leaving an orphan until a future
  `reconcile_pending_cascades` run. This is option (b) without retry.

**Locked decision**: NONE. Design assumes (a) explicitly. Reviewer
picks (a), (b), or (c) and the design document is updated to match.

---

## 3. `BiometricExternalId` UUID generation timing

The design (§7.1) places a `pre_save` signal on User that generates the
UUID on `INSERT`. The existing `User` model in this repo
(`backend/accounts/models.py`) already has extensive `pre_save` and
`post_save` signals. We need to verify:

- The signal order: which signal runs first when an `INSERT` with no
  primary key hits `User.objects.create()`? Django evaluates
  `pre_save` before the row is persisted; the `pk` attribute is set
  in `__init__` for `Model.__init__`, not in `pre_save`. The design
  assumes `instance.pk is None` is a reliable INSERT signal — it is,
  but worth verifying against the actual clinic's User model.

**Locked decision**: NONE. Worth checking while implementing 2.1.

---

## Resolution plan

When the apply phase begins, revisit this document. The locked
decisions here drive the implementation of `tasks.md`:

- §1 structural choice → which folder layout
- §2 cascade runner → sync / threaded / Celery
- §3 UUID timing → verified or adjusted pre_save hook

A follow-up commit on this branch may amend `design.md` to match
the applied decisions before the apply commit(s) land.
