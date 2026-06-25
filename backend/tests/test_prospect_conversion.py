from datetime import date
from decimal import Decimal

from django.test import TestCase

from accounts.models import Rol, Usuario
from catalogs.models import ServicioConfig, Sucursal, TipoServicio
from config.prospect_conversion_views import _serialize_medical_config
from customers.models import Cliente, ProspectoConversionBorrador


class ProspectConversionMedicalConfigTests(TestCase):
    """Cover the medical-config serialization paths used by the prospect
    conversion step 3 endpoint.

    The full step-3 round trip is exercised by `_serialize_medical_config`,
    which is the single source of truth for the JSON shape the frontend
    consumes in the conversion flow.
    """

    def setUp(self):
        rol = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Central", activa=True)
        usuario = Usuario.objects.create_user(
            username="admin.conversion",
            password="pass12345",
            rol=rol,
            sucursal=self.sucursal,
            primer_nombre="Ana",
            apellido_paterno="Perez",
        )
        self.cliente = Cliente.objects.create(
            usuario=usuario,
            ci="1234567",
            telefono="70000000",
            fecha_nacimiento=date(1990, 1, 1),
        )

        self.tipo_consulta = TipoServicio.objects.create(tipo="Cita de consulta")
        self.consulta_service = ServicioConfig.objects.create(
            tipo_servicio=self.tipo_consulta,
            proc_estetico=None,
            sector=None,
            precio_base=Decimal("120.00"),
            activo=True,
        )

    def test_cita_medica_returns_empty_sections_in_conversion_step_3(self):
        # Mirror how step 3 of the prospect conversion flow calls the
        # serializer through `_admin_conversion_detail`.
        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            datos_operacion={"serviceConfigId": self.consulta_service.id},
        )

        # The serializer is invoked with the lookup performed in
        # `_admin_conversion_detail` / `_serialize_conversion_payload`.
        service_config = ServicioConfig.objects.filter(
            pk=draft.datos_operacion["serviceConfigId"]
        ).first()

        medical_config = _serialize_medical_config(service_config)

        self.assertEqual(medical_config["sections"], [])
        self.assertIsNone(medical_config["procedureId"])
        self.assertEqual(medical_config["procedureName"], "")
        # Shared clinical catalogs must still be returned so other parts
        # of the form (analisis estetico, antecedentes) keep working.
        self.assertIn("antecedentes", medical_config)
        self.assertIn("implantes", medical_config)
        self.assertIn("cirugias", medical_config)
        self.assertIn("tiposPiel", medical_config)

    def test_no_service_config_returns_empty_sections(self):
        medical_config = _serialize_medical_config(None)

        self.assertEqual(medical_config["sections"], [])
        self.assertIsNone(medical_config["procedureId"])
        self.assertEqual(medical_config["procedureName"], "")
