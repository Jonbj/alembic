"""Strategy backtest results API routes."""

import json
import random
from datetime import date
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/strategies")

_RESULTS_DIR = Path(__file__).parent.parent.parent.parent / "results"


def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _mock_equity_curve() -> list[dict]:
    """Synthetic monthly equity curve 1995-01-01 → 2024-12-31 (seed=42)."""
    rng = random.Random(42)
    mean_monthly = 0.00565   # ≈7% annual
    std_monthly = 0.04330    # ≈15% annual vol
    points: list[dict] = []
    cum = 1.0
    peak = 1.0
    dt = date(1995, 1, 1)
    end = date(2024, 12, 31)
    while dt <= end:
        r = rng.gauss(mean_monthly, std_monthly)
        cum *= 1.0 + r
        peak = max(peak, cum)
        points.append({
            "date": dt.isoformat(),
            "cumulative_return": round(cum - 1.0, 4),
            "drawdown": round(cum / peak - 1.0, 4),
        })
        dt = date(dt.year + 1, 1, 1) if dt.month == 12 else date(dt.year, dt.month + 1, 1)
    return points


_STRATEGIES: list[dict] = [
    {
        "id": "s1",
        "name": "S1 — Time-Series Momentum",
        "description": (
            "Cross-sectional time-series momentum su 15 ETF. "
            "Segnale: rendimento passato a 12-1 mesi. Ribilanciamento mensile."
        ),
        "status": "testing",
        "n_assets": 15,
        "oos_sharpe": 0.65,
        "max_drawdown": -0.148,
        "annual_return": 0.071,
    }
]

_BACKTEST: dict[str, dict] = {
    "s1": {
        "strategy_id": "s1",
        "period": {"start": "1995-01-01", "end": "2024-12-31"},
        "metrics": {
            "sharpe": 0.65,
            "sortino": 0.88,
            "calmar": 0.47,
            "max_drawdown": -0.148,
            "annual_return": 0.071,
            "annual_vol": 0.109,
            "win_rate": 0.574,
            "skewness": -0.23,
            "kurtosis": 1.87,
        },
        "per_asset": [
            {"ticker": "SPY", "weight": 0.12, "contribution": 0.028, "sharpe": 0.71},
            {"ticker": "EFA", "weight": 0.09, "contribution": 0.015, "sharpe": 0.48},
            {"ticker": "EEM", "weight": 0.08, "contribution": 0.011, "sharpe": 0.39},
            {"ticker": "IEF", "weight": 0.07, "contribution": 0.009, "sharpe": 0.62},
            {"ticker": "TLT", "weight": 0.06, "contribution": 0.007, "sharpe": 0.54},
            {"ticker": "GLD", "weight": 0.07, "contribution": 0.008, "sharpe": 0.44},
            {"ticker": "VNQ", "weight": 0.06, "contribution": 0.006, "sharpe": 0.31},
            {"ticker": "HYG", "weight": 0.05, "contribution": 0.004, "sharpe": 0.28},
            {"ticker": "LQD", "weight": 0.06, "contribution": 0.005, "sharpe": 0.41},
            {"ticker": "DBC", "weight": 0.07, "contribution": -0.003, "sharpe": -0.12},
            {"ticker": "XLE", "weight": 0.07, "contribution": 0.002, "sharpe": 0.18},
            {"ticker": "XLF", "weight": 0.06, "contribution": 0.003, "sharpe": 0.22},
            {"ticker": "XLK", "weight": 0.06, "contribution": 0.009, "sharpe": 0.67},
            {"ticker": "IWM", "weight": 0.07, "contribution": -0.001, "sharpe": -0.08},
            {"ticker": "AGG", "weight": 0.05, "contribution": 0.004, "sharpe": 0.33},
        ],
    }
}

_GATES: dict[str, list[dict]] = {
    "s1": [
        {
            "gate_id": "gate_1",
            "gate_name": "Significatività Statistica",
            "passed": True,
            "details": "Sharpe OOS > 0 con p-value < 0.05 (test t su rendimenti OOS mensili)",
            "metric_value": 0.65,
            "threshold": 0.0,
        },
        {
            "gate_id": "gate_2",
            "gate_name": "Walk-Forward",
            "passed": True,
            "details": "Sharpe medio walk-forward positivo su 8 finestre di 3 anni ciascuna",
            "metric_value": 0.58,
            "threshold": 0.0,
        },
        {
            "gate_id": "gate_3",
            "gate_name": "Robustezza Parametrica",
            "passed": False,
            "details": "Sensibilità elevata a lookback_long: range Sharpe [0.12, 0.94] — soglia spread max 0.5",
            "metric_value": 0.82,
            "threshold": 0.5,
        },
        {
            "gate_id": "gate_4",
            "gate_name": "Stabilità di Regime",
            "passed": False,
            "details": "Performance degradata in regime risk-off: Sharpe -0.31 vs +0.89 in regime risk-on",
            "metric_value": -0.31,
            "threshold": 0.0,
        },
        {
            "gate_id": "gate_5",
            "gate_name": "Stress Test",
            "passed": True,
            "details": "Max drawdown nei periodi di crisi (2000, 2008, 2020) entro limite del 25%",
            "metric_value": -0.221,
            "threshold": -0.25,
        },
    ]
}

_SENSITIVITY: dict[str, list[dict]] = {
    "s1": [
        {
            "parameter": "lookback_long",
            "values": [3, 6, 9, 12],
            "results": [
                {"value": 3,  "sharpe": 0.31, "max_dd": -0.198},
                {"value": 6,  "sharpe": 0.47, "max_dd": -0.172},
                {"value": 9,  "sharpe": 0.59, "max_dd": -0.155},
                {"value": 12, "sharpe": 0.65, "max_dd": -0.148},
            ],
        },
        {
            "parameter": "vol_window",
            "values": [1, 3, 6],
            "results": [
                {"value": 1, "sharpe": 0.52, "max_dd": -0.162},
                {"value": 3, "sharpe": 0.65, "max_dd": -0.148},
                {"value": 6, "sharpe": 0.61, "max_dd": -0.153},
            ],
        },
        {
            "parameter": "rebalance_top_n",
            "values": [3, 5, 7, 10],
            "results": [
                {"value": 3,  "sharpe": 0.71, "max_dd": -0.189},
                {"value": 5,  "sharpe": 0.65, "max_dd": -0.148},
                {"value": 7,  "sharpe": 0.58, "max_dd": -0.135},
                {"value": 10, "sharpe": 0.44, "max_dd": -0.121},
            ],
        },
        {
            "parameter": "sharpe_grid",
            "values": [],
            "results": [],
            "lookback_long_values": [3, 6, 9, 12],
            "vol_window_values": [1, 3, 6],
            "grid": [
                [0.28, 0.31, 0.29],
                [0.41, 0.47, 0.44],
                [0.55, 0.59, 0.57],
                [0.61, 0.65, 0.62],
            ],
        },
    ]
}


@router.get("")
async def list_strategies() -> list:
    data = _load_json(_RESULTS_DIR / "strategies_list.json")
    return data if data is not None else _STRATEGIES


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str) -> dict:
    data = _load_json(_RESULTS_DIR / strategy_id / "summary.json")
    if data is not None:
        return data
    match = next((s for s in _STRATEGIES if s["id"] == strategy_id), None)
    return match or {}


@router.get("/{strategy_id}/backtest")
async def get_backtest(strategy_id: str) -> dict:
    data = _load_json(_RESULTS_DIR / strategy_id / "backtest_summary.json")
    if data is not None:
        return data
    result = _BACKTEST.get(strategy_id)
    if result is None:
        return {}
    result = dict(result)
    curve = _load_json(_RESULTS_DIR / strategy_id / "equity_curve.json")
    result["equity_curve"] = curve if curve is not None else _mock_equity_curve()
    return result


@router.get("/{strategy_id}/gates")
async def get_gates(strategy_id: str) -> list:
    data = _load_json(_RESULTS_DIR / strategy_id / "gate_report.json")
    return data if data is not None else _GATES.get(strategy_id, [])


@router.get("/{strategy_id}/sensitivity")
async def get_sensitivity(strategy_id: str) -> list:
    data = _load_json(_RESULTS_DIR / strategy_id / "sensitivity.json")
    return data if data is not None else _SENSITIVITY.get(strategy_id, [])
