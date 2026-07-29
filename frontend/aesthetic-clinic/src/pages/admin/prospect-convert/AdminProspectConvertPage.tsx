import { useParams } from 'react-router-dom'

import { DataState } from '../../../components/admin/DataState'
import { PageHeader } from '../../../components/admin/PageHeader'
import { SectionCard } from '../../../components/admin/SectionCard'

import { stepLabels } from './conversionHelpers'
import { ConversionStepBiometric } from './ConversionStepBiometric'
import { ConversionStepMedical } from './ConversionStepMedical'
import { ConversionStepOperation } from './ConversionStepOperation'
import { ConversionStepPayment } from './ConversionStepPayment'
import { ConversionStepUser } from './ConversionStepUser'
import { useConversionWizard } from './useConversionWizard'
import { blankAntecedente, blankCirugia, blankImplante } from './conversionHelpers'

export function AdminProspectConvertPage() {
  const { prospectId = '', clientId = '' } = useParams()
  const isReactivation = !!clientId

  const wizard = useConversionWizard({ prospectId, clientId, isReactivation })

  const {
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
    userForm,
    operationForm,
    medicalForm,
    biometricForm,
    biometricStatus,
    biometricModalOpen,
    biometricModalSubjectName,
    medicalDocumentFile,
    paymentQrImageUrl,
    qrModalOpen,
    setQrModalOpen,
    shouldRegisterFirstPayment,
    firstPaymentDetails,
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
    ConfirmDialogModal,
  } = wizard

  if (isLoading) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Conversion de prospecto"
          title="Preparando proceso de conversion"
          description="Estamos cargando el prospecto, el borrador guardado y la configuración clínica necesaria."
          actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/cms/prospectos' }]}
        />
        <SectionCard title="Cargando conversion">
          <DataState title="Sincronizando información" message="Consultando el borrador y los catálogos relacionados." />
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
          actions={[{ label: 'Volver a prospectos', variant: 'ghost', to: '/cms/prospectos' }]}
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
      ? 'Reactivación de cliente'
      : 'Conversión de prospecto'
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
        description="Este flujo guarda temporalmente la información en cuatro pasos: datos de usuario, operación, ficha médica y huella biometrica. Solo al finalizar se crea/actualiza el cliente y la nueva operación."
        actions={[{
          label: isReactivation ? 'Volver a cliente' : 'Volver a prospectos',
          variant: 'ghost',
          to: isReactivation ? `/cms/clientes/${clientId}` : '/cms/prospectos'
        }]}
      />

      {data.crossCityWarning ? (
        <div className="_mb-lg">
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

      {activeStep === 1 && (
        <SectionCard
          eyebrow="Paso 1"
          title="Datos de usuario"
          description="Aquí se define la cuenta del nuevo cliente y la información administrativa principal."
        >
          <ConversionStepUser
            userForm={userForm}
            password={password}
            confirmPassword={confirmPassword}
            showPassword={showPassword}
            showConfirmPassword={showConfirmPassword}
            fieldErrors={fieldErrors}
            isSaving={isSaving}
            isCancelling={isCancelling}
            isReactivation={isReactivation}
            hasPassword={hasPassword}
            onChangePassword={(value) => wizard.setPassword(value)}
            onChangeConfirmPassword={(value) => wizard.setConfirmPassword(value)}
            onToggleShowPassword={() => wizard.setShowPassword(!showPassword)}
            onToggleShowConfirmPassword={() => wizard.setShowConfirmPassword(!showConfirmPassword)}
            onSubmit={handleSaveStep1}
            onCancel={handleCancelDraft}
            onUserChange={handleUserChange}
          />
        </SectionCard>
      )}

      {activeStep === 2 && (
        <SectionCard
          eyebrow="Paso 2"
          title="Crear operación"
          description="Configura el servicio que el prospecto adquiere y los datos base de la nueva operación."
        >
          <ConversionStepOperation
            operationForm={operationForm}
            selectedService={selectedService}
            data={data}
            fieldErrors={fieldErrors}
            today={today}
            isSaving={isSaving}
            isCancelling={isCancelling}
            onChange={handleOperationChange}
            onUpdateDueDate={updateDueDate}
            onSubmit={handleSaveStep2}
            onBack={() => setActiveStep(1)}
            onCancel={handleCancelDraft}
          />
        </SectionCard>
      )}

      {activeStep === 3 && (
        <SectionCard
          eyebrow="Paso 3"
          title="Ficha médica"
          description="Completa la información clínica general y, si aplica, las respuestas del procedimiento seleccionado."
        >
          <ConversionStepMedical
            medicalForm={medicalForm}
            medicalDocumentFile={medicalDocumentFile}
            data={data}
            fieldErrors={fieldErrors}
            isSaving={isSaving}
            isCancelling={isCancelling}
            onChange={handleMedicalChange}
            onDocumentChange={handleMedicalDocumentChange}
            onUpdateAntecedente={updateAntecedente}
            onUpdateImplante={updateImplante}
            onUpdateCirugia={updateCirugia}
            onUpdateFieldResponse={updateFieldResponse}
            onUpdateAnalisisField={updateAnalisisField}
            onTogglePatologia={togglePatologia}
            onSubmit={handleSaveStep3}
            onBack={() => setActiveStep(2)}
            onCancel={handleCancelDraft}
            onAddAntecedente={() => wizard.setMedicalForm({ ...medicalForm, antecedentes: [...medicalForm.antecedentes, blankAntecedente()] })}
            onRemoveAntecedente={(index) => wizard.setMedicalForm({ ...medicalForm, antecedentes: medicalForm.antecedentes.filter((_, i) => i !== index) })}
            onAddImplante={() => wizard.setMedicalForm({ ...medicalForm, implantes: [...medicalForm.implantes, blankImplante()] })}
            onRemoveImplante={(index) => wizard.setMedicalForm({ ...medicalForm, implantes: medicalForm.implantes.filter((_, i) => i !== index) })}
            onAddCirugia={() => wizard.setMedicalForm({ ...medicalForm, cirugias: [...medicalForm.cirugias, blankCirugia()] })}
            onRemoveCirugia={(index) => wizard.setMedicalForm({ ...medicalForm, cirugias: medicalForm.cirugias.filter((_, i) => i !== index) })}
          />
        </SectionCard>
      )}

      {activeStep === 4 && (
        <SectionCard
          eyebrow="Paso 4"
          title="Huella biometrica"
          description="Simula el enrolamiento con un lector SecuGen Hamster Pro 20. Esta capa queda lista para reemplazar el proveedor mock por la WebAPI real."
        >
          <ConversionStepBiometric
            biometricForm={biometricForm}
            biometricStatus={biometricStatus}
            biometricModalOpen={biometricModalOpen}
            biometricModalSubjectName={biometricModalSubjectName}
            fieldErrors={fieldErrors}
            isSaving={isSaving}
            isCancelling={isCancelling}
            onOpenBiometricModal={handleOpenBiometricModal}
            onCloseBiometricModal={handleCloseBiometricModal}
            onConfirmCapture={handleConfirmCapture}
            onSubmit={handleSaveBiometricStep}
            onBack={() => setActiveStep(3)}
            onCancel={handleCancelDraft}
          />
        </SectionCard>
      )}

      {activeStep === 5 && (
        <SectionCard eyebrow="Paso 5" title="Primer pago" description="Activa la casilla para registrar el primer pago en este paso. Si lo activas, el comprobante es obligatorio.">
          <ConversionStepPayment
            shouldRegisterFirstPayment={shouldRegisterFirstPayment}
            firstPaymentDetails={firstPaymentDetails}
            firstPaymentAmount={firstPaymentAmount}
            paymentQrImageUrl={paymentQrImageUrl}
            fieldErrors={fieldErrors}
            isSaving={isSaving}
            isCancelling={isCancelling}
            onTogglePayment={(checked) => {
              wizard.setShouldRegisterFirstPayment(checked)
              if (!checked) {
                wizard.setFirstPaymentReceipt(null)
                wizard.setFirstPaymentDetails('')
              }
            }}
            onReceiptChange={(event) => wizard.setFirstPaymentReceipt(event.target.files?.[0] || null)}
            onDetailsChange={(event) => wizard.setFirstPaymentDetails(event.target.value)}
            onQrModalToggle={(open) => setQrModalOpen(open)}
            onSubmit={handleFinalize}
            onBack={() => setActiveStep(4)}
            onCancel={handleCancelDraft}
          />
        </SectionCard>
      )}

      {qrModalOpen && paymentQrImageUrl ? (
        <div className="qr-modal" role="dialog" aria-modal="true" aria-label="QR de pago">
          <button
            aria-label="Cerrar visor de QR"
            className="qr-modal__backdrop"
            type="button"
            onClick={() => setQrModalOpen(false)}
          />
          <div className="qr-modal__content">
            <div className="qr-modal__header">
              <div>
                <span>QR de pago</span>
                <strong>Vista ampliada</strong>
              </div>
              <button className="button button--ghost button--compact" type="button" onClick={() => setQrModalOpen(false)}>
                Cerrar
              </button>
            </div>
            <img
              alt="QR de pago bancario ampliado"
              className="qr-modal__image"
              src={paymentQrImageUrl}
            />
          </div>
        </div>
      ) : null}
      <ConfirmDialogModal />
    </div>
  )
}
