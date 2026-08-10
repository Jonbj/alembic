"""Regression tests for S4 backtest input validity and live-gate parity."""
from __future__ import annotations

import inspect
import json
from datetime import date
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.backtest.walkforward.runner import WalkForwardConfig


@pytest.fixture
def prices() -> pd.DataFrame:
    dates = pd.date_range("2026-01-02", periods=10, freq="B")
    return pd.DataFrame({"SPY": range(10), "AAPL": range(10)}, index=dates)


@pytest.fixture
def synthetic_prices() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2015-01-01", periods=800, freq="B")
    tickers = ["SPY", "AAPL", "MSFT", "GOOG", "AMZN", "META"]
    data = {ticker: 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, 800))) for ticker in tickers}
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def synthetic_signals(synthetic_prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ts in synthetic_prices.index[::5]:
        for ticker in (column for column in synthetic_prices.columns if column != "SPY"):
            rows.append(
                {
                    "symbol": ticker,
                    "score": 0.50,
                    "confidence": 0.80,
                    "generated_at": ts,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def small_wf_config() -> WalkForwardConfig:
    return WalkForwardConfig(in_sample_days=400, out_of_sample_days=150)


def _mock_store(monkeypatch, *, rows=None, error: Exception | None = None) -> None:
    from src.store import pg_store

    store_type = MagicMock()
    if error is not None:
        store_type.side_effect = error
    else:
        store_type.return_value.__enter__.return_value.fetch_signals_for_backtest_batch.return_value = rows
    monkeypatch.setattr(pg_store, "PostgreSQLStore", store_type)


def test_signal_loader_rejects_unavailable_postgres(monkeypatch, prices) -> None:
    from src.strategies.s4.backtest import _load_sentiment_signals

    _mock_store(monkeypatch, error=ConnectionError("database offline"))

    with pytest.raises(RuntimeError, match="real historical sentiment signals.*PostgreSQL"):
        _load_sentiment_signals(prices, date(2026, 1, 1), date(2026, 1, 31))


def test_signal_loader_rejects_empty_query(monkeypatch, prices) -> None:
    from src.strategies.s4.backtest import _load_sentiment_signals

    _mock_store(monkeypatch, rows=[])

    with pytest.raises(RuntimeError, match="real historical sentiment signals.*no rows"):
        _load_sentiment_signals(prices, date(2026, 1, 1), date(2026, 1, 31))


def test_signal_loader_allows_synthetic_only_by_explicit_opt_in(monkeypatch, prices) -> None:
    from src.strategies.s4.backtest import _load_sentiment_signals

    _mock_store(monkeypatch, rows=[])

    signals = _load_sentiment_signals(
        prices,
        date(2026, 1, 1),
        date(2026, 1, 31),
        allow_synthetic=True,
    )

    assert not signals.empty
    assert signals.attrs["synthetic"] is True


def test_entry_threshold_default_matches_live_gate_floor() -> None:
    from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals
    from src.workers.portfolio_scheduler import _ENTRY_THRESHOLD_BASELINE

    default = inspect.signature(run_s4_backtest_from_prices_and_signals).parameters[
        "entry_threshold"
    ].default

    assert default == _ENTRY_THRESHOLD_BASELINE == 0.30


def test_entry_threshold_keeps_only_live_eligible_signals() -> None:
    from src.strategies.s4.backtest import _apply_entry_threshold

    signals = pd.DataFrame(
        {
            "symbol": ["WEAK", "FLOOR", "STRONG", "BEAR"],
            "score": [0.29, 0.30, 0.70, -0.80],
        }
    )

    filtered = _apply_entry_threshold(signals, 0.30)

    assert filtered["symbol"].tolist() == ["FLOOR", "STRONG"]


def test_synthetic_artifacts_are_marked_non_decisional(
    synthetic_prices,
    synthetic_signals,
    small_wf_config,
    tmp_path,
) -> None:
    from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals

    output_dir = tmp_path / "synthetic_s4"
    result = run_s4_backtest_from_prices_and_signals(
        prices=synthetic_prices,
        signals_df=synthetic_signals,
        output_dir=output_dir,
        wf_config=small_wf_config,
        run_robustness=False,
        synthetic=True,
    )

    summary = json.loads((output_dir / "summary.json").read_text())
    gate_report = json.loads((output_dir / "gate_report.json").read_text())
    assert summary["synthetic"] is True
    assert gate_report["synthetic"] is True
    assert gate_report["decision_eligible"] is False
    assert result["decision_eligible"] is False
