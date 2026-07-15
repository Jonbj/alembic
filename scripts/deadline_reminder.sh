#!/usr/bin/env bash
# Deadline reminder with retry-until-acked semantics.
#
# Scheduled via host crontab (Europe/Rome):
#   11 9 * * *   scripts/deadline_reminder.sh   # daily check
#   @reboot      scripts/deadline_reminder.sh   # catch missed while host was off
#
# For each deadline in deadline_reminders.conf whose due date has arrived and
# that has NOT been acked (marker in ACK_DIR), sends a Telegram reminder. At
# most once per day per id. Keeps firing every day (+ on every boot) until the
# operator runs scripts/ack_deadline.sh <id>. If the host was off on the due
# date, the @reboot entry fires on the next boot — so the message is re-sent
# until acknowledged. Bots cannot confirm delivery, so "received" = explicit
# operator ack.
set -euo pipefail

PROJECT_DIR="/home/stefano/Documents/Projects/Alembic"
CONF="$PROJECT_DIR/scripts/deadline_reminders.conf"
ACK_DIR="$HOME/.alembic-deadline-acks"
mkdir -p "$ACK_DIR"

# Load Telegram credentials from .env (mirror daily_analysis.sh pattern)
TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [[ -f "$PROJECT_DIR/.env" ]]; then
    # shellcheck disable=SC1090
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
fi

tg_send() {
    local text="$1"
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[deadline] Telegram credentials not set — skipping send" >&2
        return 0
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$text" \
        > /dev/null || true
}

TODAY=$(date +%Y-%m-%d)

if [[ ! -f "$CONF" ]]; then
    echo "[deadline] config $CONF missing — nothing to do" >&2
    exit 0
fi

while IFS='|' read -r id due msg; do
    # skip comments / blank lines
    if [[ -z "$id" || "$id" =~ ^[[:space:]]*# ]]; then continue; fi

    ack_marker="$ACK_DIR/${id}.acked"
    lastsent="$ACK_DIR/${id}.lastsent"

    # acked → stop reminding
    if [[ -f "$ack_marker" ]]; then continue; fi
    # not yet due
    if [[ "$TODAY" < "$due" ]]; then continue; fi
    # already sent today (prevents boot + daily double-send)
    if [[ -f "$lastsent" && "$(cat "$lastsent")" == "$TODAY" ]]; then continue; fi

    if [[ "$TODAY" > "$due" ]]; then
        days_over=$(( ($(date -d "$TODAY" +%s) - $(date -d "$due" +%s)) / 86400 ))
        header="⚠️ <b>Deadline reminder — ${id}</b> (scaduta da ${days_over}g, due ${due})"
    else
        header="⏰ <b>Deadline reminder — ${id}</b> (due oggi ${due})"
    fi
    tg_send "${header}
${msg}"
    echo "$TODAY" > "$lastsent"
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') sent id=${id} due=${due}" >> "$ACK_DIR/${id}.log"
done < "$CONF"