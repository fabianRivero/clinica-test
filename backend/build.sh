#!/bin/bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Running database migrations ==="
python manage.py migrate --noinput

echo "=== Installing frontend dependencies ==="
cd ../frontend/aesthetic-clinic
npm install

echo "=== Building frontend ==="
npm run build

echo "=== Collecting static files ==="
cd ../backend
python manage.py collectstatic --noinput
