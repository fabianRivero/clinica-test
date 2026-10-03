# Guía: Levantar el sistema en un VPS Linux desde cero

## Clínica Estética — Deployment genérico en VPS

> **Reemplaza:** `docs/droplet-setup-from-scratch.md` (que estaba acoplada a DigitalOcean con credenciales hardcodeadas).
> **Compatible con:** cualquier VPS Linux con `sudo` — DigitalOcean, Hetzner, AWS Lightsail, Vultr, Linode, OVH, Contabo, GCP Compute Engine, Azure VM, etc.
> **OS:** Ubuntu 22.04 LTS o 24.04 LTS (`Debian 12` también funciona con mínimos cambios). El setup asume Ubuntu.
> **Tiempo estimado:** 20–40 minutos sobre un VPS recién creado.
> **Audiencia:** operador que despliega el sistema por primera vez o resetea un VPS existente. Asume familiaridad básica con Linux + SSH.

> **¿Buscás solo una sección específica?** Usá el índice al final. ¿Venís de la versión vieja? Mirá el [Anexo A — Tabla comparativa de cambios](#anexo-a--tabla-comparativa-de-cambios-desde-la-versión-anterior) primero.

---

## Índice

- [0. Prerrequisitos en tu máquina local](#0-prerrequisitos-en-tu-máquina-local)
- [1. Crear el VPS](#1-crear-el-vps)
- [2. Acceso inicial y hardening básico](#2-acceso-inicial-y-hardening-básico)
- [3. PostgreSQL](#3-postgresql)
- [4. Clonar el repositorio](#4-clonar-el-repositorio)
- [5. Backend (Django)](#5-backend-django)
- [6. Frontend](#6-frontend)
- [7. Nginx](#7-nginx)
- [8. SSL con Let's Encrypt](#8-ssl-con-lets-encrypt)
- [9. Gunicorn como servicio systemd](#9-gunicorn-como-servicio-systemd)
- [10. Actualizar el sistema en producción (deploy de cambios)](#10-actualizar-el-sistema-en-producción-deploy-de-cambios)
- [11. Post-instalación obligatorio](#11-post-instalación-obligatorio)
  - [11.1. Cambiar credenciales del seed](#111-cambiar-todas-las-credenciales-del-seed)
  - [11.2. Backups de la base de datos](#112-backups-de-la-base-de-datos)
  - [11.3. Sync externa de backups](#113-subir-backups-a-un-lugar-fuera-del-vps)
  - [11.4. Alertas mínimas](#114-configurar-alertas-mínimas)
  - [11.5. Actualizaciones de seguridad automáticas](#115-configurar-actualizaciones-de-seguridad-automáticas)
  - [11.6. Compliance legal](#116-datos-sensibles-consideraciones-legales)
  - [11.7. Cutover a AWS S3](#117-cutover-a-aws-s3-en-producción-storage_providers3)
  - [11.8. Almacenamiento en digital bucket (AWS S3)](#118-almacenamiento-en-digital-bucket-aws-s3)
- [12. Comandos útiles del día a día](#12-comandos-útiles-del-día-a-día)
- [13. Troubleshooting](#13-troubleshooting)
- [14. Resumen de archivos configurados](#14-resumen-de-archivos-configurados)
- [15. Estructura final en el VPS](#15-estructura-final-en-el-vps)
- [Anexo A — Tabla comparativa de cambios](#anexo-a--tabla-comparativa-de-cambios-desde-la-versión-anterior)
- [Anexo B — Variables de entorno del backend](#anexo-b--variables-de-entorno-del-backend)
- [Anexo C — Management commands del proyecto](#anexo-c--management-commands-del-proyecto)
- [Historial de cambios](#historial-de-cambios)

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

> ⚠️ **`CAMBIAR_ESTA_PASSWORD` es un placeholder, no una contraseña real.** Reemplazá ambas apariciones (línea de `CREATE USER` y línea de `ALTER USER`) por una contraseña **alfanumérica** (solo letras y números, sin `@`, `#`, `!`, `$`, `%`, `&`). Postgres 16 interpreta mal los caracteres especiales en algunos clientes. **Las dos apariciones deben ser idénticas** — es la misma contraseña que va en `DJANGO_DB_PASSWORD` del `.env` del backend.

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

> ⚠️ **Backend debe correr en WSL, no en PowerShell nativo.** El módulo `backups.services` (transitivo vía `INSTALLED_APPS`) importa `fcntl`, que es POSIX-only. En PowerShell nativo, `manage.py` falla con `ModuleNotFoundError: No module named 'fcntl'`. Si necesitás correr el backend en Windows, usá WSL bash. Esto es solo para desarrollo local — el deploy de producción está cubierto en [sección 9](#9-gunicorn-como-servicio-systemd) y no se ve afectado.

### 5.1. Crear `.env`

Copiá la plantilla `backend/.env.example` y editá los valores:

```bash
cp .env.example .env
nano .env
```

Variables **obligatorias** que tenés que setear (referencia rápida — la lista completa está en el [Anexo B](#anexo-b--variables-de-entorno-del-backend)):

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

# Storage (cloud-storage-migration — slice 1+2)
STORAGE_PROVIDER=local                    # local | s3
AWS_S3_REGION_NAME=sa-east-1              # o us-east-2 según tu bucket
MEDIA_LOCAL_FALLBACK_ENABLED=true         # false post-cutover
MEDIA_SIGNED_URL_TTL_SECONDS=900

# Backups (ver docs/backups.md para detalles)
BACKUPS_DIR=/var/lib/clinica/backups
BACKUP_DAILY_KEEP=7
BACKUP_WEEKLY_KEEP=4
```

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

> ⚠️ **`STORAGE_PROVIDER` solo acepta `local` o `s3`.** El valor `supabase` que aparecía en versiones viejas del `.env.example` ya no se acepta (eliminado en el slice 1 de cloud-storage-migration). Si ves código que menciona supabase storage, es de antes de Q4 2026.

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

> ⚠️ **Hay 13 management commands en el proyecto.** La tabla abajo cubre los 9 más usados en operaciones. La lista completa con ayuda corta está en el [Anexo C](#anexo-c--management-commands-del-proyecto).

#### Tabla comparativa de seeds (los 4 principales)

| # | Comando | Datos que crea | ¿Wipea datos existentes? | Cuándo usarlo |
|---|---|---|---|---|
| 1 | `seed_client_baseline` | 4 roles + 1 Sucursal (te la pide) + admin general (te pide user/pass) + 1 tablet kiosk (te pide código/clave) + **catálogo base** (12 modelos con precios 850/650/1500/120) | No | **Producción real de un cliente.** ⭐ Opción recomendada para deploys nuevos. |
| 2 | `seed_production_baseline` | 4 roles + 1 Sucursal fija (`Sede Principal`, La Paz) + admin fijo (`admin.general` / `admin123456`) + 1 kiosk fijo (`KIOSKO-PRINCIPAL` / `tablet-verify-123`). **Sin catálogos.** | No | Legado. Útil solo si querés arrancar con lo mínimo y cargar catálogos a mano. Reemplazado por `seed_client_baseline`. |
| 3 | `seed_pdf_baseline` | Catálogo base + 3 sucursales + 3 admins + 4 especialistas + 5 especialidades + form config + 2 prospectos + 2 pacientes demo (`INACTIVO`) + 3 kiosks. | **No** — no destructivo; solo `update_or_create` sobre natural keys. | Demo, staging, capacitación. **Rechaza correr con `DJANGO_ENVIRONMENT=production`** (ver "Guard de entorno" abajo). |
| 4 | `seed_branch_test_scenarios` | 5 pacientes + 2 especialistas móviles + 12 gastos + 3 tickets | No, pero **requiere** `seed_pdf_baseline` previo | Test manual de flujos multi-sucursal. |
| 5 | `reset_pdf_baseline` | Lo mismo que `seed_pdf_baseline`, pero **destructivo**: primero purga datos de negocio preservando admins y luego re-seeda la demo PDF, todo dentro de **una sola transacción**. | **Sí** — wipe + reseed atómico. `TRUNCATE` en Postgres, `DELETE` por tabla en SQLite. | Reset rápido de demo/staging cuando querés volver al estado PDF inicial sin pasos manuales. Idempotente. **Rechaza correr con `DJANGO_ENVIRONMENT=production`**. |

> **Otros 5 commands que el operador puede necesitar** (lista corta — el Anexo C tiene la descripción completa):
>
> | Comando | Para qué sirve |
> |---|---|
> | `ensure_main_branch` | Crea o normaliza `Sede Principal` sin tocar datos clínicos. Útil cuando la sucursal principal se borró por error. |
> | `purge_data_keep_admin` | Vacía datos de negocio preservando usuarios administradores. Hace el wipe de `reset_pdf_baseline` sin el reseed. |
> | `reset_extended_demo` | Variante extendida de `reset_pdf_baseline` que agrega un 5° especialista (`valentina.derma`), redistribuye agendas y agrega procedimiento `Depilacion 2 x 1`. Solo demo. |
> | `backfill_media` | Sube archivos de `MEDIA_ROOT` al bucket S3. Parte del change cloud-storage-migration. **Ver sección 11.7.** |
> | `audit_log_retention` | Borra filas de `AuditLog` con más de `--days` (default 90). Programa via cron. |
> | `create_backup` | Genera un dump de la DB y aplica retención. **Ver sección 11.2 → `docs/backups.md`.** |

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

### 5.3. Verificación rápida

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

    # Media: depende de STORAGE_PROVIDER (ver 5.1).
    #   - STORAGE_PROVIDER=local: Nginx sirve directamente desde disco.
    #   - STORAGE_PROVIDER=s3: este location NO se usa; el frontend pide
    #     /api/media/signed-url/?path=... y el browser descarga directo
    #     del bucket con la presigned URL. Mantener el location no rompe
    #     nada (sigue siendo útil para /media/ residual durante el
    #     cutover), pero el flujo normal NO pasa por acá.
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

> ⚠️ **El bloque `/media/` queda intencionalmente.** Aunque con `STORAGE_PROVIDER=s3` el flujo normal no pasa por ahí, mantenerlo configurado permite que `MEDIA_LOCAL_FALLBACK_ENABLED=true` siga sirviendo archivos viejos durante el cutover. Una vez completado el backfill (`backfill_media` escribiendo `_BACKFILL_COMPLETE` en el bucket) y confirmado que todas las URLs vienen vía presigned, podés comentar este bloque — pero no es obligatorio.

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

> ⚠️ **El archivo en el repo es `deploy.sh.example`, no `deploy.sh`.** La primera vez tenés que copiarlo y darle permisos de ejecución. Esto está documentado al inicio del propio archivo, pero mucha gente se lo salta y obtiene `command not found`.

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
| AWS S3 (si usás `STORAGE_PROVIDER=s3`) | access key + secret key | Guardala en 1Password / Vault, **nunca** en el repo. |

### 11.2. Backups de la base de datos

**Fuente canónica: `docs/backups.md`.** Esa guía es la única que se mantiene sincronizada con `backups/management/commands/create_backup.py`, `scripts/backups.sh.example` y los modelos `Backups` / `BackupAuditLog`. Cualquier cambio al sistema de backups se documenta primero ahí.

**Resumen ejecutivo:**

- El backup se hace con **`python manage.py create_backup`** (management command Django, no `pg_dump` directo).
- El helper `scripts/backups.sh.example` envuelve el management command con subcomandos `daily`, `weekly`, `status`. Se instala en `/usr/local/bin/clinica-backup.sh` o `/opt/clinica/scripts/backups.sh.example`.
- Se programa con **systemd timer** (recomendado) o **cron** — la guía canónica tiene los dos.
- Las variables de entorno que controlan el backup viven en `backend/.env`: `BACKUPS_DIR`, `BACKUP_DAILY_KEEP`, `BACKUP_WEEKLY_KEEP`, `BACKUP_RATE_LIMIT_*`.
- Los dumps son **custom-format `.dump`** de Postgres (no `pg_dump` plain text). Se restauran con `pg_restore`.
- **Política de retención por default:** 7 diarios + 4 semanales. Modificable vía env vars.
- **Backups contienen PHI.** Acceso restringido al service account, cifrado en tránsito y reposo, nunca en soporte técnico, nunca en home compartido.

**Setup mínimo** (el resto está en `docs/backups.md`):

```bash
# 1. Crear el directorio de backups con ownership correcto
sudo install -d -o www-data -g www-data -m 0750 /var/lib/clinica/backups

# 2. Setear BACKUPS_DIR en backend/.env
echo 'BACKUPS_DIR=/var/lib/clinica/backups' | sudo tee -a /var/www/clinica/backend/.env

# 3. Probar un backup
sudo -u www-data /var/www/clinica/backend/env/bin/python \
    /var/www/clinica/backend/manage.py create_backup

# 4. Programar via systemd timer o cron (ver docs/backups.md §"Run and schedule backups")
```

> ⚠️ **No usar `pg_dump` directo desde un script bash** como hacía la versión vieja de esta guía. El management command `create_backup` tiene un lock de filesystem, registra cada ejecución en `BackupAuditLog`, y aplica la retención automáticamente. Un `pg_dump` externo no respeta ninguno de esos mecanismos.

### 11.3. Sync externa de backups

**El backup local NO es suficiente.** Si el VPS se muere, te quedás sin backups. Configurá sincronización periódica a un destino externo. Las opciones y comandos exactos están en **`docs/backups.md` §"Security and PHI"** — esa sección se actualiza junto con el helper de backups.

| Opción | Configuración |
|---|---|
| **Backblaze B2** | Barato, `b2 sync` o `rclone`. |
| **AWS S3** | `aws s3 sync`. |
| **Storage del proveedor** | DO Spaces, Hetzner Storage Box, etc. |
| **rsync a otro servidor** | Si tenés otro VPS. |

Sumá una segunda línea al cron o un script separado. **Cifrado obligatorio** — los dumps contienen PHI.

### 11.4. Configurar alertas mínimas

Sin monitoreo, no sabés que algo se rompió hasta que el cliente te llama. Lo mínimo:

- **UptimeRobot** (gratis): chequea que `https://tu-dominio.com/` responda 200 cada 5 min. Te avisa por mail/Slack.
- **Sentry** (free tier): captura excepciones de Django y React. Indispensable para producción.
- **CloudWatch billing alarm** (si usás `STORAGE_PROVIDER=s3`): umbral de costo en `$30/mes` para detectar uso anómalo del bucket. Configuralo desde la consola AWS — el script `deploy.sh` no lo hace.

### 11.5. Configurar actualizaciones de seguridad automáticas

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 11.6. Datos sensibles: consideraciones legales

La clínica maneja datos de salud de pacientes. En Bolivia, la **Ley 164 (Ley General de Telecomunicaciones, Tecnologías de Información y Comunicación — arts. 73 a 78 sobre protección de datos personales)** y su decreto reglamentario regulan el tratamiento de datos personales. Los datos de salud son **dato sensible** bajo esa norma, y bajo HIPAA (si la clínica exporta datos a Estados Unidos o trabaja con un covered entity bajo Business Associate Agreement). Antes de poner el sistema en producción para un cliente:

- [ ] Confirmar que el cliente firmó consentimiento sobre el proveedor de hosting y sobre el cambio de almacenamiento local → cloud (migración `MEDIA_ROOT` → S3).
- [ ] Verificar que la DB está encriptada (la mayoría de proveedores cloud lo ofrece).
- [ ] Si `STORAGE_PROVIDER=s3`: firmar el BAA con AWS antes de subir el primer PDF clínico al bucket. Sin BAA, el storage NO es HIPAA-eligible.
- [ ] Política de acceso al VPS: quién tiene la clave SSH, quién rota.
- [ ] Política de backups: dónde se guardan, quién tiene acceso, retención, **cifrado en tránsito y reposo**.
- [ ] Política de logs: accesos a datos clínicos deben quedar auditados (el módulo `audit/AuditLog` cubre el endpoint `/api/media/signed-url/` — ver §11.7).
- [ ] Política de revocación de presigned URLs: aunque el TTL es de 15 minutos, dejar documentado el procedimiento de soporte si un cliente reporta un link comprometido.

### 11.7. Cutover a AWS S3 en producción (`STORAGE_PROVIDER=s3`)

> **Pre-requisito:** el runbook `docs/runbooks/aws-cloud-storage-setup.md` ya corrió completo: bucket creado en `sa-east-1`, BAA firmado (si aplica), IAM user con inline policy, credenciales en 1Password. Sin ese paso previo, este procedimiento aborta con `AccessDenied`.

Esta sección es el **paso 2 del cutover** — el runbook de AWS es el paso 1 (provisioning). Acá asumimos que el bucket existe y está vacío, y vamos a:

1. Subir los archivos de `MEDIA_ROOT` al bucket (`backfill_media`).
2. Cambiar `STORAGE_PROVIDER` de `local` a `s3` en el `.env` de producción.
3. Verificar que el endpoint `/api/media/signed-url/` emite URLs válidas.
4. Verificar que el frontend pide presigned URLs (no sirve `/media/` directo).
5. Esperar a que `backfill_media` escriba el sentinel `_BACKFILL_COMPLETE`.
6. Desactivar el fallback local.

> ⚠️ **Timing:** todo el procedimiento tarda entre 1 y 6 horas dependiendo del volumen de `backend/media/`. Planificá una ventana de mantenimiento. No hay downtime técnico (el fallback local cubre el gap), pero la decisión de cuándo decir "cutover completo" sí requiere ventana.

#### Paso 1 — Snapshot del estado pre-cutover

Antes de tocar nada, dejá evidencia de dónde estás:

```bash
ssh deploy@<VPS_IP>

# ¿Cuántos archivos hay en el disco?
sudo find /var/www/clinica/backend/media -type f | wc -l
# Anotá el número. Ejemplo: 1842

# ¿Cuánto pesan?
sudo du -sh /var/www/clinica/backend/media
# Anotá el peso. Ejemplo: 3.4G

# ¿STORAGE_PROVIDER actual?
grep STORAGE_PROVIDER /var/www/clinica/backend/.env
# Esperado: STORAGE_PROVIDER=local
```

Anotá los tres números (`archivos`, `peso`, `STORAGE_PROVIDER`) en el runbook de la deploy. Si algo sale mal, los necesitás para diagnosticar.

#### Paso 2 — Configurar las env vars de S3 (sin cambiar `STORAGE_PROVIDER` todavía)

Editá `backend/.env` y agregá **al final** (no toques las vars existentes):

```bash
sudo nano /var/www/clinica/backend/.env

# Agregar al final:
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_STORAGE_BUCKET_NAME=proyecto-c-clinical-prod
AWS_S3_REGION_NAME=sa-east-1
AWS_S3_ENDPOINT_URL=
MEDIA_LOCAL_FALLBACK_ENABLED=true
MEDIA_SIGNED_URL_TTL_SECONDS=900
```

> ⚠️ **No cambies `STORAGE_PROVIDER` todavía.** En este punto seguimos con `STORAGE_PROVIDER=local` pero Django ya tiene las credenciales de S3. Esto te permite testear la conexión sin afectar el tráfico.

Verificá la conectividad sin reiniciar nada (Django no las lee hasta el restart):

```bash
sudo -u www-data env/bin/python /var/www/clinica/backend/manage.py shell -c "
import boto3, os
s3 = boto3.client(
    's3',
    region_name=os.getenv('AWS_S3_REGION_NAME'),
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
)
r = s3.list_objects_v2(Bucket=os.getenv('AWS_STORAGE_BUCKET_NAME'), MaxKeys=5)
print(f'OK bucket accesible. KeyCount={r.get(\"KeyCount\", 0)}')
"
```

**Esperado:** `OK bucket accesible. KeyCount=0` (o el número de archivos que ya estén en el bucket).

**Si da `AccessDenied`:** el ARN en la IAM policy no coincide con el bucket name. Volvé al paso 7-8 de `docs/runbooks/aws-cloud-storage-setup.md`.

#### Paso 3 — Correr `backfill_media` en modo dry-run

```bash
sudo -u www-data /var/www/clinica/backend/env/bin/python \
    /var/www/clinica/backend/manage.py backfill_media --dry-run
```

El comando lista **qué** archivos subiría y **cuántos** ya están en el bucket (skip). Compará el número contra el snapshot del paso 1. Si hay diferencias grandes (por ejemplo, dry-run dice 1500 pero el snapshot decía 1842), investigá antes de seguir — probablemente hay archivos en subcarpetas que el script no está mirando.

#### Paso 4 — Correr `backfill_media` real, en background

No hagas el upload interactivo (te puede tirar la sesión SSH a mitad de camino). Usá `nohup` o `screen`/`tmux`:

```bash
# Opción A: nohup + log
cd /var/www/clinica/backend
sudo -u www-data nohup env/bin/python manage.py backfill_media \
    --batch-size=100 >> /var/log/clinica-backfill.log 2>&1 &

# Opción B: tmux (recomendado — podés reconectarte)
sudo -u www-data tmux new -s backfill -d \
    "env/bin/python manage.py backfill_media --batch-size=100 2>&1 | tee /var/log/clinica-backfill.log"
```

Monitoreá el progreso (en otra terminal SSH):

```bash
# Última línea del log
tail -f /var/log/clinica-backfill.log

# ¿Cuántos archivos ya subió?
grep -c "Uploaded:" /var/log/clinica-backfill.log

# ¿Cuántos errores tuvo?
grep -c "ERROR" /var/log/clinica-backfill.log
```

**Criterio de éxito:** el log termina con un mensaje tipo `Backfill complete: X uploaded, Y skipped, Z errors`. Si `errors > 0`, mirá las líneas `ERROR` específicas — suelen ser archivos con nombres de caracteres rotos o paths que rompen la API de S3.

#### Paso 5 — Verificar el sentinel `_BACKFILL_COMPLETE`

`backfill_media` escribe un archivo cero-byte en la raíz del bucket cuando termina. Si el sentinel existe, el backfill está completo:

```bash
aws s3 ls s3://proyecto-c-clinical-prod/_BACKFILL_COMPLETE --region sa-east-1
```

**Esperado:** una línea con la fecha de hoy y el tamaño `0`.

**Si no aparece:** el backfill no terminó (revisá el log) o abortó por un error. **No sigas con el paso 6 hasta que el sentinel exista**.

#### Paso 6 — Cambiar `STORAGE_PROVIDER` a `s3` y reiniciar

Ahora sí, el cutover. El cambio es **un solo valor en una sola línea**:

```bash
sudo sed -i 's/^STORAGE_PROVIDER=local$/STORAGE_PROVIDER=s3/' /var/www/clinica/backend/.env

# Verificá
grep STORAGE_PROVIDER /var/www/clinica/backend/.env
# Esperado: STORAGE_PROVIDER=s3

# Reiniciar Gunicorn
sudo systemctl restart gunicorn
sleep 2
sudo systemctl status gunicorn
```

**No hay downtime.** Mientras `MEDIA_LOCAL_FALLBACK_ENABLED=true`, las requests a archivos que ya están en el bucket van por S3, las que no van al disco local. El usuario no nota nada.

#### Paso 7 — Verificar que el endpoint `/api/media/signed-url/` emite URLs válidas

Necesitás un admin logueado. Generá el cookie jar y probá:

```bash
# En tu laptop, contra el dominio real:
ssh deploy@<VPS_IP> -- '
  curl -sS -c /tmp/clinica-test-cookie \
    -H "Origin: https://tu-dominio.com" \
    -H "Referer: https://tu-dominio.com/" \
    -X POST "https://tu-dominio.com/api/auth/login/" \
    -d "username=admin.x&password=..." \
    -o /dev/null
  ls -la /tmp/clinica-test-cookie
'

# Probá el endpoint con un archivo que sepamos que existe (subido en el backfill):
ssh deploy@<VPS_IP> -- '
  curl -sS -b /tmp/clinica-test-cookie \
    "https://tu-dominio.com/api/media/signed-url/?path=fichas_clinicas/2026/10/algo.pdf"
'
```

**Esperado:** un JSON con `{"url": "https://...s3.sa-east-1.amazonaws.com/...?...", "expires_at": "...", "ttl_seconds": 900}`.

**Si da 404:** el archivo no está en el bucket. Revisá con `aws s3 ls s3://proyecto-c-clinical-prod/fichas_clinicas/2026/10/` si el path está.

**Si da 403:** el admin no tiene permiso para acceder al prefijo (ver Anexo C de `openspec/changes/cloud-storage-migration/specs/media-signed-url-endpoint/spec.md` para las reglas de autorización).

**Si da 503:** falló el audit log write. Mirá `journalctl -u gunicorn -n 50` — el endpoint devuelve 503 fail-closed si no puede escribir en `AuditLog`.

#### Paso 8 — Verificar que el frontend pide presigned URLs

Esto requiere DevTools en el browser del operador:

1. Abrí `https://tu-dominio.com` en Chrome.
2. Login como admin.
3. Navegá a una pantalla que muestre archivos: `Detalle de cliente` o `Detalle de operación`.
4. Abrí DevTools → Network → filtrá por `signed-url` o por `amazonaws.com`.
5. Hacé click en una imagen o PDF.

**Esperado:** ves **una** request a `/api/media/signed-url/?path=...` y después **una** request al bucket de S3 (`*.s3.sa-east-1.amazonaws.com`). La URL del bucket expira después de 15 min.

**Anti-patrón (lo que NO deberías ver):** requests directos a `https://tu-dominio.com/media/...`. Si las ves, el frontend no está usando `useSignedUrl` y tenés que debuggear el componente (ver `frontend/aesthetic-clinic/src/services/media.tsx`).

#### Paso 9 — Desactivar el fallback local

Solo cuando el backfill esté completo, el endpoint emita URLs correctas, y el frontend las use:

```bash
# Confirmá que el sentinel existe
aws s3 ls s3://proyecto-c-clinical-prod/_BACKFILL_COMPLETE --region sa-east-1

# Cambiar la env var
sudo sed -i 's/^MEDIA_LOCAL_FALLBACK_ENABLED=true$/MEDIA_LOCAL_FALLBACK_ENABLED=false/' \
    /var/www/clinica/backend/.env

grep MEDIA_LOCAL_FALLBACK_ENABLED /var/www/clinica/backend/.env
# Esperado: MEDIA_LOCAL_FALLBACK_ENABLED=false

# Reiniciar
sudo systemctl restart gunicorn
```

**A partir de acá, todas las requests a archivos que NO estén en el bucket devuelven 404** (no más fallback al disco). Esto es desired — significa que el sistema está 100% en S3.

> ⚠️ **Cleanup del disco local** (opcional, no urgente): después de 30 días de cutover estable, podés vaciar `/var/www/clinica/backend/media/` para liberar espacio en el VPS. **No lo hagas antes** — te queda el rollback más difícil.

#### Paso 10 — Rollback (si algo sale mal)

Si en cualquier paso del cutover algo se rompe:

```bash
# Volver a local
sudo sed -i 's/^STORAGE_PROVIDER=s3$/STORAGE_PROVIDER=local/' /var/www/clinica/backend/.env
sudo sed -i 's/^MEDIA_LOCAL_FALLBACK_ENABLED=true$/MEDIA_LOCAL_FALLBACK_ENABLED=false/' \
    /var/www/clinica/backend/.env
sudo systemctl restart gunicorn
```

**Resultado:** el sistema vuelve a servir archivos desde disco local. El bucket sigue existiendo con los archivos que ya se subieron (no se borra nada). El frontend sigue pidiendo presigned URLs (no cambia el código), pero el endpoint devuelve 404 (archivo no en bucket) y el fallback está desactivado, así que en este modo degradado la app **no muestra imágenes**.

**Si el rollback tiene que ser rápido y no querés perder funcionalidad**, mejor revertir el cambio a `STORAGE_PROVIDER=local` y poner `MEDIA_LOCAL_FALLBACK_ENABLED=true` — eso restaura el modo original pre-cutover.

#### Criterios de "cutover completo"

| Criterio | Cómo verificarlo |
|---|---|
| Backfill terminó sin errores | `grep "ERROR" /var/log/clinica-backfill.log` devuelve 0 |
| Sentinel `_BACKFILL_COMPLETE` existe | `aws s3 ls s3://.../_BACKFILL_COMPLETE` muestra el archivo |
| Endpoint emite presigned URLs | `curl /api/media/signed-url/` devuelve JSON con `url` apuntando a S3 |
| Frontend pide presigned URLs | DevTools muestra requests a `/api/media/signed-url/` y a `*.s3.sa-east-1.amazonaws.com` |
| `MEDIA_LOCAL_FALLBACK_ENABLED=false` aplicado | `grep MEDIA_LOCAL_FALLBACK_ENABLED .env` |
| Sin requests a `/media/...` desde el frontend | DevTools Network filtrado por `/media/` muestra 0 requests en una sesión normal |

Si los 6 criterios pasan, **el cutover está completo y podés borrar el runbook de cutover de la lista de pendientes.**

#### Monitoreo post-cutover (primeras 2 semanas)

Después del cutover, prestá atención a:

- **Métricas de 404 en `/api/media/signed-url/`** — si suben, hay archivos que el frontend pide pero el bucket no tiene. Investigá caso por caso (suelen ser archivos subidos después del backfill inicial).
- **Costos de AWS** — la métrica `EstimatedCharges` en CloudWatch. Si pasa de $30/mes en el primer mes, algo está mal (muchas requests o mucho egress). Configurá el billing alarm del runbook de AWS.
- **Errores en `AuditLog`** — el endpoint registra cada emisión. Si ves `action=SIGNED_URL_DENIED` en masa, alguien está intentando acceder a archivos sin permiso. Es expected, pero un pico inusual amerita investigación.

### 11.8. Almacenamiento en digital bucket (AWS S3)

> **Esta sección explica qué es el bucket, por qué se usa y cómo provisionarlo.** El procedimiento operativo del cutover ya está cubierto en §11.7. Acá asumimos que el operador todavía no creó el bucket y necesita entenderlo antes de empezar.

#### ¿Por qué un digital bucket?

Por default, el sistema guarda las fotos, PDFs de historia clínica y comprobantes de pago en el disco local del VPS (`backend/media/`). Eso tiene tres problemas:

1. **Privacidad clínica rota.** Los archivos están en `/var/www/clinica/backend/media/`, accesibles vía `https://tu-dominio.com/media/<archivo>`. Cualquiera con el link (que se filtra en emails, chats, logs) puede ver la ficha clínica de un paciente sin autenticarse. **Viola la Ley 164 de Bolivia** y el sentido común de PHI.
2. **Disco del VPS se llena.** Una clínica con 200 fotos de operación por mes × 500 KB cada una = ~100 MB/mes solo de fotos. Sumá PDFs de fichas (1-5 MB cada uno) y comprobantes (200 KB promedio) y el VPS se queda sin espacio en 6-12 meses.
3. **Backups del VPS no incluyen `backend/media/`.** Si el VPS se muere, perdés todos los archivos clínicos aunque tengas backups de la DB. Los backups cubren datos, no media.

**Un digital bucket (AWS S3 en este caso) resuelve los tres:** el bucket es privado (autenticación requerida para cada download via presigned URL), escala sin límite práctico de storage, y los archivos están separados del VPS así un backup del VPS no los afecta.

#### Pre-requisitos antes de provisionar

Antes de tocar la consola de AWS, asegurate de tener:

- **Cuenta AWS** con método de pago cargado. Business support plan es opcional — basic support alcanza para esta operatoria.
- **Acceso a un 1Password vault** (o gestor de secretos equivalente) — las credenciales IAM nunca se commitean al repo.
- **Decisión de compliance** tomada (ver §11.6):
  - Si la clínica maneja PHI y exporta datos a US o trabaja con un covered entity bajo BAA → **firmar AWS BAA antes de subir el primer PDF clínico**.
  - Si la clínica es Bolivia-only sin exportar a US → BAA no aplica, pero el bucket sigue siendo privado y cifrado.
- **Bucket name único global.** Los nombres de bucket en S3 son únicos worldwide. Si elegís `clinica-files`, alguien ya lo tiene. Sugerencia: `proyecto-c-clinical-prod-<tu-inicial>` (ej. `proyecto-c-clinical-prod-j`).

#### Provisioning del bucket (paso a paso)

> **Tiempo estimado:** 15-20 minutos si tenés la cuenta lista. Algunos pasos requieren esperar validación de AWS (ej. propagar DNS, ~5 min).

1. **Login en AWS Console** como IAM user `admin` (NO root user). URL: https://console.aws.amazon.com/.

2. **Si aplica, firmar el AWS BAA** antes de subir el primer PDF clínico:
   - Ir a https://aws.amazon.com/compliance/hipaa-eligible-services/.
   - Descargar el BAA template.
   - Firmar online o imprimir/firmar/escanear.
   - Subir el documento firmado al AWS Artifact portal (https://console.aws.amazon.com/artifact/).
   - **Anotar el número de referencia del BAA en 1Password** bajo `AWS / BAA`.

3. **Crear el bucket:**
   - Console → S3 → Buckets → **Create bucket**.
   - **Bucket name:** `proyecto-c-clinical-prod-<tu-inicial>` (o el nombre que elegiste; recordá que debe ser único global).
   - **Region:** `sa-east-1` (São Paulo, la más cercana a Bolivia con HIPAA-eligible services) o la región que prefieras. Anotala — la vas a poner en `AWS_S3_REGION_NAME`.
   - **Object Ownership:** ACLs disabled (recommended).
   - **Block Public Access settings for this bucket:** **TODAS LAS 4 FLAGS EN TRUE**. Esto es crítico. Si dejás alguna en false, los archivos son accesibles públicamente por URL sin autenticación.
   - **Bucket Versioning:** **Enable**. Defiende contra borrado accidental de PDFs clínicos (proposal Gate 7).
   - **Tags (opcional):** `Environment=production`, `Project=clinica`, `CostCenter=clinica-storage`. Útil para billing reports.
   - **Default encryption:** Server-side encryption with Amazon S3 managed keys (SSE-S3). Free, automático, suficiente para compliance básico.
   - Click **Create bucket**.

4. **Habilitar Server Access Logs** (auditoría adicional):
   - Dentro del bucket → tab **Properties** → scroll hasta **Server access logging** → **Edit** → **Enable**.
   - **Target bucket:** `proyecto-c-clinical-prod-logs` (creá este bucket aparte primero, sin versioning, con lifecycle rule que expire objects a los 90 días).
   - **Target prefix:** `logs/`
   - Esto te da un audit trail completo de quién accedió a qué archivo, cuándo, desde qué IP.

5. **Crear el IAM user** (para que el backend acceda al bucket con permisos scoped):
   - Console → Users → **Create user**.
   - **User name:** `proyecto-c-clinical-app-prod` (o similar).
   - **Access type:** **Programmatic access** ONLY (no console password — el backend no necesita login web).
   - Click **Next: Permissions**.

6. **Attach inline policy** (NO uses managed policies — querés el ARN del bucket explícito):
   - Click **Create inline policy** → tab **JSON** → pegar:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Sid": "BucketList",
         "Effect": "Allow",
         "Action": ["s3:ListBucket"],
         "Resource": "arn:aws:s3:::proyecto-c-clinical-prod-<tu-inicial>",
         "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
       },
       {
         "Sid": "BucketObjectRW",
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:HeadObject"],
         "Resource": "arn:aws:s3:::proyecto-c-clinical-prod-<tu-inicial>/*",
         "Condition": { "StringEquals": { "aws:RequestedRegion": "sa-east-1" } }
       },
       {
         "Sid": "DenyNonSaEast1",
         "Effect": "Deny",
         "Action": "s3:*",
         "Resource": "*",
         "Condition": { "StringNotEquals": { "aws:RequestedRegion": "sa-east-1" } }
       }
     ]
   }
   ```

   - **Reemplazá** `proyecto-c-clinical-prod-<tu-inicial>` con tu nombre real del bucket en las 3 referencias ARN.
   - **Click Review policy** → **Name:** `proyecto-c-clinical-bucket-access` → **Create policy**.

7. **Descargar credenciales:**
   - Click en el user recién creado.
   - Tab **Security credentials** → **Create access key** → **Use case:** Local code (no CLI ni SDK de AWS) → Next → Create.
   - **⚠️ Esta es la ÚNICA vez que ves el secret access key.** Descargá el `.csv` o copialo a 1Password vault `AWS / proyecto-c-clinical-app-prod / prod`.
   - El **access key ID** empieza con `AKIA...`.
   - El **secret access key** es una cadena alfanumérica larga (~40 chars).

#### Costo esperado

Los números de storage (que asume 200 GB almacenados, ~50 GB de egress/mes) — estos vienen del change `cloud-storage-migration` que comparó AWS S3, Cloudflare R2 y Supabase Storage:

| Concepto | Costo por mes (USD) |
|---|---|
| **Storage** — 200 GB × $0.023/GB (Standard tier, región `sa-east-1`, primeros 50 TB) | **$4.60** |
| **Egress** — 50 GB × $0.09/GB (internet egress desde `sa-east-1`, después de los primeros 100 GB gratis para cuentas nuevas) | **$4.50** |
| **Versioning** — 200 GB adicionales × $0.023/GB (defensa contra borrado accidental, propuesta Gate 7) | **$4.60** |
| **GET requests** — 50,000 × $0.0004/1000 | **$0.02** |
| **PUT requests** — 5,000 × $0.005/1000 | **$0.025** |
| **Total estimado** | **~$13.80/mes** |

**Primer año (free tier):** las cuentas nuevas de AWS tienen 12 meses de free tier que cubren 5 GB storage, 15 GB egress, 2,000 PUT, 20,000 GET por mes. Una clínica pequeña no paga nada durante el primer año si se mantiene dentro de esos límites.

**Para escalar:** una clínica con 500 GB almacenados y 200 GB egress/mes pagaría ~$35-50/mes. Configurar el billing alarm (abajo) para que avise antes de pasar de $50/mes.

**Alternativas más baratas** (no implementadas hoy, pero documentadas por si el costo se vuelve problema):

- **Cloudflare R2:** sin costo de egress (10 GB gratis, después $0.015/GB storage). Si tu clínica tiene mucho tráfico de descarga (clientes descargando sus PDFs frecuentemente), R2 puede ser 5-10× más barato.
- **Backblaze B2:** $0.006/GB storage + $0.01/GB egress. Más barato que S3 pero menos integrado.
- **Self-hosted MinIO:** gratis pero requiere un VPS adicional grande. No vale la pena para clínicas con <1 TB.

#### Monitoreo post-provisioning

Una vez que el bucket está creado y el IAM user tiene las credenciales en 1Password, configurá el monitoreo antes de empezar el cutover (§11.7):

**1. CloudWatch billing alarm** (alerta si el costo pasa de $30/mes):

```
1. AWS Console → CloudWatch → Alarms → Create alarm.
2. Select metric → Billing → Total Estimated Charge.
3. Currency: USD.
4. Threshold: Static, $30 (o el monto que prefieras).
5. Send notification: tu email (o un SNS topic si querés Slack/PagerDuty).
6. Name: `clinica-s3-storage-cost-alarm`.
```

**2. Lifecycle rule** (mover archivos viejos a Glacier después de 90 días para ahorrar storage):

```
1. S3 → tu bucket → Management → Create lifecycle rule.
2. Name: `archive-old-clinical-files`.
3. Apply to all objects in the bucket.
4. Transitions:
   - Move to Glacier Instant Retrieval after 90 days.
   - Move to Glacier Deep Archive after 365 days.
5. Expiration: never (los archivos clínicos se conservan indefinidamente por compliance).
```

**⚠️ Glacier cambia el costo de storage de $0.023/GB a $0.004/GB** (Glacier Instant) o $0.00099/GB (Glacier Deep Archive). Si tenés 200 GB de archivos con +1 año de antigüedad, ahorrás ~$4/mes. Si los archivos se acceden vía Glacier (no vía S3 Standard), el costo de GET sube — pero los PDFs clínicos viejos rara vez se descargan.

**3. Rotación de credenciales IAM** (cada 90 días):

```
1. AWS Console → IAM → Users → proyecto-c-clinical-app-prod.
2. Tab Security credentials → Create access key.
3. Anotá la nueva key en 1Password (reemplaza la anterior).
4. Actualizá AWS_ACCESS_KEY_ID y AWS_SECRET_ACCESS_KEY en backend/.env.
5. sudo systemctl restart gunicorn.
6. Eliminá la access key vieja (mismo tab, "Make inactive" después de 24h).
```

Anotá cada rotación en `1Password → AWS / proyecto-c-clinical-app-prod / rotation-log`.

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
sudo -u www-data /var/www/clinica/backend/env/bin/python \
    /var/www/clinica/backend/manage.py create_backup

# Listar backups
ls -lh /var/lib/clinica/backups/

# Estado de la suspensión biométrica
cd /ruta/al/repo && ./scripts/biometric_suspension.sh status

# Ver últimas entradas del audit log de media
sudo -u www-data /var/www/clinica/backend/env/bin/python \
    /var/www/clinica/backend/manage.py shell -c "
from audit.models import AuditLog
for log in AuditLog.objects.all()[:10]:
    print(f'{log.created_at} | {log.user} | {log.action} | {log.resource_path}')
"

# Estado del backfill (verificar si el sentinel existe)
aws s3 ls s3://<tu-bucket>/_BACKFILL_COMPLETE --region sa-east-1
# (sin output = backfill incompleto; el archivo existe = cutover OK)
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

### 403 CSRF verification failed

Tres causas comunes (en orden de frecuencia):

1. **`DJANGO_CSRF_COOKIE_SECURE=1` pero entrás por HTTP** (sin HTTPS). Ver la tabla en la sección 5.1.
2. **`DJANGO_CSRF_TRUSTED_ORIGINS` no incluye el dominio exacto** que estás usando (sin `https://`, sin trailing slash).
3. **El dominio del frontend (`VITE_*` build) no coincide** con `DJANGO_CORS_ALLOWED_ORIGINS`.

### 404 en `/api/media/signed-url/`

Tres causas:

1. **`STORAGE_PROVIDER=local` y el archivo no existe en `backend/media/`.** El endpoint solo firma paths que ya están en el storage. Con `local`, el archivo tiene que estar en disco.
2. **`STORAGE_PROVIDER=s3` y el archivo no se subió al bucket todavía.** Corré `backfill_media` o esperá que la lazy migration en `LazyLocalFallbackStorage` lo suba en el primer read.
3. **El path no está en el allowlist.** Solo se firman paths que empiezan con: `fichas_clinicas/`, `tickets_adjuntos/`, `citas/`, `fotos_operacion/`, `comprobantes_pagos/`, `comprobantes_citas/`. Paths fuera de esos prefijos devuelven 400 (malformed) o 403 (forbidden) según el caso.

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

### Error: `manage.py: No module named 'fcntl'`

Estás corriendo `manage.py` en PowerShell nativo de Windows. El módulo `backups.services` (transitivo vía `INSTALLED_APPS`) importa `fcntl` que es POSIX-only. Soluciones:

- **Para deploys en VPS Linux:** no aplica, fcntl existe.
- **Para desarrollo local en Windows:** usá WSL bash (`wsl -e bash`), o aplicá el workaround de stub que documenta el apply phase 1.

### Error: `npm ci` o `npm run build` muestra `Killed` o `JavaScript heap out of memory`

OOM. Ver [sección 6, paso de swap](#6-frontend) — agregar swap de 2 GiB. Recomendado dejarlo permanente vía `/etc/fstab` ([sección 10.2 paso 1](#paso-1--si-tu-vps-tiene-menos-de-1-gib-de-ram-caso-real-frecuente-crear-swap-de-2-gib)).

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

### Error: `deploy.sh: command not found`

Te saltaste el paso de copiar `deploy.sh.example` a `deploy.sh`. Ver sección 10.1.

```bash
cp scripts/deploy.sh.example scripts/deploy.sh
chmod +x scripts/deploy.sh
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

### Error: `AccessDenied` de AWS S3 al subir archivos

Tres causas comunes:

1. **ARN mal escrito en la IAM policy.** Verificá que `arn:aws:s3:::NOMBRE-EXACTO-DEL-BUCKET` coincida carácter por carácter con el nombre real del bucket (case-sensitive, sin typos, sin mayúsculas/minúsculas mal).
2. **Bucket en otra región.** Si tu bucket está en `us-east-2` pero `AWS_S3_REGION_NAME=sa-east-1`, los requests fallan con `EndpointConnectionError`. Verificá la región en la consola S3.
3. **Credenciales mal copiadas del CSV.** Re-descargá el access key desde IAM y verificá que no haya caracteres raros (espacios, saltos de línea).

### Error: 500 con `Boto3Storage.url() is disabled`

Si ves este error en el runserver:

```
NotImplementedError: Boto3Storage.url() is disabled; mint signed URLs through /api/media/signed-url/ (slice 2).
```

**Causa:** un endpoint está llamando `.url()` en un `FileField`/`ImageField` con `STORAGE_PROVIDER=s3`. Por diseño del change `cloud-storage-migration` (slice 2), `Boto3Storage.url()` no está implementado — hay que usar `/api/media/signed-url/` en su lugar.

**Fix:** asegurate de estar en una versión con el fix de `cloud-storage-migration-fixes` aplicado (slice 1/3 commiteado en `feature/cloud-storage-migration-fixes`). Si no tenés ese branch, mergéalo antes.

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

### El backfill de media no termina / queda colgado

Tres causas comunes:

1. **Credenciales AWS expiraron o el bucket cambió de policy.** Verificá con `python -c "import boto3; s3=boto3.client('s3'); print(s3.list_objects_v2(Bucket='...', MaxKeys=1))"`.
2. **Archivos muy grandes en `backend/media/`.** Subilos con `aws s3 cp` manual primero, después corré `backfill_media --resume`.
3. **El proceso se interrumpió.** `backfill_media` es idempotente (usa `head_object` para detectar existentes). Re-ejecutalo sin miedo.

---

## 14. Resumen de archivos configurados

| Archivo | Ubicación | Propósito |
|---|---|---|
| `.env` | `/var/www/clinica/backend/.env` | Variables de entorno Django (sensible, NO commitear) |
| `.env.example` | `/var/www/clinica/backend/.env.example` | Plantilla del `.env` (sí commitear) |
| Nginx config | `/etc/nginx/sites-available/clinica` | Reverse proxy + SSL + estáticos |
| Gunicorn service | `/etc/systemd/system/gunicorn.service` | Daemon auto-inicio |
| Backup systemd timer | `/etc/systemd/system/clinica-backups.{service,timer}` | Dump diario de PostgreSQL (ver `docs/backups.md`) |
| Cron backups (alternativa) | `crontab -e` | Programa el backup a las 03:00 (ver `docs/backups.md`) |
| `deploy.sh` | `scripts/deploy.sh` (local, copy de `.example`) | Deploy automático desde máquina local |
| `deploy.sh.example` | `scripts/deploy.sh.example` | Plantilla, sí commitear |
| `biometric_suspension.sh` | `scripts/biometric_suspension.sh` | Helper reversible de forward/rollback biométrico |
| `backups.sh.example` | `scripts/backups.sh.example` | Helper de backup (daily/weekly/status) |

---

## 15. Estructura final en el VPS

```
/var/www/clinica/
├── backend/
│   ├── env/                  # Virtualenv Python
│   ├── .env                  # Variables de entorno (sensible)
│   ├── manage.py
│   ├── staticfiles/          # Estáticos Django (servido por Nginx)
│   └── media/                # Archivos media (legacy + fallback cutover)
├── frontend/
│   └── aesthetic-clinic/
│       └── dist/             # Build React (servido por Nginx)
├── clinica.sock              # Socket Gunicorn
├── gunicorn-access.log
└── gunicorn-error.log

/var/lib/clinica/backups/     # Backups PostgreSQL (.dump format)
/var/log/clinica-backups.log  # Log del cron de backups
```

> **Nota sobre `backend/media/`:** con `STORAGE_PROVIDER=s3`, este directorio queda como **fallback residual** durante el cutover. Una vez que `backfill_media` escribe `_BACKFILL_COMPLETE` y ponés `MEDIA_LOCAL_FALLBACK_ENABLED=false`, podés vaciarlo y dejarlo como no-op (los archivos viejos quedan accesibles vía `/api/media/signed-url/` apuntando al bucket).

---

## Anexo A — Tabla comparativa de cambios desde la versión anterior

Esta tabla documenta los cambios más importantes entre la versión vieja de esta guía (pre-Q4 2026) y la versión actual. Útil si venís de operar con la versión anterior y querés entender qué cambió.

| # | Tema | Versión vieja | Versión actual | Sección actual |
|---|---|---|---|---|
| 1 | **Backups** | Script bash con `pg_dump` directo en `/usr/local/bin/clinica-backup.sh`. Configuración inline. | Management command `python manage.py create_backup` + helper `scripts/backups.sh.example` con subcomandos `daily/weekly/status`. Fuente canónica en `docs/backups.md`. | [§11.2](#112-backups-de-la-base-de-datos) |
| 2 | **Storage** | `MEDIA_ROOT` directo a disco. `STORAGE_PROVIDER` aceptaba `local` o `supabase`. | `Boto3Storage` + `LazyLocalFallbackStorage`. `STORAGE_PROVIDER` solo acepta `local` o `s3`. Endpoint `/api/media/signed-url/` con audit log. | [§5.1](#51-crear-env), [§7](#7-nginx), [§11.6](#116-datos-sensibles-consideraciones-legales), [§11.7](#117-backfill-de-media-al-bucket-solo-si-storage_providers3) |
| 3 | **Deploy script** | `scripts/deploy.sh` ya activo. | Solo `scripts/deploy.sh.example` (plantilla). El operador debe copiarlo antes del primer deploy. | [§10.1](#101-deploy-normal-pull--restart) |
| 4 | **Seeds** | 4 commands documentados (`seed_client_baseline`, `seed_production_baseline`, `seed_pdf_baseline`, `seed_branch_test_scenarios`) + 1 reset. | 9 commands del proyecto + 4 utility commands. Tabla compacta con descripción de cada uno. | [§5.2](#52-cómo-poblar-la-base-de-datos), [Anexo C](#anexo-c--management-commands-del-proyecto) |
| 5 | **Compliance legal** | Referencia a Argentina Ley 25.326. | Actualizado a Bolivia Ley 164 (arts. 73-78) + mención HIPAA si la clínica opera con US. | [§11.6](#116-datos-sensibles-consideraciones-legales) |
| 6 | **Media en Nginx** | Bloque `location /media/` servía todos los archivos directos. | Bloque se mantiene (para fallback) pero el flujo normal con `STORAGE_PROVIDER=s3` va por presigned URLs. | [§7](#7-nginx) |
| 7 | **Variables de entorno** | No documentaba `BACKUPS_DIR` ni `BACKUP_DAILY_KEEP` ni storage vars. | Lista completa en el .env.example + resumen en Anexo B. | [Anexo B](#anexo-b--variables-de-entorno-del-backend) |
| 8 | **Audit log de media** | No existía. | `audit/AuditLog` registra cada presigned URL emitida. Retención 90 días. | [Anexo C](#anexo-c--management-commands-del-proyecto) |
| 9 | **Troubleshooting** | No incluía errores 403 CSRF ni 404 de signed-URL ni AccessDenied de S3. | Nuevos items: 403 CSRF, 404 signed-URL, AccessDenied S3, command not found de deploy.sh, fcntl en Windows. | [§13](#13-troubleshooting) |
| 10 | **Backfill de media** | No existía. | `backfill_media` management command con sentinel `_BACKFILL_COMPLETE`. | [§11.7](#117-backfill-de-media-al-bucket-solo-si-storage_providers3) |

---

## Anexo B — Variables de entorno del backend

Lista completa de variables leídas por `backend/config/settings.py` o por el management code. El `.env.example` es la fuente canónica. Esta tabla agrupa por dominio funcional.

### Seguridad y sesión

| Variable | Default | Descripción |
|---|---|---|
| `DJANGO_SECRET_KEY` | (vacío, obligatorio) | 50+ chars random. Generar con `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`. |
| `DJANGO_DEBUG` | `0` | `1` solo en dev local. NUNCA en producción. |
| `DJANGO_ALLOWED_HOSTS` | (vacío, obligatorio) | CSV de hosts. |
| `DJANGO_USE_LOCAL_DB` | `False` | `True` solo en dev local (usa SQLite). |
| `DJANGO_DB_ENGINE` | `django.db.backends.postgresql` | o `django.db.backends.sqlite3` en dev. |
| `DJANGO_DB_NAME` | `clinica` | |
| `DJANGO_DB_USER` | `clinica_app` | |
| `DJANGO_DB_PASSWORD` | (vacío) | Alfanumérica (Postgres 16 quirks). |
| `DJANGO_DB_HOST` | `localhost` | |
| `DJANGO_DB_PORT` | `5432` | |
| `DJANGO_DB_SSLMODE` | `prefer` | |
| `DJANGO_CORS_ALLOWED_ORIGINS` | (vacío) | CSV. Matchear con `https://` en prod. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | (vacío) | CSV. Matchear con `https://` en prod. |
| `DJANGO_CSRF_COOKIE_SECURE` | `1` | `0` solo si entrás por HTTP sin cert. |
| `DJANGO_CSRF_COOKIE_HTTPONLY` | `0` | |
| `DJANGO_SESSION_COOKIE_SECURE` | `1` | `0` solo si entrás por HTTP sin cert. |
| `DJANGO_BASE_URL` | `http://localhost:8000` | URL del footer de seeds. |
| `DJANGO_SEED_ADMIN_URL` | (vacío) | Override del footer. |
| `DJANGO_ENVIRONMENT` | `development` | `production` bloquea `seed_pdf_baseline` y `reset_pdf_baseline`. |

### Storage (cloud-storage-migration)

| Variable | Default | Descripción |
|---|---|---|
| `STORAGE_PROVIDER` | `local` | `local` o `s3`. `supabase` ya no se acepta. |
| `AWS_ACCESS_KEY_ID` | (vacío) | Obligatorio si `STORAGE_PROVIDER=s3`. |
| `AWS_SECRET_ACCESS_KEY` | (vacío) | Obligatorio si `STORAGE_PROVIDER=s3`. NUNCA en repo. |
| `AWS_STORAGE_BUCKET_NAME` | (vacío) | Nombre exacto del bucket (case-sensitive). |
| `AWS_S3_REGION_NAME` | `sa-east-1` | Región del bucket. Verificar en consola S3. |
| `AWS_S3_ENDPOINT_URL` | (vacío) | Solo para R2/MinIO/B2. AWS nativo queda vacío. |
| `MEDIA_LOCAL_FALLBACK_ENABLED` | `true` | `false` post-cutover (cuando `_BACKFILL_COMPLETE` existe). |
| `MEDIA_SIGNED_URL_TTL_SECONDS` | `900` | Cap 604800 (7 días, SigV4 max). |

### Biometría

| Variable | Default | Descripción |
|---|---|---|
| `BIOMETRIC_SUSPENDED` | `0` | `1` para suspender mutaciones biométricas. |
| `DP4500_BASE_URL` | (vacío) | URL del servicio DP4500. En WSL: `http://<gateway-ip>:8001`. |

### Backups (ver `docs/backups.md` para detalles)

| Variable | Default | Descripción |
|---|---|---|
| `BACKUPS_DIR` | (vacío) | Directorio de dumps. Default histórico: `/var/lib/clinica/backups`. |
| `BACKUP_DAILY_KEEP` | `7` | Retención de dumps diarios. |
| `BACKUP_WEEKLY_KEEP` | `4` | Retención de dumps semanales. |
| `BACKUP_RATE_LIMIT_TRIGGER_SECONDS` | `60` | Rate limit del trigger. |
| `BACKUP_RATE_LIMIT_DOWNLOAD_SECONDS` | `0` | Sin rate limit. |
| `BACKUP_RATE_LIMIT_DELETE_SECONDS` | `30` | Rate limit de delete. |

---

## Anexo C — Management commands del proyecto

Lista de management commands custom del proyecto (los de Django no se listan). Todos viven bajo `backend/*/management/commands/`.

| Comando | Módulo | Para qué sirve |
|---|---|---|
| `seed_client_baseline` | `accounts` | Deploy de cliente real: roles + sucursal + admin + kiosk + catálogos. ⭐ Recomendado para producción. |
| `seed_production_baseline` | `accounts` | Legado. Mínimo absoluto sin catálogos. Reemplazado por `seed_client_baseline`. |
| `seed_pdf_baseline` | `accounts` | Demo: 3 sucursales + 4 admins + 4 especialistas + 2 prospectos + 2 pacientes demo + catálogos. Rechaza correr con `DJANGO_ENVIRONMENT=production`. |
| `seed_branch_test_scenarios` | `accounts` | Test multi-sucursal. Requiere `seed_pdf_baseline` previo. |
| `reset_pdf_baseline` | `accounts` | Wipe + reseed atómico del PDF demo en una sola transacción. |
| `reset_extended_demo` | `accounts` | Variante extendida de `reset_pdf_baseline` con 5° especialista, agendas rebalanceadas y procedimiento `Depilacion 2 x 1`. |
| `ensure_main_branch` | `accounts` | Crea o normaliza `Sede Principal` sin tocar datos clínicos. |
| `purge_data_keep_admin` | `accounts` | Wipe de datos de negocio preservando usuarios admin. |
| `create_backup` | `backups` | Dump de la DB + retención. **Ver `docs/backups.md`.** |
| `backfill_media` | `config` | Sube archivos de `MEDIA_ROOT` al bucket S3. Parte de cloud-storage-migration. |
| `audit_log_retention` | `config` | Borra filas de `AuditLog` con más de `--days` (default 90). |
| `normalize_draft_templates` | `biometric` | Reescribe valores `bytes`-typed en conversion drafts a base64. |
| `reconcile_pending_cascades` | `dp4500_integration` | Reconcilia cascadas pendientes entre el sistema y DP4500. |

---

## Historial de cambios

| Commit | Qué cambió |
|---|---|
| `7b107bc` | Creación de la guía. Reemplaza `droplet-setup-from-scratch.md` y `droplet-deploy-updates.md`. Agrega guía VPS genérica, comando `seed_client_baseline`, `.env.example`, `deploy.sh.example`, spec OpenSpec y 13 tests. |
| `3332186` | Deploy script interactivo: pide VPS_HOST, PROJECT_PATH, etc. la primera vez y los guarda en `scripts/.deploy-config`. Arregla bug de paths hardcoded en el heredoc SSH. |
| `33d67c4` | Changelog footer en la guía. |
| `7f47e40` | Reorganiza la sección 5.2 con una sección dedicada "Cómo poblar la base de datos" con tabla comparativa de los 4 seeds. Corrige gaps del deploy en DO: `sudo` NOPASSWD para `deploy`, `pg_hba.conf` md5, `GRANT ON SCHEMA public`, `python3.12-venv`, swap para Node build, DNS antes de certbot, troubleshooting extendido. |
| `b4945b3` + cambios posteriores | Sección 10 dividida en 10.1 (deploy normal), 10.2 (suspender biométrica) y 10.3 (rollback). Documenta el flujo `BIOMETRIC_SUSPENDED` + `VITE_BIOMETRIC_SUSPENDED`, el helper `scripts/biometric_suspension.sh`, la validación post-deploy con `curl` + cookie/CSRF, y los comandos systemd de la PC del lector. Menciona las migraciones nuevas que se aplican automáticamente (`biometric/0001-0003`, `customers/0010-0012`, `catalogs/0007`, `operations/0025`). |
| (revisión Q4 2026) | Reescritura completa. Refleja: (1) cloud-storage-migration slices 1-4 (storage S3 + presigned URLs + audit), (2) backups canónicos via `create_backup` management command (en vez de `pg_dump` script), (3) `scripts/deploy.sh.example` requiere copia explícita, (4) compliance Bolivia Ley 164, (5) tabla comparativa de cambios, (6) anexos B (env vars) y C (management commands), (7) troubleshooting actualizado con 403 CSRF, 404 signed-URL, AccessDenied S3, fcntl en Windows, `command not found` de deploy.sh. |
| (revisión local, esta sesión) | Actualización del archivo en disco (no en repo, sigue en `.gitignore` línea 94). Agrega la §11.7 cutover a AWS S3 mergeada en slice-5. Mantiene los 3 anexos y la sección de compliance Bolivia Ley 164. |
