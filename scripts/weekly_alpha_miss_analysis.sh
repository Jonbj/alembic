#!/usr/bin/env bash
# Weekly alpha-miss synthesis. The LLM can only draft files; deterministic
# gates own completeness, Git persistence and GitHub publication (#514).

set -euo pipefail

export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
JOB="$SCRIPT_DIR/weekly_alpha_miss_job.py"
LOG_DIR="$PROJECT_DIR/logs"
REMOTE="${WEEKLY_ALPHA_MISS_REMOTE:-origin}"
BASE_BRANCH="${WEEKLY_ALPHA_MISS_BASE_BRANCH:-main}"
MODEL="${WEEKLY_ALPHA_MISS_MODEL:-opus}"
REPO="${WEEKLY_ALPHA_MISS_REPO:-Jonbj/alembic}"
AS_OF="$(date +%Y-%m-%d)"
CALENDAR_FILE=""
PILOT=0
DRY_RUN_PUBLICATION=0

while (( $# > 0 )); do
    case "$1" in
        --as-of) AS_OF="${2:?manca la data}"; shift 2 ;;
        --calendar-file) CALENDAR_FILE="${2:?manca il file calendario}"; shift 2 ;;
        --pilot) PILOT=1; shift ;;
        --dry-run-publication) DRY_RUN_PUBLICATION=1; shift ;;
        *) echo "Opzione sconosciuta: $1" >&2; exit 2 ;;
    esac
done

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_alpha_miss_${AS_OF}.log"
LOCK_FILE="$LOG_DIR/.weekly_alpha_miss.lock"
exec >>"$LOG_FILE" 2>&1
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "Un altro weekly alpha-miss è già in corso."
    exit 0
fi

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^(ALPACA_API_KEY|ALPACA_SECRET_KEY|TELEGRAM_BOT_TOKEN|TELEGRAM_CHAT_ID)=' \
        "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

tg_send() {
    local message="$1"
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[tg_send] credenziali Telegram assenti — skip" >&2
        return 0
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d text="$message" >/dev/null || true
}

die() {
    echo "FAILED: $*" >&2
    tg_send "🚨 Weekly alpha-miss ${AS_OF} fallito: $* — vedi ${LOG_FILE}"
    exit 1
}

CALENDAR_ARGS=()
if [[ -n "$CALENDAR_FILE" ]]; then
    CALENDAR_ARGS+=(--calendar-file "$CALENDAR_FILE")
fi

echo "=== Weekly Alpha-Miss ${AS_OF} ==="
WEEK=$("$JOB" week --as-of "$AS_OF" "${CALENDAR_ARGS[@]}") \
    || die "impossibile determinare la settimana dal calendario Alpaca"
WT="$PROJECT_DIR/.worktrees/weekly-alpha-miss-${WEEK}"
WT_BRANCH="weekly-alpha-miss/${WEEK}"
YEAR="${WEEK%%-*}"
WEEK_NUMBER="${WEEK##*-W}"
ARTIFACT_DIR="$WT/docs/evidence/weekly-alpha-miss/${WEEK}"
ISSUES_SNAPSHOT="$ARTIFACT_DIR/issues-snapshot.json"
MANIFEST_FILE="$ARTIFACT_DIR/manifest.json"
PLAN_FILE="$ARTIFACT_DIR/publication-plan.json"
REPORT_FILE="$WT/docs/WEEKLY_FINDINGS_${YEAR}-${WEEK_NUMBER}.md"
TOKEN_FILE="$LOG_DIR/weekly_alpha_miss_${WEEK}.token"
BASELINE_TEMPLATE="$WT/prompts/weekly_alpha_miss_baseline.md"
WT_JOB="$WT/scripts/weekly_alpha_miss_job.py"

git -C "$PROJECT_DIR" fetch --quiet "$REMOTE" \
    "+${BASE_BRANCH}:refs/remotes/${REMOTE}/${BASE_BRANCH}" \
    || die "fetch ${REMOTE}/${BASE_BRANCH} fallito"

if [[ ! -e "$WT/.git" ]]; then
    mkdir -p "$(dirname "$WT")"
    if git -C "$PROJECT_DIR" show-ref --verify --quiet "refs/heads/${WT_BRANCH}"; then
        git -C "$PROJECT_DIR" worktree add --quiet "$WT" "$WT_BRANCH" \
            || die "creazione worktree fallita"
    else
        git -C "$PROJECT_DIR" worktree add --quiet -b "$WT_BRANCH" "$WT" \
            "refs/remotes/${REMOTE}/${BASE_BRANCH}" || die "creazione worktree fallita"
    fi
fi

actual_branch=$(git -C "$WT" branch --show-current)
[[ "$actual_branch" == "$WT_BRANCH" ]] \
    || die "worktree ${WT} sul branch inatteso ${actual_branch:-DETACHED}"
if [[ -n "$(git -C "$WT" status --porcelain)" ]]; then
    die "worktree ${WT} contiene un tentativo incompleto; conservarlo e ispezionarlo"
fi
RESUME_PR_URL=""
RESUME_UNPUBLISHED_COMMIT=0
existing_pr=$(gh pr list --repo "$REPO" --state all --head "$WT_BRANCH" \
    --json url,state,mergedAt \
    --jq '.[0] | [.url,.state,(.mergedAt // "")] | @tsv') \
    || die "ricerca PR esistente fallita"
if [[ -n "$existing_pr" ]]; then
    IFS=$'\t' read -r RESUME_PR_URL existing_state existing_merged_at <<<"$existing_pr"
    if [[ "$existing_state" == "CLOSED" && -z "$existing_merged_at" ]]; then
        die "la PR ${RESUME_PR_URL} è stata chiusa senza merge; serve ispezione"
    fi
    echo "RESUMING_PUBLICATION week=${WEEK} pr=${RESUME_PR_URL}"
else
    read -r behind ahead < <(
        git -C "$WT" rev-list --left-right --count \
            "refs/remotes/${REMOTE}/${BASE_BRANCH}...HEAD"
    ) || die "confronto del branch settimanale fallito"
    if (( ahead > 0 )); then
        (( ahead == 1 )) \
            || die "worktree ${WT} contiene ${ahead} commit non pubblicati; serve ispezione"
        expected_subject="evidence(alpha-miss): weekly findings ${WEEK}"
        actual_subject=$(git -C "$WT" log -1 --format=%s)
        [[ "$actual_subject" == "$expected_subject" ]] \
            || die "commit non pubblicato inatteso in ${WT}: ${actual_subject}"
        while IFS= read -r changed_path; do
            case "$changed_path" in
                "${ISSUES_SNAPSHOT#"$WT/"}"|"${MANIFEST_FILE#"$WT/"}"|\
                "${PLAN_FILE#"$WT/"}"|"${REPORT_FILE#"$WT/"}"|\
                "${ARTIFACT_DIR#"$WT/"}/value-first.md") ;;
                *) die "commit settimanale contiene un path inatteso: ${changed_path}" ;;
            esac
        done < <(
            git -C "$WT" diff --name-only \
                "refs/remotes/${REMOTE}/${BASE_BRANCH}...HEAD"
        )
        RESUME_UNPUBLISHED_COMMIT=1
        echo "RESUMING_UNPUBLISHED_COMMIT week=${WEEK}"
    elif (( behind > 0 )); then
        git -C "$WT" merge --quiet --ff-only "refs/remotes/${REMOTE}/${BASE_BRANCH}" \
            || die "fast-forward del worktree fallito"
    fi
fi

PUBLISH_ARGS=()
(( DRY_RUN_PUBLICATION )) && PUBLISH_ARGS+=(--dry-run)

create_weekly_pr() {
    gh pr create --repo "$REPO" --base "$BASE_BRANCH" --head "$WT_BRANCH" \
        --title "Weekly alpha-miss ${WEEK}" \
        --body "Riepilogo settimanale completo e artefatti di provenienza.

Part of #514."
}

if [[ -n "$RESUME_PR_URL" ]] || (( RESUME_UNPUBLISHED_COMMIT )); then
    [[ -s "$MANIFEST_FILE" && -s "$PLAN_FILE" && -s "$REPORT_FILE" ]] \
        || die "tentativo persistito senza tutti gli artefatti validabili"
    "$WT_JOB" validate \
        --project-root "$WT" \
        --manifest "$MANIFEST_FILE" \
        --plan "$PLAN_FILE" \
        --report "$REPORT_FILE" \
        --token "$TOKEN_FILE" \
        || die "gli artefatti persistiti non superano più la validazione"
    if (( RESUME_UNPUBLISHED_COMMIT )); then
        git -C "$WT" push -u "$REMOTE" "$WT_BRANCH" \
            || die "ripresa del push ${WT_BRANCH} fallita"
        RESUME_PR_URL=$(create_weekly_pr) \
            || die "ripresa apertura PR fallita; nessuna issue finding pubblicata"
    fi
    "$WT_JOB" publish \
        --manifest "$MANIFEST_FILE" \
        --plan "$PLAN_FILE" \
        --report "$REPORT_FILE" \
        --token "$TOKEN_FILE" \
        --repo "$REPO" \
        "${PUBLISH_ARGS[@]}" \
        || die "ripresa della pubblicazione incompleta: ${RESUME_PR_URL}"
    CHALLENGER_FILE="$ARTIFACT_DIR/value-first.md"
    if [[ -s "$CHALLENGER_FILE" ]] && (( ! DRY_RUN_PUBLICATION )); then
        "$WT_JOB" record-pilot \
            --repo "$REPO" \
            --issue 515 \
            --week "$WEEK" \
            --pr-url "$RESUME_PR_URL" \
            --baseline-path "${REPORT_FILE#"$WT/"}" \
            --challenger-path "${CHALLENGER_FILE#"$WT/"}" \
            || die "pubblicazione ripresa ma registrazione pilot fallita"
    fi
    echo "WEEKLY_ALPHA_MISS_OK week=${WEEK} pr=${RESUME_PR_URL} resumed=1"
    tg_send "✅ Weekly alpha-miss ${WEEK}: ${RESUME_PR_URL}"
    exit 0
fi

# I retry di completezza non devono sporcare il worktree: snapshot e primo
# manifest vivono nei log finché tutti gli input settimanali non sono presenti.
PREFLIGHT_SNAPSHOT="$LOG_DIR/.weekly_alpha_miss_${WEEK}_issues.json"
PREFLIGHT_MANIFEST="$LOG_DIR/.weekly_alpha_miss_${WEEK}_manifest.json"

gh issue list --repo "$REPO" --state all --limit 1000 \
    --json number,title,body,state,labels,comments > "$PREFLIGHT_SNAPSHOT" \
    || die "snapshot GitHub fallito"

set +e
PREFLIGHT_OUTPUT=$("$WT_JOB" preflight \
    --project-root "$WT" \
    --logs-dir "$PROJECT_DIR/logs" \
    --as-of "$AS_OF" \
    "${CALENDAR_ARGS[@]}" \
    --prompt "$BASELINE_TEMPLATE" \
    --issues-snapshot "$PREFLIGHT_SNAPSHOT" \
    --git-commit "$(git -C "$WT" rev-parse HEAD)" \
    --model "$MODEL" \
    --output "$PREFLIGHT_MANIFEST" 2>&1)
PREFLIGHT_STATUS=$?
set -e
printf '%s\n' "$PREFLIGHT_OUTPUT"
(( PREFLIGHT_STATUS == 0 )) \
    || die "preflight incompleto: ${PREFLIGHT_OUTPUT}"

mkdir -p "$ARTIFACT_DIR"
cp "$PREFLIGHT_SNAPSHOT" "$ISSUES_SNAPSHOT"
"$WT_JOB" preflight \
    --project-root "$WT" \
    --logs-dir "$PROJECT_DIR/logs" \
    --as-of "$AS_OF" \
    "${CALENDAR_ARGS[@]}" \
    --prompt "$BASELINE_TEMPLATE" \
    --issues-snapshot "$ISSUES_SNAPSHOT" \
    --git-commit "$(git -C "$WT" rev-parse HEAD)" \
    --model "$MODEL" \
    --output "$MANIFEST_FILE" \
    || die "persistenza del manifest verificato fallita"

BASELINE_PROMPT=$(<"$BASELINE_TEMPLATE")
BASELINE_PROMPT="${BASELINE_PROMPT//__MANIFEST_FILE__/${MANIFEST_FILE#"$WT/"}}"
BASELINE_PROMPT="${BASELINE_PROMPT//__ISSUES_SNAPSHOT__/${ISSUES_SNAPSHOT#"$WT/"}}"
BASELINE_PROMPT="${BASELINE_PROMPT//__REPORT_FILE__/${REPORT_FILE#"$WT/"}}"
BASELINE_PROMPT="${BASELINE_PROMPT//__PLAN_FILE__/${PLAN_FILE#"$WT/"}}"
BASELINE_PROMPT="${BASELINE_PROMPT//__WEEK__/$WEEK}"

set +e
BASELINE_ALLOWED_TOOLS="Read,Glob,Grep,Write($REPORT_FILE),Write($PLAN_FILE)"
ANALYSIS_OUTPUT=$(cd "$WT" && claude --model "$MODEL" \
    --add-dir "$PROJECT_DIR/logs" \
    --restricted --permission-mode dontAsk --permission-prompts none \
    --no-session-persistence --allowedTools "$BASELINE_ALLOWED_TOOLS" \
    -p "$BASELINE_PROMPT" 2>&1)
ANALYSIS_STATUS=$?
set -e
printf '%s\n' "$ANALYSIS_OUTPUT"
(( ANALYSIS_STATUS == 0 )) || die "sessione baseline terminata con codice ${ANALYSIS_STATUS}"
[[ -s "$REPORT_FILE" && -s "$PLAN_FILE" ]] \
    || die "la baseline non ha prodotto report e publication plan"

"$WT_JOB" validate \
    --project-root "$WT" \
    --manifest "$MANIFEST_FILE" \
    --plan "$PLAN_FILE" \
    --report "$REPORT_FILE" \
    --token "$TOKEN_FILE" \
    || die "draft non valido: GitHub non è stato modificato"

CHALLENGER_FILE=""
if (( PILOT )); then
    CHALLENGER_TEMPLATE="$WT/prompts/weekly_alpha_miss_value_first.md"
    CHALLENGER_FILE="$ARTIFACT_DIR/value-first.md"
    CHALLENGER_PROMPT=$(<"$CHALLENGER_TEMPLATE")
    CHALLENGER_PROMPT="${CHALLENGER_PROMPT//__MANIFEST_FILE__/${MANIFEST_FILE#"$WT/"}}"
    CHALLENGER_PROMPT="${CHALLENGER_PROMPT//__ISSUES_SNAPSHOT__/${ISSUES_SNAPSHOT#"$WT/"}}"
    CHALLENGER_PROMPT="${CHALLENGER_PROMPT//__BASELINE_FILE__/${REPORT_FILE#"$WT/"}}"
    CHALLENGER_PROMPT="${CHALLENGER_PROMPT//__CHALLENGER_FILE__/${CHALLENGER_FILE#"$WT/"}}"
    set +e
    CHALLENGER_ALLOWED_TOOLS="Read,Glob,Grep,Write($CHALLENGER_FILE)"
    CHALLENGER_OUTPUT=$(cd "$WT" && claude --model "$MODEL" \
        --add-dir "$PROJECT_DIR/logs" \
        --restricted --permission-mode dontAsk --permission-prompts none \
        --no-session-persistence --allowedTools "$CHALLENGER_ALLOWED_TOOLS" \
        -p "$CHALLENGER_PROMPT" 2>&1)
    CHALLENGER_STATUS=$?
    set -e
    printf '%s\n' "$CHALLENGER_OUTPUT"
    if (( CHALLENGER_STATUS != 0 )) || [[ ! -s "$CHALLENGER_FILE" ]]; then
        echo "PILOT_INCOMPLETE: challenger non prodotto; la baseline resta pubblicabile"
        CHALLENGER_FILE=""
    fi
fi

allowed_paths=(
    "${ISSUES_SNAPSHOT#"$WT/"}"
    "${MANIFEST_FILE#"$WT/"}"
    "${PLAN_FILE#"$WT/"}"
    "${REPORT_FILE#"$WT/"}"
)
[[ -z "$CHALLENGER_FILE" ]] || allowed_paths+=("${CHALLENGER_FILE#"$WT/"}")
while IFS= read -r changed_path; do
    allowed=0
    for expected_path in "${allowed_paths[@]}"; do
        [[ "$changed_path" == "$expected_path" ]] && allowed=1 && break
    done
    (( allowed )) || die "la sessione ha modificato un path non autorizzato: ${changed_path}"
done < <(
    { git -C "$WT" diff --name-only; git -C "$WT" ls-files --others --exclude-standard; } \
        | sort -u
)

git -C "$WT" add -- "${allowed_paths[@]}"
git -C "$WT" commit -m "evidence(alpha-miss): weekly findings ${WEEK}" \
    || die "commit degli artefatti fallito"
git -C "$WT" push -u "$REMOTE" "$WT_BRANCH" \
    || die "push del branch ${WT_BRANCH} fallito"

PR_URL=$(create_weekly_pr) \
    || die "apertura PR fallita; nessuna issue finding pubblicata"

"$WT_JOB" publish \
    --manifest "$MANIFEST_FILE" \
    --plan "$PLAN_FILE" \
    --report "$REPORT_FILE" \
    --token "$TOKEN_FILE" \
    --repo "$REPO" \
    "${PUBLISH_ARGS[@]}" \
    || die "PR aperta ma pubblicazione issue incompleta: ${PR_URL}"

if [[ -n "$CHALLENGER_FILE" ]] && (( ! DRY_RUN_PUBLICATION )); then
    "$WT_JOB" record-pilot \
        --repo "$REPO" \
        --issue 515 \
        --week "$WEEK" \
        --pr-url "$PR_URL" \
        --baseline-path "${REPORT_FILE#"$WT/"}" \
        --challenger-path "${CHALLENGER_FILE#"$WT/"}" \
        || die "artefatti pubblicati ma registrazione del campione pilot fallita"
fi

echo "WEEKLY_ALPHA_MISS_OK week=${WEEK} pr=${PR_URL}"
tg_send "✅ Weekly alpha-miss ${WEEK}: ${PR_URL}"
