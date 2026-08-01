# Design: Reform Database Seed Scripts

## Technical Approach

Lock `seed_client_baseline` behavior on current models by extracting a project-local
`backend/accounts/management/_baselines/clean_baseline.py` library that produces the
exact current aesthetic baseline (Laser type, three procedures, treatment-service
links, plus the existing roles/branch/admin/kiosk/sectors). The clean command
becomes a thin orchestrator over that library, preserving its CLI surface,
validation, prompts, atomic transaction, idempotency, and non-destructive
semantics. `seed_pdf_baseline` is rewritten to call the same library for the
shared clean baseline and then add a deterministic demo layer; a pre-transaction
environment guard rejects any `ENVIRONMENT` value outside `{development, test}`
with `CommandError` and no confirmation override. The hard-coded admin URL
footer is replaced by `settings.SEED_ADMIN_URL` with a `BASE_URL + "/admin"`
fallback. Cross-command consistency is guaranteed by importing the three
aesthetic procedures from one literal table.

## Architecture Decisions

| # | Decision | Choice | Alternatives | Rationale |
|---|----------|--------|--------------|-----------|
| D1 | Library location | `backend/accounts/management/_baselines/clean_baseline.py` (Python package, leading underscore → not auto-discovered as commands) | `backend/common/seed_baseline.py`; new `seedlib` app | Lives next to the commands that own it; matches `accounts/management/commands/` neighbor structure; avoids a third app per proposal rule; stays importable by both commands without making it a Django command. |
| D2 | Canonical `TipoServicio.tipo` identity | `"Tratamiento estetico"` (unaccented) | `"Tratamiento estético"` | Clean baseline is the production bootstrap; 13 existing tests already assert the unaccented spelling on `ServicioConfig`; choosing the PDF spelling would force 13 test edits and change operator-facing strings in production. PDF command converges. |
| D3 | Migration of legacy accented row | One-shot data migration `catalogs/0007_normalize_tipo_servicio_estetico.py` that renames `Tratamiento estético` → `Tratamiento estetico` and reassigns dependent `ServicioConfig.tipo_servicio_id` rows inside the same transaction. Library uses `update_or_create(tipo=...)` on the canonical spelling only. | Coexistence via normalization in Python | Spec says "reconciled to one value without retaining both current spellings"; a migration is the cleanest way to honor that without leaving an orphan row. `PROTECT` FK in `ServicioConfig.tipo_servicio` blocks DELETE, but reassignment is safe. |
| D4 | URL derivation helper | `accounts/management/_baselines/url.py::resolve_admin_url()` reads `settings.SEED_ADMIN_URL` (env-backed via `os.getenv` in settings), normalizes trailing slash, falls back to `settings.BASE_URL + "/admin"`; raises `ValueError` when neither is an absolute `http(s)://` URL. | Hard-code in command; env-only | Spec mandates both sources; helper is reusable by any command that prints a summary. |
| D5 | Env guard for PDF command | `accounts/management/_baselines/env_guard.py::require_dev_or_test(env_value)` reads `settings.ENVIRONMENT` (or `os.getenv("ENVIRONMENT")`), raises `CommandError` with explicit message and self.stdout `rejected` line. Pre-transaction. No `--force` flag. | Confirmation prompt override | Spec forbids confirmation override; hard rejection is the safest pattern. |
| D6 | Demo admin separation | PDF command creates `admin.demo` (distinct username) in addition to whatever the clean-baseline admin is; tests assert both usernames coexist. | Reuse `admin.general` | Spec mandates "dedicated demo administrator distinct from the clean-baseline admin"; avoids stomping on the operator's real superuser. |
| D7 | Determinism | All `update_or_create` on stable natural keys; demo patients/prospects/kiosks use fixed UUID-free identifiers (`prospecto.demo1`, `cliente.demo1`, `KIOSKO-DEMO-PRINCIPAL`); no `timezone.now()` outside fixed demo timestamps captured in module-level constants. | Random IDs, time-dependent IDs | Guarantees byte-stable record counts across reruns; matches spec. |
| D8 | Non-destructive PDF | Remove `_clear_business_data` and `_clear_schedule_configuration` blocks; delete the `Rol.objects.filter(rol="ADMINISTRADOR").delete()` line; never call `Model.objects.all().delete()` on operational tables. Existing rows from a previous PDF run become orphans only if natural keys change — they do not. | Keep purges behind a flag | Spec mandates non-destructive; rollback is automatic via FK PROTECT. |
| D9 | Transaction boundary | One `with transaction.atomic():` in each command covering all writes from that invocation. Library functions are **not** decorated with `@transaction.atomic`; they participate in the caller's transaction via Django's default atomicity rules. | Library owns transaction | Keeps the existing single all-or-nothing boundary explicit and testable (`test_transaction_rollback_on_failure`). |
| D10 | Cross-command consistency | Both commands call `clean_baseline.seed_aesthetic_catalog(tipo_servicio_tratamiento_name=...)` with the same canonical literal `"Tratamiento estetico"`. | String constants duplicated | Single source of truth for the three aesthetic procedure literals; PDF command no longer maintains its own copy. |

## Data Flow

```
seed_client_baseline.handle()
   └── with transaction.atomic():
         ├── _seed_roles()              ─┐
         ├── _seed_branch(values)        │  (kept in command,
         ├── _seed_admin(roles,...)      │   preserve CLI contract)
         ├── _seed_kiosk(branch,...)     │
         ├── clean_baseline.seed_aesthetic_catalog()  ◄── single source
         └── _seed_sectors()            ─┘
   └── resolve_admin_url() → print summary footer

seed_pdf_baseline.handle()
   ├── require_dev_or_test(settings.ENVIRONMENT)   ◄── pre-transaction guard
   └── with transaction.atomic():
         ├── clean_baseline.seed_roles()
         ├── clean_baseline.seed_branches()
         ├── clean_baseline.seed_admins(usernames=("admin.general","admin.norte","admin.sur","admin.demo"))
         ├── clean_baseline.seed_staff(...)
         ├── clean_baseline.seed_aesthetic_catalog()
         ├── clean_baseline.seed_form_configuration()
         ├── clean_baseline.seed_prospects()
         ├── clean_baseline.seed_formal_patients()
         ├── clean_baseline.seed_schedules()
         └── clean_baseline.seed_tablet_kiosks()
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/accounts/management/_baselines/__init__.py` | Create | Empty package marker. |
| `backend/accounts/management/_baselines/clean_baseline.py` | Create | Library: `seed_roles`, `seed_branches`, `seed_admins`, `seed_staff`, `seed_aesthetic_catalog`, `seed_form_configuration`, `seed_prospects`, `seed_formal_patients`, `seed_schedules`, `seed_tablet_kiosks`. Pure `update_or_create` on stable natural keys. No transaction decorator. |
| `backend/accounts/management/_baselines/url.py` | Create | `resolve_admin_url() -> str`; raises `ValueError` when neither source is absolute `http(s)://`. |
| `backend/accounts/management/_baselines/env_guard.py` | Create | `require_dev_or_test(env_value) -> None`; raises `CommandError` outside `{development, test}`. |
| `backend/accounts/management/commands/seed_client_baseline.py` | Modify | Replace inline catalog literals with `clean_baseline.seed_aesthetic_catalog()`; replace footer `https://reactproject.site/admin` with `resolve_admin_url()`; existing 793-line structure kept otherwise. |
| `backend/accounts/management/commands/seed_pdf_baseline.py` | Rewrite | New `handle()` calls guard, then library helpers; remove `delete()` blocks and the `ADMINISTRADOR` purge; add `admin.demo`; deterministic seed constants. |
| `backend/config/settings.py` | Modify | Add `BASE_URL = os.getenv("DJANGO_BASE_URL", "http://localhost:8000")` and `SEED_ADMIN_URL = os.getenv("DJANGO_SEED_ADMIN_URL", "")` and `ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "development")`. |
| `backend/catalogs/migrations/0007_normalize_tipo_servicio_estetico.py` | Create | Data migration: rename `Tratamiento estético` → `Tratamiento estetico` and reassign dependent `ServicioConfig` rows; no-op when both already canonical. |
| `backend/accounts/tests/test_seed_client_baseline.py` | Modify | Preserve 13 tests byte-stable; add: `test_admin_url_uses_settings_seed_admin_url`, `test_admin_url_falls_back_to_base_url`, `test_aesthetic_set_complete_when_partial`, `test_allergy_catalogs_unchanged`, `test_invalid_url_aborts_pre_write`. |
| `backend/accounts/tests/test_seed_pdf_baseline.py` | Create | `test_env_guard_rejects_production`, `test_env_guard_accepts_development_and_test`, `test_deterministic_record_counts_across_runs`, `test_demo_admin_distinct_from_clean_admin`, `test_no_delete_calls_on_operational_tables` (introspect source AST), `test_full_baseline_reproduction`. |
| `docs/vps-setup-from-scratch.md` (5.2) | Modify | One paragraph each: `SEED_ADMIN_URL` / `BASE_URL` override + `ENVIRONMENT` guard for PDF command. |

## Interfaces / Contracts

```python
# clean_baseline.py
def seed_roles() -> dict[str, "Rol"]: ...
def seed_branches(branches: list[dict]) -> dict[str, "Sucursal"]: ...
def seed_admins(admins: list[dict]) -> dict[str, "Usuario"]: ...
def seed_staff(specialists: list[dict]) -> tuple[dict, dict]: ...
def seed_aesthetic_catalog() -> dict: ...
def seed_form_configuration(sectors: dict) -> None: ...
def seed_prospects(branches: dict) -> dict: ...
def seed_formal_patients(role: "Rol", branches: dict) -> dict: ...
def seed_schedules(specialists: dict) -> None: ...
def seed_tablet_kiosks(branches: dict) -> list[dict]: ...

# url.py
def resolve_admin_url() -> str: ...   # raises ValueError on bad config

# env_guard.py
def require_dev_or_test(env_value: str | None) -> None:  # raises CommandError
```

Idempotency: every `update_or_create` on the natural keys verified by
`exploration.md`. No `delete()` on operational tables. Library functions
do not start their own transaction — they participate in the caller's
`transaction.atomic()` block.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | URL helper, env guard, library helpers | `accounts/tests/test_clean_baseline.py`: direct calls with in-memory SQLite. |
| Integration | `seed_client_baseline` end-to-end | Extend existing 13 tests; add URL/partial-completion/allergy/rollback cases. |
| Integration | `seed_pdf_baseline` end-to-end | New file: env guard (prod rejects pre-write, dev/test passes), deterministic record counts, dedicated admin, AST-level no-delete assertion, full-baseline reproduction. |
| Migration | `0007_normalize_tipo_servicio_estetico` | Forward + reverse run on SQLite and Postgres; assert no duplicate `TipoServicio.tipo` and `ServicioConfig.tipo_servicio_id` reassignment. |
| E2E | None (project has no e2e for Django commands) | — |

`pytest` is not installed; all tests run under `python manage.py test
accounts.tests`. No `pytest-doctest` wiring required.

## Migration / Rollout

1. Land `0007_normalize_tipo_servicio_estetico` first — it is a no-op on
   fresh databases and a one-shot rename on any database previously seeded
   by `seed_pdf_baseline`. Reassigns `ServicioConfig.tipo_servicio_id`
   inside the same migration transaction.
2. Land Work Unit A (clean baseline refactor + URL helper + tests). The
   existing 13 tests are the safety floor; the 5 new tests lock the URL
   and partial-completion behavior.
3. Land Work Unit B (PDF rewrite + env guard + new tests) as a chained
   PR. Operators who had `ENVIRONMENT` unset continue to default to
   `development` and can opt into rejection by setting
   `DJANGO_ENVIRONMENT=production`.
4. Rollback: each work unit is independently revertable. Work Unit A
   reverts with no data impact. Work Unit B reverts to the legacy
   `seed_pdf_baseline.py` (kept in git until B's tests pass).

## Chained Delivery

| Slice | Budget (additions+deletions) | Dependencies | Rollback test |
|-------|------------------------------|--------------|---------------|
| A1. `0007` migration + settings additions | <80 | none | Migration reverse runs; both FK rows intact |
| A2. Library package + URL/env helpers + 13-test preservation + 5 new client tests | <200 | A1 | Existing 13 tests still green; URL tests assert derivation paths |
| B1. `seed_pdf_baseline` rewrite using library + env guard + new tests | <400 | A2 | PDF guard test rejects prod pre-write; deterministic test re-runs identically |

Budget target: A1+A2 ≤ 280 lines, B1 ≤ 400 lines — within the 400-line
review budget. No additional chained PRs required.

## Open Questions

- [ ] Confirm with operator that `admin.demo` (not `admin.demo.pdf`) is the desired demo admin username.
- [ ] Confirm the demo PDF scenarios that must remain deterministic (current PDF command creates 2 prospectos + 2 demo patients with biometric/cita/cuota/pago history) — full recreation in B1 or reduced scenario set?
- [ ] Confirm `BASE_URL` default (`http://localhost:8000`) is acceptable when `SEED_ADMIN_URL` is unset.

## Risks

- `Tratamiento estetico` rename breaks any downstream code that imports
  the accented string. Mitigated by grep confirming zero non-seed callers.
- `ServicioConfig.tipo_servicio` is `on_delete=PROTECT`; the migration
  must reassign, not delete. Mitigated by atomic migration transaction
  and explicit reassignment step.
- Hard `CommandError` in PDF command means any environment without
  `DJANGO_ENVIRONMENT` set defaults to `development` and is allowed.
  Documented in 5.2.
- AST-level "no `delete()` on operational tables" test must be updated
  if `seed_pdf_baseline` ever legitimately needs to remove demo rows;
  mitigation: scope the test to the nine tables named in
  `exploration.md` only.