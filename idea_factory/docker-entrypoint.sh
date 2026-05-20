#!/bin/sh
set -e

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

python manage.py migrate --noinput
python manage.py ensure_default_admin

exec "$@"
