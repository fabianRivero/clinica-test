type DataStateProps = {
  title: string
  message: string
  tone?: 'neutral' | 'danger'
}

export function DataState({ title, message, tone = 'neutral' }: DataStateProps) {
  return (
    <div className={`data-state data-state--${tone}`}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  )
}
