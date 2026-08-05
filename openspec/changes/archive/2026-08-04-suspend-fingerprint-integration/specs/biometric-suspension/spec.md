# Biometric Suspension Specification

## Purpose

Define reversible suspended-mode behavior for fingerprint verification, enrollment, agent operations, user interfaces, compatibility surfaces, and retained biometric history.

## Requirements

### Requirement: Authoritative Suspended Mode

When biometric suspension is enabled, the backend MUST be authoritative and MUST block every active fingerprint capture, match, enrollment, re-enrollment, verification confirmation, and agent write operation before biometric work occurs. Canonical and legacy biometric URLs MUST remain reachable and return a stable `BIOMETRIC_SUSPENDED` code with manual-only semantics where applicable. Authorization MUST still be evaluated so suspension does not grant access to unauthorized callers.

#### Scenario: Authorized stale client calls verification

- GIVEN suspended mode and an authorized caller using a canonical or legacy verification route
- WHEN the caller initiates or confirms fingerprint verification
- THEN the response MUST contain `BIOMETRIC_SUSPENDED` and indicate no biometric match
- AND no appointment transition, agent contact, or biometric attempt write SHALL occur

#### Scenario: Unauthorized caller remains rejected

- GIVEN suspended mode and a caller lacking the route's required authorization
- WHEN the caller requests a biometric endpoint
- THEN the system MUST return the applicable authorization failure
- AND MUST NOT disclose biometric data or contact an agent

#### Scenario: Agent mutation is suspended while status remains readable

- GIVEN suspended mode and an authorized administrator or agent
- WHEN a create, heartbeat, update, or delete operation is requested
- THEN the system MUST return `BIOMETRIC_SUSPENDED` without mutation
- AND authorized agent listing and historical status reads MAY remain available

### Requirement: Manual-Only User Experience

While suspended, appointment and customer interfaces MUST NOT offer fingerprint confirmation, capture, re-enrollment, agent polling, or offline-agent warnings. They MUST keep manual actions available and SHOULD clearly state that fingerprint functionality is temporarily suspended. Prospect conversion and enrollment workflows MUST continue without requiring biometric capture.

#### Scenario: Current frontend presents manual path

- GIVEN suspended mode and a pending appointment
- WHEN an administrator views available confirmation actions
- THEN only manual confirmation MUST be actionable
- AND no fingerprint request or agent poll SHALL be emitted

#### Scenario: Prospect conversion bypasses capture

- GIVEN suspended mode and an otherwise valid prospect conversion
- WHEN the biometric stage is reached or submitted
- THEN the workflow MUST advance without biometric material
- AND no fingerprint record or biometric attempt SHALL be created

### Requirement: Historical Data Preservation

Suspension MUST NOT delete, migrate, rewrite, or expose stored fingerprint templates, biometric attempts, appointment history, schemas, routes, enum values, or preserved fingerprint code. Historical descriptive biometric status MUST remain readable to authorized users, while active payload affordances MUST report biometric confirmation as unavailable and MUST NOT expose template material.

#### Scenario: Existing history remains readable

- GIVEN historical biometric records and an authorized reader
- WHEN suspended mode is active and historical status is requested
- THEN descriptive status and audit history MUST remain available
- AND stored records MUST remain unchanged

### Requirement: Reversible Reactivation

When suspended mode is disabled, preserved biometric behavior MUST become eligible to operate under its existing authorization, validation, consent, and state rules without data restoration or schema migration. A stale frontend that still suppresses biometric controls MUST NOT prevent manual workflows; the backend state remains authoritative.

#### Scenario: Suspension is disabled

- GIVEN valid historical data and suspended mode is changed from enabled to disabled
- WHEN an authorized client uses an existing biometric route
- THEN the request MUST be evaluated under the active biometric contract
- AND no restoration or migration step SHALL be required
