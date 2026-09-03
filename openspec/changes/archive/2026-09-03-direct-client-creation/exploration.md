# Exploration: direct-client-creation

## Current State

The system has **two parallel client-creation entry points** that funnel into the
same 5-step wizard, both backed by the `ProspectoConversionBorrador` model
(`backend/customers/models.py:87-133`).

1. **Prospect → Client (conversion).** Entry: `/cms/prospectos/:prospectId/convertir`
   → `AdminProspectConvertPage`. Backend resolves a draft via
   `_get_draft_convertible(request, prospecto_id=...)` (`prospect_conversion_views.py:719-731`).
   On `finalize`, the new branch (`prospect_conversion_views.py:1711-1754`) creates
   a `Usuario` (CLIENTE role) + `Cliente` and stamps the prospect as
   `marcar_como_convertido`.

2. **Reactivación de cliente.** Entry: `/cms/clientes/:clientId/reactivar` reusing
   the same `AdminProspectConvertPage` with `isReactivation=true`. Backend uses
   `_get_draft_convertible(request, cliente_id=...)` (`prospect_conversion_views.py:732-746`).
   On `finalize` the `else` branch (`prospect_conversion_views.py:1755-1768`) skips
   user creation and only updates `cliente.observaciones` for the existing row.

The reactivation path pre-populates the step-1 password hash from the existing
`Usuario.password` (`prospect_conversion_views.py:742-745`) and renders the
`ConversionStepUser` form with `isReactivation={true}`, which makes every input
`readOnly` (`ConversionStepUser.tsx:57-86,150-159`) and hides the password fields
(`ConversionStepUser.tsx:88-147`).

CI uniqueness, username uniqueness, and "ya existe cliente con este CI" checks
already live in `_validate_user_step` (`prospect_conversion_views.py:806-864`).

The `/cms/clientes` listing (`AdminClientsPage.tsx`) has NO creation affordance
today — only "Importar de otra sede" for cross-branch imports and a search
grid. The `PageHeader` actions slot exists and `AdminProspectsPage.tsx:356-358`
shows the convention (`{ label: 'Registrar prospecto', variant: 'primary', to: '/cms/prospectos/nuevo' }`).

`ProspectoConversionBorrador.prospecto` and `.cliente` are both nullable
`OneToOneField` with `null=True, blank=True` and **no DB-level check
constraint** forcing one to be non-null (verified at lines 94-107 of
`backend/customers/models.py`). However, **no application code currently
creates a draft with both null** — `_get_draft_convertible` short-circuits with
the error `"Se requiere un ID de prospecto o cliente."` at line 747.

## Affected Areas

- `backend/customers/models.py:87-133` — `ProspectoConversionBorrador` model.
  Both FKs are already nullable; no schema change needed, but no precedent for
  `(prospecto=NULL, cliente=NULL)`.
- `backend/config/prospect_conversion_views.py:714-747` — `_get_draft_convertible`.
  Needs a third branch (or new dedicated function) for "direct client" with
  neither FK set.
- `backend/config/prospect_conversion_views.py:1271-1299` — `_admin_conversion_detail`.
  Already correctly handles `prospecto=None` (`"prospect": ... if prospecto else None`),
  but the response payload assumes a `client` block (line 1286-1291) will be
  non-null in the reactivation case. For direct creation, `draft.cliente` will
  also be `None` at detail time (rows are only created in finalize), so the
  payload needs to tolerate both being null while still being usable by the
  wizard (the wizard summary cards in `AdminProspectConvertPage.tsx:150-166`
  read `data.prospect?.name`, `data.prospect?.phone`, `data.prospect?.state`,
  `data.prospect?.registeredBy`, `data.prospect?.createdAt` — all currently
  dereferenced off a non-null `prospect`).
- `backend/config/prospect_conversion_views.py:1676-2020` —
  `admin_prospect_conversion_finalize`. The `if draft.prospecto:` block at
  line 1711 creates `Usuario` + `Cliente`; the `else` at line 1755 assumes
  `draft.cliente` exists (reactivation). A third branch is needed for
  "direct client" (create both rows, like the prospect branch, but skip
  `prospecto.marcar_como_convertido` and skip `HuellaBiometricaCliente`
  migration from a prospect).
- `backend/config/prospect_conversion_views.py:806-864` — `_validate_user_step`.
  CI/username uniqueness logic is reusable as-is (lines 826-837 already
  handle "self" cases for reactivation; the new case is "no self yet" which
  is simply `existing_client = Cliente.objects.filter(ci=ci).first(); if existing_client: error`).
- `backend/config/api_urls.py:200-293` — URL routing. Existing pattern:
  `<resource>/<int:id>/reactivar/<step>/`. A new sibling like
  `clientes/directo/initialize/` or `clientes/directo/<step>/` fits naturally,
  or a unified `clientes/conversion/<step>/` namespace that dispatches by
  `?direct=true` — see Approaches.
- `frontend/aesthetic-clinic/src/pages/admin/AdminClientsPage.tsx:177-181` —
  `PageHeader` action slot. Add `{ label: 'Crear cliente directo', variant: 'primary', onClick: navigate }`
  or as a `to: '/cms/clientes/nuevo'` route.
- `frontend/aesthetic-clinic/src/App.tsx:133-137` — router. New route needed:
  `path="clientes/nuevo"` (or reuse `AdminProspectConvertPage` with a new
  `?direct=true` query param).
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/AdminProspectConvertPage.tsx`
  — the wizard page already branches on `isReactivation = !!clientId` (line 18).
  A third mode `isDirectCreation` is needed; copy/extend the existing
  ternary at lines 115-125 (`wizardTitle`, `wizardSubject`) and 134-137 (back link),
  and the wizard-summary card rendering at 150-166 (currently dereferences
  `data.prospect.*` which will be null).
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/ConversionStepUser.tsx`
  — already supports `isReactivation` and `hasPassword` flags. The
  direct-creation case is essentially `isReactivation=false` + `hasPassword=false`
  + force `readOnly=false` everywhere + force password fields visible. **No
  change needed to this file** if we just keep `isReactivation=false`.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts`
  — currently uses `prospectId`/`clientId` from URL params. Needs to handle
  a "no id" case (generate a draft client-side? or fetch from a new
  `/directo/initialize/` endpoint that creates an empty draft and returns
  its identifier?).
- `frontend/aesthetic-clinic/src/types/prospectConversion.ts:202-210` —
  `ProspectConversionResponse.prospect` is already `ProspectLead | null` and
  `client?` is `... | null`. Type system is ready.
- `frontend/aesthetic-clinic/src/services/api/admin.ts` — needs a new service
  function (e.g. `initializeDirectClientConversion`) mirroring
  `getAdminProspectConversionDetail`.

## Key Findings

- `ProspectoConversionBorrador.prospecto` and `.cliente` are both nullable
  `OneToOneField` with NO DB constraint forcing one to be non-null. The model
  schema supports a "(null, null)" row in theory; no application code has
  ever created one.
- `_get_draft_convertible` (`prospect_conversion_views.py:714-747`) REQUIRES
  one of `prospecto_id` or `cliente_id`. To create a draft without either FK,
  a new entry path is required — either a new arg like
  `create_direct=True` that creates the draft sans FK, or a new sibling
  function `_get_direct_draft(request)`.
- `_admin_conversion_detail` (`prospect_conversion_views.py:1271-1299`) is
  defensively coded for `prospecto=None` (line 1285) but assumes
  `cliente` non-null in the reactivation path (line 1286-1291 dereferences
  `cliente.usuario.nombre_completo`, `.ci`, `.estado_cliente`). For
  direct-client creation at detail time, `draft.cliente` is None; the
  `client` block in the payload will be `null`. The frontend type already
  permits this; the rendering code in `AdminProspectConvertPage.tsx:115-166`
  needs to skip the prospect-summary card when `data.prospect` is null.
- `admin_prospect_conversion_finalize` (`prospect_conversion_views.py:1676`)
  is a binary `if draft.prospecto: ... else: ...` (lines 1711-1768). The
  `else` branch dereferences `draft.cliente` unconditionally. For
  direct-client creation, we need a third branch (or restructure to:
  `if is_direct: create_user_and_client()`; `elif draft.prospecto:
  convert_prospect_to_client()`; `else: update_existing_client()`).
- `Cliente` and `Usuario` creation order is **Usuario first, then Cliente**
  with the same `target_branch` assigned to both (`prospect_conversion_views.py:1720-1754`).
  Required fields: `Usuario` needs `username, primer_nombre, apellido_paterno,
  password, rol=CLIENTE, is_active=True`; `Cliente` needs
  `usuario (OneToOne), sucursal_origen, fecha_nacimiento`. All other fields
  are optional. `cliente_codigo` is auto-generated on save via
  `Cliente.save` retry loop (`models.py:267-282`).
- `Cliente` has NO `es_migrado`/`sucursal_origen` migration flag for legacy
  clients. `sucursal_origen` is a normal FK that defaults to the admin's
  branch at creation. No special "legacy" marking exists. We don't need to
  invent one — the admin picks the branch via `target_branch = draft.prospecto.sucursal_registro or _get_branch_for_scope_check(request)`
  (line 1734) and the same logic applies to direct creation (use the admin's
  scope branch).
- Biometric migration logic at `prospect_conversion_views.py:1776-1826` is
  gated on `if draft.prospecto is not None` (line 1776) for prospect→cliente
  migration, and the `else` branch (line 1806+) is the reactivation
  "stamp from wizard payload" path. For direct-client creation we want the
  SAME stamping path as reactivation (line 1806-1826) — there is no
  prospect to migrate from, so we just stamp the huella from the wizard
  payload (or skip if suspended). This means direct creation can reuse the
  existing `else` branch as-is.
- Frontend `AdminProspectConvertPage.tsx:16-20` reads URL params
  `prospectId` / `clientId` and sets `isReactivation = !!clientId`. We need
  a third mode `isDirectCreation` (or, cleaner, a `mode: 'prospect' |
  'reactivation' | 'direct'` enum).
- CI uniqueness check already exists in `_validate_user_step`
  (`prospect_conversion_views.py:830-837`) and is correctly enforced for
  any non-empty CI input. No new validation logic is needed — just reuse.
- `ClientesViewSet.buscar_global` (`backend/config/api/viewsets/clientes.py:289-341`)
  is the existing public global-search endpoint. Could optionally be
  invoked BEFORE creating a direct client to surface existing matches to
  the admin — useful UX but not strictly required.

## Approaches

1. **Dedicated `/clientes/directo/` endpoint family + new wizard mode**
   - New backend view `admin_direct_client_initialize` that creates an
     empty `ProspectoConversionBorrador(prospecto=None, cliente=None,
     iniciado_por=request.user)` and returns its ID + `_admin_conversion_detail`.
     Add a sibling finalize path that dispatches the third branch in
     `admin_prospect_conversion_finalize` (or a dedicated
     `admin_direct_client_finalize` that wraps it).
   - New frontend route `clientes/nuevo` (or `clientes/directo`)
     rendering `AdminProspectConvertPage` with a `mode="direct"` prop.
     Reuse `ConversionStepUser` with `isReactivation=false`.
     Add a "Crear cliente directo" button in `AdminClientsPage` PageHeader.
   - Pros: cleanest separation, no behavioral cross-contamination, clear
     audit trail (a draft with both FKs null is unambiguous about its intent).
   - Cons: duplicates URL plumbing and route table; needs a 3rd ternary in
     every branchy rendering site.
   - Effort: **Medium**.

2. **Unified `clientes/conversion/<step>/` endpoint with `?direct=true` query**
   - Collapse reactivation + direct-client into a single URL family
     `clientes/conversion/<step>/` that takes `?direct=true` to mean
     "no FK yet, treat as new". `_get_draft_convertible` gains a
     `direct=True` branch.
   - Pros: less URL sprawl; one wizard entry point.
   - Cons: overloading semantics — same URL means "reactivate existing
     client" OR "create new direct client" depending on a query param.
     Breaks REST conventions slightly; harder to grep/audit. Also requires
     moving the existing reactivation routes to the new URL family
     (breaking change for any in-flight admin sessions/links).
   - Effort: **Medium-High** (and a small breaking change).

3. **Reuse reactivation plumbing with a pre-created throwaway Cliente**
   - Backend: `admin_direct_client_initialize` creates a temporary
     `Usuario` + `Cliente` immediately (status=INACTIVO, no operation
     yet), then returns the reactivation detail. The finalize
     branch is identical to the reactivation branch.
   - Pros: zero changes to `_get_draft_convertible` or finalize dispatch.
     The wizard thinks it's reactivating an existing client; the only
     difference is that the client was just created milliseconds ago
     with the data the admin is about to enter. Internally consistent.
   - Cons: creates a stub `Cliente` row that exists for ~5 minutes while
     the admin fills the wizard. If the admin abandons the wizard, an
     orphan Cliente lingers (cleanup required on cancel — already exists
     in `admin_prospect_conversion_cancel` so we can extend it). Adds a
     "pre-creation" UX wrinkle: username/CI uniqueness is enforced on
     the stub, so the wizard blocks BEFORE the admin fills the form.
   - Effort: **Low**.

## Recommendation

**Approach 1 (dedicated `/clientes/directo/` endpoint family + new wizard
mode)** is the right pick. Reasoning:

- The current model schema (`prospect_conversion_views.py:87-107`) already
  supports a `(prospecto=NULL, cliente=NULL)` draft — the migration is
  **conceptual**, not structural.
- Approach 3 (pre-create stub) creates phantom `Cliente` rows that
  dirty the `/cms/clientes` listing before the wizard even completes,
  confusing admins ("who is this CLI-XXXXXX row with no operations?").
  It also fires the username/CI uniqueness check on the stub instead of
  deferring it to the wizard's step 1, eliminating the "real-time error
  on the listing page" UX win.
- Approach 2 (URL overload) couples two semantically distinct operations
  (reactivation of existing client vs. creation of new client) behind a
  single URL family. That coupling will bite us the next time we want to
  add a behavior unique to direct creation (e.g. extra disclaimer text,
  optional "this client is legacy" checkbox).
- Approach 1 maps cleanly onto the existing naming convention:
  `clientes/<int:cliente_id>/reactivar/<step>/` →
  `clientes/directo/<step>/` (or `clientes/conversion-directa/<step>/`).
- The Wizard-side changes are minimal: 3-way enum instead of 2-way
  boolean, one new branch in the summary card rendering, one new "back"
  link. The `_validate_user_step` and `_admin_conversion_detail` helpers
  need minor defensive tweaks (tolerate `draft.cliente is None` in the
  detail payload), but no structural rewrite.

Concrete plan surface (for the proposal/spec phases):

- Backend: new views `admin_direct_client_initialize`,
  `admin_direct_client_detail`, `admin_direct_client_cancel`,
  `admin_direct_client_user_step`, `..._operation_step`,
  `..._medical_step`, `..._biometric_step`, `..._finalize`. Or a
  thin dispatcher with `_get_draft_convertible(direct=True)` and a
  generic step that resolves the right FK to update. Pragmatic decision:
  **share the existing step views** (already accept `prospecto_id=None,
  cliente_id=None`) but extend `_get_draft_convertible` to also accept
  `direct_id` (the draft's own PK) and update finalize dispatch.
- Frontend: `AdminProspectConvertPage` gains a `mode='direct'` prop (driven
  by `useParams()` or query string), `isDirectCreation` flag joins
  `isReactivation`. `AdminClientsPage` PageHeader gains a primary
  "Crear cliente directo" action. New service function
  `initializeDirectClientConversion` in `services/api/admin.ts`.

## Risks

- **Phantom draft rows.** The new `(null, null)` drafts need to be
  deletable on cancel and on session timeout. Existing
  `admin_prospect_conversion_cancel` works as-is for draft deletion; we
  should add a periodic cleanup (or just rely on cancel flow).
- **Username/CI race condition.** Two admins starting direct-client
  wizards simultaneously could both pass step 1 validation and one would
  fail at finalize. The same race exists in the prospect flow today; the
  `Usuario.objects.filter(username=username).exists()` check at
  `prospect_conversion_views.py:1717` is a TOCTOU window. Not introduced
  by this change, but worth noting.
- **Wizard UX for `(null, null)` summary card.** `AdminProspectConvertPage.tsx:150-166`
  renders three summary articles that currently assume `data.prospect` is
  non-null. For direct creation we should hide the summary card entirely
  (the admin already knows what they're entering) or replace it with a
  generic "Nuevo cliente directo" stub. Must NOT crash on null deref.
- **`ConversionStepUser` is readOnly on reactivation.** The current
  prop contract is `isReactivation: boolean` which forces readOnly on
  ALL fields including the username/CI (lines 57-86, 150-159). For
  direct creation we need editable fields everywhere — which is the
  same as the prospect flow (`isReactivation=false`). No code change
  needed; just verify the call site passes the right prop.
- **Backend detail view dereferences `cliente.usuario`** at
  `prospect_conversion_views.py:1288-1290`. For direct creation at
  detail time, `draft.cliente is None`; the block at line 1286 is
  guarded by `if cliente else None` so it's safe — but the
  `client` block in the response payload will be `null`, which the
  frontend must handle.

## Ready for Proposal

**Yes.** The schema already supports the change, the wizard's step 1
form is already correct for direct creation (it's the prospect-style
form, which IS the direct-client-style form), and the integration
surface is well-defined. The proposal phase should:

1. Confirm the URL naming convention (`clientes/directo/<step>/` vs
   `clientes/conversion-directa/<step>/` vs `clientes/nuevo/<step>/`).
2. Decide whether to share the step views with reactivation (via
   `_get_draft_convertible(direct_id=...)`) or duplicate them.
3. Decide whether the wizard summary card renders for direct creation
   or is hidden/replaced.
4. Confirm the cleanup story for abandoned `(null, null)` drafts.

### skill_resolution
`paths-injected`
