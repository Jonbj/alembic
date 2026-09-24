"""Cancello di riproducibilità del replay uscite (#614).

Pre-registrazione: docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md
§4 — con la regola invariata il replay deve riprodurre la storia realmente accaduta
entro ±2% sull'equity terminale, e la differenza va spiegata.
"""
from datetime import date, datetime, timezone

import pytest

from src.backtest.engine.exit_replay import (
    BrokerFill,
    evaluate_gate,
    initial_cash,
    ph_label_epoch,
    reconstruct_start_quantities,
    replay,
)
from src.backtest.engine.types import OrderSide


def fill(
    ts: str,
    symbol: str,
    side: OrderSide,
    qty: float,
    price: float,
) -> BrokerFill:
    return BrokerFill(
        timestamp=datetime.fromisoformat(ts),
        symbol=symbol,
        side=side,
        quantity=qty,
        fill_price=price,
    )


def ancoraggio() -> datetime:
    """Campana del 2026-08-03: fine della seduta di ancoraggio."""
    return datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc)


def chiusura_seduta(g: date) -> datetime:
    """Campana delle 20:00Z, quella del calendario Alpaca."""
    return datetime(g.year, g.month, g.day, 20, 0, tzinfo=timezone.utc)


class TestReconstructStartQuantities:
    def test_posizione_cresciuta_in_finestra(self) -> None:
        fills = [fill("2026-08-05T14:00:00+00:00", "A", OrderSide.BUY, 10, 50.0)]
        # attuale 13 = inizio 3 + buy 10
        assert reconstruct_start_quantities({"A": 13.0}, fills, after=ancoraggio()) == {"A": 3.0}

    def test_posizione_chiusa_e_riaperta(self) -> None:
        fills = [
            fill("2026-08-05T14:00:00+00:00", "A", OrderSide.SELL, 4, 50.0),
            fill("2026-08-07T14:00:00+00:00", "A", OrderSide.BUY, 2, 51.0),
        ]
        # attuale 2 = inizio 4 - sell 4 + buy 2
        assert reconstruct_start_quantities({"A": 2.0}, fills, after=ancoraggio()) == {"A": 4.0}

    def test_simbolo_completamente_chiuso_non_compare(self) -> None:
        fills = [
            fill("2026-08-05T14:00:00+00:00", "A", OrderSide.BUY, 5, 50.0),
            fill("2026-08-06T14:00:00+00:00", "A", OrderSide.SELL, 5, 49.0),
        ]
        assert reconstruct_start_quantities({}, fills, after=ancoraggio()) == {}

    def test_fill_prima_del_taglio_ignorato(self) -> None:
        fills = [
            fill("2026-08-01T14:00:00+00:00", "A", OrderSide.BUY, 10, 50.0),
            fill("2026-08-05T14:00:00+00:00", "A", OrderSide.BUY, 2, 51.0),
        ]
        # il buy del 01-08 e' prima del taglio: resta nello stato iniziale
        assert reconstruct_start_quantities({"A": 5.0}, fills, after=ancoraggio()) == {"A": 3.0}

    def test_fill_dopo_la_campana_dell_ancoraggio_e_in_finestra(self) -> None:
        fills = [
            fill("2026-08-03T20:30:00+00:00", "A", OrderSide.BUY, 1, 50.0),
            fill("2026-08-05T14:00:00+00:00", "A", OrderSide.BUY, 2, 51.0),
        ]
        # il fill del 03-08 e' dopo la campana (20:00Z): appartiene alla finestra
        assert reconstruct_start_quantities({"A": 5.0}, fills, after=ancoraggio()) == {"A": 2.0}


class TestInitialCash:
    def test_equity_meno_posizioni_marcate(self) -> None:
        cash = initial_cash(
            equity_at_start=1000.0,
            start_qty={"A": 2.0, "B": 1.0},
            start_closes={"A": 50.0, "B": 100.0},
        )
        assert cash == pytest.approx(800.0)

    def test_closes_mancante_rifiuta(self) -> None:
        with pytest.raises(ValueError, match="close"):
            initial_cash(1000.0, {"A": 2.0}, {"B": 100.0})


class TestReplay:
    def test_equity_calcolata_a_mano(self) -> None:
        """Due sedute, buy e sell parziale: equity verificata a mano."""
        giorni = [date(2026, 8, 4), date(2026, 8, 5)]
        fills = [
            fill("2026-08-04T15:00:00+00:00", "A", OrderSide.BUY, 5, 55.0),
            fill("2026-08-04T19:00:00+00:00", "A", OrderSide.SELL, 4, 62.0),
        ]
        closes = {
            date(2026, 8, 4): {"A": 60.0},
            date(2026, 8, 5): {"A": 55.0},
        }
        giorni_sedute = {g: chiusura_seduta(g) for g in giorni}

        serie, _ = replay(
            start_qty={"A": 10.0},
            start_cash=1000.0,
            start_closes={"A": 50.0},
            fills=fills,
            closes_by_day=closes,
            session_closes=giorni_sedute,
        )
        # giorno 1: cash 1000 - 5*55 + 4*62 = 973; qty 11; close 60 -> 1633
        assert serie[0].equity == pytest.approx(1633.0)
        # giorno 2: nessun fill, close 55 -> 973 + 11*55 = 1578
        assert serie[1].equity == pytest.approx(1578.0)

    def test_chiusura_totale_e_riacquisto_stesso_giorno(self) -> None:
        giorni = [date(2026, 8, 4)]
        fills = [
            fill("2026-08-04T15:00:00+00:00", "A", OrderSide.SELL, 2, 100.0),
            fill("2026-08-04T19:00:00+00:00", "A", OrderSide.BUY, 1, 90.0),
        ]
        serie, portafoglio = replay(
            start_qty={"A": 2.0},
            start_cash=0.0,
            start_closes={"A": 100.0},
            fills=fills,
            closes_by_day={date(2026, 8, 4): {"A": 95.0}},
            session_closes={date(2026, 8, 4): chiusura_seduta(date(2026, 8, 4))},
        )
        # cash 0 + 2*100 - 1*90 = 110; qty 1; close 95 -> 205
        assert serie[0].equity == pytest.approx(205.0)
        assert portafoglio.position_of("A") is not None
        assert portafoglio.position_of("A").quantity == pytest.approx(1.0)

    def test_chiusura_totale_frazionata_rimuove_posizione(self) -> None:
        qty = 12.305391274  # quantita' frazionaria reale vista sul paper
        giorni = [date(2026, 8, 4)]
        fills = [
            fill("2026-08-04T15:00:00+00:00", "A", OrderSide.BUY, qty, 116.70),
            fill("2026-08-04T16:52:00+00:00", "A", OrderSide.SELL, qty, 116.56),
        ]
        serie, portafoglio = replay(
            start_qty={},
            start_cash=1000.0,
            start_closes={"A": 116.0},
            fills=fills,
            closes_by_day={date(2026, 8, 4): {"A": 116.5}},
            session_closes={date(2026, 8, 4): chiusura_seduta(date(2026, 8, 4))},
        )
        # cash 1000 - 12.305391274*116.70 + 12.305391274*116.56, nessuna posizione
        atteso = 1000.0 + qty * (116.56 - 116.70)
        assert serie[0].equity == pytest.approx(atteso)
        assert portafoglio.position_of("A") is None

    def test_close_mancante_carry_forward(self) -> None:
        giorni = [date(2026, 8, 4), date(2026, 8, 5)]
        serie, _ = replay(
            start_qty={"A": 10.0},
            start_cash=500.0,
            start_closes={"A": 50.0},
            fills=[],
            closes_by_day={date(2026, 8, 4): {"A": 60.0}},  # 05-08 senza barra
            session_closes={g: chiusura_seduta(g) for g in giorni},
        )
        # nessun prezzo inventato: il 05-08 ripete il mark del 04-08
        assert serie[1].equity == pytest.approx(serie[0].equity)

    def test_fill_dopo_la_campana_rotola_al_giorno_dopo(self) -> None:
        """Un fill post-close (20:30Z) appartiene all'equity del giorno dopo,
        come fa il broker: il mark del giorno corrente non lo vede."""
        giorni = [date(2026, 8, 4), date(2026, 8, 5)]
        fills = [fill("2026-08-04T20:30:00+00:00", "A", OrderSide.BUY, 1, 60.0)]
        serie, _ = replay(
            start_qty={},
            start_cash=100.0,
            start_closes={"A": 50.0},
            fills=fills,
            closes_by_day={date(2026, 8, 4): {"A": 60.0}, date(2026, 8, 5): {"A": 62.0}},
            session_closes={g: chiusura_seduta(g) for g in giorni},
        )
        # giorno 1: il fill e' dopo la campana, resta cash 100 + 0 posizioni
        assert serie[0].equity == pytest.approx(100.0)
        # giorno 2: cash 40 + 1 * 62
        assert serie[1].equity == pytest.approx(102.0)

    def test_fill_fuori_dai_giorni_di_seduta_rifiuta(self) -> None:
        with pytest.raises(ValueError, match="seduta"):
            replay(
                start_qty={},
                start_cash=100.0,
                start_closes={"A": 50.0},
                fills=[fill("2026-08-06T15:00:00+00:00", "A", OrderSide.BUY, 1, 60.0)],
                closes_by_day={date(2026, 8, 6): {"A": 60.0}},
                session_closes={date(2026, 8, 4): chiusura_seduta(date(2026, 8, 4))},
            )


class TestEvaluateGate:
    def test_dentro_tolleranza_passa(self) -> None:
        esito = evaluate_gate(replay_equity=98_040.0, broker_equity=98_000.0)
        assert esito.superato
        assert esito.delta_pct == pytest.approx(0.0408, abs=1e-3)

    def test_fuori_tolleranza_fallisce(self) -> None:
        esito = evaluate_gate(replay_equity=102_100.0, broker_equity=100_000.0)
        assert not esito.superato

    def test_limite_esatto_2pct_passa(self) -> None:
        esito = evaluate_gate(replay_equity=102_000.0, broker_equity=100_000.0)
        assert esito.superato
        assert esito.delta_pct == pytest.approx(2.0)

    def test_segno_negativo_simmetrico(self) -> None:
        esito = evaluate_gate(replay_equity=98_000.0, broker_equity=100_000.0)
        assert esito.superato  # -2% esatto
        assert not evaluate_gate(replay_equity=97_900.0, broker_equity=100_000.0).superato


class TestPortfolioHistoryLabel:
    def test_etichetta_ph_e_il_giorno_dopo_la_seduta(self) -> None:
        # empirico su paper-api: la seduta 2026-09-21 ha etichetta 2026-09-22T00:00Z
        assert ph_label_epoch(date(2026, 9, 21)) == 1_790_035_200

    def test_venerdi_produce_sabato(self) -> None:
        # le sedute di venerdi' compaiono come sabato: e' il motivo dei punti
        # "Sab" nella serie 1D di Alpaca
        assert ph_label_epoch(date(2026, 7, 31)) == 1_785_542_400
