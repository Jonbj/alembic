"""S4 BUG-A reproduction: backtest/live entry-gate drift.

The LIVE order gate is `feedback:entry_threshold:S4` (ratchet, baseline 0.30),
enforced in portfolio_scheduler.py:1277-1340. The BACKTEST (backtest.py) does
NOT apply this gate — it uses only the ranker's min_score=0.10 prefilter
(ranking.py:181). So the backtest OOS Sharpe (if computed) does not reflect the
live gate, and backtest results are not representative of live behavior.

This is a drift between the validation environment (backtest) and production
(paper live): a signal with score in [0.10, 0.30) passes the backtest ranker but
is REJECTED by the live entry gate. The backtest over-admits vs live.

Run: PYTHONPATH=. python docs/audits/strategies/S4/repro_1_gate_drift.py
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"


def references(path: Path, needle: str) -> list[str]:
    """Return list of 'file:line' hits for a substring (comment-aware, raw)."""
    hits = []
    if not path.exists():
        return hits
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if needle in line:
            hits.append(f"{path.name}:{i}: {line.strip()}")
    return hits


def main() -> None:
    print("=== S4 BUG-A: backtest/live entry-gate drift ===\n")
    bt = SRC / "strategies" / "s4" / "backtest.py"
    sched = SRC / "workers" / "portfolio_scheduler.py"
    cfg = SRC / "strategies" / "s4" / "config.py"

    print("LIVE gate (portfolio_scheduler.py):")
    for h in references(sched, "entry_threshold")[:5]:
        print(f"  {h}")
    print(f"  ... (total entry_threshold refs in scheduler: "
          f"{len(references(sched, 'entry_threshold'))})")

    print("\nBACKTEST gate (backtest.py):")
    et = references(bt, "entry_threshold")
    print(f"  entry_threshold references in backtest.py: {len(et)}")
    print(f"  feedback:entry_threshold references: {len(references(bt, 'feedback:entry_threshold'))}")
    print(f"  _get_feedback_threshold references: {len(references(bt, '_get_feedback_threshold'))}")

    print("\nRanker prefilter (the ONLY filter the backtest applies):")
    for h in references(cfg, "min_score"):
        print(f"  {h}")

    print("\n--- Verdict ---")
    n_bt = len(references(bt, "entry_threshold"))
    n_sched = len(references(sched, "entry_threshold"))
    if n_bt == 0 and n_sched > 0:
        print(f"CONFIRMED: backtest.py has 0 references to entry_threshold; "
              f"portfolio_scheduler.py has {n_sched}. The live ratchet gate "
              f"(baseline 0.30) is NOT replicated in the backtest, which only "
              f"applies the ranker min_score=0.10 prefilter. A signal with "
              f"score in [0.10, 0.30) is admitted in backtest but rejected in "
              f"live -> backtest OOS Sharpe over-admits vs live behavior -> "
              f"backtest is not representative of the live gate.")
    else:
        print(f"NOT CONFIRMED: bt={n_bt} sched={n_sched}")


if __name__ == "__main__":
    main()