#!/usr/bin/env bash
# Daily Alembic trading forensic analysis via Claude Code.
# Scheduled via system cron: 30 14 * * 1-5  (14:30 CEST = 1h before NYSE open at 15:30)
# Session log : logs/daily_analysis_YYYY-MM-DD.log   (full tool output)
# Report file : docs/FORENSIC_DAILY_REPORT_YYYY-MM-DD.md  (clean Markdown report)
# Sends a Telegram summary after the analysis completes.

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
# Target the last TRADING day, not the calendar yesterday: with the Mon-Fri
# 14:30 cron, "yesterday" made Monday analyze Sunday (empty) and Friday was
# never analyzed at all (#74). Monday now targets Friday.
DATE_TARGET=$(date -d "yesterday" +%Y-%m-%d)
if [[ $(date -d "yesterday" +%u) -ge 6 ]]; then
    DATE_TARGET=$(date -d "last friday" +%Y-%m-%d)
fi
LOG_FILE="$LOG_DIR/daily_analysis_${DATE}.log"
REPORT_FILE="$PROJECT_DIR/docs/FORENSIC_DAILY_REPORT_${DATE_TARGET}.md"

# Load Telegram credentials from .env
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

# Load admin API key — ALEMBIC_API_KEY env var takes precedence, then ADMIN_API_KEY from .env.
# The key is injected into the Claude prompt at runtime; never hardcode it here.
if [[ -z "${ALEMBIC_API_KEY:-}" ]] && [[ -f "$PROJECT_DIR/.env" ]]; then
    ALEMBIC_API_KEY=$(grep -E '^ADMIN_API_KEY=' "$PROJECT_DIR/.env" | head -1 | cut -d= -f2- | tr -d '"'"'"' ')
fi
if [[ -z "${ALEMBIC_API_KEY:-}" ]]; then
    echo "ERROR: ALEMBIC_API_KEY env var or ADMIN_API_KEY in .env is required" >&2
    exit 1
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

echo "=== Alembic Daily Analysis ${DATE} (target: ${DATE_TARGET}) ===" | tee "$LOG_FILE"
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"
echo "Report: ${REPORT_FILE}" | tee -a "$LOG_FILE"

tg_send "⏳ <b>Analisi giornaliera Alembic avviata</b>
Data analisi: ${DATE_TARGET}
Claude Code sta eseguendo l'analisi forense..."

cd "$PROJECT_DIR"

# The heredoc uses single-quoted delimiter so no shell expansion occurs inside.
# Placeholders __ALEMBIC_API_KEY__, __DATE_TARGET__, __REPORT_FILE__ are replaced
# at runtime via bash parameter expansion below — never stored in source.
_PROMPT_TEMPLATE=$(cat <<'PROMPT'
Sei in una sessione autonoma di analisi giornaliera del trading system Alembic.
Modalità: non-interattiva automatizzata — esegui tutti i comandi read-only direttamente senza chiedere conferma preventiva.

Lavora come Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer.

OBIETTIVO
Analizza la giornata operativa di __DATE_TARGET__ per capire se il processo Alembic ha funzionato correttamente end-to-end:

news ingest → dedup/sanitizzazione → valutazione LLM → aggregazione segnali → decisioni → generazione ordini → esecuzione/fill → posizioni → rendimento/PnL → anomalie operative.

Il focus NON è scrivere codice.
Il focus è ricostruire cosa è successo, verificare se il comportamento è funzionalmente corretto e trovare anomalie.

DATA DA ANALIZZARE

* Data target: __DATE_TARGET__
* Timezone operativo: UTC (come definito in src/workers/celery_app.py).
* Se il timezone non è chiaro da codice o config, evidenzialo come ambiguità critica.
* Distingui pre-market, market hours (13:30–20:00 UTC), post-market e batch giornalieri.

MODALITÀ OPERATIVA

* Lavora in modalità read-only.
* Non modificare file (eccetto il report finale indicato sotto).
* Non creare commit.
* Non applicare patch.
* Non inviare ordini.
* Non chiamare broker in modalità trading.
* Non avviare worker che possano produrre nuovi segnali o ordini.
* Non rieseguire pipeline live.
* Puoi leggere codice, configurazioni, log, report, database, CSV, parquet, JSON.
* Esegui direttamente i comandi read-only standard: ls, find, grep, cat, docker compose logs, query SELECT.

RISORSE DISPONIBILI

API REST locale (Authorization: Bearer __ALEMBIC_API_KEY__):
  BASE="http://localhost:8001/api"
  Chiama queste API con curl filtrando al giorno __DATE_TARGET__:
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/decisions?limit=200"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/trades?limit=200"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/signals?limit=100"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/positions"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/orders?limit=100"

Log container Docker (solo lettura):
  docker compose logs worker --since 48h 2>&1 | grep -E "ERROR|WARNING|semaphore|fallback|FinBERT|Ollama" | tail -50
  docker compose logs worker-inference --since 48h 2>&1 | grep -E "ERROR|WARNING|quantiz|FinBERT" | tail -30

Database PostgreSQL (solo SELECT):
  docker exec alembic-postgres-1 psql -U trading -d trading -c "<query SELECT>"

PRIMA FASE — DISCOVERY
Ricostruisci dove il progetto salva:
1. news raw;
2. news deduplicate;
3. news sanitizzate;
4. output dei singoli modelli LLM;
5. score aggregati;
6. segnali per ticker;
7. decisioni strategia;
8. ordini generati;
9. ordini inviati al broker;
10. fill;
11. posizioni;
12. PnL/rendimenti;
13. alert;
14. errori;
15. log Celery/worker;
16. log backend;
17. log frontend, se rilevante.

Usa comandi read-only: ls, find, tree, rg, grep, sed, cat, git status, git diff --stat, SELECT SQL.
Cerca parole chiave:
news, ingest, gdelt, marketaux, benzinga, sentiment, llm, ensemble, score, signal,
aggregation, decision, order, fill, broker, alpaca, ibkr, position, pnl, performance,
alert, celery, worker, redis, postgres, strategy, s4, tactical, execution.

SECONDA FASE — TIMELINE DEL __DATE_TARGET__
Costruisci una timeline cronologica della giornata.
Per ogni evento rilevante indica: timestamp, timezone, componente, input, output, stato, eventuale errore/warning, file/log/tabella da cui deriva.
La timeline deve includere, se disponibili:
* avvio ingest news;
* numero news raccolte per fonte;
* numero news scartate;
* duplicati rimossi;
* errori fonte dati;
* chiamate LLM per modello;
* timeout/refusal/errori LLM;
* score per ticker;
* aggregazione ensemble;
* segnali finali;
* decisioni strategia;
* ordini generati;
* ordini inviati;
* fill o reject;
* aggiornamento posizioni;
* calcolo rendimento;
* alert o anomalie.

TERZA FASE — NEWS INGEST REVIEW
Analizza l'ingest delle news del __DATE_TARGET__.
Verifica:
* quante news sono state raccolte;
* da quali fonti;
* copertura temporale;
* tickers/entity estratti;
* duplicati;
* news stale;
* news con timestamp futuri;
* news fuori mercato;
* news duplicate tra provider;
* eventuali problemi di ticker ambiguity;
* eventuale assenza di sanitizzazione;
* eventuali campi mancanti;
* eventuali failure silenziosi;
* eventuali retry;
* eventuali buchi temporali.

Output richiesto: tabella per fonte, tabella per ticker, top news per impatto sul segnale, problemi trovati, confidenza dell'analisi.

QUARTA FASE — REVIEW VALUTAZIONE LLM
Per ogni modello LLM calcola o ricostruisci:
* numero richieste, successi, errori, timeout, refusal/invalid output;
* latenza media;
* distribuzione polarity, confidence, score (polarity × confidence);
* ticker con score estremi;
* casi di forte disaccordo tra modelli;
* casi in cui un singolo modello ha dominato l'ensemble;
* casi in cui fallback deterministico (FinBERT) è stato usato.

Verifica funzionale:
* l'output LLM è validato prima di entrare nel signal store?
* l'ensemble gestisce varianza alta?
* le news duplicate pesano più volte?
* la stessa news può generare segnali multipli?
* confidence bassa riduce davvero il peso?
* i modelli sono chiamati offline/background e non nel trading loop?
* esiste rischio che hallucination LLM entri direttamente in decisione trading?

QUINTA FASE — SEGNALE, DECISIONE E ORDINI
Ricostruisci il passaggio da segnali a ordini.
Per il __DATE_TARGET__ verifica:
* quali ticker hanno ricevuto segnali;
* quali segnali hanno superato soglia;
* quale strategia li ha usati (S4/news tactical è paper?);
* quali decisioni sono state create;
* quali target weights sono stati prodotti;
* se è stato applicato il portfolio combiner;
* se sono stati applicati cap, risk limits, exposure limits;
* se è stato applicato circuit breaker;
* se esiste distinzione chiara paper/live;
* se ordini buy/sell sono coerenti con signal, holding period, stop-loss, signal flip e rebalance logic.

Per ogni ordine indica: timestamp decisione, strategia, ticker, azione (buy/sell/close/rebalance),
quantità, prezzo atteso, prezzo fill, stato (generated/submitted/filled/rejected/cancelled),
broker o paper engine, rationale, segnale causante, risk check applicato, eventuali anomalie.

SESTA FASE — RENDIMENTO E PNL DEL __DATE_TARGET__
Calcola o ricostruisci il rendimento degli ordini e delle posizioni.
Distingui:
* PnL realizzato e non realizzato;
* PnL per ticker;
* PnL per strategia;
* PnL da posizioni aperte prima del __DATE_TARGET__;
* PnL da posizioni aperte il __DATE_TARGET__;
* slippage stimato;
* commissioni/costi.

Se i dati di prezzo non sono disponibili, non inventare performance.
Indica chiaramente cosa manca e quale query servirebbe.

SETTIMA FASE — CORRETTEZZA FUNZIONALE BUY/SELL
Controlla:
* buy generati solo quando consentito;
* sell/exit generati correttamente;
* stop-loss rispettati;
* signal flip rispettato;
* max holding days rispettato;
* rebalance band rispettata;
* niente ordini duplicati;
* niente ordini contrari nello stesso intervallo senza rationale;
* niente ordini su ticker non consentiti;
* niente ordini fuori orario non previsti;
* niente trade se dati stale;
* niente trade se LLM output non valido;
* niente trade se circuit breaker attivo;
* niente trade se strategia è disabilitata;
* paper/live mode coerente;
* idempotenza in caso di retry Celery;
* reconciliation tra ordini, fill e posizioni.

OTTAVA FASE — ANOMALIE DEL __DATE_TARGET__
Categorie obbligatorie:
* ingest anomalo o volume news anomalo;
* provider down o parziale;
* troppi duplicati;
* ticker extraction sospetta;
* LLM disagreement elevato;
* confidence troppo alta/bassa rispetto al contenuto;
* score estremi o outlier;
* segnali non coerenti con news;
* ordini generati senza segnale;
* segnali generati senza news;
* ordini duplicati;
* buy e sell ravvicinati sullo stesso ticker;
* ordini fuori orario;
* ordini senza risk check;
* posizioni non riconciliate;
* PnL incoerente;
* log errori non propagati ad alert;
* eccezioni silenziose;
* dati con timestamp futuri;
* timezone/DST issue.

Controlla anche questi pattern operativi specifici:
* Roundtrip < 30 min: buy+sell stesso simbolo nello stesso ciclo.
* BUY ripetuto > 3 volte in sequenza senza SELL intermedio (pyramiding).
* SELL con sentiment positivo (bug A5).
* fallback_used=True su tutti i simboli in un periodo (Ollama giù).
* NO-ORDER: decisione creata ma ordine non generato.
* Score < 0.05 che hanno generato ordini.
* Ordini identici nello stesso minuto (race condition scheduler).

NONA FASE — OUTPUT FINALE
Salva il report Markdown completo nel file __REPORT_FILE__ usando il Write tool.

Il report deve contenere le seguenti sezioni:

1. Executive summary (max 15 righe).
2. Verdict finale: OK / OK con warning / anomalie significative / processo non affidabile / non verificabile.
3. Timeline del __DATE_TARGET__.
4. Tabella news ingest.
5. Tabella performance modelli LLM.
6. Tabella segnali finali per ticker.
7. Tabella ordini generati/eseguiti.
8. Tabella PnL/rendimento.
9. Analisi correttezza buy/sell.
10. Anomalie trovate (formato [DAY-XXX] per ognuna — vedi FORMATO FINDING).
11. False positive o aree risultate corrette.
12. Dati mancanti o non accessibili.
13. Raccomandazioni immediate.
14. Test o monitor da aggiungere.
15. Ticket tecnici suggeriti.
16. Stato sistema: Ollama up/down e ore di downtime, FinBERT fallback rate (% decisioni), worker restart events.

Dopo aver salvato il file, stampa su stdout SOLO l'executive summary e il verdict, preceduti da una riga con il percorso del file salvato.

FORMATO FINDING obbligatorio per ogni anomalia trovata:

### [DAY-XXX] Titolo

* Tipo: Anomalia / Bug / Rischio / Ambiguità / Corretto / Non verificabile
* Area: News / LLM / Signal / Orders / Broker / PnL / Risk / Frontend / Data / Ops
* Evidenza:
  * file/log/tabella:
  * timestamp:
  * snippet/query:
* Descrizione:
* Impatto:
* Severità: Critical / High / Medium / Low
* Confidenza: High / Medium / Low
* Azione consigliata:
* Test/monitor consigliato:

REGOLE IMPORTANTI

* Non inventare dati mancanti.
* Non assumere che un ordine sia live o paper: verificalo.
* Non assumere timezone: trovalo nel codice o segnala ambiguità.
* Non confondere signal generato con ordine eseguito.
* Non confondere ordine generato con fill.
* Non confondere PnL intraday con rendimento della strategia.
* Un trade può perdere denaro ma essere funzionalmente corretto.
* Un trade può guadagnare denaro ma essere funzionalmente sbagliato.
* Dai priorità a auditabilità, riproducibilità, idempotenza e safety.
* Se trovi anomalie gravi: proponi remediation ticket, NON patch di codice.
* Al termine: salva il report nel file indicato e fermati. Non applicare fix, non creare commit.
PROMPT
)

# Replace all placeholders at runtime — nothing sensitive is ever stored in source.
_CLAUDE_PROMPT="${_PROMPT_TEMPLATE//__ALEMBIC_API_KEY__/$ALEMBIC_API_KEY}"
_CLAUDE_PROMPT="${_CLAUDE_PROMPT//__DATE_TARGET__/$DATE_TARGET}"
_CLAUDE_PROMPT="${_CLAUDE_PROMPT//__REPORT_FILE__/$REPORT_FILE}"

ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)

echo "$ANALYSIS_OUTPUT" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')" | tee -a "$LOG_FILE"

# Telegram message 1: executive summary (first output lines, max 3800 chars)
HEADER="📊 <b>Analisi Trading Alembic — ${DATE_TARGET}</b>"
SUMMARY_TEXT="$(echo "$ANALYSIS_OUTPUT" | head -c 3800)"
tg_send "${HEADER}

<pre>${SUMMARY_TEXT}</pre>"

# Telegram message 2: recommendations and tickets (separate message for visibility)
FIXES=$(echo "$ANALYSIS_OUTPUT" | grep -A 25 -E "Raccomandazioni immediate|Ticket tecnici|TOP 3 FIX" | head -30)
if [[ -n "$FIXES" ]]; then
    tg_send "🔧 <b>Fix prioritari — ${DATE_TARGET}</b>

<pre>${FIXES}</pre>"
fi

# Telegram message 3: report file path confirmation
if [[ -f "$REPORT_FILE" ]]; then
    tg_send "📄 Report salvato: <code>${REPORT_FILE}</code>"
else
    tg_send "⚠️ Report file non trovato: <code>${REPORT_FILE}</code> — controlla il log."
fi
