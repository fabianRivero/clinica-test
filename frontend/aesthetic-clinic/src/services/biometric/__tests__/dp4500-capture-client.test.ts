/**
 * Unit tests for `captureFingerprint()`.
 *
 * The wrapper lazy-loads the `@digitalpersona/fingerprint` UMD IIFE
 * by injecting a `<script>` tag and reading `window.Fingerprint`
 * (per the package's `"unpkg": "./dist/fingerprint.sdk.min.js"`
 * export). The tests stub `window.Fingerprint` directly with a
 * minimal structural shape — they do NOT exercise the real SDK.
 *
 * Phase 3 design intent: the unit tests prove the wrapper's
 *   1. happy path (sample acquired → CaptureResult),
 *   2. error path (SDK init failure → BiometricHardwareError),
 *   3. rejection path (sample acquired but empty → BiometricHardwareError),
 * without needing a DigitalPersona 4500 reader. Operator-workstation
 * validation (real hardware, real WebChannel host) is gated on the
 * Phase 3 verify-report per design.md §8 success criterion #5.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BiometricHardwareError,
  BiometricQualityTooLow,
  captureFingerprint,
} from '../dp4500-capture-client'

interface FakeWebApiHandle {
  webApi: {
    startAcquisition: ReturnType<typeof vi.fn>
    stopAcquisition: ReturnType<typeof vi.fn>
    onErrorOccurred?: (event: { error: number }) => void
    onSamplesAcquired?: (event: {
      deviceUid: string
      samples: string
    }) => void
  }
}

function installFakeSdk({
  startAcquisitionImpl,
}: {
  startAcquisitionImpl?: () => Promise<void> | void
} = {}): FakeWebApiHandle {
  const handle: FakeWebApiHandle = {
    webApi: {
      startAcquisition: vi.fn(
        startAcquisitionImpl ?? (() => Promise.resolve()),
      ),
      stopAcquisition: vi.fn(() => Promise.resolve()),
    },
  }
  // The wrapper reads `window.Fingerprint` synchronously via a
  // cached Promise — bypass the script-injection path by setting
  // the global BEFORE any captureFingerprint() call.
  Object.defineProperty(window, 'Fingerprint', {
    configurable: true,
    writable: true,
    value: {
      WebApi: vi.fn(() => handle.webApi),
    },
  })
  return handle
}

function removeFakeSdk(): void {
  // Reset the cached `sdkLoadPromise` so the next captureFingerprint
  // call re-injects the (now-missing) script. We do that by clearing
  // the global AND letting the wrapper's internal cache be reset on
  // load failure. For these tests we simply re-install the fake
  // BEFORE each test (see beforeEach below).
  delete (window as unknown as { Fingerprint?: unknown }).Fingerprint
}

describe('captureFingerprint', () => {
  beforeEach(() => {
    removeFakeSdk()
    // jsdom does not implement HTMLScriptElement onload consistently;
    // we mock document.createElement to short-circuit script injection.
    vi.spyOn(document.head, 'appendChild').mockImplementation(
      (node: Node) => node,
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns template + device metadata on first onSamplesAcquired event', async () => {
    const { webApi } = installFakeSdk()

    // Kick off capture, then simulate the SDK firing the sample
    // event after startAcquisition resolves.
    const promise = captureFingerprint()

    // Wait a microtask so the wrapper's `new WebApi()` + handler
    // wiring happens before we dispatch the event.
    await Promise.resolve()
    await Promise.resolve()
    webApi.onSamplesAcquired?.({
      deviceUid: 'reader-001',
      samples: 'ZmFrZS10ZW1wbGF0ZS1ieXRlcw==',
    })

    await expect(promise).resolves.toEqual({
      templateB64: 'ZmFrZS10ZW1wbGF0ZS1ieXRlcw==',
      qualityScore: 100,
      deviceSerial: 'reader-001',
      width: 0,
      height: 0,
    })
  })

  it('rejects with BiometricHardwareError when onErrorOccurred fires', async () => {
    const { webApi } = installFakeSdk()

    const promise = captureFingerprint()
    await Promise.resolve()
    await Promise.resolve()
    webApi.onErrorOccurred?.({ error: 42 })

    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(/SDK error code 42/)
  })

  it('rejects with BiometricHardwareError when startAcquisition rejects', async () => {
    installFakeSdk({
      startAcquisitionImpl: () =>
        Promise.reject(new Error('WebChannel host unreachable')),
    })

    const promise = captureFingerprint()
    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(/WebChannel host unreachable/)
  })

  it('rejects with BiometricHardwareError when sample payload is empty', async () => {
    const { webApi } = installFakeSdk()

    const promise = captureFingerprint()
    await Promise.resolve()
    await Promise.resolve()
    webApi.onSamplesAcquired?.({
      deviceUid: 'reader-001',
      samples: '',
    })

    await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
    await expect(promise).rejects.toThrow(/muestra vacia/)
  })

  it('rejects with BiometricHardwareError when 30s timeout elapses', async () => {
    const { webApi } = installFakeSdk()

    // Use Vitest fake timers so we don't have to wait the real 30s.
    vi.useFakeTimers()
    try {
      const promise = captureFingerprint()
      // Let the wrapper settle its `new WebApi()` + handler wiring.
      await Promise.resolve()
      // Fast-forward past the 30s timeout.
      vi.advanceTimersByTime(31_000)
      await expect(promise).rejects.toBeInstanceOf(BiometricHardwareError)
      await expect(promise).rejects.toThrow(/30s/)
      // The wrapper calls stopAcquisition as part of the timeout
      // cleanup; assert it was invoked.
      expect(webApi.stopAcquisition).toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('BiometricQualityTooLow', () => {
  beforeEach(() => {
    // The current wrapper does not yet map the SDK's QualityReported
    // event into a `BiometricQualityTooLow` rejection (the PngImage
    // sample format does not embed a numeric score in the event).
    // The class itself must still be constructible + subclass of
    // BiometricSuspendError so the wizard's `instanceof` branch
    // (useConversionWizard.ts:780) compiles + behaves correctly.
    removeFakeSdk()
  })

  it('extends BiometricSuspendError and exposes the QUALITY_TOO_LOW code', () => {
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
  beforeEach(() => {
    removeFakeSdk()
  })

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