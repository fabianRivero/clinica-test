import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { AdminLayout } from './layouts/AdminLayout'
import { ClientLayout } from './layouts/ClientLayout'
import { AdminCatalogsPage } from './pages/admin/AdminCatalogsPage'
import { AdminAvailabilityPage } from './pages/admin/AdminAvailabilityPage'
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage'
import { AdminOperationsPage } from './pages/admin/AdminOperationsPage'
import { AdminPaymentsPage } from './pages/admin/AdminPaymentsPage'
import { AdminProspectConvertPage } from './pages/admin/AdminProspectConvertPage'
import { AdminProspectCreatePage } from './pages/admin/AdminProspectCreatePage'
import { AdminProspectsPage } from './pages/admin/AdminProspectsPage'
import { AdminStaffPage } from './pages/admin/AdminStaffPage'
import { LoginPage } from './pages/auth/LoginPage'
import { ClientDashboardPage } from './pages/client/ClientDashboardPage'
import { ClientPaymentsPage } from './pages/client/ClientPaymentsPage'
import { ClientReservationCreatePage } from './pages/client/ClientReservationCreatePage'
import { ClientReservationsPage } from './pages/client/ClientReservationsPage'
import { ClientTreatmentsPage } from './pages/client/ClientTreatmentsPage'
import { RoleHomePage } from './pages/shared/RoleHomePage'
import { useAuth } from './providers/AuthProvider'
import type { RoleKey } from './types/auth'

function AppLoadingScreen() {
  return (
    <div className="app-state-screen">
      <div className="app-state-screen__card">
        <strong>Validando sesion</strong>
        <p>Estamos comprobando tu acceso y preparando la interfaz adecuada para tu rol.</p>
      </div>
    </div>
  )
}

function RootRedirect() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return <AppLoadingScreen />
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <Navigate to={user.dashboardPath} replace />
}

function LoginRoute() {
  const { user, isLoading } = useAuth()

  if (isLoading) {
    return <AppLoadingScreen />
  }

  if (user) {
    return <Navigate to={user.dashboardPath} replace />
  }

  return <LoginPage />
}

function RequireRole({ allowedRoles }: { allowedRoles: RoleKey[] }) {
  const { user, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <AppLoadingScreen />
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (!allowedRoles.includes(user.role)) {
    return <Navigate to={user.dashboardPath} replace />
  }

  return <Outlet />
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginRoute />} />

      <Route element={<RequireRole allowedRoles={['ADMINISTRADOR']} />}>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
          <Route path="prospectos" element={<AdminProspectsPage />} />
          <Route path="prospectos/nuevo" element={<AdminProspectCreatePage />} />
          <Route path="prospectos/:prospectId/convertir" element={<AdminProspectConvertPage />} />
          <Route path="operaciones" element={<AdminOperationsPage />} />
          <Route path="disponibilidad" element={<AdminAvailabilityPage />} />
          <Route path="pagos" element={<AdminPaymentsPage />} />
          <Route path="catalogos" element={<AdminCatalogsPage />} />
          <Route path="equipo" element={<AdminStaffPage />} />
        </Route>
      </Route>

      <Route element={<RequireRole allowedRoles={['TRABAJADOR']} />}>
        <Route
          path="/trabajador"
          element={
            <RoleHomePage
              eyebrow="Portal del trabajador"
              title="Interfaz operativa en construccion"
              description="El login ya esta activo y el siguiente paso sera conectar aqui agenda, citas y seguimiento clinico."
            />
          }
        />
      </Route>

      <Route element={<RequireRole allowedRoles={['CLIENTE']} />}>
        <Route path="/cliente" element={<ClientLayout />}>
          <Route index element={<ClientDashboardPage />} />
          <Route path="tratamientos" element={<ClientTreatmentsPage />} />
          <Route path="pagos" element={<ClientPaymentsPage />} />
          <Route path="reservas" element={<ClientReservationsPage />} />
          <Route path="reservas/:operationId/nueva" element={<ClientReservationCreatePage />} />
        </Route>
      </Route>

      <Route path="*" element={<RootRedirect />} />
    </Routes>
  )
}

export default App
