"""#550 (F-073) — i rebuild di CycleResult non devono perdere la provenienza.

I filtri a valle del ciclo (FIX-C stop-loss, hold minimum, anti-stale-ranker,
exit hysteresis) ricostruiscono il CycleResult per sostituire `final_orders`.
Passavano `symbol_strategies` ma non `symbol_signal_provenance`, che ha
default `{}`: appena UN filtro scattava, la provenienza del ranker spariva e
la riga BUY ricadeva sul re-fetch «latest» — score grezzo, moltiplicatore
ignoto. BA 2026-09-17: BUY a 0.2738 registrato mentre il gate aveva visto
0.3285, proprio perche' un filtro aveva ricostruito il result.
"""
from __future__ import annotations

from datetime import datetime, timezone

from src.backtest.engine.types import Order, OrderSide
from src.portfolio.orchestrator import CycleResult
from src.workers.portfolio_scheduler import _cycle_result_with_orders


def _result_with_provenance() -> CycleResult:
    order = Order.market_order(
        ts=datetime(2026, 9, 17, 16, 7, tzinfo=timezone.utc),
        symbol="BA",
        side=OrderSide.BUY,
        qty=1.0,
        strategy_id="S4",
    )
    return CycleResult(
        strategies_run=["S4"],
        orders_per_strategy={"S4": 1},
        orders_before_constraints=1,
        orders_after_constraints=1,
        constraints_fired=[],
        final_orders=[order],
        symbol_strategies={"BA": ["S4"]},
        symbol_signal_provenance={
            "BA": {
                "signal_id": 11429,
                "score": 0.3285,
                "raw_score": 0.27375,
                "velocity_multiplier": 1.2,
                "reasoning": "bull",
                "model_id": "ensemble",
            }
        },
    )


def test_il_rebuild_mantiene_la_provenienza_dei_segnali():
    original = _result_with_provenance()

    rebuilt = _cycle_result_with_orders(original, final_orders=[])

    assert rebuilt.symbol_signal_provenance == original.symbol_signal_provenance


def test_il_rebuild_mantiene_le_strategie_per_simbolo_e_sostituiscegli_ordini():
    original = _result_with_provenance()

    rebuilt = _cycle_result_with_orders(original, final_orders=[])

    assert rebuilt.symbol_strategies == original.symbol_strategies
    assert rebuilt.final_orders == []
    assert rebuilt.strategies_run == original.strategies_run
    assert rebuilt.orders_before_constraints == original.orders_before_constraints
