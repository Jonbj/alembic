"""S2 strategy: SPY put selection and entry rules.

Selects the optimal SPY put to sell (cash-secured put) given an as_of date
and available capital. Uses synthetic option chains from OptionChainDataLoader
and pre-computed greeks from the chain (originally computed via compute_greeks).

Entry logic:
  1. Generate synthetic SPY chain for all expiries in DTE [min_dte, max_dte].
  2. Filter puts by delta tolerance around target_delta (-0.20).
  3. Filter by liquidity (OI, volume).
  4. Optionally filter by VRP (implied_vol - realized_vol >= threshold).
  5. Pick contract with delta closest to target_delta.
  6. Size: floor(capital * max_collateral_pct / (strike * 100)) contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

import pandas as pd

from src.data.options.ingestion import OptionChainDataLoader, _generate_expiries
from src.strategies.s2.config import S2Config

_MULTIPLIER = 100  # standard options multiplier


@dataclass
class PutSignal:
    symbol: str
    trade_date: date
    expiry: date
    strike: float
    right: str
    delta: float
    implied_vol: float
    mid: float
    quantity: int
    collateral: float
    vrp: Optional[float]


def select_put(
    as_of: date,
    capital: float,
    config: Optional[S2Config] = None,
    underlying_price: float = 450.0,
    realized_vol: Optional[float] = None,
) -> Optional[PutSignal]:
    """Select the best SPY put to sell on as_of given capital constraints.

    Args:
        as_of:            Trade date for the signal.
        capital:          Total portfolio capital in dollars.
        config:           S2Config; uses defaults if None.
        underlying_price: SPY closing price on as_of (used for synthetic chain).
        realized_vol:     Annualized realized vol used for VRP filter.
                          If None, VRP filter is skipped.

    Returns:
        PutSignal with contract details and quantity, or None if no valid
        contract exists (no DTE match, all filtered out, or capital too small).
    """
    cfg = config or S2Config()
    loader = OptionChainDataLoader()

    # Collect all expiries and keep those within DTE window
    expiries_in_range = [
        exp
        for exp in _generate_expiries(as_of, num_expiries=5)
        if cfg.min_dte <= (exp - as_of).days <= cfg.max_dte
    ]

    if not expiries_in_range:
        return None

    frames: list[pd.DataFrame] = []
    for expiry in expiries_in_range:
        chain = loader.generate_chain("SPY", as_of, expiry, underlying_price=underlying_price)
        frames.append(chain)

    all_chains = pd.concat(frames, ignore_index=True)

    # Filter: puts only
    puts = all_chains[all_chains["right"] == "P"].copy()

    # Delta filter: target_delta ± tolerance (puts have negative delta)
    delta_lo = cfg.target_delta - cfg.delta_tolerance
    delta_hi = cfg.target_delta + cfg.delta_tolerance
    puts = puts[(puts["delta"] >= delta_lo) & (puts["delta"] <= delta_hi)]

    # Liquidity filter
    puts = puts[
        (puts["open_interest"] >= cfg.min_open_interest)
        & (puts["volume"] >= cfg.min_volume)
    ]

    # VRP filter: only when realized_vol is provided
    if realized_vol is not None:
        puts = puts[puts["implied_vol"] - realized_vol >= cfg.vrp_entry_threshold]

    if puts.empty:
        return None

    # Select contract with delta closest to target
    puts = puts.copy()
    puts["_delta_dist"] = (puts["delta"] - cfg.target_delta).abs()
    best = puts.sort_values("_delta_dist").iloc[0]

    # Sizing: maximum contracts within collateral cap
    strike = float(best["strike"])
    collateral_per_contract = strike * _MULTIPLIER
    max_collateral = capital * cfg.max_collateral_pct
    quantity = int(max_collateral / collateral_per_contract)

    if quantity < 1:
        return None

    expiry_val = best["expiry"]
    if hasattr(expiry_val, "date"):
        expiry_val = expiry_val.date()

    vrp = float(best["implied_vol"]) - realized_vol if realized_vol is not None else None

    return PutSignal(
        symbol="SPY",
        trade_date=as_of,
        expiry=expiry_val,
        strike=strike,
        right="P",
        delta=float(best["delta"]),
        implied_vol=float(best["implied_vol"]),
        mid=float(best["mid"]),
        quantity=quantity,
        collateral=float(quantity * collateral_per_contract),
        vrp=vrp,
    )
