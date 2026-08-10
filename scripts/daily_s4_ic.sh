#!/usr/bin/env bash
# Wrapper giornaliero per scripts/compute_s4_ic.py (#180).
#
# Idempotente: lo script Python riscrive l'intera serie ad ogni run e scrive
# l'esito contro il kill criterion in docs/evidence/s4_ic.json. Se l'esito
# raggiunge PASS/FAIL, parte una notifica Telegram una tantum (soppressa se
# l'ultimo stato era lo stesso). Questo wrapper si limita a schedulare il
# run, loggare l'esito e non fare nulla se non c'e' un giorno di borsa nuovo.
#
# NON tocca il cron del report alpha-miss: quel cron e' congelato fino alla
# verifica del primo commit automatico del ledger (#171, #174). Questo script
# e' un'unita' separata, da schedulare ACCANTO (proposta: stesso orario del
# dossier deterministico, 10:00 CEST feriale, dopo la chiusura del mercato USA).
#
# Session log : logs/s4_ic_YYYY-MM-DD.log
# Artefatto   : docs/evidence/s4_ic.json (riscritto integralmente)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/s4_ic_${DATE}.log"

# Persistenza: il redirect cattura anche i fallimenti prima dell'header umano,
# come in daily_analysis.sh.
exec >>"$LOG_FILE" 2>&1

echo "=== Alembic S4 IC daily ${DATE} ==="
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

cd "$PROJECT_DIR"
if uv run python "$PROJECT_DIR/scripts/compute_s4_ic.py"; then
    echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    exit 0
else
    STATUS=$?
    echo "FAILED: compute_s4_ic.py exited with code ${STATUS}"
    exit "${STATUS}"
fi
