"""Obbligazione Q7 del contratto congelato: esposizione di P0 al TP live.

Il contratto congela P0 con `risk_overlay.take_profit.enabled: false`, ma il
runtime ha `ALPACA_BRACKET_ENABLED` acceso di default e attacca un take-profit
al +6% — **solo** ai submit non frazionabili, perche' Alpaca rifiuta il bracket
sugli ordini frazionari (`portfolio_scheduler.py:4513`).

Se quel TP avrebbe toccato piu' del 5% degli intenti, P0 non riproduce piu' il
benchmark operativo reale e la sua definizione va corretta **prima di n=0**:

    obligation_before_n0: Pubblicare quanti lifecycle P0 sarebbero stati
    toccati dal TP live. Se >5% degli intenti, P0 non e' piu' il benchmark
    operativo reale e la definizione va corretta.

Il modulo e' puro: riceve i lifecycle e i massimi di prezzo gia' osservati, e
non conosce broker ne' DB. La regola che governa ogni ramo dubbio e' una sola:
**ignoto non e' zero**. Un dato mancante contato come "non toccato"
sottostimerebbe proprio la quantita' che il gate deve sorvegliare, quindi ogni
incertezza resta contata a parte e rende il verdetto non conclusivo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Mapping, Sequence

import yaml

OUTCOME_TOUCHED = "TP_WOULD_HAVE_TOUCHED"
OUTCOME_NOT_TOUCHED = "TP_NOT_TOUCHED"
OUTCOME_OUT_OF_PERIMETER = "OUT_OF_PERIMETER"
OUTCOME_PATH_MISSING = "PRICE_PATH_MISSING"
OUTCOME_PATH_INCOMPLETE = "PRICE_PATH_INCOMPLETE"
OUTCOME_FRACTIONABILITY_UNKNOWN = "FRACTIONABILITY_UNKNOWN"
OUTCOME_ENTRY_PRICE_MISSING = "ENTRY_PRICE_MISSING"

_UNKNOWN_OUTCOMES = frozenset({
    OUTCOME_PATH_MISSING,
    OUTCOME_PATH_INCOMPLETE,
    OUTCOME_FRACTIONABILITY_UNKNOWN,
    OUTCOME_ENTRY_PRICE_MISSING,
})


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class LiveTpSettings:
    take_profit_pct: float
    bracket_enabled: bool
    threshold_pct_of_intents: float
    perimeter: str


@dataclass(frozen=True)
class P0Lifecycle:
    """Un intento P0 con cio' che serve a dire se il TP lo avrebbe toccato.

    `fractionable` e' `None` quando la fractionability al momento del submit
    non e' nota: e' un ignoto, non un "no".
    """

    intent_id: str
    symbol: str
    d0: date | None
    entry_price: float
    entry_at: datetime
    exit_at: datetime | None
    fractionable: bool | None
    comparable: bool


@dataclass(frozen=True)
class PricePath:
    """Massimo osservato fra ingresso e uscita, con la finestra che lo copre."""

    highest_high: float | None
    observed_from: datetime
    observed_to: datetime


def load_live_tp_settings(path: Path | None = None) -> LiveTpSettings:
    """Legge soglia e perimetro dal contratto, e il TP dal blocco verificato.

    Il `raise` non e' difensivo: se il contratto accendesse il take-profit nel
    trial, P0 e il runtime non divergerebbero piu' su questo punto e la domanda
    di Q7 perderebbe senso. Eseguirla comunque produrrebbe un numero che non
    misura nulla.
    """
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "s4_exit_trial.yaml"
    payload = yaml.safe_load(path.read_bytes()) or {}
    overlay = payload.get("risk_overlay") or {}
    check = overlay.get("live_tp_check") or {}

    if bool((overlay.get("take_profit") or {}).get("enabled")):
        raise ValueError(
            "the trial freezes take_profit off: with it on, the Q7 question "
            "about live/P0 divergence has no meaning"
        )
    return LiveTpSettings(
        take_profit_pct=float(check.get("ALPACA_TAKE_PROFIT_PCT_default", 0.06)),
        bracket_enabled=bool(check.get("ALPACA_BRACKET_ENABLED_default", True)),
        threshold_pct_of_intents=float(check.get("threshold_pct_of_intents", 5.0)),
        perimeter=str(check.get("measurement_perimeter", "whole_share_non_fractionable")),
    )


def take_profit_price(entry_price: float, pct: float) -> float:
    """Prezzo limite del TP, con lo stesso arrotondamento del codice live.

    `round(price * (1 + pct), 2)` e' letterale da `portfolio_scheduler.py`: un
    tick di differenza sposta il verdetto su un intento che sfiora la soglia,
    quindi la formula va copiata, non riderivata.
    """
    return round(entry_price * (1.0 + pct), 2)


def _row(
    lifecycle: P0Lifecycle,
    path: PricePath | None,
    settings: LiveTpSettings,
) -> dict[str, object]:
    base: dict[str, object] = {
        "intent_id": lifecycle.intent_id,
        "symbol": lifecycle.symbol,
        "d0": None if lifecycle.d0 is None else lifecycle.d0.isoformat(),
        "entry_price": lifecycle.entry_price,
        "fractionable": lifecycle.fractionable,
        "take_profit_price": None,
        "highest_high": None if path is None else path.highest_high,
        "outcome": OUTCOME_OUT_OF_PERIMETER,
    }

    if not settings.bracket_enabled:
        return base
    if lifecycle.fractionable is None:
        return {**base, "outcome": OUTCOME_FRACTIONABILITY_UNKNOWN}
    if lifecycle.fractionable:
        # Alpaca rifiuta il bracket sugli ordini frazionari: qui il TP live non
        # esiste, quindi P0 e runtime non divergono per questa causa.
        return base
    if lifecycle.entry_price <= 0:
        return {**base, "outcome": OUTCOME_ENTRY_PRICE_MISSING}

    trigger = take_profit_price(lifecycle.entry_price, settings.take_profit_pct)
    base["take_profit_price"] = trigger

    if path is None or path.highest_high is None:
        return {**base, "outcome": OUTCOME_PATH_MISSING}
    if lifecycle.exit_at is not None and _utc(path.observed_to) < _utc(
        lifecycle.exit_at
    ):
        # La finestra non copre tutta la vita dell'intento: il TP poteva essere
        # toccato nel pezzo che non abbiamo guardato.
        return {**base, "outcome": OUTCOME_PATH_INCOMPLETE}
    if _utc(path.observed_from) > _utc(lifecycle.entry_at):
        return {**base, "outcome": OUTCOME_PATH_INCOMPLETE}

    # Confronto inclusivo: un limit a 106.00 con massimo 106.00 e' eseguibile.
    # Escluderlo sottostimerebbe l'esposizione, che e' la direzione sbagliata
    # per un gate.
    touched = float(path.highest_high) >= trigger
    return {**base, "outcome": OUTCOME_TOUCHED if touched else OUTCOME_NOT_TOUCHED}


def assess_live_tp_exposure(
    lifecycles: Sequence[P0Lifecycle],
    price_paths: Mapping[str, PricePath],
    settings: LiveTpSettings,
) -> dict[str, object]:
    """Quanti intenti il TP live avrebbe toccato, e se P0 regge come benchmark.

    Il denominatore e' **tutti gli intenti**, come dice il contratto (`% degli
    intenti`), non i soli non frazionabili: usare il perimetro gonfierebbe la
    percentuale e farebbe scattare una ridefinizione di P0 che il contratto non
    chiede.
    """
    rows = [
        _row(lifecycle, price_paths.get(lifecycle.intent_id), settings)
        for lifecycle in lifecycles
    ]
    intents = len(rows)
    touched = sum(1 for row in rows if row["outcome"] == OUTCOME_TOUCHED)
    unknown = sum(1 for row in rows if row["outcome"] in _UNKNOWN_OUTCOMES)
    in_perimeter = sum(
        1
        for row in rows
        if row["outcome"] in {OUTCOME_TOUCHED, OUTCOME_NOT_TOUCHED}
    )

    pct = (touched / intents * 100.0) if intents else 0.0
    # Caso peggiore: ogni ignoto e' un tocco. Serve a sapere se il verdetto
    # potrebbe ribaltarsi quando i dati mancanti arriveranno.
    worst = ((touched + unknown) / intents * 100.0) if intents else 0.0
    exceeds = pct > settings.threshold_pct_of_intents
    worst_exceeds = worst > settings.threshold_pct_of_intents

    return {
        "perimeter": settings.perimeter,
        "denominator": "all_intents",
        "bracket_enabled": settings.bracket_enabled,
        "take_profit_pct": settings.take_profit_pct,
        "threshold_pct_of_intents": settings.threshold_pct_of_intents,
        "intents": intents,
        "in_perimeter": in_perimeter,
        "touched": touched,
        "unknown": unknown,
        "touched_pct_of_intents": pct,
        "worst_case_pct_of_intents": worst,
        "exceeds_threshold": exceeds,
        "worst_case_exceeds_threshold": worst_exceeds,
        # Con anche un solo ignoto il gate non e' deciso: un dato mancante puo'
        # ribaltarlo, e dichiararlo sotto soglia sarebbe una conclusione che i
        # dati non sostengono.
        "conclusive": unknown == 0 and intents > 0,
        "p0_remains_benchmark": not exceeds,
        "rows": rows,
    }


def assess_universe_perimeter(
    fractionability: Mapping[str, bool | None],
    settings: LiveTpSettings,
) -> dict[str, object]:
    """Quanti candidati S4 possono ricevere un bracket TP, a prescindere dal campione.

    E' evidenza piu' forte della misura sul campione: se **nessun** simbolo
    dell'universo e' non frazionabile, il TP live non puo' attaccarsi a un
    ordine S4, e la divergenza con P0 non esiste per costruzione invece che per
    fortuna. Un campione piccolo puo' non incontrare il caso; l'universo dice
    se il caso e' possibile.

    Un simbolo di fractionability ignota **non** svuota il perimetro: potrebbe
    essere proprio quello che lo riapre.
    """
    universe = len(fractionability)
    unknown = sum(1 for value in fractionability.values() if value is None)
    non_fractionable = sorted(
        symbol for symbol, value in fractionability.items() if value is False
    )

    if not settings.bracket_enabled:
        reason = "bracket_disabled"
        empty = True
    elif universe == 0:
        # Un universo vuoto non dimostra nulla: non e' una prova di assenza.
        reason = "empty_universe"
        empty = False
    elif unknown:
        reason = "fractionability_unknown"
        empty = False
    elif non_fractionable:
        reason = "non_fractionable_present"
        empty = False
    else:
        reason = "all_fractionable"
        empty = True

    return {
        "universe": universe,
        "unknown": unknown,
        "non_fractionable": len(non_fractionable),
        "non_fractionable_pct": (
            len(non_fractionable) / universe * 100.0 if universe else 0.0
        ),
        "non_fractionable_symbols": non_fractionable,
        "perimeter_structurally_empty": empty,
        "reason": reason,
    }
