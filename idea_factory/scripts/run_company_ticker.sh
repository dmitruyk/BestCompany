#!/usr/bin/env bash
# One-shot company activity ticker (autonomous loop + checks + Monday planning).
# Cron example (every hour):
#   0 * * * * /path/to/idea_factory/scripts/run_company_ticker.sh
#
# Or use Docker ticker service (recommended): docker compose up -d idea-factory-ticker

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
python manage.py run_company_ticker --once
