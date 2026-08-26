import type { MaquinariaConflict } from '../../../types/admin'

interface MaquinariaConflictListProps {
  conflicts: MaquinariaConflict[]
  /**
   * Carga de maquinaria solicitada por el admin (suma de todas las filas del
   * modal). La usamos para etiquetar la maquina con un sufijo "+ N solicitada"
   * cuando difiere de la cantidadSolicitada reportada por el backend.
   */
  totalRequested?: number
}

/**
 * Lista los conflictos de maquinaria reportados por
 * `GET /api/admin/disponibilidad/check-maquinaria/`. Cada item describe una
 * maquina con sobre-asignacion: incluye la cantidad solicitada, la disponible
 * y las citas que ya la usan en la ventana. Por diseno del spec, esta lista es
 * SOLO informativa: el boton "Confirmar reserva" sigue habilitado aunque
 * existan conflictos. Nunca se usa para bloquear el envio.
 */
export function MaquinariaConflictList({ conflicts, totalRequested }: MaquinariaConflictListProps) {
  if (!conflicts.length) return null

  return (
    <div className="_panel-card _mt-md" data-testid="maquinaria-conflict-list">
      <p className="_mb-sm _font-bold _text-warning">
        Aviso: hay {conflicts.length} maquina(s) con sobre-asignacion en esta ventana. La
        reserva se puede confirmar de todas formas; el administrador decide.
      </p>
      {conflicts.map((conflict) => {
        const requestedHint =
          totalRequested !== undefined && totalRequested !== conflict.cantidadSolicitada
            ? ` (de ${totalRequested} solicitada(s) en total)`
            : ''
        return (
          <article
            key={conflict.maquinariaId}
            className="_mt-sm"
            data-testid="maquinaria-conflict-item"
            style={{ paddingLeft: '0.5rem', borderLeft: '2px solid var(--color-border)' }}
          >
            <p className="_mb-sm">
              <strong>{conflict.nombre}</strong>
              {' — solicitada: '}
              <span className="_font-bold">{conflict.cantidadSolicitada}{requestedHint}</span>
              {' | disponible: '}
              <span className="_font-bold _text-danger">{conflict.cantidadDisponible}</span>
            </p>
            {conflict.citasQueLaUsan.length ? (
              <ul style={{ fontSize: '0.82rem', color: 'var(--color-text-soft)', paddingLeft: '1.2rem', margin: 0 }}>
                {conflict.citasQueLaUsan.map((cita) => (
                  <li key={cita.citaId} style={{ marginBottom: '0.3rem' }}>
                    <span style={{ fontWeight: 500 }}>{cita.cliente}</span>
                    {' — '}
                    {cita.fecha}
                    {' '}
                    {cita.horaInicio}
                    {' a '}
                    {cita.horaFin}
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
