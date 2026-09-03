"""Rilevatori sullo stream del modello locale (spec 2026-09-03 §5).

Modulo puro: riceve il ragionamento accumulato e dei contatori, non tocca rete
ne' processi.

Nessuna regola di orologio: un orologio non distingue un lavoro lento da un
lavoro rotto. Il limite lo pongono due misure su cio' che il modello sta
effettivamente producendo — la ripetizione, che identifica il loop vero, e il
budget residuo, che identifica la corsa aritmeticamente incapace di chiudere.

Calibrazione (2026-09-02, due campioni): un ragionamento sano di 23.653
caratteri portava 2 righe ripetute e 1 solo 12-gramma ripetuto; il run che ha
concluso ne aveva 54.958. La soglia a 10 e' quindi deliberatamente larga: con
due soli campioni non vale la pena uccidere un ragionamento sano che ripete una
citazione. `misura_ripetizione` va loggata a ogni giro, cosi' la soglia si
scegliera' sui dati.
"""

from __future__ import annotations

import collections
import re


# Sotto le 60 battute una riga e' un frammento, non un passo di ragionamento.
LUNGHEZZA_MINIMA_RIGA = 60

# 12 parole: abbastanza lungo perche' una coincidenza sia improbabile,
# abbastanza corto per cogliere un paragrafo riformulato.
AMPIEZZA_GRAMMA = 12

SOGLIA_DODICI_GRAMMI = 10

# `max_tokens` e' 32.768 e il JSON del referto su PR #472 e' costato ~2.000
# token: oltre questo punto, con `content` ancora vuoto, il residuo non basta.
TETTO_RAGIONAMENTO = 28_000


def misura_ripetizione(ragionamento: str) -> dict[str, int]:
    """Quanto il ragionamento si ripete: righe identiche e 12-grammi.

    I 12-grammi si contano solo dentro le righe gia' emerse come duplicate
    (stessa riga, testo identico, vista piu' di una volta): un elenco che
    avanza con un indice diverso a ogni passo condivide una struttura di
    frase, non un frammento ripetuto, e non deve contribuire ai 12-grammi.
    Sulle righe duplicate la finestra scorrevole resta densa apposta, cosi'
    da pesare un paragrafo lungo ripetuto piu' di una riga breve ripetuta.
    """
    righe = [
        riga.strip()
        for riga in ragionamento.split("\n")
        if len(riga.strip()) > LUNGHEZZA_MINIMA_RIGA
    ]
    conteggio_righe = collections.Counter(righe)
    righe_ripetute = sum(n - 1 for n in conteggio_righe.values() if n > 1)

    righe_duplicate = [riga for riga in righe if conteggio_righe[riga] > 1]
    parole = re.findall(r"\w+", " ".join(righe_duplicate).lower())
    grammi = collections.Counter(
        tuple(parole[i:i + AMPIEZZA_GRAMMA])
        for i in range(max(0, len(parole) - AMPIEZZA_GRAMMA))
    )
    dodici_grammi_ripetuti = sum(1 for n in grammi.values() if n > 2)

    return {
        "righe_sostanziali": len(righe),
        "righe_ripetute": righe_ripetute,
        "dodici_grammi_ripetuti": dodici_grammi_ripetuti,
    }


def e_loop(misure: dict[str, int], soglia_dodici_grammi: int = SOGLIA_DODICI_GRAMMI) -> bool:
    """True se il ragionamento gira a vuoto invece di avanzare."""
    return misure["dodici_grammi_ripetuti"] > soglia_dodici_grammi


def e_corsa_condannata(
    token_ragionamento: int,
    content_vuoto: bool,
    tetto: int = TETTO_RAGIONAMENTO,
) -> bool:
    """True se il budget residuo non basta piu' per emettere il referto."""
    return content_vuoto and token_ragionamento >= tetto
