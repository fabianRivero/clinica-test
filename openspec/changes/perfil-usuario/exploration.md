## Exploration: User Profile Editing

### Current State

The system has a custom user model (`Usuario` in `accounts/models.py`) that inherits from Django's `AbstractUser`. It stores:
- **Base user fields**: `username`, `email`, `password` (inherited from AbstractUser)
- **Profile fields**: `telefono`, `primer_nombre`, `segundo_nombre`, `apellido_paterno`, `apellido_materno`, `fecha_nacimiento`, `sucursal`
- **Role**: ForeignKey to `Rol` model (ADMIN_PRINCIPAL, ADMIN_SUCURSAL, TRABAJADOR, CLIENTE)

Additional role-specific profiles exist as separate models:
- **`Cliente`** (`customers/models.py`): `OneToOneField` to `Usuario` with extra fields (`telefono`, `fecha_nacimiento`, `direccion_domicilio`, `ocupacion`)
- **`Especialista`** (`staff/models.py`): `OneToOneField` to `Usuario` with extra fields (`telefono`, `ci`, `observaciones`)

**Authentication**: Session-based (Django sessions + CSRF). No JWT. Auth endpoints: `/api/auth/login/`, `/api/auth/logout/`, `/api/auth/me/`.

**Profile data exposed via**: `auth_me` returns basic user info (id, username, fullName, email, role, branchId). No dedicated profile editing endpoint exists.

**Frontend has three layouts**: `AdminLayout` (admins), `ClientLayout` (clientes), `SpecialistLayout` (trabajadores/especialistas). Each shows a profile chip with user name and role, plus logout button. No profile editing UI exists.

**Password handling**: Uses Django's `set_password()` which properly hashes. Django password validators are configured (minimum length, common passwords, numeric passwords).

### Affected Areas

- `backend/accounts/models.py` — `Usuario` model, the central user model
- `backend/customers/models.py` — `Cliente` model (extra profile fields for clients)
- `backend/staff/models.py` — `Especialista` model (extra profile fields for specialists)
- `backend/config/auth_views.py` — Current auth endpoints (`_serialize_user` may need extension for phone)
- `backend/config/auth_urls.py` — Auth URL routing
- `backend/config/worker_views.py` — Worker/especialista endpoints (has `es_trabajador` check)
- `backend/config/client_api_views.py` — Client endpoints (has `es_cliente` check)
- `frontend/aesthetic-clinic/src/providers/AuthProvider.tsx` — Auth state management
- `frontend/aesthetic-clinic/src/types/auth.ts` — `AuthUser` type (may need extension)
- `frontend/aesthetic-clinic/src/layouts/AdminLayout.tsx` — Admin navigation + profile chip
- `frontend/aesthetic-clinic/src/layouts/ClientLayout.tsx` — Client navigation + profile chip
- `frontend/aesthetic-clinic/src/layouts/SpecialistLayout.tsx` — Specialist navigation + profile chip
- `frontend/aesthetic-clinic/src/services/api/auth.ts` — Auth API service

### Approaches

1. **Single Unified Profile Endpoint** — One `/api/profile/` endpoint that returns/edits fields from `Usuario` model (username, email, telefono, password). Role-specific extended profiles (Cliente, Especialista telefono, etc.) managed separately or not at all.
   - Pros: Simple, consistent with existing patterns (auth_me already aggregates user data)
   - Cons: Doesn't address Cliente/Especialista extended fields; may need separate endpoints for those
   - Effort: Low

2. **Separate Role-Based Profile Endpoints** — `/api/profile/` for base Usuario fields, plus `/api/client/profile/` and `/api/specialist/profile/` for role-specific extended fields.
   - Pros: Clear separation, follows existing API patterns (client_dashboard, worker_availability)
   - Cons: More endpoints to maintain
   - Effort: Medium

3. **Extend auth_me with PATCH** — Add a `PATCH` method to `auth_me` that allows updating own profile. Include all writable fields from Usuario and role-specific models.
   - Pros: Auth endpoint already exists; single URL for user's own profile
   - Cons: Blends concerns; endpoint already returns read-only user summary
   - Effort: Low

### Recommendation

**Approach 3 (Extend auth_me with PATCH)** is recommended. The `auth_me` endpoint already exists, returns user info, and is the natural place for users to manage their own profile. Adding a `PATCH` handler keeps related functionality together and minimizes new endpoint surface.

For the frontend, add a profile editing modal/drawer accessible from the profile chip in each layout (AdminLayout, ClientLayout, SpecialistLayout).

Fields to make editable:
- **All roles**: `username`, `email`, `telefono` (from Usuario), `password` (with current password confirmation)
- **Cliente**: `telefono`, `fecha_nacimiento`, `direccion_domicilio`, `ocupacion` (from Cliente model)
- **Especialista**: `telefono` (from Especialista model), `ci`, `observaciones`

### Risks

- **Password change without proper validation**: Must require current password before setting new one
- **Email uniqueness**: Should validate email isn't already taken by another user
- **Username change**: May break integrations if username is used elsewhere; consider making it read-only or requiring strong validation
- **Telefono duplication**: Both `Usuario.telefono` and `Cliente.telefono`/`Especialista.telefono` exist — need to clarify which takes precedence or if they should be kept in sync
- **CSRF**: Session auth requires CSRF token; frontend already handles this via `ensureCsrfCookie()`

### Ready for Proposal

**Yes**. The exploration is complete. Key clarifications needed from user before proposal:
1. Should username be editable or read-only?
2. Should Cliente's `telefono` (in Cliente model) and Usuario's `telefono` be kept separate or synced?
3. Should ADMIN_SUCURSAL users have any special restrictions on what they can edit?
4. What password validation rules (minimum length, complexity)?