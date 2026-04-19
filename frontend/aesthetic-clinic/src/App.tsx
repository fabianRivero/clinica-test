import { Navigate, Route, Routes } from 'react-router-dom'

import { AdminLayout } from './layouts/AdminLayout'
import { AdminCatalogsPage } from './pages/admin/AdminCatalogsPage'
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage'
import { AdminOperationsPage } from './pages/admin/AdminOperationsPage'
import { AdminPaymentsPage } from './pages/admin/AdminPaymentsPage'
import { AdminProspectsPage } from './pages/admin/AdminProspectsPage'
import { AdminStaffPage } from './pages/admin/AdminStaffPage'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/admin" replace />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="prospectos" element={<AdminProspectsPage />} />
        <Route path="operaciones" element={<AdminOperationsPage />} />
        <Route path="pagos" element={<AdminPaymentsPage />} />
        <Route path="catalogos" element={<AdminCatalogsPage />} />
        <Route path="equipo" element={<AdminStaffPage />} />
      </Route>
    </Routes>
  )
}

export default App
