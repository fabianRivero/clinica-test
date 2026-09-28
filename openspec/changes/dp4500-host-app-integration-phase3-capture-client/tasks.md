# Tasks: Real capture client wiring (Phase 3 of dp4500-host-app-integration-phase2)

**Change name**: `dp4500-host-app-integration-phase3-capture-client`
**Artifact store**: openspec
**Delivery strategy**: `ask-on-risk`
**Predecessors**: proposal.md + design.md + specs/wizard-biometric-enrollment/spec.md (locked)

---

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~250 (range 150-400). Frontend code + tests + docs. |
| 400-line budget risk | None — well within range. |
| Chained PRs recommended | No — single PR acceptable. |
| Suggested commit split | One commit (or 2 if SDK install needs to land separately). |
| Delivery strategy | ask-on-risk |
| Chain strategy | n/a (single PR) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a (single PR)
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely commit | Focused test command | Runtime harness | Rollback boundary |
|------|------|--------------|----------------------|------------------|-------------------|
| WU-1 | Vendorize `@digitalpersona/fingerprint` + `@digitalpersona/websdk` in `package.json`; run `npm install` to materialize `node_modules/` + update `package-lock.json`. | Commit 1 | `npx tsc -b --pretty false` exits 0 | `npm ls @digitalpersona/fingerprint @digitalpersona/websdk` shows both resolved under `^1.0.0` | Remove the deps from `package.json`, `npm install`, revert `package-lock.json`; no production code touched |
| WU-2 | Add `captureFingerprint()` wrapper + typed errors to `dp4500-capture-client.ts` (Pattern A dynamic import, Pattern B exception class). | Commit 1 | `npx vitest run src/services/biometric/__tests__/dp4500-capture-client.test.ts` | `vi.mock('@digitalpersona/fingerprint', ...)` stub; SDK never reaches a real reader | Revert the new function + class; `enrollIdentity` / `challengeIdentity` / `verifyIdentity` exports still work |
| WU-3 | Wire `captureFingerprint()` into `useConversionWizard.handleConfirmCapture` with NO_AGENT fallback preserved verbatim. | Commit 1 | `npx tsc -b --pretty false && npx eslint src/pages/admin/prospect-convert/useConversionWizard.ts` | Vite dev server + manual wizard run on a workstation WITHOUT hardware (NO_AGENT path) | Revert the `enrollDp4500` closure body at lines 753-768; the placeholder `''` flow returns |
| WU-4 | Document hardware + SDK + env requirements in `HOW_TO_RUN.md`. | Commit 2 | `git diff --stat frontend/aesthetic-clinic/HOW_TO_RUN.md` shows only the new "Phase 3 setup" section appended | Markdown preview render (operator workstation) | Delete the file (or revert the append) |

---

## Phase 3: Real capture client (Commits 1 + 2)

### 1.1 Vendorize SDKs (Commit 1)

- [x] 1.1.1 Add `@digitalpersona/fingerprint` and `@digitalpersona/websdk` to `frontend/aesthetic-clinic/package.json` dependencies (match the latest stable version per npm registry).
- [x] 1.1.2 Run `cd frontend/aesthetic-clinic && npm install` to materialize `node_modules/` and update `package-lock.json`.
- [x] 1.1.3 Verify `tsc -b --pretty false` still exits 0 (vendorization alone should not break the build).

### 1.2 Add `captureFingerprint()` wrapper (Commit 1)

- [x] 1.2.1 RED `frontend/aesthetic-clinic/src/services/biometric/dp4500-capture-client.ts`: define new types — `CaptureResult { templateB64: string; qualityScore: number; deviceSerial: string; width: number; height: number; }`, exception class `BiometricHardwareError extends BiometricSuspendError`, `BiometricQualityTooLow extends BiometricSuspendError`. Cite `design.md §6 Pattern B` for the exception class shape.

- [x] 1.2.2 GREEN `dp4500-capture-client.ts`: implement `async function captureFingerprint(): Promise<CaptureResult>` using `await import('@digitalpersona/fingerprint')` (Pattern A — dynamic import). The function initializes a `WebSdk.WebChannelClient`, calls `client.getDeviceList()`, picks the first device, calls `device.AcquireFingerprint(FingerIndex.Any, ...)` in a polling loop, returns a `CaptureResult`. Throws `BiometricHardwareError` on SDK init failure. Throws `BiometricQualityTooLow` if `qualityScore < 60`. Cite `design.md §6 Pattern A/C` for the chunk strategy.

- [x] 1.2.3 RED `frontend/aesthetic-clinic/src/services/biometric/__tests__/dp4500-capture-client.test.ts` (NEW): mock the SDK with `vi.mock('@digitalpersona/fingerprint', ...)`. Test 1: `captureFingerprint returns template + quality on happy path`. Test 2: `captureFingerprint throws BiometricHardwareError on SDK init failure`. Test 3: `captureFingerprint throws BiometricQualityTooLow when quality < 60`.

- [x] 1.2.4 GREEN: confirm unit tests pass. Cite `design.md §5 Test Surface` for the file path.

### 1.3 Wire `captureFingerprint()` into the wizard (Commit 1)

- [x] 1.3.1 RED `frontend/aesthetic-clinic/src/pages/admin/prospect-convert/useConversionWizard.ts`: in `handleConfirmCapture` (lines 700-870), BEFORE the `enrollDp4500` closure call site at line 753-768, add a `captureFingerprint()` call wrapped in try/catch. If `captureFingerprint()` succeeds, pass the real `templateB64` to `enrollIdentity`. If it throws `BiometricHardwareError` or `BiometricQualityTooLow`, fall through to the NO_AGENT path. Cite `design.md §6 Pattern D` for the wire-in point.

- [x] 1.3.2 GREEN: confirm `npx tsc -b --pretty false` exits 0 and `npx eslint src/pages/admin/prospect-convert/useConversionWizard.ts` exits 0 with 0 NEW errors.

### 1.4 Commit wrap-up (Commit 1)

- [x] 1.4.1 `npx tsc -b --pretty false` exits 0.
- [x] 1.4.2 `npx eslint src/services/biometric/dp4500-capture-client.ts src/pages/admin/prospect-convert/useConversionWizard.ts` exits 0 with 0 NEW errors. *(Pre-existing `_normalizeMedicalData` error in `useConversionWizard.ts:280` carried over from Phase 2A4 baseline — same error count as `HEAD~1`.)*
- [x] 1.4.3 `npx vitest run src/services/biometric/__tests__/dp4500-capture-client.test.ts` (or `npm test`) passes.
- [ ] 1.4.4 Commit `feat(biometric): wire real fingerprint capture via vendorized DigitalPersona Web SDK (Phase 3)`. *(Deferred per orchestrator instruction "Do NOT commit unless explicitly asked".)*

**End of Commit 1.**

### 1.5 Documentation (Commit 2)

- [x] 1.5.1 RED `frontend/aesthetic-clinic/HOW_TO_RUN.md` (existing file from Phase 2A5): add a "Phase 3 setup" section explaining: (a) operator workstation requirements (DP4500 reader connected via USB + HID Authentication Device Client running), (b) browser permissions (WebUSB / WebChannel access), (c) how to verify the SDK is loaded (`window.WebSdk` in devtools), (d) fallback to NO_AGENT path when hardware is missing.
- [x] 1.5.2 GREEN: confirm docs render correctly in markdown preview.

### 1.6 Commit wrap-up (Commit 2)

- [x] 1.6.1 Docs render correctly.
- [ ] 1.6.2 Commit `docs(setup): add Phase 3 capture client setup notes to HOW_TO_RUN.md`. *(Deferred per orchestrator instruction "Do NOT commit unless explicitly asked".)*

**End of Commit 2.**

---

## Pre-apply (verify phase)

- [ ] Unit tests pass without hardware (mock SDK).
- [ ] Phase 2A4 NO_AGENT fallback at `useConversionWizard.ts:842-859` preserved verbatim.
- [ ] Phase 2A5 challenge/verify paths unchanged.
- [ ] No new lint errors introduced.

## Post-apply (archive phase)

- [ ] Write `archive-report.md` for Phase 3 at `openspec/changes/dp4500-host-app-integration-phase3-capture-client/archive-report.md` covering the 1-2 commits, the Q1 decision, the 4 new spec scenarios, and the test counts.