"""DecayMonitor: walk-forward performance comparison against backtest baselines.

Monthly job that compares recent strategy performance (IC, hit rate, Sharpe,
max drawdown) against baseline metrics established during backtesting. Produces a
decay score (0–1) and fires alerts when actual performance degrades beyond
configurable thresholds.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np


class DecayLevel(str, enum.Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class DecayMetric:
    """Per-metric decay result."""
    metric: str           # ic, hit_rate, sharpe, max_drawdown
    baseline: float
    actual: float
    decay_score: float    # 0 (no decay) to 1 (total decay)
    level: DecayLevel
    note: str = ""


@dataclass
class DecayReport:
    """Full decay assessment for one strategy."""
    timestamp: datetime
    strategy_id: str
    metrics: list[DecayMetric] = field(default_factory=list)
    overall_decay_score: float = 0.0
    overall_level: DecayLevel = DecayLevel.NORMAL
    alerts: list[str] = field(default_factory=list)


# ── Thresholds ────────────────────────────────────────────────────────────────

_IC_DROP_THRESHOLD = 0.50          # IC drops >50% from baseline → WARNING
_HIT_RATE_DROP_THRESHOLD = 0.15   # Hit rate drops >15pp → WARNING
_SHARPE_HALF_THRESHOLD = 0.50     # Sharpe below half of baseline → WARNING
_DRAWDOWN_EXCESS_THRESHOLD = 0.05 # MaxDD exceeds baseline by >5pp → WARNING

_DECAY_WARNING = 0.5
_DECAY_CRITICAL = 0.8


def _ic_decay_score(baseline_ic: float, actual_ic: float) -> float:
    """Compute decay score for IC. Higher = worse.

    If baseline is near zero, any negative actual is full decay.
    """
    if abs(baseline_ic) < 1e-6:
        return 1.0 if actual_ic < 0 else 0.0
    drop = (baseline_ic - actual_ic) / abs(baseline_ic)
    return float(np.clip(drop, 0.0, 1.0))


def _hit_rate_decay_score(baseline_hr: float, actual_hr: float) -> float:
    """Compute decay score for hit rate. Uses absolute pp drop."""
    drop = baseline_hr - actual_hr
    # Normalise: 15pp drop = score 0.5, 30pp = 1.0
    return float(np.clip(drop / 0.30, 0.0, 1.0))


def _sharpe_decay_score(baseline_sharpe: float, actual_sharpe: float) -> float:
    """Compute decay score for Sharpe. Below half of baseline = concerning."""
    if abs(baseline_sharpe) < 1e-6:
        return 1.0 if actual_sharpe < 0 else 0.0
    ratio = actual_sharpe / baseline_sharpe
    # ratio >= 1.0 → 0 decay, ratio 0.5 → 0.5 decay, ratio 0 → 1.0 decay
    return float(np.clip(1.0 - ratio, 0.0, 1.0))


def _drawdown_decay_score(baseline_dd: float, actual_dd: float) -> float:
    """Compute decay score for max drawdown. More DD = worse."""
    if baseline_dd < 1e-6:
        # No baseline drawdown, any actual DD is concerning
        return float(np.clip(actual_dd / 0.10, 0.0, 1.0))
    excess = actual_dd - baseline_dd
    return float(np.clip(excess / 0.10, 0.0, 1.0))


class DecayMonitor:
    """Compare recent strategy performance against backtest baselines.

    Args:
        baselines: Dict of strategy_id → {metric: value} baseline metrics.
            Example: {"S1": {"ic": 0.05, "hit_rate": 0.55, "sharpe": 1.2, "max_drawdown": 0.08}}
    """

    def __init__(self, baselines: dict[str, dict[str, float]]) -> None:
        self._baselines = baselines

    def compute_report(
        self,
        strategy_id: str,
        actual_metrics: dict[str, float],
    ) -> DecayReport:
        """Compute decay report for a single strategy.

        Args:
            strategy_id: Strategy identifier (e.g. "S1").
            actual_metrics: Current measured metrics {ic, hit_rate, sharpe, max_drawdown}.

        Returns:
            DecayReport with per-metric scores and overall assessment.
        """
        baseline = self._baselines.get(strategy_id, {})
        metrics: list[DecayMetric] = []
        alerts: list[str] = []

        # IC
        b_ic = baseline.get("ic", 0.0)
        a_ic = actual_metrics.get("ic", 0.0)
        ic_score = _ic_decay_score(b_ic, a_ic)
        ic_level = self._level_from_score(ic_score)
        if a_ic < b_ic * (1 - _IC_DROP_THRESHOLD) and b_ic > 0:
            alerts.append(
                f"IC dropped {(1 - a_ic / b_ic) * 100:.0f}% from {b_ic:.3f} to {a_ic:.3f}"
            )
        metrics.append(DecayMetric(
            metric="ic", baseline=b_ic, actual=a_ic,
            decay_score=ic_score, level=ic_level,
        ))

        # Hit rate
        b_hr = baseline.get("hit_rate", 0.5)
        a_hr = actual_metrics.get("hit_rate", 0.5)
        hr_score = _hit_rate_decay_score(b_hr, a_hr)
        hr_level = self._level_from_score(hr_score)
        if b_hr - a_hr > _HIT_RATE_DROP_THRESHOLD:
            alerts.append(
                f"Hit rate dropped {(b_hr - a_hr) * 100:.1f}pp from {b_hr:.1%} to {a_hr:.1%}"
            )
        metrics.append(DecayMetric(
            metric="hit_rate", baseline=b_hr, actual=a_hr,
            decay_score=hr_score, level=hr_level,
        ))

        # Sharpe
        b_sharpe = baseline.get("sharpe", 0.0)
        a_sharpe = actual_metrics.get("sharpe", 0.0)
        sharpe_score = _sharpe_decay_score(b_sharpe, a_sharpe)
        sharpe_level = self._level_from_score(sharpe_score)
        if b_sharpe > 0 and a_sharpe < b_sharpe * _SHARPE_HALF_THRESHOLD:
            alerts.append(
                f"Sharpe below 50% of baseline: {a_sharpe:.2f} vs {b_sharpe:.2f}"
            )
        metrics.append(DecayMetric(
            metric="sharpe", baseline=b_sharpe, actual=a_sharpe,
            decay_score=sharpe_score, level=sharpe_level,
        ))

        # Max drawdown
        b_dd = baseline.get("max_drawdown", 0.0)
        a_dd = actual_metrics.get("max_drawdown", 0.0)
        dd_score = _drawdown_decay_score(b_dd, a_dd)
        dd_level = self._level_from_score(dd_score)
        if a_dd > b_dd + _DRAWDOWN_EXCESS_THRESHOLD:
            alerts.append(
                f"Max drawdown exceeds baseline by {(a_dd - b_dd) * 100:.1f}pp: {a_dd:.1%} vs {b_dd:.1%}"
            )
        metrics.append(DecayMetric(
            metric="max_drawdown", baseline=b_dd, actual=a_dd,
            decay_score=dd_score, level=dd_level,
        ))

        # Overall score = max of per-metric scores
        overall_score = max(m.decay_score for m in metrics) if metrics else 0.0
        overall_level = self._level_from_score(overall_score)

        return DecayReport(
            timestamp=datetime.now(timezone.utc),
            strategy_id=strategy_id,
            metrics=metrics,
            overall_decay_score=overall_score,
            overall_level=overall_level,
            alerts=alerts,
        )

    @staticmethod
    def _level_from_score(score: float) -> DecayLevel:
        if score >= _DECAY_CRITICAL:
            return DecayLevel.CRITICAL
        if score >= _DECAY_WARNING:
            return DecayLevel.WARNING
        return DecayLevel.NORMAL