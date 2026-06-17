#!/usr/bin/env bash
# Daily Alembic trading analysis via Claude Code.
# Scheduled via system cron: 0 7 * * 1-5
# Output logged to: logs/daily_analysis_YYYY-MM-DD.log
# Sends a Telegram summary after the analysis completes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/daily_analysis_${DATE}.log"

# Load Telegram credentials from .env
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

tg_send() {
    local text="$1"
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[tg_send] Telegram credentials not set — skipping" >&2
        return
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="HTML" \
        -d text="$text" \
        > /dev/null
}

echo "=== Alembic Daily Analysis ${DATE} ===" | tee "$LOG_FILE"
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"

tg_send "⏳ <b>Analisi giornaliera Alembic avviata</b> (${DATE})
Claude Code sta analizzando i dati di ieri..."

cd "$PROJECT_DIR"

# Run Claude Code in non-interactive mode.
ANALYSIS_OUTPUT=$(claude --dangerously-skip-permissions -p "$(cat <<'PROMPT'
Sei in una sessione autonoma di analisi giornaliera del trading system Alembic.
Obiettivo: discovery approfondita dei problemi di ieri con analisi ragionata.

API_KEY="eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg"
BASE="http://localhost:8001/api"

Esegui in parallelo queste chiamate API (filtra al giorno precedente a oggi):
- GET $BASE/decisions?limit=200
- GET $BASE/trades?limit=200
- GET $BASE/signals?limit=100
- GET $BASE/trading/positions
- GET $BASE/trading/orders?limit=100

Poi controlla i log dei container:
  docker compose logs worker --since 24h 2>&1 | grep -E "ERROR|WARNING|semaphore|fallback|FinBERT|Ollama" | tail -50
  docker compose logs worker-inference --since 24h 2>&1 | grep -E "ERROR|WARNING|quantiz|FinBERT" | tail -30

Per ogni anomalia trovata spiega: cosa è successo, perché, impatto P&L, fix consigliato.

Cerca in particolare:
- Roundtrip < 30 min (buy+sell stesso simbolo nello stesso ciclo)
- BUY ripetuto > 3 volte in sequenza senza SELL intermedio
- SELL con sentiment positivo (bug A5)
- fallback_used=True su tutti i simboli in un periodo (Ollama giù)
- NO-ORDER (decisione presa ma ordine non creato)
- Score < 0.05 che hanno generato ordini
- Esplosioni di ordini identici nello stesso minuto (race condition scheduler)

Produci UNA risposta strutturata con queste 4 sezioni (usa testo plain, no markdown):

=== METRICHE GIORNATA ===
Trade chiusi / aperti, win rate, P&L netto, decisioni BUY/SELL/NO-ORDER

=== ANOMALIE TROVATE ===
[ordinata per impatto, dalla più grave]
Per ognuna: tipo | simboli | ora | causa | fix consigliato

=== STATO SISTEMA ===
Ollama: up/down, ore di downtime
FinBERT fallback rate (% decisioni con fallback_used=True)
Worker restart events

=== TOP 3 FIX PRIORITARI ===
Fix specifici da fare oggi (con file e funzione se possibile)

Sii conciso ma preciso. Un bug non descritto è un bug che si ripete domani.
PROMPT
)" 2>&1)

echo "$ANALYSIS_OUTPUT" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"

# Send full analysis to Telegram in chunks (max 4096 chars per message)
HEADER="📊 <b>Analisi Trading Alembic — ${DATE}</b>"

# Extract sections from output and send as Telegram message
# Telegram limit: 4096 chars. Split into chunks if needed.
FULL_MSG="${HEADER}

<pre>$(echo "$ANALYSIS_OUTPUT" | tail -200 | head -c 3800)</pre>"

tg_send "$FULL_MSG"

# If analysis is long, send the "TOP 3 FIX" section separately for visibility
FIXES=$(echo "$ANALYSIS_OUTPUT" | grep -A 20 "TOP 3 FIX" | head -25)
if [[ -n "$FIXES" ]]; then
    tg_send "🔧 <b>Top 3 fix prioritari — ${DATE}</b>

<pre>${FIXES}</pre>"
fi
