"""PerformanceWorker Celery tasks for LLM Trading System.

Implements five Celery tasks, all scheduled via celery_app.py beat schedule:

- run_daily_report (03:00 UTC daily):
    Composite IC + ICIR over last 30 days. Sends Telegram performance report.
    Stores PerformanceReport JSON in Redis for GET /api/performance/latest.

- run_weekly_weights (Monday 04:00 UTC):
    LOO ICIR computation → compute_new_weights() with smoothing + guardrails.
    Stores suggestion in Redis. Triggers check_and_apply_weights after 5s.

- run_drift_detection (Sunday 04:30 UTC):
    PSI + CUSUM drift detection per model comparing 7d vs 90d/12m baselines.
    Sends Telegram alert if drift detected (YELLOW/RED).

- check_suggestion_expiry (05:00 UTC daily):
    Detects weight suggestions that expired (7d TTL) without being approved.
    Logs source="expired" to PostgreSQL weight_update_log. Cleans up snapshot.

- check_and_apply_weights (triggered by run_weekly_weights, countdown=5s):
    Guardrail cascade (G1-G4) decides auto-apply vs freeze.
    On freeze: sends Telegram ⚠️ with inline keyboard (✅ Approva / ❌ Rifiuta).
    On pass: applies weights to Redis, logs to PostgreSQL.

- run_forward_return_worker (22:00 UTC daily):
    Populates forward_return on sentiment_signals rows that are >= 1 day old.
    Uses Alpaca daily bars: fwd_ret = (close_T+1 - close_T) / close_T.
    Required for IC / ICIR computation in run_daily_report.

See docs/ARCHITECTURE.md §6c for the full weight approval flow diagram.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx
import numpy as np
import psycopg2

from src.config import config
from src.models.performance import PerformanceReport, PostMortem
import hashlib

from src.notifications.telegram import (
    TelegramNotifier,
    format_auto_apply_message,
    format_freeze_message_with_keyboard,
)
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


def _fetch_all_per_model_signals_for_loo(
    pg: PostgreSQLStore,
    days: int,
) -> list[tuple]:
    """Fetch per-model (model_id, score, forward_return) from llm_responses for LOO ICIR.

    Uses llm_responses instead of sentiment_signals because sentiment_signals.model_id
    stores a compound ensemble ID (e.g. "ensemble:kimi+qwen+deepseek+glm"), which
    collapses all models into one bucket and prevents per-model ICIR computation.
    """
    symbols = config.WATCHLIST_SYMBOLS
    all_rows: list[tuple] = []
    for symbol in symbols:
        rows = pg.fetch_per_model_signals_for_ic(symbol, days)
        all_rows.extend(rows)
    return all_rows


def _fetch_all_signals_for_ic(
    pg: PostgreSQLStore,
    days: int,
) -> list[tuple]:
    """Fetch all signals across all symbols for IC calculation.

    Returns list of (score, confidence, forward_return, generated_at, model_id, fallback_used) tuples.
    """
    # We need to fetch signals for each symbol separately.
    # Use the configurable watchlist from config instead of a hardcoded list
    # so that the performance worker stays in sync with the ingestion pipeline.
    symbols = config.WATCHLIST_SYMBOLS
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

    pg = None
    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights from Redis
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"kimi-k2.6:cloud": 0.25, "qwen3.5:397b": 0.25, "deepseek-v4-pro:cloud": 0.25, "glm-5.1:cloud": 0.25}

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
    finally:
        if pg is not None:
            pg.close()


@app.task(name="src.workers.performance.run_weekly_weights")
def run_weekly_weights():
    """Weekly weight computation task (Fase 1: observational only).

    Computes Leave-One-Out ICIR for each model and suggests new weights.
    In Fase 1, weights are NOT auto-applied - only reported as suggestions.
    """
    log.info("Starting weekly weight computation (observational)...")

    pg = None
    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"kimi-k2.6:cloud": 0.25, "qwen3.5:397b": 0.25, "deepseek-v4-pro:cloud": 0.25, "glm-5.1:cloud": 0.25}

        # Fetch per-model signals from llm_responses for LOO ICIR.
        # sentiment_signals.model_id stores the compound ensemble ID so
        # grouping by it yields one bucket; llm_responses has one row per
        # model per inference, which is what per-model ICIR requires.
        per_model_rows = _fetch_all_per_model_signals_for_loo(pg, days=30)

        if not per_model_rows:
            log.info("No per-model samples available for weight update")
            return

        _MIN_SAMPLES = 10
        if len(per_model_rows) < _MIN_SAMPLES:
            log.info(
                "Insufficient per-model samples for ICIR: %d < %d — skipping weight update",
                len(per_model_rows),
                _MIN_SAMPLES,
            )
            return {"status": "insufficient_data", "n_samples": len(per_model_rows)}

        lloo_signals: dict[str, list[float]] = defaultdict(list)
        lloo_returns: dict[str, list[float]] = defaultdict(list)
        for m_id, score, fwd_ret in per_model_rows:
            lloo_signals[m_id].append(float(score))
            lloo_returns[m_id].append(float(fwd_ret))
        model_signals = dict(lloo_signals)
        model_returns = dict(lloo_returns)

        if len(model_signals) < 2:
            log.warning("Not enough distinct models for ICIR computation")
            return

        # Compute per-model ICIR: model_returns[m] is aligned with model_signals[m]
        purified_icir = compute_purified_icir(
            model_signals=model_signals,
            model_returns=model_returns,
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

        # Extra guardrail: if every model has negative ICIR, the ensemble is
        # unanimously underperforming. Force a freeze regardless of circuit breakers.
        if purified_icir and all(v <= 0 for v in purified_icir.values()):
            all_neg_msg = (
                f"All models ICIR ≤ 0 ({', '.join(f'{m}={v:.3f}' for m, v in purified_icir.items())}) "
                "— weight update frozen until ensemble recovers"
            )
            log.warning(all_neg_msg)
            freeze_reason = all_neg_msg if not freeze_reason else f"{freeze_reason}; {all_neg_msg}"

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

        # Snapshot key: 9d TTL (2d buffer) — read by check_suggestion_expiry
        # if the 7d suggestion key expires before being approved.
        # Deleted by POST /api/weights/approve on successful approval.
        redis._r.setex(
            "ensemble:weights:suggestion:snapshot",
            86400 * 9,
            json.dumps(suggestion),
        )

        # Send Telegram alert with suggestions
        notifier = TelegramNotifier()
        message = _format_weights_telegram_message(new_weights, current_weights, freeze_reason)
        asyncio.run(notifier.send_alert(message, level="info"))

        log.info(f"Weekly weights computed. Suggestion stored in Redis.")

        # Chain: trigger guardrail check 5s after suggestion is stored in Redis
        check_and_apply_weights.apply_async(countdown=5)

    except Exception as e:
        log.exception(f"Weekly weight computation failed: {e}")
        raise
    finally:
        if pg is not None:
            pg.close()


@app.task(name="src.workers.performance.run_drift_detection")
def run_drift_detection():
    """Weekly drift detection task.

    Computes PSI and CUSUM for each model's score distribution comparing:
    - Last 7 days vs 90-day baseline (primary)
    - Last 7 days vs 12-month baseline (secondary)

    Sends Telegram alert if drift is detected (YELLOW or RED level).
    """
    log.info("Starting weekly drift detection...")

    pg = None
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
    finally:
        if pg is not None:
            pg.close()


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


@app.task(name="src.workers.performance.check_suggestion_expiry")
def check_suggestion_expiry():
    """Daily: log weight suggestions that expired without being approved.

    Checks for the snapshot key (9d TTL) left by run_weekly_weights. If the
    snapshot exists but the original suggestion key (7d TTL) is gone, the
    suggestion expired without an admin approving it. Log source='expired'.
    The snapshot is also deleted by POST /api/weights/approve on success, so
    if we reach here the suggestion was never approved.
    """
    redis = RedisStore()

    snapshot_raw = redis._r.get("ensemble:weights:suggestion:snapshot")
    if snapshot_raw is None:
        return  # no pending suggestion

    if redis._r.get("ensemble:weights:suggestion") is not None:
        return  # suggestion still active, nothing to do

    # suggestion key gone + snapshot present → expired without approval
    try:
        snapshot = json.loads(snapshot_raw)
        if not isinstance(snapshot, dict):
            print(f"Expiry check: snapshot is not a dict, deleting corrupted data")
            redis._r.delete("ensemble:weights:suggestion:snapshot")
            return
    except json.JSONDecodeError as e:
        print(f"Expiry check: corrupted JSON in snapshot: {e}")
        redis._r.delete("ensemble:weights:suggestion:snapshot")
        return

    pg = PostgreSQLStore()
    try:
        pg.log_weight_update(
            source="expired",
            applied_weights=snapshot.get("suggested_weights", {}),
            suggested_weights=snapshot.get("suggested_weights"),
            purified_icir=snapshot.get("purified_icir"),
            freeze_reason=snapshot.get("freeze_reason") or None,
            note="Suggestion expired without approval",
        )
    finally:
        pg.close()

    # Clean up snapshot
    redis._r.delete("ensemble:weights:suggestion:snapshot")


def _get_vix(redis: RedisStore) -> float | None:
    """Return VIX from Redis cache, fetching from FRED on cache miss.

    Returns None if both cache and FRED are unavailable (caller treats as fail-safe freeze).
    """
    cached = redis.get_vix_cached()
    if cached is not None:
        return cached
    try:
        from src.connectors.macro import fetch_vix_from_fred
        vix = fetch_vix_from_fred(
            series_id=config.AUTO_APPLY_VIX_FRED_SERIES,
            api_key=config.FRED_API_KEY,
        )
        redis.set_vix_cached(vix, ttl=config.AUTO_APPLY_VIX_REDIS_TTL_SECONDS)
        return vix
    except (httpx.HTTPError, httpx.RequestError, ValueError) as e:
        log.warning("Failed to fetch VIX from FRED: %s", e)
        return None


@app.task(name="src.workers.performance.check_and_apply_weights")
def check_and_apply_weights():
    """Apply suggested ensemble weights if all guardrails pass.

    Guardrails evaluated in sequence — first failure stops evaluation:
      G1: AUTO_APPLY_ENABLED flag (silent exit if disabled)
      G2: VIX < vix_threshold (FRED via Redis cache; fail-safe freeze if unavailable)
      G3: std(purified_icir) < ic_variance_threshold
      G4: max(|Δweight|) < weight_delta_max vs current weights

    On pass: applies weights, logs source='auto_apply', sends Telegram ✅
    On fail: no change, logs source='freeze', sends Telegram ⚠️
    On no suggestion: silent exit
    """
    redis = RedisStore()

    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        return

    # G1: toggle (silent exit — disabled is a normal operational state)
    if not config.AUTO_APPLY_ENABLED:
        return

    suggested_weights = suggestion.get("suggested_weights", {})
    purified_icir = suggestion.get("purified_icir", {})

    freeze_reason = None
    ic_variance: float | None = None
    max_delta: float | None = None

    # Fetch current weights once — used in G4 and in both audit/notify branches
    stored = redis.get_current_weights_stored()
    current_weights = (stored or {}).get("weights", {})

    # G2: VIX
    vix = _get_vix(redis)
    if vix is None:
        freeze_reason = "VIX data unavailable (fail-safe)"
    elif vix >= config.AUTO_APPLY_VIX_THRESHOLD:
        freeze_reason = f"VIX = {vix:.1f} >= {config.AUTO_APPLY_VIX_THRESHOLD}"

    # G3: IC variance
    if freeze_reason is None:
        if not purified_icir:
            freeze_reason = "purified_icir missing from suggestion"
        else:
            ic_variance = float(np.std(list(purified_icir.values())))
            if ic_variance >= config.AUTO_APPLY_IC_VARIANCE_THRESHOLD:
                freeze_reason = (
                    f"IC variance = {ic_variance:.3f} >= {config.AUTO_APPLY_IC_VARIANCE_THRESHOLD}"
                )

    # G4: weight delta
    if freeze_reason is None:
        if stored is None:
            freeze_reason = "current weights unavailable (fail-safe)"
        else:
            all_models = set(suggested_weights) | set(current_weights)
            max_delta = max(
                abs(suggested_weights.get(m, 0.0) - current_weights.get(m, 0.0))
                for m in all_models
            )
            if max_delta >= config.AUTO_APPLY_WEIGHT_DELTA_MAX:
                freeze_reason = (
                    f"max weight delta = {max_delta:.3f} >= {config.AUTO_APPLY_WEIGHT_DELTA_MAX}"
                )

    pg = PostgreSQLStore()
    notifier = TelegramNotifier()

    try:
      if freeze_reason:
        # Log the freeze event to PostgreSQL for audit trail
        # source="freeze" indicates guardrail blocked auto-apply
        pg.log_weight_update(
            source="freeze",
            applied_weights=current_weights,  # No change — weights frozen
            suggested_weights=suggested_weights,  # What was proposed
            purified_icir=purified_icir,  # Context for review
            freeze_reason=freeze_reason,  # Which guardrail failed
            note=f"Auto-apply blocked: {freeze_reason}",
            approved_by="system",  # No human approval yet
        )

        # =====================================================================
        # TELEGRAM APPROVAL FLOW (Feature C)
        # =====================================================================
        # Send freeze message with inline keyboard (✅ Approva / ❌ Rifiuta).
        # The operator can tap to approve or reject without using the API.
        #
        # Token generation:
        #   SHA256(computed_at)[:8] — anti-replay validation
        #   - Prevents double-tap (second tap finds deleted suggestion)
        #   - Prevents stale taps (new suggestion = new token)
        #
        # The poll_telegram_updates task (Celery beat, 5s) processes taps:
        #   - Valid approve → set_ensemble_weights(source="telegram")
        #   - Valid reject → delete suggestion, log source="rejected_via_telegram"
        # =====================================================================
        computed_at = suggestion.get("computed_at", datetime.now(timezone.utc).isoformat())
        token = hashlib.sha256(computed_at.encode()).hexdigest()[:8]

        # Generate message text and keyboard layout
        msg, keyboard = format_freeze_message_with_keyboard(
            suggested_weights, current_weights, freeze_reason, token
        )

        # Send message to Telegram. Returns message_id (not persisted — poller
        # retrieves it from callback_query["message"]["message_id"]).
        message_id = asyncio.run(notifier.send_message_with_keyboard(msg, keyboard))
        if message_id:
            log.info("Freeze message sent with keyboard: message_id=%d", message_id)

        log.info("Auto-apply frozen: %s", freeze_reason)
      else:
        redis.set_ensemble_weights(suggested_weights, source="auto_apply")
        redis.delete_suggestion_snapshot()

        pg.log_weight_update(
            source="auto_apply",
            applied_weights=suggested_weights,
            suggested_weights=suggested_weights,
            purified_icir=purified_icir,
            freeze_reason=None,
            note=json.dumps({"vix": vix, "ic_variance": ic_variance, "max_delta": max_delta}),
            approved_by="system",
        )

        next_review = (datetime.now(timezone.utc) + timedelta(days=7)).date()
        msg = format_auto_apply_message(
            suggested_weights, current_weights,
            {"vix": vix, "ic_variance": ic_variance, "weight_delta_max": max_delta},
            next_review,
        )
        asyncio.run(notifier.send_alert(msg, level="info"))
        log.info("Weights auto-applied successfully")
    finally:
        pg.close()


@app.task(name="src.workers.performance.run_forward_return_worker")
def run_forward_return_worker() -> dict:
    """Populate forward_return for sentiment signals that are at least 1 day old.

    Scheduled daily at 22:00 UTC (6pm ET, after US market close + settlement).
    Uses Alpaca StockHistoricalDataClient to fetch daily bars.

    Forward return definition:
        fwd_ret = (close_{T+1} - close_T) / close_T

    Where T = trading day of the signal and T+1 = next trading day.
    Signals generated after market close (>= 21:00 UTC / 4pm ET) are treated
    as belonging to the NEXT trading day, so their T+1 is T+2 calendar days.

    Skips symbols without available daily bars (ETFs, ADRs, delisted tickers).

    Returns:
        Dict with: updated (int), skipped_no_data (int), errors (int).
    """
    from collections import defaultdict

    import psycopg2
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    stats = {"updated": 0, "skipped_no_data": 0, "errors": 0}

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping forward return worker")
        return {**stats, "skipped": True, "reason": "no_credentials"}

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg = PostgreSQLStore(conn=pg_conn)

    try:
        rows = pg.fetch_signals_pending_forward_return(days_back=60)
        if not rows:
            log.info("No signals pending forward return")
            return stats

        log.info("Forward return worker: %d signals to process", len(rows))

        # Group by symbol to minimise Alpaca API calls (one batch per symbol).
        by_symbol: dict[str, list[tuple]] = defaultdict(list)
        for sid, symbol, generated_at in rows:
            by_symbol[symbol].append((sid, generated_at))

        data_client = StockHistoricalDataClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
        )

        updates: list[tuple[int, float]] = []

        for symbol, signals in by_symbol.items():
            try:
                # Determine date range: earliest signal date minus 1 day buffer,
                # latest signal date plus 3 days (covers weekends / holidays for T+1).
                dates = [ts for _, ts in signals]
                start = min(dates) - timedelta(days=2)
                end = max(dates) + timedelta(days=4)

                req = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Day,
                    start=start,
                    end=end,
                )
                bars_df = data_client.get_stock_bars(req).df

                # Flatten multi-index if present (symbol, timestamp) → just timestamp.
                if hasattr(bars_df.index, "levels"):
                    bars_df = bars_df.loc[symbol] if symbol in bars_df.index.get_level_values(0) else bars_df
                bars_df = bars_df.sort_index()

                if bars_df.empty or len(bars_df) < 2:
                    log.debug("Insufficient daily bars for %s — skipping", symbol)
                    stats["skipped_no_data"] += len(signals)
                    continue

                # Build a date → close price lookup from available bars.
                close_by_date: dict[date, float] = {
                    idx.date() if hasattr(idx, "date") else idx: float(row["close"])
                    for idx, row in bars_df.iterrows()
                }
                trading_dates = sorted(close_by_date.keys())

                for sid, generated_at in signals:
                    try:
                        # Signals after 21:00 UTC (4pm ET close) belong to next session.
                        if generated_at.tzinfo is None:
                            generated_at = generated_at.replace(tzinfo=timezone.utc)
                        signal_date = generated_at.date()
                        if generated_at.hour >= 21:
                            signal_date += timedelta(days=1)

                        # Find T: the first trading day on or after signal_date.
                        t_dates = [d for d in trading_dates if d >= signal_date]
                        if len(t_dates) < 2:
                            stats["skipped_no_data"] += 1
                            continue

                        t0, t1 = t_dates[0], t_dates[1]
                        close_t0 = close_by_date[t0]
                        close_t1 = close_by_date[t1]

                        if close_t0 == 0:
                            stats["skipped_no_data"] += 1
                            continue

                        fwd_ret = (close_t1 - close_t0) / close_t0
                        updates.append((sid, fwd_ret))

                    except Exception as e:
                        log.debug("Error computing fwd return for signal %d (%s): %s", sid, symbol, e)
                        stats["errors"] += 1

            except Exception as e:
                log.warning("Failed to fetch bars for %s: %s — skipping", symbol, e)
                stats["skipped_no_data"] += len(signals)

        # Bulk-write all computed forward returns in one transaction.
        if updates:
            stats["updated"] = pg.bulk_add_forward_returns(updates)
            log.info(
                "Forward return worker complete: updated=%d skipped=%d errors=%d",
                stats["updated"], stats["skipped_no_data"], stats["errors"],
            )

    finally:
        pg_conn.close()

    return stats
