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
# explícitamente.
#
# ⚠️ Node.js NO se instala desde el repo de Ubuntu. El paquete `nodejs`
# de Ubuntu 24.04 es Node 18, y Vite 8 (frontend) requiere Node ≥20.19.
# Si instalás el Node 18 de Ubuntu, `npm run build` falla con
# `CustomEvent is not defined` y ReferenceError en vite/cli.js.
#
# Instalá Node 20 desde NodeSource ANTES del resto:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -

apt install -y python3 python3-pip python3-venv python3.12-venv \
               nginx certbot python3-certbot-nginx \
               postgresql postgresql-contrib \
               ufw fail2ban curl git \
               nodejs

# Verificá que sea Node 20+ (Vite 8 lo requiere):
node -v   # tiene que decir v20.x.x o superior

# ⚠️ Pre-crear directorios del home de www-data. Por default /var/www/ es
# root:root (no www-data). Si no los creamos, `sudo -u www-data npm ...`
# revienta con EACCES cuando intenta escribir /var/www/.npm, /var/www/.npmrc
# y /var/www/.config durante el build del frontend.
sudo mkdir -p /var/www/.npm /var/www/.config
sudo touch /var/www/.npmrc
sudo chown -R www-data:www-data /var/www/.npm /var/www/.config /var/www/.npmrc

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
sudo systemctl restart ssh
```

> **⚠️ Si tenés problemas para entrar como `deploy` con `ssh-copy-id`**: abrí la consola web del proveedor (DigitalOcean, Hetzner, etc.) como root, y ejecutá los pasos de creación de `deploy` + copia de `authorized_keys` directamente ahí. A veces la key que subiste al crear el droplet no es la misma que tenés ahora en tu máquina local.

---

## 3. PostgreSQL

```bash
sudo -u postgres psql
```

Dentro de `psql` (cada línea es un comando separado, esperaba el `;` o el prompt antes de la siguiente):

> ⚠️ **`CAMBIAR_ESTA_PASSWORD` es un placeholder, no una contraseña real.** Reemplazá ambas apariciones (línea 107 y línea 142) por una contraseña **alfanumérica** (solo letras y números, sin `@`, `#`, `!`, `$`, `%`, `&`). Postgres 16 interpreta mal los caracteres especiales en algunos clientes. **Las dos apariciones deben ser idénticas** — es la misma contraseña que va en `DJANGO_DB_PASSWORD` del `.env` del backend.

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
sudo chown root:root /var/www
sudo chmod 755 /var/www
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

> ⚠️ **Git safe.directory para www-data.** Git 2.35+ rechaza operaciones sobre repos cuyo owner no es el usuario que corre `git`. Cuando `scripts/deploy.sh` ejecuta `sudo -u www-data git pull`, va a tirar:
>
> ```
> fatal: detected dubious ownership in repository at '/var/www/clinica'
> ```
>
> Solución: agregar `/var/www/clinica` al `safe.directory` global de www-data. Como `/var/www/.gitconfig` no existe por default, hay que crearlo:
>
> ```bash
> sudo touch /var/www/.gitconfig
> sudo chown www-data:www-data /var/www/.gitconfig
> sudo -u www-data git config --file /var/www/.gitconfig --add safe.directory /var/www/clinica
> ```
>
> Verificá:
>
> ```bash
> sudo -u www-data cat /var/www/.gitconfig
> # [safe]
> #         directory = /var/www/clinica
> ```

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

> ⚠️ **Estas variables tienen dependencias cruzadas que no son obvias:** `DJANGO_CSRF_COOKIE_SECURE` y `DJANGO_SESSION_COOKIE_SECURE` dependen de tener HTTPS. Si entrás por HTTP (sin dominio o sin certbot), los browsers **rechazan los cookies con `Secure=1`** y no podés loguear (login devuelve `403 CSRF verification failed` aunque el endpoint funcione con `curl`).
>
> **Regla práctica:**
>
> | Setup | `DJANGO_CSRF_COOKIE_SECURE` | `DJANGO_SESSION_COOKIE_SECURE` | `DJANGO_CORS_ALLOWED_ORIGINS` | `DJANGO_CSRF_TRUSTED_ORIGINS` |
> |---|---|---|---|---|
> | HTTP (sin dominio, prueba local) | `0` | `0` | `http://<VPS_IP>` | `http://<VPS_IP>` |
> | HTTPS (producción con dominio + certbot) | `1` | `1` | `https://<tu-dominio.com>` | `https://<tu-dominio.com>` |
>
> **Síntomas típicos de `Secure=1` mal configurado sin HTTPS:**
>
> - Login devuelve `403 Forbidden` con mensaje `La verificación CSRF ha fallado. Solicitud abortada.` desde el browser.
> - El mismo login anda perfecto si lo probás con `curl` (curl no aplica la política de `Secure`).
> - En DevTools → Network, el request POST se manda **sin** cookie `csrftoken` aunque el backend lo setee.

# Seeds (opcional): URL del footer de los comandos de seed y guard de entorno.
# DJANGO_BASE_URL=https://<tu-dominio.com>          # default http://localhost:8000
# DJANGO_SEED_ADMIN_URL=https://admin.<tu-dominio.com/admin>   # toma precedencia sobre BASE_URL
# DJANGO_ENVIRONMENT=development                    # production bloquea seed_pdf_baseline
```

**Generar `DJANGO_SECRET_KEY`:**

> ⚠️ **Este comando se ejecuta adentro del servidor, con el virtualenv activado.** No en tu máquina local (ahí no está Django instalado y vas a ver `ModuleNotFoundError: No module named 'django'`). El flujo esperado:
>
> ```bash
> ssh deploy@<VPS_IP>
> cd /var/www/clinica/backend
> source env/bin/activate
> # El prompt tiene que empezar con "(env)"
> python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```

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
| 5 | `reset_pdf_baseline` | Lo mismo que `seed_pdf_baseline` (opción 3), pero **destructivo**: primero purga datos de negocio preservando admins y luego re-seeda la demo PDF, todo dentro de **una sola transacción**. | **Sí** — wipe + reseed atómico. `TRUNCATE` en Postgres, `DELETE` por tabla en SQLite. | Reset rápido de demo/staging cuando querés volver al estado PDF inicial sin pasos manuales. Idempotente. **Rechaza correr con `DJANGO_ENVIRONMENT=production`**. |

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

> **⚠️ Si tu droplet tiene 1 GB de RAM o menos**, el build puede tirarse por OOM (Out of Memory). Si `npm ci` o `npm run build` muestra `Killed` o `JavaScript heap out of memory`, agregá swap de 2 GiB:
>
> ```bash
> sudo fallocate -l 2G /swapfile
> sudo chmod 600 /swapfile
> sudo mkswap /swapfile
> sudo swapon /swapfile
> echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
> free -h   # verificar que Swap muestre 2.0Gi
> ```
>
> **Recomendado dejarlo permanente** (la línea `echo` ya lo registra en `/etc/fstab`). En un disco de 8 GiB sobran ~3 GiB para el resto del sistema, y tener swap siempre presente previene OOMs en futuros deploys. Solo swapear bajo demanda es frágil: el próximo deploy con VPS saturado vuelve a caer igual.
>
> Si con 2 GiB sigue tirando OOM, probá con 3 GiB. Más de eso no ayuda porque el cuello pasa a ser disco, no RAM.
>
> Esta misma receta aplica cada vez que corras `scripts/deploy.sh` en un VPS chico. Ver [sección 10.2 paso 1](#paso-1--si-tu-vps-tiene-menos-de-1-gib-de-ram-caso-real-frecuente-crear-swap-de-2-gib) y el [error de Killed](#error-npm-ci-o-npm-run-build-muestra-killed-o-javascript-heap-out-of-memory) en Troubleshooting.

---

## 7. Nginx

```bash
sudo nano /etc/nginx/sites-available/clinica
```

Pegá esta configuración (reemplazá `tu-dominio.com`):

> ⚠️ **Reemplazá `tu-dominio.com` por tu dominio real, o por la IP del VPS si todavía no compraste dominio.** Si dejás el placeholder literal, Nginx no resuelve el `Host:` header y vas a ver `500 Internal Server Error` o loops de rewrite en `nginx -t` (mensaje: `rewrite or internal redirection cycle while internally redirecting to "/index.html"`).
>
> Si entrás solo por IP (sin dominio), usá:
>
> ```nginx
> server_name <VPS_IP> _;
> ```
>
> El `_` es el catch-all que matchea cualquier `Host:` que Nginx reciba. Sin esto, todo request al VPS falla con loop de rewrite.

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
        # Límite de tamaño de upload: 10 MiB. Sin esta línea, Nginx usa
        # el default de 1m y rechaza comprobantes / documentos con
        # HTTP 413 Request Entity Too Large. El default de Django
        # (DATA_UPLOAD_MAX_MEMORY_SIZE 2.5 MiB) deja pasar más, así
        # que Nginx es el cuello de botella. Subilo si tu clínica
        # necesita videos o PDFs pesados; 10m cubre fotos decentes
        # de celular y escaneos livianos.
        client_max_body_size 10m;
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

> ⚠️ **El servicio se crea en este paso.** Si intentás `sudo systemctl restart gunicorn` antes de llegar acá (por ejemplo, después de editar el `.env` en la sección 5.1), te va a tirar `Unit gunicorn.service not found`. Es esperable, no es un error de tu setup. El servicio no existe hasta que lo crees con los pasos de abajo.

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

## 10. Actualizar el sistema en producción (deploy de cambios)

> ⚠️ **Esta sección es para deploys posteriores al setup inicial.** Las secciones 0–9 se ejecutan **una sola vez** cuando creás el VPS desde cero. La sección 10 se ejecuta **cada vez que quieras subir cambios de código al VPS ya configurado** (bugfixes, features, migraciones nuevas, etc.).

Una vez que el VPS está corriendo, mantener el sistema actualizado es automático con `scripts/deploy.sh`.

### 10.1. Deploy normal (pull + restart)

**El estado por defecto de este proyecto es producción estable**: biometría activa, sin flags de suspensión inyectados. Antes de fixear esto el script activaba el flag `BIOMETRIC_SUSPENDED=1` por defecto; ahora **el default es `0`** (producción normal) y `BIOMETRIC_SUSPENDED=1` es una elección **explícita** del operador (ver 10.2). Si tu deploy no toca biometría, podés correr el script tal como está.

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
BIOMETRIC_SUSPENDED (1=forward, 0=produccion) [0]: <enter>
```

> ⚠️ **¿Te equivocaste en alguna respuesta del wizard?** El config se guarda en `scripts/.deploy-config`. Para volver al wizard desde cero:
>
> ```bash
> rm scripts/.deploy-config
> ./scripts/deploy.sh
> ```
>
> El archivo está en `.gitignore`, así que se puede borrar y regenerar sin afectar el repo. No hay confirmación previa — el próximo `./scripts/deploy.sh` te pregunta todo de nuevo.

Después de la primera corrida, los valores quedan en `scripts/.deploy-config` y no se vuelven a preguntar. Para cambiar uno:

```bash
nano scripts/.deploy-config
```

O borrá el archivo y volvé a correr el script.

**Variables guardadas en `scripts/.deploy-config`:**

| Variable | Default | Cuándo cambiarla |
|---|---|---|
| `VPS_HOST` | (vacío, obligatorio) | Primera vez. Luego queda guardada. |
| `VPS_USER` | `deploy` | Si creaste otro usuario SSH. |
| `PROJECT_PATH` | `/var/www/clinica` | Si instalaste en otro path. |
| `DOMAIN` | (vacío) | Para que el script verifique HTTP 200 al final. |
| `GIT_BRANCH` | `main` | Si deployás desde otra rama. |
| `GIT_REPO` | (vacío) | Si querés que valide que el remote coincida. |
| `BIOMETRIC_SUSPENDED` | `0` | Solo si vas a hacer forward de la suspensión (ver 10.2). |
| `VITE_BIOMETRIC_SUSPENDED` | derivado de `BIOMETRIC_SUSPENDED` | Casi nunca. Solo si necesitás divergir ambos flags. |

**Modo no-interactivo** (para CI o scripts automatizados): si `scripts/.deploy-config` ya existe con todos los valores (incluido `VPS_HOST`), el script no pregunta nada. Si lo invocás desde un entorno sin TTY sin config previa, usa los defaults sin preguntar — `VPS_HOST` queda vacío y el SSH falla con error claro, no se inventa nada.

**Lo que hace el deploy, en orden:**

1. `git pull` en el VPS a la rama configurada.
2. `pip install -r requirements.txt` (dependencias Python del backend).
3. Setea el flag de `BIOMETRIC_SUSPENDED` en `backend/.env` (idempotente: si ya tiene el mismo valor, no hace nada; si difiere, lo edita in-place con `sed`).
4. Reinicia Gunicorn.
5. **Validación gateada del backend** (ver 10.4): si hay cookie jar de admin, hace un POST al endpoint biométrico y compara contra el código HTTP esperado (503 si forward, ≠503 si rollback). **Si la validación se ejecuta y el código no coincide con lo esperado, aborta el deploy con `exit 1`.** Si no hay cookie jar, la validación se saltea.
6. `npm ci` + `npm run build` del frontend con `VITE_BIOMETRIC_SUSPENDED` horneado en el bundle.
7. `manage.py migrate --noinput` (aplica todas las pendientes — no requiere acción manual).
8. `manage.py collectstatic --noinput`.
9. `nginx -t` para verificar la config.
10. (Si `DOMAIN` está seteado) `curl https://$DOMAIN/` y reporta HTTP 200/!200.
11. Imprime la rama desplegada, el SHA local, y los flags usados como footer.

**Advertencia sobre el paso 5 (validación que aborta):** Si vas a hacer **forward** (ver 10.2) y la cookie jar de admin no se generó o venció, la validación gateada puede devolver 401, 403 o 404. El script aborta con `exit 1` y `Deploy remoto` se interrumpe. El bundle del frontend y el `migrate/collectstatic` no llegan a ejecutarse. Soluciones:

- No uses forward si no tenés biometría activa (10.2 es opcional hoy).
- Generá el cookie jar antes con `curl -c /tmp/clinica-deploy-cookie -X POST ... /api/auth/login/ ...`.

### 10.2. Suspender la integración biométrica (forward)

> ⚠️ **Este es un escenario opcional de rollout.** El default del proyecto es `BIOMETRIC_SUSPENDED=0`, es decir, biometría activa. Pasalo a `1` solo si necesitás que la PC del lector no participe en el flujo temporalmente.

**Cuándo usar esto.** El lector DigitalPersona 4500 no está conectado, está roto, o todavía no llegó el hardware. Mientras tanto, querés que el sistema siga funcionando: las conversiones de prospecto, los pasos 4 de huella y los `Confirmar con huella` en citas deben poder **saltarse** el bloque sin pedir captura.

**Qué cambia al activar el modo suspendido:**

- **Frontend**: el botón *"Capturar huella"* desaparece del paso 4 del wizard de conversión. Aparece un banner amarillo *"Huella biometrica suspendida"*. "Guardar y continuar" avanza al paso 5 sin pedir template. En `client-detail`, las citas confirmables por huella siguen apareciendo pero el botón *"Confirmar con huella"* se reemplaza por el flujo manual.
- **Backend**: cualquier `POST` a `/api/biometric/*` que intente mutar (enroll, verify-init, verify-confirm) responde `HTTP 503` con código `BIOMETRIC_SUSPENDED`. Los `GET` administrativos (listado de agentes, historial de intentos) siguen respondiendo.
- **PC del lector**: si el lector y el agente local están conectados, conviene detenerlos para que no queden en estado zombie.

**Tiempo total estimado:** 10–20 min si el VPS es chico (< 1 GiB RAM), 3–5 min si es normal.

> ⚠️ **El flag `VITE_BIOMETRIC_SUSPENDED` está horneado dentro del bundle del frontend.** Eso significa que cambiar solo el `.env` del backend **no alcanza**: el frontend seguiría compilado con el flag en `false`. El script se encarga de mantenerlos sincronizados — **no los cambies a mano en `.env` sin redesplegar**.

#### Procedimiento

**Paso 1 — Si tu VPS tiene menos de 1 GiB de RAM (caso real frecuente), crear swap de 2 GiB.**

Antes de correr el deploy, en el VPS vía SSH como `deploy` (con `sudo`):

```bash
ssh deploy@<VPS_IP>
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # verificá que la línea Swap muestre 2.0Gi
```

Salida esperada:

```
Mem:           458Mi total
Swap:          2.0Gi total
NAME      TYPE SIZE
/swapfile file 2G
```

> **¿Por qué?** El `npm run build` dentro del `deploy.sh` invoca `tsc -b && vite build`. Con menos de 1 GiB de RAM y sin swap, el OOM killer del kernel mata el proceso en mitad del build y deja `dist/` incompleto. El swap de 2 GiB es suficiente para sobrevivir el pico típico de `tsc -b` (1.5–2 GiB). **Dejarlo permanente vía fstab** es OK y recomendado: 2 GiB de swap en un disco de 8 GiB sobra espacio y solo se usa bajo presión de RAM.
>
> Si con 2 GiB sigue cayendo, ver [Troubleshooting / OOM al construir](#error-npm-ci-o-npm-run-build-muestra-killed-o-javascript-heap-out-of-memory) abajo.

**Paso 2 — Disparar el deploy desde tu laptop.**

En tu máquina local, en la raíz del repo:

```bash
cd /ruta/al/repo
BIOMETRIC_SUSPENDED=1 VITE_BIOMETRIC_SUSPENDED=true ./scripts/deploy.sh
```

> **Atajo:** el helper `scripts/biometric_suspension.sh` setea los flags por vos y emite el deploy:
>
> ```bash
> ./scripts/biometric_suspension.sh prod on
> ```
>
> Si querés ver el estado actual antes de tocar nada: `./scripts/biometric_suspension.sh status`.

Salida esperada, en orden:

```
[STEP] BIOMETRIC_SUSPENDED=1 VITE_BIOMETRIC_SUSPENDED=true
=== 1. Pull últimos cambios ===
=== 3. Activar flag backend en backend/.env ===
  -> BIOMETRIC_SUSPENDED=1 aplicado a backend/.env
=== 4. Reiniciar Gunicorn ===
=== 5. Validación gateada (POST /api/biometric/citas/<id>/huella/verify-init/) ===
  HTTP 503
  {"detail":"...","code":"BIOMETRIC_SUSPENDED",...}
  -> OK: gate activo, 503 BIOMETRIC_SUSPENDED
=== 6. Build frontend ===
... (tarda 5-15 min con swap, 1-3 min sin swap) ...
✓ built in <tiempo>
=== 7. Migraciones ===
=== 9. Verificar Nginx ===
[STEP] Sitio responde OK (HTTP 200)
  Rama desplegada: main
  SHA local:       <hash>
  BIOMETRIC_SUSPENDED=1 VITE_BIOMETRIC_SUSPENDED=true
```

**Tres líneas para mirar sí o sí:**

- `-> OK: gate activo, 503 BIOMETRIC_SUSPENDED` (en el paso 5) — confirma que el backend está rechazando mutaciones como se espera.
- `BIOMETRIC_SUSPENDED=1 aplicado a backend/.env` — confirma que el flag se escribió.
- `Sitio responde OK (HTTP 200)` — confirma que Nginx sigue sirviendo bien.

**Si alguna falla:** ver [Troubleshooting / El deploy aborta en la fase 6](#error-npm-ci-o-npm-run-build-muestra-killed-o-javascript-heap-out-of-memory) abajo. Si la falla es en el paso 5 (validación), ver 10.4.

**Paso 3 — Validar el bundle nuevo en el VPS.**

Confirmá que el bundle del frontend tiene la suspensión horneada (Vite reemplaza `import.meta.env.VITE_BIOMETRIC_SUSPENDED` por el valor literal al build):

```bash
ssh deploy@<VPS_IP> -- '
ls /var/www/clinica/frontend/aesthetic-clinic/dist/assets/*.js
# Tomá el hash del archivo que aparece (ej: index-DVa20IfX.js), y verificá:
grep -c "biometricSuspended" /var/www/clinica/frontend/aesthetic-clinic/dist/assets/index-<hash>.js
# Esperado: un número ≥ 2
'
```

**Paso 4 — Hard refresh en el navegador del admin.**

`Ctrl+Shift+R` (Linux/Windows) o `Cmd+Shift+R` (Mac). Sin esto, el navegador puede seguir sirviendo el bundle viejo en caché y vas a ver el botón "Capturar huella" que ya no debería estar.

**Paso 5 — Verificar el banner en pantalla.**

Abrí el flujo `Convertir prospecto` → paso 4. Tendrías que ver:

- Banner amarillo: *"Huella biometrica suspendida."*
- El botón *"Capturar huella"* **NO aparece**.
- El texto descriptivo dice *"Podes continuar y finalizar la conversion sin huella"*.
- "Guardar y continuar" avanza al paso 5 sin pedir nada.

**Paso 6 — (Opcional) Detener el lector físico en la PC de recepción.**

Si hay una PC con el lector DigitalPersona y el agente local, conviene bajarlos para no acumular intentos fallidos:

```bash
sudo systemctl disable --now fingerprint-agent
sudo systemctl disable --now cloudflared
sudo systemctl status fingerprint-agent --no-pager
```

`disable --now` **no borra** unidades ni archivos — sólo detiene y deshabilita. Para volver a habilitar: `sudo systemctl enable --now fingerprint-agent cloudflared`.

### 10.3. Re-habilitar la integración biométrica (rollback)

**Cuándo usar esto.** Ya tenés el lector DigitalPersona 4500 conectado y funcionando, o querés volver al flujo normal con captura obligatoria para un cliente o prospecto específico.

**Qué cambia al desactivar el modo suspendido:**

- **Frontend**: el botón *"Capturar huella"* vuelve al paso 4. El banner amarillo desaparece. "Guardar y continuar" exige un template válido (no se puede saltar).
- **Backend**: los endpoints `/api/biometric/*` vuelven al comportamiento normal (200/4xx según estado del recurso).
- **PC del lector**: el servicio `fingerprint-agent` y el túnel `cloudflared` se vuelven a iniciar.

**Tiempo total estimado:** 3–10 min en un VPS chico (la build del frontend es lo que más tarda).

#### Procedimiento

**Paso 1 — Disparar el deploy desde tu laptop con los flags en `0`/`false`.**

```bash
cd /ruta/al/repo
BIOMETRIC_SUSPENDED=0 VITE_BIOMETRIC_SUSPENDED=false ./scripts/deploy.sh
```

> **Atajo:** `./scripts/biometric_suspension.sh prod off` (setea los flags por vos y emite el deploy).
>
> **Atajo reverso** si querés ver el estado actual antes de tocar nada: `./scripts/biometric_suspension.sh status`.

**Salida esperada**, igual que en 10.2 paso 2 pero con:

```
[STEP] BIOMETRIC_SUSPENDED=0 VITE_BIOMETRIC_SUSPENDED=false
...
  -> BIOMETRIC_SUSPENDED=0 aplicado a backend/.env
=== 5. Validación gateada (POST /api/biometric/citas/<id>/huella/verify-init/) ===
  HTTP 404
  -> OK: gate inactivo, respuesta 404
...
✓ built in <tiempo>
...
Sitio responde OK (HTTP 200)
```

**Tres líneas para mirar sí o sí:**

- `-> OK: gate inactivo, respuesta <código>` — confirma que el backend ya NO está rechazando mutaciones.
- `BIOMETRIC_SUSPENDED=0 aplicado a backend/.env` — confirma que el flag se volvió a 0.
- `Sitio responde OK (HTTP 200)` — confirma Nginx.

> **Si tu VPS tiene < 1 GiB de RAM**, asegurate de tener el swap del Paso 1 de la sección 10.2 creado antes del deploy. Sin swap, `tsc -b` puede morir con `Killed` a mitad del build. Misma receta:
>
> ```bash
> sudo fallocate -l 2G /swapfile
> sudo chmod 600 /swapfile
> sudo mkswap /swapfile
> sudo swapon /swapfile
> echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
> ```
>
> Recomendado dejarlo permanente (idéntico a 10.2).

**Paso 2 — Hard refresh en el navegador del admin.**

`Ctrl+Shift+R` (Linux/Windows) o `Cmd+Shift+R` (Mac). Sin esto, el navegador sirve el bundle viejo y el banner amarillo seguirá apareciendo aunque ya no debería.

**Paso 3 — Verificar que el botón "Capturar huella" volvió al paso 4.**

Abrí `Convertir prospecto` → paso 4. Tendrías que ver:

- **No** aparece el banner amarillo *"Huella biometrica suspendida"*.
- El botón *"Capturar huella"* **sí aparece**.
- Si le das a "Guardar y continuar" sin capturar, el front valida y aparece *"Debes capturar la huella biometrica antes de continuar"* — eso confirma que la suspensión está completamente desactivada.

**Paso 4 — (Si la PC del lector está en la clínica) Levantar el lector físico.**

En la PC de recepción:

```bash
sudo systemctl enable --now fingerprint-agent cloudflared
sudo systemctl status fingerprint-agent --no-pager
sudo systemctl status cloudflared --no-pager
```

Ambas unidades deben mostrar `active (running)`.

### 10.4. Validación gateada del backend (paso 5)

> 📌 **Esta es la pieza que cambió.** Antes: si el chequeo fallaba solo se logueaba un warning. Ahora: si el chequeo se ejecutó (porque había cookie jar) y la respuesta no coincide con lo esperado, el deploy aborta. El chequeo también se puede pasar por alto si no hay cookie jar — esa parte sigue siendo SKIP silencioso.

El script hace, en el VPS, un `POST` a `http://127.0.0.1:8000/api/biometric/citas/<id>/huella/verify-init/` con la sesión de un admin si `/tmp/clinica-deploy-cookie` existe. Usa el header `Origin: https://$DOMAIN` (no `PROJECT_PATH` — el nombre de dominio, no la ruta).

**Lo que se considera éxito:**

| Forward (`BIOMETRIC_SUSPENDED=1`) | Rollback (`BIOMETRIC_SUSPENDED=0`) |
|---|---|
| HTTP 503 con `code: BIOMETRIC_SUSPENDED` | Cualquier respuesta ≠ 503 (típicamente 200 si el flujo llega a la lógica de negocio, 404 si no hay cita con `REALIZADA_PENDIENTE_VERIFICACION`, 401/403 si sesión inválida) |

**Generar el cookie jar antes del deploy:**

```bash
# En la laptop, contra el dominio real:
ssh deploy@<VPS_IP> -- '
  curl -sS -c /tmp/clinica-deploy-cookie \
    -H "Origin: https://tu-dominio.com" \
    -H "Referer: https://tu-dominio.com/" \
    -X POST "https://tu-dominio.com/api/auth/login/" \
    -d "username=admin.x&password=..." \
    -o /dev/null
  ls -la /tmp/clinica-deploy-cookie
'
```

**Posibles respuestas y qué hacer:**

| Código de respuesta | Forward | Rollback | Diagnóstico |
|---|---|---|---|
| `503` con `code: BIOMETRIC_SUSPENDED` | ✅ OK | 🚫 Aborta | Gate activo o fuera de servicio. |
| `200` o `4xx` ≠ 503 | 🚫 Aborta | ✅ OK | Gate inactivo. |
| `401` | 🚫 Aborta (forward) / ✅ OK (rollback) | Cookie vencida o mal armada. Re-generar el cookie jar. |
| `403` | 🚫 Aborta (forward) / ✅ OK (rollback) | CSRF rechazado. Verificar que `Origin` coincide con el dominio. |
| `404` | 🚫 Aborta (forward) / ✅ OK (rollback) | No hay cita con `REALIZADA_PENDIENTE_VERIFICACION`. Ajustar `CITA_ID_REMOTA=...` antes del deploy. |

**Si querés saltarte la validación** (no recomendable): borrá el cookie jar del VPS con `ssh deploy@<VPS_IP> 'sudo rm /tmp/clinica-deploy-cookie'`. Con el archivo ausente, el script hace SKIP y no aborta.

### 10.5. Contrato backend-frontend

**Si los flags divergen**, gana el `503` del backend. Ejemplo: dejás el frontend con `VITE_BIOMETRIC_SUSPENDED=true` pero el backend con `BIOMETRIC_SUSPENDED=0` — el botón "Capturar huella" no aparece, pero si llamás al endpoint manualmente responde `200`. Inconsistencia peligrosa.

Por eso **siempre se cambian ambos en el mismo deploy**. `scripts/deploy.sh` se encarga de mantenerlos sincronizados — **no los cambies a mano en `.env` sin redesplegar**.

### 10.6. Tabla rápida de referencia

| Acción | Comando desde la laptop | Tiempo | Swap requerido |
|---|---|---|---|
| Deploy normal (producción estable) | `./scripts/deploy.sh` (responde `0` o dejá el default vacío si no TTY) | 5–15 min | sí si VPS < 1 GiB RAM |
| Forward (suspender biometría) | `./scripts/biometric_suspension.sh prod on` o `BIOMETRIC_SUSPENDED=1 VITE_BIOMETRIC_SUSPENDED=true ./scripts/deploy.sh` | 5–15 min | sí si VPS < 1 GiB RAM |
| Rollback (re-habilitar) | `./scripts/biometric_suspension.sh prod off` o `BIOMETRIC_SUSPENDED=0 VITE_BIOMETRIC_SUSPENDED=false ./scripts/deploy.sh` | 5–15 min | sí si VPS < 1 GiB RAM |
| Ver estado actual | `./scripts/biometric_suspension.sh status` | < 10 s | no |

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

OOM. Ver [sección 6, paso de swap](#%E2%9D%97-si-tu-droplet-tiene-1-gb-de-ram-o-menos-el-build-puede-tirarse-por-oom-out-of-memory-si-npm-ci-o-npm-run-build-muestra-killed-o-javascript-heap-out-of-memory-agreg%C3%A1-swap-de-2-gib) — agregar swap de 2 GiB. Recomendado dejarlo permanente vía `/etc/fstab` ([sección 10.2 paso 1](#paso-1--si-tu-vps-tiene-menos-de-1-gib-de-ram-caso-real-frecuente-crear-swap-de-2-gib)).

### Error: `413 Request Entity Too Large` al subir comprobantes o documentos (Paso 5 de conversión, subir fotos de pacientes, etc.)

Nginx está rechazando el `POST` antes de llegar al backend. Por default, Nginx corta cualquier body mayor a **1 MiB**, pero los comprobantes típicos de una clínica (fotos de transferencias bancarias desde celular, PDFs de recibos) suelen pasar ese umbral.

**Diagnóstico rápido:**

```bash
# Mirá los logs de Nginx en el momento del error
sudo tail -n 20 /var/log/nginx/clinica.error.log
```

Si ves líneas con `client intended to send too large body`, Nginx es efectivamente quien rechaza.

**Fix permanente:** agregar `client_max_body_size 10m;` dentro del bloque `location /api/ {}` en `/etc/nginx/sites-available/clinica`. La [plantilla de la sección 7](#7-nginx) ya incluye esa línea (10 MiB es el default saludable). Si la config activa no la tiene (ej. setup viejo), agregarla manualmente:

```bash
sudo nano /etc/nginx/sites-available/clinica
# agregar la línea dentro de location /api/ { ... }, junto a los proxy_set_header
```

Después recargar Nginx:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Tamaño recomendado:** 10m cubre fotos decentes de celular y PDFs normales sin permitir payloads abusivos. Subilo a 25m o 50m solo si necesitás videos cortos o escaneos pesados. Más de eso expone el VPS a DoS por uploads grandes.

**Si querés ajustar el límite sin tocar Nginx**, también podés subir los de Django en el `.env` o el settings del backend:

```python
# settings.py del backend
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MiB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MiB
```

Pero recordá que Nginx rechaza **antes** que Django, así que el cuello de botella es Nginx. Si solo tocás Django y dejás Nginx en 1m, el 413 sigue siendo el de Nginx.

### Error: `sudo: command not found` o `sudo: unable to resolve host`

Normal en droplets recién creados. Andá a sección 2 — agregar `deploy` al grupo `sudo` y la línea NOPASSWD.

### Error: `Failed to restart sshd.service: Unit sshd.service not found`

En Ubuntu 24.04+, el servicio de SSH se llama `ssh` (sin la `d` final). El archivo de config sigue siendo `/etc/ssh/sshd_config`, pero el servicio systemd es `ssh.service`. Cambio silencioso en Ubuntu reciente (el sistema usa `ssh.socket` para socket activation).

Solución:

```bash
sudo systemctl restart ssh
```

En lugar de `sudo systemctl restart sshd`. Verificá que esté corriendo con `sudo systemctl status ssh`.

### Error: `error: could not lock config file /var/www/.gitconfig: Permission denied` al configurar safe.directory

`/var/www/` debe estar owned por `root:root`, no `deploy:deploy`. Si la sección 4 (`chown deploy:deploy /var/www`) cambió el owner, `www-data` no puede escribir sus configs en `/var/www/.gitconfig`, `/var/www/.npmrc`, `/var/www/.config`, etc.

Fix de ownership:

```bash
sudo chown root:root /var/www
sudo chmod 755 /var/www
```

**Pero esto solo no alcanza.** Aunque `/var/www/` esté en `root:root 755`, el comando `sudo -u www-data git config --file /var/www/.gitconfig --add ...` sigue fallando porque git quiere **crear un `.lock` file al lado**, y www-data no tiene write en `/var/www/`.

Fix correcto: ejecutar el comando como root (que sí tiene write en el directorio) y después chownear el archivo a www-data para que sea legible:

```bash
sudo bash -c "git config --file /var/www/.gitconfig --add safe.directory /var/www/clinica"
sudo chown www-data:www-data /var/www/.gitconfig
```

Verificá que www-data lo ve:

```bash
sudo -u www-data cat /var/www/.gitconfig
# [safe]
#         directory = /var/www/clinica
```

### Error: `fatal: detected dubious ownership in repository at '/var/www/clinica'` durante `deploy.sh`

El primer deploy falla en el paso 1 (`git pull`) porque Git 2.35+ rechaza operaciones sobre un repo cuyo owner no es el usuario que ejecuta `git`. `scripts/deploy.sh` corre `sudo -u www-data git pull`, pero el owner del repo es `deploy`.

Solución: agregar `/var/www/clinica` al `safe.directory` global de `www-data`. Ver sección 4.1.

```bash
sudo touch /var/www/.gitconfig
sudo chown www-data:www-data /var/www/.gitconfig
sudo -u www-data git config --file /var/www/.gitconfig --add safe.directory /var/www/clinica
```

### Error: `npm error code EACCES` durante el build del frontend en el deploy

El paso 6 del deploy (`npm ci && npm run build`) corre con `sudo -u www-data npm ...`. Si `www-data` no puede escribir en `/var/www/.npm`, `/var/www/.npmrc` o `/var/www/.config`, npm tira `EACCES: permission denied`.

Causa: `/var/www/` está owned por `root:root` por default (lo crea Nginx/Apache al instalar). Hay que pre-crear los directorios de npm con owner `www-data` ANTES del primer deploy. Ver sección 2.

```bash
sudo mkdir -p /var/www/.npm /var/www/.config
sudo touch /var/www/.npmrc
sudo chown -R www-data:www-data /var/www/.npm /var/www/.config /var/www/.npmrc
```

### Error: `npm run build` muestra `CustomEvent is not defined` o `ReferenceError` en `vite/cli.js`

Estás corriendo Node 18 (default de Ubuntu 24.04), pero Vite 8 requiere Node ≥20.19. El error se ve así:

```
You are using Node.js 18.19.1. Vite requires Node.js version 20.19+ or 22.12+. Please upgrade your Node.js version.
ReferenceError: CustomEvent is not defined
```

Solución: instalar Node 20 desde NodeSource en lugar del `nodejs` del repo de Ubuntu. Ver sección 2.

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node -v   # tiene que decir v20.x.x
```

### Error: `deploy.sh` aborta con `El campo 'DOMAIN' es obligatorio`

Bug del script: aunque la guía dice que el dominio es opcional, `scripts/deploy.sh` aborta si la respuesta está vacía. Workaround: pasar un dominio placeholder cualquiera (no se usa para nada crítico en deploys sin HTTPS):

```bash
DOMAIN="disabled.example.com" ./scripts/deploy.sh
```

El script después intenta hacer `curl https://disabled.example.com/` que falla con `HTTP 000000`, pero como vos entrás por IP directa al VPS, no te afecta.

### Error: `deploy.sh` se saltea las preguntas y usa defaults incorrectos

El script detecta "no TTY" cuando lo corrés desde CI/CD, pipes o `bash tool`. En ese caso usa los defaults de cada pregunta sin preguntarte, lo cual puede dar valores equivocados.

Solución: pre-setear todas las variables como env vars antes de invocar el script (modo no-interactivo):

```bash
VPS_HOST="167.99.147.60" \
VPS_USER="deploy" \
PROJECT_PATH="/var/www/clinica" \
GIT_BRANCH="main" \
DOMAIN="disabled.example.com" \
GIT_REPO="https://github.com/fabianRivero/clinica-test.git" \
BIOMETRIC_SUSPENDED="0" \
VITE_BIOMETRIC_SUSPENDED="false" \
./scripts/deploy.sh
```

`BIOMETRIC_SUSPENDED=0` significa "no suspender mutaciones biométricas" (correcto para deploys que no usan biometría).

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
| `b4945b3` + cambios posteriores | Sección 10 dividida en 10.1 (deploy normal), 10.2 (suspender biométrica) y 10.3 (rollback). Documenta el flujo `BIOMETRIC_SUSPENDED` + `VITE_BIOMETRIC_SUSPENDED`, el helper `scripts/biometric_suspension.sh`, la validación post-deploy con `curl` + cookie/CSRF, y los comandos systemd de la PC del lector. Menciona las migraciones nuevas que se aplican automáticamente (`biometric/0001-0003`, `customers/0010-0012`, `catalogs/0007`, `operations/0025`). |
| `en curso` | Sección 10.2 y 10.3 reescritas paso a paso (swap permanente, 6 pasos forward, 4 rollback, tabla de referencia). Bloque `location /api/ {}` de la sección 7 con `client_max_body_size 10m;` documentado. Nuevo ítem en Troubleshooting para `413 Request Entity Too Large` con receta de Nginx vs Django y tamaño recomendado. |

Si la guía quedó desactualizada respecto al código, este es el bloque a actualizar. Buscá la sección correspondiente en la tabla de arriba y en el diff del commit.

## Próximos pasos para producción real

Esta guía deja el sistema funcionando, pero para un cliente final **se recomienda**:

1. **Migrar a un PaaS** (Railway, Render) o usar **DB administrada** (Supabase, RDS) para recibir backups, monitoreo y SSL administrado.
2. **Mover archivos media** (QR, PDFs) a S3-compatible en lugar de disco local.
3. **Sumar CDN** (Cloudflare) delante del VPS.
4. **Sumar rate limiting** en Nginx (`limit_req_zone`) para la API.
5. **Revisar `docs/verification-contract-v2.md`** y demás specs periódicamente: la guía asume que el código está estable. Cambios grandes requieren actualizar la guía.
