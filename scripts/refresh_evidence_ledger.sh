#!/usr/bin/env bash
# Riallinea a origin/main le copie su disco dei ledger di osservazione (#171).
#
# Perche' esiste (#336): i cron girano nella working tree principale del repo,
# condivisa con il lavoro interattivo. Basta un `git checkout` altrui perche'
# docs/evidence/findings.json e market_daily.jsonl tornino alla versione del
# branch di turno, cioe' indietro rispetto a main. Chi legge quei file prima
# della sessione (alpha_miner_dossier.py per le mediane a 20 giorni,
# economic_pnl_scoreboard.py per i giorni osservati) lavora allora su un ledger
# monco, e la sessione riparte da un prossimo_id gia' usato su main.
#
# Uso:
#   scripts/refresh_evidence_ledger.sh docs/evidence/findings.json \
#       docs/evidence/market_daily.jsonl
#
# Il riallineamento e' un'UNIONE, mai una sostituzione: cio' che e' su disco e
# non ancora su main resta (e' il lavoro che il commit deve ancora pubblicare).
# Ed e' fail-closed sul ledger rotto (#510): un file illeggibile o non fondibile
# non e' un ritardo, e' una base di evidenza corrotta — il 2026-09-02 ha fatto
# uscire questo script con 0 su un findings.json pieno di marcatori di stash
# pop, e il cron e' comunque arrivato a GIT_STATUS=pushed. Ora esce non-zero e
# il chiamante abortisce: nessuna analisi vale piu' di una costruita su un
# ledger che non si puo' nemmeno leggere.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

REMOTE="${EVIDENCE_REMOTE:-origin}"
BRANCH="${EVIDENCE_BRANCH:-main}"

log() { echo "[evidence-refresh] $*"; }

if (( $# == 0 )); then
    log "nessun path da riallineare"
    exit 0
fi

if ! git -C "$PROJECT_DIR" fetch --quiet "$REMOTE" \
    "+${BRANCH}:refs/remotes/${REMOTE}/${BRANCH}"; then
    log "ATTENZIONE: fetch di ${REMOTE}/${BRANCH} fallito — uso il riferimento locale."
fi
if ! git -C "$PROJECT_DIR" rev-parse --verify --quiet \
    "refs/remotes/${REMOTE}/${BRANCH}" > /dev/null; then
    log "ATTENZIONE: nessun riferimento a ${REMOTE}/${BRANCH}: niente da riallineare."
    exit 0
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

for rel in "$@"; do
    local_file="$PROJECT_DIR/$rel"
    remote_file="$TMP_DIR/$(basename "$rel")"
    if ! git -C "$PROJECT_DIR" show "refs/remotes/${REMOTE}/${BRANCH}:$rel" \
        > "$remote_file" 2>/dev/null; then
        log "salto $rel: non esiste su ${REMOTE}/${BRANCH}"
        continue
    fi
    if [[ ! -f "$local_file" ]]; then
        mkdir -p "$(dirname "$local_file")"
        cp "$remote_file" "$local_file"
        log "$rel non era su disco: ripreso da ${REMOTE}/${BRANCH}"
        continue
    fi
    case "$rel" in
        *findings.json) merger="$SCRIPT_DIR/merge_evidence_findings.py" ;;
        *.jsonl) merger="$SCRIPT_DIR/merge_evidence_jsonl.py" ;;
        *)
            log "salto $rel: non e' un ledger append-only riconosciuto"
            continue
            ;;
    esac
    if python3 "$merger" "$remote_file" "$local_file" "$local_file"; then
        if git -C "$PROJECT_DIR" diff --quiet --no-index -- \
            "$remote_file" "$local_file" 2>/dev/null; then
            log "$rel gia' allineato a ${REMOTE}/${BRANCH}"
        else
            log "$rel riallineato a ${REMOTE}/${BRANCH} (unione)"
        fi
    else
        log "RIFIUTO: $rel non fondibile con ${REMOTE}/${BRANCH} — base di evidenza rotta, la copia su disco resta intatta."
        exit 1
    fi
done

exit 0
