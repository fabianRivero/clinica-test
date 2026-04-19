type StatusBadgeProps = {
  tone:
    | 'primary'
    | 'success'
    | 'warning'
    | 'danger'
    | 'neutral'
    | 'pending'
    | 'observed'
    | 'approved'
  children: string
}

export function StatusBadge({ tone, children }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>
}
