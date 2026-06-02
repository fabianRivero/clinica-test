import { NavLink } from 'react-router-dom'

import { useAuth } from '../../providers/AuthProvider'

const specialistTabs = [
  { to: '/admin/equipo/crear', label: 'Crear especialista' },
  { to: '/admin/equipo/gestionar', label: 'Gestionar especialistas' },
] as const

const branchAdminTabs = [
  { to: '/admin/equipo/admin-sucursal/crear', label: 'Crear admin sucursal' },
  { to: '/admin/equipo/admin-sucursal/gestionar', label: 'Gestionar admins sucursal' },
] as const

export function AdminStaffTabs() {
  const { user } = useAuth()
  const isMainAdmin = user?.isMainAdmin ?? false

  const tabs = [
    ...specialistTabs,
    ...(isMainAdmin ? branchAdminTabs : []),
  ]

  return (
    <nav className="section-tabs" aria-label="Subsecciones del equipo">
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
