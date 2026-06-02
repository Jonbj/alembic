"""Decay monitor Celery task (T-605).

Scheduled monthly (1st of month at 23:00 UTC). Fetches recent actual performance
from PostgreSQL, compares against backtest baselines, and stores decay reports.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict

from src.workers.celery_app import app

log = logging.getLogger(__name__)


# ── Known backtest baselines ──────────────────────────────────────────────────

_BASELINES: dict[str, dict[str, float]] = {
    "S1": {
        "ic": 0.035,
        "hit_rate": 0.54,
        "sharpe": 0.95,
        "max_drawdown": 0.08,
    },
    "S2": {
        "ic": 0.042,
        "hit_rate": 0.56,
        "sharpe": 1.10,
        "max_drawdown": 0.06,
    },
    "S4": {
        "ic": 0.028,
        "hit_rate": 0.52,
        "sharpe": 0.80,
        "max_drawdown": 0.10,
    },
}


def _fetch_actual_metrics(strategy_id: str, pg) -> dict[str, float]:
    """Fetch actual performance metrics from DB for the last 30 days.

    Falls back to zeros if data is unavailable.
    """
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            # Try to get recent signal-based metrics
            cur.execute(
                """SELECT
                    AVG(CASE WHEN score > 0 THEN 1.0 ELSE 0.0 END) AS hit_rate,
                    CORR(score, forward_return_5d) AS ic,
                    COUNT(*) AS n
                FROM sentiment_signals
                WHERE strategy_id = %s
                  AND created_at >= now() - INTERVAL '30 days'
                """,
                (strategy_id,),
            )
            row = cur.fetchone()
            if row and row[2] and row[2] >= 10:
                hit_rate = float(row[0] or 0.5)
                ic = float(row[1] or 0.0)
            else:
                hit_rate = 0.5
                ic = 0.0

            # Sharpe approximation from daily returns
            cur.execute(
                """SELECT daily_return
                FROM portfolio_daily_state
                WHERE strategy_id = %s
                  AND snapshot_date >= now() - INTERVAL '30 days'
                ORDER BY snapshot_date ASC
                """,
                (strategy_id,),
            )
            returns = [float(r[0]) for r in cur.fetchall()]
            if len(returns) >= 5:
                arr = __import__("numpy").array(returns)
                std = float(arr.std())
                sharpe = float(arr.mean() / std * (252 ** 0.5)) if std > 0 else 0.0
            else:
                sharpe = 0.0

            # Max drawdown from returns
            import numpy as np
            if returns:
                cumulative = np.cumprod([1.0 + r for r in returns])
                peak = np.maximum.accumulate(cumulative)
                drawdowns = (cumulative - peak) / peak
                max_dd = float(-np.min(drawdowns))
            else:
                max_dd = 0.0

        return {
            "ic": ic,
            "hit_rate": hit_rate,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
        }
    except Exception as e:
        log.warning("Could not fetch actual metrics for %s: %s — using zeros", strategy_id, e)
        return {"ic": 0.0, "hit_rate": 0.5, "sharpe": 0.0, "max_drawdown": 0.0}


def _store_decay_report(pg, report) -> int:
    """Store DecayReport to decay_reports table, return inserted id."""
    from src.portfolio.decay_monitor import DecayLevel

    conn = pg._get_connection()
    try:
        with conn.cursor() as cur:
            for metric in report.metrics:
                cur.execute(
                    """INSERT INTO decay_reports
                       (timestamp, strategy_id, metric, baseline_value,
                        actual_value, decay_score, alert_level, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id""",
                    (
                        report.timestamp,
                        report.strategy_id,
                        metric.metric,
                        metric.baseline,
                        metric.actual,
                        metric.decay_score,
                        metric.level.value,
                        json.dumps({"note": metric.note}),
                    ),
                )
                row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


@app.task(name="src.workers.decay_monitor_task.run_decay_check")
def run_decay_check() -> dict:
    """Monthly decay monitoring: compare actual vs baseline performance.

    Returns:
        Summary dict with per-strategy decay scores and alert counts.
    """
    from src.portfolio.decay_monitor import DecayLevel, DecayMonitor
    from src.store.pg_store import PostgreSQLStore

    log.info("Starting monthly decay monitor...")

    monitor = DecayMonitor(baselines=_BASELINES)
    pg = None
    results: dict[str, dict] = {}
    total_alerts = 0

    try:
        pg = PostgreSQLStore()

        for strategy_id in _BASELINES:
            actual = _fetch_actual_metrics(strategy_id, pg)
            report = monitor.compute_report(strategy_id, actual)

            # Log alerts
            for alert in report.alerts:
                if report.overall_level == DecayLevel.CRITICAL:
                    log.critical("DECAY CRITICAL [%s]: %s", strategy_id, alert)
                else:
                    log.warning("DECAY WARNING [%s]: %s", strategy_id, alert)

            total_alerts += len(report.alerts)

            # Store to DB
            try:
                _store_decay_report(pg, report)
            except Exception as e:
                log.warning("Could not store decay report for %s: %s", strategy_id, e)

            results[strategy_id] = {
                "overall_decay_score": report.overall_decay_score,
                "overall_level": report.overall_level.value,
                "n_alerts": len(report.alerts),
                "metrics": {
                    m.metric: {
                        "baseline": m.baseline,
                        "actual": m.actual,
                        "decay_score": m.decay_score,
                        "level": m.level.value,
                    }
                    for m in report.metrics
                },
            }

        log.info(
            "Decay monitor complete: %d strategies, %d total alerts",
            len(results),
            total_alerts,
        )

        return {
            "strategies": results,
            "total_alerts": total_alerts,
        }

    except Exception as e:
        log.exception("Decay monitor task failed: %s", e)
        return {"error": str(e)}
    finally:
        if pg is not None:
            pg.close()