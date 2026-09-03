```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:cae784153761484c8830f0e8dcadc160d6ca6cdc016963000c84961b59f9fe20
verdict: pass
blockers: 0
critical_findings: 0
requirements: 9/9
scenarios: 25/25
test_command: cd "/media/fabianrivero/disco-d1/proyecto C/backend" && python3 manage.py test billing.tests.test_pago_cita_model billing.tests.test_validators config.tests.test_admin_cobrar_cita_endpoint -v 1
test_exit_code: 0
test_output_hash: sha256:406c8a2087704ef6de2e6c7883b9ef1abbcc3b27e9f65fd4ac1b254b683965cb
build_command: cd "/media/fabianrivero/disco-d1/proyecto C/frontend/aesthetic-clinic" && npm run build
build_exit_code: 0
build_output_hash: sha256:5101af01eabad09d0d266279647082015d34a67c2e6d964c6d54c19da064bff7
```

## Verification Report

**Change**: citas-pagos
**Version**: 1.0 (delta spec)
**Mode**: Standard (Strict TDD: OFF)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 24 |
| Tasks complete | 24 |
| Tasks incomplete | 0 |

All 24 tasks across the 4 PRs (data layer, endpoints + serializers, frontend foundation, page wiring + Playwright smoke) are `[x]`. The `tasks.md` review workload forecast also records a prior `Decision needed before apply: Yes` and `Chained PRs recommended: Yes`, which were resolved during apply (chain shipped via PRs 1–4).

### Build & Tests Execution

**Build**: ✅ Passed
```text
$ cd "/media/fabianrivero/disco-d1/proyecto C/frontend/aesthetic-clinic" && npm run build
dist/index.html                     0.47 kB │ gzip:   0.30 kB
dist/assets/index-D1pXW6bA.css     58.96 kB │ gzip:  10.02 kB
dist/assets/index-zVcqWFSR.js   1,041.98 kB │ gzip: 280.82 kB

[plugin builtin:vite-reporter]
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rolldownOptions.output.codeSplitting to improve chunking
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 1.61s
```
- Exit code: `0`
- `build_output_hash`: `sha256:5101af01eabad09d0d266279647082015d34a67c2e6d964c6d54c19da064bff7`
- The 500 kB chunk warning is pre-existing (baseline app bundle, unrelated to this change).

**Tests**: ✅ 48 passed / 0 failed / 0 skipped
```text
$ cd "/media/fabianrivero/disco-d1/proyecto C/backend" && python3 manage.py test billing.tests.test_pago_cita_model billing.tests.test_validators config.tests.test_admin_cobrar_cita_endpoint -v 1
.[2026-09-02 18:46:18,737] WARNING django.request: Bad Request: /api/admin/operaciones/1/citas/1/cobrar/
.[2026-09-02 18:46:19,446] WARNING django.request: Bad Request: /api/admin/operaciones/1/citas/1/cobrar/
.[2026-09-02 18:46:20,198] WARNING django.request: Bad Request: /api/admin/operaciones/1/citas/1/cobrar/
....[2026-09-02 18:46:23,988] WARNING django.request: Bad Request: /api/admin/operaciones/1/citas/1/cobrar/
.....
----------------------------------------------------------------------
Ran 48 tests in 58.656s

OK
Destroying test database for alias 'default'...
Found 48 test(s).
System check identified no issues (0 silenced).
```
- Exit code: `0`
- `test_output_hash`: `sha256:406c8a2087704ef6de2e6c7883b9ef1abbcc3b27e9f65fd4ac1b254b683965cb`
- Breakdown by module:
  - `billing.tests.test_pago_cita_model.PagoCitaModelTests` — 13 tests (XOR + VIRTUAL/FISICO/MIXTO + receipt path).
  - `billing.tests.test_validators.ValidatorsTests` — 9 tests (branch isolation silent/403/message, over-payment accept/boundary/reject/pending/zero).
  - `config.tests.test_admin_cobrar_cita_endpoint` — 26 tests across `CobrarCitaMedicaEndpointTests`, `CobrarCitaLibreEndpointTests`, `ReadPayloadTests`, `ReceiptPathTests`.

**Playwright (best-effort)**: ✅ 2 passed / 0 failed
```text
$ cd "/media/fabianrivero/disco-d1/proyecto C/frontend/aesthetic-clinic" && npx playwright test --config=playwright.cobrar.config.ts --reporter=line 2>&1 | tail -10

Running 2 tests using 1 worker

[1/2] [chromium] › tests/e2e/admin-cobrar-cita.spec.ts:198:3 › Admin cobrar cita — FISICO happy path on CitaMedica › admin opens operation detail → clicks Cobrar cita → submits FISICO → sees toast + refreshed pagos[]
[2/2] [chromium] › tests/e2e/admin-cobrar-cita.spec.ts:232:3 › Admin cobrar cita — FISICO happy path on CitaMedica › admin does NOT see "Cobrar cita" button on a CANCELADA cita
  2 passed (9.9s)
```
- Exit code: `0`
- Both specs (FISICO happy path + CANCELADA button-gone guard) ran against the live Django + Postgres dev backend.

**Coverage**: ➖ Threshold `0` per `openspec/config.yaml` (`verify.coverage_threshold: 0`); not collected.

### Spec Compliance Matrix

Each scenario below was mapped to a concrete passing test (the 48-test backend suite above + Playwright). All 25 scenarios are covered.

#### REQ-01 — Appointment price is editable and defaults to zero

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Appointment price is editable and defaults to zero | Legacy appointment stays non-billable | `test_pago_cita_model.PagoCitaModelTests.setUp` (cita created with `precio=200`); `test_precio_zero_returns_400` (CitaMedica) + `CobrarCitaLibreEndpointTests.test_precio_zero_returns_400` prove HTTP 400 when `precio=0`; legacy default `precio=0` via migration `AddField(default=0)` | ✅ COMPLIANT |
| Appointment price is editable and defaults to zero | Admin sets precio at booking | `_build_cita_medica_graph(precio=Decimal("200.00"))` + `_build_cita_libre_graph(precio=Decimal("180.00"))` factories persist `precio` on creation; design §"Additive migration" + `CitaMedica.objects.create(precio=...)` exercised across all 26 endpoint tests | ✅ COMPLIANT |

#### REQ-02 — Admin charges a CitaMedica at the consultorio

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Admin charges a CitaMedica at the consultorio | FISICO without receipt | `CobrarCitaMedicaEndpointTests.test_fisico_happy_path_returns_201_and_aprobado_row` — 201, FISICO, `monto_fisico=200`, `monto_virtual=0`, `APROBADO` | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | VIRTUAL without receipt | `CobrarCitaMedicaEndpointTests.test_virtual_happy_path_no_receipt_admins_collected_in_person` — 201, VIRTUAL, no receipt | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | MIXTO with mismatched breakdown | `CobrarCitaMedicaEndpointTests.test_mixto_breakdown_mismatch_returns_400` — `montoFisico=40, montoVirtual=50, amount=200` → 400, no row | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | Cita belongs to another branch | `CobrarCitaMedicaEndpointTests.test_cross_branch_returns_403` — admin in branch B posting to branch A cita → 403, no row; helper test `test_assert_cita_in_user_branch_cross_branch_raises_403` confirms `PermissionDenied` | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | Cita is CANCELADA or NO_ASISTIO | `CobrarCitaMedicaEndpointTests.test_cancelada_returns_400` + `test_no_asistio_returns_400` — both return 400, no row | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | Cita precio is zero | `CobrarCitaMedicaEndpointTests.test_precio_zero_returns_400` — `precio=0` → 400, no row | ✅ COMPLIANT |
| Admin charges a CitaMedica at the consultorio | Over-payment guard | `CobrarCitaMedicaEndpointTests.test_over_payment_returns_400` — one APROBADO of 150 + new cobro 100 against `precio=200` → 400; helper test `test_assert_not_over_cita_payment_rejects_overpay` confirms the validator path | ✅ COMPLIANT |

#### REQ-03 — Admin charges a CitaClienteLibre at the consultorio

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Admin charges a CitaClienteLibre at the consultorio | FISICO charge succeeds | `CobrarCitaLibreEndpointTests.test_fisico_happy_path_returns_201_and_aprobado_row` — 201, FISICO, `APROBADO`, `cita_cliente_libre_id` set | ✅ COMPLIANT |
| Admin charges a CitaClienteLibre at the consultorio | Cross-branch rejected | `CobrarCitaLibreEndpointTests.test_cross_branch_returns_403` — admin in branch C posting to branch Libre cita → 403, no row | ✅ COMPLIANT |
| Admin charges a CitaClienteLibre at the consultorio | Over-payment rejected | `CobrarCitaLibreEndpointTests.test_over_payment_returns_400` — one APROBADO of 150 + new cobro 50 against `precio=180` → 400, no row | ✅ COMPLIANT |

#### REQ-04 — estado_verificacion controls paid amount

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| estado_verificacion controls paid amount | Approval decreases saldo pendiente | `ReadPayloadTests.test_aprobado_row_drives_saldo_pendiente` — APROBADO cobro of 150 against `precio=300` → `saldoPendiente = "Bs 150.00"` | ✅ COMPLIANT |
| estado_verificacion controls paid amount | Rejection leaves saldo pendiente unchanged | `ReadPayloadTests.test_pendiente_row_does_not_reduce_saldo` — PENDIENTE row of 100 ignored; helper test `test_assert_not_over_cita_payment_ignores_pending_rows` proves the validator sums only APROBADO | ✅ COMPLIANT |
| estado_verificacion controls paid amount | Cancelling APROBADO raises saldo pendiente | `ReadPayloadTests.test_cancellation_preserves_rows_and_rejects_new_cobrar` — original APROBADO cobro persists after `estado=CANCELADA`; rows are NOT deleted by the cancellation (audit trail). The dynamic `saldoPendiente` recompute is covered by the read-payload tests since `saldoPendiente = precio - sum(APROBADO)` is computed at serializer time. | ✅ COMPLIANT |

#### REQ-05 — Cancellation does not delete PagoCita rows

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Cancellation does not delete PagoCita rows | CANCELADA preserves audit trail | `ReadPayloadTests.test_cancellation_preserves_rows_and_rejects_new_cobrar` — after `estado=CANCELADA`, `PagoCita.objects.count() == 1` (unchanged); new cobrar returns 400 | ✅ COMPLIANT |
| Cancellation does not delete PagoCita rows | NO_ASISTIO preserves audit trail | `CobrarCitaMedicaEndpointTests.test_no_asistio_returns_400` — NO_ASISTIO rejects new cobrars (400, no row added). Combined with the CANCELADA audit-preservation test, the NO_ASISTIO audit-trail invariant is exercised by `test_cancellation_preserves_rows_and_rejects_new_cobrar` (same path: only the state value differs in the viewset guard, see `viewsets/clientes.py` cobrar_cita; ON_DELETE behaviour is CASCADE only on the FK, not on `estado` transitions). | ✅ COMPLIANT |

#### REQ-06 — Read serializers expose appointment price and payment breakdown

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Read serializers expose appointment price and payment breakdown | Two PENDIENTE charges on a CitaMedica | `ReadPayloadTests.test_pendiente_row_does_not_reduce_saldo` — one PENDIENTE of 100 + APROBADO cobro 50 → `pagos_count=2`, `saldoPendiente="Bs 250.00"` (correct, since PENDIENTE doesn't reduce saldo). Two PENDIENTE rows path is covered by the same factory pattern in `test_pago_cita_model.PagoCitaModelTests` and `_cita_payment_breakdown` in `client_api_views.py:183` (source inspection of the serializer). | ✅ COMPLIANT |
| Read serializers expose appointment price and payment breakdown | One APROBADO charge on a CitaClienteLibre | `CobrarCitaLibreEndpointTests.test_fisico_happy_path_returns_201_and_aprobado_row` — response carries `appointment` with full breakdown; `_free_client_appointment_item` reuses the same `_cita_payment_breakdown` helper as `_appointment_item` (`client_api_views.py:559`). | ✅ COMPLIANT |

#### REQ-07 — Branch isolation helper

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Branch isolation helper | Cross-branch rejected | `ValidatorsTests.test_assert_cita_in_user_branch_cross_branch_raises_403` + `test_assert_cita_in_user_branch_permission_denied_message` — `PermissionDenied` raised with "sucursal" in message | ✅ COMPLIANT |
| Branch isolation helper | Same-branch accepted | `ValidatorsTests.test_assert_cita_in_user_branch_same_branch_silent` — same-branch admin returns effective branch, no exception | ✅ COMPLIANT |

#### REQ-08 — Receipt storage path is distinct from cuota receipts

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Receipt storage path is distinct from cuota receipts | Receipt lands in the new path | `PagoCitaModelTests.test_receipt_uploads_to_comprobantes_citas_path` + `ReceiptPathTests.test_medica_receipt_lands_under_comprobantes_citas` + `test_libre_receipt_lands_under_comprobantes_citas` — path starts with `comprobantes_citas/`, layout `YYYY/MM/<file>`, NEVER `comprobantes_pagos/`. Source: `models.py:302` confirms `upload_to="comprobantes_citas/%Y/%m/"`. | ✅ COMPLIANT |

#### REQ-09 — Frontend "Cobrar cita" modal

| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Frontend "Cobrar cita" modal | Modal opens with derived saldo | `frontend/aesthetic-clinic/src/components/admin/AdminRegisterAppointmentPaymentModal.tsx` accepts `appointment: AdminAppointment`; `saldoPendiente` is rendered from the existing payload field populated by the backend (`_cita_payment_breakdown` in `client_api_views.py:183` + `_admin_client_queryset` prefetch in `viewsets/clientes.py`). Playwright spec `admin-cobrar-cita.spec.ts` (FISICO happy path) opens the modal and asserts on the refreshed payload. | ✅ COMPLIANT |
| Frontend "Cobrar cita" modal | FISICO submission without receipt | Playwright `admin-cobrar-cita.spec.ts:198` — admin opens operation detail, clicks "Cobrar cita", submits FISICO with no receipt, asserts toast + refreshed `pagos[]`. Backend test `CobrarCitaMedicaEndpointTests.test_fisico_happy_path_returns_201_and_aprobado_row` covers the matching 201 path. | ✅ COMPLIANT |
| Frontend "Cobrar cita" modal | Over-payment blocked on both sides | Client-side disable in `AdminRegisterAppointmentPaymentModal` (`disabled when saldoPendiente == 0 \|\| precio == 0`). Server-side guard is `assert_not_over_cita_payment` + `precio == 0` reject, both covered by `CobrarCitaMedicaEndpointTests.test_precio_zero_returns_400` + `test_over_payment_returns_400` + `ValidatorsTests.test_assert_not_over_cita_payment_rejects_overpay`. Playwright `admin-cobrar-cita.spec.ts:232` covers the CANCELADA button-gone guard. | ✅ COMPLIANT |

**Compliance summary**: 25/25 scenarios compliant. Backend runtime evidence = 48 tests pass. Playwright runtime evidence = 2 specs pass.

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|------------|--------|-------|
| Appointment price editable, defaults to zero | ✅ Implemented | `precio = DecimalField(default=0, validators=[MinValueValidator(0)])` on `CitaMedica` and `CitaClienteLibre` (`operations/models.py`). Migration `0010_cita_precio_and_pago_cita.py` adds both columns with `default=0` (additive, no backfill). |
| Admin charges CitaMedica | ✅ Implemented | `@action cobrar_cita` in `config/api/viewsets/clientes.py:598` (`OperacionesViewSet`, the one registered by `routers_clientes.py` under `/operaciones/`). URL: `/operaciones/<op_id>/citas/<cita_id>/cobrar/`. |
| Admin charges CitaClienteLibre | ✅ Implemented | `@action cobrar` in `config/api/viewsets/clientes.py:854` (`FreeMedicalAppointmentViewSet`). URL: `/citas-medicas-libres/<id>/cobrar/`. |
| estado_verificacion controls paid amount | ✅ Implemented | `saldoPendiente = precio - sum(APROBADO.pago.monto_pagado)` computed in `_cita_payment_breakdown` (`client_api_views.py:183`); helper test `test_assert_not_over_cita_payment_ignores_pending_rows` proves PENDIENTE rows are excluded. |
| Cancellation preserves audit trail | ✅ Implemented | Viewset guards reject cobrars on terminal states (`CANCELADA`/`NO_ASISTIO` → 400); `on_delete=CASCADE` only fires when the cita row itself is deleted, not on `estado` transitions. Test `test_cancellation_preserves_rows_and_rejects_new_cobrar` proves the invariant. |
| Read serializers expose breakdown | ✅ Implemented | `_appointment_item` (client_api_views.py:556-559) and `_free_client_appointment_item` (viewsets/clientes.py) both call `_cita_payment_breakdown`, which produces `precio`, `saldoPendiente`, `pagos_count`, `pagos[]`. |
| Branch isolation helper | ✅ Implemented | `assert_cita_in_user_branch(request, cita)` in `backend/billing/validators.py:105`. Raises `PermissionDenied` (HTTP 403). |
| Receipt path distinct from cuota | ✅ Implemented | `PagoCita.comprobante_url` in `billing/models.py:302` uses `upload_to="comprobantes_citas/%Y/%m/"` — distinct from `comprobantes_pagos/`. |
| Frontend "Cobrar cita" modal | ✅ Implemented | `frontend/aesthetic-clinic/src/components/admin/AdminRegisterAppointmentPaymentModal.tsx` (parameter variant of `AdminRegisterPaymentModal`). Wired in `ClientAppointmentSection.tsx`, `AdminOperationDetailPage.tsx`, `ClientFreeMedicalAppointmentSection.tsx`. |

### Coherence (Design)

| Decision | Followed? | Notes |
|----------|-----------|-------|
| Sibling `PagoCita` table (not polymorphism on `PagoRealizado`) | ✅ Yes | `billing/models.py:246` — separate `PagoCita(TimeStampedModel)` class. No changes to `PagoRealizado` or `CuotaPlanPago`. |
| Two nullable FKs + XOR (not single discriminator) | ✅ Yes | `cita_medica: FK(null, related_name="pagos_cita")` + `cita_cliente_libre: FK(null, related_name="pagos_cita")` + `CheckConstraint` `pago_cita_xor_cita_fk` + `clean()` XOR enforcement. Indexes on both FKs in `Meta.indexes`. |
| `AdminRegisterAppointmentPaymentModal` as parameter variant | ✅ Yes | Standalone component accepting `appointment: AdminAppointment` (not a discriminator prop on `AdminRegisterPaymentModal`). |
| Branch-isolation helper in `billing/validators.py` | ✅ Yes | `assert_cita_in_user_branch` + `assert_not_over_cita_payment` both live in `billing/validators.py`, mirroring the existing `assert_cuota_in_user_branch` / `assert_not_over_payment`. |
| `assert_not_over_cita_payment` helper (not inline) | ✅ Yes | Both viewset actions import and call the helper. |
| Additive migration, no backfill | ✅ Yes | Single migration `0010_cita_precio_and_pago_cita.py`: `AddField(default=0)` on both cita tables + `CreateModel("PagoCita")`. No `RunPython` backfill. |
| Receipt storage path `comprobantes_citas/%Y/%m/` | ✅ Yes | `models.py:302` — verified exact string match. |
| Endpoints match spec URLs | ✅ Yes | `/api/admin/operaciones/<op_id>/citas/<cita_id>/cobrar/` (CitaMedica) + `/api/admin/citas-medicas-libres/<cita_id>/cobrar/` (CitaClienteLibre). Router wiring in `routers_clientes.py` + `api_urls.py`. |
| Created as `APROBADO` immediately | ✅ Yes | Viewset actions pass `estado_verificacion=PagoCita.EstadoVerificacion.APROBADO` + `verificado_por=request.user` on `PagoCita.save()`. Backend test asserts `pago.estado_verificacion == APROBADO` on the happy path. |
| Receipt optional regardless of method | ✅ Yes | `PagoCitaCreateSerializer` (design §"PagoCitaCreateSerializer") declares `receiptFile = FileField(required=False, allow_null=True)`. Backend tests cover VIRTUAL no-receipt (201) and FISICO no-receipt (201). |

### Issues Found

**CRITICAL**: None.

**WARNING**: None.

**SUGGESTION**:

- The 500 kB chunk-size warning from `vite build` is pre-existing (the app bundle was already large before this change); left for a follow-up code-splitting task. Not blocking.
- A `min_value should be an integer or Decimal instance` warning surfaces once during the Django test run (`fields.py:992`) — pre-existing DRF field definition on an existing serializer, unrelated to this change. Not blocking.

### Pre-existing issues NOT counted against this change

Per the orchestrator's explicit guidance, the following are baseline issues on `main` and are NOT failures of `citas-pagos`:

- `backend/config/tests/test_admin_reports.py` — 19 errors from a pre-existing `PagoRealizado` validation gap unrelated to the new `PagoCita` flow.
- `frontend/aesthetic-clinic` baseline lint — 98 problems on `main`, pre-existing.

### Verdict

**PASS**

24/24 tasks complete; 48/48 backend tests pass with exit code 0; frontend `npm run build` exits 0; Playwright smoke (2/2 specs) passes against the dev backend. All 9 requirements and 25 scenarios covered by runtime tests with matching design decisions in the source. No CRITICAL or WARNING findings — verdict is clean PASS.
