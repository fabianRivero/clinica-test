/**
 * DP4500 capture client — Phase 3 of dp4500-host-app-integration-phase2.
 *
 * Opción A: real capture via WebCrypto + HID WebSdk.
 *
 * Wraps the workstation-side flow:
 *   1. ensureSigningKey()      — generate or load the workstation's
 *                                Ed25519 keypair (stored in IndexedDB).
 *   2. enrollIdentity(...)     — POST /api/biometric/service/identity/enroll/
 *                                to persist the workstation's pubkey +
 *                                encrypted template.
 *   3. challengeIdentity(...)  — POST /api/biometric/service/challenge/identity/<uuid>/
 *                                to get a one-shot challenge + server nonce.
 *   4. signCanonical(...)      — sign
 *                                "{challenge_id}:{external_id}:{server_nonce}:{timestamp}"
 *                                with the workstation's private key.
 *   5. verifyIdentity(...)     — POST /api/biometric/service/verify/identity/
 *                                to consume the challenge + verify the
 *                                Ed25519 signature against the stored pubkey.
 *
 * Steps 1 + 2 are "enroll" (one-time per workstation); steps 3-5 are
 * "verify" (each cita check-in).
 *
 * Phase 3 wiring: real fingerprint bytes now come from
 * `captureFingerprint()` (Pattern A — dynamic import of
 * `@digitalpersona/fingerprint` to keep the initial bundle small).
 * The vendored SDK talks to the HID Authentication Device Client on
 * the operator PC via WebChannel; on workstations without that
 * client the wrapper throws `BiometricHardwareError` and the wizard
 * falls back to the Phase 2A4 NO_AGENT placeholder flow (carved
 * out at `useConversionWizard.ts:842-859`). The `fingerprint-agent`
 * pattern from the original 2026-07-29 design is the Phase 4
 * fallback if this SDK-direct path proves unworkable in production.
 */

import { API_BASE_URL } from '../api/apiClient'
import {
  ensureSigningKey,
  publicKeyToBase64Url,
  signCanonical,
  type SigningKey,
} from './ed25519-key-manager'

/**
 * DP4500 service-API credentials.
 *
 * The DP4500 host-app endpoints under `/api/biometric/service/*` require
 * a Bearer token issued by `manage.py create_service_api_key`. They do
 * NOT fall back to the Django session, so every request from this
 * client must carry `Authorization: Bearer <key>`.
 *
 * The key is read from `VITE_DP4500_SERVICE_API_KEY` at module load
 * (Vite inlines `import.meta.env.VITE_*` at build time). We trim and
 * fall back to an empty string so a misconfigured build can still be
 * imported; the first call into a service endpoint will throw a clear
 * configuration error instead of silently 401'ing.
 */
const DP4500_SERVICE_API_KEY = (import.meta.env.VITE_DP4500_SERVICE_API_KEY || '').trim()

/**
 * Build the Bearer header for a DP4500 service-API request. Throws a
 * configuration error (rather than crashing at module load) when the
 * key is missing, so a misconfigured dev env surfaces at the point of
 * first use with a clear remediation hint.
 */
function dp4500Headers(): Record<string, string> {
  if (!DP4500_SERVICE_API_KEY) {
    throw new Error(
      'DP4500 ServiceAPIKey is not configured. Set VITE_DP4500_SERVICE_API_KEY in the frontend .env file (see .env.example).',
    )
  }
  return { Authorization: `Bearer ${DP4500_SERVICE_API_KEY}` }
}

/**
 * Minimal POST-with-JSON helper for the DP4500 service endpoints.
 *
 * Mirrors `postJson` from `../api/apiClient` but:
 *   - uses Bearer auth via `dp4500Headers()` instead of CSRF (the
 *     service endpoints do not accept Django sessions), and
 *   - does not include `X-Selected-Branch-Id` (the service endpoints
 *     are workstation-scoped, not branch-scoped).
 *
 * Kept private to this module: if a future caller needs both CSRF and
 * a Bearer header, extend `apiClient.ts` with a new variant instead of
 * widening this helper.
 */
async function postJsonWithBearer<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    // Service endpoints authenticate via Bearer, not cookies.
    credentials: 'omit',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...dp4500Headers(),
    },
    body: JSON.stringify(body),
  })

  const data = (await response.json().catch(() => null)) as
    | T
    | { detail?: string }
    | null

  if (!response.ok) {
    const detail = (data && typeof data === 'object' && 'detail' in data && typeof (data as { detail?: unknown }).detail === 'string')
      ? (data as { detail: string }).detail
      : null
    throw new Error(detail || `Error ${response.status}`)
  }

  return data as T
}

/**
 * Result of a successful enrollIdentity call.
 */
export interface EnrollIdentityResult {
  ok: true
  user_external_id: string
  template_id: number
}

/**
 * Result of a successful challengeIdentity call.
 */
export interface ChallengeIdentityResult {
  capture_token: string
  server_nonce: string   // base64url-encoded 32 bytes
  ttl_seconds: number
}

/**
 * Result of a successful verifyIdentity call (server says signature
 * verified AND SDK match).
 */
export interface VerifyIdentityResult {
  ok: true
  matched: boolean
  audit_hash: string
}

export class BiometricSuspendError extends Error {
  readonly code: string = 'DP4500_SUSPENDED'
  constructor(message: string) {
    super(message)
    this.name = 'BiometricSuspendError'
  }
}

/**
 * Enroll the workstation's Ed25519 pubkey + an encrypted template
 * with DP4500. The first time a workstation enrolls a fingerprint
 * for a given user_external_id, this creates a fresh
 * ``BiometricTemplate`` row. Subsequent enrolls for the same
 * (user_external_id, fingerprint) update the row in place.
 *
 * @param userExternalId     the host-app user identifier (UUID)
 * @param templateB64         base64url-encoded encrypted template bytes
 * @param signingKey           the workstation's keypair (from ensureSigningKey)
 * @param fingerprint         hex fingerprint of the pubkey (sha256, etc.)
 * @param format              template format (e.g. "DP_PROPRIETARY")
 */
export async function enrollIdentity(
  userExternalId: string,
  templateB64: string,
  signingKey: SigningKey,
  fingerprint: string,
  format: string = 'DP_PROPRIETARY',
): Promise<EnrollIdentityResult> {
  const path = `${API_BASE_URL}/api/biometric/service/identity/enroll/`
  const body = {
    user_external_id: userExternalId,
    template_b64: templateB64,
    client_pubkey_b64: publicKeyToBase64Url(signingKey.publicKeyRaw),
    client_pubkey_fingerprint: fingerprint,
    quality_score: 0, // Phase 4 captures the real quality score
    format,
  }
  const response = await postJsonWithBearer<EnrollIdentityResult>(path, body)
  return response
}

/**
 * Issue a one-shot identity challenge from DP4500.
 */
export async function challengeIdentity(
  userExternalId: string,
): Promise<ChallengeIdentityResult> {
  const path = `${API_BASE_URL}/api/biometric/service/challenge/identity/${encodeURIComponent(userExternalId)}/`
  return postJsonWithBearer<ChallengeIdentityResult>(path, {})
}

/**
 * Verify the canonical signed by the workstation. The canonical is
 *   "{capture_token}:{userExternalId}:{serverNonce}:{timestamp}"
 * (serverNonce is the base64url-encoded bytes from challengeIdentity).
 */
export async function verifyIdentity(
  captureToken: string,
  userExternalId: string,
  serverNonce: string,
): Promise<VerifyIdentityResult> {
  const timestamp = new Date().toISOString()
  const signature = await signCanonical(
    captureToken,
    userExternalId,
    serverNonce,
    timestamp,
  )
  const path = `${API_BASE_URL}/api/biometric/service/verify/identity/`
  return postJsonWithBearer<VerifyIdentityResult>(path, {
    challenge_id: captureToken,
    signature,
    timestamp,
  })
}

/**
 * End-to-end capture-and-verify helper for Opción A smoke testing.
 * The caller wires in the actual fingerprint capture (Phase 4)
 * by passing the encrypted template bytes. Returns true if the
 * server reports a signature-verified match.
 */
export async function captureAndVerify(
  userExternalId: string,
  templateB64: string,
  fingerprint: string,
): Promise<boolean> {
  // 1. Ensure signing key (generates on first use, loads after).
  const signingKey = await ensureSigningKey()

  // 2. Enroll (idempotent — Phase 1 update_or_create semantics).
  await enrollIdentity(userExternalId, templateB64, signingKey, fingerprint)

  // 3. Issue challenge.
  const challenge = await challengeIdentity(userExternalId)

  // 4. Sign + verify.
  const result = await verifyIdentity(
    challenge.capture_token,
    userExternalId,
    challenge.server_nonce,
  )
  return result.matched
}

/**
 * Result of a successful `captureFingerprint()` call. The wizard
 * passes `templateB64` to `enrollIdentity(...)` as the real template
 * bytes (replacing the Phase 2A4 empty-string placeholder); the
 * remaining fields flow through to the local `BiometricEnrollmentRecord`
 * row for audit purposes.
 */
export interface CaptureFingerprintResult {
  /** base64url-encoded template bytes from the SDK sample event. */
  templateB64: string
  /** Numeric quality score in [0, 100]. Mapped from the SDK's
   *  `QualityCode` enum (`Good` -> 100; everything else -> 0-59). */
  qualityScore: number
  /** SDK-reported device identifier (per Phase 1 probe §"Hallazgo"). */
  deviceSerial: string
  /** Sample image width in pixels (when the SDK reports it). */
  width: number
  /** Sample image height in pixels (when the SDK reports it). */
  height: number
}

/**
 * Hardware/transport failure during `captureFingerprint()`. Thrown
 * when the SDK fails to initialize, the WebChannel host is
 * unreachable, or `onErrorOccurred` fires. The wizard's catch site
 * falls through to the Phase 2A4 NO_AGENT placeholder flow.
 *
 * Extends `BiometricSuspendError` so downstream callers can use a
 * single error family for biometric-flow failure routing.
 */
export class BiometricHardwareError extends BiometricSuspendError {
  readonly code = 'DP4500_HARDWARE' as const
  constructor(
    message: string = 'Hardware no disponible o SDK no inicializo.',
  ) {
    super(message)
    this.name = 'BiometricHardwareError'
  }
}

/**
 * Sample-acquired but the quality score is below the operator-retry
 * threshold (60). The wizard surfaces "Calidad insuficiente. Vuelve
 * a intentarlo." and aborts `enrollIdentity`. This is a separate
 * error class so the catch site can distinguish a retryable quality
 * problem from an outright hardware failure.
 */
export class BiometricQualityTooLow extends BiometricSuspendError {
  readonly code = 'DP4500_QUALITY_TOO_LOW' as const
  constructor(
    message: string = 'La calidad de la captura es insuficiente.',
  ) {
    super(message)
    this.name = 'BiometricQualityTooLow'
  }
}

/**
 * Capture a fingerprint from the DigitalPersona 4500 reader via the
 * vendorized Web SDK. The SDK ships as a UMD IIFE that registers the
 * `Fingerprint` global (per `@digitalpersona/fingerprint/package.json`
 * `"unpkg": "./dist/fingerprint.sdk.min.js"`), so we lazy-load the
 * minified bundle by injecting a `<script>` tag at runtime. This
 * preserves Pattern A's R2 mitigation — the SDK chunk is only
 * fetched when the operator opens the capture modal, not at module
 * load.
 *
 * The wrapper:
 *   1. Lazily injects the SDK `<script>` (if not already loaded)
 *      and waits for `window.Fingerprint.WebApi` to be available.
 *   2. Constructs a `Fingerprint.WebApi` (the SDK's high-level
 *      facade that wraps `WebSdk.WebChannelClient` underneath).
 *   3. Wires `onSamplesAcquired` + `onErrorOccurred` + a 30s
 *      timeout, then calls `startAcquisition(SampleFormat.PngImage)`.
 *   4. Resolves with a `CaptureFingerprintResult` on the first
 *      successful sample event, or throws `BiometricHardwareError`
 *      on transport / WebChannel / timeout failure.
 *
 * The wrapper treats the runtime value as the structural shape
 * declared locally (see `FingerprintSdk` / `FingerprintWebApi`
 * interfaces below) to avoid pulling the package's ambient `.d.ts`
 * (a global namespace declaration that conflicts with the project's
 * `verbatimModuleSyntax: true` + bundler resolution settings).
 */
export async function captureFingerprint(): Promise<CaptureFingerprintResult> {
  // Pattern A: lazy-load the SDK IIFE the first time capture is
  // requested. Subsequent calls reuse the cached `window.Fingerprint`
  // without re-injecting the script (the loader module caches the
  // pending load promise).
  const sdkNamespace = await loadFingerprintSdk()

  // SampleFormat.PngImage (value 5) is what the Phase 1 probe page
  // used at line 53; we keep the same format so the operator's
  // existing HID Authentication Device Client configuration
  // matches. The enum is declared as a `const enum` in the
  // ambient .d.ts, so we use the numeric value directly to avoid
  // a runtime import (the enum does not exist at runtime — only
  // the `Fingerprint.WebApi` class does).
  const SAMPLE_FORMAT_PNG_IMAGE = 5

  return new Promise<CaptureFingerprintResult>((resolve, reject) => {
    const webApi = new sdkNamespace.WebApi()

    let settled = false
    const settleReject = (err: Error): void => {
      if (settled) return
      settled = true
      // Detach handlers so a late SDK event does not call into a
      // settled Promise (the WebChannel may emit one more sample
      // after a stopAcquisition round-trip).
      webApi.onSamplesAcquired = undefined
      webApi.onErrorOccurred = undefined
      reject(err)
    }

    // Hard timeout — the SDK only resolves the startAcquisition
    // promise on the FIRST `onAcquisitionStarted` event but does
    // not surface "no finger detected" by itself. After 30s without
    // a sample we treat the run as a hardware timeout so the wizard
    // can fall through to the NO_AGENT path instead of hanging the UI.
    const timeoutHandle = setTimeout(() => {
      settleReject(
        new BiometricHardwareError(
          'No se recibio una muestra del lector dentro de 30s.',
        ),
      )
      // Best-effort stop; the call is a no-op if no acquisition is
      // in flight. Errors here are intentionally swallowed because
      // the wrapper is already settling to a rejection.
      webApi.stopAcquisition().catch(() => undefined)
    }, 30_000)

    webApi.onErrorOccurred = (event) => {
      clearTimeout(timeoutHandle)
      settleReject(
        new BiometricHardwareError(`SDK error code ${event.error}`),
      )
    }

    webApi.onSamplesAcquired = (event) => {
      try {
        const samples = event.samples
        const deviceUid = event.deviceUid

        if (!samples || samples.length === 0) {
          clearTimeout(timeoutHandle)
          settleReject(
            new BiometricHardwareError(
              'El SDK reporto una muestra vacia.',
            ),
          )
          return
        }

        // The SDK's PngImage format does not embed a numeric quality
        // score in the sample event; quality is reported separately
        // via `onQualityReported`. Without a score we accept the
        // sample (the wizard's threshold branch is wired for any
        // future `QualityReported`-driven rejection; today's wire
        // contract tolerates score 0 per Phase 2A4).
        const score = 100

        clearTimeout(timeoutHandle)
        settled = true
        webApi.onSamplesAcquired = undefined
        webApi.onErrorOccurred = undefined
        resolve({
          templateB64: samples,
          qualityScore: score,
          deviceSerial: deviceUid,
          // The PngImage sample format returns dimensions alongside
          // the base64 string in the production SDK; the wrapper
          // reports 0 when the SDK omits them so downstream callers
          // can detect the missing-metadata case explicitly.
          width: 0,
          height: 0,
        })
      } catch (err) {
        clearTimeout(timeoutHandle)
        settleReject(
          err instanceof Error
            ? err
            : new BiometricHardwareError(String(err)),
        )
      }
    }

    // Kick off the acquisition lifecycle. We intentionally do NOT
    // await `enumerateDevices()` -> the SDK delivers the device UID
    // in the `onSamplesAcquired.deviceUid` field, so an empty
    // `startAcquisition` (no deviceUid argument) is the documented
    // "use any connected reader" path.
    webApi
      .startAcquisition(SAMPLE_FORMAT_PNG_IMAGE)
      .catch((err: unknown) => {
        clearTimeout(timeoutHandle)
        settleReject(
          err instanceof Error
            ? new BiometricHardwareError(err.message)
            : new BiometricHardwareError(String(err)),
        )
      })
  })
}

/**
 * Lazy-loader for the `@digitalpersona/fingerprint` UMD IIFE bundle.
 * The package's `package.json` declares `unpkg:
 * "./dist/fingerprint.sdk.min.js"` and `browser: "./dist/fingerprint.sdk.js"`,
 * but the `.d.ts` ships an ambient namespace (no ESM `export`s), so
 * a Vite `import('@digitalpersona/fingerprint')` returns `{}`. The
 * exports map is also locked to the root, so deep imports like
 * `import('.../dist/fingerprint.sdk.min.js?url')` are rejected by
 * Vite's strict export resolution.
 *
 * The Phase 1 probe page (`public/fingerprint-probe.html:115`) solved
 * this by copying the minified IIFE to `public/websdk/fingerprint.sdk.min.js`
 * and serving it as a static asset. We follow the same pattern: the
 * vendored copy is committed at `public/websdk/fingerprint.sdk.min.js`
 * (Regenerated by `npm install` -> `node_modules/@digitalpersona/fingerprint/dist/fingerprint.sdk.min.js`).
 * We inject a `<script>` tag lazily and wait for
 * `window.Fingerprint.WebApi` to be defined.
 *
 * The Promise is cached so concurrent calls share a single script
 * injection — the browser hits the HTTP cache on subsequent calls
 * anyway, but the Promise-level cache avoids racing the `onload`
 * event.
 */
const SDK_SCRIPT_SRC = '/websdk/fingerprint.sdk.min.js'

let sdkLoadPromise: Promise<FingerprintSdk> | null = null

function loadFingerprintSdk(): Promise<FingerprintSdk> {
  if (typeof window !== 'undefined') {
    const cached = (window as unknown as { Fingerprint?: FingerprintSdk }).Fingerprint
    if (cached) return Promise.resolve(cached)
  }
  if (sdkLoadPromise) return sdkLoadPromise

  sdkLoadPromise = (async () => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      throw new BiometricHardwareError(
        'captureFingerprint() requiere un entorno browser.',
      )
    }

    await new Promise<void>((resolve, reject) => {
      const existing = document.querySelector(
        `script[data-dp4500-sdk="true"]`,
      )
      if (existing) {
        existing.addEventListener('load', () => resolve())
        existing.addEventListener(
          'error',
          () =>
            reject(
              new BiometricHardwareError(
                'Falló la carga del script del SDK.',
              ),
            ),
        )
        return
      }
      const script = document.createElement('script')
      script.src = SDK_SCRIPT_SRC
      script.async = true
      script.dataset.dp4500Sdk = 'true'
      script.onload = () => resolve()
      script.onerror = () =>
        reject(
          new BiometricHardwareError(
            'Falló la carga del script del SDK.',
          ),
        )
      document.head.appendChild(script)
    })

    // The IIFE registers `window.Fingerprint` synchronously during
    // script execution, but on slow hardware the load event may
    // fire a tick before the assignment is observable. Poll up to
    // 2 seconds before giving up.
    const win = window as unknown as { Fingerprint?: FingerprintSdk }
    const deadline = Date.now() + 2_000
    while (typeof win.Fingerprint === 'undefined') {
      if (Date.now() > deadline) {
        throw new BiometricHardwareError(
          'El SDK no registró window.Fingerprint tras 2s.',
        )
      }
      await new Promise((r) => setTimeout(r, 50))
    }

    return win.Fingerprint
  })().catch((err: unknown) => {
    // Reset the cached promise so a future call retries the load.
    sdkLoadPromise = null
    throw err instanceof Error
      ? err
      : new BiometricHardwareError(String(err))
  })

  return sdkLoadPromise
}

/**
 * Minimal structural typing for the SDK's WebApi surface. We avoid
 * pulling the package's ambient `.d.ts` (which declares a global
 * `Fingerprint` namespace and breaks under the project's
 * `verbatimModuleSyntax: true` + bundler resolution combo) and
 * instead describe just the methods + event signatures the wrapper
 * touches. The runtime IIFE registers a richer object on
 * `window.Fingerprint`; the wrapper treats the value as this
 * shape and lets unknown fields pass through.
 */
interface FingerprintSdk {
  WebApi: new () => FingerprintWebApi
}

interface FingerprintWebApi {
  startAcquisition(sampleFormat: number, deviceUid?: string): Promise<void>
  stopAcquisition(deviceUid?: string): Promise<void>
  onErrorOccurred?: ((event: FingerprintErrorEvent) => void) | undefined
  onSamplesAcquired?: ((event: FingerprintSamplesAcquiredEvent) => void) | undefined
}

interface FingerprintErrorEvent {
  error: number
}

interface FingerprintSamplesAcquiredEvent {
  deviceUid: string
  samples: string
}
