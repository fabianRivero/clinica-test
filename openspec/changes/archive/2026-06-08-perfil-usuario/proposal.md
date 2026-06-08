# Proposal: perfil-usuario

## Intent

Enable all users (Admin, Cliente, Especialista) to view and edit their own profile fields: username, email, telefono, and password. Currently only profile reading exists via `auth_me`; no edit endpoint exists.

## Scope

### In Scope
- PATCH endpoint extending `auth_me` for profile editing
- Editable fields: `username`, `email`, `telefono`, `password`
- telefono sync: update `Usuario.telefono` and cascade to `Cliente.telefono` / `Especialista.telefono`
- Frontend profile edit UI in all three layouts (Admin, Client, Specialist)
- ADMIN_SUCURSAL role same edit rights as other roles

### Out of Scope
- Password strength validation rules (deferred)
- Profile deletion
- Admin-level user management (viewing/editing other users)
- Bulk profile updates

## Capabilities

### New Capabilities
- `user-profile-editing`: Users can modify their own profile via PATCH `/api/auth/me`

### Modified Capabilities
- None (no existing spec for user-profile-editing exists in `openspec/specs/`)

## Approach

Extend existing `auth_me` endpoint with PATCH method. Single URL, follows Django REST Framework patterns. Partial updates only — send only fields to change.

**Backend flow**: `PATCH /api/auth/me` → validate fields → update `Usuario` → sync telefono to related `Cliente`/`Especialista` → return updated profile.

**Frontend flow**: Add profile edit modal/section in each layout. Call PATCH endpoint on save.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/auth_views.py` | Modified | Add PATCH handler to `auth_me` |
| `backend/accounts/models.py` | Modified | Ensure telefono sync logic |
| `backend/customers/models.py` | Modified | Cliente.telefono sync |
| `backend/staff/models.py` | Modified | Especialista.telefono sync |
| `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` | Modified | Add profile edit UI |
| `frontend/aesthetic-clinic/src/layouts/ClientLayout.tsx` | Modified | Add profile edit UI |
| `frontend/aesthetic-clinic/src/layouts/SpecialistLayout.tsx` | Modified | Add profile edit UI |
| `frontend/aesthetic-clinic/src/services/api/auth.ts` | Modified | Add PATCH method to auth service |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| telefono sync fails silently | Low | Add transaction + validation check |
| Username collision | Low | Enforce uniqueness at model level |
| Session invalidation after password change | Medium | Return new session token or re-auth prompt |

## Rollback Plan

1. Revert `auth_views.py` — remove PATCH handler, restore GET-only
2. Revert frontend auth service — remove PATCH method
3. Revert layout components — remove edit UI elements
4. Rollback is low-risk: changes are additive except telefono sync

## Dependencies

- Django REST Framework session auth (existing)
- CSRF handling (existing)

## Success Criteria

- [ ] `PATCH /api/auth/me` updates username, email, telefono, password for all roles
- [ ] telefono change in Usuario cascades to Cliente/Especialista
- [ ] Profile edit UI accessible from all three layouts
- [ ] ADMIN_SUCURSAL can edit own profile only
- [ ] No password validation errors (rules deferred)
