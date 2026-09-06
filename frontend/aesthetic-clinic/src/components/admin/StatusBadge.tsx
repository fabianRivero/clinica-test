import type { HTMLAttributes } from 'react'

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
} & Omit<HTMLAttributes<HTMLSpanElement>, 'children'>

export function StatusBadge({ tone, children, ...rest }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-badge--${tone}`} {...rest}>
      {children}
    </span>
  )
}
