"""exit_mechanism osservato, non dedotto dall'orologio (#184).

Il 2026-08-05 quattro posizioni i cui segnali stale erano stati ri-ammessi da
FIX-D nello stesso ciclo (MCD/NVO/PFE/PLTR) sono uscite etichettate `expired`,
con un testo che descriveva come causa esattamente la condizione che FIX-D usa
per NON chiudere. La classificazione guardava l'età dell'ultimo segnale in DB,
non cosa il pipeline aveva fatto al segnale.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.backtest.engine.types import OrderSide, OrderType
from src.models.signals import SentimentResult
from src.portfolio.exit_classification import (
    BELOW_ENTRY_GATE,
    FALLBACK_FILTERED,
    FRESH,
    STALE_DROPPED,
    STALE_PRESERVED,
)
from src.portfolio.types import CombinedOrder
from src.workers.portfolio_scheduler import (
    _classify_zero_weight_exit,
    _preserve_stale_signals_for_open_positions,
    _reason_for_zero_weight_sell,
)


def _stale_signal(hours: float = 19.9, score: float = 0.514) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc) - timedelta(hours=hours),
        "score": score,
    }


class TestClassifyFromObservedDisposition:
    """L'etichetta segue la disposizione registrata, non l'età."""

    def test_preserved_stale_signal_is_not_expired(self):
        """#184, il caso del 2026-08-05: FIX-D l'ha ri-ammesso, non scartato."""
        mechanism = _classify_zero_weight_exit(
            _stale_signal(), max_age_hours=4, disposition=STALE_PRESERVED
        )

        assert mechanism == "unknown"

    def test_dropped_stale_signal_is_expired(self):
        mechanism = _classify_zero_weight_exit(
            _stale_signal(), max_age_hours=4, disposition=STALE_DROPPED
        )

        assert mechanism == "expired"

    def test_fresh_signal_stays_whipsaw(self):
        """Semantica #60/#61 invariata per il caso su cui il damper misura."""
        mechanism = _classify_zero_weight_exit(
            _stale_signal(hours=1.0, score=0.05), max_age_hours=4, disposition=FRESH
        )

        assert mechanism == "whipsaw"

    def test_gate_filtered_signal_reports_the_gate(self):
        mechanism = _classify_zero_weight_exit(
            _stale_signal(hours=1.0), max_age_hours=4, disposition=BELOW_ENTRY_GATE
        )

        assert mechanism == "below_entry_gate"

    def test_fallback_filtered_signal_reports_the_filter(self):
        mechanism = _classify_zero_weight_exit(
            _stale_signal(hours=1.0), max_age_hours=4, disposition=FALLBACK_FILTERED
        )

        assert mechanism == "fallback_filtered"

    def test_no_disposition_with_a_signal_in_db_is_unknown(self):
        """Un segnale in DB che il ciclo S4 non ha processato non spiega il peso 0.

        Prima di #184 questo ramo rispondeva "expired" o "whipsaw" a seconda
        dell'orologio: una risposta inventata.
        """
        mechanism = _classify_zero_weight_exit(
            _stale_signal(), max_age_hours=4, disposition=None
        )

        assert mechanism == "unknown"

    def test_no_signal_at_all_is_still_no_signal(self):
        """Invariante #60: nessun segnale in DB resta un fatto osservabile."""
        assert _classify_zero_weight_exit(None, max_age_hours=4) == "no_signal"


class TestReasonTextAgreesWithMechanism:
    """Invariante #60: il prefisso del testo e la colonna strutturata coincidono."""

    def test_preserved_stale_reason_is_not_an_expiry_story(self):
        reason = _reason_for_zero_weight_sell(
            "PFE", _stale_signal(), max_age_hours=4, disposition=STALE_PRESERVED
        )

        assert reason.startswith("[unknown]")
        assert "expired" not in reason
        assert "no counter-signal found" not in reason
        assert "FIX-D" in reason

    def test_dropped_stale_reason_keeps_the_expiry_wording(self):
        reason = _reason_for_zero_weight_sell(
            "CAT", _stale_signal(hours=20.3, score=0.60),
            max_age_hours=4, disposition=STALE_DROPPED,
        )

        assert reason.startswith("[expired]")
        assert "20.3h" in reason

    def test_fresh_reason_stays_whipsaw(self):
        reason = _reason_for_zero_weight_sell(
            "AAPL", _stale_signal(hours=1.0, score=0.05),
            max_age_hours=4, disposition=FRESH,
        )

        assert reason.startswith("[whipsaw]")

    def test_unobserved_reason_says_the_cycle_saw_nothing(self):
        reason = _reason_for_zero_weight_sell(
            "XYZ", _stale_signal(), max_age_hours=4, disposition=None
        )

        assert reason.startswith("[unknown]")
        assert "expired" not in reason


class TestFixDPreservationCannotProduceExpired:
    """DoD #184: reso impossibile per costruzione, non solo per convenzione."""

    @pytest.mark.parametrize("symbol", ["MCD", "NVO", "PFE", "PLTR"])
    def test_symbols_preserved_on_2026_08_05_cannot_be_expired(self, symbol):
        stale = [
            SentimentResult(
                symbol=sym, score=0.514, confidence=0.8,
                reasoning="", model_id="ensemble:glm-5.2:cloud",
                generated_at=datetime.now(timezone.utc) - timedelta(hours=19.9),
            )
            for sym in ("MCD", "NVO", "PFE", "PLTR")
        ]
        preserved = _preserve_stale_signals_for_open_positions(
            fresh_signals=[], stale_signals=stale,
            open_symbols={"MCD", "NVO", "PFE", "PLTR"},
        )
        preserved_syms = {s.symbol for s in preserved}
        assert symbol in preserved_syms, "premessa del test: FIX-D lo preserva"

        mechanism = _classify_zero_weight_exit(
            _stale_signal(), max_age_hours=4, disposition=STALE_PRESERVED
        )

        assert mechanism != "expired"


# ── _build_strategy_instance registra la disposizione dove agisce sul segnale ──


def _s4_dispositions_for(signals, open_trades=None) -> dict:
    """Costruisce l'istanza S4 su `signals` e restituisce le disposizioni registrate."""
    from src.workers.portfolio_scheduler import _build_strategy_instance

    entry = MagicMock()
    entry.strategy_id = "S4"
    bars_df = pd.DataFrame(
        {"SPY": [100.0 + i * 0.1 for i in range(5)]},
        index=pd.date_range("2025-01-01", periods=5, freq="B"),
    )
    store = MagicMock()
    store.fetch_signals_for_cycle.return_value = signals
    store.fetch_trades.return_value = open_trades or []

    dispositions: dict[str, str] = {}
    with patch("src.store.pg_store.PostgreSQLStore", return_value=store):
        _build_strategy_instance(entry, bars_df, dispositions=dispositions)
    return dispositions


def _signal(symbol, score=0.8, age_hours=1.0, fallback_used=False):
    return SentimentResult(
        symbol=symbol, score=score, confidence=0.9, reasoning="",
        model_id="ensemble:glm-5.2:cloud",
        generated_at=datetime.now(timezone.utc) - timedelta(hours=age_hours),
        fallback_used=fallback_used,
    )


def test_fresh_signal_is_recorded_as_fresh():
    assert _s4_dispositions_for([_signal("NVDA")])["NVDA"] == FRESH


def test_stale_signal_without_open_position_is_recorded_as_dropped():
    assert _s4_dispositions_for([_signal("NVDA", age_hours=20)])["NVDA"] == STALE_DROPPED


def test_stale_signal_preserved_by_fix_d_overwrites_the_dropped_tag():
    dispositions = _s4_dispositions_for(
        [_signal("NVDA", age_hours=20)],
        open_trades=[{"symbol": "NVDA", "stop_strategy": "S4"}],
    )

    assert dispositions["NVDA"] == STALE_PRESERVED


def test_fallback_signal_is_recorded_as_fallback_filtered():
    dispositions = _s4_dispositions_for([_signal("NVDA", fallback_used=True)])

    assert dispositions["NVDA"] == FALLBACK_FILTERED


def test_signal_under_the_entry_gate_is_recorded_as_below_gate():
    """Soglia di default 0.30 (_ENTRY_THRESHOLD_BASELINE), Redis non raggiungibile."""
    dispositions = _s4_dispositions_for([_signal("NVDA", score=0.05)])

    assert dispositions["NVDA"] == BELOW_ENTRY_GATE


# ── Ciclo completo: la disposizione arriva dal pipeline al Decision Log ────────


def _zero_weight_sell(symbol: str) -> CombinedOrder:
    return CombinedOrder(
        order_id=f"oid-{symbol}",
        timestamp=datetime(2026, 8, 5, 14, 22, tzinfo=timezone.utc),
        symbol=symbol,
        side=OrderSide.SELL,
        quantity=5.0,
        order_type=OrderType.MARKET,
        strategy_id=None,
        allocation_weight=0.0,
    )


def _cycle_result(symbols: list[str]):
    from src.portfolio.orchestrator import CycleResult

    return CycleResult(
        strategies_run=["S4"],
        orders_per_strategy={"S4": len(symbols)},
        orders_before_constraints=len(symbols),
        orders_after_constraints=len(symbols),
        constraints_fired=[],
        final_orders=[_zero_weight_sell(s) for s in symbols],
        symbol_strategies={},  # nessuna delle 4 è entrata nella top-N del ranker
        symbol_signal_provenance={},
    )


def _run_preserved_stale_cycle(symbols: list[str]):
    """Replica del ciclo 14:22 del 2026-08-05: 4 posizioni aperte S4, segnali
    stale (19.9h) senza counter-signal → FIX-D li preserva → peso 0 comunque."""
    mock_pg = MagicMock()
    open_trades = [
        {"symbol": s, "stop_strategy": "S4", "quantity": 5.0, "entry_price": 100.0}
        for s in symbols
    ]
    mock_pg.fetch_trades.return_value = open_trades
    mock_pg.fetch_recently_bought_symbols.return_value = set()
    mock_pg.fetch_latest_signal_ids.return_value = {}
    stale_gen_at = datetime.now(timezone.utc) - timedelta(hours=19.9)
    stale_signals = [
        SentimentResult(
            symbol=s, score=0.514, confidence=0.8,
            reasoning="preserved by FIX-D", model_id="ensemble:glm-5.2:cloud",
            generated_at=stale_gen_at,
        )
        for s in symbols
    ]

    def _fetch_signals(hours, **kwargs):
        """La finestra conta: l'anti-stale-ranker-sell interroga a max_age (4h) e
        deve trovare il vuoto, altrimenti proteggerebbe le posizioni e non ci
        sarebbe nessuna SELL da etichettare (com'è successo davvero il 05/08)."""
        return list(stale_signals) if hours >= 20 else []

    mock_pg.fetch_signals_for_cycle.side_effect = _fetch_signals
    mock_pg.write_execution_decision = MagicMock(return_value=1)

    with patch("src.strategies.registry.StrategyRegistry") as mock_reg, \
         patch("alpaca.data.historical.StockHistoricalDataClient") as mock_dc, \
         patch("alpaca.trading.client.TradingClient") as mock_tc, \
         patch("src.portfolio.orchestrator.PortfolioOrchestrator") as mock_orch, \
         patch("src.backtest.engine.data_replay.DataReplay"), \
         patch("src.backtest.engine.portfolio.VirtualPortfolio"), \
         patch("src.workers.portfolio_scheduler._persist_cycle_result"), \
         patch("src.workers.portfolio_scheduler._load_risk_config") as mock_risk_cfg, \
         patch("src.store.pg_store.PostgreSQLStore", return_value=mock_pg), \
         patch("redis.Redis") as mock_redis_cls:

        entry = MagicMock()
        entry.strategy_id = "S4"
        mock_reg.return_value.get_active_strategies.return_value = [entry]
        mock_reg.return_value.load_mode_from_db.return_value = None

        mock_risk_cfg.return_value = {
            "max_portfolio_exposure": 0.50, "max_single_asset_pct": 0.10,
            "max_sector_exposure": 0.0, "stop_loss": 0.0, "portfolio_drawdown": 0.05,
            "stop_loss_mode": "fixed", "stop_strategy_params": {},
            "stop_sigma_lookback_fast": 20, "stop_sigma_lookback_slow": 63,
            "stop_sigma_ewma_floor_ratio": 0.8, "stop_risk_budget_bp_per_pos": 12,
            "stop_risk_budget_bp_aggregate": 100, "stop_gap_buffer_pct": 0.005,
            "stop_shadow_enabled": False,
            "broker_disaster_stop": {"multiplier": 1.5, "sigma_multiple": 5.0,
                                     "floor_pct": 0.12, "cap_pct": 0.20},
            "s4_anti_whipsaw_damping_enabled": False, "s4_anti_whipsaw_confirm_cycles": 2,
        }

        dates = pd.date_range("2025-01-01", periods=100, freq="B")
        alpaca_raw = pd.concat([
            pd.DataFrame(
                {"close": [100.0 + i for i in range(100)]},
                index=pd.MultiIndex.from_arrays(
                    [[sym] * 100, dates], names=["symbol", "timestamp"]
                ),
            )
            for sym in symbols
        ])
        mock_dc.return_value.get_stock_bars.return_value.df = alpaca_raw
        mock_dc.return_value.get_stock_snapshot.side_effect = Exception("no snap")

        clock = MagicMock()
        clock.is_open = True
        account = MagicMock()
        account.cash = "100000"
        account.equity = "100000"
        account.buying_power = "100000"
        account.trading_blocked = False
        account.account_blocked = False
        mock_tc.return_value.get_clock.return_value = clock
        mock_tc.return_value.get_account.return_value = account
        mock_tc.return_value.get_all_positions.return_value = []

        mock_orch.return_value.run_cycle.return_value = _cycle_result(symbols)

        redis_inst = MagicMock()
        # gate parcheggiato: questo test è sulla disposizione, non sulla soglia
        redis_inst.get.side_effect = (
            lambda key: "0.0" if "feedback:entry_threshold" in str(key) else None
        )
        redis_inst.set.return_value = True
        redis_inst.smembers.return_value = set()
        redis_inst.incr.return_value = 99  # oltre l'isteresi di uscita
        mock_redis_cls.from_url.return_value = redis_inst

        from src.workers.portfolio_scheduler import _run_cycle_inner
        try:
            _run_cycle_inner()
        except Exception:
            import traceback
            traceback.print_exc()

    return mock_pg


@pytest.mark.parametrize("symbol", ["MCD", "NVO", "PFE", "PLTR"])
def test_2026_08_05_preserved_positions_are_not_labelled_expired(symbol):
    """Le 4 SELL del 14:22 non devono più risultare `expired` (DoD #184)."""
    symbols = ["MCD", "NVO", "PFE", "PLTR"]
    mock_pg = _run_preserved_stale_cycle(symbols)

    calls = [
        c for c in mock_pg.write_execution_decision.call_args_list
        if c.kwargs.get("symbol") == symbol and c.kwargs.get("decision") == "SELL"
    ]
    assert len(calls) == 1, f"attesa una sola decisione SELL per {symbol}, {len(calls)}"
    assert calls[0].kwargs["exit_mechanism"] == "unknown"
    assert "expired" not in calls[0].kwargs["reason"]
