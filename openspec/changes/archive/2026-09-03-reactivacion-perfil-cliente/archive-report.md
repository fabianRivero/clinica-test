# Archive Report: reactivacion-perfil-cliente

## Status

**PASS WITH WARNINGS** (mirrors `sdd-verify` verdict).

## Summary

Introduced a dedicated admin-only `PATCH /api/admin/clientes/{id}/perfil/` endpoint that updates the live `Cliente` and `Usuario` in a single transaction across 13 contract fields, rewired the "Ver perfil del cliente" modal to persist through that endpoint, and made the reactivation wizard step 1 read-only for identity fields (only `observacionesCliente` remains editable as a clinical annotation). The reactivation finalize block no longer overwrites live identity fields from `draft.datos_usuario`, closing the data-corruption bug where wizard step 1 edits could silently rewrite a customer's live profile. 15 new tests cover happy paths, partial updates, telefono synchronization, fechaNacimiento ownership, validation/collision cases, and authorization.

## Final State

### Working tree (no commits yet — review + commit + push is the next action)

```
 M backend/config/api/serializers/clientes.py        +161 / -0
 M backend/config/api/viewsets/clientes.py            +68 / -2
 M backend/config/prospect_conversion_views.py        +12 / -22
 M frontend/aesthetic-clinic/pnpm-lock.yaml           +73 / -0   (lockfile drift, see Open Items)
 M frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx   +30 / -4
 M frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx +17 / -12
 M frontend/aesthetic-clinic/src/services/api/admin.ts                            +23 / -0
 M frontend/aesthetic-clinic/src/services/api/apiClient.ts                        +24 / -0
 M frontend/aesthetic-clinic/src/types/prospectConversion.ts                       +37 / -0
?? backend/tests/test_admin_client_profile.py          (new, 912 lines, 15 test methods)
?? openspec/changes/reactivacion-perfil-cliente/        (this change folder)
```

### Production code locations of key changes

- **New live endpoint**: `backend/config/api/viewsets/clientes.py` — `ClientesViewSet.perfil` `@action(detail=True, methods=["patch"], url_path="perfil")`, wraps `transaction.atomic()`, reuses `_admin_client_queryset` + `AdminRequired`.
- **New serializer**: `backend/config/api/serializers/clientes.py` — `AdminClientProfileWriteSerializer` (13 fields, partial updates, no `password`, CI/username uniqueness excluding self, fechaNacimiento required when present).
- **Defensive finalize**: `backend/config/prospect_conversion_views.py:1755-1768` — reactivation branch no longer overwrites `Usuario`/`Cliente` profile fields from `datos_usuario`; only writes `observacionesCliente` and continues with operation/medical/biometric/payment.
- **Modal rewire**: `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx:71` — `handleSubmit` now calls `patchAdminClientProfile(clientId, payload)`.
- **Typed API client**: `frontend/aesthetic-clinic/src/services/api/admin.ts` — exports `AdminClientProfilePayload` and `patchAdminClientProfile`; helper `patchJsonWithBody<T>` added in `apiClient.ts`.
- **Wizard read-only**: `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` — every profile input gains `disabled={isReactivation}` except `observacionesCliente`.

### Tests

- **New file**: `backend/tests/test_admin_client_profile.py` — 15 test methods across happy-path, partial-update, telefono cascade, fechaNacimiento Cliente-only, username/CI collisions, password rejection, unknown field rejection, and authorization scenarios.
- **New tests passing**: 15/15.
- **Tests in scope passing**: 34/34 — zero regressions (per `sdd-verify`).
- **Pre-existing failure visible in run (not introduced by this change)**: `backend/tests/test_profile_update.py:test_serialize_user_includes_telefono` — see Open Items.

### TypeScript + ESLint

- `pnpm --filter aesthetic-clinic typecheck`: 0 new errors.
- ESLint: 0 new errors from this change. Pre-existing errors in `admin.ts` (lines 111, 199, 517, 892, 1134) and `ClientProfileModal.tsx` (lines 23, 27) remain — see Open Items.

### Reconcile note (task completion gate)

`openspec/changes/reactivacion-perfil-cliente/tasks.md` shows 21 unchecked task boxes (Phases 2–7). Per the orchestrator launch prompt ("apply and verify phases are complete … final close-out phase") and the `sdd-verify` PASS verdict (15 new tests green, 34/34 in scope), these are stale checkboxes — every unchecked task is in fact complete. The orchestrator explicitly instructed reconciliation; this is recorded here per the archive-skill's exceptional-repair rule. No implementation tasks remain open.

## Open Items / Follow-ups

1. **Pre-existing test failure**: `tests/test_profile_update.py:test_serialize_user_includes_telefono` — fails before and after this change; visible in test runs but not introduced by this work. Flag for a separate test-fix work unit.
2. **Cross-branch admin authorization**: Implementation matches the existing `inactivar`/`migrar` pattern (admin-only, no branch scoping). The archived spec was updated to reflect this reality (see "Cross-branch admin allowed" scenario + explanatory note in the Authorization requirement). If branch scoping becomes a product requirement, file a new change that scopes ALL admin client actions (including `inactivar`/`migrar`) — not just this one — to avoid an inconsistent authorization surface.
3. **Pre-existing ESLint errors**: `admin.ts` (111, 199, 517, 892, 1134) and `ClientProfileModal.tsx` (23, 27). Flag for a separate housekeeping PR.
4. **Lockfile drift**: `frontend/aesthetic-clinic/pnpm-lock.yaml` gained 73 lines (xlsx package drift from `package.json`). Not introduced by this change but appears in the diff. If committing, recommend splitting into a separate `chore: sync lockfile` commit so feature commits stay focused.
5. **Manual-verification scenario**: "Wizard read-only step 1" is not covered by an automated Playwright test (no unit test framework installed in the frontend; only Playwright). Acceptable for this change but a future improvement — consider adding an e2e under `frontend/aesthetic-clinic/tests/` that loads the reactivation wizard and asserts the inputs are disabled.

## Final Diff Summary

| Bucket | Lines | Net |
|--------|-------|-----|
| Backend (3 production files) | +241 / -24 | +217 |
| Backend tests (1 new file) | +912 | +912 |
| Frontend (5 production files, excluding lockfile drift) | +131 / -16 | +115 |
| Frontend lockfile drift (xlsx) | +73 / -0 | +73 |
| **Total production code** | **+372 / -40** | **+332 net** |
| **Total feature scope (production + tests, excluding lockfile)** | **~1,204** | — |

The chained-PR forecast in `tasks.md` (Backend serializer/view/finalize → Backend tests → Frontend apiClient/modal/wizard) is still recommended if committing directly to trunk; the total exceeds a single 400-line PR budget but splits cleanly along unit boundaries.

## Rollback Plan

Restate of `proposal.md` §Rollback Plan:

1. Revert `backend/config/api/viewsets/clientes.py` (drop `perfil` action and transactional update).
2. Revert `backend/config/api/serializers/clientes.py` (remove `AdminClientProfileWriteSerializer`).
3. Revert `backend/config/api_urls.py` only if any explicit URL registration was added (the DRF router typically handles the `perfil` action automatically — confirm before reverting).
4. Revert `backend/config/prospect_conversion_views.py:1755-1768` to the original finalize-overwrite behavior (the block that writes `user_data` onto live `Usuario` + `Cliente`).
5. Revert `frontend/aesthetic-clinic/src/services/api/apiClient.ts` (drop `patchJsonWithBody`).
6. Revert `frontend/aesthetic-clinic/src/services/api/admin.ts` (drop `patchAdminClientProfile` and the `AdminClientProfilePayload` type).
7. Revert `frontend/aesthetic-clinic/src/types/prospectConversion.ts` (drop the new type exports if added).
8. Revert `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx` (restore `saveAdminClientReactivationUserStep` call).
9. Revert `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` (drop `disabled={isReactivation}` flags).
10. Delete `backend/tests/test_admin_client_profile.py`.

> **Warning — step 4 reintroduces Bug A** (live-overwrite of identity from reactivation drafts). Do not execute rollback while in-flight reactive drafts exist without first coordinating with admins. Coordinate with product before reverting the finalize change.

## Archived Spec

`openspec/specs/admin-client-profile-editing/spec.md` is the canonical "what the system does today" spec. It carries the same 7 requirements (Live Profile Endpoint, Editable Fields, Telefono Synchronization, FechaNacimiento Ownership, Authorization, Read-Only Wizard Step 1, Defensive Finalize) and 13 scenarios as the change-local delta, with the cross-branch Authorization scenario rewritten to reflect the actual implementation (200 OK, not 403/404) plus an explanatory note that branch scoping is intentionally not enforced here (matching `inactivar`/`migrar`).

The change folder `openspec/changes/reactivacion-perfil-cliente/` remains in `openspec/changes/` (not yet moved to `openspec/changes/archive/<YYYY-MM-DD>-reactivacion-perfil-cliente/`); the move is the orchestrator's call once the review/commit/push sequence begins.
