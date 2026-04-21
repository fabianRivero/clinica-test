import { useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { createAdminProspect } from '../../services/api/admin'
import type { CreateAdminProspectPayload } from '../../types/admin'

const initialForm: CreateAdminProspectPayload = {
  nombres: '',
  apellidos: '',
  telefono: '',
  estado: 'PASAJERO',
  observaciones: '',
}

type FieldErrors = Partial<Record<keyof CreateAdminProspectPayload, string>>

export function AdminProspectCreatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState<CreateAdminProspectPayload>(initialForm)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => ({ ...current, [name]: undefined }))
    setSubmitError(null)
  }

  const validate = () => {
    const nextErrors: FieldErrors = {}

    if (!form.nombres.trim()) {
      nextErrors.nombres = 'Los nombres son obligatorios.'
    }

    if (!form.apellidos.trim()) {
      nextErrors.apellidos = 'Los apellidos son obligatorios.'
    }

    setFieldErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!validate()) {
      return
    }

    setIsSubmitting(true)
    setSubmitError(null)

    try {
      const response = await createAdminProspect({
        ...form,
        nombres: form.nombres.trim(),
        apellidos: form.apellidos.trim(),
        telefono: form.telefono.trim(),
        observaciones: form.observaciones.trim(),
      })

      navigate('/admin/prospectos', {
        replace: true,
        state: { flashMessage: response.detail },
      })
    } catch (error) {
      if (error instanceof Error && 'fieldErrors' in error) {
        const candidate = (error as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (candidate) {
          setFieldErrors(candidate)
        }
      }
      setSubmitError(
        error instanceof Error ? error.message : 'No se pudo registrar el prospecto. Intenta nuevamente.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Nuevo prospecto"
        title="Registrar prospecto"
        description="Crea un registro interno para una persona interesada en los servicios de la clinica. Solo se piden nombres y apellidos; el telefono y las observaciones son opcionales."
        actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/admin/prospectos' }]}
      />

      <SectionCard
        eyebrow="Formulario comercial"
        title="Datos iniciales del prospecto"
        description="Este registro se usa para seguimiento interno. Mas adelante se podra convertir en cliente formal cuando adquiera un procedimiento."
      >
        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="field">
            <span>Nombres</span>
            <input
              className="input"
              name="nombres"
              onChange={handleChange}
              placeholder="Ej. Carla"
              value={form.nombres}
            />
            {fieldErrors.nombres ? <small className="field__error">{fieldErrors.nombres}</small> : null}
          </label>

          <label className="field">
            <span>Apellidos</span>
            <input
              className="input"
              name="apellidos"
              onChange={handleChange}
              placeholder="Ej. Flores Vargas"
              value={form.apellidos}
            />
            {fieldErrors.apellidos ? <small className="field__error">{fieldErrors.apellidos}</small> : null}
          </label>

          <label className="field">
            <span>Telefono</span>
            <input
              className="input"
              name="telefono"
              onChange={handleChange}
              placeholder="Opcional"
              value={form.telefono}
            />
          </label>

          <label className="field">
            <span>Estado inicial</span>
            <select className="input" name="estado" onChange={handleChange} value={form.estado}>
              <option value="PASAJERO">Pasajero</option>
              <option value="DESCARTADO">Descartado</option>
            </select>
            {fieldErrors.estado ? <small className="field__error">{fieldErrors.estado}</small> : null}
          </label>

          <label className="field field--full">
            <span>Observaciones</span>
            <textarea
              className="input textarea"
              name="observaciones"
              onChange={handleChange}
              placeholder="Ej. Consulta por depilacion definitiva en piernas y axilas."
              rows={5}
              value={form.observaciones}
            />
          </label>

          {submitError ? (
            <div className="field--full">
              <DataState title="No se pudo registrar" message={submitError} tone="danger" />
            </div>
          ) : null}

          <div className="form-actions field--full">
            <button className="button button--ghost" onClick={() => navigate('/admin/prospectos')} type="button">
              Cancelar
            </button>
            <button className="button" disabled={isSubmitting} type="submit">
              {isSubmitting ? 'Guardando...' : 'Guardar prospecto'}
            </button>
          </div>
        </form>
      </SectionCard>
    </div>
  )
}
