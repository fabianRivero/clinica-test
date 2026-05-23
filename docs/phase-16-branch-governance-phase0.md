# Phase 0 — Branch governance alignment (multi-sucursal)

Date: 2026-05-22

## Decisions confirmed

1. **Only `ADMIN_PRINCIPAL` can manage branches**.
2. Branch deactivation is **soft disable only** (`Sucursal.activa = false`).
3. Admin reassignment must **never leave a branch without an active branch admin**.
4. Before deactivation, system must show warnings for:
   - pending appointments,
   - pending/unverified payments,
   - open/incomplete processes.
5. Critical branch operations must support **idempotency**.
6. Branch list UI must support filters by:
   - status,
   - city,
   - admin name,
   - branch.
   
   > No free text search for now.

---

## Phase 0 contracts to lock before implementation

## 1) Roles and permissions matrix (branch management)

| Operation | ADMIN_PRINCIPAL | ADMIN_SUCURSAL | TRABAJADOR |
|---|---:|---:|---:|
| List branches (management view) | ✅ | ❌ | ❌ |
| Create branch | ✅ | ❌ | ❌ |
| Edit branch | ✅ | ❌ | ❌ |
| Change branch admin | ✅ | ❌ | ❌ |
| Deactivate/activate branch | ✅ | ❌ | ❌ |
| Read deactivation impact | ✅ | ❌ | ❌ |

Authorization failures must return `403` with a stable business error code.

---

## 2) Pending-impact definition for deactivation warnings

The deactivation impact service must return counters per category:

- `appointments_pending`
  - future scheduled appointments,
  - in-progress appointments.
- `payments_pending`
  - unverified payments,
  - payments in pending state.
- `processes_pending`
  - operational records not in terminal status (closed/completed/cancelled).

### Candidate model mapping (to validate in Phase 1 implementation)

- Appointments: `operations.CitaProspecto`, `operations.CitaClienteLibre`, `operations.CitaMedica`.
- Payments: `billing.PagoRealizado` and/or quota/payment workflow entities.
- Processes: operations workflow entities with non-terminal states.

Final mapping is implemented in Phase 1 with explicit query rules per model/status.

---

## 3) Idempotency contract

Use request header: `Idempotency-Key: <uuid-or-random-string>`.

### Endpoints that must be idempotent

- Create branch.
- Change branch admin.
- Deactivate branch.
- Activate branch.

### Behavioral rules

- Same actor + same endpoint + same idempotency key + same payload fingerprint:
  - return previous successful response (no duplicated side effects).
- Same key with different payload fingerprint:
  - return conflict error.
- Missing key on required operations:
  - reject request with validation error.

### Retention window (initial)

- Store keys/results for **24 hours**.

This initial retention can be tuned later based on operational telemetry.

---

## 4) Branch listing filter contract (no text search)

`GET /api/admin/branches?status=<active|inactive|all>&city=<city>&admin_name=<name>&branch_id=<id>`

- `status` default: `all`.
- `city`, `admin_name`, `branch_id` are optional.
- Filters are combinable.
- Response must include pagination metadata.

---

## Deliverables completed in Phase 0

- [x] Functional decisions consolidated.
- [x] Permissions matrix locked.
- [x] Deactivation warning categories locked.
- [x] Idempotency policy and retention proposed.
- [x] Listing filters locked (without free-text search).

## Next step (Phase 1)

Implement backend permission guards + soft-disable behavior + branch inactive access guard + transactional admin reassignment invariant.
