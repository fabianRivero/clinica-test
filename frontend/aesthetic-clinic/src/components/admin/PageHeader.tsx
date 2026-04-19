type PageHeaderProps = {
  eyebrow: string
  title: string
  description: string
  actions?: Array<{
    label: string
    variant?: 'primary' | 'ghost'
  }>
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        <span className="page-header__eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions?.length ? (
        <div className="page-header__actions">
          {actions.map((action) => (
            <button
              key={action.label}
              className={`button ${action.variant === 'ghost' ? 'button--ghost' : ''}`}
              type="button"
            >
              {action.label}
            </button>
          ))}
        </div>
      ) : null}
    </header>
  )
}
