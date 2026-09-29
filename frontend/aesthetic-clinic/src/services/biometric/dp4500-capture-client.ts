/**
 * DP4500 capture client — Phase 3 of dp4500-host-app-integration-phase2,
 * refactored in Phase 4 PR C.
 *
 * Opción A: real capture via the local `fingerprint-agent` HTTP service.
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
 * Phase 4 PR C wiring: the browser-direct Web SDK path that Phase 3
 * relied on has been eliminated. The DigitalPersona Lite Client
 * monopolizes the reader on the operator workstation and blocks the
 * legacy SDK's WebChannel traffic, so the vendored legacy SDK bundle
 * is non-functional on real hardware. The `fingerprint-agent`
 * Node.js service (commit 6507628, bound to `127.0.0.1:8765`) is now
 * the DEFAULT capture path: it wraps the modern SDK via `node:vm`
 * and serves captures over loopback HTTP.
 *
 * `captureFingerprintViaSdk()` is preserved as a stub for the
 * contract surface — see its docstring for the re-enable recipe.
 * The Phase 2A4 NO_AGENT placeholder flow at
 * `useConversionWizard.ts:842-859` is the terminal fallback when the
 * agent also fails.
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
 * Feature flag for the Phase 4 PR C fingerprint-agent fall-through.
 *
 * When `true`, `captureFingerprint()` falls through to the local
 * `fingerprint-agent` Node.js service (bound to `127.0.0.1:8765`)
 * whenever the SDK-direct path raises `BiometricHardwareError`
 * (which, post Phase 4 PR C, is every call — the SDK path is a
 * stub). When `false` (the default), the SDK-direct stub's
 * `BiometricHardwareError` surfaces directly and the wizard falls
 * straight through to the Phase 2A4 NO_AGENT placeholder flow.
 *
 * The flag is read from TWO surfaces (in order):
 *   1. `import.meta.env.VITE_USE_FINGERPRINT_AGENT` — Vite inlines
 *     build-time flags; this is the production-style switch.
 *   2. `window.DP4500_USE_FINGERPRINT_AGENT` — runtime override for
 *     staged rollouts / dev work without a rebuild.
 *
 * Phase 4 PR C design note: the original intent of the flag was to
 * make the SDK-direct path the default and the agent the opt-in.
 * After the Lite Client blocked the SDK, the agent became the
 * default capture path on real workstations; the flag now controls
 * whether the agent is consulted at all. Production deployments
 * should set `VITE_USE_FINGERPRINT_AGENT=true` in `.env`.
 */
function shouldUseFingerprintAgent(): boolean {
  const envFlag = import.meta.env?.VITE_USE_FINGERPRINT_AGENT === 'true'
  if (envFlag) return true
  if (typeof window !== 'undefined') {
    return (
      (window as unknown as { DP4500_USE_FINGERPRINT_AGENT?: boolean })
        .DP4500_USE_FINGERPRINT_AGENT === true
    )
  }
  return false
}

/**
 * Capture a fingerprint from the local `fingerprint-agent` HTTP
 * service (`http://127.0.0.1:8765/capture`). Used as the Phase 4
 * PR C fall-through path when the direct browser Web SDK raises
 * `BiometricHardwareError` and the agent feature flag is on.
 *
 * Maps the agent's response shape (`{templateB64, qualityScore,
 * deviceSerial, width, height}`) into the wizard's
 * `CaptureFingerprintResult`. Translates HTTP failures back into
 * `BiometricHardwareError` so the existing wizard catch site at
 * `useConversionWizard.ts:842-859` can route to the NO_AGENT
 * terminal fallback:
 *   - HTTP 503 (no reader)        → `BiometricHardwareError`
 *   - HTTP 501 (SDK not loaded)   → `BiometricHardwareError`
 *   - HTTP 5xx / network error    → `BiometricHardwareError`
 */
async function captureFingerprintViaAgent(): Promise<CaptureFingerprintResult> {
  const AGENT_URL = 'http://127.0.0.1:8765/capture'
  let response: Response
  try {
    response = await fetch(AGENT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  } catch (err) {
    // Network failure — the agent service is not running. Re-throw
    // as BiometricHardwareError so the wizard's NO_AGENT path at
    // useConversionWizard.ts:842-859 activates.
    throw new BiometricHardwareError(
      `fingerprint-agent unreachable: ${err instanceof Error ? err.message : String(err)}`,
    )
  }
  if (!response.ok) {
    // Both 501 (SDK not initialized) and 503 (no reader) are
    // terminal conditions on the agent side — they mean the agent
    // cannot produce a capture right now. Surface them as
    // BiometricHardwareError so the wizard preserves its NO_AGENT
    // terminal fallback contract (Phase 2A4).
    throw new BiometricHardwareError(
      `fingerprint-agent returned HTTP ${response.status}`,
    )
  }
  const data = (await response.json().catch(() => null)) as
    | Partial<CaptureFingerprintResult>
    | null
  if (!data || typeof data.templateB64 !== 'string') {
    throw new BiometricHardwareError(
      'fingerprint-agent response missing templateB64',
    )
  }
  return {
    templateB64: data.templateB64,
    qualityScore: typeof data.qualityScore === 'number' ? data.qualityScore : 0,
    deviceSerial:
      typeof data.deviceSerial === 'string' ? data.deviceSerial : '',
    width: typeof data.width === 'number' ? data.width : 0,
    height: typeof data.height === 'number' ? data.height : 0,
  }
}

/**
 * Capture a fingerprint from the DigitalPersona 4500 reader via the
 * vendored Web SDK.
 *
 * Phase 4 PR C: STUB. The browser-direct Web SDK path is permanently
 * disabled because the DigitalPersona Lite Client monopolizes the
 * reader on the operator workstation and blocks the legacy SDK's
 * WebChannel traffic — the vendored legacy SDK bundle cannot reach
 * the hardware on a workstation with the Lite Client installed. The
 * default capture path is the local `fingerprint-agent` Node.js
 * service (see `captureFingerprintViaAgent`).
 *
 * This stub is preserved (not deleted) to keep the function name and
 * signature in the contract surface: `captureFingerprint()` still
 * calls it as the FIRST step in its fall-through chain, so the
 * `BiometricHardwareError` it throws routes to the agent when the
 * feature flag is on, and to the Phase 2A4 NO_AGENT placeholder when
 * the flag is off. Re-enabling the SDK-direct path in the future
 * (e.g. on a workstation without the Lite Client) means replacing
 * this body with the original Phase 3 implementation, restoring the
 * `loadFingerprintSdk` helper, and re-vendoring the SDK bundle under
 * `public/websdk/`.
 */
async function captureFingerprintViaSdk(): Promise<CaptureFingerprintResult> {
  throw new BiometricHardwareError(
    'SDK path disabled (Phase 4 PR C — fingerprint-agent is the default).',
  )
}

/**
 * Top-level capture entry point used by the wizard.
 *
 * Phase 4 PR C: tries the SDK-direct path first (stub — always
 * throws `BiometricHardwareError`); when that fails AND the agent
 * feature flag is on, falls through to the local `fingerprint-agent`
 * HTTP service (`http://127.0.0.1:8765/capture`). When the agent
 * also fails (503 / network error), the original SDK error
 * propagates so the wizard's NO_AGENT terminal fallback at
 * `useConversionWizard.ts:842-859` activates.
 *
 * Order of operations (Phase 4 PR C):
 *   1. `captureFingerprintViaSdk()` — Phase 3 path, now a stub that
 *      throws `BiometricHardwareError` on every call.
 *   2. On `BiometricHardwareError` or `BiometricQualityTooLow`:
 *        a. If the agent feature flag is OFF, re-throw the SDK
 *           error (the wizard's NO_AGENT path at
 *           `useConversionWizard.ts:842-859` activates).
 *        b. If the flag is ON, call `captureFingerprintViaAgent()`
 *           and return its result. If the agent ALSO throws, the
 *           original SDK error wins (so the wizard's NO_AGENT path
 *           sees a `BiometricHardwareError`, not a fetch error).
 *   3. Any other error type propagates unchanged.
 *
 * Note: because the SDK-direct path is a stub, in practice every
 * call with the feature flag ON routes to the agent, and every
 * call with the flag OFF throws the stub's
 * `BiometricHardwareError` immediately. The stub is preserved for
 * the contract surface (see `captureFingerprintViaSdk`'s docstring).
 */
export async function captureFingerprint(): Promise<CaptureFingerprintResult> {
  try {
    return await captureFingerprintViaSdk()
  } catch (sdkErr) {
    const isRecoverable =
      sdkErr instanceof BiometricHardwareError ||
      sdkErr instanceof BiometricQualityTooLow
    if (!isRecoverable) {
      throw sdkErr
    }
    if (!shouldUseFingerprintAgent()) {
      // Feature flag off — the SDK stub's BiometricHardwareError
      // surfaces directly. The wizard's NO_AGENT path at
      // useConversionWizard.ts:842-859 activates on this error.
      throw sdkErr
    }
    // Agent feature flag on — fall through to the local agent.
    // If the agent also fails, prefer the ORIGINAL SDK error so
    // the wizard's NO_AGENT branch sees a `BiometricHardwareError`
    // and not a fetch TypeError.
    try {
      return await captureFingerprintViaAgent()
    } catch {
      throw sdkErr
    }
  }
}
