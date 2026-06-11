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
