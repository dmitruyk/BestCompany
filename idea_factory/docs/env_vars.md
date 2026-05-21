# Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL_ID` | `gpt-oss:20b` | Tool-capable Ollama model (qwen3, gpt-oss, mistral-small3.2, etc.) |
| `OPENAI_API_KEY` | (required if openai) | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI model ID |
| `DJANGO_SECRET_KEY` | (dev default) | Django secret |
| `DJANGO_DEBUG` | `true` | Set `false` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |
| `DJANGO_PUBLIC_HOST` | (empty) | Public hostname (e.g. `manage.addmylegacy.com`); auto-added to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` |
| `CSRF_TRUSTED_ORIGINS` | (empty) | Comma-separated origins, e.g. `https://manage.addmylegacy.com` |
| `DJANGO_BEHIND_REVERSE_PROXY` | `false` | Set `true` when TLS terminates on Synology/nginx and Django receives `X-Forwarded-Proto` |
| `DB_HOST` | `192.168.0.230` | PostgreSQL host |
| `DB_PORT` | `5440` | PostgreSQL port |
| `DB_NAME` | `idea_factory` | Database name (create on server if missing) |
| `DB_USER` | `postgres` | PostgreSQL user |
| `DB_PASSWORD` | (required) | PostgreSQL password |
| `IDEA_FACTORY_LOG_FILE` | `idea_factory/logs/idea_factory.log` | Path to log file |
| `IDEA_FACTORY_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `GOOGLE_CALENDAR_CLIENT_ID` | (empty) | Google OAuth client ID for calendar sync |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | (empty) | Google OAuth client secret |
| `GOOGLE_CALENDAR_DEFAULT_REMINDERS` | `60,1440` | Default reminder offsets in minutes (comma-separated) |
| `TICKER_ENABLED` | `true` | Set `false` to disable background ticker |
| `TICKER_INTERVAL_SECONDS` | `3600` | Seconds between ticks in Docker `idea-factory-ticker` |
| `TICKER_WEEKLY_PLANNING` | `true` | Run `run_weekly_planning` on Mondays from ticker |
| `TICKER_WEEKLY_PLANNING_HOUR` | `8` | Local hour (0–23) when Monday planning is allowed |
| `TICKER_STALE_PLANNING_HOURS` | `2` | Mark stuck `IN_PROGRESS` planning sessions as FAILED |
| `TICKER_TASK_EXECUTION` | `true` | Auto-run agent-assigned company tasks from the ticker |
| `TICKER_TASK_MAX_PER_COMPANY` | `2` | Max tasks executed per company per ticker tick |
| `TICKER_TASK_AUTONOMOUS_ONLY` | `false` | If `true`, only companies with Self-Run (`autonomous_mode`) |
| `TICKER_TASK_DUE_LOOKAHEAD_DAYS` | `7` | Start tasks whose `target_date` is within this many days (not only overdue) |

Copy `.env.example` to `.env` and load with `python-dotenv` or your preferred method.

## Docker / registry deployment

`make build-docker` copies your local `idea_factory/.env` into the image. The entrypoint loads `/app/.env`, then on each container start:

1. Waits for PostgreSQL (`DB_WAIT_ATTEMPTS` / `DB_WAIT_DELAY`, optional)
2. `migrate --noinput` — applies migrations committed in the repo
3. `collectstatic --noinput` — also run at image build
4. `ensure_default_admin`
5. Starts gunicorn

**Note:** `makemigrations` is for local development only (`make makemigrations`). Do not run it in production containers; create migration files locally, commit them, then rebuild/redeploy.

1. Edit `idea_factory/.env` (DB, secrets, `ALLOWED_HOSTS` including deploy host).
2. Build and push:

```bash
cd idea_factory
make build-push-docker
```

3. On the server, pull and run (no host `.env` required):

```bash
docker compose pull && docker compose up -d
```

This starts **two** services from the same image:

- `idea-factory` — gunicorn web UI (migrations, static, admin on start)
- `idea-factory-ticker` — `run_company_ticker --loop` (activity checks, autonomous loop, Monday planning)

One-shot ticker (host cron without Docker ticker):

```bash
make ticker-once
# or: scripts/run_company_ticker.sh
```

**Security:** the private registry image contains secrets from your build machine. Do not push to public registries. Rebuild after changing `.env`.

Optional runtime override: `docker run --env-file .env ...` or uncomment `env_file` in `docker-compose.yml`.
