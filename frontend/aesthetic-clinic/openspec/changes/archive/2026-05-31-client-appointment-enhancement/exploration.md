# Exploration: Client Appointment List Enhancement

## Current State

### AdminPaymentsPage Month Navigation (Reference Implementation)

The `AdminPaymentsPage.tsx` implements month navigation with the following pattern:

**State Management (lines 36-38, 51, 60-73):**
```typescript
const [month, setMonth] = useState(now.getMonth() + 1)
const [year, setYear] = useState(now.getFullYear())
const viewedMonthLabel = `${monthNames[month - 1]} ${year}`

const changeMonth = (direction: -1 | 1) => {
  setMonth((current) => {
    const next = current + direction
    if (next < 1) { setYear((y) => y - 1); return 12 }
    if (next > 12) { setYear((y) => y + 1); return 1 }
    return next
  })
}
```

**UI Rendering (lines 326-333):**
```tsx
<SectionCard
  action={
    <div className="expense-period-controls">
      <button className="button button--ghost" type="button" onClick={() => changeMonth(-1)}>←</button>
      <div>
        <span className="eyebrow">Mes seleccionado</span>
        <h3>{viewedMonthLabel}</h3>
      </div>
      <button className="button button--ghost" type="button" onClick={() => changeMonth(1)}>→</button>
    </div>
  }
>
```

### ClientAppointmentSection (Current)

- Receives `appointments: ClientAppointment[]` prop (all appointments for a client)
- Renders a simple `<table>` with no pagination, no filtering, no month grouping
- Props interface includes appointment action handlers (cancel, reschedule, biometric confirm, etc.)

### useClientDetail Hook

- Calls `getAdminClientDetail(clientId)` which returns `AdminClientDetailResponse` containing `appointments: ClientAppointment[]`
- **No server-side filtering** — all appointments are loaded at once
- Has similar filter state patterns for operations (`operationStatusFilter`) and quotas (`pendingQuotaProcedureFilter`)

### Appointment Data Structure (`ClientAppointment`)

```typescript
type ClientAppointment = {
  id: string
  rawId: number
  operationRawId: number | null
  operation: string
  specialist: string
  dateTime: string        // ISO datetime string
  status: string          // e.g., "Programada", "Cancelada"
  statusTone: 'approved' | 'warning' | 'danger' | 'observed' | 'pending'
  verificationStatus: 'pendiente' | 'verificada' | 'no_requerida'
  canManage: boolean
  canMarkPendingBiometric: boolean
  canConfirmBiometric: boolean
  canCancelFromVerification: boolean
  isFreeMedicalAppointment?: boolean
}
```

## Affected Areas

| File | Change Type | Reason |
|------|-------------|--------|
| `src/pages/admin/client-detail/useClientDetail.ts` | Modify | Add month/year state, status filter state, pagination state, filtering logic |
| `src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Modify | Add month nav controls, status filter UI, pagination buttons, month grouping display |
| `src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Modify | Wire new state/props through to ClientAppointmentSection |
| Backend `api/admin/clientes/{id}/` | Potential API change | If client-side filtering is insufficient for large datasets |

## Approaches

### Approach A: Pure Client-Side Filtering (Recommended)

All filtering, pagination, and month grouping happens in the `useClientDetail` hook and `ClientAppointmentSection` component. No backend changes required.

**Implementation:**
1. Add `appointmentMonth`, `appointmentYear`, `appointmentStatusFilter` state to hook
2. Add `visibleAppointmentCount` state (default 5)
3. Compute `filteredAppointments` by: filter by status → group by month → sort by dateTime
4. Pass `visibleAppointments` (first N after month filter) to component
5. Component renders month nav controls (like AdminPaymentsPage), status dropdown, "Ver más"/"Ver menos" buttons

**Pros:**
- No backend changes needed
- Works immediately with existing API
- Faster iteration

**Cons:**
- Large appointment histories may slow down initial load (all data fetched regardless)
- Month navigation jumps to "current month" on change, but all months still fetched

**Effort:** Low-Medium

### Approach B: Server-Side Pagination + Filtering

Add `month`, `year`, `status`, `page`, `page_size` query params to the `getAdminClientDetail` endpoint. Backend filters/paginates.

**Pros:**
- Scales to clients with many appointments
- True pagination performance

**Cons:**
- Requires backend changes (Django REST)
- More complex implementation
- Status filter would need to be added to API

**Effort:** High

## Recommendation

**Approach A (Pure Client-Side)** is recommended for initial implementation. The codebase already loads all appointments client-side with similar filter patterns already implemented (e.g., `operationStatusFilter`, `pendingQuotaProcedureFilter`). The `expenseUtils.ts` `monthNames` array can be reused.

If performance becomes an issue (clients with 100+ appointments), Approach B can be pursued as a follow-up.

## Frontend Changes Summary

### useClientDetail.ts
- Add: `appointmentMonth`, `appointmentYear`, `appointmentStatusFilter`, `visibleAppointmentCount`
- Add: `changeAppointmentMonth(direction)` function
- Add: `appointmentStatuses` (unique status values from data)
- Add: `filteredAppointments` (by status), `appointmentsByMonth` (grouped), `visibleAppointments` (paginated slice)

### ClientAppointmentSection.tsx
- Add `action` prop to `SectionCard` for month navigation (like AdminPaymentsPage)
- Add status filter `<select>` above table
- Add "Ver más" / "Ver menos" buttons below table
- Group table rows by month with month headers

### AdminClientDetailPage.tsx
- Pass new props: `appointmentMonth`, `appointmentYear`, `appointmentStatusFilter`, `visibleAppointmentCount`, plus setters

## Backend API Considerations

The current `getAdminClientDetail` returns all appointments. For Approach A, no changes needed. For Approach B, these params would be needed:
- `month` (1-12)
- `year` (YYYY)
- `status` (optional filter)
- `page`, `page_size` for pagination

## Risks

1. **Large dataset performance**: If clients have 50+ appointments, loading all for client-side filtering may cause lag
2. **Month navigation UX**: Navigating months while keeping filter state may confuse users (reset filter when changing month?)
3. **Backend coupling**: If Approach B is eventually needed, the frontend implementation will need refactoring

## Ready for Proposal

**Yes** — clear scope, reference implementation exists, data structure understood. Recommend starting with Approach A (client-side) and noting Approach B as future optimization path.