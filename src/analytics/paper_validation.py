"""Paper-trading validation metrics — pure aggregations over trade rows (point 3).

Backs ``GET /api/validation/metrics`` so the controlled-paper run can be monitored
(deployment, turnover, churn, realized net PnL, exit mix, regime) without manual SQL.
All functions are pure (operate on plain dicts) and unit-test cleanly.

Expected trade dict keys: symbol, entry_time, entry_notional, exit_time, exit_reason,
gross_pnl, net_pnl. Missing/None values are treated as 0 / open.
"""
from __future__ import annotations

from datetime import datetime, timezone


def _is_open(t: dict) -> bool:
    return t.get("exit_time") is None


def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _hold_minutes(t: dict) -> float | None:
    et, xt = t.get("entry_time"), t.get("exit_time")
    if et is None or xt is None:
        return None
    try:
        return (xt - et).total_seconds() / 60.0
    except Exception:
        return None


def compute_turnover(trades: list[dict], nav: float | None) -> dict:
    """Traded notional and turnover ratio (sum of entry notionals / NAV)."""
    traded = sum(_f(t.get("entry_notional")) for t in trades)
    ratio = (traded / nav) if (nav and nav > 0) else None
    return {
        "traded_notional": round(traded, 2),
        "turnover_ratio": round(ratio, 4) if ratio is not None else None,
    }


def compute_churn(trades: list[dict]) -> dict:
    """Round-trip / churn indicators: repeated opens per symbol, avg hold time."""
    opens_per_symbol: dict[str, int] = {}
    for t in trades:
        sym = t.get("symbol")
        if sym:
            opens_per_symbol[sym] = opens_per_symbol.get(sym, 0) + 1
    roundtrips = {s: n for s, n in opens_per_symbol.items() if n > 1}
    holds = [h for h in (_hold_minutes(t) for t in trades) if h is not None]
    avg_hold = round(sum(holds) / len(holds), 1) if holds else None
    return {
        "total_opens": len(trades),
        "distinct_symbols": len(opens_per_symbol),
        "roundtrip_symbols": dict(sorted(roundtrips.items(), key=lambda kv: -kv[1])),
        "roundtrip_count": len(roundtrips),
        "avg_hold_minutes": avg_hold,
    }


def compute_pnl(trades: list[dict]) -> dict:
    """Realized net/gross PnL, cost drag, win rate, and open exposure."""
    closed = [t for t in trades if not _is_open(t)]
    open_t = [t for t in trades if _is_open(t)]
    net = sum(_f(t.get("net_pnl")) for t in closed)
    gross = sum(_f(t.get("gross_pnl")) for t in closed)
    wins = sum(1 for t in closed if _f(t.get("net_pnl")) > 0)
    return {
        "closed_trades": len(closed),
        "open_trades": len(open_t),
        "realized_net_pnl": round(net, 2),
        "realized_gross_pnl": round(gross, 2),
        "cost_drag": round(gross - net, 2),
        "win_rate": round(wins / len(closed), 3) if closed else None,
        "open_notional": round(sum(_f(t.get("entry_notional")) for t in open_t), 2),
    }


def compute_exit_breakdown(trades: list[dict]) -> dict:
    """Count closed trades by exit_reason (stop_loss / portfolio_sell / ...)."""
    out: dict[str, int] = {}
    for t in trades:
        if not _is_open(t):
            r = t.get("exit_reason") or "unknown"
            out[r] = out.get(r, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def compute_validation_metrics(
    trades: list[dict],
    nav: float | None = None,
    regime_mult: float | None = None,
    window_days: int | None = None,
) -> dict:
    """Aggregate all paper-validation metrics into a single response dict."""
    pnl = compute_pnl(trades)
    deployment_pct = None
    if nav and nav > 0:
        deployment_pct = round(pnl["open_notional"] / nav, 4)
    return {
        "window_days": window_days,
        "nav": round(nav, 2) if nav else None,
        "regime_mult": regime_mult,
        "deployment_pct": deployment_pct,
        "turnover": compute_turnover(trades, nav),
        "churn": compute_churn(trades),
        "pnl": pnl,
        "exits": compute_exit_breakdown(trades),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
