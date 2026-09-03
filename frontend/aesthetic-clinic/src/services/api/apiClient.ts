import { ensureCsrfCookie } from './auth'
import { getActiveBranchId } from './activeBranch'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export { API_BASE_URL }

/** Error type that includes field-level validation errors from the API */
export type ApiError = Error & {
  fieldErrors?: Record<string, string>
}

/** Build common headers (Accept, optional branch header) */
function buildHeaders(extra?: Record<string, string>): Record<string, string> {
  const branchId = getActiveBranchId()
  return {
    Accept: 'application/json',
    ...(branchId ? { 'X-Selected-Branch-Id': String(branchId) } : {}),
    ...extra,
  }
}

/** Parse response, throw ApiError with fieldErrors on failure */
function parseErrorResponse(response: Response, path: string, responseBody: { detail?: string; errors?: Record<string, string> } | null): never {
  const error: ApiError = new Error(
    responseBody?.detail || `No se pudo completar ${path} (${response.status})`
  ) as ApiError
  if (responseBody?.errors) {
    error.fieldErrors = responseBody.errors
  }
  throw error
}

/** GET request that returns typed JSON. Includes branch header. */
export async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: buildHeaders(),
  })

  if (!response.ok) {
    throw new Error(`No se pudo cargar ${path} (${response.status})`)
  }

  return (await response.json()) as T
}

/** GET request WITHOUT branch header (used by auth, client, notifications). */
export async function requestJsonNoBranch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error(`No se pudo cargar ${path} (${response.status})`)
  }

  return (await response.json()) as T
}

/** POST request with JSON body. Includes branch header. Extracts fieldErrors on error. */
export async function requestJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    }),
    body: JSON.stringify(body),
  })

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    parseErrorResponse(response, path, responseBody)
  }

  return responseBody as T
}

/** PATCH request with JSON body. Includes branch header. Extracts fieldErrors on error. */
export async function patchJsonWithBody<T>(path: string, body: unknown): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    }),
    body: JSON.stringify(body),
  })

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    parseErrorResponse(response, path, responseBody)
  }

  return responseBody as T
}

/** POST request with JSON body + idempotency key. Includes branch header. */
export async function requestJsonWithBodyIdempotent<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
      'Idempotency-Key': idempotencyKey,
    }),
    body: JSON.stringify(body),
  })
  const responseBody = (await response.json().catch(() => null)) as { detail?: string; errors?: Record<string, string> } | null
  if (!response.ok) {
    parseErrorResponse(response, path, responseBody)
  }
  return responseBody as T
}

/** POST request with FormData body. Includes branch header. Extracts fieldErrors on error. */
export async function requestFormDataWithBody<T>(path: string, body: FormData): Promise<T> {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'X-CSRFToken': csrfToken,
    }),
    body,
  })

  const responseBody = (await response.json().catch(() => null)) as
    | { detail?: string; errors?: Record<string, string> }
    | null

  if (!response.ok) {
    parseErrorResponse(response, path, responseBody)
  }

  return responseBody as T
}

/** Simple GET with branch header, returns typed JSON. Throws on error with detail message. */
export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: 'include',
    headers: buildHeaders(),
  })
  const data = (await response.json().catch(() => ({}))) as T | { detail?: string }
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

/** Simple POST with JSON body, branch header. Throws on error with detail message. */
export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
    }),
    body: JSON.stringify(body),
  })
  const data = (await response.json().catch(() => ({}))) as T | { detail?: string }
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

/** Simple POST with FormData, branch header. Throws on error with detail message. */
export async function postForm<T>(path: string, formData: FormData): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'X-CSRFToken': csrf,
    }),
    body: formData,
  })
  const data = (await response.json().catch(() => ({}))) as T | { detail?: string }
  if (!response.ok) throw new Error((data as { detail?: string })?.detail || `Error ${response.status}`)
  return data as T
}

/**
 * POST request that returns a binary payload as a `Blob` together with the
 * filename advertised by `Content-Disposition: attachment`. Used by the
 * backup trigger endpoint, which streams a freshly-created dump as
 * `application/octet-stream`. Throws on non-OK responses using the body's
 * `detail` field (when JSON) or a generic status-based message.
 */
export async function requestBlob(
  path: string,
  body: unknown = {},
): Promise<{ blob: Blob; filename: string | null }> {
  const csrf = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: buildHeaders({
      'Accept': 'application/octet-stream, application/json, */*',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrf,
    }),
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(errorBody?.detail || `No se pudo completar ${path} (${response.status})`)
  }

  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
  const filename = match && match[1] ? decodeURIComponent(match[1]) : null
  return { blob, filename }
}

/**
 * DELETE request. The current admin SPA only POSTs, but the backup endpoints
 * follow REST semantics: `DELETE /api/admin/backups/<id>/`. CSRF is required
 * via `X-CSRFToken`. Returns the parsed JSON body when present, otherwise
 * `null` (the backup delete endpoint answers `204 No Content`).
 */
export async function requestDelete<T = null>(path: string): Promise<T> {
  const csrf = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: buildHeaders({
      'Accept': 'application/json',
      'X-CSRFToken': csrf,
    }),
  })

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(errorBody?.detail || `No se pudo completar ${path} (${response.status})`)
  }

  if (response.status === 204) {
    return null as T
  }

  const data = (await response.json().catch(() => null)) as T | null
  return (data ?? null) as T
}