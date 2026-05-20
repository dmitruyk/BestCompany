#!/bin/sh
set -e

# Startup (production):
#   1. wait for PostgreSQL
#   2. migrate          — apply committed migrations (makemigrations is dev-only)
#   3. collectstatic    — also run at image build; refresh on container start
#   4. ensure_default_admin
#   5. exec CMD (gunicorn)

if [ -f /app/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /app/.env
  set +a
fi

missing=""
for var in DB_PASSWORD DJANGO_SECRET_KEY; do
  eval "value=\${$var}"
  if [ -z "$value" ]; then
    missing="$missing $var"
  fi
done

if [ -n "$missing" ]; then
  echo "ERROR: Required variables are not set:$missing" >&2
  echo "Set them in idea_factory/.env before 'make build-docker'." >&2
  exit 1
fi

mkdir -p /app/media /app/logs

echo "Waiting for database (${DB_HOST:-localhost}:${DB_PORT:-5432})..."
python - <<'PY'
import os
import sys
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "idea_factory.settings")

import django

django.setup()

from django.db import connection

host = os.environ.get("DB_HOST", "localhost")
port = os.environ.get("DB_PORT", "5432")
attempts = int(os.environ.get("DB_WAIT_ATTEMPTS", "30"))
delay = float(os.environ.get("DB_WAIT_DELAY", "2"))

for attempt in range(1, attempts + 1):
    try:
        connection.ensure_connection()
        print(f"Database ready ({host}:{port}).")
        sys.exit(0)
    except Exception as exc:
        if attempt == attempts:
            print(
                f"ERROR: Database not reachable at {host}:{port} after "
                f"{attempts} attempts: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Database not ready (attempt {attempt}/{attempts}): {exc}")
        time.sleep(delay)
PY

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Ensuring default admin user..."
python manage.py ensure_default_admin

exec "$@"
