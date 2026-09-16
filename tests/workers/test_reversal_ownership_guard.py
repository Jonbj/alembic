"""Il guard di precedenza sulle uscite #182: sentiment_reversal chiude solo S4.

Decisione 2026-08-22 (opzione a) + deroga al freeze 2026-08-25: S4 puo' vietare
un ingresso, non puo' forzare un'uscita. Concretamente `sentiment_reversal` non
e' piu' titolo sufficiente a chiudere una posizione che S4 non ha aperto.

La misura del 2026-08-11 in issue: 22 uscite `sentiment_reversal` su 22 hanno
liquidato core o legacy (−$350,90, 58% delle perdite realizzate della finestra);
zero hanno toccato posizioni di S4. Sulle posizioni proprie la leva resta.

La proprieta' si legge da `trades.stop_strategy` (popolato dal 2026-07-13).
In dubbio non si chiude: la direzione di errore e' fail-closed, coerente con
l'asimmetria di danno che giustifica la regola.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.workers.portfolio_scheduler import (
    _filter_reversal_sells_by_ownership,
    _record_reversal_vetoes,
    _reversal_veto_key,
)


def _trade(symbol: str, stop_strategy: str | None) -> dict:
    return {"symbol": symbol, "stop_strategy": stop_strategy}


def _candidate(symbol: str, score: float = -0.5, signal_id: int = 42) -> dict:
    return {symbol: {"score": score, "signal_id": signal_id, "identity": str(signal_id)}}


class TestFiltroProprieta:
    """I tre casi della DoD: S4 chiude, S1 no, legacy/non attribuita no."""

    def test_posizione_s4_resta_chiudibile(self) -> None:
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("SOXX"), [_trade("SOXX", "S4")]
        )
        assert "SOXX" in allowed
        assert vetoed == []

    def test_posizione_s1_non_viene_chiusa(self) -> None:
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("CAT"), [_trade("CAT", "S1")]
        )
        assert allowed == {}
        assert [v["symbol"] for v in vetoed] == ["CAT"]

    def test_posizione_legacy_non_viene_chiusa(self) -> None:
        """stop_strategy vuoto/None = coorte legacy: nessuna attribuzione pulita,
        quindi nessuna chiusura (49 righe exit_reason vuote e 16 LEGACY_FLATTEN
        esistono davvero nel libro)."""
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("MU"), [_trade("MU", None)]
        )
        assert allowed == {}
        assert vetoed[0]["owner"] == "legacy"

    def test_simbolo_senza_righe_trades_aperte_non_viene_chiuso(self) -> None:
        """Posizione al broker ma nessuna riga trades aperta: non attribuita."""
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("XLK"), []
        )
        assert allowed == {}
        assert vetoed[0]["owner"] == "non_attribuita"

    def test_attribuzione_non_disponibile_veta_tutto(self) -> None:
        """DB trades illeggibile (open_trades=None): non si puo' confermare che
        S4 possiede nulla, quindi non si chiude nulla. Fail-closed."""
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("SOXX"), None
        )
        assert allowed == {}
        assert vetoed[0]["owner"] == "non_leggibile"

    def test_simbolo_con_trade_s1_e_s4_aperti_viene_vetato(self) -> None:
        """Il force-sell liquida tutta la quantita' a broker: se S1 detiene
        qualunque parte del nome, chiuderlo liquiderebbe anche quella."""
        allowed, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("TSM"),
            [_trade("TSM", "S4"), _trade("TSM", "S1")],
        )
        assert allowed == {}
        assert vetoed[0]["owner"] == "S1+S4"

    def test_il_veto_porta_score_e_segnale_per_la_riga_skip(self) -> None:
        _, vetoed = _filter_reversal_sells_by_ownership(
            _candidate("CAT", score=-0.573, signal_id=3861),
            [_trade("CAT", "S1")],
        )
        assert vetoed[0]["score"] == -0.573
        assert vetoed[0]["signal_id"] == 3861
        assert vetoed[0]["identity"] == "3861"
        assert vetoed[0]["owner"] == "S1"


class TestChiaveIdempotenza:
    """Una riga per segnale, non una per ciclo (stesso schema di #231)."""

    def test_la_chiave_e_simbolo_piu_identita(self) -> None:
        assert _reversal_veto_key("SOXX", "3861") == "SOXX|3861"

    def test_segnali_diversi_sullo_stesso_simbolo_sono_veti_diversi(self) -> None:
        assert _reversal_veto_key("SOXX", "3861") != _reversal_veto_key("SOXX", "3900")


class TestScritturaDellaRiga:
    def _pg(self):
        pg = MagicMock()
        pg.write_execution_decision = MagicMock(return_value=1)
        return pg

    def _veto(self, **over):
        v = {"symbol": "CAT", "owner": "S1", "score": -0.573,
             "signal_id": 3861, "identity": "3861"}
        v.update(over)
        return v

    def test_scrive_una_riga_skip_per_il_veto(self) -> None:
        pg = self._pg()
        _record_reversal_vetoes(pg, [self._veto()], gia_registrati=set(), regime_mult=1.0)
        assert pg.write_execution_decision.call_count == 1
        kw = pg.write_execution_decision.call_args.kwargs
        assert kw["symbol"] == "CAT"
        assert kw["signal_id"] == 3861
        assert kw["signal_score"] == -0.573

    def test_la_decisione_non_e_un_sell(self) -> None:
        """Una riga SELL per un'uscita che non e' stata eseguita sarebbe il difetto
        che questo guard esiste per prevenire, al contrario."""
        pg = self._pg()
        _record_reversal_vetoes(pg, [self._veto()], gia_registrati=set(), regime_mult=1.0)
        decisione = pg.write_execution_decision.call_args.kwargs["decision"]
        assert decisione != "SELL"
        assert decisione.startswith("SKIP")
        assert len(decisione) <= 20, "la colonna decision e' varchar(20)"

    def test_la_ragione_dice_proprietario_e_score(self) -> None:
        pg = self._pg()
        _record_reversal_vetoes(pg, [self._veto()], gia_registrati=set(), regime_mult=1.0)
        reason = pg.write_execution_decision.call_args.kwargs["reason"]
        assert "S1" in reason
        assert "-0.573" in reason or "0.573" in reason

    def test_veto_gia_registrato_non_si_riscrive(self) -> None:
        pg = self._pg()
        gia = {_reversal_veto_key("CAT", "3861")}
        _record_reversal_vetoes(pg, [self._veto()], gia_registrati=gia, regime_mult=1.0)
        assert pg.write_execution_decision.call_count == 0

    def test_una_sola_riga_anche_con_piu_veti(self) -> None:
        pg = self._pg()
        _record_reversal_vetoes(
            pg,
            [self._veto(), self._veto(symbol="XLK", owner="legacy", identity="77", signal_id=77)],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        assert pg.write_execution_decision.call_count == 2

    def test_non_solleva_mai(self) -> None:
        pg = self._pg()
        pg.write_execution_decision.side_effect = RuntimeError("db down")
        scritte = _record_reversal_vetoes(
            pg, [self._veto()], gia_registrati=set(), regime_mult=1.0
        )
        assert scritte == []


class _FakeRedis:
    """Redis in memoria per i soli comandi che l'idempotenza usa (schema #231)."""

    def __init__(self):
        self.set: dict[str, list[str]] = {}

    def smembers(self, k):
        return set(self.set.get(k, []))

    def sadd(self, k, *vals):
        self.set.setdefault(k, []).extend(vals)

    def expire(self, k, ttl):
        pass

    def close(self):
        pass


class TestIdempotenzaRedis:
    def test_mark_poi_get_restituisce_le_stesse_chiavi(self) -> None:
        from src.workers.portfolio_scheduler import (
            _get_logged_reversal_veto_keys,
            _mark_reversal_vetoes_logged,
        )
        fake = _FakeRedis()
        with patch("redis.Redis.from_url", return_value=fake):
            _mark_reversal_vetoes_logged(["SOXX|3861"], "redis://x")
            lette = _get_logged_reversal_veto_keys("redis://x")
        assert lette == {"SOXX|3861"}

    def test_get_fallito_restituisce_none_fail_open(self) -> None:
        """Redis giu' = meglio una riga duplicata che un veto invisibile."""
        from src.workers.portfolio_scheduler import _get_logged_reversal_veto_keys
        with patch("redis.Redis.from_url", side_effect=RuntimeError("down")):
            assert _get_logged_reversal_veto_keys("redis://x") is None


class TestApplicazioneNelCiclo:
    """_apply_reversal_ownership_guard e' quello che il ciclo chiama: filtro +
    log + righe SKIP + marcatura idempotente, con le tre direzioni di errore."""

    def _apply(self, candidati, trades, pg=None, fake=None):
        from src.workers.portfolio_scheduler import _apply_reversal_ownership_guard
        fake = fake if fake is not None else _FakeRedis()
        with patch("redis.Redis.from_url", return_value=fake):
            if pg is None:
                pg = MagicMock()
                pg.write_execution_decision = MagicMock(return_value=1)
            with patch("src.store.pg_store.PostgreSQLStore", return_value=pg):
                out = _apply_reversal_ownership_guard(
                    candidati, open_trades=trades,
                    regime_mult=1.0, redis_url="redis://x",
                )
        return out, pg

    def test_passa_solo_i_s4_e_scrive_le_righe_skip(self) -> None:
        candidati = {
            "SOXX": {"score": -0.42, "signal_id": 3861, "identity": "3861"},
            "CAT": {"score": -0.57, "signal_id": 99, "identity": "99"},
        }
        trades = [_trade("SOXX", "S4"), _trade("CAT", "S1")]
        out, pg = self._apply(candidati, trades)
        assert set(out) == {"SOXX"}
        assert pg.write_execution_decision.call_count == 1
        kw = pg.write_execution_decision.call_args.kwargs
        assert kw["symbol"] == "CAT"
        assert kw["decision"] == "SKIP_REVERSAL_OWNER"

    def test_un_veto_gia_registrato_non_si_riscrive(self) -> None:
        candidati = {"CAT": {"score": -0.57, "signal_id": 99, "identity": "99"}}
        fake = _FakeRedis()  # lo stesso Redis fra i due cicli
        out1, pg1 = self._apply(candidati, [_trade("CAT", "S1")], fake=fake)
        _, pg2 = self._apply(candidati, [_trade("CAT", "S1")], fake=fake)
        assert pg1.write_execution_decision.call_count == 1
        assert pg2.write_execution_decision.call_count == 0

    def test_db_delle_righe_skip_giu_non_perde_il_veto(self) -> None:
        """La scrittura della riga e' best-effort: il filtro deve reggere anche
        se il log non si puo' scrivere."""
        pg = MagicMock()
        pg.write_execution_decision = MagicMock(side_effect=RuntimeError("db down"))
        out, _ = self._apply(
            {"CAT": {"score": -0.57, "signal_id": 99, "identity": "99"}},
            [_trade("CAT", "S1")],
            pg=pg,
        )
        assert out == {}

    def test_attribuzione_non_disponibile_restituisce_vuoto(self) -> None:
        out, pg = self._apply(
            {"SOXX": {"score": -0.42, "signal_id": 3861, "identity": "3861"}},
            None,
        )
        assert out == {}
        assert pg.write_execution_decision.call_count == 1
        assert "non_leggibile" in pg.write_execution_decision.call_args.kwargs["reason"]

