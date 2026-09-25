"""Rami controfattuali del replay uscite (#614) — pre-registrazione della misura.

Pre-registrazione: docs/evidence/PREREGISTRAZIONE_MISURA_CONTROFATTUALE_USCITE_2026-09-24.md
§3: soppressione delle vendite ``portfolio_sell``, vendita ipotetica a D+N, vincolo di
budget sui fill reali restanti (buy saltato / sell troncata), estensioni censurate.
"""
from datetime import date, datetime, timezone

import pytest

from src.backtest.engine.exit_counterfactual import (
    TOLLERANZA_BUDGET,
    FillConMotivo,
    replay_ramo,
)
from src.backtest.engine.exit_replay import replay
from src.backtest.engine.types import OrderSide

# --- mondo sintetico -------------------------------------------------------
# 5 sedute, X e Y. Cash iniziale 100, X detenuta in 10 pezzi a 100.
D1, D2, D3, D4, D5 = (date(2026, 8, g) for g in (3, 4, 5, 6, 7))
SEDUTE = {g: datetime(g.year, g.month, g.day, 20, tzinfo=timezone.utc) for g in (D1, D2, D3, D4, D5)}
CLOSES = {
    D1: {"X": 100.0, "Y": 100.0},
    D2: {"X": 100.0, "Y": 101.0},
    D3: {"X": 105.0, "Y": 102.0},
    D4: {"X": 110.0, "Y": 103.0},
    D5: {"X": 120.0, "Y": 104.0},
}


def _sell(simbolo, qty, prezzo, giorno, motivo=None, ora=15):
    return FillConMotivo(
        timestamp=datetime(giorno.year, giorno.month, giorno.day, ora, tzinfo=timezone.utc),
        symbol=simbolo, side=OrderSide.SELL, quantity=qty, fill_price=prezzo,
        exit_reason=motivo,
    )


def _buy(simbolo, qty, prezzo, giorno, ora=16):
    return FillConMotivo(
        timestamp=datetime(giorno.year, giorno.month, giorno.day, ora, tzinfo=timezone.utc),
        symbol=simbolo, side=OrderSide.BUY, quantity=qty, fill_price=prezzo,
    )


def _prezza(simbolo, qty, close, campana):
    """Pricing finto ma non gratis: commissione fissa 0,50, prezzo = close."""
    from src.backtest.engine.exit_replay import BrokerFill

    return BrokerFill(
        timestamp=campana, symbol=simbolo, side=OrderSide.SELL,
        quantity=qty, fill_price=close, commission=0.5,
    )


def _replay(fills, orizzonte, start_cash=100.0):
    return replay_ramo(
        start_qty={"X": 10.0},
        start_cash=start_cash,
        start_closes={"X": 100.0},
        fills=fills,
        closes_by_day=CLOSES,
        session_closes=SEDUTE,
        orizzonte=orizzonte,
        prezza_vendita=_prezza,
    )


FILLS_A = [
    _sell("X", 10.0, 100.0, D1, motivo="portfolio_sell"),
    _buy("Y", 9.0, 100.0, D1),
]


class TestSoppressioneERitardo:
    def test_vendita_portfolio_sell_ritardata_di_n_sedute(self) -> None:
        """H_2: X resta detenuta fino alla campana di D3, poi venduta dal pricer."""
        esito, pf = _replay(FILLS_A, orizzonte=2)
        assert len(esito.vendite_ritardate) == 1
        v = esito.vendite_ritardate[0]
        assert v.simbolo == "X"
        assert v.quantita_soppressa == pytest.approx(10.0)
        assert v.seduta_originale == D1
        assert v.seduta_uscita == D3
        # la vendita ipotetica esiste, un solo fill, alla campana di D3 a prezzo close
        assert len(esito.fill_ipotetici) == 1
        ip = esito.fill_ipotetici[0]
        assert ip.symbol == "X"
        assert ip.quantity == pytest.approx(10.0)
        assert ip.fill_price == pytest.approx(105.0)
        assert ip.commission == pytest.approx(0.5)
        assert ip.timestamp == SEDUTE[D3]
        # il sell reale NON è stato applicato: nessun costo di commissione reale,
        # e il cash finale riflette la vendita ipotetica (105*10 - 0.5) + 100 iniziali
        assert esito.serie[-1].cash == pytest.approx(100.0 + 1050.0 - 0.5)
        assert esito.serie[-1].equity == pytest.approx(1149.5)

    def test_serie_giorni_intermedi_tiene_la_posizione(self) -> None:
        esito, _ = _replay(FILLS_A, orizzonte=2)
        # D1 e D2: X valsa 1000, cash 100 -> equity 1100, valore posizioni 1000
        assert esito.serie[0].valore_posizioni == pytest.approx(1000.0)
        assert esito.serie[1].valore_posizioni == pytest.approx(1000.0)
        # D3: vendita a campana, da D4 solo cash
        assert esito.serie[2].cash == pytest.approx(1149.5)
        assert esito.serie[3].valore_posizioni == pytest.approx(0.0)


class TestDisplacement:
    def test_buy_non_coperto_dal_budget_saltato_e_loggato(self) -> None:
        """Il ricavato della vendita soppressa non c'è: l'acquisto sostitutivo
        salta (artefatto 2: il displacement entra qui, per costruzione)."""
        esito, pf = _replay(FILLS_A, orizzonte=2)
        assert pf.position_of("Y") is None
        assert len(esito.buy_saltati) == 1
        assert esito.buy_saltati[0].simbolo == "Y"
        assert esito.buy_saltati[0].quantita == pytest.approx(9.0)

    def test_buy_entro_la_tolleranza_applicato(self) -> None:
        """Tolleranza di budget 1,00 $: un buy che sfora il cash di meno di così
        passa (arrotondamenti del paper), oltre no."""
        fills = [
            _sell("X", 10.0, 100.0, D1, motivo="portfolio_sell"),
            # costo 100,90 contro cash 100: dentro la tolleranza
            _buy("Y", 1.009, 100.0, D1),
        ]
        esito, pf = _replay(fills, orizzonte=2)
        assert pf.position_of("Y") is not None
        assert esito.buy_saltati == ()

    def test_sell_reale_su_posizione_mai_comprata_sparecchia(self) -> None:
        """La vendita di Y (altro motivo) arriva in un mondo dove Y non è mai
        stata comprata: troncata a zero, registrata."""
        fills = FILLS_A + [_sell("Y", 9.0, 102.0, D3, motivo="hold_minimum_expiry")]
        esito, pf = _replay(fills, orizzonte=2)
        assert pf.position_of("Y") is None
        assert len(esito.sell_troncate) == 1
        assert esito.sell_troncate[0].simbolo == "Y"


class TestCensuraECap:
    def test_estensione_oltre_la_finestra_censurata(self) -> None:
        """portfolio_sell all'ultima seduta, N=2: la vendita non può avvenire,
        la posizione resta marcata all'ultimo close."""
        fills = [_sell("X", 10.0, 120.0, D5, motivo="portfolio_sell")]
        esito, pf = _replay(fills, orizzonte=2)
        assert esito.estensioni_censurate == 1
        assert esito.fill_ipotetici == ()
        assert pf.position_of("X") is not None
        assert esito.serie[-1].valore_posizioni == pytest.approx(10 * 120.0)

    def test_vendita_ipotetica_capped_alla_qty_detenuta(self) -> None:
        """Tra D e D+N una vendita reale (altro motivo) riduce X: la vendita
        ipotetica vende min(qty soppressa, qty detenuta), mai corto."""
        fills = [
            _sell("X", 10.0, 100.0, D1, motivo="portfolio_sell"),
            _sell("X", 6.0, 100.0, D2, motivo="sentiment_reversal"),
        ]
        esito, pf = _replay(fills, orizzonte=2)
        # detenute 4 alla D3: vende 4 @105, commissione 0.5
        assert len(esito.fill_ipotetici) == 1
        assert esito.fill_ipotetici[0].quantity == pytest.approx(4.0)
        assert pf.position_of("X") is None
        assert esito.serie[-1].cash == pytest.approx(100.0 + 600.0 + 4 * 105.0 - 0.5)


class TestControlloEInvarianti:
    def test_orizzonte_zero_riproduce_il_replay_del_cancello(self) -> None:
        """Il ramo di controllo (nessuna soppressione) deve coincidere col replay
        del cancello: stesse convenzioni di mark, stessa contabilità."""
        serie_gate, _ = replay(
            start_qty={"X": 10.0}, start_cash=100.0, start_closes={"X": 100.0},
            fills=FILLS_A, closes_by_day=CLOSES, session_closes=SEDUTE,
        )
        esito, _ = _replay(FILLS_A, orizzonte=0)
        assert len(esito.serie) == len(serie_gate)
        for mio, gate in zip(esito.serie, serie_gate):
            assert mio.giorno == gate.giorno
            assert mio.equity == pytest.approx(gate.equity)
            assert mio.cash == pytest.approx(gate.cash)
            assert mio.valore_posizioni == pytest.approx(gate.valore_posizioni)

    def test_vendita_senza_etichetta_non_e_portfolio_sell(self) -> None:
        """Solo le vendite etichettate portfolio_sell vengono ritardate: una
        vendita senza etichetta resta reale (§2: fail-closed sull'etichetta)."""
        fills = [_sell("X", 10.0, 100.0, D1, motivo=None)]
        esito, pf = _replay(fills, orizzonte=2)
        assert esito.vendite_ritardate == ()
        assert pf.position_of("X") is None
        assert esito.serie[0].cash == pytest.approx(1100.0)


class TestMetriche:
    def test_capitale_impiegato_e_cash_drag(self) -> None:
        """Q2-rec-4: senza questi due numeri l'equity terminale è ambigua."""
        esito, _ = _replay(FILLS_A, orizzonte=2)
        # H_2: posizioni in D1 (1000/1100) e D2 (1000/1100), cash dal D3
        capitale = (1000 / 1100 + 1000 / 1100 + 0.0 + 0.0 + 0.0) / 5
        drag = (100 / 1100 + 100 / 1100 + 1.0 + 1.0 + 1.0) / 5
        assert esito.capitale_medio_impiegato == pytest.approx(capitale)
        assert esito.cash_drag_medio == pytest.approx(drag)
        assert esito.equity_finale == pytest.approx(1149.5)

    def test_tolleranza_budget_dichiarata(self) -> None:
        assert TOLLERANZA_BUDGET == 1.0


class TestPolvereDiVirgolaMobile:
    def test_sell_con_differenza_di_1e15_non_e_truncation(self) -> None:
        """Sui dati reali il fill broker porta quantita' che differiscono dal
        detenuto per ~1e-15: la vendita e' piena, non va loggata come troncata
        (6 falsi eventi nel controllo, tutti polvere)."""
        fills = [
            FillConMotivo(
                timestamp=datetime(D1.year, D1.month, D1.day, 14, tzinfo=timezone.utc),
                symbol="X", side=OrderSide.BUY, quantity=16.669511,
                fill_price=100.0,
            ),
            FillConMotivo(
                timestamp=datetime(D1.year, D1.month, D1.day, 16, tzinfo=timezone.utc),
                symbol="X", side=OrderSide.SELL,
                quantity=16.669511 + 3.55e-15,
                fill_price=101.0, exit_reason="sentiment_reversal",
            ),
        ]
        esito, pf = replay_ramo(
            start_qty={}, start_cash=2000.0, start_closes={"X": 100.0},
            fills=fills, closes_by_day=CLOSES, session_closes=SEDUTE,
            orizzonte=2, prezza_vendita=_prezza,
        )
        assert esito.sell_troncate == ()
        assert pf.position_of("X") is None
        # vendita piena accreditata: 16.669511 * 101
        assert esito.serie[0].cash == pytest.approx(2000.0 - 1666.9511 + 16.669511 * 101.0)
