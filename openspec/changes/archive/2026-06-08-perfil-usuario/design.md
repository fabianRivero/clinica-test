# Design: perfil-usuario

## Technical Approach

Extend `auth_me` with a PATCH handler to support partial profile updates. The endpoint validates incoming fields, updates `Usuario`, syncs `telefono` to related `Cliente`/`Especialista` within a transaction, and returns the updated profile. Frontend adds a profile edit modal accessible from the `profile-chip` in each layout's topbar.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| Single endpoint vs separate | PATCH `auth_me` | New `/api/auth/profile/` endpoint | Proposal specifies extending `auth_me`; single URL keeps API surface minimal |
| telefono sync location | In view, wrapped in `transaction.atomic` | Model signals (`post_save`) | Sync in view is explicit and easier to test; signals add coupling |
| Password update | `request.user.set_password()` + `request.session.cycle_key()` | Re-auth required | Session cycle maintains CSRF state; no forced logout |
| Frontend edit UX | Modal from profile-chip | Dedicated `/perfil` route | Less navigation, faster access; modal is consistent with existing patterns |
| telefono cascade | Manual update to `Cliente`/`Especialista` | `bulk_update` | Single related model per user; manual is simpler and safer |

## Data Flow

```
┌─────────────┐     PATCH /api/auth/me/      ┌──────────────────┐
│  Frontend   │ ─────────────────────────────▶│  auth_me (PATCH) │
│ Modal     │     { username, email,       │                  │
└─────────────┘ telefono, password }  └────────┬─────────┘
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              │                       │                       │
                              ▼                       ▼                       ▼
 ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
                    │ Usuario.set_    │    │ Cliente.telefono│    │ Especialista.   │
                    │ password() │    │ = telefono      │    │ telefono =      │
                    │ (if password)   │    │ (if exists)     │    │ telefono        │
                    └─────────────────┘    └─────────────────┘    └─────────────────┘
                              │                       │                       │
                              └───────────────────────┼───────────────────────┘
                                                      │
                                                      ▼
                                            ┌─────────────────┐
                                            │ _serialize_user │
                                            │ (updated user)  │
                                            └─────────────────┘
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/config/auth_views.py` | Modify | Add PATCH handler via `@require_http_methods`; telefono sync in atomic block |
| `backend/config/auth_urls.py` | Modify | No change needed (same URL, new method) |
| `frontend/aesthetic-clinic/src/services/api/auth.ts` | Modify | Add `updateProfile(payload)` using PATCH |
| `frontend/aesthetic-clinic/src/types/auth.ts` | Modify | Add `telefono?: string` to `AuthUser` |
| `frontend/aesthetic-clinic/src/providers/AuthProvider.tsx` | Modify | Add `updateProfile` method that calls auth service and refreshes session |
| `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` | Modify | Add ProfileEditModal to topbar profile-chip |
| `frontend/aesthetic-clinic/src/layouts/ClientLayout.tsx` | Modify | Add ProfileEditModal to topbar profile-chip |
| `frontend/aesthetic-clinic/src/layouts/SpecialistLayout.tsx` | Modify | Add ProfileEditModal to topbar profile-chip |
| `frontend/aesthetic-clinic/src/components/profile/ProfileEditModal.tsx` | Create | Reusable modal with form (username, email, telefono, password) |

## Interfaces / Contracts

### Backend: PATCH /api/auth/me/

**Request body** (all fields optional):
```json
{
  "username": "string",
  "email": "user@example.com",
  "telefono": "70000000",
  "password": "newpassword"
}
```

**Response** (200 OK):
```json
{
  "user": {
    "id": 1,
    "username": "juanp",
    "fullName": "Juan Pérez",
    "email": "juan@example.com",
    "telefono": "70000000",
    "role": "CLIENTE",
    "dashboardPath": "/cliente",
    "isAdmin": false,
    "isMainAdmin": false,
    "isWorker": false,
    "isClient": true,
    "branchId": 1,
    "branchName": "Sucursal Central"
  }
}
```

**Error responses**: 400 (validation), 401 (not authenticated), 409 (username collision)

### Frontend: updateProfile payload

```typescript
type ProfileUpdatePayload = {
  username?: string
  email?: string
  telefono?: string
  password?: string
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `_serialize_user` includes telefono; telefono sync logic | Django unittest on view functions |
| Integration | PATCH `/api/auth/me/` with session auth | Django test client with authenticated session |
| E2E | Edit profile from each layout, verify telefono cascades | Playwright: login → open modal → edit → save → verify |

## Migration / Rollout

No migration required. Changes are additive:
- New PATCH method on existing endpoint
- New `telefono` field added to serialized user response (no DB change)
- Sync is bidirectional on save only

## Open Questions

- [ ] Should username changes trigger a re-login? Currently the session is preserved. Consider whether this is a security concern for ADMIN_SUCURSAL.
- [ ] Do we need field-level validation (e.g., email format, telefono digits)? Proposal defers password rules but email/phone validation isn't specified.
