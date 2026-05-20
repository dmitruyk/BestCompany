#!/usr/bin/env bash
# Cron script for autonomous company loop.
# Add to crontab (e.g. daily at 9am):
#   0 9 * * * /path/to/idea_factory/scripts/run_autonomous_cron.sh
#
# Or every 6 hours: 0 */6 * * * /path/to/idea_factory/scripts/run_autonomous_cron.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
python manage.py run_autonomous_loop
