# Client Payment Cancelled Specification

## Purpose

The system SHALL provide a `CLIENT_PAYMENT_CANCELLED` notification type to inform clients when their payment is set to `CANCELADO` state by an admin.

## Requirements

### Requirement: CLIENT_PAYMENT_CANCELLED Notification Type Exists

The system SHALL include `CLIENT_PAYMENT_CANCELLED` in the `Notification.Type` enum in `notifications/models.py`.

#### Scenario: Notification type is defined in enum

- GIVEN the `Notification` model exists with a `Type` choices enum
- WHEN the enum is evaluated
- THEN `CLIENT_PAYMENT_CANCELLED` SHALL be present as a valid notification type
- AND it SHALL have an associated human-readable label

### Requirement: CLIENT_PAYMENT_CANCELLED Triggered When Admin Sets Payment to CANCELADO

The system SHALL create a `CLIENT_PAYMENT_CANCELLED` notification when an admin sets a payment's `estado_verificacion` to `CANCELADO`.

#### Scenario: Notification created on admin cancellation

- GIVEN a `PagoRealizado` record exists with an associated client
- WHEN an admin changes the payment state to `CANCELADO` via the admin interface or API
- THEN the system SHALL automatically create a `CLIENT_PAYMENT_CANCELLED` notification
- AND the notification SHALL be associated with the payment and the client

### Requirement: CLIENT_PAYMENT_CANCELLED Notification Content

The `CLIENT_PAYMENT_CANCELLED` notification SHALL include a descriptive title and message that clearly indicates the payment was cancelled.

#### Scenario: Notification has appropriate title

- GIVEN a `CLIENT_PAYMENT_CANCELLED` notification is created
- THEN the notification SHALL have a `title` field indicating "Payment Cancelled" or equivalent
- AND the title SHALL be human-readable and localized

#### Scenario: Notification has appropriate message

- GIVEN a `CLIENT_PAYMENT_CANCELLED` notification is created
- THEN the notification SHALL have a `message` field
- AND the message SHALL reference the payment identifier (e.g., payment ID or date)
- AND the message SHALL indicate the payment was cancelled and may need attention

### Requirement: CLIENT_PAYMENT_CANCELLED Received by Client (Paciente)

The `CLIENT_PAYMENT_CANCELLED` notification SHALL be associated with the client (`paciente`) who submitted the payment.

#### Scenario: Notification targets the correct client

- GIVEN a `PagoRealizado` record exists linked to a specific client
- WHEN the payment is cancelled by an admin
- THEN the `CLIENT_PAYMENT_CANCELLED` notification SHALL be created for the same client
- AND the notification SHALL appear in the client's notification list
