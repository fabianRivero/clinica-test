#!/bin/bash

# Abortar en caso de error critico (excepto en el purge si el usuario no existe)
set -e

# Colores para la terminal
CYAN='\033[0;36m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Directorio raíz del backend
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_ROOT"

# Detectar el binario de Python
if [ -f "env/bin/python" ]; then
    PYTHON="env/bin/python"
elif [ -f "env/Scripts/python.exe" ]; then
    PYTHON="env/Scripts/python.exe"
else
    echo -e "${RED}[Error] No se encontró el entorno virtual en 'env/'${NC}"
    exit 1
fi

echo -e "${CYAN}[reset_pdf_baseline] Iniciando purge...${NC}"

# Intentamos el purge. Si falla porque el usuario no existe, lo ignoramos y seguimos
USERNAMES=${@:-"admin.general admin"}
PURGE_ARGS="manage.py purge_data_keep_admin --force"

for name in $USERNAMES; do
    PURGE_ARGS="$PURGE_ARGS --username $name"
done

$PYTHON $PURGE_ARGS || echo -e "${CYAN}[Nota] Algunos usuarios no existian, se procedera con seed limpio.${NC}"

echo -e "${GREEN}[reset_pdf_baseline] Purge completado. Iniciando seed base PDF...${NC}"
$PYTHON manage.py seed_pdf_baseline

echo -e "${GREEN}[reset_pdf_baseline] Seed completado correctamente.${NC}"
echo -e "${CYAN}[reset_pdf_baseline] Revisa arriba las credenciales de tablet kiosko generadas para pruebas.${NC}"
