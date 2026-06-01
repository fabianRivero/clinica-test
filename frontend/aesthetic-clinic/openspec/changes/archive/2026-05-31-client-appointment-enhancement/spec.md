# Spec: Client Appointment List Enhancement

## Change Name
`client-appointment-enhancement`

## Intent
Improve admin's ability to manage and navigate client appointments efficiently by adding:
1. Status filter dropdown (Programada, Cancelada, Realizada, etc.)
2. Pagination: show 5 items, "Ver más" (+5), "Ver menos" (-5)
3. Month navigation with month grouping display

## Approach
**Pure client-side** - All filtering, pagination, and month grouping happens in `useClientDetail` hook and `ClientAppointmentSection` component. No backend API changes required.

Reference implementation: `AdminPaymentsPage.tsx` lines 320-350 for month navigation pattern.

---

## Requirements

### Requirement 1: Month Navigation

**Scenario**: Admin wants to browse appointments by month

**Given** the client detail page is open
**When** the admin views the "Todas las citas del cliente" section
**Then** month navigation controls should appear above the table
**And** they should display the current selected month/year label

**UI Pattern** (from AdminPaymentsPage):
```
← [Mes seleccionado] [Mes/Año] →
```

**Behavior**:
- Left arrow button: decrement month (wrap to previous year at January)
- Right arrow button: increment month (wrap to next year at December)
- Default to current month/year when page loads
- `viewedMonthLabel` format: "Mayo 2026" (Spanish, using existing `monthNames` array)

---

### Requirement 2: Status Filter

**Scenario**: Admin wants to filter appointments by status

**Given** the client detail page is open
**When** the admin views the "Todas las citas del cliente" section
**Then** a status filter dropdown should appear above the table

**Filter Options**:
- "" (empty) = "Todos"
- "Programada"
- "Cancelada"
- "Realizada"
- "No asistió"
- "Pendiente biometría"

**Behavior**:
- Filter applies to the currently selected month
- Changing month does NOT reset the status filter
- Default value: "" (show all statuses)

---

### Requirement 3: Pagination (Show 5, Ver más, Ver menos)

**Scenario**: Admin wants to see appointments in manageable chunks

**Given** there are more than 5 appointments in the selected month
**When** the admin views the appointment list
**Then** only the first 5 appointments should be displayed
**And** a "Ver más" button should appear below the table

**"Ver más" Button**:
- Label: "Ver más"
- Style: `button button--secondary`
- On click: show 5 more appointments (increment visible count by 5)
- Disabled when all appointments for the month are visible

**"Ver menos" Button**:
- Label: "Ver menos"
- Style: `button button--ghost`
- On click: show 5 fewer appointments (decrement visible count by 5, minimum 5)
- Only appears when visible count > 5
- Disabled when showing exactly 5

**Display Format**:
```
Mostrando X de Y citas de [Mes/Año]
[Ver menos] [Ver más]
```

---

### Requirement 4: Month Grouping Display

**Scenario**: Admin wants to see which month the displayed appointments belong to

**Given** the appointment list is displayed
**When** the admin scrolls to the pagination controls
**Then** the month/year label should be visible showing which month's appointments are displayed

**Behavior**:
- Group appointments by extracting month/year from `dateTime` field
- Only appointments matching the selected month/year are displayed
- Empty months show "No hay citas en [Mes/Año]" instead of table

---

## Component Changes

### 1. useClientDetail.ts

**New State**:
```typescript
const [appointmentMonth, setAppointmentMonth] = useState(now.getMonth() + 1)
const [appointmentYear, setAppointmentYear] = useState(now.getFullYear())
const [appointmentStatusFilter, setAppointmentStatusFilter] = useState('')
const [visibleAppointmentCount, setVisibleAppointmentCount] = useState(5)
```

**New Derived State**:
```typescript
// Unique status options from appointments
const appointmentStatuses = useMemo(() => {
  const statuses = [...new Set(appointments.map(a => a.status))]
  return statuses.sort()
}, [appointments])

// Month navigation function
const changeAppointmentMonth = (direction: -1 | 1) => {
  setAppointmentMonth(current => {
    const next = current + direction
    if (next < 1) { setAppointmentYear(y => y - 1); return 12 }
    if (next > 12) { setAppointmentYear(y => y + 1); return 1 }
    return next
  })
}

// Filtered appointments (by status + month)
const filteredAppointments = useMemo(() => {
  return appointments.filter(a => {
    const appointmentDate = new Date(a.dateTime)
    const matchesMonth = appointmentDate.getMonth() + 1 === appointmentMonth
    const matchesYear = appointmentDate.getFullYear() === appointmentYear
    const matchesStatus = !appointmentStatusFilter || a.status === appointmentStatusFilter
    return matchesMonth && matchesYear && matchesStatus
  })
}, [appointments, appointmentMonth, appointmentYear, appointmentStatusFilter])

// Visible slice for pagination
const visibleAppointments = filteredAppointments.slice(0, visibleAppointmentCount)
const hasMore = visibleAppointmentCount < filteredAppointments.length
const hasLess = visibleAppointmentCount > 5
```

**New Props to Pass**:
```typescript
{
  // Navigation
  appointmentMonth,
  appointmentYear,
  changeAppointmentMonth,
  viewedMonthLabel, // `${monthNames[appointmentMonth - 1]} ${appointmentYear}`

  // Filter
  appointmentStatusFilter,
  setAppointmentStatusFilter,
  appointmentStatuses,

  // Pagination
  visibleAppointments,
  visibleAppointmentCount,
  setVisibleAppointmentCount,
  hasMore,
  hasLess,

  // Stats
  totalInMonth: filteredAppointments.length,
}
```

---

### 2. ClientAppointmentSection.tsx

**Props Changes**:
- Replace `appointments: ClientAppointment[]` with `visibleAppointments: ClientAppointment[]`
- Add month navigation props
- Add status filter props
- Add pagination props

**New UI Structure**:
```tsx
<SectionCard
  eyebrow="Agenda"
  title="Todas las citas del cliente"
  description="..."
  action={
    <div className="expense-period-controls">
      <button onClick={() => changeAppointmentMonth(-1)}>←</button>
      <div>
        <span className="eyebrow">Mes seleccionado</span>
        <h3>{viewedMonthLabel}</h3>
      </div>
      <button onClick={() => changeAppointmentMonth(1)}>→</button>
    </div>
  }
>
  {/* Status Filter */}
  <div className="_mb-md">
    <select value={appointmentStatusFilter} onChange={...}>
      <option value="">Todos</option>
      {appointmentStatuses.map(status => (
        <option key={status} value={status}>{status}</option>
      ))}
    </select>
  </div>

  {/* Table or Empty State */}
  {visibleAppointments.length ? (
    <table>...</table>
  ) : (
    <DataState title={`No hay citas en ${viewedMonthLabel}`} ... />
  )}

  {/* Pagination Info + Controls */}
  {filteredAppointments.length > 0 && (
    <div className="_flex-between _mt-md">
      <span>Mostrando {visibleAppointmentCount} de {filteredAppointments.length} citas de {viewedMonthLabel}</span>
      <div>
        {hasLess && (
          <button onClick={() => setVisibleAppointmentCount(c => c - 5)}>Ver menos</button>
        )}
        {hasMore && (
          <button onClick={() => setVisibleAppointmentCount(c => c + 5)}>Ver más</button>
        )}
      </div>
    </div>
  )}
</SectionCard>
```

---

### 3. AdminClientDetailPage.tsx

**Changes**:
- Wire new props from `useClientDetail` to `ClientAppointmentSection`
- Remove passing of raw `appointments` array, pass `visibleAppointments` instead

---

## Edge Cases

1. **Empty month**: Show `DataState` with message "No hay citas en [Mes/Año]"
2. **All filtered out**: If status filter returns no results, show appropriate message
3. **Exactly 5 appointments**: "Ver más" disabled, "Ver menos" hidden (since hasLess = false)
4. **Month with 3 appointments, visibleCount = 8**: Show all 3, "Ver más" disabled, "Ver menos" hidden
5. **Changing month resets visible count**: When month changes, `visibleAppointmentCount` resets to 5

---

## Acceptance Criteria

1. [ ] Month navigation arrows (`←` and `→`) change the displayed month, wrapping correctly between years
2. [ ] Month label displays correctly in Spanish format (e.g., "Mayo 2026")
3. [ ] Status filter dropdown shows all unique statuses from the appointments data
4. [ ] Selecting a status filters the table to show only matching appointments
5. [ ] Table shows maximum 5 appointments by default
6. [ ] "Ver más" increases visible count by 5 (disabled when all are shown)
7. [ ] "Ver menos" decreases visible count by 5 (minimum 5, hidden when showing exactly 5)
8. [ ] Pagination info shows "Mostrando X de Y citas de [Mes/Año]"
9. [ ] Changing month resets visible count to 5
10. [ ] Empty months show appropriate empty state message
11. [ ] All existing appointment actions (cancel, reprogram, biometric) still work correctly

---

## Files to Modify

| File | Change |
|------|--------|
| `src/pages/admin/client-detail/useClientDetail.ts` | Add state, derived state, and pass new props |
| `src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Add month nav, status filter, pagination UI |
| `src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Wire new props through |

---

## Effort Estimate

**Complexity**: Medium
**Lines of change**: ~150-200 (frontend only)
**Backend changes**: None required