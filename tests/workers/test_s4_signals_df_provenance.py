"""#236 — il marcatore di provenienza FIX-D arriva fino a `signals_df`.

`_signals_as_of` sa esentare dal filtro d'età i segnali marcati `fix_d_preserved`
(vedi tests/strategies/test_s4_fix_d_parity_defect.py). Ma il marcatore deve
esistere: il ciclo di portfolio costruisce `signals_df` a partire dalla lista che
`_preserve_stale_signals_for_open_positions` ha appena arricchito, e se la colonna
non viene scritta il fix è inerte in produzione — verde nei test, senza effetto sul
comportamento reale.

Seam sotto test: `_signals_to_dataframe`, funzione pura estratta dal corpo del
ciclo proprio per poter verificare questa propagazione senza montare uno scheduler.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.workers.portfolio_scheduler import (
    _preserve_stale_signals_for_open_positions,
    _signals_to_dataframe,
)

_TS = datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc)


def _sig(symbol: str, score: float, age_h: float):
    """Segnale con la superficie che il DataFrame legge."""
    return SimpleNamespace(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="",
        model_id="glm52",
        ensemble_std=0.05,
        fallback_used=False,
        generated_at=_TS - timedelta(hours=age_h),
        signal_id=1,
    )


class TestMarcatoreDiProvenienza:
    def test_un_segnale_preservato_da_fix_d_e_marcato(self):
        fresh = [_sig("DIS", 0.572, 0.12)]
        stale = [_sig("MCD", 0.393, 19.87)]
        ammessi = _preserve_stale_signals_for_open_positions(fresh, stale, {"MCD"})

        df = _signals_to_dataframe(ammessi, preserved={"MCD"})

        assert bool(df.loc[df["symbol"] == "MCD", "fix_d_preserved"].iloc[0]) is True

    def test_un_segnale_fresh_non_e_marcato(self):
        df = _signals_to_dataframe([_sig("DIS", 0.572, 0.12)], preserved=set())

        assert bool(df.loc[df["symbol"] == "DIS", "fix_d_preserved"].iloc[0]) is False

    def test_la_colonna_esiste_sempre_anche_senza_preservati(self):
        """Senza la colonna `_signals_as_of` non saprebbe distinguere «non
        preservato» da «informazione assente», e ricadrebbe sul filtro d'età per
        tutti — cioè sul difetto."""
        df = _signals_to_dataframe([_sig("DIS", 0.572, 0.12)], preserved=set())

        assert "fix_d_preserved" in df.columns

    def test_le_colonne_esistenti_restano(self):
        """Il DataFrame è consumato dal ranker: aggiungere una colonna non deve
        togliere quelle che c'erano."""
        df = _signals_to_dataframe([_sig("DIS", 0.572, 0.12)], preserved=set())

        for colonna in (
            "symbol", "score", "confidence", "reasoning", "model_id",
            "ensemble_std", "fallback_used", "generated_at", "signal_id",
        ):
            assert colonna in df.columns, f"colonna {colonna} persa"


class TestCatenaCompleta:
    def test_dal_ciclo_14_22_il_preservato_sopravvive_al_filtro_d_eta(self):
        """L'incidente del 2026-08-05, end-to-end attraverso il produttore reale.

        Non usa un DataFrame costruito a mano come i test di strategia: parte dai
        segnali, passa da FIX-D e dal produttore, e verifica che il preservato
        arrivi vivo dall'altra parte di `_signals_as_of`. È il test che si
        romperebbe se qualcuno togliesse la colonna dal produttore lasciando
        intatto il filtro.
        """
        from src.strategies.s4.config import S4Config
        from src.strategies.s4.strategy import NewsDrivenTactical

        fresh = [_sig("DIS", 0.572, 0.12)]
        stale = [_sig("NVO", 0.656, 19.62), _sig("PFE", 0.514, 19.87)]
        ammessi = _preserve_stale_signals_for_open_positions(fresh, stale, {"NVO", "PFE"})
        preserved = {s.symbol for s in ammessi if s in stale}

        df = _signals_to_dataframe(ammessi, preserved=preserved)
        strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)

        sopravvissuti = {r.symbol for r in strat._signals_as_of(_TS)}
        assert sopravvissuti == {"DIS", "NVO", "PFE"}
