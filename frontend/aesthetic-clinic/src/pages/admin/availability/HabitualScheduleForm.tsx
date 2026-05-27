import type { FormEvent } from 'react'

import { SectionCard } from '../../../components/admin/SectionCard'
import { buildEmptyHabitualForm, toggleSelection } from './availabilityHelpers'
import type { HabitualFormType, SpecialistOption, WeekdayOption } from './availabilityHelpers'

interface HabitualScheduleFormProps {
  habitualForm: HabitualFormType
  setHabitualForm: React.Dispatch<React.SetStateAction<HabitualFormType>>
  editingHabitualId: number | null
  setEditingHabitualId: React.Dispatch<React.SetStateAction<number | null>>
  specialists: SpecialistOption[]
  weekdayOptions: WeekdayOption[]
  activeBranch: { id: number; nombre: string }
  isSubmitting: boolean
  onSubmit: (e: FormEvent) => void
}

export function HabitualScheduleForm({
  habitualForm,
  setHabitualForm,
  editingHabitualId,
  setEditingHabitualId,
  specialists,
  weekdayOptions,
  activeBranch,
  isSubmitting,
  onSubmit,
}: HabitualScheduleFormProps) {
  return (
    <SectionCard
      title={editingHabitualId ? 'Editar agenda habitual' : 'Nueva agenda habitual'}
      description="Configura un horario recurrente. El sistema cruzara este horario con las reservas para validar disponibilidad."
    >
      <form className="form-stack" onSubmit={(e) => void onSubmit(e)}>
        <div className="form-group">
          <label>{editingHabitualId ? 'Especialista' : 'Especialista(s)'}</label>
          {editingHabitualId ? (
            <select
              className="input"
              value={habitualForm.specialistId || ''}
              onChange={(e) => setHabitualForm({ ...habitualForm, specialistId: Number(e.target.value) || null })}
              required
            >
              <option value="">Seleccione un especialista...</option>
              {specialists.map((sp) => (
                <option key={sp.id} value={sp.id}>
                  {sp.label}
                </option>
              ))}
            </select>
          ) : (
            <div
              className="checkbox-group"
              style={{
                maxHeight: '150px',
                overflowY: 'auto',
                border: '1px solid var(--border)',
                padding: '0.5rem',
                borderRadius: '4px',
                background: 'var(--bg-card)',
              }}
            >
              {specialists.map((sp) => (
                <label
                  key={sp.id}
                  className="checkbox-label"
                  style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', cursor: 'pointer' }}
                >
                  <input
                    type="checkbox"
                    checked={habitualForm.specialistIds.includes(sp.id)}
                    onChange={() =>
                      setHabitualForm({
                        ...habitualForm,
                        specialistIds: toggleSelection(habitualForm.specialistIds, sp.id),
                      })
                    }
                  />
                  <span>{sp.label}</span>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label>Fecha de inicio</label>
            <input
              type="date"
              className="input"
              value={habitualForm.startDate}
              onChange={(e) => setHabitualForm({ ...habitualForm, startDate: e.target.value })}
              required
            />
          </div>
          <div>
            <label>Fecha de fin (opcional)</label>
            <input
              type="date"
              className="input"
              value={habitualForm.endDate}
              onChange={(e) => setHabitualForm({ ...habitualForm, endDate: e.target.value })}
            />
          </div>
        </div>

        <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label>Hora Inicio</label>
            <input
              type="time"
              className="input"
              value={habitualForm.startTime}
              onChange={(e) => setHabitualForm({ ...habitualForm, startTime: e.target.value })}
              required
            />
          </div>
          <div>
            <label>Hora Fin</label>
            <input
              type="time"
              className="input"
              value={habitualForm.endTime}
              onChange={(e) => setHabitualForm({ ...habitualForm, endTime: e.target.value })}
              required
            />
          </div>
        </div>

        <div className="form-group">
          <label>Dias de atencion</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
            {weekdayOptions.map((w) => (
              <label key={w.value} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'var(--c-neutral-100)', padding: '0.25rem 0.5rem', borderRadius: '4px' }}>
                <input
                  type="checkbox"
                  checked={habitualForm.weekdayCodes.includes(w.value)}
                  onChange={() =>
                    setHabitualForm({ ...habitualForm, weekdayCodes: toggleSelection(habitualForm.weekdayCodes, w.value) })
                  }
                />
                <span style={{ fontSize: '0.875rem' }}>{w.label}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="form-group">
          <label>Detalle interno</label>
          <input
            type="text"
            className="input"
            value={habitualForm.detail}
            onChange={(e) => setHabitualForm({ ...habitualForm, detail: e.target.value })}
            placeholder="Ej. Turno mañana cardiologia"
          />
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button type="submit" className="button button--primary" disabled={isSubmitting}>
            {isSubmitting ? 'Guardando...' : 'Guardar agenda'}
          </button>
          {editingHabitualId && (
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                setEditingHabitualId(null)
                setHabitualForm(buildEmptyHabitualForm(activeBranch.id))
              }}
            >
              Cancelar
            </button>
          )}
        </div>
      </form>
    </SectionCard>
  )
}