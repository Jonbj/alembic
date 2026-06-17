#!/usr/bin/env bash
# Daily Alembic trading analysis via Claude Code.
# Scheduled via system cron: 0 7 * * 1-5
# Output logged to: logs/daily_analysis_YYYY-MM-DD.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/daily_analysis_${DATE}.log"

echo "=== Alembic Daily Analysis ${DATE} ===" | tee "$LOG_FILE"
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

# Run Claude Code in non-interactive mode with the analysis prompt.
# --output-format stream-json gives structured output; pipe to plain text for readability.
claude --dangerously-skip-permissions -p "$(cat <<'PROMPT'
Sei in una sessione autonoma di analisi giornaliera del trading system Alembic.
Obiettivo: discovery approfondita dei problemi di ieri con analisi ragionata.

API_KEY="eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg"
BASE="http://localhost:8001/api"

Esegui in parallelo queste chiamate API (filtra al giorno precedente):
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

Produci:
1. METRICHE (trade chiusi/aperti, win rate, P&L netto, decisioni BUY/SELL/NO-ORDER)
2. ANOMALIE (ordinata per impatto, con causa e fix specifico)
3. STATO SISTEMA (Ollama up/down, fallback rate, worker restart)
4. TOP 3 FIX PRIORITARI per oggi

Scrivi l'analisi come testo nel terminale — conciso ma preciso.
PROMPT
)" 2>&1 | tee -a "$LOG_FILE"

echo "" | tee -a "$LOG_FILE"
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"
