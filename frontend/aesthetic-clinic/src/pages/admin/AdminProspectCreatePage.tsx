import { useState, useEffect, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { FieldError } from '../../components/admin/FieldError'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import { createAdminProspect, checkAdminProspectDuplicates } from '../../services/api/admin'
import { useNotifications } from '../../providers/NotificationProvider'
import type { CreateAdminProspectPayload, CheckAdminProspectDuplicatesResponse } from '../../types/admin'

const initialForm: CreateAdminProspectPayload = {
  primerNombre: '',
  segundoNombre: '',
  apellidoPaterno: '',
  apellidoMaterno: '',
  telefono: '',
  estado: 'PASAJERO',
  observaciones: '',
}

type FieldErrors = Partial<Record<keyof CreateAdminProspectPayload, string>>

export function AdminProspectCreatePage() {
  const navigate = useNavigate()
  const { showNotification } = useNotifications()
  const [form, setForm] = useState<CreateAdminProspectPayload>(initialForm)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [duplicateCheck, setDuplicateCheck] = useState<CheckAdminProspectDuplicatesResponse | null>(null)

  useEffect(() => {
    const primerNombre = form.primerNombre.trim()
    const segundoNombre = form.segundoNombre.trim()
    const apellidoPaterno = form.apellidoPaterno.trim()
    const apellidoMaterno = form.apellidoMaterno.trim()
    const telefono = form.telefono.trim()

    if (primerNombre.length < 2 || apellidoPaterno.length < 2) {
      setDuplicateCheck(null)
      return
    }

    const timer = setTimeout(async () => {
      try {
        const result = await checkAdminProspectDuplicates({
          primerNombre,
          segundoNombre,
          apellidoPaterno,
          apellidoMaterno,
          telefono,
        })
        setDuplicateCheck(result)
      } catch (error) {
        console.error('Error al verificar duplicados:', error)
      }
    }, 600)

    return () => clearTimeout(timer)
  }, [form.primerNombre, form.segundoNombre, form.apellidoPaterno, form.apellidoMaterno, form.telefono])

  const handleChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = event.target
    setForm((current) => ({ ...current, [name]: value }))
    setFieldErrors((current) => ({ ...current, [name]: undefined }))
    setSubmitError(null)
  }

  const validate = () => {
    const nextErrors: FieldErrors = {}

    if (!form.primerNombre.trim()) {
      nextErrors.primerNombre = 'El primer nombre es obligatorio.'
    }

    if (!form.apellidoPaterno.trim()) {
      nextErrors.apellidoPaterno = 'El apellido paterno es obligatorio.'
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
        primerNombre: form.primerNombre.trim(),
        segundoNombre: form.segundoNombre.trim(),
        apellidoPaterno: form.apellidoPaterno.trim(),
        apellidoMaterno: form.apellidoMaterno.trim(),
        telefono: form.telefono.trim(),
        observaciones: form.observaciones.trim(),
      })

      showNotification({
        title: 'Prospecto registrado',
        message: response.detail,
        tone: 'success',
      })
      navigate('/admin/prospectos', {
        replace: true,
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
        description="Crea un registro interno para una persona interesada en los servicios de la clínica. Se registran nombre y apellidos por separado; solo primer nombre y apellido paterno son obligatorios."
        actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/cms/prospectos' }]}
      />

      <SectionCard
        eyebrow="Formulario comercial"
        title="Datos iniciales del prospecto"
        description="Este registro se usa para seguimiento interno. Mas adelante se podra convertir en cliente formal cuando adquiera un procedimiento."
      >
        <form className="form-grid" onSubmit={handleSubmit}>
          <label className="field">
            <span>Primer nombre</span>
            <input
              className="input"
              name="primerNombre"
              onChange={handleChange}
              placeholder="Ej. Carla"
              value={form.primerNombre}
            />
            <FieldError message={fieldErrors.primerNombre} />
          </label>

          <label className="field">
            <span>Segundo nombre</span>
            <input
              className="input"
              name="segundoNombre"
              onChange={handleChange}
              placeholder="Opcional"
              value={form.segundoNombre}
            />
          </label>

          <label className="field">
            <span>Apellido paterno</span>
            <input
              className="input"
              name="apellidoPaterno"
              onChange={handleChange}
              placeholder="Ej. Flores"
              value={form.apellidoPaterno}
            />
            {fieldErrors.apellidoPaterno ? <small className="field__error">{fieldErrors.apellidoPaterno}</small> : null}
          </label>

          <label className="field">
            <span>Apellido materno</span>
            <input
              className="input"
              name="apellidoMaterno"
              onChange={handleChange}
              placeholder="Opcional"
              value={form.apellidoMaterno}
            />
          </label>

          <label className="field">
            <span>Teléfono</span>
            <input
              className="input"
              name="telefono"
              type="tel"
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

          {duplicateCheck?.exists ? (
            <div className="field--full">
              <DataState 
                title="Posible duplicado detectado" 
                message={duplicateCheck.message || ''} 
                tone="warning" 
              />
            </div>
          ) : null}

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
