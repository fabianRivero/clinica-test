from decimal import Decimal

from django.test import TestCase

from accounts.models import Usuario, Rol
from catalogs.models import (
    AntecedenteMedico,
    CirugiaEstetica,
    ImplanteInjerto,
    ProcEstetico,
    ServicioConfig,
    Sucursal,
    TipoServicio,
)
from config.prospect_conversion_views import (
    _blank_medical_data,
    _build_initial_client_medical_data,
    _serialize_draft,
)
from customers.models import Cliente, ProspectoConversionBorrador
from operations.models import Operacion
from clinical.models import (
    FichaAntecedenteMedico,
    FichaCirugiaEstetica,
    FichaClinica,
    FichaImplanteInjerto,
)


class MedicalPrefillTests(TestCase):
    def setUp(self):
        rol = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.sucursal = Sucursal.objects.create(nombre="Central", activa=True)
        usuario = Usuario.objects.create_user(
            username="client.prefill",
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
        )

        self.proc = ProcEstetico.objects.create(proceso="Depilacion", activa=True)
        tipo_servicio = TipoServicio.objects.create(tipo="Tratamiento", activa=True)
        self.servicio = ServicioConfig.objects.create(
            tipo_servicio=tipo_servicio,
            proc_estetico=self.proc,
            precio_base=Decimal("100.00"),
            activa=True,
        )

        self.antecedente = AntecedenteMedico.objects.create(nombre="Diabetes", activa=True)
        self.implante = ImplanteInjerto.objects.create(nombre="Protesis", activa=True)
        self.cirugia = CirugiaEstetica.objects.create(nombre="Rinoplastia", activa=True)

    def _create_operacion(self, estado):
        return Operacion.objects.create(
            paciente=self.cliente,
            servicio_config=self.servicio,
            precio_total=Decimal("250.00"),
            cuotas_totales=1,
            sesiones_totales=1,
            estado=estado,
        )

    def test_uses_latest_operation_with_ficha_when_newest_lacks_ficha(self):
        op_with_ficha = self._create_operacion(Operacion.Estado.FINALIZADA)
        ficha = FichaClinica.objects.create(operacion=op_with_ficha)
        FichaAntecedenteMedico.objects.create(
            ficha=ficha,
            antecedente=self.antecedente,
            tipo_antecedente=FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            detalle="Controlado",
        )
        FichaImplanteInjerto.objects.create(
            ficha=ficha,
            implante=self.implante,
            detalle="Brazo derecho",
        )
        FichaCirugiaEstetica.objects.create(
            ficha=ficha,
            cirugia=self.cirugia,
            hace_cuanto_tiempo="2 años",
            detalle="Sin complicaciones",
        )

        self._create_operacion(Operacion.Estado.EN_PROCESO)

        data = _build_initial_client_medical_data(self.cliente)

        self.assertEqual(len(data["antecedentes"]), 1)
        self.assertEqual(data["antecedentes"][0]["antecedenteId"], self.antecedente.id)
        self.assertEqual(data["antecedentes"][0]["tipoAntecedente"], "PERSONAL")
        self.assertEqual(data["antecedentes"][0]["detalle"], "Controlado")

        self.assertEqual(len(data["implantes"]), 1)
        self.assertEqual(data["implantes"][0]["implanteId"], self.implante.id)
        self.assertEqual(data["implantes"][0]["detalle"], "Brazo derecho")

        self.assertEqual(len(data["cirugias"]), 1)
        self.assertEqual(data["cirugias"][0]["cirugiaId"], self.cirugia.id)
        self.assertEqual(data["cirugias"][0]["haceCuantoTiempo"], "2 años")
        self.assertEqual(data["cirugias"][0]["detalle"], "Sin complicaciones")

    def test_uses_operation_in_process_with_ficha(self):
        op = self._create_operacion(Operacion.Estado.EN_PROCESO)
        ficha = FichaClinica.objects.create(operacion=op)
        FichaImplanteInjerto.objects.create(
            ficha=ficha,
            implante=self.implante,
            detalle="Reciente",
        )

        data = _build_initial_client_medical_data(self.cliente)

        self.assertEqual(len(data["implantes"]), 1)
        self.assertEqual(data["implantes"][0]["implanteId"], self.implante.id)

    def test_returns_blank_lists_when_no_previous_ficha(self):
        self._create_operacion(Operacion.Estado.EN_PROCESO)

        data = _build_initial_client_medical_data(self.cliente)

        self.assertEqual(data["antecedentes"], [])
        self.assertEqual(data["implantes"], [])
        self.assertEqual(data["cirugias"], [])

    def test_serialize_draft_prefills_when_datos_ficha_is_blank_structure(self):
        op = self._create_operacion(Operacion.Estado.FINALIZADA)
        ficha = FichaClinica.objects.create(operacion=op)
        FichaAntecedenteMedico.objects.create(
            ficha=ficha,
            antecedente=self.antecedente,
            tipo_antecedente=FichaAntecedenteMedico.TipoAntecedente.FAMILIAR,
            detalle="Padre",
        )

        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            datos_ficha=_blank_medical_data(),
        )

        payload = _serialize_draft(draft)
        self.assertEqual(len(payload["medicalData"]["antecedentes"]), 1)
        self.assertEqual(payload["medicalData"]["antecedentes"][0]["antecedenteId"], self.antecedente.id)

    def test_serialize_draft_blank_keys_do_not_override_historical_prefill(self):
        op = self._create_operacion(Operacion.Estado.FINALIZADA)
        ficha = FichaClinica.objects.create(operacion=op)
        FichaAntecedenteMedico.objects.create(
            ficha=ficha,
            antecedente=self.antecedente,
            tipo_antecedente=FichaAntecedenteMedico.TipoAntecedente.PERSONAL,
            detalle="Historico",
        )
        FichaImplanteInjerto.objects.create(ficha=ficha, implante=self.implante, detalle="Historico")
        FichaCirugiaEstetica.objects.create(
            ficha=ficha,
            cirugia=self.cirugia,
            hace_cuanto_tiempo="1 año",
            detalle="Historico",
        )

        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            datos_ficha={
                **_blank_medical_data(),
                "antecedentes": [],
                "implantes": [],
                "cirugias": [],
            },
        )

        payload = _serialize_draft(draft)
        self.assertEqual(len(payload["medicalData"]["antecedentes"]), 1)
        self.assertEqual(len(payload["medicalData"]["implantes"]), 1)
        self.assertEqual(len(payload["medicalData"]["cirugias"]), 1)

    def test_serialize_draft_keeps_existing_datos_ficha_content(self):
        draft = ProspectoConversionBorrador.objects.create(
            cliente=self.cliente,
            datos_ficha={
                **_blank_medical_data(),
                "antecedentes": [
                    {
                        "id": "manual",
                        "antecedenteId": self.antecedente.id,
                        "tipoAntecedente": "PERSONAL",
                        "detalle": "Manual",
                    }
                ],
            },
        )

        payload = _serialize_draft(draft)
        self.assertEqual(len(payload["medicalData"]["antecedentes"]), 1)
        self.assertEqual(payload["medicalData"]["antecedentes"][0]["detalle"], "Manual")
