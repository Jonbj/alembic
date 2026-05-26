#!/usr/bin/env bash
# Dedicated backtest launcher — runs inside the Docker backtest container.
#
# Usage:
#   ./scripts/backtest.sh --start 2025-12-01 --end 2025-12-31 --run-id gkg-dec25-v1
#   ./scripts/backtest.sh --start 2025-12-01 --end 2025-12-31 --run-id gkg-dec25-v1 --concurrency 3
#
# The backtest service uses the same image as the worker (Python 3.11, all deps)
# and overrides DATABASE_URL to reach the postgres container on the Docker network.
# logs/ and reports/ are volume-mounted so output persists on the host.
#
# On first run (or after Dockerfile/deps changes):
#   docker compose build backtest

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Ensure logs dir exists for volume mount
mkdir -p logs reports

LOG="logs/backtest_$(date +%Y%m%d_%H%M%S).log"

echo "Starting backtest container — logging to $LOG"
echo "Args: $*"
echo ""

docker compose --profile backtest run --rm \
    backtest \
    python scripts/run_backtest.py "$@" \
    2>&1 | tee "$LOG"
