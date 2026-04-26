import {
  createContext,
  type PropsWithChildren,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

type NotificationTone = 'success' | 'info' | 'warning' | 'danger'

type NotificationItem = {
  id: string
  title: string
  message: string
  tone: NotificationTone
  duration: number
}

type ShowNotificationInput = {
  title: string
  message: string
  tone?: NotificationTone
  duration?: number
}

type NotificationContextValue = {
  showNotification: (input: ShowNotificationInput) => void
  dismissNotification: (id: string) => void
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

function buildNotificationId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function NotificationProvider({ children }: PropsWithChildren) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const timeoutRefs = useRef<Record<string, number>>({})

  const dismissNotification = useCallback((id: string) => {
    const timeoutId = timeoutRefs.current[id]
    if (timeoutId) {
      window.clearTimeout(timeoutId)
      delete timeoutRefs.current[id]
    }

    setNotifications((current) => current.filter((item) => item.id !== id))
  }, [])

  const showNotification = useCallback(
    ({ title, message, tone = 'info', duration = 4000 }: ShowNotificationInput) => {
      const id = buildNotificationId()
      const item: NotificationItem = {
        id,
        title,
        message,
        tone,
        duration,
      }

      setNotifications((current) => [...current, item])
      timeoutRefs.current[id] = window.setTimeout(() => {
        dismissNotification(id)
      }, duration)
    },
    [dismissNotification],
  )

  useEffect(() => {
    return () => {
      Object.values(timeoutRefs.current).forEach((timeoutId) => window.clearTimeout(timeoutId))
      timeoutRefs.current = {}
    }
  }, [])

  const contextValue = useMemo(
    () => ({
      showNotification,
      dismissNotification,
    }),
    [dismissNotification, showNotification],
  )

  return (
    <NotificationContext.Provider value={contextValue}>
      {children}
      <div aria-live="polite" aria-atomic="true" className="notification-stack">
        {notifications.map((item) => (
          <article className={`notification-toast notification-toast--${item.tone}`} key={item.id}>
            <div className="notification-toast__content">
              <strong>{item.title}</strong>
              <p>{item.message}</p>
            </div>
            <button
              aria-label="Cerrar notificacion"
              className="notification-toast__close"
              type="button"
              onClick={() => dismissNotification(item.id)}
            >
              ×
            </button>
          </article>
        ))}
      </div>
    </NotificationContext.Provider>
  )
}

export function useNotifications() {
  const context = useContext(NotificationContext)

  if (!context) {
    throw new Error('useNotifications debe usarse dentro de NotificationProvider.')
  }

  return context
}
