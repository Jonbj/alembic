"""Test delle funzioni pure del runner del cancello di riproducibilità (#614)."""
from datetime import date, datetime, timezone

import pytest

from src.backtest.engine.types import OrderSide
from scripts.replay_gate_614 import (
    closes_da_barre,
    fills_da_ordini,
    session_closes_da_calendario,
    seduta_precedente,
)


def _ordine(
    symbol: str,
    side: str,
    qty: str,
    price: str | None,
    filled_at: str,
    status: str = "filled",
) -> dict:
    return {
        "symbol": symbol,
        "side": side,
        "status": status,
        "filled_qty": qty,
        "filled_avg_price": price,
        "filled_at": filled_at,
    }


class TestFillsDaOrdini:
    def test_ordini_riempiti_diventano_fill(self) -> None:
        fills = fills_da_ordini(
            [_ordine("A", "buy", "2.5", "100.125", "2026-08-04T14:22:11.263899Z")]
        )
        assert len(fills) == 1
        f = fills[0]
        assert f.symbol == "A"
        assert f.side == OrderSide.BUY
        assert f.quantity == pytest.approx(2.5)
        assert f.fill_price == pytest.approx(100.125)
        assert f.timestamp == datetime(2026, 8, 4, 14, 22, 11, 263899, tzinfo=timezone.utc)

    def test_parzialmente_riempiti_e_annullati_contano(self) -> None:
        """Un ordine cancellato dopo un fill parziale ha comunque mosso il cash."""
        fills = fills_da_ordini(
            [_ordine("A", "sell", "3", "50", "2026-08-04T15:00:00Z", status="canceled")]
        )
        assert len(fills) == 1
        assert fills[0].side == OrderSide.SELL

    def test_senza_fill_scartati(self) -> None:
        fills = fills_da_ordini(
            [
                _ordine("A", "buy", "0", None, "2026-08-04T15:00:00Z", status="canceled"),
                _ordine("A", "buy", "2", None, "2026-08-04T15:01:00Z", status="expired"),
            ]
        )
        assert fills == []

    def test_ordinati_per_timestamp(self) -> None:
        fills = fills_da_ordini(
            [
                _ordine("A", "buy", "1", "10", "2026-08-05T15:00:00Z"),
                _ordine("B", "sell", "1", "20", "2026-08-04T15:00:00Z"),
            ]
        )
        assert [f.symbol for f in fills] == ["B", "A"]


class TestSessionClosesDaCalendario:
    def test_hhmm_diventa_datetime_utc(self) -> None:
        calendario = [
            {"date": "2026-08-03", "session_close": "2000"},
            {"date": "2026-08-04", "session_close": "2000"},
        ]
        sc = session_closes_da_calendario(calendario)
        assert sc == {
            date(2026, 8, 3): datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc),
            date(2026, 8, 4): datetime(2026, 8, 4, 20, 0, tzinfo=timezone.utc),
        }

    def test_chiusura_anticipata_1700(self) -> None:
        sc = session_closes_da_calendario([{"date": "2026-11-27", "session_close": "1700"}])
        assert sc[date(2026, 11, 27)].hour == 17


class TestClosesDaBarre:
    def test_dataframe_multiindice(self) -> None:
        import pandas as pd

        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 50.0],
            },
            index=pd.MultiIndex.from_tuples(
                [
                    ("A", pd.Timestamp("2026-08-04", tz="UTC")),
                    ("A", pd.Timestamp("2026-08-05", tz="UTC")),
                    ("B", pd.Timestamp("2026-08-04", tz="UTC")),
                ],
                names=["symbol", "timestamp"],
            ),
        )
        closes = closes_da_barre(df)
        assert closes[date(2026, 8, 4)] == {"A": 100.0, "B": 50.0}
        assert closes[date(2026, 8, 5)] == {"A": 101.0}


class TestSedute:
    def test_seduta_precedente_salta_il_weekend(self) -> None:
        giorni = [date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3)]
        assert seduta_precedente(date(2026, 8, 3), giorni) == date(2026, 7, 31)
