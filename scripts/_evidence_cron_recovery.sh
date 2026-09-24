#!/usr/bin/env bash
# Primitive condivise dai cron di evidenza e dal loop roadmap (#563 / F-074).
# Una quota Claude non e' un errore permanente: la data non materializzata resta
# recuperabile e, quando il messaggio dichiara il reset, la stessa esecuzione
# riprova una sola volta dopo quel momento.

_CLAUDE_RATE_LIMIT_RE='rate.?limit|429|quota exceeded|too many requests|usage limit|resource_exhausted|overloaded|hit your (weekly|5-hour|usage|session) limit|weekly limit|session limit'

claude_rate_limited() {
    printf '%s\n' "$1" | grep -qiE "$_CLAUDE_RATE_LIMIT_RE"
}

# Stampa la prima seduta della lista che non compare fra quelle gia' pubblicate.
# Gli argomenti sono stringhe whitespace-separated per non dipendere da bash 4.3
# (la macchina dei cron e' GNU/Linux, ma il contratto resta banale da testare).
oldest_missing_session() {
    local sessions="$1" published="$2" session
    for session in $sessions; do
        if ! printf '%s\n' "$published" | grep -qxF "$session"; then
            printf '%s\n' "$session"
            return 0
        fi
    done
    return 1
}

# Come oldest_missing_session, ma salta le sedute che il predicato $3 dichiara
# irrecuperabili: il predicato riceve la data e riesce (exit 0) quando questa
# seduta NON e' recuperabile dal cron. La scelta e le saltate tornano nelle
# globali CHOSEN_SESSION e SKIPPED_SESSIONS (separata da spazi) — non solo su
# stdout — perche' il chiamante di produzione cattura con $(...) e la
# sostituzione gira in subshell, dove le variabili non sopravvivono. Un buco
# nella serie osservata deve restare visibile all'operatore, non silenzioso.
# Serve al recupero #563: il 2026-09-24 due run hanno selezionato 2026-09-09,
# ne hanno preservato il dossier (schema 2.9) e sono morti sul contratto
# schema #287 — per sempre, perche' ogni run successivo riselezionava la
# stessa data bloccando anche le sedute piu' recenti.
oldest_recoverable_session() {
    local sessions="$1" published="$2" is_unrecoverable="$3" session
    SKIPPED_SESSIONS=""
    CHOSEN_SESSION=""
    for session in $sessions; do
        if printf '%s\n' "$published" | grep -qxF "$session"; then
            continue
        fi
        if "$is_unrecoverable" "$session"; then
            SKIPPED_SESSIONS+="${session} "
            continue
        fi
        CHOSEN_SESSION="$session"
        printf '%s\n' "$session"
        return 0
    done
    return 1
}

_claude_reset_epoch() {
    local output="$1" reset epoch now
    reset=$(printf '%s\n' "$output" | sed -nE \
        's/.*resets[[:space:]]+([^()]*)[[:space:]]*\(Europe\/Rome\).*/\1/p' | tail -1)
    [[ -n "$reset" ]] || return 1
    epoch=$(TZ=Europe/Rome date -d "$reset" +%s 2>/dev/null) || return 1
    now=$(date +%s)
    if (( epoch <= now )); then
        # Claude omette la data per i reset intragiornalieri. Dopo quell'ora,
        # il prossimo reset e' domani, non un errore terminale della seduta.
        [[ "$reset" =~ ^[[:space:]]*[0-9]{1,2}(:[0-9]{2})?[[:space:]]*([aApP][mM])?[[:space:]]*$ ]] || return 1
        epoch=$(TZ=Europe/Rome date -d "tomorrow $reset" +%s 2>/dev/null) || return 1
    fi
    printf '%s\n' "$epoch"
}

# Imposta CLAUDE_SESSION_OUTPUT e CLAUDE_SESSION_STATUS. Il chiamante conserva
# l'unico ramo di errore, ma non perde una seduta per un limite che si resetta.
run_claude_with_quota_retry() {
    local prompt="$1" allowed_tools="$2" reset_epoch wait_seconds
    set +e
    CLAUDE_SESSION_OUTPUT=$(claude --allowedTools "$allowed_tools" -p "$prompt" 2>&1)
    CLAUDE_SESSION_STATUS=$?
    set -e

    if (( CLAUDE_SESSION_STATUS == 0 )) || ! claude_rate_limited "$CLAUDE_SESSION_OUTPUT"; then
        return 0
    fi
    reset_epoch=$(_claude_reset_epoch "$CLAUDE_SESSION_OUTPUT") || return 0
    wait_seconds=$(( reset_epoch - $(date +%s) + 5 ))
    (( wait_seconds > 0 )) || return 0
    echo "Quota Claude esaurita: riprovo una volta dopo il reset dichiarato alle $(TZ=Europe/Rome date -d "@$reset_epoch" '+%H:%M %Z')."
    sleep "$wait_seconds"

    set +e
    CLAUDE_SESSION_OUTPUT=$(claude --allowedTools "$allowed_tools" -p "$prompt" 2>&1)
    CLAUDE_SESSION_STATUS=$?
    set -e
}
