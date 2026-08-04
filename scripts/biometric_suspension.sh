#!/bin/bash
# ============================================
# biometric_suspension.sh — toggle helper
# ============================================
#
# Helper reversible para suspender / re-habilitar la integración de
# huella en desarrollo local y en producción. Forma parte del change
# OpenSpec `suspend-fingerprint-integration`. NO borra código, modelos,
# servicios, archivos ni unidades systemd: sólo muta
# `BIOMETRIC_SUSPENDED` en `backend/.env` y rebuilda el frontend con
# el flag correspondiente.
#
# Subcomandos: local on/off, prod on/off, status. Ver `./scripts/
# biometric_suspension.sh --help` para detalles.
# ============================================

set -e

# ============================================
# CONFIGURACIÓN
# ============================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_ENV="$REPO_ROOT/backend/.env"
FRONTEND_DIR="$REPO_ROOT/frontend/aesthetic-clinic"
DIST_DIR="$FRONTEND_DIR/dist"
DEPLOY_SCRIPT="$REPO_ROOT/scripts/deploy.sh"
SYSTEMD_UNITS=(fingerprint-agent cloudflared)

# ============================================
# HELPERS (mismo estilo que deploy.sh.example)
# ============================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_step() { echo -e "${GREEN}[STEP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

# set_env_flag FILE KEY VALUE
# Reemplaza la línea que empieza con KEY= si existe; si no, la agrega
# al final precedida por un newline (mantiene el patrón de
# deploy.sh.example).
set_env_flag() {
    local file="$1"
    local key="$2"
    local value="$3"

    if [ ! -f "$file" ]; then
        log_error "No existe $file"
        exit 1
    fi

    if grep -qE "^${key}=" "$file"; then
        local escaped_value
        escaped_value=$(printf '%s\n' "$value" | sed -e 's/[\/&]/\\&/g')
        sed -i "s/^${key}=.*/${key}=${escaped_value}/" "$file"
        log_step "${key}=${value} actualizado en $(basename "$file")"
    else
        local newline=""
        if [ -s "$file" ] && [ "$(tail -c1 "$file" | wc -l)" -eq 0 ]; then
            newline=$'\n'
        fi
        printf '%s%s=%s\n' "$newline" "$key" "$value" >> "$file"
        log_step "${key}=${value} agregado al final de $(basename "$file")"
    fi
}

# build_frontend BOOL
# Rebuilda el bundle con VITE_BIOMETRIC_SUSPENDED=<bool>.
build_frontend() {
    local vite_flag="$1"

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_error "No existe $FRONTEND_DIR"
        exit 1
    fi

    log_step "Rebuildeando frontend con VITE_BIOMETRIC_SUSPENDED=$vite_flag"
    (
        cd "$FRONTEND_DIR"
        VITE_BIOMETRIC_SUSPENDED="$vite_flag" npm run build
    )
    log_step "Build OK. Artefactos en $DIST_DIR"
}

# status_report
# Lee BIOMETRIC_SUSPENDED del .env, busca el flag embebido en dist/ y
# consulta systemctl para las unidades listadas. Best-effort: no
# aborta si una falla.
status_report() {
    echo "=========================================="
    log_step "Estado de la suspensión biométrica"
    echo "=========================================="

    if [ -f "$BACKEND_ENV" ]; then
        local current
        current=$(grep -E "^BIOMETRIC_SUSPENDED=" "$BACKEND_ENV" || true)
        if [ -n "$current" ]; then
            echo "  backend/.env   : $current"
        else
            echo "  backend/.env   : BIOMETRIC_SUSPENDED no definido"
        fi
    else
        echo "  backend/.env   : NO EXISTE"
    fi

    if [ -d "$DIST_DIR" ]; then
        local embedded
        embedded=$(grep -rE "BIOMETRIC_SUSPENDED" "$DIST_DIR" 2>/dev/null \
            | head -3 || true)
        if [ -n "$embedded" ]; then
            echo "  dist/ embebido :"
            echo "$embedded" | sed 's/^/    /'
        else
            echo "  dist/ embebido : no se encontró BIOMETRIC_SUSPENDED en dist/"
        fi
    else
        echo "  dist/          : NO EXISTE (frontend sin build)"
    fi

    echo ""
    echo "  systemd units  :"
    if command -v systemctl >/dev/null 2>&1; then
        local unit enabled active
        for unit in "${SYSTEMD_UNITS[@]}"; do
            # systemctl imprime a stdout el estado (incluido "not-found").
            # Capturamos stdout y descartamos stderr; si falla, fallback.
            enabled=$(systemctl is-enabled "$unit" 2>/dev/null) || enabled="unknown"
            active=$(systemctl is-active "$unit" 2>/dev/null) || active="unknown"
            echo "    $unit: enabled=$enabled active=$active"
        done
    else
        echo "    systemctl no disponible"
    fi
    echo ""
    echo "  Recordatorio   : estos checks son best-effort y no requieren"
    echo "                   sudo. Ver scripts/deploy.sh.example para"
    echo "                   los comandos operador con sudo."
}

# maybe_rebuild ARG...
# Avisa si dist/ no existe (rebuild obligatorio) o si el usuario pasó
# --rebuild. Usado por prod on/off.
maybe_rebuild() {
    if [ ! -d "$DIST_DIR" ]; then
        log_warn "dist/ no existe — rebuild obligatorio"
        return
    fi
    local arg found=0
    for arg in "$@"; do
        if [ "$arg" = "--rebuild" ]; then
            found=1
            break
        fi
    done
    if [ "$found" -eq 1 ]; then
        log_step "--rebuild pasado: rebuildando dist/ sí o sí"
    else
        log_step "dist/ existe. Pasá --rebuild si querés regenerar el bundle."
    fi
}

# print_local_next_steps
# Mensaje común para local on/off: el backend debe reiniciarse para
# tomar el flag del .env, y Vite dev server si está corriendo.
print_local_next_steps() {
    echo ""
    log_step "Listo. Próximos pasos:"
    echo "  1. Reiniciar el backend para que tome el flag:"
    echo "       cd backend && env/bin/python manage.py runserver"
    echo "  2. Si tenés Vite dev server corriendo (npm run dev), reiniciarlo:"
    echo "       cd frontend/aesthetic-clinic && npm run dev"
    echo "  3. Verificá con: ./scripts/biometric_suspension.sh status"
}

# ============================================
# SUBCOMANDOS
# ============================================
cmd_local_on() {
    log_step "local ON — suspendiendo mutaciones biométricas en desarrollo"
    set_env_flag "$BACKEND_ENV" "BIOMETRIC_SUSPENDED" "1"
    build_frontend "true"
    print_local_next_steps
}

cmd_local_off() {
    log_step "local OFF — re-habilitando mutaciones biométricas en desarrollo"
    set_env_flag "$BACKEND_ENV" "BIOMETRIC_SUSPENDED" "0"
    build_frontend "false"
    print_local_next_steps
}

cmd_prod_on() {
    maybe_rebuild "$@"
    log_step "prod ON — preparando artefactos para forward (BIOMETRIC_SUSPENDED=1)"
    set_env_flag "$BACKEND_ENV" "BIOMETRIC_SUSPENDED" "1"
    build_frontend "true"
    echo ""
    log_step "Artefactos preparados localmente. Para empujar al VPS:"
    echo "       ./scripts/deploy.sh"
    echo ""
    echo "  Después del deploy, validar con el bloque 'Validación gateada'"
    echo "  de scripts/deploy.sh.example (esperado: HTTP 503 + código"
    echo "  BIOMETRIC_SUSPENDED)."
}

cmd_prod_off() {
    maybe_rebuild "$@"
    log_step "prod OFF — preparando artefactos para rollback (BIOMETRIC_SUSPENDED=0)"
    set_env_flag "$BACKEND_ENV" "BIOMETRIC_SUSPENDED" "0"
    build_frontend "false"
    echo ""
    log_step "Artefactos preparados localmente. Para empujar el rollback al VPS:"
    echo "       BIOMETRIC_SUSPENDED=0 VITE_BIOMETRIC_SUSPENDED=false ./scripts/deploy.sh"
    echo ""
    echo "  Después del deploy, validar que NO se devuelva HTTP 503"
    echo "  en el endpoint gateado (ver scripts/deploy.sh.example)."
}

# ============================================
# ENTRY POINT
# ============================================
print_help() {
    cat <<EOF
biometric_suspension.sh — helper reversible de suspensión biométrica
(OpenSpec change: suspend-fingerprint-integration)

Uso: ./scripts/biometric_suspension.sh <subcomando> [--rebuild]

Subcomandos:
  local on     Suspende en desarrollo (backend/.env + bundle local).
  local off    Re-habilita en desarrollo.
  prod on      Prepara .env + bundle para forward al VPS.
  prod off     Prepara .env + bundle para rollback al VPS.
  status       Muestra el estado actual (env, dist embebido, systemd).
  --help       Muestra esta ayuda.

Banderas:
  --rebuild    En prod on/off, fuerza el rebuild del bundle aunque
               dist/ ya exista. En local on/off siempre se rebuilda.

Ejemplos:
  ./scripts/biometric_suspension.sh local on
  ./scripts/biometric_suspension.sh prod on --rebuild
  ./scripts/biometric_suspension.sh prod off
  ./scripts/biometric_suspension.sh status

Notas:
  - NO borra código, modelos, servicios ni unidades systemd: sólo
    muta BIOMETRIC_SUSPENDED en backend/.env y rebuilda el bundle.
  - Para prod, NO se conecta por SSH. Prepara los artefactos
    localmente; el operador corre ./scripts/deploy.sh.
  - Después de local on/off, reiniciar manage.py runserver para que
    el backend tome el nuevo flag.
EOF
}

main() {
    if [ $# -lt 1 ]; then
        print_help
        exit 1
    fi

    case "$1" in
        --help|-h|help)
            print_help
            ;;
        local)
            shift
            case "${1:-}" in
                on)  shift; cmd_local_on "$@" ;;
                off) shift; cmd_local_off "$@" ;;
                *)   log_error "Subcomando local desconocido: '${1:-}'"; print_help; exit 1 ;;
            esac
            ;;
        prod)
            shift
            case "${1:-}" in
                on)  shift; cmd_prod_on "$@" ;;
                off) shift; cmd_prod_off "$@" ;;
                *)   log_error "Subcomando prod desconocido: '${1:-}'"; print_help; exit 1 ;;
            esac
            ;;
        status)
            shift
            status_report
            ;;
        *)
            log_error "Subcomando desconocido: '$1'"
            print_help
            exit 1
            ;;
    esac
}

main "$@"
