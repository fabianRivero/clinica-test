#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Ensuring main branch and base expense categories ==="
python manage.py ensure_main_branch

echo "=== Installing frontend dependencies ==="
cd "$SCRIPT_DIR/../frontend/aesthetic-clinic"
npm install

echo "=== Building frontend ==="
# OpenSpec change `suspend-fingerprint-integration` (PR #3):
# mirror the backend `BIOMETRIC_SUSPENDED` flag into the frontend build
# so the UI hides every biometric control and stops issuing capture /
# match / agent heartbeat requests. Default is "true" (production
# deployments suspend fingerprint); set `VITE_BIOMETRIC_SUSPENDED=false`
# in the environment before running this script to keep the original
# behaviour (e.g. local dev, staging, post-rollback).
VITE_BIOMETRIC_SUSPENDED="${VITE_BIOMETRIC_SUSPENDED:-true}" \
  npm run build

echo "=== Collecting static files ==="
cd "$SCRIPT_DIR"
python manage.py collectstatic --noinput
