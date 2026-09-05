#!/usr/bin/env bash
# Daily Alembic trading forensic analysis via Claude Code.
# Scheduled via system cron: 30 14 * * 1-5  (14:30 CEST = 1h before NYSE open at 15:30)
# Session log : logs/daily_analysis_YYYY-MM-DD.log   (full tool output)
# Report file : docs/FORENSIC_DAILY_REPORT_YYYY-MM-DD.md  (clean Markdown report)
# Sends a Telegram summary after the analysis completes.
# Il commit di report e ledger su main avviene DOPO la sessione, deterministicamente,
# con scripts/commit_evidence_ledger.sh (#411): la sessione scrive solo i file.

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
LOG_FILE="$LOG_DIR/daily_analysis_${DATE}.log"

# Persist the whole cron process, including failures before the human-readable
# header.  The host crontab does not provide a redirect of its own.
exec >>"$LOG_FILE" 2>&1

# Target the last TRADING day, not the calendar yesterday: with the Mon-Fri
# 14:30 cron, "yesterday" made Monday analyze Sunday (empty) and Friday was
# never analyzed at all (#74). Monday now targets Friday.
DATE_TARGET=$(date -d "yesterday" +%Y-%m-%d)
if [[ $(date -d "yesterday" +%u) -ge 6 ]]; then
    DATE_TARGET=$(date -d "last friday" +%Y-%m-%d)
fi
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

echo "=== Alembic Daily Analysis ${DATE} (target: ${DATE_TARGET}) ==="
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Report: ${REPORT_FILE}"

tg_send "⏳ <b>Analisi giornaliera Alembic avviata</b>
Data analisi: ${DATE_TARGET}
Claude Code sta eseguendo l'analisi forense..."

cd "$PROJECT_DIR"

# Prima che la sessione legga findings.json, riallinealo a origin/main (#411): questa
# working tree e' condivisa e un `git checkout` altrui riporta il ledger alla versione
# del branch di turno. Il forense lo AGGIORNA, quindi partire da una copia riportata
# indietro significa ripartire da un prossimo_id gia' consumato su main. E' un'unione,
# non una sostituzione, ed e' fail-open: al massimo si lavora sulla copia vecchia.
"$PROJECT_DIR/scripts/refresh_evidence_ledger.sh" docs/evidence/findings.json || true

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
* Esegui direttamente i comandi read-only standard: ls, find, grep, cat, query SELECT.

RISORSE DISPONIBILI

API REST locale (Authorization: Bearer __ALEMBIC_API_KEY__):
  BASE="http://localhost:8001/api"
  Chiama queste API con curl filtrando al giorno __DATE_TARGET__:
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/decisions?limit=200"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/trades?limit=200"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/signals?limit=100"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/positions"
    curl -s -H "Authorization: Bearer __ALEMBIC_API_KEY__" "$BASE/orders?limit=100"

Log applicativi persistenti sull'host (sopravvivono ai redeploy):
  logs/containers/worker-__DATE_TARGET__.log
  logs/containers/worker-inference-__DATE_TARGET__.log
  logs/containers/api-__DATE_TARGET__.log
  logs/containers/beat-__DATE_TARGET__.log
Usa questi file, non `docker compose logs`: i log Docker appartengono alla sola
istanza corrente del container e dopo una ricreazione non coprono la data target.

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

Avvertenza obbligatoria su exit_mechanism (#184): fino alla correzione di #184 l'etichetta
non era osservata ma dedotta dall'età dell'ultimo segnale in DB, quindi posizioni chiuse
per altri motivi risultano `expired` o `whipsaw` a seconda dell'orologio. Le righe pre-fix
si riconoscono dal testo del motivo (vedi docs/exit_mechanism_labels.md). Se il report
conta o interpreta `exit_mechanism` su righe pre-fix, dillo esplicitamente nel report:
è una stima per età, non una misura del meccanismo.

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

LEDGER DELLE EVIDENZE

Prima di iniziare l'analisi leggi docs/evidence/findings.json e
docs/evidence/OBSERVATION_CHARTER.md. Sei dentro un periodo di sola osservazione: NON proporre
tarature. I remediation ticket che la sezione precedente ti chiede restano ammessi solo per
difetti di CORRETTEZZA, cioè quelli che, se non corretti, rendono sbagliata l'evidenza raccolta
nelle settimane successive.

Al termine, per OGNI anomalia che hai riportato, aggiorna docs/evidence/findings.json:
- SE corrisponde a un finding già presente: aggiungi UNA voce al suo array "occorrenze" e
  ricalcola "costo_cumulato_usd" come somma di occorrenze[].costo_usd.
- SE è genuinamente nuova: crea un record con id "F-NNN" dove NNN è il valore corrente di
  "prossimo_id" formattato a 3 cifre, poi incrementa "prossimo_id" di 1.

Schema di un record:
{"id":"F-001","titolo":"","tipo":"difetto|alpha_miss|osservazione",
 "confidenza":"misurata|attribuita|congetturale","primo_avvistamento":"__DATE_TARGET__",
 "occorrenze":[{"data":"__DATE_TARGET__","costo_usd":0.0,"nota":"","fonte":""}],
 "costo_cumulato_usd":0.0,"occorrenze_non_stimate":0,"stato":"aperto","issue":null}

Livelli di confidenza: misurata = perdita reale tracciabile a righe di DB; attribuita = il trade
esiste e il controfattuale è corto; congetturale = nessun trade avvenuto.

IL COSTO VA STIMATO. E' obbligatorio provarci: le soglie che decideranno cosa merita lavoro sono
espresse in dollari, quindi un'occorrenza senza costo non pesa nulla e l'evidenza raccolta diventa
inutilizzabile.

Come stimarlo, per livello:
- misurata: il P&L reale attribuibile al difetto (es. il net_pnl di un trade chiuso male). Cita
  l'id del trade.
- attribuita: la differenza fra quanto e' successo e quanto sarebbe successo senza il difetto, su
  un controfattuale CORTO. Cita i numeri usati.
- congetturale: il movimento non catturato per una size di posizione plausibile — usa la size
  tipica S4 (~2% del NAV, ~2.200 $ su ~110.000 $), NON il notional pieno del titolo.

SE NON E' STIMABILE, scrivi "costo_usd": null — MAI 0.0. Zero significa "e' costato zero", che e'
un'affermazione; null significa "non l'ho stimato", che e' un'altra cosa. Un'anomalia strutturale
o di sola osservabilita' tipicamente non ha costo stimabile: usa null e conta sulla ricorrenza.

"costo_cumulato_usd" e' la somma delle sole occorrenze con costo non-null. Aggiungi anche
"occorrenze_non_stimate": <quante hanno costo_usd null>.
Il campo "fonte" punta al report e alla sezione, es. "FORENSIC_DAILY_REPORT___DATE_TARGET__.md".

DUE REGOLE VINCOLANTI:
1. SOLO APPEND. Non modificare né cancellare occorrenze già presenti, né cambiare titolo o id di
   un finding esistente.
2. NEL DUBBIO, AGGANCIA. Creare un id nuovo va giustificato nella nota. Un'evidenza spezzata in
   più id ha ricorrenza 1 ciascuno e sparisce sotto tutte le soglie.

Poi NON committare e NON pushare nulla: limitati a scrivere i file su disco (il report e
docs/evidence/findings.json). Al commit ci pensa lo script chiamante, dopo la sessione,
con scripts/commit_evidence_ledger.sh: committa il ledger e il report insieme su main
da una worktree dedicata, quindi non importa su quale branch si trovi questa directory
di lavoro (di solito e' quella di un altro agente). Un tuo commit qui finirebbe sul
branch sbagliato e disperderebbe il ledger, che e' la cronologia dell'audit stesso.

Nel report, ogni anomalia riportata deve avere il suo id fra parentesi quadre a inizio riga.

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

set +e
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
ANALYSIS_STATUS=$?
set -e

printf '%s\n' "$ANALYSIS_OUTPUT"
if (( ANALYSIS_STATUS != 0 )); then
    echo "FAILED: sessione Claude terminata con codice $ANALYSIS_STATUS"
    FAILURE_TAIL=$(printf '%s\n' "$ANALYSIS_OUTPUT" | tail -c 3000)
    tg_send "🚨 Analisi forense ${DATE_TARGET} fallita con codice ${ANALYSIS_STATUS}.

Coda output:
${FAILURE_TAIL}" "" || true
    exit "$ANALYSIS_STATUS"
fi

# Il report e' l'uscita primaria del cron: una sessione che termina bene senza averlo
# scritto non e' un giro sano. Fino al 2026-08-24 questo caso mandava solo l'avviso
# Telegram e usciva comunque 0, nascondendo il buco a chi sorveglia l'exit code (#411).
if [[ ! -f "$REPORT_FILE" ]]; then
    echo "FAILED: report ${REPORT_FILE} non prodotto dalla sessione"
    tg_send "🚨 Analisi forense ${DATE_TARGET}: la sessione è terminata senza scrivere il report (${REPORT_FILE}) — vedi <code>${LOG_FILE}</code>." "" || true
    exit 1
fi

# Telegram message 1: executive summary (first output lines, max 3800 chars)
HEADER="📊 <b>Analisi Trading Alembic — ${DATE_TARGET}</b>"
SUMMARY_TEXT="$(echo "$ANALYSIS_OUTPUT" | head -c 3800)"
tg_send "${HEADER}

<pre>${SUMMARY_TEXT}</pre>"

# Telegram message 2: recommendations and tickets (separate message for visibility).
# La sezione e' facoltativa: un summary senza quelle parole non deve ammazzare il cron
# (grep senza match vale 1 e set -e uscirebbe qui).
FIXES=$(echo "$ANALYSIS_OUTPUT" | grep -A 25 -E "Raccomandazioni immediate|Ticket tecnici|TOP 3 FIX" | head -30 || true)
if [[ -n "${FIXES:-}" ]]; then
    tg_send "🔧 <b>Fix prioritari — ${DATE_TARGET}</b>

<pre>${FIXES}</pre>"
fi

# Telegram message 3: report file path confirmation
tg_send "📄 Report salvato: <code>${REPORT_FILE}</code>"

# Commit deterministico del ledger (#411), come gia' fa l'alpha-miss (#336). La
# sessione scrive soltanto i file: il commit lo fa qui una worktree dedicata
# appuntata su main, cosi' il branch su cui e' parcheggiata questa directory di
# lavoro non conta piu' nulla. L'esito e' esplicito su Telegram e nell'ultima
# riga del log, perche' finora un mancato commit era visibile solo rileggendo il
# log a mano.
COMMIT_PATHS=(docs/evidence/findings.json "$REPORT_FILE")
set +e
GIT_OUTPUT=$("$PROJECT_DIR/scripts/commit_evidence_ledger.sh" \
    --message "evidence: forensic ${DATE_TARGET}" "${COMMIT_PATHS[@]}" 2>&1)
set -e
printf '%s\n' "$GIT_OUTPUT"
GIT_STATUS=$(printf '%s\n' "$GIT_OUTPUT" | sed -n 's/^GIT_STATUS=//p' | tail -1)
GIT_STATUS="${GIT_STATUS:-not_committed}"

case "$GIT_STATUS" in
    pushed)
        tg_send "✅ Report e ledger su <code>main</code> (GIT_STATUS=pushed)."
        ;;
    nothing_to_commit)
        tg_send "ℹ️ Nessuna modifica al ledger da committare (GIT_STATUS=nothing_to_commit)."
        ;;
    *)
        tg_send "⚠️ Report forense ${DATE_TARGET} NON arrivato su <code>main</code> (GIT_STATUS=${GIT_STATUS}) — serve un intervento manuale, vedi <code>${LOG_FILE}</code>."
        ;;
esac

echo ""
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
# Ultima riga del log, leggibile a macchina dalla review settimanale.
echo "GIT_STATUS=${GIT_STATUS}"
case "$GIT_STATUS" in
    pushed|nothing_to_commit) exit 0 ;;
    *) exit 1 ;;
esac
