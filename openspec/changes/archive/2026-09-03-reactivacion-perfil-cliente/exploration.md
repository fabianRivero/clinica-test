## Exploration: reactivacion-perfil-cliente

### Current State

The reactivation/new-procedure wizard reuses the prospect conversion flow whenever `clientId` is present (`frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx:16-20`). Step 1 hides password fields for reactivation, but every other profile field remains editable (`frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx:50-82,83-168`). The frontend sends those edits to `/reactivar/paso-1/` (`frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts:470-490`; `frontend/aesthetic-clinic/src/services/api/admin.ts:1257-1259`), whose handler only writes `draft.datos_usuario` and marks the step complete (`backend/config/prospect_conversion_views.py:1350-1374`). This is safe in isolation, but finalize later reads that same draft and overwrites the live `Usuario` and `Cliente` rows (`backend/config/prospect_conversion_views.py:1676-1696,1755-1778`), so profile edits made during reactivation can unexpectedly alter the live identity. `observacionesCliente` is stored on `Cliente.observaciones`; the other profile fields span both models: `Usuario` owns names, username, email, phone, and date of birth (`backend/accounts/models.py:18-34`), while `Cliente` owns CI, child count, address, occupation, phone, and observations (`backend/customers/models.py:141-184`). `Cliente.usuario` is a required `OneToOneField` (`backend/customers/models.py:141-145`).

The profile modal loads `res.draft.userData` and saves through `saveAdminClientReactivationUserStep` (`frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx:22-35,44-57`). That API is the same draft endpoint above, so the modal gives a misleading “save” experience without changing the live profile and can contaminate a later reactivation finalize. No dedicated live client-profile serializer/viewset action was found; existing serializers cover reports, payments, migrations, and unrelated domains, so a purpose-built write serializer is appropriate. The reactivation route maps directly to the shared step handler (`backend/config/api_urls.py:227-235`), and the only identified frontend callers of that client-specific `paso-1` endpoint are the modal and wizard (`frontend/aesthetic-clinic/src/services/api/admin.ts:1249-1259`).

Existing tests cover reactivation biometric/finalize splitting and first-payment behavior, but not profile ownership or draft contamination. `backend/tests/suspension/test_conversion_split.py:259-291` verifies that reactivation preserves biometric data and removes its draft, while `backend/billing/tests/test_conversion_first_payment.py:49-97,171-175` constructs full reactivation drafts and exercises finalize/payment paths. They do not assert that wizard step-1 edits remain confined to the draft or that the profile modal updates live rows.

### Affected Areas

- `backend/config/prospect_conversion_views.py:732-745,806-864,1350-1374,1676-1778` — draft creation/prefill, user-step validation, and reactivation finalize currently mix wizard input with live profile ownership.
- `backend/config/api_urls.py:217-256` — add the dedicated `PATCH /api/admin/clientes/<id>/perfil/` route and retain the existing reactivation routes for wizard steps.
- `backend/customers/models.py:136-184` — target `Cliente` fields, required `OneToOneField` relationship, and current model constraints.
- `backend/accounts/models.py:18-63` — target `Usuario` fields; `username` also inherits `AbstractUser` uniqueness and the existing profile endpoint excludes password changes.
- `backend/config/api/serializers/clientes.py` — inspect the client serializer; if it is read-only or too broad, add a focused client-profile write serializer there.
- `backend/config/api/viewsets/clientes.py:266-280` — natural location for a live profile action on the admin client ViewSet.
- `backend/config/api_serializers.py:22-30` — only report serializers are present; no generic live profile serializer was found.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx:50-168` — make all fields except `observacionesCliente` read-only during reactivation/new procedure, while retaining draft submission and the existing password omission.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx:187-213` — pass the reactivation mode and render the restricted step; no endpoint contract change is required here.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts:195-243,470-490` — initialize reactivation user data from the draft/live snapshot and submit the restricted step through the existing draft endpoint.
- `frontend/aesthetic-clinic/src/pages/admin/client-detail/ClientProfileModal.tsx:1-127` — replace draft load/save calls with the dedicated live profile API and keep all 13 editable fields editable.
- `frontend/aesthetic-clinic/src/services/api/admin.ts:1246-1259` — add a PATCH client-profile client while preserving the existing reactivation step client.
- `backend/tests/suspension/test_conversion_split.py:54-102,259-291` — add regression assertions that reactivation finalize leaves live profile data unchanged when step 1 is edited or skipped.
- `backend/billing/tests/test_conversion_first_payment.py:49-97,147-175` — preserve payment coverage and optionally add a live-profile isolation assertion for the reactivation finalize path.
- `backend/tests/test_profile_update.py:11-18,99-184` — establish reusable validation/partial-update patterns, but this change must remain distinct from the self-service endpoint and must not expose password changes.

### Approaches

1. **Option B (Recommended)**: Add a dedicated admin-only `PATCH /api/admin/clientes/{id}/perfil/` that validates and updates the live `Cliente` plus its `Usuario` in one transaction, with no password field and no draft/wizard dependency. Rewire the modal to load/save through this API. Keep `paso-1` for wizard draft persistence, but make its profile inputs read-only for reactivation/new procedure except `observacionesCliente`, which remains an annotation for the new procedure and can continue through the draft/finalization path.
   - Pros: Establishes explicit ownership boundaries; profile edits are immediately visible and survive draft cancellation; leaves prospect conversion and operation finalization intact; prevents future reactivation drafts from inheriting modal edits; supports one canonical validation path for the 13 requested fields.
   - Cons: Adds a new endpoint, serializer, URL, API client method, and regression tests; requires defining the canonical source for duplicated phone/date/observations between `Usuario` and `Cliente`; the existing draft and live representations may still diverge.
   - Effort: Medium

2. **Option A**: Make the profile modal a separate read-only view or remove its save action, and leave the existing reactivation step as-is (optionally making only the most dangerous identity fields read-only in the UI/backend).
   - Pros: Smaller implementation and lower regression risk; avoids introducing a new live-write contract; preserves existing conversion behavior for the wizard.
   - Cons: Does not satisfy the requirement that all current modal fields remain editable; a UI-only restriction is bypassable through the API; still leaves the finalize overwrite bug and misleading modal behavior; leaves duplicated ownership in the shared draft endpoint.
   - Effort: Low

### Recommendation

Adopt Option B. The shared draft endpoint must remain the boundary for wizard-only data, but it must not be treated as a live profile editor. A focused live-profile endpoint gives the modal an honest persistence target, while the UI and backend guard can keep reactivation step-1 profile fields read-only without breaking operation/medical draft flow. The proposal should include explicit field ownership rules, transactional validation, no password support, and regression tests proving that both modal saves and later reactivation finalization have the expected live/draft effects.

### Risks

- **Medium — Duplicated fields are updated inconsistently** (`Usuario` and `Cliente` both contain phone/date/observations-related values): define a single source of truth in the proposal and update both rows only where the requested modal contract requires it; add assertions for every accepted field.
- **Medium — Existing clients have missing or invalid profile data**: make PATCH field-level/partial and preserve omitted values; reject only values that violate explicit model/serializer rules rather than requiring a full replacement.
- **Medium — Branch authorization is bypassed or leaks cross-branch clients**: reuse `_admin_client_queryset`/admin ViewSet authorization and add unauthenticated, non-admin, and cross-branch tests.
- **Low — The modal still sends draft-shaped data or accidentally exposes password**: keep a separate typed client/payload type, omit `password`, and add an unknown-field/password regression test.
- **Low — Reactivation UI still submits stale profile values**: initialize `userForm` from the live snapshot or a clearly non-editable draft prefill, and disable/read-only all non-observation fields before submit.
- **Medium — Drafts from older clients contain profile edits that finalize today still overwrites live rows**: this change should remove live updates from reactivation finalize; existing drafts may need a one-time migration/cleanup decision. The safest proposal should state that pending drafts created under the old behavior cannot silently overwrite live data and should be treated as requiring an explicit profile update before finalization.
- **Low — New endpoint response shape differs from current draft `userData`**: define and test one response contract for the modal, or normalize the serializer to the existing camelCase fields (`fechaNacimiento`, `direccionDomicilio`, `observacionesCliente`, etc.).

### Ready for Proposal

Yes — the orchestrator should write a proposal for a focused live client-profile PATCH endpoint, a read-only reactivation step-1 policy, and tests covering live/draft separation, all requested fields, validation, authorization, and finalize isolation. The proposal should explicitly choose the canonical `Usuario`/`Cliente` ownership for duplicated values and document handling for pre-existing drafts affected by the old finalize behavior.
