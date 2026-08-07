import { useCallback, useEffect, useState } from 'react'

import type { BackupFile } from '../../../types/admin'
import {
  deleteAdminBackup,
  listAdminBackups,
  triggerAdminBackup,
} from '../../../services/api/admin'

/**
 * State exposed by the admin Backups page. `trigger` and `remove` each carry
 * their own loading flag so the table can grey out only the affected row
 * while a sibling action runs in parallel. `triggerError` is reset on every
 * attempt so a stale message from a previous run cannot leak into the
 * confirmation modal that follows a successful create.
 */
type UseBackupsResult = {
  backups: BackupFile[]
  isLoading: boolean
  error: string | null
  refresh: () => void
  isTriggering: boolean
  triggerError: string | null
  trigger: () => Promise<{ blob: Blob; filename: string | null }>
  isRemoving: boolean
  removeError: string | null
  remove: (filename: string) => Promise<void>
}

const LIST_FALLBACK = 'No se pudieron cargar los respaldos.'
const TRIGGER_FALLBACK = 'No se pudo generar el respaldo.'
const REMOVE_FALLBACK = 'No se pudo eliminar el respaldo.'

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback
}

/**
 * Centralises the four backup operations used by `AdminBackupsPage`:
 *   - `list` initial fetch + manual `refresh()`
 *   - `trigger` produces a `Blob` (the freshly streamed dump) and clears the
 *     list cache so the next `refresh()` shows the new row immediately
 *   - `remove` deletes a backup by filename and refreshes the list
 *
 * Mirrors the SWR-ish hand-rolled pattern used in `ReportLayout`: data is
 * kept visible during background refreshes so the table does not flash a
 * loading skeleton between operations.
 */
export function useBackups(): UseBackupsResult {
  const [backups, setBackups] = useState<BackupFile[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const [isTriggering, setIsTriggering] = useState(false)
  const [triggerError, setTriggerError] = useState<string | null>(null)

  const [isRemoving, setIsRemoving] = useState(false)
  const [removeError, setRemoveError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setReloadKey((current) => current + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- matches useApiResource pattern
    setIsLoading(true)
    listAdminBackups()
      .then((response) => {
        if (cancelled) return
        setBackups(response.results ?? [])
        setError(null)
      })
      .catch((caught: unknown) => {
        if (cancelled) return
        setBackups([])
        setError(errorMessage(caught, LIST_FALLBACK))
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const trigger = useCallback(async () => {
    setIsTriggering(true)
    setTriggerError(null)
    try {
      const result = await triggerAdminBackup()
      // The newly created file is already persisted by the backend, but the
      // local cache predates it; refresh so the row appears in the table.
      setReloadKey((current) => current + 1)
      return result
    } catch (caught: unknown) {
      setTriggerError(errorMessage(caught, TRIGGER_FALLBACK))
      throw caught
    } finally {
      setIsTriggering(false)
    }
  }, [])

  const remove = useCallback(async (filename: string) => {
    setIsRemoving(true)
    setRemoveError(null)
    try {
      await deleteAdminBackup(filename)
      setReloadKey((current) => current + 1)
    } catch (caught: unknown) {
      setRemoveError(errorMessage(caught, REMOVE_FALLBACK))
      throw caught
    } finally {
      setIsRemoving(false)
    }
  }, [])

  return {
    backups,
    isLoading,
    error,
    refresh,
    isTriggering,
    triggerError,
    trigger,
    isRemoving,
    removeError,
    remove,
  }
}
