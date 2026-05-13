import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { DataState } from '../../components/admin/DataState'
import { PageHeader } from '../../components/admin/PageHeader'
import { SectionCard } from '../../components/admin/SectionCard'
import {
  cancelAdminProspectConversion,
  finalizeAdminProspectConversion,
  getAdminProspectConversion,
  saveAdminProspectConversionBiometricStep,
  saveAdminProspectConversionMedicalStep,
  saveAdminProspectConversionOperationStep,
  saveAdminProspectConversionUserStep,
  initializeAdminClientReactivation,
  cancelAdminClientReactivation,
  saveAdminClientReactivationUserStep,
  saveAdminClientReactivationOperationStep,
  saveAdminClientReactivationMedicalStep,
  saveAdminClientReactivationBiometricStep,
  finalizeAdminClientReactivation,
} from '../../services/api/admin'
import { checkMockFingerprintDevice, enrollMockFingerprint } from '../../services/fingerprint/mockFingerprint'
import type {
  ConversionStep,
  ProspectConversionBiometricData,
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
  { step: 4, label: 'Huella biometrica' },
]

type FieldErrors = Record<string, string>

function getInitialStep(draft: ProspectConversionDraft): ConversionStep {
  if (!draft.stepUserCompleted) return 1
  if (!draft.stepOperationCompleted) return 2
  if (!draft.stepMedicalCompleted) return 3
  return 4
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

function buildDueDateList(count: number, currentValues: string[]) {
  return Array.from({ length: count }, (_, index) => currentValues[index] || '')
}

function blankBiometricData(): ProspectConversionBiometricData {
  return {
    provider: 'MOCK',
    template: '',
    quality: 0,
    deviceSerial: '',
    consentAccepted: true,
    capturedAt: '',
  }
}

export function AdminProspectConvertPage() {
  const navigate = useNavigate()
  const { prospectId = '', clientId = '' } = useParams()
  const isReactivation = !!clientId

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
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [medicalDocumentFile, setMedicalDocumentFile] = useState<File | null>(null)
  const [userForm, setUserForm] = useState<ProspectConversionUserData | null>(null)
  const [operationForm, setOperationForm] = useState<ProspectConversionOperationData | null>(null)
  const [medicalForm, setMedicalForm] = useState<ProspectConversionMedicalData | null>(null)
  const [biometricForm, setBiometricForm] = useState<ProspectConversionBiometricData>(blankBiometricData)
  const [biometricStatus, setBiometricStatus] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        const response = isReactivation
          ? await initializeAdminClientReactivation(clientId)
          : await getAdminProspectConversion(prospectId)

        if (cancelled) return
        setData(response)
        setUserForm(response.draft.userData)
        if (response.draft.userData.hasPassword) {
          setPassword('********')
          setConfirmPassword('********')
        }
        const draftOpData = { ...response.draft.operationData }
        if (!draftOpData.fechaInicio) {
          draftOpData.fechaInicio = new Date().toLocaleDateString('en-CA')
        }
        setOperationForm(draftOpData)

        setMedicalForm(response.draft.medicalData)
        setBiometricForm(response.draft.biometricData)
        setMedicalDocumentFile(null)
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

  const selectedService =
    data && operationForm?.serviceConfigId
      ? data.serviceConfigs.find((item) => String(item.id) === String(operationForm.serviceConfigId)) || null
      : null

  const canGoToStep = (step: ConversionStep) => {
    if (!data) return false
    if (step === 1) return true
    if (step === 2) return data.draft.stepUserCompleted || activeStep === 2
    if (step === 3) return data.draft.stepOperationCompleted || activeStep === 3
    return data.draft.stepMedicalCompleted || activeStep === 4
  }

  const applyResponse = (response: ProspectConversionResponse) => {
    setData(response)
    setUserForm(response.draft.userData)
    setOperationForm(response.draft.operationData)
    setMedicalForm(response.draft.medicalData)
    setBiometricForm(response.draft.biometricData)
  }

  const resetFeedback = () => {
    setSubmitError(null)
    setFieldErrors({})
  }

  const handleUserChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (!userForm) return
    const { name, value } = event.target
    const nextForm = { ...userForm, [name]: name === 'nroHijos' ? Number(value || 0) : value }

    if (name === 'ci') {
      if (!userForm.username || userForm.username === userForm.ci) {
        nextForm.username = value
      }
      if (!password || password === userForm.ci) {
        setPassword(value)
      }
      if (!confirmPassword || confirmPassword === userForm.ci) {
        setConfirmPassword(value)
      }
    }

    setUserForm(nextForm)
    setFieldErrors((current) => ({ ...current, [name]: '' }))
    setSubmitError(null)
  }

  const handleOperationChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    if (!operationForm) return
    const { name, value } = event.target
    const nextValue =
      name === 'cuotasTotales' || name === 'sesionesTotales'
        ? Number(value || 0)
        : value

    const nextForm: ProspectConversionOperationData = {
      ...operationForm,
      [name]: nextValue,
    }

    if (name === 'cuotasTotales') {
      nextForm.fechasVencimientoCuotas = buildDueDateList(
        Number(value || 0),
        operationForm.fechasVencimientoCuotas,
      )
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

  const updateDueDate = (index: number, value: string) => {
    if (!operationForm) return
    const nextDueDates = [...operationForm.fechasVencimientoCuotas]
    nextDueDates[index] = value
    setOperationForm({
      ...operationForm,
      fechasVencimientoCuotas: nextDueDates,
    })
    setFieldErrors((current) => ({
      ...current,
      [`fechasVencimientoCuotas.${index}`]: '',
      fechasVencimientoCuotas: '',
    }))
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

  const handleMedicalDocumentChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] || null
    setMedicalDocumentFile(nextFile)
    setFieldErrors((current) => ({
      ...current,
      documentoFichaPdf: '',
    }))
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
      const response = isReactivation
        ? await saveAdminClientReactivationUserStep(clientId, { ...userForm, password: password || undefined })
        : await saveAdminProspectConversionUserStep(prospectId, { ...userForm, password: password || undefined })
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

  const today = new Date().toLocaleDateString('en-CA')

  const handleSaveStep2 = async (event: FormEvent) => {
    event.preventDefault()
    if (!operationForm) return

    const finalForm = {
      ...operationForm,
      fechaInicio: today
    }

    resetFeedback()
    setIsSaving(true)
    try {
      const response = isReactivation
        ? await saveAdminClientReactivationOperationStep(clientId, finalForm)
        : await saveAdminProspectConversionOperationStep(prospectId, finalForm)
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

  const handleSaveStep3 = async (event: FormEvent) => {
    event.preventDefault()
    if (!medicalForm) return

    resetFeedback()
    if (!medicalDocumentFile) {
      setFieldErrors({
        documentoFichaPdf: 'Debes adjuntar el PDF escaneado de la ficha medica antes de continuar.',
      })
      return
    }

    setIsSaving(true)
    try {
      const saveResponse = isReactivation
        ? await saveAdminClientReactivationMedicalStep(clientId, medicalForm, medicalDocumentFile || undefined)
        : await saveAdminProspectConversionMedicalStep(prospectId, medicalForm)
      applyResponse(saveResponse)
      setActiveStep(4)
    } catch (requestError) {
      if (requestError instanceof Error && 'fieldErrors' in requestError) {
        const maybeFieldErrors = (requestError as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (maybeFieldErrors) {
          setFieldErrors(maybeFieldErrors)
        }
      }
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo guardar el paso 3.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleCaptureBiometric = async () => {
    resetFeedback()
    setBiometricStatus('Conectando con el lector SecuGen simulado...')
    try {
      const device = await checkMockFingerprintDevice()
      setBiometricStatus(device.message)
      const capture = await enrollMockFingerprint(`${userForm?.username || data?.prospect?.name || prospectId}`)
      setBiometricForm({
        provider: capture.provider,
        template: capture.template,
        quality: capture.quality,
        deviceSerial: capture.deviceSerial,
        capturedAt: capture.capturedAt,
        consentAccepted: biometricForm.consentAccepted,
      })
      setBiometricStatus(`Huella simulada capturada con calidad ${capture.quality}.`)
    } catch (requestError) {
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo capturar la huella simulada.')
      setBiometricStatus(null)
    }
  }

  const handleFinalize = async (event: FormEvent) => {
    event.preventDefault()

    resetFeedback()
    if (!biometricForm.template) {
      setFieldErrors({ template: 'Debes capturar la huella biometrica simulada.' })
      return
    }
    if (!medicalDocumentFile) {
      setFieldErrors({
        documentoFichaPdf: 'Debes adjuntar el PDF escaneado de la ficha medica para finalizar la conversion.',
      })
      return
    }

    setIsSaving(true)
    try {
      const biometricResponse = isReactivation
        ? await saveAdminClientReactivationBiometricStep(clientId, biometricForm)
        : await saveAdminProspectConversionBiometricStep(prospectId, biometricForm)
      applyResponse(biometricResponse)
      const finalizeResponse = isReactivation
        ? await finalizeAdminClientReactivation(clientId, medicalDocumentFile)
        : await finalizeAdminProspectConversion(prospectId, medicalDocumentFile)
      navigate(isReactivation ? `/admin/clientes/${clientId}` : '/admin/prospectos', {
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
      if (isReactivation) {
        await cancelAdminClientReactivation(clientId)
      } else {
        await cancelAdminProspectConversion(prospectId)
      }
      navigate(isReactivation ? `/admin/clientes/${clientId}` : '/admin/prospectos', {
        replace: true,
        state: {
          flashMessage: 'Borrador cancelado correctamente.',
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
    const fieldError = fieldErrors[`fieldResponses.${field.id}.required`] || null

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
          <span>{field.label} <span style={{ color: 'var(--color-danger)' }}>*</span></span>
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
              updateFieldResponse(field.id, (current) => ({
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
              updateFieldResponse(field.id, (current) => ({
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
        {fieldError ? <small className="field__error">{fieldError}</small> : null}
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

  const isActiveClient = isReactivation && data?.client?.status === 'ACTIVO'
  const wizardTitle = isActiveClient
    ? 'Nuevo procedimiento'
    : isReactivation
      ? 'Reactivacion de cliente'
      : 'Conversion de prospecto'
  const wizardSubject = isActiveClient
    ? `Nuevo procedimiento para ${data.client?.name}`
    : isReactivation
      ? `Reactivar a ${data.client?.name}`
      : `Convertir a ${data.prospect?.name}`

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow={wizardTitle}
        title={wizardSubject}
        description="Este flujo guarda temporalmente la informacion en cuatro pasos: datos de usuario, operacion, ficha medica y huella biometrica. Solo al finalizar se crea/actualiza el cliente y la nueva operacion."
        actions={[{
          label: isReactivation ? 'Volver a cliente' : 'Volver a prospectos',
          variant: 'ghost',
          to: isReactivation ? `/admin/clientes/${clientId}` : '/admin/prospectos'
        }]}
      />

      {data.crossCityWarning ? (
        <div style={{ marginBottom: '1.5rem' }}>
          <DataState 
            title="Advertencia de Tratamiento Activo" 
            message={data.crossCityWarning} 
            tone="warning" 
          />
        </div>
      ) : null}

      <section className="wizard-summary">
        <article>
          <span>{isReactivation ? 'Cliente' : 'Prospecto'}</span>
          <strong>{isReactivation ? data.client?.name : data.prospect?.name}</strong>
          <p>{isReactivation ? data.client?.ci : data.prospect?.phone}</p>
        </article>
        <article>
          <span>{isReactivation ? 'Estado de cliente' : 'Interes inicial'}</span>
          <strong>{isReactivation ? data.client?.status : data.prospect?.interest}</strong>
          <p>{isActiveClient ? 'Agregar nuevo tratamiento' : isReactivation ? 'Procedimiento previo finalizado' : `Registrado por ${data.prospect?.registeredBy}`}</p>
        </article>
        <article>
          <span>{isReactivation ? 'Identificacion' : 'Estado actual'}</span>
          <strong>{isReactivation ? data.client?.ci : data.prospect?.state}</strong>
          <p>{isReactivation ? 'Verificado en sistema' : `Creado ${data.prospect?.createdAt}`}</p>
        </article>
      </section>
      <div className="stepper">
        {stepLabels.map((item) => (
          <button
            key={item.step}
            className={`stepper__item ${activeStep === item.step ? 'is-active' : ''} ${item.step < activeStep || (item.step === 1 && data.draft.stepUserCompleted) || (item.step === 2 && data.draft.stepOperationCompleted) || (item.step === 3 && data.draft.stepMedicalCompleted) || (item.step === 4 && data.draft.stepBiometricCompleted)
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
              <span>CI</span>
              <input className="input" name="ci" value={userForm.ci} onChange={handleUserChange} />
              {fieldErrors.ci ? <small className="field__error">{fieldErrors.ci}</small> : null}
            </label>
            <label className="field">
              <span>Nombre de usuario</span>
              <input className="input" name="username" value={userForm.username} onChange={handleUserChange} />
              {fieldErrors.username ? <small className="field__error">{fieldErrors.username}</small> : null}
            </label>
            <label className="field">
              <span>Email</span>
              <input className="input" name="email" type="email" value={userForm.email} onChange={handleUserChange} />
            </label>
            {!isReactivation && (
              <>
                <label className="field field--password">
                  <span>Contraseña</span>
                  <input
                    className="input"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={userForm.hasPassword ? 'Dejar vacio para conservar la actual' : ''}
                  />
                  <button
                    className="field__toggle"
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    title={showPassword ? 'Ocultar' : 'Mostrar'}
                  >
                    {showPassword ? (
                      <svg fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" x2="23" y1="1" y2="23" />
                      </svg>
                    ) : (
                      <svg fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                  {fieldErrors.password ? <small className="field__error">{fieldErrors.password}</small> : null}
                </label>
                <label className="field field--password">
                  <span>Confirmar contraseña</span>
                  <input
                    className="input"
                    type={showConfirmPassword ? 'text' : 'password'}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                  <button
                    className="field__toggle"
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    title={showConfirmPassword ? 'Ocultar' : 'Mostrar'}
                  >
                    {showConfirmPassword ? (
                      <svg fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                        <line x1="1" x2="23" y1="1" y2="23" />
                      </svg>
                    ) : (
                      <svg fill="none" height="20" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24" width="20">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </button>
                </label>
              </>
            )}
            <label className="field">
              <span>Telefono</span>
              <input className="input" name="telefono" value={userForm.telefono} onChange={handleUserChange} />
            </label>
            <label className="field">
              <span>Fecha de nacimiento</span>
              <input className="input" name="fechaNacimiento" type="date" value={userForm.fechaNacimiento} onChange={handleUserChange} />
              {fieldErrors.fechaNacimiento ? <small className="field__error">{fieldErrors.fechaNacimiento}</small> : null}
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
              <span>Servicio <span style={{ color: 'var(--color-danger)' }}>*</span></span>
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
              <span>Precio total <span style={{ color: 'var(--color-danger)' }}>*</span></span>
              <input className="input" name="precioTotal" value={operationForm.precioTotal} onChange={handleOperationChange} />
              {fieldErrors.precioTotal ? <small className="field__error">{fieldErrors.precioTotal}</small> : null}
            </label>

            <label className="field">
              <span>Sesiones totales <span style={{ color: 'var(--color-danger)' }}>*</span></span>
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
              <input className="input" name="zonaGeneral" value={operationForm.zonaGeneral} onChange={handleOperationChange} />
              {fieldErrors.zonaGeneral ? <small className="field__error">{fieldErrors.zonaGeneral}</small> : null}
            </label>
            <label className="field">
              <span>Zona especifica <span style={{ color: 'var(--color-danger)' }}>*</span></span>
              <input className="input" name="zonaEspecifica" value={operationForm.zonaEspecifica} onChange={handleOperationChange} />
              {fieldErrors.zonaEspecifica ? <small className="field__error">{fieldErrors.zonaEspecifica}</small> : null}
            </label>

            <label className="field">
              <span>Cuotas totales <span style={{ color: 'var(--color-danger)' }}>*</span></span>
              <input className="input" min="1" name="cuotasTotales" type="number" value={operationForm.cuotasTotales} onChange={handleOperationChange} />
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
                        onChange={(event) => updateDueDate(index, event.target.value)}
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
          <form className="form-grid" onSubmit={handleSaveStep3}>
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
                <label className="field field--full">
                  <span>Motivo de consulta</span>
                  <textarea className="input textarea" name="motivoConsulta" rows={4} value={medicalForm.motivoConsulta} onChange={handleMedicalChange} />
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
                      <span>Antecedente <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                      <select className="input" value={item.antecedenteId} onChange={(event) => updateAntecedente(index, 'antecedenteId', event.target.value)}>
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
                      <select className="input" value={item.tipoAntecedente} onChange={(event) => updateAntecedente(index, 'tipoAntecedente', event.target.value as 'FAMILIAR' | 'PERSONAL')}>
                        <option value="PERSONAL">Personal</option>
                        <option value="FAMILIAR">Familiar</option>
                      </select>
                      {fieldErrors[`antecedentes.${index}.tipoAntecedente`] ? <small className="field__error">{fieldErrors[`antecedentes.${index}.tipoAntecedente`]}</small> : null}
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
                      <span>Implante <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                      <select className="input" value={item.implanteId} onChange={(event) => updateImplante(index, 'implanteId', event.target.value)}>
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
                      <span>Cirugia <span style={{ color: 'var(--color-danger)' }}>*</span></span>
                      <select className="input" value={item.cirugiaId} onChange={(event) => updateCirugia(index, 'cirugiaId', event.target.value)}>
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
                      <input className="input" value={item.haceCuantoTiempo} onChange={(event) => updateCirugia(index, 'haceCuantoTiempo', event.target.value)} />
                      {fieldErrors[`cirugias.${index}.haceCuantoTiempo`] ? <small className="field__error">{fieldErrors[`cirugias.${index}.haceCuantoTiempo`]}</small> : null}
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
                  onChange={handleMedicalDocumentChange}
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
                onClick={handleCancelDraft}
              >
                {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
              </button>
              <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={() => setActiveStep(2)}>
                Volver
              </button>
              <button className="button" disabled={isSaving || isCancelling} type="submit">
                {isSaving ? 'Guardando...' : 'Guardar ficha y continuar'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}

      {activeStep === 4 ? (
        <SectionCard
          eyebrow="Paso 4"
          title="Huella biometrica"
          description="Simula el enrolamiento con un lector SecuGen Hamster Pro 20. Esta capa queda lista para reemplazar el proveedor mock por la WebAPI real."
        >
          <form className="form-grid" onSubmit={handleFinalize}>
            <div className="wizard-block field--full">
              <div className="wizard-block__header">
                <div>
                  <strong>Captura simulada</strong>
                  <p>El sistema genera un template estable para probar el flujo completo sin conectar el dispositivo fisico.</p>
                </div>
                <button
                  className="button button--ghost button--compact"
                  disabled={isSaving || isCancelling}
                  type="button"
                  onClick={handleCaptureBiometric}
                >
                  Capturar huella mock
                </button>
              </div>
              <div className="operation-card__note-grid">
                <article>
                  <span>Proveedor</span>
                  <p>{biometricForm.provider === 'MOCK' ? 'Simulador SecuGen' : 'SecuGen real'}</p>
                </article>
                <article>
                  <span>Dispositivo</span>
                  <p>{biometricForm.deviceSerial || 'Sin captura'}</p>
                </article>
                <article>
                  <span>Calidad</span>
                  <p>{biometricForm.quality ? `${biometricForm.quality}/100` : 'Pendiente'}</p>
                </article>
                <article>
                  <span>Capturada</span>
                  <p>{biometricForm.capturedAt || 'Pendiente'}</p>
                </article>
              </div>
              {biometricStatus ? <small className="field__hint">{biometricStatus}</small> : null}
              {fieldErrors.template ? <small className="field__error">{fieldErrors.template}</small> : null}
              {fieldErrors.quality ? <small className="field__error">{fieldErrors.quality}</small> : null}
            </div>


            <div className="form-actions field--full">
              <button
                className="button button--ghost"
                disabled={isSaving || isCancelling}
                type="button"
                onClick={handleCancelDraft}
              >
                {isCancelling ? 'Cancelando...' : 'Cancelar conversion'}
              </button>
              <button className="button button--ghost" disabled={isSaving || isCancelling} type="button" onClick={() => setActiveStep(3)}>
                Volver
              </button>
              <button className="button" disabled={isSaving || isCancelling} type="submit">
                {isSaving ? 'Guardando y convirtiendo...' : 'Finalizar'}
              </button>
            </div>
          </form>
        </SectionCard>
      ) : null}
    </div>
  )
}
