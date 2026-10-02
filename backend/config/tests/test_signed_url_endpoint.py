"""Tests for ``/api/media/signed-url/`` (cloud-storage-migration, slice 2).

These tests cover the per-spec scenario table:

* 401 — unauthenticated.
* 400 — ``path=../../etc/passwd`` / leading ``/`` / backslash.
* 400 — path outside the allowlist.
* 200 — cliente self (their own ficha PDF).
* 200 — admin principal wildcard.
* 200 — admin sucursal (own branch).
* 403 — cliente A tries to mint for cliente B's ficha.
* 403 — admin sucursal A tries to mint for admin sucursal B's resource.
* 503 — audit write fails (fail-closed).
* TTL clamp — request ``ttl=99999999`` returns ``ttl_seconds=604800``.
* 404 — key missing in bucket (slice 2 decision: never fall back to
  local for presigned URL issuance).

All boto3 + DB writes are mocked. No live AWS calls. No live DB
writes beyond the in-memory SQLite created by Django's ``TestCase``.
"""

from __future__ import annotations

import io
import os
import tempfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import mock

# Boot Django before any Django imports below — matches the slice 1
# ``test_storage_backends.py`` bootstrap so both files share the same
# settings module + DB backend across a pytest run.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_USE_LOCAL_DB", "1")
os.environ.setdefault("AWS_STORAGE_BUCKET_NAME", "test-bucket")
import django  # noqa: E402

django.setup()

from django.db import DatabaseError  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.test import SimpleTestCase, TestCase, override_settings  # noqa: E402

from accounts.models import Rol, Usuario  # noqa: E402
from customers.models import Cliente  # noqa: E402
from catalogs.models import ServicioConfig, Sucursal, TipoServicio  # noqa: E402
from operations.models import Operacion, OperacionFoto  # noqa: E402
from staff.models import Especialista  # noqa: E402
from clinical.models import FichaClinica  # noqa: E402
from audit.models import AuditLog  # noqa: E402
from audit.services import write_audit_log, AuditWriteFailure  # noqa: E402


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class _FakeS3Client:
    """In-memory boto3 S3 client stand-in.

    Mirrors the slice 1 fake client: ``put_object``/``get_object``/
    ``delete_object``/``head_object`` are the four CRUD entry points
    the storage backend exercises. ``generate_presigned_url`` is the
    fifth, exercised only by the slice 2 endpoint.
    """

    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict] = []
        self.get_calls: list[dict] = []
        self.head_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.presign_calls: list[dict] = []
        self.head_error: Exception | None = None

    def put_object(self, *, Bucket, Key, Body, **_kwargs):
        self.put_calls.append({"Bucket": Bucket, "Key": Key, "Body": Body})
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key, **_kwargs):
        self.get_calls.append({"Bucket": Bucket, "Key": Key})
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket, Key, **_kwargs):
        self.head_calls.append({"Bucket": Bucket, "Key": Key})
        if self.head_error is not None:
            raise self.head_error
        if (Bucket, Key) not in self.objects:
            raise _client_error(404)
        return {
            "ContentLength": len(self.objects[(Bucket, Key)]),
            "LastModified": datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        }

    def delete_object(self, *, Bucket, Key, **_kwargs):
        self.delete_calls.append({"Bucket": Bucket, "Key": Key})
        self.objects.pop((Bucket, Key), None)

    def generate_presigned_url(self, operation, *, Params, ExpiresIn, **_kwargs):
        self.presign_calls.append(
            {
                "operation": operation,
                "Params": dict(Params),
                "ExpiresIn": ExpiresIn,
            }
        )
        return (
            f"https://{Params['Bucket']}.s3.sa-east-1.amazonaws.com/"
            f"{Params['Key']}?X-Amz-Signature=fake&ExpiresIn={ExpiresIn}"
        )


def _client_error(status_code: int) -> Exception:
    from botocore.exceptions import ClientError

    return ClientError(
        error_response={
            "Error": {"Code": "NoSuchKey"},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        },
        operation_name="HeadObject",
    )


def _seed_graph(testcase: "_SignedUrlEndpointTests"):
    """Build a minimal but realistic fixture set used by the auth +
    owner-lookup tests.

    Layout:

    * ``sucursal_a`` / ``sucursal_b`` — two branches.
    * ``admin_principal_user`` — ADMIN_PRINCIPAL wildcard.
    * ``admin_sucursal_a_user`` — ADMIN_SUCURSAL of branch A.
    * ``admin_sucursal_b_user`` — ADMIN_SUCURSAL of branch B.
    * ``cliente_a_user`` / ``cliente_b_user`` — CLIENTE in branch A/B.
    * ``especialista_user`` — Especialista assigned to ``operacion_a``.
    * ``operacion_a`` — owned by ``cliente_a`` in branch A.
    * ``operacion_b`` — owned by ``cliente_b`` in branch B.
    * ``ficha_a_pdf`` — ``fichas_clinicas/2026/10/a.pdf`` on ficha A.
    * ``ficha_b_pdf`` — ``fichas_clinicas/2026/10/b.pdf`` on ficha B.
    """
    testcase.sucursal_a = Sucursal.objects.create(nombre="Sucursal A", activa=True)
    testcase.sucursal_b = Sucursal.objects.create(nombre="Sucursal B", activa=True)

    rol_admin_principal = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    rol_admin_sucursal = Rol.objects.create(rol="ADMIN_SUCURSAL")
    rol_cliente = Rol.objects.create(rol="CLIENTE")
    rol_especialista = Rol.objects.create(rol="TRABAJADOR")

    testcase.admin_principal_user = Usuario.objects.create_user(
        username="admin_principal",
        password="x",
        primer_nombre="Admin",
        apellido_paterno="Principal",
        rol=rol_admin_principal,
        sucursal=None,
    )

    testcase.admin_sucursal_a_user = Usuario.objects.create_user(
        username="admin_sucursal_a",
        password="x",
        primer_nombre="Admin",
        apellido_paterno="Sucursal A",
        rol=rol_admin_sucursal,
        sucursal=testcase.sucursal_a,
    )
    testcase.admin_sucursal_b_user = Usuario.objects.create_user(
        username="admin_sucursal_b",
        password="x",
        primer_nombre="Admin",
        apellido_paterno="Sucursal B",
        rol=rol_admin_sucursal,
        sucursal=testcase.sucursal_b,
    )

    cliente_a_user = Usuario.objects.create_user(
        username="cliente_a",
        password="x",
        primer_nombre="Cliente",
        apellido_paterno="A",
        rol=rol_cliente,
        sucursal=None,
    )
    cliente_b_user = Usuario.objects.create_user(
        username="cliente_b",
        password="x",
        primer_nombre="Cliente",
        apellido_paterno="B",
        rol=rol_cliente,
        sucursal=None,
    )

    testcase.cliente_a = Cliente.objects.create(
        usuario=cliente_a_user,
        sucursal_origen=testcase.sucursal_a,
        fecha_nacimiento=date(1990, 1, 1),
    )
    testcase.cliente_b = Cliente.objects.create(
        usuario=cliente_b_user,
        sucursal_origen=testcase.sucursal_b,
        fecha_nacimiento=date(1990, 1, 1),
    )

    specialist_user = Usuario.objects.create_user(
        username="especialista_a",
        password="x",
        primer_nombre="Especialista",
        apellido_paterno="A",
        rol=rol_especialista,
        sucursal=None,
    )
    testcase.especialista_a = Especialista.objects.create(
        usuario=specialist_user,
        sucursal_base=testcase.sucursal_a,
    )

    tipo_servicio = TipoServicio.objects.create(tipo="Consulta")
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo_servicio,
        precio_base=Decimal("100"),
    )
    testcase.operacion_a = Operacion.objects.create(
        paciente=testcase.cliente_a,
        servicio_config=servicio,
        precio_total=Decimal("100"),
        sesiones_totales=1,
    )
    testcase.operacion_b = Operacion.objects.create(
        paciente=testcase.cliente_b,
        servicio_config=servicio,
        precio_total=Decimal("100"),
        sesiones_totales=1,
    )

    testcase.ficha_a_pdf = "fichas_clinicas/2026/10/a.pdf"
    testcase.ficha_b_pdf = "fichas_clinicas/2026/10/b.pdf"
    FichaClinica.objects.create(
        operacion=testcase.operacion_a,
        documento_escaneado_pdf=testcase.ficha_a_pdf,
    )
    FichaClinica.objects.create(
        operacion=testcase.operacion_b,
        documento_escaneado_pdf=testcase.ficha_b_pdf,
    )

    # Seed an operation photo on operacion_a so we have a
    # ``fotos_operacion/`` test target if needed.
    testcase.foto_operacion_path = "fotos_operacion/2026/10/x.jpg"
    OperacionFoto.objects.create(
        operacion=testcase.operacion_a,
        kind=OperacionFoto.Kind.ANTES,
        imagen=testcase.foto_operacion_path,
    )


# ---------------------------------------------------------------------------
# TestCase base
# ---------------------------------------------------------------------------


class _SignedUrlEndpointTests(TestCase):
    """Shared bootstrap for the endpoint test cases.

    Subclasses get a fresh fake boto3 client, a stub
    ``AuditLog.objects.create`` spy, and the full user/owner graph
    populated. Subclasses may override either patch in
    ``setUp()``/``tearDown()`` for the audit-failure scenario.
    """

    def setUp(self) -> None:
        super().setUp()
        self.fake_client = _FakeS3Client()
        # Pre-seed the bucket with the two fixture ficha PDFs so the
        # happy-path "exists" check returns True.
        self.fake_client.objects[(
            "test-bucket",
            "fichas_clinicas/2026/10/a.pdf",
        )] = b"a-pdf"
        self.fake_client.objects[(
            "test-bucket",
            "fichas_clinicas/2026/10/b.pdf",
        )] = b"b-pdf"
        self.fake_client.objects[(
            "test-bucket",
            "fotos_operacion/2026/10/x.jpg",
        )] = b"x-jpg"

        # Patch boto3.client — same pattern as the slice 1 tests.
        # The endpoint constructs a fresh ``Boto3Storage`` instance per
        # request and calls ``exists`` / ``generate_presigned_url``
        # through it; both methods go through
        # ``config.storage_backends._get_s3_client``, which itself
        # invokes ``config.storage_backends.boto3.client`` — patching
        # that one call site covers every path the view exercises.
        client_patcher = mock.patch(
            "config.storage_backends.boto3.client",
            return_value=self.fake_client,
        )
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

        # Seed the user / cliente / operacion / ficha graph.
        _seed_graph(self)

        # Spy on AuditLog.objects.create so we can both count calls and
        # force the audit-failure path in the dedicated test.
        self._audit_create_calls: list[dict] = []

        real_create = AuditLog.objects.create

        def _spy(**kwargs):
            self._audit_create_calls.append(kwargs)
            return real_create(**kwargs)

        self._create_spy = mock.patch.object(
            AuditLog.objects, "create", side_effect=_spy
        )
        self._create_spy.start()
        self.addCleanup(self._create_spy.stop)


# ---------------------------------------------------------------------------
# Status code coverage
# ---------------------------------------------------------------------------


class MediaSignedUrlEndpointTests(_SignedUrlEndpointTests):
    """HTTP-level coverage of the endpoint."""

    def _get(self, path, query, user=None):
        """Issue a GET against the endpoint with the given path query
        param. When ``user`` is provided, the test client logs in as
        that user before issuing the request.
        """
        client = self.client
        if user is not None:
            client.force_login(user)
        return client.get(
            "/api/media/signed-url/",
            {"path": query},
        )

    # ---- 401 ----

    def test_unauthenticated_request_returns_401(self):
        response = self._get("/api/media/signed-url/", "fichas_clinicas/2026/10/a.pdf")
        self.assertEqual(response.status_code, 401)
        # No audit row on 401 — the spec §"401 and 403 do not write
        # audit rows" is a hard contract.
        self.assertEqual(self._audit_create_calls, [])

    # ---- 400 ----

    def test_malformed_path_dotdot_returns_400(self):
        response = self._get(
            "/api/media/signed-url/", "../../etc/passwd", user=self.cliente_a.usuario
        )
        self.assertEqual(response.status_code, 400)

    def test_malformed_path_leading_slash_returns_400(self):
        response = self._get(
            "/api/media/signed-url/", "/etc/passwd", user=self.cliente_a.usuario
        )
        self.assertEqual(response.status_code, 400)

    def test_malformed_path_backslash_returns_400(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas\\2026\\10\\a.pdf",
            user=self.cliente_a.usuario,
        )
        self.assertEqual(response.status_code, 400)

    def test_path_outside_allowlist_returns_400(self):
        response = self._get(
            "/api/media/signed-url/",
            "random/path.pdf",
            user=self.cliente_a.usuario,
        )
        self.assertEqual(response.status_code, 400)

    # ---- 200 happy paths ----

    def test_cliente_self_mints_url(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/a.pdf",
            user=self.cliente_a.usuario,
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("url", body)
        self.assertIn("expires_at", body)
        self.assertEqual(body["ttl_seconds"], 900)
        self.assertEqual(
            body["url"],
            "https://test-bucket.s3.sa-east-1.amazonaws.com/"
            "fichas_clinicas/2026/10/a.pdf"
            "?X-Amz-Signature=fake&ExpiresIn=900",
        )
        # Audit row recorded.
        self.assertEqual(len(self._audit_create_calls), 1)
        audit = self._audit_create_calls[0]
        self.assertEqual(audit["resource_path"], "fichas_clinicas/2026/10/a.pdf")
        self.assertEqual(audit["user_role"], "CLIENTE")
        self.assertEqual(audit["action"], "SIGNED_URL_ISSUED")
        # boto3 presign call shape (the view calls
        # Boto3Storage.generate_presigned_url which delegates to the
        # underlying boto3 client).
        self.assertEqual(len(self.fake_client.presign_calls), 1)
        presign = self.fake_client.presign_calls[0]
        self.assertEqual(presign["operation"], "get_object")
        self.assertEqual(presign["Params"]["Bucket"], "test-bucket")
        self.assertEqual(presign["Params"]["Key"], "fichas_clinicas/2026/10/a.pdf")
        self.assertEqual(presign["ExpiresIn"], 900)

    def test_admin_principal_wildcard_mints_any_resource(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/b.pdf",
            user=self.admin_principal_user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["ttl_seconds"], 900)
        self.assertEqual(len(self.fake_client.presign_calls), 1)

    def test_admin_sucursal_own_branch_mints(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/a.pdf",
            user=self.admin_sucursal_a_user,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(self.fake_client.presign_calls), 1)

    # ---- 403 forbidden ----

    def test_cliente_cannot_mint_for_other_cliente(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/b.pdf",
            user=self.cliente_a.usuario,
        )
        self.assertEqual(response.status_code, 403)
        # No audit row on 403.
        self.assertEqual(self._audit_create_calls, [])

    def test_admin_sucursal_cannot_mint_for_other_branch(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/b.pdf",
            user=self.admin_sucursal_a_user,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self._audit_create_calls, [])

    # ---- 404 bucket miss ----

    def test_missing_key_in_bucket_returns_404(self):
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/nonexistent.pdf",
            user=self.admin_principal_user,
        )
        self.assertEqual(response.status_code, 404)
        # No audit on a 404 either (the endpoint short-circuits before
        # the audit write).
        self.assertEqual(self._audit_create_calls, [])
        # And no presigned URL was minted.
        self.assertEqual(self.fake_client.presign_calls, [])

    # ---- 503 audit fail-closed ----

    def test_audit_write_failure_returns_503(self):
        # Force AuditLog.objects.create to raise a DatabaseError.
        with mock.patch.object(
            AuditLog.objects,
            "create",
            side_effect=DatabaseError("simulated DB outage"),
        ):
            response = self._get(
                "/api/media/signed-url/",
                "fichas_clinicas/2026/10/a.pdf",
                user=self.cliente_a.usuario,
            )
        self.assertEqual(response.status_code, 503)
        # Critical: NO presigned URL minted on audit failure.
        self.assertEqual(self.fake_client.presign_calls, [])

    # ---- TTL clamping ----

    def test_ttl_clamped_to_sigv4_max(self):
        """``ttl=99999999`` from the caller is clamped to 604800 (SigV4 max).

        The default TTL (when no ``ttl`` query param is provided) is
        ``MEDIA_SIGNED_URL_TTL_SECONDS`` = 900. The clamp applies only
        when the caller asks for more than the SigV4 hard cap, which is
        exactly what the spec §"TTL caps at 7 days" scenario covers.
        """
        response = self._get(
            "/api/media/signed-url/",
            "fichas_clinicas/2026/10/a.pdf",
            user=self.admin_principal_user,
        )
        # Bare login, default TTL — confirms the 900 baseline used by
        # the other happy-path tests.
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["ttl_seconds"], 900)

        # Now request an absurd TTL — must clamp to 604800.
        self.client.force_login(self.admin_principal_user)
        response = self.client.get(
            "/api/media/signed-url/",
            {"path": "fichas_clinicas/2026/10/a.pdf", "ttl": "99999999"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["ttl_seconds"], 604800)
        # Presign call observed the clamped TTL.
        self.assertEqual(
            self.fake_client.presign_calls[-1]["ExpiresIn"], 604800
        )


# ---------------------------------------------------------------------------
# Service-layer coverage (audit writer)
# ---------------------------------------------------------------------------


class AuditWriteFailureTranslationTests(TestCase):
    """``audit.services.write_audit_log`` translates DB errors into
    :class:`AuditWriteFailure` so the view only has to catch one
    exception type regardless of the DB driver.
    """

    def test_audit_write_failure_translates_database_error(self):
        with mock.patch.object(
            AuditLog.objects,
            "create",
            side_effect=DatabaseError("DB outage"),
        ):
            with self.assertRaises(AuditWriteFailure):
                write_audit_log(
                    user=None,
                    user_role="",
                    action="SIGNED_URL_ISSUED",
                    resource_path="fichas_clinicas/2026/10/a.pdf",
                    resource_type="clinical.FichaClinica.documento_escaneado_pdf",
                    client_ip=None,
                    user_agent="",
                    expires_at=None,
                )

    def test_audit_write_success_returns_instance(self):
        row = write_audit_log(
            user=None,
            user_role="CLIENTE",
            action="SIGNED_URL_ISSUED",
            resource_path="fichas_clinicas/2026/10/a.pdf",
            resource_type="clinical.FichaClinica.documento_escaneado_pdf",
            client_ip="127.0.0.1",
            user_agent="Mozilla/5.0",
            expires_at=None,
        )
        self.assertIsInstance(row, AuditLog)
        self.assertEqual(row.action, "SIGNED_URL_ISSUED")
        self.assertEqual(row.resource_path, "fichas_clinicas/2026/10/a.pdf")
        self.assertEqual(row.user_role, "CLIENTE")
        self.assertEqual(row.client_ip, "127.0.0.1")


# ---------------------------------------------------------------------------
# Boto3Storage.generate_presigned_url coverage
# ---------------------------------------------------------------------------


class Boto3StoragePresignedUrlTests(TestCase):
    """The new helper delegates to ``boto3.client.generate_presigned_url``
    with the right operation + Params shape.
    """

    def setUp(self) -> None:
        super().setUp()
        self.fake_client = _FakeS3Client()
        bucket_patcher = mock.patch.dict(
            os.environ, {"AWS_STORAGE_BUCKET_NAME": "test-bucket"}
        )
        bucket_patcher.start()
        self.addCleanup(bucket_patcher.stop)
        client_patcher = mock.patch(
            "config.storage_backends.boto3.client",
            return_value=self.fake_client,
        )
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

    def test_generate_presigned_url_signature(self):
        from config.storage_backends import Boto3Storage

        storage = Boto3Storage()
        url = storage.generate_presigned_url("uploads/foo.pdf", 900)
        self.assertIn("X-Amz-Signature=fake", url)
        self.assertEqual(len(self.fake_client.presign_calls), 1)
        call = self.fake_client.presign_calls[0]
        self.assertEqual(call["operation"], "get_object")
        self.assertEqual(call["Params"], {"Bucket": "test-bucket", "Key": "uploads/foo.pdf"})
        self.assertEqual(call["ExpiresIn"], 900)


# Slice 4 additive: backfill_media --verify flag accepted.


class _VerifyFakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket, Key, Body, **_kwargs):
        self.objects[(Bucket, Key)] = Body

    def head_object(self, *, Bucket, Key, **_kwargs):
        if (Bucket, Key) not in self.objects:
            raise _client_error(404)
        return {"ContentLength": len(self.objects[(Bucket, Key)])}


class BackfillMediaVerifyFlagTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="backfill-verify-test-"))
        self.fake = _VerifyFakeS3Client()
        bucket_patch = mock.patch.dict(
            os.environ, {"AWS_STORAGE_BUCKET_NAME": "test-bucket"}
        )
        bucket_patch.start()
        self.addCleanup(bucket_patch.stop)
        client_patch = mock.patch(
            "config.storage_backends.boto3.client", return_value=self.fake
        )
        client_patch.start()
        self.addCleanup(client_patch.stop)

    def test_verify_flag_runs_uploads(self):
        (self.tmp / "a.pdf").write_bytes(b"a")
        (self.tmp / "b.pdf").write_bytes(b"b")
        with override_settings(MEDIA_ROOT=self.tmp):
            call_command("backfill_media", "--verify", "--batch-size=10")
        keys = {k for (_, k) in self.fake.objects.keys()}
        self.assertIn("a.pdf", keys)
        self.assertIn("b.pdf", keys)