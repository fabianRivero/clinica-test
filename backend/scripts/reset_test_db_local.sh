#!/bin/bash
set -e

# Colores
CYAN='\033[0;36m'
GREEN='\033[0;32m'
NC='\033[0m'

# Directorio raíz del backend
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_ROOT"

# Forzar el uso de base de datos LOCAL (SQLite)
export DJANGO_USE_LOCAL_DB=1

# Detectar Python
if [ -f "env/bin/python" ]; then
    PYTHON="env/bin/python"
else
    PYTHON="python"
fi

echo -e "${CYAN}[local_reset] Reiniciando base de datos SQLite...${NC}"

# Borrar base de datos local vieja
rm -f db.sqlite3

# Migrar (Crear tablas desde cero)
$PYTHON manage.py migrate --no-input

# Sembrar datos iniciales
$PYTHON manage.py seed_pdf_baseline

echo -e "${GREEN}[local_reset] Base de datos SQLite lista para tests.${NC}"
