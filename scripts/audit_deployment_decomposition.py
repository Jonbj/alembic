#!/usr/bin/env python3
"""Deployment decomposition snapshot (Step 1 — F6 + 26%->35% residual).

Read-only / idempotent. Snapshots the CURRENT binding state of the portfolio
deployment levers and attributes the gap between the theoretical max gross
exposure (full conviction) and the observed gross exposure to each lever.

This is the "measure" half of measure-before-enforce (QX-01). It writes
nothing, flips no flag, changes no behavior. It only reads:
  - Redis: regime:current, feedback:entry_threshold:S*, feedback:regime_scale:S*,
    feedback:state:S*
  - config: active strategy sleeve caps (strategies.yaml), max_portfolio_exposure,
    target_vol, threshold_baseline, apply_regime_scale
  - Alpaca (read-only market data + positions): daily bars for the active
    universe (to compute realized vol exactly as the scheduler does) and the
    current account/positions (to read observed gross exposure)

Decomposition model (multiplicative, top-down from NAV):
    ceiling       = min(max_portfolio_exposure, sum(active allocation_pct))
    after_regime  = ceiling * regime_mult            (Redis regime:current)
    after_vol     = after_regime * vol_scale          (0.10 / realized_vol, clamp [0.5,2.0])
    after_f8      = after_vol * f8_portfolio_scale    (1.0 while apply_regime_scale=false)
    theoretical_max_gross = after_f8                  (full-conviction max gross/NAV)
    observed_gross       = sum(|position mv|) / NAV   (from Alpaca positions)

Per-lever cut:
    regime_cut   = ceiling       - after_regime
    vol_cut      = after_regime  - after_vol
    f8_cut       = after_vol     - after_f8          (0 while shadow-only)
    residual     = after_f8      - observed_gross    (signal sparsity / ratchet / low conviction)

Interpretation:
  - If theoretical_max_gross ~= observed_gross: the levers fully explain current
    deployment; the residual is ~0 and the gap to 35%/50% is a LEVER to move
    (most likely vol_scale -> F6: raise target_vol or widen the clamp), not a
    signal problem.
  - If theoretical_max_gross >> observed_gross: residual is the binding factor
    -> signal sparsity / ratchet entry-threshold filtering / low conviction.
    F6 (vol-targeter) is NOT the limiter; look at the ratchet threshold vs
    baseline and at strategy signal rates.
  - The ratchet (feedback:entry_threshold) blocks new entries below a conviction
    threshold; it is a FILTER, not a multiplier, so it shows up inside the
    residual. Its current value vs baseline is reported separately.

Run inside the worker container:
    docker compose exec worker python scripts/audit_deployment_decomposition.py
Or locally against the live stack (REDIS_URL + Alpaca creds from env):
    .venv/bin/python scripts/audit_deployment_decomposition.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone

# Project imports (lazy where they touch live clients).
from src.config import config
from src.strategies.registry import StrategyRegistry


_PRICE_BARS = 300  # match portfolio_scheduler._PRICE_BARS
_VOL_SPAN = 60     # match PortfolioVolTargeter default span
_ANNUALIZE = 252.0

# Read the vol-targeter calibration from the live config (F6: config-driven).
# Falls back to status quo if the config / loader is unavailable.
try:
    from src.portfolio.vol_targeting import load_vol_target_config as _load_vtc
    _vtc = _load_vtc()
    _TARGET_VOL = float(_vtc.get("target_vol", 0.10))
    _VOL_CLAMP_LOW = float(_vtc.get("clamp_low", 0.5))
    _VOL_CLAMP_HIGH = float(_vtc.get("clamp_high", 2.0))
except Exception:
    _TARGET_VOL = 0.10
    _VOL_CLAMP_LOW = 0.5
    _VOL_CLAMP_HIGH = 2.0


def _read_redis_feedback(strategy_ids: list[str]) -> dict:
    """Read regime:current + per-strategy feedback keys from Redis (fail-open)."""
    from redis import Redis

    out: dict = {"regime_mult": None, "regime_raw": None, "per_strategy": {}, "errors": []}
    try:
        r = Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            # regime:current
            raw = r.get("regime:current")
            out["regime_raw"] = raw
            if raw:
                try:
                    j = json.loads(raw)
                    out["regime_mult"] = float(j.get("multiplier", 1.0))
                    out["regime_name"] = j.get("regime")
                except Exception as exc:
                    out["errors"].append(f"regime:current parse: {exc}")
            # per-strategy feedback keys
            for sid in strategy_ids:
                thr = r.get(f"feedback:entry_threshold:{sid}")
                sca = r.get(f"feedback:regime_scale:{sid}")
                st = r.get(f"feedback:state:{sid}")
                state = None
                if st:
                    try:
                        state = json.loads(st)
                    except Exception:
                        state = {"raw": st}
                out["per_strategy"][sid] = {
                    "entry_threshold": float(thr) if thr is not None else None,
                    "regime_scale": float(sca) if sca is not None else None,
                    "state": state,
                }
            # legacy (non-per-strategy) fallbacks, for context
            out["legacy_entry_threshold"] = (
                float(r.get("feedback:entry_threshold")) if r.get("feedback:entry_threshold") else None
            )
            out["legacy_regime_scale"] = (
                float(r.get("feedback:regime_scale")) if r.get("feedback:regime_scale") else None
            )
        finally:
            r.close()
    except Exception as exc:
        out["errors"].append(f"redis unreachable: {exc}")
    return out


def _load_loss_feedback_cfg() -> dict:
    try:
        from src.workers.performance import _load_loss_feedback_config
        return _load_loss_feedback_config()
    except Exception as exc:
        return {"_load_error": str(exc)}


def _active_strategies() -> list:
    return StrategyRegistry().get_active_strategies()


def _strategy_symbols(entry) -> list[str]:
    """Reuse the scheduler's symbol resolver for a strategy entry."""
    try:
        from src.workers.portfolio_scheduler import _strategy_symbols as _ss
        return list(_ss(entry))
    except Exception:
        return []


def _fetch_bars(symbols: list[str]):
    """Fetch daily bars exactly as the scheduler does (IEX, _PRICE_BARS*2d)."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment, DataFeed

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_PRICE_BARS * 2)
    client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY, secret_key=config.ALPACA_SECRET_KEY
    )
    req = StockBarsRequest(
        symbol_or_symbols=symbols or config.WATCHLIST_SYMBOLS or ["SPY"],
        timeframe=TimeFrame.Day, start=start, end=end,
        feed=DataFeed.IEX, adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(req).df
    if raw.empty:
        return None
    raw = raw.reset_index()
    return raw.pivot(index="timestamp", columns="symbol", values="close")


def _realized_vol(bars_df) -> tuple[float | None, int]:
    """Replicate PortfolioVolTargeter.estimate_vol on the equal-weight portfolio
    of all symbols in bars_df (the scheduler's {"portfolio": ...} path).

    Returns (annualized_ewma_vol, n_bars_used).
    """
    import pandas as pd
    if bars_df is None or bars_df.empty or len(bars_df) < 3:
        return None, 0
    ret = bars_df.pct_change().dropna(how="all")
    port = ret.mean(axis=1).dropna()
    if len(port) < 2:
        return None, 0
    ewma_var = pd.Series(port.tolist()).ewm(span=_VOL_SPAN).var().iloc[-1]
    if not math.isfinite(ewma_var) or ewma_var <= 0.0:
        return None, len(port)
    return math.sqrt(ewma_var * _ANNUALIZE), len(port)


def _vol_scale(realized_vol: float | None, target_vol: float) -> float:
    if realized_vol is None or realized_vol <= 0.0:
        return 1.0
    raw = target_vol / realized_vol
    return max(_VOL_CLAMP_LOW, min(_VOL_CLAMP_HIGH, raw))


def _read_positions_and_nav():
    """Read observed gross exposure from Alpaca (read-only)."""
    from alpaca.trading.client import TradingClient

    tc = TradingClient(api_key=config.ALPACA_API_KEY, secret_key=config.ALPACA_SECRET_KEY)
    account = tc.get_account()
    nav = float(getattr(account, "portfolio_value", 0) or 0) or float(getattr(account, "equity", 0) or 0)
    positions = tc.get_all_positions()
    rows = []
    gross = 0.0
    for p in positions:
        try:
            mv = abs(float(getattr(p, "market_value", 0) or 0))
        except Exception:
            mv = 0.0
        gross += mv
        rows.append({
            "symbol": getattr(p, "symbol", "?"),
            "qty": float(getattr(p, "qty", 0) or 0),
            "market_value": float(getattr(p, "market_value", 0) or 0),
        })
    return nav, gross, rows


def _max_portfolio_exposure() -> float:
    """Read risk.max_portfolio_exposure from trading.yaml."""
    import yaml, pathlib
    cfg = yaml.safe_load(pathlib.Path("config/trading.yaml").read_text())
    return float(cfg.get("risk", {}).get("max_portfolio_exposure", 0.50))


def main() -> int:
    print("=" * 78)
    print("DEPLOYMENT DECOMPOSITION SNAPSHOT (read-only)")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print(f"REDIS_URL: {config.REDIS_URL}")
    print("=" * 78)

    # --- active strategies + sleeve caps ---
    active = _active_strategies()
    strategy_ids = [e.strategy_id for e in active]
    sleeve_caps = {e.strategy_id: float(e.allocation_pct) for e in active}
    sum_caps = sum(sleeve_caps.values())
    print("\n[1] ACTIVE STRATEGIES + SLEEVE CAPS")
    for sid, cap in sleeve_caps.items():
        print(f"    {sid}: allocation_pct = {cap:.2f}")
    print(f"    -> sum(active allocation_pct) = {sum_caps:.2f}")

    # --- risk config ---
    max_exposure = _max_portfolio_exposure()
    fb_cfg = _load_loss_feedback_cfg()
    # F6: target_vol + clamp are now config-driven (trading.yaml vol_target),
    # read at import time into _TARGET_VOL / _VOL_CLAMP_* above.
    target_vol = _TARGET_VOL
    threshold_baseline = float(fb_cfg.get("threshold_baseline", 0.30))
    apply_regime_scale = bool(fb_cfg.get("apply_regime_scale", False))
    print("\n[2] RISK / FEEDBACK CONFIG")
    print(f"    max_portfolio_exposure (hard cap) = {max_exposure:.2f}")
    print(f"    vol-targeter target_vol           = {target_vol:.2f}  (from trading.yaml vol_target)")
    print(f"    vol-targeter clamp                = [{_VOL_CLAMP_LOW}, {_VOL_CLAMP_HIGH}]")
    print(f"    ratchet threshold_baseline        = {threshold_baseline:.2f}")
    print(f"    apply_regime_scale (F8)           = {apply_regime_scale}  (False=SHADOW ONLY)")

    ceiling = min(max_exposure, sum_caps)
    print(f"    -> ceiling = min(max_exposure, sum_caps) = {ceiling:.2f}")

    # --- Redis: regime + feedback ---
    fb = _read_redis_feedback(strategy_ids)
    regime_mult = fb["regime_mult"]
    print("\n[3] REDIS — regime:current + feedback:*")
    if regime_mult is not None:
        print(f"    regime_mult = {regime_mult:.3f}  (regime={fb.get('regime_name')})")
    else:
        print(f"    regime_mult = <absent>  (scheduler fallback = 0.2 fail-conservative)")
        regime_mult = 0.2  # mirror scheduler fallback for the decomposition
    for sid in strategy_ids:
        ps = fb["per_strategy"].get(sid, {})
        thr = ps.get("entry_threshold")
        sca = ps.get("regime_scale")
        state = ps.get("state") or {}
        thr_flag = ""
        if thr is not None and thr > threshold_baseline + 1e-9:
            thr_flag = f"  <-- RAISED vs baseline {threshold_baseline:.2f} (ratchet blocking low-conviction S4 entries)"
        sca_flag = ""
        if sca is not None and abs(sca - 1.0) > 1e-9:
            sca_flag = f"  <-- {'suppressed' if sca < 1.0 else 'elevated'} (F8 shadow, apply={apply_regime_scale})"
        print(f"    {sid}: entry_threshold={thr}  regime_scale={sca}{thr_flag}{sca_flag}")
        if state:
            print(f"         state: reason={state.get('reason')} last_adjustment_ts={state.get('last_adjustment_ts')}")
    if fb["errors"]:
        for e in fb["errors"]:
            print(f"    [warn] {e}")

    # --- realized vol (Alpaca bars, same as scheduler) ---
    print("\n[4] REALIZED VOL + VOL-TARGETER SCALE (F6 lever)")
    symbols = list({sym for e in active for sym in _strategy_symbols(e)})
    if not symbols:
        symbols = list(config.WATCHLIST_SYMBOLS or [])
    bars_df = None
    bars_err = None
    try:
        bars_df = _fetch_bars(symbols)
    except Exception as exc:
        bars_err = str(exc)
    if bars_err:
        print(f"    [warn] bars fetch failed: {bars_err}")
    rvol, n = _realized_vol(bars_df)
    vol_scale = _vol_scale(rvol, target_vol)
    if rvol is not None:
        raw_scale = target_vol / rvol
        clamped = abs(raw_scale - vol_scale) > 1e-9
        print(f"    universe symbols      = {len(symbols)}")
        print(f"    bars used (n)         = {n}")
        print(f"    realized vol (ann.)   = {rvol:.4f}  ({rvol*100:.1f}%)")
        print(f"    raw scale = {target_vol}/{rvol:.4f} = {raw_scale:.3f}")
        print(f"    vol_scale (clamped)   = {vol_scale:.3f}  {'<-- CLAMPED at floor 0.5' if (clamped and raw_scale < vol_scale) else ('<-- CLAMPED at cap 2.0' if clamped else '')}")
    else:
        print(f"    realized vol = <unavailable>  -> vol_scale = {vol_scale:.3f} (neutral)")

    # --- observed gross exposure (Alpaca positions) ---
    print("\n[5] OBSERVED GROSS EXPOSURE (Alpaca positions)")
    nav = gross = None
    positions_rows = []
    pos_err = None
    try:
        nav, gross, positions_rows = _read_positions_and_nav()
    except Exception as exc:
        pos_err = str(exc)
    if pos_err:
        print(f"    [warn] positions read failed: {pos_err}")
        observed_gross = None
    else:
        observed_gross = (gross / nav) if nav else None
        print(f"    NAV            = ${nav:,.2f}")
        print(f"    gross (abs mv) = ${gross:,.2f}")
        print(f"    observed gross / NAV = {observed_gross:.2%}" if observed_gross is not None else "    observed gross = <nav=0>")
        print(f"    held positions = {len(positions_rows)}")

    # --- decomposition ---
    print("\n[6] DECOMPOSITION (multiplicative, top-down from NAV)")
    after_regime = ceiling * regime_mult
    after_vol = after_regime * vol_scale
    # F8 is per-strategy, not a portfolio-wide multiplier; while apply=false it
    # contributes 0 to sizing. Report the would-be portfolio scale for context.
    f8_scales = {
        sid: fb["per_strategy"].get(sid, {}).get("regime_scale")
        for sid in strategy_ids
    }
    f8_active_scales = {sid: s for sid, s in f8_scales.items() if s is not None and abs(s - 1.0) > 1e-9}
    f8_portfolio_scale = 1.0  # sizing effect is 0 while apply=false
    after_f8 = after_vol * f8_portfolio_scale
    theoretical_max = after_f8

    regime_cut = ceiling - after_regime
    vol_cut = after_regime - after_vol
    f8_cut = after_vol - after_f8  # 0 while shadow

    print(f"    ceiling              = {ceiling:.4f}   (= min(max_exposure, sum_caps))")
    print(f"    after regime  ×{regime_mult:.3f} = {after_regime:.4f}   regime_cut = {regime_cut:+.4f}")
    print(f"    after vol     ×{vol_scale:.3f} = {after_vol:.4f}   vol_cut    = {vol_cut:+.4f}")
    print(f"    after F8      ×{f8_portfolio_scale:.3f} = {after_f8:.4f}   f8_cut     = {f8_cut:+.4f}  (shadow, apply={apply_regime_scale})")
    print(f"    -> theoretical_max_gross (full conviction) = {theoretical_max:.4f}  ({theoretical_max*100:.1f}%)")

    if observed_gross is not None:
        residual = theoretical_max - observed_gross
        print(f"    observed_gross                               = {observed_gross:.4f}  ({observed_gross*100:.1f}%)")
        print(f"    residual (conviction/ratchet/signal sparsity)= {residual:+.4f}  ({residual*100:+.1f}pp)")
        print()
        print(f"    gap to 35% target  = {0.35 - observed_gross:+.4f}  ({(0.35-observed_gross)*100:+.1f}pp)")
        print(f"    gap to 50% hard cap = {max_exposure - observed_gross:+.4f}  ({(max_exposure-observed_gross)*100:+.1f}pp)")
    else:
        print(f"    observed_gross = <unavailable> (positions read failed)")
        print(f"    residual = <cannot compute without observed gross>")

    if f8_active_scales:
        print(f"\n    F8 shadow scales (per-strategy, NOT applied to sizing): {f8_active_scales}")
    else:
        print(f"\n    F8: no per-strategy regime_scale currently set (all at 1.0 / absent).")

    # --- interpretation ---
    print("\n[7] INTERPRETATION")
    if observed_gross is not None and theoretical_max > 0:
        if abs(residual) < 0.03:
            print(f"    theoretical_max ~= observed_gross ({theoretical_max*100:.1f}% vs {observed_gross*100:.1f}%).")
            print(f"    Levers FULLY EXPLAIN current deployment. The gap to 35% is a LEVER to move,")
            print(f"    not a signal problem. Dominant lever: {'vol-targeter (F6: target_vol=' + format(target_vol,'.2f') + ' / clamp floor 0.5)' if vol_cut < regime_cut - 1e-6 else 'regime_mult'}.")
            if vol_cut < -1e-6:
                print(f"    vol_cut = {vol_cut*100:+.1f}pp -> raising target_vol (e.g. 0.15) or lowering the clamp")
                print(f"    floor (0.5 -> 0.3) would directly raise deployment. Measure before enforce.")
        elif residual > 0.03:
            print(f"    theoretical_max ({theoretical_max*100:.1f}%) >> observed_gross ({observed_gross*100:.1f}%).")
            print(f"    residual = {residual*100:+.1f}pp is the binding factor -> signal sparsity / ratchet / low conviction.")
            print(f"    F6 (vol-targeter, vol_cut={vol_cut*100:+.1f}pp) is NOT the dominant limiter.")
            # ratchet flag
            raised = [sid for sid in strategy_ids
                      if (fb["per_strategy"].get(sid, {}).get("entry_threshold") or 0) > threshold_baseline + 1e-9]
            if raised:
                print(f"    Ratchet raised on {raised} (entry_threshold > baseline {threshold_baseline}) ->")
                print(f"    blocks low-conviction entries; contributes to residual. Check feedback:state reasons.")
            else:
                print(f"    Ratchet at baseline on all strategies -> residual is genuine signal sparsity / low conviction.")
            print(f"    Chasing 35% via sizing levers won't help; this is an alpha/signal-rate problem.")
        else:
            print(f"    observed_gross ({observed_gross*100:.1f}%) > theoretical_max ({theoretical_max*100:.1f}%) — unexpected;")
            print(f"    check for stale positions or a regime_mult/vol mismatch. Decomposition may be conservative.")
    else:
        print("    observed gross unavailable — fix positions read to complete interpretation.")

    print("\n" + "=" * 78)
    print("Snapshot complete. Read-only: no Redis writes, no orders, no flag changes.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())