import { useEffect, useMemo, useState } from 'react'

import {
  getMyNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  notifyNotificationsUpdated,
  type NotificationItem,
} from '../../services/api/notifications'

export function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<NotificationItem | null>(null)
  const [statusFilter, setStatusFilter] = useState('')

  const load = async () => {
    const data = await getMyNotifications()
    setItems(data.items || [])
    setLoading(false)
  }

  useEffect(() => {
    void load()
  }, [])

  const markAll = async () => {
    await markAllNotificationsRead()
    await load()
    notifyNotificationsUpdated()
  }

  const openNotification = async (item: NotificationItem) => {
    if (!item.isRead) {
      await markNotificationRead(item.id)
      setItems((current) => current.map((n) => (n.id === item.id ? { ...n, isRead: true } : n)))
      setSelected({ ...item, isRead: true })
      notifyNotificationsUpdated()
      return
    }
    setSelected(item)
  }

  const unreadCount = useMemo(() => items.filter((item) => !item.isRead).length, [items])

  const filteredItems = items.filter((item) => {
    if (statusFilter === 'leida') return item.isRead
    if (statusFilter === 'no_leida') return !item.isRead
    return true
  })

  return (
    <section className="page-section">
      <header className="_flex-between">
        <div>
          <h1>Notificaciones</h1>
          <p className="_m-0 _text-muted">No leídas: {unreadCount}</p>
        </div>
        <button className="button button--ghost button--compact" onClick={() => void markAll()}>
          Marcar todas como leídas
        </button>
      </header>

      {loading ? (
        <p>Cargando...</p>
      ) : (
        <>
          <div className="form-grid _mb-md">
            <label className="field">
              <span>Estado</span>
              <select
                className="input"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">Todos</option>
                <option value="leida">Leída</option>
                <option value="no_leida">No leída</option>
              </select>
            </label>
          </div>
          {filteredItems.length > 0 ? (
            <div className="table-card">
              <table className="table">
                <thead>
                  <tr>
                    <th>Estado</th>
                    <th>Mensaje</th>
                    <th>Fecha</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredItems.map((item) => (
                  <tr key={item.id} className="_cursor-pointer" onClick={() => void openNotification(item)}>
                    <td>{item.isRead ? 'Leída' : 'No leída'}</td>
                    <td>
                      <strong>{item.title}</strong>
                      <div>{item.message}</div>
                    </td>
                    <td>{new Date(item.createdAt).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
              </table>
            </div>
          ) : (
            <p style={{ padding: '1rem', textAlign: 'center' }}>
              {items.length > 0
                ? 'No hay notificaciones para el filtro seleccionado.'
                : 'No tienes notificaciones registradas.'}
            </p>
          )}
        </>
      )}

      {selected ? (
        <div className="booking-modal-overlay" role="dialog" aria-modal="true" aria-label="Detalle de notificación">
          <div className="booking-modal-content _max-w-md">
            <header className="booking-modal-header">
              <h2 className="_m-0">{selected.title}</h2>
              <button className="booking-modal-close" type="button" onClick={() => setSelected(null)}>
                ×
              </button>
            </header>
            <div className="booking-modal-body _p-6">
              <p className="_m-0">{selected.message}</p>
              <small className="_text-muted">
                {new Date(selected.createdAt).toLocaleString()}
              </small>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
