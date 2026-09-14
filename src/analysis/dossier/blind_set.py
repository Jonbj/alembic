"""Streak di copertura zero per la watchlist (#511).

Il conteggio giornaliero ``watchlist_zero_news`` e' una fotografia aggregata:
non distingue un insieme che resta cieco da un ticker che ricompare nella
copertura. Questa misura conserva entrambe le forme di assenza per ticker,
senza intervenire su connettori, segnali o decisioni live.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

BLIND_SET_SCHEMA_VERSION = "1.0"
SEDUTE_ALLERTA_ZERO_ARTICOLI = 5

DEFINIZIONE = (
    "streak per ticker sulle sedute di borsa disponibili: zero articoli canonici "
    "e, separatamente, zero articoli ISSUER_SPECIFIC tempestivi. Un dossier "
    "mancante o incompleto tronca lo streak; non equivale a copertura."
)


def _is_zero(metrics: object, field: str) -> bool | None:
    if not isinstance(metrics, Mapping):
        return None
    value = metrics.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value == 0


def _streak_zero(
    *,
    zero_oggi: bool | None,
    field: str,
    ticker: str,
    sedute_precedenti: Sequence[str],
    dossier_storici: Mapping[str, Mapping[str, Any]],
) -> tuple[int | None, str | None]:
    """Conta lo streak verso il passato, senza passare sopra dati ignoti."""
    if zero_oggi is None:
        return None, "dati_giorno_mancanti"
    if not zero_oggi:
        return 0, None

    streak = 1
    for seduta in reversed(sedute_precedenti):
        dossier = dossier_storici.get(seduta)
        if not isinstance(dossier, Mapping):
            return streak, "dossier_mancante"
        coverage = dossier.get("per_ticker")
        if not isinstance(coverage, Mapping) or ticker not in coverage:
            return streak, "dossier_incompleto"
        zero = _is_zero(coverage[ticker], field)
        if zero is None:
            return streak, "dossier_incompleto"
        if not zero:
            return streak, None
        streak += 1
    return streak, "finestra"


def build_blind_set(
    copertura_odierna: Mapping[str, Any],
    *,
    universe: Sequence[str],
    sedute: Sequence[str],
    dossier_storici: Mapping[str, Mapping[str, Any]],
    soglia_allerta: int = SEDUTE_ALLERTA_ZERO_ARTICOLI,
) -> dict:
    """Costruisce la misura persistibile della cecita' per ticker.

    ``dossier_storici`` contiene il solo blocco ``copertura_articoli`` delle
    sedute precedenti. Il chiamante fa l'I/O; qui restano soltanto i calcoli
    riproducibili e il contratto None/UNKNOWN.
    """
    if soglia_allerta < 1:
        raise ValueError("soglia_allerta deve essere positiva")

    per_ticker_oggi = copertura_odierna.get("per_ticker")
    if not isinstance(per_ticker_oggi, Mapping):
        per_ticker_oggi = {}
    sedute = list(sedute)
    calendario_assente = not sedute
    sedute_precedenti = sedute[:-1] if sedute else []
    righe: dict[str, dict] = {}

    for ticker in sorted({str(symbol).upper() for symbol in universe}):
        metrics = per_ticker_oggi.get(ticker)
        zero_raw = _is_zero(metrics, "articoli_unici")
        zero_effective = _is_zero(metrics, "effective_timely_articles")
        streak_raw: int | None
        troncato_raw: str | None
        streak_effective: int | None
        troncato_effective: str | None
        if calendario_assente:
            streak_raw, troncato_raw = None, "calendario_sedute_non_disponibile"
            streak_effective, troncato_effective = None, "calendario_sedute_non_disponibile"
        else:
            streak_raw, troncato_raw = _streak_zero(
                zero_oggi=zero_raw,
                field="articoli_unici",
                ticker=ticker,
                sedute_precedenti=sedute_precedenti,
                dossier_storici=dossier_storici,
            )
            streak_effective, troncato_effective = _streak_zero(
                zero_oggi=zero_effective,
                field="effective_timely_articles",
                ticker=ticker,
                sedute_precedenti=sedute_precedenti,
                dossier_storici=dossier_storici,
            )
        righe[ticker] = {
            "articoli_unici_giorno": (
                metrics.get("articoli_unici") if isinstance(metrics, Mapping) else None
            ),
            "effective_timely_articles_giorno": (
                metrics.get("effective_timely_articles")
                if isinstance(metrics, Mapping) else None
            ),
            "sedute_consecutive_zero_articoli": streak_raw,
            "zero_articoli_streak_troncato_da": troncato_raw,
            "sedute_consecutive_zero_effective_timely": streak_effective,
            "zero_effective_timely_streak_troncato_da": troncato_effective,
        }

    return {
        "schema_version": BLIND_SET_SCHEMA_VERSION,
        "definizione": DEFINIZIONE,
        "sedute_finestra": sedute,
        "soglia_allerta_sedute_zero_articoli": soglia_allerta,
        "per_ticker": righe,
        "ticker_zero_articoli": sorted(
            ticker for ticker, row in righe.items()
            if row["sedute_consecutive_zero_articoli"] not in (None, 0)
        ),
        "ticker_zero_effective_timely": sorted(
            ticker for ticker, row in righe.items()
            if row["sedute_consecutive_zero_effective_timely"] not in (None, 0)
        ),
        "ticker_allerta_zero_articoli": sorted(
            ticker for ticker, row in righe.items()
            if (row["sedute_consecutive_zero_articoli"] or 0) >= soglia_allerta
        ),
        "freeze": "strumento di misura read-only (#511); nessuna taratura toccata",
    }