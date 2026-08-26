#!/usr/bin/env bash
# Controllo intermedio del parse_fail dei candidati shadow (#34, #358, #368).
#
# PERCHE' ESISTE
# Il verdetto sulla finestra Stage-2 arriva solo alla chiusura, quando
# run_shadow_comparison_report costruisce il confronto e disarma. Ma la
# finestra dura 7 giorni, e le tre precedenti (27/07, 10/08, 24/08) hanno
# raccolto il 100% di scarti senza che nessuno se ne accorgesse fino alla
# fine: il costo dell'accorgersene tardi e' l'intera finestra.
#
# Questo controllo guarda a 24 e 48 ore dall'armamento se il parse_fail e'
# sceso sotto soglia. Se non lo e', c'e' ancora tempo per intervenire invece
# di scoprirlo il giorno della chiusura.
#
# NON decide nulla e non tocca il toggle: legge, scrive un log, notifica.
#
# Session log: logs/shadow_parse_fail_YYYY-MM-DD.log

set -uo pipefail

# cron parte con un PATH minimo: senza questo `docker` non si trova e il giro
# muore prima di cominciare (stesso motivo di daily_s4_ic.sh e deploy_reconcile.sh).
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/shadow_parse_fail_${DATE}.log"
exec >>"$LOG_FILE" 2>&1

echo "=== Controllo parse_fail shadow ${DATE} ==="
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

SOGLIA=${SOGLIA_PARSE_FAIL:-10}

ARMATO=$(docker exec alembic-redis-1 redis-cli GET shadow:model_comparison:started_at 2>/dev/null)
if [[ -z "$ARMATO" ]]; then
    echo "Finestra non armata — niente da controllare. Esco."
    exit 0
fi
echo "Finestra armata dal: $ARMATO"

# Stato dei pool: se un pool e' in ammanco, il parse_fail alto e' una
# conseguenza, non la causa (#368). Va letto prima, non dopo.
for k in ollama:sem ollama:sem:shadow; do
    echo "pool $k: $(docker exec alembic-redis-1 redis-cli LLEN "$k" 2>/dev/null) slot"
done

# Il verdetto si legge sulle ULTIME 24 ORE, non sull'intera finestra.
# Motivo: se durante la finestra si corregge la causa dei fallimenti — com'e'
# successo il 25/08 col pool shadow riseminato (#368) — le righe rotte di
# prima restano nel denominatore e trascinerebbero la percentuale per tutti i
# giorni rimanenti, facendo suonare l'allarme su un guasto gia' risolto.
# La finestra intera resta riportata sotto, come contesto: serve a vedere
# quanto del campione e' compromesso, che e' un'altra domanda.
FINESTRA_VERDETTO="now() - interval '24 hours'"

LETTURA=$(docker exec alembic-postgres-1 psql -U trading -d trading -tA -F'|' -c "
select model_id,
       count(*),
       count(*) filter (where parse_error),
       round(100.0*count(*) filter (where parse_error)/nullif(count(*),0),1),
       round(avg(latency_ms)),
       coalesce(string_agg(distinct failure_reason, ','), '-')
from llm_shadow_responses
where created_at > greatest('${ARMATO}'::timestamptz, ${FINESTRA_VERDETTO})
group by 1 order by 1;" 2>/dev/null)

CONTESTO=$(docker exec alembic-postgres-1 psql -U trading -d trading -tA -F'|' -c "
select model_id, count(*),
       round(100.0*count(*) filter (where parse_error)/nullif(count(*),0),1)
from llm_shadow_responses
where created_at > '${ARMATO}'::timestamptz
group by 1 order by 1;" 2>/dev/null)

if [[ -z "$LETTURA" ]]; then
    echo "Nessuna riga shadow nelle ultime 24h: o non e' passata news, o il path shadow non gira."
    echo "-- contesto, intera finestra:"; echo "${CONTESTO:-(vuoto)}"
    MSG="Shadow parse_fail: NESSUN DATO nelle ultime 24h (finestra armata dal $ARMATO). Il path shadow potrebbe non girare."
else
    echo "-- verdetto, ultime 24h: model_id|n|fail|fail_pct|avg_ms|failure_reason"
    echo "$LETTURA"
    echo "-- contesto, intera finestra: model_id|n|fail_pct"
    echo "${CONTESTO:-(vuoto)}"
    PEGGIO=$(echo "$LETTURA" | awk -F'|' '{if ($4+0 > max) max=$4+0} END {print max+0}')
    echo "parse_fail peggiore: ${PEGGIO}% (soglia ${SOGLIA}%)"
    if (( $(echo "$PEGGIO > $SOGLIA" | bc -l) )); then
        MSG="Shadow parse_fail ${PEGGIO}% > ${SOGLIA}% — la finestra Stage-2 sta raccogliendo scarti. Vedi $LOG_FILE"
        echo "ESITO: SOPRA SOGLIA"
    else
        MSG="Shadow parse_fail ${PEGGIO}% — sotto la soglia del ${SOGLIA}%, la finestra raccoglie dati validi."
        echo "ESITO: OK"
    fi
fi

# Credenziali Telegram: non sono nell'ambiente del cron. Caricamento selettivo,
# solo le due chiavi che servono, come negli altri cron.
if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    curl -sS -o /dev/null -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_CHAT_ID}" -d "text=${MSG}" \
        && echo "Notifica inviata." || echo "Notifica fallita (non blocca)."
else
    echo "Credenziali Telegram assenti — solo log."
fi

echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
