"""PerformanceWorker Celery tasks for LLM Trading System.

Implements:
- run_daily_report: Daily IC report with Telegram alert
- run_weekly_weights: Weekly LOO ICIR weight computation (observational in Fase 1)
- run_drift_detection: Weekly PSI + CUSUM drift detection
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np
import psycopg2

from src.config import config
from src.models.performance import PerformanceReport, PostMortem
from src.notifications.telegram import TelegramNotifier
from src.performance.drift import (
    CircuitBreakerContext,
    check_circuit_breakers,
    detect_drift,
    DriftAlert,
)
from src.performance.ic import compute_composite_ic, compute_icir
from src.performance.postmortem import diagnose_loss, should_trigger_postmortem, TradeContext
from src.performance.weights import compute_new_weights, compute_purified_icir
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

# Minimum samples required for meaningful IC computation
_MIN_SAMPLES = 300
_MIN_SAMPLES_PER_MODEL = 30


def _fetch_all_signals_for_ic(
    pg: PostgreSQLStore,
    days: int,
) -> list[tuple]:
    """Fetch all signals across all symbols for IC calculation.

    Returns list of (score, confidence, forward_return, generated_at, model_id, fallback_used) tuples.
    """
    # We need to fetch signals for each symbol separately
    # For now, fetch from a representative set of symbols
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"]
    all_rows = []

    for symbol in symbols:
        rows = pg.fetch_signals_for_ic(symbol, days)
        all_rows.extend(rows)

    return all_rows


def _compute_model_metrics(
    rows: list[tuple],
) -> tuple[dict[str, list[float]], dict[str, list[float]], dict[str, list[float]]]:
    """Group signals by model and compute per-model metrics.

    Returns:
        Tuple of (model_signals, model_returns, model_confs) dictionaries
    """
    by_model_signals: dict[str, list[float]] = defaultdict(list)
    by_model_returns: dict[str, list[float]] = defaultdict(list)
    by_model_confs: dict[str, list[float]] = defaultdict(list)

    for score, conf, fwd_ret, _, model_id, fallback in rows:
        if fwd_ret is None or fallback:
            continue
        by_model_signals[model_id].append(score)
        by_model_returns[model_id].append(fwd_ret)
        by_model_confs[model_id].append(conf)

    return dict(by_model_signals), dict(by_model_returns), dict(by_model_confs)


def build_performance_report(
    pg: PostgreSQLStore,
    current_weights: dict[str, float],
    period_days: int = 30,
    report_version: str = "1.0",
) -> PerformanceReport:
    """Build a PerformanceReport from PostgreSQL signal + outcome data.

    Args:
        pg: PostgreSQL store instance
        current_weights: Current ensemble weights
        period_days: Number of days to look back
        report_version: Report schema version

    Returns:
        PerformanceReport with all metrics and recommendations
    """
    # Fetch signals
    rows = _fetch_all_signals_for_ic(pg, period_days)

    # Filter out fallback rows and rows without forward return
    rows = [(s, c, r, d, m, f) for (s, c, r, d, m, f) in rows if r is not None and not f]

    today = date.today()
    period_start = date.fromordinal(today.toordinal() - period_days)

    # Check minimum samples
    if len(rows) < _MIN_SAMPLES:
        log.info(f"Insufficient samples for performance report: {len(rows)} < {_MIN_SAMPLES}")
        return PerformanceReport(
            period_start=period_start,
            period_end=today,
            overall_ic=0.0,
            icir=0.0,
            hit_rate=0.0,
            model_ic={m: 0.0 for m in current_weights},
            model_icir={m: 0.0 for m in current_weights},
            recommended_weights=current_weights,
            weight_change_applied=False,
            threshold_analysis={},
            threshold_suggestion=None,
            drift_alerts=[],
            post_mortems=[],
            generated_at=datetime.now(timezone.utc),
            report_version=report_version,
        )

    # Extract scores and returns
    all_scores = [r[0] for r in rows]
    all_confs = [r[1] for r in rows]
    all_returns = [r[2] for r in rows]

    # Compute overall IC and ICIR
    ic_result = compute_composite_ic(all_scores, all_returns, all_confs)
    overall_ic = ic_result.composite_ic

    icir_result = compute_icir(all_scores, all_returns, all_confs, min_samples=30)
    icir = icir_result.icir

    # Hit rate: percentage of signals with correct sign
    hit_rate = float(np.mean([np.sign(s) == np.sign(r) for s, r in zip(all_scores, all_returns)]))

    # Per-model IC/ICIR
    model_signals, model_returns, model_confs = _compute_model_metrics(rows)

    model_ic: dict[str, float] = {}
    model_icir: dict[str, float] = {}

    for model in current_weights.keys():
        ms = model_signals.get(model, [])
        mr = model_returns.get(model, [])
        mc = model_confs.get(model, [])

        if len(ms) >= _MIN_SAMPLES_PER_MODEL:
            mic = compute_composite_ic(ms, mr, mc)
            micir = compute_icir(ms, mr, mc, min_samples=10)
            model_ic[model] = mic.composite_ic
            model_icir[model] = micir.icir
        else:
            model_ic[model] = 0.0
            model_icir[model] = 0.0

    # Threshold analysis - simple bucket IC comparison
    threshold_analysis = _compute_bucket_ic(all_scores, all_returns, all_confs)
    threshold_suggestion = _suggest_threshold(threshold_analysis, current_threshold=0.3)

    return PerformanceReport(
        period_start=period_start,
        period_end=today,
        overall_ic=overall_ic,
        icir=icir,
        hit_rate=hit_rate,
        model_ic=model_ic,
        model_icir=model_icir,
        recommended_weights=current_weights,  # Fase 1: no auto-update
        weight_change_applied=False,
        threshold_analysis=threshold_analysis,
        threshold_suggestion=threshold_suggestion,
        drift_alerts=[],  # Populated by drift detection task
        post_mortems=[],  # Populated by event-driven task
        generated_at=datetime.now(timezone.utc),
        report_version=report_version,
    )


def _compute_bucket_ic(
    scores: list[float],
    returns: list[float],
    confidences: list[float],
) -> dict[str, float]:
    """Compute IC per score bucket for threshold analysis."""
    buckets = {
        "0.1-0.2": [],
        "0.2-0.3": [],
        "0.3-0.4": [],
        "0.4-0.6": [],
        "0.6-1.0": [],
    }

    for s, r, c in zip(scores, returns, confidences):
        abs_s = abs(s)
        if 0.1 <= abs_s < 0.2:
            buckets["0.1-0.2"].append((s, r, c))
        elif 0.2 <= abs_s < 0.3:
            buckets["0.2-0.3"].append((s, r, c))
        elif 0.3 <= abs_s < 0.4:
            buckets["0.3-0.4"].append((s, r, c))
        elif 0.4 <= abs_s < 0.6:
            buckets["0.4-0.6"].append((s, r, c))
        elif 0.6 <= abs_s <= 1.0:
            buckets["0.6-1.0"].append((s, r, c))

    result = {}
    for bucket_name, items in buckets.items():
        if len(items) >= 20:
            bs = [x[0] for x in items]
            br = [x[1] for x in items]
            bc = [x[2] for x in items]
            ic = compute_composite_ic(bs, br, bc)
            result[bucket_name] = ic.composite_ic
        else:
            result[bucket_name] = 0.0

    return result


def _suggest_threshold(
    bucket_ic: dict[str, float],
    current_threshold: float = 0.3,
    improvement_threshold: float = 0.15,
) -> float | None:
    """Suggest a new threshold if a stricter bucket has significantly better IC.

    Args:
        bucket_ic: IC per bucket
        current_threshold: Current entry threshold
        improvement_threshold: Required relative improvement (15%)

    Returns:
        Suggested new threshold or None if no improvement found
    """
    # Find current bucket IC
    current_bucket = None
    for bucket_name in ["0.2-0.3", "0.3-0.4"]:
        if current_bucket is None and bucket_name in bucket_ic:
            current_bucket = bucket_name

    if current_bucket is None or current_bucket not in bucket_ic:
        return None

    current_ic = bucket_ic[current_bucket]

    # Check stricter buckets
    stricter_buckets = ["0.4-0.6", "0.6-1.0"]
    for bucket_name in stricter_buckets:
        if bucket_name not in bucket_ic:
            continue
        candidate_ic = bucket_ic[bucket_name]
        if current_ic > 0 and candidate_ic > current_ic * (1.0 + improvement_threshold):
            # Suggest the lower bound of this bucket
            suggested = float(bucket_name.split("-")[0])
            return suggested

    return None


@app.task(name="src.workers.performance.run_daily_report")
def run_daily_report():
    """Daily performance report task.

    Computes IC metrics over the last 30 days and sends a Telegram alert
    with the performance summary.
    """
    log.info("Starting daily performance report...")

    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights from Redis
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33}

        # Build report
        report = build_performance_report(pg, current_weights, period_days=30)

        # Store report in Redis for API access
        redis._r.setex("performance:latest_report", 86400 * 7, report.model_dump_json())

        # Update consecutive_negative_ic_streak based on daily IC
        current_streak = int(redis._r.get("performance:neg_ic_streak") or 0)
        if report.overall_ic < 0:
            current_streak += 1
        else:
            current_streak = 0
        redis._r.setex("performance:neg_ic_streak", 86400 * 30, str(current_streak))

        # Build market context for soft warnings
        ctx = CircuitBreakerContext(
            vix=float(redis._r.get("market:vix") or 20.0),
            vix_1d_change=0.0,
            portfolio_drawdown=float(redis._r.get("portfolio:drawdown") or 0.0),
            consecutive_negative_ic_days=current_streak,
            portfolio_earnings_pct=float(redis._r.get("portfolio:earnings_pct") or 0.0),
            cross_asset_correlation=float(redis._r.get("market:cross_corr") or 0.5),
        )

        # Check circuit breakers for soft warnings
        cb_result = check_circuit_breakers(ctx)

        # Send Telegram alert
        notifier = TelegramNotifier()
        message = _format_performance_telegram_message(report, cb_result.soft_warnings_triggered)
        asyncio.run(notifier.send_alert(message, level="info"))

        log.info(f"Daily report sent. Overall IC: {report.overall_ic:.4f}, ICIR: {report.icir:.3f}")

    except Exception as e:
        log.exception(f"Daily performance report failed: {e}")
        raise


@app.task(name="src.workers.performance.run_weekly_weights")
def run_weekly_weights():
    """Weekly weight computation task (Fase 1: observational only).

    Computes Leave-One-Out ICIR for each model and suggests new weights.
    In Fase 1, weights are NOT auto-applied - only reported as suggestions.
    """
    log.info("Starting weekly weight computation (observational)...")

    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33}

        # Fetch signals for LOO ICIR computation
        rows = _fetch_all_signals_for_ic(pg, days=30)
        rows = [(s, c, r, d, m, f) for (s, c, r, d, m, f) in rows if r is not None and not f]

        if len(rows) < _MIN_SAMPLES:
            log.info(f"Insufficient samples for weight update: {len(rows)} < {_MIN_SAMPLES}")
            return

        # Group by model
        model_signals, model_returns, _ = _compute_model_metrics(rows)
        all_returns = [r[2] for r in rows]

        if len(model_signals) < 2:
            log.warning("Not enough models for LOO ICIR computation")
            return

        # Compute purified ICIR (Leave-One-Out)
        purified_icir = compute_purified_icir(
            model_signals=model_signals,
            forward_returns=all_returns,
            current_weights=current_weights,
            window_size=30,
            step_size=5,
        )

        # Compute new weights with smoothing and guardrails
        new_weights = compute_new_weights(purified_icir, current_weights)

        # Build market context for circuit breaker check
        ctx = CircuitBreakerContext(
            vix=float(redis._r.get("market:vix") or 20.0),
            vix_1d_change=0.0,
            portfolio_drawdown=float(redis._r.get("portfolio:drawdown") or 0.0),
            consecutive_negative_ic_days=int(redis._r.get("performance:neg_ic_streak") or 0),
            portfolio_earnings_pct=float(redis._r.get("portfolio:earnings_pct") or 0.0),
            cross_asset_correlation=float(redis._r.get("market:cross_corr") or 0.5),
        )

        cb_result = check_circuit_breakers(ctx)
        freeze_reason = cb_result.reason if cb_result.freeze_weight_update else ""

        # Fase 1: OBSERVATIONAL - store as suggestion, do NOT auto-apply
        suggestion = {
            "suggested_weights": new_weights,
            "purified_icir": purified_icir,
            "freeze_reason": freeze_reason,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

        redis._r.setex(
            "ensemble:weights:suggestion",
            86400 * 7,  # 7 day TTL
            json.dumps(suggestion),
        )

        # Send Telegram alert with suggestions
        notifier = TelegramNotifier()
        message = _format_weights_telegram_message(new_weights, current_weights, freeze_reason)
        asyncio.run(notifier.send_alert(message, level="info"))

        log.info(f"Weekly weights computed. Suggestion stored in Redis.")

    except Exception as e:
        log.exception(f"Weekly weight computation failed: {e}")
        raise


@app.task(name="src.workers.performance.run_drift_detection")
def run_drift_detection():
    """Weekly drift detection task.

    Computes PSI and CUSUM for each model's score distribution comparing:
    - Last 7 days vs 90-day baseline (primary)
    - Last 7 days vs 12-month baseline (secondary)

    Sends Telegram alert if drift is detected (YELLOW or RED level).
    """
    log.info("Starting weekly drift detection...")

    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Fetch signals for different time windows
        rows_7d = _fetch_all_signals_for_ic(pg, days=7)
        rows_90d = _fetch_all_signals_for_ic(pg, days=90)
        rows_12m = _fetch_all_signals_for_ic(pg, days=365)

        # Group by model
        def group_by_model(rows):
            by_model: dict[str, list[float]] = defaultdict(list)
            for score, _, _, _, model_id, _ in rows:
                if score is not None:
                    by_model[model_id].append(score)
            return dict(by_model)

        signals_7d = group_by_model(rows_7d)
        signals_90d = group_by_model(rows_90d)
        signals_12m = group_by_model(rows_12m)

        alerts = []

        for model in signals_7d.keys():
            if model not in signals_90d:
                continue

            current = np.array(signals_7d[model])
            baseline_90d = np.array(signals_90d[model])
            baseline_12m = np.array(signals_12m.get(model, []))

            if len(current) < 7 or len(baseline_90d) < 30:
                log.debug(f"Insufficient data for drift detection on {model}")
                continue

            # Run drift detection
            drift_alert = detect_drift(
                baseline_90gg=baseline_90d,
                baseline_12m=baseline_12m if len(baseline_12m) > 0 else None,
                current_7gg=current,
                cusum_threshold=8.0,
            )

            if drift_alert.level in ("yellow", "red"):
                alerts.append(
                    f"{drift_alert.level.upper()}: {model} "
                    f"(PSI_90d={drift_alert.psi_90gg:.3f}, "
                    f"mean_shift: {drift_alert.baseline_mean:.3f} -> {drift_alert.current_mean:.3f})"
                )

                # Store drift alert in Redis
                redis._r.setex(
                    f"drift:alert:{model}",
                    86400 * 7,
                    json.dumps({
                        "level": drift_alert.level,
                        "psi_90d": drift_alert.psi_90gg,
                        "psi_12m": drift_alert.psi_12m,
                        "cusum_value": drift_alert.cusum_value,
                        "cusum_threshold": drift_alert.cusum_threshold,
                        "detected_at": datetime.now(timezone.utc).isoformat(),
                    }),
                )

        if alerts:
            notifier = TelegramNotifier()
            message = "Drift Detection Alert\n\n" + "\n".join(alerts)
            level = "critical" if any("RED" in a for a in alerts) else "warning"
            asyncio.run(notifier.send_alert(message, level=level))
            log.warning(f"Drift alerts sent: {len(alerts)}")
        else:
            log.info("No drift detected.")

    except Exception as e:
        log.exception(f"Drift detection failed: {e}")
        raise


def _format_performance_telegram_message(
    report: PerformanceReport,
    soft_warnings: list[str],
) -> str:
    """Format performance report for Telegram message."""
    lines = [
        "Performance Report",
        f"Period: {report.period_start} to {report.period_end}",
        "",
        "Metrics:",
        f"  Composite IC: {report.overall_ic:.4f}",
        f"  ICIR: {report.icir:.3f}",
        f"  Hit Rate: {report.hit_rate:.1%}",
        "",
        "Model IC:",
    ]

    for model in sorted(report.model_ic.keys(), key=lambda m: -report.model_ic.get(m, 0)):
        ic = report.model_ic.get(model, 0)
        icir = report.model_icir.get(model, 0)
        weight = report.recommended_weights.get(model, 0)
        trend = "+" if ic > report.overall_ic else "-" if ic < report.overall_ic * 0.8 else "~"
        lines.append(f"  {model}: IC={ic:.3f} ({trend}) ICIR={icir:.2f} weight={weight:.0%}")

    if report.threshold_suggestion:
        lines.append("")
        lines.append(f"Threshold suggestion: {report.threshold_suggestion:.2f} (vs current 0.30)")

    if soft_warnings:
        lines.append("")
        lines.append("Soft warnings:")
        for w in soft_warnings:
            lines.append(f"  - {w}")

    return "\n".join(lines)


def _format_weights_telegram_message(
    new_weights: dict[str, float],
    current_weights: dict[str, float],
    freeze_reason: str,
) -> str:
    """Format weight suggestions for Telegram message."""
    lines = [
        "Weekly Weight Suggestions (Observational)",
        "",
        "Current -> Suggested:",
    ]

    for model in sorted(new_weights.keys()):
        old_w = current_weights.get(model, 0)
        new_w = new_weights.get(model, 0)
        delta = new_w - old_w
        delta_str = f"{delta:+.1%}" if abs(delta) > 0.001 else "no change"
        lines.append(f"  {model}: {old_w:.0%} -> {new_w:.0%} ({delta_str})")

    if freeze_reason:
        lines.append("")
        lines.append(f"Circuit breaker active: {freeze_reason}")
        lines.append("Weight update frozen - manual approval required")

    lines.append("")
    lines.append("Note: Fase 1 = observational only (no auto-update)")

    return "\n".join(lines)
