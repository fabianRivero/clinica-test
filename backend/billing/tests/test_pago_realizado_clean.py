"""Tests for ``PagoRealizado.clean()`` and the metodo_pago / breakdown validation.

Each test exercises a single rule from the ``PagoRealizado.clean()`` spec:

* ``VIRTUAL``: receipt required, ``monto_virtual == monto_pagado``, ``monto_fisico == 0``.
* ``FISICO``: receipt optional, ``monto_fisico == monto_pagado``, ``monto_virtual == 0``.
* ``MIXTO``: receipt optional, both breakdown amounts strictly > 0 and sum to ``monto_pagado``.

The tests skip ``save()`` and call ``clean()`` directly so they can assert on the
``ValidationError`` raised by the model without having to materialize a full
``cuota.operacion`` graph. Tests that need to verify the over-payment guard (a
view-layer concern, not the model) live elsewhere.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from billing.models import PagoRealizado


class PagoRealizadoCleanTests(TestCase):
    """Unit tests for ``PagoRealizado.clean()`` method-validation rules."""

    @staticmethod
    def _receipt():
        return SimpleUploadedFile(
            "receipt.pdf", b"%PDF-test", content_type="application/pdf"
        )

    # -------------------------------------------------------------------------
    # VIRTUAL branch
    # -------------------------------------------------------------------------

    def test_clean_virtual_requires_receipt(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
            comprobante_url="",
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("comprobante_url", ctx.exception.message_dict)

    def test_clean_virtual_requires_amount_match(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("80.00"),
            monto_fisico=Decimal("0"),
            comprobante_url=self._receipt(),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_virtual", ctx.exception.message_dict)

    def test_clean_virtual_rejects_nonzero_fisico(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("5.00"),
            comprobante_url=self._receipt(),
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_fisico", ctx.exception.message_dict)

    def test_clean_virtual_with_receipt_and_balanced_amounts_passes(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.VIRTUAL,
            monto_virtual=Decimal("100.00"),
            monto_fisico=Decimal("0"),
            comprobante_url=self._receipt(),
        )
        payment.clean()  # should not raise

    # -------------------------------------------------------------------------
    # FISICO branch
    # -------------------------------------------------------------------------

    def test_clean_fisico_receipt_is_optional(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            comprobante_url="",
        )
        payment.clean()  # should not raise

    def test_clean_fisico_requires_amount_match(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.FISICO,
            monto_fisico=Decimal("80.00"),
            monto_virtual=Decimal("0"),
            comprobante_url="",
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_fisico", ctx.exception.message_dict)

    def test_clean_fisico_rejects_nonzero_virtual(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.FISICO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("5.00"),
            comprobante_url="",
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_virtual", ctx.exception.message_dict)

    # -------------------------------------------------------------------------
    # MIXTO branch
    # -------------------------------------------------------------------------

    def test_clean_mixto_requires_both_positive(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.MIXTO,
            monto_fisico=Decimal("100.00"),
            monto_virtual=Decimal("0"),
            comprobante_url="",
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_pagado", ctx.exception.message_dict)

    def test_clean_mixto_requires_sum_match(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.MIXTO,
            monto_fisico=Decimal("40.00"),
            monto_virtual=Decimal("50.00"),
            comprobante_url="",
        )
        with self.assertRaises(ValidationError) as ctx:
            payment.clean()
        self.assertIn("monto_pagado", ctx.exception.message_dict)

    def test_clean_mixto_with_valid_breakdown_passes(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            metodo_pago=PagoRealizado.MetodoPago.MIXTO,
            monto_fisico=Decimal("40.00"),
            monto_virtual=Decimal("60.00"),
            comprobante_url="",
        )
        payment.clean()  # should not raise

    # -------------------------------------------------------------------------
    # Default behaviour preserved (back-compat for VIRTUAL default)
    # -------------------------------------------------------------------------

    def test_default_metodo_pago_is_virtual(self):
        payment = PagoRealizado(
            monto_pagado=Decimal("100.00"),
            comprobante_url=self._receipt(),
        )
        # No metodo_pago set → defaults to VIRTUAL.
        self.assertEqual(payment.metodo_pago, PagoRealizado.MetodoPago.VIRTUAL)
        # With the VIRTUAL default, monto_virtual must match monto_pagado to
        # pass clean(). Defaulting both to 0 means callers must set the
        # breakdown explicitly — see the 7 factory call patches.
        with self.assertRaises(ValidationError):
            payment.clean()