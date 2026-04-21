import type { AuthResponse, LoginPayload } from '../../types/auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

function getCookie(name: string) {
  const cookie = document.cookie
    .split('; ')
    .find((item) => item.startsWith(`${name}=`))

  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : ''
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json().catch(() => null)) as T | { detail?: string } | null

  if (!response.ok) {
    const message =
      data && typeof data === 'object' && 'detail' in data && data.detail
        ? data.detail
        : `La solicitud fallo con estado ${response.status}.`
    throw new Error(message)
  }

  return data as T
}

export async function ensureCsrfCookie() {
  const response = await fetch(`${API_BASE_URL}/api/auth/csrf/`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  await parseResponse<{ detail: string }>(response)
}

export async function getSessionUser() {
  const response = await fetch(`${API_BASE_URL}/api/auth/me/`, {
    credentials: 'include',
    headers: {
      Accept: 'application/json',
    },
  })

  if (response.status === 401) {
    return null
  }

  const data = await parseResponse<AuthResponse>(response)
  return data.user
}

export async function loginUser(payload: LoginPayload) {
  await ensureCsrfCookie()
  const csrfToken = getCookie('csrftoken')

  const response = await fetch(`${API_BASE_URL}/api/auth/login/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify(payload),
  })

  return parseResponse<AuthResponse>(response)
}

export async function logoutUser() {
  await ensureCsrfCookie()
  const csrfToken = getCookie('csrftoken')

  const response = await fetch(`${API_BASE_URL}/api/auth/logout/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
  })

  await parseResponse<{ detail: string }>(response)
}
