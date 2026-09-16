"""Provenienza di trasporto di una news: da quale consegna e' entrata (#541).

`source` dice **chi** ha pubblicato l'articolo (`alpaca_benzinga`), non **da
dove** e' arrivato. Alpaca ne ha due consegne per lo stesso contenuto — il
WebSocket 24/7 (`src/workers/news_stream.py`) e il poller REST a 15 minuti
(`src/workers/ingestion.py`) — e #455 le ha deliberatamente unificate sotto un
solo contratto di dedup/telemetria. Corretto, ma cancella la provenienza: una
volta persistita, la riga non dice piu' quale dei due l'ha vista per primo.

Conseguenza misurata, non teorica. L'analisi del 2026-09-15
(`docs/research/stale_cohort_fetch_latency_2026-09-15.md` §4.1) attribuisce il
gradino `already_stale_at_fetch` 18 → 263 fra il 09 e il 10/09 al passaggio del
primo avvistamento dal REST al WS — ma **per inferenza dalla latenza**
(`raw_ingested_at - published_at ≈ 0` ⇒ WebSocket), non per osservazione. E il
tasso di articoli mai consegnati dal WebSocket (~2,5% il 08/09, #455) non ha una
serie storica perche' si ricostruisce solo incrociando log di container che
ruotano.

Regola di scrittura: **registra chi osserva**. L'item accodato porta il
trasporto del primo avvistamento (gli altri non superano il dedup), la riga di
scarto porta quello dell'avvistamento che l'ha prodotta. Il trasporto non entra
mai in una chiave di dedup: WS e REST devono continuare a deduplicarsi a
vicenda.

Perimetro: sola telemetria. Nessuna soglia, nessun peso, nessun gate — il
destino di nessuna news cambia (freeze #171).
"""

TRANSPORT_WS = "ws"
TRANSPORT_REST = "rest"
TRANSPORTS = frozenset({TRANSPORT_WS, TRANSPORT_REST})


def marca_trasporto(item, transport: str):
    """Marca l'item col trasporto che lo sta osservando e lo restituisce.

    Stretta di proposito: gira sul **produttore**, dove il valore e' una
    costante di modulo scelta da noi. Un'etichetta ignota qui finirebbe dentro
    una serie pubblicata e nessuno saprebbe piu' cosa significa — meglio un
    errore rumoroso al deploy che un terzo valore inventato nel ledger.
    """
    if transport not in TRANSPORTS:
        raise ValueError(
            f"Trasporto news sconosciuto: {transport!r} "
            f"(ammessi: {sorted(TRANSPORTS)})"
        )
    item.transport = transport
    return item


def leggi_trasporto(item) -> str | None:
    """Trasporto dichiarato dall'item, o `None` se assente o non riconosciuto.

    Permissiva, all'opposto di `marca_trasporto`: gira sul **consumatore**, su
    payload gia' in coda che possono essere stati scritti da una versione
    precedente del produttore. Un valore ignoto e' un difetto di chi ha scritto,
    non un motivo per far cadere la riga di telemetria che lo documenterebbe.

    `None` significa «non strumentato», e va persistito come NULL: e'
    un'informazione vera e distinta da «arrivato dal REST».
    """
    valore = getattr(item, "transport", None) or ""
    return valore if valore in TRANSPORTS else None
