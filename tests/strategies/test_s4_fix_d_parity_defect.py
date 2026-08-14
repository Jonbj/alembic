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
a 0 e `orchestrator.py:247-265` emette una SELL con `strategy_id="merged"`.
(`NewsDrivenTactical.__call__:101-114` fa la stessa cosa, ma è il path di
**backtest**: in live la SELL nasce nell'orchestrator.)

Lo stesso filtro è un deliberato backtest/live parity (QS-07, b4421f2) — non è
un bug di per sé, ed è indispensabile in backtest, dove nessuno ha già filtrato
`signals_df` a monte. Il difetto è che non distingue i due chiamanti: dopo
FIX-D il contratto di `signals_df` è "fresh **+ preserved**", e il filtro
riscrive una decisione di ammissione già presa da `_build_strategy_instance`.

Forma del fix: un marcatore di provenienza in `signals_df` — colonna booleana
`fix_d_preserved` — che `_signals_as_of` rispetta, lasciando **intatto** il
filtro d'età per i segnali non marcati (backtest). Questi test codificano
esattamente quel contratto.

**Fix applicato il 2026-08-14 (#236).** Questo modulo nasce come evidenza
riproducibile del difetto sotto il freeze #171, con 2 test verdi + 5
`xfail(strict)`; alla deroga d'ambito i cinque sono diventati `XPASS` e sono
stati promossi a verdi, e il bug-witness del ciclo 14:22 è stato invertito —
descriveva il comportamento rotto, ora è il test di regressione.

Struttura attuale: 7 test verdi, di cui due portano il peso del contratto:

- `test_age_filter_still_drops_unmarked_stale_signals` — il filtro d'età deve
  restare per i segnali NON marcati. È la metà del contratto che si romperebbe
  se qualcuno "semplificasse" il fix disattivando QS-07: in backtest nessuno
  filtra `signals_df` a monte, quindi quello è l'unica difesa contro la
  contaminazione T0.
- `test_2026_08_05_14_22_regression_...` — l'incidente storico, ora al
  contrario.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical

_TS = datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)

# #236 applicato il 2026-08-14: il marcatore `fix_d_preserved` esenta dal filtro
# d'età i segnali che FIX-D ha già ri-ammesso (strategy.py, `_signals_as_of`).
# I test che erano xfail(strict) sono stati promossi a verdi, come istruiva il
# docstring del modulo, e il test testimone del difetto è stato invertito:
# descriveva il comportamento rotto, ora descrive quello corretto.

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
# L'incidente storico e la guardia di backtest.
# ─────────────────────────────────────────────────────────────────────────────


def test_2026_08_05_14_22_regression_preserved_signals_reach_the_ranker():
    """Regressione sull'incidente del ciclo 14:22: nessuno dei 5 va perso.

    Prima di #236 questo test era il *testimone del difetto* e pretendeva
    `{"DIS"}`: il marcatore `fix_d_preserved` era già nel DataFrame ma
    `_signals_as_of` non lo guardava, quindi i 4 segnali che FIX-D aveva appena
    ri-ammesso uscivano dal ranker, il peso merged andava a 0 e l'orchestrator
    (`orchestrator.py:247-265`) vendeva la posizione senza alcun contro-segnale.

    Costo storico del meccanismo, dal DB: 30 uscite S4 a peso-zero in 40 giorni
    (27 etichettate `expired`, 3 `unknown`), fra cui SONY, HOOD, IBM e SPCX.
    IBM chiusa a −26,47 $ e risalita di 13,71 $ sulla stessa quantità dopo
    l'uscita.

    Ora pretende l'inverso, ed è il test che si romperebbe se il difetto
    tornasse: 1 fresh + 4 preserved = 5 sopravvissuti.
    """
    expected = {r["symbol"] for r in _CYCLE_14_22}
    survivors = {r.symbol for r in _strategy(_CYCLE_14_22)._signals_as_of(_TS)}

    assert survivors == expected, (
        f"atteso {sorted(expected)} (1 fresh + 4 marcati fix_d_preserved), "
        f"got {sorted(survivors)}: se manca uno dei preserved il filtro d'età di "
        f"`_signals_as_of` ha ripreso a scartare i segnali ri-ammessi da FIX-D, "
        f"cioè il difetto #236 è regredito"
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
# Il contratto: `_signals_as_of` rispetta il marcatore.
# ─────────────────────────────────────────────────────────────────────────────



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



@pytest.mark.parametrize(
    "row", _PRESERVED, ids=[r["symbol"] for r in _PRESERVED],
)
def test_fix_d_preserved_signal_keeps_non_zero_weight(row):
    """Check funzionale, simbolo per simbolo: dal marcatore al peso.

    Complementare al test precedente, che si ferma a `_signals_as_of`: qui si
    verifica che il segnale marcato arrivi fino a `compute_target_weights`, cioè
    che il ranker gli assegni un peso invece di lasciarlo fuori dal target (la
    condizione che in live produce la SELL a `orchestrator.py:247-265`).
    """
    strat = _strategy([row])
    weights = strat.compute_target_weights(strat._signals_as_of(_TS), as_of=_TS)

    assert weights.get(row["symbol"], 0.0) > 0, (
        f"{row['symbol']} (age={row['age_h']}h, fix_d_preserved=True) esce dal ranker "
        f"con peso 0: il filtro QS-07 a strategy.py:167-169 lo scarta prima del ranking, "
        f"quindi il peso merged va a 0 e la posizione viene venduta"
    )
