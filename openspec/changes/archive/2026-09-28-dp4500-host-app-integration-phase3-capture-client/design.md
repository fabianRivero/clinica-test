# Design: Phase 3 — Real capture client (vendorize DigitalPersona Web SDK + dynamic-import wrapper)

**Change name**: `dp4500-host-app-integration-phase3-capture-client`
**Artifact store**: openspec (this repo, the clinic)
**Status**: Draft (will lock after `sdd-tasks`)
**Predecessors**:
- `proposal.md` (Q1 locked — browser Web SDK direct)
- `specs/wizard-biometric-enrollment/spec.md` (Phase 3 delta — §"ADDED Capture Surface")
- `explore.md` (R1/R2/R3 risks, P1-P6 patterns)
- Phase 2A4 archive: `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/` — `handleConfirmCapture` placeholder at `useConversionWizard.ts:753-768`; NO_AGENT fallback at `useConversionWizard.ts:842-859`.

---

## 1. Architecture Decision

**Q1 — Locked**: browser Web SDK direct (NOT the `fingerprint-agent` proxy from the 2026-07-29 design §6). Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `frontend/aesthetic-clinic/node_modules`. Agent pattern stays as the Phase 4 fallback if the verify-report flags a WebChannel blocker.

**What changes**:
- `dp4500-capture-client.ts` gains a sibling function `captureFingerprint(): Promise<CaptureFingerprintResult>` (template_b64 + quality_score + device_serial) via **dynamic import** of the SDK.
- `useConversionWizard.ts::handleConfirmCapture` calls `captureFingerprint()` BEFORE the existing `enrollDp4500` placeholder call. On success, the real `template_b64` replaces `''` in `enrollIdentity(externalId, templateB64, ...)` at `useConversionWizard.ts:760`. On `BiometricHardwareError`, the existing `''` placeholder flow runs (dev escape hatch).
- `captureFingerprint()` is wired only when `biometricSuspended === false` (`useConversionWizard.ts:712-724`). The `VITE_BIOMETRIC_SUSPENDED=true` skip path is untouched.

**What does NOT change**:
- Phase 2A4 NO_AGENT fallback at `useConversionWizard.ts:842-859` — **carved out, preserved verbatim**. The `'No hay ningun lector'` branch + its UUID mint + `enrollDp4500(externalId)` call + the "DP4500 enroll OK; legacy omitido" status string are out-of-scope for any Phase 3 modification.
- Phase 2A5 challenge/verify paths (`challengeIdentity` / `verifyIdentity` / `captureAndVerify`) — unchanged signatures in `dp4500-capture-client.ts:185-243`.
- DP4500 service endpoints (`/api/biometric/service/*`) — unchanged. Phase 1 wire contract + Phase 2A4 empty-`template_b64` placeholder remain valid.
- `ed25519-key-manager.ts` — unchanged (Phase 2A2 lineage).
- All backend files under `backend/` — unchanged.

---

## 2. SDK Selection Rationale

| Axis | `@digitalpersona/fingerprint` | `@digitalpersona/websdk` | Decision |
|---|---|---|---|
| **API surface owned** | High-level `Fingerprint.WebApi`, `SampleFormat`, device/sample events. | Low-level `WebSdk.WebChannelClient`, transport, `WebSdk.Fingerprint.WebApi` re-export. | **Need both** — the high-level API is what the wrapper calls; the low-level client is the WebChannel transport underneath. |
| **Exports `WebSdk.WebChannelClient` / `WebSdk.Fingerprint.WebApi`** | Re-exports `WebSdk.Fingerprint.WebApi` for ergonomic usage. | Owns `WebSdk.WebChannelClient` + the transport plumbing. | Both required; `@digitalpersona/websdk` is the transport, `@digitalpersona/fingerprint` is the ergonomic facade. |
| **Bundle size (npm registry)** | ~2-3 MB minified (`@digitalpersona/fingerprint` ~2.4 MB unpacked). | ~3-5 MB minified (`@digitalpersona/websdk` ~3.8 MB unpacked). | Total ~5-8 MB. Mitigated by dynamic import (Pattern A). |
| **TypeScript support** | Ships `.d.ts` for `Fingerprint` namespace + `WebApi` class. | Ships `.d.ts` for `WebSdk` namespace + `WebChannelClient`. | Both type-check cleanly under `tsc -b --strict`. |
| **Last published** | 1.0.0 line (matching the probe at `fingerprint-probe.html:53`). | 1.0.0 line (companion release). | Both pinned at `^1.0.0` to match the Phase 1 probe page. |

**Dependency tree** (peer-dependency relationship in `node_modules/@digitalpersona/fingerprint/package.json`):

```
@digitalpersona/fingerprint@^1.0.0
  └── peerDependencies: @digitalpersona/websdk@^1.0.0
```

`@digitalpersona/fingerprint` declares `@digitalpersona/websdk` as a **peer** dependency (not a direct dep). Both go into `package.json` `dependencies` so `npm install` resolves the peer cleanly. No version mismatch risk under the `^1.0.0` semver.

---

## 3. Test Surface

Unit tests for `captureFingerprint()` — file path `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts` (NEW).

| # | Test name | What it asserts |
|---|---|---|
| **T-3.1** | `captureFingerprint() resolves with { templateB64, qualityScore, deviceSerial } on first onSamplesAcquired event` | `sdk.WebApi` constructed; `webApi.startAcquisition(SampleFormat.PngImage, '')` called; a fake `onSamplesAcquired` event resolves the returned Promise with non-empty `templateB64` and `qualityScore > 0`. |
| **T-3.2** | `captureFingerprint() rejects with BiometricHardwareError when onErrorOccurred fires` | A synthetic `onErrorOccurred` event rejects the Promise; the thrown error is `instanceof BiometricHardwareError`; the catch site in `useConversionWizard.ts` falls back to the NO_AGENT placeholder (`enrollIdentity(..., '', ...)`). |
| **T-3.3** | `captureFingerprint() rejects with BiometricQualityTooLow when quality_score < 60` | A synthetic `onSamplesAcquired` event with `qualityScore = 45` rejects with `BiometricQualityTooLow`; no `enrollIdentity` call is issued; the wizard surfaces "Calidad insuficiente. Vuelve a intentarlo." |

The test file mocks `@digitalpersona/fingerprint` via Vitest's `vi.mock('@digitalpersona/fingerprint', ...)`, returning a stub object that exposes `WebApi` (constructible), `SampleFormat.PngImage`, and the three event handlers (`onDeviceConnected`, `onSamplesAcquired`, `onErrorOccurred`) as `vi.fn()`s.

---

## 4. Test Patterns (code templates for apply phase)

### Pattern A — Dynamic import inside `captureFingerprint()`

```ts
// inside dp4500-capture-client.ts
export async function captureFingerprint(): Promise<CaptureFingerprintResult> {
  // R2 mitigation: keep the SDK out of the initial bundle. The chunk
  // is fetched only when the operator opens the capture modal in the
  // wizard — not at module load.
  const sdk = await import('@digitalpersona/fingerprint')
  const { SampleFormat } = await import('@digitalpersona/websdk')

  return new Promise<CaptureFingerprintResult>((resolve, reject) => {
    const webApi = new sdk.WebApi()
    webApi.onDeviceConnected = (device) => { /* no-op for now */ }
    webApi.onSamplesAcquired = (sample) => {
      try {
        const templateB64 = btoa(String.fromCharCode(...new Uint8Array(sample.Samples[0].Data)))
        const qualityScore = sample.Quality ?? 0
        if (qualityScore < 60) {
          reject(new BiometricQualityTooLow(`quality ${qualityScore} < 60`))
          return
        }
        resolve({
          templateB64,
          qualityScore,
          deviceSerial: sample.DeviceId ?? '',
        })
      } catch (err) {
        reject(err instanceof Error ? err : new BiometricHardwareError(String(err)))
      }
    }
    webApi.onErrorOccurred = (error) => {
      reject(new BiometricHardwareError(error?.message ?? 'SDK error'))
    }
    webApi.startAcquisition(SampleFormat.PngImage, '')
  })
}
```

**Reason**: dynamic import keeps the initial page-load bundle at the Phase 2A4 size (~800 KB gzipped). The SDK chunk is fetched only when the operator opens the wizard's capture modal — never at module top level.

### Pattern B — `BiometricHardwareError` (typed exception)

```ts
// dp4500-capture-client.ts — extends the BiometricSuspendError family
export class BiometricHardwareError extends BiometricSuspendError {
  readonly code = 'DP4500_HARDWARE' as const
  constructor(message: string) {
    super(message)
    this.name = 'BiometricHardwareError'
  }
}

export class BiometricQualityTooLow extends Error {
  readonly code = 'DP4500_QUALITY_TOO_LOW' as const
  constructor(message: string) {
    super(message)
    this.name = 'BiometricQualityTooLow'
  }
}
```

**Reason**: typed rejections give the wizard's catch site a clean discriminator (`code` field) for routing: `BiometricHardwareError` → fall back to NO_AGENT placeholder; `BiometricQualityTooLow` → show the retry message and abort `enrollIdentity`. Both extend the existing `BiometricSuspendError` family (`dp4500-capture-client.ts:141-147`) for downstream type-narrowing.

**Catch site in `useConversionWizard.ts`** (inside `enrollDp4500`, replacing the `''` literal):

```ts
// inside the enrollDp4500 closure (replaces the literal '' at line 760)
const enrollDp4500 = async (externalId: string): Promise<boolean> => {
  try {
    const signingKey = await ensureSigningKey()
    const digest = await crypto.subtle.digest('SHA-256', signingKey.publicKeyRaw)
    const fingerprintHex = Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, '0')).join('')
    let templateB64 = ''
    if (!biometricSuspended) {
      try {
        const captured = await captureFingerprint()
        templateB64 = captured.templateB64
      } catch (captureErr) {
        if (captureErr instanceof BiometricQualityTooLow) {
          setBiometricStatus('Calidad insuficiente. Vuelve a intentarlo.')
          return false
        }
        // BiometricHardwareError → fall through with templateB64 = ''
      }
    }
    await enrollIdentity(externalId, templateB64, signingKey, fingerprintHex, 'DP_PROPRIETARY')
    return true
  } catch {
    return false
  }
}
```

### Pattern C — Quality threshold check (mirror `cita_medica_form.html`)

The wizard reuses the UI text "Calidad insuficiente. Vuelve a intentarlo." from `dp4500_integration/templates/cita_medica_form.html` (per the spec delta §"Modified scenario — Real capture quality below threshold"). Threshold: `quality_score < 60` → throw `BiometricQualityTooLow`; operator can retry; no template is persisted.

### Pattern D — Wire-in point in `useConversionWizard.ts`

**Carving-out boundary**: the `enrollDp4500` closure at `useConversionWizard.ts:753-768` is the **only** region inside `handleConfirmCapture` (lines 701-865) that Phase 3 modifies. Specifically:

- Line 760 (`await enrollIdentity(externalId, '', signingKey, fingerprintHex, 'DP_PROPRIETARY')`) is the literal replaced by Pattern B's body — the `''` placeholder becomes a real `templateB64` from `captureFingerprint()`.
- Lines 842-859 (the `if (message.includes('No hay ningun lector'))` block) are **carved out — preserved verbatim**. The NO_AGENT fallback stays intact as the dev escape hatch when no physical reader is connected.

The two reactivation + prospect call sites at `useConversionWizard.ts:781` and `:812` (`const dp4500Enrolled = await enrollDp4500(externalId)`) are unchanged — they call the modified `enrollDp4500` and inherit the new behavior transparently.

---

## 5. Fixture Considerations

| Scenario | SDK behavior | Wizard behavior |
|---|---|---|
| **Dev (NO_AGENT path)** — no HID Authentication Device Client, no reader. | `captureFingerprint()` fails on `onDeviceConnected` event firing with empty device list, OR the dynamic import rejects because `window.WebSdk` is undefined. Throws `BiometricHardwareError`. | Catch site falls through with `templateB64 = ''`; `enrollIdentity(externalId, '', ...)` runs exactly as Phase 2A4 (placeholder). **Behavior is byte-identical to Phase 2A4 in dev.** |
| **Workstation with real hardware + WebChannel host** — DP4500 reader connected, HID Authentication Device Client running. | `captureFingerprint()` resolves with non-empty `templateB64`, `qualityScore > 60`, `deviceSerial` populated. | Wizard passes real `templateB64` to `enrollIdentity`; DP4500 enroll returns 201 with non-empty template bytes; wizard advances to step 5 with `calidadCaptura` from the SDK. |
| **Workstation with HID Auth Device Client running but no reader connected** — host alive, USB device missing. | SDK init succeeds; `onDeviceConnected` fires with empty device list; `startAcquisition` resolves with no `onSamplesAcquired` event. After a 30s timeout, the wrapper rejects with `BiometricHardwareError("no_device")`. | Catch site falls back to NO_AGENT placeholder; the wizard logs `BiometricHardwareError: no_device` to the browser console for operator diagnostics; UI shows the same NO_AGENT success message. |

---

## 6. Risks

| # | Risk | File:line impact | Mitigation | Phase 4 fallback |
|---|---|---|---|---|
| **R1** | SDK is WebChannel-based; `captureFingerprint()` may not work without the HID Authentication Device Client on the operator PC. (`fingerprint-probe.html:80-88`) | New `captureFingerprint()` at `dp4500-capture-client.ts` (~+80 lines). Wire-in at `useConversionWizard.ts:760` (the `''` placeholder). | (a) NO_AGENT fallback at `useConversionWizard.ts:842-859` preserved verbatim. (b) `VITE_BIOMETRIC_SUSPENDED=true` skip path at `useConversionWizard.ts:712-724` unchanged. (c) Verify-report gates Phase 3 archive: if `captureFingerprint()` cannot acquire a sample on the operator workstation, do not archive — open Phase 4 with the agent pattern. | Agent pattern from `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6. Wizard's `captureFingerprint()` surface stays unchanged; only the implementation swaps. |
| **R2** | Vendorized SDK adds ~5-8 MB to the bundle. | `frontend/aesthetic-clinic/package.json` (+2 deps), `public/websdk/fingerprint.sdk.min.js` (new file, ~5-8 MB). | Dynamic import inside `captureFingerprint()` (Pattern A). SDK chunk loads on-demand only when the operator opens the capture modal — initial bundle stays at the Phase 2A4 size (~800 KB gzipped). Vite produces a separate chunk for `@digitalpersona/fingerprint` (verifiable via `npm run build` output). | N/A — the agent pattern is local-process, not bundled. |
| **R3** | Deviation from the 2026-07-29 design (which chose the agent pattern for OS independence, no vendor lock-in, Cloudflare Tunnel security boundary). | Phase 3 abandons all three for SDK-direct. `dp4500-capture-client.ts:1-31` header changes from "Phase 4 work deferred" to "Phase 3 wired — see design §4 Pattern A". | (a) Phase 4 fallback (see R1). (b) No DB migration in Phase 3 — `enrollIdentity` already accepts empty + non-empty `template_b64` (Phase 1 + Phase 2A4). (c) No wire-contract change — `enrollIdentity` / `challengeIdentity` / `verifyIdentity` signatures unchanged. | Phase 4 agent pattern: Windows-port of `fingerprint-agent` Python on `127.0.0.1:8765` exposing the same REST surface; `captureFingerprint()` swaps implementation behind the same TS surface. |

---

## 7. Dependencies

| File | Action | Description |
|---|---|---|
| `frontend/aesthetic-clinic/package.json` | Modify | ADD 2 deps: `@digitalpersona/fingerprint` `^1.0.0`, `@digitalpersona/websdk` `^1.0.0`. |
| `frontend/aesthetic-clinic/package-lock.json` | Regenerate | Run `npm install` to lock the SDK versions. |
| `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` | Modify | ADD `captureFingerprint()` (~80 lines) + `CaptureFingerprintResult` type + `BiometricHardwareError` + `BiometricQualityTooLow` classes. Keep `enrollIdentity` / `challengeIdentity` / `verifyIdentity` / `captureAndVerify` exports unchanged. Update the module header comment (lines 1-31) to reflect Phase 3 wiring. |
| `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts` | Create (NEW) | Vitest unit tests for `captureFingerprint()` — T-3.1, T-3.2, T-3.3 (see §3). |
| `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` | Modify | Inside the `enrollDp4500` closure at lines 753-768: replace the literal `''` at line 760 with the Pattern B catch-site code. **Lines 842-859 (NO_AGENT fallback) preserved verbatim.** |
| `frontend/aesthetic-clinic/HOW_TO_RUN.md` | Create (NEW) | Phase 3 setup section: DP4500 reader USB, Chrome/Edge only, HID Authentication Device Client install, `VITE_DP4500_SERVICE_API_KEY` env var, `VITE_BIOMETRIC_SUSPENDED=false`. |

---

## 8. Success Criteria

Phase 3 closes when ALL of the following hold:

1. `npx tsc -b --pretty false` exits 0 (TypeScript strict, including the new `captureFingerprint()` + `BiometricHardwareError` + `BiometricQualityTooLow` signatures).
2. `npx eslint src/services/biometric/dp4500-capture-client.ts src/pages/admin/prospect-convert/useConversionWizard.ts` exits 0 with **0 NEW errors** (existing Phase 2A4 baseline preserved).
3. Vitest unit tests for `captureFingerprint()` pass without hardware (T-3.1, T-3.2, T-3.3 — SDK mocked).
4. Workstation with real DigitalPersona 4500 connected AND HID Authentication Device Client installed: wizard step 4 captures a **non-empty** `template_b64`, DP4500 enroll returns 201, `qualityScore > 60`. (Gated on operator-workstation validation; documented in `verify-report.md`.)
5. Workstation WITHOUT hardware: wizard step 4 still completes end-to-end via the NO_AGENT fallback at `useConversionWizard.ts:842-859` (Phase 2A4 behavior preserved verbatim).
6. Workstation with `VITE_BIOMETRIC_SUSPENDED=true`: wizard step 4 skips capture entirely (`useConversionWizard.ts:712-724`); `captureFingerprint()` is never called.
7. `npm run build` succeeds; Vite produces a **separate dynamic-import chunk** for `@digitalpersona/fingerprint` (verifiable in `dist/assets/`).
8. Total changed lines ≤ 400 net (well under `openspec/config.yaml:64` `review_budget_lines` cap).

---

## 9. Cross-cutting concerns

- **Bundle hygiene**: dynamic import (Pattern A) is the only R2 mitigation. The vendored `public/websdk/fingerprint.sdk.min.js` is the legacy Phase 1 probe-page loader — Phase 3 keeps it for the probe page only; the wizard's `captureFingerprint()` loads via the bundler-managed chunk path.
- **Threat matrix**: N/A — Phase 3 does not touch routing, shell commands, subprocesses, VCS/PR automation, executable-file classification, or process integration. The SDK runs inside the browser sandbox; no new process boundary.
- **Module header drift**: `dp4500-capture-client.ts:1-31` currently says "Phase 4 work per the design §Q1 decision". Phase 3 rewrites this comment to reflect the Phase 3 wiring + the carve-out for Phase 4 fallback (R1 mitigation).
- **Audit trail**: `BiometricEnrollmentRecord.enrollment_strategy` enum (Phase 2A4) gains no new value in Phase 3 — the existing `"websdk"` value covers the real-capture path. (Phase 2A4 already listed `"websdk"` and `"electron"` as Phase 4 placeholders; "websdk" is now used in practice.)

---

## 10. References

- `openspec/changes/dp4500-host-app-integration-phase3-capture-client/proposal.md` — Q1 lock, in/out of scope, rollback plan.
- `openspec/changes/dp4500-host-app-integration-phase3-capture-client/explore.md` §5 — R1/R2/R3 risks, P1-P6 design patterns.
- `openspec/changes/dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md` — §"ADDED Capture Surface (Phase 3)" delta.
- `openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/design.md` — tone + structure reference; §6.2 signal handler pattern, §10.1 unit-test layering.
- `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts` — current Phase 2A4 surface (244 lines); header comment at lines 1-31 will be rewritten.
- `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts` — `handleConfirmCapture` at lines 701-865; carve-out boundary at lines 842-859.
- `frontend/aesthetic-clinic/public/fingerprint-probe.html` — Phase 1 probe evidence (lines 80-88 "Hallazgo del probe"); SDK loads from `/websdk/fingerprint.sdk.min.js`.
- `openspec/changes/archive/2026-07-29-add-digital-persona-4500-integration/design.md` §6 — the agent pattern, deferred to Phase 4 fallback.

---

## 11. Predecessor artifact chain

```
docs/plans/2026-09-27-biometric-web-integration.md
  ↓
C:\proyectos\DP4500 estandar\openspec\changes\dp4500-host-app-integration-phase1/
  ↓
openspec/changes/archive/2026-09-28-dp4500-host-app-integration-phase2/   (Phase 2A4 wire contract)
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/explore.md
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/proposal.md
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/specs/wizard-biometric-enrollment/spec.md
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/design.md   ← this file
  ↓
openspec/changes/dp4500-host-app-integration-phase3-capture-client/tasks.md   (next)
  ↓
apply → verify → archive
```

---

**Draft. Patterns A/B/C/D are concrete enough to serve as code templates for the apply phase. NO_AGENT fallback carved out at `useConversionWizard.ts:842-859`. Ready for tasks.md.**