#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Installing frontend dependencies ==="
cd "$SCRIPT_DIR/../frontend/aesthetic-clinic"
npm install

echo "=== Building frontend ==="
npm run build

echo "=== Collecting static files ==="
cd "$SCRIPT_DIR"
python manage.py collectstatic --noinput
