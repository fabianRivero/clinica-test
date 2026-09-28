# Aesthetic Clinic — Cómo correrla en dev

Guía paso a paso para correr el frontend + backend del clinic con la integración DP4500.

## Qué necesitás

- **Windows** + **WSL** (Windows Subsystem for Linux). El backend del clinic corre dentro de WSL porque su venv fue creada allá.
- **Python 3.14** en Windows nativo (`C:\Python314\python.exe`) — sin venv.
- **Node 20+** + **npm 11+** (para el frontend Vite).
- **SQLite** (default del dev). No requiere PostgreSQL.
- **DP4500 estandar** corriendo en otro puerto (ver abajo).

## Estructura

```
.
├── backend/                  # Django + DRF (clinica)
├── frontend/aesthetic-clinic/ # Vite + React 19 + TS
└── openspec/                 # Artefactos de Spec-Driven Development
```

## 1. Backend del clinic (puerto 8001, WSL)

Desde la terminal WSL bash:

```bash
cd "/mnt/c/proyectos/proyecto C/backend"
source env/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings

# Phase 2A setup: el backend llama a DP4500 (puerto 8000) para
# /api/biometric/service/*. Si probás enroll o verify con huella,
# seteá estas env vars antes de arrancar el runserver:
export DP4500_BASE_URL="http://localhost:8000"
export DP4500_SERVICE_KEY_SUCURSAL_1="83mdy6xRsBOHSRGiKxfKVue-aZZpIYnuUWUKufv0i7U"
# (Si corrés WSL, reemplazá localhost por la IP del gateway, ej http://172.20.176.1:8000)

python manage.py runserver 0.0.0.0:8001
```

Esperado: `Starting development server at http://0.0.0.0:8001/`.

## 2. DP4500 estandar (puerto 8000, Windows nativo)

Desde PowerShell nativo:

```powershell
cd "C:\proyectos\DP4500 estandar\backend"
.\.venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
python manage.py runserver 0.0.0.0:8000
```

Esperado: `Starting development server at http://0.0.0.0:8000/`.

## 3. Frontend del clinic (puerto 5173, Windows nativo)

Desde PowerShell nativo:

```powershell
cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
npm run dev
```

Esperado: `Local: http://localhost:5173/`.

## Verificación rápida

Tres smoke checks (uno por terminal, o desde PowerShell nativo):

```powershell
# DP4500 — espera 400 con MISSING_FIELDS
curl.exe -s http://localhost:8000/api/biometric/service/identity/enroll/ -X POST -H "Content-Type: application/json" -H "Authorization: Bearer 83mdy6xRsBOHSRGiKxfKVue-aZZpIYnuUWUKufv0i7U" -d "{}"

# Clinic — espera 200 con CSRF cookie
curl.exe -s http://localhost:8001/api/auth/csrf/

# Vite — espera 200 con HTML del index
curl.exe -s http://localhost:5173/
```

## Tests automatizados

Backend (WSL only):

```bash
cd "/mnt/c/proyectos/proyecto C/backend"
source env/bin/activate
export DJANGO_SETTINGS_MODULE=config.settings
python -m pytest -q
```

Frontend:

```powershell
cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
npm run test:e2e
```

## Flujo end-to-end Phase 2A (registro + verify de huella)

### Step 4: registro de huella (enroll)

1. Login admin en `http://localhost:5173`.
2. Ir a un prospecto → "Convertir".
3. Avanzar los pasos 1, 2, 3 del wizard.
4. En **step 4** click "Capturar huella" → modal → "Activar lector".
5. Si no hay hardware lector configurado, el modal muestra "DP4500 enroll OK; legacy omitido (sin lector)." Eso es éxito — el UUID se persiste igual en `Cliente.external_id`.

### Verify de cita

1. Crear una cita via shell para el cliente recién creado:
   ```bash
   cd "/mnt/c/proyectos/proyecto C/backend"
   source env/bin/activate
   export DJANGO_SETTINGS_MODULE=config.settings
   python manage.py shell --command "
   from customers.models import Cliente
   from operations.models import CitaMedica, Operacion
   from datetime import datetime, timezone, timedelta
   cliente = Cliente.objects.get(usuario__username='TU_USERNAME')
   op = cliente.operaciones.first()
   if op.sesiones_totales == 0:
       op.sesiones_totales = 10
       op.save(update_fields=['sesiones_totales'])
   cita = CitaMedica.objects.create(
       operacion=op,
       sucursal=cliente.sucursal_origen,
       fecha_hora=datetime.now(timezone.utc) + timedelta(days=1),
       estado=CitaMedica.Estado.REALIZADA_PENDIENTE_VERIFICACION,
   )
   print(f'cita.id={cita.id}')
   "
   ```
2. En el browser, ir al detalle de la cita → "Confirmar huella" → modal → "Activar lector".
3. Si todo está bien: el modal muestra "Huella confirmada. La cita pasó a CONFIRMADA." y la cita en DB tiene `estado=CONFIRMADA, metodo_confirmacion=BIOMETRICO`.

## Troubleshooting

### "DP4500 no responde: no_service_key" en verify

El backend del clinic no encuentra el ServiceAPIKey de la sucursal. Verificá que `DP4500_SERVICE_KEY_SUCURSAL_<id>` esté seteada en el shell del runserver antes de arrancarlo.

### "DP4500 no responde: transport:ConnectError" en verify

El backend del clinic no puede conectar a DP4500. Si corrés WSL, `localhost` no resuelve al host Windows. Usá la IP del gateway:
```bash
ip route show default | awk '{print $3}'  # típicamente 172.x.x.1
export DP4500_BASE_URL="http://$(ip route show default | awk '{print $3}'):8000"
```

### "UNIQUE constraint failed: biometric_template.client_pubkey_fingerprint" en enroll

La workstation ya tiene un template activo en DP4500 con ese fingerprint. Cerrá la ventana de incógnito y abrí una nueva (IndexedDB limpio → nueva keypair Ed25519 → nuevo fingerprint).