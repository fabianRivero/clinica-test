import { type ChangeEvent, type FormEvent } from 'react'

import type { ProspectConversionOperationData, ProspectConversionResponse } from '../../../types/prospectConversion'

import { buildDueDateList } from './conversionHelpers'
import type { FieldErrors } from './conversionHelpers'

type Props = {
  operationForm: ProspectConversionOperationData
  selectedService: ProspectConversionResponse['serviceConfigs'][number] | null
  data: ProspectConversionResponse
  fieldErrors: FieldErrors
  today: string
  isSaving: boolean
  isCancelling: boolean
  onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void
  onUpdateDueDate: (index: number, value: string) => void
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  onCancel: () => void
}

export function ConversionStepOperation({
  operationForm,
  selectedService,
  data,
  fieldErrors,
  today,
  isSaving,
  isCancelling,
  onChange,
  onUpdateDueDate,
  onSubmit,
  onBack,
  onCancel,
}: Props) {
  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label className="field field--full">
        <span>Servicio <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <select className="input" name="serviceConfigId" value={operationForm.serviceConfigId} onChange={onChange}>
          <option value="">Seleccionar servicio</option>
          {data.serviceConfigs.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label} | Bs {item.basePrice}
            </option>
          ))}
        </select>
        {fieldErrors.serviceConfigId ? <small className="field__error">{fieldErrors.serviceConfigId}</small> : null}
      </label>

      {selectedService ? (
        <div className="wizard-info-card field--full">
          <strong>{selectedService.label}</strong>
          <p>
            Tipo: {selectedService.serviceType}
            {selectedService.procedureName ? ` | Procedimiento: ${selectedService.procedureName}` : ''}
          </p>
        </div>
      ) : null}

      <label className="field">
        <span>Precio total <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input className="input" name="precioTotal" value={operationForm.precioTotal} onChange={onChange} />
        {fieldErrors.precioTotal ? <small className="field__error">{fieldErrors.precioTotal}</small> : null}
      </label>

      <label className="field">
        <span>Sesiones totales <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input className="input" min="1" name="sesionesTotales" type="number" value={operationForm.sesionesTotales} onChange={onChange} />
        {fieldErrors.sesionesTotales ? <small className="field__error">{fieldErrors.sesionesTotales}</small> : null}
      </label>
      <label className="field">
        <span>Estado de la operacion</span>
        <select className="input" name="estado" value={operationForm.estado} onChange={onChange}>
          {data.operationStates.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        {fieldErrors.estado ? <small className="field__error">{fieldErrors.estado}</small> : null}
      </label>
      <label className="field">
        <span>Fecha de registro</span>
        <input
          className="input"
          name="fechaInicio"
          type="date"
          value={today}
          disabled
        />
        {fieldErrors.fechaInicio ? <small className="field__error">{fieldErrors.fechaInicio}</small> : null}
      </label>

      <label className="field">
        <span>Zona general <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input className="input" name="zonaGeneral" value={operationForm.zonaGeneral} onChange={onChange} />
        {fieldErrors.zonaGeneral ? <small className="field__error">{fieldErrors.zonaGeneral}</small> : null}
      </label>
      <label className="field">
        <span>Zona especifica <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input className="input" name="zonaEspecifica" value={operationForm.zonaEspecifica} onChange={onChange} />
        {fieldErrors.zonaEspecifica ? <small className="field__error">{fieldErrors.zonaEspecifica}</small> : null}
      </label>

      <label className="field">
        <span>Cuotas totales <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input className="input" min="1" name="cuotasTotales" type="number" value={operationForm.cuotasTotales} onChange={onChange} />
        {fieldErrors.cuotasTotales ? <small className="field__error">{fieldErrors.cuotasTotales}</small> : null}
      </label>

      <div className="field field--full">
        <span>Fechas de vencimiento por cuota</span>
        <div className="wizard-list">
          {buildDueDateList(operationForm.cuotasTotales, operationForm.fechasVencimientoCuotas).map((dueDate, index) => (
            <div className="wizard-list__item" key={`cuota-vencimiento-${index}`}>
              <label className="field">
                <span>{`Cuota ${index + 1}`}</span>
                <input
                  className="input"
                  type="date"
                  value={dueDate}
                  onChange={(event) => onUpdateDueDate(index, event.target.value)}
                />
                {fieldErrors[`fechasVencimientoCuotas.${index}`] ? (
                  <small className="field__error">{fieldErrors[`fechasVencimientoCuotas.${index}`]}</small>
                ) : null}
              </label>
            </div>
          ))}
        </div>
        {fieldErrors.fechasVencimientoCuotas ? (
          <small className="field__error">{fieldErrors.fechasVencimientoCuotas}</small>
        ) : null}
      </div>

      <label className="field field--full">
        <span>Detalle de la operacion</span>
        <textarea className="input textarea" name="detallesOperacion" rows={4} value={operationForm.detallesOperacion} onChange={onChange} />
      </label>
      <label className="field field--full">
        <span>Recomendaciones</span>
        <textarea className="input textarea" name="recomendaciones" rows={4} value={operationForm.recomendaciones} onChange={onChange} />
      </label>
      <div className="form-actions field--full">
        <button
          className="button button--ghost"
          disabled={isSaving || isCancelling}
          type="button"
          onClick={onCancel}
        >
          {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
        </button>
        <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={onBack}>
          Volver
        </button>
        <button className="button" disabled={isSaving || isCancelling} type="submit">
          {isSaving ? 'Guardando...' : 'Guardar y continuar'}
        </button>
      </div>
    </form>
  )
}
