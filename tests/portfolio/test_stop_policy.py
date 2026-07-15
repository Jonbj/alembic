"""Test surface for StopPolicy (protective + disaster stop)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.portfolio.stop_policy import FrozenStop, StopPolicy


def _risk_cfg(stop_loss_mode: str = "fixed") -> dict:
    return {
        "stop_loss": 0.02,
        "stop_loss_mode": stop_loss_mode,
        "stop_strategy_params": {
            "S1": {"k": 3.5, "floor": 0.06, "cap": 0.12},
            "S4": {"k": 2.0, "floor": 0.03, "cap": 0.08},
            "default": {"k": 3.0, "floor": 0.04, "cap": 0.12},
        },
        "stop_sigma_lookback_fast": 20,
        "stop_sigma_lookback_slow": 63,
        "stop_sigma_ewma_floor_ratio": 0.8,
        "broker_disaster_stop": {
            "multiplier": 1.5,
            "sigma_multiple": 5.0,
            "floor_pct": 0.12,
            "cap_pct": 0.20,
        },
    }


def _bars(symbol: str, sigma_daily: float, n: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    returns = np.random.normal(loc=0.0, scale=sigma_daily, size=n)
    prices = 100.0 * np.exp(np.cumsum(returns))
    idx = pd.date_range(end="2026-07-10", periods=n, freq="D")
    return pd.DataFrame({symbol: prices}, index=idx)


def test_fixed_mode_reproduces_legacy_two_percent_and_freezes_audit_fields():
    cfg = _risk_cfg("fixed")
    policy = StopPolicy(cfg, bars_df=None)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("AAPL", "S1", 100.0, ts)
    assert frozen.mode == "fixed"
    assert frozen.d_init == pytest.approx(0.02)
    # Fixed mode must still freeze k/floor/cap/sigma for future vol_scaled sizing.
    assert frozen.k == pytest.approx(3.5)
    assert frozen.floor == pytest.approx(0.06)
    assert frozen.cap == pytest.approx(0.12)
    assert frozen.vol_at_entry is not None

    dec = policy.compute("AAPL", 100.0, 97.0, frozen, ts)
    assert dec.trigger_price == pytest.approx(98.0)
    assert dec.breached is True

    dec2 = policy.compute("AAPL", 100.0, 99.0, frozen, ts)
    assert dec2.breached is False


def test_vol_scaled_high_vol_hits_cap():
    # ~5% daily vol -> k=3.5 * 0.05 = 0.175, capped at 12%
    cfg = _risk_cfg("vol_scaled")
    bars = _bars("PANW", sigma_daily=0.05)
    policy = StopPolicy(cfg, bars_df=bars)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("PANW", "S1", 100.0, ts)
    assert frozen.mode == "vol_scaled"
    assert frozen.d_init == pytest.approx(0.12, abs=0.015)
    assert frozen.vol_source == "bars_df"


def test_vol_scaled_low_vol_hits_floor():
    # ~0.5% daily vol -> k=3.5 * 0.005 = 0.0175, floored at 6%
    cfg = _risk_cfg("vol_scaled")
    bars = _bars("BOND", sigma_daily=0.005)
    policy = StopPolicy(cfg, bars_df=bars)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("BOND", "S1", 100.0, ts)
    assert frozen.d_init == pytest.approx(0.06, abs=0.01)


def test_never_widens_despite_rising_current_vol():
    cfg = _risk_cfg("vol_scaled")
    bars = _bars("TICK", sigma_daily=0.02)
    policy = StopPolicy(cfg, bars_df=bars)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("TICK", "S1", 100.0, ts)
    trigger_1 = frozen.d_init

    # Simulate "current vol doubled" by passing a different policy with higher vol,
    # but use the same frozen stop from the original policy.
    bars_high = _bars("TICK", sigma_daily=0.04)
    policy_high = StopPolicy(cfg, bars_df=bars_high)
    dec = policy_high.compute("TICK", 100.0, 100.0 * (1 - trigger_1), frozen, ts)
    assert dec.trigger_price == pytest.approx(100.0 * (1 - trigger_1))
    assert dec.breached is True


def test_d_hard_wider_than_d_init_and_clipped():
    cfg = _risk_cfg("vol_scaled")
    policy = StopPolicy(cfg, bars_df=None)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("AAPL", "S4", 100.0, ts)
    d_hard = policy.d_hard("AAPL", frozen, sigma_eff_current=0.02)
    assert d_hard >= frozen.d_init
    assert 0.12 <= d_hard <= 0.20


def test_tier_fallback_for_unknown_symbol():
    cfg = _risk_cfg("vol_scaled")
    policy = StopPolicy(cfg, bars_df=pd.DataFrame())
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    # SPY is tier_a -> stop_loss_pct 0.020 -> sigma = 0.020 / k_default(3.0)
    frozen = policy.freeze("SPY", "S4", 100.0, ts)
    assert frozen.vol_source == "tier"
    assert frozen.d_init == pytest.approx(0.03, abs=0.005)  # k=2.0 * 0.0067 ~ 0.013, floored to 0.03


def test_last_good_fallback_used_when_bars_missing():
    cfg = _risk_cfg("vol_scaled")
    def lookup(sym: str) -> float | None:
        return 0.035 if sym == "GONE" else None
    policy = StopPolicy(cfg, bars_df=None, last_good_lookup=lookup)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("GONE", "S4", 100.0, ts)
    assert frozen.vol_source == "last_good"
    assert frozen.d_init == pytest.approx(0.07, abs=0.001)  # k=2.0 * 0.035


def test_asset_median_fallback_used_when_bars_and_last_good_missing():
    cfg = _risk_cfg("vol_scaled")
    peer = pd.concat([_bars("A", 0.04), _bars("B", 0.06)], axis=1)
    policy = StopPolicy(cfg, bars_df=peer)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("MISSING", "S4", 100.0, ts)
    assert frozen.vol_source == "asset_median"
    # median sigma between 0.04 and 0.06 is ~0.05 -> d_init ~0.10, capped at 0.08
    assert frozen.d_init == pytest.approx(0.08, abs=0.01)


def test_bars_df_requires_at_least_21_bars():
    cfg = _risk_cfg("vol_scaled")
    bars = _bars("X", sigma_daily=0.05, n=15)
    policy = StopPolicy(cfg, bars_df=bars)
    ts = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    frozen = policy.freeze("X", "S4", 100.0, ts)
    assert frozen.vol_source != "bars_df"
