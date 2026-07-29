# Tasks: add-digital-persona-4500-integration

This breakdown follows `specs/biometric/spec.md` and `design.md`. Delivery is a three-PR chain: backend MVP, agent/tunnel infrastructure, then frontend and manual QA.

## PR #1 — Backend minimal viable (this implementation batch)

Estimated changed lines: 700–1,000; 400-line budget risk: High; chained PRs recommended: Yes; chain strategy: feature-branch-chain; delivery strategy: chained PRs.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Phase 1.0 — Bootstrapping
- [x] 1.1 Create `backend/biometric/{__init__.py,apps.py,models.py,migrations/__init__.py}`.
- [x] 1.2 Add `biometric` to `INSTALLED_APPS` in `backend/config/settings.py`.
- [x] 1.3 Read and validate `BIOMETRIC_FERNET_KEY`; configure `BIOMETRIC_MATCH_THRESHOLD` defaulting to `0.85`; fail startup on invalid key.

### Phase 1.1 — Encryption service
- [x] 1.4 Create `backend/biometric/services/{__init__.py,encryption.py}` with single-key Fernet `encrypt_template(bytes)` and `decrypt_template(bytes)`.
- [x] 1.5 Add Django unittest coverage in `backend/biometric/tests/test_encryption.py` for round-trip, wrong-key `InvalidToken`, and missing-key fail-fast.

### Phase 1.2 — Model migrations
- [x] 1.6 Update `HuellaBiometricaCliente` fields, BinaryField storage, provider enum, one-client uniqueness, and legacy `MOCK_LEGACY` data state.
- [x] 1.7 Add `BiometricAttempt` with required metadata, nullable relations, operations, and `(cita, created_at)` index.
- [x] 1.8 Add `AgentToken` with protected sucursal, hashed token, URL, activity, heartbeat, and creator fields.
- [x] 1.9 Generate `backend/biometric/migrations/0001_initial.py` and required customer migration(s), including legacy backfill.
- [x] 1.10 Test forward/reverse migrations in `backend/biometric/tests/test_migrations.py`.

### Phase 1.3 — Threshold service
- [x] 1.11 Create `backend/biometric/services/threshold.py` with `decide_match(score)` using the configured threshold.
- [x] 1.12 Test above, below, and exact-threshold decisions.

### Phase 1.4 — Mock agent client
- [x] 1.13 Create `agent_client.py` with `BaseAgentClient` and controllable `MockAgentClient`; leave HTTP client for PR #2.
- [x] 1.14 Add `AGENT_CLIENT_CLASS` factory with Mock default.
- [x] 1.15 Test mock payloads and simulated agent errors.

### Phase 1.5 — Endpoints
- [x] 1.16 Implement enroll-init/finalize at `/api/clientes/{id}/huella/`, with consent, UUID capture token TTL, mock capture, encryption, persistence, and ENROLL audit.
- [x] 1.17 Implement verify-init at `/api/citas/{id}/huella/verify-init/`, requiring pending state and client-only lookup; PR #1 selects the first active agent.
- [x] 1.18 Implement verify-confirm at `/api/citas/{id}/huella/verify-confirm/`, server threshold decision, appointment transition, score, failure reason, and VERIFY audit.
- [x] 1.19 Implement `POST /api/agents/` for `ADMIN_PRINCIPAL`, returning the raw token once.
- [x] 1.20 Implement `GET /api/agents/` with role scoping and redacted token fingerprint metadata.
- [x] 1.21 Implement agent-authenticated `POST /api/agents/{id}/heartbeat/` updating `last_seen_at` and returning 204.
- [x] 1.22 Implement `DELETE /api/agents/{id}/` as principal-only soft deactivation.
- [x] 1.23 Add `backend/biometric/tests/test_endpoints.py` for success, 401/403 guards, invalid state, consent, missing fingerprint, low quality, and error responses.

### Phase 1.6 — Permissions
- [x] 1.24 Create `permissions.py` with `IsAdminPrincipal`, `IsAdminPrincipalOrSucursal`, `IsAdminAndOwnsSucursal`, and `IsAgentToken`.
- [x] 1.25 Test permissions for principal, branch admin, receptionist verification, worker denial, and unauthenticated requests.

### Phase 1.7 — Log scrubber
- [x] 1.26 Create `backend/biometric/log_filters.py` to scrub base64 blobs over 256 characters from biometric records.
- [x] 1.27 Register the filter in `backend/config/settings.py` for biometric logging.
- [x] 1.28 Test that template material is absent from messages and tracebacks.

### Phase 1.8 — Fallback, audit, and verification
- [x] 1.29 Return `{has_fingerprint:false, manual_only:true}` when verify-init finds no template; test manual fallback availability.
- [x] 1.30 Add cross-sucursal test proving lookup uses `cliente_id` only.
- [x] 1.31 Add tests proving every enrollment/verification operation creates metadata-only `BiometricAttempt` rows, including unlimited failures and manual confirmation.
- [x] 1.32 Run `python manage.py check` and `python manage.py test biometric` with all tests passing.
- [x] 1.33 Smoke-test enrollment and verification with `DJANGO_USE_LOCAL_DB=True` and a generated Fernet key.
- [x] 1.34 Update the PR description with files, line count, test results, and demo commands.

## PR #2 — fingerprint-agent + Cloudflare Tunnel

Deferred: create the Python 3.12 agent, DigitalPersona/fprintd capture and match endpoints, heartbeat client, tests, packaging, systemd files, and Cloudflare Tunnel configuration.

- [x] 2.1 Create and validate the Linux agent, tunnel configuration, service files, and smoke tests.

## PR #3 — Frontend integration

Deferred: replace `mockFingerprint.ts` with `biometricClient.ts`, wire enrollment and verification screens, agent online/offline states, manual fallback, Playwright coverage, build/lint/type checks, and manual QA.

- [ ] 3.1 Replace the mock client, wire React flows, add E2E coverage, and complete build/lint/type/manual QA checks.

## Spec → Task

- Phase 1.0–1.1 covers Requirement 1 (encrypted storage and fail-fast key).
- Phase 1.2 covers Requirements 2–4 (model updates, audit log, AgentToken lifecycle).
- Phase 1.3 covers Requirement 9 (server threshold policy).
- Phase 1.4–1.5 covers Requirements 5–7 and 11 (enrollment, verification, registration).
- Phase 1.6 covers Requirement 13 (permissions); Phase 1.7 covers Requirement 15 (privacy).
- Phase 1.8 covers Requirements 8, 10, 12, and 14 (fallback, cross-sucursal, retry policy, audit completeness).
- PR #2 covers agent lifecycle and heartbeat; PR #3 covers Requirement 16 (frontend mock replacement) and UI offline/manual behavior.

## Out-of-scope / Future

- Windows/macOS agent support
- Biometric login
- Multi-finger
- `/agents/{id}/rotate/` (no key rotation in this design)

END OF tasks.md
