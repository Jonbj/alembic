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

from src.util.retry import retry_transient
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


def _fetch_account_state() -> tuple[float, float]:
    """Fetch real NAV (account equity) and gross exposure from Alpaca.

    total_exposure = Σ|position market value| / equity, as a fraction of NAV.
    Returns (0.0, 0.0) if the broker is unreachable: the report is still stored
    with the DB-derived drawdown metrics, and the exposure alert stays silent
    rather than firing on a placeholder value.
    """
    from alpaca.trading.client import TradingClient

    from src.config import config

    try:
        client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        equity = float(retry_transient(client.get_account).equity)
        gross = sum(abs(float(p.market_value)) for p in retry_transient(client.get_all_positions))
        exposure = gross / equity if equity > 0 else 0.0
        return equity, exposure
    except Exception as e:
        log.warning("Could not fetch Alpaca account state: %s — nav/exposure set to 0", e)
        return 0.0, 0.0


def _fetch_equity_curve(pg, current_equity: float) -> list[float]:
    """Real account-equity curve for the drawdown alert (#107).

    Historical NAV from risk_reports (nav > 0, on/after the clean baseline date)
    plus the current live equity appended. Anchoring at the baseline excludes
    pre-baseline garbage NAV. On error / empty → returns whatever it has (caller
    reports 0 drawdown for <2 points: fail-safe, never a spurious CRITICAL).
    """
    from src.config import config

    baseline = getattr(config, "RISK_DRAWDOWN_BASELINE_DATE", "2026-07-04")
    curve: list[float] = []
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nav FROM risk_reports
                WHERE nav > 0 AND timestamp::date >= %s::date
                ORDER BY timestamp ASC
                """,
                (baseline,),
            )
            curve = [float(r[0]) for r in cur.fetchall()]
    except Exception as e:
        log.warning("Could not fetch equity curve for drawdown (#107): %s", e)
        curve = []
    if current_equity and current_equity > 0:
        curve.append(float(current_equity))
    return curve


def _fetch_position_weights() -> dict[str, float]:
    """Per-symbol portfolio weights (|market value| / gross) from Alpaca, for a
    meaningful concentration (Herfindahl) metric. #75: the report previously fed
    {"portfolio": 1.0}, making HHI a constant 1.0 that measured nothing. Returns
    {} on any broker error / no positions → caller falls back to the old value.
    """
    from alpaca.trading.client import TradingClient

    from src.config import config

    try:
        client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        market_values = {
            p.symbol: abs(float(p.market_value)) for p in retry_transient(client.get_all_positions)
        }
        gross = sum(market_values.values())
        if gross <= 0:
            return {}
        return {sym: mv / gross for sym, mv in market_values.items()}
    except Exception as e:
        log.warning("Could not fetch position weights for HHI (#75): %s", e)
        return {}


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

    log.info("Starting daily risk monitor computation...")

    pg = None
    try:
        pg = PostgreSQLStore()

        nav, total_exposure = _fetch_account_state()

        # Whole-book drawdown comes from the real Alpaca equity curve (#107),
        # not from a per-strategy return series. We deliberately pass NO
        # strategy_returns: the only "strategy" the DB view portfolio_daily_state
        # can describe is the whole book, and its daily_return is
        # SUM(net_pnl)/SUM(entry_notional) over the trades closed that day — a
        # closed-trades-only notional return, not a NAV-based portfolio return.
        # Feeding that into the per-strategy drawdown machinery (_compute_drawdown
        # cumprod's it) produced a bogus ~17% 'Strategy portfolio drawdown' ALERT
        # every night (F-003, 14 occurrences 07-31 → 08-21) while the real drawdown
        # was ~1.2%. The whole-book drawdown is reported as combined_drawdown
        # below; no synthetic per-strategy entry is registered.
        from src.portfolio.risk_monitor import max_drawdown_from_equity

        equity_curve = _fetch_equity_curve(pg, nav)
        if not equity_curve:
            # No historical snapshots and broker unreachable (nav == 0) — the
            # equity curve is empty and there is nothing meaningful to report.
            log.info("No equity curve and broker unreachable — skipping risk report")
            return {"skipped": True, "reason": "no_data"}

        equity_dd = max_drawdown_from_equity(equity_curve)

        # Stale-drawdown instrumentation (F-003, point 3): when the live equity
        # could not be appended (broker unreachable → nav == 0) the curve holds
        # historical snapshots only, so combined_drawdown is frozen at whatever
        # the last reachable peak implies — it does not reflect today. Surface
        # that so a frozen value is not read as a live measurement.
        if nav <= 0:
            log.warning(
                "Broker unreachable (nav=0): combined_drawdown=%.4f computed from "
                "historical snapshots only — may be stale, not today's drawdown",
                equity_dd,
            )

        from src.portfolio.risk_monitor import _herfindahl

        position_weights = _fetch_position_weights()
        hhi_override = _herfindahl(position_weights) if position_weights else None

        monitor = PortfolioRiskMonitor(target_weights={})

        report = monitor.compute_report(
            strategy_returns={},
            current_weights={},
            total_exposure=total_exposure,
            nav=nav,
            combined_drawdown_override=equity_dd,
            herfindahl_override=hhi_override,
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
