#!/usr/bin/env bash
# Committa su main i file del ledger di osservazione (#171) prodotti dai cron.
#
# Perche' esiste (#336): i cron girano nella working tree principale del repo,
# che e' abitualmente parcheggiata sul branch di lavoro di un altro agente. La
# guardia "committa solo se sei su main" era corretta ma si limitava a rifiutare:
# nella settimana 2026-34 due run su cinque non hanno committato nulla e altre
# due si sono fermate al push rifiutato. Qui il commit avviene in una worktree
# dedicata appuntata su origin/main, quindi il branch della tree principale non
# entra piu' nell'equazione, e la tree principale non viene toccata.
#
# Uso:
#   scripts/commit_evidence_ledger.sh --message "evidence: ledger 2026-08-26" \
#       docs/evidence/findings.json docs/evidence/market_daily.jsonl docs/REPORT.md
#
# I path sono relativi alla radice del repo (gli assoluti dentro il repo vanno
# bene lo stesso). L'ultima riga stampata e' sempre leggibile a macchina:
#   GIT_STATUS=pushed | committed_not_pushed | not_committed | nothing_to_commit
# Exit 0 solo per pushed / nothing_to_commit.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

REMOTE="${EVIDENCE_REMOTE:-origin}"
BRANCH="${EVIDENCE_BRANCH:-main}"
WORKTREE="${EVIDENCE_WORKTREE:-$PROJECT_DIR/.worktrees/evidence-cron}"
# Branch dedicato: nessun altro lo tocca, quindi "already checked out" non puo'
# accadere e un commit che non riesce a pushare resta raggiungibile (non
# diventa un oggetto penzolante come i c5f37d9/f1d778b di #330).
WT_BRANCH="${EVIDENCE_WORKTREE_BRANCH:-evidence-cron}"
# Path non ancora arrivati su main: si riprovano al giro dopo, altrimenti il
# report di ieri sparirebbe al primo reset della worktree.
PENDING_FILE="${EVIDENCE_PENDING_FILE:-$PROJECT_DIR/logs/.evidence_cron_pending}"

MESSAGE=""
PATHS=()
while (( $# > 0 )); do
    case "$1" in
        -m|--message)
            MESSAGE="${2-}"
            shift 2
            ;;
        --)
            shift
            ;;
        -*)
            echo "Opzione sconosciuta: $1" >&2
            exit 2
            ;;
        *)
            PATHS+=("$1")
            shift
            ;;
    esac
done

if [[ -z "$MESSAGE" ]]; then
    echo "Manca --message" >&2
    exit 2
fi

log() { echo "[evidence-commit] $*"; }

finish() {
    local status="$1"
    shift
    [[ $# -gt 0 ]] && log "$*"
    echo "GIT_STATUS=${status}"
    case "$status" in
        pushed|nothing_to_commit) exit 0 ;;
        *) exit 1 ;;
    esac
}

# Path relativi alla radice, deduplicati, unione con i pendenti del giro prima.
declare -a WANTED=()
add_path() {
    local raw="$1" rel="$1"
    [[ -z "$raw" ]] && return 0
    if [[ "$raw" == /* ]]; then
        rel="${raw#"$PROJECT_DIR"/}"
        if [[ "$rel" == /* ]]; then
            log "ignoro $raw: fuori dal repo"
            return 0
        fi
    fi
    local seen
    for seen in ${WANTED[@]+"${WANTED[@]}"}; do
        [[ "$seen" == "$rel" ]] && return 0
    done
    WANTED+=("$rel")
}

for candidate in ${PATHS[@]+"${PATHS[@]}"}; do
    add_path "$candidate"
done
if [[ -f "$PENDING_FILE" ]]; then
    while IFS= read -r line; do
        add_path "$line"
    done < "$PENDING_FILE"
fi

if (( ${#WANTED[@]} == 0 )); then
    finish nothing_to_commit "nessun path da committare"
fi

write_pending() {
    mkdir -p "$(dirname "$PENDING_FILE")"
    printf '%s\n' ${WANTED[@]+"${WANTED[@]}"} > "$PENDING_FILE"
}

clear_pending() {
    [[ -f "$PENDING_FILE" ]] && : > "$PENDING_FILE"
    return 0
}

fetch_main() {
    # Refspec esplicita: aggiorna refs/remotes/<remote>/<branch> anche quando il
    # remoto non ha un fetch refspec configurato (worktree create a mano).
    git -C "$PROJECT_DIR" fetch --quiet "$REMOTE" \
        "+${BRANCH}:refs/remotes/${REMOTE}/${BRANCH}"
}

ensure_worktree() {
    # Una worktree registrata ma rotta (cancellata a mano, repo spostato) e' il
    # modo piu' facile di incastrare il cron: si ricrea invece di fallire.
    if [[ -e "$WORKTREE/.git" ]] \
        && git -C "$WORKTREE" rev-parse --is-inside-work-tree > /dev/null 2>&1; then
        return 0
    fi
    rm -rf "$WORKTREE"
    git -C "$PROJECT_DIR" worktree prune
    mkdir -p "$(dirname "$WORKTREE")"
    git -C "$PROJECT_DIR" worktree add --quiet -B "$WT_BRANCH" \
        "$WORKTREE" "refs/remotes/${REMOTE}/${BRANCH}"
}

# Riporta la worktree esattamente su origin/main: e' un'area di servizio, non
# conserva stato fra un giro e l'altro (quello che serve e' nei file su disco
# della tree principale piu' la lista dei pendenti).
sync_worktree() {
    git -C "$WORKTREE" reset --quiet --hard "refs/remotes/${REMOTE}/${BRANCH}" \
        && git -C "$WORKTREE" clean --quiet -fd
}

# Copia i file dalla tree principale nella worktree e li mette in staging.
# I due ledger append-only non vengono mai sovrascritti ma fusi sopra main: il
# cron puo' partire da uno snapshot vecchio, e cio' che e' gia' pubblicato non
# deve sparire. Restituisce 1 per qualunque regressione append-only, 2 per un
# errore operativo.
stage_paths() {
    local rel src dest deleted
    local staged=0
    for rel in "${WANTED[@]}"; do
        src="$PROJECT_DIR/$rel"
        if [[ ! -f "$src" ]]; then
            log "salto $rel: non esiste su disco"
            continue
        fi
        dest="$WORKTREE/$rel"
        mkdir -p "$(dirname "$dest")"
        if [[ "$rel" == "docs/evidence/findings.json" ]]; then
            if ! python3 "$SCRIPT_DIR/merge_evidence_findings.py" "$dest" "$src" "$dest"; then
                log "RIFIUTO: impossibile fondere $rel senza perdere evidenza."
                return 1
            fi
        elif [[ "$rel" == *.jsonl ]]; then
            if ! python3 "$SCRIPT_DIR/merge_evidence_jsonl.py" "$dest" "$src" "$dest"; then
                log "RIFIUTO: impossibile fondere $rel senza perdere evidenza."
                return 1
            fi
        else
            cp "$src" "$dest" || return 2
        fi
        git -C "$WORKTREE" add -- "$rel" || return 2
        staged=1
        if [[ "$rel" == *.jsonl ]]; then
            # Invariante, non guardia: dopo la fusione le righe del remoto ci
            # sono tutte. Se ne mancasse una, la fusione ha un difetto e il
            # commit non deve partire lo stesso.
            deleted=$(git -C "$WORKTREE" diff --cached --numstat -- "$rel" | awk '{print $2}')
            if [[ -n "$deleted" && "$deleted" != "-" ]] && (( deleted > 0 )); then
                log "RIFIUTO: $rel perderebbe ${deleted} righe rispetto a ${REMOTE}/${BRANCH}."
                log "La fusione append-only non ha tenuto: risolvere a mano."
                return 1
            fi
        fi
    done
    (( staged == 1 )) || return 3
    return 0
}

if ! fetch_main; then
    log "ATTENZIONE: fetch di ${REMOTE}/${BRANCH} fallito — uso il riferimento locale."
fi
if ! git -C "$PROJECT_DIR" rev-parse --verify --quiet "refs/remotes/${REMOTE}/${BRANCH}" > /dev/null; then
    write_pending
    finish not_committed "nessun riferimento a ${REMOTE}/${BRANCH}: impossibile committare."
fi
if ! ensure_worktree; then
    write_pending
    finish not_committed "impossibile creare la worktree dedicata ${WORKTREE}"
fi

committed=0
for attempt in 1 2; do
    if ! sync_worktree; then
        write_pending
        finish not_committed "impossibile allineare la worktree a ${REMOTE}/${BRANCH}"
    fi

    stage_paths
    stage_status=$?
    if (( stage_status == 1 )); then
        write_pending
        finish not_committed "commit annullato: ledger append-only in regressione o conflitto"
    elif (( stage_status == 2 )); then
        write_pending
        finish not_committed "errore nello staging dei file"
    elif (( stage_status == 3 )); then
        clear_pending
        finish nothing_to_commit "nessuno dei path richiesti esiste su disco"
    fi

    if git -C "$WORKTREE" diff --cached --quiet; then
        clear_pending
        finish nothing_to_commit "i file sono gia' identici a ${REMOTE}/${BRANCH}"
    fi

    if ! git -C "$WORKTREE" commit --quiet -m "$MESSAGE"; then
        write_pending
        finish not_committed "git commit fallito"
    fi
    committed=1
    log "commit $(git -C "$WORKTREE" rev-parse --short HEAD) su ${WT_BRANCH} (tentativo ${attempt})"

    if git -C "$WORKTREE" push --quiet "$REMOTE" "HEAD:${BRANCH}"; then
        clear_pending
        finish pushed "ledger su ${REMOTE}/${BRANCH}: $(printf '%s ' "${WANTED[@]}")"
    fi

    log "push rifiutato al tentativo ${attempt}."
    if (( attempt == 1 )); then
        # Tipicamente non-fast-forward: il remoto e' avanzato. Si risincronizza e
        # si ricommitta sopra la punta nuova — mai un force push.
        if ! fetch_main; then
            log "ATTENZIONE: fetch di rientro fallito."
        fi
    fi
done

write_pending
finish committed_not_pushed "commit locale su ${WT_BRANCH}, push non riuscito: intervento manuale."
