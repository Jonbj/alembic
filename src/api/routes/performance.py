"""Performance and weights endpoints."""

import hashlib
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.api.deps import get_alpaca_trading_client, get_pg_store, get_redis_store
from src.llm.model_registry import (
    default_weights,
    model_ids_for_keys,
    normalize_model_selection,
    normalize_weights_for_active_models,
    sentiment_model_payload,
)
from src.portfolio.benchmark import compute_period_benchmark
from src.portfolio.spy import fetch_spy_closes, spy_fetch_end_date
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
log = logging.getLogger(__name__)


def _spy_fetch_end_date(to_date: str, today: date) -> date:
    """Compatibility seam for the existing performance API tests."""
    return spy_fetch_end_date(to_date, today)


def _fetch_spy_closes(
    from_date: str,
    to_date: str,
    redis=None,
) -> dict[str, float] | None:
    """Compatibility seam around the shared cached loader."""
    return fetch_spy_closes(from_date, to_date, redis)


_WEIGHT_MIN = 0.10
_WEIGHT_MAX = 0.70

_DEFAULT_WEIGHTS = {
    "weights": default_weights(),
    "source": "default",
}


class ApproveWeightsRequest(BaseModel):
    override_weights: dict[str, float] | None = None
    note: str | None = None


def _validate_override_weights(weights: dict[str, float]) -> dict[str, float]:
    _, keys, _ = normalize_model_selection("all")
    known = set(model_ids_for_keys(keys))
    for model_id, w in weights.items():
        if model_id not in known:
            raise HTTPException(status_code=422, detail=f"Unknown or inactive model: {model_id}")
        if w < _WEIGHT_MIN:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} below floor {_WEIGHT_MIN}",
            )
        if w > _WEIGHT_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} exceeds cap {_WEIGHT_MAX}",
            )
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            status_code=422, detail=f"Weights must sum to 1.0 (got {total:.4f})"
        )
    return weights


@router.get("/performance/latest")
async def get_latest_performance(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    report = redis.get_performance_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No performance report available yet")
    return report


@router.get("/performance/weekly")
async def get_weekly_report(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
    client: Annotated[object, Depends(get_alpaca_trading_client)],
) -> dict:
    """Return latest structured weekly report (computed Monday 04:00 UTC, TTL 9d).

    Capital efficiency is enriched with live Alpaca account + positions data at
    read time, since the cached snapshot is generated at 04:00 UTC before market
    open and cannot observe same-day deployed capital.
    """
    report = redis.get_weekly_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No weekly report available yet (corrupted or missing)")

    # Enrich capital_efficiency with live Alpaca account data.
    try:
        account = client.get_account()
        positions = client.get_all_positions()

        portfolio_value = float(account.portfolio_value or 0)
        deployed_notional = sum(float(p.market_value or 0) for p in positions)
        n_open = len(positions)
        depl_pct = deployed_notional / portfolio_value if portfolio_value > 0 else 0.0
        cash_pct = 1.0 - depl_pct
        theoretical_max_pct = 0.50  # 5 positions × 10%

        report["capital_efficiency"] = {
            "portfolio_value_usd": portfolio_value,
            "deployed_notional": deployed_notional,
            "n_open_positions": n_open,
            "deployment_pct": depl_pct,
            "cash_pct": cash_pct,
            "annual_cash_drag_pct": cash_pct * 0.045 * 100,
            "efficiency_ratio": (deployed_notional / (portfolio_value * theoretical_max_pct)) if portfolio_value > 0 else 0.0,
        }
    except Exception:
        pass  # fall back to cached value on Alpaca error

    # Enrich regime with live Redis data — the cached snapshot may have been
    # generated when regime:current was absent (e.g. key expired over the weekend
    # since the detector only runs Mon-Fri 07:00 UTC with a 25h TTL).
    try:
        regime_state = redis.get_regime()
        if regime_state is not None:
            label = str(regime_state.regime)
            mult = float(regime_state.multiplier)
            # confidence lives inside each llm_output dict, not as a top-level field
            llm_outputs = regime_state.llm_outputs or []
            confs = [float(o.get("confidence", 0)) for o in llm_outputs if o.get("confidence") is not None]
            conf = sum(confs) / len(confs) if confs else 0.0
            report["regime"] = {
                "label": label,
                "multiplier": mult,
                "confidence": conf,
                "deployment_ceiling_pct": 0.10 * mult * 5,
                "regime_discount_pct": (1.0 - mult) * 100,
            }
    except Exception:
        pass  # fall back to cached value on Redis error

    return report


@router.get("/weights/current")
async def get_current_weights(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    stored = redis.get_current_weights_stored()
    selection = redis.get_llm_models() or "all"
    _, keys, _ = normalize_model_selection(selection)
    active_model_ids = model_ids_for_keys(keys)

    source = "default"
    weights = _DEFAULT_WEIGHTS["weights"]
    if stored is not None:
        source = stored.get("source", "stored")
        weights = stored.get("weights", {})

    normalized, dropped = normalize_weights_for_active_models(weights, active_model_ids)
    return {
        "weights": normalized,
        "source": source,
        "dropped_models": dropped,
        "model_registry": sentiment_model_payload(selection),
    }


@router.get("/weights/suggestion")
async def get_weight_suggestion(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")
    try:
        computed_at = datetime.fromisoformat(suggestion["computed_at"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid computed_at format: {suggestion.get('computed_at', 'missing')}",
        )
    return {**suggestion, "expires_at": (computed_at + timedelta(days=7)).isoformat()}


@router.post("/weights/approve")
async def approve_weights(
    body: ApproveWeightsRequest,
    api_key: Annotated[str, Depends(require_api_key)],
    redis: Annotated[RedisStore, Depends(get_redis_store)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")

    if suggestion.get("freeze_reason") and body.override_weights is None:
        raise HTTPException(
            status_code=403,
            detail=f"Weight update frozen: {suggestion['freeze_reason']}",
        )

    if body.override_weights is not None:
        weights = _validate_override_weights(body.override_weights)
        dropped_models: list[str] = []
        source = "override"
    else:
        selection = redis.get_llm_models() or "all"
        _, keys, _ = normalize_model_selection(selection)
        weights, dropped_models = normalize_weights_for_active_models(
            suggestion["suggested_weights"],
            model_ids_for_keys(keys),
        )
        source = "suggestion"

    # Redis write happens before PostgreSQL write. If pg.log_weight_update() fails,
    # the weights are applied but not in the audit log. Acceptable trade-off: a missing
    # log row is preferable to blocking or reverting a weight update that is already live.
    redis.set_ensemble_weights(weights, source=source)
    redis._r.delete("ensemble:weights:suggestion:snapshot")

    # approved_by stores SHA-256[:8] — 8 hex chars are sufficient to distinguish operators
    # in the audit log; the truncated hash is not reversible to the raw API key.
    approved_by = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    log_id = pg.log_weight_update(
        source=source,
        applied_weights=weights,
        suggested_weights=suggestion.get("suggested_weights"),
        purified_icir=suggestion.get("purified_icir"),
        freeze_reason=suggestion.get("freeze_reason") or None,
        note=body.note,
        approved_by=approved_by,
    )

    return {
        "applied_weights": weights,
        "source": source,
        "log_id": log_id,
        "dropped_models": dropped_models,
    }


@router.get("/performance/daily")
def get_daily_pnl(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    redis: Annotated[RedisStore, Depends(get_redis_store)],
    from_date: str | None = None,
    to_date: str | None = None,
    days: int = 7,
) -> dict:
    """Return per-day P&L breakdown from closed trades in the local trades table.

    Args (query params):
        from_date: 'YYYY-MM-DD' (default: today - days)
        to_date:   'YYYY-MM-DD' (default: today)
        days:      shortcut for last N days when from_date/to_date not set (default 7)
    """
    today = date.today()
    try:
        _to = date.fromisoformat(to_date) if to_date else today
        _from = date.fromisoformat(from_date) if from_date else (_to - timedelta(days=days - 1))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {exc}") from exc

    if (_to - _from).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 365 days")

    day_rows = pg.fetch_daily_pnl(str(_from), str(_to))

    # NAV mark-to-market enrichment from risk_reports snapshots: closed-trade
    # sums alone hid the real day result (07-17: −$18.46 realized vs −$115.60
    # NAV). 7-day buffer before from_date to find the baseline snapshot.
    nav_change_period = None
    nav_rows: list[dict] = []
    try:
        nav_rows = pg.fetch_nav_daily(str(_from - timedelta(days=7)), str(_to))
        nav_by_day = {str(r["date"]): float(r["nav"]) for r in nav_rows}
        snap_days = sorted(nav_by_day)
        for r in day_rows:
            d = str(r["date"])
            nav = nav_by_day.get(d)
            prev_days = [s for s in snap_days if s < d]
            prev = nav_by_day[prev_days[-1]] if prev_days else None
            r["nav_eod"] = nav
            r["nav_change_1d"] = (
                round(nav - prev, 2) if nav is not None and prev is not None else None
            )
        in_range = [s for s in snap_days if str(_from) <= s <= str(_to)]
        baseline = [s for s in snap_days if s < str(_from)]
        if in_range and baseline:
            nav_change_period = round(
                nav_by_day[in_range[-1]] - nav_by_day[baseline[-1]], 2
            )
    except Exception as exc:
        log.warning("NAV MTM enrichment failed: %s", exc)
        for r in day_rows:
            r.setdefault("nav_eod", None)
            r.setdefault("nav_change_1d", None)

    # Beta-scaled benchmark + alpha: the book is ~30% net-long, so SPY outright
    # is an unfair bar; the fair benchmark is exposure × SPY. Alpha isolates what
    # the strategies add/subtract vs their market exposure. Fail-open.
    benchmark = {
        "alembic_return": None, "spy_return": None,
        "avg_exposure": None, "benchmark_return": None, "alpha": None,
    }
    try:
        _spy = _fetch_spy_closes(str(_from), str(_to), redis)
        benchmark = compute_period_benchmark(nav_rows, _spy, str(_from), str(_to))
    except Exception as exc:
        log.warning("Benchmark computation failed: %s", exc)

    total_gross_pnl = sum(r["total_gross_pnl"] for r in day_rows)
    total_costs = sum(r["total_costs"] for r in day_rows)
    total_net_pnl = sum(r["total_net_pnl"] for r in day_rows)
    total_trades = sum(r["trades_closed"] for r in day_rows)
    total_winners = sum(r["winners"] for r in day_rows)
    total_losers = sum(r["losers"] for r in day_rows)
    positive_days = sum(1 for r in day_rows if r["total_net_pnl"] > 0)
    negative_days = sum(1 for r in day_rows if r["total_net_pnl"] < 0)

    return {
        "from_date": str(_from),
        "to_date": str(_to),
        "days": day_rows,
        "summary": {
            "total_gross_pnl": round(total_gross_pnl, 2),
            "total_costs": round(total_costs, 2),
            "total_net_pnl": round(total_net_pnl, 2),
            "total_trades": total_trades,
            "winners": total_winners,
            "losers": total_losers,
            "win_rate": round(total_winners / total_trades, 4) if total_trades > 0 else 0.0,
            "positive_days": positive_days,
            "negative_days": negative_days,
            "nav_change_period": nav_change_period,
            "alembic_return": benchmark["alembic_return"],
            "spy_return": benchmark["spy_return"],
            "avg_exposure": benchmark["avg_exposure"],
            "benchmark_return": benchmark["benchmark_return"],
            "alpha": benchmark["alpha"],
        },
    }


@router.get("/performance/pnl")
def get_pnl(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
    period: str = "6M",
) -> dict:
    """Return portfolio P&L history from Alpaca (daily + monthly aggregate)."""
    from alpaca.trading.requests import GetPortfolioHistoryRequest

    history = client.get_portfolio_history(
        GetPortfolioHistoryRequest(period=period, timeframe="1D")
    )

    daily = []
    monthly: dict[str, float] = defaultdict(float)

    timestamps = history.timestamp or []
    profit_loss = history.profit_loss or []
    equities = history.equity or []

    for ts, pl, eq in zip(timestamps, profit_loss, equities):
        if ts is None:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_str = dt.strftime("%Y-%m-%d")
        month_str = dt.strftime("%Y-%m")
        daily.append({"date": date_str, "equity": eq, "profit_loss": pl or 0.0})
        monthly[month_str] += pl or 0.0

    return {
        "daily": daily,
        "monthly": [{"month": k, "pnl": round(v, 2)} for k, v in sorted(monthly.items())],
    }
