# Exploration: dp4500-host-app-integration-phase3-capture-client

**Prepared**: 2026-09-28
**Branch under review**: `feat/dp4500-host-app-integration-phase2-sdd` at `c07c2f9`
**Companion archive**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` (Phase 2A4 / 2A5 closed, archived at `71f518b` lineage); Phase 2A6 + Phase 2A7 (cascade revoke hardening) also archived on the same lineage.
**Purpose**: Define the scope of Phase 3 — vendorize the DigitalPersona Web SDK in the frontend `node_modules`, replace the Phase 2A4 placeholder `enrollIdentity(externalId, '', ...)` with a real capture wrapper, and decide Q1 (capture strategy).

This file is read-only for the orchestrator. It does NOT modify the SDD artifacts.

---

## 1. Goal

Phase 3 = **vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `frontend/aesthetic-clinic/node_modules` and replace the Phase 2A4 placeholder `dp4500-capture-client.ts` with a real `captureFingerprint()` wrapper** that the wizard's `handleConfirmCapture` actually invokes.

**Q1 decision (locked in this session)**: browser Web SDK direct (no `fingerprint-agent` proxy). The original 2026-07-29 DP4500 design (`openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md`) chose the agent pattern (Linux `fprintd` + per-PC `fingerprint-agent` exposed via Cloudflare Tunnel); the user has **overridden** that decision. The agent pattern stays on the table as the Phase 4 fallback if Phase 3's SDK-direct path proves unworkable in production.

**Compatibility with Phase 2A4**: the NO_AGENT fallback (placeholder empty `template_b64` + mint UUID + enroll pubkey anyway) is preserved as the dev-environment code path for workstations without a DP4500 attached. The build flag `VITE_BIOMETRIC_SUSPENDED` (read by `isBiometricSuspended()` at `useConversionWizard.ts:181`) also remains the canonical "skip capture entirely" path.

---

## 2. What landed in Phase 2 (already covered — DO NOT regress)

The Phase 2A4 archive (`explore-reconciliation.md` §1 at line 14) documents what shipped. The Phase 3 scope is built on top of this surface:

### 2.1 Frontend biometric layer (Phase 2A2 / 2A3)

| File | Surface shipped | Status |
|---|---|---|
| `frontend/aesthetic-clinic/src/services/biometric/ed25519-key-manager.ts` | `ensureSigningKey()`, `publicKeyToBase64Url()`, `signCanonical(...)`. Private key non-extractable in IndexedDB (`dp4500-signing:keys:signing-key-v1`). | ✅ Phase 2A2 |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` | `enrollIdentity(userExternalId, templateB64, signingKey, fingerprint, format)`, `challengeIdentity(userExternalId)`, `verifyIdentity(captureToken, userExternalId, serverNonce)`, `captureAndVerify(...)`. Reads `VITE_DP4500_SERVICE_API_KEY` at module load (`dp4500-capture-client.ts:55`). `BiometricSuspendError` class. | ✅ Phase 2A2/A3 (placeholder `template_b64 = ''`) |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | `handleConfirmCapture` (lines 701-865) mints `crypto.randomUUID()` and calls `enrollIdentity(externalId, '', signingKey, fingerprintHex, 'DP_PROPRIETARY')` (line 760). NO_AGENT fallback at lines 842-859. UUID persisted in `biometricForm.externalId`. | ✅ Phase 2A4 |
| `frontend/aesthetic-clinic/src/types/prospectConversion.ts` | `ProspectConversionBiometricData.externalId?: string` field. | ✅ Phase 2A4 |
| `frontend/aesthetic-clinic/vite.config.ts` | Dual-backend proxy: `/api/biometric/service/* → VITE_DP4500_PROXY_TARGET` (default `127.0.0.1:8000`) most-specific; everything else → `VITE_API_PROXY_TARGET`. | ✅ Phase 2A4 |
| `frontend/aesthetic-clinic/.env.example` | Documents `VITE_DP4500_SERVICE_API_KEY`. | ✅ Phase 2A4 |
| `frontend/aesthetic-clinic/public/fingerprint-probe.html` | Phase 1 probe page (lines 1-238). Loads `/websdk/fingerprint.sdk.min.js` and exercises `Fingerprint.WebApi.startAcquisition`. The probe page's §"Hallazgo del probe" (lines 80-88) explicitly notes the SDK is a WebChannel wrapper and that "pura-browser" capture is NOT viable without a local relay. | ✅ Phase 1 (read-only evidence) |

### 2.2 Backend wire contract (Phase 1, already validated)

- `POST /api/biometric/service/identity/enroll/` accepts empty `template_b64` (Phase 2A4 placeholder contract, validated end-to-end at `7f89a35` per `explore-reconciliation.md:46`).
- `POST /api/biometric/service/challenge/identity/<uuid>/` returns `server_nonce` as urlsafe base64 (wire-contract fix at `75a481a`).
- `POST /api/biometric/service/verify/identity/` does real Ed25519 verify against the stored pubkey (server-side commit `de64ad4`).

### 2.3 Build flags

- `VITE_BIOMETRIC_SUSPENDED=true` (per `package.json:9` `build:suspended` script) is the canonical "skip capture entirely" mode. Used by `isBiometricSuspended()` at `useConversionWizard.ts:181`.

### 2.4 Out of scope for Phase 3

The Phase 2A4 reconciliation (`explore-reconciliation.md:68`) explicitly defers "Phase 3 capture client" as the next phase. Phase 3 is the first time anything real about capture is wired.

---

## 3. Q1 — Capture strategy decision

### 3.1 Candidates

| Approach | Mechanism | Status |
|---|---|---|
| **A — Browser Web SDK direct (Q1-A)** | Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `frontend/aesthetic-clinic/package.json`; import via dynamic import in `dp4500-capture-client.ts::captureFingerprint()`; browser calls `Fingerprint.WebApi` directly. No extra process on the workstation. | **CHOSEN** (per user session) |
| **B — `fingerprint-agent` local via HTTP** | Separate `fingerprint-agent` Python process on the workstation exposing `POST /capture /match /health` on `127.0.0.1:8765` (per the 2026-07-29 design §6 at `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md:96-107`). Browser calls `fetch('http://127.0.0.1:8765/capture', ...)`. | DEFERRED — Phase 4 fallback if A proves unworkable in production |

### 3.2 Why A (the user's choice)

- **One fewer moving part per workstation**: no per-PC Python agent, no `cloudflared` tunnel, no systemd unit. The browser does the work.
- **Phase 2A2/A3/A4 already committed to the Opción A model** (`dp4500-capture-client.ts:1-31` header explicitly says "Opción A: real capture via WebCrypto + HID WebSdk"). The backend Phase 1 service API was designed around an Opción A client (single workstation, signs challenges in-browser).
- **Probe page evidence is mixed but not fatal**: `fingerprint-probe.html:80-88` shows the SDK is a WebChannel wrapper (`Fingerprint.WebApi` is `websdk.client.WebSdk` underneath), but the Phase 1 probe DID successfully load the SDK and enumerate devices — only the actual sample-acquisition step required a local relay. Whether this is a hard wall or a configuration choice depends on whether the operator PC has the HID Authentication Device Client (or equivalent WebChannel host) running. Phase 3 vendors the SDK first, then tests on a real workstation before committing to the wrapper as the production path.

### 3.3 Why not B (the deferred option)

- **Agent pattern was the right choice for the original DP4500 project** (`fingerprint-agent` + Cloudflare Tunnel per `2026-07-29 design §6`) because the original stack was Linux-only, the `fingerprint-agent` could speak D-Bus to `fprintd`, and the operator PCs were already known to be Linux. In **this** repo (the clinic) the operator PCs are Windows browsers hitting a Vite dev server; the agent pattern requires a Windows-side Python process, which is significantly more operational complexity.
- **Per-PC cloudflared tunnel** is also overkill for a localhost-only capture endpoint. Cloudflare Tunnel makes sense when the agent is on a different network from the consumer; here both are on the same Windows desktop.
- **No D-Bus on Windows**: the original design's `fprintd` D-Bus path is Linux-only. A Windows port would need a separate `WinUsb`/`WinHID` shim (or a relay that talks the DP4500 SDK's own protocol), which is essentially the same work as wiring the SDK directly.

### 3.4 What B keeps on the table

If Phase 3's SDK-direct path cannot acquire a sample in production (e.g. operator PCs lack the HID Authentication Device Client and installing it is not an option), Phase 4 can pivot to a Windows-port of `fingerprint-agent` (a tiny Python service that wraps the DP4500 SDK on `127.0.0.1:8765` and exposes the same REST surface). The wizard's `captureFingerprint()` wrapper would then swap implementations behind the same TS surface — no UI change.

---

## 4. Open work for Phase 3

### 4.1 Vendorize the SDK (5-10 MB)

| WU | Action | File(s) | Notes |
|---|---|---|---|
| **WU-3.1** | Add `@digitalpersona/fingerprint` + `@digitalpersona/websdk` to `frontend/aesthetic-clinic/package.json` `dependencies`. Run `npm install`. Vendor the minified browser bundle at `frontend/aesthetic-clinic/public/websdk/fingerprint.sdk.min.js` (per the probe page's loader at `fingerprint-probe.html:115`). | `package.json`, `package-lock.json`, `public/websdk/` | Size budget: 5-10 MB total. Use a `^1.0.0` semver range to match the probe (line 53: `@digitalpersona/fingerprint 1.0.0`). |

### 4.2 Replace the placeholder capture wrapper

| WU | Action | File(s) | Notes |
|---|---|---|---|
| **WU-3.2** | Add `captureFingerprint(): Promise<{ templateB64: string; qualityScore: number; deviceSerial: string; }>` to `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts`. Uses a **dynamic import** of the vendored SDK (`await import('@digitalpersona/fingerprint')`) to keep the initial bundle small (Risk R2). Walks `Fingerprint.WebApi` lifecycle: construct `new sdk.WebApi()`, wire `onDeviceConnected` + `onSamplesAcquired` + `onErrorOccurred`, call `webApi.startAcquisition(SampleFormat.PngImage, '')`, resolve on first `onSamplesAcquired` event. | `dp4500-capture-client.ts` | Keep `enrollIdentity` / `challengeIdentity` / `verifyIdentity` signatures unchanged. The new `captureFingerprint()` is a sibling, not a replacement. |
| **WU-3.3** | Update `handleConfirmCapture` in `useConversionWizard.ts` (lines 701-865): when `biometricSuspended` is false and the legacy endpoint does NOT return NO_AGENT, call `captureFingerprint()` first, then pass the real `templateB64` + `qualityScore` to `enrollIdentity(...)` (line 760). Fall back to the existing placeholder `''` flow when `captureFingerprint()` throws (preserves dev without hardware). | `useConversionWizard.ts` | NO_AGENT fallback (lines 842-859) MUST be preserved verbatim — it is the dev escape hatch. |

### 4.3 Tests (mock the SDK; no hardware required)

| WU | Action | File(s) | Notes |
|---|---|---|---|
| **WU-3.4** | Unit tests for `captureFingerprint()` that mock `@digitalpersona/fingerprint` and assert: (a) `sdk.WebApi` is constructed; (b) `startAcquisition(SampleFormat.PngImage, '')` is called; (c) `onSamplesAcquired` resolves with `{ templateB64, qualityScore, deviceSerial }`; (d) `onErrorOccurred` rejects with a typed error. The frontend has NO unit runner today (`openspec/config.yaml:50-51` `unit_available: false`); Phase 3 either adds Vitest (preferred — mirrors the Phase 4 Vitest note at `config.yaml:69`) or skips unit-level coverage and relies on the Playwright e2e. | New `dp4500-capture-client.test.ts` (Vitest) OR `tests/e2e/` (Playwright with `mock-service-worker` for the SDK) | Per `openspec/config.yaml` `apply.tdd: true` for the backend but frontend is `tdd: false` today — adding Vitest is the canonical Phase 4 path. Phase 3 should at minimum add an e2e Playwright spec that loads `fingerprint-probe.html` with a stubbed SDK and asserts the new `captureFingerprint()` happy path. |
| **WU-3.5** | Update the existing Playwright smoke (the probe page at `fingerprint-probe.html`) to load the vendored SDK from `node_modules` rather than the legacy `public/websdk/fingerprint.sdk.min.js` static path. Confirms the vendored bundle is reachable in the dev server. | `public/fingerprint-probe.html` (or new `src/dev-tools/dp4500-probe.tsx`) | The probe page is the only existing UI surface that exercises the SDK; Phase 3 should either refresh it or replace it with a TypeScript variant. |

### 4.4 Documentation

| WU | Action | File(s) | Notes |
|---|---|---|---|
| **WU-3.6** | Document the hardware requirements: "The DP4500 reader must be connected via USB. The operator's browser must be Chrome or Edge (no Firefox, no Safari). The HID Authentication Device Client must be installed on the operator PC (or the WebChannel host the SDK expects must be running). The `VITE_DP4500_SERVICE_API_KEY` env var must be set. The `VITE_BIOMETRIC_SUSPENDED` flag must be `false`." | New section in `HOW_TO_RUN.md` (does not exist today — `glob 'HOW_TO_RUN*'` returns no results in `frontend/aesthetic-clinic/`). Either create `frontend/aesthetic-clinic/HOW_TO_RUN.md` or add to the root `README.md`. | Match the Phase 2A4 `HOW_TO_RUN.md` style if it exists in the DP4500 estandar sibling repo (out of scope to read here; assume same minimal "setup steps" style). |

---

## 5. Risks

### R1 — SDK is WebChannel-based; direct browser SDK may not work without the HID Authentication Device Client installed on the operator PC

**Severity**: high.

**Evidence**: `fingerprint-probe.html:80-88` (the Phase 1 probe page's §"Hallazgo del probe") explicitly states: "El SDK cargado es un wrapper sobre `WebSdk.WebChannelClient` (puerto local 52181). Para capturar en browser hace falta un servidor local (HID Authentication Device Client, o el desktop client de DP4500 estandar, o un relay custom) corriendo en el PC del operador. Esto descarta la **Opción A pura-browser**; la captura real pasa a ser un componente Electron (Opción B)."

The probe page was written when the DP4500 estandar project chose the agent pattern (Option B in the original framing); the user has since chosen to override that decision and try Option A anyway. Phase 3 vendors the SDK and tests on a real workstation first; if the WebChannel host requirement holds, Phase 4 installs it via the operator PC bootstrap (or pivots to the agent pattern).

**Mitigation**:
- (a) **Keep the Phase 2A4 NO_AGENT placeholder as the dev fallback** (`useConversionWizard.ts:842-859`). The wizard still completes end-to-end on a workstation without hardware; the backend enrolls with empty `template_b64` per the Phase 2A4 placeholder contract.
- (b) **Keep `VITE_BIOMETRIC_SUSPENDED=true` as the full skip path** (`useConversionWizard.ts:712-724`). The build flag remains the canonical "this deployment does not capture" mode.
- (c) **Treat Phase 3's verify-report as the gate**. If `captureFingerprint()` cannot acquire a sample on the operator's workstation, do not archive — open Phase 4 with the agent pattern instead.

### R2 — Vendorized SDK adds ~5-10 MB to the bundle; the initial page-load bundle must stay small

**Severity**: medium.

**Evidence**: `@digitalpersona/fingerprint` ships a minified browser bundle of ~2-3 MB; `@digitalpersona/websdk` adds the WebChannel client of similar size. The total is comparable to a code-split route.

**Mitigation**: **Dynamic import** in `captureFingerprint()` (`await import('@digitalpersona/fingerprint')`). The SDK is loaded on-demand only when the operator clicks "Capturar huella" in the wizard — not at initial page render. The wizard modal opens, the SDK fetch starts, the device picker pops, the operator scans. Initial bundle stays at the Phase 2A4 size (~800 KB gzipped); the SDK chunk is fetched only when the modal triggers it.

### R3 — The original DP4500 project chose the agent pattern for good reasons; Phase 3 deviates

**Severity**: medium.

**Evidence**: `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6 ("Agent Protocol") and §2 ("Architecture") establish the agent pattern as the production design. The rationale (per §2 §6): OS independence (Linux `fprintd` D-Bus), no vendor lock-in (Fernet at rest + tunnel security boundary), controlled via Cloudflare Tunnel (no inbound ports on the operator PC). Phase 3 abandons all three for the SDK-direct path.

**Mitigation**:
- (a) **Phase 4 fallback**: if R1's WebChannel requirement holds, Phase 4 ships the agent pattern as documented in the 2026-07-29 design. The wizard's `captureFingerprint()` wrapper surface stays unchanged; only the implementation swaps.
- (b) **No DB migration in Phase 3**: the wizard's contract with the backend (`enrollIdentity` accepts empty `template_b64`) already supports both paths. Phase 3 is frontend-only.
- (c) **No breaking change to the wire contract**: `dp4500-capture-client.ts` keeps the same exported function names; the backend Phase 1 endpoints are untouched.

---

## 6. Affected areas

| Path | Change | Why |
|---|---|---|
| `frontend/aesthetic-clinic/package.json` | ADD 2 deps: `@digitalpersona/fingerprint`, `@digitalpersona/websdk` | Vendorize the SDK |
| `frontend/aesthetic-clinic/package-lock.json` | Regenerated by `npm install` | Lock the SDK versions |
| `frontend/aesthetic-clinic/public/websdk/fingerprint.sdk.min.js` | New file (or symlink to `node_modules/...`) | Host the SDK bundle for the browser |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` | ADD `captureFingerprint()` function (new, sibling to `enrollIdentity`) | Replace the placeholder |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | MODIFY `handleConfirmCapture` (lines 701-865): call `captureFingerprint()` first when available; preserve NO_AGENT fallback (lines 842-859) verbatim | Wire the real capture |
| `frontend/aesthetic-clinic/public/fingerprint-probe.html` | Optional: update `script.src` to point at the vendored bundle path | Keep the probe usable |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` (NEW FILE) | Document hardware + SDK + env requirements | Operator runbook |
| `frontend/aesthetic-clinic/tests/e2e/dp4500-capture.spec.ts` (NEW FILE) | Playwright spec with `mock-service-worker` for the SDK | E2E coverage of the wrapper |

**NOT affected** (Phase 3 leaves these alone):

- `frontend/aesthetic-clinic/src/services/biometric/ed25519-key-manager.ts` — unchanged (Phase 2A2).
- `frontend/aesthetic-clinic/src/services/fingerprint/biometricClient.ts` — unchanged (legacy fprintd path; Phase 3's wrapper is parallel, not replacement).
- All backend files under `backend/` — unchanged. The Phase 1 wire contract already supports empty `template_b64` (Phase 2A4) and real Ed25519-signed challenges (Phase 2A5+).
- `openspec/specs/` — unchanged. Phase 3 does not touch main specs.
- All archive directories — unchanged.

---

## 7. Recommendation for proposal / design / tasks

### 7.1 Spec delta (proposal §Scope)

- **In Scope**:
  - Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `package.json` + `npm install` (WU-3.1).
  - Add `captureFingerprint()` to `dp4500-capture-client.ts` (WU-3.2).
  - Wire `captureFingerprint()` into `useConversionWizard.handleConfirmCapture` with the NO_AGENT fallback preserved (WU-3.3).
  - Unit or Playwright e2e coverage of the new wrapper (WU-3.4 + WU-3.5).
  - Document the hardware + SDK + env requirements (WU-3.6).
- **Out of Scope**:
  - Any backend change (the wire contract is already complete).
  - Any change to the DP4500 host (`C:\proyectos\DP4500 estandar\`) — Phase 3 is clinic-side only.
  - Real-hardware validation — gated on the operator's workstation; the verify-report flags failure.
  - **Phase 4 work** (deferred to a separate change):
    - Agent pattern (`fingerprint-agent` Python on operator PC + `127.0.0.1:8765` HTTP) if Phase 3's SDK-direct path fails.
    - Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing (per `explore-reconciliation.md` §3.2 Disposition: "Reasign").
    - `Cliente.external_id` UUIDField + finalize handler persistence (per `explore-reconciliation.md` §3.7 Disposition: "Reasign").
    - KMS-backed key store (per `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/proposal.md:281`).
    - mTLS between the wizard and DP4500.
    - DPIA §9 sign-off (regulatory, not engineering).
    - Vault-backed secret store (current `env_key_resolver` is dev-only).
    - Cron-driven `reconcile_pending_cascades` (per `archive-report.md §3.3` acknowledgement).

### 7.2 Design patterns to lock in

| # | Pattern | Source | What to follow |
|---|---|---|---|
| **P1** | **Dynamic import for the SDK** | This explore.md §5 R2 mitigation | `const sdk = await import('@digitalpersona/fingerprint')` inside `captureFingerprint()`; never at module top level. Keeps the initial bundle small. |
| **P2** | **NO_AGENT fallback is canonical** | Phase 2A4 (`useConversionWizard.ts:842-859`) | When `captureFingerprint()` throws OR when the legacy endpoint reports "No hay ningun lector", fall back to the empty-`template_b64` flow. The wizard stays navigable end-to-end on workstations without hardware. |
| **P3** | **`VITE_BIOMETRIC_SUSPENDED=true` is canonical skip** | Phase 2A4 (`useConversionWizard.ts:712-724`) | The build flag remains the "this deployment does not capture" path. `captureFingerprint()` is never called when the flag is on. |
| **P4** | **Verify-report gates Phase 3 archive** | This explore.md §5 R1 mitigation | If `captureFingerprint()` cannot acquire a sample on the real operator workstation, do not archive; open Phase 4 with the agent pattern instead. |
| **P5** | **Fronted function signatures are stable** | Phase 2A2 lineage | `enrollIdentity`, `challengeIdentity`, `verifyIdentity` keep their current signatures. The new `captureFingerprint()` is a sibling, not a replacement. |
| **P6** | **Backend wire contract unchanged** | Phase 1 + Phase 2A4 | The Phase 1 service API endpoints + the Phase 2A4 empty-`template_b64` placeholder contract are sufficient. No DP4500-side change in Phase 3. |

### 7.3 Tasks artifact (tasks.md §Suggested Work Units)

| Unit | Goal | Files touched | Lines estimate | Rollback boundary |
|---|---|---|---|---|
| **WU-3.1** | Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` | `package.json`, `package-lock.json`, `public/websdk/` | ~50 lines (`package.json` diff + lockfile regen + SDK copy) | Remove the deps from `package.json`, delete `public/websdk/`, revert the lockfile. No production code change. |
| **WU-3.2** | Add `captureFingerprint()` wrapper | `dp4500-capture-client.ts` | ~60-100 lines (dynamic import + WebApi lifecycle + error handling) | Revert the function. `enrollIdentity` / `challengeIdentity` / `verifyIdentity` still work. |
| **WU-3.3** | Wire `captureFingerprint()` into the wizard | `useConversionWizard.ts` (lines 701-865) | ~20 lines net (call `captureFingerprint()` first, then pass real bytes to `enrollIdentity`; preserve NO_AGENT fallback at lines 842-859) | Revert the diff; the placeholder flow returns. |
| **WU-3.4** | Unit OR e2e coverage of the wrapper | `tests/e2e/dp4500-capture.spec.ts` (Playwright) OR `dp4500-capture-client.test.ts` (Vitest) | ~80-150 lines | Delete the test file. |
| **WU-3.5** | Refresh the probe page to use the vendored bundle | `public/fingerprint-probe.html` | ~5 lines (one URL change) | Revert the URL. |
| **WU-3.6** | Document hardware + SDK + env requirements | `frontend/aesthetic-clinic/HOW_TO_RUN.md` (NEW FILE) | ~40-80 lines | Delete the file. |

Net line estimate: ~250-400 lines (well within the 400-line `review_budget_lines` cap from `openspec/config.yaml:64`). **No chain PRs required** unless verify surfaces a hardware blocker.

### 7.4 Pre-apply + Post-apply checklist

- **Pre-apply**:
  - `package.json` lists both `@digitalpersona/fingerprint` + `@digitalpersona/websdk` with `^1.0.0` semver ranges.
  - `public/websdk/fingerprint.sdk.min.js` exists (or symlinks to `node_modules/`).
  - `captureFingerprint()` is documented with JSDoc + a clear error type (`BiometricHardwareError` or similar — extend `BiometricSuspendError` family).
- **Post-apply**:
  - `npm run build` succeeds (Vite dynamic-import chunk for the SDK).
  - `npm run lint` passes.
  - Playwright e2e (or Vitest unit, if added) covers the happy path + the NO_AGENT fallback + the SDK error path.
  - `verify-report.md` documents the operator-workstation validation: did `captureFingerprint()` successfully acquire a sample with the HID Authentication Device Client installed? If yes, Phase 3 archives. If no, Phase 4 opens with the agent pattern.

---

## 8. Out of scope (Phase 4)

Phase 4 is the production-hardening + real-deployment phase. The Phase 2A4 archive already lists the deferrals (`openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/proposal.md:281` and `explore-reconciliation.md:68`). The Phase 3 explore does NOT enumerate them again; they are inherited from Phase 2:

- Real hardware integration (production deployment + per-PC operator bootstrap).
- KMS-backed key store + key rotation (current `BIOMETRIC_FERNET_KEY` env-only).
- mTLS between the wizard and DP4500 (Phase 2 ships plaintext-over-TLS-via-Vite-proxy only).
- DPIA §9 sign-off (regulatory, not engineering).
- Vault-backed secret store (current `DP4500_KEY_STORE_BACKEND=env` only).
- Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing (single-key today; per `explore-reconciliation.md` §3.2).
- `Cliente.external_id` UUIDField + finalize handler persistence (per `explore-reconciliation.md` §3.7).
- The `fingerprint-agent` proxy pattern as a fallback if Phase 3's SDK-direct path fails (per this explore.md §5 R1 mitigation).
- Cron-driven `reconcile_pending_cascades` (per Phase 2 archive-report §3.3).
- Cita verify path browser-signed canonical integration (Phase 2A5 work — `explore-reconciliation.md §4.3`).

---

## 9. Ready for proposal

**Yes.** The change is well-scoped, has a clear Q1 decision (browser Web SDK direct), has explicit risks with mitigations (R1: WebChannel host requirement; R2: bundle size; R3: deviation from the original agent pattern), and a fallback path (Phase 4 agent pattern). The apply agent's failure surface is fully characterized by §5 R1-R3 + §7.4 P1-P6 above.

The orchestrator should proceed to `sdd-propose` with the following guidance:

- **Q1 decision is locked**: do not let the proposal re-litigate "agent vs SDK-direct". The user has chosen the SDK path; the agent pattern is the Phase 4 fallback.
- **NO_AGENT fallback is canonical**: the proposal must explicitly state "NO_AGENT placeholder preserved as dev escape hatch" in §Scope to avoid drift during apply. The fallback at `useConversionWizard.ts:842-859` MUST survive the apply.
- **No chain PRs**: this is a ~250-400-line change, well under the 400-line review budget.
- **Verify-report gates archive**: the proposal must commit to a verify gate that proves `captureFingerprint()` works on the real operator workstation. If it does not, Phase 4 opens with the agent pattern instead.
- **Rollback path**: revert the `package.json` deps, delete `public/websdk/`, revert the `dp4500-capture-client.ts` change, revert the `useConversionWizard.ts` change. The Phase 2A4 placeholder flow returns intact.
