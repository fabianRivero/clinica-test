import { requestJsonNoBranch, postJson } from './apiClient'

export type NotificationItem = {
  id: number
  type: string
  title: string
  message: string
  createdAt: string
  isRead: boolean
  actionUrl: string
}

export const NOTIFICATIONS_UPDATED_EVENT = 'notifications:updated'

export function notifyNotificationsUpdated() {
  window.dispatchEvent(new Event(NOTIFICATIONS_UPDATED_EVENT))
}

export function getMyNotifications() {
  return requestJsonNoBranch<{ items: NotificationItem[]; latest: NotificationItem[]; unreadCount: number }>('/api/notifications/')
}

export function markAllNotificationsRead() {
  return postJson<{ detail?: string }>('/api/notifications/mark-all-read/', {})
}

export function markNotificationRead(notificationId: number) {
  return postJson<{ detail?: string }>(`/api/notifications/${notificationId}/read/`, {})
}
