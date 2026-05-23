#!/bin/bash
set -euo pipefail

# Colores
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Directorio raíz del backend
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_ROOT"

# Forzar el uso de base de datos LOCAL (SQLite)
export DJANGO_USE_LOCAL_DB=1

# Detectar Python del entorno virtual si existe
if [ -x "env/bin/python" ]; then
    PYTHON="env/bin/python"
elif [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python"
fi

echo -e "${CYAN}[local_reset] Reiniciando base de datos SQLite local...${NC}"

# Borrar base local previa
rm -f db.sqlite3

# Reconstruir esquema
echo -e "${CYAN}[local_reset] Ejecutando migraciones...${NC}"
"$PYTHON" manage.py migrate --no-input

# Sembrar base mínima y escenarios locales actuales
echo -e "${CYAN}[local_reset] Cargando baseline PDF...${NC}"
"$PYTHON" manage.py seed_pdf_baseline

echo -e "${CYAN}[local_reset] Normalizando sede principal y categorías...${NC}"
"$PYTHON" manage.py ensure_main_branch

echo -e "${CYAN}[local_reset] Cargando escenarios de prueba multi-sucursal...${NC}"
"$PYTHON" manage.py seed_branch_test_scenarios

echo -e "${YELLOW}[local_reset] Usuarios demo: admin.general / admin123456, admin.sucursal / admin123456${NC}"
echo -e "${YELLOW}[local_reset] Nota: el sistema ahora incluye wizard de creación de sucursales (3 pasos), gestión de admins de sucursal e historial/auditoría de cambios en sucursales.${NC}"
echo -e "${YELLOW}[local_reset] Nota: las credenciales de TabletKiosko se almacenan hasheadas; revisa la salida de seed_pdf_baseline para credenciales de prueba en texto plano.${NC}"
echo -e "${GREEN}[local_reset] Base de datos SQLite lista para pruebas locales.${NC}"
