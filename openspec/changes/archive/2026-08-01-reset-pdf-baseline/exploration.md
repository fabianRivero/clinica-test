## Exploration: reset-pdf-baseline

### Scope (clarified by orchestrator + user brief, 2026-08-01)

This change adds a single new destructive orchestrator command:

- **`reset_pdf_baseline`** — new management command that, in one operator step, purges business data and re-seeds the PDF demo dataset. It composes two existing commands (`purge_data_keep_admin` + `seed_pdf_baseline`) inside a single `transaction.atomic` boundary, behind the same `require_dev_or_test()` env guard used by `seed_pdf_baseline`.

**Explicitly out of scope:**

- Modifying the source of `seed_pdf_baseline` or `seed_client_baseline` — both are sibling commands and stay byte-stable.
- Modifying `purge_data_keep_admin` — the new command invokes it as a callable subprocess (via `call_command` inside the transaction).
- Adding new dependencies; only stdlib + Django + the project's `accounts`/`catalogs`/`operations` models and the existing A2 baseline library are used.
- Production-grade features like audit trails, dry-run flags, or rollback hooks beyond what the underlying commands already provide.

This artifact documents the as-is state of the three building blocks and identifies the integration surface for the new command.

### Current State

#### `seed_pdf_baseline` — non-destructive orchestrator (rebuilt by reform-database-seed-scripts)

- File: `backend/accounts/management/commands/seed_pdf_baseline.py` (312 lines).
- `BaseCommand.help` declares the command non-destructive and pre-transaction guarded.
- Invocation: `ENVIRONMENT=development python manage.py seed_pdf_baseline`.
- Pre-transaction guard: `require_dev_or_test()` from `backend/accounts/management/_baselines/env_guard.py`. `production`, `staging`, empty, and any non-`{"development","test"}` value raise `CommandError` before the transaction opens. No override flag.
- `handle` is decorated with `@transaction.atomic` — all writes from one invocation commit together. Library helpers (`clean_baseline.seed_*`) participate in the caller's transaction; they do not own their own atomic block.
- Writes (idempotent via `update_or_create` on stable natural keys):
  - 4 `Rol` rows.
  - 3 `Sucursal` rows: `Sede Principal` (principal), `Sucursal Norte`, `Sucursal Sur`.
  - 4 admin users (`admin.general`, `admin.norte`, `admin.sur`, `admin.demo`) plus 4 specialist users (`lucia.laser`, `diego.tatuajes`, `sofia.manchas`, `rafael.consulta`).
  - 5 `Especialidad` rows + `EspecialistaEspecialidad` links.
  - Aesthetic catalog (shared via `clean_baseline.seed_aesthetic_catalog`).
  - `clinical.FichaSeccion` + `clinical.FichaCampo` form configuration.
  - Prospects, formal patients, schedules (Mon–Fri 08:00–18:00 for each specialist), and 3 tablet kiosks.
- Idempotent: byte-stable record counts across reruns (covered by `DeterministicRecordCountsAcrossRunsTests`).
- Tests: `backend/accounts/tests/test_seed_pdf_baseline.py` — 8 end-to-end + 2 AST/helper tests.

#### `seed_client_baseline` — production bootstrap (untouched)

- File: `backend/accounts/management/commands/seed_client_baseline.py` (794 lines).
- Production-facing: takes a real client's credentials via 10 value flags + 2 control flags and produces a fresh, atomic, validated, idempotent, non-destructive deployment baseline.
- Pre-transaction guard: `_validate_values` (no env guard; runs against any environment by design).
- One `transaction.atomic` boundary. Any failure rolls back everything.
- Out of scope for `reset_pdf_baseline` — the new command composes the PDF demo, not the production bootstrap.

#### `purge_data_keep_admin` — destructive purge (existing)

- File: `backend/accounts/management/commands/purge_data_keep_admin.py` (134 lines).
- Destructive. Wipes every table except `accounts.Rol`, `accounts.Usuario`, `auth.Group`, `auth.Permission`, `contenttypes.ContentType`. Preserved users default to `is_superuser=True` unless `--username <name>` is passed (repeatable). `--force` skips the "Escribe 'SI' para continuar" prompt.
- PostgreSQL path: `TRUNCATE TABLE ... RESTART IDENTITY CASCADE`. SQLite path: `PRAGMA foreign_keys = OFF`, `DELETE FROM <table>` per table, `DELETE FROM sqlite_sequence` per table, then `PRAGMA foreign_keys = ON`. Other vendors raise `CommandError`.
- Wraps the wipe in `with transaction.atomic():` so a mid-flight failure rolls back the purge itself.
- After the wipe, deletes every non-preserved user via `user_model.objects.exclude(pk__in=preserved_ids).delete()`.
- Has its own stdout summary and does NOT print a "destructive wipe" header. The new orchestrator must add that header.

#### Env guard (`require_dev_or_test`)

- File: `backend/accounts/management/_baselines/env_guard.py` (31 lines).
- Public API: `require_dev_or_test(env_value=None) -> None`. Reads `settings.ENVIRONMENT` when called with no argument.
- Raises `CommandError` if `env_value` is not in `{"development", "test"}` (case-insensitive, whitespace-stripped).
- The new command will call this function **before** opening its `transaction.atomic` so the failure is hard and pre-write.

### Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/accounts/management/commands/reset_pdf_baseline.py` | New | The orchestrator command itself; composes `purge_data_keep_admin` + `seed_pdf_baseline` inside a single `transaction.atomic` boundary. |
| `backend/accounts/tests/test_reset_pdf_baseline.py` | New | Env guard tests, idempotent destructive-then-seed waveform test, no-op on empty DB test, rollback on mid-flight failure test. |
| `backend/accounts/management/commands/seed_pdf_baseline.py` | Unchanged | Sibling command; only invoked, not modified. |
| `backend/accounts/management/commands/seed_client_baseline.py` | Unchanged | Sibling command; not invoked. |
| `backend/accounts/management/commands/purge_data_keep_admin.py` | Unchanged | Invoked as a callable subprocess; not modified. |
| `backend/accounts/management/_baselines/env_guard.py` | Unchanged | Imported and called; not modified. |

### Approaches

1. **Subprocess composition (recommended)** — the new command uses Django's `call_command("purge_data_keep_admin", "--force", ...)` and `call_command("seed_pdf_baseline")` from inside a `@transaction.atomic handle` method. The outer atomic block wraps both inner commands' transactions, giving a single all-or-nothing boundary.
   - Pros: Reuses existing commands verbatim — zero risk to `seed_pdf_baseline` or `purge_data_keep_admin`. The outer atomic block composes cleanly with the inner ones (innermost savepoints; outer rollback undoes everything). No new dependencies. Output from both commands stays intact.
   - Cons: `call_command` swallows the inner commands' stdout by default unless we capture and forward it; we need to pass `stdout=self.stdout` so operators still see progress. Inner transactions become savepoints inside the outer atomic — this is the standard Django pattern and is safe.
   - Effort: Low

2. **Inline composition** — copy-paste the body of `purge_data_keep_admin` into the new command and orchestrate the wipe directly.
   - Pros: No subprocess overhead; fewer moving parts inside the atomic block.
   - Cons: Duplicates 134 lines of purge logic; diverges from the canonical purge the moment either side is fixed; violates the "do not touch existing commands" rule in spirit. High regression risk.
   - Effort: Medium

3. **Shell-out composition (`subprocess.run(["python", "manage.py", ...])`)** — invoke each command via a new Python subprocess.
   - Pros: Each command runs in its own DB connection/transaction; no nested atomic semantics.
   - Cons: Two separate transactions; if the seed half fails, the purge already committed and the operator has lost data with no rollback. Defeats the whole point of the new command.
   - Effort: Low

4. **Wrapper script outside Django** — bash/zsh wrapper that runs `purge_data_keep_admin --force` and then `seed_pdf_baseline`.
   - Pros: No Django code needed; trivial.
   - Cons: Same as option 3 — no shared transaction. Operator must remember the order. No env guard at the wrapper level.
   - Effort: Low

### Recommendation

Adopt **Approach 1** (subprocess composition via `call_command` inside `@transaction.atomic`). It is the only option that:

- Preserves the "do not touch `seed_pdf_baseline` or `seed_client_baseline`" constraint.
- Achieves a true all-or-nothing boundary around both steps (so a mid-flight seed failure rolls back the purge).
- Reuses the A2 baseline library and `require_dev_or_test` guard exactly as they exist today.
- Stays under the 400-line review budget — the new command is expected to be ~70-90 lines plus tests.

The orchestrator command itself will look like this in shape:

```python
@transaction.atomic
def handle(self, *args, **options):
    require_dev_or_test()  # hard pre-write guard
    self.stdout.write(self.style.WARNING("=== DESTRUCTIVE WIPE ==="))
    self.stdout.write("This will erase all demo data and re-seed the PDF baseline.")
    # Optionally prompt for 'SI' to confirm (mirrors purge_data_keep_admin UX).
    call_command("purge_data_keep_admin", "--force", stdout=self.stdout)
    call_command("seed_pdf_baseline", stdout=self.stdout)
```

`call_command(..., stdout=self.stdout)` forwards the inner commands' progress so operators see "Base de datos vaciada correctamente." followed by "Base PDF demo cargada correctamente." in the same terminal session.

### Risks

- **`call_command` + nested `transaction.atomic`** — Django composes nested atomic blocks as savepoints. If the outer block rolls back, all inner savepoints roll back too. This is the documented, intended behavior and the safest option. The only edge case: if `purge_data_keep_admin` opens its connection with `set_autocommit(False)` outside the atomic block, the savepoint model still works, but any pre-atomic state must be checked.
- **PostgreSQL `TRUNCATE ... RESTART IDENTITY CASCADE` inside an outer transaction** — Postgres `TRUNCATE` is transaction-safe and can be rolled back. The outer atomic block will roll back the truncate on seed failure. Confirmed by Django docs.
- **SQLite path inside an outer transaction** — `PRAGMA foreign_keys = OFF` + per-table `DELETE FROM` + `DELETE FROM sqlite_sequence` is also transactional. The `PRUNCATE/DELETE` work will roll back on failure.
- **Output interleaving** — `call_command(..., stdout=self.stdout)` forwards stdout but each inner command's `_print_summary` is independent. The orchestrator must print its own "destructive wipe" header before calling the inner commands so the operator sees the warning up front.
- **Existing tests assume `DJANGO_USE_LOCAL_DB` and SQLite** — any new test must use the same harness. Tests run inside `transaction.atomic` by default, so they need to either opt out of that wrapping (`TransactionTestCase`) or mock the inner commands.
- **`seed_pdf_baseline` already uses `require_dev_or_test`** — calling it from inside `reset_pdf_baseline` will trigger the guard twice (once in our command, once in the inner). This is idempotent and safe — both raise the same `CommandError` if `ENVIRONMENT` is wrong. We only need the outer guard to fail fast on the same precondition.
- **Confirmation prompt** — `purge_data_keep_admin --force` skips the inner "Escribe 'SI'" prompt. The new command can either keep `--force` (one-click) or do its own confirmation. The brief says the command MUST "document clearly in output that this is a destructive wipe" — a single warning header is the minimum; an interactive prompt is optional but recommended for safety.

### Ready for Proposal

Yes. The proposal should:

1. Define a new capability `seed-orchestrators` whose purpose is "destructive or non-destructive orchestrator commands that compose baseline steps inside a single transaction".
2. Lock the `reset_pdf_baseline` command into that capability as `ADDED` requirements (no existing spec to MODIFY).
3. Document the rollback story: any failure inside the outer atomic block restores the DB to its pre-purge state.
4. State the explicit constraint that `seed_pdf_baseline` and `seed_client_baseline` source code is not touched.

---

## Result Contract (this exploration)

### status
`success`

### executive_summary
`reset_pdf_baseline` will compose the existing `purge_data_keep_admin` and `seed_pdf_baseline` commands inside a single `@transaction.atomic` boundary, behind the existing `require_dev_or_test()` env guard. The new command adds a clear "destructive wipe" stdout header, forwards inner commands' output, and reuses the A2 baseline library unchanged. The implementation is approach 1 (`call_command` inside outer atomic) — the only option that satisfies the "do not touch sibling commands" constraint AND a true all-or-nothing boundary.

### artifacts
- `openspec/changes/reset-pdf-baseline/exploration.md` — this file.
- Read-only verification sources (no modifications):
  - `backend/accounts/management/commands/seed_pdf_baseline.py`
  - `backend/accounts/management/commands/seed_client_baseline.py`
  - `backend/accounts/management/commands/purge_data_keep_admin.py`
  - `backend/accounts/management/_baselines/env_guard.py`
  - `backend/accounts/management/_baselines/clean_baseline.py`
  - `backend/accounts/tests/test_seed_pdf_baseline.py`

### next_recommended
1. Run `sdd-propose` to write the proposal — define a new `seed-orchestrators` capability, document intent and rollback.
2. Run `sdd-spec` to write the delta spec — `ADDED Requirements` for env guard, destructive wipe header, single transaction, idempotent waveform, no-op on empty DB.
3. Run `sdd-design` to lock the architecture — `call_command` composition inside `@transaction.atomic`, `require_dev_or_test` pre-write, `--force` for purge.
4. Run `sdd-tasks` — break the work into ~4-6 tasks across foundation / implementation / testing phases.
5. Run `sdd-apply` → `sdd-verify` → `sdd-archive` to close the cycle.

### risks
- Nested `transaction.atomic` semantics: documented and safe; savepoint model applies.
- `TRUNCATE` and `DELETE FROM` rollback semantics differ by vendor; both supported by Django atomic blocks.
- The new command inherits `seed_pdf_baseline`'s env guard; calling it from inside `reset_pdf_baseline` triggers it twice. Idempotent, safe.
- Output interleaving from `call_command`; mitigated by passing `stdout=self.stdout` and printing a destructive-wipe header up front.
- Existing test harness wraps each test in `transaction.atomic` by default; tests for atomic-rollback semantics must use `TransactionTestCase`.

### skill_resolution
- Loaded all eight phase skills from `/home/fabianrivero/.config/opencode/skills/{sdd-explore,sdd-propose,sdd-spec,sdd-design,sdd-tasks,sdd-apply,sdd-verify,sdd-archive}/SKILL.md`.
- Followed Section B (retrieval) + Section C (persistence) from `skills/_shared/sdd-phase-common.md`.
