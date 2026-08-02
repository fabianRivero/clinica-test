# Archive Note: reset-pdf-baseline — FK nullification follow-up

This note documents a follow-up to the archived `reset-pdf-baseline` change.

## What changed

The archived `tasks.md` (16/16 complete) is preserved byte-stable. The follow-up
adds ONE ADDED requirement to the canonical spec at
`openspec/specs/seed-orchestrators/spec.md`, mirrored verbatim into the
archive's `specs/seed-orchestrators/spec.md`.

## Why a follow-up was needed

The archived implementation invoked `purge_data_keep_admin` (which sets
`PRAGMA foreign_keys = OFF` for SQLite and then `DELETE FROM sucursales`)
followed by `seed_pdf_baseline`, all inside one `@transaction.atomic`. With FKs
disabled, Django did not null the `sucursal_id` on preserved `Usuario` rows
that pointed to the now-deleted Sucursal. When the outer atomic block
committed, SQLite re-ran `PRAGMA foreign_key_check` and raised
`IntegrityError: FOREIGN KEY constraint failed`.

The fix: a pre-purge step that nullifies `Usuario.sucursal_id` on every
preserved superuser BEFORE the inner purge runs. The selection of preserved
users mirrors `purge_data_keep_admin`'s default (no `--username` → all
`is_superuser=True`). The nullification uses a queryset `.update(sucursal=...)`
so it bypasses any pre-save hooks.

## New requirement (mirrored in both spec files)

### Requirement: Pre-Purge Foreign-Key Nullification

`reset_pdf_baseline.handle` MUST nullify the `sucursal_id` (and any other
foreign key on `Usuario` that points to a table the inner purge is about to
clear) on every preserved superuser BEFORE invoking
`call_command("purge_data_keep_admin", "--force", ...)`. The nullification MUST
be performed via a queryset
`Usuario.objects.filter(pk__in=preserved_ids).update(sucursal=None)`. The
selection of preserved users MUST mirror the selection used by
`purge_data_keep_admin` when no `--username` is passed (i.e.,
`is_superuser=True`). The command MUST emit a `WARNING`-styled line indicating
how many preserved superusers had their `sucursal_id` nullified.

Plus three new scenarios covering the nullification, the full-waveform
commit clean, and the rollback-on-seed-failure path.

## Files modified in the follow-up

| File | Action |
|------|--------|
| `backend/accounts/management/commands/reset_pdf_baseline.py` | Added pre-purge FK nullification step (between `require_dev_or_test()` and the DESTRUCTIVE WIPE header) |
| `backend/accounts/tests/test_reset_pdf_baseline.py` | Added 5 new tests covering the nullification, warning line, AST guard, full-waveform commit, and seed-failure rollback |
| `openspec/specs/seed-orchestrators/spec.md` | Mirrored the new ADDED requirement |
| `openspec/changes/archive/2026-08-01-reset-pdf-baseline/specs/seed-orchestrators/spec.md` | Mirrored the new ADDED requirement |
| `openspec/changes/archive/2026-08-01-reset-pdf-baseline/tasks.md` | UNCHANGED (byte-stable) |
| `backend/accounts/management/commands/{seed_pdf_baseline,seed_client_baseline,purge_data_keep_admin}.py` | UNCHANGED (byte-stable) |
| `backend/accounts/management/_baselines/env_guard.py` | UNCHANGED (byte-stable) |

## Test evidence

`DJANGO_USE_LOCAL_DB=1 python3 manage.py test accounts.tests`

- 21/21 tests in `accounts.tests.test_reset_pdf_baseline` PASS (16 original + 5 new).
- 76/76 tests in `accounts.tests` PASS.

## Verdict

PASS.
