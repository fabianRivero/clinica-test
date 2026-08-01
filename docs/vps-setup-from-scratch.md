# Guía: Levantar el sistema en un VPS Linux desde cero

## Clínica Estética — Deployment genérico en VPS

> **Reemplaza:** `docs/droplet-setup-from-scratch.md` (que estaba acoplada a DigitalOcean con credenciales hardcodeadas).
> **Compatible con:** cualquier VPS Linux con `sudo` — DigitalOcean, Hetzner, AWS Lightsail, Vultr, Linode, OVH, Contabo, GCP Compute Engine, Azure VM, etc.
> **OS:** Ubuntu 22.04 LTS o 24.04 LTS (`Debian 12` también funciona con mínimos cambios). El setup asume Ubuntu.
> **Tiempo estimado:** 20–40 minutos sobre un VPS recién creado.

---

## 0. Prerrequisitos en tu máquina local

Antes de tocar el VPS, necesitas:

- **SSH key** generada: `ssh-keygen -t ed25519 -C "tu-email@ejemplo.com"` (si no se tiene).
- Acceso al repo Git del proyecto (HTTPS o SSH).
- Dominio apuntando a la IP del VPS (registro A en DNS). Si todavía no tienes dominio, peudes usar la IP pública para probar, pero HTTPS no funcionará.

---

## 1. Crear el VPS

En el proveedor que elijas:

| Parámetro | Valor recomendado |
|---|---|
| **Imagen** | Ubuntu 22.04 LTS o 24.04 LTS (x86_64) |
| **Size** | 2 vCPU / 4 GB RAM / 80 GB SSD (mínimo para clínica con 1–3 sucursales). Para arrancar, 1 vCPU / 2 GB funciona. **El de 1 vCPU / 512 MB no sirve para producción real** — el build del frontend se queda sin memoria y va a fallar. |
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

# Instalar paquetes base. En Ubuntu 24.04, los nombres de los paquetes
# cambiaron respecto a 22.04: hay que agregar python3-pip y python3.12-venv
# explícitamente, y nodejs está en el repo de Ubuntu (no en NodeSource).
apt install -y python3 python3-pip python3-venv python3.12-venv \
               nginx certbot python3-certbot-nginx \
               postgresql postgresql-contrib \
               ufw fail2ban curl git \
               nodejs npm

# Crear usuario de aplicación (NO usar root para la app)
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy

# SIN esta línea, `sudo` te va a pedir password cada vez y los
# deploys automatizados no van a funcionar. NOPASSWD es estándar para
# usuarios de deploy.
echo "deploy ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/deploy
chmod 440 /etc/sudoers.d/deploy

# Firewall: abrir solo SSH, HTTP y HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status

# Proteger SSH contra brute-force
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

Ahora cierra la sesión root y sigue como `deploy`:

```bash
# En tu máquina local, copiar tu SSH key al nuevo usuario
ssh-copy-id deploy@<VPS_IP>

# Conectar como deploy
ssh deploy@<VPS_IP>

# Deshabilitar login root por SSH (opcional pero recomendado)
sudo sed -i 's/^PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart sshd
```

> **⚠️ Si tenés problemas para entrar como `deploy` con `ssh-copy-id`**: abrí la consola web del proveedor (DigitalOcean, Hetzner, etc.) como root, y ejecutá los pasos de creación de `deploy` + copia de `authorized_keys` directamente ahí. A veces la key que subiste al crear el droplet no es la misma que tenés ahora en tu máquina local.

---

## 3. PostgreSQL

```bash
sudo -u postgres psql
```

Dentro de `psql` (cada línea es un comando separado, esperaba el `;` o el prompt antes de la siguiente):

```sql
CREATE DATABASE clinica;
CREATE USER clinica_app WITH PASSWORD 'CAMBIAR_ESTA_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE clinica TO clinica_app;
```

⚠️ **Postgres 16 (Ubuntu 24.04) rechaza SCRAM.** Si Django tira `password authentication failed for user "clinica_app"` al hacer `migrate`, hay que cambiar la auth a `md5`. Salí de psql con `\q` y:

```bash
sudo nano /etc/postgresql/16/main/pg_hba.conf
```

Buscá la línea:

```
host    all             all             127.0.0.1/32            scram-sha-256
```

Y cambiala por:

```
host    all             all             127.0.0.1/32            md5
```

Reiniciá Postgres:

```bash
sudo systemctl restart postgresql
```

Y reseteá la password (Postgres 16 necesitó esto — la password que tipeaste con `CREATE USER` queda con un hash que puede no coincidir):

```bash
sudo -u postgres psql
```

```sql
ALTER USER clinica_app WITH PASSWORD 'CAMBIAR_ESTA_PASSWORD';
```

⚠️ **Usá password sin caracteres especiales** (`@`, `#`, `!`, `$`). Postgres 16 a veces los interpreta mal. Alfanumérica es lo más seguro.

```sql
\c clinica
GRANT ALL ON SCHEMA public TO clinica_app;
ALTER DATABASE clinica OWNER TO clinica_app;
GRANT ALL ON DATABASE clinica TO clinica_app;
\q
```

> **⚠️ Postgres 15+ cambió los permisos del schema `public` por default.** El owner es `postgres`, así que sin los `GRANT` de arriba, `clinica_app` no puede crear tablas. Vas a ver `permission denied for schema public` cuando corras `migrate`. Esos `GRANT` lo arreglan.

> **Importante:** Reemplazá `CAMBIAR_ESTA_PASSWORD` por una contraseña fuerte y guardala aparte. La vas a poner en el `.env` del backend. Tiene que ser **la misma** que usaste en el `CREATE USER` y en el `ALTER USER`.

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

# En Ubuntu 24.04, hay que instalar python3.12-venv explícitamente.
# En 22.04 viene por defecto. Si vas a usar 24.04 y todavía no lo hiciste:
sudo apt install -y python3-pip python3.12-venv

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

# Seeds (opcional): URL del footer de los comandos de seed y guard de entorno.
# DJANGO_BASE_URL=https://<tu-dominio.com>          # default http://localhost:8000
# DJANGO_SEED_ADMIN_URL=https://admin.<tu-dominio.com/admin>   # toma precedencia sobre BASE_URL
# DJANGO_ENVIRONMENT=development                    # production bloquea seed_pdf_baseline
```

**Generar `DJANGO_SECRET_KEY`:**

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Pegá el resultado en `DJANGO_SECRET_KEY=...`.

### 5.2. Cómo poblar la base de datos

Antes de poblar, siempre corré las migraciones:

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py migrate --noinput
```

El sistema trae **4 comandos de seed** para 4 contextos distintos. Elegí el que se ajusta a tu situación.

#### Tabla comparativa

| # | Comando | Datos que crea | ¿Wipea datos existentes? | Cuándo usarlo |
|---|---|---|---|---|
| 1 | `seed_client_baseline` | 4 roles + 1 Sucursal (te la pide) + admin general (te pide user/pass) + 1 tablet kiosk (te pide código/clave) + **catálogo base** (12 modelos con precios 850/650/1500/120) | No | **Producción real de un cliente.** ⭐ Opción recomendada para deploys nuevos. |
| 2 | `seed_production_baseline` | 4 roles + 1 Sucursal fija (`Sede Principal`, La Paz) + admin fijo (`admin.general` / `admin123456`) + 1 kiosk fijo (`KIOSKO-PRINCIPAL` / `tablet-verify-123`). **Sin catálogos.** | No | Legado. Útil solo si querés arrancar con lo mínimo y cargar catálogos a mano. Reemplazado por `seed_client_baseline`. |
| 3 | `seed_pdf_baseline` | Catálogo base + 3 sucursales + 3 admins + 4 especialistas + 5 especialidades + form config + 2 prospectos + 2 pacientes demo (`INACTIVO`) + 3 kiosks. | **No** — no destructivo; solo `update_or_create` sobre natural keys. | Demo, staging, capacitación. **Rechaza correr con `DJANGO_ENVIRONMENT=production`** (ver "Guard de entorno" abajo). |
| 4 | `seed_branch_test_scenarios` | 5 pacientes + 2 especialistas móviles + 12 gastos + 3 tickets | No, pero **requiere** `seed_pdf_baseline` previo | Test manual de flujos multi-sucursal. |

---

#### Opción 1 — `seed_client_baseline` (recomendada para producción) ⭐

Comando pensado para deploys de clientes reales. Te pregunta los datos por consola (modo interactivo) o los tomá de flags (modo no-interactivo).

**Modo interactivo** — el asistente te pregunta uno por uno:

```bash
sudo -u www-data env/bin/python manage.py seed_client_baseline
```

Te va a pedir en este orden:

1. **Datos de la sucursal**: `nombre`, `ciudad`, `direccion`.
2. **Datos del admin general**: `username`, `password`, `primer_nombre`, `apellido_paterno`, `email`.
3. **Datos del kiosk**: `codigo`, `clave`.
4. **Confirmación** si ya existe una sucursal principal.

**Validaciones que aplica** (rechaza y vuelve a preguntar si no se cumplen):

- Username único (salvo que colisione con el admin target, en cuyo caso lo actualiza).
- Email con formato válido (`validate_email` de Django).
- Password ≥8 chars (corre las validators de Django: longitud, passwords comunes, numéricos, similitud al usuario).
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

| Flag | Obligatorio en no-interactive | Descripción |
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

⚠️ **Anotá las credenciales que te muestra al final.** Es la única vez que se imprimen en texto plano.

---

#### Opción 2 — `seed_production_baseline` (legado, sin catálogos)

Comando antiguo que quedó reemplazado por `seed_client_baseline`. Crea los mismos 4 registros básicos pero con valores fijos y sin catálogos.

```bash
sudo -u www-data env/bin/python manage.py seed_production_baseline
```

| Registro | Valor | Notas |
|---|---|---|
| 4 roles | `ADMIN_PRINCIPAL`, `ADMIN_SUCURSAL`, `TRABAJADOR`, `CLIENTE` | `accounts/management/commands/seed_production_baseline.py:34-40` |
| 1 Sucursal | `Sede Principal` (ciudad: `La Paz`, `es_principal=True`, `activa=True`) | Renombrá esto en el admin apenas entres. |
| 1 Usuario admin | `admin.general` / `admin123456` (superuser) | **CAMBIAR LA PASSWORD EN EL PRIMER LOGIN.** |
| 1 Tablet kiosk | `KIOSKO-PRINCIPAL` / `tablet-verify-123` | **CAMBIAR LA CLAVE.** El save hashea automáticamente. |

**No se crean catálogos**. Vas a tener que cargarlos manualmente desde `/admin/` (Tipo de servicio, Procedimientos estéticos, Servicios con precio, Antecedentes médicos, Especialidades, Sectores, etc.) o correr `seed_client_baseline` después.

**Cuándo usarlo:** solo si necesitás el mínimo absoluto y preferís cargar catálogos a mano. Para producción de un cliente, **preferí siempre `seed_client_baseline`**.

---

#### Opción 3 — `seed_pdf_baseline` (solo demo, NO en producción)

```bash
sudo -u www-data env/bin/python manage.py seed_pdf_baseline
```

Útil para demos, staging, o capacitar a un cliente sobre cómo se ve el sistema poblado. Crea lo mismo que `seed_client_baseline` en términos de catálogo, **más**:

- 2 Sucursales extra: `Sucursal Norte` (La Paz), `Sucursal Sur` (Santa Cruz).
- 4 Admins: `admin.general` (clean), `admin.norte`, `admin.sur`, **`admin.demo`** (D6 — administrador dedicado para demos, todos password `admin123456`).
- 4 Especialistas (usuarios): `lucia.laser`, `diego.tatuajes`, `sofia.manchas`, `rafael.consulta` — passwords `laser123456`, `tatuajes123456`, `manchas123456`, `consulta123456`.
- 5 Especialidades + 4 Especialistas (vinculados).
- 2 Prospectos (`PASAJERO`).
- 2 Pacientes demo: `paciente.demo` / `paciente123456`, `paciente.inactivo` / `paciente123456` (ambos en estado `INACTIVO`).
- Agendas: lun–vie 08:00–18:00 para cada especialista.
- 3 Tablet kiosks: `KIOSKO-PRINCIPAL` / `tablet-principal-123`, `KIOSKO-NORTE` / `tablet-norte-123`, `KIOSKO-SUR` / `tablet-sur-123`.

**No es destructivo:** la nueva implementación solo hace `update_or_create` sobre natural keys. No llama `Model.delete()` sobre ninguna tabla operacional (las 9 tablas de `exploration.md` quedan intactas). Si necesitás arrancar de cero, la convención es vaciar la base manualmente antes de correr el seed.

**Guard de entorno:** el comando aborta con `CommandError` antes de escribir nada si `settings.ENVIRONMENT` no es `development` o `test`. Por default `DJANGO_ENVIRONMENT=development` en el `.env.example` (los seeds siguen funcionando). Para bloquear el comando en producción seteá `DJANGO_ENVIRONMENT=production` en el `.env` del backend. No hay flag de override — el rechazo es duro.

**Override del footer URL:** los comandos `seed_client_baseline` y `seed_pdf_baseline` derivan la URL del footer de la configuración del proyecto. Si en el `.env` definís `DJANGO_SEED_ADMIN_URL=https://admin.tu-dominio.com/admin` se usa esa URL exacta (con normalización de slashes). Si está vacía, se usa `DJANGO_BASE_URL + "/admin"` (default `http://localhost:8000`). Ambos comandos fallan con `CommandError` antes de tocar la base si ninguna de las dos es una URL `http(s)://` válida.

---

#### Opción 4 — `seed_branch_test_scenarios` (test multi-sucursal)

Capa adicional para testear flujos multi-sucursal. **Requiere `seed_pdf_baseline` previo** (si no, falla con `RuntimeError`).

```bash
sudo -u www-data env/bin/python manage.py seed_branch_test_scenarios
```

Agrega:

- 5 Pacientes (`paciente.multisucursal`, `paciente.importable`, `paciente.importable.libre`, `paciente.norte`, `paciente.sur`) — todos password `paciente123456`.
- 2 Especialistas móviles (`especialista.movible.norte`, `especialista.movible.sur`) — password `especialista123456`.
- 12 `GastoSucursal` (abril–mayo 2026, 6 por sucursal).
- 3 `Ticket` con sus `TicketMessage`.

**Solo para dev/test. No en producción.**

---

#### Catálogo base que cargan `seed_client_baseline` y `seed_pdf_baseline`

Ambos comandos cargan la misma tabla de catálogo base. La diferencia es que `seed_client_baseline` te deja configurar la sucursal y admin con datos propios, y `seed_pdf_baseline` carga datos demo extra (sucursales, especialistas, pacientes, agendas).

Los **12 modelos** que ambos cargan:

| Modelo | Cantidad | Registros clave |
|---|---|---|
| `TipoServicio` | 2 | `Cita de consulta`, `Tratamiento estético` |
| `CategoriaGasto` | 8 | `Alquiler`, `Servicios`, `Insumos`, `Equipamiento`, `Marketing`, `Sueldos`, `Mantenimiento`, `Otros` |
| `ProcEsteticosTipo` | 1 | `Laser` |
| `ProcEstetico` | 3 | `Depilacion definitiva`, `Tratamiento de manchas`, `Borrado de tatuajes` |
| `ServicioConfig` | 4 | **Precios base**: Consulta → **120**, Depilación → **850**, Manchas → **650**, Tatuajes → **1500** |
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

---

#### Verificación rápida post-seed

```bash
# ¿Gunicorn puede arrancar?
sudo -u www-data env/bin/python manage.py check

# ¿La DB responde?
sudo -u www-data env/bin/python manage.py shell -c "from accounts.models import Usuario; print('Usuarios:', Usuario.objects.count())"
sudo -u www-data env/bin/python manage.py shell -c "from catalogs.models import Sucursal, ProcEstetico, ServicioConfig; print('Sucursales:', Sucursal.objects.count(), 'Procedimientos:', ProcEstetico.objects.count(), 'Servicios:', ServicioConfig.objects.count())"
```

Después de esto:

```bash
# Archivos estáticos
sudo -u www-data env/bin/python manage.py collectstatic --noinput
```

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

> **⚠️ Si tu droplet tiene 1 GB de RAM o menos**, el build puede tirarse por OOM (Out of Memory). Si `npm ci` o `npm run build` muestra `Killed` o `JavaScript heap out of memory`, agregá swap temporal:
>
> ```bash
> sudo fallocate -l 2G /swapfile
> sudo chmod 600 /swapfile
> sudo mkswap /swapfile
> sudo swapon /swapfile
> free -h   # verificar que Swap muestre 2G
> ```
>
> Reintentá `npm ci` y `npm run build`. Al terminar, podés eliminar el swap:
>
> ```bash
> sudo swapoff /swapfile
> sudo rm /swapfile
> ```
>
> Si con 2 GB de swap sigue tirando OOM, probá con 3 GB.

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

> **⚠️ Antes de correr certbot, asegurate de que el dominio ya apunta a la IP del droplet.** Si no, Let's Encrypt no puede validar el dominio y el comando falla. Verificá con:
>
> ```bash
> dig +short tu-dominio.com
> # Debe devolver la IP del droplet
> ```
>
> Si usás Cloudflare, dejá el proxy desactivado (DNS only, gris) durante el cert — después lo podés volver a activar.

```bash
sudo certbot --nginx -d tu-dominio.com -d www.tu-dominio.com
```

Certbot te va a pedir:
1. **Email**: el tuyo, para avisos de renovación.
2. **Acepta los ToS**: `Y`.
3. **Compartir email con EFF**: `Y` o `N`, no importa.
4. **Redirigir HTTP a HTTPS**: `2` (redirect).

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

### 400 Bad Request en `/admin/` o `/api/`

Django rechaza el `Host` header. Verificá que el dominio (o IP) que estás usando esté en `DJANGO_ALLOWED_HOSTS` del `.env`:

```bash
cat /var/www/clinica/backend/.env | grep ALLOWED_HOSTS
```

Si no está, agregalo y reiniciá:

```bash
sudo systemctl restart gunicorn
```

### Error de migraciones

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py showmigrations
sudo -u www-data env/bin/python migrate
```

### Error: `psycopg.OperationalError: connection to server failed: FATAL: password authentication failed for user "clinica_app"`

Postgres 16 (Ubuntu 24.04) rechazando la password por usar `scram-sha-256`. Ver la sección 3 — cambiar `pg_hba.conf` a `md5` y resetear la password.

### Error: `permission denied for schema public` durante `migrate`

Postgres 15+ asigna el schema `public` al usuario `postgres` por default. Hay que dar permisos explícitos. Ver sección 3 — el bloque con `GRANT ALL ON SCHEMA public TO clinica_app`.

### Error: `python3 -m venv env` falla con "ensurepip is not available"

En Ubuntu 24.04, `python3-venv` no trae `ensurepip` por defecto. Instalá:

```bash
sudo apt install -y python3.12-venv
```

### Error: `npm ci` o `npm run build` muestra `Killed` o `JavaScript heap out of memory`

OOM. Ver sección 6 — agregar swap temporal de 2–3 GB.

### Error: `sudo: command not found` o `sudo: unable to resolve host`

Normal en droplets recién creados. Andá a sección 2 — agregar `deploy` al grupo `sudo` y la línea NOPASSWD.

### `certbot` o `nginx` no encontrados

Algún paquete del `apt install` de la sección 2 falló. Reintentá:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

### `ssh-copy-id` rechaza con `Permission denied (publickey)`

La SSH key que subiste al crear el droplet no coincide con la que tenés ahora en tu máquina. Ver el bloque de la sección 2 sobre cómo inyectar la key por la consola web del proveedor.

### Cambié el `.env` y nada se actualiza

Gunicorn NO recarga al cambiar el `.env`. Hay que reiniciar:

```bash
sudo systemctl restart gunicorn
```

### Olvidé la contraseña del admin

```bash
cd /var/www/clinica/backend
sudo -u www-data env/bin/python manage.py changepassword <username>
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
| `3332186` | Deploy script interactivo: pide VPS_HOST, PROJECT_PATH, etc. la primera vez y los guarda en `scripts/.deploy-config`. Arregla bug de paths hardcoded en el heredoc SSH. |
| `33d67c4` | Changelog footer en la guía. |
| `7f47e40` | Reorganiza la sección 5.2 con una sección dedicada "Cómo poblar la base de datos" con tabla comparativa de los 4 seeds. Corrige gaps del deploy en DO: `sudo` NOPASSWD para `deploy`, `pg_hba.conf` md5, `GRANT ON SCHEMA public`, `python3.12-venv`, swap para Node build, DNS antes de certbot, troubleshooting extendido. |

Si la guía quedó desactualizada respecto al código, este es el bloque a actualizar. Buscá la sección correspondiente en la tabla de arriba y en el diff del commit.

## Próximos pasos para producción real

Esta guía deja el sistema funcionando, pero para un cliente final **se recomienda**:

1. **Migrar a un PaaS** (Railway, Render) o usar **DB administrada** (Supabase, RDS) para recibir backups, monitoreo y SSL administrado.
2. **Mover archivos media** (QR, PDFs) a S3-compatible en lugar de disco local.
3. **Sumar CDN** (Cloudflare) delante del VPS.
4. **Sumar rate limiting** en Nginx (`limit_req_zone`) para la API.
5. **Revisar `docs/verification-contract-v2.md`** y demás specs periódicamente: la guía asume que el código está estable. Cambios grandes requieren actualizar la guía.
