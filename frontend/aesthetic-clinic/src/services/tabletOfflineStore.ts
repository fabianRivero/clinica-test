import type { TabletCurrentAppointmentResponse } from '../types/tablet'

const DB_NAME = 'tablet-offline-db'
const DB_VERSION = 1
const SNAPSHOT_STORE = 'snapshot'
const EVENTS_STORE = 'offline_events'

export interface TabletOfflineSnapshot {
  id: 'today'
  savedAt: string
  data: TabletCurrentAppointmentResponse
}

export interface TabletOfflineEvent {
  eventId: string
  operationId: number
  createdAt: string
  status: 'pending' | 'synced' | 'conflict' | 'rejected'
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(SNAPSHOT_STORE)) {
        db.createObjectStore(SNAPSHOT_STORE, { keyPath: 'id' })
      }
      if (!db.objectStoreNames.contains(EVENTS_STORE)) {
        db.createObjectStore(EVENTS_STORE, { keyPath: 'eventId' })
      }
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function saveTabletSnapshot(data: TabletCurrentAppointmentResponse): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(SNAPSHOT_STORE, 'readwrite')
    tx.objectStore(SNAPSHOT_STORE).put({ id: 'today', savedAt: new Date().toISOString(), data } as TabletOfflineSnapshot)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function loadTabletSnapshot(): Promise<TabletOfflineSnapshot | null> {
  const db = await openDb()
  const result = await new Promise<TabletOfflineSnapshot | null>((resolve, reject) => {
    const tx = db.transaction(SNAPSHOT_STORE, 'readonly')
    const req = tx.objectStore(SNAPSHOT_STORE).get('today')
    req.onsuccess = () => resolve((req.result as TabletOfflineSnapshot | undefined) ?? null)
    req.onerror = () => reject(req.error)
  })
  db.close()
  return result
}

export async function queueOfflineConfirmation(operationId: number): Promise<TabletOfflineEvent> {
  const db = await openDb()
  const event: TabletOfflineEvent = {
    eventId: crypto.randomUUID(),
    operationId,
    createdAt: new Date().toISOString(),
    status: 'pending',
  }
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(EVENTS_STORE, 'readwrite')
    tx.objectStore(EVENTS_STORE).put(event)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
  return event
}

export async function listPendingOfflineEvents(): Promise<TabletOfflineEvent[]> {
  const db = await openDb()
  const pending = await new Promise<TabletOfflineEvent[]>((resolve, reject) => {
    const tx = db.transaction(EVENTS_STORE, 'readonly')
    const req = tx.objectStore(EVENTS_STORE).getAll()
    req.onsuccess = () => resolve((req.result as TabletOfflineEvent[]).filter((item) => item.status === 'pending'))
    req.onerror = () => reject(req.error)
  })
  db.close()
  return pending
}

export async function markOfflineEventStatus(eventId: string, status: TabletOfflineEvent['status']): Promise<void> {
  const db = await openDb()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(EVENTS_STORE, 'readwrite')
    const store = tx.objectStore(EVENTS_STORE)
    const req = store.get(eventId)
    req.onsuccess = () => {
      const item = req.result as TabletOfflineEvent | undefined
      if (!item) {
        resolve()
        return
      }
      item.status = status
      store.put(item)
    }
    req.onerror = () => reject(req.error)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function countPendingOfflineEvents(): Promise<number> {
  const pending = await listPendingOfflineEvents()
  return pending.length
}

const DEVICE_ID_KEY = 'tablet-offline-device-id'

export function getOfflineDeviceId(): string {
  const existing = window.localStorage.getItem(DEVICE_ID_KEY)
  if (existing) return existing
  const created = crypto.randomUUID()
  window.localStorage.setItem(DEVICE_ID_KEY, created)
  return created
}


const OFFLINE_RETENTION_HOURS = 48

function toMillis(value: string): number {
  const ts = Date.parse(value)
  return Number.isFinite(ts) ? ts : 0
}

export async function purgeOldOfflineData(now = Date.now()): Promise<void> {
  const db = await openDb()
  const cutoff = now - OFFLINE_RETENTION_HOURS * 60 * 60 * 1000
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction([SNAPSHOT_STORE, EVENTS_STORE], 'readwrite')
    const snapshotStore = tx.objectStore(SNAPSHOT_STORE)
    const eventsStore = tx.objectStore(EVENTS_STORE)

    const snapshotReq = snapshotStore.get('today')
    snapshotReq.onsuccess = () => {
      const snapshot = snapshotReq.result as TabletOfflineSnapshot | undefined
      if (snapshot && toMillis(snapshot.savedAt) < cutoff) {
        snapshotStore.delete('today')
      }
    }

    const eventsReq = eventsStore.getAll()
    eventsReq.onsuccess = () => {
      const events = (eventsReq.result as TabletOfflineEvent[]) || []
      for (const event of events) {
        if (toMillis(event.createdAt) < cutoff) {
          eventsStore.delete(event.eventId)
        }
      }
    }

    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}
