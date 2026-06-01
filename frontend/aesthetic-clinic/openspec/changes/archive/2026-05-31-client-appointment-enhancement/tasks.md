# Tasks: Client Appointment List Enhancement

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~150-200 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Full implementation | PR 1 | All 3 files modified; single PR sufficient for this scope |

---

## Phase 1: useClientDetail.ts — State & Derived Logic

- [x] 1.1 Add state vars: `appointmentMonth`, `appointmentYear`, `appointmentStatusFilter`, `visibleAppointmentCount` with initial values (current month/year, `''`, `5`)
- [x] 1.2 Add `changeAppointmentMonth(direction: -1 | 1)` function with year wrap logic; call `setVisibleAppointmentCount(5)` on month change
- [x] 1.3 Add `viewedMonthLabel` using `monthNames[appointmentMonth - 1]` and `appointmentYear`
- [x] 1.4 Add `filteredAppointments` useMemo filtering by month/year/status from `data?.appointments`
- [x] 1.5 Add `visibleAppointments` (slice), `hasMore`, `hasLess` derived values
- [x] 1.6 Add `appointmentStatuses` useMemo extracting unique statuses from `data?.appointments`
- [x] 1.7 Return all new state and derived values in the hook return object

---

## Phase 2: ClientAppointmentSection.tsx — UI Components

- [x] 2.1 Update props interface: replace `appointments` with `visibleAppointments`, add month nav/status filter/pagination props
- [x] 2.2 Add month navigation controls in `action` prop using `expense-period-controls` CSS class with `←` and `→` buttons
- [x] 2.3 Add `viewedMonthLabel` display with `eyebrow` class above table
- [x] 2.4 Add status filter `<select>` with "Todos" default option; populate from `appointmentStatuses`
- [x] 2.5 Conditionally render table or `DataState` empty message when `visibleAppointments.length === 0`
- [x] 2.6 Add pagination row with "Mostrando X de Y citas de [Mes/Año]" text using `_flex-between _mt-md`
- [x] 2.7 Add "Ver menos" button (`button button--ghost`) visible when `hasLess === true`
- [x] 2.8 Add "Ver más" button (`button button--secondary`) visible when `hasMore === true`

---

## Phase 3: AdminClientDetailPage.tsx — Wiring

- [x] 3.1 Remove passing of raw `appointments` array to `ClientAppointmentSection`
- [x] 3.2 Wire all new props from `useClientDetail` to `ClientAppointmentSection`

---

## Phase 4: Verification

- [ ] 4.1 Smoke test: page loads, default month shown, 5 appointments visible
- [ ] 4.2 Test month navigation: click `→` on December → January + year increments; click `←` on January → December + year decrements
- [ ] 4.3 Test status filter: select "Cancelada" → table filters to cancelled only
- [ ] 4.4 Test "Ver más": with >5 appointments, click "Ver más" → count increases by 5
- [ ] 4.5 Test "Ver menos": with visibleCount > 5, click "Ver menos" → count decreases by 5
- [ ] 4.6 Test month change resets pagination: navigate to another month → visibleCount resets to 5
- [ ] 4.7 Test empty month: navigate to month with no appointments → `DataState` renders with "No hay citas en [Mes/Año]"
- [ ] 4.8 Verify all existing appointment actions (cancel, reprogram, biometric) still function
