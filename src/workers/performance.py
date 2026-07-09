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
from src.workers._async_utils import run_async
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
from src.workers.execution import ENTRY_THRESHOLD

log = logging.getLogger(__name__)

# Minimum samples required for meaningful IC computation
_MIN_SAMPLES = 300
_MIN_SAMPLES_PER_MODEL = 30
_MIN_ABS_MEAN_ICIR = 0.05  # G3.5: freeze if mean ICIR < -this (ensemble anti-predictive)
_SLIPPAGE_WARN_PCT = 0.30   # ⚠️ if estimated slippage > 30% of gross P&L


def _fetch_all_per_model_signals_for_loo(
    pg: PostgreSQLStore,
    days: int,
) -> list[tuple]:
    """Fetch per-model (model_id, score, forward_return) from llm_responses for LOO ICIR.

    Uses llm_responses instead of sentiment_signals because sentiment_signals.model_id
    stores a compound ensemble ID (e.g. "ensemble:kimi+qwen+deepseek+glm"), which
    collapses all models into one bucket and prevents per-model ICIR computation.
    """
    symbols = list(config.WATCHLIST_SYMBOLS or [])
    return pg.fetch_all_per_model_signals_for_ic(symbols, days)


def _fetch_all_signals_for_ic(
    pg: PostgreSQLStore,
    days: int,
) -> list[tuple]:
    """Fetch all signals across all symbols for IC calculation.

    Returns list of (score, confidence, forward_return, generated_at, model_id, fallback_used) tuples.
    """
    symbols = list(config.WATCHLIST_SYMBOLS or [])
    return pg.fetch_all_signals_for_ic(symbols, days)


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

    # Per-model IC/ICIR — must use llm_responses (individual model IDs).
    # sentiment_signals.model_id stores the compound ensemble ID
    # (e.g. "ensemble:kimi-k2.6+glm-5.2"), so grouping it yields one
    # bucket and the per-model lookup against current_weights.keys() always
    # returns [].  llm_responses has one row per model per inference with the
    # correct individual model_id (e.g. "kimi-k2.6:cloud").
    per_model_raw = _fetch_all_per_model_signals_for_loo(pg, period_days)
    pm_signals: dict[str, list[float]] = defaultdict(list)
    pm_returns: dict[str, list[float]] = defaultdict(list)
    for m_id, score, fwd_ret in per_model_raw:
        pm_signals[m_id].append(float(score))
        pm_returns[m_id].append(float(fwd_ret))

    model_ic: dict[str, float] = {}
    model_icir: dict[str, float] = {}

    for model in current_weights.keys():
        ms = pm_signals.get(model, [])
        mr = pm_returns.get(model, [])

        if len(ms) >= _MIN_SAMPLES_PER_MODEL:
            mic = compute_composite_ic(ms, mr)
            micir = compute_icir(ms, mr, min_samples=10)
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


def _format_trade_metrics_section(trades_summary: dict) -> str:
    """Format the trade P&L section for the weekly Telegram report."""
    from src.config import config

    total = trades_summary.get("total_trades", 0)
    if total == 0:
        return "\n📊 *Trade P&L (last 7d)*\nNo closed trades in period."

    win_pct = trades_summary.get("win_rate", 0) * 100
    avg_net = trades_summary.get("avg_net_pnl", 0)
    avg_gross = trades_summary.get("avg_gross_pnl", 0)
    avg_slip = trades_summary.get("avg_slippage_est", 0)
    total_net = trades_summary.get("total_net_pnl", 0)
    total_gross = trades_summary.get("total_gross_pnl", 0)
    total_notional = trades_summary.get("total_notional", 0)
    tpw = trades_summary.get("trades_per_week", 0)
    avg_hold = trades_summary.get("avg_hold_minutes", 0)
    slip_pct = trades_summary.get("slippage_pct_of_gross", 0)
    ron = trades_summary.get("return_on_notional", 0) * 100

    warnings = []
    if avg_net < config.MIN_TRADE_PNL_THRESHOLD:
        warnings.append(f"⚠️ avg net P&L ${avg_net:.2f} < ${config.MIN_TRADE_PNL_THRESHOLD:.2f} threshold")
    if slip_pct > _SLIPPAGE_WARN_PCT:
        warnings.append(f"⚠️ slippage {slip_pct*100:.1f}% of gross — consider raising ENTRY_THRESHOLD")

    warn_str = "\n" + "\n".join(warnings) if warnings else ""

    # Cost analysis section
    avg_cost_bps = trades_summary.get("avg_cost_bps", 0.0)
    total_cost_usd = trades_summary.get("total_cost_usd", 0.0)
    avg_spread_bps = trades_summary.get("avg_spread_cost_bps", 0.0)
    avg_impact_bps = trades_summary.get("avg_impact_cost_bps", 0.0)
    cost_drag_pct = trades_summary.get("cost_drag_pct", 0.0)

    if avg_cost_bps > 0:
        annualized_drag_bps = cost_drag_pct * 252 * 10_000 if cost_drag_pct else 0.0
        cost_section = (
            f"\n💸 *Cost Analysis*\n"
            f"Avg cost/trade: {avg_cost_bps:.1f} bps "
            f"(spread {avg_spread_bps:.1f} + impact {avg_impact_bps:.1f})\n"
            f"Total cost: ${total_cost_usd:.2f} | Cost drag: {cost_drag_pct*100:.3f}%\n"
            f"Annualised drag: ~{annualized_drag_bps:.0f} bps/yr"
        )
    else:
        cost_section = "\n💸 *Cost Analysis*\nNo cost data yet (pre-migration trades)"

    return (
        f"\n📊 *Trade P&L (last 7d)*\n"
        f"Trades: {total} | Win rate: {win_pct:.1f}%\n"
        f"Avg gross P&L: ${avg_gross:.2f} | Avg slippage: ${avg_slip:.2f} | Avg net: ${avg_net:.2f}\n"
        f"Total gross: ${total_gross:.2f} | Total net: ${total_net:.2f}\n"
        f"\n📈 *Frequency vs Margin*\n"
        f"Trades/week: {tpw:.1f} | Total notional: ${total_notional:.0f}\n"
        f"Return on notional: {ron:.2f}% | Avg hold: {avg_hold:.0f}min\n"
        f"Est. slippage: {slip_pct*100:.1f}% of gross P&L"
        f"{cost_section}"
        f"{warn_str}"
    )


def _format_capital_efficiency_section(
    open_trades: list[dict],
    portfolio_value_usd: float,
) -> str:
    """Format capital deployment / cash-drag section for the weekly report.

    open_trades: rows from pg.fetch_trades(status="open")
    portfolio_value_usd: last known portfolio value from Redis (0 if unavailable)
    """
    deployed_notional = sum(float(t.get("entry_notional") or 0) for t in open_trades)
    n_open = len(open_trades)

    # MAX_POSITION_PCT=10%, up to 5 positions = 50% theoretical max
    theoretical_max_pct = 0.50

    if portfolio_value_usd > 0:
        deployment_pct = deployed_notional / portfolio_value_usd
        cash_pct = 1.0 - deployment_pct
        # Cash drag = uninvested capital × assumed risk-free rate (4.5% US T-bill proxy)
        risk_free_rate = 0.045
        annual_cash_drag_pct = cash_pct * risk_free_rate * 100
        pv_str = f"${portfolio_value_usd:,.0f}"
        deploy_str = f"{deployment_pct:.1%} ({n_open} open pos, ${deployed_notional:,.0f})"
        cash_str = f"{cash_pct:.1%} idle → ~{annual_cash_drag_pct:.1f}%/yr opportunity cost"
    else:
        deploy_str = f"{n_open} open positions (${deployed_notional:,.0f} notional)"
        cash_str = "portfolio value unavailable — run execution cycle to populate"
        pv_str = "unknown"

    efficiency_ratio = (deployed_notional / (portfolio_value_usd * theoretical_max_pct)) if portfolio_value_usd > 0 else 0.0
    efficiency_str = f"{efficiency_ratio:.0%} of theoretical max" if portfolio_value_usd > 0 else "N/A"

    return (
        f"\n💰 *Capital Efficiency*\n"
        f"Portfolio: {pv_str} | Deployed: {deploy_str}\n"
        f"Cash idle: {cash_str}\n"
        f"Deployment efficiency: {efficiency_str} (max={theoretical_max_pct:.0%} with 5 positions)"
    )


def _format_feedback_stall_section(redis: "RedisStore") -> str:
    """Format loss-feedback / threshold-stall section for the weekly report."""
    import yaml
    from pathlib import Path
    _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
    try:
        with open(_TRADING_YAML) as f:
            cfg_yaml = yaml.safe_load(f) or {}
        fb_cfg = cfg_yaml.get("loss_feedback", {})
    except Exception:
        fb_cfg = {}

    baseline = float(fb_cfg.get("threshold_baseline", 0.30))
    threshold_max = float(fb_cfg.get("threshold_max", 0.60))
    recovery_win_streak = int(fb_cfg.get("recovery_win_streak", 3))

    current_threshold = redis.get_feedback_entry_threshold() or baseline
    current_scale = redis.get_feedback_regime_scale() or 1.0
    feedback_state = redis.get_feedback_state() or {}

    is_elevated = current_threshold > baseline + 0.001
    consecutive_wins = int(feedback_state.get("consecutive_wins") or 0)
    last_ts = feedback_state.get("last_adjustment_ts", "")

    if is_elevated:
        wins_needed = max(0, recovery_win_streak - consecutive_wins)
        # Fraction of signal space filtered: signals between baseline and current
        # threshold are blocked. Rough proxy: (current - baseline) / (max - baseline)
        signal_filter_pct = (current_threshold - baseline) / (threshold_max - baseline) * 100
        stall_status = (
            f"🔴 ELEVATED: {current_threshold:.2f} (baseline {baseline:.2f})\n"
            f"~{signal_filter_pct:.0f}% of marginal signals suppressed | "
            f"Regime scale: {current_scale:.2f}\n"
            f"Recovery: {consecutive_wins}/{recovery_win_streak} wins ({wins_needed} more needed)"
        )
    else:
        stall_status = f"✅ Normal: threshold {current_threshold:.2f} (baseline {baseline:.2f})"

    last_str = f" | Last trigger: {last_ts[:10]}" if last_ts else ""
    return f"\n🧠 *Feedback Loop*\n{stall_status}{last_str}"


def _format_regime_section(redis: "RedisStore", portfolio_value_usd: float = 0.0) -> str:
    """Format current regime + deployment ceiling for the weekly report."""
    _MULTIPLIERS = {"bull": 1.0, "sideways": 0.7, "bear": 0.4, "high_vol": 0.2}
    _MAX_POSITION_PCT = 0.10
    _MAX_POSITIONS = 5

    regime_state = redis.get_regime()
    if regime_state is None:
        return "\n📡 *Regime*\nNo regime data in Redis (check regime worker)"

    label = getattr(regime_state, "regime", "unknown")
    multiplier = float(getattr(regime_state, "multiplier", _MULTIPLIERS.get(str(label), 0.2)))
    confidence = float(getattr(regime_state, "confidence", 0.0))

    bull_ceiling_pct = _MAX_POSITION_PCT * 1.0 * _MAX_POSITIONS
    current_ceiling_pct = _MAX_POSITION_PCT * multiplier * _MAX_POSITIONS
    regime_discount_pct = (1.0 - multiplier) * 100

    if portfolio_value_usd > 0:
        ceiling_str = f"${current_ceiling_pct * portfolio_value_usd:,.0f} ({current_ceiling_pct:.0%} of portfolio)"
        bull_str = f" vs ${bull_ceiling_pct * portfolio_value_usd:,.0f} in bull"
    else:
        ceiling_str = f"{current_ceiling_pct:.0%} of portfolio"
        bull_str = f" vs {bull_ceiling_pct:.0%} in bull"

    emoji = {"bull": "🟢", "sideways": "🟡", "bear": "🔴", "high_vol": "🚨"}.get(str(label), "⚪")

    return (
        f"\n📡 *Regime*\n"
        f"{emoji} {label} ×{multiplier} (confidence {confidence:.0%})\n"
        f"Deployment ceiling: {ceiling_str}{bull_str}\n"
        f"Regime discount: {regime_discount_pct:.0f}% of max capital withheld"
    )


def _format_infrastructure_section(pg: "PostgreSQLStore") -> str:
    """Format infrastructure cost / break-even section for the weekly report."""
    import yaml
    from pathlib import Path
    _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
    try:
        with open(_TRADING_YAML) as f:
            cfg_yaml = yaml.safe_load(f) or {}
        annual_fixed = float(cfg_yaml.get("infrastructure", {}).get("annual_fixed_cost_usd", 1440.0))
    except Exception:
        annual_fixed = 1440.0

    try:
        llm_30d = pg.fetch_llm_budget_period(days=30)
    except Exception:
        llm_30d = 0.0

    monthly_fixed = annual_fixed / 12
    monthly_llm = llm_30d
    monthly_total = monthly_fixed + monthly_llm
    annual_total = annual_fixed + monthly_llm * 12

    # Break-even portfolio sizes at 5%, 10%, 15% net annual return assumptions
    breakevens = {
        pct: annual_total / (pct / 100)
        for pct in [5, 10, 15]
    }
    be_str = " | ".join(f"{p}% return→${v:,.0f}" for p, v in breakevens.items())

    return (
        f"\n🏗️ *Infrastructure Costs*\n"
        f"Monthly: ${monthly_total:.0f} (fixed ${monthly_fixed:.0f} + LLM ${monthly_llm:.2f})\n"
        f"Annual estimate: ${annual_total:,.0f}\n"
        f"Break-even portfolio: {be_str}"
    )


def _build_weekly_structured(
    new_weights: dict,
    current_weights: dict,
    freeze_reason: str,
    purified_icir: dict,
    pg: "PostgreSQLStore",
    redis: "RedisStore",
) -> dict:
    """Build structured weekly report dict for the web API (JSON-serializable)."""
    data: dict = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "weights": {
            "current": current_weights,
            "suggested": new_weights,
            "purified_icir": purified_icir,
            "freeze_reason": freeze_reason,
        },
        "trade_pnl": {},
        "capital_efficiency": {},
        "regime": {},
        "feedback": {},
        "infrastructure": {},
    }

    # Load trading.yaml once for feedback and infrastructure sections
    _cfg_yaml: dict = {}
    try:
        import yaml
        from pathlib import Path
        _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
        with open(_TRADING_YAML) as f:
            _cfg_yaml = yaml.safe_load(f) or {}
    except Exception as e:
        log.warning("weekly_structured: failed to load trading.yaml: %s", e)

    try:
        ts = pg.fetch_trade_summary(days=7)
        data["trade_pnl"] = {k: ts.get(k, 0) for k in [
            "total_trades", "win_rate", "avg_net_pnl", "avg_gross_pnl",
            "avg_slippage_est", "total_net_pnl", "total_gross_pnl",
            "total_notional", "trades_per_week", "avg_hold_minutes",
            "slippage_pct_of_gross", "return_on_notional",
            "avg_cost_bps", "total_cost_usd", "avg_spread_cost_bps",
            "avg_impact_cost_bps", "cost_drag_pct",
        ]}
    except Exception as e:
        log.warning("weekly_structured: trade_pnl fetch failed: %s", e)

    try:
        open_trades = pg.fetch_trades(status="open", limit=20)
        pv = float(redis._r.get("portfolio:value") or 0)
        deployed = sum(float(t.get("entry_notional") or 0) for t in open_trades)
        n_open = len(open_trades)
        depl_pct = deployed / pv if pv > 0 else 0.0
        cash_pct = 1.0 - depl_pct
        data["capital_efficiency"] = {
            "portfolio_value_usd": pv,
            "deployed_notional": deployed,
            "n_open_positions": n_open,
            "deployment_pct": depl_pct,
            "cash_pct": cash_pct,
            "annual_cash_drag_pct": cash_pct * 0.045 * 100,
            "efficiency_ratio": (deployed / (pv * 0.50)) if pv > 0 else 0.0,
        }
    except Exception as e:
        log.warning("weekly_structured: capital_efficiency fetch failed: %s", e)

    try:
        regime_state = redis.get_regime()
        _MULTS = {"bull": 1.0, "sideways": 0.7, "bear": 0.4, "high_vol": 0.2}
        label = str(getattr(regime_state, "regime", "unknown") if regime_state else "unknown")
        mult = float(getattr(regime_state, "multiplier", _MULTS.get(label, 0.2)) if regime_state else 0.2)
        conf = float(getattr(regime_state, "confidence", 0.0) if regime_state else 0.0)
        data["regime"] = {
            "label": label,
            "multiplier": mult,
            "confidence": conf,
            "deployment_ceiling_pct": 0.10 * mult * 5,
            "regime_discount_pct": (1.0 - mult) * 100,
        }
    except Exception as e:
        log.warning("weekly_structured: regime fetch failed: %s", e)

    try:
        fb_cfg = _cfg_yaml.get("loss_feedback", {})
        baseline = float(fb_cfg.get("threshold_baseline", 0.30))
        recovery_win_streak = int(fb_cfg.get("recovery_win_streak", 3))
        current_thr = redis.get_feedback_entry_threshold() or baseline
        current_scale = redis.get_feedback_regime_scale() or 1.0
        fb_state = redis.get_feedback_state() or {}
        data["feedback"] = {
            "threshold_baseline": baseline,
            "threshold_max": float(fb_cfg.get("threshold_max", 0.60)),
            "current_threshold": current_thr,
            "current_scale": current_scale,
            "is_elevated": current_thr > baseline + 0.001,
            "consecutive_wins": int(fb_state.get("consecutive_wins") or 0),
            "recovery_win_streak": recovery_win_streak,
            "last_adjustment_ts": fb_state.get("last_adjustment_ts", ""),
        }
    except Exception as e:
        log.warning("weekly_structured: feedback fetch failed: %s", e)

    try:
        annual_fixed = float(_cfg_yaml.get("infrastructure", {}).get("annual_fixed_cost_usd", 1440.0))
        llm_30d = pg.fetch_llm_budget_period(days=30)
        monthly_fixed = annual_fixed / 12
        monthly_llm = float(llm_30d)
        monthly_total = monthly_fixed + monthly_llm
        annual_total = annual_fixed + monthly_llm * 12
        data["infrastructure"] = {
            "monthly_fixed_usd": monthly_fixed,
            "monthly_llm_usd": monthly_llm,
            "monthly_total_usd": monthly_total,
            "annual_total_usd": annual_total,
            "breakevens": {str(p): annual_total / (p / 100) for p in [5, 10, 15]},
        }
    except Exception as e:
        log.warning("weekly_structured: infrastructure fetch failed: %s", e)

    return data


@app.task(name="src.workers.performance.run_reconcile_fills_intraday")
def run_reconcile_fills_intraday() -> dict:
    """Intraday fill reconciliation — runs every 15 min during market hours.

    Fetches Alpaca fill prices for trades whose exit_order_id is set but
    exit_price is still NULL (recorded by record_trade_exit, price pending).
    Lightweight: no IC/report computation, no Telegram alerts.
    """
    from src.config import config as _cfg

    if not _cfg.ALPACA_API_KEY or not _cfg.ALPACA_SECRET_KEY:
        return {"skipped": True, "reason": "no_credentials"}

    pg = PostgreSQLStore()
    try:
        from alpaca.trading.client import TradingClient
        tc = TradingClient(
            api_key=_cfg.ALPACA_API_KEY,
            secret_key=_cfg.ALPACA_SECRET_KEY,
            paper=_cfg.ALPACA_PAPER_MODE,
        )
        updated = pg.reconcile_trade_fills(tc)
        log.info("Intraday reconcile: %d fill(s) updated", updated)
        return {"updated": updated}
    except Exception as exc:
        log.warning("Intraday fill reconciliation failed: %s", exc)
        return {"error": str(exc)}
    finally:
        pg.close()


@app.task(name="src.workers.performance.run_daily_report")
def run_daily_report():
    """Daily performance report task.

    Computes IC metrics over the last 30 days and sends a Telegram alert
    with the performance summary.
    """
    log.info("Starting daily performance report...")

    pg = None
    redis = None
    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights from Redis
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"kimi-k2.6:cloud": 0.50, "glm-5.2:cloud": 0.50}

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

        # Build signal distribution for last 24h (visibility into why portfolio is cash)
        signal_distribution = _build_signal_distribution(pg, lookback_hours=24)

        # Send Telegram alert
        notifier = TelegramNotifier()
        message = _format_performance_telegram_message(
            report, cb_result.soft_warnings_triggered, signal_distribution
        )
        run_async(notifier.send_alert(message, level="info"))

        log.info(f"Daily report sent. Overall IC: {report.overall_ic:.4f}, ICIR: {report.icir:.3f}")

        # Reconcile fill prices from Alpaca for trades placed in last 24h
        if config.ALPACA_API_KEY and config.ALPACA_SECRET_KEY:
            try:
                from alpaca.trading.client import TradingClient
                tc = TradingClient(
                    api_key=config.ALPACA_API_KEY,
                    secret_key=config.ALPACA_SECRET_KEY,
                    paper=config.ALPACA_PAPER_MODE,
                )
                updated = pg.reconcile_trade_fills(tc)
                log.info("Reconciled %d trade fill(s) from Alpaca", updated)
            except Exception as e:
                log.warning("Fill reconciliation failed: %s", e)

    except Exception as e:
        log.exception(f"Daily performance report failed: {e}")
        raise
    finally:
        if redis is not None:
            redis.close()
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
    redis = None
    try:
        pg = PostgreSQLStore()
        redis = RedisStore()

        # Get current weights
        raw_weights = redis.get_ensemble_weights()
        if raw_weights:
            current_weights = json.loads(raw_weights).get("weights", {})
        else:
            current_weights = {"kimi-k2.6:cloud": 0.50, "glm-5.2:cloud": 0.50}

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

        # G3.5: if mean ICIR is strongly negative, the ensemble is anti-predictive.
        # This catches cases where most models are significantly negative but one is
        # marginally positive — not caught by all(v <= 0) or by the variance check.
        if purified_icir:
            mean_icir = sum(purified_icir.values()) / len(purified_icir)
            if mean_icir < -_MIN_ABS_MEAN_ICIR:
                anti_msg = (
                    f"ensemble anti-predictive: mean ICIR = {mean_icir:.3f} < -{_MIN_ABS_MEAN_ICIR} "
                    f"({', '.join(f'{m}={v:.3f}' for m, v in purified_icir.items())}) "
                    "— weight update frozen until ensemble recovers"
                )
                log.warning(anti_msg)
                freeze_reason = anti_msg if not freeze_reason else f"{freeze_reason}; {anti_msg}"

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

        # Append trade P&L section
        try:
            trade_summary = pg.fetch_trade_summary(days=7)
            message += _format_trade_metrics_section(trade_summary)
        except Exception as e:
            log.warning("Failed to fetch trade summary for weekly report: %s", e)

        # Append capital efficiency / cash-drag section
        try:
            open_trades = pg.fetch_trades(status="open", limit=20)
            portfolio_value_usd = float(redis._r.get("portfolio:value") or 0)
            message += _format_capital_efficiency_section(open_trades, portfolio_value_usd)
        except Exception as e:
            log.warning("Failed to build capital efficiency section: %s", e)

        # Append regime / deployment-ceiling section
        try:
            portfolio_value_usd = float(redis._r.get("portfolio:value") or 0)
            message += _format_regime_section(redis, portfolio_value_usd)
        except Exception as e:
            log.warning("Failed to build regime section: %s", e)

        # Append feedback loop / threshold-stall section
        try:
            message += _format_feedback_stall_section(redis)
        except Exception as e:
            log.warning("Failed to build feedback stall section: %s", e)

        # Append infrastructure cost / break-even section
        try:
            message += _format_infrastructure_section(pg)
        except Exception as e:
            log.warning("Failed to build infrastructure section: %s", e)

        run_async(notifier.send_alert(message, level="info"))

        # Store structured weekly report for web API (TTL 9d, same as snapshot)
        try:
            weekly_structured = _build_weekly_structured(
                new_weights=new_weights,
                current_weights=current_weights,
                freeze_reason=freeze_reason,
                purified_icir=purified_icir,
                pg=pg,
                redis=redis,
            )
            redis._r.setex(
                "performance:weekly_report",
                86400 * 9,
                json.dumps(weekly_structured),
            )
        except Exception as e:
            log.warning("Failed to store structured weekly report: %s", e)

        log.info(f"Weekly weights computed. Suggestion stored in Redis.")

        # Chain: trigger guardrail check 5s after suggestion is stored in Redis
        check_and_apply_weights.apply_async(countdown=5)

    except Exception as e:
        log.exception(f"Weekly weight computation failed: {e}")
        raise
    finally:
        if redis is not None:
            redis.close()
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
    redis = None
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
            run_async(notifier.send_alert(message, level=level))
            log.warning(f"Drift alerts sent: {len(alerts)}")
        else:
            log.info("No drift detected.")

    except Exception as e:
        log.exception(f"Drift detection failed: {e}")
        raise
    finally:
        if redis is not None:
            redis.close()
        if pg is not None:
            pg.close()


def _build_signal_distribution(
    pg: PostgreSQLStore,
    lookback_hours: int = 24,
) -> dict[str, dict]:
    """Build per-model signal score distribution stats for the last N hours.

    Returns:
        Dict mapping model_id to stats: count, mean, median, p25, p75,
        above_threshold (score > ENTRY_THRESHOLD), near_threshold (half..threshold].
    """
    rows = pg.fetch_signals_last_hours(lookback_hours)
    if not rows:
        return {}

    half_threshold = ENTRY_THRESHOLD / 2
    by_model: dict[str, list[float]] = defaultdict(list)
    for score, model_id in rows:
        by_model[model_id].append(float(score))

    result = {}
    for model_id, scores in by_model.items():
        arr = np.array(scores)
        result[model_id] = {
            "count": len(arr),
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "above_threshold": int(np.sum(arr > ENTRY_THRESHOLD)),
            "near_threshold": int(np.sum((arr > half_threshold) & (arr <= ENTRY_THRESHOLD))),
        }
    return result


def _format_performance_telegram_message(
    report: PerformanceReport,
    soft_warnings: list[str],
    signal_distribution: dict | None = None,
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

    if signal_distribution:
        lines.append("")
        lines.append(f"Signal Distribution (last 24h, threshold={ENTRY_THRESHOLD}):")
        for model_id, stats in sorted(signal_distribution.items()):
            lines.append(
                f"  {model_id}: n={stats['count']}"
                f" mean={stats['mean']:.3f}"
                f" p25/p75={stats['p25']:.3f}/{stats['p75']:.3f}"
                f" above={stats['above_threshold']}"
                f" near={stats['near_threshold']}"
            )

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
    try:
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
    finally:
        redis.close()


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

    # G3.5: anti-predictive ensemble guard
    if freeze_reason is None and purified_icir:
        mean_icir = sum(purified_icir.values()) / len(purified_icir)
        if mean_icir < -_MIN_ABS_MEAN_ICIR:
            freeze_reason = (
                f"ensemble anti-predictive: mean ICIR = {mean_icir:.3f} < -{_MIN_ABS_MEAN_ICIR}"
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
        message_id = run_async(notifier.send_message_with_keyboard(msg, keyboard))
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
        run_async(notifier.send_alert(msg, level="info"))
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


# ---------------------------------------------------------------------------
# Loss Feedback — Phase B
# ---------------------------------------------------------------------------

def _load_loss_feedback_config() -> dict:
    """Load loss_feedback section from trading.yaml with safe defaults."""
    import yaml
    from pathlib import Path
    _TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
    defaults = {
        "enabled": True,
        "consecutive_loss_trigger": 3,
        "rolling_pnl_window": 10,
        "threshold_step": 0.05,
        "threshold_max": 0.60,
        "threshold_baseline": 0.30,
        "regime_scale_factor": 0.80,
        "regime_min_scale": 0.20,
        "cooldown_hours": 4,
        "recovery_win_streak": 3,
        "feedback_ttl_hours": 48,
    }
    try:
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f) or {}
        merged = {**defaults, **cfg.get("loss_feedback", {})}
        return merged
    except Exception as exc:
        log.warning("Could not load loss_feedback config (%s) — using defaults", exc)
        return defaults


def _count_consecutive_losses(trades: list[dict]) -> int:
    """Count consecutive losses from the most recent trade backward."""
    count = 0
    for trade in trades:  # trades are most-recent first
        if (trade.get("net_pnl") or 0) < 0:
            count += 1
        else:
            break
    return count


def _count_consecutive_wins(trades: list[dict]) -> int:
    """Count consecutive wins from the most recent trade backward."""
    count = 0
    for trade in trades:  # trades are most-recent first
        if (trade.get("net_pnl") or 0) > 0:
            count += 1
        else:
            break
    return count


@app.task(name="src.workers.performance.run_loss_feedback_check")
def run_loss_feedback_check() -> dict:
    """Detect loss patterns and auto-adjust ENTRY_THRESHOLD and regime scale.

    Trigger conditions (either is sufficient):
      - N consecutive losses  (consecutive_loss_trigger)
      - Negative sum of rolling net P&L over last rolling_pnl_window trades

    On trigger:
      - Raises ENTRY_THRESHOLD by threshold_step (capped at threshold_max)
      - Reduces regime scale by regime_scale_factor (floored at regime_min_scale)
      - Writes both to Redis with feedback_ttl_hours TTL
      - Sends Telegram alert

    Recovery:
      - recovery_win_streak consecutive wins → steps threshold back toward baseline

    Cooldown: no adjustment within cooldown_hours of the last one.
    """
    cfg = _load_loss_feedback_config()
    if not cfg["enabled"]:
        return {"skipped": True, "reason": "disabled"}

    redis = RedisStore()
    pg = PostgreSQLStore()
    try:
        fetch_n = max(cfg["consecutive_loss_trigger"] + 1, cfg["rolling_pnl_window"])
        trades = pg.fetch_trades(status="closed", limit=fetch_n)
    finally:
        pg.close()

    if not trades:
        redis.close()
        return {"skipped": True, "reason": "no_closed_trades"}

    consecutive_losses = _count_consecutive_losses(trades)
    consecutive_wins = _count_consecutive_wins(trades)
    rolling_trades = trades[: cfg["rolling_pnl_window"]]
    rolling_net_pnl = sum((t.get("net_pnl") or 0) for t in rolling_trades)

    # Cooldown check
    feedback_state = redis.get_feedback_state() or {}
    last_adj_str = feedback_state.get("last_adjustment_ts")
    cooldown_ok = True
    if last_adj_str:
        try:
            last_adj = datetime.fromisoformat(last_adj_str)
            if last_adj.tzinfo is None:
                last_adj = last_adj.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_adj).total_seconds() / 3600
            cooldown_ok = hours_since >= cfg["cooldown_hours"]
        except (ValueError, TypeError):
            pass

    ttl_seconds = int(cfg["feedback_ttl_hours"] * 3600)
    current_threshold = redis.get_feedback_entry_threshold() or cfg["threshold_baseline"]
    current_scale = redis.get_feedback_regime_scale() or 1.0

    triggered = (
        consecutive_losses >= cfg["consecutive_loss_trigger"]
        or rolling_net_pnl < 0
    )

    result: dict = {
        "consecutive_losses": consecutive_losses,
        "consecutive_wins": consecutive_wins,
        "rolling_net_pnl": round(rolling_net_pnl, 2),
        "current_threshold": current_threshold,
        "current_scale": current_scale,
        "triggered": triggered,
        "cooldown_ok": cooldown_ok,
        "adjusted": False,
        "recovered": False,
    }

    if triggered and cooldown_ok:
        new_threshold = min(current_threshold + cfg["threshold_step"], cfg["threshold_max"])
        new_scale = max(current_scale * cfg["regime_scale_factor"], cfg["regime_min_scale"])

        redis.set_feedback_entry_threshold(new_threshold, ttl=ttl_seconds)
        redis.set_feedback_regime_scale(new_scale, ttl=ttl_seconds)

        now_iso = datetime.now(timezone.utc).isoformat()
        redis.set_feedback_state({
            "last_adjustment_ts": now_iso,
            "reason": "triggered",
            "consecutive_losses": consecutive_losses,
            "rolling_net_pnl": round(rolling_net_pnl, 2),
            "threshold_before": current_threshold,
            "threshold_after": new_threshold,
            "scale_before": current_scale,
            "scale_after": new_scale,
        }, ttl=ttl_seconds)

        result["adjusted"] = True
        result["new_threshold"] = new_threshold
        result["new_scale"] = new_scale

        log.warning(
            "Loss feedback triggered: %d consecutive losses, rolling P&L $%.2f — "
            "threshold %.2f→%.2f, regime scale %.2f→%.2f",
            consecutive_losses, rolling_net_pnl,
            current_threshold, new_threshold,
            current_scale, new_scale,
        )

        reason_parts = []
        if consecutive_losses >= cfg["consecutive_loss_trigger"]:
            reason_parts.append(f"{consecutive_losses} consecutive losses")
        if rolling_net_pnl < 0:
            reason_parts.append(f"rolling P&L ${rolling_net_pnl:.2f}")
        reason_str = " + ".join(reason_parts)

        msg = (
            f"⚠️ *Loss Feedback Triggered*\n"
            f"Reason: {reason_str}\n"
            f"ENTRY\\_THRESHOLD: {current_threshold:.2f} → {new_threshold:.2f}\n"
            f"Regime scale: {current_scale:.2f} → {new_scale:.2f}\n"
            f"_Adjustments active for {cfg['feedback_ttl_hours']}h_"
        )
        try:
            notifier = TelegramNotifier()
            run_async(notifier.send_alert(msg, level="warning"))
        except Exception as exc:
            log.warning("Telegram alert failed for loss feedback: %s", exc)

    elif not triggered and consecutive_wins >= cfg["recovery_win_streak"]:
        # Recovery: step threshold back toward baseline
        if current_threshold > cfg["threshold_baseline"]:
            new_threshold = max(current_threshold - cfg["threshold_step"], cfg["threshold_baseline"])
            new_scale = min(current_scale / cfg["regime_scale_factor"], 1.0)

            redis.set_feedback_entry_threshold(new_threshold, ttl=ttl_seconds)
            redis.set_feedback_regime_scale(new_scale, ttl=ttl_seconds)

            redis.set_feedback_state({
                "last_adjustment_ts": datetime.now(timezone.utc).isoformat(),
                "reason": "recovery",
                "consecutive_wins": consecutive_wins,
                "threshold_before": current_threshold,
                "threshold_after": new_threshold,
                "scale_before": current_scale,
                "scale_after": new_scale,
            }, ttl=ttl_seconds)

            result["recovered"] = True
            result["new_threshold"] = new_threshold
            result["new_scale"] = new_scale

            log.info(
                "Loss feedback recovery: %d consecutive wins — threshold %.2f→%.2f, scale %.2f→%.2f",
                consecutive_wins, current_threshold, new_threshold, current_scale, new_scale,
            )

            if new_threshold <= cfg["threshold_baseline"]:
                msg = (
                    f"✅ *Loss Feedback Reset*\n"
                    f"{consecutive_wins} consecutive wins — threshold back to baseline {new_threshold:.2f}\n"
                    f"Regime scale restored to {new_scale:.2f}"
                )
                try:
                    notifier = TelegramNotifier()
                    run_async(notifier.send_alert(msg, level="info"))
                except Exception as exc:
                    log.warning("Telegram alert failed for feedback recovery: %s", exc)

    redis.close()
    return result


# ---------------------------------------------------------------------------
# Counterfactual / Opportunity Cost — Phase C
# ---------------------------------------------------------------------------

_COUNTERFACTUAL_HORIZON_MIN = 60  # forward window in minutes


def _compute_1h_return(
    bars_by_minute: dict,
    tick_time: datetime,
    horizon_min: int = _COUNTERFACTUAL_HORIZON_MIN,
) -> float | None:
    """Compute (price_at_T+horizon - price_at_T) / price_at_T from a minute-bar dict.

    Args:
        bars_by_minute: {truncated_minute_utc: close_price}
        tick_time: decision timestamp (UTC)
        horizon_min: forward window in minutes

    Returns:
        Float return, or None if bars unavailable at T or T+horizon.
    """
    def _floor_minute(ts: datetime) -> datetime:
        return ts.replace(second=0, microsecond=0)

    entry_key = _floor_minute(tick_time)
    exit_key = _floor_minute(tick_time + timedelta(minutes=horizon_min))

    entry_price = bars_by_minute.get(entry_key)
    exit_price = bars_by_minute.get(exit_key)

    if entry_price is None or exit_price is None or entry_price == 0:
        return None
    return (exit_price - entry_price) / entry_price


@app.task(name="src.workers.performance.run_counterfactual_worker")
def run_counterfactual_worker() -> dict:
    """Compute 1-hour counterfactual returns for trade-filter skip decisions.

    For each skipped decision, answers: "if we had entered at tick_time,
    what would the 1-hour return have been?"

    Includes SKIP_THRESHOLD because the live portfolio path now enforces the
    feedback gate there. Excludes freshness/fallback skips: stale or fallback-only
    signals are data-quality/reliability issues, not filters to relax for alpha.

    Scheduled daily at 22:45 UTC (after market close and forward-return worker).
    Only processes decisions from the last 7 days with no counterfactual yet.

    Returns:
        Dict: updated, skipped_no_data, errors, total_decisions.
    """
    import psycopg2
    from collections import defaultdict
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    stats: dict = {"updated": 0, "skipped_no_data": 0, "errors": 0, "total_decisions": 0}
    started_at = datetime.now(timezone.utc)

    def _record_run(status: str, reason: str | None = None) -> None:
        state = {
            "last_run_at": started_at.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "reason": reason,
            **stats,
        }
        store = RedisStore()
        try:
            store.set_counterfactual_worker_state(state)
        finally:
            store.close()

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping counterfactual worker")
        _record_run("skipped", "no_credentials")
        return {**stats, "skipped": True, "reason": "no_credentials"}

    pg_conn = psycopg2.connect(config.DATABASE_URL)
    pg = PostgreSQLStore(conn=pg_conn)

    try:
        rows = pg.fetch_skip_decisions_without_counterfactual(days_back=7, limit=500)
        if not rows:
            log.info("No SKIP decisions pending counterfactual")
            _record_run("ok", "no_pending_decisions")
            return stats

        stats["total_decisions"] = len(rows)
        log.info("Counterfactual worker: %d decisions to process", len(rows))

        # Group by symbol to minimise Alpaca API calls.
        by_symbol: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_symbol[row["symbol"]].append(row)

        data_client = StockHistoricalDataClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
        )

        computed_at = datetime.now(timezone.utc)
        updates: list[tuple] = []  # (decision_id, return_1h_or_None, computed_at)

        for symbol, decisions in by_symbol.items():
            try:
                tick_times = [
                    d["tick_time"] if d["tick_time"].tzinfo is not None
                    else d["tick_time"].replace(tzinfo=timezone.utc)
                    for d in decisions
                ]
                start = min(tick_times) - timedelta(minutes=5)
                end = max(tick_times) + timedelta(minutes=_COUNTERFACTUAL_HORIZON_MIN + 10)

                req = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Minute,
                    start=start,
                    end=end,
                )
                bars_df = data_client.get_stock_bars(req).df

                if bars_df.empty:
                    log.debug("No 1-min bars for %s — marking as no_data", symbol)
                    for d in decisions:
                        updates.append((d["id"], None, computed_at))
                    stats["skipped_no_data"] += len(decisions)
                    continue

                # Flatten multi-index (symbol, timestamp) → timestamp only.
                if hasattr(bars_df.index, "levels"):
                    sym_vals = bars_df.index.get_level_values(0)
                    if symbol in sym_vals:
                        bars_df = bars_df.loc[symbol]
                    else:
                        for d in decisions:
                            updates.append((d["id"], None, computed_at))
                        stats["skipped_no_data"] += len(decisions)
                        continue

                bars_df = bars_df.sort_index()

                # Build minute → close lookup with UTC-normalised keys.
                bars_by_minute: dict[datetime, float] = {}
                for idx, row in bars_df.iterrows():
                    ts = idx if hasattr(idx, "tzinfo") else idx.to_pydatetime()
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    key = ts.replace(second=0, microsecond=0)
                    bars_by_minute[key] = float(row["close"])

                for d in decisions:
                    tick = d["tick_time"]
                    if tick.tzinfo is None:
                        tick = tick.replace(tzinfo=timezone.utc)
                    ret = _compute_1h_return(bars_by_minute, tick)
                    updates.append((d["id"], ret, computed_at))
                    if ret is None:
                        stats["skipped_no_data"] += 1
                    else:
                        stats["updated"] += 1

            except Exception as e:
                log.warning("Counterfactual: failed to fetch bars for %s — %s", symbol, e)
                for d in decisions:
                    updates.append((d["id"], None, computed_at))
                stats["errors"] += len(decisions)

        if updates:
            pg.bulk_set_counterfactual(updates)

        log.info(
            "Counterfactual worker complete: updated=%d skipped=%d errors=%d",
            stats["updated"], stats["skipped_no_data"], stats["errors"],
        )
        _record_run("ok")

    except Exception as exc:
        _record_run("error", str(exc))
        raise
    finally:
        pg_conn.close()

    return stats

@app.task(name="src.workers.performance.run_daily_trading_analysis")
def run_daily_trading_analysis(target_date: str | None = None) -> dict:
    """Replaced by scheduled Claude Code session (daily at 07:00 CEST, weekdays).
    Kept as no-op so any queued tasks don't crash the worker.
    """
    log.info("run_daily_trading_analysis: replaced by Claude Code scheduled session — skipping")
    stats_out = {"skipped": True, "reason": "replaced_by_claude_code"}
    log.info("Daily trading analysis complete: %s", stats_out)
    return stats_out
