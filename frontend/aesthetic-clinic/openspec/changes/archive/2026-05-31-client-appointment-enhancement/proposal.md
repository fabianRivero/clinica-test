# Proposal: Client Appointment List Enhancement

## Change Name
`client-appointment-enhancement`

## Intent
Improve admin's ability to manage and navigate client appointments efficiently by adding filtering, pagination, and month-based organization to the appointment list in AdminClientDetailPage.

## Problem Statement
The current appointment list in `ClientAppointmentSection` displays all appointments without any filtering, pagination, or month navigation. This makes it difficult for admins to find specific appointments when a client has a long history.

## Proposed Solution
Implement client-side filtering, pagination, and month navigation using existing data patterns and reference implementation from `AdminPaymentsPage.tsx`.

---

## Scope

### In Scope
- Add month navigation controls (← Month/Year →)
- Add status filter dropdown (Todos, Programada, Cancelada, Realizada, etc.)
- Add pagination: show 5, "Ver más" (+5), "Ver menos" (-5)
- Group/display appointments by selected month
- Add empty state when no appointments exist for selected month

### Out of Scope
- Backend API changes
- New appointment creation/modification flows
- Export functionality
- Multi-client views

---

## Deliverables

| File | Deliverable |
|------|-------------|
| `src/pages/admin/client-detail/useClientDetail.ts` | New state variables and derived filtered/paginated data |
| `src/pages/admin/client-detail/ClientAppointmentSection.tsx` | New UI controls (month nav, filter, pagination) |
| `src/pages/admin/client-detail/AdminClientDetailPage.tsx` | Wire new props through |

---

## Approach

**Approach A: Pure Client-Side** (Selected)

All filtering, pagination, and month grouping happens in the `useClientDetail` hook and `ClientAppointmentSection` component. No backend changes required.

### Implementation Plan
1. Add state: `appointmentMonth`, `appointmentYear`, `appointmentStatusFilter`, `visibleAppointmentCount`
2. Add derived state: `filteredAppointments` (by status + month), `visibleAppointments` (paginated slice)
3. Add month navigation: `changeAppointmentMonth(direction)` function
4. Update `ClientAppointmentSection` to accept and render new props
5. Wire props in `AdminClientDetailPage`

### Reference Implementation
`AdminPaymentsPage.tsx` lines 320-350 for month navigation pattern:
```tsx
<div className="expense-period-controls">
  <button onClick={() => changeMonth(-1)}>←</button>
  <div>
    <span className="eyebrow">Mes seleccionado</span>
    <h3>{viewedMonthLabel}</h3>
  </div>
  <button onClick={() => changeMonth(1)}>→</button>
</div>
```

---

## Effort Estimate

| Aspect | Estimate |
|--------|----------|
| **Complexity** | Medium |
| **Lines of code** | ~150-200 (frontend only) |
| **Backend changes** | None |
| **Testing** | Manual verification + existing test coverage |
| **Risk** | Low (client-side only, uses existing patterns) |

---

## Risks

1. **Large dataset performance**: If clients have 50+ appointments, loading all for client-side filtering may cause lag
   - *Mitigation*: Start with Approach A, can add server-side pagination later if needed

2. **Month navigation UX**: Navigating months while keeping filter state may confuse users
   - *Mitigation*: Changing month does NOT reset the status filter; only pagination resets on month change

---

## Alternatives Considered

### Approach B: Server-Side Pagination + Filtering
- **Pros**: Scales better for clients with many appointments
- **Cons**: Requires backend changes (Django REST), more complex, longer implementation
- **Rejected**: Overkill for initial release; Approach A provides good UX for most cases

---

## Success Criteria

1. Admin can navigate between months using ← → buttons
2. Admin can filter appointments by status using dropdown
3. Admin can paginate through appointments using "Ver más" / "Ver menos"
4. Month/year label is clearly displayed
5. Empty months show appropriate message
6. All existing appointment actions (cancel, reprogram, biometric confirm) still work
7. UI matches existing design patterns (CSS classes, component styles)

---

## Next Steps

1. ✅ Exploration complete
2. ✅ Spec complete  
3. ✅ Design complete
4. → Tasks: Break down into implementation tasks
5. → Apply: Implement the changes
6. → Verify: Test the implementation