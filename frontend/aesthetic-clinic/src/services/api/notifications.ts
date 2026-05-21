import { ensureCsrfCookie } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export type NotificationItem = {
  id: number
  type: string
  title: string
  message: string
  createdAt: string
  isRead: boolean
  actionUrl: string
}

export async function getMyNotifications() {
  const response = await fetch(`${API_BASE_URL}/api/notifications/`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    throw new Error(`No se pudo cargar notificaciones (${response.status})`)
  }
  return (await response.json()) as { items: NotificationItem[]; latest: NotificationItem[]; unreadCount: number }
}

async function post(path: string) {
  const csrfToken = await ensureCsrfCookie()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken,
    },
    body: JSON.stringify({}),
  })
  const data = (await response.json().catch(() => null)) as { detail?: string } | null
  if (!response.ok) throw new Error(data?.detail || `No se pudo completar ${path} (${response.status})`)
  return data
}

export function markAllNotificationsRead() {
  return post('/api/notifications/mark-all-read/')
}

export function markNotificationRead(notificationId: number) {
  return post(`/api/notifications/${notificationId}/read/`)
}
