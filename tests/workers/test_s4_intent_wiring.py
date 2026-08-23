"""#294: wiring freeze-safe del ledger nel path live S4."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.backtest.engine.types import MarketSnapshot, OrderSide
from src.models.signals import SentimentResult
from src.portfolio.types import CombinedOrder
from src.strategies.s4.config import S4Config
from src.strategies.s4.intent_ledger import S4IntentLedger, build_component_versions
from src.strategies.s4.strategy import NewsDrivenTactical
from src.workers.portfolio_scheduler import (
    _submit_portfolio_orders,
    _write_s4_intent_events_fail_open,
)


_TS = datetime(2026, 8, 24, 14, 7, tzinfo=timezone.utc)


def _versions():
    return build_component_versions(
        config=S4Config(n_top=1),
        risk_config={"s4_fixed_slot_sizing_enabled": True},
        code_version="abc1234",
        config_hash="deadbeef",
        policy_version="s4-exit-trial:v1",
    )


def _signal(symbol: str, signal_id: int, score: float):
    return SentimentResult(
        symbol=symbol,
        signal_id=signal_id,
        score=score,
        confidence=0.9,
        reasoning="test",
        model_id="ensemble:test",
        generated_at=_TS,
    )


def _buy(symbol: str, qty: float):
    return CombinedOrder(
        order_id=f"order-{symbol}",
        timestamp=_TS,
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=qty,
        order_type="MARKET",
        limit_price=None,
        strategy_id="merged",
        allocation_weight=0.02,
    )


def test_strategy_trasferisce_i_diagnostics_del_ranker_al_ledger():
    ledger = S4IntentLedger(_TS, _versions())
    signals = [_signal("AMD", 1, 0.8), _signal("NVDA", 2, 0.7)]
    ledger.capture(signals)
    strategy = NewsDrivenTactical(
        config=S4Config(n_top=1, min_stocks=1),
        intent_ledger=ledger,
    )

    assert strategy.compute_target_weights(signals, as_of=_TS) == {"AMD": 0.2}
    dispositions = {event.signal_id: event for event in ledger.disposition_events(
        default_reason="UNCLASSIFIED"
    )}

    assert (dispositions[1].rank, dispositions[1].reason_code) == (1, "RANK_SELECTED")
    assert (dispositions[2].rank, dispositions[2].reason_code) == (
        2,
        "RANK_OUTSIDE_TOP_N",
    )


def test_writer_intenti_fail_open_non_interrompe_il_path_live():
    store = MagicMock()
    store.write_s4_intent_events.side_effect = RuntimeError("db down")

    assert _write_s4_intent_events_fail_open(store, [MagicMock()], phase="candidate") is False


def test_callback_disposition_non_modifica_gli_ordini_inviati():
    orders = [_buy("AMD", 1.0), _buy("NVDA", 0.01)]
    market = MarketSnapshot(timestamp=_TS, prices={"AMD": 100.0, "NVDA": 100.0})
    submit = MagicMock()

    baseline = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=submit,
        regime_mult=1.0,
    )
    dispositions = []
    instrumented = _submit_portfolio_orders(
        orders,
        MagicMock(),
        market,
        _submit_fn=submit,
        regime_mult=1.0,
        _on_disposition=lambda symbol, reason, details: dispositions.append(
            (symbol, reason, details)
        ),
    )

    assert instrumented == baseline
    assert [(symbol, reason) for symbol, reason, _ in dispositions] == [
        ("AMD", "SUBMITTED"),
        ("NVDA", "SKIP_MIN_NOTIONAL"),
    ]


def test_callback_disposition_guasta_non_modifica_gli_ordini():
    order = _buy("AMD", 1.0)
    market = MarketSnapshot(timestamp=_TS, prices={"AMD": 100.0})

    submitted = _submit_portfolio_orders(
        [order],
        MagicMock(),
        market,
        _submit_fn=MagicMock(),
        _on_disposition=MagicMock(side_effect=RuntimeError("telemetry down")),
    )

    assert [row["symbol"] for row in submitted] == ["AMD"]
