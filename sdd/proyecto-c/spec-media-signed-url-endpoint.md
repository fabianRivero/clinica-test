# media-signed-url-endpoint — Specification (mirror)

> **Authoritative mirror** at `C:\proyectos\proyecto C\sdd\proyecto-c\spec-media-signed-url-endpoint.md`.
> Source-of-truth openspec path: `C:\proyectos\proyecto C\openspec\changes\cloud-storage-migration\specs\media-signed-url-endpoint\spec.md`.
> Generated 2026-10-01 for change `cloud-storage-migration`.

## Purpose

Define an authenticated HTTP endpoint that mints short-lived S3 presigned URLs for protected user-uploaded files (clinical PDFs, operation photos, payment receipts, ticket attachments), with per-resource authorization rules, a fail-closed audit log, and a frontend caching contract. Greenfield: `backend/config/urls.py:30` serves `MEDIA_URL` only when `DEBUG=True`, leaving production clinical PDFs effectively unreachable from authenticated contexts and reachable without auth in dev.

---

## ADDED Requirements

### Requirement: Signed URL Endpoint

`GET /api/media/signed-url/?path=<relative_path>` SHALL return a SigV4 presigned S3 GET URL. The endpoint SHALL require the existing JWT/cookie auth. `path` SHALL be sanitized: reject `..`, leading `/`, and `\`; reject paths outside the allowlist `{fichas_clinicas/, tickets_adjuntos/, citas/, fotos_operacion/, comprobantes_pagos/, comprobantes_citas/}`. SHALL call `boto3.client.generate_presigned_url('get_object', Params={'Bucket':..., 'Key': path}, ExpiresIn=MEDIA_SIGNED_URL_TTL_SECONDS)`. Default TTL **900 s** (15 min, proposal Gate 5); cap at **604800 s (7 days)** — SigV4 max per research §"Presigned URL support". Response JSON: `{ url, expires_at, ttl_seconds }`. HTTP 401 unauth, 403 forbidden, 400 malformed, 503 if audit write fails (fail-closed). URL SHALL be HTTPS-only; endpoint SHALL NOT expose bucket name, account id, or credentials.

#### Scenario: Authenticated user mints URL for an authorized resource

- GIVEN cliente with `user.cliente.id == ficha.cliente.id`
- WHEN cliente calls `GET /api/media/signed-url/?path=fichas_clinicas/2026/10/abc.pdf`
- THEN response SHALL be `200` with `{ "url": "https://...", "expires_at": "<ISO8601>", "ttl_seconds": 900 }`
- AND the URL SHALL be valid for `ttl_seconds` (max 604800)

#### Scenario: Unauthenticated request is rejected

- GIVEN no auth
- WHEN client calls the endpoint
- THEN response SHALL be `401 Unauthorized`
- AND no presigned URL SHALL be issued
- AND no audit row SHALL be written (audit only fires on success)

#### Scenario: Malformed path is rejected

- GIVEN an authenticated user
- WHEN the user calls with `path=../../etc/passwd` or `path=/etc/passwd`
- THEN response SHALL be `400 Bad Request`

#### Scenario: Path outside allowed prefixes is rejected

- GIVEN an authenticated user
- WHEN the user calls with `path=random/path.pdf`
- THEN response SHALL be `400 Bad Request`

#### Scenario: TTL caps at 7 days

- GIVEN `MEDIA_SIGNED_URL_TTL_SECONDS=99999999`
- WHEN a signed URL is generated
- THEN `ttl_seconds` SHALL be clamped to `604800` (7 days — SigV4 max)

---

### Requirement: Per-Resource Authorization

The endpoint SHALL authorize against the DB row owning the path. Rules:

| Path prefix | Authorized |
|-------------|------------|
| `fichas_clinicas/` | `admin_principal` OR `admin_sucursal` of same sucursal OR `cliente` self (`user.cliente.id == ficha.cliente.id`) |
| `citas/.../antes/`, `citas/.../despues/` | `admin_principal` OR `admin_sucursal` of operation's sucursal OR the operation's assigned `especialista` |
| `fotos_operacion/` | `admin_principal` OR `admin_sucursal` of operation's sucursal OR the operation's assigned `especialista` |
| `comprobantes_pagos/` | `admin_principal` OR `admin_sucursal` of cliente's sucursal OR the cliente OR the specialist who registered the payment |
| `comprobantes_citas/` | `admin_principal` OR `admin_sucursal` of cliente's sucursal OR the cliente OR the specialist who registered the payment |
| `tickets_adjuntos/` | `admin_principal` OR `admin_sucursal` OR the ticket creator OR the ticket assignee |

Unmatched rule → deny (HTTP 403). If path maps to no DB row, deny unless requester is `admin_principal`. Audit row SHALL record which rule matched.

#### Scenario: Cliente accesses their own clinical PDF

- GIVEN `FichaClinica` id 42 owned by cliente 7; user with `user.cliente.id == 7`
- WHEN user requests URL for the ficha's PDF
- THEN response SHALL be `200`; audit row records `rule: cliente_self`

#### Scenario: Cliente cannot access another cliente's clinical PDF

- GIVEN `FichaClinica` id 42 owned by cliente 7; user with `user.cliente.id == 8`
- WHEN user requests URL
- THEN response SHALL be `403 Forbidden`

#### Scenario: Especialista accesses assigned operation photos

- GIVEN `Operacion` id 100 assigned to especialista 5; user with `user.especialista.id == 5`
- WHEN user requests URL for an `OperacionFoto.imagen`
- THEN response SHALL be `200`; audit row records `rule: especialista_assigned`

#### Scenario: Non-assigned especialista is denied

- GIVEN `Operacion` id 100 assigned to especialista 5; user with `user.especialista.id == 9`
- WHEN user requests URL
- THEN response SHALL be `403 Forbidden`

#### Scenario: Admin principal has wildcard access

- GIVEN any file in any allowed prefix
- WHEN `admin_principal` requests URL
- THEN response SHALL be `200` regardless of which row owns the path

#### Scenario: Stale key with no owning row

- GIVEN path `fichas_clinicas/2026/01/orphan.pdf` with no `FichaClinica` pointing at it
- AND a non-admin user
- WHEN user requests URL
- THEN response SHALL be `403 Forbidden`

---

### Requirement: Audit Log (Fail-Closed)

Every successful signed URL generation SHALL write a record (table or structured log) with: `user_id`, `resource_path`, `resource_type` (model + field, e.g. `clinical.FichaClinica.documento_escaneado_pdf`), `authorization_rule` (`cliente_self` | `admin_principal` | `especialista_assigned` | `admin_sucursal` | `ticket_creator` | `ticket_assignee` | …), `expires_at`, `timestamp`, `client_ip` (respect `X-Forwarded-For`), `user_agent`. Retention **90 days** (proposal Gate 6). Audit write SHALL be **fail-closed**: if writing fails (DB error, log ship down, disk full), URL generation SHALL NOT proceed and endpoint SHALL return HTTP 503 — an unauditable signed URL cannot be defended in a compliance review. Defense-in-depth S3 server access logs SHALL be enabled on the bucket itself (proposal Gate 6).

#### Scenario: Successful mint writes audit row

- GIVEN an authorized request
- WHEN URL is generated
- THEN a row with all eight fields SHALL be persisted
- AND queryable by `user_id`, `resource_path`, or `timestamp`

#### Scenario: Audit write failure causes 503

- GIVEN audit log DB unreachable
- WHEN an authorized request arrives
- THEN endpoint SHALL NOT issue a URL
- AND response SHALL be `503 Service Unavailable`
- AND the failure SHALL be logged at ERROR level

#### Scenario: 401 and 403 do not write audit rows

- GIVEN 401 or 403 responses
- WHEN the request is rejected
- THEN no audit row SHALL be written (audit fires only on successful generation)

---

### Requirement: Frontend Cache Contract

The frontend SHALL cache signed URLs in memory. Cache lifetime: `min(ttl_seconds - 60, 300)` seconds — expire ≥60 s before S3 expiration, capped at 5 min so compromised sessions cannot hold URLs indefinitely. Cache key: absolute bucket-relative `resource_path`. On render: if cached URL expired (or within safety margin), re-request from endpoint. Cache SHALL be per-tab/per-session in memory — no `localStorage` or `sessionStorage` (these leak across sessions/tabs). If endpoint returns 503, frontend SHALL NOT cache the error; SHALL retry on next render after short backoff (e.g., 30 s). All `<img>`/`<a>` previously referencing `/media/...` SHALL be replaced with the signed-URL helper; per proposal §"Affected Areas", a frontend-wide grep audit SHALL be performed before sign-off.

#### Scenario: Cached URL served within safe window

- GIVEN URL with `ttl_seconds=900` cached at `t=0`
- WHEN frontend renders same path at `t=100`
- THEN cached URL SHALL be reused without a network call (cache lifetime `min(840, 300)=300`)

#### Scenario: URL re-requested after cache expiry

- GIVEN cached URL with cache lifetime 300 s
- WHEN frontend renders after expiry
- THEN endpoint SHALL be called and a fresh URL received

#### Scenario: 503 from endpoint is not cached

- GIVEN endpoint returned 503
- WHEN frontend renders after the backoff window
- THEN endpoint SHALL be retried
- AND the 503 SHALL NOT be remembered as resource state

#### Scenario: No signed URL in persistent storage

- GIVEN a signed URL is cached
- WHEN the browser tab is closed
- THEN the cached URL SHALL be discarded with the page lifecycle (no `localStorage`/`sessionStorage` write)

---

## Capabilities (delta)

### New Capabilities

- `signed-url-endpoint`
- `signed-url-authorization`
- `signed-url-audit-log`
- `signed-url-cache`

### Modified Capabilities

None.
