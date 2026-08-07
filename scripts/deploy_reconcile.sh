#!/usr/bin/env bash
# Riporta ciò che gira in linea con origin/main, quando è sicuro farlo.
#
# Non è un "deploy dopo il merge": è un RICONCILIATORE. Confronta il commit
# effettivamente in esecuzione con origin/main e agisce solo se divergono. La
# differenza conta: si auto-ripara anche quando il merge lo fa una persona, e
# rieseguirlo due volte di fila non fa nulla la seconda.
#
# Serve perché le immagini sono baked (src/, config/, scripts/ sono COPY nel
# Dockerfile, non montati): un merge sposta main e lascia la produzione ferma.
# Con il merge automatico quello scarto cresce di alcune PR al giorno, in
# silenzio.
#
# Uso:
#   scripts/deploy_reconcile.sh              # riconcilia se serve e se è sicuro
#   scripts/deploy_reconcile.sh --stato      # cosa gira, cosa manca — non tocca nulla
#   scripts/deploy_reconcile.sh --forza      # ignora la finestra di mercato (operatore)

set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
SHA_FILE="$LOG_DIR/deployed_sha"
LOCK_FILE="$LOG_DIR/.deploy_reconcile.lock"
LOG_FILE="$LOG_DIR/deploy_reconcile_$(date +%Y-%m-%d).log"

# Servizi che contengono il codice Python. Il frontend ha la sua immagine.
SERVIZI_BACKEND=(worker worker-inference api beat)

# Il nome del progetto compose DEVE essere esplicito. Di default lo deduce dal
# nome della directory: costruendo dal worktree diventerebbe "deploy" e docker
# tirerebbe su uno STACK NUOVO accanto a quello vivo, invece di sostituirlo.
COMPOSE_PROJ="alembic"

mkdir -p "$LOG_DIR"
log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG_FILE"; }

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "Un'altra riconciliazione è in corso — esco."
    exit 0
fi

cd "$PROJECT_DIR"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^(TELEGRAM_(BOT_TOKEN|CHAT_ID)|ALPACA_(API_KEY|SECRET_KEY))=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

tg_send() {
    [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]] && return 0
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d parse_mode="HTML" -d text="$1" >/dev/null || true
}

git fetch --quiet origin main
TARGET=$(git rev-parse origin/main)
CORRENTE=$(cat "$SHA_FILE" 2>/dev/null || echo "")

# --- cosa è cambiato, e serve davvero ricostruire? ------------------------------
# Un merge di sola documentazione non giustifica un riavvio dei worker: il rischio
# di un restart non è mai zero, e va speso solo dove cambia il comportamento.
servizi_da_ricostruire() {
    local da="$1" a="$2" cambiati backend=0 frontend=0
    if [[ -z "$da" ]]; then echo "backend frontend"; return; fi
    cambiati=$(git diff --name-only "$da" "$a" 2>/dev/null || echo "TUTTO")
    [[ "$cambiati" == "TUTTO" ]] && { echo "backend frontend"; return; }
    while read -r f; do
        [[ -z "$f" ]] && continue
        case "$f" in
            src/*|config/*|scripts/*|pyproject.toml|uv.lock|Dockerfile) backend=1 ;;
            frontend/*) frontend=1 ;;
        esac
    done <<< "$cambiati"
    local out=""
    (( backend )) && out="backend"
    (( frontend )) && out="$out frontend"
    echo "${out# }"
}

DA_FARE=$(servizi_da_ricostruire "$CORRENTE" "$TARGET")

if [[ "$CORRENTE" == "$TARGET" ]]; then
    log "Già allineato a ${TARGET:0:8} — niente da fare."
    [[ "${1:-}" == "--stato" ]] && echo "allineato: ${TARGET:0:8}"
    exit 0
fi

DIETRO=$(git rev-list --count "${CORRENTE:-$TARGET}".."$TARGET" 2>/dev/null || echo "?")

if [[ "${1:-}" == "--stato" ]]; then
    echo "in esecuzione : ${CORRENTE:-sconosciuto}"
    echo "origin/main   : ${TARGET:0:8}  ($DIETRO commit avanti)"
    echo "da ricostruire: ${DA_FARE:-nulla (solo documentazione o test)}"
    exit 0
fi

if [[ -z "$DA_FARE" ]]; then
    # Solo doc/test: allineo il riferimento senza toccare i container, altrimenti
    # ogni commit di documentazione lascerebbe un finto "deploy in ritardo".
    echo "$TARGET" > "$SHA_FILE"
    log "Solo documentazione o test fra ${CORRENTE:0:8} e ${TARGET:0:8}: nessun rebuild, riferimento aggiornato."
    exit 0
fi

# --- finestra di mercato --------------------------------------------------------
# Riavviare i worker a mercato aperto significa interrompere un ciclo di
# portafoglio a metà, con ordini potenzialmente in volo. Il ritardo non costa
# nulla: il riconciliatore ripassa.
mercato_aperto() {
    [[ -z "${ALPACA_API_KEY:-}" ]] && return 0   # in dubbio, si considera aperto
    local r
    r=$(uv run python3 - <<'PYEOF' 2>/dev/null
import os
from alpaca.trading.client import TradingClient
try:
    c = TradingClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
    print("APERTO" if c.get_clock().is_open else "CHIUSO")
except Exception:
    print("IGNOTO")
PYEOF
)
    [[ "$r" == "CHIUSO" ]] && return 1
    return 0   # APERTO o IGNOTO → non si tocca nulla
}

if [[ "${1:-}" != "--forza" ]] && mercato_aperto; then
    log "Mercato aperto (o stato ignoto): rimando. Indietro di $DIETRO commit."
    exit 0
fi

# --- ricostruzione --------------------------------------------------------------
log "=== Riconciliazione ${CORRENTE:0:8} → ${TARGET:0:8} ($DIETRO commit, da ricostruire: $DA_FARE) ==="
tg_send "🔧 <b>Deploy</b> — riallineo la produzione a <code>${TARGET:0:8}</code> ($DIETRO commit indietro)."

# Si ricostruisce da origin/main, non dall'albero di lavoro: un'altra sessione
# potrebbe averci lasciato dentro un branch o modifiche non committate, e
# finirebbero in produzione senza che nessuno le abbia mai mergiate.
WT="$PROJECT_DIR/.worktrees/deploy"
git worktree remove --force "$WT" 2>/dev/null || true
git worktree add -q --detach "$WT" "$TARGET"
# Il .env non e' versionato: senza, compose non riesce nemmeno a interpolare il
# file. Collegato invece che copiato, per non lasciare in giro una seconda copia
# dei segreti.
ln -sf "$PROJECT_DIR/.env" "$WT/.env"

fallisci() {
    log "FALLITO: $1"
    tg_send "🔴 <b>Deploy fallito</b> — $1
La produzione resta su <code>${CORRENTE:0:8}</code>. Il riferimento NON è stato aggiornato: il prossimo giro riprova."
    git worktree remove --force "$WT" 2>/dev/null || true
    exit 1
}

if [[ "$DA_FARE" == *backend* ]]; then
    (cd "$WT" && timeout 1800 docker compose -p "$COMPOSE_PROJ" build "${SERVIZI_BACKEND[@]}") >>"$LOG_FILE" 2>&1 \
        || fallisci "build dei servizi backend"
    (cd "$WT" && timeout 600 docker compose -p "$COMPOSE_PROJ" up -d "${SERVIZI_BACKEND[@]}") >>"$LOG_FILE" 2>&1 \
        || fallisci "avvio dei servizi backend"
fi
if [[ "$DA_FARE" == *frontend* ]]; then
    (cd "$WT" && timeout 1800 docker compose -p "$COMPOSE_PROJ" build frontend) >>"$LOG_FILE" 2>&1 \
        || fallisci "build del frontend"
    (cd "$WT" && timeout 600 docker compose -p "$COMPOSE_PROJ" up -d frontend) >>"$LOG_FILE" 2>&1 \
        || fallisci "avvio del frontend"
fi

sleep 25

# --- verifica -------------------------------------------------------------------
# Il riferimento si aggiorna SOLO dopo la verifica. Se qualcosa non torna, il
# prossimo giro riprova invece di credere che sia andata bene.
# Il `|| true` non e' cosmetico: con `pipefail`, un grep che non trova nulla fa
# fallire la pipeline, e "nulla da segnalare" e' proprio il caso di SUCCESSO.
# Senza, lo script moriva qui in silenzio ogni volta che il deploy andava bene.
GIU=$( { docker compose -p "$COMPOSE_PROJ" ps --format '{{.Service}} {{.State}}' 2>/dev/null \
         | grep -v " running" || true; } | awk '{print $1}' | tr '\n' ' ')
[[ -n "$GIU" ]] && fallisci "servizi non in esecuzione dopo il riavvio: $GIU"

if [[ "$DA_FARE" == *backend* ]]; then
    docker exec alembic-worker-1 python -c "import src.workers.portfolio_scheduler" >/dev/null 2>&1 \
        || fallisci "il worker non importa il codice dell'applicazione"
fi

echo "$TARGET" > "$SHA_FILE"
git worktree remove --force "$WT" 2>/dev/null || true
log "=== Riconciliato a ${TARGET:0:8} ==="
tg_send "🟢 <b>Deploy completato</b> — produzione allineata a <code>${TARGET:0:8}</code> ($DIETRO commit, $DA_FARE)."
