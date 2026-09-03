"""Tests for ``PagoRealizadoCreateSerializer``.

The serializer is a write-only shape validator shared by the admin
endpoint (PR 2) and the client upload path (also PR 2). It catches the
common errors before they reach the model ``clean()``:

* ``VIRTUAL`` requires a receipt file.
* ``VIRTUAL`` and ``FISICO`` derive the breakdown from ``monto_pagado``.
* ``MIXTO`` requires both breakdown amounts strictly > 0 and equal to
  ``monto_pagado`` when summed.
* ``monto_pagado`` itself must be positive.

The serializer is intentionally NOT a ModelSerializer — see its
docstring. The tests therefore feed plain dicts to ``.validate({...})``
and assert on the returned dict or on the raised ``ValidationError``.
"""

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from billing.models import PagoRealizado
from config.api.serializers.payments import PagoRealizadoCreateSerializer


class PagoRealizadoCreateSerializerTests(TestCase):
    """Unit tests for ``PagoRealizadoCreateSerializer.validate``."""

    @staticmethod
    def _receipt():
        return SimpleUploadedFile(
            "receipt.pdf", b"%PDF-test", content_type="application/pdf"
        )

    # -------------------------------------------------------------------------
    # Happy paths
    # -------------------------------------------------------------------------

    def test_virtual_derives_breakdown_from_monto_pagado(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.VIRTUAL,
            "monto_pagado": Decimal("100.00"),
            "receiptFile": self._receipt(),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        attrs = serializer.validated_data
        self.assertEqual(attrs["montoVirtual"], Decimal("100.00"))
        self.assertEqual(attrs["montoFisico"], Decimal("0"))

    def test_fisico_derives_breakdown_from_monto_pagado(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.FISICO,
            "monto_pagado": Decimal("120.00"),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        attrs = serializer.validated_data
        self.assertEqual(attrs["montoFisico"], Decimal("120.00"))
        self.assertEqual(attrs["montoVirtual"], Decimal("0"))

    def test_mixto_passes_when_breakdown_matches_total(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.MIXTO,
            "monto_pagado": Decimal("100.00"),
            "montoFisico": Decimal("40.00"),
            "montoVirtual": Decimal("60.00"),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        attrs = serializer.validated_data
        self.assertEqual(attrs["montoFisico"], Decimal("40.00"))
        self.assertEqual(attrs["montoVirtual"], Decimal("60.00"))

    # -------------------------------------------------------------------------
    # Error paths
    # -------------------------------------------------------------------------

    def test_virtual_without_receipt_fails(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.VIRTUAL,
            "monto_pagado": Decimal("100.00"),
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("receiptFile", serializer.errors)

    def test_mixto_with_zero_amount_fails(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.MIXTO,
            "monto_pagado": Decimal("100.00"),
            "montoFisico": Decimal("100.00"),
            "montoVirtual": Decimal("0"),
        })
        self.assertFalse(serializer.is_valid())
        # ValidationError raised as a non-field error; DRF maps it onto
        # the "non_field_errors" key.
        self.assertTrue(serializer.errors)

    def test_mixto_with_mismatched_breakdown_fails(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.MIXTO,
            "monto_pagado": Decimal("100.00"),
            "montoFisico": Decimal("40.00"),
            "montoVirtual": Decimal("50.00"),
        })
        self.assertFalse(serializer.is_valid())
        self.assertTrue(serializer.errors)

    def test_invalid_payment_method_fails(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": "INVALID",
            "monto_pagado": Decimal("100.00"),
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("paymentMethod", serializer.errors)

    def test_zero_monto_pagado_fails(self):
        serializer = PagoRealizadoCreateSerializer(data={
            "paymentMethod": PagoRealizado.MetodoPago.VIRTUAL,
            "monto_pagado": Decimal("0"),
            "receiptFile": self._receipt(),
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("monto_pagado", serializer.errors)