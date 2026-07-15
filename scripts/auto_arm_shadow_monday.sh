#!/bin/bash
# Auto-arm Stage-2 shadow-mode model comparison every Monday morning, with
# pre-arm safety checks (all required containers running, not already armed).
# Scheduled via local crontab (Europe/Rome time): 0 9 * * 1
#
# Safe by construction: arming just sets a Redis key
# (shadow:model_comparison:started_at) that the already-reviewed,
# already-deployed Stage-2 feature reads. It self-disarms after 7 days via
# the existing run_shadow_comparison_report Celery beat task, which also
# sends the comparison report over the already-configured Telegram bot.
# This script does NOT touch the Alembic codebase or deploy anything — it
# only flips the same manual toggle an operator would flip by hand.
set -uo pipefail

LOG="/home/stefano/Documents/Projects/Alembic/logs/auto_arm_shadow.log"
mkdir -p "$(dirname "$LOG")"

log() { echo "$(date -Iseconds) $*" >> "$LOG"; }

log "=== auto-arm check starting ==="

REQUIRED_CONTAINERS="alembic-worker-1 alembic-worker-inference-1 alembic-beat-1 alembic-api-1 alembic-redis-1 alembic-postgres-1"
for c in $REQUIRED_CONTAINERS; do
    status=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo "missing")
    if [ "$status" != "running" ]; then
        log "ABORT: container $c is not running (status: $status) — not arming, check manually"
        exit 1
    fi
done

already_armed=$(docker exec alembic-redis-1 redis-cli GET shadow:model_comparison:started_at 2>/dev/null || echo "REDIS_ERROR")
if [ "$already_armed" = "REDIS_ERROR" ]; then
    log "ABORT: could not reach Redis — not arming, check manually"
    exit 1
fi
if [ -n "$already_armed" ]; then
    log "ABORT: shadow already armed since $already_armed — not re-arming (previous window may not have disarmed yet)"
    exit 1
fi

ts=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
if docker exec alembic-redis-1 redis-cli SET shadow:model_comparison:started_at "$ts" >> "$LOG" 2>&1; then
    log "ARMED at $ts (UTC) — 7-day window started, auto-report + disarm via Telegram when it closes"
else
    log "ABORT: redis-cli SET failed — not armed, check manually"
    exit 1
fi
