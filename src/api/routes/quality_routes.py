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
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


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
