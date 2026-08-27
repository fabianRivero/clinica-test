import type {
  EspecialistaDisponibilidad,
  MaquinariaDisponibilidad,
} from '../../../types/admin'

interface RecursosDisponibilidadPanelProps {
  /** Per-maquinaria availability from GET check-maquinaria. */
  maquinaria: MaquinariaDisponibilidad[]
  /** Per-specialist availability from GET check-especialistas. */
  especialistas: EspecialistaDisponibilidad[]
}

/**
 * Always-on panel that lists each requested resource (maquinaria and
 * especialista) with the citas that already use it in the window. The
 * admin uses this to confirm availability before confirming the
 * reservation, alongside the existing concurrency panel (citas 1h±) and
 * the MaquinariaConflictList (warn-only when over-assigned).
 *
 * Renders nothing when both lists are empty (e.g. the admin selected no
 * maquinaria and no especialistas).
 */
export function RecursosDisponibilidadPanel({
  maquinaria,
  especialistas,
}: RecursosDisponibilidadPanelProps) {
  if (maquinaria.length === 0 && especialistas.length === 0) return null

  return (
    <div className="_panel-card _mt-md" data-testid="recursos-disponibilidad">
      <p className="_mb-sm _font-bold">Disponibilidad por recurso</p>
      <p className="_text-soft _mb-sm" style={{ fontSize: '0.85rem' }}>
        Citas que ya tienen asignada la maquinaria o el especialista en esta ventana.
      </p>

      {maquinaria.length > 0 ? (
        <section className="_mb-md">
          <h4 className="_mt-0 _mb-sm">Maquinaria</h4>
          {maquinaria.map((m) => (
            <RecursoMaquinariaRow key={m.maquinariaId} item={m} />
          ))}
        </section>
      ) : null}

      {especialistas.length > 0 ? (
        <section>
          <h4 className="_mt-0 _mb-sm">Especialistas</h4>
          {especialistas.map((e) => (
            <RecursoEspecialistaRow key={e.especialistaId} item={e} />
          ))}
        </section>
      ) : null}
    </div>
  )
}

function RecursoMaquinariaRow({ item }: { item: MaquinariaDisponibilidad }) {
  const tone = item.sobreAsignada ? '_text-danger' : '_text-success'
  const headerLabel = `${item.nombre} — ${item.cantidadSolicitada} solicitada(s), ${item.cantidadDisponible} disponible(s) de ${item.cantidadTotal}`
  return (
    <article
      className="_mt-sm"
      data-testid="recurso-maquinaria-item"
      style={{
        paddingLeft: '0.5rem',
        borderLeft: item.sobreAsignada
          ? '2px solid var(--color-danger, #c0392b)'
          : '2px solid var(--color-success, #2c7)',
      }}
    >
      <p className={`_mb-sm ${tone}`}>
        <strong>{headerLabel}</strong>
      </p>
      {item.citasQueLaUsan.length === 0 ? (
        <p className="_text-soft" style={{ fontSize: '0.82rem' }}>
          Sin citas asignadas en esta ventana.
        </p>
      ) : (
        <ul
          style={{
            fontSize: '0.82rem',
            color: 'var(--color-text-soft)',
            paddingLeft: '1.2rem',
            margin: 0,
          }}
        >
          {item.citasQueLaUsan.map((cita) => (
            <li key={cita.citaId} style={{ marginBottom: '0.3rem' }}>
              <span style={{ fontWeight: 500 }}>{cita.cliente}</span>
              {' — '}
              {cita.fecha}
              {' '}
              {cita.horaInicio}
              {cita.horaFin !== cita.horaInicio ? ` a ${cita.horaFin}` : ''}
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}

function RecursoEspecialistaRow({
  item,
}: {
  item: EspecialistaDisponibilidad
}) {
  const libre = item.citasAsignadas.length === 0
  const tone = libre ? '_text-success' : ''
  return (
    <article
      className="_mt-sm"
      data-testid="recurso-especialista-item"
      style={{
        paddingLeft: '0.5rem',
        borderLeft: libre
          ? '2px solid var(--color-success, #2c7)'
          : '2px solid var(--color-border)',
      }}
    >
      <p className={`_mb-sm ${tone}`}>
        <strong>{item.nombre}</strong>
        {' — '}
        {libre
          ? 'Sin citas asignadas en esta ventana'
          : `${item.citasAsignadas.length} cita(s) asignada(s)`}
      </p>
      {libre ? null : (
        <ul
          style={{
            fontSize: '0.82rem',
            color: 'var(--color-text-soft)',
            paddingLeft: '1.2rem',
            margin: 0,
          }}
        >
          {item.citasAsignadas.map((cita) => (
            <li key={cita.citaId} style={{ marginBottom: '0.3rem' }}>
              <span style={{ fontWeight: 500 }}>{cita.cliente}</span>
              {' — '}
              {cita.fecha}
              {' '}
              {cita.horaInicio}
              {cita.horaFin !== cita.horaInicio ? ` a ${cita.horaFin}` : ''}
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}