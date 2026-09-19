#!/usr/bin/env bash
# Idempotency guard per i cron daily_alpha_miss_analysis.sh e daily_analysis.sh
# (#564, finding F-075). Dopo un market-holiday weekday il cron risolve
# DATE_TARGET come ultima seduta di borsa chiusa — la stessa gia' analizzata
# il giorno prima. Senza guard, lo script lancia una sessione Claude Code
# intera, rigenera il dossier forense e ri-committa il ledger con lo stesso
# messaggio del run precedente. Questo helper centralizza il check cosi' i
# due cron possono uscire 0 in modo deterministico.
#
# Convenzioni di uscita:
#   exit 0  -> DATE_TARGET gia' processata; il caller deve fare exit 0 pulito.
#   exit 1  -> DATE_TARGET nuova o non confermata; il caller prosegue.
#   exit 2  -> uso errato (parametri mancanti).
#
# Uso da daily_alpha_miss_analysis.sh:
#   bash scripts/_alpha_miss_idempotency_guard.sh \
#       --date-target "$DATE_TARGET" \
#       --ledger "$PROJECT_DIR/docs/evidence/market_daily.jsonl"
#
# Uso da daily_analysis.sh:
#   bash scripts/_alpha_miss_idempotency_guard.sh \
#       --date-target "$DATE_TARGET" \
#       --ledger "/nonexistent" \
#       --report "$REPORT_FILE" \
#       --commit-pattern "evidence: forensic ${DATE_TARGET}" \
#       --project-dir "$PROJECT_DIR"

set -euo pipefail

DATE_TARGET=""
LEDGER_FILE=""
REPORT_FILE=""
COMMIT_PATTERN=""
PROJECT_DIR_ARG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --date-target)
            DATE_TARGET="${2:-}"
            shift 2
            ;;
        --ledger)
            LEDGER_FILE="${2:-}"
            shift 2
            ;;
        --report)
            REPORT_FILE="${2:-}"
            shift 2
            ;;
        --commit-pattern)
            COMMIT_PATTERN="${2:-}"
            shift 2
            ;;
        --project-dir)
            PROJECT_DIR_ARG="${2:-}"
            shift 2
            ;;
        *)
            echo "SKIP (guard): argomento sconosciuto '$1' — procedo." >&2
            exit 1
            ;;
    esac
done

if [[ -z "$DATE_TARGET" ]]; then
    echo "SKIP (guard): --date-target richiesto" >&2
    exit 2
fi

# Chiave alpha-miss: market_daily.jsonl contiene gia' una riga per la data?
# E' la chiave piu' economica — e' l'output osservazionale della pipeline,
# e il cron la riallinea a main prima dell'analisi (#510), quindi se la data
# c'e', e' perche' un run precedente l'ha materializzata.
if [[ -n "$LEDGER_FILE" && -f "$LEDGER_FILE" ]]; then
    if grep -q "\"data\": *\"${DATE_TARGET}\"" "$LEDGER_FILE"; then
        echo "SKIP (guard): ${DATE_TARGET} gia' a ledger in ${LEDGER_FILE} — run duplicato o giorno di borsa chiusa, nessuna sessione Claude necessaria."
        exit 0
    fi
fi

# Chiave forense: il forense non scrive su market_daily.jsonl, ma produce
# docs/FORENSIC_DAILY_REPORT_${DATE_TARGET}.md e committa con messaggio
# deterministico. Il check richiede ENTRAMBI: il file da solo non basta
# (potrebbe essere uno stash non pubblicato), e il commit da solo non basta
# (potrebbe essere stato revertato). Insieme sono la prova che la seduta e'
# stata osservabilmente pubblicata.
#
# Il commit va cercato su origin/main, non su HEAD: lo fa
# commit_evidence_ledger.sh (#411) da una worktree dedicata appuntata su
# main, mentre la tree condivisa da cui gira il cron e' abitualmente
# parcheggiata sul branch di lavoro di un altro agente — su HEAD il commit
# forense spesso non c'e' (la guard girerebbe a vuoto), e quando c'e' non e'
# prova di pubblicazione. Il `-C` serve perche' il cron gira dalla cwd della
# crontab, non dal repo (il `cd "$PROJECT_DIR"` arriva piu' in la'). Senza
# --project-dir il check git non e' interrogabile in modo affidabile: si
# tratta come non disponibile e si procede, perche' un run duplicato costa
# una sessione mentre un cron bloccato costa la seduta.
if [[ -n "$REPORT_FILE" && -n "$COMMIT_PATTERN" && -n "$PROJECT_DIR_ARG" ]]; then
    if [[ -f "$REPORT_FILE" ]]; then
        if git -C "$PROJECT_DIR_ARG" log --oneline origin/main --grep="${COMMIT_PATTERN}" 2>/dev/null | grep -q .; then
            echo "SKIP (guard): ${DATE_TARGET} gia' committata come '${COMMIT_PATTERN}' su origin/main e report forense presente — run duplicato, nessuna sessione Claude necessaria."
            exit 0
        fi
    fi
fi

echo "PROCEDI (guard): ${DATE_TARGET} non a ledger e (per il forense) report/commit non presenti — il cron prosegue."
exit 1
