"""P1-04 S4 gate script runnable — gate report ID linkable to strategy_lifecycle.

Problems (from audit):
- run_s4_backtest_from_prices_and_signals returns report_path but no gate_report_id.
- No function to link a completed gate report to strategy_lifecycle.
- No CLI entry point for running S4 gates reproducibly.

Tests pin:
1. Backtest function returns a gate_report_id in result dict.
2. link_gate_report_to_lifecycle() writes gate_report_id to strategy_lifecycle.
3. src.strategies.s4.gate_cli has a callable main().
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestGateReportIdInResult:

    def test_run_s4_backtest_returns_gate_report_id(self, tmp_path):
        """run_s4_backtest_from_prices_and_signals must return a 'gate_report_id' key."""
        import numpy as np
        import pandas as pd

        dates = pd.date_range("2020-01-01", periods=600, freq="B")
        rng = np.random.default_rng(0)
        prices = pd.DataFrame(
            {
                "AAPL": 100 * (1 + rng.normal(0, 0.01, len(dates))).cumprod(),
                "MSFT": 80  * (1 + rng.normal(0, 0.01, len(dates))).cumprod(),
                "SPY":  300 * (1 + rng.normal(0, 0.005, len(dates))).cumprod(),
            },
            index=dates,
        )

        signals_rows = []
        for i, dt in enumerate(dates[::10]):
            for sym in ["AAPL", "MSFT"]:
                signals_rows.append({
                    "symbol": sym,
                    "score": float(rng.uniform(-0.5, 0.9)),
                    "confidence": 0.7,
                    "generated_at": pd.Timestamp(dt),
                    "model_id": "test",
                    "reasoning": "test",
                    "ensemble_std": 0.05,
                    "fallback_used": False,
                })
        signals_df = pd.DataFrame(signals_rows)

        from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals
        from src.backtest.walkforward.runner import WalkForwardConfig

        result = run_s4_backtest_from_prices_and_signals(
            prices=prices,
            signals_df=signals_df,
            output_dir=tmp_path / "s4_gate",
            wf_config=WalkForwardConfig(in_sample_days=200, out_of_sample_days=100),
            run_robustness=False,
        )

        assert "gate_report_id" in result, (
            "run_s4_backtest_from_prices_and_signals must return 'gate_report_id' in result dict. "
            "This ID is used to link the gate report to strategy_lifecycle for promotion requests."
        )
        assert result["gate_report_id"], "gate_report_id must be a non-empty string"


class TestLinkGateReportToLifecycle:

    def test_link_function_exists(self):
        try:
            from src.strategies.s4.gate_cli import link_gate_report_to_lifecycle
        except ImportError:
            pytest.fail(
                "src.strategies.s4.gate_cli must export link_gate_report_to_lifecycle(). "
                "This function writes gate_report_id to strategy_lifecycle after a run."
            )

    def test_link_writes_gate_report_id_to_lifecycle(self):
        """link_gate_report_to_lifecycle updates strategy_lifecycle.gate_report_id."""
        from src.strategies.s4.gate_cli import link_gate_report_to_lifecycle

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        link_gate_report_to_lifecycle(
            strategy_id="S4",
            gate_report_id="s4-gate-2026-06-19",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any(
            "update" in sql and "strategy_lifecycle" in sql
            for sql in executed_sqls
        ), (
            "link_gate_report_to_lifecycle must UPDATE strategy_lifecycle with gate_report_id. "
            f"Got: {executed_sqls}"
        )


class TestGateCliEntryPoint:

    def test_gate_cli_module_has_main(self):
        """src.strategies.s4.gate_cli must have a main() function."""
        try:
            from src.strategies.s4.gate_cli import main
        except ImportError:
            pytest.fail("src.strategies.s4.gate_cli must export main()")
        assert callable(main)
