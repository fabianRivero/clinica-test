"""Tests for the operation observations + photo gallery feature.

Adds three admin endpoints under ``/api/admin/operaciones/<id>/``:

* ``actualizar-observaciones/`` (POST JSON) — single-field save of
  ``Operacion.detalles_op`` (does NOT touch ``recomendaciones`` or
  ``sesiones_totales``).
* ``fotos/<kind>/`` (POST multipart) — multi-file upload of
  ``OperacionFoto`` rows with 5 MB per-file cap and partial-success
  semantics.
* ``fotos/<photo_id>/`` (DELETE) — removes one photo (and its file
  from disk), 404 on cross-operation.

The ``_operation_detail`` payload now embeds ``fotosAntes`` /
``fotosDespues`` ordered by ``uploaded_at ASC, id ASC``.
"""

import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from customers.models import Cliente
from operations.models import Operacion, OperacionFoto


def _make_fixtures(cls):
    """Build an admin user + a cliente + an EN_PROCESO operacion.

    Called from ``setUpTestData`` on each test class so the fixtures are
    created once per class (Django rolls back inside the test anyway).
    """
    cls.TZ = ZoneInfo("America/La_Paz")

    cls.rol_admin = Rol.objects.create(rol="ADMIN_PRINCIPAL")
    cls.rol_cliente = Rol.objects.create(rol="CLIENTE")

    cls.sucursal = Sucursal.objects.create(nombre="Centro", activa=True)

    cls.admin = Usuario.objects.create_user(
        username="admin",
        password="password123",
        primer_nombre="A",
        apellido_paterno="Admin",
        rol=cls.rol_admin,
        sucursal=cls.sucursal,
    )
    cls.cliente_user = Usuario.objects.create_user(
        username="cli",
        password="password123",
        primer_nombre="M",
        apellido_paterno="G",
        rol=cls.rol_cliente,
    )
    cls.cliente = Cliente.objects.create(
        usuario=cls.cliente_user,
        ci="1",
        telefono="1",
        fecha_nacimiento=date(1990, 1, 1),
    )
    tipo = TipoServicio.objects.create(tipo="T")
    servicio = ServicioConfig.objects.create(
        tipo_servicio=tipo, precio_base=100
    )
    cls.operacion = Operacion.objects.create(
        paciente=cls.cliente,
        servicio_config=servicio,
        sesiones_totales=4,
        precio_total=400,
        estado=Operacion.Estado.EN_PROCESO,
        detalles_op="detalles iniciales",
        recomendaciones="recom iniciales",
    )


def _tiny_png_bytes():
    """Return the smallest valid 1x1 PNG as raw bytes."""
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
        b"\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfeA"
        b"\xb6\xfa\x92\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _png_upload(name="foto.png", size_increase_bytes=0):
    """Build a SimpleUploadedFile with a valid PNG header and an optional
    filler so the size can exceed 5 MB for the cap tests."""
    return SimpleUploadedFile(
        name,
        _tiny_png_bytes() + b"x" * size_increase_bytes,
        content_type="image/png",
    )


class UpdateObservacionesTests(TestCase):
    """POST /api/admin/operaciones/<id>/actualizar-observaciones/"""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        self.url = f"/api/admin/operaciones/{self.operacion.pk}/actualizar-observaciones/"

    def _post(self, payload):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_happy_path_persists_detalles_op(self):
        """POST {details: 'nuevo'} persists detalles_op only."""
        self.client.force_login(self.admin)
        response = self._post({"details": "nuevo"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("operation", body)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.detalles_op, "nuevo")

    def test_does_not_clobber_recomendaciones(self):
        """Guardar observaciones no debe tocar ``recomendaciones``."""
        original = self.operacion.recomendaciones
        self.client.force_login(self.admin)
        self._post({"details": "actualizado"})
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.recomendaciones, original)

    def test_does_not_clobber_sesiones_totales(self):
        """Guardar observaciones no debe tocar ``sesiones_totales``."""
        original = self.operacion.sesiones_totales
        self.client.force_login(self.admin)
        self._post({"details": "actualizado"})
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.sesiones_totales, original)

    def test_strips_whitespace(self):
        """`"  nuevo  "` → detalles_op == `"nuevo"`."""
        self.client.force_login(self.admin)
        response = self._post({"details": "  nuevo  "})
        self.assertEqual(response.status_code, 200, response.content)
        self.operacion.refresh_from_db()
        self.assertEqual(self.operacion.detalles_op, "nuevo")

    def test_missing_details_returns_400(self):
        """POST {} → 400 + errors.details."""
        self.client.force_login(self.admin)
        response = self._post({})
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertIn("details", body.get("errors", {}))

    def test_invalid_json_returns_400(self):
        """POST no-JSON → 400 with detail mentioning JSON."""
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("JSON", response.json()["detail"])

    def test_missing_operacion_returns_404(self):
        self.client.force_login(self.admin)
        response = self._post.__self__.client.post(
            "/api/admin/operaciones/9999/actualizar-observaciones/",
            data=json.dumps({"details": "x"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404, response.content)

    def test_anonymous_returns_401(self):
        response = self._post({"details": "nuevo"})
        self.assertEqual(response.status_code, 401, response.content)

    def test_non_admin_returns_403(self):
        """A logged-in cliente cannot update observaciones."""
        cliente_user = Usuario.objects.create_user(
            username="cli2",
            password="password123",
            primer_nombre="C",
            apellido_paterno="L",
            rol=self.rol_cliente,
        )
        self.client.force_login(cliente_user)
        response = self._post({"details": "nuevo"})
        self.assertEqual(response.status_code, 403, response.content)


class UploadPhotosTests(TestCase):
    """POST /api/admin/operaciones/<id>/fotos/<kind>/"""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        self.url_antes = (
            f"/api/admin/operaciones/{self.operacion.pk}/fotos/antes/"
        )
        self.url_despues = (
            f"/api/admin/operaciones/{self.operacion.pk}/fotos/despues/"
        )

    def test_single_upload_persists_row_and_returns_201(self):
        self.client.force_login(self.admin)
        upload = _png_upload("antes-1.png")
        response = self.client.post(
            self.url_antes,
            data={"archivos": upload},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["saved"]), 1)
        self.assertEqual(OperacionFoto.objects.count(), 1)
        foto = OperacionFoto.objects.first()
        self.assertEqual(foto.kind, "antes")
        self.assertEqual(foto.operacion_id, self.operacion.pk)
        self.assertEqual(body["saved"][0]["fileName"], "antes-1.png")
        # The url MUST be absolute (because ``request`` is threaded in).
        self.assertTrue(body["saved"][0]["url"].startswith("http"))
        # The embedded operation payload carries the new photo.
        self.assertEqual(len(body["operation"]["fotosAntes"]), 1)
        self.assertTrue(body["operation"]["fotosAntes"][0]["url"].startswith("http"))

    def test_multi_upload_persists_all(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url_antes,
            data={"archivos": [_png_upload("a.png"), _png_upload("b.png"), _png_upload("c.png")]},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["saved"]), 3)
        self.assertEqual(OperacionFoto.objects.count(), 3)
        self.assertEqual(
            list(OperacionFoto.objects.values_list("kind", flat=True)),
            ["antes", "antes", "antes"],
        )

    def test_partial_success_one_oversized(self):
        """One file > 5 MB → 201 with saved.length == 2 and the oversized
        file's index reported under ``errors``."""
        self.client.force_login(self.admin)
        oversized = _png_upload("big.png", size_increase_bytes=5 * 1024 * 1024 + 1)
        response = self.client.post(
            self.url_antes,
            data={
                "archivos": [
                    _png_upload("a.png"),
                    oversized,
                    _png_upload("c.png"),
                ]
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["saved"]), 2)
        self.assertEqual(OperacionFoto.objects.count(), 2)
        self.assertIn("archivos[1]", body["errors"])

    def test_all_oversized_returns_400(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url_antes,
            data={
                "archivos": [
                    _png_upload("a.png", size_increase_bytes=5 * 1024 * 1024 + 1),
                    _png_upload("b.png", size_increase_bytes=5 * 1024 * 1024 + 1),
                ]
            },
        )
        self.assertEqual(response.status_code, 400, response.content)
        body = response.json()
        self.assertEqual(OperacionFoto.objects.count(), 0)
        self.assertIn("archivos[0]", body["errors"])
        self.assertIn("archivos[1]", body["errors"])

    def test_missing_archivos_returns_400(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url_antes, data={})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("archivos", response.json().get("errors", {}))

    def test_invalid_kind_returns_400(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            f"/api/admin/operaciones/{self.operacion.pk}/fotos/laterales/",
            data={"archivos": [_png_upload("a.png")]},
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("kind", response.json().get("errors", {}))

    def test_kind_despues_stored_separately(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url_despues,
            data={"archivos": [_png_upload("d.png")]},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(
            OperacionFoto.objects.filter(kind="despues").count(), 1
        )
        self.assertEqual(
            OperacionFoto.objects.filter(kind="antes").count(), 0
        )

    def test_detail_payload_after_upload_includes_new_photo(self):
        """The response ``operation.fotosAntes`` MUST contain the new
        photo AND its ``url`` MUST be an absolute URL."""
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url_antes,
            data={"archivos": [_png_upload("a.png")]},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(len(body["operation"]["fotosAntes"]), 1)
        self.assertTrue(body["operation"]["fotosAntes"][0]["url"].startswith("http"))

    def test_operacion_not_found_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            "/api/admin/operaciones/9999/fotos/antes/",
            data={"archivos": [_png_upload("a.png")]},
        )
        self.assertEqual(response.status_code, 404, response.content)


class DeletePhotoTests(TestCase):
    """DELETE /api/admin/operaciones/<operacion_id>/fotos/<photo_id>/"""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        self.foto = OperacionFoto.objects.create(
            operacion=self.operacion,
            kind=OperacionFoto.Kind.ANTES,
            imagen=_png_upload("to-delete.png"),
        )
        self.url = (
            f"/api/admin/operaciones/{self.operacion.pk}"
            f"/fotos/{self.foto.pk}/"
        )

    def test_delete_existing_returns_204_and_frees_disk(self):
        path_before = self.foto.imagen.path
        self.assertTrue(os.path.exists(path_before))
        self.client.force_login(self.admin)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(OperacionFoto.objects.count(), 0)
        self.assertFalse(os.path.exists(path_before))

    def test_cross_operation_delete_returns_404(self):
        """DELETE on operacion A for a photo that belongs to operacion B
        returns 404 AND leaves the photo intact."""
        tipo = TipoServicio.objects.create(tipo="T2")
        servicio = ServicioConfig.objects.create(tipo_servicio=tipo, precio_base=100)
        other_op = Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=servicio,
            sesiones_totales=1,
            precio_total=100,
            estado=Operacion.Estado.EN_PROCESO,
        )
        url_wrong = (
            f"/api/admin/operaciones/{other_op.pk}/fotos/{self.foto.pk}/"
        )
        self.client.force_login(self.admin)
        response = self.client.delete(url_wrong)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertTrue(OperacionFoto.objects.filter(pk=self.foto.pk).exists())

    def test_delete_missing_photo_returns_404(self):
        self.client.force_login(self.admin)
        response = self.client.delete(
            f"/api/admin/operaciones/{self.operacion.pk}/fotos/99999/"
        )
        self.assertEqual(response.status_code, 404, response.content)


class OperationDetailGalleryTests(TestCase):
    """GET /api/admin/operaciones/<id>/ embeds the gallery in ``fotosAntes``
    and ``fotosDespues``."""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def setUp(self):
        self.url = f"/api/admin/operaciones/{self.operacion.pk}/"

    def test_detail_payload_includes_fotos_antes_ordered_by_upload_time(self):
        OperacionFoto.objects.create(
            operacion=self.operacion,
            kind="antes",
            imagen=_png_upload("a.png"),
        )
        OperacionFoto.objects.create(
            operacion=self.operacion,
            kind="antes",
            imagen=_png_upload("b.png"),
        )
        OperacionFoto.objects.create(
            operacion=self.operacion,
            kind="antes",
            imagen=_png_upload("c.png"),
        )
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        antes = body["operation"]["fotosAntes"]
        self.assertEqual(len(antes), 3)
        # Order: uploaded_at ASC, id ASC tiebreak. fileNames confirm.
        self.assertEqual([p["fileName"] for p in antes], ["a.png", "b.png", "c.png"])
        # URLs are absolute because ``request`` is threaded into _operation_detail.
        for entry in antes:
            self.assertTrue(entry["url"].startswith("http"))

    def test_detail_payload_includes_fotos_despues(self):
        OperacionFoto.objects.create(
            operacion=self.operacion,
            kind="despues",
            imagen=_png_upload("d1.png"),
        )
        OperacionFoto.objects.create(
            operacion=self.operacion,
            kind="despues",
            imagen=_png_upload("d2.png"),
        )
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        body = response.json()
        self.assertEqual(len(body["operation"]["fotosDespues"]), 2)

    def test_empty_gallery_returns_empty_arrays(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["operation"]["fotosAntes"], [])
        self.assertEqual(body["operation"]["fotosDespues"], [])

    def test_gallery_is_single_query_no_n_plus_1(self):
        """With the new prefetch, fetching a payload with N photos
        MUST NOT trigger N+1 queries for ``fotos_operacion``. The number
        of queries when N=0 and N=6 must be identical (the prefetch is
        a single query; iterating over the cached queryset in Python is
        free)."""
        from django.db import reset_queries
        from django.test.utils import CaptureQueriesContext

        baseline_count = self._count_queries(n_photos=0)
        flat_count = self._count_queries(n_photos=6)
        self.assertEqual(
            baseline_count,
            flat_count,
            f"Gallery queries grew with N: baseline={baseline_count}, n=6={flat_count}.",
        )

    def _count_queries(self, n_photos):
        from django.db import reset_queries
        from django.test.utils import CaptureQueriesContext

        # Reset all photos, then add n_photos fresh ones.
        OperacionFoto.objects.filter(operacion=self.operacion).delete()
        for index in range(n_photos):
            OperacionFoto.objects.create(
                operacion=self.operacion,
                kind="antes",
                imagen=_png_upload(f"a{index}.png"),
            )
        # The test runner sets DEBUG=True, so reset_queries + capturing works.
        self.client.force_login(self.admin)
        reset_queries()
        with CaptureQueriesContext(connection):
            self.client.get(self.url)
        return len(connection.queries)


class LifecycleTests(TestCase):
    """Lifecycle gating is FE-only per the spec (lines 124-144): the
    backend accepts mutations regardless of ``estado``. The frontend
    ``editable`` prop drives visibility, and ``canEditObservations`` is
    derived from ``[borrador, en proceso]``. The tests below assert the
    server-side behavior: ALL four estados accept the writes."""

    @classmethod
    def setUpTestData(cls):
        _make_fixtures(cls)

    def _set_estado(self, estado):
        self.operacion.estado = estado
        self.operacion.save()

    def _post_observaciones(self):
        self.client.force_login(self.admin)
        return self.client.post(
            f"/api/admin/operaciones/{self.operacion.pk}/actualizar-observaciones/",
            data=json.dumps({"details": "ok"}),
            content_type="application/json",
        )

    def _post_foto(self):
        self.client.force_login(self.admin)
        return self.client.post(
            f"/api/admin/operaciones/{self.operacion.pk}/fotos/antes/",
            data={"archivos": [_png_upload("a.png")]},
        )

    def test_borrador_is_editable(self):
        self._set_estado(Operacion.Estado.BORRADOR)
        self.assertEqual(self._post_observaciones().status_code, 200)
        self.assertEqual(self._post_foto().status_code, 201)

    def test_en_proceso_is_editable(self):
        self._set_estado(Operacion.Estado.EN_PROCESO)
        self.assertEqual(self._post_observaciones().status_code, 200)
        self.assertEqual(self._post_foto().status_code, 201)

    def test_finalizada_is_read_only(self):
        """FE-only gating: server still accepts the write."""
        self._set_estado(Operacion.Estado.FINALIZADA)
        self.assertEqual(self._post_observaciones().status_code, 200)
        self.assertEqual(self._post_foto().status_code, 201)

    def test_cancelada_is_read_only(self):
        """FE-only gating: server still accepts the write."""
        self._set_estado(Operacion.Estado.CANCELADA)
        self.assertEqual(self._post_observaciones().status_code, 200)
        self.assertEqual(self._post_foto().status_code, 201)
