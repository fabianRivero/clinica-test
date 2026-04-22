import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import {
  cancelAdminProspectConversion,
  finalizeAdminProspectConversion,
  getAdminProspectConversion,
  saveAdminProspectConversionMedicalStep,
  saveAdminProspectConversionOperationStep,
  saveAdminProspectConversionUserStep,
} from '../../services/api/admin'
import type {
  ConversionStep,
  ProspectConversionAntecedente,
  ProspectConversionCirugia,
  ProspectConversionDraft,
  ProspectConversionField,
  ProspectConversionFieldResponse,
  ProspectConversionImplante,
  ProspectConversionMedicalData,
  ProspectConversionOperationData,
  ProspectConversionResponse,
  ProspectConversionUserData,
} from '../../types/prospectConversion'

const stepLabels: Array<{ step: ConversionStep; label: string }> = [
  { step: 1, label: 'Datos de usuario' },
  { step: 2, label: 'Operacion' },
  { step: 3, label: 'Ficha medica' },
]

type FieldErrors = Record<string, string>

function getInitialStep(draft: ProspectConversionDraft): ConversionStep {
  if (!draft.stepUserCompleted) return 1
  if (!draft.stepOperationCompleted) return 2
  return 3
}

function emptyFieldResponse(): ProspectConversionFieldResponse {
  return {
    valueText: '',
    valueNumber: '',
    valueDate: '',
    valueBoolean: null,
    detail: '',
    optionIds: [],
  }
}

function blankAntecedente(): ProspectConversionAntecedente {
  return {
    antecedenteId: '',
    tipoAntecedente: 'PERSONAL',
    detalle: '',
  }
}

function blankImplante(): ProspectConversionImplante {
  return {
    implanteId: '',
    detalle: '',
  }
}

function blankCirugia(): ProspectConversionCirugia {
  return {
    cirugiaId: '',
    haceCuantoTiempo: '',
    detalle: '',
  }
}

export function AdminProspectConvertPage() {
  const navigate = useNavigate()
  const { prospectId = '' } = useParams()

  const [data, setData] = useState<ProspectConversionResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [activeStep, setActiveStep] = useState<ConversionStep>(1)
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [userForm, setUserForm] = useState<ProspectConversionUserData | null>(null)
  const [operationForm, setOperationForm] = useState<ProspectConversionOperationData | null>(null)
  const [medicalForm, setMedicalForm] = useState<ProspectConversionMedicalData | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = await getAdminProspectConversion(prospectId)
        if (cancelled) return
        setData(response)
        setUserForm(response.draft.userData)
        setOperationForm(response.draft.operationData)
        setMedicalForm(response.draft.medicalData)
        setActiveStep(getInitialStep(response.draft))
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError instanceof Error ? requestError.message : 'No se pudo cargar la conversion.')
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false)
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [prospectId])

  const selectedService = useMemo(() => {
    if (!data || !operationForm?.serviceConfigId) return null
    return data.serviceConfigs.find((item) => String(item.id) === String(operationForm.serviceConfigId)) || null
  }, [data, operationForm?.serviceConfigId, operationForm])

  const canGoToStep = (step: ConversionStep) => {
    if (!data) return false
    if (step === 1) return true
    if (step === 2) return data.draft.stepUserCompleted || activeStep === 2
    return data.draft.stepOperationCompleted || activeStep === 3
  }

  const resetFeedback = () => {
    setSubmitError(null)
    setFieldErrors({})
  }

  const applyResponse = (response: ProspectConversionResponse) => {
    setData(response)
    setUserForm(response.draft.userData)
    setOperationForm(response.draft.operationData)
    setMedicalForm(response.draft.medicalData)
  }

  const handleUserChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!userForm) return
    const { name, value } = event.target
    setUserForm({ ...userForm, [name]: name === 'nroHijos' ? Number(value || 0) : value })
    setFieldErrors((current) => ({ ...current, [name]: '' }))
    setSubmitError(null)
  }

  const handleOperationChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    if (!operationForm) return
    const { name, value } = event.target
    const nextForm = {
      ...operationForm,
      [name]:
        name === 'cuotasTotales' || name === 'sesionesTotales'
          ? Number(value || 0)
          : value,
    }

    if (name === 'serviceConfigId' && data) {
      const nextService = data.serviceConfigs.find((item) => String(item.id) === value)
      if (nextService) {
        nextForm.precioTotal = nextService.basePrice
      }
    }

    setOperationForm(nextForm)
    setFieldErrors((current) => ({ ...current, [name]: '' }))
    setSubmitError(null)
  }

  const handleMedicalChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!medicalForm) return
    const { name, value, type } = event.target
    setMedicalForm({
      ...medicalForm,
      [name]: type === 'checkbox' ? (event.target as HTMLInputElement).checked : value,
    })
    setSubmitError(null)
  }

  const updateAntecedente = (index: number, key: keyof ProspectConversionAntecedente, value: string) => {
    if (!medicalForm) return
    const nextItems = [...medicalForm.antecedentes]
    nextItems[index] = { ...nextItems[index], [key]: value }
    setMedicalForm({ ...medicalForm, antecedentes: nextItems })
  }

  const updateImplante = (index: number, key: keyof ProspectConversionImplante, value: string) => {
    if (!medicalForm) return
    const nextItems = [...medicalForm.implantes]
    nextItems[index] = { ...nextItems[index], [key]: value }
    setMedicalForm({ ...medicalForm, implantes: nextItems })
  }

  const updateCirugia = (index: number, key: keyof ProspectConversionCirugia, value: string) => {
    if (!medicalForm) return
    const nextItems = [...medicalForm.cirugias]
    nextItems[index] = { ...nextItems[index], [key]: value }
    setMedicalForm({ ...medicalForm, cirugias: nextItems })
  }

  const updateFieldResponse = (fieldId: number, updater: (current: ProspectConversionFieldResponse) => ProspectConversionFieldResponse) => {
    if (!medicalForm) return
    const currentValue = medicalForm.fieldResponses[String(fieldId)] || emptyFieldResponse()
    setMedicalForm({
      ...medicalForm,
      fieldResponses: {
        ...medicalForm.fieldResponses,
        [String(fieldId)]: updater(currentValue),
      },
    })
  }

  const updateAnalisisField = (
    key: 'tipoPielId' | 'gradoDeshidratacionId' | 'grosorPielId',
    value: string,
  ) => {
    if (!medicalForm) return
    setMedicalForm({
      ...medicalForm,
      analisisEstetico: {
        ...medicalForm.analisisEstetico,
        [key]: value,
      },
    })
    setFieldErrors((current) => ({
      ...current,
      [`analisisEstetico.${key}`]: '',
    }))
    setSubmitError(null)
  }

  const togglePatologia = (patologiaId: number, checked: boolean) => {
    if (!medicalForm) return
    const currentIds = medicalForm.analisisEstetico.patologiaIds
    setMedicalForm({
      ...medicalForm,
      analisisEstetico: {
        ...medicalForm.analisisEstetico,
        patologiaIds: checked
          ? [...currentIds, patologiaId]
          : currentIds.filter((item) => item !== patologiaId),
      },
    })
    setFieldErrors((current) => ({
      ...current,
      'analisisEstetico.patologiaIds': '',
    }))
    setSubmitError(null)
  }

  const handleSaveStep1 = async (event: FormEvent) => {
    event.preventDefault()
    if (!userForm) return

    resetFeedback()
    if ((!userForm.hasPassword && !password) || (password && password !== confirmPassword)) {
      setFieldErrors({
        password:
          !userForm.hasPassword && !password
            ? 'Debes definir una contraseña para la nueva cuenta.'
            : 'La confirmacion de contraseña no coincide.',
      })
      return
    }

    setIsSaving(true)
    try {
      const response = await saveAdminProspectConversionUserStep(prospectId, {
        ...userForm,
        password: password || undefined,
      })
      applyResponse(response)
      setPassword('')
      setConfirmPassword('')
      setActiveStep(2)
    } catch (requestError) {
      if (requestError instanceof Error && 'fieldErrors' in requestError) {
        const maybeFieldErrors = (requestError as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (maybeFieldErrors) {
          setFieldErrors(maybeFieldErrors)
        }
      }
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo guardar el paso 1.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveStep2 = async (event: FormEvent) => {
    event.preventDefault()
    if (!operationForm) return

    resetFeedback()
    setIsSaving(true)
    try {
      const response = await saveAdminProspectConversionOperationStep(prospectId, operationForm)
      applyResponse(response)
      setActiveStep(3)
    } catch (requestError) {
      if (requestError instanceof Error && 'fieldErrors' in requestError) {
        const maybeFieldErrors = (requestError as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (maybeFieldErrors) {
          setFieldErrors(maybeFieldErrors)
        }
      }
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo guardar el paso 2.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleFinalize = async (event: FormEvent) => {
    event.preventDefault()
    if (!medicalForm) return

    resetFeedback()
    setIsSaving(true)
    try {
      const saveResponse = await saveAdminProspectConversionMedicalStep(prospectId, medicalForm)
      applyResponse(saveResponse)
      const finalizeResponse = await finalizeAdminProspectConversion(prospectId)
      navigate('/admin/prospectos', {
        replace: true,
        state: {
          flashMessage: `${finalizeResponse.detail} Cliente: ${finalizeResponse.client.name}. Operacion: ${finalizeResponse.operation.procedure}.`,
        },
      })
    } catch (requestError) {
      if (requestError instanceof Error && 'fieldErrors' in requestError) {
        const maybeFieldErrors = (requestError as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (maybeFieldErrors) {
          setFieldErrors(maybeFieldErrors)
        }
      }
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo finalizar la conversion.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCancelDraft = async () => {
    if (isSaving || isCancelling) return

    const shouldCancel = window.confirm(
      'Se eliminara todo el borrador de conversion guardado hasta ahora. ¿Deseas continuar?',
    )

    if (!shouldCancel) {
      return
    }

    resetFeedback()
    setIsCancelling(true)
    try {
      const response = await cancelAdminProspectConversion(prospectId)
      navigate('/admin/prospectos', {
        replace: true,
        state: {
          flashMessage: response.detail,
        },
      })
    } catch (requestError) {
      setSubmitError(
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo cancelar la conversion.',
      )
    } finally {
      setIsCancelling(false)
    }
  }

  const renderDynamicField = (field: ProspectConversionField) => {
    if (!medicalForm) return null
    const response = medicalForm.fieldResponses[String(field.id)] || emptyFieldResponse()

    const detailInput = field.allowsDetail ? (
      <textarea
        className="input textarea"
        rows={3}
        value={response.detail}
        onChange={(event) =>
          updateFieldResponse(field.id, (current) => ({
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
          <span>{field.label}</span>
          <input
            className="input"
            value={response.valueText}
            onChange={(event) =>
              updateFieldResponse(field.id, (current) => ({
                ...current,
                valueText: event.target.value,
              }))
            }
          />
          {detailInput}
        </label>
      )
    }

    if (field.type === 'NUMERO') {
      return (
        <label className="field" key={field.id}>
          <span>{field.label}</span>
          <input
            className="input"
            type="number"
            value={response.valueNumber}
            onChange={(event) =>
              updateFieldResponse(field.id, (current) => ({
                ...current,
                valueNumber: event.target.value,
              }))
            }
          />
          {detailInput}
        </label>
      )
    }

    if (field.type === 'FECHA') {
      return (
        <label className="field" key={field.id}>
          <span>{field.label}</span>
          <input
            className="input"
            type="date"
            value={response.valueDate}
            onChange={(event) =>
              updateFieldResponse(field.id, (current) => ({
                ...current,
                valueDate: event.target.value,
              }))
            }
          />
          {detailInput}
        </label>
      )
    }

    if (field.type === 'BOOLEANO') {
      return (
        <label className="field" key={field.id}>
          <span>{field.label}</span>
          <select
            className="input"
            value={
              response.valueBoolean === null ? '' : response.valueBoolean ? 'true' : 'false'
            }
            onChange={(event) =>
              updateFieldResponse(field.id, (current) => ({
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
          {detailInput}
        </label>
      )
    }

    if (field.type === 'SELECCION') {
      return (
        <label className="field" key={field.id}>
          <span>{field.label}</span>
          <select
            className="input"
            value={response.optionIds[0] ? String(response.optionIds[0]) : ''}
            onChange={(event) =>
              updateFieldResponse(field.id, (current) => ({
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
          {detailInput}
        </label>
      )
    }

    return (
      <div className="field field--full" key={field.id}>
        <span>{field.label}</span>
        <div className="checkbox-grid">
          {field.options.map((option) => {
            const checked = response.optionIds.includes(option.id)
            return (
              <label className="checkbox-pill" key={option.id}>
                <input
                  checked={checked}
                  type="checkbox"
                  onChange={(event) =>
                    updateFieldResponse(field.id, (current) => ({
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
        {detailInput}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Conversion de prospecto"
          title="Preparando wizard de conversion"
          description="Estamos cargando el prospecto, el borrador guardado y la configuracion clinica necesaria."
          actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/admin/prospectos' }]}
        />
        <SectionCard title="Cargando conversion">
          <DataState title="Sincronizando informacion" message="Consultando el borrador y los catalogos relacionados." />
        </SectionCard>
      </div>
    )
  }

  if (error || !data || !userForm || !operationForm || !medicalForm) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Conversion de prospecto"
          title="No pudimos iniciar la conversion"
          description="Este flujo solo funciona para prospectos pasajeros que aun no fueron convertidos."
          actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/admin/prospectos' }]}
        />
        <SectionCard title="Conversion no disponible">
          <DataState title="No disponible" message={error || 'No encontramos datos suficientes para continuar.'} tone="danger" />
        </SectionCard>
      </div>
    )
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Conversion de prospecto"
        title={`Convertir a ${data.prospect.name}`}
        description="Este flujo guarda temporalmente la informacion en tres pasos: datos de usuario, operacion y ficha medica. Solo al finalizar se crea el cliente y la nueva operacion."
        actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/admin/prospectos' }]}
      />

      <section className="wizard-summary">
        <article>
          <span>Prospecto</span>
          <strong>{data.prospect.name}</strong>
          <p>{data.prospect.phone}</p>
        </article>
        <article>
          <span>Interes inicial</span>
          <strong>{data.prospect.interest}</strong>
          <p>Registrado por {data.prospect.registeredBy}</p>
        </article>
        <article>
          <span>Estado actual</span>
          <strong>{data.prospect.state}</strong>
          <p>Creado {data.prospect.createdAt}</p>
        </article>
      </section>

      <div className="stepper">
        {stepLabels.map((item) => (
          <button
            key={item.step}
            className={`stepper__item ${activeStep === item.step ? 'is-active' : ''} ${
              item.step < activeStep || (item.step === 1 && data.draft.stepUserCompleted) || (item.step === 2 && data.draft.stepOperationCompleted) || (item.step === 3 && data.draft.stepMedicalCompleted)
                ? 'is-complete'
                : ''
            }`}
            disabled={isSaving || isCancelling || !canGoToStep(item.step)}
            type="button"
            onClick={() => setActiveStep(item.step)}
          >
            <span className="stepper__index">Paso {item.step}</span>
            <strong>{item.label}</strong>
          </button>
        ))}
      </div>

      {submitError ? <DataState title="No se pudo guardar el proceso" message={submitError} tone="danger" /> : null}

      {activeStep === 1 ? (
        <SectionCard
          eyebrow="Paso 1"
          title="Datos de usuario"
          description="Aqui se define la cuenta del nuevo cliente y la informacion administrativa principal."
        >
          <form className="form-grid" onSubmit={handleSaveStep1}>
            <label className="field">
              <span>Primer nombre</span>
              <input className="input" name="primerNombre" value={userForm.primerNombre} onChange={handleUserChange} />
              {fieldErrors.primerNombre ? <small className="field__error">{fieldErrors.primerNombre}</small> : null}
            </label>
            <label className="field">
              <span>Segundo nombre</span>
              <input className="input" name="segundoNombre" value={userForm.segundoNombre} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Apellido paterno</span>
              <input className="input" name="apellidoPaterno" value={userForm.apellidoPaterno} onChange={handleUserChange} />
              {fieldErrors.apellidoPaterno ? <small className="field__error">{fieldErrors.apellidoPaterno}</small> : null}
            </label>
            <label className="field">
              <span>Apellido materno</span>
              <input className="input" name="apellidoMaterno" value={userForm.apellidoMaterno} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Usuario</span>
              <input className="input" name="username" value={userForm.username} onChange={handleUserChange} />
              {fieldErrors.username ? <small className="field__error">{fieldErrors.username}</small> : null}
            </label>
            <label className="field">
              <span>Email</span>
              <input className="input" name="email" type="email" value={userForm.email} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Contraseña</span>
              <input className="input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={userForm.hasPassword ? 'Dejar vacio para conservar la actual' : ''} />
              {fieldErrors.password ? <small className="field__error">{fieldErrors.password}</small> : null}
            </label>
            <label className="field">
              <span>Confirmar contraseña</span>
              <input className="input" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
            </label>
            <label className="field">
              <span>Telefono</span>
              <input className="input" name="telefono" value={userForm.telefono} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>CI</span>
              <input className="input" name="ci" value={userForm.ci} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Codigo biometrico</span>
              <input className="input" name="codBiometrico" value={userForm.codBiometrico} onChange={handleUserChange} />
              {fieldErrors.codBiometrico ? <small className="field__error">{fieldErrors.codBiometrico}</small> : null}
            </label>
            <label className="field">
              <span>Fecha de nacimiento</span>
              <input className="input" name="fechaNacimiento" type="date" value={userForm.fechaNacimiento} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Nro. hijos</span>
              <input className="input" name="nroHijos" type="number" min="0" value={userForm.nroHijos} onChange={handleUserChange} />
              {fieldErrors.nroHijos ? <small className="field__error">{fieldErrors.nroHijos}</small> : null}
            </label>
            <label className="field">
              <span>Ocupacion</span>
              <input className="input" name="ocupacion" value={userForm.ocupacion} onChange={handleUserChange} />
            </label>
            <label className="field field--full">
              <span>Direccion</span>
              <input className="input" name="direccionDomicilio" value={userForm.direccionDomicilio} onChange={handleUserChange} />
            </label>
            <label className="field field--full">
              <span>Observaciones del cliente</span>
              <textarea className="input textarea" name="observacionesCliente" rows={4} value={userForm.observacionesCliente} onChange={handleUserChange} />
            </label>
            <div className="form-actions field--full">
              <button
                className="button button--ghost"
                disabled={isSaving || isCancelling}
                type="button"
                onClick={handleCancelDraft}
              >
                {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
              </button>
              <button className="button" disabled={isSaving || isCancelling} type="submit">
                {isSaving ? 'Guardando...' : 'Guardar y continuar'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {activeStep === 2 ? (
        <SectionCard
          eyebrow="Paso 2"
          title="Crear operacion"
          description="Configura el servicio que el prospecto adquiere y los datos base de la nueva operacion."
        >
          <form className="form-grid" onSubmit={handleSaveStep2}>
            <label className="field field--full">
              <span>Servicio</span>
              <select className="input" name="serviceConfigId" value={operationForm.serviceConfigId} onChange={handleOperationChange}>
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
              <span>Precio total</span>
              <input className="input" name="precioTotal" value={operationForm.precioTotal} onChange={handleOperationChange} />
              {fieldErrors.precioTotal ? <small className="field__error">{fieldErrors.precioTotal}</small> : null}
            </label>
            <label className="field">
              <span>Cuotas totales</span>
              <input className="input" min="1" name="cuotasTotales" type="number" value={operationForm.cuotasTotales} onChange={handleOperationChange} />
              {fieldErrors.cuotasTotales ? <small className="field__error">{fieldErrors.cuotasTotales}</small> : null}
            </label>
            <label className="field">
              <span>Sesiones totales</span>
              <input className="input" min="1" name="sesionesTotales" type="number" value={operationForm.sesionesTotales} onChange={handleOperationChange} />
              {fieldErrors.sesionesTotales ? <small className="field__error">{fieldErrors.sesionesTotales}</small> : null}
            </label>
            <label className="field">
              <span>Estado de la operacion</span>
              <select className="input" name="estado" value={operationForm.estado} onChange={handleOperationChange}>
                {data.operationStates.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              {fieldErrors.estado ? <small className="field__error">{fieldErrors.estado}</small> : null}
            </label>
            <label className="field">
              <span>Fecha de inicio</span>
              <input className="input" name="fechaInicio" type="date" value={operationForm.fechaInicio} onChange={handleOperationChange} />
              {fieldErrors.fechaInicio ? <small className="field__error">{fieldErrors.fechaInicio}</small> : null}
            </label>
            <label className="field">
              <span>Fecha final</span>
              <input className="input" name="fechaFinal" type="date" value={operationForm.fechaFinal} onChange={handleOperationChange} />
              {fieldErrors.fechaFinal ? <small className="field__error">{fieldErrors.fechaFinal}</small> : null}
            </label>
            <label className="field">
              <span>Primera fecha de vencimiento</span>
              <input className="input" name="primeraFechaVencimiento" type="date" value={operationForm.primeraFechaVencimiento} onChange={handleOperationChange} />
              {fieldErrors.primeraFechaVencimiento ? <small className="field__error">{fieldErrors.primeraFechaVencimiento}</small> : null}
            </label>
            <label className="field">
              <span>Zona general</span>
              <input className="input" name="zonaGeneral" value={operationForm.zonaGeneral} onChange={handleOperationChange} />
            </label>
            <label className="field field--full">
              <span>Zona especifica</span>
              <input className="input" name="zonaEspecifica" value={operationForm.zonaEspecifica} onChange={handleOperationChange} />
            </label>
            <label className="field field--full">
              <span>Detalle de la operacion</span>
              <textarea className="input textarea" name="detallesOperacion" rows={4} value={operationForm.detallesOperacion} onChange={handleOperationChange} />
            </label>
            <label className="field field--full">
              <span>Recomendaciones</span>
              <textarea className="input textarea" name="recomendaciones" rows={4} value={operationForm.recomendaciones} onChange={handleOperationChange} />
            </label>
            <div className="form-actions field--full">
              <button
                className="button button--ghost"
                disabled={isSaving || isCancelling}
                type="button"
                onClick={handleCancelDraft}
              >
                {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
              </button>
              <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={() => setActiveStep(1)}>
                Volver
              </button>
              <button className="button" disabled={isSaving || isCancelling} type="submit">
                {isSaving ? 'Guardando...' : 'Guardar y continuar'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {activeStep === 3 ? (
        <SectionCard
          eyebrow="Paso 3"
          title="Ficha medica"
          description="Completa la informacion clinica general y, si aplica, las respuestas del procedimiento seleccionado."
        >
          <form className="form-grid" onSubmit={handleFinalize}>
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
                  <input className="input" name="fechaFicha" type="date" value={medicalForm.fechaFicha} onChange={handleMedicalChange} />
                </label>
                <label className="field">
                  <span>Firma paciente CI</span>
                  <input className="input" name="firmaPacienteCi" value={medicalForm.firmaPacienteCi} onChange={handleMedicalChange} />
                </label>
                <label className="field field--full">
                  <span>Motivo de consulta</span>
                  <textarea className="input textarea" name="motivoConsulta" rows={4} value={medicalForm.motivoConsulta} onChange={handleMedicalChange} />
                </label>
                <label className="field field--full checkbox-row">
                  <input checked={medicalForm.consentimientoAceptado} name="consentimientoAceptado" type="checkbox" onChange={handleMedicalChange} />
                  <span>Consentimiento aceptado</span>
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
                    onChange={(event) => updateAnalisisField('tipoPielId', event.target.value)}
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
                    onChange={(event) => updateAnalisisField('gradoDeshidratacionId', event.target.value)}
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
                    onChange={(event) => updateAnalisisField('grosorPielId', event.target.value)}
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
                            onChange={(event) => togglePatologia(option.id, event.target.checked)}
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
                <textarea className="input textarea" name="observaciones" rows={4} value={medicalForm.observaciones} onChange={handleMedicalChange} />
              </label>
            </div>

            <div className="wizard-block field--full">
              <div className="wizard-block__header">
                <div>
                  <strong>Antecedentes medicos</strong>
                  <p>Usa el mismo catalogo para antecedentes personales y familiares.</p>
                </div>
                <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, antecedentes: [...medicalForm.antecedentes, blankAntecedente()] })}>
                  Agregar antecedente
                </button>
              </div>
              <div className="wizard-list">
                {medicalForm.antecedentes.map((item, index) => (
                  <div className="wizard-list__item" key={`antecedente-${index}`}>
                    <label className="field">
                      <span>Antecedente</span>
                      <select className="input" value={item.antecedenteId} onChange={(event) => updateAntecedente(index, 'antecedenteId', event.target.value)}>
                        <option value="">Seleccionar</option>
                        {data.medicalConfig.antecedentes.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.nombre}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Tipo</span>
                      <select className="input" value={item.tipoAntecedente} onChange={(event) => updateAntecedente(index, 'tipoAntecedente', event.target.value as 'FAMILIAR' | 'PERSONAL')}>
                        <option value="PERSONAL">Personal</option>
                        <option value="FAMILIAR">Familiar</option>
                      </select>
                    </label>
                    <label className="field field--full">
                      <span>Detalle</span>
                      <input className="input" value={item.detalle} onChange={(event) => updateAntecedente(index, 'detalle', event.target.value)} />
                    </label>
                    <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, antecedentes: medicalForm.antecedentes.filter((_, itemIndex) => itemIndex !== index) })}>
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
                <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, implantes: [...medicalForm.implantes, blankImplante()] })}>
                  Agregar implante
                </button>
              </div>
              <div className="wizard-list">
                {medicalForm.implantes.map((item, index) => (
                  <div className="wizard-list__item" key={`implante-${index}`}>
                    <label className="field">
                      <span>Implante</span>
                      <select className="input" value={item.implanteId} onChange={(event) => updateImplante(index, 'implanteId', event.target.value)}>
                        <option value="">Seleccionar</option>
                        {data.medicalConfig.implantes.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.nombre}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field field--full">
                      <span>Detalle</span>
                      <input className="input" value={item.detalle} onChange={(event) => updateImplante(index, 'detalle', event.target.value)} />
                    </label>
                    <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, implantes: medicalForm.implantes.filter((_, itemIndex) => itemIndex !== index) })}>
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
                <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, cirugias: [...medicalForm.cirugias, blankCirugia()] })}>
                  Agregar cirugia
                </button>
              </div>
              <div className="wizard-list">
                {medicalForm.cirugias.map((item, index) => (
                  <div className="wizard-list__item" key={`cirugia-${index}`}>
                    <label className="field">
                      <span>Cirugia</span>
                      <select className="input" value={item.cirugiaId} onChange={(event) => updateCirugia(index, 'cirugiaId', event.target.value)}>
                        <option value="">Seleccionar</option>
                        {data.medicalConfig.cirugias.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.nombre}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>Hace cuanto tiempo</span>
                      <input className="input" value={item.haceCuantoTiempo} onChange={(event) => updateCirugia(index, 'haceCuantoTiempo', event.target.value)} />
                    </label>
                    <label className="field field--full">
                      <span>Detalle</span>
                      <input className="input" value={item.detalle} onChange={(event) => updateCirugia(index, 'detalle', event.target.value)} />
                    </label>
                    <button className="button button--ghost button--compact" type="button" onClick={() => setMedicalForm({ ...medicalForm, cirugias: medicalForm.cirugias.filter((_, itemIndex) => itemIndex !== index) })}>
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
                        {section.fields.map((field) => renderDynamicField(field))}
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

            {Object.keys(fieldErrors).length ? (
              <div className="field--full">
                <DataState
                  title="Hay campos por revisar"
                  message={Object.values(fieldErrors).filter(Boolean).join(' ')}
                  tone="danger"
                />
              </div>
            ) : null}

            <div className="form-actions field--full">
              <button
                className="button button--ghost"
                disabled={isSaving || isCancelling}
                type="button"
                onClick={handleCancelDraft}
              >
                {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
              </button>
              <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={() => setActiveStep(2)}>
                Volver
              </button>
              <button className="button" disabled={isSaving || isCancelling} type="submit">
                {isSaving ? 'Guardando y convirtiendo...' : 'Guardar ficha y convertir prospecto'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}
    </div>
  )
}
