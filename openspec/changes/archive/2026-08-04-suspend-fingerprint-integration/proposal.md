# Proposal: Suspend Fingerprint Integration

## Intent

Temporarily suspend unreliable OS-dependent fingerprint verification and enrollment while retaining code, routes, models, historical biometric data, and reactivation capability. Appointment and customer workflows must continue through explicit manual confirmation.

## Proposal question round

Product assumptions inferred from the approved exploration (no harness questions):
- The suspension is effective immediately for all new biometric capture, verification, and agent write operations; historical biometric records and descriptive status remain readable.
- Manual confirmation is the supported replacement and must preserve existing appointment-state invariants (`metodo_confirmacion=MANUAL`, `verif_biometria=false`).
- Existing URLs remain reachable for compatibility and return a clear `BIOMETRIC_SUSPENDED` response rather than disappearing; legacy endpoints are covered equally.
- Enrollment/prospect conversion must skip biometric capture without blocking the surrounding customer workflow.
- Re-enabling is an operational rollback/forward action controlled by one backend flag, with frontend behavior aligned to the same suspended state.

## Scope

### In Scope
- Add a central `BIOMETRIC_SUSPENDED` feature flag and fail-closed backend gates for biometric endpoints, legacy confirmation, agent access, serializers, and payload affordances.
- Hide fingerprint UI, agent polling, and frontend calls while preserving compatible clients and manual workflows.
- Skip biometric prospect/enrollment capture, preserve historical data/schema, and add regression coverage for suspended behavior and rollback-off behavior.

### Out of Scope
- Deleting or migrating biometric code, tables, columns, templates, audit logs, or enum values.
- Restoring Fernet encryption or changing the fingerprint agent/systemd implementation.
- Changing appointment state definitions or removing biometric historical display data.

## Capabilities

### New Capabilities
- `biometric-suspension`: Central, reversible suspended-mode behavior across backend, frontend, legacy APIs, serializers, and operations.

### Modified Capabilities
- `appointment-states`: Manual confirmation remains the supported transition while biometric confirmation is suspended.

## Approach

Use one backend environment flag (`BIOMETRIC_SUSPENDED`, default false) and a matching frontend build flag. Gate every active entry point before agent or persistence work; return stable `BIOMETRIC_SUSPENDED`/manual-only responses, force `canConfirmBiometric=false`, and keep URLs and imports intact. Return a suspended agent client from the factory so accidental calls fail closed. Preserve historical biometric fields and statuses. Rollback is setting the flag(s) to false and redeploying.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `backend/biometric`, `backend/config` | Modified | Flag gates, legacy endpoints, serializers/payloads, agent factory, prospect flow |
| `frontend/aesthetic-clinic/src` | Modified | Hide affordances/calls and retain manual UX |
| `backend/*/tests`, frontend E2E | Modified | Suspended-mode and manual-fallback regression coverage |
| `fingerprint-agent/`, models, migrations | Preserved | No deletion, schema change, or agent rewrite |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Missed legacy or stale-client path permits biometric work | Med | Inventory and test canonical plus legacy endpoints; fail closed in factory |
| Frontend/backend flags diverge | Med | Backend is authoritative; frontend hides UI and handles suspended responses |
| Manual transition violates model validation | Low | Assert `MANUAL` and `verif_biometria=false` in regression tests |

## Rollback Plan

Set `BIOMETRIC_SUSPENDED=false` and the frontend flag false, redeploy, and verify existing endpoint tests. No data or migration rollback is required.

## Dependencies

- Production configuration must expose the suspension flag(s).
- Existing manual appointment confirmation endpoint remains available.

## Success Criteria

- [ ] No new biometric capture, match, enrollment, or agent write reaches the agent while suspended.
- [ ] All biometric affordances and calls are hidden or return stable suspended responses, including legacy endpoints and serializers.
- [ ] Manual appointment/customer workflows continue and write valid manual confirmation state.
- [ ] Historical biometric data/status remains readable and reactivation requires only flag rollback.
