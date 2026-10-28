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
from operations.models import CitaMedica, Operacion, OperacionFoto  # noqa: E402
from staff.models import Especialista  # noqa: E402
from clinical.models import FichaClinica  # noqa: E402
from notifications.models import Ticket, TicketMessage  # noqa: E402
from billing.models import (  # noqa: E402
    CategoriaGasto,
    ConfiguracionPagoQR,
    CuotaPlanPago,
    GastoSucursal,
    PagoRealizado,
)
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


# ---------------------------------------------------------------------------
# Bug 2 — operaciones/ prefix in the allowlist
# ---------------------------------------------------------------------------


class OperacionFotoAuthorizationTests(_SignedUrlEndpointTests):
    """Regression coverage for Bug 2 (cloud-storage-migration-fixes).

    The runtime upload callable
    :func:`operations.models._operacion_foto_upload_to` generates
    ``operaciones/<YYYY>/<MM>/<DD>/<kind>/<12hex>-<file>`` paths for
    ``OperacionFoto.imagen`` rows. The signed-URL endpoint's
    :data:`ALLOWED_PATH_PREFIXES` must accept ``operaciones/`` so that
    authorized admins can mint a presigned URL for a freshly-uploaded
    operation photo.

    Before the fix the endpoint returned 400 (path outside the
    allowlist). After the fix the endpoint returns 200 + an
    :class:`AuditLog` row with ``action='SIGNED_URL_ISSUED'``.
    """

    OPERACIONES_PATH = "operaciones/2026/10/03/antes/abcd1234abcd-foo.webp"

    def setUp(self) -> None:
        super().setUp()
        # Create an OperacionFoto whose ``imagen`` matches the runtime
        # generator shape so the path-lookup helpers
        # (``_resolve_foto_operacion_branch`` /
        # ``_resolve_foto_operacion_especialista_id``) resolve to the
        # seeded operacion_a / especialista_a.
        self.operacion_foto = OperacionFoto.objects.create(
            operacion=self.operacion_a,
            kind=OperacionFoto.Kind.ANTES,
            imagen=self.OPERACIONES_PATH,
        )
        # Pre-seed the fake S3 client so ``head_object`` returns 200 for
        # the operaciones/ key — otherwise the endpoint short-circuits
        # to 404 BEFORE the prefix check we want to assert.
        self.fake_client.objects[
            ("test-bucket", self.OPERACIONES_PATH)
        ] = b"fake-image-bytes"

    def test_signed_url_operaciones_antes_path_authorizes(self):
        """Admin principal can mint a signed URL for an
        ``operaciones/.../antes/`` path that the runtime
        ``_operacion_foto_upload_to`` callable produced.
        """
        client = self.client
        client.force_login(self.admin_principal_user)
        response = client.get(
            "/api/media/signed-url/",
            {"path": self.OPERACIONES_PATH},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("url", body)
        # The presigned URL must point at the S3 endpoint (the fake
        # client returns ``*.s3.sa-east-1.amazonaws.com``).
        self.assertIn(
            "https://test-bucket.s3.sa-east-1.amazonaws.com/",
            body["url"],
        )
        self.assertIn(self.OPERACIONES_PATH, body["url"])
        # TTL clamp uses the default 900 unless caller overrides.
        self.assertEqual(body["ttl_seconds"], 900)
        # Audit row recorded (admin_principal wildcard → role label
        # matches the wildcard-skipping branch).
        self.assertEqual(len(self._audit_create_calls), 1)
        audit = self._audit_create_calls[0]
        self.assertEqual(audit["action"], "SIGNED_URL_ISSUED")
        self.assertEqual(audit["resource_path"], self.OPERACIONES_PATH)
        self.assertEqual(
            audit["resource_type"], "operations.OperacionFoto.imagen"
        )
        # boto3 presign called with the right Key.
        self.assertEqual(len(self.fake_client.presign_calls), 1)
        self.assertEqual(
            self.fake_client.presign_calls[0]["Params"]["Key"],
            self.OPERACIONES_PATH,
        )


# ---------------------------------------------------------------------------
# Bug 1 — Read APIs return relative paths (not absolute URLs)
# ---------------------------------------------------------------------------


class PathBasedReadTests(_SignedUrlEndpointTests):
    """Bug 1 (cloud-storage-migration-fixes) regression coverage.

    The 9 production callsites in design.md §2 used ``FieldFile.url``
    on a ``FileField``/``ImageField`` — returning ``/media/<path>``
    under local and HTTP 500 under s3 (Boto3Storage raises
    NotImplementedError). The fix swaps ``.url`` → ``.name`` so the
    response carries the bucket-relative path the ``useSignedUrl(path)``
    frontend hook consumes. Each test below asserts the field is a
    non-empty path starting with the upload prefix, NOT containing
    ``/media/`` and NOT starting with ``http://``/``https://``.
    """

    RECEIPT_PATH = "comprobantes_pagos/2026/10/recibo-prueba.pdf"
    FOTO_PATH = "operaciones/2026/10/03/antes/abcd1234abcd-foto.webp"
    ADJUNTO_PATH = "tickets_adjuntos/2026/10/adjunto-prueba.pdf"

    def _assert_path(self, value, prefix):
        """value MUST be a non-empty relative path starting with prefix."""
        self.assertIsInstance(value, str)
        self.assertTrue(value, f"expected non-empty path, got {value!r}")
        self.assertTrue(
            value.startswith(prefix),
            f"expected path to start with {prefix!r}, got {value!r}",
        )
        self.assertNotIn("/media/", value)
        self.assertFalse(
            value.startswith("http://") or value.startswith("https://"),
        )

    def setUp(self) -> None:
        super().setUp()
        # Migration 0008_data_migrate_sucursales seeds a
        # ``Sede Principal`` (es_principal=True). For admin_principal
        # ``get_user_branch`` returns that branch and the payments
        # viewset filters by ``paciente__usuario__sucursal_id``. The
        # cliente_a user seeded in ``_seed_graph`` has
        # ``sucursal=None`` — re-point it so the filter passes.
        principal_branch = Sucursal.objects.filter(es_principal=True).first()
        if principal_branch is not None:
            self.cliente_a.usuario.sucursal = principal_branch
            self.cliente_a.usuario.save(update_fields=["sucursal"])
        # Build a CuotaPlanPago + PagoRealizado for operacion_a. Django
        # accepts a bare string for ``FileField`` when no upload_to
        # round-trip is needed (matches the slice 1 fixture pattern).
        self.cuota_a = CuotaPlanPago.objects.create(
            operacion=self.operacion_a,
            nro_cuota=1,
            fecha_vencimiento=date(2026, 10, 15),
            monto_programado=Decimal("50"),
        )
        self.pago_a = PagoRealizado.objects.create(
            cuota=self.cuota_a,
            monto_pagado=Decimal("50"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("50"),
            comprobante_url=self.RECEIPT_PATH,
        )
        # Ticket + message with attachment path string.
        self.ticket_a = Ticket.objects.create(
            sucursal=self.sucursal_a,
            creado_por=self.admin_principal_user,
            asunto="Prueba Bug 1",
        )
        self.ticket_message = TicketMessage.objects.create(
            ticket=self.ticket_a,
            autor=self.admin_principal_user,
            contenido="Mensaje con adjunto de prueba",
            adjunto=self.ADJUNTO_PATH,
        )
        # The shared ``_seed_graph`` seeds an ``OperacionFoto`` with
        # the legacy ``fotos_operacion/`` prefix (predates slice 2's
        # rename). Mutate to the new prefix so the relative-path
        # assertion holds.
        OperacionFoto.objects.filter(
            operacion=self.operacion_a,
            imagen="fotos_operacion/2026/10/x.jpg",
        ).update(imagen=self.FOTO_PATH)

    # ---- Test 1: GET /api/admin/pagos/ (callsite 1) ----

    def test_admin_pagos_returns_relative_receipt_path(self):
        """``GET /api/admin/pagos/`` (DRF ViewSet) — ``receiptUrl`` is a
        relative path. Callsite: ``api/viewsets/payments.py:631``."""
        self.client.force_login(self.admin_principal_user)
        response = self.client.get("/api/admin/pagos/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        matching = [
            p for p in body["payments"] if p["rawId"] == self.pago_a.pk
        ]
        self.assertEqual(len(matching), 1, body)
        self._assert_path(matching[0]["receiptUrl"], "comprobantes_pagos/")

    # ---- Test 2: POST /api/client/pagos/cuotas/<id>/comprobante/ (callsite 7) ----

    def test_client_pago_comprobante_returns_relative_receipt_path(self):
        """``POST /api/client/pagos/cuotas/<id>/comprobante/`` — the
        embedded ``payment.receiptUrl`` is a relative path. Callsite:
        ``client_api_views.py:418``. The client serializer requires a
        ``receiptFile`` upload."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.cliente_a.usuario)
        receipt = SimpleUploadedFile(
            "comprobante.pdf", b"%PDF-1.4\n%%EOF",
            content_type="application/pdf",
        )
        response = self.client.post(
            f"/api/client/pagos/cuotas/{self.cuota_a.pk}/comprobante/",
            data={"monto_pagado": "50", "receiptFile": receipt},
        )
        self.assertIn(response.status_code, (200, 201), response.content)
        body = response.json()
        self.assertIn("payment", body)
        self._assert_path(
            body["payment"]["receiptUrl"], "comprobantes_pagos/"
        )

    # ---- Test 3: GET /api/admin/operaciones/<id>/ (callsites 4-5) ----

    def test_admin_operacion_detail_returns_relative_photo_url(self):
        """``GET /api/admin/operaciones/<id>/`` — each photo's ``url`` is
        a relative path. Callsites: ``api_views.py:444,446``. Response
        splits fotos by kind under ``fotosAntes`` / ``fotosDespues``."""
        self.client.force_login(self.admin_principal_user)
        response = self.client.get(
            f"/api/admin/operaciones/{self.operacion_a.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        op = response.json()["operation"]
        all_fotos = list(op.get("fotosAntes", [])) + list(
            op.get("fotosDespues", [])
        )
        self.assertTrue(all_fotos, "expected at least one seeded foto")
        for foto in all_fotos:
            self._assert_path(foto["url"], "operaciones/")

    # ---- Test 4: POST /api/admin/operaciones/<id>/fotos/<kind>/ (callsite 6) ----

    def test_admin_upload_operation_photos_response_carries_relative_path(self):
        """``POST /api/admin/operaciones/<id>/fotos/<kind>/`` — each
        saved item's ``url`` is a relative path. Callsite:
        ``api_views.py:5162``. Response uses the ``saved`` key."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_login(self.admin_principal_user)
        upload = SimpleUploadedFile(
            "foto.webp", b"fake-image-bytes", content_type="image/webp",
        )
        response = self.client.post(
            f"/api/admin/operaciones/{self.operacion_a.pk}/fotos/antes/",
            data={"archivos": [upload]},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertIn("saved", body)
        self.assertTrue(body["saved"], "expected at least one saved photo")
        for photo in body["saved"]:
            self._assert_path(photo["url"], "operaciones/")

    # ---- Test 5: GET /api/tickets/<id>/ (callsite 8) ----

    def test_ticket_message_attachment_returns_relative_path(self):
        """``GET /api/tickets/<id>/`` — each message's ``attachmentUrl``
        is a relative path. Callsite: ``ticket_views.py:171``."""
        self.client.force_login(self.admin_principal_user)
        response = self.client.get(f"/api/tickets/{self.ticket_a.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        matching = [
            m for m in body["messages"]
            if m["id"] == self.ticket_message.id
        ]
        self.assertEqual(len(matching), 1, body)
        self._assert_path(
            matching[0]["attachmentUrl"], "tickets_adjuntos/"
        )

# ---------------------------------------------------------------------------
# Gap 2 — the read APIs expose bucket-relative media paths
# ---------------------------------------------------------------------------


class RelativePathReadApiTests(_SignedUrlEndpointTests):
    """Every media field the read APIs expose must be a bucket-relative
    path, never an absolute URL.

    ``Boto3Storage.url()`` raises by design under
    ``STORAGE_PROVIDER=s3``, so any callsite that still called ``.url()``
    returned HTTP 500 in the cloud deployment. The contract is: the API
    returns the RELATIVE bucket path and the frontend resolves it to a
    presigned URL through the ``useSignedUrl`` hook.

    Each test below pins one callsite shape: the response field MUST be
    a non-empty relative path under the upload prefix, MUST NOT start
    with ``http://``/``https://`` and MUST NOT contain ``/media/``.
    """

    QR_PATH = "pagos_qr/2026/10/qr-prueba.webp"
    GASTO_FACTURA_PATH = "facturas_gastos/2026/10/factura-prueba.pdf"
    FOTO_ANTES_PATH = "citas/2026/10/03/antes/foto-antes.webp"
    FOTO_DESPUES_PATH = "citas/2026/10/03/despues/foto-despues.webp"
    RECIBO_PATH = "comprobantes_pagos/2026/10/recibo-prueba.pdf"

    def _assert_path(self, value, prefix):
        """value MUST be a non-empty relative path starting with prefix."""
        self.assertIsInstance(value, str)
        self.assertTrue(value, f"expected non-empty path, got {value!r}")
        self.assertTrue(
            value.startswith(prefix),
            f"expected path to start with {prefix!r}, got {value!r}",
        )
        self.assertNotIn("/media/", value)
        self.assertFalse(
            value.startswith("http://") or value.startswith("https://"),
        )

    def setUp(self) -> None:
        super().setUp()
        # The branch-scoped admin endpoints resolve the branch from the
        # admin's ``sucursal``; the seeded client user must point at the
        # SAME branch so the payment / quota / cita fixtures are visible.
        self.cliente_a.usuario.sucursal = self.sucursal_a
        self.cliente_a.usuario.save(update_fields=["sucursal"])

        # Branch QR config (``pagos_qr/``).
        self.qr_config = ConfiguracionPagoQR.objects.create(
            sucursal=self.sucursal_a,
            imagen_qr=self.QR_PATH,
        )
        # Branch expense with a supplier invoice (``facturas_gastos/``).
        self.categoria = CategoriaGasto.objects.create(nombre="Insumos")
        self.gasto = GastoSucursal.objects.create(
            sucursal=self.sucursal_a,
            categoria=self.categoria,
            fecha=date(2026, 10, 15),
            concepto="Compra de insumos",
            unidades=Decimal("1"),
            costo_unidad=Decimal("100"),
            gasto_total=Decimal("100"),
            factura=self.GASTO_FACTURA_PATH,
        )
        # Quota + payment with a receipt (``comprobantes_pagos/``).
        self.cuota_a = CuotaPlanPago.objects.create(
            operacion=self.operacion_a,
            nro_cuota=1,
            fecha_vencimiento=date(2026, 10, 15),
            monto_programado=Decimal("50"),
        )
        self.pago_a = PagoRealizado.objects.create(
            cuota=self.cuota_a,
            monto_pagado=Decimal("50"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("50"),
            comprobante_url=self.RECIBO_PATH,
        )
        # Appointment photos (``citas/.../antes/`` and ``.../despues/``).
        self.cita_a = CitaMedica.objects.create(
            operacion=self.operacion_a,
            sucursal=self.sucursal_a,
            fecha_hora=datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc),
            foto_antes=self.FOTO_ANTES_PATH,
            foto_despues=self.FOTO_DESPUES_PATH,
        )

    # ---- GET /api/admin/operaciones/<id>/ ----

    def test_operation_detail_returns_relative_document_and_photo_paths(self):
        """``GET /api/admin/operaciones/<id>/`` — the clinical PDF
        (``documentPdfUrl``) and the appointment photos
        (``citas[].fotoAntesUrl`` / ``fotoDespuesUrl``) are relative
        paths. Callsites: ``api_views.py:439`` and ``api_views.py:653-654``.
        """
        self.client.force_login(self.admin_principal_user)
        response = self.client.get(
            f"/api/admin/operaciones/{self.operacion_a.pk}/"
        )
        self.assertEqual(response.status_code, 200, response.content)
        operation = response.json()["operation"]
        self._assert_path(operation["documentPdfUrl"], "fichas_clinicas/")
        matching = [
            c for c in operation["appointments"]
            if c.get("rawId") == self.cita_a.pk
        ]
        self.assertEqual(len(matching), 1, operation["appointments"])
        self._assert_path(matching[0]["fotoAntesUrl"], "citas/")
        self.assertIn("/antes/", matching[0]["fotoAntesUrl"])
        self._assert_path(matching[0]["fotoDespuesUrl"], "citas/")
        self.assertIn("/despues/", matching[0]["fotoDespuesUrl"])

    # ---- GET /api/admin/gastos/ ----

    def test_admin_gastos_returns_relative_invoice_path(self):
        """``GET /api/admin/gastos/`` — ``expenses[].invoiceUrl`` is a
        relative path under ``facturas_gastos/``. Callsite:
        ``api_views.py:1075``."""
        self.client.force_login(self.admin_sucursal_a_user)
        response = self.client.get(
            "/api/admin/gastos/", {"month": 10, "year": 2026}
        )
        self.assertEqual(response.status_code, 200, response.content)
        matching = [
            e for e in response.json()["expenses"] if e["rawId"] == self.gasto.pk
        ]
        self.assertEqual(len(matching), 1, response.json())
        self._assert_path(matching[0]["invoiceUrl"], "facturas_gastos/")

    # ---- GET /api/admin/reportes/ingresos/ ----

    def test_admin_report_income_returns_relative_invoice_path(self):
        """``GET /api/admin/reportes/ingresos/`` — ``rows[].invoiceUrl``
        is a relative path under ``comprobantes_pagos/``. Callsite:
        ``api_views.py:8304``."""
        self.client.force_login(self.admin_sucursal_a_user)
        response = self.client.get(
            "/api/admin/reportes/ingresos/", {"month": 10, "year": 2026}
        )
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()["rows"]
        matching = [r for r in rows if r["paymentId"] == self.pago_a.pk]
        self.assertEqual(len(matching), 1, rows)
        self._assert_path(matching[0]["invoiceUrl"], "comprobantes_pagos/")

    # ---- GET /api/admin/pagos/ ----

    def test_admin_pagos_returns_relative_qr_path(self):
        """``GET /api/admin/pagos/`` — ``paymentQrConfig.qrImageUrl`` is a
        relative path under ``pagos_qr/``. Callsite:
        ``api/viewsets/payments.py`` (``_payment_qr_config_item``)."""
        self.client.force_login(self.admin_sucursal_a_user)
        response = self.client.get("/api/admin/pagos/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["paymentQrConfig"]["hasQr"])
        self._assert_path(
            body["paymentQrConfig"]["qrImageUrl"], "pagos_qr/"
        )

    # ---- GET /api/admin/pagos/configuracion-qr/ ----

    def test_admin_qr_config_returns_relative_qr_path(self):
        """``GET /api/admin/pagos/configuracion-qr/`` — the branch QR is
        a relative path under ``pagos_qr/``. Callsite:
        ``api/viewsets/payments.py`` (``_payment_qr_config_item``)."""
        self.client.force_login(self.admin_sucursal_a_user)
        response = self.client.get("/api/admin/pagos/configuracion-qr/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["paymentQrConfig"]["hasQr"])
        self._assert_path(
            body["paymentQrConfig"]["qrImageUrl"], "pagos_qr/"
        )

    # ---- GET /api/client/pagos/ ----

    def test_client_pagos_returns_relative_qr_path(self):
        """``GET /api/client/pagos/`` — the client portal QR is a
        relative path under ``pagos_qr/``. Callsite:
        ``client_api_views.py:430``."""
        self.client.force_login(self.cliente_a.usuario)
        response = self.client.get("/api/client/pagos/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["paymentQrConfig"]["hasQr"])
        self._assert_path(
            body["paymentQrConfig"]["qrImageUrl"], "pagos_qr/"
        )

    # ---- GET /api/client/reservas/ ----

    def test_client_reservas_returns_relative_photo_paths(self):
        """``GET /api/client/reservas/`` — the appointment photos are
        relative paths under ``citas/``. Callsites:
        ``client_api_views.py:561-562``."""
        self.client.force_login(self.cliente_a.usuario)
        response = self.client.get("/api/client/reservas/")
        self.assertEqual(response.status_code, 200, response.content)
        matching = [
            a for a in response.json()["appointments"]
            if a.get("rawId") == self.cita_a.pk
        ]
        self.assertEqual(len(matching), 1, response.json())
        self._assert_path(matching[0]["fotoAntesUrl"], "citas/")
        self._assert_path(matching[0]["fotoDespuesUrl"], "citas/")
