#!/usr/bin/env python3
"""Vol-target calibration replay (Step 2 — F6 (b), read-only).

Replays the PortfolioVolTargeter over a trailing window of real market data and,
for each candidate target_vol, reports the would-be vol_scale trajectory and the
risk-band / deployment consequences. This is the "measure" half of F6 before any
live flip of trading.yaml `vol_target.target_vol`.

Read-only / idempotent. Writes nothing, flips no flag, changes no behavior. Only
reads:
  - config: active universe (strategies.yaml), max_portfolio_exposure, current
    vol_target calibration (load_vol_target_config = the live baseline)
  - Alpaca (read-only market data): daily bars for the active universe
  - Redis: regime:current (the current regime_mult, for the "current regime"
    deployment scenario)

What it measures (per candidate target_vol in {baseline, 0.12, 0.15}):
  - vol_scale(t) = clamp(target_vol / realized_vol(t), clamp_low, clamp_high)
    over the trailing window (daily granularity — EWMA vol only moves on a new
    daily bar, so 15-min cycles within a day share one vol_scale).
  - stats: mean / p50 / p10 / p90 / min / max, % days clamped at floor, % at cap.
  - implied scaled portfolio vol = realized_vol(t) * vol_scale(t): does the
    targeter track the target? (when unclamped it == target_vol).
  - theoretical max gross scenarios:
      regime=1.0 (headroom): 0.50 * 1.0 * vol_scale(t) -> % days breaching the
        0.50 hard cap, max gross.
      current regime: 0.50 * regime_mult * vol_scale(t) -> mean gross.
  - deployment delta vs the live baseline (target_vol = config value): mean
    0.50 * regime_mult * (scale_candidate - scale_baseline).

Honest scope: this is a RISK-BAND / DEPLOYMENT measure, not a clean P&L delta.
A P&L comparison would require re-simulating fills at each sizing (a backtest),
which is out of scope for a "replay". The target_vol choice is an operator
risk-tolerance decision; this replay confirms the band, the clamp frequency, and
the hard-cap headroom — it does not "prove" a value.

Run inside the worker container (creds + Redis):
    docker compose exec -T worker python - < scripts/audit_vol_target_replay.py
Or locally with creds in env:
    .venv/bin/python scripts/audit_vol_target_replay.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from src.config import config
from src.strategies.registry import StrategyRegistry
from src.portfolio.vol_targeting import load_vol_target_config

_ANNUALIZE = 252.0
_VOL_SPAN = 60          # match PortfolioVolTargeter default span
_PRICE_BARS = 300       # match portfolio_scheduler._PRICE_BARS
_WINDOW_DAYS = 60       # trailing trading days to replay
_CANDIDATES = [0.12, 0.15]  # baseline (config) is always included too


def _active_symbols() -> list[str]:
    active = StrategyRegistry().get_active_strategies()
    try:
        from src.workers.portfolio_scheduler import _strategy_symbols
        syms = {s for e in active for s in _strategy_symbols(e)}
    except Exception:
        syms = set()
    if not syms:
        syms = set(config.WATCHLIST_SYMBOLS or [])
    return sorted(syms) or ["SPY"]


def _fetch_bars(symbols: list[str], days: int = 700) -> pd.DataFrame:
    """Fetch daily bars (IEX) over `days` calendar days, pivoted wide."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment, DataFeed

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY, secret_key=config.ALPACA_SECRET_KEY
    )
    req = StockBarsRequest(
        symbol_or_symbols=symbols, timeframe=TimeFrame.Day,
        start=start, end=end, feed=DataFeed.IEX, adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(req).df
    if raw.empty:
        return pd.DataFrame()
    raw = raw.reset_index()
    return raw.pivot(index="timestamp", columns="symbol", values="close")


def _ewma_vol_series(bars: pd.DataFrame) -> pd.Series:
    """Equal-weight portfolio EWMA annualized vol series (matches the scheduler's
    {"portfolio": ...} path: pct_change().mean(axis=1), ewm(span=60).var())."""
    ret = bars.pct_change().dropna(how="all")
    port = ret.mean(axis=1).dropna()
    if len(port) < 2:
        return pd.Series(dtype=float)
    ewma_var = port.ewm(span=_VOL_SPAN).var()
    vol = np.sqrt(ewma_var * _ANNUALIZE)
    return vol.dropna()


def _scale(vols: pd.Series, target_vol: float, lo: float, hi: float) -> pd.Series:
    raw = target_vol / vols
    return raw.clip(lower=lo, upper=hi)


def _current_regime_mult() -> float | None:
    try:
        from redis import Redis
        r = Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            raw = r.get("regime:current")
            if raw:
                return float(json.loads(raw).get("multiplier", 1.0))
        finally:
            r.close()
    except Exception:
        pass
    return None


def _max_portfolio_exposure() -> float:
    import yaml, pathlib
    cfg = yaml.safe_load(pathlib.Path("config/trading.yaml").read_text())
    return float(cfg.get("risk", {}).get("max_portfolio_exposure", 0.50))


def _stats(s: pd.Series) -> dict:
    if s.empty:
        return {}
    return {
        "mean": float(s.mean()),
        "p50": float(s.median()),
        "p10": float(s.quantile(0.10)),
        "p90": float(s.quantile(0.90)),
        "min": float(s.min()),
        "max": float(s.max()),
    }


def main() -> int:
    print("=" * 78)
    print("VOL-TARGET CALIBRATION REPLAY (read-only — F6 (b))")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 78)

    vtc = load_vol_target_config()
    baseline_tv = float(vtc["target_vol"])
    lo = float(vtc["clamp_low"])
    hi = float(vtc["clamp_high"])
    max_exposure = _max_portfolio_exposure()
    candidates = sorted(set([baseline_tv] + _CANDIDATES))

    print(f"\n[config] baseline target_vol = {baseline_tv:.2f}  clamp=[{lo}, {hi}]")
    print(f"[config] max_portfolio_exposure = {max_exposure:.2f}")
    print(f"[config] candidates = {candidates}")
    print(f"[config] replay window = {_WINDOW_DAYS} trailing trading days  (EWMA span={_VOL_SPAN})")

    syms = _active_symbols()
    print(f"\n[data] active universe = {len(syms)} symbols")
    bars = _fetch_bars(syms)
    if bars.empty or len(bars) < _VOL_SPAN + _WINDOW_DAYS:
        print(f"[data] insufficient bars ({len(bars)}) for a {_WINDOW_DAYS}-day replay with span {_VOL_SPAN}")
        return 1
    print(f"[data] bars fetched = {len(bars)} trading days  ({bars.index[0].date()} -> {bars.index[-1].date()})")

    vol = _ewma_vol_series(bars)
    window = vol.iloc[-_WINDOW_DAYS:]
    print(f"[data] vol series len = {len(vol)}, replay window = {len(window)} days")
    print(f"[data] realized vol over window: mean={window.mean():.4f}  "
          f"p10={window.quantile(0.10):.4f}  p90={window.quantile(0.90):.4f}  "
          f"min={window.min():.4f}  max={window.max():.4f}")

    regime_mult = _current_regime_mult()
    regime_str = f"{regime_mult:.3f} (current)" if regime_mult is not None else "<absent> (assume 1.0)"
    if regime_mult is None:
        regime_mult = 1.0
    print(f"\n[regime] regime_mult = {regime_str}")

    # --- per-candidate table ---
    print("\n[1] VOL_SCALE TRAJECTORY  (vol_scale = clamp(target_vol / realized_vol))")
    print(f"    {'candidate':>10} | {'mean':>6} {'p50':>6} {'p10':>6} {'p90':>6} {'min':>6} {'max':>6} | {'%floor':>6} {'%cap':>6} | {'scaled_vol mean':>15}")
    rows = []
    for tv in candidates:
        sc = _scale(window, tv, lo, hi)
        pct_floor = float((sc <= lo + 1e-9).mean()) * 100
        pct_cap = float((sc >= hi - 1e-9).mean()) * 100
        scaled_vol = (window * sc)  # implied portfolio vol after scaling
        st = _stats(sc)
        print(f"    {tv:>10.2f} | {st['mean']:>6.3f} {st['p50']:>6.3f} {st['p10']:>6.3f} "
              f"{st['p90']:>6.3f} {st['min']:>6.3f} {st['max']:>6.3f} | "
              f"{pct_floor:>5.1f}% {pct_cap:>5.1f}% | {scaled_vol.mean():>15.4f}")
        rows.append({"tv": tv, "scale": sc, "scaled_vol": scaled_vol,
                     "pct_floor": pct_floor, "pct_cap": pct_cap})

    # --- gross scenarios ---
    print("\n[2] THEORETICAL MAX GROSS  (max_portfolio_exposure * regime_mult * vol_scale)")
    print(f"    {'candidate':>10} | {'gross@regime=1.0 mean':>20} {'max':>6} {'%>cap':>6} | "
          f"{'gross@current mean':>18} {'current':>7}")
    for r in rows:
        tv, sc = r["tv"], r["scale"]
        gross_full = max_exposure * 1.0 * sc
        gross_cur = max_exposure * regime_mult * sc
        pct_breach = float((gross_full > max_exposure + 1e-9).mean()) * 100
        print(f"    {tv:>10.2f} | {gross_full.mean():>20.4f} {gross_full.max():>6.3f} "
              f"{pct_breach:>5.1f}% | {gross_cur.mean():>18.4f} {gross_cur.iloc[-1]:>7.4f}")

    # --- deployment delta vs baseline ---
    base_scale = _scale(window, baseline_tv, lo, hi)
    print(f"\n[3] DEPLOYMENT DELTA vs baseline (target_vol={baseline_tv:.2f}, regime_mult={regime_mult:.2f})")
    print(f"    {'candidate':>10} | {'mean delta (pp)':>16} {'mean gross base':>16} {'mean gross cand':>16}")
    for r in rows:
        if abs(r["tv"] - baseline_tv) < 1e-9:
            continue
        delta = max_exposure * regime_mult * (r["scale"] - base_scale)
        gross_base = max_exposure * regime_mult * base_scale
        gross_cand = max_exposure * regime_mult * r["scale"]
        print(f"    {r['tv']:>10.2f} | {delta.mean()*100:>15.2f}pp {gross_base.mean()*100:>15.2f}% "
              f"{gross_cand.mean()*100:>15.2f}%")

    # --- interpretation ---
    print("\n[4] INTERPRETATION")
    for r in rows:
        tv = r["tv"]
        sc = r["scale"]
        gross_full = max_exposure * 1.0 * sc
        pct_breach = float((gross_full > max_exposure + 1e-9).mean()) * 100
        tag = " (baseline / live)" if abs(tv - baseline_tv) < 1e-9 else ""
        print(f"  target_vol={tv:.2f}{tag}:")
        print(f"    vol_scale mean={sc.mean():.3f}, clamp at floor {r['pct_floor']:.1f}% / at cap {r['pct_cap']:.1f}%; "
              f"implied scaled-vol mean={(window*sc).mean():.4f} (target {tv:.2f})")
        print(f"    gross@regime=1.0 mean={gross_full.mean():.3f}, max={gross_full.max():.3f}, "
              f"breach 0.50 cap {pct_breach:.1f}% of days")
        if abs(tv - baseline_tv) < 1e-9:
            print(f"    -> this is the live setting; the others are measured against it.")
        else:
            delta = max_exposure * regime_mult * (sc - base_scale)
            verdict = []
            if r["pct_floor"] > 5:
                verdict.append(f"floor binds {r['pct_floor']:.0f}% of days (target above realized vol often)")
            if pct_breach > 0:
                verdict.append(f"HARD CAP breached {pct_breach:.0f}% of days at regime=1.0 (headroom risk)")
            if not verdict:
                verdict.append("no clamp/cap issues in window")
            print(f"    -> deployment +{delta.mean()*100:.2f}pp vs baseline at current regime; "
                  f"{'; '.join(verdict)}")

    print("\n" + "=" * 78)
    print("Replay complete. Read-only: no Redis writes, no orders, target_vol unchanged.")
    print("Flip is an operator decision after reviewing clamp frequency + cap headroom.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())