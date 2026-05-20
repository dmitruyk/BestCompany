FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=idea_factory.settings

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Local .env from build machine (make build-docker ensures it exists)
COPY .env .env
COPY . .

# Bake static assets into the image; entrypoint runs collectstatic again on start.
RUN python manage.py collectstatic --noinput

RUN mkdir -p media logs \
    && chmod +x docker-entrypoint.sh docker-entrypoint-ticker.sh scripts/run_company_ticker.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "idea_factory.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "300", "--access-logfile", "-", "--error-logfile", "-"]
