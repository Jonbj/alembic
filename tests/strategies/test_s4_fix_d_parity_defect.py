"""#186 — broken QS-07 / FIX-D parity in `NewsDrivenTactical._signals_as_of`.

Il 2026-08-05 alle 14:22 (UTC) quattro posizioni S4 i cui segnali stale erano
stati ri-ammessi da FIX-D nello stesso ciclo (MCD/NVO/PFE/PLTR) sono state
chiuse con motivazione "[expired] S4 signal expired (age=19.9h > max_age=4h,
... no counter-signal found, position closed". La frase descrive esattamente
la condizione che FIX-D usa per NON chiudere.

#184 (merged) corregge solo l'etichetta → "unknown". #186 va oltre: trova
**perché** il peso era 0. Risposta: la filter di freshness in
`strategy.py:167-169` (`generated_at >= ts - max_age`) viene applicata nel
metodo chiamato dall'orchestrator su `signals_df`, e quel `signals_df`
contiene già i segnali preservati da FIX-D. Il filtro butta via MCD/NVO/PFE/
PLTR; il ranker vede solo DIS; ogni simbolo non in `target_weights` viene
venduto da `NewsDrivenTactical.__call__:101-114`.

La stessa filter è un deliberato backtest/live parity (QS-07, b4421f2) — non
è un bug di per sé, ma non riconosce il contratto che `_build_strategy_instance`
ha già onorato a monte. Il naming (`_signals_as_of`) e la sua vicinanza al
filter obbligano a leggerlo come parity check, non come ri-filtro.

Questi test falliscono oggi: la prima coppia codifica il comportamento
osservato in produzione (4 SELL non volute), la seconda codifica il
comportamento atteso (FIX-D preserved signals devono sopravvivere a
`_signals_as_of` quando il segnale è già passato il filtro a monte).

Per il freeze #171 non c'è fix nel codice — solo evidenza riproducibile.
Il fix è un'issue separata (`#186 → fix`) da aprire al termine del freeze.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical


_TS = datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Caso di riferimento: 14:22 del 2026-08-05, replicato punto per punto.
# ─────────────────────────────────────────────────────────────────────────────


def test_2026_08_05_14_22_fix_d_preserved_signals_are_dropped_before_ranking():
    """Replica del ciclo 14:22: 4 stale (preserved by FIX-D) + 1 fresh (DIS).

    In produzione il ranker vede solo DIS, gli altri 4 finiscono in
    `target_weights` = {} → SELL. Conferma che il path di uscita non passa
    da FIX-D (FIX-D li preserva a monte, ma la freshness filter a
    strategy.py:167-169 li scarta di nuovo).
    """
    df = _df([
        {"symbol": "DIS",  "score": 0.572, "confidence": 0.775,
         "generated_at": _TS - timedelta(hours=0,  minutes=7)},   # fresh
        {"symbol": "NVO",  "score": 0.656, "confidence": 0.85,
         "generated_at": _TS - timedelta(hours=19, minutes=37)},  # FIX-D preserved
        {"symbol": "PFE",  "score": 0.514, "confidence": 0.80,
         "generated_at": _TS - timedelta(hours=19, minutes=52)},  # FIX-D preserved
        {"symbol": "MCD",  "score": 0.393, "confidence": 0.725,
         "generated_at": _TS - timedelta(hours=19, minutes=52)},  # FIX-D preserved
        {"symbol": "PLTR", "score": 0.383, "confidence": 0.675,
         "generated_at": _TS - timedelta(hours=18, minutes=52)},  # FIX-D preserved
    ])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)
    survivors = {r.symbol for r in strat._signals_as_of(_TS)}

    # Comportamento attuale (broken): solo DIS sopravvive.
    assert survivors == {"DIS"}, (
        f"se FIX-D preservation è onorata nel strategy, expected DIS+MCD+NVO+PFE+PLTR, "
        f"got {sorted(survivors)} — il filter a strategy.py:167-169 scarta i segnali "
        f"che _build_strategy_instance ha appena preservato"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Comportamento atteso: _signals_as_of non deve re-filtrare ciò che il
# costruttore (portfolio_scheduler._build_strategy_instance) ha già filtrato.
# Un segnale è in `signals_df` perché ha passato FIX-D — il downstream
# strategy non ha informazione per distinguerlo da un fresh, quindi al
# momento si affida al timestamp. Il fix sarà un marcatore di provenienza
# (FIX_D_PRESERVED) o un canale di segnali separato. Per ora il test
# documenta l'expected.
# ─────────────────────────────────────────────────────────────────────────────


def test_signals_as_of_preserves_signals_already_admitted_by_caller():
    """Il filter QS-07 presume che signals_df = "segnali freschi" — ma FIX-D
    delega al chiamante la decisione di ammissione, e quindi dopo FIX-D
    signals_df = "segnali che hanno passato fresh + preserved (FIX-D)".

    Se il chiamante ha deciso di ammettere un segnale, lo strategy non ha
    alcun motivo per scartarlo di nuovo basandosi solo sull'orologio.
    """
    df = _df([
        {"symbol": "MCD", "score": 0.393, "confidence": 0.725,
         "generated_at": _TS - timedelta(hours=19, minutes=52)},
    ])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)
    survivors = {r.symbol for r in strat._signals_as_of(_TS)}

    # La presenza di MCD in `signals_df` È il fatto che il chiamante l'ha
    # promosso (FIX-D). Il filter a valle non ha autorità di sovrascriverlo.
    assert "MCD" in survivors, (
        "segnale presente in signals_df deve passare _signals_as_of: il filter "
        "a strategy.py:167-169 contraddice il fatto che FIX-D lo ha ammesso"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Parametrize sui 4 simboli del caso 14:22 del 2026-08-05.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("symbol,score,confidence,age_h", [
    ("MCD",  0.393, 0.725, 19.87),
    ("NVO",  0.656, 0.85,  19.62),
    ("PFE",  0.514, 0.80,  19.87),
    ("PLTR", 0.383, 0.675, 18.87),
])
def test_fix_d_preserved_signal_loses_zero_weight(symbol, score, confidence, age_h):
    """Ognuno dei 4 simboli del 14:22, da solo, deve entrare in target_weights.

    Questo è il check funzionale del fix: in isolamento, dopo FIX-D,
    lo strategy deve poterli riclassificare. Con il filter QS-07 attivo,
    ognuno esce dal ranker e diventa un SELL.
    """
    df = _df([{
        "symbol": symbol,
        "score": score,
        "confidence": confidence,
        "generated_at": _TS - timedelta(hours=age_h),
    }])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)
    weights = strat.compute_target_weights(
        strat._signals_as_of(_TS), as_of=_TS,
    )

    assert symbol in weights, (
        f"{symbol} era nel signals_df (ammesso dal chiamante) ma esce dal ranker "
        f"con weight 0%: il segnale preservato da FIX-D è stato scartato dal "
        f"filter QS-07 a strategy.py:167-169"
    )
