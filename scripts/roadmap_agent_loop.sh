#!/usr/bin/env bash
# Un giro di lavoro sulla roadmap, eseguito in un worktree isolato da un modello
# esterno a chi ha progettato l'impianto (vedi MOTORI piu' sotto).
#
# Prende UNA issue per run — la prima della coda ancora lavorabile — apre una PR,
# la fa rivedere a un modello diverso, e la mergia se DUE cancelli passano
# entrambi: zero test rotti in piu' rispetto a main (stesso commit), e verdetto
# positivo del recensore. Qualsiasi altro esito lascia la PR aperta.
#
# La CI qui e' cronicamente rossa per motivi ambientali, quindi il suo esito preso
# da solo non dice nulla: e' la DIFFERENZA rispetto a main a essere il segnale.
#
# Dopo un merge chiama scripts/deploy_reconcile.sh, perche' le immagini sono baked
# e un merge da solo lascerebbe la produzione indietro.
#
# Perimetro: dal 2026-08-03 al 2026-09-28 vige il freeze di osservazione (#171).
# L'agente NON sceglie cosa sia compatibile col freeze. Due lucchetti indipendenti
# lo decidono a monte:
#   1. scripts/roadmap_queue.txt  — l'ordine
#   2. la label `freeze-ok` su GitHub — il permesso
# Una issue si lavora solo se compare in entrambi. L'agente non puo' modificare
# nessuno dei due (e il prompt glielo vieta esplicitamente).
#
# Log      : logs/roadmap_agent_YYYY-MM-DD.log
# Stato    : logs/roadmap_agent_state.tsv   (issue <TAB> tentativi)
# Risultati: logs/roadmap_results.jsonl (una riga JSON per evento significativo,
#            append-only — vedi log_evento piu' sotto)

set -euo pipefail

# cron parte con un PATH minimo (/usr/bin:/bin). Senza /usr/local/bin `ollama`
# non si trova, e glm52/minimax risulterebbero "non installati": il loop girerebbe
# sul solo codex senza che nulla lo segnali.
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUEUE_FILE="${ROADMAP_QUEUE_FILE:-$SCRIPT_DIR/roadmap_queue.txt}"
LOG_DIR="$PROJECT_DIR/logs"
STATE_FILE="$LOG_DIR/roadmap_agent_state.tsv"
LOCK_FILE="$LOG_DIR/.roadmap_agent.lock"
LOG_FILE="$LOG_DIR/roadmap_agent_$(date +%Y-%m-%d).log"

MAX_TENTATIVI=2          # dopo due fallimenti l'issue esce dalla rotazione
TIMEOUT_SESSIONE=5400    # 90 minuti: oltre, la sessione e' bloccata, non lenta

# --- chi lavora le issue --------------------------------------------------------
# Il lavoro di roadmap e' demandato ad altri modelli, non alla sessione che ha
# scritto questo impianto. Due ragioni, e la seconda conta piu' della prima:
#   1. chi ha scritto la coda e i criteri non e' l'osservatore adatto a giudicare
#      se il lavoro che ne esce li rispetta;
#   2. modelli diversi sbagliano in modo diverso. Un solo modello su venti issue
#      ripete venti volte lo stesso punto cieco, e nessuno lo vede.
# La rotazione avanza a ogni giro, indipendentemente dall'esito.
#
# glm52 e minimax girano dentro Claude Code ma con un modello diverso sotto
# (`ollama launch claude --model ...`): stesso utensile, testa diversa.
MOTORI=(codex glm52 minimax)
MOTORE_STATE="$LOG_DIR/roadmap_agent_engine.txt"

# Rate limit: un motore esaurito non e' un motore rotto. Viene messo in panchina
# per un po' e rientra da solo alla scadenza — nessun intervento manuale, che
# altrimenti diventerebbe il vero collo di bottiglia del loop.
RATE_LIMIT_COOLDOWN=$(( 3 * 3600 ))
# Le firme sono volutamente larghe: un falso positivo costa una panchina di 3h,
# un falso negativo brucia il giro e conta un fallimento a carico della issue.
_RATE_LIMIT_RE='rate.?limit|429|quota exceeded|too many requests|usage limit|resource_exhausted|overloaded'

# Quante righe finali contano come ESITO della sessione. Il resto dell'output non e'
# un giudizio: e' la trascrizione di cio' che il recensore ha letto — prompt
# riecheggiato, `gh issue list`, diff, sorgenti numerati.
CODA_ESITO=40

# Legge l'esito di una review dallo stdin. Unico punto in cui l'output di un
# recensore viene interpretato (#211).
#
# L'ordine dei due controlli non e' arbitrario. Prima il verdetto, poi il rate
# limit, perche' una sessione uccisa dalla quota non arriva a scrivere una riga
# canonica in coda: se il verdetto c'e', la sessione e' viva e qualunque
# "rate limit" nel testo e' roba che il recensore ha LETTO, non che ha subito.
# Era l'errore inverso a bruciare i verdetti veri: il titolo della issue #43
# ("B8: rate limiting + CORS"), un hunk `@@ -429,6` o la riga 3429 di un sorgente
# bastavano a scartare un RESPINGI motivato e a mettere in panchina il recensore.
#
# `tail -1` chiude il difetto grave: codex riecheggia il prompt, che contiene
# ENTRAMBE le righe canoniche, e le contiene PRIMA di aver giudicato. Un `grep -q`
# su tutto l'output usciva al primo match — sempre l'eco, sempre APPROVA — e
# mergiava in produzione PR che il recensore aveva respinto.
#
# La sicurezza non dipende dalla taratura di CODA_ESITO: nell'eco del prompt
# RESPINGI viene DOPO APPROVA, quindi `tail -1` su un'eco isolata da' comunque
# RESPINGI. Sbagliare la finestra puo' far perdere un verdetto, mai inventarne
# uno positivo.
estrai_verdetto() {
    local _out _coda _v
    _out=$(cat)
    _coda=$(printf '%s\n' "$_out" | tail -n "$CODA_ESITO")

    # `|| true`: nessun match e' l'esito normale di una sessione senza verdetto, non
    # un errore. Con `set -euo pipefail` l'uscita 1 di grep ucciderebbe lo script.
    _v=$(printf '%s\n' "$_coda" | grep -E "^VERDETTO: (APPROVA|RESPINGI)[[:space:]]*$" | tail -1 || true)
    case "$_v" in
        "VERDETTO: APPROVA")  echo "APPROVA";  return 0 ;;
        "VERDETTO: RESPINGI") echo "RESPINGI"; return 0 ;;
    esac

    if printf '%s\n' "$_coda" | grep -qiE "$_RATE_LIMIT_RE"; then
        echo "RATE_LIMIT"; return 0
    fi
    echo "NON_ESEGUITA"
}

# Ricava il numero di issue dal nome del branch. Legge il segmento `issue-<N>`, non
# la coda della stringa: gli agenti che rifanno il lavoro pubblicano su branch
# derivati, e `grep -oE '[0-9]+$'` su `agent/issue-191-v3` restituiva 3 (#221).
# `--rivedi` ci costruiva sopra il prompt di review, che finiva per giudicare la PR
# contro i requisiti della issue #3.
issue_del_branch() {
    printf '%s\n' "$1" | sed -nE 's|.*issue-([0-9]+).*|\1|p' | head -1
}

# Trova la PR prodotta dal giro. Il nome del branch e' un ripiego, non il criterio:
# l'ancoraggio solido e' la issue che la PR dichiara di chiudere. Con la sola
# corrispondenza esatta sul branch, PR #220 (`agent/issue-191-v3`) e #217
# (`agent/issue-185-v2`) risultavano inesistenti — tentativo contato come
# fallimento e, molto peggio, cancello di review mai raggiunto.
#
# Il ripiego sul nome resta per le PR che dichiarano `Part of #N` invece di
# `closes`: li' closingIssuesReferences e' vuoto. Ancorato con `($|-)` perche'
# `agent/issue-19` non deve rispondere per la issue #191.
trova_pr_del_giro() {
    local _issue="$1"
    gh pr list --state open --json number,headRefName,closingIssuesReferences 2>/dev/null \
        | jq -r --argjson i "$_issue" '
            [ .[] | select(
                ((.closingIssuesReferences // []) | any(.number == $i))
                or (.headRefName | test("^agent/issue-\($i)($|-)"))
            ) ] | .[0].number // ""' 2>/dev/null || true
}

# Prima del lock: sono funzioni pure, non giri di lavoro.
if [[ "${1:-}" == "--verdetto" ]]; then
    estrai_verdetto
    exit 0
fi
if [[ "${1:-}" == "--issue-del-branch" ]]; then
    issue_del_branch "${2:?uso: --issue-del-branch <branch>}"
    exit 0
fi
if [[ "${1:-}" == "--trova-pr" ]]; then
    trova_pr_del_giro "${2:?uso: --trova-pr <numero issue>}"
    exit 0
fi

mkdir -p "$LOG_DIR"
touch "$STATE_FILE"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG_FILE"; }

# --- telemetria strutturata ------------------------------------------------------
# Una riga JSON per evento significativo (0-1 per giro): risponde a domande tipo
# "quante PR ha mergiato codex questo mese" senza ssh+grep+incrocio manuale con
# GitHub. Append-only e mai riletto da questo script — e' un log di eventi, non
# uno stato che il loop deve mantenere coerente. Si carica in pandas/sqlite
# quando serve analizzarlo.
RESULTS_FILE="$LOG_DIR/roadmap_results.jsonl"

# Scrive un evento. Argomenti come "chiave=valore"; un valore che inizia con '#'
# e' scritto senza virgolette (numero, bool, null), il resto come stringa. jq
# costruisce il JSON apposta: niente escaping a mano di virgolette o unicode nei
# titoli delle issue o nel testo di un verdetto.
# Un fallimento qui (jq assente, disco pieno) non deve mai fermare il giro: la
# telemetria e' un di piu', non un requisito del loop — da cui il `|| true`.
log_evento() {
    local action="$1"; shift
    local jq_args=(--arg ts "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" --arg action "$action")
    local jq_filter='ts:$ts, action:$action'
    local kv k v
    for kv in "$@"; do
        k="${kv%%=*}"; v="${kv#*=}"
        if [[ "$v" == \#* ]]; then
            jq_args+=(--argjson "$k" "${v#\#}")
        else
            jq_args+=(--arg "$k" "$v")
        fi
        jq_filter+=", ${k}: \$${k}"
    done
    jq -nc "${jq_args[@]}" "{${jq_filter}}" >> "$RESULTS_FILE" 2>/dev/null || true
}

# Un solo giro alla volta. Senza questo, due run sovrapposti lavorerebbero la
# stessa issue in due worktree diversi e produrrebbero due PR concorrenti.
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "Un altro giro e' gia' in corso — esco."
    exit 0
fi

cd "$PROJECT_DIR"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
    set +a
fi

tg_send() {
    local text="$1"
    [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]] && return 0
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" -d parse_mode="HTML" -d text="$text" >/dev/null || true
}

RESPINTE_FILE="$LOG_DIR/roadmap_agent_respinte.tsv"
MAX_RESPINTE=2           # oltre, il problema non e' l'esecuzione ma la specifica
RIPRESA=0
touch "$RESPINTE_FILE"

respinte_di() { awk -F'\t' -v n="$1" '$1==n {print $2}' "$RESPINTE_FILE" | tail -1; }

registra_respinta() {
    local n="$1" prec; prec=$(respinte_di "$n"); prec=${prec:-0}
    grep -v -P "^${n}\t" "$RESPINTE_FILE" > "${RESPINTE_FILE}.tmp" 2>/dev/null || true
    printf '%s\t%s\n' "$n" "$((prec + 1))" >> "${RESPINTE_FILE}.tmp"
    mv "${RESPINTE_FILE}.tmp" "$RESPINTE_FILE"
}

# Verdetto dell'ultima review sulla PR di questa issue, o vuoto se non c'e'.
verdetto_pr_di() {
    local corpo
    corpo=$(gh pr list --state open --head "agent/issue-$1" --json number -q '.[0].number' 2>/dev/null)
    [[ -z "$corpo" ]] && return 0
    corpo=$(gh pr view "$corpo" --json comments -q '.comments[-1].body' 2>/dev/null || echo "")
    if echo "$corpo" | grep -qiE 'VERDETTO:[[:space:]]*\**RESPINGI'; then echo "RESPINGI"
    elif echo "$corpo" | grep -qiE 'VERDETTO:[[:space:]]*\**APPROVA'; then echo "APPROVA"; fi
}

tentativi_di() { awk -F'\t' -v n="$1" '$1==n {print $2}' "$STATE_FILE" | tail -1; }

registra_tentativo() {
    local n="$1" prec
    prec=$(tentativi_di "$n"); prec=${prec:-0}
    grep -v -P "^${n}\t" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
    printf '%s\t%s\n' "$n" "$((prec + 1))" >> "${STATE_FILE}.tmp"
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
}

# Sceglie il motore del giro, ruotando fra quelli effettivamente installati.
# Se nessuno lo e', il giro NON viene eseguito: non esiste un ripiego su `claude`.
# Un ripiego silenzioso riporterebbe il lavoro esattamente dove non deve stare,
# e nel log sembrerebbe tutto normale.
# Imposta le globali MOTORE e N_DISPONIBILI. Non usa la sostituzione di comando
# perche' girerebbe in una subshell e le globali non tornerebbero indietro.
_panchina_file() { echo "$LOG_DIR/engine_blocked_$1"; }

# Un motore e' in panchina finche' il file contiene un'epoca futura. Il rientro e'
# automatico: nessun comando da ricordare, che sarebbe il modo piu' facile di
# lasciare un motore spento per giorni senza accorgersene.
motore_in_panchina() {
    local f; f=$(_panchina_file "$1")
    [[ -f "$f" ]] || return 1
    local fino; fino=$(cat "$f" 2>/dev/null)
    [[ "$fino" =~ ^[0-9]+$ ]] || { rm -f "$f"; return 1; }
    if (( fino <= $(date +%s) )); then
        rm -f "$f"
        log "Motore $1: panchina scaduta, rientra in rotazione."
        return 1
    fi
    return 0
}

metti_in_panchina() {
    local m="$1" fino=$(( $(date +%s) + RATE_LIMIT_COOLDOWN ))
    echo "$fino" > "$(_panchina_file "$m")"
    log "Motore $m: rate limit — in panchina fino a $(date -d "@$fino" '+%H:%M')."
}

motore_installato() {
    case "$1" in
        codex|gemini|opencode) command -v "$1" >/dev/null 2>&1 ;;
        glm52|minimax)        command -v ollama >/dev/null 2>&1 ;;
        *)                    return 1 ;;
    esac
}

scegli_motore() {
    local indice disponibili=() in_panchina=()
    for m in "${MOTORI[@]}"; do
        if ! motore_installato "$m"; then
            # Rumoroso di proposito: un motore configurato che sparisce dal PATH
            # riduce la rotazione a uno solo, ed e' invisibile nel log del giro.
            log "ATTENZIONE: motore $m configurato ma non trovato nel PATH — escluso dalla rotazione."
            continue
        fi
        if motore_in_panchina "$m"; then in_panchina+=("$m"); else disponibili+=("$m"); fi
    done
    if (( ${#disponibili[@]} == 0 )); then
        if (( ${#in_panchina[@]} > 0 )); then
            log "Tutti i motori sono in panchina per rate limit: [${in_panchina[*]}] — giro rimandato."
            tg_send "⏸ <b>Roadmap</b> — tutti i motori in rate limit ([${in_panchina[*]}]). Il giro riparte da solo alla scadenza."
            log_evento "engine_select" "result=all_rate_limited" "engines=${in_panchina[*]}"
            exit 0
        fi
        log "Nessun motore fra [${MOTORI[*]}] e' installato — giro annullato."
        tg_send "⛔ <b>Roadmap</b> — nessun motore disponibile fra [${MOTORI[*]}]. Nessun giro eseguito."
        log_evento "engine_select" "result=none_installed"
        exit 1
    fi
    MOTORI_DISPONIBILI=("${disponibili[@]}")
    indice=$(cat "$MOTORE_STATE" 2>/dev/null || echo 0)
    [[ "$indice" =~ ^[0-9]+$ ]] || indice=0
    # La rotazione NON avanza qui: avanzarla adesso la farebbe avanzare anche in
    # --dry-run, che promette di non toccare lo stato.
    N_DISPONIBILI=${#disponibili[@]}
    MOTORE="${disponibili[$(( indice % N_DISPONIBILI ))]}"
}

avanza_rotazione() {
    local indice
    indice=$(cat "$MOTORE_STATE" 2>/dev/null || echo 0)
    [[ "$indice" =~ ^[0-9]+$ ]] || indice=0
    echo $(( (indice + 1) % N_DISPONIBILI )) > "$MOTORE_STATE"
}

# Ogni CLI ha la sua sintassi non interattiva e i suoi default di approvazione.
# Il worktree e' isolato, ma il sandbox resta ristretto alla directory di lavoro:
# l'accesso di rete serve solo perche' `gh` deve poter aprire la PR.
esegui_agente() {
    local motore="$1" prompt="$2" wt="$3"
    case "$motore" in
        codex)
            # `exec` non chiede approvazioni per costruzione. Il sandbox resta
            # workspace-write: l'accesso di rete e' abilitato solo perche' `gh`
            # deve poter aprire la PR, non per dare mano libera.
            (cd "$wt" && timeout "$TIMEOUT_SESSIONE" codex exec \
                -s workspace-write \
                -c sandbox_workspace_write.network_access=true \
                "$prompt" </dev/null 2>&1)
            ;;
        glm52|minimax)
            # Claude Code con un modello diverso sotto. Gli argomenti dopo
            # l'integrazione sono passati a claude cosi' come sono.
            local _mod
            [[ "$motore" == glm52 ]] && _mod="glm-5.2:cloud" || _mod="minimax-m3:cloud"
            # Il `--` non e' opzionale: senza, `ollama launch` intercetta gli
            # argomenti di claude e muore con "unknown flag". Verificato il
            # 2026-08-07, insieme al fatto che il modello che risponde e' davvero
            # quello richiesto e non un ripiego su Claude.
            (cd "$wt" && timeout "$TIMEOUT_SESSIONE" ollama launch claude --model "$_mod" -- \
                -p "$prompt" --allowedTools "Bash,Read,Write,Edit,Glob,Grep" </dev/null 2>&1)
            ;;
        gemini)
            (cd "$wt" && timeout "$TIMEOUT_SESSIONE" gemini --yolo -p "$prompt" 2>&1)
            ;;
        opencode)
            (cd "$wt" && timeout "$TIMEOUT_SESSIONE" opencode run "$prompt" 2>&1)
            ;;
        *)
            echo "Motore non riconosciuto: $motore"; return 2
            ;;
    esac
}

# Il recensore gira con gli strumenti di scrittura tolti. Il prompt gli dice di
# non modificare nulla, ma un divieto scritto e un permesso negato non sono la
# stessa cosa: il secondo regge anche se il modello non legge le istruzioni.
esegui_revisore() {
    local motore="$1" prompt="$2" wt="$3"
    case "$motore" in
        codex)
            (cd "$wt" && timeout "$TIMEOUT_REVIEW" codex exec \
                -s read-only -c sandbox_workspace_write.network_access=true \
                "$prompt" </dev/null 2>&1)
            ;;
        glm52|minimax)
            local _mod
            [[ "$motore" == glm52 ]] && _mod="glm-5.2:cloud" || _mod="minimax-m3:cloud"
            (cd "$wt" && timeout "$TIMEOUT_REVIEW" ollama launch claude --model "$_mod" -- \
                -p "$prompt" --allowedTools "Bash,Read,Glob,Grep" </dev/null 2>&1)
            ;;
        *)  echo "Recensore non riconosciuto: $motore"; return 2 ;;
    esac
}

# --- review e cancelli di merge -------------------------------------------------
# La CI di questo repo e' rossa in modo cronico per motivi ambientali (integration
# test senza DB/auth). Presa com'e' non dice nulla. Ma la DIFFERENZA fra i test
# falliti nella PR e quelli falliti su main dice tutto: e' il controllo fatto a
# mano il 2026-08-07, qui meccanizzato.
CI_ATTESA_MAX=1200      # 20 min: oltre, la CI non e' lenta, e' ferma
TIMEOUT_REVIEW=1800     # 30 min per la review

_falliti_di_run() { gh run view "$1" --log-failed 2>/dev/null | grep -oE "FAILED [^ ]+" | sort -u; }

_run_completato() {  # $1 = branch, $2 = sha atteso (opzionale)
    # Con lo sha, accetta solo il run di QUEL commit. Senza, un run concluso di un
    # push precedente verrebbe scambiato per l'esito della revisione in corso, e
    # il cancello approverebbe guardando la CI sbagliata.
    if [[ -n "${2:-}" ]]; then
        gh run list --branch "$1" --workflow CI --status completed --limit 10 \
            --json databaseId,headSha -q "[.[]|select(.headSha==\"$2\")][0].databaseId" 2>/dev/null
    else
        gh run list --branch "$1" --workflow CI --status completed --limit 1 \
            --json databaseId -q '.[0].databaseId' 2>/dev/null
    fi
}

attendi_ci() {  # $1 = branch. Esito: id del run per la testa del branch.
    local branch="$1" scaduta=$(( $(date +%s) + CI_ATTESA_MAX )) rid="" sha
    sha=$(git rev-parse "origin/$branch" 2>/dev/null || git rev-parse "$branch" 2>/dev/null)
    while (( $(date +%s) < scaduta )); do
        rid=$(_run_completato "$branch" "$sha")
        [[ -n "$rid" && "$rid" != "null" ]] && { echo "$rid"; return 0; }
        sleep 30
    done
    return 1
}

conta_regressioni() {  # $1 = run della PR. Esito: numero di test rotti NUOVI.
    local rid_pr="$1" rid_main
    rid_main=$(_run_completato main)
    [[ -z "$rid_main" || "$rid_main" == "null" ]] && { echo "-1"; return; }
    comm -13 <(_falliti_di_run "$rid_main") <(_falliti_di_run "$rid_pr") | grep -c . || true
}

# Il recensore non e' mai il modello che ha scritto la PR: e' l'argomento della
# rotazione applicato alla review. Se resta un solo motore disponibile, la review
# NON si fa — meglio nessuna review che un modello che si rilegge da solo.
scegli_recensore() {
    local implementatore="$1" c
    for c in "${MOTORI_DISPONIBILI[@]}"; do
        [[ "$c" != "$implementatore" ]] && { echo "$c"; return 0; }
    done
    return 1
}

# Review + cancelli, isolati in una funzione perche' servono in due punti: dentro
# il giro, e in --rivedi per recuperare una PR rimasta senza verdetto. Senza il
# secondo, una PR bloccata blocca la sua issue per sempre: il giro la salta
# proprio perche' ha gia' una PR aperta.
rivedi_e_mergia() {
    local _PR="$1" _ISSUE="$2" _BRANCH="$3" _WT="$4" _IMPL="$5" _TIT="$6" _URL="$7"
    local REGRESSIONI VERDETTO REVISORE RID REV_OUT REV_PROMPT _REV_TEMPLATE _REV_FILE
    tg_send "🔍 <b>Roadmap — PR aperta, review in corso</b>
Issue #${_ISSUE}: ${_TIT}
Implementata da: ${_IMPL}
${_URL}"

    # ── cancello 1: nessun test rotto NUOVO rispetto a main ────────────────────
    REGRESSIONI=-1
    if RID=$(attendi_ci "$_BRANCH"); then
        REGRESSIONI=$(conta_regressioni "$RID")
        log "#$_ISSUE — CI conclusa (run $RID): $REGRESSIONI test rotti in piu' rispetto a main"
    else
        log "#$_ISSUE — CI non conclusa entro ${CI_ATTESA_MAX}s: il cancello non e' calcolabile."
    fi

    # ── cancello 2: review di un modello diverso dall'implementatore ───────────
    VERDETTO="NON_ESEGUITA"; REVISORE=""
    if REVISORE=$(scegli_recensore "$_IMPL"); then
        log "#$_ISSUE — review affidata a $REVISORE"
        # Prompt costruito con heredoc QUOTATO + segnaposto, come fa gia' il cron
        # alpha-miss. Non e' stile: in una stringa fra virgolette i backtick del
        # testo aprono una sostituzione di comando, bash esegue davvero i `gh` che
        # stiamo solo CITANDO, e con set -e l'assegnazione fallita uccide lo
        # script. E' successo: tre review morte qui senza lasciare un verdetto.
        _REV_TEMPLATE=$(cat <<'REVEOF'
Rivedi la pull request #__PR_NUM__ di questo repository, che chiude o riguarda la issue #__ISSUE__.

Sei nel worktree __WT__, sul branch __BRANCH__. NON scrivere e NON modificare nulla: la tua uscita
e' un giudizio, non una correzione. Non mergiare, non chiudere, non commentare via gh.

Contesto che devi leggere prima di giudicare:
- CLAUDE.md, per le convenzioni del progetto
- `gh issue view __ISSUE__ --comments` — se un commento dell'operatore restringe il perimetro,
  quella decisione vince sul testo originale della issue
- docs/evidence/OBSERVATION_CHARTER.md — dal 2026-08-03 al 2026-09-28 ogni TARATURA e' congelata
  (soglie, pesi, flag, cooldown, parametri di strategia). Sono ammessi solo correttezza,
  strumentazione e misura.
- `gh pr diff __PR_NUM__` — il diff completo

Dato oggettivo gia' calcolato, non ricalcolarlo: rispetto a main la CI di questa PR ha
__REGRESSIONI__ test rotti in piu' (-1 significa "non calcolabile").

Giudica in questo ordine, e fermati al primo che fallisce:
1. La PR fa cio' che la issue chiede? Se ha ristretto il perimetro, lo ha DICHIARATO nel corpo?
   Una restrizione dichiarata e motivata e' accettabile; una silenziosa no.
2. Viola il freeze? Cerca soglie, pesi, flag e parametri di strategia modificati. Un valore in
   config/trading.yaml o in un default di codice che cambia il comportamento di trading e' una
   violazione, anche se il resto della PR e' corretto.
3. I test aggiunti verificano davvero la correzione, o passerebbero anche senza? Un test che
   passa anche sul codice pre-fix non sta testando niente.
4. Ci sono difetti di correttezza nel diff: divisioni per zero, ordinamenti sbagliati, errori
   off-by-one, gestione mancante del caso vuoto o del fallimento di rete?

Sii concreto: cita file e riga. Se non trovi problemi dillo in una riga, senza inventarne per
sembrare accurato.

Chiudi la risposta con UNA SOLA di queste due righe, esattamente come scritta, in ultima posizione:
VERDETTO: APPROVA
VERDETTO: RESPINGI
REVEOF
)
        REV_PROMPT="${_REV_TEMPLATE//__PR_NUM__/$_PR}"
        REV_PROMPT="${REV_PROMPT//__ISSUE__/$_ISSUE}"
        REV_PROMPT="${REV_PROMPT//__WT__/$_WT}"
        REV_PROMPT="${REV_PROMPT//__BRANCH__/$_BRANCH}"
        REV_PROMPT="${REV_PROMPT//__REGRESSIONI__/$REGRESSIONI}"

        set +e
        REV_OUT=$(esegui_revisore "$REVISORE" "$REV_PROMPT" "$_WT")
        set -e
        VERDETTO=$(printf '%s\n' "$REV_OUT" | estrai_verdetto)
        if [[ "$VERDETTO" == "RATE_LIMIT" ]]; then
            metti_in_panchina "$REVISORE"; VERDETTO="NON_ESEGUITA"
            log "#$_ISSUE — recensore $REVISORE in rate limit: review saltata."
        fi
        # NON_ESEGUITA da rate limit e NON_ESEGUITA da sessione morta sono due cose
        # diverse e vanno distinte nel log: la prima si recupera aspettando, la
        # seconda no.
        log "#$_ISSUE — verdetto di $REVISORE: $VERDETTO"
        # Il giudizio si conserva su disco PRIMA di provare a pubblicarlo, e non si
        # cancella. Finiva in un file temporaneo rimosso subito, con l'unica via di
        # pubblicazione silenziata: un errore transitorio dell'API GitHub — che qui
        # capita, `error connecting to api.github.com` si legge nelle trascrizioni —
        # bastava a perdere per sempre la motivazione di un verdetto. E' successo su
        # PR #207 il 2026-08-09: RESPINGI registrato, ragioni irrecuperabili.
        _REV_FILE="$LOG_DIR/review_${_PR}_$(date +%Y-%m-%d).md"
        printf '## Review automatica — %s\n\nTest rotti in piu%s rispetto a main: **%s**\n\nVerdetto letto: **%s**\n\n---\n\n%s\n' \
            "$REVISORE" "'" "$REGRESSIONI" "$VERDETTO" "$REV_OUT" > "$_REV_FILE"
        # GitHub rifiuta i commenti oltre ~65k caratteri, e la trascrizione di un
        # recensore che stampa il diff li supera senza sforzo (319k su #237). Il
        # risultato era che le review PIU' approfondite erano proprio quelle che
        # non venivano mai pubblicate. Si pubblica la coda — dove sta il giudizio,
        # perche' il verdetto e' l'ultima riga — e il resto resta su disco.
        _REV_BODY="$LOG_DIR/.rev_body_$_PR.md"
        {
            printf '## Review automatica — %s\n\nTest rotti in piu%s rispetto a main: **%s**\n\nVerdetto letto: **%s**\n\n---\n\n' \
                "$REVISORE" "'" "$REGRESSIONI" "$VERDETTO"
            if (( $(wc -c < "$_REV_FILE") > 50000 )); then
                printf '_Trascrizione completa in `%s` (%s caratteri). Qui la parte conclusiva._\n\n' \
                    "${_REV_FILE#"$PROJECT_DIR/"}" "$(wc -c < "$_REV_FILE")"
                tail -c 40000 "$_REV_FILE"
            else
                cat "$_REV_FILE"
            fi
        } > "$_REV_BODY"
        if ! gh pr comment "$_PR" --body-file "$_REV_BODY" >/dev/null 2>&1; then
            log "#$_ISSUE — commento di review NON pubblicato su GitHub: resta in $_REV_FILE"
        fi
        rm -f "$_REV_BODY"
    else
        log "#$_ISSUE — nessun motore diverso dall'implementatore disponibile: review non eseguita."
    fi

    # ── merge solo se ENTRAMBI i cancelli sono passati ─────────────────────────
    if [[ "$VERDETTO" == "APPROVA" && "$REGRESSIONI" == "0" ]]; then
        # Non ci si fida del codice di uscita di `gh pr merge`: esce non-zero anche
        # quando il merge E' avvenuto e a fallire e' solo la cancellazione del
        # branch. E' successo su #206: merge riuscito, esito "rifiutato", deploy
        # mai lanciato. L'esito lo determina lo STATO della PR.
        gh pr merge "$_PR" --merge >/dev/null 2>&1 || true
        sleep 3
        if [[ "$(gh pr view "$_PR" --json state -q .state 2>/dev/null)" == "MERGED" ]]; then
            # La cancellazione del branch e' cosmetica: non deve mai decidere l'esito.
            gh api -X DELETE "repos/{owner}/{repo}/git/refs/heads/$_BRANCH" >/dev/null 2>&1 || true
            log "#$_ISSUE — PR #$_PR mergiata (0 regressioni, $REVISORE approva)."
            tg_send "🟢 <b>Roadmap — PR mergiata da sola</b>
Issue #${_ISSUE}: ${_TIT}
${_IMPL} ha implementato, ${REVISORE} ha approvato, 0 test rotti in piu&#39;.
${_URL}

<i>Riconciliazione del deploy avviata: rimandata da sola se il mercato e&#39; aperto.</i>"
            log_evento "review" "result=merged" "engine=$REVISORE" "impl=$_IMPL" \
                "issue=#$_ISSUE" "pr=#$_PR" "regressions=#$REGRESSIONI" "verdetto=$VERDETTO"
            # Il riconciliatore decide da solo se e quando: se il mercato e' aperto
            # rimanda, e il cron ripassa. Qui serve solo a non aspettare il cron
            # quando la finestra e' gia' libera.
            "$SCRIPT_DIR/deploy_reconcile.sh" >/dev/null 2>&1 || \
                log "#$_ISSUE — riconciliazione del deploy non riuscita: se ne occupa il cron."
        else
            log "#$_ISSUE — merge rifiutato da GitHub (conflitto o protezione)."
            tg_send "⚠️ <b>Roadmap</b> — #${_PR} approvata ma il merge e&#39; stato rifiutato da GitHub. Serve una mano.
${_URL}"
            log_evento "review" "result=merge_rejected" "engine=${REVISORE:-none}" "impl=$_IMPL" \
                "issue=#$_ISSUE" "pr=#$_PR" "regressions=#$REGRESSIONI" "verdetto=$VERDETTO"
        fi
    else
        [[ "$VERDETTO" == "RESPINGI" ]] && registra_respinta "$_ISSUE"
        _n=$(respinte_di "$_ISSUE"); _n=${_n:-0}
        log "#$_ISSUE — NON mergiata (verdetto=$VERDETTO, regressioni=$REGRESSIONI, respinte=$_n)."
        if [[ "$VERDETTO" == "RESPINGI" ]] && (( _n >= MAX_RESPINTE )); then
            tg_send "🛑 <b>Roadmap — #${_ISSUE} esce dalla rotazione</b>
Respinta ${_n} volte da modelli diversi. Quando due modelli distinti non ci riescono il problema non e&#39; l&#39;esecuzione ma la specifica: serve una tua decisione, non un altro giro.
${_URL}"
        fi
        tg_send "🟡 <b>Roadmap — PR da guardare</b>
Issue #${_ISSUE}: ${_TIT}
Implementata da ${_IMPL}${REVISORE:+, rivista da $REVISORE}
Verdetto: <b>${VERDETTO}</b> · test rotti in piu&#39; rispetto a main: <b>${REGRESSIONI}</b>
${_URL}"
        log_evento "review" "result=not_merged" "engine=${REVISORE:-none}" "impl=$_IMPL" \
            "issue=#$_ISSUE" "pr=#$_PR" "regressions=#$REGRESSIONI" "verdetto=$VERDETTO" "respinte=#$_n"
    fi
}

# --- comandi operatore ----------------------------------------------------------
if [[ "${1:-}" == "--rivedi" ]]; then
    # Recupera una PR rimasta senza verdetto (review fallita, timeout, rate limit).
    # Ricostruisce il minimo indispensabile e applica gli stessi due cancelli.
    _pr="${2:?uso: --rivedi <numero PR>}"
    scegli_motore
    _b=$(gh pr view "$_pr" --json headRefName -q .headRefName)
    _t=$(gh pr view "$_pr" --json title -q .title)
    _u=$(gh pr view "$_pr" --json url -q .url)
    _i=$(issue_del_branch "$_b")
    [[ -z "$_i" ]] && { echo "Non ricavo il numero di issue dal branch '$_b'."; exit 1; }
    # L'implementatore va escluso dalla review: se non e' ricavabile dal log, si
    # assume il motore di turno, che e' l'ipotesi prudente (al massimo cambia
    # recensore, mai lo fa coincidere con chi ha scritto).
    _impl=$(grep -hoE "PR aperta da [a-z0-9]+: .*/${_pr}$" "$LOG_DIR"/roadmap_agent_*.log 2>/dev/null \
            | tail -1 | awk '{print $4}' | tr -d ':')
    _impl="${_impl:-$MOTORE}"
    _wt="$PROJECT_DIR/.worktrees/rivedi-$_pr"
    git fetch -q origin "$_b"
    git worktree remove --force "$_wt" 2>/dev/null || true
    git worktree add -q --detach "$_wt" "origin/$_b"
    log "--rivedi #$_pr (issue #$_i, branch $_b, implementata da $_impl)"
    rivedi_e_mergia "$_pr" "$_i" "$_b" "$_wt" "$_impl" "$_t" "$_u"
    git worktree remove --force "$_wt" 2>/dev/null || true
    exit 0
fi

if [[ "${1:-}" == "--motori" ]]; then
    printf '%-10s %-14s %s\n' MOTORE STATO NOTE
    for m in "${MOTORI[@]}"; do
        if ! motore_installato "$m"; then
            printf '%-10s %-14s %s\n' "$m" "non-installato" "-"
        elif motore_in_panchina "$m"; then
            fino=$(cat "$(_panchina_file "$m")")
            printf '%-10s %-14s rientra alle %s\n' "$m" "rate-limit" "$(date -d "@$fino" '+%H:%M')"
        else
            printf '%-10s %-14s %s\n' "$m" "disponibile" "-"
        fi
    done
    exit 0
fi
if [[ "${1:-}" == "--sblocca" ]]; then
    # Scorciatoia per quando la quota rientra prima della scadenza stimata. Non
    # serve mai per correttezza: la panchina scade comunque da sola.
    if [[ -n "${2:-}" ]]; then rm -f "$(_panchina_file "$2")"; echo "Motore $2 rimesso in rotazione."
    else rm -f "$LOG_DIR"/engine_blocked_*; echo "Tutti i motori rimessi in rotazione."; fi
    exit 0
fi

if [[ "${1:-}" == "--prova" ]]; then
    # Verifica che il motore risponda e che gli argomenti arrivino davvero fino a
    # lui. Serve soprattutto per glm52/minimax, dove il prompt passa attraverso
    # `ollama launch` prima di raggiungere claude.
    _m="${2:?uso: --prova <motore>}"
    motore_installato "$_m" || { echo "Motore $_m non installato."; exit 1; }
    _tmp=$(mktemp -d); echo "Provo $_m (60s)..."
    set +e
    _out=$(TIMEOUT_SESSIONE=60 esegui_agente "$_m" "Rispondi solo con la parola PRONTO, senza usare strumenti." "$_tmp")
    _rc=$?
    set -e
    rmdir "$_tmp" 2>/dev/null || true
    echo "--- uscita (codice $_rc) ---"; echo "$_out" | tail -5
    if echo "$_out" | grep -qiE "$_RATE_LIMIT_RE"; then echo ">>> $_m e' in RATE LIMIT."
    elif echo "$_out" | grep -qi "PRONTO"; then echo ">>> $_m risponde: OK."
    else echo ">>> $_m non ha risposto come atteso — controlla l'invocazione."; fi
    exit 0
fi

log "=== Giro roadmap ==="
scegli_motore
log "Motore del giro: $MOTORE (disponibili: [${MOTORI_DISPONIBILI[*]}] su [${MOTORI[*]}])"
git fetch --quiet origin main

# --- selezione della issue: primo elemento della coda che sia lavorabile --------
PR_APERTE=$(gh pr list --state open --json headRefName -q '.[].headRefName' 2>/dev/null || echo "")
ISSUE=""
while read -r numero _resto; do
    [[ -z "$numero" || "$numero" == \#* ]] && continue

    stato_labels=$(gh issue view "$numero" --json state,labels \
        -q '"\(.state) \(.labels|map(.name)|join(","))"' 2>/dev/null || echo "")
    if [[ -z "$stato_labels" ]]; then
        log "  #$numero — non leggibile da GitHub, salto."; continue
    fi
    if [[ "$stato_labels" != OPEN* ]]; then
        log "  #$numero — gia' chiusa, salto."; continue
    fi
    if [[ "$stato_labels" != *freeze-ok* ]]; then
        # In coda ma senza permesso: e' il secondo lucchetto che tiene.
        log "  #$numero — in coda ma SENZA label freeze-ok: salto e segnalo."; continue
    fi
    if echo "$PR_APERTE" | grep -qx "agent/issue-${numero}"; then
        # Una PR RESPINTA non deve bloccare la sua issue: senza questo ramo ogni
        # bocciatura la congelava per sempre, perche' il giro salta cio' che ha
        # una PR aperta. Si riprende lo stesso branch, con la review addosso.
        _v=$(verdetto_pr_di "$numero")
        _r=$(respinte_di "$numero"); _r=${_r:-0}
        if [[ "$_v" != "RESPINGI" ]]; then
            log "  #$numero — PR aperta in attesa di verdetto o gia' approvata, salto."; continue
        fi
        if (( _r >= MAX_RESPINTE )); then
            # Se due modelli diversi non ci riescono, il problema non e'
            # l'esecuzione: e' la specifica, e non la risolve un terzo giro.
            log "  #$numero — $_r review respinte, esce dalla rotazione: serve l'operatore."; continue
        fi
        RIPRESA=1
        log "  #$numero — PR respinta ($_r volte): la riprendo sullo stesso branch."
    fi
    t=$(tentativi_di "$numero"); t=${t:-0}
    if (( t >= MAX_TENTATIVI )); then
        log "  #$numero — $t tentativi falliti, fuori rotazione."; continue
    fi
    ISSUE="$numero"; break
done < "$QUEUE_FILE"

if [[ -z "$ISSUE" ]]; then
    log "Nessuna issue lavorabile in coda. Niente da fare."
    tg_send "🧭 <b>Roadmap</b> — coda vuota o tutta in attesa di review. Nessun giro eseguito."
    log_evento "queue" "result=empty" "engine=$MOTORE"
    exit 0
fi

TITOLO=$(gh issue view "$ISSUE" --json title -q .title)
log "Issue selezionata: #$ISSUE — $TITOLO"

# --dry-run: verifica la selezione senza consumare una sessione ne' toccare lo
# stato. Serve dopo ogni modifica alla coda o alle label.
if [[ "${1:-}" == "--dry-run" ]]; then
    log "(dry-run) motore che sarebbe usato: $MOTORE"
    log "(dry-run) mi fermo qui: nessun worktree, nessuna sessione, stato invariato."
    exit 0
fi

registra_tentativo "$ISSUE"
avanza_rotazione

# --- worktree isolato ----------------------------------------------------------
# Mai nell'albero principale: li' girano i cron dell'osservazione e vive il
# ledger delle evidenze. Un agente che sbaglia non deve poterli toccare.
BRANCH="agent/issue-${ISSUE}"
WT="$PROJECT_DIR/.worktrees/agent-${ISSUE}"

git worktree remove --force "$WT" 2>/dev/null || true
git worktree prune; rm -rf "$WT" 2>/dev/null || true
if (( RIPRESA )); then
    # Sul branch esistente: il lavoro gia' fatto e giudicato non si butta.
    git fetch -q origin "$BRANCH"
    git branch -D "$BRANCH" 2>/dev/null || true
    git worktree add -q "$WT" -b "$BRANCH" "origin/$BRANCH" >>"$LOG_FILE" 2>&1
else
    git branch -D "$BRANCH" 2>/dev/null || true
    git worktree add -b "$BRANCH" "$WT" origin/main >>"$LOG_FILE" 2>&1
fi

tg_send "🧭 <b>Roadmap — giro avviato</b>
Issue #${ISSUE}: ${TITOLO}
Motore: ${MOTORE}"

# Su una ripresa, la review che ha bocciato entra nel prompt: ripartire senza
# leggerla significherebbe rifare lo stesso errore con un modello diverso.
CODA_REVIEW=""
if (( RIPRESA )); then
    _pr_rip=$(gh pr list --state open --head "$BRANCH" --json number -q '.[0].number' 2>/dev/null)
    if [[ -n "$_pr_rip" ]]; then
        CODA_REVIEW=$(gh pr view "$_pr_rip" --json comments -q '.comments[-1].body' 2>/dev/null | tail -c 6000)
    fi
fi

PROMPT=$(cat <<PROMPTEOF
Lavora la issue GitHub #${ISSUE} di questo repository (Alembic) fino ad aprire una pull request.

${CODA_REVIEW:+ATTENZIONE — questa e' una RIPRESA. Esiste gia' una PR aperta su questo branch, con il
lavoro precedente, ed e' stata RESPINTA da una review. Non ricominciare da zero: correggi cio' che la
review contesta, sullo stesso branch. Se ritieni che un rilievo sia sbagliato, dillo nel corpo della
PR con l'argomento, non ignorandolo. Questa e' la review da cui partire:

--- inizio review precedente ---
${CODA_REVIEW}
--- fine review precedente ---
}

Sei in un worktree dedicato: $WT, sul branch $BRANCH, basato su origin/main.
Leggi CLAUDE.md prima di tutto: e' il file di istruzioni di questo progetto, valido
qualunque sia lo strumento con cui stai girando.

## Il vincolo che conta piu' di ogni altro

Dal 2026-08-03 al 2026-09-28 e' in corso un periodo di sola osservazione (issue #171),
regolato da docs/evidence/OBSERVATION_CHARTER.md. **Ogni taratura e' congelata**: soglie,
pesi, flag, cooldown, parametri di strategia. Sono ammessi solo difetti di correttezza,
strumentazione e misura.

Questa issue e' gia' stata giudicata compatibile — non devi rivalutarlo. Ma il perimetro
del TUO intervento si': se per chiudere la issue ti accorgi che servirebbe cambiare un
parametro di taratura, **non farlo**. Implementa la parte compatibile, e scrivi nella PR
cosa hai lasciato fuori e perche'.

Ti e' vietato modificare: scripts/roadmap_queue.txt, le label delle issue,
docs/evidence/OBSERVATION_CHARTER.md, docs/evidence/findings.json,
docs/evidence/market_daily.jsonl. Se pensi che uno di questi vada cambiato, scrivilo
nella PR e fermati — e' una decisione dell'operatore.

Leggi i commenti della issue: se contengono una decisione dell'operatore che ne restringe
il perimetro, quella decisione vince sul testo originale della issue.

## Come lavorare

1. Leggi la issue per intero: \`gh issue view ${ISSUE} --comments\`
2. Verifica le sue affermazioni contro il codice reale prima di fidartene. Le issue di
   questo repo sono scritte con cura ma possono essere invecchiate: se la premessa non
   regge piu', dillo nella PR invece di implementare una correzione a un problema che
   non esiste.
3. TDD: prima un test che fallisce per la ragione giusta, poi il codice minimo che lo fa
   passare. Un test che passa gia' prima della modifica non sta testando la correzione.
4. Segui le convenzioni del codice che tocchi: densita' di commenti, nomi, idiomi.
5. Commit frequenti e piccoli, messaggi in italiano come il resto del repo.
6. Esegui i test che riguardano cio' che hai toccato. **Non** lanciare l'intera suite: in
   CI e' cronicamente rossa per motivi ambientali (integration test senza DB), e il
   rumore ti farebbe perdere il segnale.

## Come finire

Apri una PR verso main con \`gh pr create\`, con nel corpo:
- cosa hai cambiato e perche', in prosa, non un elenco di file
- **come si verifica** che funziona: il comando esatto e cosa ci si aspetta di vedere
- cosa hai lasciato fuori perche' ricade nel freeze, se applicabile
- la riga \`Closes #${ISSUE}\` solo se la PR chiude davvero la issue per intero;
  altrimenti \`Part of #${ISSUE}\` e di' cosa resta

**Non mergiare la PR.** Il merge e' dell'operatore.

## Se non e' lavorabile

Se dopo aver letto il codice concludi che la issue non e' lavorabile — premessa
sbagliata, perimetro ambiguo, oppure ogni strada passa da una taratura congelata — **non
inventare una PR di ripiego**. Commenta la issue spiegando cosa hai trovato e cosa serve
per sbloccarla, non aprire PR, e termina dicendo chiaramente NESSUNA PR e la ragione.
Un no-op onesto vale piu' di una PR che sembra lavoro.
PROMPTEOF
)

# Prova i motori disponibili partendo da quello di turno. Un rate limit non
# consuma il giro: si passa al successivo. E non viene addebitato alla issue —
# altrimenti due esaurimenti di quota basterebbero a buttarla fuori rotazione
# senza che nessuno l'abbia mai davvero guardata.
_ordine=()
_start=$(cat "$MOTORE_STATE" 2>/dev/null || echo 0); [[ "$_start" =~ ^[0-9]+$ ]] || _start=0
for _k in $(seq 0 $(( N_DISPONIBILI - 1 ))); do
    _ordine+=("${MOTORI_DISPONIBILI[$(( (_start + _k) % N_DISPONIBILI ))]}")
done

OUTPUT=""; ESITO=0; RATE_LIMITED_TUTTI=1
_T0=$(date +%s)
for _m in "${_ordine[@]}"; do
    MOTORE="$_m"
    log "#$ISSUE — provo con $MOTORE"
    set +e
    OUTPUT=$(esegui_agente "$MOTORE" "$PROMPT" "$WT")
    ESITO=$?
    set -e
    if echo "$OUTPUT" | grep -qiE "$_RATE_LIMIT_RE"; then
        metti_in_panchina "$MOTORE"
        tg_send "⏸ <b>Roadmap</b> — $MOTORE in rate limit, in panchina 3h. Provo il motore successivo."
        continue
    fi
    RATE_LIMITED_TUTTI=0
    break
done

if (( RATE_LIMITED_TUTTI == 1 )); then
    # Nessun motore ha potuto lavorare: la issue torna com'era, tentativi compresi.
    grep -v -P "^${ISSUE}\t" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
    log "#$ISSUE — tutti i motori in rate limit: tentativo NON addebitato, giro rimandato."
    tg_send "⏸ <b>Roadmap</b> — tutti i motori in rate limit. #${ISSUE} resta in cima alla coda, nessun tentativo consumato."
    log_evento "work" "result=all_rate_limited" "issue=#$ISSUE"
    git worktree remove --force "$WT" 2>/dev/null || true
    git branch -D "$BRANCH" 2>/dev/null || true
    exit 0
fi

echo "$OUTPUT" >> "$LOG_FILE"
_DURATA=$(( $(date +%s) - _T0 ))

if (( ESITO == 124 )); then
    log "#$ISSUE — sessione uccisa dal timeout dopo ${TIMEOUT_SESSIONE}s."
elif (( ESITO != 0 )); then
    log "#$ISSUE — sessione terminata con codice $ESITO."
fi

# --- esito reale: la PR esiste o no. Non ci si fida del racconto della sessione.
PR_NUM=$(trova_pr_del_giro "$ISSUE")
PR_URL=""
if [[ -n "$PR_NUM" ]]; then
    PR_URL=$(gh pr view "$PR_NUM" --json url -q .url 2>/dev/null || echo "")
    # Il branch effettivo puo' non essere quello creato dal loop: gli agenti
    # pubblicano anche su branch derivati. Review e merge devono lavorare su
    # quello vero, non su quello atteso (#221).
    BRANCH_PR=$(gh pr view "$PR_NUM" --json headRefName -q .headRefName 2>/dev/null || echo "$BRANCH")
    [[ "$BRANCH_PR" != "$BRANCH" ]] && \
        log "#$ISSUE — PR su branch derivato '$BRANCH_PR' (il giro aveva creato '$BRANCH')."
fi

if [[ -n "$PR_URL" ]]; then
    log "#$ISSUE — PR aperta da $MOTORE: $PR_URL"
    # Tentativo riuscito: lo tolgo dal conteggio dei fallimenti.
    grep -v -P "^${ISSUE}\t" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
    log_evento "work" "result=pr_opened" "engine=$MOTORE" "issue=#$ISSUE" "pr=#$PR_NUM" "duration_s=#$_DURATA"
    rivedi_e_mergia "$PR_NUM" "$ISSUE" "$BRANCH_PR" "$WT" "$MOTORE" "$TITOLO" "$PR_URL"
else
    log "#$ISSUE — nessuna PR aperta."
    CODA=$(echo "$OUTPUT" | tail -c 1200)
    tg_send "⚠️ <b>Roadmap — nessuna PR</b>
Issue #${ISSUE}: ${TITOLO}
Motore: ${MOTORE} — esito sessione: ${ESITO}

<pre>$(echo "$CODA" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</pre>"
    log_evento "work" "result=no_pr" "engine=$MOTORE" "issue=#$ISSUE" "esito=#$ESITO" "duration_s=#$_DURATA"
    # Il branch senza commit non serve a nessuno; se ha commit lo tengo per l'ispezione.
    if [[ -z "$(git log --oneline origin/main.."$BRANCH" 2>/dev/null)" ]]; then
        git worktree remove --force "$WT" 2>/dev/null || true
        git branch -D "$BRANCH" 2>/dev/null || true
        log "#$ISSUE — nessun commit prodotto: worktree e branch rimossi."
        exit 0
    fi
    # Commit senza PR: non e' un giro a vuoto, e il log non deve farlo sembrare
    # tale. Sono due situazioni diverse e vanno distinte a colpo d'occhio (#221).
    log "#$ISSUE — ATTENZIONE: la sessione ha lasciato commit su '$BRANCH' ma nessuna PR. Lavoro da recuperare a mano."
fi

git worktree remove --force "$WT" 2>/dev/null || true
log "=== Giro concluso (#$ISSUE) ==="
