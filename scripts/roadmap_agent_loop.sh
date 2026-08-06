#!/usr/bin/env bash
# Un giro di lavoro sulla roadmap, eseguito da Claude Code in un worktree isolato.
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

export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
QUEUE_FILE="${ROADMAP_QUEUE_FILE:-$SCRIPT_DIR/roadmap_queue.txt}"
LOG_DIR="$PROJECT_DIR/logs"
STATE_FILE="$LOG_DIR/roadmap_agent_state.tsv"
LOCK_FILE="$LOG_DIR/.roadmap_agent.lock"
LOG_FILE="$LOG_DIR/roadmap_agent_$(date +%Y-%m-%d).log"

MAX_TENTATIVI=2          # dopo due fallimenti l'issue esce dalla rotazione
TIMEOUT_SESSIONE=5400    # 90 minuti: oltre, la sessione e' bloccata, non lenta

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

log "=== Giro roadmap ==="
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
    log "(dry-run) mi fermo qui: nessun worktree, nessuna sessione, stato invariato."
    exit 0
fi

registra_tentativo "$ISSUE"

# --- worktree isolato ----------------------------------------------------------
# Mai nell'albero principale: li' girano i cron dell'osservazione e vive il
# ledger delle evidenze. Un agente che sbaglia non deve poterli toccare.
BRANCH="agent/issue-${ISSUE}"
WT="$PROJECT_DIR/.worktrees/agent-${ISSUE}"

git worktree remove --force "$WT" 2>/dev/null || true
git branch -D "$BRANCH" 2>/dev/null || true
git worktree add -b "$BRANCH" "$WT" origin/main >>"$LOG_FILE" 2>&1

tg_send "🧭 <b>Roadmap — giro avviato</b>
Issue #${ISSUE}: ${TITOLO}"

PROMPT=$(cat <<PROMPTEOF
Lavora la issue GitHub #${ISSUE} di questo repository (Alembic) fino ad aprire una pull request.

Sei in un worktree dedicato: $WT, sul branch $BRANCH, basato su origin/main.
Leggi CLAUDE.md prima di tutto.

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

set +e
OUTPUT=$(cd "$WT" && timeout "$TIMEOUT_SESSIONE" \
    claude --allowedTools "Bash,Read,Write,Edit,Glob,Grep" -p "$PROMPT" 2>&1)
ESITO=$?
set -e

echo "$OUTPUT" >> "$LOG_FILE"

if (( ESITO == 124 )); then
    log "#$ISSUE — sessione uccisa dal timeout dopo ${TIMEOUT_SESSIONE}s."
elif (( ESITO != 0 )); then
    log "#$ISSUE — sessione terminata con codice $ESITO."
fi

# --- esito reale: la PR esiste o no. Non ci si fida del racconto della sessione.
PR_URL=$(gh pr list --state open --head "$BRANCH" --json url -q '.[0].url' 2>/dev/null || echo "")

if [[ -n "$PR_URL" ]]; then
    log "#$ISSUE — PR aperta: $PR_URL"
    # Tentativo riuscito: lo tolgo dal conteggio dei fallimenti.
    grep -v -P "^${ISSUE}\t" "$STATE_FILE" > "${STATE_FILE}.tmp" 2>/dev/null || true
    mv "${STATE_FILE}.tmp" "$STATE_FILE"
    tg_send "✅ <b>Roadmap — PR pronta per review</b>
Issue #${ISSUE}: ${TITOLO}
${PR_URL}"
else
    log "#$ISSUE — nessuna PR aperta."
    CODA=$(echo "$OUTPUT" | tail -c 1200)
    tg_send "⚠️ <b>Roadmap — nessuna PR</b>
Issue #${ISSUE}: ${TITOLO}
Esito sessione: ${ESITO}

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
