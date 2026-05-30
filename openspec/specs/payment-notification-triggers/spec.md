# Payment Notification Triggers Specification

## Purpose

The system SHALL send automatic notifications to admins and clients when payment state transitions occur. Admins receive alerts on new payment submissions; clients receive alerts on all payment status outcomes.

## Requirements

### Requirement: Admin Notification on New Payment Submission

The system SHALL send an `ADMIN_PAYMENT_PENDING_CONFIRMATION` notification to the admin when a client creates a new `PagoRealizado` in `PENDIENTE` state.

#### Scenario: Admin receives notification when client submits new payment

- GIVEN a client submits a payment receipt via the client API
- WHEN the `PagoRealizado` record is created with `estado_verificacion` set to `PENDIENTE`
- THEN the system SHALL create a notification with type `ADMIN_PAYMENT_PENDING_CONFIRMATION`
- AND the notification SHALL be associated with the `clinica` (branch) of the payment
- AND the admin SHALL receive the notification

#### Scenario: Admin notification fires only on initial payment creation

- GIVEN a `PagoRealizado` record already exists in `PENDIENTE` state
- WHEN the record is saved again (e.g., other fields updated but state remains `PENDIENTE`)
- THEN the system SHALL NOT create another `ADMIN_PAYMENT_PENDING_CONFIRMATION` notification
- AND no duplicate notification SHALL be sent

### Requirement: Client Notification on APROBADO State

The system SHALL send a `CLIENT_PAYMENT_CONFIRMED` notification to the client when their payment transitions to `APROBADO` state.

#### Scenario: Client receives confirmation when payment is approved

- GIVEN a `PagoRealizado` record exists with `estado_verificacion` in `PENDIENTE` or `RECHAZADO`
- WHEN an admin updates the payment state to `APROBADO` via `PagosViewSet.update()`
- THEN the system SHALL create a notification with type `CLIENT_PAYMENT_CONFIRMED`
- AND the client SHALL receive the notification

### Requirement: Client Notification on RECHAZADO State

The system SHALL send a `CLIENT_PAYMENT_REJECTED` notification to the client when their payment transitions to `RECHAZADO` state.

#### Scenario: Client receives rejection when payment is denied

- GIVEN a `PagoRealizado` record exists with `estado_verificacion` in `PENDIENTE` or `APROBADO`
- WHEN an admin updates the payment state to `RECHAZADO` via `PagosViewSet.update()`
- THEN the system SHALL create a notification with type `CLIENT_PAYMENT_REJECTED`
- AND the client SHALL receive the notification

### Requirement: Client Notification on CANCELADO State

The system SHALL send a `CLIENT_PAYMENT_CANCELLED` notification to the client when their payment transitions to `CANCELADO` state.

#### Scenario: Client receives cancellation when payment is cancelled

- GIVEN a `PagoRealizado` record exists with `estado_verificacion` in any state
- WHEN an admin updates the payment state to `CANCELADO` via `PagosViewSet.update()`
- THEN the system SHALL create a notification with type `CLIENT_PAYMENT_CANCELLED`
- AND the client SHALL receive the notification

### Requirement: Client Notification on PENDIENTE Reversion

The system SHALL send a notification to the client when their payment reverts to `PENDIENTE` state.

#### Scenario: Client receives notification when payment reverts to pending

- GIVEN a `PagoRealizado` record exists with `estado_verificacion` in `APROBADO` or `RECHAZADO`
- WHEN an admin updates the payment state back to `PENDIENTE` via `PagosViewSet.update()`
- THEN the system SHALL create a notification to inform the client
- AND the client SHALL receive the notification

### Requirement: Notification Trigger Uses Correct Service Path

The notification creation SHALL be reachable from payment code paths without causing circular imports.

#### Scenario: Notification trigger handles import correctly

- GIVEN `create_notification` is defined in `notifications/services.py`
- WHEN notification triggers are placed in `billing/models.py` or `config/api/viewsets/payments.py`
- THEN the import SHALL succeed without circular dependency errors
- AND if circular import would occur, the trigger SHALL be placed in the viewsets layer instead
