import { Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { AdminLayout } from './layouts/AdminLayout'
import { ClientLayout } from './layouts/ClientLayout'
import {
  AdminAllServicesCatalogPage,
  AdminExpenseCategoriesCatalogPage,
  AdminProceduresCatalogPage,
  AdminServiceTypesCatalogPage,
  AdminSkinPathologiesCatalogPage,
  AdminSpecialtiesCatalogPage,
} from './pages/admin/AdminCatalogsPage'
import {
  AdminAvailabilityBlocksPage,
  AdminAvailabilitySchedulesPage,
  AdminAvailabilityVisiblePage,
} from './pages/admin/availability'
import { AdminClientDetailPage } from './pages/admin/client-detail'
import { AdminClientsPage } from './pages/admin/AdminClientsPage'
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage'
import { AdminExpenseCreatePage, AdminExpenseListPage } from './pages/admin/expenses'
import { AdminOperationDetailPage } from './pages/admin/AdminOperationDetailPage'
import { AdminOperationsPage } from './pages/admin/AdminOperationsPage'
import { AdminPaymentsPage } from './pages/admin/AdminPaymentsPage'
import { AdminMessagingPermissionsPage, AdminMessagingTicketsPage } from './pages/admin/AdminTicketsPage'
import { AdminTicketDetailPage } from './pages/admin/AdminTicketDetailPage'
import { AdminProspectConvertPage } from './pages/admin/prospect-convert'
import { AdminProspectCreatePage } from './pages/admin/AdminProspectCreatePage'
import { AdminProspectsPage } from './pages/admin/AdminProspectsPage'
import { AdminStaffCreatePage, AdminStaffManagePage } from './pages/admin/AdminStaffPage'
import { AdminBranchesPage } from './pages/admin/AdminBranchesPage'
import { AdminBranchHistoryPage } from './pages/admin/AdminBranchHistoryPage'
import { AdminBranchAdminsPage } from './pages/admin/AdminBranchAdminsPage'
import { AdminBranchAdminDetailPage } from './pages/admin/AdminBranchAdminDetailPage'
import { LoginPage } from './pages/auth/LoginPage'
import { TabletKioskPage } from './pages/tablet/TabletKioskPage'
import { ClientDashboardPage } from './pages/client/ClientDashboardPage'
import { ClientPaymentsPage } from './pages/client/ClientPaymentsPage'
import { ClientPaymentHistoryPage } from './pages/client/ClientPaymentHistoryPage'
import { ClientReservationsPage } from './pages/client/ClientReservationsPage'
import { ClientTreatmentsPage } from './pages/client/ClientTreatmentsPage'
import { SpecialistLayout } from './layouts/SpecialistLayout'
import { SpecialistAgendaPage } from './pages/specialist/SpecialistAgendaPage'
import { SpecialistMessageDetailPage, SpecialistMessagesCreatePage, SpecialistMessagesTicketsPage } from './pages/specialist/SpecialistMessagesPage'
import { useAuth } from './providers/AuthProvider'
import { NotificationsPage } from './pages/shared/NotificationsPage'
import type { RoleKey } from './types/auth'

function AppLoadingScreen() {
  return (
    <div className="app-state-screen">
      <div className="app-state-screen__card">
        <strong>Validando sesión</strong>
        <p>Estamos comprobando tu acceso y preparando la interfaz.</p>
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
      <Route path="/tablet" element={<TabletKioskPage />} />

      <Route element={<RequireRole allowedRoles={['ADMINISTRADOR']} />}>
        <Route path="/cms" element={<AdminLayout />}>
          <Route index element={<AdminDashboardPage />} />
          <Route path="prospectos" element={<AdminProspectsPage />} />
          <Route path="clientes" element={<AdminClientsPage />} />
          <Route path="clientes/:clientId" element={<AdminClientDetailPage />} />
          <Route path="clientes/:clientId/reactivar" element={<AdminProspectConvertPage />} />
          <Route path="prospectos/nuevo" element={<AdminProspectCreatePage />} />
          <Route path="prospectos/:prospectId/convertir" element={<AdminProspectConvertPage />} />
          <Route path="operaciones" element={<AdminOperationsPage />} />
          <Route path="operaciones/:operationId" element={<AdminOperationDetailPage />} />
          <Route path="gastos" element={<Navigate to="/cms/gastos/lista" replace />} />
          <Route path="gastos/crear" element={<AdminExpenseCreatePage />} />
          <Route path="gastos/lista" element={<AdminExpenseListPage />} />
          <Route
            path="disponibilidad"
            element={<Navigate to="/cms/disponibilidad/visibles" replace />}
          />
          <Route path="disponibilidad/visibles" element={<AdminAvailabilityVisiblePage />} />
          <Route path="disponibilidad/bloques" element={<AdminAvailabilityBlocksPage />} />
          <Route path="disponibilidad/gestionar" element={<AdminAvailabilitySchedulesPage />} />
          <Route path="pagos" element={<Navigate to="/cms/pagos/qr" replace />} />
          <Route path="pagos/qr" element={<AdminPaymentsPage view="qr" />} />
          <Route path="pagos/pendientes" element={<AdminPaymentsPage view="pendientes" />} />
          <Route path="pagos/cuotas" element={<AdminPaymentsPage view="cuotas" />} />
          <Route path="mensajes" element={<Navigate to="/cms/mensajes/permisos" replace />} />
          <Route path="mensajes/permisos" element={<AdminMessagingPermissionsPage />} />
          <Route path="mensajes/fichas" element={<AdminMessagingTicketsPage />} />
          <Route path="mensajes/:ticketId" element={<AdminTicketDetailPage />} />
          <Route
            path="catalogos"
            element={<Navigate to="/cms/catalogos/todos-los-servicios" replace />}
          />
          <Route path="catalogos/todos-los-servicios" element={<AdminAllServicesCatalogPage />} />
          <Route path="catalogos/procedimientos-esteticos" element={<AdminProceduresCatalogPage />} />
          <Route path="catalogos/tipos-servicio" element={<AdminServiceTypesCatalogPage />} />
          <Route path="catalogos/patologias-cutaneas" element={<AdminSkinPathologiesCatalogPage />} />
          <Route path="catalogos/especialidades" element={<AdminSpecialtiesCatalogPage />} />
          <Route path="catalogos/categorias-gasto" element={<AdminExpenseCategoriesCatalogPage />} />
          <Route path="equipo" element={<Navigate to="/cms/equipo/gestionar" replace />} />
          <Route path="equipo/crear" element={<AdminStaffCreatePage />} />
          <Route path="equipo/gestionar" element={<AdminStaffManagePage />} />
          <Route path="equipo/admin-sucursal/crear" element={<AdminBranchAdminsPage view="create" />} />
          <Route path="equipo/admin-sucursal/gestionar" element={<AdminBranchAdminsPage view="manage" />} />
          <Route path="equipo/admin-sucursal/:userId" element={<AdminBranchAdminDetailPage />} />
          <Route path="notificaciones" element={<NotificationsPage />} />
          <Route path="sucursales" element={<Navigate to="/cms/sucursales/editar" replace />} />
          <Route path="sucursales/editar" element={<AdminBranchesPage view="edit" />} />
          <Route path="sucursales/historial" element={<AdminBranchHistoryPage />} />
          <Route path="sucursales/crear" element={<AdminBranchesPage view="create" />} />
        </Route>
      </Route>
      <Route element={<RequireRole allowedRoles={['TRABAJADOR']} />}>
        <Route path="/trabajador" element={<SpecialistLayout />}>
          <Route index element={<Navigate to="/trabajador/agenda" replace />} />
          <Route path="agenda" element={<SpecialistAgendaPage />} />
          <Route path="mensajes" element={<Navigate to="/trabajador/mensajes/fichas" replace />} />
          <Route path="mensajes/fichas" element={<SpecialistMessagesTicketsPage />} />
          <Route path="mensajes/nueva" element={<SpecialistMessagesCreatePage />} />
          <Route path="mensajes/:ticketId" element={<SpecialistMessageDetailPage />} />
          <Route path="notificaciones" element={<NotificationsPage />} />
        </Route>
      </Route>
      <Route element={<RequireRole allowedRoles={['CLIENTE']} />}>
        <Route path="/cliente" element={<ClientLayout />}>
          <Route index element={<ClientDashboardPage />} />
          <Route path="tratamientos" element={<ClientTreatmentsPage />} />
          <Route path="pagos" element={<ClientPaymentsPage />} />
          <Route path="pagos/historial" element={<ClientPaymentHistoryPage />} />
          <Route path="reservas" element={<ClientReservationsPage />} />
          <Route path="notificaciones" element={<NotificationsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  )
}

export default App
