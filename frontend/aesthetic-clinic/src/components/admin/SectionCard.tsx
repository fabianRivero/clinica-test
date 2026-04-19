import type { PropsWithChildren, ReactNode } from 'react'

type SectionCardProps = PropsWithChildren<{
  eyebrow?: string
  title: string
  description?: string
  action?: ReactNode
}>

export function SectionCard({
  eyebrow,
  title,
  description,
  action,
  children,
}: SectionCardProps) {
  return (
    <section className="section-card">
      <header className="section-card__header">
        <div>
          {eyebrow ? <span className="section-card__eyebrow">{eyebrow}</span> : null}
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        {action ? <div className="section-card__action">{action}</div> : null}
      </header>
      <div className="section-card__body">{children}</div>
    </section>
  )
}
