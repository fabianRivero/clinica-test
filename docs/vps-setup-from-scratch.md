# Guía: Levantar el sistema en un VPS Linux desde cero

## Clínica Estética — Deployment genérico en VPS

> **Reemplaza:** `docs/droplet-setup-from-scratch.md` (que estaba acoplada a DigitalOcean con credenciales hardcodeadas).
> **Compatible con:** cualquier VPS Linux con `sudo` — DigitalOcean, Hetzner, AWS Lightsail, Vultr, Linode, OVH, Contabo, GCP Compute Engine, Azure VM, etc.
> **OS:** Ubuntu 22.04 LTS o 24.04 LTS (`Debian 12` también funciona con mínimos cambios). El setup asume Ubuntu.
> **Tiempo estimado:** 20–40 minutos sobre un VPS recién creado.

---

## 0. Prerrequisitos en tu máquina local

Antes de tocar el VPS, necesitás:

- **SSH key** generada: `ssh-keygen -t ed25519 -C "tu-email@ejemplo.com"` (si no tenés).
- Acceso al repo Git del proyecto (HTTPS o SSH).
- Dominio apuntando a la IP del VPS (registro A en DNS). Si todavía no tenés dominio, podés usar la IP pública para probar, pero HTTPS no funcionará.

---

## 1. Crear el VPS

En el proveedor que elijas:

| Parámetro | Valor recomendado |
|---|---|
| **Imagen** | Ubuntu 22.04 LTS o 24.04 LTS (x86_64) |
| **Size** | 2 vCPU / 4 GB RAM / 80 GB SSD (mínimo para clínica con 1–3 sucursales). Para arrancar, 1 vCPU / 2 GB funciona. |
| **Región** | La más cercana al cliente (latencia). |
| **Hostname** | `clinica-prod` (o el nombre que quieras). |
| **SSH Keys** | Pegar tu clave pública (`cat ~/.ssh/id_ed25519.pub`). |
| **Firewall** | Si el proveedor ofrece "cloud firewall", cerrá todo excepto 22/80/443. |

Anotá la **IP pública** del VPS. La llamaremos `<VPS_IP>` de acá en adelante.

---

## 2. Acceso inicial y hardening básico

```bash
# Conectar como root (o el usuario que el proveedor haya creado)
ssh root@<VPS_IP>

# Actualizar el sistema
apt update && apt upgrade -y

# Instalar paquetes base
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx \
               postgresql postgresql-contrib ufw fail2ban curl git

# Crear usuario de aplicación (NO usar root para la app)
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy

# Firewall: abrir solo SSH, HTTP y HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status

# Proteger SSH contra brute-force
systemctl enable fail2ban
systemctl start fail2ban
```

Ahora cerrá la sesión root y seguí como `deploy`:

```bash
# En tu máquina local, copiar tu SSH key al nuevo usuario
ssh-copy-id deploy@<VPS_IP>

# Conectar como deploy
ssh deploy@<VPS_IP>

# Deshabilitar login root por SSH (opcional pero recomendado)
sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

---

## 3. PostgreSQL

```bash
sudo -u postgres psql
```

Dentro de `psql`:

```sql
CREATE DATABASE clinica;
CREATE USER clinica_app WITH PASSWORD 'CAMBIAR_ESTA_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE clinica TO clinica_app;
\q
```

> **Importante:** Reemplazá `CAMBIAR_ESTA_PASSWORD` por una contraseña fuerte y guardala aparte. La vas a poner en el `.env` del backend.

---

## 4. Clonar el repositorio

```bash
sudo mkdir -p /var/www
sudo chown deploy:deploy /var/www
cd /var/www

# HTTPS (te pide usuario + PAT/token de GitHub)
git clone https://github.com/<ORG>/<REPO>.git clinica

# O SSH (recomendado si configuraste deploy keys)
# git clone git@github.com:<ORG>/<REPO>.git clinica

cd clinica
```

### 4.1. Permisos

```bash
# El usuario que corre Gunicorn va a ser 'www-data' (default de Nginx)
sudo chown -R deploy:www-data /var/www/clinica
sudo chmod -R g+rwX /var/www/clinica
find /var/www/clinica -type d -exec sudo chmod 2775 {} \;
```

---

## 5. Backend (Django)

```bash
cd /var/www/clinica/backend

# Crear virtualenv
python3 -m venv env
source env/bin/activate

# Instalar dependencias
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

### 5.1. Crear `.env`

Copiá la plantilla `backend/.env.example` y editá los valores:

```bash
cp .env.example .env
nano .env
```

Variables **obligatorias** que tenés que setear:

```bash
# Seguridad Django
DJANGO_SECRET_KEY=<GENERAR-VER-INSTRUCCIONES>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=<tu-dominio.com>,www.<tu-dominio.com>

# Base de datos
DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=clinica
DJANGO_DB_USER=clinica_app
DJANGO_DB_PASSWORD=<CAMBIAR_ESTA_PASSWORD>
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
DJANGO_DB_SSLMODE=prefer

# Cookies y CORS
DJANGO_USE_LOCAL_DB=False
DJANGO_CORS_ALLOWED_ORIGINS=https://<tu-dominio.com>
DJANGO_CSRF_TRUSTED_ORIGINS=https://<tu-dominio.com>
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SESSION_COOKIE_SECURE=1
```

**Generar `DJANGO_SECRET_KEY`:**

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Pegá el resultado en `DJANGO_SECRET_KEY=...`.

### 5.2. Elegir el modo de seed

El sistema trae **4 comandos de seed** con alcances muy distintos. Elegí el que necesitás según el contexto:

| # | Comando | Qué va a la DB | Cuándo usarlo |
|---|---|---|---|
| 1 | `seed_client_baseline` | 4 roles + 1 Sucursal (te pide los datos) + admin general (te pide user/pass) + 1 tablet kiosk (te pide código/clave) + **catálogo completo** (12 modelos: tipos de servicio, categorías de gasto, procedimientos, servicios con precio, antecedentes, implantes, cirugías, opciones, tipos de piel, patologías, sectores, etc.). **Idempotente y atómico.** | **Producción real de un cliente.** Esta es la opción correcta para hacer un deploy a un cliente nuevo. |
| 2 | `seed_production_baseline` | 4 roles + 1 Sucursal fija (`Sede Principal`, La Paz) + admin fijo (`admin.general` / `admin123456`) + 1 tablet kiosk fijo (`KIOSKO-PRINCIPAL` / `tablet-verify-123`). **SIN catálogos.** | Legado. Útil solo si querés arrancar con menos y cargar catálogos a mano desde el admin. Fue reemplazado por `seed_client_baseline`. |
| 3 | `seed_pdf_baseline` | Catálogo completo + 3 sucursales + 3 admins + 4 especialistas + 5 especialidades + form config + 2 pacientes demo con huellas mock + 3 tablet kiosks. **Wipea datos clínicos antes de correr.** | Demo, ambiente de staging, capacitación. **NUNCA en producción con datos reales.** |
| 4 | `seed_branch_test_scenarios` | Capa extra: 5 pacientes, 2 especialistas móviles, 12 gastos, 3 tickets. **Requiere `seed_pdf_baseline` antes.** | Test manual de flujos multi-sucursal. |

**Para un cliente real en producción, la opción correcta es `seed_client_baseline`**. Crea todo lo necesario con los datos que vos le das, y además te carga el catálogo de muestra (precios base 850/650/1500/120) para que el sistema funcione sin pasos manuales adicionales.

### 5.3. Migraciones y seed

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py migrate --noinput

# Producción real de un cliente (RECOMENDADO):
sudo -u www-data env/bin/python manage.py seed_client_baseline

# Opcionales según contexto:
# sudo -u www-data env/bin/python manage.py seed_production_baseline     # legado, sin catálogos
# sudo -u www-data env/bin/python manage.py seed_pdf_baseline          # demo, wipea datos
# sudo -u www-data env/bin/python manage.py seed_branch_test_scenarios # demo multi-sucursal

# Archivos estáticos
sudo -u www-data env/bin/python manage.py collectstatic --noinput
```

#### 5.3.1. Seed `seed_client_baseline` — para producción real de un cliente

Es el comando recomendado para cualquier deploy de un cliente nuevo. Tiene dos modos.

**Modo interactivo** — te pregunta todo uno por uno:

```bash
sudo -u www-data env/bin/python manage.py seed_client_baseline
```

El asistente te va a pedir (en este orden):

1. **Datos de la sucursal**: `nombre`, `ciudad`, `direccion`.
2. **Datos del admin general**: `username`, `password`, `primer_nombre`, `apellido_paterno`, `email`.
3. **Datos del kiosk**: `codigo`, `clave`.
4. **Confirmación** si ya existe una sucursal principal.

Validaciones que aplica (rechaza y vuelve a preguntar si no se cumplen):

- Username único (salvo que colisione con el admin target, en cuyo caso lo actualiza).
- Email con formato válido (`validate_email` de Django).
- Password ≥8 chars (corre todas las validaciones de Django: longitud, passwords comunes, numéricos, similitud al usuario).
- Clave del kiosk ≥8 chars.
- Nombre de sucursal único.
- Código de kiosk único.

**Modo no-interactivo** — para deploys automatizados o scripts:

```bash
sudo -u www-data env/bin/python manage.py seed_client_baseline \
    --non-interactive \
    --branch-name "Sede Central" \
    --branch-city "La Paz" \
    --branch-address "Av. Principal #123" \
    --admin-username "admin.central" \
    --admin-password "supersecret123" \
    --admin-first-name "Maria" \
    --admin-last-name "Gutierrez" \
    --admin-email "maria.gutierrez@clinic.local" \
    --kiosk-code "KIOSKO-CENTRAL" \
    --kiosk-password "tablet-secret-123" \
    --replace-main-branch
```

Flags disponibles:

| Flag | Obligatorio no-interactive | Descripción |
|---|---|---|
| `--non-interactive` | sí | Suprime todos los prompts. Falla si falta algún valor. |
| `--branch-name` | sí | Nombre único de la sucursal. |
| `--branch-city` | sí | Ciudad (string libre). |
| `--branch-address` | sí | Dirección (string libre). |
| `--admin-username` | sí | Username único del admin. |
| `--admin-password` | sí | Password (≥8 chars, validado por Django). |
| `--admin-first-name` | sí | Primer nombre. |
| `--admin-last-name` | sí | Apellido paterno. |
| `--admin-email` | sí | Email válido. |
| `--kiosk-code` | sí | Código único del kiosk. |
| `--kiosk-password` | sí | Clave (≥8 chars). |
| `--replace-main-branch` | condicional | Requerido en no-interactive si ya existe una sucursal principal con datos distintos. |

**Seguridad de re-ejecución:**

- **Idempotente**: se puede correr varias veces. `update_or_create` en todos los modelos. Si los datos coinciden, no duplica nada.
- **Atómico**: todo dentro de un `transaction.atomic`. Si CUALQUIER paso falla, NADA se guarda.
- **Reemplazo de sucursal principal**: si ya existe una `Sucursal` con `es_principal=True`, el modo interactivo te muestra los datos actuales y te pregunta "¿Reemplazarla?". El modo no-interactivo requiere `--replace-main-branch`. Al reemplazar, todas las demás sucursales se ponen en `es_principal=False`.

**Qué va a la base de datos con `seed_client_baseline`:**

**Sistema (4 registros):**

| Modelo | Registros | Valores |
|---|---|---|
| `Rol` | 4 | `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE` |

**Sucursal + admin + kiosk (los datos que vos diste):**

| Modelo | Registros | Origen |
|---|---|---|
| `Sucursal` | 1 | Datos del prompt. `es_principal=True`, `activa=True`. |
| `Usuario` (admin) | 1 | Datos del prompt. Superuser, `is_staff=True`, `is_active=True`, rol `ADMIN_PRINCIPAL`, sucursal la de arriba. |
| `TabletKiosko` | 1 | Datos del prompt. `activo=True`, sucursal la de arriba. |

**Catálogo completo (12 modelos, todos los registros):**

| Modelo | Cantidad | Registros |
|---|---|---|
| `TipoServicio` | 2 | `Cita de consulta`, `Tratamiento estético` |
| `CategoriaGasto` | 8 | `Alquiler`, `Servicios`, `Insumos`, `Equipamiento`, `Marketing`, `Sueldos`, `Mantenimiento`, `Otros` |
| `ProcEsteticosTipo` | 1 | `Laser` |
| `ProcEstetico` | 3 | `Depilacion definitiva`, `Tratamiento de manchas`, `Borrado de tatuajes` |
| `ServicioConfig` | 4 | Consulta → **120**, Depilación → **850**, Manchas → **650**, Tatuajes → **1500** |
| `AntecedenteMedico` | 6 | `Diabetes`, `Asma`, `Hipertension`, `Cancer`, `Otro`, `Ninguna` |
| `ImplanteInjerto` | 5 | `Menton`, `Mejillas`, `Nariz`, `Otro`, `Ninguno` |
| `CirugiaEstetica` | 7 | `Blefaroplastia`, `Rinoplastia`, `Bichectomia`, `Rinomodelacion`, `Lifting`, `Botox`, `Ninguna` |
| `GrupoOpciones` | 2 | `SI_NO` (Sí/No), `PROFUNDIDAD_TATUAJE` (Superficial/Profunda) |
| `OpcionCatalogo` | 4 | `Si`, `No`, `Superficial`, `Profunda` |
| `TipoPiel` | 6 | `Piel normal`, `Mixta`, `Seca`, `Grasa`, `Desvitalizada`, `Hidratada` |
| `GradoDeshidratacion` | 3 | `Leve`, `Medio`, `Alto` |
| `GrosorPiel` | 5 | `Fina`, `Media fina`, `Media`, `Media gruesa`, `Gruesa` |
| `PatologiaCutanea` | 28 | `Eritema`, `Telangiectasias`, `Papulas`, `Melasma`, `Hiperpigmentaciones`, `Ampollas`, `Couperosis`, `Pustulas`, `Arrugas`, `Estrellas vasculares`, `Vesiculas`, `Cicatrices`, `Quistes`, `Micosis`, `Dermatitis`, `Angiomas`, `Costra`, `Millium`, `Efelides`, `Hirsutismo`, `Comedones`, `Verruga`, `Rosacea`, `Queratosis`, `Urticaria`, `Eczema`, `Nodulos`, `Vitiligo` |
| `Sector` | 3 | `DEP` (Depilacion), `MAN` (Manchas), `TAT` (Tatuajes) |

**Catálogos NO cargados** (quedan vacíos y hay que popularlos a mano desde el admin si los necesitás): `ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`.

**Output al finalizar:**

```
[CLIENT] Starting client baseline seed...
  Branch created: Sede Central
  Admin created: Maria Gutierrez
  Kiosk created: KIOSKO-CENTRAL
  Catalog baseline seeded.
  Sectors seeded.
[CLIENT] Client baseline seed completed.

Summary:
  Roles:     4 baseline roles
  Branch:    Sede Central (La Paz)
  Admin:     admin.central (maria.gutierrez@clinic.local)
  Kiosk:     KIOSKO-CENTRAL
  Catalogs:  2 service types, 3 procedures, 4 service configs, 28 pathologies, 3 sectors

Final credentials (shown once):
  Admin general: admin.central / supersecret123
  Admin email:   maria.gutierrez@clinic.local
  Admin name:    Maria Gutierrez
  Kiosk code:    KIOSKO-CENTRAL
  Kiosk secret:  tablet-secret-123
  URL Admin:     https://tu-dominio.com/admin
```

#### 5.3.2. Seed `seed_production_baseline` — legado, sin catálogos

Comando antiguo que quedó reemplazado por `seed_client_baseline`. Crea los mismos 4 registros básicos pero con valores fijos y sin catálogos.

| Registro | Valor | Notas |
|---|---|---|
| 4 roles | `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE` | `accounts/management/commands/seed_production_baseline.py:34-40` |
| 1 Sucursal | `Sede Principal` (ciudad: `La Paz`, `es_principal=True`, `activa=True`) | Renombrá esto en el admin apenas entres. |
| 1 Usuario admin | `admin.general` / `admin123456` (superuser) | **CAMBIAR LA PASSWORD EN EL PRIMER LOGIN.** |
| 1 Tablet kiosk | `KIOSKO-PRINCIPAL` / `tablet-verify-123` | **CAMBIAR LA CLAVE.** El save hashea automáticamente. |

**No se crean catálogos**. Vas a tener que cargarlos manualmente desde `/admin/` (Tipo de servicio, Procedimientos estéticos, Servicios con precio, Antecedentes médicos, Especialidades, Sectores, etc.) o correr `seed_pdf_baseline` si querés ver el catálogo de muestra.

**Cuándo usarlo:** solo si necesitás el mínimo absoluto y preferís cargar catálogos a mano. Para producción de un cliente, **preferí siempre `seed_client_baseline`**.

#### 5.3.3. Seed `seed_pdf_baseline` — solo demo, NO en producción

Catálogos completos que se cargan (todos via `seed_pdf_baseline._seed_catalogs()`):

| Catálogo | Registros | Fuente |
|---|---|---|
| Tipos de servicio | 2: `Cita de consulta`, `Tratamiento estético` | `seed_pdf_baseline.py:380-389` |
| Categorías de gasto | 8: `Alquiler`, `Servicios`, `Insumos`, `Equipamiento`, `Marketing`, `Sueldos`, `Mantenimiento`, `Otros` | `:391-405` |
| Tipo procedimiento estético | 1: `Laser` | `:407-415` |
| Procedimientos estéticos | 3: `Depilacion definitiva`, `Tratamiento de manchas`, `Borrado de tatuajes` | `:417-447` |
| Servicios con precio | 4 (precios base): Depilación **850**, Manchas **650**, Tatuajes **1500**, Consulta **120** | `:437-460` |
| Antecedentes médicos | 6: `Diabetes`, `Asma`, `Hipertension`, `Cancer`, `Otro`, `Ninguna` | `:462-474` |
| Implante/Injerto | 5: `Menton`, `Mejillas`, `Nariz`, `Otro`, `Ninguno` | `:476-488` |
| Cirugía estética | 7: `Blefaroplastia`, `Rinoplastia`, `Bichectomia`, `Rinomodelacion`, `Lifting`, `Botox`, `Ninguna` | `:490-510` |
| Grupos de opciones | 2: `SI_NO` (Sí/No), `PROFUNDIDAD_TATUAJE` (Superficial/Profunda) | `:512-557` |
| Tipos de piel | 6: `Piel normal`, `Mixta`, `Seca`, `Grasa`, `Desvitalizada`, `Hidratada` | `:559-570` |
| Grado de deshidratación | 3: `Leve`, `Medio`, `Alto` | `:572-580` |
| Grosor de piel | 5: `Fina`, `Media fina`, `Media`, `Media gruesa`, `Gruesa` | `:582-593` |
| Patologías cutáneas | 28: `Eritema`, `Telangiectasias`, `Papulas`, `Melasma`, `Hiperpigmentaciones`, …, `Vitiligo` | `:595-633` |
| Sectores | 3: `DEP` (Depilación), `MAN` (Manchas), `TAT` (Tatuajes) | `:638-655` |

**Registros NO creados por el seed:** `ProductoAlergia`, `TipoAlergia`, `GravedadAlergia`. Quedan vacíos.

**Datos extra que también se crean:**

- 3 Sucursales: `Sede Principal`, `Sucursal Norte` (La Paz), `Sucursal Sur` (Santa Cruz).
- 3 Admins: `admin.general` (superuser), `admin.norte`, `admin.sur` — todos password `admin123456`.
- 4 Especialistas (usuarios): `lucia.laser`, `diego.tatuajes`, `sofia.manchas`, `rafael.consulta` — passwords `laser123456`, `tatuajes123456`, `manchas123456`, `consulta123456`.
- 5 Especialidades + 4 Especialistas (vinculados).
- 2 Prospectos (`PASAJERO`).
- 2 Pacientes demo: `paciente.demo` / `paciente123456`, `paciente.inactivo` / `paciente123456`. **Cada uno con una `HuellaBiometricaCliente` mock** — `MOCK_TEMPLATE_DEMO_abc123def456` y `MOCK_TEMPLATE_CARLOS_xyz789ghi012`. Esto es porque el sistema todavía no tiene integración biométrica real (es un placeholder).
- Agendas: lun–vie 08:00–18:00 para cada especialista.
- 3 Tablet kiosks: `KIOSKO-PRINCIPAL` / `tablet-principal-123`, `KIOSKO-NORTE` / `tablet-norte-123`, `KIOSKO-SUR` / `tablet-sur-123`.

**Datos que el seed DESTRUYE antes de correr** (importante si lo corrés en una DB con datos reales):

- `HuellaBiometricaCliente` (todas las huellas)
- `PagoRealizado`, `CuotaPlanPago`, `CitaMedica`, `Operacion` (todo el historial clínico de pagos y turnos)

`seed_pdf_baseline.py:1045-1050` lo hace explícitamente. **No lo corras en producción con datos clínicos reales.**

#### 5.3.4. Seed `seed_branch_test_scenarios` — extra multi-sucursal

Capa adicional para testear flujos multi-sucursal. **Requiere haber corrido `seed_pdf_baseline` antes** (si no, falla con `RuntimeError`).

Agrega:

- 5 Pacientes (`paciente.multisucursal`, `paciente.importable`, `paciente.importable.libre`, `paciente.norte`, `paciente.sur`) — todos password `paciente123456`.
- 2 Especialistas móviles (`especialista.movible.norte`, `especialista.movible.sur`) — password `especialista123456`.
- 12 `GastoSucursal` (abril–mayo 2026, 6 por sucursal).
- 3 `Ticket` con sus `TicketMessage`.

**Solo para dev/test. No en producción.**

### 5.4. Verificación rápida

```bash
# ¿Gunicorn puede arrancar?
sudo -u www-data env/bin/python manage.py check

# ¿La DB responde?
sudo -u www-data env/bin/python manage.py shell -c "from accounts.models import Usuario; print(Usuario.objects.count())"
```

---

## 6. Frontend

```bash
cd /var/www/clinica/frontend/aesthetic-clinic

# Instalar dependencias y compilar
npm ci
npm run build
```

El build genera `dist/` que Nginx va a servir.

---

## 7. Nginx

```bash
sudo nano /etc/nginx/sites-available/clinica
```

Pegá esta configuración (reemplazá `tu-dominio.com`):

```nginx
server {
    server_name tu-dominio.com www.tu-dominio.com;

    root /var/www/clinica/frontend/aesthetic-clinic/dist;
    index index.html;

    # Logs
    access_log /var/log/nginx/clinica.access.log;
    error_log  /var/log/nginx/clinica.error.log;

    # Archivos del backend Django
    location /static/ {
        alias /var/www/clinica/backend/staticfiles/;
        access_log off;
        expires 30d;
    }

    location /media/ {
        alias /var/www/clinica/backend/media/;
        access_log off;
        expires 30d;
    }

    # API
    location /api/ {
        proxy_pass http://unix:/var/www/clinica/clinica.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # Admin Django
    location /admin/ {
        proxy_pass http://unix:/var/www/clinica/clinica.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend SPA: cualquier ruta no-matcheada va al index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Seguridad básica
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}
```

Activar el sitio:

```bash
sudo ln -s /etc/nginx/sites-available/clinica /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

---

## 8. SSL con Let's Encrypt

```bash
sudo certbot --nginx -d tu-dominio.com -d www.tu-dominio.com
```

Certbot modifica automáticamente el bloque Nginx para redirigir HTTP→HTTPS. Verificá:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Certbot instala un timer systemd que renueva automáticamente. Verificar:

```bash
sudo systemctl status certbot.timer
```

---

## 9. Gunicorn como servicio systemd

```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=Gunicorn Django daemon for clinica
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/clinica/backend
EnvironmentFile=/var/www/clinica/backend/.env
ExecStart=/var/www/clinica/backend/env/bin/gunicorn \
    --workers 2 \
    --bind unix:/var/www/clinica/clinica.sock \
    --timeout 120 \
    --access-logfile /var/www/clinica/gunicorn-access.log \
    --error-logfile /var/www/clinica/gunicorn-error.log \
    config.wsgi:application

Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn
sudo systemctl start gunicorn
sudo systemctl status gunicorn
```

Si falla:

```bash
sudo journalctl -u gunicorn --no-pager -n 50
```

---

## 10. Deploy desde la máquina local

Una vez que el VPS está corriendo, mantener el sistema actualizado es automático con `scripts/deploy.sh`.

**La primera vez**, copiá la plantilla y dale permisos. El script te va a preguntar los datos del VPS y los guarda en `scripts/.deploy-config` (gitignored) para no volver a preguntarlos:

```bash
cp scripts/deploy.sh.example scripts/deploy.sh
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

Te va a pedir (con defaults entre corchetes):

```
IP o hostname del VPS []: <VPS_IP>
Path del proyecto en el VPS [/var/www/clinica]: <enter>
Usuario SSH en el VPS [deploy]: <enter>
Dominio principal (sin https://) []: tu-dominio.com
Rama a desplegar [main]: <enter>
URL del repo (para validar el remote) []: <enter>
```

Después de la primera corrida, los valores quedan en `scripts/.deploy-config` y no se vuelven a preguntar. Para cambiar uno:

```bash
nano scripts/.deploy-config
```

O borrá el archivo y volvé a correr el script.

**Variables que podés querer editar** (todas opcionales, todas con default razonable):

| Variable | Default | Cuándo cambiarla |
|---|---|---|
| `VPS_HOST` | (vacío, obligatorio) | Primera vez. Luego queda guardada. |
| `VPS_USER` | `deploy` | Si creaste otro usuario SSH. |
| `PROJECT_PATH` | `/var/www/clinica` | Si instalaste en otro path. |
| `DOMAIN` | (vacío) | Para que el script verifique HTTP 200 al final. |
| `GIT_BRANCH` | `main` | Si deployás desde otra rama. |
| `GIT_REPO` | (vacío) | Si querés que valide que el remote coincida. |

**Modo no-interactivo** (para CI o scripts automatizados): si `scripts/.deploy-config` ya existe con todos los valores, el script no pregunta nada.

**Lo que hace el deploy:**

1. Hace `git pull` en el VPS.
2. Actualiza dependencias Python.
3. Reconstruye el frontend (`npm ci` + `npm run build`).
4. Aplica migraciones.
5. Recolecta estáticos.
6. Reinicia Gunicorn.
7. Verifica Nginx y (si hay dominio) hace un `curl` al sitio.

---

## 11. Post-instalación obligatorio

### 11.1. Cambiar TODAS las credenciales del seed

| Servicio | Credencial seed | Acción |
|---|---|---|
| Admin Django | `admin.general` / `admin123456` | Cambiar en el primer login o via Django shell. |
| Tablet kiosks (si usaste `seed_pdf_baseline`) | `KIOSKO-PRINCIPAL` / `tablet-principal-123`, etc. | Desde `/admin/` o Django shell. |
| PostgreSQL | la que pusiste en el `.env` | Guardala en un gestor de secretos. |

### 11.2. Configurar backups automáticos de la base de datos

Sin backups, un disco que se muere te deja sin sistema y sin datos. Para una clínica esto es inaceptable.

```bash
# Crear script de backup
sudo nano /usr/local/bin/clinica-backup.sh
```

```bash
#!/bin/bash
set -e

BACKUP_DIR=/var/backups/clinica
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/clinica_${TIMESTAMP}.sql.gz"

# Cargar credenciales desde .env (sin imprimirlas)
set -a
source /var/www/clinica/backend/.env
set +a

pg_dump -U "$DJANGO_DB_USER" -h "$DJANGO_DB_HOST" -d "$DJANGO_DB_NAME" \
    | gzip > "$BACKUP_FILE"

# Conservar últimos 30 días
find "$BACKUP_DIR" -name "clinica_*.sql.gz" -mtime +30 -delete

echo "Backup creado: $BACKUP_FILE"
```

```bash
sudo chmod 700 /usr/local/bin/clinica-backup.sh

# Probar
sudo /usr/local/bin/clinica-backup.sh

# Programar diario a las 03:00
sudo crontab -e
# Agregar:
0 3 * * * /usr/local/bin/clinica-backup.sh >> /var/log/clinica-backup.log 2>&1
```

### 11.3. Subir backups a un lugar fuera del VPS

El backup local NO es suficiente. Si el VPS se muere, te quedás sin backups. Configurá sincronización periódica a un destino externo:

| Opción | Configuración |
|---|---|
| **Backblaze B2** | Barato, `b2 sync` o `rclone`. |
| **AWS S3** | `aws s3 sync`. |
| **Storage del proveedor** | DO Spaces, Hetzner Storage Box, etc. |
| **rsync a otro servidor** | Si tenés otro VPS. |

Sumá una segunda línea al cron o un script separado.

### 11.4. Configurar alertas mínimas

Sin monitoreo, no sabés que algo se rompió hasta que el cliente te llama. Lo mínimo:

- **UptimeRobot** (gratis): chequea que `https://tu-dominio.com/` responda 200 cada 5 min. Te avisa por mail/Slack.
- **Sentry** (free tier): captura excepciones de Django y React. Indispensable para producción.

### 11.5. Configurar actualizaciones de seguridad automáticas

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 11.6. Datos sensibles: consideraciones legales

La clínica maneja datos de salud de pacientes. En Argentina (Ley 25.326) y muchas otras jurisdicciones, esto es **dato sensible**. Antes de poner el sistema en producción para un cliente:

- [ ] Confirmar que el cliente firmó consentimiento sobre el proveedor de hosting.
- [ ] Verificar que la DB está encriptada (la mayoría de proveedores cloud lo ofrece).
- [ ] Política de acceso al VPS: quién tiene la clave SSH, quién rota.
- [ ] Política de backups: dónde se guardan, quién tiene acceso, retención.
- [ ] Política de logs: accesos a datos clínicos deben quedar auditados.

---

## 12. Comandos útiles del día a día

```bash
# Estado de servicios
sudo systemctl status gunicorn postgresql nginx

# Ver logs de Gunicorn
sudo journalctl -u gunicorn -f
tail -f /var/www/clinica/gunicorn-error.log

# Ver logs de Nginx
sudo tail -f /var/log/nginx/clinica.error.log

# Reiniciar todo
sudo systemctl restart gunicorn postgresql nginx

# Cuánto ocupa la DB
sudo du -sh /var/lib/postgresql/

# Backup manual
sudo /usr/local/bin/clinica-backup.sh

# Listar backups
ls -lh /var/backups/clinica/
```

---

## 13. Troubleshooting

### El sitio no carga

```bash
# ¿Gunicorn está corriendo?
sudo systemctl status gunicorn

# ¿Nginx puede leer el socket?
ls -la /var/www/clinica/clinica.sock

# Logs de Nginx
sudo tail -f /var/log/nginx/clinica.error.log
```

### 502 Bad Gateway

Casi siempre es que Gunicorn no está corriendo o el socket no existe. Mirá `journalctl -u gunicorn`.

### Error de migraciones

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py showmigrations
sudo -u www-data env/bin/python manage.py migrate
```

### Cambié el `.env` y nada se actualiza

Gunicorn NO recarga al cambiar el `.env`. Hay que reiniciar:

```bash
sudo systemctl restart gunicorn
```

### Olvidé la contraseña del admin

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py changepassword admin.general
```

### Necesito cambiar la contraseña de la DB

```bash
sudo -u postgres psql
ALTER USER clinica_app WITH PASSWORD 'nueva_password';
\q

# Actualizar .env
sudo nano /var/www/clinica/backend/.env
# (cambiar DJANGO_DB_PASSWORD=...)

sudo systemctl restart gunicorn
```

---

## 14. Resumen de archivos configurados

| Archivo | Ubicación | Propósito |
|---|---|---|
| `.env` | `/var/www/clinica/backend/.env` | Variables de entorno Django (sensible, NO commitear) |
| `.env.example` | `/var/www/clinica/backend/.env.example` | Plantilla del `.env` (sí commitear) |
| Nginx config | `/etc/nginx/sites-available/clinica` | Reverse proxy + SSL + estáticos |
| Gunicorn service | `/etc/systemd/system/gunicorn.service` | Daemon auto-inicio |
| Backup script | `/usr/local/bin/clinica-backup.sh` | Dump diario de PostgreSQL |
| Cron backups | `crontab -e` | Programa el backup a las 03:00 |
| `deploy.sh` | `scripts/deploy.sh` (local) | Deploy automático desde máquina local (la primera vez pregunta los datos y los guarda en `scripts/.deploy-config`) |

---

## 15. Estructura final en el VPS

```
/var/www/clinica/
├── backend/
│   ├── env/                  # Virtualenv Python
│   ├── .env                  # Variables de entorno (sensible)
│   ├── manage.py
│   ├── staticfiles/          # Estáticos Django (servido por Nginx)
│   └── media/                # Archivos media (QR, recibos)
├── frontend/
│   └── aesthetic-clinic/
│       └── dist/             # Build React (servido por Nginx)
├── clinica.sock              # Socket Gunicorn
├── gunicorn-access.log
└── gunicorn-error.log

/var/backups/clinica/         # Backups PostgreSQL
```

---

## Historial de cambios de esta guía

| Commit | Qué cambió |
|---|---|
| `7b107bc` | Creación de la guía. Reemplaza `droplet-setup-from-scratch.md` y `droplet-deploy-updates.md`. Agrega guía VPS genérica, comando `seed_client_baseline`, `.env.example`, `deploy.sh.example`, spec OpenSpec y 13 tests. |

Si la guía quedó desactualizada respecto al código, este es el bloque a actualizar. Buscá la sección correspondiente en la tabla de arriba y en el diff del commit.

## Próximos pasos para producción real

Esta guía deja el sistema funcionando, pero para un cliente final **se recomienda**:

1. **Migrar a un PaaS** (Railway, Render) o usar **DB administrada** (Supabase, RDS) para recibir backups, monitoreo y SSL administrado.
2. **Mover archivos media** (QR, PDFs) a S3-compatible en lugar de disco local.
3. **Sumar CDN** (Cloudflare) delante del VPS.
4. **Sumar rate limiting** en Nginx (`limit_req_zone`) para la API.
5. **Revisar `docs/verification-contract-v2.md`** y demás specs periódicamente: la guía asume que el código está estable. Cambios grandes requieren actualizar la guía.
