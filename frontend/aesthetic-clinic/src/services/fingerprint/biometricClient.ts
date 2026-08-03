import { postJson } from '../api/apiClient'

/**
 * Frontend wrapper for the DigitalPersona 4500 biometric flow.
 *
 * The frontend never imports `mockFingerprint` or talks to the agent
 * directly: every request goes to Django, which calls the local
 * `fingerprint-agent` service over Cloudflare Tunnel and returns the
 * metadata the UI needs. Wire contract matches `backend/biometric/views.py`.
 *
 *  - `enrollInit(clienteId, {consentimiento_aceptado})` — backend
 *      captures once via the agent, encrypts the template, persists a
 *      `HuellaBiometricaCliente` row (provider `DIGITAL_PERSONA`) and
 *      writes a `BiometricAttempt`. Response carries metadata only.
 *  - `verifyInit(citaId)` — backend returns `{capture_token, ...}` if
 *      the cliente has a stored template, or `{manual_only: true}` if
 *      not (the UI hides the biometric button in that case).
 *  - `verifyConfirm(citaId, {capture_token, score})` — backend pops the
 *      one-shot token, compares the score, transitions the cita on
 *      match, and writes a `BiometricAttempt`.
 *  - `listAgents()` — backend returns active `AgentToken` rows. The UI
 *      uses `last_seen_at` to render the "reader offline" banner.
 *
 * Suspension:
 *
 *  `isBiometricSuspended()` reads the build-time flag
 *  `VITE_BIOMETRIC_SUSPENDED` (set by `backend/build.sh`). When `true`,
 *  every capture/match/enroll call short-circuits at the source — no
 *  HTTP request is emitted — and the agent heartbeat poll is skipped.
 *  The backend `BIOMETRIC_SUSPENDED` env var remains authoritative;
 *  if the flags diverge, the backend 503 response wins. Rebuild and
 *  reload are required to change the frontend value at runtime.
 */

const BIOMETRIC_SUSPENDED_RAW = import.meta.env.VITE_BIOMETRIC_SUSPENDED

/**
 * Returns `true` when the build was produced with
 * `VITE_BIOMETRIC_SUSPENDED=true` (also accepts `1`, case-insensitive).
 * Vite replaces `import.meta.env.VITE_*` at build time, so this value
 * is immutable without a rebuild.
 */
export function isBiometricSuspended(): boolean {
  const value = BIOMETRIC_SUSPENDED_RAW
  if (typeof value !== 'string') return false
  const normalized = value.trim().toLowerCase()
  return normalized === '1' || normalized === 'true'
}

// Snapshot at module load. Kept private — callers should go through
// `isBiometricSuspended()` so the contract stays explicit.
const SUSPENDED: boolean = isBiometricSuspended()

// ---------------------------------------------------------------------------
// Enrollment
// ---------------------------------------------------------------------------

export interface BiometricEnrollInitRequest {
  consentimiento_aceptado: boolean
  dedo_referencia?: string
}

export interface BiometricEnrollInitResponse {
  ok: boolean
  cliente_id: number
  huella_id: number
  device_serial: string
  template_format: string
  calidad_captura: number
  proveedor: string
  created: boolean
  attempt: {
    id: number
    operation: string
    success: boolean
    score: string | null
    failure_reason: string | null
    created_at: string | null
  }
}

/**
 * Thrown by capture/match calls when the build flag
 * `VITE_BIOMETRIC_SUSPENDED` is set. Callers can catch it to render
 * the manual-only path. Distinct from network failures so tests and
 * UI flows can differentiate "we deliberately didn't try" from "the
 * backend is unreachable".
 */
export class BiometricSuspendedError extends Error {
  readonly code = 'BIOMETRIC_SUSPENDED' as const
  constructor(message = 'Biometric capture is temporarily suspended.') {
    super(message)
    this.name = 'BiometricSuspendedError'
  }
}

export async function enrollInit(
  clienteId: number,
  payload: BiometricEnrollInitRequest,
): Promise<BiometricEnrollInitResponse> {
  if (SUSPENDED) {
    throw new BiometricSuspendedError('Captura por huella suspendida.')
  }
  return postJson<BiometricEnrollInitResponse>(
    `/api/biometric/clientes/${clienteId}/huella/enroll/`,
    payload,
  )
}

// ---------------------------------------------------------------------------
// Prospect enrollment
// ---------------------------------------------------------------------------
//
// The conversion wizard captures the fingerprint at step 4, before the
// prospect has been promoted to a `Cliente`. The backend endpoint
// persists the row against the prospect and the finalize handler
// re-attaches it to the freshly-created cliente atomically.

export interface ProspectEnrollResponse {
  ok: boolean
  cliente_id: number | null
  prospecto_id: number
  huella_id: number
  device_serial: string
  template_format: string
  calidad_captura: number
  proveedor: string
  attempt_id: number
}

export async function prospectoEnrollInit(
  prospectoId: number,
  payload: BiometricEnrollInitRequest,
): Promise<ProspectEnrollResponse> {
  if (SUSPENDED) {
    throw new BiometricSuspendedError('Captura por huella suspendida.')
  }
  return postJson<ProspectEnrollResponse>(
    `/api/biometric/prospectos/${prospectoId}/huella/enroll/`,
    payload,
  )
}

// ---------------------------------------------------------------------------
// Verification
// ---------------------------------------------------------------------------

/**
 * Reasons the verify-init response can come back without a capture
 * token. `suspended` is the build-time VITE flag result and is
 * distinct from `no_fingerprint` (cliente has no stored template).
 */
export type BiometricVerifyUnavailableReason = 'suspended' | 'no_fingerprint'

export interface BiometricVerifyInitResponse {
  has_fingerprint: boolean
  manual_only?: boolean
  /**
   * When the verify path is unavailable, this field names the reason.
   * `suspended` = build-time flag is on; `no_fingerprint` = cliente
   * has no template on file. Absent on the happy path.
   */
  unavailable_reason?: BiometricVerifyUnavailableReason
  capture_token?: string
  /** Backend-computed score from the agent's match call. 0..1. */
  score?: number
  /** Backend-configured threshold (DecimalField serialized as string). */
  threshold?: string
  cliente_id?: number
  cita_id?: number
}

export interface BiometricVerifyConfirmRequest {
  capture_token: string
  score: number
}

export interface BiometricVerifyConfirmResponse {
  matched: boolean
  score: string
  threshold: string
  attempt: {
    id: number
    cita_id: number
    success: boolean
    score: string | null
    failure_reason: string | null
  }
  cita_id: number
  message: string
  code?: string
}

export async function verifyInit(citaId: number): Promise<BiometricVerifyInitResponse> {
  if (SUSPENDED) {
    return {
      has_fingerprint: false,
      manual_only: true,
      unavailable_reason: 'suspended',
    }
  }
  return postJson<BiometricVerifyInitResponse>(
    `/api/biometric/citas/${citaId}/huella/verify-init/`,
    {},
  )
}

export async function verifyConfirm(
  citaId: number,
  payload: BiometricVerifyConfirmRequest,
): Promise<BiometricVerifyConfirmResponse> {
  if (SUSPENDED) {
    throw new BiometricSuspendedError('Verificacion por huella suspendida.')
  }
  return postJson<BiometricVerifyConfirmResponse>(
    `/api/biometric/citas/${citaId}/huella/verify-confirm/`,
    payload,
  )
}

// ---------------------------------------------------------------------------
// Agent list (used for the offline banner)
// ---------------------------------------------------------------------------

export interface AgentListItem {
  id: number
  name: string
  sucursal_id: number | null
  public_url: string
  is_active: boolean
  last_seen_at: string | null
  created_at: string | null
  token_fingerprint: string
}

export async function listAgents(): Promise<AgentListItem[]> {
  if (SUSPENDED) {
    return []
  }
  const response = await postJson<{ results: AgentListItem[] }>(
    '/api/biometric/agents/',
    {},
  )
  return response.results
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_OFFLINE_THRESHOLD_MS = 5 * 60 * 1000

/**
 * Returns `true` if the agent's heartbeat is fresh enough to be
 * considered online. `null` `last_seen_at` is treated as offline so
 * the warning banner renders.
 */
export function isAgentOnline(
  lastSeenAt: string | null,
  nowMs: number = Date.now(),
  thresholdMs: number = DEFAULT_OFFLINE_THRESHOLD_MS,
): boolean {
  if (!lastSeenAt) {
    return false
  }
  const ts = new Date(lastSeenAt).getTime()
  if (Number.isNaN(ts)) {
    return false
  }
  return nowMs - ts < thresholdMs
}

export const biometricClient = {
  enrollInit,
  prospectoEnrollInit,
  verifyInit,
  verifyConfirm,
  listAgents,
  isAgentOnline,
  isBiometricSuspended,
}

export default biometricClient