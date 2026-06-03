"""Risk monitor Celery task for multi-strategy portfolio (T-602).

Scheduled daily after market close (22:30 UTC, after the forward-return worker at 22:00).
Reads latest positions and P&L from PostgreSQL, computes per-strategy and combined risk
metrics, stores RiskReport to the risk_reports table, and logs alert warnings.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from src.workers.celery_app import app

log = logging.getLogger(__name__)


def _serialize_report(report) -> dict:
    """Convert RiskReport to a JSON-serialisable dict."""
    per_strategy = {
        sid: {
            "strategy_id": m.strategy_id,
            "daily_pnl": m.daily_pnl,
            "drawdown": m.drawdown,
            "sharpe": m.sharpe,
            "volatility": m.volatility,
            "current_weight": m.current_weight,
            "target_weight": m.target_weight,
        }
        for sid, m in report.per_strategy_metrics.items()
    }
    alerts = [
        {
            "level": a.level.value,
            "message": a.message,
            "strategy_id": a.strategy_id,
        }
        for a in report.alerts
    ]
    return {
        "timestamp": report.timestamp.isoformat(),
        "nav": report.nav,
        "total_exposure": report.total_exposure,
        "herfindahl_index": report.herfindahl_index,
        "combined_drawdown": report.combined_drawdown,
        "strategy_correlations": report.strategy_correlations,
        "per_strategy_metrics": per_strategy,
        "alerts": alerts,
    }


def _fetch_strategy_data(pg) -> tuple[dict[str, list[float]], dict[str, float], float, float]:
    """Fetch strategy returns, weights, exposure and NAV from PostgreSQL.

    Returns (strategy_returns, current_weights, total_exposure, nav).
    Falls back to empty data if tables don't exist yet.
    """
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT strategy_id, daily_return, weight, nav, total_exposure
                FROM portfolio_daily_state
                WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM portfolio_daily_state)
                ORDER BY strategy_id
                """
            )
            rows = cur.fetchall()
    except Exception as e:
        log.warning("Could not fetch portfolio_daily_state: %s — using defaults", e)
        return {}, {}, 0.0, 0.0

    strategy_returns: dict[str, list[float]] = {}
    current_weights: dict[str, float] = {}
    nav = 0.0
    total_exposure = 0.0

    for sid, daily_ret, weight, row_nav, row_exp in rows:
        strategy_returns.setdefault(sid, []).append(float(daily_ret or 0.0))
        current_weights[sid] = float(weight or 0.0)
        nav = float(row_nav or 0.0)
        total_exposure = float(row_exp or 0.0)

    # Fetch rolling 60d history for richer metrics; only replace single-day data
    # if the history query actually returns rows (empty history → keep what we have).
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT strategy_id, daily_return
                FROM portfolio_daily_state
                WHERE snapshot_date >= now() - INTERVAL '60 days'
                ORDER BY strategy_id, snapshot_date ASC
                """
            )
            history_rows = cur.fetchall()
        if history_rows:
            strategy_returns = {}
            for sid, daily_ret in history_rows:
                strategy_returns.setdefault(sid, []).append(float(daily_ret or 0.0))
    except Exception as e:
        log.debug("Could not fetch rolling history: %s", e)

    return strategy_returns, current_weights, total_exposure, nav


def _store_risk_report(pg, report) -> int:
    """Store RiskReport to risk_reports table, return inserted id."""
    data = _serialize_report(report)
    conn = pg._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO risk_reports (
                    timestamp, nav, total_exposure, herfindahl_index,
                    combined_drawdown, per_strategy_metrics, alerts
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    report.timestamp,
                    report.nav,
                    report.total_exposure,
                    report.herfindahl_index,
                    report.combined_drawdown,
                    json.dumps(data["per_strategy_metrics"]),
                    json.dumps(data["alerts"]),
                ),
            )
            row_id: int = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


@app.task(name="src.workers.risk_monitor_task.compute_risk_report")
def compute_risk_report() -> dict:
    """Compute daily multi-strategy risk report and store to DB.

    Scheduled at 22:30 UTC daily, after the forward-return worker.
    Logs WARNING for each alert fired.

    Returns:
        Summary dict with n_alerts, combined_drawdown, herfindahl_index.
    """
    from src.portfolio.risk_monitor import AlertLevel, PortfolioRiskMonitor
    from src.store.pg_store import PostgreSQLStore
    from src.config import config

    log.info("Starting daily risk monitor computation...")

    pg = None
    try:
        pg = PostgreSQLStore()

        strategy_returns, current_weights, total_exposure, nav = _fetch_strategy_data(pg)

        # Use target weights from config if available, else equal-weight
        target_weights: dict[str, float] = getattr(config, "PORTFOLIO_TARGET_WEIGHTS", {})
        if not target_weights and current_weights:
            n = len(current_weights)
            target_weights = {sid: 1.0 / n for sid in current_weights}

        monitor = PortfolioRiskMonitor(target_weights=target_weights)

        if not strategy_returns:
            log.info("No strategy return data available — skipping risk report")
            return {"skipped": True, "reason": "no_data"}

        report = monitor.compute_report(
            strategy_returns=strategy_returns,
            current_weights=current_weights,
            total_exposure=total_exposure,
            nav=nav,
        )

        # Log all alerts
        for alert in report.alerts:
            if alert.level == AlertLevel.CRITICAL:
                log.critical("RISK CRITICAL: %s", alert.message)
            elif alert.level == AlertLevel.ALERT:
                log.warning("RISK ALERT: %s", alert.message)
            else:
                log.warning("RISK WARNING: %s", alert.message)

        try:
            report_id = _store_risk_report(pg, report)
            log.info(
                "Risk report stored (id=%d): combined_dd=%.2f%% HHI=%.3f alerts=%d",
                report_id,
                report.combined_drawdown * 100,
                report.herfindahl_index,
                len(report.alerts),
            )
        except Exception as e:
            log.warning("Could not store risk report to DB (table may not exist yet): %s", e)
            report_id = -1

        return {
            "n_alerts": len(report.alerts),
            "combined_drawdown": report.combined_drawdown,
            "herfindahl_index": report.herfindahl_index,
            "total_exposure": report.total_exposure,
            "report_id": report_id,
        }

    except Exception as e:
        log.exception("Risk monitor task failed: %s", e)
        raise
    finally:
        if pg is not None:
            pg.close()
