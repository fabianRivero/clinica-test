# Design: reset-pdf-baseline

## Technical Approach

`reset_pdf_baseline` is a thin `BaseCommand` whose `handle` is decorated with `@transaction.atomic`. It composes `purge_data_keep_admin --force` and `seed_pdf_baseline` via `call_command` inside the atomic block, behind a pre-write `require_dev_or_test()` guard. Reuses the A2 baseline library, `env_guard.py`, and inner commands verbatim. No new modules, no new dependencies.

## Architecture Decisions

### Decision: Compose via `call_command`, not import-and-call

**Choice**: `call_command("purge_data_keep_admin", "--force", stdout=self.stdout)` and `call_command("seed_pdf_baseline", stdout=self.stdout)`.

**Alternatives**: import `Command` classes (bypasses argument parsing; violates sibling-stability in spirit); `subprocess.run` shell-out (two separate transactions; mid-seed failure cannot roll back the purge).

**Rationale**: `call_command` is the canonical Django pattern; runs inner commands in-process so the outer `@transaction.atomic` wraps both. Forwarding `stdout=self.stdout` preserves operator-visible progress.

### Decision: Pass `--force` to `purge_data_keep_admin`

**Choice**: Always pass `--force` so the inner `Escribe 'SI'` prompt is skipped.

**Alternatives**: add a `--confirm` flag on the new command (rejected: two-step confirmation is confusing); don't pass `--force` (rejected: makes the command interactive and brittle in CI).

**Rationale**: The new command is explicitly destructive; the `WARNING` header documents intent. `--force` keeps the operator one keystroke from a clean state.

### Decision: Use `@transaction.atomic` decorator, not `with transaction.atomic():`

**Choice**: Decorate `handle` with `@transaction.atomic`.

**Rationale**: Matches `seed_pdf_baseline.handle`'s existing pattern. Reads as "this whole method is one transaction".

### Decision: Use `TransactionTestCase` for the rollback test

**Choice**: The mid-flight-rollback test MUST extend `TransactionTestCase`.

**Rationale**: `TestCase` wraps each test in its own `transaction.atomic` savepoint, which itself rolls back on a simulated failure and masks the orchestrator's rollback. `TransactionTestCase` truncates tables between tests instead of using savepoints, so the outer `@transaction.atomic` semantics are observed exactly as in production.

## Data Flow

```
operator -> python manage.py reset_pdf_baseline
              |
              v
      reset_pdf_baseline.handle  (@transaction.atomic)
              |
              |-- require_dev_or_test() ---> CommandError if env != dev|test
              |-- self.stdout.write(WARNING "=== DESTRUCTIVE WIPE === ...")
              |
              |-- call_command("purge_data_keep_admin", "--force", stdout=self.stdout)
              |       (inner atomic becomes savepoint under outer atomic)
              |
              |-- call_command("seed_pdf_baseline", stdout=self.stdout)
              |       (inner atomic becomes savepoint under outer atomic)
              |
              v
      commit (or rollback on any inner exception)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/accounts/management/commands/reset_pdf_baseline.py` | Create | Orchestrator (~70 lines). |
| `backend/accounts/tests/test_reset_pdf_baseline.py` | Create | Tests (~180 lines). |
| `openspec/specs/seed-orchestrators/spec.md` | Create | Source-of-truth spec (during archive). |
| `seed_pdf_baseline.py`, `seed_client_baseline.py`, `purge_data_keep_admin.py`, `env_guard.py` | Unchanged | Sibling commands and shared helpers. |

## Interfaces / Contracts

No public Python interface beyond `BaseCommand`. No arguments.

```python
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.management._baselines.env_guard import require_dev_or_test


class Command(BaseCommand):
    help = (
        "Destructive orchestrator: purges business data and re-seeds the PDF "
        "demo baseline in a single transaction. Refuses to run outside "
        "development/test. Idempotent."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        require_dev_or_test()
        self.stdout.write(self.style.WARNING(
            "=== DESTRUCTIVE WIPE === "
            "All business data (preserving admin users) will be erased and "
            "the PDF demo baseline will be reseeded. Not reversible."
        ))
        call_command("purge_data_keep_admin", "--force", stdout=self.stdout)
        call_command("seed_pdf_baseline", stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("Reset PDF baseline complete."))
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Env guard | Reject `production`/`staging`/`""`; accept `development`/`test`. | `TestCase` + `override_settings(ENVIRONMENT=...)`. |
| Stdout header | `WARNING`-styled `DESTRUCTIVE WIPE` precedes inner output. | `TestCase`; capture `StringIO`; assert substring order. |
| AST guard | `handle` is `@transaction.atomic`; both `call_command` calls inside. | `TestCase`; `ast.parse` on source. |
| Idempotent | Two consecutive runs = byte-stable counts across 14 model tables. | `TestCase` + `override_settings`; `_record_counts()` helper. |
| No-op empty DB | Empty DB + run = identical to fresh `seed_pdf_baseline`. | `TestCase`; assert counts match. |
| Atomic rollback | Mocked `seed_pdf_baseline` raises; pre-existing rows still present. | `TransactionTestCase` + `mock.patch`. |
| Sibling non-modification | `git diff` shows no changes to siblings. | Subprocess: `git diff --name-only HEAD~1 HEAD -- <siblings>` is empty. |

## Migration / Rollout

No migration. The command is purely operational; no schema changes.

## Open Questions

None.
