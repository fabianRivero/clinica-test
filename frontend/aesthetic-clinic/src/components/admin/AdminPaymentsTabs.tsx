import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/admin/pagos/qr', label: 'Configurar QR' },
  { to: '/admin/pagos/pendientes', label: 'Pagos' },
  { to: '/admin/pagos/cuotas', label: 'Todas las cuotas' },
] as const

export function AdminPaymentsTabs() {
  return (
    <nav className="section-tabs" aria-label="Subsecciones de pagos y cuotas">
      {tabs.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) => `section-tabs__link ${isActive ? 'is-active' : ''}`}
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}
