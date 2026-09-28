/**
 * DP4500 capture client — Phase 2A of dp4500-host-app-integration-phase2.
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
 * The actual fingerprint *capture* in the browser (HID WebSdk,
 * sample acquisition, template construction) is Phase 4 work per the
 * design §Q1 decision (the probe showed direct WebUSB is not viable
 * for the DigitalPersona SDK; we'd need the HID Authentication Device
 * Client running locally on the operator's PC). For now, the caller
 * passes a `template_b64` placeholder; the wire contract for the
 * rest of the flow is exercised.
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
  readonly code = 'DP4500_SUSPENDED' as const
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
