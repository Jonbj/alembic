"""PortfolioRiskMonitor: per-strategy and combined risk metrics with alert thresholds."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np


class AlertLevel(str, enum.Enum):
    WARNING = "WARNING"
    ALERT = "ALERT"
    CRITICAL = "CRITICAL"


@dataclass
class Alert:
    level: AlertLevel
    message: str
    strategy_id: Optional[str] = None


@dataclass
class StrategyRiskMetrics:
    strategy_id: str
    daily_pnl: float
    drawdown: float        # max drawdown fraction (non-negative)
    sharpe: float
    volatility: float      # rolling 60d EWMA annualised vol
    current_weight: float
    target_weight: float


@dataclass
class RiskReport:
    timestamp: datetime
    nav: float
    total_exposure: float
    herfindahl_index: float | None
    combined_drawdown: float
    per_strategy_metrics: dict[str, StrategyRiskMetrics]
    strategy_correlations: dict[str, float]   # "S1:S2" → correlation
    alerts: list[Alert]


# ── Thresholds ────────────────────────────────────────────────────────────────

_STRATEGY_DRAWDOWN_ALERT = 0.10      # >10% drawdown per strategy → ALERT
_COMBINED_DRAWDOWN_CRITICAL = 0.15   # >15% combined drawdown → CRITICAL
_WEIGHT_DRIFT_WARNING = 0.05         # >5% drift from target → WARNING
_CORRELATION_WARNING = 0.80          # correlation >0.80 → WARNING
_TOTAL_EXPOSURE_ALERT = 0.50         # >50% total exposure → ALERT

_TRADING_DAYS_PER_YEAR = 252


class _UseCurrentWeights:
    """Sentinel distinguishing an omitted HHI override from unavailable data."""


_USE_CURRENT_WEIGHTS = _UseCurrentWeights()


def _compute_drawdown(returns: list[float]) -> float:
    """Compute max drawdown over the full series (non-negative fraction)."""
    if not returns:
        return 0.0
    cumulative = np.cumprod([1.0 + r for r in returns])
    peak = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - peak) / peak
    return float(-np.min(drawdowns))


def max_drawdown_from_equity(equity_curve: list[float]) -> float:
    """Peak-to-trough max drawdown of an equity LEVEL series (non-negative fraction).

    Distinct from _compute_drawdown, which consumes a *returns* series. This
    feeds the CRITICAL portfolio-drawdown alert (#107), so it must reflect real
    account equity, not trade-notional returns. Non-positive points are ignored;
    fewer than two usable points → 0.0 (fail-safe: no drawdown asserted).
    """
    levels = [e for e in equity_curve if e and e > 0]
    if len(levels) < 2:
        return 0.0
    peak = levels[0]
    max_dd = 0.0
    for e in levels:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd
    return float(max_dd)


def _ewma_volatility(returns: list[float], span: int = 60) -> float:
    """Annualised EWMA volatility with given span."""
    if len(returns) < 2:
        return 0.0
    alpha = 2.0 / (span + 1)
    variance = float(np.var(returns[:2]))
    for r in returns[2:]:
        variance = alpha * r ** 2 + (1 - alpha) * variance
    return float(np.sqrt(variance * _TRADING_DAYS_PER_YEAR))


def _compute_sharpe(returns: list[float]) -> float:
    """Annualised Sharpe assuming zero risk-free rate."""
    if len(returns) < 2:
        return 0.0
    arr = np.array(returns, dtype=float)
    std = float(np.std(arr))
    if std == 0.0:
        return 0.0
    return float(np.mean(arr) / std * np.sqrt(_TRADING_DAYS_PER_YEAR))


def _herfindahl(weights: dict[str, float]) -> float:
    """Herfindahl-Hirschman Index for concentration."""
    total = sum(weights.values())
    if total == 0.0:
        return 0.0
    return float(sum((w / total) ** 2 for w in weights.values()))


def _combined_returns(
    strategy_returns: dict[str, list[float]],
    weights: dict[str, float],
) -> list[float]:
    """Weighted sum of per-strategy returns → combined daily returns."""
    if not strategy_returns:
        return []
    n = min(len(v) for v in strategy_returns.values())
    combined = []
    for i in range(n):
        day_ret = sum(
            weights.get(sid, 0.0) * rets[i]
            for sid, rets in strategy_returns.items()
        )
        combined.append(day_ret)
    return combined


class PortfolioRiskMonitor:
    """Compute per-strategy and combined portfolio risk metrics and fire alerts.

    Args:
        target_weights: Target allocation per strategy_id (fractions summing to ≤1).
    """

    def __init__(self, target_weights: dict[str, float]) -> None:
        self._target_weights = target_weights

    def compute_report(
        self,
        strategy_returns: dict[str, list[float]],
        current_weights: dict[str, float],
        total_exposure: float,
        nav: float,
        combined_drawdown_override: float | None = None,
        herfindahl_override: float | None | _UseCurrentWeights = _USE_CURRENT_WEIGHTS,
    ) -> RiskReport:
        """Compute full risk report.

        Args:
            strategy_returns: Per-strategy list of daily returns (most recent last).
            current_weights:  Current allocation fractions per strategy_id.
            total_exposure:   Combined portfolio exposure as fraction of NAV.
            nav:              Net asset value.

        Returns:
            RiskReport with metrics and alerts.
        """
        per_strategy: dict[str, StrategyRiskMetrics] = {}

        for sid, rets in strategy_returns.items():
            weight = current_weights.get(sid, 0.0)
            target = self._target_weights.get(sid, 0.0)
            daily_pnl = float(rets[-1] * nav * weight) if rets else 0.0
            per_strategy[sid] = StrategyRiskMetrics(
                strategy_id=sid,
                daily_pnl=daily_pnl,
                drawdown=_compute_drawdown(rets),
                sharpe=_compute_sharpe(rets),
                volatility=_ewma_volatility(rets),
                current_weight=weight,
                target_weight=target,
            )

        hhi: float | None
        if isinstance(herfindahl_override, _UseCurrentWeights):
            hhi = _herfindahl(current_weights)
        else:
            # Explicit None means that the upstream measurement failed. This is
            # distinct from an omitted override, which retains the legacy
            # calculation from current_weights.
            hhi = herfindahl_override

        if combined_drawdown_override is not None:
            combined_dd = combined_drawdown_override
        else:
            combined_rets = _combined_returns(strategy_returns, current_weights)
            combined_dd = _compute_drawdown(combined_rets)

        # Pairwise correlations
        strategy_correlations: dict[str, float] = {}
        ids = list(strategy_returns.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                ra = np.array(strategy_returns[a])
                rb = np.array(strategy_returns[b])
                n = min(len(ra), len(rb))
                if n < 2:
                    corr = 0.0
                else:
                    corr = float(np.corrcoef(ra[:n], rb[:n])[0, 1])
                    if np.isnan(corr):
                        corr = 0.0
                strategy_correlations[f"{a}:{b}"] = corr

        alerts = self._check_alerts(
            per_strategy, combined_dd, current_weights, total_exposure, strategy_correlations
        )

        return RiskReport(
            timestamp=datetime.now(timezone.utc),
            nav=nav,
            total_exposure=total_exposure,
            herfindahl_index=hhi,
            combined_drawdown=combined_dd,
            per_strategy_metrics=per_strategy,
            strategy_correlations=strategy_correlations,
            alerts=alerts,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _check_alerts(
        self,
        per_strategy: dict[str, StrategyRiskMetrics],
        combined_dd: float,
        current_weights: dict[str, float],
        total_exposure: float,
        correlations: dict[str, float],
    ) -> list[Alert]:
        alerts: list[Alert] = []

        # Per-strategy drawdown
        for sid, m in per_strategy.items():
            if m.drawdown > _STRATEGY_DRAWDOWN_ALERT:
                alerts.append(Alert(
                    level=AlertLevel.ALERT,
                    message=f"Strategy {sid} drawdown {m.drawdown:.1%} exceeds {_STRATEGY_DRAWDOWN_ALERT:.0%}",
                    strategy_id=sid,
                ))

        # Combined drawdown
        if combined_dd > _COMBINED_DRAWDOWN_CRITICAL:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                message=f"Combined portfolio drawdown {combined_dd:.1%} exceeds {_COMBINED_DRAWDOWN_CRITICAL:.0%}",
            ))

        # Weight drift
        for sid, cur_w in current_weights.items():
            target_w = self._target_weights.get(sid, 0.0)
            drift = abs(cur_w - target_w)
            if drift > _WEIGHT_DRIFT_WARNING:
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    message=(
                        f"Strategy {sid} weight {cur_w:.1%} drifted {drift:.1%} from target {target_w:.1%}"
                    ),
                    strategy_id=sid,
                ))

        # Correlation
        for pair_key, corr in correlations.items():
            if corr > _CORRELATION_WARNING:
                a, b = pair_key.split(":", 1)
                alerts.append(Alert(
                    level=AlertLevel.WARNING,
                    message=f"Correlation between {a} and {b} is {corr:.2f} (threshold {_CORRELATION_WARNING})",
                ))

        # Total exposure
        if total_exposure > _TOTAL_EXPOSURE_ALERT:
            alerts.append(Alert(
                level=AlertLevel.ALERT,
                message=f"Total portfolio exposure {total_exposure:.1%} exceeds {_TOTAL_EXPOSURE_ALERT:.0%}",
            ))

        return alerts
