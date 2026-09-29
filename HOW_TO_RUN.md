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

## Phase 3 setup — captura real de huella (DigitalPersona 4500)

Phase 3 (`openspec/changes/dp4500-host-app-integration-phase3-capture-client/`) reemplaza el placeholder `template_b64 = ''` de Phase 2A4 con un wrapper `captureFingerprint()` que carga el SDK vendoreado y captura una muestra real desde el lector. Esto es **opt-in** — el fallback NO_AGENT sigue activo en workstations sin hardware.

### Requisitos del operador

- **Lector DigitalPersona 4500** conectado vía USB a la workstation.
- **HID Authentication Device Client** (gratis, Windows) instalado y corriendo — el SDK de browser habla con el lector a través de este cliente vía WebChannel (puerto local 52181). Sin este cliente el wrapper tira `BiometricHardwareError` y el wizard cae al NO_AGENT.
- **Chrome o Edge** (no Firefox, no Safari). El SDK declara `"browserslist": ["not iOS > 0", "not Android > 0", "edge >= 17"]` — Firefox y Safari quedan fuera.
- Permiso USB para el lector cuando el browser lo pida la primera vez.

### Variables de entorno del frontend

- `VITE_DP4500_SERVICE_API_KEY` — el Bearer token que `dp4500-capture-client.ts` lee al cargarse. Sin esto, `enrollIdentity()` tira error de configuración antes de cualquier captura (Phase 2A4 contract).
- `VITE_BIOMETRIC_SUSPENDED` — si está en `true`, el wizard skipea captura entera (Phase 2A4 build flag). Para activar la captura real, dejá en `false` o sin setear.

### Verificar que el SDK cargó

En DevTools del browser, después de abrir el modal de captura y clickear "Activar lector":

```js
window.Fingerprint        // { WebApi: function, ... } — el global del SDK
window.Fingerprint.WebApi // class — constructor del facade
```

Si `window.Fingerprint` es `undefined` después de clickear "Activar lector", el script `/websdk/fingerprint.sdk.min.js` no se inyectó (404, MIME type, CSP). Revisá la pestaña Network.

### Fallback NO_AGENT

Workstations SIN lector o SIN HID Authentication Device Client:
- El wrapper tira `BiometricHardwareError` tras 30s (timeout) o inmediato si no hay WebChannel host.
- El wizard cae al NO_AGENT path (`useConversionWizard.ts:842-859` — preservado verbatim desde Phase 2A4).
- El enroll se completa con `template_b64 = ''` (placeholder contract validado en Phase 2A4).
- La UI muestra "DP4500 enroll OK; legacy omitido (sin lector)" o "Captura legacy omitida (sin lector); enroll DP4500 diferido." según el enroll sidecar.

### Verificación end-to-end

```bash
cd "C:\proyectos\proyecto C\frontend\aesthetic-clinic"
npx tsc -b --pretty false                              # type-check
npx eslint src/services/biometric/dp4500-capture-client.ts src/pages/admin/prospect-convert/useConversionWizard.ts
npx vitest run src/services/biometric/__tests__/dp4500-capture-client.test.ts   # unit tests (sin hardware)
```

Para validación con hardware real, abrí `http://localhost:5173/public/fingerprint-probe.html` y seguí los 3 pasos (cargar SDK, iniciar adquisición, esperar muestra). El probe page carga el mismo `/websdk/fingerprint.sdk.min.js` vendoreado.

### Out of scope (Phase 4)

- `fingerprint-agent` local (Python + `cloudflared` tunnel) si la verificación con hardware falla.
- KMS-backed key store, mTLS, per-sucursal routing, DPIA §9.
- `Cliente.external_id` UUIDField + finalize handler persistence.

## Phase 3.1 operator workstation validation guide

Phase 3.1 wires el SDK `onQualityReported` event en `captureFingerprint()` (Deviation 3 del verify-report Phase 3). El wrapper ahora rechaza capturas con `BiometricQualityTooLow` cuando la calidad reportada != `Good` (0). Este es un **manual validation gate** — Phase 3.1 no se puede ejercitar desde el test suite (no hay DigitalPersona 4500 conectado en CI). Un operador debe validar en una workstation con el hardware real antes de cerrar Phase 3.

### Pre-requisitos (operator workstation)

- **Windows 10/11** con **HID Authentication Device Client** corriendo — verificá en `services.msc` que el servicio `DPS` (DigitalPersona Service) está `Running`. Sin este servicio, el WebChannel del SDK no encuentra el lector y la captura tira `BiometricHardwareError`.
- **Lector DigitalPersona 4500** conectado vía USB. Verificá en Device Manager que aparece bajo "Biometric devices".
- **Entorno de dev clinic corriendo**: DP4500 backend en 8000 + clinic backend en 8001 + Vite dev server en 5173 (los tres corriendo en terminales separadas).
- **Un prospecto enrolado** como cliente de prueba (cualquier nombre — sirve para llegar a step 4 sin re-enrolar).

### Step-by-step validation

1. **Abrí el clinic admin** en Chrome/Edge en `http://localhost:5173` → login como admin.
2. **Navegá al prospecto de prueba** → iniciá conversión → avanzá hasta **step 4** (captura biomilística).
3. **Verificá que el modal de captura Phase 3 renderiza** (NO el fallback NO_AGENT). Buscá una referencia a "DigitalPersona" en el modal — si ves "Captura legacy omitida (sin lector)" o "DP4500 enroll OK; legacy omitido (sin lector)", estás en el fallback NO_AGENT y el SDK no cargó.
4. **Poné tu dedo en el lector** cuando el modal lo pida.
5. **Resultados esperados**:
   - **Happy path**: el modal muestra "Huella capturada" → step 4 avanza a step 5. La enrollment record se persiste con `template_b64` no vacío.
   - **Calidad baja**: el modal muestra "Calidad insuficiente (TooNoisy). Vuelve a intentarlo." (o el nombre del código que aplique: `TooSkewed`, `TooFast`, `FakeFinger`, etc.). El operador puede reintentar — NO se persiste template.
   - **Timeout sin calidad**: el modal muestra "No se recibio un reporte de calidad dentro de 30s. Vuelve a intentarlo." — típicamente el operador sacó el dedo antes de que el WebChannel alcance a scorear la muestra.
   - **Hardware error**: el modal muestra "Hardware no disponible o SDK no inicializo." o "SDK error code N" — revisá el servicio DPS (`services.msc` → "DigitalPersona Service") y que el lector esté bien conectado.

### Verificación del lado enroll DP4500

Después de que el wizard avanza, confirmá que el `template_b64` se envió a DP4500 (no el placeholder vacío de Phase 2A4):

```bash
# En WSL bash, sobre el terminal del backend DP4500:
cd "C:\proyectos\DP4500 estandar\backend"
.\.venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "config.settings.dev"
python manage.py shell --command "
from apps.biometric.infrastructure.persistence.models import BiometricTemplate
rows = list(BiometricTemplate.objects.filter(client_pubkey_fingerprint__isnull=False).order_by('-id')[:3])
for t in rows:
    print(f'id={t.id} user_ext={t.user_external_id} template_len={len(t.encrypted_fmd or chr(0))} pubkey_fpr={t.client_pubkey_fingerprint[:16]}')
"
```

La fila más reciente debe tener `template_len > 0` (template real, NO los bytes vacíos del placeholder Phase 2A4).

### Troubleshooting

- **"QualityCode TooNoisy" repetido** → el operador tiene el dedo muy seco/húmedo. Pasale un pañuelo o pedile que se limpie el dedo.
- **"QualityCode TooSkewed" / "NotCentered"** → el operador no apoyó el dedo centrado en el sensor. Re-entrená la posición.
- **"QualityCode FakeFinger"** → el sensor detectó un material que no es piel viva (silicona, látex). Es comportamiento esperado del liveness check del SDK; no es un bug.
- **El modal muestra "Hardware no disponible"** → verificá `services.msc` → "DigitalPersona Service" (debe estar Running). Si está stopped, iniciá manualmente. Si está Running y aún falla, revisá la consola del browser por WebChannel errors.
- **El modal no renderiza (queda en blanco)** → el script `/websdk/fingerprint.sdk.min.js` no se inyectó. Revisá la pestaña Network del DevTools y la consola por errores 404 / MIME type / CSP.