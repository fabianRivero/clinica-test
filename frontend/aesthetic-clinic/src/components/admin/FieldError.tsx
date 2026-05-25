type FieldErrorProps = {
  message?: string | null
}

export function FieldError({ message }: FieldErrorProps) {
  if (!message) return null
  return <small className="field__error">{message}</small>
}