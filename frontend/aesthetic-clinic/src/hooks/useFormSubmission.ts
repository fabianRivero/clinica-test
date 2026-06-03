import { useCallback, useState } from 'react'
import type { ApiError } from '../services/api/apiClient'

type NotificationTone = 'success' | 'info' | 'warning' | 'danger'

type UseFormSubmissionOptions = {
  onSuccess?: (response: unknown) => void | Promise<void>
  successTitle?: string
  successMessage?: string | ((response: unknown) => string)
}

type UseFormSubmissionReturn = {
  isSubmitting: boolean
  submitError: string | null
  fieldErrors: Record<string, string>
  setFieldErrors: (errors: Record<string, string>) => void
  clearFieldError: (field: string) => void
  clearErrors: () => void
  handleSubmit: (action: () => Promise<unknown>, options?: UseFormSubmissionOptions) => Promise<void>
}

function isApiError(error: unknown): error is ApiError {
  return Boolean(error && typeof error === 'object' && 'fieldErrors' in (error as object))
}

export function useFormSubmission(
  showNotification: (input: { title: string; message: string; tone?: NotificationTone }) => void,
): UseFormSubmissionReturn {
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const clearFieldError = useCallback((field: string) => {
    setFieldErrors((current) => {
      if (!current[field]) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }, [])

  const clearErrors = useCallback(() => {
    setSubmitError(null)
    setFieldErrors({})
  }, [])

  const handleSubmit = useCallback(
    async (action: () => Promise<unknown>, options?: UseFormSubmissionOptions) => {
      setIsSubmitting(true)
      setSubmitError(null)
      setFieldErrors({})
      try {
        const response = await action()
        if (options?.onSuccess) {
          await options.onSuccess(response)
        }
        if (options?.successTitle || options?.successMessage) {
          showNotification({
            title: options.successTitle ?? 'Operación exitosa',
            message:
              typeof options.successMessage === 'function'
                ? options.successMessage(response)
                : (options.successMessage ?? (response as { detail?: string })?.detail ?? ''),
            tone: 'success',
          })
        }
      } catch (requestError: unknown) {
        const errorWithFields = isApiError(requestError) ? (requestError as ApiError) : null
        setSubmitError(
          requestError instanceof Error
            ? requestError.message
            : 'Ocurrio un error inesperado.',
        )
        setFieldErrors(errorWithFields?.fieldErrors || {})
      } finally {
        setIsSubmitting(false)
      }
    },
    [showNotification],
  )

  return {
    isSubmitting,
    submitError,
    fieldErrors,
    setFieldErrors,
    clearFieldError,
    clearErrors,
    handleSubmit,
  }
}