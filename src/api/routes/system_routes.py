"""System status endpoints: scheduler health and activity log."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.deps import get_pg_store, get_redis_store
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api/system", dependencies=[Depends(require_api_key)])

# Static schedule — mirrors src/workers/celery_app.py beat config
_SCHEDULE = [
    {
        "task": "sentiment-worker",
        "description": "LLM sentiment analysis on latest news",
        "cron": "*/15 14-21 * * 1-5",
        "human": "Every 15 min, 14:00–21:00 UTC, Mon–Fri",
        "db_table": "sentiment_signals",
        "db_col": "generated_at",
    },
    {
        "task": "portfolio-cycle",
        "description": "Portfolio orchestration + order execution",
        "cron": "7,22,37,52 14-21 * * 1-5",
        "human": "xx:07/22/37/52, 14:00–21:00 UTC, Mon–Fri",
        "db_table": "portfolio_cycles",
        "db_col": "timestamp",
    },
    {
        "task": "rss-ingestion",
        "description": "Reuters + CNBC RSS feed ingestion",
        "cron": "*/30 * * * *",
        "human": "Every 30 min, always",
        "db_table": "news_log",
        "db_col": "fetched_at",
        "db_filter": "source IN ('reuters','cnbc')",
    },
    {
        "task": "sec-edgar-ingestion",
        "description": "SEC EDGAR 8-K filing ingestion",
        "cron": "0 14-21 * * 1-5",
        "human": "Hourly, 14:00–21:00 UTC, Mon–Fri",
        "db_table": "news_log",
        "db_col": "fetched_at",
        "db_filter": "source = 'sec_edgar'",
    },
    {
        "task": "pead-ingestion",
        "description": "PEAD earnings classification (S7)",
        "cron": "5,35 14-21 * * 1-5",
        "human": "xx:05/35, 14:00–21:00 UTC, Mon–Fri",
        "db_table": None,
        "db_col": None,
    },
    {
        "task": "risk-monitor",
        "description": "Portfolio risk check + drawdown alert",
        "cron": "*/30 14-21 * * 1-5",
        "human": "Every 30 min during market hours",
        "db_table": None,
        "db_col": None,
    },
    {
        "task": "counterfactual-worker",
        "description": "Phase C: nightly counterfactual return calculation",
        "cron": "45 22 * * 1-5",
        "human": "22:45 UTC, Mon–Fri",
        "db_table": None,
        "db_col": None,
    },
]


@router.get("/scheduler")
def get_scheduler_status(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> list[dict]:
    """Return beat schedule with last-run timestamps from DB."""
    import psycopg2

    conn = None
    last_runs: dict[str, str | None] = {}
    try:
        from src.config import config as _cfg
        conn = psycopg2.connect(_cfg.DATABASE_URL)
        cur = conn.cursor()
        for entry in _SCHEDULE:
            if not entry["db_table"]:
                last_runs[entry["task"]] = None
                continue
            where = f"WHERE {entry['db_filter']}" if entry.get("db_filter") else ""
            try:
                cur.execute(
                    f"SELECT MAX({entry['db_col']}) FROM {entry['db_table']} {where}"
                )
                row = cur.fetchone()
                last_runs[entry["task"]] = row[0].isoformat() if row and row[0] else None
            except Exception:
                last_runs[entry["task"]] = None
    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    return [
        {
            "task": e["task"],
            "description": e["description"],
            "schedule": e["human"],
            "last_run": last_runs.get(e["task"]),
        }
        for e in _SCHEDULE
    ]


@router.get("/activity")
def get_activity_log(
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 60,
) -> list[dict]:
    """Return a unified activity log from recent system events."""
    import psycopg2

    conn = None
    events: list[dict] = []
    try:
        from src.config import config as _cfg
        conn = psycopg2.connect(_cfg.DATABASE_URL)
        cur = conn.cursor()

        # Portfolio cycles
        try:
            cur.execute(
                """SELECT timestamp, strategies_run, orders_count, constraints_fired
                   FROM portfolio_cycles
                   ORDER BY timestamp DESC LIMIT 20"""
            )
            for row in cur.fetchall():
                ts, strats, n_orders, constraints = row
                strats_str = ", ".join(strats) if isinstance(strats, list) else str(strats)
                events.append({
                    "type": "portfolio_cycle",
                    "time": ts.isoformat(),
                    "summary": f"Cycle ran {strats_str} → {n_orders} orders",
                    "detail": f"Constraints fired: {len(constraints) if isinstance(constraints, list) else 0}",
                    "status": "ok",
                })
        except Exception:
            pass

        # Recent signals (grouped by run)
        try:
            cur.execute(
                """SELECT DATE_TRUNC('minute', generated_at) AS run_time,
                          COUNT(*) AS n_signals,
                          AVG(score) AS avg_score,
                          COUNT(CASE WHEN fallback_used = TRUE THEN 1 END) AS fallbacks
                   FROM sentiment_signals
                   WHERE generated_at > NOW() - INTERVAL '24 hours'
                   GROUP BY run_time
                   ORDER BY run_time DESC LIMIT 15"""
            )
            for row in cur.fetchall():
                run_time, n_sigs, avg_score, fallbacks = row
                events.append({
                    "type": "sentiment_run",
                    "time": run_time.isoformat(),
                    "summary": f"Sentiment: {n_sigs} signals, avg score {float(avg_score or 0):.3f}",
                    "detail": f"Fallbacks: {fallbacks}",
                    "status": "ok" if (fallbacks or 0) < n_sigs * 0.5 else "warn",
                })
        except Exception:
            pass

        # Recent news ingestion (last 24h, grouped by source and hour)
        try:
            cur.execute(
                """SELECT DATE_TRUNC('hour', fetched_at) AS hour,
                          source, COUNT(*) AS n_articles
                   FROM news_log
                   WHERE fetched_at > NOW() - INTERVAL '24 hours'
                   GROUP BY hour, source
                   ORDER BY hour DESC LIMIT 20"""
            )
            for row in cur.fetchall():
                hour, source, count = row
                events.append({
                    "type": "ingestion",
                    "time": hour.isoformat(),
                    "summary": f"Ingested {count} articles from {source}",
                    "detail": None,
                    "status": "ok",
                })
        except Exception:
            pass

        # Recent trade decisions
        try:
            cur.execute(
                """SELECT tick_time, symbol, decision, reason
                   FROM execution_decisions
                   ORDER BY tick_time DESC LIMIT 15"""
            )
            for row in cur.fetchall():
                tick_time, symbol, decision, reason = row
                events.append({
                    "type": "trade_decision",
                    "time": tick_time.isoformat(),
                    "summary": f"{decision.upper()} {symbol}",
                    "detail": (reason or "")[:100],
                    "status": "ok",
                })
        except Exception:
            pass

    except Exception:
        pass
    finally:
        if conn:
            conn.close()

    events.sort(key=lambda e: e["time"], reverse=True)
    return events[:limit]
