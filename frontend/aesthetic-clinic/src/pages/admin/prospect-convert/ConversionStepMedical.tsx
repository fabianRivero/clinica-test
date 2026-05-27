import { type ChangeEvent, type FormEvent } from 'react'

import { DataState } from '../../../components/admin/DataState'
import type {
  ProspectConversionAntecedente,
  ProspectConversionCirugia,
  ProspectConversionField,
  ProspectConversionFieldResponse,
  ProspectConversionImplante,
  ProspectConversionMedicalData,
  ProspectConversionResponse,
} from '../../../types/prospectConversion'

import { emptyFieldResponse } from './conversionHelpers'
import type { FieldErrors } from './conversionHelpers'

type Props = {
  medicalForm: ProspectConversionMedicalData
  medicalDocumentFile: File | null
  data: ProspectConversionResponse
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
  onDocumentChange: (event: ChangeEvent<HTMLInputElement>) => void
  onUpdateAntecedente: (index: number, key: keyof ProspectConversionAntecedente, value: string) => void
  onUpdateImplante: (index: number, key: keyof ProspectConversionImplante, value: string) => void
  onUpdateCirugia: (index: number, key: keyof ProspectConversionCirugia, value: string) => void
  onUpdateFieldResponse: (fieldId: number, updater: (current: ProspectConversionFieldResponse) => ProspectConversionFieldResponse) => void
  onUpdateAnalisisField: (key: 'tipoPielId' | 'gradoDeshidratacionId' | 'grosorPielId', value: string) => void
  onTogglePatologia: (patologiaId: number, checked: boolean) => void
  onSubmit: (event: FormEvent) => void
  onBack: () => void
  onCancel: () => void
  onAddAntecedente: () => void
  onRemoveAntecedente: (index: number) => void
  onAddImplante: () => void
  onRemoveImplante: (index: number) => void
  onAddCirugia: () => void
  onRemoveCirugia: (index: number) => void
}

function DynamicFieldRenderer({
  field,
  medicalForm,
  fieldErrors,
  onUpdateFieldResponse,
}: {
  field: ProspectConversionField
  medicalForm: ProspectConversionMedicalData
  fieldErrors: FieldErrors
  onUpdateFieldResponse: (fieldId: number, updater: (current: ProspectConversionFieldResponse) => ProspectConversionFieldResponse) => void
}) {
  const response = medicalForm.fieldResponses[String(field.id)] || emptyFieldResponse()
  const fieldError = fieldErrors[`fieldResponses.${field.id}.required`] || null

  const detailInput = field.allowsDetail ? (
    <textarea
      className="input textarea"
      rows={3}
      value={response.detail}
      onChange={(event) =>
        onUpdateFieldResponse(field.id, (current) => ({
          ...current,
          detail: event.target.value,
        }))
      }
      placeholder="Detalle adicional"
    />
  ) : null

  if (field.type === 'TEXTO') {
    return (
      <label className="field field--full" key={field.id}>
        <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input
          className="input"
          value={response.valueText}
          onChange={(event) =>
            onUpdateFieldResponse(field.id, (current) => ({
              ...current,
              valueText: event.target.value,
            }))
          }
        />
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
        {detailInput}
      </label>
    )
  }

  if (field.type === 'NUMERO') {
    return (
      <label className="field" key={field.id}>
        <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input
          className="input"
          type="number"
          value={response.valueNumber}
          onChange={(event) =>
            onUpdateFieldResponse(field.id, (current) => ({
              ...current,
              valueNumber: event.target.value,
            }))
          }
        />
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
        {detailInput}
      </label>
    )
  }

  if (field.type === 'FECHA') {
    return (
      <label className="field" key={field.id}>
        <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <input
          className="input"
          type="date"
          value={response.valueDate}
          onChange={(event) =>
            onUpdateFieldResponse(field.id, (current) => ({
              ...current,
              valueDate: event.target.value,
            }))
          }
        />
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
        {detailInput}
      </label>
    )
  }

  if (field.type === 'BOOLEANO') {
    return (
      <label className="field" key={field.id}>
        <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <select
          className="input"
          value={
            response.valueBoolean === null ? '' : response.valueBoolean ? 'true' : 'false'
          }
          onChange={(event) =>
            onUpdateFieldResponse(field.id, (current) => ({
              ...current,
              valueBoolean:
                event.target.value === ''
                  ? null
                  : event.target.value === 'true',
            }))
          }
        >
          <option value="">Seleccionar</option>
          <option value="true">Si</option>
          <option value="false">No</option>
        </select>
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
        {detailInput}
      </label>
    )
  }

  if (field.type === 'SELECCION') {
    return (
      <label className="field" key={field.id}>
        <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
        <select
          className="input"
          value={response.optionIds[0] ? String(response.optionIds[0]) : ''}
          onChange={(event) =>
            onUpdateFieldResponse(field.id, (current) => ({
              ...current,
              optionIds: event.target.value ? [Number(event.target.value)] : [],
            }))
          }
        >
          <option value="">Seleccionar</option>
          {field.options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.name}
            </option>
          ))}
        </select>
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
        {detailInput}
      </label>
    )
  }

  return (
    <div className="field field--full" key={field.id}>
      <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
      <div className="checkbox-grid">
        {field.options.map((option) => {
          const checked = response.optionIds.includes(option.id)
          return (
            <label className="checkbox-pill" key={option.id}>
              <input
                checked={checked}
                type="checkbox"
                onChange={(event) =>
                  onUpdateFieldResponse(field.id, (current) => ({
                    ...current,
                    optionIds: event.target.checked
                      ? [...current.optionIds, option.id]
                      : current.optionIds.filter((item) => item !== option.id),
                  }))
                }
              />
              <span>{option.name}</span>
            </label>
          )
        })}
      </div>
      {fieldError ? <small className="field__error">{fieldError}</small> : null}
      {detailInput}
    </div>
  )
}

export function ConversionStepMedical({
  medicalForm,
  medicalDocumentFile,
  data,
  fieldErrors,
  isSaving,
  isCancelling,
  onChange,
  onDocumentChange,
  onUpdateAntecedente,
  onUpdateImplante,
  onUpdateCirugia,
  onUpdateFieldResponse,
  onUpdateAnalisisField,
  onTogglePatologia,
  onSubmit,
  onBack,
  onCancel,
  onAddAntecedente,
  onRemoveAntecedente,
  onAddImplante,
  onRemoveImplante,
  onAddCirugia,
  onRemoveCirugia,
}: Props) {
  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Datos generales de la ficha</strong>
            <p>Completa la informacion administrativa y clinica base para el procedimiento.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Fecha de ficha</span>
            <input className="input" name="fechaFicha" type="date" value={medicalForm.fechaFicha} onChange={onChange} />
          </label>
          <label className="field field--full">
            <span>Motivo de consulta</span>
            <textarea className="input textarea" name="motivoConsulta" rows={4} value={medicalForm.motivoConsulta} onChange={onChange} />
          </label>
        </div>
      </div>

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Parte 5. Analisis estetico</strong>
            <p>Estos datos alimentan el historial clinico del paciente y se guardan como un analisis estetico inicial.</p>
          </div>
        </div>
        <div className="form-grid">
          <label className="field">
            <span>Tipo de piel</span>
            <select
              className="input"
              value={medicalForm.analisisEstetico.tipoPielId}
              onChange={(event) => onUpdateAnalisisField('tipoPielId', event.target.value)}
            >
              <option value="">Seleccionar</option>
              {data.medicalConfig.tiposPiel.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.nombre}
                </option>
              ))}
            </select>
            {fieldErrors['analisisEstetico.tipoPielId'] ? (
              <small className="field__error">{fieldErrors['analisisEstetico.tipoPielId']}</small>
            ) : null}
          </label>
          <label className="field">
            <span>Grado de deshidratacion</span>
            <select
              className="input"
              value={medicalForm.analisisEstetico.gradoDeshidratacionId}
              onChange={(event) => onUpdateAnalisisField('gradoDeshidratacionId', event.target.value)}
            >
              <option value="">Seleccionar</option>
              {data.medicalConfig.gradosDeshidratacion.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.nombre}
                </option>
              ))}
            </select>
            {fieldErrors['analisisEstetico.gradoDeshidratacionId'] ? (
              <small className="field__error">{fieldErrors['analisisEstetico.gradoDeshidratacionId']}</small>
            ) : null}
          </label>
          <label className="field">
            <span>Grosor de piel</span>
            <select
              className="input"
              value={medicalForm.analisisEstetico.grosorPielId}
              onChange={(event) => onUpdateAnalisisField('grosorPielId', event.target.value)}
            >
              <option value="">Seleccionar</option>
              {data.medicalConfig.grosoresPiel.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.nombre}
                </option>
              ))}
            </select>
            {fieldErrors['analisisEstetico.grosorPielId'] ? (
              <small className="field__error">{fieldErrors['analisisEstetico.grosorPielId']}</small>
            ) : null}
          </label>
          <div className="field field--full">
            <span>Patologias cutaneas</span>
            <div className="checkbox-grid">
              {data.medicalConfig.patologiasCutaneas.map((option) => {
                const checked = medicalForm.analisisEstetico.patologiaIds.includes(option.id)
                return (
                  <label className="checkbox-pill" key={option.id}>
                    <input
                      checked={checked}
                      type="checkbox"
                      onChange={(event) => onTogglePatologia(option.id, event.target.checked)}
                    />
                    <span>{option.nombre}</span>
                  </label>
                )
              })}
            </div>
            {fieldErrors['analisisEstetico.patologiaIds'] ? (
              <small className="field__error">{fieldErrors['analisisEstetico.patologiaIds']}</small>
            ) : null}
          </div>
        </div>
      </div>

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Parte 6. Observaciones</strong>
            <p>Registra observaciones generales importantes para el tratamiento, seguimiento o conducta clinica.</p>
          </div>
        </div>
        <label className="field field--full">
          <span>Observaciones</span>
          <textarea className="input textarea" name="observaciones" rows={4} value={medicalForm.observaciones} onChange={onChange} />
        </label>
      </div>

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Antecedentes medicos</strong>
            <p>Usa el mismo catalogo para antecedentes personales y familiares.</p>
          </div>
          <button className="button button--ghost button--compact" type="button" onClick={onAddAntecedente}>
            Agregar antecedente
          </button>
        </div>
        <div className="wizard-list">
          {medicalForm.antecedentes.map((item, index) => (
            <div className="wizard-list__item" key={`antecedente-${index}`}>
              <label className="field">
                <span>Antecedente <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                <select className="input" value={item.antecedenteId} onChange={(event) => onUpdateAntecedente(index, 'antecedenteId', event.target.value)}>
                  <option value="">Seleccionar</option>
                  {data.medicalConfig.antecedentes.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.nombre}
                    </option>
                  ))}
                </select>
                {fieldErrors[`antecedentes.${index}.antecedenteId`] ? <small className="field__error">{fieldErrors[`antecedentes.${index}.antecedenteId`]}</small> : null}
              </label>
              <label className="field">
                <span>Tipo <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                <select className="input" value={item.tipoAntecedente} onChange={(event) => onUpdateAntecedente(index, 'tipoAntecedente', event.target.value as 'FAMILIAR' | 'PERSONAL')}>
                  <option value="PERSONAL">Personal</option>
                  <option value="FAMILIAR">Familiar</option>
                </select>
                {fieldErrors[`antecedentes.${index}.tipoAntecedente`] ? <small className="field__error">{fieldErrors[`antecedentes.${index}.tipoAntecedente`]}</small> : null}
              </label>
              <label className="field field--full">
                <span>Detalle</span>
                <input className="input" value={item.detalle} onChange={(event) => onUpdateAntecedente(index, 'detalle', event.target.value)} />
              </label>
              <button className="button button--ghost button--compact" type="button" onClick={() => onRemoveAntecedente(index)}>
                Quitar
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Implantes e injertos</strong>
            <p>Registra solo los que apliquen para la evaluacion actual.</p>
          </div>
          <button className="button button--ghost button--compact" type="button" onClick={onAddImplante}>
            Agregar implante
          </button>
        </div>
        <div className="wizard-list">
          {medicalForm.implantes.map((item, index) => (
            <div className="wizard-list__item" key={`implante-${index}`}>
              <label className="field">
                <span>Implante <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                <select className="input" value={item.implanteId} onChange={(event) => onUpdateImplante(index, 'implanteId', event.target.value)}>
                  <option value="">Seleccionar</option>
                  {data.medicalConfig.implantes.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.nombre}
                    </option>
                  ))}
                </select>
                {fieldErrors[`implantes.${index}.implanteId`] ? <small className="field__error">{fieldErrors[`implantes.${index}.implanteId`]}</small> : null}
              </label>
              <label className="field field--full">
                <span>Detalle</span>
                <input className="input" value={item.detalle} onChange={(event) => onUpdateImplante(index, 'detalle', event.target.value)} />
              </label>
              <button className="button button--ghost button--compact" type="button" onClick={() => onRemoveImplante(index)}>
                Quitar
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Cirugias esteticas</strong>
            <p>Incluye el tiempo transcurrido y cualquier detalle relevante para el tratamiento.</p>
          </div>
          <button className="button button--ghost button--compact" type="button" onClick={onAddCirugia}>
            Agregar cirugia
          </button>
        </div>
        <div className="wizard-list">
          {medicalForm.cirugias.map((item, index) => (
            <div className="wizard-list__item" key={`cirugia-${index}`}>
              <label className="field">
                <span>Cirugia <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                <select className="input" value={item.cirugiaId} onChange={(event) => onUpdateCirugia(index, 'cirugiaId', event.target.value)}>
                  <option value="">Seleccionar</option>
                  {data.medicalConfig.cirugias.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.nombre}
                    </option>
                  ))}
                </select>
                {fieldErrors[`cirugias.${index}.cirugiaId`] ? <small className="field__error">{fieldErrors[`cirugias.${index}.cirugiaId`]}</small> : null}
              </label>
              <label className="field">
                <span>Hace cuanto tiempo <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                <input className="input" value={item.haceCuantoTiempo} onChange={(event) => onUpdateCirugia(index, 'haceCuantoTiempo', event.target.value)} />
                {fieldErrors[`cirugias.${index}.haceCuantoTiempo`] ? <small className="field__error">{fieldErrors[`cirugias.${index}.haceCuantoTiempo`]}</small> : null}
              </label>
              <label className="field field--full">
                <span>Detalle</span>
                <input className="input" value={item.detalle} onChange={(event) => onUpdateCirugia(index, 'detalle', event.target.value)} />
              </label>
              <button className="button button--ghost button--compact" type="button" onClick={() => onRemoveCirugia(index)}>
                Quitar
              </button>
            </div>
          ))}
        </div>
      </div>

      {data.medicalConfig.procedureName ? (
        <div className="wizard-block field--full">
          <div className="wizard-block__header">
            <div>
              <strong>Ficha especifica: {data.medicalConfig.procedureName}</strong>
              <p>Estas respuestas cambian segun el procedimiento seleccionado en el paso 2.</p>
            </div>
          </div>
          <div className="wizard-dynamic-sections">
            {data.medicalConfig.sections.map((section) => (
              <section className="wizard-dynamic-section" key={section.id}>
                <header>
                  <span>{section.code}</span>
                  <strong>{section.name}</strong>
                </header>
                <div className="form-grid">
                  {section.fields.map((field) => (
                    <DynamicFieldRenderer
                      key={field.id}
                      field={field}
                      medicalForm={medicalForm}
                      fieldErrors={fieldErrors}
                      onUpdateFieldResponse={onUpdateFieldResponse}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        </div>
      ) : (
        <div className="field--full">
          <DataState
            title="Sin ficha dinamica para este servicio"
            message="El servicio seleccionado no tiene campos clinicos especificos configurados, pero igual puedes completar la ficha general."
          />
        </div>
      )}

      <div className="wizard-block field--full">
        <div className="wizard-block__header">
          <div>
            <strong>Documento escaneado de la ficha</strong>
            <p>Adjunta el PDF final escaneado. Este archivo se guardara junto a la ficha clinica de la operacion.</p>
          </div>
        </div>
        <label className="field field--full">
          <span>PDF de la ficha medica</span>
          <input
            accept=".pdf,application/pdf"
            className="input input--file"
            type="file"
            onChange={onDocumentChange}
          />
          <small className="field__hint">
            {medicalDocumentFile
              ? `Archivo seleccionado: ${medicalDocumentFile.name}`
              : 'Debes subir un archivo PDF antes de pasar a la huella biometrica.'}
          </small>
          {fieldErrors.documentoFichaPdf ? (
            <small className="field__error">{fieldErrors.documentoFichaPdf}</small>
          ) : null}
        </label>
      </div>

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
          {isSaving ? 'Guardando...' : 'Guardar ficha y continuar'}
        </button>
      </div>
    </form>
  )
}
