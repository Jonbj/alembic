"""BacktestReportBuilder — builds IC/ICIR report from backtest_signals."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.performance.ic import ICIRResult, ICResult, compute_composite_ic, compute_icir

log = logging.getLogger(__name__)

_MIN_SAMPLES = 30

_COUNT_TOTAL = """
    SELECT COUNT(*) FROM backtest_signals WHERE run_id = %s AND score IS NOT NULL
"""

_FETCH_BOUNDS = """
    SELECT MIN(generated_at), MAX(generated_at)
    FROM backtest_signals
    WHERE run_id = %s AND score IS NOT NULL
"""

_FETCH_ROWS = """
    SELECT symbol, model_id, score, confidence, fallback_used,
           forward_return_1h, forward_return_4h, forward_return_24h
    FROM backtest_signals
    WHERE run_id = %s AND score IS NOT NULL
    ORDER BY generated_at
"""


@dataclass
class BacktestReport:
    run_id: str
    period_start: datetime | None
    period_end: datetime | None
    total_signals: int
    signals_with_returns: int
    ic_1h: ICResult | None
    ic_4h: ICResult | None
    ic_24h: ICResult | None
    icir_1h: ICIRResult | None
    icir_4h: ICIRResult | None
    icir_24h: ICIRResult | None
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_symbol: dict[str, dict[str, Any]] = field(default_factory=dict)
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
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "total_signals": self.total_signals,
            "signals_with_returns": self.signals_with_returns,
            "ic_1h": _ic(self.ic_1h),
            "ic_4h": _ic(self.ic_4h),
            "ic_24h": _ic(self.ic_24h),
            "icir_1h": _icir(self.icir_1h),
            "icir_4h": _icir(self.icir_4h),
            "icir_24h": _icir(self.icir_24h),
            "by_model": self.by_model,
            "by_symbol": self.by_symbol,
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
          2. SELECT MIN/MAX generated_at to derive period bounds.
          3. SELECT all scored rows with forward returns (includes symbol column).
          4. For each horizon (1h=idx0, 4h=idx1, 24h=idx2):
             - Filter out rows where return is None or fallback_used=True.
             - If < _MIN_SAMPLES (30), IC/ICIR = None (insufficient data).
             - Else call compute_composite_ic and compute_icir.
          5. Build per-model breakdown at all three horizons.
          6. Build per-symbol 24h IC breakdown (for debugging weak tickers).
          7. signals_with_returns = count of non-fallback rows with at least
             one non-None return across any horizon.
        """
        with self._conn.cursor() as cur:
            cur.execute(_COUNT_TOTAL, (run_id,))
            total = cur.fetchone()[0]

            cur.execute(_FETCH_BOUNDS, (run_id,))
            bounds = cur.fetchone()
            period_start = bounds[0] if bounds else None
            period_end = bounds[1] if bounds else None

            cur.execute(_FETCH_ROWS, (run_id,))
            rows = cur.fetchall()

        # rows columns: symbol, model_id, score, confidence, fallback_used,
        #               forward_return_1h, forward_return_4h, forward_return_24h

        def _extract(horizon_idx: int, filter_rows=None):
            """Extract (scores, returns, confs) for a horizon, skipping None returns.

            Why skip fallback_used?
              See class docstring — FinBERT is a different signal class.
            """
            source = filter_rows if filter_rows is not None else rows
            scores, returns, confs = [], [], []
            for _sym, _model_id, score, conf, fallback, r1h, r4h, r24h in source:
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

        # Count rows that have at least one non-None return (excluding fallback)
        signals_with_returns = sum(
            1 for _s, _m, _sc, _co, fallback, r1h, r4h, r24h in rows
            if not fallback and any(r is not None for r in (r1h, r4h, r24h))
        )

        # Per-model breakdown at all three horizons
        by_model: dict[str, dict] = {}
        for mid in {row[1] for row in rows}:
            model_rows = [r for r in rows if r[1] == mid]
            by_model[mid] = {}
            sample_count_24h = 0
            for h_idx, h_key in enumerate(("1h", "4h", "24h")):
                ms, mr, mc = _extract(h_idx, filter_rows=model_rows)
                if h_idx == 2:
                    sample_count_24h = len(ms)
                if len(ms) >= _MIN_SAMPLES:
                    mic = compute_composite_ic(ms, mr, mc)
                    micir = compute_icir(ms, mr, mc, min_samples=_MIN_SAMPLES)
                    by_model[mid][f"ic_{h_key}"] = mic.composite_ic
                    by_model[mid][f"icir_{h_key}"] = micir.icir
                else:
                    by_model[mid][f"ic_{h_key}"] = None
                    by_model[mid][f"icir_{h_key}"] = None
            by_model[mid]["sample_count"] = sample_count_24h

        # Per-symbol 24h IC (for debugging weak tickers)
        by_symbol: dict[str, dict] = {}
        for sym in {row[0] for row in rows}:
            sym_rows = [r for r in rows if r[0] == sym]
            ss, sr, sc = _extract(2, filter_rows=sym_rows)
            if len(ss) >= _MIN_SAMPLES:
                sic = compute_composite_ic(ss, sr, sc)
                sicir = compute_icir(ss, sr, sc, min_samples=_MIN_SAMPLES)
                by_symbol[sym] = {
                    "ic_24h": sic.composite_ic,
                    "icir_24h": sicir.icir,
                    "sample_count": len(ss),
                }
            else:
                by_symbol[sym] = {"ic_24h": None, "icir_24h": None, "sample_count": len(ss)}

        return BacktestReport(
            run_id=run_id,
            period_start=period_start,
            period_end=period_end,
            total_signals=total,
            signals_with_returns=signals_with_returns,
            ic_1h=ic_1h,
            ic_4h=ic_4h,
            ic_24h=ic_24h,
            icir_1h=icir_1h,
            icir_4h=icir_4h,
            icir_24h=icir_24h,
            by_model=by_model,
            by_symbol=by_symbol,
        )
