"""S2 strategy: exit logic for short put positions.

Exit conditions (evaluated in priority order):
  1. EXPIRY      — DTE <= force_close_dte (forced close to avoid assignment)
  2. STOP_LOSS   — loss > stop_loss_multiplier × initial premium, OR
                   underlying dropped > underlying_stop_loss_pct from entry
  3. TARGET_PROFIT — premium captured >= profit_target_pct
  4. TIME_DECAY  — DTE < min_dte_exit (close to harvest remaining theta)
  5. SIGNAL_FLIP — VRP turned negative (implied_vol - realized_vol < 0)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from src.strategies.s2.config import S2Config
from src.strategies.s2.signal import PutSignal

_MULTIPLIER = 100


class ExitReason(Enum):
    TARGET_PROFIT = "TARGET_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_DECAY = "TIME_DECAY"
    SIGNAL_FLIP = "SIGNAL_FLIP"
    EXPIRY = "EXPIRY"


@dataclass
class ExitSignal:
    reason: ExitReason
    exit_date: date
    pnl: float


def compute_pnl(signal: PutSignal, current_mid: float) -> float:
    """P&L for a short put position.

    Short put: received signal.mid at entry, costs current_mid to close.
    P&L = (signal.mid - current_mid) × quantity × 100
    """
    return (signal.mid - current_mid) * signal.quantity * _MULTIPLIER


def evaluate_exit(
    signal: PutSignal,
    current_price: float,
    current_date: date,
    current_mid: float,
    implied_vol: Optional[float] = None,
    realized_vol: Optional[float] = None,
    entry_price: Optional[float] = None,
    config: Optional[S2Config] = None,
) -> Optional[ExitSignal]:
    """Evaluate whether the short put position should be closed.

    Args:
        signal:        Original entry signal (contains strike, expiry, mid, etc.).
        current_price: Current underlying price.
        current_date:  Date of evaluation.
        current_mid:   Current option mid price (cost to close).
        implied_vol:   Current implied volatility (for signal flip check).
        realized_vol:  Current realized volatility (for signal flip check).
        entry_price:   Underlying price at entry (for underlying stop loss).
                       If None, the underlying stop loss check is skipped.
        config:        S2Config; uses defaults if None.

    Returns:
        ExitSignal with reason and P&L, or None if no exit condition is met.
    """
    cfg = config or S2Config()
    dte = (signal.expiry - current_date).days
    pnl = compute_pnl(signal, current_mid)
    initial_premium = signal.mid * signal.quantity * _MULTIPLIER

    # Priority 1: forced close to avoid assignment
    if dte <= cfg.force_close_dte:
        return ExitSignal(reason=ExitReason.EXPIRY, exit_date=current_date, pnl=pnl)

    # Priority 2: stop loss
    if pnl < -cfg.stop_loss_multiplier * initial_premium:
        return ExitSignal(reason=ExitReason.STOP_LOSS, exit_date=current_date, pnl=pnl)
    if entry_price is not None:
        underlying_drop = (entry_price - current_price) / entry_price
        if underlying_drop > cfg.underlying_stop_loss_pct:
            return ExitSignal(reason=ExitReason.STOP_LOSS, exit_date=current_date, pnl=pnl)

    # Priority 3: target profit
    pct_captured = (signal.mid - current_mid) / signal.mid if signal.mid > 0 else 0.0
    if pct_captured >= cfg.profit_target_pct:
        return ExitSignal(reason=ExitReason.TARGET_PROFIT, exit_date=current_date, pnl=pnl)

    # Priority 4: time decay
    if dte < cfg.min_dte_exit:
        return ExitSignal(reason=ExitReason.TIME_DECAY, exit_date=current_date, pnl=pnl)

    # Priority 5: signal flip
    if implied_vol is not None and realized_vol is not None:
        if implied_vol - realized_vol < 0:
            return ExitSignal(reason=ExitReason.SIGNAL_FLIP, exit_date=current_date, pnl=pnl)

    return None
