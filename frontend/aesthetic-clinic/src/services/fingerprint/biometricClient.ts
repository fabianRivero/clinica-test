import { postJson } from '../api/apiClient'

/**
 * Frontend wrapper for the DigitalPersona 4500 biometric flow.
 *
 * PR #1 / PR #2 move the capture and match orchestration to the Django
 * backend (which calls the local `fingerprint-agent` service over
 * Cloudflare Tunnel). The frontend never imports `mockFingerprint` or
 * talks to the agent directly: every request goes to Django, which
 * returns the metadata the UI needs.
 *
 * Wire contract (matches `backend/biometric/views.py`):
 *
 *  - `enrollInit(clienteId, {consentimiento_aceptado})`
 *      Backend captures once via the agent, encrypts the template,
 *      persists a `HuellaBiometricaCliente` row (provider
 *      `DIGITAL_PERSONA`) and writes a `BiometricAttempt`. The response
 *      carries metadata only (no template bytes).
 *  - `verifyInit(citaId)`
 *      Backend returns `{capture_token, agent_url, threshold, ...}`
 *      if the cliente has a stored template. The frontend then asks
 *      the agent to capture+match by POSTing to `agent_url/match`
 *      with the same `capture_token`. The agent returns a raw score.
 *      If the cliente has no template, the backend answers
 *      `{has_fingerprint: false, manual_only: true}` so the UI hides
 *      the biometric button.
 *  - `verifyConfirm(citaId, {capture_token, agent_score})`
 *      Backend pops the one-shot token, compares the score to the
 *      configured threshold, transitions the cita to `CONFIRMADA` on
 *      match, and writes a `BiometricAttempt`.
 *  - `listAgents()`
 *      Backend returns all active `AgentToken` rows scoped to the
 *      admin's role. The UI uses `last_seen_at` to render the
 *      "reader offline" warning banner.
 */

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

export async function enrollInit(
  clienteId: number,
  payload: BiometricEnrollInitRequest,
): Promise<BiometricEnrollInitResponse> {
  return postJson<BiometricEnrollInitResponse>(
    `/api/biometric/clientes/${clienteId}/huella/enroll/`,
    payload,
  )
}

// ---------------------------------------------------------------------------
// Verification
// ---------------------------------------------------------------------------

export interface BiometricVerifyInitResponse {
  has_fingerprint: boolean
  manual_only?: boolean
  capture_token?: string
  agent_url?: string
  agent_token_hint?: string
  agent_id?: number
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
  return postJson<BiometricVerifyInitResponse>(
    `/api/biometric/citas/${citaId}/huella/verify-init/`,
    {},
  )
}

export async function verifyConfirm(
  citaId: number,
  payload: BiometricVerifyConfirmRequest,
): Promise<BiometricVerifyConfirmResponse> {
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
 * considered online. We compare against `nowMs` (defaults to `Date.now()`)
 * with a 5-minute window to match `design.md` §7 / spec requirement 11.
 *
 * `null` `last_seen_at` means the agent has never reported in; that is
 * always treated as offline so the UI shows the warning banner.
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
  verifyInit,
  verifyConfirm,
  listAgents,
  isAgentOnline,
}

export default biometricClient