from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import Usuario, Rol
from catalogs.models import (
    Sucursal, ServicioConfig, ProcEstetico, TipoServicio, 
    TipoPiel, GradoDeshidratacion, GrosorPiel
)
from customers.models import Prospecto, Cliente, ProspectoConversionBorrador
from staff.models import Especialista
import json
from decimal import Decimal

class ClinicBusinessTests(TestCase):
    def setUp(self):
        # Configuración de base: Roles
        self.rol_admin_gral = Rol.objects.create(rol="ADMIN_PRINCIPAL")
        self.rol_admin_suc = Rol.objects.create(rol="ADMIN_SUCURSAL")
        self.rol_trabajador = Rol.objects.create(rol="TRABAJADOR")
        
        # Sucursales
        self.suc_norte = Sucursal.objects.create(nombre="Norte", activa=True)
        self.suc_sur = Sucursal.objects.create(nombre="Sur", activa=True)

        # Catálogos básicos para validaciones
        self.tipo_piel = TipoPiel.objects.create(nombre="Seca", activa=True)
        self.grado_desh = GradoDeshidratacion.objects.create(nombre="Leve", activa=True)
        self.grosor_piel = GrosorPiel.objects.create(nombre="Fino", activa=True)
        
        self.tipo_serv = TipoServicio.objects.create(tipo="Tratamiento", activa=True)
        self.proc = ProcEstetico.objects.create(proceso="Depilacion", activa=True)
        self.serv_config = ServicioConfig.objects.create(
            tipo_servicio=self.tipo_serv, proc_estetico=self.proc, precio_base=Decimal("100.00"), activa=True
        )

        # Usuarios
        self.admin_gral = Usuario.objects.create_user(
            username="admin.gral", password="password123", rol=self.rol_admin_gral, sucursal=self.suc_norte
        )
        self.admin_sur = Usuario.objects.create_user(
            username="admin.sur", password="password123", rol=self.rol_admin_suc, sucursal=self.suc_sur
        )

        self.client_gral = Client()
        self.client_gral.login(username="admin.gral", password="password123")
        
        self.client_sur = Client()
        self.client_sur.login(username="admin.sur", password="password123")

    # --- TESTS DE AISLAMIENTO ---
    
    def test_prospect_isolation(self):
        """Un admin de sucursal solo debe ver sus prospectos."""
        Prospecto.objects.create(primer_nombre="Norte", apellido_paterno="Test", sucursal_registro=self.suc_norte)
        Prospecto.objects.create(primer_nombre="Sur", apellido_paterno="Test", sucursal_registro=self.suc_sur)

        response = self.client_sur.get('/api/admin/prospectos/')
        self.assertEqual(len(response.json()['prospects']), 1)
        self.assertEqual(response.json()['prospects'][0]['segundoNombre'], "Sur")

    # --- TESTS DE CONVERSION (4 PASOS) ---

    def test_step_2_mandatory_zones(self):
        """El paso 2 debe exigir zona general y especifica."""
        prospecto = Prospecto.objects.create(primer_nombre="Test", apellido_paterno="Valid", sucursal_registro=self.suc_sur)
        
        url = f'/api/admin/prospectos/{prospecto.id}/convertir/operacion/'
        payload = {
            "serviceConfigId": self.serv_config.id,
            "precioTotal": "500.00",
            "cuotasTotales": 1,
            "sesionesTotales": 1,
            "fechaInicio": str(timezone.localdate()),
            "zonaGeneral": "", # VACIO
            "zonaEspecifica": "" # VACIO
        }
        
        response = self.client_sur.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        errors = response.json().get('fieldErrors', {})
        self.assertIn("zonaGeneral", errors)
        self.assertIn("zonaEspecifica", errors)

    def test_step_3_mandatory_medical_analysis(self):
        """El paso 3 debe exigir analisis estetico (Piel, Deshidratacion, Grosor)."""
        prospecto = Prospecto.objects.create(primer_nombre="Test", apellido_paterno="Med", sucursal_registro=self.suc_sur)
        # Necesitamos el PDF ficticio para que no falle por falta de archivo (usando mock o simulando multipart)
        from django.core.files.uploadedfile import SimpleUploadedFile
        pdf_file = SimpleUploadedFile("ficha.pdf", b"file_content", content_type="application/pdf")
        
        url = f'/api/admin/prospectos/{prospecto.id}/convertir/ficha-medica/'
        
        # Datos medicos sin analisis estetico
        medical_data = {
            "fechaFicha": str(timezone.localdate()),
            "analisisEstetico": {
                "tipoPielId": "",
                "gradoDeshidratacionId": "",
                "grosorPielId": ""
            }
        }
        
        response = self.client_sur.post(url, {
            "medicalData": json.dumps(medical_data),
            "documentoFichaPdf": pdf_file
        })
        
        self.assertEqual(response.status_code, 400)
        errors = response.json().get('fieldErrors', {})
        self.assertIn("analisisEstetico.tipoPielId", errors)
        self.assertIn("analisisEstetico.gradoDeshidratacionId", errors)

    # --- TESTS DE ESPECIALISTAS ---

    def test_specialist_creation_auto_branch(self):
        """Admin de sucursal crea especialista y se le asigna su sucursal automaticamente."""
        url = '/api/admin/equipo/crear/'
        payload = {
            "username": "esp.nuevo",
            "password": "password123",
            "primerNombre": "Juan",
            "apellidoPaterno": "Perez",
            "ci": "123456",
            "telefono": "788888",
            "specialtyIds": []
            # NO ENVIAMOS sucursalId, debe tomar la del admin (Sur)
        }
        
        response = self.client_sur.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        
        # Verificar en BD
        esp = Especialista.objects.get(usuario__username="esp.nuevo")
        self.assertEqual(esp.usuario.sucursal, self.suc_sur)

    def test_main_admin_can_choose_branch_for_specialist(self):
        """Admin General puede elegir cualquier sucursal para un especialista."""
        url = '/api/admin/equipo/crear/'
        payload = {
            "username": "esp.gral",
            "password": "password123",
            "primerNombre": "Ana",
            "apellidoPaterno": "Lopez",
            "ci": "654321",
            "telefono": "799999",
            "sucursalId": self.suc_sur.id, # Elige Sur aunque el sea de Norte
            "specialtyIds": []
        }
        
        response = self.client_gral.post(url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        
        esp = Especialista.objects.get(usuario__username="esp.gral")
        self.assertEqual(esp.usuario.sucursal, self.suc_sur)
