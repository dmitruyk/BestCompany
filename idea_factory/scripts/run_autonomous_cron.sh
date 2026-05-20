#!/usr/bin/env bash
# Legacy wrapper — prefer scripts/run_company_ticker.sh or Docker idea-factory-ticker.
# Runs activity checks + autonomous loop + Monday weekly planning.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_company_ticker.sh"
