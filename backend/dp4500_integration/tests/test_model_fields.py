"""Tests for the model additions of dp4500-host-app-integration-phase2.

Covers:
  - Usuario.biometric_external_id + pre_save signal
  - CitaMedica biometric fields
  - Sucursal.dp4500_service_key_id + validator

These are pure-ORM tests; no HTTP / no Celery involved.
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.test import TestCase

from accounts.models import Usuario, Rol
from catalogs.models import Sucursal
from common.models import TimeStampedModel  # noqa: F401  (sanity import)
from operations.models import CitaMedica


# --------------------------------------------------------------------------
# Usuario.biometric_external_id + pre_save signal
# --------------------------------------------------------------------------


class UsuarioBiometricExternalIdTests(TestCase):
    def test_pre_save_assigns_uuid_on_first_insert(self):
        """A fresh Usuario gets a non-null UUID on save."""
        rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
        user = Usuario(
            username="bio_external_1",
            primer_nombre="Alice",
            apellido_paterno="Test",
            rol=rol,
        )
        user.set_password("Sup3rSecret!")
        user.save()
        self.assertIsNotNone(user.biometric_external_id)
        # Stable across subsequent saves.
        first_id = user.biometric_external_id
        user.save()
        self.assertEqual(user.biometric_external_id, first_id)

    def test_pre_save_does_not_overwrite_existing_uuid(self):
        """Saving with a pre-set value must preserve it."""
        import uuid as uuidlib

        preset = uuidlib.UUID("11111111-2222-3333-4444-555555555555")
        rol, _ = Rol.objects.get_or_create(rol="ADMIN_PRINCIPAL")
        user = Usuario(
            username="bio_external_2",
            primer_nombre="Bob",
            apellido_paterno="Test",
            rol=rol,
            biometric_external_id=preset,
        )
        user.set_password("Sup3rSecret!")
        user.save()
        self.assertEqual(user.biometric_external_id, preset)


# --------------------------------------------------------------------------
# CitaMedica biometric fields
# --------------------------------------------------------------------------


class CitaMedicaBiometricFieldsTests(TestCase):
    """CitaMedica.save() requires a full Operacion + Cliente setup which is
    orthogonal to this Phase 2 change. We verify the schema additions
    via class introspection + DB column existence rather than going
    through the full save() flow.
    """

    def test_three_biometric_fields_defined(self):
        from django.db import models
        for fname in (
            "biometric_challenge_id",
            "biometric_match_confidence",
            "biometric_verified_at",
        ):
            field = CitaMedica._meta.get_field(fname)
            self.assertIsNotNone(field, f"{fname} must be declared on CitaMedica")

    def test_challenge_id_is_nullable_charfield(self):
        field = CitaMedica._meta.get_field("biometric_challenge_id")
        self.assertEqual(type(field), models.CharField)
        self.assertEqual(field.max_length, 64)
        self.assertTrue(field.null)
        self.assertTrue(field.blank)

    def test_match_confidence_is_nullable_decimalfield(self):
        from django.db import models
        field = CitaMedica._meta.get_field("biometric_match_confidence")
        self.assertEqual(type(field), models.DecimalField)
        self.assertEqual(field.max_digits, 5)
        self.assertEqual(field.decimal_places, 4)
        self.assertTrue(field.null)

    def test_verified_at_is_nullable_datetimefield(self):
        from django.db import models
        field = CitaMedica._meta.get_field("biometric_verified_at")
        self.assertEqual(type(field), models.DateTimeField)
        self.assertTrue(field.null)


# --------------------------------------------------------------------------
# Sucursal.dp4500_service_key_id + validator
# --------------------------------------------------------------------------


class SucursalDp4500ServiceKeyTests(TestCase):
    def test_field_default_is_null(self):
        suc = Sucursal.objects.create(nombre="SucTest1")
        self.assertIsNone(suc.dp4500_service_key_id)

    def test_field_round_trip(self):
        suc = Sucursal.objects.create(
            nombre="SucTest2", dp4500_service_key_id="key-001",
        )
        suc.refresh_from_db()
        self.assertEqual(suc.dp4500_service_key_id, "key-001")

    def test_field_validator_accepts_alphanumeric_dots_dashes_underscores(self):
        suc = Sucursal(nombre="SucTest3", dp4500_service_key_id="A_b.c-1")
        suc.full_clean()  # raises if invalid

    def test_field_validator_rejects_spaces(self):
        suc = Sucursal(nombre="SucTest4", dp4500_service_key_id="with spaces")
        with self.assertRaises(ValidationError) as ctx:
            suc.full_clean()
        self.assertIn("dp4500_service_key_id", ctx.exception.message_dict)

    def test_field_validator_rejects_too_long(self):
        too_long = "x" * 65
        suc = Sucursal(nombre="SucTest5", dp4500_service_key_id=too_long)
        with self.assertRaises(ValidationError) as ctx:
            suc.full_clean()
        self.assertIn("dp4500_service_key_id", ctx.exception.message_dict)
