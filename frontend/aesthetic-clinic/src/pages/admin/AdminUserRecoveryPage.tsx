import {
  useCallback,
  useMemo,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'
import { useNotifications } from '../../providers/NotificationProvider'
import { searchAdminUserRecovery, postAdminUserRecoveryReset } from '../../services/api/admin'
import type {
  AdminUserRecoveryItem,
  AdminUserRecoveryKind,
  AdminUserRecoveryResetResponse,
  AdminUserRecoverySearchResponse,
} from '../../types/admin'

/**
 * Admin-assisted user recovery page.
 *
 * Backs the `/cms/equipo/recuperar` route. Lets an admin look up any
 * user (cliente, trabajador, branch admin, main admin) by username,
 * name, email, phone, or CI, then either reveal their username or
 * trigger a password reset.
 *
 * This file owns commit 6 of the feature branch: search input,
 * results table, and the "Ver username" modal. The "Resetear
 * contrasena" modal is wired up in commit 7. The page is reachable
 * from a direct URL but not yet exposed in any sidebar/tab — that
 * link lands in commit 9.
 */

const KIND_LABEL: Record<AdminUserRecoveryKind, string> = {
  admin_principal: 'Admin principal',
  admin_sucursal: 'Admin sucursal',
  trabajador: 'Trabajador',
  cliente: 'Cliente',
  otro: 'Otro',
}

const KIND_TONE: Record<
  AdminUserRecoveryKind,
  'primary' | 'success' | 'warning' | 'neutral'
> = {
  admin_principal: 'warning',
  admin_sucursal: 'primary',
  trabajador: 'success',
  cliente: 'neutral',
  otro: 'neutral',
}

type UsernameModalState = {
  open: boolean
  user: AdminUserRecoveryItem | null
}

/**
 * Reset modal phases:
 *  - 'confirm' — admin sees who they are about to reset and the
 *    blast radius ("session cerrada, debera cambiar al entrar").
 *  - 'result' — backend responded OK; the temporary password is
 *    stored here only while the modal is open. The state is wiped
 *    on close so the password never lingers in React state beyond
 *    the lifetime of the modal.
 */
type ResetModalState =
  | { phase: 'closed' }
  | { phase: 'confirm'; user: AdminUserRecoveryItem; isSubmitting: boolean; error: string | null }
  | { phase: 'result'; user: AdminUserRecoveryItem; response: AdminUserRecoveryResetResponse }

export function AdminUserRecoveryPage() {
  const { showNotification } = useNotifications()
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [searchResults, setSearchResults] = useState<AdminUserRecoveryItem[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [usernameModal, setUsernameModal] = useState<UsernameModalState>({
    open: false,
    user: null,
  })

  const runSearch = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      setSubmittedQuery(trimmed)
      setHasSearched(true)
      if (!trimmed) {
        setSearchResults([])
        setSearchError(null)
        return
      }
      setIsSearching(true)
      setSearchError(null)
      try {
        const response: AdminUserRecoverySearchResponse =
          await searchAdminUserRecovery(trimmed)
        setSearchResults(response.users)
      } catch (requestError) {
        setSearchError(
          requestError instanceof Error
            ? requestError.message
            : 'No se pudo realizar la busqueda.',
        )
        setSearchResults([])
      } finally {
        setIsSearching(false)
      }
    },
    [],
  )

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    runSearch(query)
  }

  const handleQueryChange = (event: ChangeEvent<HTMLInputElement>) => {
    const next = event.target.value
    setQuery(next)
    // Auto-trigger an empty search when the operator clears the input so
    // the result panel stays in sync with the visible query.
    if (next.trim() === '' && submittedQuery !== '') {
      runSearch('')
    }
  }

  const handleOpenUsername = (user: AdminUserRecoveryItem) => {
    setUsernameModal({ open: true, user })
  }

  const handleCloseUsername = () => {
    setUsernameModal({ open: false, user: null })
  }

  const handleCopyUsername = async (username: string) => {
    try {
      await navigator.clipboard.writeText(username)
      showNotification({
        title: 'Username copiado',
        message: 'Lo pegamos al portapapeles.',
        tone: 'success',
      })
    } catch {
      showNotification({
        title: 'No se pudo copiar',
        message:
          'Tu navegador bloqueo el portapapeles. Copialo manualmente.',
        tone: 'danger',
      })
    }
  }

  const [resetModal, setResetModal] = useState<ResetModalState>({ phase: 'closed' })

  const handleOpenReset = (user: AdminUserRecoveryItem) => {
    setResetModal({ phase: 'confirm', user, isSubmitting: false, error: null })
  }

  const handleCloseReset = () => {
    // Wipe the state on close so the temporary password doesn't linger
    // in React state beyond the modal's lifetime.
    setResetModal({ phase: 'closed' })
  }

  const handleConfirmReset = async () => {
    if (resetModal.phase !== 'confirm') return
    setResetModal({ ...resetModal, isSubmitting: true, error: null })
    try {
      const response = await postAdminUserRecoveryReset(resetModal.user.id)
      setResetModal({ phase: 'result', user: resetModal.user, response })
      showNotification({
        title: 'Contrasena temporal generada',
        message: 'La cuenta fue marcada para forzar cambio en el proximo login.',
        tone: 'success',
      })
    } catch (requestError) {
      setResetModal({
        ...resetModal,
        isSubmitting: false,
        error:
          requestError instanceof Error
            ? requestError.message
            : 'No se pudo resetear la contrasena.',
      })
    }
  }

  const handleCopyTemporaryPassword = async (password: string) => {
    try {
      await navigator.clipboard.writeText(password)
      showNotification({
        title: 'Contrasena copiada',
        message: 'Pegala en un canal seguro antes de cerrar esta pantalla.',
        tone: 'success',
      })
    } catch {
      showNotification({
        title: 'No se pudo copiar',
        message:
          'Tu navegador bloqueo el portapapeles. Anotala manualmente.',
        tone: 'danger',
      })
    }
  }

  const rows = useMemo(() => searchResults, [searchResults])

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Equipo"
        title="Recuperar acceso de usuario"
        description="Busca un usuario por nombre, email, CI o telefono y, desde aca, podes ver su username o resetear su contrasena. Solo accesible para administradores."
      />

      <SectionCard
        eyebrow="Busqueda"
        title="Buscar usuario"
        description="Busca por nombre completo, email, telefono, CI o nombre de usuario."
      >
        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="field field--full">
            <span>Criterio de busqueda</span>
            <input
              className="input"
              type="search"
              name="q"
              value={query}
              onChange={handleQueryChange}
              placeholder="Ej. Fabian Rivero, fabian.rivero, fabian@ejemplo.com, 70000000, 6777132"
              autoComplete="off"
              maxLength={120}
              aria-label="Buscar usuario por nombre, email, telefono o CI"
            />
          </label>
          <div className="form-actions field--full">
            <button className="button" type="submit" disabled={isSearching}>
              {isSearching ? 'Buscando...' : 'Buscar'}
            </button>
          </div>
        </form>
      </SectionCard>

      <SectionCard
        eyebrow="Resultados"
        title={submittedQuery ? `Coincidencias para "${submittedQuery}"` : 'Resultados'}
        description={
          hasSearched
            ? `${rows.length} usuario(s) encontrado(s).`
            : 'Todavia no realizaste una busqueda.'
        }
      >
        {isSearching ? (
          <DataState title="Buscando" message="Consultando al backend..." />
        ) : searchError ? (
          <DataState
            title="No pudimos realizar la busqueda"
            message={searchError}
            tone="danger"
          />
        ) : !hasSearched ? (
          <DataState
            title="Esperando una busqueda"
            message="Ingresa un criterio arriba y presiona Buscar. Buscar por nombre completo funciona mejor si el usuario recuerda su nombre real."
          />
        ) : rows.length === 0 ? (
          <DataState
            title="Sin coincidencias"
            message={
              submittedQuery
                ? `No hay usuarios que coincidan con "${submittedQuery}".`
                : 'No hay resultados para mostrar.'
            }
          />
        ) : (
          <div className="table-card">
            <table>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Nombre</th>
                  <th>Rol</th>
                  <th>Sucursal</th>
                  <th>Estado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((user) => (
                  <tr key={user.id}>
                    <td>
                      <code>{user.username}</code>
                    </td>
                    <td>
                      <strong>{user.fullName}</strong>
                      <span>
                        {[user.email, user.telefono, user.ci]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    </td>
                    <td>
                      <StatusBadge tone={KIND_TONE[user.kind]}>
                        {KIND_LABEL[user.kind]}
                      </StatusBadge>
                    </td>
                    <td>{user.sucursal || '—'}</td>
                    <td>
                      <StatusBadge tone={user.isActive ? 'success' : 'neutral'}>
                        {user.isActive ? 'Activo' : 'Inactivo'}
                      </StatusBadge>
                      {user.mustChangePassword ? (
                        <>
                          {' '}
                          <StatusBadge tone="warning">
                            Debe cambiar password
                          </StatusBadge>
                        </>
                      ) : null}
                    </td>
                    <td>
                      <div className="table-actions">
                        <button
                          className="button button--ghost button--compact"
                          type="button"
                          onClick={() => handleOpenUsername(user)}
                        >
                          Ver username
                        </button>
                        <button
                          className="button button--warning button--compact"
                          type="button"
                          onClick={() => handleOpenReset(user)}
                        >
                          Resetear contrasena
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {usernameModal.open && usernameModal.user ? (
        <div
          className="qr-modal"
          role="dialog"
          aria-modal="true"
          aria-label="Username del usuario"
        >
          <div
            className="qr-modal__backdrop"
            onClick={handleCloseUsername}
          />
          <div className="qr-modal__content">
            <header className="qr-modal__header">
              <div>
                <span>Username</span>
                <strong>{usernameModal.user.fullName}</strong>
              </div>
              <button
                className="button button--ghost button--compact"
                type="button"
                onClick={handleCloseUsername}
              >
                Cerrar
              </button>
            </header>
            <div className="form-grid" style={{ marginTop: '1rem' }}>
              <label className="field field--full">
                <span>Nombre de usuario</span>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input
                    className="input"
                    readOnly
                    value={usernameModal.user.username}
                    aria-label="Username del usuario"
                    onFocus={(event) => event.currentTarget.select()}
                  />
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => handleCopyUsername(usernameModal.user!.username)}
                  >
                    Copiar
                  </button>
                </div>
              </label>
            </div>
            <p className="field__hint" style={{ marginTop: '0.75rem' }}>
              Este username no se guarda en esta pantalla. Anotalo si lo
              necesitas.
            </p>
          </div>
        </div>
      ) : null}

      {resetModal.phase !== 'closed' ? (
        <div
          className="qr-modal"
          role="dialog"
          aria-modal="true"
          aria-label="Resetear contrasena"
        >
          <div
            className="qr-modal__backdrop"
            onClick={
              resetModal.phase === 'confirm' && resetModal.isSubmitting
                ? undefined
                : handleCloseReset
            }
          />
          <div className="qr-modal__content">
            <header className="qr-modal__header">
              <div>
                {resetModal.phase === 'confirm' ? (
                  <>
                    <span>Resetear contrasena</span>
                    <strong>{resetModal.user.fullName}</strong>
                  </>
                ) : (
                  <>
                    <span>Contrasena temporal generada</span>
                    <strong>{resetModal.user.fullName}</strong>
                  </>
                )}
              </div>
              {!(
                resetModal.phase === 'confirm' && resetModal.isSubmitting
              ) ? (
                <button
                  className="button button--ghost button--compact"
                  type="button"
                  onClick={handleCloseReset}
                >
                  Cerrar
                </button>
              ) : null}
            </header>

            {resetModal.phase === 'confirm' ? (
              <div style={{ marginTop: '1rem' }}>
                <p>
                  Vas a generar una contrasena temporal para este usuario. La
                  cuenta sera marcada para forzar el cambio en el proximo
                  inicio de sesion y todas las sesiones abiertas se cerraran.
                </p>
                <p
                  className="field__hint"
                  style={{
                    background: 'rgba(245, 158, 11, 0.12)',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '0.375rem',
                    marginTop: '0.75rem',
                  }}
                >
                  El usuario debera cambiar la contrasena apenas entre.
                  Anotala antes de cerrar esta pantalla — no la veras de
                  nuevo.
                </p>
                {resetModal.error ? (
                  <div
                    className="form-error"
                    style={{ marginTop: '0.75rem' }}
                  >
                    {resetModal.error}
                  </div>
                ) : null}
                <div
                  className="form-actions"
                  style={{ marginTop: '1rem' }}
                >
                  <button
                    className="button button--ghost"
                    type="button"
                    onClick={handleCloseReset}
                    disabled={resetModal.isSubmitting}
                  >
                    Cancelar
                  </button>
                  <button
                    className="button"
                    type="button"
                    onClick={handleConfirmReset}
                    disabled={resetModal.isSubmitting}
                  >
                    {resetModal.isSubmitting
                      ? 'Generando...'
                      : 'Generar contrasena temporal'}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ marginTop: '1rem' }}>
                <div
                  className="field__hint"
                  style={{
                    background: 'rgba(245, 158, 11, 0.12)',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '0.375rem',
                  }}
                >
                  Esta contrasena se muestra una sola vez. Se invalidaron
                  todas las sesiones activas del usuario.
                </div>
                <label className="field" style={{ marginTop: '1rem' }}>
                  <span>Contrasena temporal</span>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <input
                      className="input"
                      readOnly
                      value={resetModal.response.temporaryPassword}
                      aria-label="Contrasena temporal"
                      onFocus={(event) =>
                        event.currentTarget.select()
                      }
                      style={{ fontFamily: 'monospace', letterSpacing: '0.05em' }}
                    />
                    <button
                      className="button button--secondary"
                      type="button"
                      onClick={() =>
                        handleCopyTemporaryPassword(
                          resetModal.response.temporaryPassword,
                        )
                      }
                    >
                      Copiar
                    </button>
                  </div>
                </label>
                <p
                  className="field__hint"
                  style={{ marginTop: '0.75rem' }}
                >
                  Pegala en un canal seguro (presencial, telefono) antes de
                  cerrar esta ventana.
                </p>
                <div
                  className="form-actions"
                  style={{ marginTop: '1rem' }}
                >
                  <button
                    className="button"
                    type="button"
                    onClick={handleCloseReset}
                  >
                    Cerrar
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}