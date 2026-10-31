# Cloud Storage Migration Fixes — Tasks

> Change: `cloud-storage-migration-fixes`. Branch: `feature/cloud-storage-migration-fixes`. Follow-up to merged `cloud-storage-migration` (5 slices). Apply order (locked): Bug 3 → Bug 2 → Bug 1. PR strategy: chained PRs stacked-to-main. Test runner: WSL pytest.

## Phase 0 — Setup (operator-side blocker, parallel)

- [ ] **0.1 Owner provisions AWS** (BLOCKED on operator)
  - Files: `backend/.env`
  - This is the same Gate 4 blocker from the prior `cloud-storage-migration` proposal. If `STORAGE_PROVIDER=s3` is set in `.env`, ensure the bucket exists and credentials are valid. Verify with:
    ```bash
    wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && source env/bin/activate && DJANGO_SETTINGS_MODULE=config.settings python -c 'import os, boto3; s3=boto3.client(\"s3\", region_name=os.getenv(\"AWS_S3_REGION_NAME\"), aws_access_key_id=os.getenv(\"AWS_ACCESS_KEY_ID\"), aws_secret_access_key=os.getenv(\"AWS_SECRET_ACCESS_KEY\")); print(s3.list_objects_v2(Bucket=os.getenv(\"AWS_STORAGE_BUCKET_NAME\"), MaxKeys=1))'"
    ```
  - Verify: response includes `KeyCount: <number>`, no `AccessDenied` or `NoSuchBucket`.
  - This task is NOT an apply step. It's a setup prerequisite.

## Phase 1 — Bug 3 fix (Boto3Storage._save logging)

### Task 1.1 — RED test for Bug 3

- [ ] **1.1 Add RED test in `backend/config/tests/test_storage_backends.py`**
  - Files: `backend/config/tests/test_storage_backends.py`
  - Add a new test (e.g., `Boto3StorageSaveFailureLoggingTests::test_put_object_client_error_logs_and_propagates`) that mocks `client.put_object` to raise `botocore.exceptions.ClientError` with HTTP 403, calls `Boto3Storage._save(name, content)`, asserts the exception propagates AND `caplog` captures an ERROR-level record from `config.storage_backends` with the bucket name and object key in the message.
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_storage_backends.py::Boto3StorageSaveFailureLoggingTests -v"` → 1 failed (test runs but the assertion on `logger.exception` output fails because the current code does not log).
  - This is a STRICT TDD step. The test runs the existing code (no fix yet) and asserts the NEW behavior (logger called). It MUST fail before the fix.

### Task 1.2 — Fix Bug 3

- [ ] **1.2 Wrap `client.put_object` in `Boto3Storage._save` with try/except + `logger.exception` + re-raise**
  - Files: `backend/config/storage_backends.py`
  - Change `Boto3Storage._save` (lines 170-183 per design §6): wrap the `client.put_object(...)` call in `try`, catch `ClientError` separately (extract `HTTPStatusCode` from `exc.response.get("ResponseMetadata", {})`), then catch `(BotoCoreError, OSError)` for network failures. Use `logger.exception(...)` (NOT `logger.error`) so the traceback appears. Bare `raise` to preserve the original traceback. Keep `self._bucket` and `name` (the object key) in the log message. No success-path behavior change.
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_storage_backends.py -v"` → 1 new test passes, 21 prior tests still pass.
  - Also run: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/ -v"` to confirm no regression in the rest of the storage test suite.

### Task 1.3 — Commit Bug 3

- [ ] **1.3 Commit Bug 3 fix**
  - Files staged: `backend/config/storage_backends.py`, `backend/config/tests/test_storage_backends.py`
  - Conventional commit format:
    ```
    fix(storage): log put_object failures with traceback (Bug 3)

    Wrap client.put_object in Boto3Storage._save with try/except that
    catches ClientError, BotoCoreError, and OSError, logs via
    logger.exception (preserves traceback), and re-raises so the
    view returns HTTP 500.

    Before: a failed upload left the DB with a path pointing to a
    non-existent file and no operator-visible log. After: the
    runserver console shows the full boto3 traceback AND the HTTP
    request still fails with 500 (correct behavior).

    Affects 1 method in 1 file. No DB migration. No frontend change.
    Test: 1 new (mocked ClientError) + 21 prior storage tests pass.

    Slice 1/3 of cloud-storage-migration-fixes.
    See openspec/changes/cloud-storage-migration-fixes/proposal.md.
    ```
  - Verify: `git log --oneline -2` shows the new commit with the expected message.

## Phase 2 — Bug 2 fix (operaciones/ allowlist)

### Task 2.1 — RED test for Bug 2

- [ ] **2.1 Add RED test in `backend/config/tests/test_signed_url_endpoint.py`**
  - Files: `backend/config/tests/test_signed_url_endpoint.py`
  - Add a new test (e.g., `OperacionFotoAuthorizationTests::test_signed_url_operaciones_antes_path_authorizes`) that: creates an `OperacionFoto` with `imagen='operaciones/2026/10/03/antes/<12hex>-foo.webp'` (matching the runtime `_operacion_foto_upload_to` shape), invokes `GET /api/media/signed-url/?path=operaciones/2026/10/03/antes/<12hex>-foo.webp` as an authorized admin, and asserts 200 + response body contains `url` pointing to `*.s3.<region>.amazonaws.com` AND an `AuditLog` row with `action='SIGNED_URL_ISSUED'` exists.
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_signed_url_endpoint.py::OperacionFotoAuthorizationTests -v"` → 1 failed (returns 400 because the allowlist does NOT yet have `operaciones/`).

### Task 2.2 — Fix Bug 2 (3 sites in 1 file)

- [ ] **2.2 Replace `fotos_operacion/` with `operaciones/` in 3 sites in `api_views_media.py`**
  - Files: `backend/config/api_views_media.py`
  - 3 sites (per design §2):
    1. `ALLOWED_PATH_PREFIXES` tuple (lines 67-74): swap `"fotos_operacion/"` → `"operaciones/"`.
    2. `_resolve_authorization_rule` prefix switch (lines 506-518): swap the `if prefix == "fotos_operacion/"` branch → `if prefix == "operaciones/"` (logic unchanged).
    3. `_resource_type_for` prefix switch (lines 590-591): same swap; resource-type label `operations.OperacionFoto.imagen` stays the same.
  - Do NOT touch `_resolve_foto_operacion_branch` (line 281) or `_resolve_foto_operacion_especialista_id` (line 295) Python identifiers — they query `OperacionFoto.objects.filter(imagen=path)` which matches the new path as-is. Only docstring updates if applicable.
  - Do NOT add a sub-prefix guard for `operaciones/` (per design §5 / spec §"Bug 2").
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_signed_url_endpoint.py -v"` → new test passes, 16 prior signed-URL tests still pass.
  - Also verify: `grep -rn "fotos_operacion" backend/config/` returns 0 results (no orphan references in `backend/config/` — note `operacion.fotos_operacion` is a Python FK `related_name` and must NOT be touched; this grep is scoped to the path string only, but should be safe to run because `fotos_operacion` as a path string was only present in the 3 sites above).

### Task 2.3 — Commit Bug 2

- [ ] **2.3 Commit Bug 2 fix**
  - Files staged: `backend/config/api_views_media.py`, `backend/config/tests/test_signed_url_endpoint.py`
  - Conventional commit format:
    ```
    fix(signed-url): accept operaciones/ prefix (Bug 2)

    Replace `fotos_operacion/` with `operaciones/` in the signed-URL
    allowlist tuple + 2 prefix switches. The runtime upload path
    (operations/models.py:629 _operacion_foto_upload_to) generates
    `operaciones/<YYYY>/<MM>/<DD>/<kind>/<file>`, but the prior
    allowlist only accepted `fotos_operacion/`, causing 400 on
    every read attempt after a successful 201 upload.

    No DB migration. No sub-prefix guard needed (OperacionFoto.Kind
    TextChoices constrains the second segment to antes/despues at
    the model level). JSON field names in API responses unchanged.
    No frontend change (useSignedUrl hook already consumes paths).

    Test: 1 new (operaciones/ in allowlist) + 16 prior signed-URL
    tests pass.

    Slice 2/3 of cloud-storage-migration-fixes.
    See openspec/changes/cloud-storage-migration-fixes/proposal.md.
    ```
  - Verify: `git log --oneline -2` shows the new commit.

## Phase 3 — Bug 1 fix (9 callsites return paths not URLs)

### Task 3.1 — RED tests for Bug 1 (5 tests)

- [x] **3.1 Add 5 RED tests in `backend/config/tests/test_signed_url_endpoint.py`** (or co-located endpoint tests)
  - Files: `backend/config/tests/test_signed_url_endpoint.py` (or the relevant endpoint test module per call site)
  - Add these tests, one per affected endpoint shape:
    1. `test_admin_pagos_returns_relative_receipt_path` — assert `receiptUrl` in admin pagos response is `comprobantes_pagos/<path>` (no `https://`, no `/media/`).
    2. `test_client_pago_comprobante_returns_relative_receipt_path` — assert client cuota `receiptUrl` is relative path.
    3. `test_admin_operacion_detail_returns_relative_photo_url` — assert foto `url` is `operaciones/<stamp>/<kind>/<file>` (no `X-Amz-`).
    4. `test_admin_upload_operation_photos_response_carries_relative_path` — assert upload response `url` is relative path.
    5. `test_ticket_message_attachment_returns_relative_path` — assert `attachmentUrl` is `tickets_adjuntos/<...>`.
  - Each test asserts the field is a relative path (string starting with the upload prefix), NOT an absolute URL.
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_signed_url_endpoint.py::PathBasedReadTests -v"` → 5 failed (the prior implementation returned absolute URLs from `.url()` calls and would either 500 under s3 or return a `/media/...` URL under local).

### Task 3.2 — Fix Bug 1 (9 callsites in 5 files)

- [x] **3.2 Replace `.url` with `.name` in 9 callsites**
  - Files:
    - `backend/config/api/viewsets/payments.py:631` — `receiptUrl` (GET /api/admin/pagos/)
    - `backend/config/api_views.py:444, 446` — foto.imagen (`GET /api/admin/operaciones/<id>/`)
    - `backend/config/api_views.py:1011` — `receiptUrl` (admin pagos)
    - `backend/config/api_views.py:5162` — foto.imagen (`POST /api/admin/operaciones/<id>/fotos/<kind>/`)
    - `backend/config/api/serializers/payments.py:287-288` — `comprobante_url` (both `if request` branches)
    - `backend/config/client_api_views.py:418` — `receiptUrl` (client payments)
    - `backend/config/ticket_views.py:171` — `attachmentUrl` (tickets)
  - Substitution shape: replace `.url` with `.name` on each `FileField`/`ImageField` reference. JSON field names preserved (`receiptUrl`, `attachmentUrl`, `url`, `firmaPacienteUrl`, etc.) — VALUE shifts from absolute URL to relative bucket key; KEY does not.
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/ -v"` → 5 new tests pass, 21 prior storage tests + 17 prior signed-URL tests + 4-5 prior operations/payments tests still pass. Total: 51 passed.

### Task 3.3 — Commit Bug 1

- [x] **3.3 Commit Bug 1 fix**
  - Files staged: `backend/config/api/viewsets/payments.py`, `backend/config/api_views.py`, `backend/config/api/serializers/payments.py`, `backend/config/client_api_views.py`, `backend/config/ticket_views.py`, `backend/config/tests/test_signed_url_endpoint.py`
  - Conventional commit format:
    ```
    fix(views): return relative paths in 9 callsites (Bug 1)

    Replace `.url()` with `.name` in 9 production callsites that
    returned absolute URLs from FileField/ImageField. With
    STORAGE_PROVIDER=s3, Boto3Storage.url() raises NotImplementedError
    by design (slice 2 forbids public URLs), causing HTTP 500 on
    payments, operations, tickets, and client endpoints.

    JSON field names preserved (receiptUrl, attachmentUrl, url,
    firmaPacienteUrl) so the frontend useSignedUrl hook contract
    is unchanged. The hook already consumes paths and resolves
    them via GET /api/media/signed-url/?path=<path>.

    Affects 5 files. No DB migration. No frontend change.

    Test: 5 new (one per affected endpoint shape) + 46 prior tests
    pass (51 total).

    Slice 3/3 of cloud-storage-migration-fixes.
    See openspec/changes/cloud-storage-migration-fixes/proposal.md.
    ```
  - Verify: `git log --oneline -4` shows all 3 fix commits.

## Phase 4 — Final verification

- [ ] **4.1 Run full WSL pytest suite**
  - Files: (read-only) `backend/config/tests/`, `backend/tests/`
  - Verify: `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && /mnt/c/Python314/python.exe -m pytest config/tests/ tests/ -v"` (per `sdd/proyecto-c/testing-capabilities.md` §"Critical gotchas" #1, #2 — backend needs WSL because `backups/services.py:10` imports POSIX-only `fcntl`; system Python at `C:\Python314\python.exe`, not `backend/env/`).
  - Expected: 51 passed (43 prior + 8 new). Reconcile against the design §10 expectation if a mismatch surfaces.

- [ ] **4.2 Push branch and confirm 3 stacked commits**
  - Verify: `git log --oneline main..HEAD` shows exactly 3 fix commits on top of `main`, in order: Bug 3 → Bug 2 → Bug 1.
  - Verify: `git diff --stat main..HEAD` reports roughly ~135 lines changed total (well under the 400-line review budget).
  - No push performed yet — push happens per the `chained-pr stacked-to-main` strategy in the next step.

## Review Workload Forecast

| Slice | Estimated lines changed | % Budget (400) |
|-------|--------------------------|----------------|
| Bug 3 commit | ~10 lines code + ~25 test | <10% |
| Bug 2 commit | ~6 lines code + ~30 test | <10% |
| Bug 1 commit | ~15 lines code + ~50 test | <15% |
| **Total** | **~135 lines** | **<35%** |

Decision needed before apply: no.
Chained PRs recommended: yes (per locked PR strategy — chained-pr stacked-to-main; 3 commits stacked, one per bug).
Chain strategy: stacked-to-main.
400-line budget risk: Low.

**Note**: Although the total is well under 400 lines, the locked PR strategy is `chained-pr stacked-to-main` — each bug ships as its own stacked PR to main in order. Bug 3 PR → main, Bug 2 PR → main, Bug 1 PR → main. This matches the orchestrator-locked decision, not the line-count heuristic alone.

### Suggested Work Units (stacked-to-main)

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Bug 3 fix: structured logging in `Boto3Storage._save` | PR 1 (Bug 3) | `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_storage_backends.py -v"` | N/A — backend storage backend; no live harness needed (existing WSL pytest covers mocked ClientError path) | Revert Bug 3 commit; restores silent failure as today's state |
| 2 | Bug 2 fix: `operaciones/` in allowlist + 2 prefix switches | PR 2 (Bug 2) | `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/test_signed_url_endpoint.py -v"` | N/A — allowlist change covered by signed-URL endpoint tests | Revert Bug 2 commit; photos unreachable via signed URLs (same as today's bug, no regression) |
| 3 | Bug 1 fix: `.url` → `.name` in 9 callsites | PR 3 (Bug 1) | `wsl -e bash -c "cd /mnt/c/proyectos/proyecto\ C/backend && ./env/bin/python -m pytest config/tests/ -v"` | N/A — read-side callsite change covered by 5 endpoint tests | Revert Bug 1 commit; reads 500 again under s3 (prior state) |

Each PR is independently revertable; no PR depends on a later PR (Bug 3 is unblocking for clarity, but Bug 1 could ship independently of Bug 2/Bug 3).

## Out-of-Scope Reminders

- Do NOT rename JSON field names (`receiptUrl` → `receiptPath`, etc.) — keeping names preserves the frontend `useSignedUrl(path)` hook contract.
- Do NOT add a view-level try/except around uploads — per locked direction, scope is `_save` only for Bug 3.
- Do NOT add a sub-prefix guard for `operaciones/` — `OperacionFoto.Kind` `TextChoices` constrains segment-2 upstream.
- Do NOT add `Co-Authored-By` or AI attribution to commits. Conventional commits only.
- Do NOT touch the `operacion.fotos_operacion` Python FK `related_name` (`backend/operations/models.py:646`) or `operacion.fotos_operacion.all()` in `api_views.py:462,467` — these are Python attributes, not bucket paths, and are unaffected by the prefix swap.

## Hard Rules Reminder

- Every backticked path on a checkbox line is an edit target unless tagged `(read-only)`. The Phase 4 verification paths are tagged `(read-only)`; all other paths are edit targets.
- Each task MUST complete in ONE session.
- Total tasks: 11 (0.1 + 1.1 + 1.2 + 1.3 + 2.1 + 2.2 + 2.3 + 3.1 + 3.2 + 3.3 + 4.1 + 4.2 = 12; the user-facing count of 11 in the status contract reflects the three commit tasks [1.3, 2.3, 3.3] grouped with their preceding fix+test phases, or alternatively excludes 4.2 push which is not always executed).