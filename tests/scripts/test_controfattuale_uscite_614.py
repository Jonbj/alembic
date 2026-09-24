"""Test delle funzioni pure del runner del controfattuale uscite (#614)."""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from src.backtest.costs.realistic import RealisticCostModel
from src.backtest.engine.types import OrderSide
from src.performance.ic import compute_newey_west_hac
from scripts.controfattuale_uscite_614 import (
    dati_per_inferenza,
    inferenza,
    motivi_da_righe_trades,
    riga_charter_presente,
    vendita_ipotetica,
)
from scripts.replay_gate_614 import fills_da_ordini

CHARTER_SENZA_RIGA = """# Charter
| 2026-08-25 | **#182(a)**: `sentiment_reversal` di S4 non chiude più posizioni altrui | testo |
| 2026-09-12 | **#512**: misura ombra della rincorsa; riusare il worker controfattuale | testo |
"""

CHARTER_CON_RIGA = CHARTER_SENZA_RIGA + (
    "| 2026-09-28 | **#614**: registrato il controfattuale sulle uscite (rami H_N) | testo |\n"
)


class TestRigaCharter:
    def test_senza_riga_rifiuta(self) -> None:
        presente, riga = riga_charter_presente(CHARTER_SENZA_RIGA)
        assert presente is False
        assert riga is None

    def test_con_riga_614_contraffattuale_passa(self) -> None:
        presente, riga = riga_charter_presente(CHARTER_CON_RIGA)
        assert presente is True
        assert riga is not None and "#614" in riga and "controfattuale" in riga.lower()

    def test_la_riga_di_512_non_basta(self) -> None:
        """Una riga che nomina un controfattuale ma non #614 non autorizza."""
        presente, _ = riga_charter_presente(CHARTER_SENZA_RIGA)
        assert presente is False


class TestMotiviDaTrades:
    def test_righe_piatte_diventano_dizionario(self) -> None:
        righe = [
            {"order_id": "a-1", "exit_reason": "portfolio_sell"},
            {"order_id": "a-2", "exit_reason": "hold_minimum_expiry"},
            {"order_id": "a-3", "exit_reason": "portfolio_sell"},
        ]
        assert motivi_da_righe_trades(righe) == {
            "a-1": "portfolio_sell",
            "a-2": "hold_minimum_expiry",
            "a-3": "portfolio_sell",
        }

    def test_righe_senza_motivo_scartate(self) -> None:
        """Un NULL non entra nella mappa: chi non ha etichetta resta reale."""
        righe = [
            {"order_id": "a-1", "exit_reason": None},
            {"order_id": "a-2", "exit_reason": "sentiment_reversal"},
        ]
        assert motivi_da_righe_trades(righe) == {"a-2": "sentiment_reversal"}


def _ordine_con_id(oid: str, side: str, qty: str, price: str, filled_at: str) -> dict:
    return {
        "id": oid, "symbol": "A", "side": side, "status": "filled",
        "filled_qty": qty, "filled_avg_price": price, "filled_at": filled_at,
        "asset_class": "us_equity",
    }


class TestFillsConMotivo:
    def test_etichetta_attaccata_per_id_ordine(self) -> None:
        fills = fills_da_ordini(
            [_ordine_con_id("a-1", "sell", "2", "100", "2026-08-04T15:00:00Z")],
            motivi={"a-1": "portfolio_sell"},
        )
        assert fills[0].exit_reason == "portfolio_sell"

    def test_id_senza_motivo_resta_none(self) -> None:
        fills = fills_da_ordini(
            [_ordine_con_id("a-9", "sell", "2", "100", "2026-08-04T15:00:00Z")],
            motivi={"a-1": "portfolio_sell"},
        )
        assert fills[0].exit_reason is None

    def test_senza_motivi_comportamento_invariato(self) -> None:
        fills = fills_da_ordini(
            [_ordine_con_id("a-1", "buy", "2", "100", "2026-08-04T15:00:00Z")]
        )
        assert fills[0].exit_reason is None


class TestInferenza:
    def test_wrapper_riusa_newey_west_con_lag_dichiarato(self) -> None:
        diff = [1.0, -2.0, 3.0, 0.5, -1.5, 2.0, 1.0, -0.5, 2.5, -1.0] * 3
        esito = inferenza(diff, lag=2)
        se = compute_newey_west_hac(diff, lag=2)
        assert esito["n"] == len(diff)
        assert esito["media"] == pytest.approx(sum(diff) / len(diff))
        assert esito["se_nw"] == pytest.approx(se)
        assert esito["t"] == pytest.approx(esito["media"] / se)
        # MDE pre-registrata §5: 3·SE — ciò che sta sotto non è decidibile
        assert esito["mde"] == pytest.approx(3.0 * se)

    def test_varianza_zero_non_produce_t_infinito(self) -> None:
        esito = inferenza([5.0] * 10, lag=1)
        assert esito["t"] is None
        assert esito["mde"] == 0.0

    def test_diff_allineata_per_giorno(self) -> None:
        giorni = [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]
        ramo = {g: 100.0 + i for i, g in enumerate(giorni)}
        controllo = {g: 99.0 + i * 2 for i, g in enumerate(giorni)}
        giorni_comuni, diff = dati_per_inferenza(ramo, controllo)
        assert giorni_comuni == giorni
        assert diff == [1.0, 0.0, -1.0]


class TestVenditaIpotetica:
    def test_prezzo_peggiore_del_close_e_commissioni_mai_zero(self) -> None:
        """§4: i fill ipotetici passano da src/backtest/costs/, mai gratis."""
        modello = RealisticCostModel(config_path=Path("config/cost_model.yaml"))
        campana = datetime(2026, 8, 5, 20, tzinfo=timezone.utc)
        fill = vendita_ipotetica(modello, "X", 10.0, 105.0, campana)
        assert fill.side == OrderSide.SELL
        assert fill.quantity == pytest.approx(10.0)
        # vendita: half-spread + impatto peggiorano il prezzo sotto il close
        assert fill.fill_price < 105.0
        assert fill.commission > 0.0
        assert fill.timestamp == campana


class TestDiagnosticaEtichette:
    def test_conta_le_vendite_etichettate_e_no(self) -> None:
        from scripts.controfattuale_uscite_614 import diagnostica_etichette
        from src.backtest.engine.exit_counterfactual import FillConMotivo

        def _f(side, motivo=None):
            return FillConMotivo(
                timestamp=datetime(2026, 8, 4, 15, tzinfo=timezone.utc),
                symbol="A", side=side, quantity=1.0, fill_price=10.0,
                exit_reason=motivo,
            )

        fills = [
            _f(OrderSide.SELL, "portfolio_sell"),
            _f(OrderSide.SELL, "hold_minimum_expiry"),
            _f(OrderSide.SELL, None),
            _f(OrderSide.BUY, None),
        ]
        d = diagnostica_etichette(fills)
        assert d["vendite"] == 3
        assert d["vendite_etichettate"] == 2
        assert d["vendite_senza_etichetta"] == 1
        assert d["per_motivo"] == {"portfolio_sell": 1, "hold_minimum_expiry": 1}
