"""Distillazione deterministica dei log di container (triage locale, 2026-09-14).

Modulo puro: niente rete, niente disco, niente processi.

Esiste per una ragione di aritmetica. Il modello locale legge a ~121 token/s:
i 9 MB al giorno di `worker-inference` sarebbero quasi sei ore di solo prefill.
Dare al modello i log grezzi significa non finire mai. Qui il volume viene
ridotto **prima** e **in modo deterministico** — righe identiche a meno di
timestamp, id e numeri collassano in un template contato una volta sola — cosi'
al modello arriva un distillato di poche decine di migliaia di caratteri.

Secondo motivo, non meno importante: i log contengono segreti (il token del bot
Telegram compare in chiaro in ogni riga di polling). `redigi` li maschera prima
che finiscano nell'esempio conservato, nel prompt o in un digest scritto su
disco. La redazione e' applicata all'ingresso, non all'uscita: cio' che non
entra non puo' sfuggire.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Ordine significativo: i segreti vanno mascherati prima di qualunque altra
# normalizzazione, altrimenti il collasso dei numeri ne cambierebbe la forma e
# la maschera non li riconoscerebbe piu'.
_SEGRETI = (
    re.compile(r"bot\d+:[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\b(?:bearer|token|api[_-]?key|secret|password)\b[\"'\s:=]+[A-Za-z0-9_\-\.]{6,}"),
    re.compile(r"(?i)\"(?:api_key|token|secret|password)\"\s*:\s*\"[^\"]+\""),
    re.compile(r"\bsk-[A-Za-z0-9]{8,}"),
)

_INTESTAZIONE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} (?P<ora>\d{2}:\d{2}:\d{2}),\d+: (?P<livello>[A-Z]+)/(?P<processo>[^\]]+)\]\s*"
)
# I log dell'API (uvicorn) hanno un'altra forma: "LIVELLO:   messaggio".
_INTESTAZIONE_API = re.compile(r"^(?P<livello>[A-Z]+):\s+")

_MASCHERE = (
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<UUID>"),
    (re.compile(r"\b[0-9a-f]{32,}\b"), "<HEX>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b"), "<IP>"),
    (re.compile(r"\b\d+(?:\.\d+)?s\b"), "<DURATA>"),
    # Issue #619: \b fallisce su numeri incollati a lettere (es. "18.6pp"):
    # il confine di parola non puo' cadere fra una cifra e una lettera (entrambe
    # word char) e il motore maschera solo la parte intera, lasciando ".6pp" che
    # spezza i template in varianti. Il lookaround richiede che a sinistra non ci
    # sia una cifra o un '.' (cosi' "v1.2.3" resta intoccato) e che a destra non
    # ci sia una cifra (cosi' "18.6pp" mangia anche il decimale). Il prefisso
    # esadecimale resta escluso, come con i precedenti confini di parola.
    (re.compile(r"(?<![\w.])(?!0[xX])\d+(?:\.\d+)?(?!\d)"), "<N>"),
)

# Il numero del worker nel pool e' una coordinata di esecuzione, non un fatto:
# tenerlo distinto moltiplicherebbe lo stesso template per ogni fork.
_PROCESSO = re.compile(r"-\d+$")


@dataclass(frozen=True)
class Voce:
    """Un template di riga con quante volte e' comparso e un esempio redatto.

    `giorni_storico` dice in quanti dei giorni precedenti lo stesso template era
    gia' comparso: e' la differenza fra una notizia e lo sfondo. Vale 0 finche'
    non si chiama `annota_ricorrenza`.
    """

    template: str
    livello: str
    conteggio: int
    esempio: str
    prima: str
    ultima: str
    giorni_storico: int = 0


def redigi(riga: str) -> str:
    """Sostituisce i segreti noti con `[REDATTO]`, prima di ogni altro passo."""
    for maschera in _SEGRETI:
        riga = maschera.sub("[REDATTO]", riga)
    return riga


def _scompone(riga: str) -> tuple[str, str, str, str]:
    """Restituisce (ora, livello, processo, messaggio) da una riga di log."""
    intestazione = _INTESTAZIONE.match(riga)
    if intestazione:
        processo = _PROCESSO.sub("-N", intestazione.group("processo"))
        return (
            intestazione.group("ora"),
            intestazione.group("livello"),
            processo,
            riga[intestazione.end() :],
        )
    api = _INTESTAZIONE_API.match(riga)
    if api:
        return "", api.group("livello"), "api", riga[api.end() :]
    return "", "", "", riga


def normalizza_riga(riga: str) -> str:
    """Riduce una riga al suo template: stesso evento, stessa stringa."""
    _, livello, processo, messaggio = _scompone(redigi(riga))
    for maschera, sostituto in _MASCHERE:
        messaggio = maschera.sub(sostituto, messaggio)
    return f"[{livello}/{processo}] {messaggio.strip()}"


def distilla(righe) -> list[Voce]:
    """Collassa le righe in template contati, conservando un esempio redatto.

    L'esempio e' la **prima** occorrenza: una riga vera, citabile, che il
    cancello a valle potra' riscontrare nel file grezzo.
    """
    accumulo: dict[str, dict] = {}
    for riga in righe:
        riga = riga.rstrip("\n")
        if not riga.strip():
            continue
        template = normalizza_riga(riga)
        ora, livello, _, _ = _scompone(riga)
        voce = accumulo.get(template)
        if voce is None:
            accumulo[template] = {
                "livello": livello,
                "conteggio": 1,
                "esempio": redigi(riga),
                "prima": ora,
                "ultima": ora,
            }
        else:
            voce["conteggio"] += 1
            if ora:
                voce["ultima"] = ora
    return [
        Voce(
            template=template,
            livello=dati["livello"],
            conteggio=dati["conteggio"],
            esempio=dati["esempio"],
            prima=dati["prima"],
            ultima=dati["ultima"],
        )
        for template, dati in accumulo.items()
    ]


def annota_ricorrenza(voci: list[Voce], storici) -> list[Voce]:
    """Copia le voci annotando da quanti giorni precedenti il template esiste.

    Senza questa annotazione un allarme che si ripete identico da una settimana
    entra nel referto come se fosse successo oggi: e' esattamente cio' che ha
    riempito di rumore il primo giro (dieci reperti su ventuno erano lo stesso
    DECAY CRITICAL presente da giorni).
    """
    conteggi = storici if isinstance(storici, dict) else {t: 1 for t in storici}
    return [
        Voce(
            template=voce.template,
            livello=voce.livello,
            conteggio=voce.conteggio,
            esempio=voce.esempio,
            prima=voce.prima,
            ultima=voce.ultima,
            giorni_storico=conteggi.get(voce.template, 0),
        )
        for voce in voci
    ]


def novita(voci: list[Voce], storici) -> list[Voce]:
    """Voci il cui template non compare nello storico: il segnale piu' onesto."""
    return [voce for voce in voci if voce.template not in storici]


_GRAVI = ("ERROR", "CRITICAL", "FATAL", "WARNING")


def _priorita(voce: Voce, storici) -> tuple[int, int]:
    """Ordinamento: prima cio' che e' grave **e** nuovo, per ultimo lo sfondo.

    Un errore che si ripete identico da giorni non e' una notizia: precede le
    righe rare, ma segue tutto cio' che oggi non c'era.
    """
    nuovo = voce.template not in storici
    if voce.livello in _GRAVI and nuovo:
        return (0, -voce.conteggio)
    if nuovo:
        return (1, -voce.conteggio)
    if voce.livello in _GRAVI:
        return (2, -voce.conteggio)
    return (3, voce.conteggio)


def seleziona(voci: list[Voce], storici, tetto_caratteri: int) -> list[Voce]:
    """Sceglie le voci che entrano nel prompt, senza mai superare il tetto.

    Le righe frequenti e gia' viste non entrano: non sono anomalie, sono lo
    sfondo. Cio' che entra e' errore, novita' o rarita' — in quest'ordine.
    """
    scelte: list[Voce] = []
    for voce in sorted(voci, key=lambda v: _priorita(v, storici)):
        candidate = scelte + [voce]
        if len(rendi_digest(candidate)) > tetto_caratteri:
            break
        scelte.append(voce)
    return scelte


def rendi_digest(voci: list[Voce]) -> str:
    """Il distillato che il modello legge: una riga per template, numerata."""
    return "\n".join(
        f"T{indice:04d} conteggio={voce.conteggio} {voce.prima}->{voce.ultima} "
        f"gia_visto_in={voce.giorni_storico}g | {voce.esempio}"
        for indice, voce in enumerate(voci, 1)
    )
