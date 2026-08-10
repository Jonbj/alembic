"""Copertura della watchlist da parte del sentiment: chi non arriva mai (#226).

Un simbolo puo' stare in watchlist e non ricevere **mai** un segnale di sentiment,
senza che nulla lo segnali. E' successo a `BRK.B` per 96 segnali: il sentiment li
scriveva come `BRKB`, la watchlist dice `BRK.B`, e le due forme non si sono mai
incontrate. Sei di quei segnali erano sopra il gate d'ingresso.

**Perche' il controllo guarda i segnali e non le decisioni.** L'istinto e' cercare i
simboli che non compaiono mai in `execution_decisions`. Su questo caso avrebbe dato
un falso negativo: `BRK.B` ha quattro righe li', prodotte dal path momentum S1, che
non passa dal sentiment. Il simbolo risultava "negoziato" mentre il suo canale
sentiment era morto. La firma che coglie il difetto e' l'assenza di **segnali**.

Due controlli, con forza diversa:

- `orfani_di_normalizzazione` — un segnale scritto in una forma che la watchlist non
  riconosce ma che, a meno di punteggiatura, e' un simbolo di watchlist. Segnale
  forte: quasi nessun falso positivo, perche' richiede una corrispondenza esatta
  sulla forma normalizzata.
- `simboli_watchlist_senza_segnali` — un simbolo di watchlist a zero segnali nella
  finestra. Segnale debole: un titolo puo' legittimamente non fare notizia, quindi
  va letto su una finestra lunga e vale come sospetto, non come diagnosi.

I due insieme distinguono le due cause: *nessuno ne parla* contro *ne parlano ma con
un altro nome*. Il secondo e' un difetto, il primo no.

Funzioni pure: nessun accesso a DB o rete. L'ispezione sui dati veri sta in
`scripts/check_watchlist_coverage.py`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re


_NON_ALFANUMERICI = re.compile(r"[^A-Z0-9]")


def forma_confrontabile(simbolo: str) -> str:
    """Forma su cui confrontare due scritture dello stesso ticker.

    Maiuscolo e senza punteggiatura: `BRK.B`, `brk-b` e `BRK/B` collassano tutti su
    `BRKB`. Serve solo a confrontare, mai a scrivere: la forma canonica resta quella
    della watchlist.
    """
    return _NON_ALFANUMERICI.sub("", simbolo.strip().upper())


def orfani_di_normalizzazione(
    watchlist: Iterable[str],
    simboli_con_segnali: Iterable[str],
) -> list[tuple[str, str]]:
    """Segnali scritti in una forma che la watchlist non riconosce.

    Restituisce le coppie `(forma_del_segnale, forma_di_watchlist)` ordinate, per i
    simboli che **non** compaiono nella watchlist cosi' come sono ma che vi
    corrispondono una volta normalizzati. E' il caso `BRKB` → `BRK.B`.

    Un simbolo semplicemente fuori universo (`VOO`, `DIA`) non e' un orfano: non
    somiglia a nulla che sia in watchlist, ed e' atteso che non venga negoziato.
    """
    canoniche = set(watchlist)
    per_forma = {forma_confrontabile(s): s for s in canoniche}

    orfani: dict[str, tuple[str, str]] = {}
    for simbolo in simboli_con_segnali:
        if simbolo in canoniche:
            continue
        canonica = per_forma.get(forma_confrontabile(simbolo))
        # `canonica != simbolo` e' gia' garantito dal `continue` sopra, ma la
        # corrispondenza deve essere esatta sulla forma normalizzata: BRKA non
        # deve appaiarsi a BRK.B, sono due titoli diversi.
        if canonica is not None:
            orfani[simbolo] = (simbolo, canonica)

    return sorted(orfani.values())


def simboli_watchlist_senza_segnali(
    watchlist: Iterable[str],
    segnali_per_simbolo: Mapping[str, int],
) -> list[str]:
    """Simboli di watchlist che non hanno ricevuto nessun segnale nella finestra.

    Un simbolo assente dalla mappa vale zero: non essere mai stato contato e essere
    stato contato zero volte sono la stessa cosa per chi legge.
    """
    return sorted(s for s in set(watchlist) if segnali_per_simbolo.get(s, 0) == 0)
