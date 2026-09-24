#!/usr/bin/env bash
# Stop di rischio S4 — sorveglianza giornaliera della soglia pre-registrata.
#
# La carta di osservazione (docs/evidence/OBSERVATION_CHARTER.md § "Stop di rischio,
# pre-registrato", #329, registrato il 2026-08-25) dice:
#
#   «Se il P&L economico cumulato della sleeve S4 sulla finestra tocca -$1.000, S4 passa
#    a shadow immediatamente. Continua a produrre segnali e a misurarsi, smette di
#    eseguire. Nessuna discussione, nessuna deroga, nessuna taratura come alternativa.»
#
# Fino al 2026-09-21 nessun codice leggeva quella soglia: lo stop esisteva solo sulla
# carta. Il 2026-09-16 il cumulato ha toccato -$979,55, cioe' $20,45 dallo scatto, e
# nessun canale lo ha segnalato. Questo script chiude quel buco.
#
# Semantica: "TOCCA" — conta il MINIMO della serie sulla finestra, non il valore di oggi.
# Un rientro successivo (il 09-17 risale a -$696,33) non annulla un tocco avvenuto: lo
# stop e' un livello, non uno stato istantaneo.
#
# Non e' uno stop automatico: non tocca ordini, flag o configurazione. Allerta l'operatore,
# che esegue. Silenziabile solo con un ack esplicito:
#   bash scripts/ack_deadline.sh S4_RISK_STOP
set -euo pipefail

PROJECT_DIR="/home/stefano/Documents/Projects/Alembic"
LEDGER="$PROJECT_DIR/docs/evidence/economic_pnl.json"
ACK_DIR="$HOME/.alembic-deadline-acks"
ID="S4_RISK_STOP"
SOGLIA="-1000"      # stop pre-registrato
PREALLERTA="-900"   # banda di preavviso, NON un secondo stop
mkdir -p "$ACK_DIR"

TELEGRAM_BOT_TOKEN=""
TELEGRAM_CHAT_ID=""
if [[ -f "$PROJECT_DIR/.env" ]]; then
    # shellcheck disable=SC1090
    source <(grep -E '^TELEGRAM_(BOT_TOKEN|CHAT_ID)=' "$PROJECT_DIR/.env" | sed 's/#.*//')
fi

tg_send() {
    if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
        echo "[risk-stop] credenziali Telegram assenti — invio saltato" >&2
        return 0
    fi
    # --data-urlencode e non -d: l'escape HTML contiene & e troncherebbe il messaggio (#591).
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode chat_id="${TELEGRAM_CHAT_ID}" \
        --data-urlencode parse_mode="HTML" \
        --data-urlencode text="$1" > /dev/null || true
}

if [[ ! -f "$LEDGER" ]]; then
    # Fail loudly: un ledger assente non e' "nessun rischio".
    tg_send "⚠️ <b>Stop di rischio S4 NON VERIFICABILE</b> — ${LEDGER} manca. Lo stop pre-registrato a ${SOGLIA}\$ non e' sorvegliato fino a quando il ledger non torna."
    echo "[risk-stop] ledger assente: $LEDGER" >&2
    exit 2
fi

read -r STATO MIN_VAL MIN_DATA ULTIMO_VAL ULTIMA_DATA < <(python3 - "$LEDGER" "$SOGLIA" "$PREALLERTA" <<'PY'
import json, sys
ledger, soglia, preallerta = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
serie = json.load(open(ledger))["pnl_economico"]["cumulato"]["S4"]
date = sorted(serie)
if not date:
    print("VUOTO 0 - 0 -")
    raise SystemExit
min_data = min(date, key=lambda d: serie[d])
min_val = serie[min_data]
ultima = date[-1]
stato = "BREACH" if min_val <= soglia else ("PREALLERTA" if min_val <= preallerta else "OK")
print(f"{stato} {min_val:.2f} {min_data} {serie[ultima]:.2f} {ultima}")
PY
)

if [[ "$STATO" == "VUOTO" ]]; then
    tg_send "⚠️ <b>Stop di rischio S4 NON VERIFICABILE</b> — la serie <code>pnl_economico.cumulato.S4</code> e' vuota in ${LEDGER}."
    exit 2
fi

echo "[risk-stop] stato=$STATO min=$MIN_VAL ($MIN_DATA) ultimo=$ULTIMO_VAL ($ULTIMA_DATA)"

[[ "$STATO" == "OK" ]] && exit 0
[[ -f "$ACK_DIR/${ID}.acked" ]] && { echo "[risk-stop] gia' ackato — nessun invio"; exit 0; }

TODAY=$(date +%Y-%m-%d)
LASTSENT="$ACK_DIR/${ID}.lastsent"
[[ -f "$LASTSENT" && "$(cat "$LASTSENT")" == "$TODAY" ]] && { echo "[risk-stop] gia' inviato oggi"; exit 0; }

if [[ "$STATO" == "BREACH" ]]; then
    MSG="🛑 <b>STOP DI RISCHIO S4 TOCCATO</b> — minimo <b>${MIN_VAL}\$</b> il ${MIN_DATA} (soglia ${SOGLIA}\$, pre-registrata il 2026-08-25, #329).
La carta non lascia scelta: <b>S4 passa a shadow immediatamente</b> — continua a produrre segnali e a misurarsi, smette di eseguire. «Nessuna discussione, nessuna deroga, nessuna taratura come alternativa.»
Due cose da NON sbagliare alla sintesi: (1) lo stop e' <b>di rischio, non di merito</b> — non dice che la news editoriale non ha alpha, dice che non lo scopriremo con questi soldi, quindi la domanda di uscita 1 resta <b>aperta e senza risposta</b>, non falsificata; (2) il campione troncato non va confuso con un campione completo.
Ultimo valore della serie: ${ULTIMO_VAL}\$ il ${ULTIMA_DATA} — un rientro <b>non</b> annulla il tocco.
Carta: docs/evidence/OBSERVATION_CHARTER.md § Stop di rischio. Ack: bash ${PROJECT_DIR}/scripts/ack_deadline.sh ${ID}"
else
    MSG="⚠️ <b>Stop di rischio S4 — banda di preavviso</b>: minimo <b>${MIN_VAL}\$</b> il ${MIN_DATA}, contro la soglia pre-registrata di ${SOGLIA}\$ (#329).
Non e' un secondo stop e non richiede alcuna azione: e' il preavviso che ${PREALLERTA}\$ e' stato superato, cosi' che lo scatto non arrivi come una sorpresa.
Ultimo valore: ${ULTIMO_VAL}\$ il ${ULTIMA_DATA}. Ack (silenzia anche il BREACH): bash ${PROJECT_DIR}/scripts/ack_deadline.sh ${ID}"
fi

tg_send "$MSG"
echo "$TODAY" > "$LASTSENT"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') sent stato=${STATO} min=${MIN_VAL} data=${MIN_DATA}" >> "$ACK_DIR/${ID}.log"
