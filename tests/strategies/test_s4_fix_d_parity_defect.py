"""#186 — broken QS-07 / FIX-D parity in `NewsDrivenTactical._signals_as_of`.

Il 2026-08-05 alle 14:22 (UTC) quattro posizioni S4 i cui segnali stale erano
stati ri-ammessi da FIX-D nello stesso ciclo (MCD/NVO/PFE/PLTR) sono state
chiuse con motivazione "[expired] S4 signal expired (age=19.9h > max_age=4h,
... no counter-signal found, position closed)". La frase descrive esattamente
la condizione che FIX-D usa per NON chiudere.

#184 (deployato ~2026-08-07) corregge solo l'etichetta → "unknown". #186 va
oltre: trova **perché** il peso era 0. Risposta: il filtro di freshness in
`strategy.py:167-169` (`generated_at >= ts - max_age`) viene applicato dentro
`_signals_as_of`, che l'orchestrator chiama su `signals_df` — e quel
`signals_df` contiene già i segnali preservati da FIX-D. Il filtro butta via
MCD/NVO/PFE/PLTR; il ranker vede solo DIS; il peso merged del simbolo scende
a 0 e `orchestrator.py:271-288` emette una SELL con `strategy_id="merged"`.
(`NewsDrivenTactical.__call__:101-114` fa la stessa cosa, ma è il path di
**backtest**: in live la SELL nasce nell'orchestrator.)

Lo stesso filtro è un deliberato backtest/live parity (QS-07, b4421f2) — non è
un bug di per sé, ed è indispensabile in backtest, dove nessuno ha già filtrato
`signals_df` a monte. Il difetto è che non distingue i due chiamanti: dopo
FIX-D il contratto di `signals_df` è "fresh **+ preserved**", e il filtro
riscrive una decisione di ammissione già presa da `_build_strategy_instance`.

Forma del fix (fuori scope qui per il freeze #171): un marcatore di provenienza
in `signals_df` — colonna booleana `fix_d_preserved` — che `_signals_as_of`
deve rispettare, lasciando **intatto** il filtro d'età per i segnali non
marcati (backtest). Questi test codificano esattamente quel contratto.

Struttura: 2 test verdi + 5 xfail(strict).

- verdi:  il bug-witness del ciclo 14:22 (oggi i marcati vengono scartati) e la
          guardia di backtest (i non marcati stale vengono ancora scartati —
          questo comportamento NON deve cambiare col fix).
- xfail:  il contratto post-fix (marcatore rispettato in `_signals_as_of` e,
          simbolo per simbolo, peso non nullo dal ranker). `strict=True`: se
          uno di questi passa, il fix è arrivato e il test va promosso a verde.

Per il freeze #171 non c'è fix nel codice — solo evidenza riproducibile.
Il fix è tracciato dall'issue separata #236.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical

_TS = datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)

_XFAIL_FIX = pytest.mark.xfail(
    strict=True, reason="#186 — fix blocked by freeze #171 (tracked in #236)",
)

# Il ciclo 14:22 del 2026-08-05, punto per punto: 1 fresh (DIS) + 4 segnali
# stale che `_preserve_stale_signals_for_open_positions` (FIX-D) ha ri-ammesso
# in `signals_df` — marcati qui con `fix_d_preserved=True`.
_CYCLE_14_22 = [
    {"symbol": "DIS", "score": 0.572, "confidence": 0.775,
     "age_h": 0.12, "fix_d_preserved": False},
    {"symbol": "NVO", "score": 0.656, "confidence": 0.85,
     "age_h": 19.62, "fix_d_preserved": True},
    {"symbol": "PFE", "score": 0.514, "confidence": 0.80,
     "age_h": 19.87, "fix_d_preserved": True},
    {"symbol": "MCD", "score": 0.393, "confidence": 0.725,
     "age_h": 19.87, "fix_d_preserved": True},
    {"symbol": "PLTR", "score": 0.383, "confidence": 0.675,
     "age_h": 18.87, "fix_d_preserved": True},
]

_PRESERVED = [r for r in _CYCLE_14_22 if r["fix_d_preserved"]]


def _df(rows: list[dict]) -> pd.DataFrame:
    """signals_df come lo costruisce `_build_strategy_instance`, con in più la
    colonna di provenienza `fix_d_preserved` che il fix dovrà propagare."""
    return pd.DataFrame([
        {
            "symbol": r["symbol"],
            "score": r["score"],
            "confidence": r["confidence"],
            "generated_at": _TS - timedelta(hours=r["age_h"]),
            "fix_d_preserved": r["fix_d_preserved"],
        }
        for r in rows
    ])


def _strategy(rows: list[dict]) -> NewsDrivenTactical:
    return NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=_df(rows))


# ─────────────────────────────────────────────────────────────────────────────
# Verdi — comportamento osservato oggi in produzione.
# ─────────────────────────────────────────────────────────────────────────────


def test_2026_08_05_14_22_fix_d_preserved_signals_are_dropped_before_ranking():
    """Bug witness del ciclo 14:22: 4 preserved + 1 fresh → sopravvive solo DIS.

    Il marcatore `fix_d_preserved` è già nel DataFrame, ma `_signals_as_of` non
    lo guarda: i 4 escono dal ranker, il peso merged va a 0 e l'orchestrator
    (`orchestrator.py:271-288`) li vende. Questo test resta verde finché il
    difetto è in produzione.
    """
    survivors = {r.symbol for r in _strategy(_CYCLE_14_22)._signals_as_of(_TS)}

    assert survivors == {"DIS"}, (
        f"atteso il comportamento rotto (solo DIS sopravvive), got {sorted(survivors)}: "
        f"se sono sopravvissuti anche i preserved il fix #236 è stato applicato e "
        f"i test xfail di questo modulo vanno promossi a verdi"
    )


def test_age_filter_still_drops_unmarked_stale_signals():
    """Guardia di backtest: senza marcatore, il filtro d'età deve restare.

    In backtest nessuno filtra `signals_df` a monte, quindi QS-07 è l'unica
    difesa contro la contaminazione T0 (usare a un tick segnali che il live
    avrebbe scartato). Il fix #236 deve esentare **solo** i segnali marcati:
    questo test deve restare verde prima e dopo il fix.
    """
    rows = [
        {"symbol": "DIS", "score": 0.572, "confidence": 0.775,
         "age_h": 0.12, "fix_d_preserved": False},
        {"symbol": "MCD", "score": 0.393, "confidence": 0.725,
         "age_h": 19.87, "fix_d_preserved": False},  # stale, NON preservato
    ]
    survivors = {r.symbol for r in _strategy(rows)._signals_as_of(_TS)}

    assert survivors == {"DIS"}, (
        f"un segnale stale senza `fix_d_preserved` deve essere scartato dal filtro "
        f"QS-07 (parità backtest/live, strategy.py:167-169), got {sorted(survivors)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# xfail(strict) — contratto post-fix: `_signals_as_of` rispetta il marcatore.
# ─────────────────────────────────────────────────────────────────────────────


@_XFAIL_FIX
def test_signals_as_of_honours_fix_d_preserved_marker():
    """Sul ciclo 14:22 completo, tutti e 5 i segnali devono sopravvivere.

    `fix_d_preserved=True` significa "il chiamante ha già deciso di ammettere
    questo segnale, sapendo che è vecchio". `_signals_as_of` non ha autorità
    per sovrascrivere quella decisione basandosi solo sull'orologio.
    """
    expected = {r["symbol"] for r in _CYCLE_14_22}
    survivors = {r.symbol for r in _strategy(_CYCLE_14_22)._signals_as_of(_TS)}

    assert survivors == expected, (
        f"atteso {sorted(expected)} (1 fresh + 4 marcati fix_d_preserved), "
        f"got {sorted(survivors)}: il filtro d'età a strategy.py:167-169 scarta "
        f"i segnali che FIX-D ha appena ri-ammesso in signals_df"
    )


@_XFAIL_FIX
@pytest.mark.parametrize(
    "row", _PRESERVED, ids=[r["symbol"] for r in _PRESERVED],
)
def test_fix_d_preserved_signal_keeps_non_zero_weight(row):
    """Check funzionale, simbolo per simbolo: dal marcatore al peso.

    Complementare al test precedente, che si ferma a `_signals_as_of`: qui si
    verifica che il segnale marcato arrivi fino a `compute_target_weights`, cioè
    che il ranker gli assegni un peso invece di lasciarlo fuori dal target (la
    condizione che in live produce la SELL a `orchestrator.py:271-288`).
    """
    strat = _strategy([row])
    weights = strat.compute_target_weights(strat._signals_as_of(_TS), as_of=_TS)

    assert weights.get(row["symbol"], 0.0) > 0, (
        f"{row['symbol']} (age={row['age_h']}h, fix_d_preserved=True) esce dal ranker "
        f"con peso 0: il filtro QS-07 a strategy.py:167-169 lo scarta prima del ranking, "
        f"quindi il peso merged va a 0 e la posizione viene venduta"
    )
