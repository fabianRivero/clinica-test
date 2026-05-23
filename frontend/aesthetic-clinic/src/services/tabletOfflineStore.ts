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
  status: 'pending'
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

export async function countPendingOfflineEvents(): Promise<number> {
  const db = await openDb()
  const count = await new Promise<number>((resolve, reject) => {
    const tx = db.transaction(EVENTS_STORE, 'readonly')
    const req = tx.objectStore(EVENTS_STORE).count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  db.close()
  return count
}
