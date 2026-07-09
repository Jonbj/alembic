"""Quality dashboard (QX-02) — sentiment + extraction quality, read-only.

Surfaces the empirical signal-quality issues from the quality review: per-model
polarity/confidence distribution, near-zero rate, ensemble fallback/divergence, and
the QX-01 label-set extraction precision/recall. Never in the hot execution path.
"""
import logging
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends

from src.api.auth import require_api_key

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quality", dependencies=[Depends(require_api_key)])

_TRADING_YAML = Path(__file__).resolve().parents[3] / "config" / "trading.yaml"


def _watchlist() -> set[str]:
    try:
        return set(yaml.safe_load(_TRADING_YAML.read_text()).get("symbols", {}).get("watchlist", []))
    except Exception:
        return set()


def _rows(cur, sql, params=()):
    """Run a query and return rows as dicts, with NUMERIC/Decimal columns coerced
    to float. Postgres NUMERIC (e.g. ROUND(...)::numeric) comes back from psycopg
    as decimal.Decimal; FastAPI's default JSON encoder serializes Decimal as a
    *string*, silently breaking the `number | null` contract the frontend expects
    and crashing any `.toFixed()` call on the value. Convert at the source so
    every caller gets a real JSON number.
    """
    from decimal import Decimal

    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [
        {col: (float(val) if isinstance(val, Decimal) else val) for col, val in zip(cols, r)}
        for r in cur.fetchall()
    ]


@router.get("/metrics")
def quality_metrics(days: int = 14) -> dict:
    """Per-model sentiment distribution, signal-level stats, and extraction metrics."""
    from src.store.pg_store import PostgreSQLStore

    out: dict = {"window_days": days, "per_model": [], "signals": {}, "extraction": {}}
    try:
        with PostgreSQLStore() as store:
            with store._get_connection().cursor() as cur:
                out["per_model"] = _rows(cur, """
                    SELECT model_id,
                           COUNT(*)::int AS n,
                           ROUND(AVG(polarity)::numeric, 3) AS mean_polarity,
                           ROUND(STDDEV(polarity)::numeric, 3) AS std_polarity,
                           ROUND(AVG(confidence)::numeric, 3) AS mean_confidence,
                           ROUND((SUM((ABS(polarity)<0.05)::int)::float / COUNT(*))::numeric, 3) AS near_zero_rate,
                           ROUND(AVG(eligible::int)::numeric, 3) AS eligible_rate
                    FROM llm_responses
                    WHERE generated_at > now() - (%s || ' days')::interval
                    GROUP BY model_id ORDER BY n DESC
                """, (str(days),))

                sig = _rows(cur, """
                    SELECT COUNT(*)::int AS n,
                           ROUND(AVG(score)::numeric, 3) AS mean_score,
                           ROUND(STDDEV(score)::numeric, 3) AS std_score,
                           ROUND((SUM((ABS(score)<0.05)::int)::float / NULLIF(COUNT(*),0))::numeric, 3) AS near_zero_rate,
                           ROUND(AVG(fallback_used::int)::numeric, 3) AS fallback_rate,
                           ROUND(AVG(ensemble_std)::numeric, 3) AS mean_ensemble_std
                    FROM sentiment_signals
                    WHERE generated_at > now() - (%s || ' days')::interval
                """, (str(days),))
                out["signals"] = sig[0] if sig else {}

                labels = _rows(cur,
                    "SELECT source, extracted_tickers, gt_tickers, gt_relevance, status "
                    "FROM news_labels WHERE status='labeled'")
        out["extraction"] = _extraction_metrics(labels, _watchlist())
    except Exception as exc:
        log.warning("quality_metrics failed: %s", exc)
    return out


@router.get("/sources")
def quality_sources(days: int = 14) -> dict:
    """Per-source funnel (EN-06), latency, near-zero and trade P&L (FIX-04).

    Removal thresholds (ROADMAP_DATA_ALPHA §7.4, applied in the frontend verdict):
    hit-rate <40% AND 30d P&L <0; or latency p50 >24h; or near-zero >50%.
    """
    from src.store.pg_store import PostgreSQLStore

    out: dict = {"window_days": days, "funnel": [], "signals": [], "trades": [],
                 "trace_coverage": {}}
    try:
        with PostgreSQLStore() as store:
            with store._get_connection().cursor() as cur:
                out["funnel"] = _rows(cur, """
                    SELECT source,
                           SUM(fetched)::int AS fetched,
                           SUM(queued)::int AS queued,
                           SUM(duplicates)::int AS duplicates,
                           SUM(discarded_no_ticker)::int AS discarded_no_ticker,
                           SUM(discarded_stale)::int AS discarded_stale,
                           SUM(parse_fail)::int AS parse_fail
                    FROM ingestion_stats_daily
                    WHERE day > CURRENT_DATE - %s::int
                    GROUP BY source ORDER BY fetched DESC
                """, (days,))

                out["signals"] = _rows(cur, """
                    SELECT nl.source,
                           COUNT(*)::int AS n_signals,
                           ROUND(AVG(ss.score)::numeric, 3) AS mean_score,
                           ROUND((SUM((ABS(ss.score) < 0.05)::int)::float
                                  / NULLIF(COUNT(*), 0))::numeric, 3) AS near_zero_rate,
                           ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                               EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at)) / 60
                           ))::numeric, 1) AS latency_p50_min,
                           ROUND((PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY
                               EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at)) / 60
                           ))::numeric, 1) AS latency_p95_min
                    FROM sentiment_signals ss
                    JOIN news_log nl ON nl.id = ss.news_log_id
                    WHERE ss.generated_at > now() - (%s || ' days')::interval
                    GROUP BY nl.source ORDER BY n_signals DESC
                """, (str(days),))

                out["trades"] = _rows(cur, """
                    SELECT COALESCE(nl.source, 'unknown') AS source,
                           COUNT(*)::int AS n_trades,
                           SUM((t.net_pnl > 0)::int)::int AS winners,
                           ROUND((SUM((t.net_pnl > 0)::int)::float
                                  / NULLIF(COUNT(*), 0))::numeric, 3) AS hit_rate,
                           ROUND(SUM(t.net_pnl)::numeric, 2) AS total_net_pnl,
                           ROUND(AVG(t.net_pnl)::numeric, 2) AS avg_net_pnl
                    FROM trades t
                    LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
                    LEFT JOIN news_log nl ON nl.id = ss.news_log_id
                    WHERE t.exit_time > now() - (%s || ' days')::interval
                      AND t.net_pnl IS NOT NULL
                    GROUP BY 1 ORDER BY total_net_pnl ASC
                """, (str(days),))

                cov = _rows(cur, """
                    SELECT COUNT(*)::int AS total,
                           SUM((news_log_id IS NOT NULL)::int)::int AS linked
                    FROM sentiment_signals
                    WHERE generated_at > now() - (%s || ' days')::interval
                """, (str(days),))
                out["trace_coverage"] = cov[0] if cov else {}
    except Exception as exc:
        log.warning("quality_sources failed: %s", exc)
    return out


def _extraction_metrics(rows: list[dict], watch: set[str]) -> dict:
    """Precision/recall/FP from the label set (mirrors validate_ticker_sentiment.py)."""
    if not rows:
        return {"n_labeled": 0}
    tp = fp = fn = n_ext = n_gt = n_gt_wl = tp_wl = rel_fp = n_macro = 0
    for r in rows:
        ext, gt = set(r["extracted_tickers"] or []), set(r["gt_tickers"] or [])
        gt_wl = {t for t in gt if t in watch}
        tp += len(ext & gt); fp += len(ext - gt); fn += len(gt - ext)
        n_ext += len(ext); n_gt += len(gt); n_gt_wl += len(gt_wl); tp_wl += len(ext & gt_wl)
        if r["gt_relevance"] in ("macro", "irrelevant"):
            n_macro += 1; rel_fp += len(ext)

    def d(a, b): return round(a / b, 3) if b else None
    return {
        "n_labeled": len(rows),
        "precision": d(tp, n_ext),
        "recall": d(tp, n_gt),
        "recall_in_watchlist": d(tp_wl, n_gt_wl),
        "fp_per_article": d(fp, len(rows)),
        "macro_fp_per_article": d(rel_fp, n_macro),
    }
