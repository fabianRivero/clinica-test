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

# NO forzar DJANGO_USE_LOCAL_DB — deja que .env decida
# Si .env tiene DJANGO_USE_LOCAL_DB=False, usa Supabase

# Detectar Python del entorno virtual si existe
if [ -x "env/bin/python" ]; then
    PYTHON="env/bin/python"
elif [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python"
fi

echo -e "${CYAN}[supabase_reset] Reiniciando base de datos Supabase...${NC}"

# Confirmar que se usa Supabase
DB_HOST=$("$PYTHON" -c "
from dotenv import load_dotenv
load_dotenv('$BACKEND_ROOT/.env')
import os
print(os.getenv('DJANGO_DB_HOST', 'not set'))
" 2>/dev/null || echo "unknown")

echo -e "${CYAN}[supabase_reset] Host: $DB_HOST${NC}"

# Vaciar datos de negocio preservando admin
echo -e "${CYAN}[supabase_reset] Purgeando datos...${NC}"
"$PYTHON" manage.py purge_data_keep_admin --force --username admin.general

# Sembrar baseline PDF
echo -e "${CYAN}[supabase_reset] Cargando baseline PDF...${NC}"
"$PYTHON" manage.py seed_pdf_baseline

# Asegurar sede principal y categorías base
echo -e "${CYAN}[supabase_reset] Normalizando sede principal y categorías...${NC}"
"$PYTHON" manage.py ensure_main_branch

# Sembrar escenarios multi-sucursal
echo -e "${CYAN}[supabase_reset] Cargando escenarios de prueba multi-sucursal...${NC}"
"$PYTHON" manage.py seed_branch_test_scenarios

echo -e "${YELLOW}[supabase_reset] Usuarios demo: admin.general / admin123456${NC}"
echo -e "${YELLOW}[supabase_reset] Credenciales tablet kiosko verificalas en la salida de seed_pdf_baseline.${NC}"
echo -e "${GREEN}[supabase_reset] Base de datos Supabase reseteada correctamente.${NC}"