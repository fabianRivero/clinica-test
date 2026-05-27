import type { FormEvent } from 'react'

import { toggleSelection } from './availabilityHelpers'
import type { ExceptionFormType, SpecialistOption, WeekdayOption } from './availabilityHelpers'

interface ExceptionFormProps {
  exceptionForm: ExceptionFormType
  setExceptionForm: React.Dispatch<React.SetStateAction<ExceptionFormType>>
  specialists: SpecialistOption[]
  weekdayOptions: WeekdayOption[]
  isSubmitting: boolean
  onSubmit: (e: FormEvent) => void
}

export function ExceptionForm({
  exceptionForm,
  setExceptionForm,
  specialists,
  weekdayOptions,
  isSubmitting,
  onSubmit,
}: ExceptionFormProps) {
  return (
    <form className="form-stack" onSubmit={(e) => void onSubmit(e)}>
      <div className="form-group">
        <label>Especialistas afectados</label>
        <div className="checkbox-group" style={{ maxHeight: '150px', overflowY: 'auto', border: '1px solid var(--border)', padding: '0.5rem', borderRadius: '4px', background: 'var(--bg-card)' }}>
          {specialists.map((sp) => (
            <label key={sp.id} className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={exceptionForm.specialistIds.includes(sp.id)}
                onChange={() => setExceptionForm({ ...exceptionForm, specialistIds: toggleSelection(exceptionForm.specialistIds, sp.id) })}
              />
              <span>{sp.label}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="form-group">
        <label>Tipo de excepcion</label>
        <select
          className="input"
          value={exceptionForm.type}
          onChange={(e) => setExceptionForm({ ...exceptionForm, type: e.target.value as 'AGREGAR' | 'BLOQUEAR' })}
          required
        >
          <option value="BLOQUEAR">Bloquear disponibilidad (Dia libre / Permiso)</option>
          <option value="AGREGAR">Añadir disponibilidad extra</option>
        </select>
      </div>

      <div className="form-group">
        <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={exceptionForm.isWholeDay}
            onChange={(e) => setExceptionForm({ ...exceptionForm, isWholeDay: e.target.checked })}
          />
          <span>Afecta a todo el dia (Sin restriccion de horas)</span>
        </label>
      </div>

      {!exceptionForm.isWholeDay && (
        <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div>
            <label>Hora Inicio</label>
            <input
              type="time"
              className="input"
              value={exceptionForm.startTime}
              onChange={(e) => setExceptionForm({ ...exceptionForm, startTime: e.target.value })}
              required
            />
          </div>
          <div>
            <label>Hora Fin</label>
            <input
              type="time"
              className="input"
              value={exceptionForm.endTime}
              onChange={(e) => setExceptionForm({ ...exceptionForm, endTime: e.target.value })}
              required
            />
          </div>
        </div>
      )}

      <div className="form-group">
        <label className="checkbox-label" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={exceptionForm.useDateRange}
            onChange={(e) => setExceptionForm({ ...exceptionForm, useDateRange: e.target.checked })}
          />
          <span>Usar rango de fechas con dias de semana</span>
        </label>
      </div>

      {exceptionForm.useDateRange && (
        <>
          <div className="form-group" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label>Desde</label>
              <input type="date" className="input" value={exceptionForm.rangeStartDate} onChange={(e) => setExceptionForm({ ...exceptionForm, rangeStartDate: e.target.value })} />
            </div>
            <div>
              <label>Hasta</label>
              <input type="date" className="input" value={exceptionForm.rangeEndDate} onChange={(e) => setExceptionForm({ ...exceptionForm, rangeEndDate: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label>Dias de la semana a aplicar</label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
              {weekdayOptions.map((w) => (
                <label key={w.value} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', background: 'var(--c-neutral-100)', padding: '0.25rem 0.5rem', borderRadius: '4px' }}>
                  <input
                    type="checkbox"
                    checked={exceptionForm.rangeWeekdayCodes.includes(w.value)}
                    onChange={() => setExceptionForm({ ...exceptionForm, rangeWeekdayCodes: toggleSelection(exceptionForm.rangeWeekdayCodes, w.value) })}
                  />
                  <span style={{ fontSize: '0.875rem' }}>{w.label}</span>
                </label>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="form-group">
        <label>Añadir Fecha(s)</label>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="date"
            className="input"
            value={exceptionForm.dateInput}
            onChange={(e) => setExceptionForm({ ...exceptionForm, dateInput: e.target.value })}
          />
          <button
            type="button"
            className="button button--ghost"
            onClick={() => {
              if (exceptionForm.dateInput && !exceptionForm.dates.includes(exceptionForm.dateInput)) {
                setExceptionForm({
                  ...exceptionForm,
                  dates: [...exceptionForm.dates, exceptionForm.dateInput].sort(),
                  dateInput: '',
                })
              }
            }}
          >
            Añadir
          </button>
        </div>
      </div>

      {exceptionForm.dates.length > 0 && (
        <div className="form-group">
          <label>Fechas seleccionadas</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
            {exceptionForm.dates.map((d) => (
              <div key={d} className="status-badge status-badge--primary">
                {d}
                <button
                  type="button"
                  onClick={() => setExceptionForm({ ...exceptionForm, dates: exceptionForm.dates.filter((x) => x !== d) })}
                  style={{ background: 'none', border: 'none', marginLeft: '0.5rem', cursor: 'pointer', color: 'inherit' }}
                >
                  x
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="form-group">
        <label>Motivo / Detalle</label>
        <input
          type="text"
          className="input"
          value={exceptionForm.detail}
          onChange={(e) => setExceptionForm({ ...exceptionForm, detail: e.target.value })}
          placeholder="Ej. Congreso medico, Vacaciones, Hora extra feriado"
        />
      </div>

      <button className="button button--primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Guardando...' : 'Aplicar excepcion'}
      </button>
    </form>
  )
}