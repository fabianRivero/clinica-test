# Guia: Configurar Droplet desde Cero

## Clinica Estetica - Deployment en DigitalOcean

---

## 1. Crear el Droplet

En DigitalOcean:
- **Imagen:** Ubuntu 22.04 LTS
- **Size:** Segun necesidades (la mas basica funciona para empezar)
- **Region:** La mas cercana a vos
- **SSH Keys:** Agregar tu clave publica

---

## 2. Configuracion Inicial del Droplet

```bash
ssh root@tu-droplet-ip

apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx postgresql postgresql-contrib
```

---

## 3. PostgreSQL

```bash
sudo -u postgres psql
```

Dentro de psql:
```sql
CREATE DATABASE clinica;
CREATE USER admin_general WITH PASSWORD 'admin123456';
GRANT ALL PRIVILEGES ON DATABASE clinica TO admin_general;
\q
```

---

## 4. Clonar Repo y Estructura

```bash
mkdir -p /var/www
cd /var/www
git clone https://github.com/fabianRivero/clinica-test.git clinica
chown -R www-data:www-data /var/www/clinic
```

---

## 5. Backend

```bash
cd /var/www/clinic/backend
python3 -m venv env
env/bin/pip install -r requirements.txt
```

### 5.1 Crear .env

```bash
cat > .env << 'EOF'
DJANGO_SECRET_KEY=genera-una-nueva-key-unica
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com

DJANGO_DB_ENGINE=django.db.backends.postgresql
DJANGO_DB_NAME=clinica
DJANGO_DB_USER=admin_general
DJANGO_DB_PASSWORD=admin123456
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
DJANGO_DB_SSLMODE=prefer

DJANGO_USE_LOCAL_DB=False
DJANGO_CORS_ALLOWED_ORIGINS=https://tu-dominio.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://tu-dominio.com
DJANGO_CSRF_COOKIE_SECURE=1
DJANGO_SESSION_COOKIE_SECURE=1
EOF
```

### 5.2 Migraciones y Datos Iniciales

```bash
env/bin/python manage.py migrate
env/bin/python manage.py seed_production_baseline
env/bin/python manage.py collectstatic --noinput
```

**Output esperado del seed:**
```
[PROD] Iniciando seed de produccion...
  Admin General creado: Administrador General del Sistema
  Tablet Kiosko creado: KIOSKO-PRINCIPAL
[PROD] Seed de produccion completado.
Credenciales creadas:
  Admin General: admin.general / admin123456
  Nombre: Administrador General del Sistema
  Sucursal: Sede Principal
  Tablet Kiosko: KIOSKO-PRINCIPAL / tablet-verify-123
  URL Admin: https://tu-dominio.com/admin
```

---

## 6. Frontend

```bash
cd /var/www/clinic/frontend/aesthetic-clinic
npm install
npm run build
```

---

## 7. Nginx

```bash
cat > /etc/nginx/sites-available/clinica << 'EOF'
server {
    server_name tu-dominio.com www.tu-dominio.com;

    root /var/www/clinic/frontend/aesthetic-clinic/dist;
    index index.html;

    location /static/ {
        alias /var/www/clinic/backend/staticfiles/;
    }

    location /media/ {
        alias /var/www/clinic/backend/media/;
    }

    location /api/ {
        proxy_pass http://unix:/var/www/clinic/clinica.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin/ {
        proxy_pass http://unix:/var/www/clinic/clinica.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

ln -s /etc/nginx/sites-available/clinica /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

---

## 8. SSL con Let's Encrypt

```bash
certbot --nginx -d tu-dominio.com -d www.tu-dominio.com
```

---

## 9. Gunicorn como Servicio

```bash
cat > /etc/systemd/system/gunicorn.service << 'EOF'
[Unit]
Description=Gunicorn Django daemon for clinica
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/clinic/backend
EnvironmentFile=/var/www/clinic/backend/.env
ExecStart=/var/www/clinic/backend/env/bin/gunicorn \
    --workers 2 \
    --bind unix:/var/www/clinic/clinica.sock \
    --timeout 120 \
    --access-logfile /var/www/clinic/gunicorn-access.log \
    --error-logfile /var/www/clinic/gunicorn-error.log \
    config.wsgi:application

Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable gunicorn
systemctl start gunicorn
```

---

## 10. Script de Deploy en Maquina Local

En tu **maquina local**, crear `deploy.sh`:

```bash
#!/bin/bash
set -e

DROPLET_HOST="tu-droplet-ip"
DROPLET_USER="root"
PROJECT_PATH="/var/www/clinic"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_step() { echo -e "${GREEN}[STEP]${NC} $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo_step "Iniciando deploy a $DROPLET_HOST..."

ssh $DROPLET_USER@$DROPLET_HOST << 'SSHEOF'
set -e
PROJECT_PATH="/var/www/clinic"
cd $PROJECT_PATH

echo_step "1. Pull cambios de GitHub..."
sudo -u www-data git pull origin main

echo_step "2. Instalar dependencias Python..."
cd backend
sudo -u www-data env/bin/pip install -q -r requirements.txt
cd ..

echo_step "3. Build frontend..."
cd frontend/aesthetic-clinic
sudo -u www-data npm install
sudo -u www-data npm run build
cd ../..

echo_step "4. Migraciones..."
sudo -u www-data env/bin/python backend/manage.py migrate --noinput

echo_step "5. Static files..."
sudo -u www-data env/bin/python backend/manage.py collectstatic --noinput

echo_step "6. Reiniciar Gunicorn..."
sudo systemctl restart gunicorn
sleep 2

echo_step "7. Verificar Nginx..."
sudo nginx -t

echo ""
echo_step "Deploy completado!"
echo "  URL: https://tu-dominio.com"
echo "  Admin: https://tu-dominio.com/admin"
SSHEOF

echo_step "Verificando sitio..."
sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://tu-dominio.com/ || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}[OK]${NC} Sitio responde correctamente"
else
    echo_error "Sitio no responde (codigo: $HTTP_CODE)"
fi
EOF

chmod +x deploy.sh
```

---

## Resumen de Archivos Configurados

| Archivo | Ubicacion | Proposito |
|---------|-----------|-----------|
| .env | /var/www/clinic/backend/.env | Credenciales Django |
| Nginx config | /etc/nginx/sites-available/clinica | Proxy reverso + SSL |
| Gunicorn service | /etc/systemd/system/gunicorn.service | Demonio auto-inicio |
| deploy.sh | Maquina local | Deploy automatico |

---

## Comandos Utiles en el Droplet

```bash
# Ver estado de Gunicorn
sudo systemctl status gunicorn

# Reiniciar Gunicorn
sudo systemctl restart gunicorn

# Ver logs de Gunicorn
sudo journalctl -u gunicorn -f

# Ver logs de acceso
tail -f /var/www/clinic/gunicorn-access.log

# Ver logs de error
tail -f /var/www/clinic/gunicorn-error.log

# Ver logs de Nginx
sudo tail -f /var/log/nginx/error.log
```

---

## Credenciales Creadas

| Servicio | Usuario | Contrasena |
|----------|---------|------------|
| Admin Django | admin.general | admin123456 |
| Tablet Kiosko | KIOSKO-PRINCIPAL | tablet-verify-123 |
| PostgreSQL | admin_general | admin123456 |

---

## Cambiar Contrasenas

### 1. Cambiar Contrasena de PostgreSQL

```bash
# Conectar a PostgreSQL como postgres
sudo -u postgres psql

# Cambiar contrasena del usuario
ALTER USER admin_general WITH PASSWORD 'nueva_contrasena_segura';

# Salir de psql
\q

# Actualizar .env
sed -i "s/DJANGO_DB_PASSWORD=.*/DJANGO_DB_PASSWORD=nueva_contrasena_segura/" /var/www/clinic/backend/.env

# Reiniciar Gunicorn para aplicar cambios
sudo systemctl restart gunicorn
```

### 2. Cambiar Contrasena del Admin Django

```bash
cd /var/www/clinic/backend

# Opcion A: Usando Django shell
sudo -u www-data env/bin/python manage.py shell << 'EOF'
from accounts.models import Usuario
user = Usuario.objects.get(username='admin.general')
user.set_password('nueva_contrasena_segura')
user.save()
print(f"Contrasena de {user.username} cambiada exitosamente")
EOF

# Opcion B: Usando createsuperuser (si no existe, lo crea)
sudo -u www-data env/bin/python manage.py changepassword admin.general
```

### 3. Cambiar Contrasena del Tablet Kiosko

```bash
cd /var/www/clinic/backend

sudo -u www-data env/bin/python manage.py shell << 'EOF'
from operations.models import TabletKiosko
kiosko = TabletKiosko.objects.get(codigo='KIOSKO-PRINCIPAL')
kiosko.set_clave('nueva_clave_segura')
kiosko.save()
print(f"Clave de {kiosko.codigo} cambiada exitosamente")
EOF
```

### 4. Cambiar DJANGO_SECRET_KEY

**Importante:** Cambiar la SECRET_KEY invalida todas las sesiones activas y tokens existentes. Los usuarios deberan login de nuevo.

```bash
# Generar una nueva key
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Actualizar .env con la nueva key
sed -i 's/DJANGO_SECRET_KEY=.*/DJANGO_SECRET_KEY=tu_nueva_key_aqui/' /var/www/clinic/backend/.env

# Reiniciar Gunicorn
sudo systemctl restart gunicorn
```

###5. Cambiar Contrasena de Root del Droplet

**Desde DigitalOcean (metodo recomendado):**

1. Ir a DigitalOcean -> Droplet -> Access -> Console
2. Hacer click en "Reset Root Password"
3. Recibiras un email con la nueva contrasena temporal
4. En la consola, login con root y la contrasena temporal
5. Te pedira cambiar la contrasena inmediatamente

**Desde la consola (si ya tienes acceso):**

```bash
passwd root
# Te pedira la contrasena actual y luego la nueva
```

### 6. Agregar SSH Key para Acceso sin Contrasena

```bash
# En tu maquina local, generar SSH key (si no tienes)
ssh-keygen -t ed25519 -C "tu-email@ejemplo.com"

# Copiar la clave publica al droplet
ssh-copy-id root@tu-droplet-ip

# Probar que funciona
ssh root@tu-droplet-ip
```

### 7. Configurar SSH sin Contrasena desde el Droplet a GitHub

```bash
# En el droplet, generar SSH key para GitHub
ssh-keygen -t ed25519 -C "droplet@tu-dominio.com" -f /var/www/.ssh/github_deploy

# Copiar la clave publica
cat /var/www/.ssh/github_deploy.pub
# Agregarla en GitHub -> Settings -> Deploy Keys

# Configurar SSH para usar esta key
mkdir -p /var/www/.ssh
chown www-data:www-data /var/www/.ssh
chmod 700 /var/www/.ssh
cp /var/www/.ssh/github_deploy /var/www/.ssh/
chown www-data:www-data /var/www/.ssh/github_deploy
chmod 600 /var/www/.ssh/github_deploy

cat > /var/www/.ssh/config << 'EOF'
Host github.com
    IdentityFile /var/www/.ssh/github_deploy
    UserKnownHostsFile /var/www/.ssh/known_hosts
EOF
chown www-data:www-data /var/www/.ssh/config
chmod 600 /var/www/.ssh/config

# Probar conexion
sudo -u www-data GIT_SSH_COMMAND="ssh -i /var/www/.ssh/github_deploy" git pull origin main
```

---

## Estructura del Proyecto en el Droplet

```
/var/www/clinic/
├── backend/
│   ├── env/                  # Virtualenv Python
│   ├── .env                  # Variables de entorno
│   ├── manage.py
│   ├── staticfiles/          # Archivos estaticos Django
│   └── media/                # Archivos media (QR, recibos, etc.)
├── frontend/
│   └── aesthetic-clinic/
│       └── dist/             # Build de React (servido por Nginx)
├── clinica.sock              # Socket Gunicorn
├── gunicorn-access.log
└── gunicorn-error.log
```
