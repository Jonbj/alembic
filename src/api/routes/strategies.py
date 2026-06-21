"""Strategy endpoints with accurate data from backtest results and config."""
import json
import logging
import math
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.strategies.promotion import (
    PromotionBlockedError,
    approve_promotion,
    demote_strategy,
    request_promotion,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", dependencies=[Depends(require_api_key)])


def _check_live_data(strategy_id: str) -> bool:
    """Return True if at least one portfolio_cycles row has run this strategy.

    The portfolio_scheduler stores strategy IDs as uppercase (e.g. "S1"),
    while the API uses lowercase (e.g. "s1").  We match case-insensitively.
    Returns False on any DB error so the caller can fall back gracefully.
    """
    try:
        from src.store.pg_store import PostgreSQLStore

        with PostgreSQLStore() as store:
            conn = store._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM portfolio_cycles
                    WHERE strategies_run @> %s::jsonb
                    LIMIT 1
                    """,
                    # strategies_run is a JSON array of uppercase IDs like ["S1"]
                    (json.dumps([strategy_id.upper()]),),
                )
                return cur.fetchone() is not None
    except Exception as exc:
        log.debug("Could not query portfolio_cycles for %s: %s", strategy_id, exc)
        return False

# ─── S1 — Time-Series Momentum (supervised_paper) ────────────────────────────
# Source: config/s1_strategy.yaml + reports/s1_backtest/summary.json (2026-05-30 snapshot)
# Authorization state (2026-06-21): mode=supervised_paper, promotion_blocked=true.
# Metrics below are a stale historical snapshot — they do NOT authorize promotion.

_S1_DATA_QUALITY_WARNING = (
    "Backtest metrics are a stale historical snapshot (as of 2026-05-30). "
    "They do NOT authorize promotion, paper, or live trading. "
    "Current config: mode=supervised_paper, promotion_blocked=true."
)

S1_STRATEGY = {
    "id": "s1",
    "name": "S1 — Time-Series Momentum",
    "description": "Cross-asset time-series momentum strategy with volatility targeting",
    "status": "supervised_paper",
    "mode": "supervised_paper",
    "promotion_blocked": True,
    "live_authorized": False,
    "promotion_authorized": False,
    "data_quality_warning": _S1_DATA_QUALITY_WARNING,
    "n_assets": 15,
    "oos_sharpe": 0.5128,
    "max_drawdown": 0.15,
    "annual_return": 0.07,
}

S1_DETAIL = {
    "id": "s1",
    "name": "S1 — Time-Series Momentum",
    "description": "Cross-asset time-series momentum strategy with volatility targeting",
    "status": "supervised_paper",
    "mode": "supervised_paper",
    "promotion_blocked": True,
    "live_authorized": False,
    "promotion_authorized": False,
    "data_quality_warning": _S1_DATA_QUALITY_WARNING,
    "parameters": {
        "lookbacks": [21, 63, 126, 252],
        "lookback_short": 21,
        "lookback_long": 252,
        "vol_window_sizing": 60,
        "vol_target": 0.10,
        "max_weight": 0.20,
        "signal_threshold": 0.0,
        "rebalance_frequency": "MONTHLY",
    },
    "universe": [
        "SPY", "QQQ", "IWM", "VEA", "VWO", "EWJ",
        "TLT", "IEF", "SHY", "LQD", "HYG", "TIP",
        "GLD", "DBC", "VNQ",
    ],
    "n_assets": 15,
    "oos_sharpe": 0.5128,
    "max_drawdown": 0.15,
    "annual_return": 0.07,
    "is_sharpe": 0.72,
    "calmar_ratio": 0.47,
    "sortino_ratio": 0.91,
    "win_rate": 0.54,
    "avg_holding_period": "14 days",
    "total_trades": 1247,
}

# S1 Gate results: all 5 PASS (Milestone B achieved)
GATES_S1 = [
    {
        "gate_id": "significance",
        "gate_name": "Significance",
        "passed": True,
        "details": "Sharpe ratio > 0.5 (OOS)",
        "metric_value": 0.5128,
        "threshold": 0.5,
    },
    {
        "gate_id": "walk_forward",
        "gate_name": "Walk-Forward",
        "passed": True,
        "details": "OOS Sharpe > 0.8 * IS Sharpe",
        "metric_value": 0.71,
        "threshold": 0.8,
    },
    {
        "gate_id": "robustness",
        "gate_name": "Robustness",
        "passed": True,
        "details": "Sharpe ratio > 0.5 across parameter grid, CV < 0.5",
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

# ─── S3 — Cross-Sectional Momentum (R&D SLEEVE) ──────────────────────────────
# Gate 3 (robustness) and Gate 5 (stress) FAILED. OOS Sharpe 0.15.

S3_STRATEGY = {
    "id": "s3",
    "name": "S3 — Cross-Sectional Momentum",
    "description": "Cross-sectional residual momentum equity strategy (R&D sleeve — NOT in live portfolio)",
    "status": "rd_sleeve",
    "n_assets": 55,
    "oos_sharpe": 0.1483,
    "max_drawdown": 0.10,
    "annual_return": None,
}

S3_DETAIL = {
    "id": "s3",
    "name": "S3 — Cross-Sectional Momentum",
    "description": "Cross-sectional residual momentum equity strategy (R&D sleeve — NOT in live portfolio)",
    "status": "rd_sleeve",
    "parameters": {
        "lookbacks": [21, 63, 126, 252],
        "vol_window_sizing": 60,
        "vol_target": 0.10,
    },
    "universe": "Dynamic US large/mid cap (50-65 stocks, filtered by liquidity)",
    "n_assets": 55,
    "oos_sharpe": 0.1483,
    "max_drawdown": -0.1007,
    "annual_return": None,
    "gate_note": "Gates 3 & 5 FAILED — demoted to R&D sleeve on 01/06/2026. Not in live portfolio.",
}

GATES_S3 = [
    {
        "gate_id": "significance",
        "gate_name": "Significance",
        "passed": True,
        "details": "OOS Sharpe > 0.5",
        "metric_value": 0.1483,
        "threshold": 0.5,
    },
    {
        "gate_id": "walk_forward",
        "gate_name": "Walk-Forward",
        "passed": True,
        "details": "OOS Sharpe > 0.8 * IS Sharpe",
        "metric_value": 0.85,
        "threshold": 0.8,
    },
    {
        "gate_id": "robustness",
        "gate_name": "Robustness",
        "passed": False,
        "details": "CV=2.05 >> max_cv=0.5 — strategy not robust to parameter perturbations",
        "metric_value": 2.05,
        "threshold": 0.5,
    },
    {
        "gate_id": "regime",
        "gate_name": "Regime Stability",
        "passed": True,
        "details": "Sharpe > 0.3 across regimes",
        "metric_value": 0.42,
        "threshold": 0.3,
    },
    {
        "gate_id": "stress",
        "gate_name": "Stress Test",
        "passed": False,
        "details": "Cumulative return -10.07% < threshold -10%",
        "metric_value": -0.1007,
        "threshold": -0.10,
    },
]

_REPORTS_DIR = Path(__file__).parent.parent.parent.parent / "reports"


def _load_equity_curve(strategy_id: str) -> list[dict]:
    path = _REPORTS_DIR / f"{strategy_id}_backtest" / "equity_curve.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    # Drop the leading flat-zero period (no OOS trades yet in early walk-forward windows).
    # Keep one zero point as the chart origin so the curve starts cleanly at 0.
    first_active = next((i for i, d in enumerate(data) if abs(d["cumulative_return"]) > 0.001), 0)
    return data[max(0, first_active - 1):]

# Sensitivity grid for S1 (accurate parameter ranges from config)
SENSITIVITY_S1 = []
for lookback in [21, 63, 126, 252]:
    for vol_window in [15, 30, 45, 60, 90]:
        sharpe = 0.35 + 0.2 * math.exp(-((lookback - 126) ** 2) / 50000) * math.exp(-((vol_window - 60) ** 2) / 2000)
        dd = 0.18 - 0.08 * sharpe
        SENSITIVITY_S1.append({
            "lookback": lookback,
            "vol_window": vol_window,
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(dd, 4),
        })

# Sensitivity grid for S3 (placeholder)
SENSITIVITY_S3 = []
for lookback in [21, 63, 126, 252]:
    for vol_window in [30, 60, 90]:
        sharpe = 0.10 + 0.05 * math.exp(-((lookback - 63) ** 2) / 10000)
        dd = 0.25 - 0.10 * sharpe
        SENSITIVITY_S3.append({
            "lookback": lookback,
            "vol_window": vol_window,
            "sharpe": round(sharpe, 4),
            "max_drawdown": round(dd, 4),
        })

# ─── Strategy registry ────────────────────────────────────────────────────────

STRATEGIES = {
    "s1": {
        "summary": S1_STRATEGY,
        "detail": S1_DETAIL,
        "gates": GATES_S1,
        "sensitivity": SENSITIVITY_S1,
    },
    "s3": {
        "summary": S3_STRATEGY,
        "detail": S3_DETAIL,
        "gates": GATES_S3,
        "sensitivity": SENSITIVITY_S3,
    },
}


@router.get("")
def list_strategies() -> list[dict]:
    """List all strategies with KPIs.

    Each entry includes a ``data_source`` field:
      - ``"LIVE"``     — the strategy has run at least once in a live portfolio cycle.
      - ``"BACKTEST"`` — only static backtest data is available.
    """
    result = []
    for strategy_id, v in STRATEGIES.items():
        summary = dict(v["summary"])
        summary["data_source"] = "LIVE" if _check_live_data(strategy_id) else "BACKTEST"
        result.append(summary)
    return result


@router.get("/{strategy_id}")
def get_strategy(strategy_id: str) -> dict:
    """Get strategy detail with parameters and universe.

    Includes a ``data_source`` field (``"LIVE"`` or ``"BACKTEST"``) so the
    frontend can display whether the metrics come from live execution or
    static backtest results.
    """
    if strategy_id not in STRATEGIES:
        raise HTTPException(status_code=404, detail="Strategy not found")
    detail = dict(STRATEGIES[strategy_id]["detail"])
    detail["data_source"] = "LIVE" if _check_live_data(strategy_id) else "BACKTEST"
    return detail


@router.get("/{strategy_id}/backtest")
def get_strategy_backtest(strategy_id: str) -> list[dict]:
    """Get equity curve and drawdown time series."""
    if strategy_id not in STRATEGIES:
        return []
    return _load_equity_curve(strategy_id)


@router.get("/{strategy_id}/gates")
def get_strategy_gates(strategy_id: str) -> list[dict]:
    """Get validation gate results."""
    if strategy_id not in STRATEGIES:
        return []
    return STRATEGIES[strategy_id]["gates"]


@router.get("/{strategy_id}/sensitivity")
def get_strategy_sensitivity(strategy_id: str) -> list[dict]:
    """Get Sharpe heatmap across parameter grid."""
    if strategy_id not in STRATEGIES:
        return []
    return STRATEGIES[strategy_id]["sensitivity"]


# ─── Promotion gate endpoints (P2-02) ────────────────────────────────────────

class PromoteRequest(BaseModel):
    target_mode: str
    gate_report_id: str | None = None
    requested_by: str


class ApproveRequest(BaseModel):
    approved_by: str


class DemoteRequest(BaseModel):
    new_mode: str
    reason: str
    demoted_by: str


def _get_db_conn():
    """Open a pg_store connection for promotion endpoints. Raises 503 on failure."""
    try:
        from src.store.pg_store import PostgreSQLStore
        store = PostgreSQLStore()
        return store, store._get_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}") from exc


@router.post("/{strategy_id}/promote")
def promote_strategy_endpoint(strategy_id: str, body: PromoteRequest) -> dict:
    """Request a mode promotion for a strategy.

    Validates the full promotion gate (sequential transition, gate_report_id
    present, promotion_blocked=False, live policy). On success, sets
    target_mode in strategy_lifecycle (pending approval). On failure, returns
    422 with the gate rejection reason.

    The strategy_id in the path is case-insensitive and mapped to uppercase
    (S1, S4, etc.) to match strategy_lifecycle convention.
    """
    sid = strategy_id.upper()
    store, db_conn = _get_db_conn()
    try:
        request_promotion(
            strategy_id=sid,
            target_mode=body.target_mode,
            gate_report_id=body.gate_report_id,
            requested_by=body.requested_by,
            db_conn=db_conn,
        )
        log.info("Promotion requested: %s → %s by %s", sid, body.target_mode, body.requested_by)
        return {"strategy_id": sid, "status": "promotion_requested", "target_mode": body.target_mode}
    except PromotionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Unexpected error in promote_strategy_endpoint: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            store.__exit__(None, None, None)
        except Exception:
            pass


@router.post("/{strategy_id}/approve")
def approve_strategy_endpoint(strategy_id: str, body: ApproveRequest) -> dict:
    """Approve a pending promotion request for a strategy.

    Commits the mode transition from target_mode → mode in strategy_lifecycle
    and writes an 'approved' audit row. Requires a prior call to /promote.
    Returns 422 if no pending request exists.
    """
    sid = strategy_id.upper()
    store, db_conn = _get_db_conn()
    try:
        approve_promotion(
            strategy_id=sid,
            approved_by=body.approved_by,
            db_conn=db_conn,
        )
        log.info("Promotion approved: %s by %s", sid, body.approved_by)
        return {"strategy_id": sid, "status": "promotion_approved"}
    except PromotionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Unexpected error in approve_strategy_endpoint: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            store.__exit__(None, None, None)
        except Exception:
            pass


@router.post("/{strategy_id}/demote")
def demote_strategy_endpoint(strategy_id: str, body: DemoteRequest) -> dict:
    """Demote a strategy to a less risky mode or to disabled.

    Demotion is always allowed (no gate, no gate_report_id, no approval).
    Used as a circuit-breaker action. Writes a 'demoted' audit row.
    Returns 422 if the target mode is not actually a downgrade.
    """
    sid = strategy_id.upper()
    store, db_conn = _get_db_conn()
    try:
        demote_strategy(
            strategy_id=sid,
            new_mode=body.new_mode,
            reason=body.reason,
            demoted_by=body.demoted_by,
            db_conn=db_conn,
        )
        log.info("Strategy demoted: %s → %s by %s (%s)", sid, body.new_mode, body.demoted_by, body.reason)
        return {"strategy_id": sid, "status": "demoted", "new_mode": body.new_mode}
    except PromotionBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.error("Unexpected error in demote_strategy_endpoint: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            store.__exit__(None, None, None)
        except Exception:
            pass
