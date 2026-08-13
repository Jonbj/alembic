#!/usr/bin/env bash
# Ogni mattina: il lavoro dei modelli è arrivato fino in fondo, o si è fermato a metà?
#
# Il giro della roadmap ha quattro passaggi — PR aperta, CI, review, merge — più il
# deploy. Ognuno può fallire lasciando lo stato precedente intatto, quindi
# "nessun errore" e "tutto fermo da tre giorni" hanno la stessa faccia. Questo
# controllo guarda solo i punti dove il lavoro può restare appeso.
#
# Nasce da un caso reale: il 07/08 tre PR hanno superato la CI e si sono fermate
# alla review senza lasciare un verdetto, e il riconciliatore del deploy ha
# fallito cinque giri di fila annunciando ogni volta di partire. Nulla ha gridato.
#
# Uso: scripts/roadmap_health_check.sh [--quiet]
#   --quiet: manda il Telegram solo se c'è qualcosa che non va

set -euo pipefail
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

# Una PR che aspetta da più di questo è ferma, non lenta: il giro che l'ha aperta
# è finito da un pezzo e nessuno tornerà a guardarla da solo.
ORE_PR_FERMA=18

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi
tg_send() {
    [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]] && return 0
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d parse_mode="HTML" -d text="$1" >/dev/null || true
}

PROBLEMI=(); NOTE=()
git fetch --quiet origin main 2>/dev/null || NOTE+=("fetch di origin fallito")

# ── 1. PR del loop rimaste appese ───────────────────────────────────────────────
# Una PR aperta dal loop e mai chiusa significa che uno dei passaggi dopo la CI
# non è arrivato in fondo. Distingue chi ha già una review da chi non ne ha
# nessuna: sono due guasti diversi (merge rifiutato vs review morta).
ADESSO=$(date +%s)
while read -r riga; do
    [[ -z "$riga" ]] && continue
    num=${riga%% *}; resto=${riga#* }
    creata=${resto%% *}; branch=${resto#* }
    eta=$(( (ADESSO - $(date -d "$creata" +%s)) / 3600 ))
    (( eta < ORE_PR_FERMA )) && continue
    # Il verdetto distingue un guasto da un esito sano: una PR RESPINTA è il
    # sistema che funziona, una APPROVATA e non mergiata è il merge che si è
    # rotto, una senza verdetto è la review morta a metà. Confonderle
    # trasformerebbe questo controllo in rumore da ignorare.
    corpo=$(gh pr view "$num" --json comments -q '.comments[-1].body' 2>/dev/null || echo "")
    if [[ -z "$corpo" ]]; then
        PROBLEMI+=("PR #${num} (${branch}) aperta da ${eta}h, <b>nessuna review</b> — il giro si è fermato prima del verdetto")
    elif echo "$corpo" | grep -qiE 'VERDETTO:[[:space:]]*\**APPROVA'; then
        PROBLEMI+=("PR #${num} (${branch}) aperta da ${eta}h, <b>approvata e non mergiata</b> — il merge non è andato a buon fine")
    elif echo "$corpo" | grep -qiE 'VERDETTO:[[:space:]]*\**RESPINGI'; then
        NOTE+=("PR #${num} respinta dalla review ${eta}h fa — attende un altro giro, non è un guasto")
    else
        PROBLEMI+=("PR #${num} (${branch}) aperta da ${eta}h, review presente ma <b>senza verdetto leggibile</b>")
    fi
done < <(gh pr list --state open --json number,createdAt,headRefName \
            -q '.[]|select(.headRefName|startswith("agent/issue-"))|"\(.number) \(.createdAt) \(.headRefName)"' 2>/dev/null)

# ── 2. Produzione indietro rispetto a main ──────────────────────────────────────
# Il merge non è un deploy: le immagini sono baked. Questo è lo scarto che cresce
# in silenzio a ogni PR mergiata.
SHA_DEP=$(cat "$LOG_DIR/deployed_sha" 2>/dev/null || echo "")
SHA_MAIN=$(git rev-parse origin/main)
if [[ -z "$SHA_DEP" ]]; then
    PROBLEMI+=("Nessun riferimento di deploy registrato: non si sa cosa stia girando")
elif [[ "$SHA_DEP" != "$SHA_MAIN" ]]; then
    dietro=$(git rev-list --count "$SHA_DEP".."$SHA_MAIN" 2>/dev/null || echo "?")
    # Solo doc/test non è un problema: il riconciliatore lo salta apposta.
    rilevante=$(git diff --name-only "$SHA_DEP" "$SHA_MAIN" 2>/dev/null \
                | grep -cE '^(src/|config/|scripts/|pyproject.toml|uv.lock|Dockerfile|frontend/)' || true)
    if (( rilevante > 0 )); then
        PROBLEMI+=("Produzione indietro di <b>${dietro} commit</b> (${rilevante} file che richiedono rebuild): <code>${SHA_DEP:0:8}</code> → <code>${SHA_MAIN:0:8}</code>")
    else
        NOTE+=("main avanti di ${dietro} commit, ma solo documentazione o test")
    fi
fi

# ── 3. Il riconciliatore del deploy fallisce ripetutamente ──────────────────────
# Un fallimento isolato si recupera da solo al giro dopo. Uno ripetuto no, ed è
# il caso che è passato inosservato per dodici ore.
recenti=$(cat "$LOG_DIR"/deploy_reconcile_$(date +%Y-%m-%d).log \
               "$LOG_DIR"/deploy_reconcile_$(date -d yesterday +%Y-%m-%d).log 2>/dev/null || true)
avviati=$(echo "$recenti" | grep -c "=== Riconciliazione" || true)
conclusi=$(echo "$recenti" | grep -c "=== Riconciliato" || true)
if (( avviati > 0 && avviati - conclusi >= 2 )); then
    PROBLEMI+=("Riconciliazione del deploy: <b>${avviati} avviate, ${conclusi} concluse</b> nelle ultime 48h — si annuncia e non finisce")
fi

# ── 4. Il loop ha girato? ───────────────────────────────────────────────────────
# Quattro giri al giorno. Zero significa cron morto, lock rimasto, o coda vuota:
# distinguerli richiede di guardare, ma accorgersene no.
giri=$(grep -c "=== Giro roadmap" "$LOG_DIR/roadmap_agent_$(date -d yesterday +%Y-%m-%d).log" 2>/dev/null || echo 0)
(( giri == 0 )) && PROBLEMI+=("Ieri il loop non ha fatto <b>nessun giro</b>: cron, lock o coda")

# ── 5. Motori in panchina ───────────────────────────────────────────────────────
for f in "$LOG_DIR"/engine_blocked_*; do
    [[ -f "$f" ]] || continue
    m=$(basename "$f" | sed 's/engine_blocked_//')
    fino=$(cat "$f" 2>/dev/null || echo 0)
    (( fino > ADESSO )) && NOTE+=("motore ${m} in panchina fino alle $(date -d "@$fino" '+%H:%M')")
done

# ── 6. Coda ─────────────────────────────────────────────────────────────────────
rimaste=$(gh issue list --state open --label freeze-ok --json number -q '.|length' 2>/dev/null || echo "?")
NOTE+=("${rimaste} issue freeze-ok ancora aperte")

# ── esito ───────────────────────────────────────────────────────────────────────
if (( ${#PROBLEMI[@]} == 0 )); then
    testo="🟢 <b>Roadmap — catena integra</b>
Nessuna PR appesa, produzione allineata a <code>${SHA_MAIN:0:8}</code>."
    [[ ${#NOTE[@]} -gt 0 ]] && testo="$testo

<i>$(printf '%s · ' "${NOTE[@]}" | sed 's/ · $//')</i>"
    echo "OK — nessun problema"
    [[ "${1:-}" == "--quiet" ]] || tg_send "$testo"
else
    testo="🟠 <b>Roadmap — la catena si è interrotta</b>

$(printf '• %s\n' "${PROBLEMI[@]}")"
    [[ ${#NOTE[@]} -gt 0 ]] && testo="$testo

<i>$(printf '%s · ' "${NOTE[@]}" | sed 's/ · $//')</i>"
    printf '%s\n' "${PROBLEMI[@]}" | sed 's/<[^>]*>//g'
    tg_send "$testo"
fi
