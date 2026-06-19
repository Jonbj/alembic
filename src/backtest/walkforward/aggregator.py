"""Walk-forward aggregator: combine per-window OOS results into aggregate metrics."""
from __future__ import annotations

import logging
import statistics
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from src.backtest.walkforward.runner import WindowResult

log = logging.getLogger(__name__)


class WalkForwardAggregator:
    """Combine OOS results from all walk-forward windows."""

    def aggregate(self, windows: list[WindowResult]) -> dict:
        """Compute cross-window statistics from OOS metrics.

        Returns aggregate dict with:
        - per_window: list of per-window metric dicts
        - mean_sharpe, median_sharpe, std_sharpe
        - mean_annualized_return, mean_max_drawdown
        - pct_windows_positive: fraction of windows with positive return
        - n_windows: total number of windows
        - oos_nav_series: concatenated OOS NAV as pd.Series (index=timestamp)
        """
        if not windows:
            return {"n_windows": 0, "error": "no_windows"}

        valid = [w for w in windows if "error" not in w.oos_metrics]
        if not valid:
            return {"n_windows": len(windows), "error": "all_windows_insufficient_data"}

        per_window = [
            {
                "window_idx": w.window_idx,
                "oos_start": w.oos_start.date().isoformat(),
                "oos_end": w.oos_end.date().isoformat(),
                **w.oos_metrics,
            }
            for w in valid
        ]

        sharpes = [m["sharpe"] for m in per_window]
        ann_rets = [m["annualized_return"] for m in per_window]
        drawdowns = [m["max_drawdown"] for m in per_window]

        pct_positive = sum(1 for r in ann_rets if r > 0) / len(ann_rets)

        is_sharpes = [w.is_sharpe for w in valid]
        mean_is_sharpe = round(statistics.mean(is_sharpes), 4) if is_sharpes else 0.0
        mean_oos_sharpe = round(statistics.mean(sharpes), 4)
        if mean_is_sharpe != 0.0:
            is_oos_degradation_ratio: float | None = round(mean_oos_sharpe / mean_is_sharpe, 4)
        else:
            is_oos_degradation_ratio = None

        agg: dict = {
            "n_windows": len(windows),
            "n_valid_windows": len(valid),
            "mean_sharpe": mean_oos_sharpe,
            "median_sharpe": round(statistics.median(sharpes), 4),
            "std_sharpe": round(statistics.stdev(sharpes) if len(sharpes) > 1 else 0.0, 4),
            "mean_annualized_return": round(statistics.mean(ann_rets), 4),
            "mean_max_drawdown": round(statistics.mean(drawdowns), 4),
            "worst_drawdown": round(min(drawdowns), 4),
            "pct_windows_positive": round(pct_positive, 4),
            "mean_is_sharpe": mean_is_sharpe,
            "is_oos_degradation_ratio": is_oos_degradation_ratio,
            "per_window": per_window,
        }

        # Concatenated OOS NAV series (non-overlapping OOS windows only)
        agg["oos_nav_series"] = self._concat_oos_nav(valid)

        return agg

    def _concat_oos_nav(self, windows: list[WindowResult]) -> pd.Series:
        """Concatenate OOS snapshots from each window into a single NAV series.

        Uses only the OOS portion of each window (snapshots >= oos_start).
        Windows are sorted by oos_start so the series is chronological.
        """
        sorted_windows = sorted(windows, key=lambda w: w.oos_start)
        pieces: list[pd.Series] = []

        for w in sorted_windows:
            oos_snaps = [s for s in w.oos_result.snapshots if s.timestamp >= w.oos_start]
            if not oos_snaps:
                continue
            piece = pd.Series(
                data=[s.total_nav for s in oos_snaps],
                index=[s.timestamp for s in oos_snaps],
            )
            pieces.append(piece)

        if not pieces:
            return pd.Series(dtype=float)

        combined = pd.concat(pieces)
        combined = combined[~combined.index.duplicated(keep="last")]
        return combined.sort_index()
