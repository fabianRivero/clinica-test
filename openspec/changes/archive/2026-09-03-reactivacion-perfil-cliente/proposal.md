# Proposal: reactivacion-perfil-cliente

## Intent

The admin reactivation/new-procedure wizard and the "Ver perfil del cliente" modal both currently read and write `ProspectoConversionBorrador.datos_usuario`, so wizard step 1 silently lets an admin rewrite a live customer's identity and the modal gives a misleading "saved" feel while touching no live rows. This change makes wizard step 1 read-only for identity fields during reactivation/new procedure (only `observacionesCliente` stays editable as a clinical annotation), introduces a dedicated admin-only `PATCH /api/admin/clientes/{id}/perfil/` that updates the live `Cliente` and `Usuario` in one transaction, and rewires the modal to that endpoint. Finalization will no longer overwrite the live `Cliente`/`Usuario` rows from `datos_usuario` when reactivating an existing client — only operation/medical/biometric/payment fields will come from the draft.

## Scope

### In Scope

- New endpoint `PATCH /api/admin/clientes/{id}/perfil/` (admin-only, branch-scoped)
- Live profile serializer covering 13 fields: `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `ci`, `username`, `email`, `telefono`, `fechaNacimiento`, `nroHijos`, `ocupacion`, `direccionDomicilio`, `observacionesCliente`
- Field ownership rules and atomic `Cliente` + `Usuario` update in a single DB transaction
- Validation: `ci` uniqueness (excluding self), `username` uniqueness (excluding self), `fechaNacimiento` required, no `password` accepted
- Frontend: `ConversionStepUser.tsx` renders all profile fields read-only during reactivation/new procedure; `observacionesCliente` remains editable and still goes through the draft
- Frontend: `ClientProfileModal.tsx` loads/saves through the new live endpoint
- Frontend: new typed API client in `frontend/aesthetic-clinic/src/services/api/admin.ts`
- Defensive finalize: when `draft.cliente` exists (reactivation), finalize MUST NOT write profile fields from `datos_usuario` onto the live `Usuario`/`Cliente` rows; only operation, medical, biometric, and payment fields are finalized from the draft
- Regression tests covering: field ownership, validation, authorization (unauthenticated/non-admin/cross-branch), draft isolation, and finalize non-overwrite of live profile data

### Out of Scope

- Password changes via this endpoint (admin-driven password reset is a separate flow)
- Profile deletion or account deletion
- Admin-managed cross-client profile editing UI (admin still edits one client at a time via the modal)
- Bulk profile updates or CSV import
- Audit log of profile edits (deferred)
- Migration/cleanup of pre-existing reactive drafts that may contain stale identity edits — handled as a one-time operator decision, not automatic
- Password strength validation rules (already deferred in `user-profile-editing`)

## Capabilities

### New Capabilities

- `admin-client-profile-editing`: Admins can edit a single live client's profile via `PATCH /api/admin/clientes/{id}/perfil/` with strict field ownership, transactional updates, and branch-scoped authorization.

### Modified Capabilities

- No existing spec in `openspec/specs/` covers the reactivation draft flow today. The proposal documents a **policy change** on the existing reactivation/new-procedure wizard flow: step 1 profile fields become read-only during reactivation (live `clienteId` mode), and reactivation finalize no longer overwrites live profile data from the draft. The new `admin-client-profile-editing` capability is the supported path for those edits.

## Approach

**Backend — new endpoint:**

- Add `PATCH /api/admin/clientes/{id}/perfil/` on the admin client ViewSet (`backend/config/api/viewsets/clientes.py`), reusing `_admin_client_queryset` and the existing admin/branch authorization so unauthenticated, non-admin, and cross-branch callers are rejected.
- Introduce a focused write serializer in `backend/config/api/serializers/clientes.py` (or a sibling module) with explicit fields and ownership:

  | Field | Owned by | Sync to |
  |---|---|---|
  | `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `username`, `email` | `Usuario` | (none) |
  | `telefono` | `Usuario.telefono` | `Cliente.telefono` (sync, mirroring `auth_views.py:90` and `test_profile_update.py:112-138`) |
  | `fechaNacimiento` | `Cliente.fecha_nacimiento` | (do NOT touch `Usuario.fecha_nacimiento` — current finalize convention) |
  | `ci`, `nroHijos`, `direccionDomicilio`, `ocupacion`, `observacionesCliente` | `Cliente` | (none) |

- The serializer accepts partial updates (PATCH semantics); omitted fields keep their current value. `fechaNacimiento` is required when present. `ci` and `username` uniqueness checks exclude the current row.
- The view wraps `cliente` and `cliente.usuario` updates in a single `transaction.atomic()` block; any validation error rolls both rows back. `Cliente.usuario` is a required `OneToOneField` (`backend/customers/models.py:141-145`), so there is always exactly one `Usuario` to update.
- Response shape matches the modal's current camelCase fields so the UI can hydrate from one source of truth.
- No `password` field on the serializer; an unknown field test rejects `password` payloads.

**Backend — defensive finalize:**

- In `backend/config/prospect_conversion_views.py` lines 1755-1778, the reactivation branch currently reads `user_data = draft.datos_usuario` and overwrites both `user` and `cliente` rows. After this change, when `draft.cliente` is set, finalize MUST NOT apply `primerNombre`, `segundoNombre`, `apellidoPaterno`, `apellidoMaterno`, `username`, `email`, `telefono`, `ci`, `fechaNacimiento`, `nroHijos`, `direccionDomicilio`, or `ocupacion` from the draft onto the live rows.
- `observacionesCliente` is the only profile-adjacent field finalize still writes during reactivation, and only as the procedure-scoped annotation. Operation, medical, biometric, and payment draft fields continue to finalize normally.
- This is what makes Bug A actually fixed: even if an admin typed something into step 1 before this change shipped, the next finalize after this change cannot silently rewrite the live identity.

**Frontend — wizard step 1:**

- In `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx`, when the wizard runs in reactivation/new-procedure mode (i.e., `clientId` is set), every profile field except `observacionesCliente` is rendered disabled/read-only. The submit still posts to the existing `paso-1` draft endpoint so the observation is persisted in the draft, but the typed profile values from step 1 cannot reach the live rows anymore.
- Prefill `userForm` from the live snapshot passed in by `AdminProspectConvertPage.tsx` / `useConversionWizard.ts` so the admin sees the current truth, not a stale draft.

**Frontend — modal rewire:**

- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx` stops calling `saveAdminClientReactivationUserStep` and `load` from `res.draft.userData`. It calls a new typed client (`patchAdminClientProfile(id, payload)`) in `frontend/aesthetic-clinic/src/services/api/admin.ts:1246-1259` that targets `PATCH /api/admin/clientes/{id}/perfil/`.
- All 13 fields remain editable in the modal. Save now reflects immediately in the live data and is visible everywhere the profile is read.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/config/api/viewsets/clientes.py` | Modified | Add `perfil` action handling `PATCH /api/admin/clientes/<id>/perfil/`; reuse `_admin_client_queryset`/admin authorization; wrap in `transaction.atomic()`. |
| `backend/config/api/serializers/clientes.py` | Modified (or new sibling) | Add `AdminClientProfileWriteSerializer` with 13 fields, partial updates, ownership rules, CI/username uniqueness excluding self, no `password` field. |
| `backend/config/api_urls.py` | Modified | Register the new `perfil` route on the admin client ViewSet; keep existing reactivation routes intact. |
| `backend/config/prospect_conversion_views.py:1755-1778` | Modified | When `draft.cliente` exists, finalize MUST NOT overwrite live `Usuario`/`Cliente` profile fields from `datos_usuario`; only `observacionesCliente` and operation/medical/biometric/payment fields finalize. |
| `backend/customers/models.py:136-184` | Read-only reference | Target fields and required `OneToOneField` constraints. |
| `backend/accounts/models.py:18-63` | Read-only reference | `Usuario` field ownership for names/username/email/telefono. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx:50-168` | Modified | Render all profile fields read-only during reactivation/new procedure; keep `observacionesCliente` editable and submitted to the draft. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx:187-213` | Modified | Pass reactivation mode and live snapshot; no contract change to the draft endpoint. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts:195-243,470-490` | Modified | Initialize reactivation `userForm` from the live snapshot; submit observation through existing draft endpoint. |
| `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx:1-127` | Modified | Replace draft load/save with new live endpoint; keep all 13 fields editable; remove any implicit dependency on `res.draft.userData`. |
| `frontend/aesthetic-clinic/src/services/api/admin.ts:1246-1259` | Modified | Add `patchAdminClientProfile` (and a load helper if needed) typed client; preserve existing reactivation step client. |
| `backend/tests/suspension/test_conversion_split.py:259-291` | Modified | Add regression assertions that reactivation finalize leaves live profile data unchanged when step 1 is edited or skipped. |
| `backend/billing/tests/test_conversion_first_payment.py:49-97,147-175` | Modified | Add live-profile isolation assertion for the reactivation finalize path; preserve payment coverage. |
| `backend/tests/test_profile_update.py:11-18,99-184` | Reference | Reuse partial-update and `telefono` sync patterns; keep the two endpoints distinct and ensure this endpoint excludes password. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Duplicated fields (`telefono`) drift between `Usuario` and `Cliente` | Medium | Define ownership in the proposal (table above); update both rows in one transaction; add assertions for every accepted field. |
| Existing clients have missing/invalid data; PATCH breaks them | Medium | PATCH is partial; only values that violate explicit serializer rules are rejected; omitted fields are preserved. |
| Branch authorization bypassed or cross-branch leak | Medium | Reuse `_admin_client_queryset` and admin ViewSet authorization; add unauthenticated/non-admin/cross-branch tests. |
| Modal accidentally exposes `password` or unknown fields | Low | Serializer omits `password`; add an unknown-field/password regression test. |
| Wizard step 1 still submits stale profile values | Low | Disable/read-only all non-observation fields; initialize `userForm` from the live snapshot. |
| Pre-existing reactive drafts contain identity edits that today overwrite live rows on finalize | Medium | Finalize policy change removes live overwrite on reactivation. Pre-existing drafts in the wild may still hold stale identity edits in `datos_usuario`; document that those edits will no longer reach the live rows after this change and treat cleanup as an operator decision. |
| Response shape mismatch between new endpoint and existing modal expectations | Low | Lock the response contract to the existing camelCase fields (`fechaNacimiento`, `direccionDomicilio`, `observacionesCliente`, etc.); add a contract test. |
| Admin saves a profile change that should have been a separate audit event | Low | Audit log is out of scope; surface as a follow-up rather than blocking this fix. |

## Rollback Plan

1. Revert `backend/config/api_urls.py` to remove the `perfil` route registration.
2. Revert `backend/config/api/viewsets/clientes.py` to drop the `perfil` action and its transactional update.
3. Revert `backend/config/api/serializers/clientes.py` (or sibling) to remove `AdminClientProfileWriteSerializer`.
4. Revert `backend/config/prospect_conversion_views.py:1755-1778` to the original finalize-overwrite behavior.
5. Revert `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx` to allow step-1 profile edits during reactivation.
6. Revert `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx` to read/write through `saveAdminClientReactivationUserStep`.
7. Revert `frontend/aesthetic-clinic/src/services/api/admin.ts` to drop `patchAdminClientProfile`.
8. Revert the new regression tests; keep `test_profile_update.py` untouched.
9. Rollback is medium-risk because step 4 re-enables the live-overwrite path; do not roll back without coordinating with admins who may have in-flight reactive drafts.

## Dependencies

- Django REST Framework session auth and CSRF handling (existing).
- Existing admin client ViewSet authorization and `_admin_client_queryset` branch scoping.
- Existing `Usuario`/`Cliente` model constraints (`backend/customers/models.py:141-145` — required `OneToOneField`).
- Existing reactivation draft endpoint and `ProspectoConversionBorrador` model — kept as the wizard draft persistence boundary; no schema change required.
- No new third-party packages.

## Success Criteria

- [ ] `PATCH /api/admin/clientes/{id}/perfil/` updates live `Cliente` and `Usuario` in a single transaction for all 13 fields.
- [ ] `telefono` change writes to `Usuario.telefono` and syncs `Cliente.telefono`; `fechaNacimiento` writes to `Cliente.fecha_nacimiento` only.
- [ ] `ci` and `username` uniqueness excludes the current row; `fechaNacimiento` is required when present.
- [ ] `password` is not accepted; unknown fields are rejected with 400.
- [ ] Unauthenticated, non-admin, and cross-branch requests are rejected.
- [ ] `ClientProfileModal.tsx` loads from and saves to the new endpoint; all 13 fields remain editable in the UI; the modal's save visibly updates the live profile.
- [ ] Wizard step 1 renders every profile field read-only during reactivation/new procedure; only `observacionesCliente` is editable and continues through the draft.
- [ ] Reactivation finalize does NOT overwrite live `Usuario`/`Cliente` profile fields from `draft.datos_usuario`; only operation/medical/biometric/payment draft fields (and `observacionesCliente` as the procedure annotation) are applied.
- [ ] Regression tests cover: field ownership, partial update, validation, authorization, draft isolation, and finalize non-overwrite of live profile data.
- [ ] Pre-existing reactive drafts in the wild are documented as no longer able to silently rewrite live identity via finalize.