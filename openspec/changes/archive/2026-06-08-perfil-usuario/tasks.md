# Tasks: perfil-usuario

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~380–460 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: Backend + Frontend foundation / PR 2: UI integration + tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend PATCH + Frontend API/service/types | PR 1 | Base = main; backend auth_views + models + auth.ts + types + AuthProvider |
| 2 | UI integration + tests | PR 2 | Base = PR 1 branch; ProfileEditModal + 3 layouts + backend tests |

## Phase 1: Backend Foundation

- [x] 1.1 Add PATCH handler via `@require_http_methods(["GET", "PATCH"])` to `auth_me` in `backend/config/auth_views.py`; validate allowed fields (`username`, `email`, `telefono`, `password`); call `transaction.atomic` for telefono sync
- [x] 1.2 In `backend/accounts/models.py` — override or confirm `Usuario.save()` syncs telefono to `Cliente`/`Especialista` within the same atomic block used by the view
- [x] 1.3 Add username uniqueness check in PATCH handler; return 409 on collision

## Phase 2: Frontend Foundation

- [x] 2.1 Add `ProfileUpdatePayload` type and `updateProfile(payload)` to `frontend/aesthetic-clinic/src/services/api/auth.ts` using PATCH method
- [x] 2.2 Add `telefono?: string` to `AuthUser` type in `frontend/aesthetic-clinic/src/types/auth.ts`
- [x] 2.3 Add `updateProfile(payload)` method to `AuthProvider.tsx` that calls the auth service and refreshes session/user state

## Phase 3: UI Components

- [x] 3.1 Create `frontend/aesthetic-clinic/src/components/profile/ProfileEditModal.tsx` — form with username, email, telefono, password fields; validation; calls `updateProfile`
- [x] 3.2 Add `ProfileEditModal` to topbar profile-chip in `AdminLayout.tsx`
- [x] 3.3 Add `ProfileEditModal` to topbar profile-chip in `ClientLayout.tsx`
- [x] 3.4 Add `ProfileEditModal` to topbar profile-chip in `SpecialistLayout.tsx`

## Phase 4: Testing

- [x] 4.1 Django unit test: `_serialize_user` includes telefono in response
- [x] 4.2 Django integration test: PATCH `/api/auth/me/` with session auth — partial update, password change, username collision (409), invalid field (400), telefono cascade to Cliente
- [x] 4.3 Playwright E2E: login as Cliente → open modal → edit telefono → save → verify Cliente.telefono updated in DB
  - Also covers ADMIN_SUCURSAL role (new test added)

## Warnings Addressed

| Warning | Fix |
|---------|-----|
| ADMIN_SUCURSAL role has no explicit test | Added `test_patch_telefono_updates_admin_sucursal` in `backend/tests/test_profile_update.py` |
| Playwright E2E missing ADMIN_SUCURSAL coverage | Added `Profile Edit Modal — ADMIN_SUCURSAL role` test suite in `frontend/aesthetic-clinic/tests/e2e/profile_edit.spec.ts` |