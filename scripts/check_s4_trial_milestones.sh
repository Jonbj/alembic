#!/usr/bin/env bash
# Sorveglia le milestone pre-registrate del trial exit S4 (#298).
#
# PERCHE' ESISTE
# Il contratto congelato fissa tre momenti in cui qualcuno deve intervenire, e
# nessuno li guardava:
#   1. `N_cluster: null` — la raccolta non ha un traguardo, quindi nemmeno le
#      altre due milestone possono scattare. E' lo stato di oggi.
#   2. ri-stima blinded al 50% di N_cluster, concessa una sola volta.
#   3. l'unica analisi decisionale, a N_cluster.
# Superarli in silenzio costa il trial: la ri-stima e' irripetibile e
# l'analisi e' una sola.
#
# COSA NON FA
# Non decide, non promuove una policy, non scrive nel contratto congelato:
# sono atti dell'operatore. E non pubblica mai l'effetto — il contratto limita
# gli interim a "integrita', sicurezza e statistiche blinded", quindi da qui
# escono solo sigma, conteggi e progresso. Mai media ne' delta.
#
# Stato: logs/.s4_trial_milestones  (una milestone per riga, gia' annunciate)
# Session log: logs/s4_trial_milestones_YYYY-MM-DD.log

set -uo pipefail

# cron parte con un PATH minimo (stesso motivo di deploy_reconcile.sh).
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/s4_trial_milestones_${DATE}.log"
STATO_FILE="${S4_MILESTONE_STATE:-$LOG_DIR/.s4_trial_milestones}"
SNAPSHOT_DIR="$PROJECT_DIR/docs/evidence/s4_trial_milestones"
ISSUE=298
# L'inizio della finestra del trial: le prime coppie ricostruibili sono del 25/08
# (coverage P0 100% solo dopo #372 e #374).
FINESTRA_INIZIO="${S4_TRIAL_START:-2026-08-25}"

exec >>"$LOG_FILE" 2>&1
echo "=== Milestone trial exit S4 ${DATE} ==="
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

tg_send() {
    local text="$1"
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[tg_send] credenziali Telegram assenti — salto"; return
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d parse_mode=HTML -d text="$text" > /dev/null
}

touch "$STATO_FILE"
GIA=$(paste -sd, "$STATO_FILE" 2>/dev/null || echo "")
echo "Gia' annunciate: ${GIA:-nessuna}"

set +e
USCITA_JSON=$(cd "$PROJECT_DIR" && uv run python scripts/check_s4_trial_milestones.py \
    --start "$FINESTRA_INIZIO" --end "$(date +%Y-%m-%d)" \
    --gia-notificate "$GIA" \
    --osservazioni-minime "${S4_MILESTONE_MIN_OBS:-20}" 2>&1)
STATO=$?
set -e
printf '%s\n' "$USCITA_JSON"

if (( STATO == 0 )); then
    echo "Nessuna milestone nuova."
    echo "MILESTONE=none"
    exit 0
fi
if (( STATO != 10 )); then
    echo "FAILED: il controllo e' uscito con codice ${STATO}"
    tg_send "🚨 Controllo milestone trial S4 fallito (codice ${STATO}) — vedi <code>${LOG_FILE}</code>."
    echo "MILESTONE=error"
    exit "$STATO"
fi

MILESTONE=$(printf '%s' "$USCITA_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["milestone"])')
echo "Milestone raggiunta: $MILESTONE"

# 1. Traccia databile: la milestone deve restare dimostrabile a posteriori.
mkdir -p "$SNAPSHOT_DIR"
SNAPSHOT="$SNAPSHOT_DIR/${DATE}_${MILESTONE}.json"
printf '%s\n' "$USCITA_JSON" > "$SNAPSHOT"
echo "Snapshot: $SNAPSHOT"

# 2. Notifica, blinded per costruzione: il JSON che stampiamo non puo'
#    contenere l'effetto, ci pensa riepilogo_blinded() a rifiutarlo.
tg_send "🔔 <b>Trial exit S4 — milestone ${MILESTONE}</b>

<pre>${USCITA_JSON}</pre>

Serve l'operatore: il contratto congelato non lo tocca un job.
Snapshot: <code>${SNAPSHOT}</code>"

# 3. La issue torna leggibile come lavoro umano.
gh issue edit "$ISSUE" --add-label ready-for-human --remove-label waiting 2>/dev/null \
    && echo "Issue #${ISSUE}: ready-for-human" \
    || echo "ATTENZIONE: non sono riuscito a rietichettare #${ISSUE}."
gh issue comment "$ISSUE" --body "Milestone **${MILESTONE}** raggiunta il ${DATE}.

\`\`\`json
${USCITA_JSON}
\`\`\`

Solo statistiche blinded: il contratto limita gli interim a integrità, sicurezza e statistiche blinded, quindi qui non compaiono né \`mean_delta_bps\` né \`net_delta_usd\`.

Snapshot: \`${SNAPSHOT#"$PROJECT_DIR/"}\`" 2>/dev/null \
    && echo "Commento pubblicato su #${ISSUE}." \
    || echo "ATTENZIONE: non sono riuscito a commentare #${ISSUE}."

# 4. Rientro nella coda del loop, SOLO all'analisi decisionale.
#    Le prime due milestone chiedono un atto dell'operatore sul contratto
#    congelato, che un agente non puo' compiere: rimetterla in coda li'
#    produrrebbe solo giri a vuoto. La coda resta comunque di chi la scrive —
#    questo append e' rumoroso di proposito, ed e' disattivabile.
if [[ "$MILESTONE" == "ANALISI_DECISIONALE" && "${S4_MILESTONE_REQUEUE:-1}" == "1" ]]; then
    CODA="$PROJECT_DIR/scripts/roadmap_queue.txt"
    if ! grep -qE "^${ISSUE}\b" "$CODA"; then
        {
            echo ""
            echo "# Rimessa in coda da check_s4_trial_milestones.sh il ${DATE}:"
            echo "# raggiunto N_cluster, l'analisi decisionale e' dovuta."
            echo "${ISSUE}  S4 exit trial: analisi decisionale a N_cluster"
        } >> "$CODA"
        echo "Issue #${ISSUE} rimessa in scripts/roadmap_queue.txt."
        tg_send "📋 #${ISSUE} rimessa nella coda della roadmap: analisi decisionale dovuta."
    fi
fi

printf '%s\n' "$MILESTONE" >> "$STATO_FILE"
echo "Completed: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "MILESTONE=${MILESTONE}"
