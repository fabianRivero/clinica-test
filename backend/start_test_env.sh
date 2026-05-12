#!/bin/bash
set -e

# Directorio raíz del proyecto
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/backend"

# 1. Configurar entorno local
export DJANGO_USE_LOCAL_DB=1

echo "--- Configurando Base de Datos Local (SQLite) ---"

# 2. Reiniciar base de datos (usando el script que ya tenemos)
bash scripts/reset_test_db_local.sh

echo "--- Iniciando Servidor de Desarrollo en Modo Local ---"
echo "--- Los cambios en esta base de datos NO afectaran a Supabase ---"

# 3. Arrancar el servidor
python manage.py runserver
