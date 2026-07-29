import { type ChangeEvent, type FormEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { useConfirmDialog } from '../../../hooks/useConfirmDialog'
import { useNotifications } from '../../../providers/NotificationProvider'
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
  getAdminPayments,
} from '../../../services/api/admin'
import type {
  ConversionStep,
  ProspectConversionBiometricData,
  ProspectConversionAntecedente,
  ProspectConversionCirugia,
  ProspectConversionFieldResponse,
  ProspectConversionImplante,
  ProspectConversionMedicalData,
  ProspectConversionOperationData,
  ProspectConversionResponse,
  ProspectConversionUserData,
} from '../../../types/prospectConversion'

import {
  blankBiometricData,
  buildDueDateList,
  emptyFieldResponse,
  getInitialStep,
  type FieldErrors,
} from './conversionHelpers'
import {
  enrollInit as biometricEnrollInit,
  prospectoEnrollInit as biometricProspectoEnrollInit,
} from '../../../services/fingerprint/biometricClient'

type UseConversionWizardParams = {
  prospectId: string
  clientId: string
  isReactivation: boolean
}

type UseConversionWizardReturn = {
  data: ProspectConversionResponse | null
  isLoading: boolean
  error: string | null
  isSaving: boolean
  isCancelling: boolean
  submitError: string | null
  fieldErrors: FieldErrors
  activeStep: ConversionStep
  setActiveStep: (step: ConversionStep) => void
  password: string
  confirmPassword: string
  showPassword: boolean
  showConfirmPassword: boolean
  userForm: ProspectConversionUserData | null
  operationForm: ProspectConversionOperationData | null
  medicalForm: ProspectConversionMedicalData | null
  biometricForm: ProspectConversionBiometricData
  biometricStatus: string | null
  biometricModalOpen: boolean
  biometricModalSubjectName: string
  medicalDocumentFile: File | null
  paymentQrImageUrl: string
  qrModalOpen: boolean
  shouldRegisterFirstPayment: boolean
  firstPaymentReceipt: File | null
  firstPaymentDetails: string
  selectedService: ProspectConversionResponse['serviceConfigs'][number] | null
  firstPaymentAmount: string
  today: string
  hasPassword: boolean
  setPassword: (value: string) => void
  setConfirmPassword: (value: string) => void
  setShowPassword: (value: boolean) => void
  setShowConfirmPassword: (value: boolean) => void
  setMedicalForm: (value: ProspectConversionMedicalData) => void
  setShouldRegisterFirstPayment: (value: boolean) => void
  setFirstPaymentReceipt: (value: File | null) => void
  setFirstPaymentDetails: (value: string) => void
  setQrModalOpen: (value: boolean) => void
  handleUserChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
  handleOperationChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void
  updateDueDate: (index: number, value: string) => void
  handleMedicalChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
  handleMedicalDocumentChange: (event: ChangeEvent<HTMLInputElement>) => void
  updateAntecedente: (index: number, key: keyof ProspectConversionAntecedente, value: string) => void
  updateImplante: (index: number, key: keyof ProspectConversionImplante, value: string) => void
  updateCirugia: (index: number, key: keyof ProspectConversionCirugia, value: string) => void
  updateFieldResponse: (fieldId: number, updater: (current: ProspectConversionFieldResponse) => ProspectConversionFieldResponse) => void
  updateAnalisisField: (key: 'tipoPielId' | 'gradoDeshidratacionId' | 'grosorPielId', value: string) => void
  togglePatologia: (patologiaId: number, checked: boolean) => void
  handleSaveStep1: (event: FormEvent) => Promise<void>
  handleSaveStep2: (event: FormEvent) => Promise<void>
  handleSaveStep3: (event: FormEvent) => Promise<void>
  handleOpenBiometricModal: () => void
  handleCloseBiometricModal: () => void
  handleConfirmCapture: () => Promise<{
    success: boolean
    errorMessage?: string
    calidadCaptura?: number
  }>
  handleSaveBiometricStep: (event: FormEvent) => Promise<void>
  handleFinalize: (event: FormEvent) => Promise<void>
  handleCancelDraft: () => Promise<void>
  canGoToStep: (step: ConversionStep) => boolean
  applyResponse: (response: ProspectConversionResponse) => void
  resetFeedback: () => void
  ConfirmDialogModal: ReturnType<typeof useConfirmDialog>['ConfirmDialog']
}

export function useConversionWizard({ prospectId, clientId, isReactivation }: UseConversionWizardParams): UseConversionWizardReturn {
  const navigate = useNavigate()
  const { confirm, ConfirmDialog: ConfirmDialogModal } = useConfirmDialog()
  const { showNotification } = useNotifications()

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
  const [biometricModalOpen, setBiometricModalOpen] = useState(false)
  const [paymentQrImageUrl, setPaymentQrImageUrl] = useState('')
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [shouldRegisterFirstPayment, setShouldRegisterFirstPayment] = useState(false)
  const [firstPaymentReceipt, setFirstPaymentReceipt] = useState<File | null>(null)
  const [firstPaymentDetails, setFirstPaymentDetails] = useState('')

  const firstPaymentAmount = useMemo(() => {
    if (!operationForm) return ''
    const total = Number(operationForm.precioTotal)
    const cuotas = Number(operationForm.cuotasTotales)
    if (!Number.isFinite(total) || !Number.isFinite(cuotas) || cuotas <= 0) return ''
    return (total / cuotas).toFixed(2)
  }, [operationForm])

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
        const now = new Date()
        const month = now.getMonth() + 1
        const year = now.getFullYear()
        const paymentsResponse = await getAdminPayments(month, year)
        setPaymentQrImageUrl(paymentsResponse.paymentQrConfig?.qrImageUrl || '')
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
  }, [prospectId, clientId, isReactivation])

  const selectedService =
    data && operationForm?.serviceConfigId
      ? data.serviceConfigs.find((item) => String(item.id) === String(operationForm.serviceConfigId)) || null
      : null

  const today = new Date().toLocaleDateString('en-CA')

  const hasPassword = !!userForm?.hasPassword

  const canGoToStep = (step: ConversionStep) => {
    if (!data) return false
    if (step === 1) return true
    if (step === 2) return data.draft.stepUserCompleted || activeStep === 2
    if (step === 3) return data.draft.stepOperationCompleted || activeStep === 3
    if (step === 4) return data.draft.stepMedicalCompleted || activeStep === 4
    return data.draft.stepBiometricCompleted || activeStep === 5
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
            : 'La confirmación de contraseña no coincide.',
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

  const handleConfirmCapture = async (): Promise<{
    success: boolean
    errorMessage?: string
    calidadCaptura?: number
  }> => {
    resetFeedback()
    setBiometricStatus('Capturando huella en el lector DigitalPersona 4500...')
    try {
      if (isReactivation) {
        const existingClientId = Number(clientId)
        if (!Number.isFinite(existingClientId)) {
          const message = 'No se pudo determinar el cliente para la captura.'
          setBiometricStatus(message)
          return { success: false, errorMessage: message }
        }
        const result = await biometricEnrollInit(existingClientId, {
          consentimiento_aceptado: biometricForm.consentAccepted,
        })
        setBiometricForm({
          provider: 'DIGITAL_PERSONA',
          template: `digital-persona-${result.huella_id}`,
          quality: result.calidad_captura,
          deviceSerial: result.device_serial,
          capturedAt: new Date().toISOString(),
          consentAccepted: biometricForm.consentAccepted,
        })
        setBiometricStatus(`Huella capturada con calidad ${result.calidad_captura}.`)
        return { success: true, calidadCaptura: result.calidad_captura }
      }

      // Prospect path: capture against the prospect before it has a
      // cliente row. The finalize handler re-attaches the row to the
      // newly-created cliente atomically.
      const prospectIdValue = Number(prospectId)
      if (!Number.isFinite(prospectIdValue)) {
        const message = 'No se pudo determinar el prospecto para la captura.'
        setBiometricStatus(message)
        return { success: false, errorMessage: message }
      }
      const result = await biometricProspectoEnrollInit(prospectIdValue, {
        consentimiento_aceptado: biometricForm.consentAccepted,
      })
      setBiometricForm({
        provider: 'DIGITAL_PERSONA',
        template: `digital-persona-${result.huella_id}`,
        quality: result.calidad_captura,
        deviceSerial: result.device_serial,
        capturedAt: new Date().toISOString(),
        consentAccepted: biometricForm.consentAccepted,
      })
      setBiometricStatus(`Huella capturada con calidad ${result.calidad_captura}.`)
      return { success: true, calidadCaptura: result.calidad_captura }
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'No se pudo capturar la huella.'
      setSubmitError(message)
      setBiometricStatus(message)
      return { success: false, errorMessage: message }
    }
  }

  const handleOpenBiometricModal = () => {
    resetFeedback()
    setBiometricModalOpen(true)
  }

  const handleCloseBiometricModal = () => {
    setBiometricModalOpen(false)
  }

  const handleSaveBiometricStep = async (event: FormEvent) => {
    event.preventDefault()

    resetFeedback()
    if (!biometricForm.template) {
      setFieldErrors({ template: 'Debes capturar la huella biometrica antes de continuar.' })
      return
    }
    setIsSaving(true)
    try {
      const biometricResponse = isReactivation
        ? await saveAdminClientReactivationBiometricStep(clientId, biometricForm)
        : await saveAdminProspectConversionBiometricStep(prospectId, biometricForm)
      applyResponse(biometricResponse)
      setActiveStep(5)
    } catch (requestError) {
      if (requestError instanceof Error && 'fieldErrors' in requestError) {
        const maybeFieldErrors = (requestError as Error & { fieldErrors?: FieldErrors }).fieldErrors
        if (maybeFieldErrors) {
          setFieldErrors(maybeFieldErrors)
        }
      }
      setSubmitError(requestError instanceof Error ? requestError.message : 'No se pudo guardar la biometria.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleFinalize = async (event: FormEvent) => {
    event.preventDefault()
    resetFeedback()
    if (shouldRegisterFirstPayment && !firstPaymentReceipt) {
      setFieldErrors({ primerPagoComprobante: 'Debes adjuntar un comprobante para registrar el primer pago.' })
      return
    }
    if (shouldRegisterFirstPayment && !firstPaymentAmount) {
      setFieldErrors({ primerPagoMonto: 'No se pudo calcular el monto del primer pago.' })
      return
    }

    const shouldContinue = await confirm({
      title: 'Confirmar finalizacion',
      message: '¿Estás seguro de que toda la información es correcta para finalizar el proceso?',
      tone: 'warning',
    })
    if (!shouldContinue) {
      return
    }
    setIsSaving(true)
    try {
      const firstPaymentPayload = shouldRegisterFirstPayment
        ? { receiptFile: firstPaymentReceipt, amount: firstPaymentAmount, details: firstPaymentDetails }
        : undefined
      const finalizeResponse = isReactivation
        ? await finalizeAdminClientReactivation(clientId, medicalDocumentFile || undefined, firstPaymentPayload)
        : await finalizeAdminProspectConversion(prospectId, medicalDocumentFile || undefined, firstPaymentPayload)
      showNotification({
        title: isReactivation ? 'Reactivación exitosa' : 'Conversión exitosa',
        message: `${finalizeResponse.detail} Cliente: ${finalizeResponse.client.name}. Operación: ${finalizeResponse.operation.procedure}.`,
        tone: 'success',
        duration: 6000,
      })
      navigate(isReactivation ? `/cms/clientes/${clientId}` : '/cms/prospectos', {
        replace: true,
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

    const shouldCancel = await confirm({
      title: 'Cancelar conversion',
      message: 'Se eliminara todo el borrador de conversion guardado hasta ahora. ¿Deseas continuar?',
      tone: 'danger',
    })

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
      showNotification({
        title: 'Borrador descartado',
        message: 'El borrador de conversion fue cancelado correctamente.',
        tone: 'info',
      })
      navigate(isReactivation ? `/cms/clientes/${clientId}` : '/cms/prospectos', {
        replace: true,
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

  return {
    data,
    isLoading,
    error,
    isSaving,
    isCancelling,
    submitError,
    fieldErrors,
    activeStep,
    setActiveStep,
    password,
    confirmPassword,
    showPassword,
    showConfirmPassword,
    setPassword,
    setConfirmPassword,
    setShowPassword,
    setShowConfirmPassword,
    userForm,
    operationForm,
    medicalForm,
    setMedicalForm,
    biometricForm,
    biometricStatus,
    biometricModalOpen,
    biometricModalSubjectName: data?.prospect?.name ?? data?.client?.name ?? '',
    medicalDocumentFile,
    paymentQrImageUrl,
    qrModalOpen,
    shouldRegisterFirstPayment,
    firstPaymentReceipt,
    firstPaymentDetails,
    setShouldRegisterFirstPayment,
    setFirstPaymentReceipt,
    setFirstPaymentDetails,
    setQrModalOpen,
    selectedService,
    firstPaymentAmount,
    today,
    hasPassword,
    handleUserChange,
    handleOperationChange,
    updateDueDate,
    handleMedicalChange,
    handleMedicalDocumentChange,
    updateAntecedente,
    updateImplante,
    updateCirugia,
    updateFieldResponse,
    updateAnalisisField,
    togglePatologia,
    handleSaveStep1,
    handleSaveStep2,
    handleSaveStep3,
    handleOpenBiometricModal,
    handleCloseBiometricModal,
    handleConfirmCapture,
    handleSaveBiometricStep,
    handleFinalize,
    handleCancelDraft,
    canGoToStep,
    applyResponse,
    resetFeedback,
    ConfirmDialogModal,
  }
}
