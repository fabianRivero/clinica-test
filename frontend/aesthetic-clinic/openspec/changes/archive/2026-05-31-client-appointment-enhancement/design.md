# Design: Client Appointment List Enhancement

## Technical Approach

Pure client-side filtering, pagination, and month navigation. All state lives in `useClientDetail` hook, derived computations use `useMemo`. UI follows existing patterns from `AdminPaymentsPage` (lines 320-350) and `expenseUtils.ts` for `monthNames`.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Month nav pattern | Mirror AdminPaymentsPage lines 326-333 | Consistent UX across admin pages |
| CSS class for month controls | `expense-period-controls` | Reuse existing component, avoid duplication |
| Status options | Derive dynamically from `appointments` via `useMemo` | No hardcoding, adapts to API changes |
| Reset on month change | `visibleAppointmentCount` resets to 5 | Spec requirement, prevents stale pagination |
| Button styles | `button--secondary` for "Ver más", `button--ghost` for "Ver menos" | Matches spec; ghost for secondary action |

## Data Flow

```
useClientDetail (state) ──→ AdminClientDetailPage (props wiring) ──→ ClientAppointmentSection (render)
     │
     ├── appointmentMonth / appointmentYear
     ├── appointmentStatusFilter
     ├── visibleAppointmentCount
     │
     └── useMemo: filteredAppointments ──► visibleAppointments (slice)
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/pages/admin/client-detail/useClientDetail.ts` | Modify | Add 4 state vars, 3 derived computations, return new props |
| `src/pages/admin/client-detail/ClientAppointmentSection.tsx` | Modify | Add month nav, status filter, pagination UI; replace `appointments` prop with `visibleAppointments` |
| `src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Modify | Wire new props from `useClientDetail` to `ClientAppointmentSection` |

## State Management (useClientDetail.ts)

```typescript
// New state
const [appointmentMonth, setAppointmentMonth] = useState(now.getMonth() + 1)
const [appointmentYear, setAppointmentYear] = useState(now.getFullYear())
const [appointmentStatusFilter, setAppointmentStatusFilter] = useState('')
const [visibleAppointmentCount, setVisibleAppointmentCount] = useState(5)

// Month navigation (mirrors AdminPaymentsPage)
const changeAppointmentMonth = (direction: -1 | 1) => {
  setAppointmentMonth(current => {
    const next = current + direction
    if (next < 1) { setAppointmentYear(y => y - 1); return 12 }
    if (next > 12) { setAppointmentYear(y => y + 1); return 1 }
    return next
  })
  setVisibleAppointmentCount(5) // Reset pagination on month change
}

// Derived state
const viewedMonthLabel = `${monthNames[appointmentMonth - 1]} ${appointmentYear}`

const filteredAppointments = useMemo(() => {
  if (!data?.appointments) return []
  return data.appointments.filter(a => {
    const d = new Date(a.dateTime)
    return d.getMonth() + 1 === appointmentMonth
      && d.getFullYear() === appointmentYear
      && (!appointmentStatusFilter || a.status === appointmentStatusFilter)
  })
}, [data?.appointments, appointmentMonth, appointmentYear, appointmentStatusFilter])

const visibleAppointments = filteredAppointments.slice(0, visibleAppointmentCount)
const hasMore = visibleAppointmentCount < filteredAppointments.length
const hasLess = visibleAppointmentCount > 5
const appointmentStatuses = useMemo(
  () => [...new Set(data?.appointments.map(a => a.status) ?? [])].sort(),
  [data?.appointments]
)
```

## Props Contract (ClientAppointmentSection)

```typescript
// Replace appointments: ClientAppointment[] with:
visibleAppointments: ClientAppointment[]
filteredTotal: number
viewedMonthLabel: string
appointmentMonth: number
appointmentYear: number
changeAppointmentMonth: (dir: -1 | 1) => void
appointmentStatusFilter: string
setAppointmentStatusFilter: (v: string) => void
appointmentStatuses: string[]
visibleAppointmentCount: number
setVisibleAppointmentCount: (v: number) => void
hasMore: boolean
hasLess: boolean
```

## CSS / Class Naming Conventions

- Month nav container: `expense-period-controls` (reused from AdminPaymentsPage)
- Eyebrow label: `eyebrow` (existing pattern)
- Section margin bottom: `_mb-md` (existing utility)
- Flex between: `_flex-between` (existing utility)
- Button variants: `button button--secondary`, `button button--ghost`
- "Ver menos" appears only when `hasLess = true`

## Empty Month Handling

When `filteredAppointments.length === 0`:
```tsx
<DataState 
  title={`No hay citas en ${viewedMonthLabel}`} 
  message="Intenta con otro mes o ajusta el filtro." 
/>
```

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `changeAppointmentMonth` wrapping logic | Test edge cases: Jan→Dec, Dec→Jan |
| Unit | `filteredAppointments` filtering | Test month/year/status combinations |
| Unit | `hasMore`/`hasLess` boundaries | Test at exactly 5, exactly 10, more than 10 |
| Integration | Full flow: navigate month → filter status → paginate | Smoke test in AdminClientDetailPage |

## Open Questions

- [ ] None — spec is complete and unambiguous.

## Next Step

Ready for tasks (sdd-tasks).