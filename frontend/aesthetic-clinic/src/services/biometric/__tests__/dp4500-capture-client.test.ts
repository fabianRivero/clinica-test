/**
 * Unit tests for `captureFingerprint()`.
 *
 * Phase 4 PR C: the browser-direct Web SDK path is now a permanent
 * stub (`captureFingerprintViaSdk()` throws `BiometricHardwareError`
 * on every call). The `fingerprint-agent` HTTP service is the
 * default capture path on real workstations; the Phase 2A4
 * NO_AGENT placeholder flow at `useConversionWizard.ts:842-859` is
 * the terminal fallback when the agent is also unreachable.
 *
 * These tests cover:
 *   1. The SDK-direct stub throws the documented
 *      `BiometricHardwareError` (8 tests — 7 SDK-direct variants +
 *      the BiometricQualityTooLow class shape).
 *   2. The Phase 2A4 NO_AGENT contract still holds when the agent
 *      feature flag is OFF (1 test).
 *   3. The agent fall-through when the flag is ON (2 tests:
 *      successful capture, agent 503 → propagate SDK error).
 *
 * `fetch` is mocked with `vi.fn()` so the agent tests run without
 * a real agent service. The SDK-direct tests do not need any
 * window/global stubbing because the stub does not read the SDK
 * global — it throws synchronously before any browser SDK would
 * have been consulted.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BiometricHardwareError,
  BiometricQualityTooLow,
  captureFingerprint,
} from '../dp4500-capture-client'

// Canonical message the SDK-direct stub throws. Every SDK-direct
// test below asserts on this exact string (or the looser substring
// "SDK path disabled") so a future re-enable of the SDK-direct
// path is forced to update tests in lockstep.
const SDK_STUB_MESSAGE =
  'SDK path disabled (Phase 4 PR C — fingerprint-agent is the default).'

describe('captureFingerprint (Phase 4 PR C — SDK-direct stub)', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") on the happy-path call site', async () => {
    // The Phase 3 happy-path test exercised the SDK's
    // onSamplesAcquired + onQualityReported handshake. With the
    // SDK-direct path stubbed, the call rejects before any SDK
    // surface is touched.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") on the SDK error path', async () => {
    // Mirrors the Phase 3 "onErrorOccurred fires" test — the
    // stub now short-circuits that event before any handler wiring.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") when startAcquisition would have rejected', async () => {
    // Mirrors the Phase 3 "startAcquisition rejects" test.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") when the sample payload would have been empty', async () => {
    // Mirrors the Phase 3 "empty samples" test.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") instead of timing out after 30s', async () => {
    // Mirrors the Phase 3 30s timeout test. With the stub there
    // is no timeout — the rejection is synchronous on the next
    // microtask. We deliberately do NOT use fake timers here so
    // any regression that re-enables a 30s wait would surface as
    // a slow test rather than a silent timeout-resolved pass.
    const start = Date.now()
    await expect(captureFingerprint()).rejects.toBeInstanceOf(
      BiometricHardwareError,
    )
    await expect(captureFingerprint()).rejects.toThrow(SDK_STUB_MESSAGE)
    expect(Date.now() - start).toBeLessThan(1_000)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") when onQualityReported would have fired with non-Good quality', async () => {
    // Mirrors the Phase 3 "non-Good quality" test. The stub
    // rejects before the SDK handshake would have run.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })

  it('rejects with BiometricHardwareError("SDK path disabled ...") instead of accepting the stashed sample', async () => {
    // Mirrors the Phase 3 "stashed sample + Good quality" test.
    // The stub rejects before the SDK sample/quality handshake
    // would have completed.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)
  })
})

describe('BiometricQualityTooLow', () => {
  it('extends BiometricSuspendError and exposes the QUALITY_TOO_LOW code', () => {
    // The SDK-direct path is stubbed, but the BiometricQualityTooLow
    // class remains in the contract surface for the agent and for
    // any future SDK-direct re-enablement. The wizard's
    // `instanceof` branch (useConversionWizard.ts:780) compiles +
    // behaves correctly as long as the class shape is preserved.
    const err = new BiometricQualityTooLow()
    expect(err).toBeInstanceOf(BiometricQualityTooLow)
    expect((err as unknown as { code: string }).code).toBe(
      'DP4500_QUALITY_TOO_LOW',
    )
    expect(err.name).toBe('BiometricQualityTooLow')
    expect(err.message).toBe('La calidad de la captura es insuficiente.')
  })
})

describe('BiometricHardwareError', () => {
  it('extends BiometricSuspendError and exposes the HARDWARE code', () => {
    const err = new BiometricHardwareError('SDK timeout')
    expect(err).toBeInstanceOf(BiometricHardwareError)
    expect((err as unknown as { code: string }).code).toBe('DP4500_HARDWARE')
    expect(err.name).toBe('BiometricHardwareError')
    expect(err.message).toBe('SDK timeout')
  })

  it('defaults to the Spanish hardware-unavailable message', () => {
    const err = new BiometricHardwareError()
    expect(err.message).toBe('Hardware no disponible o SDK no inicializo.')
  })
})

/**
 * Phase 4 PR C — fingerprint-agent fall-through tests.
 *
 * The agent is the third capture path that sits BETWEEN the
 * (stubbed) SDK-direct path and the Phase 2A4 NO_AGENT terminal
 * fallback at `useConversionWizard.ts:842-859`. The wrapper
 * (`captureFingerprint()`) calls `captureFingerprintViaSdk()`
 * first; the stub throws `BiometricHardwareError('SDK path
 * disabled ...')` on every call. The wrapper then consults the
 * agent feature flag (`VITE_USE_FINGERPRINT_AGENT` or
 * `window.DP4500_USE_FINGERPRINT_AGENT`). If the flag is OFF,
 * the stub's error propagates and the wizard takes the NO_AGENT
 * branch. If the flag is ON, the wrapper calls the local
 * `fingerprint-agent` HTTP service
 * (`http://127.0.0.1:8765/capture`) and maps its response into
 * `CaptureFingerprintResult`.
 *
 * `fetch` is mocked with `vi.fn()` so these tests run without a
 * real agent service.
 */
describe('captureFingerprint (Phase 4 PR C — fingerprint-agent fall-through)', () => {
  let fetchSpy: ReturnType<typeof vi.fn>

  beforeEach(() => {
    // The agent feature flag must be explicitly unset between
    // tests so a previous test's stubEnv does not leak. We force
    // the env var to empty string (not just unstubAllEnvs) so the
    // local `.env` setting `VITE_USE_FINGERPRINT_AGENT=true` does
    // not bleed into the OFF-flag tests. `import.meta.env.X` is
    // statically inlined from `process.env.X` + the Vite `.env`
    // files at transform time, so vi.unstubAllEnvs alone is not
    // enough to override a value baked into the source.
    vi.stubEnv('VITE_USE_FINGERPRINT_AGENT', '')
    delete (window as unknown as { DP4500_USE_FINGERPRINT_AGENT?: boolean })
      .DP4500_USE_FINGERPRINT_AGENT
    fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    delete (window as unknown as { DP4500_USE_FINGERPRINT_AGENT?: boolean })
      .DP4500_USE_FINGERPRINT_AGENT
  })

  it('falls through to fingerprint-agent on the SDK stub error when the flag is on', async () => {
    // The SDK-direct stub throws "SDK path disabled ..." on every
    // call — that's the canonical Phase 4 PR C trigger for agent
    // fall-through. The agent responds with a valid capture and
    // the wrapper must map its shape ({templateB64, qualityScore,
    // deviceSerial, width, height}) into CaptureFingerprintResult.
    vi.stubEnv('VITE_USE_FINGERPRINT_AGENT', 'true')

    fetchSpy.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          templateB64: 'YWdlbnQtdGVtcGxhdGU=',
          qualityScore: 0,
          deviceSerial: '05ba-000a',
          width: 0,
          height: 0,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )

    const result = await captureFingerprint()

    expect(result).toEqual({
      templateB64: 'YWdlbnQtdGVtcGxhdGU=',
      qualityScore: 0,
      deviceSerial: '05ba-000a',
      width: 0,
      height: 0,
    })
    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/capture',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('does NOT fall through to the agent when the feature flag is off', async () => {
    // Feature flag OFF — env var absent, window flag absent.
    // vi.unstubAllEnvs() in beforeEach already cleared the env.
    // The SDK-direct stub's BiometricHardwareError surfaces
    // directly so the wizard's NO_AGENT terminal fallback at
    // useConversionWizard.ts:842-859 activates. The agent must
    // NOT be called.
    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('propagates the SDK stub error when the agent returns 503 (NO_AGENT terminal fallback)', async () => {
    // Both paths fail: SDK-direct stub throws AND the agent
    // responds with 503 (no reader). The wrapper must surface
    // the ORIGINAL SDK stub error so the wizard's NO_AGENT path
    // at useConversionWizard.ts:842-859 activates with a
    // recognizable BiometricHardwareError rather than a fetch
    // TypeError.
    vi.stubEnv('VITE_USE_FINGERPRINT_AGENT', 'true')

    fetchSpy.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'no reader enumerated' }), {
        status: 503,
      }),
    )

    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(SDK_STUB_MESSAGE)

    expect(fetchSpy).toHaveBeenCalledTimes(1)
    expect(fetchSpy).toHaveBeenCalledWith(
      'http://127.0.0.1:8765/capture',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
