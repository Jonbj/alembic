"""Backtest analysis endpoints."""

from fastapi import APIRouter, Depends
from typing import Annotated

from src.api.deps import get_pg_store
from src.store.pg_store import PostgreSQLStore

router = APIRouter(prefix="/api/backtest")


@router.get("/runs")
def get_runs(pg: Annotated[PostgreSQLStore, Depends(get_pg_store)]) -> list[dict]:
    """List all backtest runs with summary counts."""
    conn = pg._get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                run_id,
                COUNT(*)                                        AS total,
                COUNT(score)                                    AS scored,
                COUNT(forward_return_24h)                       AS with_return,
                MIN(generated_at)                               AS started_at,
                MAX(generated_at)                               AS ended_at,
                COUNT(DISTINCT symbol)                          AS symbols,
                COUNT(DISTINCT model_id)                        AS models
            FROM backtest_signals
            GROUP BY run_id
            ORDER BY MIN(generated_at)
        """)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@router.get("/{run_id}/summary")
def get_summary(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> dict:
    """
    Key performance metrics for a backtest run.

    Returns IC, ICIR, hit_rate, avg_long_return, avg_short_return computed
    only on signals that have a non-null forward_return_24h.
    """
    conn = pg._get_connection()
    with conn.cursor() as cur:
        # Spearman IC: compute ranks first in CTE, then corr() in outer query
        cur.execute("""
            WITH ranked AS (
                SELECT
                    percent_rank() OVER (ORDER BY score)              AS r_score,
                    percent_rank() OVER (ORDER BY forward_return_24h) AS r_ret,
                    score,
                    forward_return_24h
                FROM backtest_signals
                WHERE run_id = %s
                  AND score IS NOT NULL
                  AND forward_return_24h IS NOT NULL
            )
            SELECT
                corr(r.r_score, r.r_ret)                         AS ic,
                AVG(CASE WHEN r.score > 0.05  THEN r.forward_return_24h END) AS avg_long_return,
                AVG(CASE WHEN r.score < -0.05 THEN r.forward_return_24h END) AS avg_short_return,
                AVG(CASE WHEN (r.score > 0 AND r.forward_return_24h > 0)
                              OR (r.score < 0 AND r.forward_return_24h < 0)
                         THEN 1.0 ELSE 0.0 END)                  AS hit_rate,
                COUNT(*)                                          AS n
            FROM ranked r
        """, (run_id,))
        row = cur.fetchone()
        ic, avg_long, avg_short, hit_rate, n = row

        # ICIR: ranks first, then weekly corr(), then stddev across weeks
        cur.execute("""
            WITH ranked_weekly AS (
                SELECT
                    date_trunc('week', generated_at)                                                           AS week,
                    percent_rank() OVER (PARTITION BY date_trunc('week', generated_at) ORDER BY score)              AS rs,
                    percent_rank() OVER (PARTITION BY date_trunc('week', generated_at) ORDER BY forward_return_24h) AS rr
                FROM backtest_signals
                WHERE run_id = %s
                  AND score IS NOT NULL
                  AND forward_return_24h IS NOT NULL
            ),
            weekly AS (
                SELECT week, corr(rs, rr) AS wic
                FROM ranked_weekly
                GROUP BY week
            )
            SELECT AVG(wic), STDDEV(wic), COUNT(DISTINCT week)
            FROM weekly
        """, (run_id,))
        r2 = cur.fetchone()
        avg_wic, std_wic, n_weeks = r2
        icir = (avg_wic / std_wic) if std_wic and std_wic > 0 else None

        return {
            "ic": round(float(ic), 4) if ic is not None else None,
            "icir": round(float(icir), 4) if icir is not None else None,
            "hit_rate": round(float(hit_rate), 4) if hit_rate is not None else None,
            "avg_long_return": round(float(avg_long), 4) if avg_long is not None else None,
            "avg_short_return": round(float(avg_short), 4) if avg_short is not None else None,
            "n_scored": int(n) if n else 0,
            "n_weeks": int(n_weeks) if n_weeks else 0,
        }


@router.get("/{run_id}/bucket_analysis")
def get_bucket_analysis(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    buckets: int = 10,
) -> list[dict]:
    """
    Average 24h forward return by score decile.
    Reveals whether the model's signal ranking is predictive.
    A monotonically increasing chart = good model.
    """
    conn = pg._get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            WITH bucketed AS (
                SELECT
                    width_bucket(
                        score,
                        (SELECT MIN(score) FROM backtest_signals WHERE run_id = %s AND score IS NOT NULL),
                        (SELECT MAX(score) + 0.0001 FROM backtest_signals WHERE run_id = %s AND score IS NOT NULL),
                        %s
                    ) AS bucket,
                    score,
                    forward_return_24h
                FROM backtest_signals
                WHERE run_id = %s
                  AND score IS NOT NULL
                  AND forward_return_24h IS NOT NULL
            )
            SELECT
                bucket,
                AVG(score)               AS avg_score,
                AVG(forward_return_24h)  AS avg_return,
                COUNT(*)                 AS n
            FROM bucketed
            GROUP BY bucket
            ORDER BY bucket
        """, (run_id, run_id, buckets, run_id))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@router.get("/{run_id}/model_ic")
def get_model_ic(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> list[dict]:
    """IC, hit_rate and avg_return broken down by model_id."""
    conn = pg._get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            WITH per_model AS (
                SELECT
                    model_id,
                    score,
                    forward_return_24h,
                    percent_rank() OVER (PARTITION BY model_id ORDER BY score)              AS rs,
                    percent_rank() OVER (PARTITION BY model_id ORDER BY forward_return_24h) AS rr
                FROM backtest_signals
                WHERE run_id = %s
                  AND score IS NOT NULL
                  AND forward_return_24h IS NOT NULL
            )
            SELECT
                model_id,
                COUNT(*)                    AS n,
                corr(rs, rr)               AS ic,
                AVG(CASE WHEN (score > 0 AND forward_return_24h > 0)
                              OR (score < 0 AND forward_return_24h < 0)
                         THEN 1.0 ELSE 0.0 END) AS hit_rate,
                AVG(forward_return_24h)    AS avg_return
            FROM per_model
            GROUP BY model_id
            ORDER BY ic DESC NULLS LAST
        """, (run_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@router.get("/{run_id}/symbol_ic")
def get_symbol_ic(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> list[dict]:
    """IC and hit_rate broken down by ticker symbol."""
    conn = pg._get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            WITH per_sym AS (
                SELECT
                    symbol,
                    score,
                    forward_return_24h,
                    percent_rank() OVER (PARTITION BY symbol ORDER BY score)              AS rs,
                    percent_rank() OVER (PARTITION BY symbol ORDER BY forward_return_24h) AS rr
                FROM backtest_signals
                WHERE run_id = %s
                  AND score IS NOT NULL
                  AND forward_return_24h IS NOT NULL
            )
            SELECT
                symbol,
                COUNT(*)                    AS n,
                corr(rs, rr)               AS ic,
                AVG(CASE WHEN (score > 0 AND forward_return_24h > 0)
                              OR (score < 0 AND forward_return_24h < 0)
                         THEN 1.0 ELSE 0.0 END) AS hit_rate,
                AVG(forward_return_24h)    AS avg_return
            FROM per_sym
            GROUP BY symbol
            ORDER BY n DESC
        """, (run_id,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


@router.get("/{run_id}/pnl_curve")
def get_pnl_curve(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    threshold: float = 0.05,
) -> list[dict]:
    """
    Simulated long/short P&L curve over time.
    Long signals with score > threshold, short with score < -threshold.
    Returns daily cumulative P&L (equal-weighted, no compounding).
    """
    conn = pg._get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                date_trunc('day', generated_at)::date  AS day,
                AVG(CASE WHEN score >  %s THEN forward_return_24h END) AS long_return,
                AVG(CASE WHEN score < -%s THEN forward_return_24h END) AS short_return,
                COUNT(*)                                                AS signals
            FROM backtest_signals
            WHERE run_id = %s
              AND score IS NOT NULL
              AND forward_return_24h IS NOT NULL
            GROUP BY day
            ORDER BY day
        """, (threshold, threshold, run_id))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]

        # Compute cumulative
        cum_long = 0.0
        cum_short = 0.0
        cum_ls = 0.0
        for r in rows:
            lr = float(r["long_return"] or 0)
            sr = float(r["short_return"] or 0)
            cum_long += lr
            cum_short -= sr  # short = negative of return
            cum_ls += lr - sr
            r["cum_long"] = round(cum_long, 4)
            r["cum_short"] = round(cum_short, 4)
            r["cum_long_short"] = round(cum_ls, 4)
            r["day"] = str(r["day"])
        return rows


@router.get("/{run_id}/signals")
def get_signals(
    run_id: str,
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    limit: int = 200,
    offset: int = 0,
    symbol: str | None = None,
) -> list[dict]:
    """Raw backtest signals with pagination."""
    conn = pg._get_connection()
    filters = ["run_id = %s"]
    params: list = [run_id]
    if symbol:
        filters.append("symbol = %s")
        params.append(symbol.upper())
    where = " AND ".join(filters)
    params += [min(limit, 500), offset]
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, symbol, score, confidence, model_id, ensemble_std,
                   fallback_used, forward_return_24h, forward_return_4h,
                   forward_return_1h, news_source, generated_at
            FROM backtest_signals
            WHERE {where}
            ORDER BY generated_at DESC
            LIMIT %s OFFSET %s
        """, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
