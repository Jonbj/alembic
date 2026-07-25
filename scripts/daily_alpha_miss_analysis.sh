#!/usr/bin/env bash
# Daily Alembic alpha-miss analysis via Claude Code.
# Scheduled via system cron: 0 10 * * 1-5  (10:00 CEST, morning IT — the prior US
# trading day is long closed by then so the data is final).
# Session log : logs/alpha_miss_analysis_YYYY-MM-DD.log   (full tool output)
# Report file : docs/ALPHA_MISS_REPORT_YYYY-MM-DD.md       (clean Markdown report)
# Sends a Telegram summary after the analysis completes.
#
# Scope: ONLY the symbols in config/trading.yaml's watchlist (Alembic's own
# universe) — not a whole-market scan. The question is "did we miss something
# we could actually have traded", not "what did the market do".

set -euo pipefail

# cron runs with a minimal PATH that doesn't include ~/.local/bin, where the
# `claude` binary lives — without this the script aborts silently right after
# the header lines (set -e kills it at the `claude -p` call with "not found").
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)

# Target the most recent actual TRADING day per Alpaca's market calendar — not
# "yesterday" adjusted only for weekends (that still misfires on US market
# holidays, e.g. a Friday cron would target a Thursday July 4th with zero bars
# and no news, wasting a session on a day with nothing to analyze). Fails
# closed: if the calendar lookup itself fails (credentials/network), skip this
# run entirely rather than guess with calendar-unaware date arithmetic.
cd "$PROJECT_DIR"
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^ALPACA_(API_KEY|SECRET_KEY)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi
DATE_TARGET=$(uv run python3 - <<'PYEOF' 2>/dev/null
import os
from datetime import date, timedelta
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest

tc = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
today = date.today()
cal = tc.get_calendar(GetCalendarRequest(start=today - timedelta(days=14), end=today - timedelta(days=1)))
if cal:
    print(cal[-1].date.strftime("%Y-%m-%d"))
PYEOF
)
if [[ -z "${DATE_TARGET:-}" ]]; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') Could not determine last trading day via Alpaca calendar (market closed run window or API error) — skipping this run." | tee -a "$LOG_DIR/alpha_miss_analysis_${DATE}.log"
    exit 0
fi

LOG_FILE="$LOG_DIR/alpha_miss_analysis_${DATE}.log"
REPORT_FILE="$PROJECT_DIR/docs/ALPHA_MISS_REPORT_${DATE_TARGET}.md"

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

echo "=== Alembic Alpha-Miss Analysis ${DATE} (target: ${DATE_TARGET}) ===" | tee "$LOG_FILE"
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"
echo "Report: ${REPORT_FILE}" | tee -a "$LOG_FILE"

tg_send "⏳ <b>Analisi alpha-miss Alembic avviata</b>
Data analisi: ${DATE_TARGET}
Claude Code sta confrontando i migliori titoli della giornata con quanto intercettato da Alembic..."

# The heredoc uses single-quoted delimiter so no shell expansion occurs inside.
# The only placeholder substituted at runtime is __DATE_TARGET__ / __REPORT_FILE__ —
# no secret is ever injected into the prompt: the session reads .env itself via
# its own Bash calls (ALPACA_API_KEY/ALPACA_SECRET_KEY, Postgres via docker exec).
_PROMPT_TEMPLATE=$(cat <<'PROMPT'
Sei in una sessione autonoma di analisi giornaliera del trading system Alembic.
Modalità: non-interattiva automatizzata — esegui tutti i comandi read-only direttamente senza chiedere conferma preventiva.

Lavora come Quant Research Analyst: il tuo compito NON è un audit forense end-to-end
(quello lo fa già lo script gemello daily_analysis.sh / FORENSIC_DAILY_REPORT).
Il tuo compito è UNA domanda sola, precisa: tra i titoli del NOSTRO universo, quali sono
saliti di più il __DATE_TARGET__, quali di questi Alembic ha intercettato e quali no, e perché.

SCOPE — IMPORTANTE
Limita l'analisi ESCLUSIVAMENTE ai simboli in config/trading.yaml -> symbols.watchlist
(circa 96 simboli). Non è uno scan whole-market: la domanda è "abbiamo perso qualcosa che
potevamo effettivamente tradare", non "cosa ha fatto il mercato in generale".

FASE 1 — RENDIMENTI DEL __DATE_TARGET__
Scarica le barre giornaliere Alpaca per l'intera watchlist e calcola il rendimento
percentuale (close vs close precedente). Credenziali in .env (ALPACA_API_KEY,
ALPACA_SECRET_KEY) — leggile tu stesso, non sono nel prompt. Esempio di approccio:

  set -a; source .env; set +a
  uv run python3 << 'EOF'
  import os
  from datetime import datetime, timezone
  from alpaca.data.historical import StockHistoricalDataClient
  from alpaca.data.requests import StockBarsRequest
  from alpaca.data.timeframe import TimeFrame
  import yaml
  with open("config/trading.yaml") as f:
      watchlist = yaml.safe_load(f)["symbols"]["watchlist"]
  client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])
  # richiedi 2 giorni di barre giornaliere che includano __DATE_TARGET__ e il giorno precedente,
  # calcola return % per simbolo, ordina.
  EOF

Produci una classifica completa (top e bottom mover), non solo i primi 5.

FASE 2 — COSA HA FATTO ALEMBIC IL __DATE_TARGET__
Via `docker exec alembic-postgres-1 psql -U trading -d trading -c "<SELECT>"`:
* trades con entry_time o exit_time nel __DATE_TARGET__ (symbol, strategy, entry/exit price, net_pnl)
* portfolio_cycles del giorno (conteggio, eventuali gap > 16 min sulla cadenza attesa di 15 min)
* sentiment_signals del giorno per OGNI simbolo del top/bottom mover (score, fallback_used, model_id, orario)
* news_log del giorno per OGNI simbolo del top/bottom mover (conteggio articoli, extraction_method)

FASE 3 — CLASSIFICAZIONE DEI MISS
Per ogni titolo tra i migliori mover (definisci tu una soglia ragionevole, es. |return| >= 3%,
motiva la scelta) che Alembic NON ha tradato quel giorno, classifica la causa in una di queste
categorie, con evidenza a supporto:

(a) NO_NEWS — zero righe in news_log per quel ticker quel giorno (data coverage gap puro)
(b) THIN_NEUTRAL — news presente ma segnale vicino a zero / coverage troppo bassa per un segnale forte
(c) WRONG_SIGN — segnale generato con segno opposto al movimento di prezzo
(d) FILTERED — segnale valido, sopra soglia, ma scartato da ranking/breadth (min_stocks)/hysteresis/
    altro meccanismo della strategia (verifica se possibile nei log worker, se disponibili)
(e) OUT_OF_STRATEGY_SCOPE — riguarda un simbolo che S1/S4 non tradano per costruzione (es. ETF
    settoriali usati solo come benchmark, se presenti nella watchlist)
(f) CAUGHT — Alembic lo ha effettivamente tradato: nota comunque se con timing/size subottimale

Per i titoli CATTURATI, riporta comunque brevemente l'esito (net P&L, exit_reason).

FASE 4 — PATTERN
Osserva se i mover del giorno si raggruppano per settore/tema (es. rotazione da un gruppo verso
un altro — confronta i migliori vs i peggiori). Non inventare un settore per ogni titolo se non
è ovvio: dichiara "pattern non chiaro" se è così.

OUTPUT FINALE
Salva un report Markdown in __REPORT_FILE__ usando il Write tool, con queste sezioni:

1. Executive summary (max 10 righe): quanti mover rilevanti, quanti catturati, quanti mancati,
   causa prevalente dei miss.
2. Tabella completa rendimenti (simbolo, return%, catturato sì/no).
3. Tabella dei miss classificati (simbolo, return%, categoria, evidenza breve).
4. Titoli catturati: esito.
5. Pattern osservato (o "non chiaro").
6. Se emergono pattern ricorrenti rispetto a giorni precedenti (puoi guardare eventuali
   docs/ALPHA_MISS_REPORT_*.md già esistenti per confronto, se presenti), segnalali — altrimenti
   non speculare oltre il singolo giorno.
7. Non proporre fix di codice: se una causa (es. FILTERED) sembra un bug piuttosto che un limite
   noto, dillo esplicitamente e basta — la decisione se aprire un'issue è dell'operatore.

REGOLE IMPORTANTI
* Modalità read-only: nessuna modifica a codice, nessun commit, nessun ordine, nessun worker
  avviato. L'unico file che scrivi è __REPORT_FILE__.
* Non inventare dati mancanti — se un simbolo non ha barre disponibili, dillo.
* Non uscire dallo scope della watchlist.
* Al termine: salva il report e fermati.
* Dopo aver salvato il file, stampa su stdout SOLO l'executive summary, preceduto da una riga
  con il percorso del file salvato.
PROMPT
)

_CLAUDE_PROMPT="${_PROMPT_TEMPLATE//__DATE_TARGET__/$DATE_TARGET}"
_CLAUDE_PROMPT="${_CLAUDE_PROMPT//__REPORT_FILE__/$REPORT_FILE}"

ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)

echo "$ANALYSIS_OUTPUT" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"

HEADER="🔎 <b>Alpha-miss Alembic — ${DATE_TARGET}</b>"
SUMMARY_TEXT="$(echo "$ANALYSIS_OUTPUT" | head -c 3800)"
tg_send "${HEADER}

<pre>${SUMMARY_TEXT}</pre>"

if [[ -f "$REPORT_FILE" ]]; then
    tg_send "📄 Report salvato: <code>${REPORT_FILE}</code>"
else
    tg_send "⚠️ Report file non trovato: <code>${REPORT_FILE}</code> — controlla il log."
fi
