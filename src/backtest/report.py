"""BacktestReportBuilder — builds IC/ICIR report from backtest_signals."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.performance.ic import ICIRResult, ICResult, compute_composite_ic, compute_icir

log = logging.getLogger(__name__)

_MIN_SAMPLES = 30

_FETCH_ROWS = """
    SELECT model_id, score, confidence, fallback_used,
           forward_return_1h, forward_return_4h, forward_return_24h
    FROM backtest_signals
    WHERE run_id = %s AND score IS NOT NULL
    ORDER BY generated_at
"""

_COUNT_TOTAL = """
    SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s AND score IS NOT NULL
"""


@dataclass
class BacktestReport:
    run_id: str
    total_signals: int
    signals_with_returns: int
    ic_1h: ICResult | None
    ic_4h: ICResult | None
    ic_24h: ICResult | None
    icir_1h: ICIRResult | None
    icir_4h: ICIRResult | None
    icir_24h: ICIRResult | None
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        def _ic(r):
            if r is None:
                return None
            return {
                "composite_ic": r.composite_ic,
                "spearman_ic": r.spearman_ic,
                "weighted_hit_rate": r.weighted_hit_rate,
                "brier_score": r.brier_score,
                "sample_count": r.sample_count,
            }

        def _icir(r):
            if r is None:
                return None
            return {
                "icir": r.icir,
                "ic_mean": r.ic_mean,
                "ic_std": r.ic_std,
                "newey_west_std": r.newey_west_std,
                "lag": r.lag,
                "sample_count": r.sample_count,
            }

        return {
            "run_id": self.run_id,
            "total_signals": self.total_signals,
            "signals_with_returns": self.signals_with_returns,
            "ic_1h": _ic(self.ic_1h),
            "ic_4h": _ic(self.ic_4h),
            "ic_24h": _ic(self.ic_24h),
            "icir_1h": _icir(self.icir_1h),
            "icir_4h": _icir(self.icir_4h),
            "icir_24h": _icir(self.icir_24h),
            "by_model": self.by_model,
            "generated_at": self.generated_at.isoformat(),
        }


class BacktestReportBuilder:
    """Reads backtest_signals for a run_id and computes IC/ICIR at three horizons.

    Why three horizons?
      - 1h validates the signal's immediate directional accuracy.
      - 4h aligns with the intraday_strategy.py execution window.
      - 24h produces daily IC comparable to the live PerformanceWorker output.
      Comparing across horizons reveals the signal's decay profile.

    Why exclude fallback_used rows?
      FinBERT fallback signals are a *different* signal source (deterministic
      model, not LLM ensemble). Including them would dilute the IC measurement
      of the ensemble specifically.
    """

    def __init__(self, pg_conn) -> None:
        self._conn = pg_conn

    def build(self, run_id: str) -> BacktestReport:
        """Fetch rows and compute IC/ICIR report for all three horizons.

        Steps:
          1. COUNT total scored rows for run_id.
          2. SELECT all scored rows with forward returns.
          3. For each horizon (1h=idx0, 4h=idx1, 24h=idx2):
             - Filter out rows where return is None or fallback_used=True.
             - If < _MIN_SAMPLES (30), IC/ICIR = None (insufficient data).
             - Else call compute_composite_ic and compute_icir.
          4. Build per-model breakdown for the 24h horizon (most stable).
          5. signals_with_returns = max count across horizons (each horizon
             may have a different number of non-None returns).
        """
        with self._conn.cursor() as cur:
            cur.execute(_COUNT_TOTAL, (run_id,))
            total = cur.fetchone()[0]

            cur.execute(_FETCH_ROWS, (run_id,))
            rows = cur.fetchall()

        # rows columns: model_id, score, confidence, fallback_used,
        #               forward_return_1h, forward_return_4h, forward_return_24h
        def _extract(horizon_idx: int):
            """Extract (scores, returns, confs) for a horizon, skipping None returns.

            Why skip fallback_used?
              See class docstring — FinBERT is a different signal class.
            """
            scores, returns, confs = [], [], []
            for model_id, score, conf, fallback, r1h, r4h, r24h in rows:
                ret = [r1h, r4h, r24h][horizon_idx]
                if ret is None or fallback:
                    continue
                scores.append(score)
                returns.append(ret)
                confs.append(conf)
            return scores, returns, confs

        def _ic_icir(scores, returns, confs):
            """Compute IC and ICIR if enough samples, else None."""
            if len(scores) < _MIN_SAMPLES:
                return None, None
            return (
                compute_composite_ic(scores, returns, confs),
                compute_icir(scores, returns, confs, min_samples=_MIN_SAMPLES),
            )

        s1, r1, c1 = _extract(0)
        s4, r4, c4 = _extract(1)
        s24, r24, c24 = _extract(2)

        ic_1h, icir_1h = _ic_icir(s1, r1, c1)
        ic_4h, icir_4h = _ic_icir(s4, r4, c4)
        ic_24h, icir_24h = _ic_icir(s24, r24, c24)

        # Max across horizons because each may have different missing-bar counts.
        signals_with_returns = max(len(s1), len(s4), len(s24))

        # Per-model breakdown (24h horizon) — helps identify which models drive IC.
        by_model: dict[str, dict] = {}
        model_ids = list({row[0] for row in rows})
        for mid in model_ids:
            model_rows = [r for r in rows if r[0] == mid and not r[3]]
            ms = [r[1] for r in model_rows if r[6] is not None]
            mr = [r[6] for r in model_rows if r[6] is not None]
            mc = [r[2] for r in model_rows if r[6] is not None]
            if len(ms) >= _MIN_SAMPLES:
                mic = compute_composite_ic(ms, mr, mc)
                micir = compute_icir(ms, mr, mc, min_samples=_MIN_SAMPLES)
                by_model[mid] = {
                    "ic_24h": mic.composite_ic,
                    "icir_24h": micir.icir,
                    "sample_count": len(ms),
                }
            else:
                by_model[mid] = {"ic_24h": None, "icir_24h": None, "sample_count": len(ms)}

        return BacktestReport(
            run_id=run_id,
            total_signals=total,
            signals_with_returns=signals_with_returns,
            ic_1h=ic_1h,
            ic_4h=ic_4h,
            ic_24h=ic_24h,
            icir_1h=icir_1h,
            icir_4h=icir_4h,
            icir_24h=icir_24h,
            by_model=by_model,
        )
