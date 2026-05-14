import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { StatusBadge } from '../../components/admin/StatusBadge'

export function SpecialistMessagesPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Portal de especialista"
        title="Mensajeria interna"
        description="Comunicacion estilo correo con administracion de sucursal."
      />

      <SectionCard
        eyebrow="Redactar"
        title="Nuevo mensaje"
        description="Adjunta documentos o imagenes."
      >
        <form className="form-stack" onSubmit={(e) => e.preventDefault()}>
          <div className="form-group">
            <label>Para</label>
            <input className="input" value="Administrador Sucursal Norte" readOnly />
          </div>
          <div className="form-group">
            <label>Asunto</label>
            <input className="input" />
          </div>
          <div className="form-group">
            <label>Mensaje</label>
            <textarea className="input" rows={6} />
          </div>
          <div className="form-group">
            <label>Adjuntar imagenes o documentos</label>
            <input className="input" type="file" multiple accept="image/*,.pdf,.doc,.docx" />
          </div>
          <button className="button" type="submit">
            Enviar mensaje
          </button>
        </form>
      </SectionCard>

      <SectionCard
        eyebrow="Bandeja"
        title="Historial de mensajes"
        description="Comunicaciones recientes con administracion."
      >
        <div className="table-card">
          <table>
            <thead>
              <tr>
                <th>Estado</th>
                <th>Asunto</th>
                <th>Remitente</th>
                <th>Fecha</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <StatusBadge tone="warning">Nuevo</StatusBadge>
                </td>
                <td>Ajuste de horarios por mantenimiento</td>
                <td>Admin Norte</td>
                <td>2026-05-14 09:20</td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  )
}
