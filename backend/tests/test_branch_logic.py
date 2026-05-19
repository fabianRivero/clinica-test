from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import Usuario, Rol
from catalogs.models import Sucursal, ServicioConfig, ProcEstetico, TipoServicio
from customers.models import Prospecto, Cliente
import json

class BranchIsolationTest(TestCase):
    def setUp(self):
        # 1. Crear Roles y Sucursales
        self.rol_admin_gral = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_admin_suc = Rol.objects.create(rol="ADMIN_SUCURSAL")
        
        self.sucursal_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.sucursal_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        # 2. Crear Usuarios Administradores
        self.admin_gral = Usuario.objects.create_user(
            username="admin.gral", password="password123", 
            rol=self.rol_admin_gral, sucursal=self.sucursal_norte,
            primer_nombre="Admin", apellido_paterno="Gral"
        )
        
        self.admin_sucursal = Usuario.objects.create_user(
            username="admin.sucursal", password="password123", 
            rol=self.rol_admin_suc, sucursal=self.sucursal_sur,
            primer_nombre="Admin", apellido_paterno="Sur"
        )

        # 3. Configurar Clientes de API
        self.client_gral = Client()
        self.client_gral.login(username="admin.gral", password="password123")
        
        self.client_suc = Client()
        self.client_suc.login(username="admin.sucursal", password="password123")

    def test_branch_admin_isolation_prospects(self):
        """Un admin de sucursal solo debe ver prospectos de su sucursal."""
        # Crear un prospecto en Norte y otro en Sur
        Prospecto.objects.create(primer_nombre="P.", segundo_nombre="Norte", apellido_paterno="Test", sucursal_registro=self.sucursal_norte)
        Prospecto.objects.create(primer_nombre="P.", segundo_nombre="Sur", apellido_paterno="Test", sucursal_registro=self.sucursal_sur)

        # El admin de sucursal (Sur) pide la lista
        response = self.client_suc.get('/api/admin/prospectos/')
        data = response.json()
        
        # Debe ver solo 1 prospecto (el de Sur)
        self.assertEqual(len(data['prospects']), 1)
        self.assertEqual(data['prospects'][0]['segundoNombre'], "P. Sur")

    def test_mandatory_fields_step_2(self):
        """Validar que el Paso 2 falle si faltan campos obligatorios."""
        prospecto = Prospecto.objects.create(primer_nombre="Test", apellido_paterno="Validacion", sucursal_registro=self.sucursal_sur)
        
        # Intentar guardar operacion sin zona_general (Paso 2)
        payload = {
            "serviceConfigId": 1,
            "precioTotal": "850.00",
            "zonaGeneral": "", # VACIO
            "zonaEspecifica": "Piernas"
        }
        
        response = self.client_suc.post(
            f'/api/admin/prospectos/{prospecto.id}/convertir/operacion/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        
        # Debe devolver 400 Bad Request
        self.assertEqual(response.status_code, 400)
        self.assertIn("zonaGeneral", response.json().get('fieldErrors', {}))

    def test_main_admin_can_see_everything(self):
        """El admin general debe ver prospectos de todas las sucursales."""
        Prospecto.objects.create(primer_nombre="P.", segundo_nombre="Norte", apellido_paterno="Test", sucursal_registro=self.sucursal_norte)
        Prospecto.objects.create(primer_nombre="P.", segundo_nombre="Sur", apellido_paterno="Test", sucursal_registro=self.sucursal_sur)

        response = self.client_gral.get('/api/admin/prospectos/')
        data = response.json()
        
        # Debe ver ambos (2)
        self.assertEqual(len(data['prospects']), 2)
