#!/usr/bin/env python3
"""Historical replay for stop-loss variants — full gate spec §10.

Fetches 15-minute Alpaca bars for each closed-trade window, simulates multiple
stop variants, computes counterfactual P&L with costs, and reports the
measurement gates required before enabling `vol_scaled` live.

Usage:
    export $(grep -E '^(DATABASE_URL|ALPACA_API_KEY|ALPACA_SECRET_KEY|ALPACA_BASE_URL)=' .env)
    .venv/bin/python scripts/replay_stop_loss.py --start 2026-06-01 --end 2026-07-11 \
        --bars-csv data/daily_close.csv --mode report

The script is read-only/idempotent: it never writes to the database.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from src.config import config
from src.costs.calculator import TradeCostCalculator
from src.portfolio.stop_policy import StopPolicy
from src.store.pg_store import PostgreSQLStore


# ---------------------------------------------------------------------------
# Config / helpers
# ---------------------------------------------------------------------------


def _load_risk_cfg() -> dict:
    import yaml

    path = os.path.join(os.path.dirname(__file__), "..", "config", "trading.yaml")
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    risk = cfg.get("risk", {})
    return {
        "stop_loss": float(risk.get("stop_loss", 0.02)),
        "stop_loss_mode": "vol_scaled",
        "stop_strategy_params": risk.get("stop_strategy_params", {}),
        "stop_sigma_lookback_fast": risk.get("stop_sigma_lookback_fast", 20),
        "stop_sigma_lookback_slow": risk.get("stop_sigma_lookback_slow", 63),
        "stop_sigma_ewma_floor_ratio": risk.get("stop_sigma_ewma_floor_ratio", 0.8),
        "broker_disaster_stop": risk.get("broker_disaster_stop", {}),
        "stop_risk_budget_bp_per_pos": risk.get("stop_risk_budget_bp_per_pos", 12),
        "stop_risk_budget_bp_aggregate": risk.get("stop_risk_budget_bp_aggregate", 100),
    }


def _load_daily_bars(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df.sort_index(inplace=True)
    # Ensure index is timezone-aware UTC.
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df


def _strategy_for_trade(trade: dict) -> str:
    return trade.get("stop_strategy") or ("S4" if trade.get("signal_id") is not None else "S1")


def _trade_qty(trade: dict) -> float:
    qty = trade.get("qty")
    if qty:
        return float(qty)
    entry_price = float(trade.get("entry_price") or 0.0)
    entry_notional = float(trade.get("entry_notional") or 0.0)
    if entry_price > 0 and entry_notional > 0:
        return entry_notional / entry_price
    return 0.0


def _clean_trade(trade: dict) -> dict | None:
    """Return a normalized trade dict or None if unusable."""
    entry_price = _num(trade.get("entry_price"))
    exit_price = _num(trade.get("exit_price"))
    entry_notional = _num(trade.get("entry_notional"))
    qty = _trade_qty(trade)
    entry_time = _dt(trade.get("entry_time"))
    exit_time = _dt(trade.get("exit_time"))
    net_pnl = _num(trade.get("net_pnl"))

    if not all([entry_price, exit_price, entry_notional, qty, entry_time, exit_time]):
        return None
    if trade.get("exit_reason") == "LEGACY_FLATTEN":
        return None
    if net_pnl is None:
        return None
    return {
        **trade,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_notional": entry_notional,
        "qty": qty,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "net_pnl": net_pnl,
        "strategy": _strategy_for_trade(trade),
    }


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v is None or np.isnan(v):
        return None
    return float(v)


def _dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d
        except ValueError:
            return None
    return None


def _atr14(close: pd.Series) -> float:
    """Simplified ATR proxy using daily close range (high=low=close unavailable)."""
    log_hl = close.rolling(14, min_periods=14).apply(lambda s: np.log(max(s.max() / s.min(), 1.0001)), raw=False)
    return float(log_hl.iloc[-1]) if not pd.isna(log_hl.iloc[-1]) else 0.0


def _atr_stop_distance(symbol: str, close_series: pd.Series, k: float, floor: float, cap: float) -> float:
    atr = _atr14(close_series)
    last_price = float(close_series.iloc[-1])
    d = min(max(k * atr, floor), cap) if last_price > 0 else floor
    return d


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------


def _fetch_intraday_bars(trades: list[dict], data_client: StockHistoricalDataClient) -> dict[str, pd.DataFrame]:
    """Fetch 15-min bars per symbol covering all trade windows."""
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)

    result: dict[str, pd.DataFrame] = {}
    for symbol, sym_trades in by_symbol.items():
        starts = [t["entry_time"] for t in sym_trades]
        ends = []
        for t in sym_trades:
            hmax = _hmax_for_strategy(t["strategy"])
            ends.append(min(t["exit_time"], t["entry_time"] + hmax) + timedelta(hours=1))
        start = min(starts) - timedelta(hours=2)
        end = max(ends)

        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=start,
                end=end,
                adjustment=Adjustment.ALL,
            )
            bars = data_client.get_stock_bars(req).df
            if bars.empty:
                print(f"  No 15-min bars for {symbol}; falling back to daily close path", file=sys.stderr)
                continue

            # Flatten multi-index if present.
            if hasattr(bars.index, "levels"):
                sym_vals = bars.index.get_level_values(0)
                if symbol in sym_vals:
                    bars = bars.loc[symbol].copy()
                else:
                    continue
            bars = bars.sort_index()
            if bars.index.tz is None:
                bars.index = bars.index.tz_localize("UTC")
            result[symbol] = bars
        except APIError as exc:
            print(f"  Alpaca API error for {symbol}: {exc} — skipping symbol", file=sys.stderr)
        except Exception as exc:
            print(f"  Failed to fetch bars for {symbol}: {exc} — skipping", file=sys.stderr)
    return result


def _hmax_for_strategy(strategy: str) -> timedelta:
    if strategy == "S1":
        return timedelta(days=21)
    if strategy == "S4":
        return timedelta(days=7)
    return timedelta(days=7)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


def _build_variants(trade: dict, daily_bars: pd.DataFrame, risk_cfg: dict) -> dict[str, dict]:
    """Return a dict of variant definitions for this trade.

    Keys: fixed_2pct, fixed_3pct, fixed_5pct, fixed_7pct, vol_scaled, vol_scaled_k25,
          vol_scaled_k30, vol_scaled_k35, vol_scaled_k40, atr14_x2, atr14_x3,
          no_protective.
    Each value: {"d_init": float, "name": str}.
    """
    symbol = trade["symbol"]
    strategy = trade["strategy"]
    entry_price = trade["entry_price"]
    entry_time = trade["entry_time"]

    variants: dict[str, dict] = {
        "fixed_2pct": {"d_init": 0.02, "name": "Fixed 2%"},
        "fixed_3pct": {"d_init": 0.03, "name": "Fixed 3%"},
        "fixed_5pct": {"d_init": 0.05, "name": "Fixed 5%"},
        "fixed_7pct": {"d_init": 0.07, "name": "Fixed 7%"},
        "no_protective": {"d_init": 1.0, "name": "No protective (strategy-exit only)"},
    }

    # Vol-scaled using bars up to entry_time (no look-ahead).
    daily_before = daily_bars.loc[daily_bars.index <= entry_time]
    policy = StopPolicy(risk_cfg, bars_df=daily_before)
    frozen = policy.freeze(symbol, strategy, entry_price, entry_time)
    variants["vol_scaled"] = {"d_init": frozen.d_init, "name": f"Vol-scaled (k config, d={frozen.d_init:.3f})"}

    # Sweep k values.
    for k in [2.5, 3.0, 3.5, 4.0]:
        sweep_cfg = dict(risk_cfg)
        sweep_params = {s: dict(p) for s, p in (risk_cfg.get("stop_strategy_params", {}) or {}).items()}
        for s in sweep_params:
            sweep_params[s]["k"] = k
        sweep_params.setdefault("default", {"k": k, "floor": 0.04, "cap": 0.12})
        sweep_cfg["stop_strategy_params"] = sweep_params
        pol = StopPolicy(sweep_cfg, bars_df=daily_before)
        fr = pol.freeze(symbol, strategy, entry_price, entry_time)
        variants[f"vol_scaled_k{int(k*10)}"] = {"d_init": fr.d_init, "name": f"Vol-scaled k={k} (d={fr.d_init:.3f})"}

    # ATR variants.
    if symbol in daily_before.columns and len(daily_before[symbol].dropna()) >= 14:
        close_series = daily_before[symbol].dropna()
        for k in [2.0, 3.0]:
            d = _atr_stop_distance(symbol, close_series, k, floor=0.02, cap=0.15)
            variants[f"atr14_x{int(k)}"] = {"d_init": d, "name": f"ATR(14)×{k} (d={d:.3f})"}

    return variants


def _simulate_trade(
    trade: dict,
    bars: pd.DataFrame | None,
    variant: dict,
    cost_calc: TradeCostCalculator,
) -> dict[str, Any]:
    """Simulate a single variant for one trade.

    Returns exit info including exit_price, exit_time, pnl, costs, breached flag.
    """
    symbol = trade["symbol"]
    strategy = trade["strategy"]
    entry_price = trade["entry_price"]
    entry_time = trade["entry_time"]
    real_exit_time = trade["exit_time"]
    real_exit_price = trade["exit_price"]
    real_exit_reason = trade.get("exit_reason")
    qty = trade["qty"]
    d_init = variant["d_init"]

    trigger_price = entry_price * (1.0 - d_init)
    hmax = _hmax_for_strategy(strategy)
    horizon_end = min(real_exit_time, entry_time + hmax)

    exit_time = real_exit_time
    exit_price = real_exit_price
    exit_reason = real_exit_reason
    breached = False
    mae_pct = 0.0
    mfe_pct = 0.0

    # No protective stop: exit always at strategy exit.
    if d_init >= 0.99:
        pass
    elif bars is not None and not bars.empty:
        path = bars[(bars.index >= entry_time) & (bars.index <= horizon_end)].copy()
        if not path.empty:
            lows = path["low"].values
            highs = path["high"].values
            closes = path["close"].values
            idxs = path.index

            # MAE / MFE as % from entry (long only in this portfolio).
            if len(lows):
                mae_pct = float((np.min(lows) - entry_price) / entry_price)
                mfe_pct = float((np.max(highs) - entry_price) / entry_price)

            breach_mask = lows <= trigger_price
            if breach_mask.any():
                breach_idx = int(np.argmax(breach_mask))
                breach_bar_time = idxs[breach_idx]
                # Slippage fill: next bar open if available, else trigger*(1-slip).
                slip = 0.0005
                if breach_idx + 1 < len(idxs):
                    next_open = float(path["open"].iloc[breach_idx + 1])
                    fill = min(trigger_price * (1.0 - slip), next_open)
                else:
                    fill = trigger_price * (1.0 - slip)
                exit_time = breach_bar_time
                exit_price = fill
                exit_reason = "stop_loss"
                breached = True

    # Costs: entry + exit.
    entry_notional = entry_price * qty
    exit_notional = exit_price * qty
    entry_costs = cost_calc.compute(symbol, entry_notional, qty, entry_price, side="BUY")
    exit_costs = cost_calc.compute(symbol, exit_notional, qty, exit_price, side="SELL")
    total_cost_usd = entry_costs.total_cost_usd + exit_costs.total_cost_usd

    gross_pnl = (exit_price - entry_price) * qty
    net_pnl = gross_pnl - total_cost_usd

    return {
        "trade_id": trade["id"],
        "symbol": symbol,
        "strategy": strategy,
        "variant": variant["name"],
        "d_init": d_init,
        "entry_price": entry_price,
        "entry_time": entry_time,
        "exit_price": exit_price,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "breached": breached,
        "mae_pct": mae_pct,
        "mfe_pct": mfe_pct,
        "qty": qty,
        "entry_notional": entry_notional,
        "gross_pnl": gross_pnl,
        "costs": total_cost_usd,
        "net_pnl": net_pnl,
        "real_net_pnl": trade["net_pnl"],
        "real_exit_reason": real_exit_reason,
    }


def _run_simulation(trades: list[dict], bars_map: dict[str, pd.DataFrame], daily_bars: pd.DataFrame, risk_cfg: dict) -> pd.DataFrame:
    cost_calc = TradeCostCalculator()
    rows: list[dict] = []
    for trade in trades:
        variants = _build_variants(trade, daily_bars, risk_cfg)
        bars = bars_map.get(trade["symbol"])
        for key, variant in variants.items():
            sim = _simulate_trade(trade, bars, variant, cost_calc)
            sim["variant_key"] = key
            rows.append(sim)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def _bootstrap_delta_pnl(df: pd.DataFrame, baseline: str, candidate: str, n_boot: int = 1000) -> float:
    """Return % of bootstrap resamples where candidate net_pnl > baseline net_pnl."""
    base_df = df[df["variant_key"] == baseline][["trade_id", "net_pnl"]].set_index("trade_id").sort_index()
    cand_df = df[df["variant_key"] == candidate][["trade_id", "net_pnl"]].set_index("trade_id").sort_index()
    common = base_df.index.intersection(cand_df.index)
    if len(common) == 0:
        return 0.0
    base_pnls = base_df.loc[common, "net_pnl"].values
    cand_pnls = cand_df.loc[common, "net_pnl"].values
    n = len(common)
    diffs = cand_pnls - base_pnls
    positives = 0
    for _ in range(n_boot):
        idx = np.random.randint(0, n, size=n)
        if np.sum(diffs[idx]) > 0:
            positives += 1
    return positives / n_boot


def _portfolio_max_dd(pnls: np.ndarray) -> float:
    """Max drawdown from cumulative P&L series."""
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = (peak - cum) / np.where(peak > 0, peak, 1.0)
    return float(np.max(dd)) if len(dd) else 0.0


def _es95(pnls: np.ndarray) -> float:
    """Expected shortfall at 95% (average of worst 5%)."""
    if len(pnls) == 0:
        return 0.0
    var = np.percentile(pnls, 5)
    tail = pnls[pnls <= var]
    return float(np.mean(tail)) if len(tail) else 0.0


def _max_open_stop_risk(sub: pd.DataFrame, nav_est: float) -> float:
    """Return peak aggregate open-stop risk in bp of NAV across all timestamps.

    Simultaneously-open positions contribute d_init * notional each.
    """
    if sub.empty or nav_est <= 0:
        return 0.0
    events: list[tuple[datetime, float, str]] = []
    for _, row in sub.iterrows():
        risk = row["d_init"] * row["entry_notional"]
        events.append((row["entry_time"], risk, "add"))
        events.append((row["exit_time"], -risk, "remove"))
    events.sort(key=lambda x: x[0])
    current = 0.0
    peak = 0.0
    for _, delta, _ in events:
        current += delta
        if current > peak:
            peak = current
    return float(peak / nav_est * 10000.0)


def _classify_false_stop(row: pd.Series) -> str | None:
    """Classify whether a simulated stop was a false stop relative to the real outcome."""
    if not row["breached"]:
        return None
    # If real exit was also stop_loss, treat as true protective stop.
    if row["real_exit_reason"] == "stop_loss":
        return "true_stop"
    # If simulated stop but real trade was profitable or recovered, it's a false stop.
    if row["real_net_pnl"] > 0:
        return "false_stop"
    # If price after stop continued down (MAE lower than trigger) — true.
    if row["mae_pct"] < -row["d_init"] * 1.5:
        return "true_stop"
    return "false_stop"


def _analyze_variant(df: pd.DataFrame, variant_key: str, baseline_key: str, nav_est: float) -> dict[str, Any]:
    sub = df[df["variant_key"] == variant_key].copy()
    base = df[df["variant_key"] == baseline_key].copy()
    if sub.empty or base.empty:
        return {}

    sub["false_stop"] = sub.apply(_classify_false_stop, axis=1)
    base["false_stop"] = base.apply(_classify_false_stop, axis=1)

    false_stops = int((sub["false_stop"] == "false_stop").sum())
    base_false_stops = int((base["false_stop"] == "false_stop").sum())
    reduction = (
        (base_false_stops - false_stops) / base_false_stops * 100
        if base_false_stops > 0
        else 0.0
    )

    median_pnl = float(sub["net_pnl"].median())
    base_median_pnl = float(base["net_pnl"].median())

    bootstrap_pos = _bootstrap_delta_pnl(df, baseline_key, variant_key) * 100.0

    max_dd = _portfolio_max_dd(sub["net_pnl"].values)
    base_max_dd = _portfolio_max_dd(base["net_pnl"].values)
    dd_delta = max_dd - base_max_dd

    es95 = _es95(sub["net_pnl"].values)
    base_es95 = _es95(base["net_pnl"].values)
    es95_delta = es95 - base_es95

    # Open-stop risk in bp of estimated NAV.
    open_risk = _max_open_stop_risk(sub, nav_est)
    budget_bp = 100.0  # aggregate sleeve budget from trading.yaml

    # Name-dependence: top 2 symbols absolute P&L contribution.
    by_sym = sub.groupby("symbol")["net_pnl"].sum().abs().sort_values(ascending=False)
    total_abs = by_sym.sum()
    top2_pct = float(by_sym.head(2).sum() / total_abs * 100.0) if total_abs > 0 else 0.0

    # Costs included flag.
    costs_included = bool((sub["costs"] != 0).any())

    return {
        "variant": variant_key,
        "trades": len(sub),
        "false_stops": false_stops,
        "base_false_stops": base_false_stops,
        "false_stop_reduction_pct": round(reduction, 1),
        "median_net_pnl": round(median_pnl, 2),
        "base_median_net_pnl": round(base_median_pnl, 2),
        "bootstrap_delta_positive_pct": round(bootstrap_pos, 1),
        "max_dd": round(max_dd, 4),
        "dd_delta": round(dd_delta, 4),
        "es95": round(es95, 2),
        "es95_delta": round(es95_delta, 2),
        "open_stop_risk_bp": round(open_risk, 1),
        "open_stop_budget_bp": round(budget_bp, 1),
        "top2_name_contrib_pct": round(top2_pct, 1),
        "costs_included": costs_included,
        "cum_pnl": round(float(sub["net_pnl"].sum()), 2),
        "base_cum_pnl": round(float(base["net_pnl"].sum()), 2),
    }


def _walk_forward_split(trades: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sort trades by entry_time and split 70/30 train/test."""
    sorted_trades = sorted(trades, key=lambda t: t["entry_time"])
    n = len(sorted_trades)
    split = int(n * 0.7)
    return sorted_trades[:split], sorted_trades[split:]


def _gate_check(m: dict[str, Any]) -> tuple[bool, list[tuple[str, bool, str]]]:
    """Evaluate the spec §10 gates for a candidate vs fixed 2% baseline."""
    checks: list[tuple[str, bool, str]] = []

    def _check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))

    _check(
        "false-stop reduction",
        m.get("false_stop_reduction_pct", 0) >= 40,
        f"{m.get('false_stop_reduction_pct', 0):.1f}% (gate >= 40%)",
    )
    _check(
        "median net P&L",
        m.get("median_net_pnl", 0) > m.get("base_median_net_pnl", 0),
        f"fixed {m.get('base_median_net_pnl', 0):.2f} vs vol {m.get('median_net_pnl', 0):.2f}",
    )
    _check(
        "bootstrap delta P&L positive",
        m.get("bootstrap_delta_positive_pct", 0) >= 70,
        f"{m.get('bootstrap_delta_positive_pct', 0):.1f}% resamples (gate >= 70-75%)",
    )
    _check(
        "max DD not materially worse",
        m.get("dd_delta", 0) <= 0.10,
        f"delta {m.get('dd_delta', 0):.4f} (gate <= 0.10)",
    )
    base_es95 = m.get("base_es95", 0)
    es95_delta = m.get("es95_delta", 0)
    if base_es95 < 0:
        es95_ok = es95_delta >= -abs(base_es95) * 0.10
    else:
        # Base has essentially no tail risk; candidate must keep tail losses below 1% NAV.
        es95_ok = (m.get("es95", 0) or 0) >= -0.01 * m.get("nav_est", 110_000)
    _check(
        "ES95 not materially worse",
        es95_ok,
        f"delta {es95_delta:.2f} vs base {base_es95:.2f}",
    )
    _check(
        "open-stop risk within budget",
        m.get("open_stop_risk_bp", 0) <= m.get("open_stop_budget_bp", 0),
        f"{m.get('open_stop_risk_bp', 0):.1f} bp vs budget {m.get('open_stop_budget_bp', 0):.1f} bp",
    )
    _check(
        "name-dependence",
        m.get("top2_name_contrib_pct", 100) <= 50,
        f"top-2 contrib {m.get('top2_name_contrib_pct', 0):.1f}% (gate <= 50%)",
    )
    _check(
        "costs included",
        m.get("costs_included", False),
        "yes" if m.get("costs_included") else "no",
    )

    ok = all(c[1] for c in checks)
    return ok, checks


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _print_report(report: dict[str, Any]) -> None:
    print("\n=== Stop-Loss Replay Report (Round 2) ===")
    print(f"Total trades analyzed: {report['total_trades']}")
    print(f"Symbols covered: {report['symbol_count']}")
    print(f"Intraday 15-min coverage: {report['intraday_coverage_pct']:.0f}% of trades")
    print(f"Walk-forward split: train {report['train_count']} / test {report['test_count']}")
    print(f"Estimated NAV used for risk budgeting: ${report['nav_est']:,.0f}")

    print("\n--- Full-sample gate table ---")
    _print_gate_table(report["full_sample"])

    print("\n--- Walk-forward OOS gate table ---")
    _print_gate_table(report["oos"])

    print("\n--- Variant summary (full sample) ---")
    for key, m in report["variants"].items():
        status = "RECOMMENDED" if key == report.get("recommended_variant") else ""
        print(
            f"  {key:22s} cum=${m['cum_pnl']:8.2f} median=${m['median_net_pnl']:6.2f} "
            f"false_red={m['false_stop_reduction_pct']:5.1f}% boot={m['bootstrap_delta_positive_pct']:5.1f}% "
            f"maxDD={m['max_dd']:.3f} ES95={m['es95']:6.2f} {status}"
        )

    print("\n--- Recommendation ---")
    print(report["recommendation"])


def _print_gate_table(metrics: dict[str, Any]) -> None:
    for name, ok, detail in metrics["gate_checks"]:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay fixed vs vol-scaled stop losses.")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--bars-csv", default=None, help="Pivoted daily close CSV")
    parser.add_argument("--mode", choices=["report", "rows"], default="report", help="Output format")
    parser.add_argument("--nav-est", type=float, default=110_000.0, help="Estimated NAV for risk budgeting")
    args = parser.parse_args()

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        print("ALPACA_API_KEY / ALPACA_SECRET_KEY not set. Source .env first.", file=sys.stderr)
        return 2

    risk_cfg = _load_risk_cfg()
    daily_bars = _load_daily_bars(args.bars_csv) if args.bars_csv else None

    pg = PostgreSQLStore(use_pool=False)
    try:
        start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(args.end, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=timezone.utc)
        all_trades = pg.fetch_trades(status="closed", limit=10000)
        trades = [
            _clean_trade(t)
            for t in all_trades
            if t.get("exit_time") and start_dt <= t["exit_time"] <= end_dt
        ]
        trades = [t for t in trades if t is not None]
    finally:
        pg.close()

    if not trades:
        print("No closed trades in range.")
        return 0

    train, test = _walk_forward_split(trades)

    print(f"Fetched {len(trades)} trades; fetching 15-min bars for {len({t['symbol'] for t in trades})} symbols...")
    data_client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    bars_map = _fetch_intraday_bars(trades, data_client)

    print("Running counterfactual simulation...")
    df = _run_simulation(trades, bars_map, daily_bars, risk_cfg)

    if args.mode == "rows":
        df.to_csv(sys.stdout, index=False)
        return 0

    # Full-sample analysis.
    baseline = "fixed_2pct"
    candidate_keys = sorted([k for k in df["variant_key"].unique() if k != baseline])
    full_metrics: dict[str, dict] = {}
    for key in candidate_keys:
        m = _analyze_variant(df, key, baseline, args.nav_est)
        if m:
            full_metrics[key] = m

    # OOS analysis: simulate only test trades.
    test_bars_map = {sym: bars for sym, bars in bars_map.items() if any(t["symbol"] == sym for t in test)}
    df_test = _run_simulation(test, test_bars_map, daily_bars, risk_cfg) if test else pd.DataFrame()
    oos_metrics: dict[str, dict] = {}
    for key in candidate_keys:
        if not df_test.empty:
            m = _analyze_variant(df_test, key, baseline, args.nav_est)
            if m:
                oos_metrics[key] = m

    # Pick recommended variant: best OOS cum P&L among variants passing majority gates.
    recommended = None
    for key in candidate_keys:
        oos_m = oos_metrics.get(key)
        if not oos_m:
            continue
        gate_pass, _ = _gate_check(oos_m)
        if gate_pass:
            if recommended is None or oos_m["cum_pnl"] > oos_metrics[recommended]["cum_pnl"]:
                recommended = key

    # Fallback: best OOS cum P&L if no variant passes all gates.
    if recommended is None and oos_metrics:
        recommended = max(oos_metrics, key=lambda k: oos_metrics[k]["cum_pnl"])

    report: dict[str, Any] = {
        "total_trades": len(trades),
        "symbol_count": len({t["symbol"] for t in trades}),
        "intraday_coverage_pct": (
            sum(1 for t in trades if t["symbol"] in bars_map) / len(trades) * 100
        ),
        "train_count": len(train),
        "test_count": len(test),
        "nav_est": args.nav_est,
        "variants": full_metrics,
        "oos_variants": oos_metrics,
        "recommended_variant": recommended,
    }

    # Gate tables for recommended variant.
    rec_full = full_metrics.get(recommended, {})
    rec_oos = oos_metrics.get(recommended, {})
    if rec_full:
        pass_full, checks_full = _gate_check(rec_full)
        report["full_sample"] = {"gate_pass": pass_full, "gate_checks": checks_full}
    else:
        report["full_sample"] = {"gate_pass": False, "gate_checks": [("metrics", False, "No metrics available")]}

    if rec_oos:
        pass_oos, checks_oos = _gate_check(rec_oos)
        report["oos"] = {"gate_pass": pass_oos, "gate_checks": checks_oos}
    else:
        report["oos"] = {"gate_pass": False, "gate_checks": [("metrics", False, "No OOS metrics available")]}

    if recommended:
        gate_status = "PASS" if report["oos"]["gate_pass"] else "FAIL"
        rec_name = full_metrics.get(recommended, {}).get("variant", recommended)
        report["recommendation"] = (
            f"Recommended variant: {rec_name} ({recommended}) — OOS gate {gate_status}. "
            f"Cum P&L OOS ${rec_oos.get('cum_pnl', 0):.2f} vs fixed ${rec_oos.get('base_cum_pnl', 0):.2f}."
        )
        if not report["oos"]["gate_pass"]:
            report["recommendation"] += " DO NOT enable vol_scaled live until gates pass."
    else:
        report["recommendation"] = "No variant produced usable metrics. Gate FAIL."

    _print_report(report)
    return 0 if report["oos"].get("gate_pass", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
