"""S4 gate CLI — runnable entry point for S4 validation gate script.

Usage:
    python -m src.strategies.s4.gate_cli [--output-dir reports/s4_backtest]

Produces gate_report.json, summary.json, gate_report_id.txt under output_dir.
Optionally links the completed report to strategy_lifecycle in PostgreSQL.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def link_gate_report_to_lifecycle(
    strategy_id: str,
    gate_report_id: str,
    db_conn,
) -> None:
    """Write gate_report_id to strategy_lifecycle so request_promotion() can reference it.

    This is the bridge between the S4 gate run and the promotion workflow.
    After a successful gate run, call this to mark the report as available.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE strategy_lifecycle
               SET gate_report_id = %s,
                   updated_at     = NOW()
             WHERE strategy_id    = %s
            """,
            (gate_report_id, strategy_id),
        )
    db_conn.commit()
    log.info("Linked gate_report_id=%s to strategy_lifecycle[%s]", gate_report_id, strategy_id)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: run S4 gates and optionally link result to lifecycle table."""
    parser = argparse.ArgumentParser(description="Run S4 validation gate script")
    parser.add_argument(
        "--output-dir",
        default="reports/s4_backtest",
        help="Directory for gate report output",
    )
    parser.add_argument(
        "--link-lifecycle",
        action="store_true",
        help="Write gate_report_id to strategy_lifecycle table after run",
    )
    args = parser.parse_args(argv)

    from src.strategies.s4.backtest import run_s4_backtest_full

    log.info("Running S4 gate script → %s", args.output_dir)
    result = run_s4_backtest_full(output_dir=Path(args.output_dir))

    gate_report_id = result.get("gate_report_id", "")
    log.info(
        "S4 gate complete. OOS Sharpe=%.4f hard_gates=%s all_gates=%s report_id=%s",
        result.get("oos_sharpe", 0.0),
        result.get("hard_gates_pass"),
        result.get("all_gates_pass"),
        gate_report_id,
    )

    if args.link_lifecycle and gate_report_id:
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as store:
                conn = store._get_connection()
                link_gate_report_to_lifecycle("S4", gate_report_id, conn)
        except Exception as exc:
            log.warning("Could not link gate report to lifecycle: %s", exc)

    return 0 if result.get("hard_gates_pass") else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
