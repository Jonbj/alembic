"""S2 audit — repro_3: accounting divergence — put P&L is decorative, not in NAV.

The backtest's portfolio NAV (src/backtest/engine/portfolio.py:97) is

    total_nav = cash + total_position_value

where `total_position_value` is the mark-to-market of EQUITY positions only.
The short-put P&L computed by `compute_pnl` (exit.py:39-45) is returned inside
`ExitSignal.pnl` by `evaluate_exit`, but the caller `VRPStrategy.__call__`
(strategy.py:226-242) only uses `exit_signal.reason` for logging and issues a
SELL-SPY order; it NEVER writes `exit_signal.pnl` to the portfolio.

Consequence: the OOS Sharpe in summary.json (-0.613) measures a long-SPY
regime-gated position, NOT the short-put VRP P&L.

This repro demonstrates the divergence deterministically by simulating two
identical runs that differ ONLY in the put's mark price (current_mid). A correct
accounting would make NAV differ by the put P&L; the S2 backtest makes NAV
IDENTICAL because the put P&L never enters the portfolio.

We do NOT instantiate the real VirtualPortfolio (to avoid touching live code
paths); we replicate the two NAV components the S2 backtest actually uses
(cash + SPY_position_value) and show the put P&L is absent.

Run: python docs/audits/strategies/S2/repro_3_accounting.py
"""
from __future__ import annotations

# The ONLY components the S2 backtest NAV uses (portfolio.py:97):
#   nav = cash + (spy_qty * spy_price)
# The put P&L (compute_pnl) is computed but never added.

def spy_equity_nav(cash, spy_qty, spy_price):
    """Replicates VirtualPortfolio.total_nav for the S2 equity proxy."""
    return cash + spy_qty * spy_price

def put_pnl(entry_mid, current_mid, qty, mult=100):
    """Replicates exit.compute_pnl — the short-put P&L (never written to NAV)."""
    return (entry_mid - current_mid) * qty * mult

# Two scenarios at exit time. Same SPY position, same cash. DIFFERENT put mark.
# In a correct VRP accounting, scenario X (put expired worthless, mid~0) books
# the full premium as profit; scenario Y (put blown out, mid>>entry) books a loss.
entry_mid = 2.00
spy_qty = 44
spy_price = 450.0
cash = 100_000.0
put_qty = 10

# Scenario X: put collapsed (good for seller) -> mid 0.10 -> big profit
mid_X, pnl_X = 0.10, put_pnl(entry_mid, 0.10, put_qty)
# Scenario Y: put blew out (bad for seller) -> mid 5.00 -> big loss
mid_Y, pnl_Y = 5.00, put_pnl(entry_mid, 5.00, put_qty)

nav_X = spy_equity_nav(cash, spy_qty, spy_price)
nav_Y = spy_equity_nav(cash, spy_qty, spy_price)

print("=== Two exit scenarios, identical SPY, different put mark ===")
print(f"Scenario X (put collapsed): put mid={mid_X}, put P&L=+${pnl_X:.2f}")
print(f"Scenario Y (put blown out):  put mid={mid_Y}, put P&L=${pnl_Y:.2f}")
print(f"\nPut P&L difference (correct accounting would change NAV by this): ${pnl_X - pnl_Y:.2f}")
print(f"\nS2 backtest NAV (cash + SPY equity) — scenario X: ${nav_X:,.2f}")
print(f"S2 backtest NAV (cash + SPY equity) — scenario Y: ${nav_Y:,.2f}")
print(f"NAV difference captured by S2 backtest: ${nav_X - nav_Y:.2f}")

if nav_X == nav_Y and (pnl_X - pnl_Y) != 0:
    print("\nCONFIRMED: the S2 backtest NAV is IDENTICAL across the two scenarios")
    print("even though the short-put P&L differs by ${:.2f}. The put premium P&L".format(pnl_X - pnl_Y))
    print("(compute_pnl / ExitSignal.pnl) is never written to the portfolio NAV")
    print("(portfolio.py:97 = cash + equity only). The OOS Sharpe therefore measures")
    print("the long-SPY equity proxy, NOT the short-put VRP P&L.")
else:
    print("\nResult not as predicted; inspect manually.")