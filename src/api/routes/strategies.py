import math
"""S1 Strategies endpoints with mock data."""

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/strategies")

# Mock data for S1 Strategy
S1_STRATEGY = {
    "id": "s1",
    "name": "S1 — Time-Series Momentum",
    "description": "Cross-asset time-series momentum strategy with volatility targeting",
    "status": "validated",
    "n_assets": 15,
    "oos_sharpe": 0.65,
    "max_drawdown": 0.15,
    "annual_return": 0.07,
}

S1_DETAIL = {
    "id": "s1",
    "name": "S1 — Time-Series Momentum",
    "description": "Cross-asset time-series momentum strategy with volatility targeting",
    "status": "validated",
    "parameters": {
        "lookback_long": 120,
        "lookback_short": 20,
        "vol_window": 30,
        "vol_target": 0.10,
        "max_leverage": 2.0,
    },
    "universe": [
        "SPY", "EFA", "EEM", "AGG", "LQD", "TLT", "DBC", "GLD", "VNQ", "IYR",
        "XLF", "XLE", "XLI", "XLK", "XLV"
    ],
    "n_assets": 15,
    "oos_sharpe": 0.65,
    "max_drawdown": 0.15,
    "annual_return": 0.07,
    "is_sharpe": 0.72,
    "calmar_ratio": 0.47,
    "sortino_ratio": 0.91,
    "win_rate": 0.54,
    "avg_holding_period": "14 days",
    "total_trades": 1247,
}

# Mock equity curve: monthly returns from 2010-01 to 2024-12
# Realistic curve with ~7% annualized return, ~15% max DD
EQUITY_CURVE = []
cumulative = 0.0
for year in range(2010, 2025):
    for month in range(1, 13):
        # Simulate realistic monthly returns with volatility
        import random
        monthly_return = 0.005 + random.gauss(0, 0.04)  # ~6% annualized + noise
        cumulative += monthly_return
        drawdown = max(0, -cumulative + max(0, cumulative - abs(random.gauss(0, 0.03))))
        EQUITY_CURVE.append({
            "date": f"{year}-{month:02d}-01",
            "cumulative_return": round(cumulative, 6),
            "drawdown": round(drawdown, 6),
        })

# Gate results: 4 passed, 1 marginal (Robustness)
GATES = [
    {
        "gate_id": "significance",
        "gate_name": "Significance",
        "passed": True,
        "details": "Sharpe ratio > 0.5 (OOS)",
        "metric_value": 0.65,
        "threshold": 0.5,
    },
    {
        "gate_id": "walk_forward",
        "gate_name": "Walk-Forward",
        "passed": True,
        "details": "OOS Sharpe > 0.8 * IS Sharpe",
        "metric_value": 0.65 / 0.72,
        "threshold": 0.8,
    },
    {
        "gate_id": "robustness",
        "gate_name": "Robustness",
        "passed": False,
        "details": "Sharpe ratio > 0.5 across parameter grid",
        "metric_value": 0.45,
        "threshold": 0.5,
    },
    {
        "gate_id": "regime",
        "gate_name": "Regime Stability",
        "passed": True,
        "details": "Sharpe > 0.3 in bull/bear regimes",
        "metric_value": 0.68,
        "threshold": 0.3,
    },
    {
        "gate_id": "stress",
        "gate_name": "Stress Test",
        "passed": True,
        "details": "Max DD < 20% in 2008/2020 scenarios",
        "metric_value": 0.15,
        "threshold": 0.20,
    },
]

# Sensitivity grid: 6 lookbacks x 5 vol_windows
SENSITIVITY = []
for lookback in [20, 40, 60, 80, 100, 120]:
    for vol_window in [15, 20, 30, 45, 60]:
        # Peak near (lookback=60, vol_window=30)
        sharpe = 0.5 + 0.3 * math.exp(-((lookback - 60) ** 2) / 800) * math.exp(-((vol_window - 30) ** 2) / 200)
        dd = 0.18 - 0.08 * sharpe
        SENSITIVITY.append({
            "lookback": lookback,
            "vol_window": vol_window,
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(dd, 4),
        })


@router.get("")
def list_strategies() -> list[dict]:
    """List all strategies with KPIs."""
    return [S1_STRATEGY]


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str) -> dict:
    """Get strategy detail with parameters and universe."""
    if strategy_id != "s1":
        raise HTTPException(status_code=404, detail="Strategy not found")
    return S1_DETAIL


@router.get("/{strategy_id}/backtest")
def get_strategy_backtest(strategy_id: str) -> list[dict]:
    """Get equity curve and drawdown time series."""
    if strategy_id != "s1":
        return []
    return EQUITY_CURVE


@router.get("/{strategy_id}/gates")
def get_strategy_gates(strategy_id: str) -> list[dict]:
    """Get validation gate results."""
    if strategy_id != "s1":
        return []
    return GATES


@router.get("/{strategy_id}/sensitivity")
def get_strategy_sensitivity(strategy_id: str) -> list[dict]:
    """Get Sharpe heatmap across parameter grid."""
    if strategy_id != "s1":
        return []
    return SENSITIVITY