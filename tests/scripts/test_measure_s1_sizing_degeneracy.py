"""#490: lo script di misura S1 resta deterministico e separa I/O/calcolo."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.measure_s1_sizing_degeneracy import (
    build_report,
    first_trading_sessions,
)
from src.strategies.s1.sizing import compute_sizing_metrics

PROJECT_DIR = Path(__file__).resolve().parents[2]


def _synthetic_panel() -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=470, freq="B", tz="UTC")
    rng = np.random.default_rng(490)
    return pd.DataFrame(
        {
            f"T{i:02d}": 100
            * np.exp(np.cumsum(rng.normal(0.0002 + i * 0.00008, 0.01, len(dates))))
            for i in range(12)
        },
        index=dates,
    )


def test_first_trading_sessions_selects_one_observation_per_month() -> None:
    index = pd.DatetimeIndex(
        [
            "2026-06-01T04:00:00Z",
            "2026-06-02T04:00:00Z",
            "2026-07-01T04:00:00Z",
            "2026-08-03T04:00:00Z",
            "2026-09-01T04:00:00Z",
        ]
    )

    sessions = first_trading_sessions(index, since=date(2026, 6, 1))

    assert [session.date().isoformat() for session in sessions] == [
        "2026-06-01",
        "2026-07-01",
        "2026-08-03",
        "2026-09-01",
    ]


def test_build_report_measures_live_target_and_monthly_history() -> None:
    prices = _synthetic_panel()
    as_of = prices.index[-1]
    live_state = {
        "last_rebalance": as_of.isoformat(),
        "target_weights": {"T09": 0.5, "T10": 0.3, "T11": 0.2},
    }

    report = build_report(
        prices,
        live_state,
        since=prices.index[-45].date(),
        generated_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
    )

    assert report["generated_at"] == "2026-09-04T12:00:00+00:00"
    assert report["live"]["metrics"]["n_target"] == 3
    assert report["live"]["metrics"]["n_eff"] == 1 / (0.5**2 + 0.3**2 + 0.2**2)
    assert report["live"]["matched_target_symbols"] == 3
    assert set(report["live"]["inputs"]) == {"target_weights", "signals", "raw_weights"}
    assert report["historical_first_trading_days"]
    assert all(
        set(row["metrics"]) == {
            "n_target",
            "n_eff",
            "cap_bound_share",
            "spearman_signal_weight",
        }
        for row in report["historical_first_trading_days"]
    )


def test_live_2026_09_01_metrics_are_reproducible_from_evidence() -> None:
    evidence = json.loads(
        (PROJECT_DIR / "docs/evidence/s1_sizing_degeneracy.json").read_text()
    )
    inputs = evidence["live"]["inputs"]

    metrics = compute_sizing_metrics(
        target_weights=inputs["target_weights"],
        signals=inputs["signals"],
        raw_weights=inputs["raw_weights"],
        max_weight=0.20,
    )

    assert metrics["n_target"] == 46
    assert metrics["n_eff"] == pytest.approx(44.7, abs=0.1)
    assert metrics["cap_bound_share"] == pytest.approx(0.761, abs=0.001)
    assert metrics["spearman_signal_weight"] == pytest.approx(-0.621, abs=0.001)
