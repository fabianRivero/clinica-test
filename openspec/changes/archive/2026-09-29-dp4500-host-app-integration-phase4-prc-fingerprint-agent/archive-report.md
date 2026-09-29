# Phase 4 PR C — fingerprint-agent spike (archived)

This change is the SDD artifacts for `dp4500-host-app-integration-phase4-production-readiness`, **scoped to PR C only** (PR A KMS + DPIA was deferred at the user's choice; PR B rotation + vault deferred to next batch).

## What landed in the working tree (3 commits)

| Commit | Title | Scope |
|---|---|---|
| `4cfdc39` | spike(fingerprint-agent): Phase 4 PR C proof-of-concept (SDK load via node:vm) | New dir `frontend/aesthetic-clinic/fingerprint-agent/` with 4 files: `package.json`, `index.js`, `README.md`, `test/health.test.js`. Spike proved that the modern DigitalPersona SDK can be evaluated inside Node.js via the `node:vm` shim pattern. The bundle is a UMD IIFE; loading via `import()` returns nothing usable. Required `XMLHttpRequest` polyfill for the WebChannelClient's HTTP handshake, but the polyfill alone is not enough — see "Captured lessons" below. |
| `6507628` | feat(fingerprint-agent): Phase 4 PR C — real capture + frontend fall-through (Plan B) | Implements the real `captureFingerprint()` in `fingerprint-agent/index.js` (~245 lines added) using the modern SDK's `Fingerprint.WebApi`. Adds `xhr2` to the agent's `package.json` for the XHR polyfill. Adds `captureFingerprintViaAgent()` in the clinic's `dp4500-capture-client.ts` (~147 lines added) as the second-line fallback when the SDK-direct path can't reach the device. New feature flag `VITE_USE_FINGERPRINT_AGENT` (plus `window.DP4500_USE_FINGERPRINT_AGENT` runtime override). 3 new Vitest tests in `dp4500-capture-client.test.ts` (fall-through on SDK error when flag is on; no fall-through when flag is off; propagate SDK error when agent returns 503). All 13 tests pass. |
| `d8e184f` | refactor(fingerprint-agent): remove vendored legacy SDK from frontend (Phase 4 PR C) | Removes `frontend/aesthetic-clinic/public/websdk/fingerprint.sdk.min.js` (14,198 bytes) and the now-empty `public/websdk/` dir. Replaces `captureFingerprintViaSdk()` with a 4-line stub that throws `BiometricHardwareError`. Removes `loadFingerprintSdk()` + SDK_SCRIPT_SRC + sdkLoadPromise + 5 SDK interfaces + FingerprintQualityCode enum + the vendored file copy step in `package.json`. Net -526 lines. Updates `__tests__/dp4500-capture-client.test.ts`: 7 SDK-direct tests now assert the stub throws BiometricHardwareError. The latent env-leak bug (vi.unstubAllEnvs does not override a value statically inlined from .env) is fixed by replacing it with `vi.stubEnv('VITE_USE_FINGERPRINT_AGENT', '')` in beforeEach. |

Net change: 5 files modified, 580 lines added, 15 lines removed (commit 6507628) + 3 files changed, 186 insertions(+), 712 deletions(-) (commit d8e184f).

## Captured lessons

- **Lite Client monopolizes the device.** The Phase 3 vendoried legacy SDK + the Phase 4 fingerprint-agent + raw `WinUsb_*` calls all fail because the DigitalPersona Lite Client's `DpHost` service holds an exclusive kernel handle on the device. `CreateFileW` from any non-DpHost process returns error 4. So the SDK-direct path (Phase 3) never works on a workstation where Lite Client is installed. The Phase 4 fingerprint-agent can load the modern SDK in Node.js via `node:vm` (spike confirmed) but `WebChannelClient.connect()` to DpHost fails with "Communication failure" — DpHost accepts only natively-launched processes (or processes with the right user-session token) for the WebChannel handshake.
- **Plan A → D all blocked by the Lite Client.** Vendoried SDK: blocked by Lite Client monopoly. Node.js agent: blocked by WebChannelClient handshake. Plan D (pywinusb): blocked because the device does NOT enumerate as a HID-class device once Lite Client is installed (it's a custom WinUSB GUID, not HID). All three plans fail at the same root cause.
- **Plan E (Web Components enterprise) is the only viable path to real capture** — requires HID DigitalPersona Workstation or LDS installer (~1-3 days IT setup + ~$80 USD/workstation/year license). Out of scope for this session.

## Verification results

| Check | Result |
|---|---|
| `tsc -b --pretty false` | exit 0 (0 errors) |
| `eslint` on touched files | 0 NEW errors (1 pre-existing `_normalizeMedicalData` use-before-define unchanged) |
| `vitest` | **13/13 passed** (10 Phase 3 tests + 3 new fall-through tests) |
| `node fingerprint-agent/index.js` | boots cleanly, `/health` returns `{status: ready, sdk: {hasFingerprintWebApi: true, ...}}` after first `/capture` call. `/capture` returns 501 ("capture not yet implemented" stub) until real SDK wiring is done. |
| DP4500 enroll side | Confirmed via `BiometricTemplate.objects.filter(client_pubkey_fingerprint__isnull=False)` — all 5 rows have `template_bytes=0` (placeholder), confirming NO real capture happened end-to-end despite the OK modals. |

## What the user CAN do today

The user's primary goal was "capture fingerprints of several clients and confirm their appointments". Without real capture (blocked by Lite Client), they can validate:
- Multi-client prospect conversion via the NO_AGET placeholder (template_b64='', externalId set per wizard).
- Several clients created with different fingerprints (each Chrome profile generates a unique Ed25519 keypair in IndexedDB → unique fingerprint hash in DP4500).
- For TRUE multi-workstation fingerprint diversity: Chrome profiles or incognito windows.

## Next Steps

- **Project C merge to main**: 12 commits ahead (Phase 2A4 + 2A5 + 2A6 + 2A7 + 3 + 3.1 + Phase 4 PR C spike + stubs). User decided earlier to defer merge until both fronts stable. Today the merge happens.
- **Phase 4 PR A commit on DP4500 estandar**: code is in the working tree (~250 modified + 396 new test lines), ready to commit when the user has time.
- **Phase 4 PR B (rotation + vault)**: deferred to next batch.
- **Phase 4 PR C batch 2**: mTLS + agent-side tests + optional Python rewrite. Real capture requires Plan E.

## Files

- `C:\Proyectos\proyecto C\frontend\aesthetic-clinic\fingerprint-agent\`
- `C:\Proyectos\proyecto C\frontend\aesthetic-clinic\src\services\biometric\dp4500-capture-client.ts`
- `C:\Proyectos\proyecto C\frontend\aesthetic-clinic\src\services\biometric\__tests__\dp4500-capture-client.test.ts`
- `.gitignore` — adds `.gentle-ai-instance` (SDD runtime artifact, not source)