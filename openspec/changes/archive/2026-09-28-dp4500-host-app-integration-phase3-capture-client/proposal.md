# Proposal: Host-app integration — Phase 3 (Real fingerprint capture client)

**Change name**: `dp4500-host-app-integration-phase3-capture-client`
**Artifact store**: openspec (this repo, the clinic)
**Status**: draft (will be locked after `sdd-tasks`)
**Predecessor**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` — Phase 2A4 closed the wire contract with placeholder `template_b64`, validated end-to-end in the browser via DevTools.
**Companion exploration**: `openspec/changes/dp4500-host-app-integration-phase3-capture-client/explore.md` (Q1 decision rationale, R1/R2/R3 risks).

---

## 1. Why

### Problem statement

Phase 2A4 shipped a placeholder `dp4500-capture-client.ts` (`enrollIdentity(externalId, '', signingKey, fingerprintHex, 'DP_PROPRIETARY')` at `useConversionWizard.ts:760`) that enrolls the workstation's Ed25519 pubkey with an **empty** `template_b64`. That was the right move for closing the wire contract, but it leaves the clinic's two flagship biometric flows (conversion wizard step 4 + future cita verify) without a real capture path. When real DigitalPersona 4500 readers arrive at the operator PCs, the wizard cannot acquire a sample.

### Q1 decision (locked in this session)

**Browser Web SDK direct — vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `frontend/aesthetic-clinic/node_modules`.**

This **deviates** from the original 2026-07-29 DP4500 design (`openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6 "Agent Protocol"), which chose a per-PC `fingerprint-agent` Python process on `127.0.0.1:8765` exposed via Cloudflare Tunnel. That pattern was the right choice for the original Linux/fprintd stack. The clinic's operator PCs are **Windows browsers** hitting a Vite dev server; the agent pattern means a Windows-side Python process + per-PC tunnel + systemd unit, which is significantly more operational complexity for the same outcome. Phase 3 vendors the SDK first, tests on a real workstation, and **keeps the agent pattern as the Phase 4 fallback** if SDK-direct cannot acquire a sample in production.

### Why SDK-direct (the rationale, see explore.md §5)

| Risk from explore.md | Why it pushes us toward SDK-direct | Why the agent pattern is the fallback, not the default |
|---|---|---|
| **R1 — WebChannel host requirement** (`fingerprint-probe.html:80-88`) | Phase 3 installs the HID Authentication Device Client on the operator PC during bootstrap; the SDK then talks to it via WebChannel. | If R1 cannot be resolved by host configuration, Phase 4 ports the agent to Windows (a small Python service wrapping the DP4500 SDK on `127.0.0.1:8765`); the wizard's `captureFingerprint()` surface stays unchanged. |
| **R2 — bundle bloat (~5-10 MB)** | Dynamic import inside `captureFingerprint()` keeps the initial page-load bundle at the Phase 2A4 size (~800 KB gzipped); the SDK chunk loads only when the operator opens the capture modal. | N/A — the agent pattern is local-process, not bundled. |
| **R3 — deviation from the 2026-07-29 design** | Phase 2A2/A3/A4 already committed to the Opción A model (`dp4500-capture-client.ts:1-31` header); the Phase 1 service API was designed around an Opción A client (single workstation, signs challenges in-browser). | The agent pattern was correct for Linux; on Windows it duplicates work the SDK already does. |

### Business value

- One fewer moving part per workstation (no per-PC Python agent, no `cloudflared` tunnel, no systemd unit).
- Wizard step 4 captures a real `template_b64` (NOT empty) on workstations with the HID Authentication Device Client installed; DP4500 enroll returns 201 with non-empty template bytes.
- Workstations without hardware still complete the wizard end-to-end via the **NO_AGENT fallback** (Phase 2A4 behavior at `useConversionWizard.ts:842-859` — preserved verbatim).
- Phase 4 fallback (agent pattern) stays available if the verify-report flags a hardware blocker.

---

## 2. What changes

Four concrete deliverables, all in this repo's frontend.

### 2.1 Vendorize the DigitalPersona Web SDK

Add `@digitalpersona/fingerprint` + `@digitalpersona/websdk` (`^1.0.0` semver, matching the probe at `fingerprint-probe.html:53`) to `frontend/aesthetic-clinic/package.json` `dependencies`. Run `npm install` to regenerate `package-lock.json`. Vendor the minified browser bundle at `frontend/aesthetic-clinic/public/websdk/fingerprint.sdk.min.js` (per the probe page's loader at `fingerprint-probe.html:115`). Size budget: 5-10 MB total.

### 2.2 Add `captureFingerprint()` wrapper

In `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts`, add a sibling function:

```ts
export interface CaptureFingerprintResult {
  templateB64: string
  qualityScore: number
  deviceSerial: string
}

export async function captureFingerprint(): Promise<CaptureFingerprintResult>
```

Implementation: **dynamic import** of `@digitalpersona/fingerprint` (`await import('@digitalpersona/fingerprint')`) to keep the initial bundle small (R2 mitigation). Walk the `Fingerprint.WebApi` lifecycle: construct `new sdk.WebApi()`, wire `onDeviceConnected` + `onSamplesAcquired` + `onErrorOccurred`, call `webApi.startAcquisition(SampleFormat.PngImage, '')`, resolve on the first `onSamplesAcquired` event. Throw a typed `BiometricHardwareError` (extending the `BiometricSuspendError` family) on `onErrorOccurred` or device-not-connected.

**Keep the existing `enrollIdentity` / `challengeIdentity` / `verifyIdentity` signatures unchanged** — `captureFingerprint()` is a sibling, not a replacement.

### 2.3 Wire the wrapper into the wizard

Update `handleConfirmCapture` in `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` (lines 701-865):

- In the `enrollDp4500` closure (lines 753-768), call `captureFingerprint()` first when `biometricSuspended` is false; on success, pass the real `templateB64` + `qualityScore` + `deviceSerial` to `enrollIdentity(...)`. On `BiometricHardwareError`, fall back to the existing placeholder `''` flow (dev escape hatch).
- **The NO_AGENT fallback at lines 842-859 MUST be preserved verbatim** — it is the dev escape hatch when no physical reader is connected. The Phase 2A4 behavior is the canonical "no hardware" path.
- The `VITE_BIOMETRIC_SUSPENDED=true` flag (`useConversionWizard.ts:712-724`) remains the canonical "skip capture entirely" path; `captureFingerprint()` is never called when the flag is on.

### 2.4 Unit tests + operator runbook

- Unit tests for `captureFingerprint()` in `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts` (NEW) — mock `@digitalpersona/fingerprint` via Vitest or Playwright `mock-service-worker`. Assert: (a) `sdk.WebApi` is constructed; (b) `startAcquisition(SampleFormat.PngImage, '')` is called; (c) `onSamplesAcquired` resolves with `{ templateB64, qualityScore, deviceSerial }`; (d) `onErrorOccurred` rejects with a typed error.
- Refresh `frontend/aesthetic-clinic/public/fingerprint-probe.html` to load the vendored SDK from `node_modules` (one URL change at the `<script src="...">` tag).
- Document hardware + SDK + env requirements in a new `frontend/aesthetic-clinic/HOW_TO_RUN.md` (does not exist today).

---

## 3. Scope

### In scope (Phase 3)

- Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `package.json` + `npm install` + `public/websdk/` (deliverable 2.1).
- Add `captureFingerprint()` to `dp4500-capture-client.ts` (deliverable 2.2).
- Wire `captureFingerprint()` into `useConversionWizard.handleConfirmCapture` with NO_AGENT fallback preserved (deliverable 2.3).
- Unit tests + probe-page refresh + operator runbook (deliverable 2.4).

### Out of scope (Phase 4 / deferred)

- **Real-hardware validation gate**: `captureFingerprint()` must acquire a sample on the operator's workstation before Phase 3 archives. If it cannot, Phase 4 opens with the agent pattern instead. (Phase 4 work, NOT Phase 3.)
- **`fingerprint-agent` proxy fallback** (per `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6).
- KMS-backed key store (current `BIOMETRIC_FERNET_KEY` env-only).
- mTLS between the wizard and DP4500.
- DPIA §9 sign-off (regulatory, not engineering).
- Vault-backed secret store (current `DP4500_KEY_STORE_BACKEND=env` only).
- Per-sucursal `VITE_DP4500_SERVICE_API_KEY` routing (single-key today).
- `Cliente.external_id` UUIDField + finalize handler persistence (per Phase 2 archive `explore-reconciliation.md` §3.7 Disposition: "Reasign").
- Cron-driven `reconcile_pending_cascades`.

---

## 4. Decisions locked in this session

| # | Decision | Source |
|---|---|---|
| **Q1 — Capture strategy** | **Browser Web SDK direct** (vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk`); agent pattern deferred to Phase 4 fallback. | session 2026-09-28 |
| Q1.1 — Bundle strategy | Dynamic import inside `captureFingerprint()` (never at module top level). | R2 mitigation in explore.md §5 |
| Q1.2 — SDK error type | Extend `BiometricSuspendError` family with `BiometricHardwareError` (typed rejection). | design hygiene |
| Q1.3 — NO_AGENT preservation | Phase 2A4 fallback at `useConversionWizard.ts:842-859` survives the apply verbatim. | Phase 2A4 archive lineage |

---

## 5. Open items

**None.** The exploration phase resolved all design questions (Q1 lock + Q1.1-Q1.3). Remaining detail (exact `WebApi` event sequencing, dynamic-import chunk naming, Vitest vs Playwright decision) belongs in `design.md` and `tasks.md`, not in this proposal.

---

## 6. Affected components

| Path | Impact | Description |
|---|---|---|
| `frontend/aesthetic-clinic/package.json` | Modified | ADD 2 deps: `@digitalpersona/fingerprint` ^1.0.0, `@digitalpersona/websdk` ^1.0.0. |
| `frontend/aesthetic-clinic/package-lock.json` | Regenerated | Lock the SDK versions (via `npm install`). |
| `frontend/aesthetic-clinic/public/websdk/fingerprint.sdk.min.js` | New file | Host the minified browser bundle (5-10 MB). |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` | Modified | ADD `captureFingerprint()` + `CaptureFingerprintResult` type + `BiometricHardwareError` class. Keep existing exports unchanged. |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modified | `handleConfirmCapture` lines 701-865: replace the `enrollDp4500` closure at lines 753-768 to call `captureFingerprint()` first when `!biometricSuspended`; on success, pass real `templateB64` + `qualityScore` + `deviceSerial` to `enrollIdentity(...)`. **Preserve the NO_AGENT fallback at lines 842-859 verbatim.** |
| `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts` | New file | Unit tests for `captureFingerprint()` (Vitest, with `@digitalpersona/fingerprint` mocked). |
| `frontend/aesthetic-clinic/public/fingerprint-probe.html` | Modified | Update `<script src="...">` to point at the vendored bundle path. |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` | New file | Operator runbook: hardware requirements + SDK load + env vars. |

**NOT affected** (Phase 3 leaves these alone):

- `frontend/aesthetic-clinic/src/services/biometric/ed25519-key-manager.ts` — unchanged (Phase 2A2 lineage).
- All backend files under `backend/` — unchanged. The Phase 1 wire contract already supports empty `template_b64` (Phase 2A4) and real Ed25519-signed challenges (Phase 2A5+).
- `openspec/specs/` — unchanged. Phase 3 does not touch main specs.
- `useConversionWizard.ts` lines outside 701-865 — unchanged. The closure at 753-768 is the only modified region inside `handleConfirmCapture`.

---

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **R1 — SDK requires a WebChannel host (HID Authentication Device Client) on the operator PC** (`fingerprint-probe.html:80-88`). Direct capture may not work without it. | Med | (a) Keep the Phase 2A4 NO_AGENT placeholder as the dev fallback (`useConversionWizard.ts:842-859`). (b) Keep `VITE_BIOMETRIC_SUSPENDED=true` as the full skip path (`useConversionWizard.ts:712-724`). (c) **Verify-report gates Phase 3 archive**: if `captureFingerprint()` cannot acquire a sample on the operator's workstation, do not archive — open Phase 4 with the agent pattern instead. |
| **R2 — Vendorized SDK adds ~5-10 MB to the bundle.** | Med | **Dynamic import** in `captureFingerprint()` (`await import('@digitalpersona/fingerprint')`). SDK loads on-demand only when the operator clicks "Capturar huella" in the wizard — not at initial page render. Initial bundle stays at the Phase 2A4 size; SDK chunk is a separate fetch. |
| **R3 — Deviation from the 2026-07-29 design.** The original DP4500 project chose the agent pattern for good reasons (OS independence, no vendor lock-in, Cloudflare Tunnel as security boundary). Phase 3 abandons all three. | Med | (a) **Phase 4 fallback**: if R1's WebChannel requirement holds, Phase 4 ships the agent pattern as documented in `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6. The wizard's `captureFingerprint()` wrapper surface stays unchanged; only the implementation swaps. (b) **No DB migration in Phase 3**: the wizard's contract with the backend (`enrollIdentity` accepts empty `template_b64`) already supports both paths. Phase 3 is frontend-only. (c) **No breaking change to the wire contract**: `dp4500-capture-client.ts` keeps the same exported function names; the backend Phase 1 endpoints are untouched. |

---

## 8. Rollback plan

**Pure frontend additions — rollback = `git revert` of the single commit.** The Phase 2A4 placeholder flow returns intact.

Specifically:

1. Revert `frontend/aesthetic-clinic/package.json` (remove the two new deps).
2. Delete `frontend/aesthetic-clinic/public/websdk/`.
3. Revert `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` (remove `captureFingerprint()`, `CaptureFingerprintResult`, `BiometricHardwareError`; keep the original exports).
4. Revert `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` lines 753-768 (`enrollDp4500` closure returns to its placeholder-only behavior). **The NO_AGENT fallback at lines 842-859 is preserved unchanged through the rollback** — it is the canonical Phase 2A4 "no hardware" path.
5. Delete `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts`.
6. Revert `frontend/aesthetic-clinic/public/fingerprint-probe.html` (one URL change).
7. Delete `frontend/aesthetic-clinic/HOW_TO_RUN.md` (the Phase 3 section).

**After rollback, the wizard's end-to-end behavior matches Phase 2A4 exactly**: empty `template_b64`, pubkey enroll, NO_AGENT dev fallback. **Phase 2's end-to-end validation (validated in browser via DevTools) is not affected by either applying or rolling back Phase 3.**

---

## 9. Success criteria

Phase 3 is complete when:

1. `npx tsc -b --pretty false` exits 0 (TypeScript strict, including the new `captureFingerprint()` signatures).
2. `npx eslint src/services/biometric/dp4500-capture-client.ts src/pages/admin/prospect-convert/useConversionWizard.ts` exits 0 with 0 NEW errors (existing Phase 2A4 baseline preserved).
3. `npm run build` succeeds; Vite produces a separate dynamic-import chunk for `@digitalpersona/fingerprint`.
4. Unit tests for `captureFingerprint()` pass without hardware (Vitest with `@digitalpersona/fingerprint` mocked): (a) `sdk.WebApi` constructed; (b) `startAcquisition(SampleFormat.PngImage, '')` called; (c) `onSamplesAcquired` resolves with `{ templateB64, qualityScore, deviceSerial }`; (d) `onErrorOccurred` rejects with `BiometricHardwareError`.
5. **Workstation with real DigitalPersona 4500 connected AND HID Authentication Device Client installed**: wizard step 4 captures a real `templateB64` (NOT empty), DP4500 enroll returns 201, and `qualityScore > 0`. (Gated on operator-workstation validation; documented in `verify-report.md`.)
6. **Workstation WITHOUT hardware**: wizard step 4 still succeeds via the NO_AGENT fallback at `useConversionWizard.ts:842-859` (Phase 2A4 behavior preserved).
7. **Workstation with `VITE_BIOMETRIC_SUSPENDED=true`**: wizard step 4 skips capture entirely (Phase 2A4 build flag behavior preserved).
8. Total changed lines ≤ 400 net (well under the `review_budget_lines` cap per `openspec/config.yaml:64`).

---

## 10. References

- **Exploration**: `openspec/changes/dp4500-host-app-integration-phase3-capture-client/explore.md` — Q1 decision rationale, R1/R2/R3 risks, P1-P6 design patterns.
- **Predecessor proposal**: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/proposal.md` — Phase 2A4 wire contract.
- **Original design (deviated from)**: `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6 — the `fingerprint-agent` pattern, deferred to Phase 4 fallback.
- **Phase 1 probe page**: `frontend/aesthetic-clinic/public/fingerprint-probe.html` — Phase 1 evidence (`Fingerprint.WebApi` loads; actual acquisition requires a local relay).
- **Frontend capture client**: `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` (current Phase 2A4 placeholder).
- **Wizard**: `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` — `handleConfirmCapture` at lines 701-865; NO_AGENT fallback at lines 842-859.

---

## 11. Predecessor artifact chain

```
docs/plans/2026-09-27-biometric-web-integration.md
  ↓
C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1/
  ↓
openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/   (Phase 2A4 wire contract)
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/explore.md   (Q1 lock)
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/proposal.md   (this file)
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/specs/*/spec.md   (next)
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/design.md
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/tasks.md
  ↓
apply → verify → archive
```

---

**Awaiting user review before proceeding to `specs/`.**
