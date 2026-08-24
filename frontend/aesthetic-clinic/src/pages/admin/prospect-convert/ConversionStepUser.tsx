import { type ChangeEvent, type FormEvent } from 'react'

import type { ProspectConversionUserData } from '../../../types/prospectConversion'

import type { FieldErrors } from './conversionHelpers'

type Props = {
  userForm: ProspectConversionUserData
  password: string
  confirmPassword: string
  showPassword: boolean
  showConfirmPassword: boolean
  fieldErrors: FieldErrors
  isSaving: boolean
  isCancelling: boolean
  isReactivation: boolean
  hasPassword: boolean
  onChangePassword: (value: string) => void
  onChangeConfirmPassword: (value: string) => void
  onToggleShowPassword: () => void
  onToggleShowConfirmPassword: () => void
  onSubmit: (event: FormEvent) => void
  onCancel: () => void
  onUserChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void
}

export function ConversionStepUser({
  userForm,
  password,
  confirmPassword,
  showPassword,
  showConfirmPassword,
  fieldErrors,
  isSaving,
  isCancelling,
  isReactivation,
  hasPassword,
  onChangePassword,
  onChangeConfirmPassword,
  onToggleShowPassword,
  onToggleShowConfirmPassword,
  onSubmit,
  onCancel,
  onUserChange,
}: Props) {
  return (
    <form className="form-grid" onSubmit={onSubmit}>
      <label className="field">
        <span>Primer nombre <abbr title="obligatorio" className="required-mark">*</abbr></span>
        <input className="input" name="primerNombre" value={userForm.primerNombre} onChange={onUserChange} />
        {fieldErrors.primerNombre ? <small className="field__error">{fieldErrors.primerNombre}</small> : null}
      </label>
      <label className="field">
        <span>Segundo nombre</span>
        <input className="input" name="segundoNombre" value={userForm.segundoNombre} onChange={onUserChange} />
      </label>
      <label className="field">
        <span>Apellido paterno <abbr title="obligatorio" className="required-mark">*</abbr></span>
        <input className="input" name="apellidoPaterno" value={userForm.apellidoPaterno} onChange={onUserChange} />
        {fieldErrors.apellidoPaterno ? <small className="field__error">{fieldErrors.apellidoPaterno}</small> : null}
      </label>
      <label className="field">
        <span>Apellido materno</span>
        <input className="input" name="apellidoMaterno" value={userForm.apellidoMaterno} onChange={onUserChange} />
      </label>
      <label className="field">
        <span>CI <small className="field__hint">(opcional)</small></span>
        <input className="input" name="ci" value={userForm.ci} onChange={onUserChange} />
        <small className="field__hint">Si el cliente no recuerda su CI, podés dejarlo vacío. Se le asignará un código único al guardar.</small>
        {fieldErrors.ci ? <small className="field__error">{fieldErrors.ci}</small> : null}
      </label>
      <label className="field">
        <span>Nombre de usuario <abbr title="obligatorio" className="required-mark">*</abbr></span>
        <input className="input" name="username" value={userForm.username} onChange={onUserChange} />
        {fieldErrors.username ? <small className="field__error">{fieldErrors.username}</small> : null}
      </label>
      <label className="field">
        <span>Email</span>
        <input className="input" name="email" type="email" value={userForm.email} onChange={onUserChange} />
      </label>
      {!isReactivation && (
        <>
          <label className="field field--password">
            <span>Contraseña <abbr title="obligatorio" className="required-mark">*</abbr></span>
            <input
              className="input"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(event) => onChangePassword(event.target.value)}
              placeholder={hasPassword ? 'Dejar vacío para conservar la actual' : ''}
            />
            <button
              className="field__toggle"
              type="button"
              onClick={onToggleShowPassword}
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
            <span>Confirmar contraseña <abbr title="obligatorio" className="required-mark">*</abbr></span>
            <input
              className="input"
              type={showConfirmPassword ? 'text' : 'password'}
              value={confirmPassword}
              onChange={(event) => onChangeConfirmPassword(event.target.value)}
            />
            <button
              className="field__toggle"
              type="button"
              onClick={onToggleShowConfirmPassword}
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
        <span>Teléfono</span>
        <input className="input" name="telefono" type="tel" value={userForm.telefono} onChange={onUserChange} />
      </label>
      <label className="field">
        <span>Fecha de nacimiento <abbr title="obligatorio" className="required-mark">*</abbr></span>
        <input className="input" name="fechaNacimiento" type="date" value={userForm.fechaNacimiento} onChange={onUserChange} />
        {fieldErrors.fechaNacimiento ? <small className="field__error">{fieldErrors.fechaNacimiento}</small> : null}
      </label>
      <label className="field">
        <span>Nro. hijos</span>
        <input className="input" name="nroHijos" type="number" min="0" value={userForm.nroHijos} onChange={onUserChange} />
        {fieldErrors.nroHijos ? <small className="field__error">{fieldErrors.nroHijos}</small> : null}
      </label>
      <label className="field">
        <span>Ocupación</span>
        <input className="input" name="ocupacion" value={userForm.ocupacion} onChange={onUserChange} />
      </label>
      <label className="field field--full">
        <span>Dirección</span>
        <input className="input" name="direccionDomicilio" value={userForm.direccionDomicilio} onChange={onUserChange} />
      </label>
      <label className="field field--full">
        <span>Observaciones del cliente</span>
        <textarea className="input textarea" name="observacionesCliente" rows={4} value={userForm.observacionesCliente} onChange={onUserChange} />
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
        <button className="button" disabled={isSaving || isCancelling} type="submit">
          {isSaving ? 'Guardando...' : 'Guardar y continuar'}
        </button>
      </div>
    </form>
  )
}
