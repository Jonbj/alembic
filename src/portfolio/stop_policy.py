"""Protective + disaster stop policy for the portfolio path (F9a redesign).

Deep module: all stop logic behind a small interface. The protective stop is
ALWAYS synthetic per-cycle and uniform across fractionable/whole-share (invariant
#2). The broker disaster stop (d_hard) is separate and wider.

Invariants enforced here (spec §7):
  - stop never widens (long: trigger monotonic non-increasing) — guaranteed because
    the protective trigger uses the FROZEN d_init, never recomputed from current vol.
  - freeze-at-entry: sigma_eff / k / floor / cap / d_init computed once at entry.
  - mode=fixed reproduces the legacy 2% (parity) so existing tests hold.

DO NOT call any LLM / remote API from here — this runs in the 15-min hot path.
"""
from __future__ import annotations

import os
import typing
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import yaml


@dataclass(frozen=True)
class FrozenStop:
    """Stop params frozen at entry; persisted on the trade row (migration 034)."""

    strategy: str | None  # "S1" | "S4" | "S7" | None
    mode: str  # "fixed" | "vol_scaled"
    vol_at_entry: float | None  # sigma_eff at entry (None in fixed mode)
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    d_init: float  # clipped protective distance (legacy 0.02 in fixed mode)
    vol_source: str | None  # bars_df | last_good | asset_median | tier | default


@dataclass(frozen=True)
class StopDecision:
    """Result of one per-cycle protective check on one held position."""

    symbol: str
    strategy: str | None
    mode: str
    entry_price: float
    observed_price: float
    trigger_price: float  # entry_price * (1 - d_init) for a long
    d_init: float
    vol_at_entry: float | None
    sigma_eff: float | None
    k: float | None
    floor: float | None
    cap: float | None
    price_source: str  # market.prices | bid | ...
    vol_source: str | None
    breached: bool
    cycle_ts: datetime


class StopPolicy:
    """One policy, two modes. The protective stop is synthetic per-cycle.

    Interface (the test surface — tests/portfolio/test_stop_policy.py):
      freeze(symbol, strategy, entry_price, cycle_ts) -> FrozenStop
      compute(symbol, entry_price, observed_price, frozen, cycle_ts, price_source) -> StopDecision
      d_hard(symbol, frozen, sigma_eff_current) -> float
    """

    def __init__(
        self,
        risk_cfg: dict,
        bars_df: pd.DataFrame | None = None,
        last_good_lookup: typing.Callable[[str], float | None] | None = None,
    ) -> None:
        self._cfg = risk_cfg
        self._bars = bars_df  # pivoted close: index=timestamp, columns=symbol
        self._sigma_cache: dict[str, tuple[float | None, str]] = {}
        self._last_good_lookup = last_good_lookup
        self._tier_lookup = self._load_tier_lookup()
        self._asset_median: float | None = None
        self._precompute_sigma()

    # --- tier fallback (level 4 of the hierarchy) ---
    def _load_tier_lookup(self) -> dict[str, float]:
        """Build symbol -> stop_loss_pct map from config/cost_model.yaml."""
        path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "cost_model.yaml")
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            return {}
        equity = cfg.get("equity", {})
        tiers = equity.get("spread_tiers", {})
        lookup: dict[str, float] = {}
        default_pct: float | None = None
        for _name, tier in tiers.items():
            pct = tier.get("stop_loss_pct")
            if tier.get("default") and pct is not None:
                default_pct = float(pct)
            for sym in tier.get("symbols", []):
                if pct is not None:
                    lookup[sym.upper()] = float(pct)
        if default_pct is not None:
            lookup["__default__"] = default_pct
        return lookup

    def _tier_sigma(self, symbol: str) -> tuple[float | None, str]:
        """Convert a tier stop_loss_pct into an implied sigma_eff = pct / k_default."""
        pct = self._tier_lookup.get(symbol.upper()) or self._tier_lookup.get("__default__")
        if pct is None:
            return None, "default"
        k_default = float(
            (self._cfg.get("stop_strategy_params", {}) or {})
            .get("default", {})
            .get("k", 3.0)
        )
        return pct / k_default, "tier"

    # --- strategy params lookup ---
    def _params(self, strategy: str | None) -> tuple[float, float, float]:
        """Return (k, floor, cap) for the strategy, falling back to 'default'."""
        params = self._cfg.get("stop_strategy_params", {}) or {}
        p = params.get(strategy) or params.get("default") or {"k": 3.0, "floor": 0.04, "cap": 0.12}
        return float(p["k"]), float(p["floor"]), float(p["cap"])

    # --- sigma_eff with fallback hierarchy (spec §6.3) ---
    def _precompute_sigma(self) -> None:
        """Compute per-symbol sigma_eff from bars_df daily returns.

        Spec §6.3: use bars_df only if >= 21 bars are available. Insufficient or
        invalid histories are NOT cached as "bars_df" so the fallback hierarchy
        (last_good -> asset_median -> tier -> default) can apply.
        """
        if self._bars is None or self._bars.empty:
            return
        fast = int(self._cfg.get("stop_sigma_lookback_fast", 20))
        slow = int(self._cfg.get("stop_sigma_lookback_slow", 63))
        floor_ratio = float(self._cfg.get("stop_sigma_ewma_floor_ratio", 0.8))
        min_obs = 21
        returns = self._bars.pct_change().dropna(how="all")
        for sym in self._bars.columns:
            s = returns[sym].dropna()
            if len(s) < min_obs:
                continue
            ewma20 = s.ewm(span=fast, adjust=False).std().iloc[-1]
            std63 = s.rolling(slow, min_periods=slow).std().iloc[-1]
            if pd.isna(ewma20) or pd.isna(std63):
                continue
            sigma = max(float(ewma20), floor_ratio * float(std63))
            self._sigma_cache[sym] = (sigma, "bars_df")
        # asset_median is computed from valid bars_df entries only.
        valid_sigmas = [v[0] for v in self._sigma_cache.values() if v[0] is not None]
        if valid_sigmas:
            self._asset_median = float(pd.Series(valid_sigmas).median())

    def _sigma_eff(self, symbol: str) -> tuple[float | None, str]:
        """Return (sigma_eff, vol_source).

        Fallback hierarchy (spec §6.3):
          1. bars_df for this symbol (if >=21 daily returns)
          2. last_good lookup (redis/cache of this symbol's last frozen sigma)
          3. asset_median across the current bars_df peer set
          4. tier stop_loss_pct / k_default
          5. None -> caller uses default-strategy floor/cap
        """
        # 1. bars_df
        if symbol in self._sigma_cache:
            return self._sigma_cache[symbol]
        # 2. last_good cache
        if self._last_good_lookup is not None:
            sigma = self._last_good_lookup(symbol)
            if sigma is not None and sigma > 0:
                return float(sigma), "last_good"
        # 3. asset_median
        if self._asset_median is not None:
            return self._asset_median, "asset_median"
        # 4. tier table
        sigma, source = self._tier_sigma(symbol)
        if sigma is not None:
            return sigma, source
        # 5. default (caller will use default-strategy params)
        return None, "default"

    def freeze(
        self,
        symbol: str,
        strategy: str | None,
        entry_price: float,
        cycle_ts: datetime,
    ) -> FrozenStop:
        """Compute + freeze stop params at entry. Persist the result on the trade row.

        mode=fixed  -> d_init = risk_cfg['stop_loss'] (0.02), vol fields None.
        mode=vol_scaled -> sigma_eff via _sigma_eff; d_init = clip(k*sigma_eff, floor, cap).
        """
        mode = self._cfg.get("stop_loss_mode", "fixed")
        if mode == "fixed":
            return FrozenStop(
                strategy=strategy,
                mode="fixed",
                vol_at_entry=None,
                sigma_eff=None,
                k=None,
                floor=None,
                cap=None,
                d_init=float(self._cfg.get("stop_loss", 0.02)),
                vol_source=None,
            )
        k, floor, cap = self._params(strategy)
        sigma_eff, vol_source = self._sigma_eff(symbol)
        d_init = min(max(k * (sigma_eff or 0.0), floor), cap)
        return FrozenStop(
            strategy=strategy,
            mode="vol_scaled",
            vol_at_entry=sigma_eff,
            sigma_eff=sigma_eff,
            k=k,
            floor=floor,
            cap=cap,
            d_init=d_init,
            vol_source=vol_source,
        )

    def compute(
        self,
        symbol: str,
        entry_price: float,
        observed_price: float,
        frozen: FrozenStop,
        cycle_ts: datetime,
        price_source: str = "market.prices",
    ) -> StopDecision:
        """Per-cycle protective check. Uses ONLY frozen.d_init -> never widens."""
        trigger = entry_price * (1.0 - frozen.d_init)
        return StopDecision(
            symbol=symbol,
            strategy=frozen.strategy,
            mode=frozen.mode,
            entry_price=entry_price,
            observed_price=observed_price,
            trigger_price=trigger,
            d_init=frozen.d_init,
            vol_at_entry=frozen.vol_at_entry,
            sigma_eff=frozen.sigma_eff,
            k=frozen.k,
            floor=frozen.floor,
            cap=frozen.cap,
            price_source=price_source,
            vol_source=frozen.vol_source,
            breached=observed_price <= trigger,
            cycle_ts=cycle_ts,
        )

    def d_hard(
        self,
        symbol: str,
        frozen: FrozenStop,
        sigma_eff_current: float | None,
    ) -> float:
        """Broker disaster stop distance. Wider than d_init. clip([floor_pct, cap_pct])."""
        cfg = self._cfg.get("broker_disaster_stop", {}) or {}
        mult = float(cfg.get("multiplier", 1.5))
        sig_mult = float(cfg.get("sigma_multiple", 5.0))
        floor = float(cfg.get("floor_pct", 0.12))
        cap = float(cfg.get("cap_pct", 0.20))
        base = max(mult * frozen.d_init, sig_mult * (sigma_eff_current or 0.0))
        return min(max(base, floor), cap)
