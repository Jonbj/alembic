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
LOG_FILE="$LOG_DIR/alpha_miss_analysis_${DATE}.log"

# Persist the whole cron process, including failures before the human-readable
# header.  The host crontab does not provide a redirect of its own.
exec >>"$LOG_FILE" 2>&1

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
set +e
DATE_TARGET=$(uv run python3 - <<'PYEOF'
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
CALENDAR_STATUS=$?
set -e
if (( CALENDAR_STATUS != 0 )) || [[ -z "${DATE_TARGET:-}" ]]; then
    echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') Could not determine last trading day via Alpaca calendar (codice ${CALENDAR_STATUS}, market closed run window or API error) — skipping this run."
    exit 0
fi

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
    local parse_mode="${2-HTML}"
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[tg_send] Telegram credentials not set — skipping" >&2
        return
    fi
    local curl_args=(
        -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
        -d chat_id="${TELEGRAM_CHAT_ID}"
        -d text="$text"
    )
    if [[ -n "$parse_mode" ]]; then
        curl_args+=(-d parse_mode="$parse_mode")
    fi
    curl "${curl_args[@]}" > /dev/null
}

echo "=== Alembic Alpha-Miss Analysis ${DATE} (target: ${DATE_TARGET}) ==="
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Report: ${REPORT_FILE}"

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

FASE 0 — LEGGI IL DOSSIER E IL LEDGER PRIMA DI ANALIZZARE

Un dossier deterministico con i numeri della giornata e' gia' stato calcolato:
  __DOSSIER_FILE__
Se il percorso e' "(non disponibile)" la generazione e' fallita: calcola i numeri
tu come facevi prima e segnalalo nel report. Altrimenti LEGGILO e USALO.

Contiene: rendimenti di tutti i simboli, dispersione cross-sectional, conteggio
mover, copertura news, candidati miss con la loro evidenza, gli INGRESSI del
giorno con entry_percentile/mtm_eod/vs_apertura, le CHIUSURE con
drift_post_uscita, e tre aggregati (per ora d'ingresso, cause di miss cumulate,
mediane mobili a 20 giorni).

REGOLA: NON ricalcolare cio' che il dossier contiene gia'. Ogni numero che citi
deve venire dal dossier, e in caso di discrepanza fra il tuo calcolo e il suo
vince il dossier — e' deterministico, tu no. Il tuo compito e' interpretare:
classificare le cause dei miss leggendo il testo degli articoli (cosa che il
dossier non puo' fare), leggere il pattern della giornata, e scrivere le
segnalazioni.

FASE 0b — LEGGI IL LEDGER
Leggi docs/evidence/findings.json. Contiene le evidenze già note, ciascuna con un id stabile
(F-001, F-002, ...), un titolo e le occorrenze già registrate. Tienile presenti per tutta
l'analisi: alla fine ogni segnalazione che produrrai andrà agganciata a una di queste o
registrata come nuova.
Leggi anche docs/evidence/OBSERVATION_CHARTER.md: sei dentro un periodo di sola osservazione,
quindi NON proporre tarature né fix, solo evidenza.

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

FASE FINALE — AGGIORNA I DUE LEDGER

A) Appendi UNA riga a docs/evidence/market_daily.jsonl.

   FORMATO VINCOLANTE: JSON Lines. La riga deve stare su UNA SOLA RIGA FISICA, senza
   indentazione e senza a capo interni, terminata da newline. Il file NON e' un JSON: e' una
   sequenza di oggetti JSON uno per riga, e un oggetto spezzato su piu' righe lo rende
   illeggibile. Lo schema qui sotto e' scritto su una riga sola apposta: copiane la FORMA, non
   solo i campi.

   {"data":"__DATE_TARGET__","spy":0.0,"qqq":0.0,"dispersione_sigma":0.0,"mover_3pct":0,"up":0,"down":0,"watchlist_zero_news":0,"tema":"","miss":{"NO_NEWS":0,"THIN_NEUTRAL":0,"WRONG_SIGN":0,"FILTERED":0,"OUT_OF_STRATEGY_SCOPE":0},"catturati":0,"book":{"equity":0.0,"realizzato":0.0,"mtm":null,"s1_realizzato":0.0,"s4_realizzato":0.0}}

   Dopo aver scritto, VERIFICA che il file sia ancora JSON Lines valido:
     python3 -c "import json;[json.loads(l) for l in open('docs/evidence/market_daily.jsonl') if l.strip()];print('JSONL ok')"
   Se stampa un errore invece di "JSONL ok", hai spezzato la riga: correggila.

   Definizioni:
   - spy / qqq: rendimento giornaliero (close vs close precedente), come frazione non percentuale.
   - dispersione_sigma: deviazione standard cross-sectional dei rendimenti dei 96 simboli.
   - mover_3pct / up / down: quanti simboli con |return| >= 3%, e la ripartizione.
   - watchlist_zero_news: quanti dei 96 simboli hanno ZERO righe in news_log quel giorno.
   - tema: una riga di testo, la stessa lettura della tua sezione "Pattern osservato".
     Ammesso "non chiaro".
   - miss: i conteggi della tua tabella dei miss classificati.
   - catturati: quanti mover erano in portafoglio o sono stati tradati.
   - book: equity di fine giornata da Alpaca; realizzato = somma net_pnl dei trade chiusi quel
     giorno; s1_realizzato / s4_realizzato = stessa somma per strategia; mtm = variazione
     mark-to-market del book aperto se la calcoli, altrimenti null.
   Se un valore non lo puoi calcolare, scrivi null. NON inventarlo e NON omettere la chiave.
   Se esiste già una riga con la stessa "data", NON aggiungerne una seconda: significa che il
   report è stato rigenerato. In quel caso lascia il file com'è e segnalalo a stdout.

B) Aggiorna docs/evidence/findings.json per OGNI voce della tua sezione di segnalazioni.
   Per ciascuna, decidi se è già nel ledger:
   - SE corrisponde a un finding esistente: aggiungi UNA voce al suo array "occorrenze" e
     ricalcola "costo_cumulato_usd" come somma di occorrenze[].costo_usd.
   - SE è genuinamente nuova: crea un record con id "F-NNN" dove NNN è il valore corrente di
     "prossimo_id" formattato a 3 cifre, poi incrementa "prossimo_id" di 1.

   Schema di un record:
   {"id":"F-001","titolo":"","tipo":"difetto|alpha_miss|osservazione",
    "confidenza":"misurata|attribuita|congetturale","primo_avvistamento":"__DATE_TARGET__",
    "occorrenze":[{"data":"__DATE_TARGET__","costo_usd":0.0,"nota":"","fonte":""}],
    "costo_cumulato_usd":0.0,"occorrenze_non_stimate":0,"stato":"aperto","issue":null}

   Livelli di confidenza:
   - misurata: perdita reale tracciabile a righe di DB.
   - attribuita: il trade esiste, il controfattuale è corto.
   - congetturale: alpha mancato, nessun trade avvenuto. TUTTI i miss sono congetturali.

   IL COSTO VA STIMATO. E' obbligatorio provarci: le soglie che decideranno cosa
   merita lavoro sono espresse in dollari, quindi un'occorrenza senza costo non
   pesa nulla e l'evidenza raccolta diventa inutilizzabile.

   Come stimarlo, per livello:
   - misurata: il P&L reale attribuibile al difetto. Esempio: un trade chiuso in
     perdita per un exit sbagliato -> il suo net_pnl. Cita l'id del trade.
   - attribuita: la differenza fra quanto e' successo e quanto sarebbe successo
     senza il difetto, su un controfattuale CORTO. Esempio: uscita troppo presto
     -> (close del giorno - exit_price) * qty. Cita i numeri usati.
   - congetturale: il movimento non catturato per una size di posizione
     plausibile. Usa la size tipica di una posizione S4 (~2% del NAV, cioe'
     ~2.200 $ su un conto da ~110.000 $), NON il notional pieno del titolo.
     Esempio: mover a +6% mancato -> 2200 * 0.06 = 132 $.

   SE NON E' STIMABILE, scrivi "costo_usd": null — MAI 0.0. Zero significa "e'
   costato zero", che e' un'affermazione; null significa "non l'ho stimato", che
   e' un'altra cosa. Confonderle rende impossibile distinguere un difetto innocuo
   da uno mai quantificato.

   Un'osservazione strutturale (es. "la copertura news e' bassa") tipicamente NON
   ha un costo giornaliero stimabile: usa null, e conta sulla ricorrenza.

   "costo_cumulato_usd" e' la somma delle sole occorrenze con costo non-null.
   Aggiungi anche "occorrenze_non_stimate": <quante hanno costo_usd null>.
   Il campo "fonte" deve puntare al report e alla sezione che giustifica l'occorrenza, es.
   "ALPHA_MISS_REPORT___DATE_TARGET__.md §7".

   DUE REGOLE VINCOLANTI:
   1. SOLO APPEND. Non modificare né cancellare occorrenze già presenti, né cambiare il titolo o
      l'id di un finding esistente. Puoi solo aggiungere occorrenze, creare record nuovi, e
      ricalcolare costo_cumulato_usd.
   2. NEL DUBBIO, AGGANCIA. Creare un id nuovo va giustificato nella nota. Due record duplicati si
      fondono a fine periodo; un'evidenza spezzata in cinque id diversi ha ricorrenza 1 ciascuno e
      sparisce sotto tutte le soglie — errore silenzioso e non recuperabile.

   Le CAUSE di miss (NO_NEWS, THIN_NEUTRAL, ...) NON diventano findings: sono già contate in
   market_daily.jsonl. Diventa un finding solo un'affermazione strutturale, es. "39 simboli su 96
   non hanno copertura news in un giorno tipico".

C) Committa i ledger e il report SOLO SE il branch corrente e' main. Controlla PRIMA:

     git rev-parse --abbrev-ref HEAD

   - Se stampa "main": sincronizza origin/main PRIMA di committare. Report e ledger sono gia'
     modificati, quindi preservali durante il rebase con autostash:
       git pull --rebase --autostash origin main
     Se il pull fallisce, NON aggiungere o committare nulla e segnalalo a stdout. Se riesce:
       git add docs/evidence/findings.json docs/evidence/market_daily.jsonl "__REPORT_FILE__"
       git commit -m "evidence: ledger __DATE_TARGET__"
       git push origin main
     Se questo primo push fallisce perche' origin/main e' avanzato ancora, sincronizza il commit
     appena creato e ritenta il push UNA SOLA VOLTA:
       git pull --rebase origin main
       git push origin main
     Il PUSH e' obbligatorio quanto il commit: senza, il ledger vive solo su questa
     macchina e un cambio di sessione o un guasto lo perde. Se il rebase del retry va in conflitto,
     esegui `git rebase --abort` per tornare al commit locale valido. Se il retry fallisce (rete,
     divergenza o conflitto) NON forzarlo: lascia il commit locale e segnala chiaramente il
     fallimento a stdout.
   - Se stampa QUALSIASI ALTRA COSA: NON committare. I file restano scritti sul disco (non
     annullare le modifiche) e stampi su stdout, come ultima riga:
       ATTENZIONE: ledger scritto ma NON committato — branch corrente <nome>, atteso main.

   Motivo: questo cron gira nella directory principale del repo, che puo' trovarsi sul branch di
   lavoro di un altro agente. Un commit del ledger su un branch casuale lo disperderebbe e
   spezzerebbe la cronologia git, che e' l'audit del ledger stesso.

   Se non c'e' nulla da committare, non forzare il commit.

D) Nella sezione di segnalazioni del report, ogni voce deve riportare il suo id fra parentesi
   quadre a inizio riga, es. "[F-004] Sembra un difetto — ...".

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

# Dossier deterministico (#174): i numeri si calcolano UNA volta, qui, e la
# sessione li interpreta invece di ri-derivarli. Fallisce in modo morbido: se il
# dossier non si genera la sessione lavora come prima, calcolandosi i numeri da
# se'. Meglio un report senza dossier che nessun report.
DOSSIER_FILE="$PROJECT_DIR/docs/evidence/dossier/${DATE_TARGET}.json"
if uv run python "$PROJECT_DIR/scripts/alpha_miner_dossier.py" "$DATE_TARGET" >> "$LOG_FILE" 2>&1; then
    echo "Dossier generato: $DOSSIER_FILE"
else
    echo "ATTENZIONE: generazione dossier fallita — la sessione procede senza."
    DOSSIER_FILE="(non disponibile)"
fi

_CLAUDE_PROMPT="${_PROMPT_TEMPLATE//__DATE_TARGET__/$DATE_TARGET}"
_CLAUDE_PROMPT="${_CLAUDE_PROMPT//__DOSSIER_FILE__/$DOSSIER_FILE}"
_CLAUDE_PROMPT="${_CLAUDE_PROMPT//__REPORT_FILE__/$REPORT_FILE}"

set +e
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
ANALYSIS_STATUS=$?
set -e

printf '%s\n' "$ANALYSIS_OUTPUT"
if (( ANALYSIS_STATUS != 0 )); then
    echo "FAILED: sessione Claude terminata con codice $ANALYSIS_STATUS"
    FAILURE_TAIL=$(printf '%s\n' "$ANALYSIS_OUTPUT" | tail -c 3000)
    tg_send "🚨 Analisi alpha-miss ${DATE_TARGET} fallita con codice ${ANALYSIS_STATUS}.

Coda output:
${FAILURE_TAIL}" "" || true
    exit "$ANALYSIS_STATUS"
fi

# Scoreboard del P&L economico della carta (#278, M3): misura deterministica
# delle due domande di uscita pre-registrate. Fail-soft come il dossier: se non
# si genera, il cron non si rompe -- ma a differenza del dossier questo gira DOPO
# la sessione, cosi' il ledger di mercato (market_daily.jsonl) e' aggiornato al
# DATE_TARGET e la quota NO_NEWS-dominante e il benchmark SPY sono correnti.
set +e
ECON_OUTPUT=$(uv run python "$PROJECT_DIR/scripts/economic_pnl_scoreboard.py" --as-of "$DATE_TARGET" 2>&1)
ECON_STATUS=$?
set -e
if (( ECON_STATUS == 0 )); then
    echo "Scoreboard economico generato: docs/evidence/economic_pnl.json"
    printf '%s\n' "$ECON_OUTPUT"
else
    echo "ATTENZIONE: scoreboard economico fallito (codice ${ECON_STATUS}) — il cron prosegue."
    printf '%s\n' "$ECON_OUTPUT" | tail -c 1500
fi

echo ""
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

HEADER="🔎 <b>Alpha-miss Alembic — ${DATE_TARGET}</b>"
SUMMARY_TEXT="$(echo "$ANALYSIS_OUTPUT" | head -c 3800)"
tg_send "${HEADER}

<pre>${SUMMARY_TEXT}</pre>"

if [[ -f "$REPORT_FILE" ]]; then
    tg_send "📄 Report salvato: <code>${REPORT_FILE}</code>"
else
    tg_send "⚠️ Report file non trovato: <code>${REPORT_FILE}</code> — controlla il log."
fi
