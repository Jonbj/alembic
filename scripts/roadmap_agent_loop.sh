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
    tg_send "✅ <b>Roadmap — PR pronta per review</b>
Issue #${ISSUE}: ${TITOLO}
Motore: ${MOTORE}
${PR_URL}"
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
