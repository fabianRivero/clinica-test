# Tasks: reactivacion-perfil-cliente

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~430–530 |
| 400-line budget risk | Medium–High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Backend (serializer + view + URL + finalize) / PR 2: Backend tests / PR 3: Frontend (apiClient + admin.ts + modal + wizard + optional Playwright) |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium–High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend serializer + view action + URL + finalize defensive change | PR 1 | `python manage.py test backend.tests.test_admin_client_profile_edit -v 2` (will fail with skipped/no-method until PR 2 lands; PR 1 verifies import + admin via dev server smoke) | Manual: `curl -X PATCH` against running server or `python manage.py shell` roundtrip; N/A for full harness | Revert serializer, viewset action, URL, finalize block — independent of frontend |
| 2 | Backend tests for new endpoint and finalize non-overwrite | PR 2 (base = PR 1 branch) | `python manage.py test backend.tests.test_admin_client_profile_edit backend.tests.suspension.test_conversion_split backend.billing.tests.test_conversion_first_payment -v 2` | Django `TestCase` + `Client` (session auth) — same harness used by `test_profile_update.py` | Revert new test files; existing tests untouched |
| 3 | Frontend apiClient helper + typed admin client + modal rewire + wizard read-only | PR 3 (base = PR 2 branch) | `pnpm --filter aesthetic-clinic typecheck` + manual smoke | Manual browser smoke (no unit framework; Playwright optional add) | Revert apiClient.ts, admin.ts, ClientProfileModal.tsx, ConversionStepUser.tsx — frontend-only rollback |

## Phase 1: Backend Foundation (Unit 1)

- [x] **T-1.1** Append `AdminClientProfileWriteSerializer` to `backend/config/api/serializers/clientes.py` (~60 lines, files: `backend/config/api/serializers/clientes.py`)
  - Acceptance: 13 camelCase fields declared (`primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, `direccionDomicilio`, `observacionesCliente`); no `password` field; `partial=True` semantics; `validate_username` excludes `instance.usuario.pk`; `validate_ci` excludes `instance.pk`; `validate_fechaNacimiento` requires ISO date when present; `validate()` raises `"password is not editable through this endpoint"` if `password` is in payload; `update()` dispatches USER_FIELDS → `instance.usuario`, telefono → both rows, CLIENTE_FIELDS → `instance`, then `user.save()` + `instance.save()`.
  - Test: `python manage.py shell -c "from config.api.serializers.clientes import AdminClientProfileWriteSerializer; print(AdminClientProfileWriteSerializer)"` (import check).

- [x] **T-1.2** Add `@action(detail=True, methods=["patch"], url_path="perfil")` `perfil` method to `ClientesViewSet` in `backend/config/api/viewsets/clientes.py` (~45 lines, files: `backend/config/api/viewsets/clientes.py`)
  - Acceptance: method reuses `_admin_client_queryset().filter(pk=pk).first()`; returns 404 when missing; `AdminClientProfileWriteSerializer(data=request.data, partial=True)` validates; wraps `serializer.save()` in `transaction.atomic()`; returns 200 with `{"client": _build_initial_client_user_data(cliente)}`; uses existing `_build_initial_client_user_data` helper from `prospect_conversion_views.py` (import or relocate helper).
  - Test: `python manage.py check` (no errors) + `python manage.py runserver` then `curl -X PATCH http://localhost:8000/api/admin/clientes/1/perfil/ -H 'Content-Type: application/json' -d '{"primerNombre":"X"}'` returns 401/403 unauthenticated.

- [x] **T-1.3** Verify URL routing exposes `clientes/<int:pk>/perfil/` (~0 net lines, files: `backend/config/api_urls.py`)
  - Acceptance: existing DRF router registration already maps `ClientesViewSet` actions to `clientes/<pk>/<url_path>/`; no code change required. Confirm via `python manage.py show_urls | grep perfil` (or `python -c "from django.urls import get_resolver; ..."`).
  - Test: `python manage.py show_urls | grep clientes.*perfil` shows the route.

- [x] **T-1.4** Document response contract parity (~10 lines added to serializer docstring, files: `backend/config/api/serializers/clientes.py`)
  - Acceptance: serializer docstring enumerates the 13 fields + `hasPassword` and references `_build_initial_client_user_data` as the response source of truth so any future reviewer sees the contract immediately.
  - Test: `grep -c "hasPassword" backend/config/api/serializers/clientes.py` returns ≥ 1.

## Phase 2: Defensive Finalize (Unit 1)

- [x] **T-2.1** Modify reactivation finalize in `backend/config/prospect_conversion_views.py` lines 1755–1778 (~24 lines removed, ~10 lines added = net −14 lines, files: `backend/config/prospect_conversion_views.py`)
  - Acceptance: when `draft.cliente` exists (reactivation branch), delete the entire `user`+`cliente` overwrite block (lines 1755–1778 today); replace with `cliente = draft.cliente; user_data = draft.datos_usuario; cliente.observaciones = user_data.get("observacionesCliente") or ""; cliente.save(update_fields=["observaciones", "updated_at"])`; `if draft.prospecto:` branch (1711–1754) untouched; all post-creation work (operation, medical, biometric, payment) unchanged.
  - Test: `python manage.py check` + `grep -n "Actualizamos datos del usuario" backend/config/prospect_conversion_views.py` returns no match (block deleted).

- [ ] **T-2.2** Verify prospect conversion finalize path is byte-equivalent (~0 lines, files: `backend/config/prospect_conversion_views.py`)
  - Acceptance: lines 1711–1754 (`if draft.prospecto:` branch) untouched; `git diff backend/config/prospect_conversion_views.py` shows changes only inside the reactivation `else:` branch.
  - Test: `git diff -U0 backend/config/prospect_conversion_views.py | grep -E '^[+-]' | grep -v '^[+-]{3}' | wc -l` (line count change reflects only the reactivation branch).

## Phase 3: Backend Tests (Unit 2)

- [ ] **T-3.1** Create `backend/tests/test_admin_client_profile_edit.py` with happy-path single-field test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `AdminClientProfilePatchSingleFieldTest.test_patch_primer_nombre_updates_usuario` — admin session logs in, PATCH `/api/admin/clientes/<pk>/perfil/` with `{"primerNombre": "Maria"}`, asserts `Usuario.primer_nombre == "Maria"`, asserts all other Usuario/Cliente fields unchanged, asserts 200, asserts `response.json()["client"]["primerNombre"] == "Maria"`.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchSingleFieldTest -v 2`.

- [ ] **T-3.2** Add partial-update-preserves-omitted test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_email_only_preserves_telefono_ci` — PATCH `{"email": "x@y.com"}`, assert `Usuario.email == "x@y.com"` and `Usuario.telefono`, `Cliente.telefono`, `Cliente.ci`, `Cliente.fecha_nacimiento` all unchanged from fixtures.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchSingleFieldTest.test_patch_email_only_preserves_telefono_ci -v 2`.

- [ ] **T-3.3** Add telefono-cascades-to-Cliente test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_telefono_updates_usuario_and_cliente` — PATCH `{"telefono": "70000000"}`, assert `Usuario.telefono == "70000000"` AND `Cliente.telefono == "70000000"`.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchSingleFieldTest.test_patch_telefono_updates_usuario_and_cliente -v 2`.

- [ ] **T-3.4** Add fechaNacimiento-Cliente-only test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_fecha_nacimiento_writes_cliente_only` — pre-seed `Usuario.fecha_nacimiento = ORIGINAL`, PATCH `{"fechaNacimiento": "1990-01-15"}`, assert `Cliente.fecha_nacimiento == date(1990,1,15)` and `Usuario.fecha_nacimiento == ORIGINAL`.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchSingleFieldTest.test_patch_fecha_nacimiento_writes_cliente_only -v 2`.

- [ ] **T-3.5** Add username-collision-400 test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_username_collision_returns_400` — create second Usuario with `username="taken"`, PATCH `{"username": "taken"}` on target, assert status 400, assert target `Usuario.username` unchanged.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchCollisionTest.test_patch_username_collision_returns_400 -v 2`.

- [ ] **T-3.6** Add ci-collision-400 test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_ci_collision_returns_400` — create second Cliente with `ci="1234567"`, PATCH `{"ci": "1234567"}` on target, assert status 400, target `Cliente.ci` unchanged.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchCollisionTest.test_patch_ci_collision_returns_400 -v 2`.

- [ ] **T-3.7** Add password-rejected-400 test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_password_returns_400` — PATCH `{"password": "newpass"}`, assert status 400, response body contains `"password is not editable through this endpoint"`, assert target `Usuario.check_password("newpass")` is False (no password change applied).
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchCollisionTest.test_patch_password_returns_400 -v 2`.

- [ ] **T-3.8** Add unknown-field-rejected-400 test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_unknown_field_returns_400` — PATCH `{"invalid": "x"}`, assert status 400, assert no DB writes (snapshot `Usuario`/`Cliente` fields before and compare).
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchCollisionTest.test_patch_unknown_field_returns_400 -v 2`.

- [ ] **T-3.9** Add non-admin-403 test (~15 lines, files: `backend/tests/test_admin_client_profile_edit.py`)
  - Acceptance: `test_patch_non_admin_returns_403` — log in as `CLIENTE` user, PATCH any payload, assert status 403, no DB writes.
  - Test: `python manage.py test backend.tests.test_admin_client_profile_edit.AdminClientProfilePatchAuthTest.test_patch_non_admin_returns_403 -v 2`.

- [ ] **T-3.10** Add finalize-on-reactivation-leaves-live-profile-unchanged test (~25 lines, files: `backend/tests/suspension/test_conversion_split.py`)
  - Acceptance: `test_finalize_reactivation_leaves_live_profile_unchanged` — pre-seed reactivation draft with `datos_usuario` containing DIFFERENT names/ci/email/telefono/fechaNacimiento; call `admin_prospect_conversion_finalize`; assert live `Usuario.primer_nombre`, `apellido_paterno`, `email`, `telefono` unchanged AND `Cliente.ci`, `Cliente.fecha_nacimiento`, `Cliente.telefono` unchanged; assert `Cliente.observaciones == user_data["observacionesCliente"]` (only this one field written).
  - Test: `python manage.py test backend.tests.suspension.test_conversion_split.FinalizeSplitTests.test_finalize_reactivation_leaves_live_profile_unchanged -v 2`.

- [ ] **T-3.11** Add finalize-still-creates-operation-medical-biometric-payment test (~25 lines, files: `backend/tests/suspension/test_conversion_split.py`)
  - Acceptance: `test_finalize_reactivation_still_creates_operation_medical_biometric_payment` — reactivation draft with operation+medical+biometric+payment fields; call finalize; assert all four sub-records exist and reference the existing `cliente`. Proves the policy change didn't accidentally drop those writes.
  - Test: `python manage.py test backend.tests.suspension.test_conversion_split.FinalizeSplitTests.test_finalize_reactivation_still_creates_operation_medical_biometric_payment -v 2`.

- [ ] **T-3.12** Add prospect-conversion-finalize-regression test (~20 lines, files: `backend/billing/tests/test_conversion_first_payment.py`)
  - Acceptance: `test_finalize_prospect_conversion_still_creates_user_and_client` — build prospect draft with full `user_data`; call finalize; assert new `Usuario` exists with names/email/username/passwordHash; assert new `Cliente` exists with ci/fechaNacimiento/telefono/observaciones from draft; existing first-payment behavior preserved. Proves the reactivation branch isolation didn't regress the prospect branch.
  - Test: `python manage.py test backend.billing.tests.test_conversion_first_payment.<ProspectFirstPaymentTests>.test_finalize_prospect_conversion_still_creates_user_and_client -v 2`.

## Phase 4: Frontend API Helper (Unit 3)

- [ ] **T-4.1** Add `patchJsonWithBody<T>(path, body)` to `frontend/aesthetic-clinic/src/services/api/apiClient.ts` (~20 lines, files: `frontend/aesthetic-clinic/src/services/api/apiClient.ts`)
  - Acceptance: helper mirrors `requestJsonWithBody` but uses `method: 'PATCH'`; reuses `ensureCsrfCookie`, `buildHeaders`, `API_BASE_URL`, `parseErrorResponse`; returns `responseBody as T` on success; throws on `!response.ok`.
  - Test: `pnpm --filter aesthetic-clinic typecheck` passes; `grep -n "export async function patchJsonWithBody" frontend/aesthetic-clinic/src/services/api/apiClient.ts` returns a match.

- [ ] **T-4.2** Add `patchAdminClientProfile(clientId, payload)` and `AdminClientProfilePayload` type to `frontend/aesthetic-clinic/src/services/api/admin.ts` (~25 lines, files: `frontend/aesthetic-clinic/src/services/api/admin.ts`)
  - Acceptance: `AdminClientProfilePayload` exported with 13 optional camelCase fields (no `password`); `patchAdminClientProfile(clientId, payload)` calls `patchJsonWithBody<{ client: AdminClientProfilePayload & { hasPassword: boolean } }>("/api/admin/clientes/${clientId}/perfil/", payload)`; existing `saveAdminClientReactivationUserStep` and `getAdminClientReactivation` untouched.
  - Test: `pnpm --filter aesthetic-clinic typecheck` passes; `grep -n "patchAdminClientProfile" frontend/aesthetic-clinic/src/services/api/admin.ts` returns ≥ 2 matches (type import / export).

## Phase 5: Frontend Modal Rewire (Unit 3)

- [ ] **T-5.1** Rewire `ClientProfileModal.tsx` to use new live endpoint (~25 lines, files: `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx`)
  - Acceptance: import `patchAdminClientProfile` instead of `saveAdminClientReactivationUserStep`; `handleSubmit` calls `patchAdminClientProfile(clientId, form)`; on success sets `setForm(response.client)` (not `response.draft.userData`) then `onClose()`; hydration stays on `getAdminClientReactivation` (live snapshot via `_build_initial_client_user_data`); error path unchanged; all 13 inputs still rendered and editable in the modal; no password input added.
  - Test: `pnpm --filter aesthetic-clinic typecheck` passes; `grep -n "saveAdminClientReactivationUserStep" frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx` returns no match (call removed).

- [ ] **T-5.2** Optional: refresh client detail page after modal close (~5 lines, files: parent page that renders `ClientProfileModal`)
  - Acceptance: parent page receives an `onSaved` callback (or the modal triggers a refetch); client detail page re-fetches its `getAdminClient` (or equivalent) after `onClose()` so updated fields appear without manual reload. If no clean callback exists in the parent, document and skip.
  - Test: manual browser smoke (open modal, edit `telefono`, save, observe detail page shows new value).

## Phase 6: Wizard Read-Only (Unit 3)

- [ ] **T-6.1** Add `disabled={isReactivation}` to every profile input except `observacionesCliente` in `ConversionStepUser.tsx` (~15 lines net, files: `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx`)
  - Acceptance: every input for `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, `direccionDomicilio` gains `disabled={isReactivation}`; `observacionesCliente` textarea is intentionally NOT disabled; password block is already conditional and stays conditional; `onUserChange` / `onNameBlur` paths unchanged.
  - Test: `pnpm --filter aesthetic-clinic typecheck` passes; `grep -c "disabled={isReactivation}" frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` returns ≥ 12 matches.

- [ ] **T-6.2** Verify `AdminProspectConvertPage` already passes `isReactivation` (no change) (~0 lines, files: `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx`)
  - Acceptance: page already computes `isReactivation = !!clientId` and passes it to `ConversionStepUser`; no contract change required. Verification only.
  - Test: `grep -n "isReactivation" frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx` returns ≥ 2 matches; `pnpm --filter aesthetic-clinic typecheck` passes.

## Phase 7: Verification (Unit 2 + Unit 3)

- [ ] **T-7.1** Run backend test suite (~0 net lines, files: `backend/tests/test_admin_client_profile_edit.py`, `backend/tests/suspension/test_conversion_split.py`, `backend/billing/tests/test_conversion_first_payment.py`)
  - Acceptance: `python manage.py test backend.tests.test_admin_client_profile_edit backend.tests.suspension.test_conversion_split backend.billing.tests.test_conversion_first_payment backend.tests.test_profile_update -v 2` passes with no regressions; full backend suite `python manage.py test` passes.
  - Test: green run; capture exit code 0.

- [ ] **T-7.2** Manual smoke: end-to-end live edit (~0 net lines, files: n/a)
  - Acceptance: open `/cms/clientes/<id>/`, click "Ver perfil", edit `telefono` and `email`, save, verify DB updated (`SELECT telefono FROM customers_cliente WHERE id=...`), verify no reactivation finalize contamination by triggering a separate finalize and re-reading live row.
  - Test: manual run + SQL assertion.

## Review Workload Forecast

- Estimated total changed lines: ~480
- New files: ~1 (`backend/tests/test_admin_client_profile_edit.py`, ~225 lines)
- Modified files: ~9 (serializer, viewset, apiClient, admin.ts, ClientProfileModal, ConversionStepUser, prospect_conversion_views, two existing test files)
- Test files: ~3 (lines: ~245)
- 400-line budget risk: Medium–High
- Chained PRs recommended: Yes
- Decision needed before apply: Yes
- Notes: Per-unit breakdown above. Backend is ~330 lines (serializer ~60, view ~45, finalize −14 net, two test mods ~45 + new test file ~225). Frontend is ~85 lines (apiClient helper ~20, admin.ts payload/client ~25, modal rewire ~25, wizard read-only ~15). Sum ~480 lines exceeds the 400 budget; user explicitly chose `ask-on-risk`, so the orchestrator should pause before apply to confirm whether to (a) split into chained PRs (Unit 1 / Unit 2 / Unit 3), (b) accept `size:exception`, or (c) trim scope (e.g., drop optional Playwright e2e and T-5.2).

## delivery_strategy Input

- delivery_strategy: ask-on-risk
- chain_strategy: TBD (only if chained)
- size_exception: not_required

## Skill Resolution

For sdd-apply, list any matching skills by trigger/context:

- `sdd-apply` — required (this change is the input)
- `work-unit-commits` — recommended (the forecast splits into 3 work units; each PR maps to one unit's commits)
- `go-testing` — N/A (stack is Django + React, not Go)
- `chained-pr` — recommended if the user picks the chained-PR path at the `ask-on-risk` gate (PR #2 base = PR #1 branch; PR #3 base = PR #2 branch)
- `branch-pr` — recommended when opening each PR (Gentle AI issue-first checks)
- `judgment-day` — optional (worth a dual-review pass on `prospect_conversion_views.py` finalize changes; small but high-blast-radius)
- `skill-registry` — N/A (no skill changes in this change)
