#!/usr/bin/env bash
# Un giro di lavoro sulla roadmap, eseguito in un worktree isolato da un modello
# esterno a chi ha progettato l'impianto (vedi MOTORI piu' sotto).
#
# Prende UNA issue per run — la prima della coda ancora lavorabile — apre una PR e
# si ferma. Non mergia mai: in questo repo la CI e' cronicamente rossa per motivi
# ambientali (integration test senza DB), quindi un merge automatico si
# appoggerebbe a un segnale che non c'e'.
#
# Perimetro: dal 2026-08-03 al 2026-09-28 vige il freeze di osservazione (#171).
# L'agente NON sceglie cosa sia compatibile col freeze. Due lucchetti indipendenti
# lo decidono a monte:
#   1. scripts/roadmap_queue.txt  — l'ordine
#   2. la label `freeze-ok` su GitHub — il permesso
# Una issue si lavora solo se compare in entrambi. L'agente non puo' modificare
# nessuno dei due (e il prompt glielo vieta esplicitamente).
#
# Log   : logs/roadmap_agent_YYYY-MM-DD.log
# Stato : logs/roadmap_agent_state.tsv   (issue <TAB> tentativi)

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

mkdir -p "$LOG_DIR"
touch "$STATE_FILE"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "$LOG_FILE"; }

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
            exit 0
        fi
        log "Nessun motore fra [${MOTORI[*]}] e' installato — giro annullato."
        tg_send "⛔ <b>Roadmap</b> — nessun motore disponibile fra [${MOTORI[*]}]. Nessun giro eseguito."
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

# --- comandi operatore ----------------------------------------------------------
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
        log "  #$numero — ha gia' una PR aperta, salto."; continue
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
git branch -D "$BRANCH" 2>/dev/null || true
git worktree add -b "$BRANCH" "$WT" origin/main >>"$LOG_FILE" 2>&1

tg_send "🧭 <b>Roadmap — giro avviato</b>
Issue #${ISSUE}: ${TITOLO}
Motore: ${MOTORE}"

PROMPT=$(cat <<PROMPTEOF
Lavora la issue GitHub #${ISSUE} di questo repository (Alembic) fino ad aprire una pull request.

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
    git worktree remove --force "$WT" 2>/dev/null || true
    git branch -D "$BRANCH" 2>/dev/null || true
    exit 0
fi

echo "$OUTPUT" >> "$LOG_FILE"

if (( ESITO == 124 )); then
    log "#$ISSUE — sessione uccisa dal timeout dopo ${TIMEOUT_SESSIONE}s."
elif (( ESITO != 0 )); then
    log "#$ISSUE — sessione terminata con codice $ESITO."
fi

# --- esito reale: la PR esiste o no. Non ci si fida del racconto della sessione.
PR_URL=$(gh pr list --state open --head "$BRANCH" --json url -q '.[0].url' 2>/dev/null || echo "")

if [[ -n "$PR_URL" ]]; then
    log "#$ISSUE — PR aperta da $MOTORE: $PR_URL"
    # Tentativo riuscito: lo tolgo dal conteggio dei fallimenti.
    grep -v -P "^${ISSUE}\t" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
    PR_NUM=$(gh pr list --state open --head "$BRANCH" --json number -q '.[0].number')
    tg_send "🔍 <b>Roadmap — PR aperta, review in corso</b>
Issue #${ISSUE}: ${TITOLO}
Implementata da: ${MOTORE}
${PR_URL}"

    # ── cancello 1: nessun test rotto NUOVO rispetto a main ────────────────────
    REGRESSIONI=-1
    if RID=$(attendi_ci "$BRANCH"); then
        REGRESSIONI=$(conta_regressioni "$RID")
        log "#$ISSUE — CI conclusa (run $RID): $REGRESSIONI test rotti in piu' rispetto a main"
    else
        log "#$ISSUE — CI non conclusa entro ${CI_ATTESA_MAX}s: il cancello non e' calcolabile."
    fi

    # ── cancello 2: review di un modello diverso dall'implementatore ───────────
    VERDETTO="NON_ESEGUITA"; REVISORE=""
    if REVISORE=$(scegli_recensore "$MOTORE"); then
        log "#$ISSUE — review affidata a $REVISORE"
        REV_PROMPT="Rivedi la pull request #${PR_NUM} di questo repository, che chiude o riguarda la issue #${ISSUE}.

Sei nel worktree $WT, sul branch $BRANCH. NON scrivere e NON modificare nulla: la tua uscita
e' un giudizio, non una correzione. Non mergiare, non chiudere, non commentare via gh.

Contesto che devi leggere prima di giudicare:
- CLAUDE.md, per le convenzioni del progetto
- \\`gh issue view ${ISSUE} --comments\\` — se un commento dell'operatore restringe il perimetro,
  quella decisione vince sul testo originale della issue
- docs/evidence/OBSERVATION_CHARTER.md — dal 2026-08-03 al 2026-09-28 ogni TARATURA e' congelata
  (soglie, pesi, flag, cooldown, parametri di strategia). Sono ammessi solo correttezza,
  strumentazione e misura.
- \\`gh pr diff ${PR_NUM}\\` — il diff completo

Dato oggettivo gia' calcolato, non ricalcolarlo: rispetto a main la CI di questa PR ha
${REGRESSIONI} test rotti in piu' (-1 significa 'non calcolabile').

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
VERDETTO: RESPINGI"

        set +e
        REV_OUT=$(esegui_revisore "$REVISORE" "$REV_PROMPT" "$WT")
        set -e
        if echo "$REV_OUT" | grep -qiE "$_RATE_LIMIT_RE"; then
            metti_in_panchina "$REVISORE"; VERDETTO="NON_ESEGUITA"
            log "#$ISSUE — recensore $REVISORE in rate limit: review saltata."
        elif echo "$REV_OUT" | grep -qE "^VERDETTO: APPROVA[[:space:]]*$"; then
            VERDETTO="APPROVA"
        elif echo "$REV_OUT" | grep -qE "^VERDETTO: RESPINGI[[:space:]]*$"; then
            VERDETTO="RESPINGI"
        fi
        log "#$ISSUE — verdetto di $REVISORE: $VERDETTO"
        printf '## Review automatica — %s\n\nTest rotti in piu%s rispetto a main: **%s**\n\n---\n\n%s\n' \
            "$REVISORE" "'" "$REGRESSIONI" "$REV_OUT" > "$LOG_DIR/.review_$PR_NUM.md"
        gh pr comment "$PR_NUM" --body-file "$LOG_DIR/.review_$PR_NUM.md" >/dev/null 2>&1 || true
        rm -f "$LOG_DIR/.review_$PR_NUM.md"
    else
        log "#$ISSUE — nessun motore diverso dall'implementatore disponibile: review non eseguita."
    fi

    # ── merge solo se ENTRAMBI i cancelli sono passati ─────────────────────────
    if [[ "$VERDETTO" == "APPROVA" && "$REGRESSIONI" == "0" ]]; then
        if gh pr merge "$PR_NUM" --merge --delete-branch >/dev/null 2>&1; then
            log "#$ISSUE — PR #$PR_NUM mergiata (0 regressioni, $REVISORE approva)."
            tg_send "🟢 <b>Roadmap — PR mergiata da sola</b>
Issue #${ISSUE}: ${TITOLO}
${MOTORE} ha implementato, ${REVISORE} ha approvato, 0 test rotti in piu&#39;.
${PR_URL}

<i>Nota: il merge non e&#39; un deploy. Le immagini sono baked: serve rebuild.</i>"
        else
            log "#$ISSUE — merge rifiutato da GitHub (conflitto o protezione)."
            tg_send "⚠️ <b>Roadmap</b> — #${PR_NUM} approvata ma il merge e&#39; stato rifiutato da GitHub. Serve una mano.
${PR_URL}"
        fi
    else
        log "#$ISSUE — NON mergiata (verdetto=$VERDETTO, regressioni=$REGRESSIONI)."
        tg_send "🟡 <b>Roadmap — PR da guardare</b>
Issue #${ISSUE}: ${TITOLO}
Implementata da ${MOTORE}${REVISORE:+, rivista da $REVISORE}
Verdetto: <b>${VERDETTO}</b> · test rotti in piu&#39; rispetto a main: <b>${REGRESSIONI}</b>
${PR_URL}"
    fi
else
    log "#$ISSUE — nessuna PR aperta."
    CODA=$(echo "$OUTPUT" | tail -c 1200)
    tg_send "⚠️ <b>Roadmap — nessuna PR</b>
Issue #${ISSUE}: ${TITOLO}
Motore: ${MOTORE} — esito sessione: ${ESITO}

<pre>$(echo "$CODA" | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g')</pre>"
    # Il branch senza commit non serve a nessuno; se ha commit lo tengo per l'ispezione.
    if [[ -z "$(git log --oneline origin/main.."$BRANCH" 2>/dev/null)" ]]; then
        git worktree remove --force "$WT" 2>/dev/null || true
        git branch -D "$BRANCH" 2>/dev/null || true
        log "#$ISSUE — nessun commit prodotto: worktree e branch rimossi."
        exit 0
    fi
fi

git worktree remove --force "$WT" 2>/dev/null || true
log "=== Giro concluso (#$ISSUE) ==="
