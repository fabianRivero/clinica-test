# Delta for auth-me

## ADDED Requirements

### Requirement: PATCH Method Support

The system MUST accept PATCH requests to `/api/auth/me` for partial profile updates. The endpoint MUST reject requests with unknown fields.

#### Scenario: Partial update email only

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"email": "new@email.com"}`
- THEN only email is updated, other fields unchanged, returns 200

#### Scenario: Update multiple fields

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{"username": "newname", "telefono": "1234567890"}`
- THEN both fields are updated atomically, returns 200

#### Scenario: Empty PATCH returns current profile

- GIVEN an authenticated user
- WHEN they send `PATCH /api/auth/me` with `{}`
- THEN returns 200 with current profile, no changes made