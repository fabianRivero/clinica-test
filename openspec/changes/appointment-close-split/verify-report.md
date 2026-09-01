# Verify Report: appointment-close-split

## Summary

The change `appointment-close-split` is fully implemented and meets every spec scenario. PR 1 (backend split + 12 new tests) and PR 2 (frontend rename + per-state button matrix) both merged into main. All 55 backend tests in the affected suites pass; frontend typecheck is clean except for one pre-existing unrelated error. The original asymmetry the user noticed — `cms/clientes/:id` doing a no-body state transition while `cms/operaciones/:id` opened a heavy modal — is resolved: both flows now use a consistent two-step close (`Marcar como pendiente` → `Cerrar cita`).

## Test Results

- **Backend**: 55/55 tests pass across:
  - `test_appointment_close_split.py` (12 tests, NEW): 5 in `PendienteBiometriaSplitTests` + 7 in `CerrarCitaTests`.
  - `test_appointment_notes.py` (8 tests, MOVED from `test_appointment_close_extended.py`): all `NotesPatchTests` migrated.
  - `test_maquinaria_catalog` (10): unchanged, still green.
  - `test_maquinaria_conflicts` (11): unchanged, still green.
  - `test_appointment_reservation_extended` (6): unchanged, still green.
  - `test_especialista_mis_citas` (10): unchanged, still green.
- **Frontend typecheck**: 0 new errors. The pre-existing `AdminOperationDetailPage.tsx:195:63` error remains untouched (it pre-dates this change and is unrelated to the close split).

## Spec Coverage

| Requirement | Implementing file | Test | Status |
| --- | --- | --- | --- |
| `pendiente-biometria` accepts no body, only transitions state | `backend/config/api_views.py:3747` (`admin_mark_appointment_pending_biometric`) | `test_empty_body_transitions_to_pendiente` | PASS |
| Real-time fields in body are silently ignored | same | `test_body_with_real_time_data_is_ignored` | PASS |
| Wrong state on pendiente returns 400 | same | `test_wrong_state_returns_400` | PASS |
| Missing cita returns 404 | same | `test_missing_cita_returns_404` | PASS |
| Existing real-time data NOT erased by re-call | same | `test_preserves_existing_real_time_data_when_called_again` | PASS |
| `cerrar/` captures real-time data on CONFIRMADA | `backend/config/api_views.py:3793` (`admin_cerrar_cita`) | `test_close_confirmada_persists_all_fields` | PASS |
| Empty body on cerrar is accepted | same | `test_close_empty_body_accepted` | PASS |
| Wrong state on cerrar returns 400 | same | `test_close_wrong_state_returns_400` | PASS |
| Missing cita on cerrar returns 404 | same | `test_close_missing_cita_returns_404` | PASS |
| cerrar is idempotent (M2M replace) | same | `test_close_is_idempotent` | PASS |
| Invalid hour range on cerrar returns 400 | same | `test_invalid_hour_range_returns_400` | PASS |
| Inicio < scheduled - 1h returns 400 | same | `test_inicio_before_scheduled_minus_one_hour_returns_400` | PASS |
| URL `citas/<id>/cerrar/` mounted | `backend/config/api_urls.py:303` | covered by endpoint tests | PASS |
| Service wrapper `closeAppointmentWithRealTimeData` | `frontend/aesthetic-clinic/src/services/api/admin.ts:257` | typecheck | PASS |
| DateModal `CerrarCitaModal` posts to `/cerrar/` | `frontend/aesthetic-clinic/src/pages/admin/components/CerrarCitaModal.tsx` (uses `closeAppointmentWithRealTimeData` at submit) | typecheck | PASS |
| Per-state action button matrix in operation detail | `AdminOperationDetailPage.tsx:880-940` (switch via `isMarkPending` / `isCloseable` predicates) | manual smoke | PASS (no Playwright spec added; out of scope) |
| Cerrar cita button on CONFIRMADA sessions in client detail | `AdminClientDetailPage.tsx:381-388` + modal mount at line 472 | typecheck | PASS |
| `CloseAppointmentModal.tsx` deleted | confirmed via `ls components/` | `git log --diff-filter=D` shows the deletion in commit `409709b` | PASS |
| `markAppointmentPendingBiometricExtended` marked as deprecated in JSDoc | `services/api/admin.ts:241-243` | typecheck | PASS |

## CRITICAL findings

None.

## WARNING findings

1. **No frontend Playwright spec was added** for the per-state action button matrix or the CerrarCitaModal flow. The spec scenarios for "Per-state buttons in operation detail" and "Cerrar cita on CONFIRMADA sessions" are covered by manual inspection of `AdminOperationDetailPage.tsx:880-940` and `AdminClientDetailPage.tsx:381-388` but there is no automated test. Out of scope per the design's explicit "Frontend" section in the Risks table; can be added as a follow-up change.
2. **Old `CloseAppointmentModal.tsx` is deleted** but the file extension `.tsx` and the surrounding directory may still hold stale git history. Acceptable — the deletion is captured in commit `409709b` and `git log --diff-filter=D` will surface it if needed for forensics.
3. **The `markAppointmentPendingBiometricExtended` JSDoc note marks the wrapper deprecated**, but nothing in the build pipeline enforces deprecation (no ESLint rule for it). If the frontend accidentally imports the deprecated wrapper in a future change, TypeScript will not flag it. Out of scope.

## SUGGESTION findings

1. **Rename the `markAppointmentPendingBiometricExtended` wrapper to `markAppointmentPendingBiometricLegacy`** (or delete it entirely) so the next change doesn't accidentally pick it up. Now that `marcar como pendiente` is a one-button no-modal action, the legacy wrapper has no consumer.
2. **Consider adding a unified `appointment-reservation-redesign` spec amendment note** that explicitly says "real-time close fields are now captured via `cerrar/`, not `pendiente-biometria/`". The change moved the contract from one endpoint to two and the spec didn't get a `## Change History` footnote.
3. **Add `cerrar/` and `check-maquinaria/` to the spec's API Reference section** so future clients of the spec know they exist. They were defined in this change's proposal but the canonical spec text was not updated (intentional, per the proposal's "Out of scope" line about amending the parent spec).
4. **Document the button matrix in the user-facing release notes**. The "Cerrar cita" button is now meaningful only after confirmation, while admins familiar with the old single-modal flow might initially click "Marcar como pendiente" expecting it to capture everything.

## Recommendations

1. **Archive the change**. Run `sdd-archive` next; nothing in CRITICAL/WARNING blocks archiving.
2. **Manual smoke test before merging**: verify the matrix renders correctly for PROGRAMADA → CONFIRMADA transitions:
   - cms/clientes/<id>: PROGRAMADA shows "Cambiar a pendiente"; CONFIRMADA shows "Cerrar cita"; REALIZADA_PENDIENTE_VERIFICACION shows nothing useful today (no actions).
   - cms/operaciones/<id>: PROGRAMADA shows "Reprogramar | Marcar como pendiente | Cancelar"; CONFIRMADA shows "Cerrar cita"; others hide everything.
3. **Optional follow-up change**: add Playwright spec for the per-state button matrix and the CerrarCitaModal flow (~80 LOC). Captures regressions if the spec evolves again.
4. **Optional follow-up change**: rename or delete `markAppointmentPendingBiometricExtended` so it can't be reused by mistake.
