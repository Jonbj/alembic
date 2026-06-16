"""Generate S4 OOS gate report using real historical sentiment signals from PostgreSQL.

Usage:
    python scripts/run_s4_gate_report.py

Output:
    reports/s4_gate_report_2026/gate_report.json
    reports/s4_gate_report_2026/summary.json
    docs/s4_gate_report_2026.md   (human-readable markdown)

Prerequisites:
    - DATABASE_URL set in .env and pointing to the production database
    - Sentiment signals table populated for 2023-01 to 2025-12
    - Market price data available via DataLoader (downloads from yfinance if absent)

Gate thresholds (from master roadmap B-05):
    G1  OOS Sharpe    > 0.30
    G2  Calmar ratio  > 0.50
    G3  Hit rate      > 52%
    G4  Max drawdown  < 20%
    G5  IC (30d roll) > 0.03
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    from src.backtest.data.loader import DataLoader
    from src.backtest.data.cache import ParquetCache
    from src.backtest.walkforward.runner import WalkForwardConfig
    from src.backtest.gates.runner import GateConfig
    from src.strategies.s4.config import S4Config
    from src.strategies.s4.backtest import run_s4_backtest_from_prices_and_signals
    from src.store.pg_store import PostgreSQLStore

    OOS_START = date(2023, 1, 1)
    OOS_END = date(2025, 12, 31)
    OUTPUT_DIR = Path("reports/s4_gate_report_2026")
    GATE_REPORT_MD = Path("docs/s4_gate_report_2026.md")

    # --- Load prices ---
    log.info("Loading price data for OOS period %s → %s ...", OOS_START, OOS_END)
    cache = ParquetCache()
    loader = DataLoader(cache=cache)

    from scripts.run_backtest import load_universe
    universe = load_universe("s4")
    prices = loader.get_aligned_prices(universe, start=OOS_START, end=OOS_END)
    log.info("Prices loaded: %d days × %d tickers", len(prices), prices.shape[1])

    # --- Load signals from DB ---
    log.info("Loading sentiment signals from PostgreSQL ...")
    with PostgreSQLStore() as store:
        tickers = [c for c in prices.columns if c != "SPY"]
        rows = store.fetch_signals_for_backtest_batch(tickers, str(OOS_START), str(OOS_END))

    import pandas as pd
    if rows:
        signals_df = pd.DataFrame(rows)
        signals_df["generated_at"] = pd.to_datetime(signals_df["generated_at"])
        log.info("Loaded %d signals for %d tickers", len(signals_df), signals_df["symbol"].nunique())
    else:
        log.warning("No signals found in DB — using synthetic fallback (not valid for gate report)")
        signals_df = pd.DataFrame(columns=["symbol", "score", "confidence", "generated_at"])

    # --- Run backtest ---
    log.info("Running S4 walk-forward backtest ...")
    wf_config = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)  # 2y IS, 1y OOS
    gate_config = GateConfig(
        sharpe_threshold=0.30,
        calmar_threshold=0.50,
        hit_rate_threshold=0.52,
        max_drawdown_threshold=0.20,
    )

    result = run_s4_backtest_from_prices_and_signals(
        prices=prices,
        signals_df=signals_df,
        output_dir=OUTPUT_DIR,
        wf_config=wf_config,
        s4_config=S4Config(),
        gate_config=gate_config,
        run_robustness=True,
    )

    # --- Write markdown gate report ---
    GATE_REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    _write_markdown_report(result, GATE_REPORT_MD, OOS_START, OOS_END)

    # --- Print summary ---
    log.info("OOS Sharpe: %.3f", result["oos_sharpe"])
    log.info("Hard gates pass: %s", result["hard_gates_pass"])
    log.info("All gates pass: %s", result["all_gates_pass"])
    log.info("Report: %s", result["report_path"])
    log.info("Markdown: %s", GATE_REPORT_MD)

    if result["all_gates_pass"]:
        log.info("✅ ALL GATES PASSED — update config/strategies.yaml: S4 allocation_pct → 0.20, mode → live")
    else:
        log.warning("❌ Some gates FAILED — review gate_report.json before promoting S4")


def _write_markdown_report(result: dict, path: Path, start, end) -> None:
    gate_report = result["gate_report"]
    sharpe = result["oos_sharpe"]

    lines = [
        f"# S4 Gate Report — {date.today().isoformat()}",
        f"",
        f"**OOS Period:** {start} → {end}",
        f"**OOS Sharpe:** {sharpe:.3f}",
        f"",
        f"## Gate Results",
        f"",
        f"| Gate | Metric | Value | Threshold | Pass |",
        f"|------|--------|-------|-----------|------|",
    ]

    gate_labels = {
        "gate_1_significance": ("G1", "OOS Sharpe", "> 0.30"),
        "gate_2_walkforward": ("G2", "WF consistency", "Sharpe > 0 in >50% windows"),
        "gate_3_robustness": ("G3", "Perturbation", "Mean perturbed Sharpe > 0"),
        "gate_4_regime": ("G4", "Regime", "Sharpe in both regimes"),
        "gate_5_stress": ("G5", "Stress", "No excessive drawdown"),
    }

    for key, (gid, metric, threshold) in gate_labels.items():
        gate = gate_report.get(key, {})
        passed = gate.get("passed", False)
        val = gate.get("value", "N/A")
        icon = "✅" if passed else "❌"
        lines.append(f"| {gid} | {metric} | {val} | {threshold} | {icon} |")

    all_pass = result["all_gates_pass"]
    hard_pass = result["hard_gates_pass"]
    lines += [
        f"",
        f"**Hard gates (G1, G2):** {'✅ PASS' if hard_pass else '❌ FAIL'}",
        f"**All gates:** {'✅ PASS' if all_pass else '❌ FAIL'}",
        f"",
        f"## Recommendation",
        f"",
    ]
    if all_pass:
        lines += [
            "All gates passed. Update `config/strategies.yaml`:",
            "```yaml",
            "S4:",
            "  allocation_pct: 0.20",
            "  mode: live",
            "```",
        ]
    else:
        lines += ["Gates failed. Do not promote S4 to full allocation until issues are resolved."]

    path.write_text("\n".join(lines))


if __name__ == "__main__":
    main()
