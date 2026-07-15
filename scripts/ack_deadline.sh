#!/usr/bin/env bash
# Acknowledge a deadline reminder — stops further reminders for that id.
# Usage: scripts/ack_deadline.sh <id>
#
# Creates a marker file in ACK_DIR that deadline_reminder.sh checks. Sends a
# Telegram confirmation (best-effort). The marker survives reboots (on disk),
# so acking is durable across sessions and host restarts.
set -euo pipefail

PROJECT_DIR="/home/stefano/Documents/Projects/Alembic"
ACK_DIR="$HOME/.alembic-deadline-acks"
id="${1:-}"

if [[ -z "$id" ]]; then
    echo "Usage: $0 <id>   (e.g. F8, S7_CUTOFF, S7_DECISION)" >&2
    exit 1
fi
mkdir -p "$ACK_DIR"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [[ -f "$PROJECT_DIR/.env" ]]; then
    # shellcheck disable=SC1090
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
fi

date -u '+%Y-%m-%dT%H:%M:%SZ' > "$ACK_DIR/${id}.acked"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') acked id=${id}" >> "$ACK_DIR/${id}.log"

if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="✅ <b>Deadline ${id} acked</b> — reminder fermati." \
        > /dev/null || true
fi

echo "Acked deadline '${id}'. Reminders for it will stop."