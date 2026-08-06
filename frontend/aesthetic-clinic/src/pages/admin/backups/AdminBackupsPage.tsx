import { useEffect, useMemo, useState } from 'react'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'
import { useNotifications } from '../../../providers/NotificationProvider'
import type { BackupFile } from '../../../types/admin'

import { BackupTable } from './BackupTable'
import { TriggerBackupModal } from './TriggerBackupModal'
import { useBackups } from './useBackups'

const PAGE_TITLE = 'Respaldos de base de datos'
const PAGE_EYEBROW = 'Respaldos'

const LOADING_TITLE = 'Cargando respaldos'
const LOADING_MESSAGE = 'Listando los respaldos disponibles en el servidor.'
const ERROR_TITLE = 'No se pudieron cargar los respaldos'
const EMPTY_TITLE = 'Aun no hay respaldos generados'
const EMPTY_MESSAGE =
  "Pulsa 'Crear respaldo' para generar el primero. Conservamos hasta 7 diarios y 4 semanales automaticamente."

/**
 * Save a Blob via a programmatic anchor. The clinic SPA does not depend on
 * `file-saver`; we mirror the same approach used by the XLSX export path,
 * which funnels through `URL.createObjectURL` + a synthetic `<a>` click.
 * Returns true when the browser accepted the save.
 */
function saveBlob(blob: Blob, filename: string): boolean {
  if (typeof document === 'undefined' || typeof URL === 'undefined') return false
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  // Release the URL after the click is dispatched.
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
  return true
}

/**
 * Admin Backups page. Composes `PageHeader` + the trigger button + the
 * `BackupTable` inside a `SectionCard`. Two modals cover the user-facing
 * confirmation steps:
 *   - `TriggerBackupModal` for "create + download"
 *   - `useConfirmDialog` for the per-row delete confirmation
 *
 * The page deliberately re-uses the same layout primitives as the rest of
 * the admin area so reviewers do not have to learn a new design language.
 */
export function AdminBackupsPage() {
  const {
    backups,
    isLoading,
    error,
    isTriggering,
    triggerError,
    trigger,
    isRemoving,
    removeError,
    remove,
  } = useBackups()
  const { showNotification } = useNotifications()
  const [isTriggerModalOpen, setIsTriggerModalOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<BackupFile | null>(null)

  const knownFilenames = useMemo(
    () => new Set(backups.map((row) => row.id || row.name)),
    [backups],
  )

  // Surface stored errors from `useBackups` as toast notifications so the
  // user does not have to inspect the table state to learn what failed. The
  // initial load error renders inline via the `error` data branch.
  useEffect(() => {
    if (removeError) {
      showNotification({
        title: 'No se pudo eliminar el respaldo',
        message: removeError,
        tone: 'danger',
      })
    }
  }, [removeError, showNotification])

  const handleTriggerConfirm = async () => {
    try {
      const { blob, filename } = await trigger()
      const finalName = filename || `clinica_${new Date().toISOString().replace(/[:.]/g, '-')}.dump`
      saveBlob(blob, finalName)
      setIsTriggerModalOpen(false)
      showNotification({
        title: 'Respaldo generado',
        message: `Descarga iniciada: ${finalName}`,
        tone: 'success',
      })
    } catch (caught: unknown) {
      // The `useBackups` hook stores the same message in `triggerError` so
      // the modal can render it inline, but we also flash a toast to match
      // every other admin action.
      showNotification({
        title: 'No se pudo generar el respaldo',
        message: caught instanceof Error ? caught.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
    }
  }

  const handleRequestDelete = (row: BackupFile) => {
    setPendingDelete(row)
  }

  const handleConfirmDelete = async () => {
    const target = pendingDelete
    if (!target) return
    const targetKey = target.id || target.name
    try {
      await remove(target.name)
      showNotification({
        title: 'Respaldo eliminado',
        message: `${target.name} ya no esta disponible.`,
        tone: 'success',
      })
      setPendingDelete(null)
    } catch (caught: unknown) {
      showNotification({
        title: 'No se pudo eliminar',
        message: caught instanceof Error ? caught.message : 'Intenta nuevamente en unos segundos.',
        tone: 'danger',
      })
      // Keep the modal context active so the user can retry; only close on
      // success.
      if (!knownFilenames.has(targetKey)) {
        setPendingDelete(null)
      }
    }
  }

  const triggerErrorToShow = triggerError

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={PAGE_EYEBROW}
        title={PAGE_TITLE}
        description="Genera, descarga y elimina respaldos completos de la base de datos clinica."
      />

      {isLoading && backups.length === 0 ? (
        <SectionCard title={LOADING_TITLE}>
          <DataState title={LOADING_TITLE} message={LOADING_MESSAGE} />
        </SectionCard>
      ) : null}

      {!isLoading && error && backups.length === 0 ? (
        <SectionCard title={ERROR_TITLE}>
          <DataState title={ERROR_TITLE} message={error} tone="danger" />
        </SectionCard>
      ) : null}

      {backups.length > 0 || (!isLoading && !error) ? (
        <SectionCard
          title={PAGE_TITLE}
          description="Lista de archivos generados. Los semanales se conservan 4 semanas, los diarios 7 dias."
          action={
            <button
              className="button"
              data-testid="backup-trigger-open"
              disabled={isTriggering}
              type="button"
              onClick={() => {
                setIsTriggerModalOpen(true)
              }}
            >
              {isTriggering ? 'Generando...' : 'Descargar respaldo ahora'}
            </button>
          }
        >
          {backups.length ? (
            <BackupTable
              pendingDeleteName={pendingDelete ? pendingDelete.id || pendingDelete.name : null}
              rows={backups}
              onRequestDelete={handleRequestDelete}
            />
          ) : (
            <DataState title={EMPTY_TITLE} message={EMPTY_MESSAGE} />
          )}
        </SectionCard>
      ) : null}

      <TriggerBackupModal
        errorMessage={triggerErrorToShow}
        isOpen={isTriggerModalOpen}
        isSubmitting={isTriggering}
        onCancel={() => {
          if (!isTriggering) setIsTriggerModalOpen(false)
        }}
        onConfirm={() => {
          void handleTriggerConfirm()
        }}
      />

      {pendingDelete ? (
        <div
          aria-label="Confirmar eliminacion de respaldo"
          aria-modal="true"
          className="booking-modal-overlay"
          data-testid="backup-delete-modal"
          role="dialog"
        >
          <div className="booking-modal-content _confirm-modal">
            <header className="booking-modal-header">
              <div>
                <h2 className="_m-0">Eliminar respaldo</h2>
                <p className="_m-0 _text-muted">Esta accion no se puede deshacer.</p>
              </div>
            </header>
            <div className="booking-modal-body _p-modal">
              <p className="_m-0 _white-space-pre">
                {`¿Eliminar el respaldo ${pendingDelete.name}? Esta accion no se puede deshacer.`}
              </p>
              <div className="_flex-end _flex-gap-md _mt-md">
                <button
                  className="button button--ghost"
                  disabled={isRemoving}
                  type="button"
                  onClick={() => setPendingDelete(null)}
                >
                  Cancelar
                </button>
                <button
                  className="button button--danger"
                  data-testid="backup-delete-confirm"
                  disabled={isRemoving}
                  type="button"
                  onClick={() => {
                    void handleConfirmDelete()
                  }}
                >
                  {isRemoving ? 'Eliminando...' : 'Eliminar'}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
