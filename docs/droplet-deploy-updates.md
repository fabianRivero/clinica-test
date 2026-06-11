# Guia: Deployar Actualizaciones al Droplet

## Clinica Estetica

---

## Metodo Automatico (Recomendado)

### Requisitos Previos

1. Tener `deploy.sh` en tu maquina local
2. Tener la IP del droplet configurada en `deploy.sh`
3. Tener acceso SSH al droplet

### Ejecutar Deploy

```bash
cd "/media/fabianrivero/disco-d/proyecto C"
./deploy.sh
```

### Que hace el script automaticamente

```
1. git pull          → Baja cambios de GitHub al droplet
2. pip install       → Instala dependencias Python nuevas
3. npm install       → Instala dependencias frontend nuevas
4. npm run build     → Reconstruye el frontend
5. migrate → Aplica migraciones de base de datos
6. collectstatic     → Copia archivos estaticos
7. restart gunicorn  → Recarga workers con codigo nuevo
8. curl test         → Verifica que el sitio responda
```

### Output Esperado

```
[STEP] Verificando configuracion...
[STEP] Iniciando deploy a 198.211.115.7...
[STEP] 1. Pull cambios de GitHub...
[STEP] 2. Instalar dependencias Python...
[STEP] 3. Build frontend...
[STEP] 4. Migraciones...
[STEP] 5. Static files...
[STEP] 6. Reiniciar Gunicorn...
[STEP] 7. Verificar Nginx...
[STEP] Deploy completado!
  URL: https://reactproject.site
  Admin: https://reactproject.site/admin
[STEP] Verificando sitio...
[OK] Sitio responde correctamente
[STEP] Deploy finalizado!
```

---

## Metodo Manual

Si el script automatico falla, podes hacer el deploy manualmente desde la consola del droplet:

### Paso 1: Pull de Cambios

```bash
cd /var/www/clinic
sudo -u www-data GIT_SSH_COMMAND="ssh -i /var/www/.ssh/github_deploy -o UserKnownHostsFile=/var/www/.ssh/known_hosts" git pull origin main
```

### Paso 2: Dependencias Python

```bash
cd /var/www/clinic/backend
sudo -u www-data env/bin/pip install -q -r requirements.txt
```

### Paso 3: Build Frontend

```bash
cd /var/www/clinic/frontend/aesthetic-clinic
sudo -u www-data npm install
sudo -u www-data npm run build
```

### Paso 4: Migraciones

```bash
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py migrate --noinput
```

### Paso 5: Static Files

```bash
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py collectstatic --noinput
```

### Paso 6: Reiniciar Gunicorn

```bash
sudo systemctl restart gunicorn
```

### Paso 7: Verificar

```bash
# Ver estado
sudo systemctl status gunicorn

# Probar sitio
curl -I https://reactproject.site
```

---

### Comando Unico (copiar y pegar todo junto)

```bash
cd /var/www/clinic && \
sudo -u www-data GIT_SSH_COMMAND="ssh -i /var/www/.ssh/github_deploy -o UserKnownHostsFile=/var/www/.ssh/known_hosts" git pull origin main && \
cd backend && sudo -u www-data env/bin/pip install -q -r requirements.txt && \
cd ../frontend/aesthetic-clinic && sudo -u www-data npm install && sudo -u www-data npm run build && \
cd ../.. && \
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py migrate --noinput && \
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py collectstatic --noinput && \
sudo systemctl restart gunicorn && \
curl -I https://reactproject.site
```

---

## Si Algo Sale Mal

### Gunicorn no levanta

```bash
# Ver logs
sudo journalctl -u gunicorn --no-pager -n 50

# Verificar syntax de .env
cat /var/www/clinic/backend/.env

# Verificar que el socket no exista trabado
ls -la /var/www/clinic/clinica.sock
rm -f /var/www/clinic/clinica.sock
sudo systemctl restart gunicorn
```

### Nginx no responde

```bash
# Testear configuracion
sudo nginx -t

# Ver logs
sudo tail -f /var/log/nginx/error.log

# Recargar
sudo systemctl reload nginx
```

### Frontend no carga

```bash
# Verificar que exista el build
ls -la /var/www/clinic/frontend/aesthetic-clinic/dist/

# Rebuild manual
cd /var/www/clinic/frontend/aesthetic-clinic
sudo -u www-data npm run build
```

### Base de datos con problemas

```bash
# Ver migraciones pendientes
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py showmigrations

# Hacer migrate manualmente
sudo -u www-data /var/www/clinic/backend/env/bin/python /var/www/clinic/backend/manage.py migrate
```

---

## Comandos de Emergencia

```bash
# Reiniciar todo
sudo systemctl restart gunicorn postgresql nginx

# Ver todos los servicios
sudo systemctl status gunicorn postgresql nginx

# Ver si algo esta escuchando en el puerto
sudo netstat -tlnp | grep -E '80|443|5432'

# Ver uso de recursos
htop
df -h
```

---

## Checklist Post-Deploy

- [ ] El sitio carga correctamente
- [ ] El admin de Django funciona
- [ ] La API responde (/api/)
- [ ] Los archivos estaticos cargan (/static/)
- [ ] No hay errores en los logs

---

## Frecuencia de Updates

Normalmente se hace deploy cuando:
- Se agregaron features nuevas
- Se corrigieron bugs
- Se actualizaron dependencias
- Se agregaron migraciones

**No es necesario hacer deploy si solo cambiaste CSS o archivos estaticos** (salvo que sean del build de frontend).

---

## Como Hacer Rollback

Si el deploy rompe algo y necesitas volver atras:

```bash
# En el droplet
cd /var/www/clinic
sudo -u www-data GIT_SSH_COMMAND="ssh -i /var/www/.ssh/github_deploy -o UserKnownHostsFile=/var/www/.ssh/known_hosts" git log --oneline -5

# Volver a un commit anterior
sudo -u www-data GIT_SSH_COMMAND="ssh -i /var/www/.ssh/github_deploy -o UserKnownHostsFile=/var/www/.ssh/known_hosts" git revert HEAD~1

# Reiniciar
sudo systemctl restart gunicorn
```

Despues de rollback, ejecutar deploy de nuevo cuando este corregido.

---

## Notas Importantes

1. **El deploy corta conexiones activas** - Los usuarios en sesion pueden experimentar un error momentaneo
2. **Las migraciones son automaticas** - Se aplican solas si hay cambios en modelos
3. **El orden importa** - Si el deploy hace cosas en orden diferente, puede fallar
4. **Siempre verificar** - Despues de deploy, verificar que todo funcione

---

## Credenciales del Sistema

| Servicio | Usuario | Contrasena |
|----------|---------|------------|
| Admin Django | admin.general | admin123456 |
| Tablet Kiosko | KIOSKO-PRINCIPAL | tablet-verify-123 |
| SSH | root | (la que configuraste) |
| PostgreSQL | admin_general | admin123456 |
