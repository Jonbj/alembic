"""Celery task: run portfolio orchestration cycle at market open.

Scheduled: Mon-Fri 14:00-21:00 UTC (hourly) via Celery beat.

Cycle flow:
    1. Check kill-switch (halt immediately if active).
    2. Build StrategyRegistry + initialize strategy callables.
    3. Build PortfolioOrchestrator with ConstraintEnforcer + VolTargeter.
    4. Call orchestrator.run_cycle() with current market data.
    5. Check portfolio drawdown cap — activate kill-switch + Telegram alert if breached.
    6. Submit final orders to Alpaca and persist cycle result.
    7. Back-fill Alpaca order_ids on execution_decisions rows.
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.notifications.base import AlertLevel
from src.portfolio.whipsaw_damping import evaluate_whipsaw_damping
from src.workers.celery_app import app

_PEAK_EQUITY_KEY = "portfolio:peak_equity"

log = logging.getLogger(__name__)

_PRICE_BARS = 300

# P1-B: In-memory cache for fractionable asset flags (refreshed every 24h per worker process).
import time as _time
_FRACTIONABLE_CACHE: dict[str, bool] = {}
_FRACTIONABLE_CACHE_TS: float = 0.0
_FRACTIONABLE_CACHE_TTL: float = 86400.0


def _portfolio_postmortem(
    pg_store,
    trade_id: int,
    signal: dict,
    score: float,
    entry_price: float,
    exit_price: float,
    tick_time,
) -> None:
    """Run postmortem diagnosis on a portfolio-flow exit and persist it.

    Mirrors execution.py's _maybe_postmortem() but without regime lookup
    (the portfolio cycle doesn't apply regime gating, so regime="risk_on").
    """
    from src.performance.postmortem import TradeContext, diagnose_loss, should_trigger_postmortem

    # If entry_price is 0 (Alpaca positions failed to load), fall back to the
    # reconciled entry_price from the DB trade record.
    if entry_price <= 0 and trade_id:
        try:
            _trade_rec = pg_store.fetch_trade_with_signal(trade_id)
            if _trade_rec and _trade_rec.get("entry_price"):
                entry_price = float(_trade_rec["entry_price"])
        except Exception:
            pass

    loss_pct = (entry_price - exit_price) / entry_price if entry_price > 0 else 0.0
    confidence = float(signal.get("confidence", 0.5))
    ensemble_std = float(signal.get("ensemble_std", 0.0))

    if not should_trigger_postmortem(loss_pct, score, ensemble_std):
        return

    ctx = TradeContext(
        loss_pct=loss_pct,
        signal_score=score,
        signal_confidence=confidence,
        ensemble_std=ensemble_std,
        regime="risk_on",
        reasoning_summary="",
    )
    diagnosis = diagnose_loss(ctx)
    try:
        pg_store.write_postmortem(trade_id, diagnosis)
    except Exception as exc:
        log.warning("Failed to write postmortem for trade %s: %s", trade_id, exc)


def _filter_approved_strategies(
    entries: list,
    db_conn,
) -> list:
    """Return only the strategies that are operationally approved in strategy_lifecycle.

    Approval semantics:
    - Row exists + approved=True  → admitted.
    - Row exists + approved=False → excluded (fail-closed: explicitly not approved).
    - Row absent (None)           → admitted with warning (fail-open: legacy strategy,
                                    no lifecycle row seeded yet).
    - DB error                    → excluded (fail-closed: cannot verify approval state).

    This function is a module-level helper so tests can inject a mock db_conn
    without triggering the full Celery task infrastructure.
    """
    from src.strategies.promotion import is_strategy_operationally_approved

    approved: list = []
    for entry in entries:
        try:
            # Peek at the raw lifecycle row to distinguish "absent" from "approved=False".
            with db_conn.cursor() as cur:
                cur.execute(
                    "SELECT approved FROM strategy_lifecycle WHERE strategy_id = %s",
                    (entry.strategy_id,),
                )
                row = cur.fetchone()

            if row is None:
                # No lifecycle row — fail-open: legacy strategy, admit with warning.
                log.warning(
                    "Strategy %s: no strategy_lifecycle row found — admitted as legacy "
                    "(fail-open). Seed the lifecycle table to enable promotion gate.",
                    entry.strategy_id,
                )
                approved.append(entry)
            else:
                # Support both dict-like (RealDictCursor) and positional tuple rows.
                try:
                    approved_val = row["approved"]
                except (TypeError, KeyError):
                    approved_val = row[0]

                if approved_val:
                    # Row present, approved=True.
                    approved.append(entry)
                else:
                    # Row present, approved=False — fail-closed.
                    log.warning(
                        "Strategy %s: approved=False in strategy_lifecycle — excluded from cycle. "
                        "Call approve_promotion() to clear the gate.",
                        entry.strategy_id,
                    )
        except Exception as exc:
            # DB error — fail-closed: cannot verify, must not admit.
            log.warning(
                "Strategy %s: DB error during approval check (%s) — excluded (fail-closed).",
                entry.strategy_id, exc,
            )
    return approved


def _fire_alert(notifier, message: str, level: AlertLevel) -> None:
    if notifier is None:
        return
    try:
        asyncio.run(notifier.send_alert(message, level=level))
    except Exception as exc:
        log.warning("Telegram alert send failed: %s", exc)


def _divergence_alert_enabled() -> bool:
    """Read notifications.send_signal_order_divergence_alert from config/trading.yaml.

    Default false (2026-07-15): suppress the recurring "Signal/order divergence:
    signals=..." Telegram noise. The divergence is still detected by
    _check_divergence_and_alert; only the Telegram WARNING send is gated. Flip the
    flag to true to re-enable. Isolated as a helper so tests can patch it.
    """
    try:
        import yaml
        _ty = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
        with open(_ty) as _f:
            return bool(
                ((yaml.safe_load(_f) or {}).get("notifications") or {})
                .get("send_signal_order_divergence_alert", False)
            )
    except Exception:
        return False


def _fill_divergence_alert_enabled() -> bool:
    """Read notifications.send_fill_divergence_alert from config/trading.yaml.

    Default false (2026-07-15): suppress the recurring "Execution fill divergence:
    N/M orders submitted" Telegram noise. On the live book this alert fires almost
    every cycle as a false positive — when the anti-pyramiding guard (P0-05)
    skips redundant re-BUYs for already-held symbols, submitted_count drops to 0
    while final_count stays high, and the detector flags it as a divergence even
    though the suppression is intentional and correct. The divergence is still
    detected by _check_divergence_and_alert; only the Telegram WARNING send is
    gated. Flip the flag to true to re-enable. Isolated as a helper so tests can
    patch it.
    """
    try:
        import yaml
        _ty = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"
        with open(_ty) as _f:
            return bool(
                ((yaml.safe_load(_f) or {}).get("notifications") or {})
                .get("send_fill_divergence_alert", False)
            )
    except Exception:
        return False


def _check_divergence_and_alert(
    signal_syms: set,
    order_syms: set,
    submitted_count: int,
    final_count: int,
    notifier,
) -> None:
    """Fire Telegram WARNING alerts when signal/execution divergence thresholds are exceeded (P2-04).

    Two checks:
    1. Signal/order symbol divergence — Jaccard overlap of signal_syms vs order_syms.
       Alert fires when overlap < 0.8 (check_signal_divergence threshold).
    2. Execution fill divergence — |fill_ratio - 1.0| > 0.20 where
       fill_ratio = submitted_count / final_count.  Alert fires when fewer than
       80% of intended orders were actually submitted to the broker.

    Both alerts are WARNING level (not CRITICAL) — they indicate anomalies that
    warrant review but do not automatically halt trading.
    """
    from src.monitoring.alerts import check_signal_divergence, check_execution_divergence

    if check_signal_divergence(signal_syms, order_syms):
        # Gated by notifications.send_signal_order_divergence_alert in
        # config/trading.yaml (default false: suppress the recurring
        # "Signal/order divergence: signals=..." Telegram noise, P2-04). The
        # divergence is still detected here; only the Telegram WARNING send is
        # gated. Flip the flag to true to re-enable the alert.
        if _divergence_alert_enabled():
            _fire_alert(
                notifier,
                f"Signal/order divergence: signals={sorted(signal_syms)}, orders={sorted(order_syms)}",
                AlertLevel.WARNING,
            )

    # Skip fill-divergence check when no orders were generated: 0/0 is not a divergence,
    # it means the cycle had nothing to trade (signals below threshold, market closed, etc.).
    if final_count > 0:
        fill_ratio = submitted_count / final_count
        if check_execution_divergence(fill_ratio, 1.0):
            # Gated by notifications.send_fill_divergence_alert (default false) — on the
            # live book this fires as a false positive whenever the anti-pyramiding guard
            # skips redundant re-BUYs (submitted=0, final_count high). Detection still
            # runs; only the Telegram WARNING send is suppressed. Flip the flag to re-enable.
            if _fill_divergence_alert_enabled():
                _fire_alert(
                    notifier,
                    f"Execution fill divergence: {submitted_count}/{final_count} orders submitted",
                    AlertLevel.WARNING,
                )


def _emergency_cancel_all(api_key: str, secret_key: str, paper: bool) -> None:
    """Cancel all pending Alpaca orders. Called from kill-switch path before aborting cycle."""
    from alpaca.trading.client import TradingClient as _TC
    try:
        _tc = _TC(api_key=api_key, secret_key=secret_key, paper=paper)
        _tc.cancel_orders()
        log.warning("EMERGENCY: cancelled all pending Alpaca orders (kill-switch active)")
    except Exception as exc:
        log.warning("EMERGENCY cancel_orders failed: %s", exc)


def _is_ks_active_failclosed(redis_url: str) -> bool:
    """Return True if kill-switch is active, or if Redis is unreachable (fail-closed, P0-06).

    Used for the pre-submission re-check: if we cannot verify the kill-switch is clear,
    we assume it is active and skip order submission rather than risk trading while halted.
    """
    try:
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            return bool(_r.get("killswitch_active")) or bool(_r.get("system:halted_by_operator"))
        finally:
            _r.close()
    except Exception as _ks_exc:
        log.warning("P0-06: Kill-switch re-check failed (%s) — fail-closed, skipping submission", _ks_exc)
        return True


# Deterministic VIX→multiplier fallback used when regime:current is absent.
# The LLM-derived regime (regime:current) requires both a FRED macro fetch and the
# Ollama ensemble to succeed; when either is unavailable the key is never written and
# sizing would otherwise collapse to a flat ×0.2 regardless of actual market calm.
# This map keeps sizing risk-proportional from VIX alone (no LLM required). The ×0.2
# floor still applies when even VIX is unknown.
_REGIME_VIX_FALLBACK: tuple[tuple[float, float], ...] = (
    (20.0, 1.0),   # VIX < 20  → calm      → ×1.0
    (30.0, 0.7),   # 20–30     → elevated  → ×0.7
    (40.0, 0.4),   # 30–40     → stressed  → ×0.4
)
_REGIME_VIX_FLOOR = 0.2  # VIX ≥ 40, or VIX unknown → ×0.2 (fail-conservative)


def _vix_fallback_multiplier(vix: float | None) -> float:
    """Map a VIX level to a deterministic sizing multiplier (no LLM required)."""
    if vix is None:
        return _REGIME_VIX_FLOOR
    for threshold, mult in _REGIME_VIX_FALLBACK:
        if vix < threshold:
            return mult
    return _REGIME_VIX_FLOOR


def _get_regime_multiplier_from_redis(redis_url: str) -> float:
    """Read regime multiplier from Redis key regime:current (P0-09).

    Resolution order:
      1. regime:current present → use its LLM-derived multiplier.
      2. regime:current absent  → deterministic VIX fallback from macro:vix:latest.
      3. VIX also absent / any error → ×0.2 (fail-conservative).

    Never returns 1.0 blindly: ×1.0 only when VIX is present and benign (<20).
    """
    try:
        import json as _rj
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            raw = _r.get("regime:current")
            vix_raw = _r.get("macro:vix:latest") if raw is None else None
        finally:
            _r.close()
        if raw is not None:
            data = _rj.loads(raw)
            return float(data["multiplier"])
        vix: float | None = None
        if vix_raw is not None:
            try:
                vix = float(vix_raw)
            except (TypeError, ValueError):
                vix = None
        mult = _vix_fallback_multiplier(vix)
        log.warning(
            "P0-09: regime:current absent — deterministic VIX fallback ×%.2f (vix=%s)",
            mult, f"{vix:.1f}" if vix is not None else "absent",
        )
        return mult
    except Exception as _exc:
        log.warning("P0-09: Could not read regime multiplier (%s) — using fallback (×0.2)", _exc)
        return 0.2


_TRADING_YAML = Path(__file__).resolve().parents[2] / "config" / "trading.yaml"


def _peak_and_drawdown(raw_peak: float | None, equity: float) -> tuple[float, float]:
    """Return (peak_equity, drawdown_fraction) for the drawdown-cap kill-switch.

    Seeds peak = equity on the first observation (raw_peak is None — e.g. an
    unset/expired Redis key). Bug 2026-07-22: the old inline logic defaulted
    peak to equity but only persisted it on ``equity > peak`` — never true on an
    empty key — so the peak never seeded, drawdown stayed 0, and the cap could
    never fire. The caller persists the returned peak every cycle so it always
    survives.
    """
    peak = equity if raw_peak is None else max(raw_peak, equity)
    drawdown = (peak - equity) / peak if peak > 0 else 0.0
    return peak, drawdown


def _build_f8_shadow_rows(cycle_ts, feedback_shadow: dict | None) -> list[dict]:
    """Turn CycleResult.feedback_shadow into f8_regime_scale_shadow rows (#32).

    One row per scaled strategy. The F8 shadow was previously only logged +
    kept in a 48h-TTL Redis key, so no trajectory survived for the flip
    decision. Persisting it per cycle makes the evidence a look-up, matching
    the #61/#71 shadow pattern. Missing numeric fields default to None so a
    malformed entry never crashes the cycle.
    """
    if not feedback_shadow:
        return []
    rows = []
    for strategy, s in feedback_shadow.items():
        rows.append({
            "cycle_ts": cycle_ts,
            "strategy": strategy,
            "scale": s.get("scale"),
            "unscaled_weight": s.get("unscaled_weight"),
            "scaled_weight": s.get("scaled_weight"),
            "applied": s.get("applied"),
        })
    return rows


def _read_feedback_regime_scales(redis_url: str, strategy_ids) -> dict[str, float]:
    """Read per-strategy feedback:regime_scale:S* (F8 de-risk/re-risk throttle).

    Returns {strategy_id: scale} for strategies with a non-identity scale set.
    The legacy key ``feedback:regime_scale`` (no suffix) is the fallback when a
    per-strategy key is absent. Fail-open: any error → {} → no de-risking applied
    (safe default; the orchestrator then sees an empty dict and applies 1.0
    everywhere, i.e. zero behavior change).

    The scheduler passes this dict to the orchestrator. Whether it is *applied*
    (vs shadow-only) is gated by ``loss_feedback.apply_regime_scale``.
    """
    if not strategy_ids:
        return {}
    try:
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            out: dict[str, float] = {}
            legacy: str | None = None  # lazily read once
            for sid in strategy_ids:
                raw = _r.get(f"feedback:regime_scale:{sid}")
                if raw is None:
                    if legacy is None:
                        legacy = _r.get("feedback:regime_scale")
                    raw = legacy
                if raw is None:
                    continue
                try:
                    scale = float(raw)
                except (TypeError, ValueError):
                    continue
                if abs(scale - 1.0) > 1e-9:
                    out[sid] = scale
            return out
        finally:
            _r.close()
    except Exception as _exc:
        log.warning(
            "F8: could not read feedback:regime_scale (%s) — no de-risking applied",
            _exc,
        )
        return {}


def _build_vol_targeter():
    """Construct the PortfolioVolTargeter from config/trading.yaml `vol_target` (F6).

    Co-locates the config read with the targeter so target_vol / clamp are
    calibratable without a code change. Defaults = status quo (zero behavior
    change). Returns (targeter, cfg) so the caller can log the active config.
    measure-before-enforce (QX-01): do not raise target_vol without a read-only
    replay shadow (scripts/audit_deployment_decomposition.py) confirming the
    implied vol band and headroom under max_portfolio_exposure at regime_mult=1.0.
    """
    from src.portfolio.vol_targeting import PortfolioVolTargeter, load_vol_target_config
    cfg = load_vol_target_config()
    return PortfolioVolTargeter(**cfg), cfg


def _get_fractionable_symbols(trading_client) -> set[str]:
    """Return set of symbols that support fractional/notional orders.

    Results are cached in-memory for 24h per worker process to avoid N API
    calls per cycle. Falls back to treating all symbols as fractionable on error.
    """
    global _FRACTIONABLE_CACHE, _FRACTIONABLE_CACHE_TS
    now = _time.monotonic()
    if _FRACTIONABLE_CACHE and (now - _FRACTIONABLE_CACHE_TS) < _FRACTIONABLE_CACHE_TTL:
        return {sym for sym, ok in _FRACTIONABLE_CACHE.items() if ok}
    try:
        from alpaca.trading.requests import GetAssetsRequest
        from alpaca.trading.enums import AssetStatus
        assets = trading_client.get_all_assets(GetAssetsRequest(status=AssetStatus.ACTIVE))
        _FRACTIONABLE_CACHE = {a.symbol: bool(a.fractionable) for a in assets if a.symbol}
        _FRACTIONABLE_CACHE_TS = now
        log.debug("P1-B: loaded fractionable flags for %d assets", len(_FRACTIONABLE_CACHE))
    except Exception as exc:
        log.warning("P1-B: failed to load fractionable assets: %s — assuming all fractionable", exc)
    return {sym for sym, ok in _FRACTIONABLE_CACHE.items() if ok}


def _sync_fractional_protective_stops(trading_client, stop_policy, cycle_ts) -> dict:
    """#62/#63: reconcile broker-side protective stops for fractional positions.

    Alpaca rejects bracket orders on fractional/notional quantities, so
    fractionable positions (100% of the book as of 2026-07-16) carry no
    broker-side floor from the BUY-time bracket path. This runs once per
    cycle, idempotently: re-derives the desired stop (whole-share floor of
    the current position, d_hard trigger from avg_entry_price) and only
    touches the broker when it's missing or stale. Never raises — a failure
    here must not block order submission.
    """
    from alpaca.trading.enums import OrderSide as _OrderSideEnum
    from alpaca.trading.enums import OrderType as _OrderTypeEnum
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    from src.portfolio.fractional_stop_orders import (
        ExistingStopOrder,
        build_protective_stop_plans,
        execute_protective_stop_plans,
    )

    try:
        positions = trading_client.get_all_positions()
    except Exception as exc:
        log.warning("Fractional protective stop sync: failed to fetch positions: %s", exc)
        return {"skipped": "positions_fetch_failed"}

    try:
        open_orders = trading_client.get_orders(
            GetOrdersRequest(status=QueryOrderStatus.OPEN, side=_OrderSideEnum.SELL)
        )
    except Exception as exc:
        log.warning("Fractional protective stop sync: failed to fetch open orders: %s", exc)
        return {"skipped": "orders_fetch_failed"}

    stop_orders_by_symbol: dict[str, list[ExistingStopOrder]] = {}
    for o in open_orders:
        if getattr(o, "type", None) != _OrderTypeEnum.STOP:
            continue
        stop_orders_by_symbol.setdefault(o.symbol, []).append(
            ExistingStopOrder(id=str(o.id), qty=float(o.qty), stop_price=float(o.stop_price))
        )

    plans = build_protective_stop_plans(positions, stop_orders_by_symbol, stop_policy, cycle_ts)
    summary = execute_protective_stop_plans(plans, trading_client)
    if summary.get("created") or summary.get("replaced") or summary.get("errors"):
        log.info("Fractional protective stop sync: %s", summary)
    return summary


def _load_execution_engine() -> str:
    """Return execution.engine from trading.yaml; defaults to 'portfolio'."""
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("execution", {}).get("engine", "portfolio")
    except Exception as exc:
        log.warning("Could not load execution.engine (%s) — defaulting to portfolio", exc)
        return "portfolio"


_S4_FIRED_SIGNALS_TTL = 108_000  # 30 hours — auto-expires after session date


def _preserve_stale_signals_for_open_positions(
    fresh_signals: list,
    stale_signals: list,
    open_symbols: set,
) -> list:
    """Re-admit stale positive signals when the symbol has an open position and no counter-signal.

    FIX-D (Day 2): a signal expiry (max_signal_age_hours exceeded) is not the same
    as a counter-signal. When AMD's BUY signal aged out at 19:16 UTC, the portfolio
    set its weight to 0 → portfolio_sell at the next cycle, triggering a roundtrip
    loss. Signal expiry means "no new information", not "exit". Only a fresh negative
    signal or a stop-loss breach should close a position.

    Rule: if a stale signal has score > 0 AND its symbol has an open DB trade AND no
    fresh signal (counter-signal) exists for the same symbol → re-add it so the
    portfolio retains the current weight rather than dropping to zero.
    """
    fresh_syms = {s.symbol for s in fresh_signals}
    preserved = []
    for sig in stale_signals:
        if sig.score > 0 and sig.symbol in open_symbols and sig.symbol not in fresh_syms:
            preserved.append(sig)
    return fresh_signals + preserved


def _classify_zero_weight_exit(
    last_signal: dict | None,
    max_age_hours: int,
) -> str:
    """Classify why a weight-0 S4 SELL happened: "no_signal" | "expired" | "whipsaw".

    #60: a structured tag alongside the free-text reason (`_reason_for_zero_weight_sell`)
    so downstream measurement (#61 anti-whipsaw damping) doesn't need to parse free
    text to tell the 3 cases apart. Same boundary rule as the reason text: age strictly
    greater than max_age_hours is "expired", otherwise a fresh-but-weak signal is
    "whipsaw".

    Args:
        last_signal: dict with "generated_at" (datetime) and "score" (float), or None.
        max_age_hours: S4 max_signal_age_hours threshold (default 4).
    """
    if last_signal is None:
        return "no_signal"
    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)
    age_h = (now_utc - last_signal["generated_at"]).total_seconds() / 3600
    return "expired" if age_h > max_age_hours else "whipsaw"


def _reason_and_mechanism_for_non_s4_weight_drop(
    symbol: str,
    origin_strategy: str,
    wt_pct: str,
) -> tuple[str, str]:
    """#72: origin-aware reason/tag for a weight-0 SELL on a non-S4 position.

    _classify_zero_weight_exit/_reason_for_zero_weight_sell only ever check
    the S4 sentiment-signals table, so they ALWAYS tag a non-S4-origin
    position "[no_signal]" — trivially true (it never had an S4 signal to
    begin with) but misleading, and it over-counts [no_signal] in #61's
    flip-decision measurement. Real incident: SBUX trades 348/360
    (2026-07-17), verified S1 momentum entries, tagged [no_signal].

    Returns (exit_mechanism, reason_text).
    """
    exit_mechanism = f"{origin_strategy.lower()}_weight_drop"
    reason = (
        f"[{exit_mechanism}] {origin_strategy} target weight dropped to 0% "
        f"— position closed (not an S4 exit; portfolio weight {wt_pct})."
    )
    return exit_mechanism, reason


def _reason_for_zero_weight_sell(
    symbol: str,
    last_signal: dict | None,
    max_age_hours: int,
) -> str:
    """Return an informative decision-log reason for a SELL order with weight 0.0%.

    FIX-F (Day 3): "Portfolio rebalance: weight 0.0%" gave no indication of why the
    weight dropped to zero. For stale-signal SELLs (CAT/TSM on 2026-06-25) the true
    cause is signal expiry overnight — visible here as age > max_age_hours — not an
    operator rebalance or a counter-signal.

    #60: each branch is prefixed with the same tag `_classify_zero_weight_exit`
    returns ("[no_signal]" / "[expired]" / "[whipsaw]"), so the reason text and the
    structured `exit_mechanism` column always agree.

    Args:
        symbol: ticker being sold.
        last_signal: dict with "generated_at" (datetime) and "score" (float), or None.
        max_age_hours: S4 max_signal_age_hours threshold (default 4).
    """
    if last_signal is None:
        return (
            f"[no_signal] Portfolio rebalance: weight 0.0% — no S4 signal found in DB "
            f"(signal may be older than the lookback window or never generated)."
        )
    from datetime import datetime as _dt, timezone as _tz
    now_utc = _dt.now(_tz.utc)
    age_h = (now_utc - last_signal["generated_at"]).total_seconds() / 3600
    gen_str = last_signal["generated_at"].strftime("%Y-%m-%d %H:%M UTC")
    score = last_signal.get("score", 0.0)

    if age_h > max_age_hours:
        return (
            f"[expired] S4 signal expired (age={age_h:.1f}h > max_age={max_age_hours}h, "
            f"generated {gen_str}, score={score:+.3f}): "
            f"weight 0.0% — no counter-signal found, position closed."
        )
    # Signal is technically fresh but weight is still 0 (e.g. score below min_score,
    # or the portfolio constraint forced it out). Show score so log is actionable.
    return (
        f"[whipsaw] Portfolio rebalance: weight 0.0% — S4 signal present but not driving a position "
        f"(score={score:+.3f}, age={age_h:.1f}h, generated {gen_str})."
    )


def _log_constraint_block_if_needed(result, risk_cfg: dict) -> None:
    """Emit a CONSTRAINT_BLOCK warning when all pre-constraint orders are eliminated.

    FIX-E (Day 2): when only 1 symbol passed the feedback gate (max_single_asset_pct=10%
    requires ≥10 symbols for diversification), the portfolio cycle logged "0 final orders"
    with no explanation. This function surfaces the constraint names and minimum symbol
    count so the log is actionable.
    """
    if result.orders_before_constraints > 0 and len(result.final_orders) == 0:
        max_single = risk_cfg.get("max_single_asset_pct", 0.10)
        min_syms = int(1.0 / max_single) if max_single > 0 else "?"
        fired = sorted(result.constraints_fired) if result.constraints_fired else ["unknown"]
        log.warning(
            "CONSTRAINT_BLOCK: %d strategy signal(s) → 0 orders after constraints. "
            "Fired: %s. Diversification requires ≥%s symbols (max_single_asset_pct=%.0f%%).",
            result.orders_before_constraints,
            fired,
            min_syms,
            max_single * 100,
        )


def _filter_stale_signals(
    signals: list,
    max_age_hours: int,
    now_utc,
) -> tuple[list, list]:
    """Split signals into (fresh, stale) by comparing generated_at to now_utc.

    Signals with generated_at more than max_age_hours before now_utc are stale.
    Clock-skew (slightly future generated_at) is treated as age=0 (not stale).
    """
    fresh, stale = [], []
    for sig in signals:
        age_seconds = (now_utc - sig.generated_at).total_seconds()
        if age_seconds > max_age_hours * 3600:
            stale.append(sig)
        else:
            fresh.append(sig)
    return fresh, stale


def _filter_fallback_signals(signals: list) -> tuple[list, list]:
    """Split signals into (non_fallback, fallback) by ``fallback_used``.

    #108: a BUY must not rest on a FinBERT-fallback signal — fallback fires when
    the ensemble is unavailable/diverged (low reliability, lesson from the SPCX
    −0.573 fallback → −20.23 loss on 2026-07-01). The reversal SELL path already
    excludes fallback signals; this mirrors that guard on the BUY/ranking side.
    """
    non_fallback, fallback = [], []
    for sig in signals:
        (fallback if getattr(sig, "fallback_used", False) else non_fallback).append(sig)
    return non_fallback, fallback


def _s4_signal_metadata_by_id(signal_ids: dict, signals_by_id: list[dict]) -> dict:
    """Map each symbol's score/reasoning/model_id to its RESOLVED ``signal_id``.

    #109: the logged S4 conviction must come from the same signal the decision
    links to. Previously the id (fetch_latest_signal_ids) and the score
    (fetch_signals_for_cycle) came from two independent "latest signal" queries
    that could resolve to different signals — WDC recorded signal_id=4427
    (finbert +0.363) with signal_score=−0.385 (stale ensemble). Keying on the
    resolved id makes the two impossible to desync.
    """
    by_id = {r["signal_id"]: r for r in signals_by_id}
    out: dict = {}
    for sym, sid in signal_ids.items():
        row = by_id.get(sid)
        if row is not None:
            out[sym] = {
                "score": row["score"],
                "reasoning": row["reasoning"],
                "model_id": row["model_id"],
            }
    return out


def _mark_stop_loss_today(redis_url: str, symbol: str) -> None:
    """Write stop_loss_today:{symbol} with TTL until midnight UTC.

    Prevents same-day re-entry after a stop-loss exit: the BUY guard reads
    this key and skips the symbol for the rest of the trading session.
    """
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = max(1, int((midnight - now).total_seconds()))
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            r.set(f"stop_loss_today:{symbol}", 1, ex=ttl)
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not mark stop-loss cooldown for %s: %s", symbol, exc)


def _get_stop_loss_cooldown_symbols(redis_url: str) -> set[str]:
    """Return symbols that were stopped out today (BUY blocked for rest of session)."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            keys = r.keys("stop_loss_today:*")
            return {k.split(":", 1)[1] for k in keys} if keys else set()
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not fetch stop-loss cooldown symbols: %s", exc)
        return set()


def _get_reversal_cooldown_symbols(redis_url: str) -> set[str]:
    """#68: symbols force-sold for sentiment reversal still in re-entry cooldown.

    Any strategy's BUY is blocked while the key lives (2026-07-16: S1 re-bought
    SOXX/INTC 15 min after every reversal exit, re-arming the churn loop)."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            keys = r.keys("reversal_cooldown:*")
            return {k.split(":", 1)[1] for k in keys} if keys else set()
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not fetch reversal cooldown symbols: %s", exc)
        return set()


def _get_s1_reentry_cooldown_symbols(redis_url: str) -> set[str]:
    """#71: symbols S1 excluded (weight dropped to 0 by S1's own signal) still
    in re-entry cooldown. Only S1's own BUY is blocked (see the check site) —
    unlike #68's reversal_cooldown, a genuine S4 conviction buy on the same
    name is a different signal and must not be vetoed by S1's own churn.
    Evidence: SBUX sold 14:37, S1 re-bought 14:52 (15 min flip, 2026-07-17);
    same week GE and XLF flipped within 1-2 cycles."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            keys = r.keys("s1_reentry_cooldown:*")
            return {k.split(":", 1)[1] for k in keys} if keys else set()
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not fetch S1 re-entry cooldown symbols: %s", exc)
        return set()


def _mark_s1_reentry_cooldown(redis_url: str, symbol: str, minutes: float) -> None:
    """#71: start (or refresh) the S1 re-entry cooldown for symbol. No-op if
    minutes <= 0 (cooldown disabled)."""
    if minutes <= 0:
        return
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            r.setex(f"s1_reentry_cooldown:{symbol}", int(minutes * 60), "1")
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not set S1 re-entry cooldown for %s: %s", symbol, exc)


_WHIPSAW_STREAK_TTL = 1800  # 30 min — ~2 cycles at 15-min cadence; a longer gap restarts the streak


def _get_whipsaw_streak(redis_url: str, symbol: str) -> int:
    """Return the current consecutive-whipsaw streak for symbol (0 if none/expired). #61."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            val = r.get(f"s4:whipsaw_streak:{symbol.upper()}")
            return int(val) if val is not None else 0
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not fetch whipsaw streak for %s: %s", symbol, exc)
        return 0


def _set_whipsaw_streak(redis_url: str, symbol: str, streak: int) -> None:
    """Persist (streak > 0) or clear (streak == 0) the consecutive-whipsaw streak. #61."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            key = f"s4:whipsaw_streak:{symbol.upper()}"
            if streak <= 0:
                r.delete(key)
            else:
                r.setex(key, _WHIPSAW_STREAK_TTL, str(streak))
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not persist whipsaw streak for %s: %s", symbol, exc)


def _update_last_good_sigma(redis_url: str, symbol: str, sigma: float | None) -> None:
    """Persist a non-default sigma_eff for future cycles when bars_df is sparse.

    Stored in Redis with 30-day TTL; StopPolicy's last_good_lookup reads it back
    as the second fallback tier (bars_df -> last_good -> asset_median -> tier -> default).
    """
    if sigma is None or sigma <= 0:
        return
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            r.setex(f"stop:last_good_sigma:{symbol.upper()}", 86400 * 30, str(float(sigma)))
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not update last_good sigma for %s: %s", symbol, exc)


def _last_good_sigma_lookup(redis_url: str):
    """Return a callable(symbol) -> sigma | None backed by Redis."""
    def _lookup(symbol: str) -> float | None:
        try:
            import redis as _redis
            r = _redis.Redis.from_url(redis_url, decode_responses=True)
            try:
                raw = r.get(f"stop:last_good_sigma:{symbol.upper()}")
                if raw is not None:
                    return float(raw)
            finally:
                r.close()
        except Exception as exc:
            log.warning("last_good sigma lookup failed for %s: %s", symbol, exc)
        return None
    return _lookup


def _get_fired_signal_ids(session_date: str, redis_url: str) -> set[int] | None:
    """Return fired signal_ids for today, or None if Redis is unavailable (P2-05-A fail-closed).

    Returns:
        set[int]: IDs of signals already fired this session (may be empty on first run).
        None:     Redis unreachable — caller must treat as fail-closed (skip all S4 BUYs).
    """
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=False)
        try:
            raw = r.smembers(f"s4:fired_signals:{session_date}")
            return {int(v) for v in raw}
        finally:
            r.close()
    except Exception as exc:
        log.warning(
            "P2-05-A: idempotency Redis unreachable — all S4 BUY signals will be skipped (fail-closed): %s",
            exc,
        )
        return None


def _apply_idempotency_filter(orders: list, skip_syms: set[str]) -> list:
    """Filter S4 BUY orders for symbols in skip_syms (P2-05-A fail-closed safety).

    SELL orders are never filtered — only BUY orders for skipped symbols are excluded.
    When Redis is unavailable, callers pass all S4 symbols as skip_syms to prevent
    duplicate BUYs on the assumption that signals may have already fired.
    """
    from src.backtest.engine.types import OrderSide as _OS
    if not skip_syms:
        return orders
    return [o for o in orders if not (o.symbol in skip_syms and o.side == _OS.BUY)]


def _apply_whipsaw_damping_filter(orders: list, suppressed_syms: set[str]) -> list:
    """Exclude SELL orders for symbols the anti-whipsaw damper suppressed this cycle (#61).

    Only SELLs are filtered — a damped whipsaw means "hold the position", it never
    affects any other order (mirrors _apply_idempotency_filter's BUY-only symmetry).
    """
    from src.backtest.engine.types import OrderSide as _OS
    if not suppressed_syms:
        return orders
    return [o for o in orders if not (o.symbol in suppressed_syms and o.side == _OS.SELL)]


def _resolve_buy_origin_strategy(symbol: str, sym_strats: dict, decision: dict) -> str:
    """Return the strategy that actually contributed weight to this BUY this cycle.

    Prefers sym_strats (CycleResult.symbol_strategies — accurate, computed from
    which strategies contributed non-zero weight this cycle) over inferring
    from signal_id presence. The signal_id heuristic silently mislabels an S4
    BUY as S1 whenever its signal_id wasn't captured in the decision dict —
    real incident 2026-07-17: trade 361 (DB) was a genuine S4 BUY (execution_
    decisions.reason said "S4 news-driven: sentiment +0.672...") but
    trades.stop_strategy recorded "S1", corrupting which stop_strategy_params
    (k/floor/cap) applied to a $6,181 position.
    """
    strats = sym_strats.get(symbol, [])
    if "S4" in strats:
        return "S4"
    if "S1" in strats:
        return "S1"
    if strats:
        return strats[0]
    # Defensive fallback only for the case sym_strats has no entry at all
    # (shouldn't happen for a just-submitted BUY, but never crash on it).
    return "S4" if decision.get("signal_id") else "S1"


def _load_sector_map() -> dict[str, str] | None:
    """Invert the trading.yaml `sectors:` block to {symbol: sector}.

    Fail-open (None) when the block is missing/unreadable: the enforcer treats
    None as 'sector pass disabled', matching pre-2026-07-13 behavior.
    """
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            raw = yaml.safe_load(f) or {}
        sectors = raw.get("sectors") or {}
        if not sectors:
            return None
        return {
            str(sym): str(sector)
            for sector, symbols in sectors.items()
            for sym in (symbols or [])
        }
    except Exception as exc:
        log.warning("Could not load sector map (%s) — sector cap disabled", exc)
        return None


def _load_risk_config() -> dict:
    """Return the full risk section from trading.yaml; safe defaults on error (P2-05-B)."""
    defaults: dict = {
        "max_portfolio_exposure": 0.50,
        "max_single_asset_pct": 0.10,
        "max_sector_exposure": 0.0,
        "stop_loss": 0.02,
        "portfolio_drawdown": 0.05,
        "stop_loss_mode": "fixed",
        "stop_strategy_params": {
            "S1": {"k": 3.5, "floor": 0.06, "cap": 0.12},
            "S4": {"k": 2.0, "floor": 0.03, "cap": 0.08},
            "default": {"k": 3.0, "floor": 0.04, "cap": 0.12},
        },
        "stop_sigma_lookback_fast": 20,
        "stop_sigma_lookback_slow": 63,
        "stop_sigma_ewma_floor_ratio": 0.8,
        "stop_risk_budget_bp_per_pos": 12,
        "stop_risk_budget_bp_aggregate": 100,
        "stop_gap_buffer_pct": 0.005,
        "stop_shadow_enabled": False,
        "broker_disaster_stop": {"multiplier": 1.5, "sigma_multiple": 5.0, "floor_pct": 0.12, "cap_pct": 0.20},
        # #61: require N consecutive "whipsaw"-classified cycles (#60) before letting
        # a weight-0 S4 SELL through, instead of exiting on the first fresh weak/neutral
        # re-signal. Off by default — flip only after reviewing the shadow frequency log.
        # STACKS with execution.exit_persistence_cycles (_apply_exit_hysteresis, runs
        # earlier, always on) — effective confirmation is ~exit_persistence_cycles +
        # s4_anti_whipsaw_confirm_cycles, not this value alone. See config/trading.yaml.
        "s4_anti_whipsaw_damping_enabled": False,
        "s4_anti_whipsaw_confirm_cycles": 2,
        # #81: cap each S4 ticker's weight at 1/n_top regardless of how many
        # candidates actually pass the gate — fixes the lone-survivor
        # concentration bug (a single surviving ticker taking the full 10%
        # sleeve bucket instead of its 2% slot). ON by default per explicit
        # operator decision 2026-07-20. See src/strategies/s4/config.py
        # S4Config.fixed_slot_sizing.
        "s4_fixed_slot_sizing_enabled": True,
        # #71: once S1 excludes a symbol (weight dropped to 0 by S1's own
        # signal), block S1 from re-buying it for N minutes — kills the
        # 15-min self-churn flip (SBUX/GE/XLF, 2026-07-17). Off by default —
        # flip only after reviewing the shadow frequency log.
        "s1_reentry_cooldown_enabled": False,
        "s1_reentry_cooldown_minutes": 30,
    }
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        risk = cfg.get("risk", {})
        merged = {**defaults, **risk}
        # Preserve nested structures (shallow merge for stop_strategy_params / broker_disaster_stop).
        for nested in ("stop_strategy_params", "broker_disaster_stop"):
            if nested in defaults and nested in risk:
                merged[nested] = {**defaults[nested], **risk[nested]}
        # Alias: trading.yaml uses risk.max_position_pct; code uses max_single_asset_pct.
        merged["max_single_asset_pct"] = float(
            risk.get("max_position_pct", defaults["max_single_asset_pct"])
        )
        return merged
    except Exception as exc:
        log.warning("P2-05-B: could not load risk config (%s) — using defaults", exc)
        return defaults


def _num(v: Any) -> float | None:
    """Coerce an observed scalar price/qty to float; reject bools and non-numerics."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def _open_stop_risk(open_trades: list[dict] | None) -> float:
    """Return total open stop-risk in $: sum(d_init * entry_notional) across open trades.

    Pre-migration trades without stop_d_init use the legacy 2% fixed stop.
    """
    total = 0.0
    for t in open_trades or []:
        notional = float(t.get("entry_notional") or 0.0)
        if notional <= 0:
            continue
        d_init = t.get("stop_d_init")
        if d_init is None or d_init <= 0:
            d_init = 0.02
        total += float(d_init) * notional
    return total


def _aggregate_stop_budget(nav: float, risk_cfg: dict) -> float:
    """Aggregate sleeve stop-risk budget in dollars."""
    bp = float(risk_cfg.get("stop_risk_budget_bp_aggregate", 100))
    return nav * bp / 10000.0


def _stop_loss_breached_symbols(
    positions: list,
    entry_prices: dict[str, float],
    market,
    stop_policy: "StopPolicy",
    pg_store: "PostgreSQLStore",
) -> dict[str, "StopDecision"]:
    """Return per-symbol StopDecision objects for positions that breached.

    FIX-C synthetic stop-loss: Alpaca rejects bracket (stop-loss) legs on
    notional/fractional orders (error 42210000), so positions opened via notional
    BUYs carry no broker-side stop. This check runs every cycle and force-closes any
    position trading at or below the frozen protective trigger.

    Fail-open: positions with no recorded entry price or no current market price are
    skipped (never force-sold on missing data). Pre-migration open trades (no frozen
    stop) fall back to the legacy fixed stop_loss_pct.
    """
    prices = getattr(market, "prices", {}) or {}
    breached: dict[str, "StopDecision"] = {}

    # Legacy disable: a zero fixed stop pct disables the protective check.
    if stop_policy._cfg.get("stop_loss", 0.02) <= 0 and stop_policy._cfg.get("stop_loss_mode", "fixed") == "fixed":
        return {}

    cycle_ts = datetime.now(timezone.utc)
    for pos in positions:
        sym = getattr(pos, "symbol", None)
        if sym is None:
            continue
        entry = _num(entry_prices.get(sym))
        price = _num(prices.get(sym))
        if entry is None or price is None:
            continue
        if entry <= 0 or price <= 0:
            continue

        frozen = None
        try:
            frozen = pg_store.load_frozen_stop(sym)
        except Exception:
            frozen = None
        if frozen is None:
            # Pre-migration / fallback: legacy fixed stop.
            frozen = stop_policy.freeze(sym, None, entry, cycle_ts)
        decision = stop_policy.compute(sym, entry, price, frozen, cycle_ts, "market.prices")
        if decision.breached:
            breached[sym] = decision
            log.warning(
                "Stop-loss: %s price %.4f <= trigger %.4f (d_init %.3f, mode %s, strat %s) — forced exit",
                sym, price, decision.trigger_price, decision.d_init,
                decision.mode, decision.strategy,
            )
    return breached


def _build_stop_shadow_rows(
    positions: list,
    entry_prices: dict[str, float],
    market,
    stop_policy: "StopPolicy",
    pg_store: "PostgreSQLStore",
) -> list[dict]:
    """Return stop_shadow_log rows for every held position (fixed + vol_scaled)."""
    prices = getattr(market, "prices", {}) or {}
    rows: list[dict] = []
    cycle_ts = datetime.now(timezone.utc)

    # One shared vol-scaled policy per cycle; avoid per-symbol instantiation.
    vol_cfg = dict(stop_policy._cfg)
    vol_cfg["stop_loss_mode"] = "vol_scaled"
    vol_policy = stop_policy.__class__(vol_cfg, bars_df=stop_policy._bars)

    for pos in positions:
        sym = getattr(pos, "symbol", None)
        if sym is None:
            continue
        entry = _num(entry_prices.get(sym))
        price = _num(prices.get(sym))
        if entry is None or price is None or entry <= 0 or price <= 0:
            continue

        strategy = None
        try:
            meta = pg_store.fetch_open_trade_meta(sym)
            strategy = meta.get("strategy") if meta else None
        except Exception:
            strategy = None

        # fixed mode
        fixed_frozen = stop_policy.freeze(sym, strategy, entry, cycle_ts)
        fixed_dec = stop_policy.compute(sym, entry, price, fixed_frozen, cycle_ts, "market.prices")

        # vol_scaled mode (force mode in a temporary cfg copy)
        vol_frozen = vol_policy.freeze(sym, strategy, entry, cycle_ts)
        vol_dec = vol_policy.compute(sym, entry, price, vol_frozen, cycle_ts, "market.prices")

        # d_hard audit: broker disaster-stop distance for this position.
        d_hard = d_hard_trigger = None
        try:
            sigma_current = vol_policy._sigma_eff(sym)[0]
            d_hard = vol_policy.d_hard(sym, vol_frozen, sigma_current)
            d_hard_trigger = entry * (1.0 - d_hard) if d_hard is not None else None
        except Exception as _dhard_exc:
            log.warning("d_hard shadow audit failed for %s: %s", sym, _dhard_exc)

        rows.append({
            "cycle_ts": cycle_ts,
            "symbol": sym,
            "strategy": strategy,
            "entry_price": entry,
            "observed_price": price,
            "vol_at_entry": vol_frozen.vol_at_entry,
            "sigma_eff": vol_frozen.sigma_eff,
            "vol_source": vol_frozen.vol_source,
            "d_init_fixed": fixed_dec.d_init,
            "trigger_fixed": fixed_dec.trigger_price,
            "would_breach_fixed": fixed_dec.breached,
            "d_init_vol_scaled": vol_dec.d_init,
            "trigger_vol_scaled": vol_dec.trigger_price,
            "would_breach_vol_scaled": vol_dec.breached,
            "d_hard": d_hard,
            "d_hard_trigger": d_hard_trigger,
            "d_hard_breached": (d_hard_trigger is not None and price <= d_hard_trigger),
        })
    return rows


def _get_feedback_threshold(redis_url: str, strategy: str = "S4") -> float:
    """Return active feedback entry threshold for a strategy sleeve from Redis.

    Per-strategy keys (feedback:entry_threshold:S4, :S1, …) decouple the ratchet so a
    loss in one strategy does not poison another. Falls back to the legacy bare key
    and then to S4Config.min_score when Redis is unreachable.
    """
    try:
        from redis import Redis as _R
        _r = _R.from_url(redis_url, decode_responses=True)
        try:
            raw = _r.get(f"feedback:entry_threshold:{strategy}")
            if raw is None:
                raw = _r.get("feedback:entry_threshold")
            if raw is not None:
                return float(raw)
        finally:
            _r.close()
    except Exception as exc:
        log.warning(
            "Could not read feedback threshold for %s from Redis: %s — using S4 min_score",
            strategy, exc,
        )
    from src.strategies.s4.config import S4Config as _S4Cfg
    return _S4Cfg().min_score


def _fresh_signal_protected_symbols(
    candidate_symbols: set[str],
    pg,
    entry_threshold: float,
    max_age_hours: int,
) -> set[str]:
    """Return symbols from candidate_symbols that should be protected from a rebalance SELL.

    A symbol is protected when its most recent signal within max_age_hours has
    score >= entry_threshold (fresh, positive signal → original buy thesis still holds).

    This prevents the S4 min_stocks constraint from causing premature exits:
    when only 1 positive-strength signal exists but the ranker requires min_stocks=2,
    the ranker returns {} weights and the orchestrator generates a SELL for all positions,
    including ones whose signal is still valid.

    Fail-open: returns empty set on DB error (positions may be sold rather than blocking).
    """
    if not candidate_symbols:
        return set()
    try:
        signals = pg.fetch_signals_for_cycle(hours=max_age_hours, symbols=list(candidate_symbols))
        latest: dict[str, object] = {}
        for sig in signals:
            prev = latest.get(sig.symbol)
            if prev is None or sig.generated_at > prev.generated_at:
                latest[sig.symbol] = sig
        return {sym for sym, sig in latest.items() if sig.score >= entry_threshold}
    except Exception as exc:
        log.warning(
            "_fresh_signal_protected_symbols: DB error (%s) — no protection applied (fail-open)", exc
        )
        return set()


def _mark_signal_fired(
    signal_id: int,
    session_date: str,
    redis_url: str,
    ttl_seconds: int = _S4_FIRED_SIGNALS_TTL,
) -> None:
    """Add signal_id to the per-session Redis set; set TTL on first write (fail-silent)."""
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=False)
        try:
            key = f"s4:fired_signals:{session_date}"
            r.sadd(key, signal_id)
            r.expire(key, ttl_seconds)
        finally:
            r.close()
    except Exception as exc:
        log.warning("P1-S4: failed to mark signal_id=%s as fired: %s", signal_id, exc)


_CYCLE_LOCK_KEY = "portfolio:cycle:lock"
_CYCLE_LOCK_TTL = 1200  # 20 min — safely above the 15-min beat cadence (was 840s, shorter than beat)
# FIX-B: raised 30→90 so a freshly-entered position cannot be sold by the next
# rebalance cycle. With a 15-min cadence, 30 min allowed buy→sell→buy churn every
# ~2 cycles (Day-1: GS/MU/MS roundtrips). 90 min (≥6 cycles) also subsumes the
# "S4 just bought it" conflict — an S4 BUY registers as recently-bought.
_HOLD_MINIMUM_MINUTES = 90  # don't sell a position entered less than this many minutes ago
_MIN_ORDER_NOTIONAL = 100.0  # skip BUY orders below this USD threshold — prevents $40 micro-rebalancing


def _get_hold_minimum_minutes() -> int:
    """Minimum minutes to hold a freshly-entered position before a rebalance can sell it.

    Read from trading.yaml ``execution.hold_minimum_minutes``; defaults to
    ``_HOLD_MINIMUM_MINUTES`` (90) on any error. Stop-loss exits bypass this hold.
    """
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        return int(cfg.get("execution", {}).get("hold_minimum_minutes", _HOLD_MINIMUM_MINUTES))
    except Exception:
        return _HOLD_MINIMUM_MINUTES


_EXIT_HYSTERESIS_KEY = "portfolio:exit_count:"  # + symbol; per-symbol exit streak counter
_CYCLE_SECONDS = 900  # ~15-min beat cadence; used to size the hysteresis counter TTL


def _get_exit_persistence_cycles() -> int:
    """Consecutive rebalance cycles a held position must be targeted for exit before it
    is actually sold (anti-churn hysteresis). 0 disables. From trading.yaml
    ``execution.exit_persistence_cycles``, default 2.

    A no-trade band cannot fix this churn: positions are ~0.85% of NAV, so the exit gap
    (weight->0) equals the entry gap, and any band that blocks marginal exits also blocks
    marginal entries. Hysteresis instead makes exits *sticky* — a name that drops out of
    the target for a single cycle then returns is held, not flipped.
    """
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        return int(cfg.get("execution", {}).get("exit_persistence_cycles", 2))
    except Exception:
        return 2


def _apply_exit_hysteresis(final_orders, redis_url: str, persistence_cycles: int):
    """Suppress rebalance SELLs until a position has been targeted for exit for
    ``persistence_cycles`` consecutive cycles. Kills the buy->sell->buy flicker where a
    name drops out of the merged target for one cycle then re-enters the next.

    Per-symbol exit streak is tracked in Redis (INCR + TTL). A BUY resets the streak;
    a SELL increments it and is only allowed through once the streak reaches the
    threshold. Stop-loss / reversal sells are NOT in ``final_orders`` here, so they are
    never delayed. Fail-open: any Redis error returns the orders unchanged.
    """
    from src.backtest.engine.types import OrderSide as _OS

    if persistence_cycles <= 0 or not final_orders:
        return final_orders
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
    except Exception as exc:
        log.warning("Exit hysteresis: Redis unavailable (%s) — no suppression", exc)
        return final_orders

    ttl = (persistence_cycles + 1) * _CYCLE_SECONDS
    kept: list = []
    suppressed: list[str] = []
    try:
        for o in final_orders:
            key = f"{_EXIT_HYSTERESIS_KEY}{o.symbol}"
            if o.side == _OS.BUY:
                r.delete(key)  # re-wanted -> reset exit streak
                kept.append(o)
            elif o.side == _OS.SELL:
                count = int(r.incr(key))
                r.expire(key, ttl)
                if count < persistence_cycles:
                    suppressed.append(o.symbol)  # hold this cycle (not yet persistent)
                else:
                    r.delete(key)
                    kept.append(o)  # genuine, persistent exit
            else:
                kept.append(o)
    except Exception as exc:
        log.warning("Exit hysteresis: error (%s) — no suppression", exc)
        try:
            r.close()
        except Exception:
            pass
        return final_orders
    try:
        r.close()
    except Exception:
        pass
    if suppressed:
        log.info(
            "Exit hysteresis (%d cycles): held %d position(s) flagged for exit: %s",
            persistence_cycles, len(suppressed), sorted(suppressed),
        )
    return kept


def _persist_trade_fills(
    submitted_orders,
    *,
    open_trades,
    symbol_decisions,
    written_buy_order_ids,
    stop_policy,
    market,
    alpaca_entry_prices,
    s4_signals,
    regime_mult,
    tick_time,
    sym_strats: dict | None = None,
) -> int:
    """Persist trade entry/exit rows + back-fill Alpaca order_ids, one order at a time.

    Extracted from run_portfolio_cycle's trade-write tail (B28-FIX + WS-5).
    B33 (2026-07-15): each order's DB write is isolated in its OWN try/except so
    a single failing order cannot abort the remaining ones. Previously the whole
    loop shared one try/except and record_trade_exit re-raises DB errors — so the
    first SELL that threw (a dead pooled connection) broke the loop, skipping
    record_trade_exit AND the order_id back-fill for every subsequent order,
    leaving 5 Alpaca fills unrecorded (DB↔Alpaca divergence). On a per-order
    failure the connection is rolled back (clearing psycopg2's 'current
    transaction is aborted' state) so the next order reuses the same connection,
    then the loop continues. Reconcile-fills remains the safety net for any fill
    whose trade row still didn't get written.

    Returns the count of orders whose trade-write failed (0 = all written).
    """
    _pg_trades = None
    _failures = 0
    try:
        from src.store.pg_store import PostgreSQLStore
        _pg_trades = PostgreSQLStore()
        # Map symbol -> open trade id so record_trade_exit targets the specific
        # trade being wound down (never the historical closed trades for the
        # same symbol). open_trades was fetched at the top of the cycle
        # (exit_time IS NULL => positions still open at submit time).
        _open_trade_ids = {t["symbol"]: t["id"] for t in open_trades}
        for sub in submitted_orders:
            sym = sub["symbol"]
            dec = symbol_decisions.get(sym, {})
            _trade_id = None
            # --- Trade write (BUY open_trade / SELL record_trade_exit) ---
            # Isolated per-order: a failure here counts as a trade-write failure,
            # rolls back the connection, and skips this order's postmortem/back-fill
            # (continue). One bad order must NOT abort the remaining batch (B33).
            try:
                if sub["side"] == "buy":
                    # B28-FIX: BUY rows already written immediately after submission.
                    # Skip to avoid duplicate primary-key violation.
                    if sub["order_id"] not in written_buy_order_ids:
                        # Freeze stop metadata at entry for the legacy batch path too.
                        _frozen_stop_legacy: "FrozenStop | None" = None
                        if stop_policy is not None:
                            _raw_px_l = market.prices.get(sym) if market and getattr(market, "prices", None) else None
                            _entry_px_l = float(_raw_px_l) if isinstance(_raw_px_l, (int, float)) and not isinstance(_raw_px_l, bool) else None
                            if _entry_px_l is None and sub.get("qty"):
                                _entry_px_l = sub["notional"] / sub["qty"]
                            if _entry_px_l is None:
                                _entry_px_l = float(sub["notional"]) if sub.get("notional") else 0.0
                            _strategy_l = _resolve_buy_origin_strategy(sym, sym_strats or {}, dec)
                            _frozen_stop_legacy = stop_policy.freeze(
                                sym, _strategy_l, float(_entry_px_l), tick_time
                            )
                        _pg_trades.open_trade(
                            symbol=sym,
                            signal_id=dec.get("signal_id"),
                            decision_id=dec.get("decision_id"),
                            entry_order_id=sub["order_id"],
                            entry_time=tick_time,
                            entry_notional=sub["notional"],
                            score=dec.get("score", 0.0),
                            regime_mult=regime_mult,
                            signal_score=dec.get("signal_score"),
                            frozen_stop=_frozen_stop_legacy,
                        )
                else:
                    # WS-5 fix-back: target the open trade by id and tell
                    # record_trade_exit whether this is the final tranche.
                    # is_final: a SELL whose target allocation_weight is 0.0 is a
                    # full close (final tranche); stop-loss / reversal SELLs carry
                    # no allocation_weight and default to 0.0 => final (full close).
                    _is_final = float(sub.get("allocation_weight", 0.0) or 0.0) == 0.0
                    _trade_id = _pg_trades.record_trade_exit(
                        symbol=sym,
                        exit_order_id=sub["order_id"],
                        exit_time=tick_time,
                        exit_reason=sub.get("reason", "portfolio_sell"),
                        trade_id=_open_trade_ids.get(sym),
                        is_final=_is_final,
                    )
            except Exception as _tw_exc:
                _failures += 1
                # Rollback so a connection left in 'current transaction is
                # aborted' by the failed op is cleaned before the next iteration —
                # otherwise every subsequent order cascade-fails too. Idempotent:
                # record_trade_exit and open_trade both rollback on their own
                # re-raise; stop_policy.freeze is pure (no DB). This guards future
                # code paths and any op that doesn't self-rollback.
                try:
                    _pg_trades.rollback()
                except Exception:
                    pass
                log.warning(
                    "B33: trade-write failed for %s %s (order_id=%s): %s — continuing with remaining orders",
                    sym, sub["side"], sub.get("order_id"), _tw_exc,
                )
                continue
            # --- Postmortem (final tranche only) ---
            # Runs only after a successful trade write. A postmortem failure must
            # NOT count as a trade-write failure (the trade row is already committed)
            # and must NOT skip the order_id back-fill below. (I-1: keeping the
            # failure counter honest for the B33 'N/M failed' monitor log.)
            if _trade_id is not None:
                try:
                    _entry_px = alpaca_entry_prices.get(sym, 0.0)
                    _exit_px = market.prices.get(sym, 0.0) if market and getattr(market, "prices", None) else 0.0
                    _sig = s4_signals.get(sym, {})
                    _portfolio_postmortem(
                        _pg_trades,
                        _trade_id,
                        signal=_sig,
                        score=dec.get("score", 0.0),
                        entry_price=_entry_px,
                        exit_price=_exit_px,
                        tick_time=tick_time,
                    )
                except Exception as _pm_exc:
                    log.warning("B33: postmortem failed for %s (trade_id=%s): %s", sym, _trade_id, _pm_exc)
            # --- Back-fill Alpaca order_id on the execution_decisions row ---
            # Cosmetic (Decision Log display); failure must not count as a trade-write
            # failure (the trade row already committed) and must not roll back.
            dec_id = dec.get("decision_id")
            if dec_id is not None:
                try:
                    _pg_trades.update_decision_order_id(dec_id, sub["order_id"])
                except Exception as _eid_exc:
                    log.warning("Could not back-fill order_id on decision %s: %s", dec_id, _eid_exc)
        if _failures:
            log.warning(
                "B33: %d/%d trade writes failed this cycle (continued past failures; "
                "reconcile-fills will backfill any Alpaca fills not recorded)",
                _failures, len(submitted_orders),
            )
    except Exception as _exc:
        # Fatal init failure (pool unavailable, open_trades malformed) — nothing
        # written. Reconcile-fills remains the safety net for any Alpaca fills.
        log.warning("Failed to initialize trade-write batch: %s", _exc)
    finally:
        # B7/B32: return the trade-writes connection to the pool on every path.
        if _pg_trades is not None:
            try:
                _pg_trades.close()
            except Exception:
                pass
    return _failures


@app.task(name="src.workers.portfolio_scheduler.run_portfolio_cycle")
def run_portfolio_cycle() -> dict:
    """Celery entry-point for the portfolio orchestration cycle."""
    from src.config import config

    engine = _load_execution_engine()
    if engine not in ("portfolio",):
        log.info("execution.engine=%s — portfolio cycle inactive", engine)
        return {"skipped": True, "reason": f"engine={engine}"}

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        log.warning("Alpaca credentials not configured — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_credentials"}

    # Cycle idempotency lock: prevents duplicate runs when Celery beat fires
    # multiple tasks before the previous one completes (e.g. worker restart at :30).
    # B26-FIX: use a UUID token as lock value so the finally block only deletes
    # the lock it owns — safe even if the TTL expires and a second cycle starts.
    import uuid as _uuid
    _cycle_token = str(_uuid.uuid4())
    _lock_acquired = False
    try:
        from redis import Redis as _RedisLock
        _rl = _RedisLock.from_url(config.REDIS_URL, decode_responses=True)
        try:
            acquired = _rl.set(_CYCLE_LOCK_KEY, _cycle_token, nx=True, ex=_CYCLE_LOCK_TTL)
            if not acquired:
                log.info("Portfolio cycle skipped — lock held by a concurrent run")
                return {"skipped": True, "reason": "cycle_lock"}
            _lock_acquired = True
        finally:
            _rl.close()
    except Exception as _lock_exc:
        log.warning("Could not acquire cycle lock: %s — proceeding anyway", _lock_exc)

    # Lua script: atomically delete the lock only if we own it (token matches).
    _UNLOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

    try:
        return _run_cycle_inner()
    except Exception as exc:
        log.error("Portfolio cycle unhandled error: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        # Release the lock early so the next scheduled cycle can run.
        # Only delete if we own the lock (token check via Lua to avoid TOCTOU).
        if _lock_acquired:
            try:
                from redis import Redis as _RedisUnlock
                from src.config import config as _cfg_ul
                _ru = _RedisUnlock.from_url(_cfg_ul.REDIS_URL, decode_responses=True)
                try:
                    _ru.eval(_UNLOCK_LUA, 1, _CYCLE_LOCK_KEY, _cycle_token)
                finally:
                    _ru.close()
            except Exception as _ul_exc:
                log.debug("Could not release cycle lock: %s", _ul_exc)


def _run_cycle_inner() -> dict:
    """Inner cycle logic, separated for testability."""
    import pandas as pd
    from alpaca.data.enums import Adjustment, DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.trading.client import TradingClient

    from src.backtest.engine.data_replay import DataReplay
    from src.backtest.engine.portfolio import VirtualPortfolio
    from src.backtest.engine.types import MarketSnapshot
    from src.config import config
    from src.notifications.telegram import TelegramNotifier
    from src.portfolio.constraints import ConstraintEnforcer
    from src.portfolio.orchestrator import PortfolioOrchestrator
    from src.strategies.registry import StrategyRegistry

    notifier = TelegramNotifier()

    # B2 — Kill-switch check: halt immediately if active (drawdown-triggered or operator).
    # Uses direct Redis (same pattern as system:mode check below) so tests can mock redis.Redis.
    try:
        from redis import Redis as _RedisKS
        _r_ks = _RedisKS.from_url(config.REDIS_URL, decode_responses=True)
        try:
            _ks_active = bool(_r_ks.get("killswitch_active")) or bool(_r_ks.get("system:halted_by_operator"))
            if _ks_active:
                _reason_raw = _r_ks.get("killswitch_reason") or _r_ks.get("system:halted_by_operator_reason")
                try:
                    import json as _jks
                    reason = _jks.loads(_reason_raw).get("reason", "unknown") if _reason_raw else "unknown"
                except Exception:
                    reason = "unknown"
                log.warning("Portfolio cycle skipped — kill-switch active: %s", reason)
                # P0-A: Cancel any pending orders to prevent stale fills after kill-switch.
                _emergency_cancel_all(
                    api_key=config.ALPACA_API_KEY,
                    secret_key=config.ALPACA_SECRET_KEY,
                    paper=config.ALPACA_PAPER_MODE,
                )
                return {"skipped": True, "reason": f"killswitch:{reason}"}
        finally:
            _r_ks.close()
    except Exception as exc:
        # Redis unreachable — CRITICAL: we cannot check the kill-switch safely.
        msg = f"🚨 Portfolio cycle: Redis unreachable — cannot verify kill-switch. Aborting cycle.\n<code>{exc}</code>"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Redis unreachable in portfolio cycle: %s", exc)
        return {"error": "redis_unreachable"}

    registry = StrategyRegistry()

    # P2-02: Override YAML mode with DB source-of-truth (fail-open if DB unavailable).
    try:
        from src.store.pg_store import PostgreSQLStore
        with PostgreSQLStore() as _pg_reg:
            _reg_conn = _pg_reg._get_connection()
            registry.load_mode_from_db(_reg_conn)
    except Exception as _db_exc:
        log.warning("load_mode_from_db: DB unavailable (%s) — keeping YAML mode", _db_exc)

    active = registry.get_active_strategies()
    if not active:
        log.warning("No active strategies in registry — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_active_strategies"}

    # P2-02: Filter out strategies not operationally approved in strategy_lifecycle.
    try:
        from src.store.pg_store import PostgreSQLStore
        with PostgreSQLStore() as _pg_gate:
            _gate_conn = _pg_gate._get_connection()
            active = _filter_approved_strategies(active, _gate_conn)
    except Exception as _gate_exc:
        log.warning(
            "Approval gate DB unavailable (%s) — admitting all enabled strategies (fail-open at gate level).",
            _gate_exc,
        )

    if not active:
        log.warning("No operationally approved strategies — skipping portfolio cycle")
        return {"skipped": True, "reason": "no_approved_strategies"}

    # Single TradingClient instance shared across all pre-flight checks and order submission.
    trading_client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )

    # P0-B: Market clock pre-flight — skip cycle if NYSE is closed (handles early-close days).
    try:
        clock = trading_client.get_clock()
        if not clock.is_open:
            log.info("Market closed (next open: %s) — skipping portfolio cycle", clock.next_open)
            return {"skipped": True, "reason": "market_closed", "next_open": str(clock.next_open)}
    except Exception as _clk_exc:
        # P0-07: fail-closed — if we can't verify market is open, abort rather than risk
        # submitting orders on a holiday, early-close day, or during an exchange outage.
        log.error("Could not fetch market clock: %s — aborting cycle (fail-closed)", _clk_exc)
        _fire_alert(
            notifier,
            f"⚠️ Portfolio cycle: Alpaca clock API unreachable — cycle aborted (P0-07 fail-closed).\n<code>{_clk_exc}</code>",
            AlertLevel.WARNING,
        )
        return {"error": "clock_unavailable"}

    # P0-D: Account pre-flight — abort if Alpaca has blocked the account.
    try:
        account = trading_client.get_account()
        cash = float(account.cash)
        equity = float(account.equity)
    except Exception as exc:
        # B2 — Alpaca unreachable: CRITICAL alert, abort cycle (don't trade blind).
        msg = f"🚨 Portfolio cycle: Alpaca API unreachable — cycle aborted.\n<code>{exc}</code>"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Failed to fetch Alpaca account: %s — aborting cycle", exc)
        return {"error": "alpaca_unreachable"}

    # Use `is True` (not truthy) so MagicMock objects in tests don't trigger this.
    if account.trading_blocked is True or account.account_blocked is True:
        msg = "🚨 Portfolio cycle: account bloccato da Alpaca (trading_blocked o account_blocked) — ciclo abortito"
        _fire_alert(notifier, msg, AlertLevel.CRITICAL)
        log.error("Alpaca account blocked — aborting cycle (trading_blocked=%s, account_blocked=%s)",
                  account.trading_blocked, account.account_blocked)
        return {"skipped": True, "reason": "account_blocked"}

    buying_power = float(account.buying_power) if account.buying_power else cash
    log.debug("Account: equity=%.2f, cash=%.2f, buying_power=%.2f", equity, cash, buying_power)

    # Fetch price history
    data_client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
    )
    symbols = list({sym for e in active for sym in _strategy_symbols(e)})
    if not symbols:
        symbols = list(config.WATCHLIST_SYMBOLS or [])

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_PRICE_BARS * 2)

    bars_df = None
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=start, end=end,
            feed=DataFeed.IEX,
            adjustment=Adjustment.ALL,
        )
        raw = data_client.get_stock_bars(request).df
        if not raw.empty:
            raw = raw.reset_index()
            bars_df = raw.pivot(index="timestamp", columns="symbol", values="close")
    except Exception as exc:
        log.warning("Failed to fetch price bars: %s — using empty DataFrame", exc)

    if bars_df is None or bars_df.empty:
        log.error("No price data available — aborting portfolio cycle")
        return {"error": "no_price_data"}

    # Build strategy instances
    strategy_instances = {}
    for entry in active:
        try:
            instance = _build_strategy_instance(entry, bars_df)
            if instance is not None:
                strategy_instances[entry.strategy_id] = instance
        except Exception as exc:
            log.error("Failed to build instance for %s: %s", entry.strategy_id, exc)

    # Build market snapshot — seed prices from daily bar closes.
    latest_prices = {}
    for sym in bars_df.columns:
        if not bars_df[sym].dropna().empty:
            latest_prices[sym] = float(bars_df[sym].dropna().iloc[-1])

    # P1-A: Refresh prices from Snapshot API (latest_trade price, then minute_bar close).
    # This replaces yesterday's close with the current intraday price for order sizing.
    try:
        from alpaca.data.requests import StockSnapshotRequest
        snap_req = StockSnapshotRequest(symbol_or_symbols=symbols, feed=DataFeed.IEX)
        snapshots = data_client.get_stock_snapshot(snap_req)
        refreshed = 0
        for sym, snap in snapshots.items():
            price = None
            if snap.latest_trade and snap.latest_trade.price:
                price = float(snap.latest_trade.price)
            elif snap.minute_bar and snap.minute_bar.close:
                price = float(snap.minute_bar.close)
            if price and price > 0:
                latest_prices[sym] = price
                refreshed += 1
        log.debug("P1-A Snapshot: refreshed %d/%d prices from Alpaca real-time", refreshed, len(symbols))
    except Exception as _snap_exc:
        log.warning("Snapshot API failed: %s — using bar closes for pricing", _snap_exc)

    market = MarketSnapshot(
        timestamp=end,
        prices=latest_prices,
        volumes={sym: 1_000_000.0 for sym in latest_prices},
        adv_20d={sym: 1_000_000.0 for sym in latest_prices},
    )

    # B1 — Portfolio drawdown cap: update peak equity in Redis, halt if drawdown breached.
    try:
        from redis import Redis as _Redis2
        import json as _jdd
        _r_dd = _Redis2.from_url(config.REDIS_URL, decode_responses=True)
        try:
            _raw_peak = _r_dd.get(_PEAK_EQUITY_KEY)
            peak_equity, drawdown = _peak_and_drawdown(
                float(_raw_peak) if _raw_peak else None, equity
            )
            # Persist every cycle so the peak always survives — seeds on the
            # first observation (the old code never did, disabling the cap).
            _r_dd.set(_PEAK_EQUITY_KEY, str(peak_equity))

            # Cache equity for consumers that need account size (e.g. the
            # loss-feedback relative trigger). Legacy execution wrote this key;
            # in portfolio mode this is the authoritative writer.
            _r_dd.setex("portfolio:value", 86400, str(equity))

            _dd_cap = _load_risk_config()["portfolio_drawdown"]
            if drawdown >= _dd_cap:
                _dd_reason = f"portfolio drawdown {drawdown:.1%} >= {_dd_cap:.0%} cap"
                _dd_payload = _jdd.dumps({"reason": _dd_reason, "activated_at": datetime.now(timezone.utc).isoformat()})
                _r_dd.pipeline().setex("killswitch_active", 64800, 1).setex("killswitch_reason", 64800, _dd_payload).execute()
                msg = (
                    f"🚨 <b>Drawdown cap raggiunto — kill-switch attivato</b>\n\n"
                    f"Equity attuale: <b>${equity:,.0f}</b>\n"
                    f"Picco: <b>${peak_equity:,.0f}</b>\n"
                    f"Drawdown: <b>{drawdown:.1%}</b> (soglia: {_dd_cap:.0%})\n\n"
                    f"Trading sospeso per 18h. Per riprendere: <code>redis-cli DEL killswitch_active</code>"
                )
                _fire_alert(notifier, msg, AlertLevel.CRITICAL)
                log.error("Drawdown cap %.1f%% — kill-switch activated, aborting cycle", drawdown * 100)
                return {"skipped": True, "reason": f"drawdown_cap:{drawdown:.3f}"}
        finally:
            _r_dd.close()
    except Exception as exc:
        log.warning("Drawdown cap check failed: %s — proceeding without check", exc)

    portfolio = VirtualPortfolio(initial_cash=cash)

    # Load existing Alpaca positions so delta-orders are computed correctly.
    # Without this, the VirtualPortfolio is empty → nav ≈ 0 when account.cash ≈ 0
    # (all equity already invested) → all target quantities ≈ 0 → 0 orders.
    alpaca_entry_prices: dict[str, float] = {}
    alpaca_positions: list = []
    try:
        alpaca_positions = trading_client.get_all_positions()
        for ap in alpaca_positions:
            qty = float(ap.qty)
            avg_cost = float(ap.avg_entry_price)
            portfolio.load_position(symbol=ap.symbol, quantity=qty, avg_cost=avg_cost)
            alpaca_entry_prices[ap.symbol] = avg_cost
        log.info("Loaded %d existing Alpaca positions into VirtualPortfolio", len(alpaca_positions))
    except Exception as exc:
        log.warning("Could not load Alpaca positions: %s — VirtualPortfolio starts empty", exc)

    # Sentiment reversal check: find held positions with strongly negative LLM signal.
    reversal_sell_symbols: set = set()
    try:
        from redis import Redis as _RedisRev
        _r_rev = _RedisRev.from_url(config.REDIS_URL, decode_responses=True)
        try:
            reversal_sell_symbols = _sentiment_reversal_sells(
                alpaca_positions,
                _r_rev,
                threshold=config.SENTIMENT_REVERSAL_EXIT_THRESHOLD,
                max_age_minutes=config.SENTIMENT_REVERSAL_MAX_AGE_MINUTES,
            )
        finally:
            _r_rev.close()
    except Exception as _rev_exc:
        log.warning("Sentiment reversal check failed: %s — skipping", _rev_exc)

    # Run orchestration cycle
    # P2-05-B: read risk limits from trading.yaml so operator changes to the config
    # are reflected in the live constraint enforcement (not silently ignored).
    _risk_cfg = _load_risk_config()

    # FIX-C: synthetic stop-loss. Notional/fractional BUYs cannot carry an Alpaca
    # bracket, so positions are force-closed here when price breaches the stop.
    # Computed before the rebalance so breached symbols are dropped from normal
    # orders and force-sold below (bypassing the hold-minimum hold).
    stop_loss_sells: dict[str, "StopDecision"] = {}
    _stop_policy: "StopPolicy" | None = None
    _pg_stop = None
    try:
        from src.portfolio.stop_policy import StopPolicy as _StopPolicy
        from src.store.pg_store import PostgreSQLStore as _PGStore

        _stop_policy = _StopPolicy(
            _risk_cfg,
            bars_df=bars_df,
            last_good_lookup=_last_good_sigma_lookup(config.REDIS_URL),
        )
        _pg_stop = _PGStore()
        stop_loss_sells = _stop_loss_breached_symbols(
            alpaca_positions, alpaca_entry_prices, market, _stop_policy, _pg_stop
        )
        if stop_loss_sells:
            log.warning("FIX-C stop-loss breached: %s", sorted(stop_loss_sells.keys()))

        # Shadow log: compare fixed vs vol_scaled triggers for every held position.
        if _risk_cfg.get("stop_shadow_enabled"):
            try:
                _shadow_rows = _build_stop_shadow_rows(
                    alpaca_positions, alpaca_entry_prices, market, _stop_policy, _pg_stop
                )
                if _shadow_rows:
                    _pg_stop.insert_stop_shadow(_shadow_rows)
            except Exception as _shadow_exc:
                log.warning("Stop shadow log failed: %s — continuing", _shadow_exc)
    except Exception as _sl_exc:
        log.warning("Stop-loss check failed: %s — proceeding without stop-loss", _sl_exc)
    finally:
        # B7/B32 (2026-07-15): return the stop-loss connection to the pool. The
        # bare _pg_stop was never closed → one leaked idle-in-transaction conn
        # per 15-min cycle (20 conns live, blocking migration 037).
        if _pg_stop is not None:
            _pg_stop.close()

    data_replay = DataReplay(bars_df)
    _vol_targeter, _vol_cfg = _build_vol_targeter()
    log.info(
        "Vol targeter config (F6): target_vol=%.4f clamp=[%.2f, %.2f]",
        _vol_cfg.get("target_vol", 0.10),
        _vol_cfg.get("clamp_low", 0.5),
        _vol_cfg.get("clamp_high", 2.0),
    )
    orchestrator = PortfolioOrchestrator(
        registry=registry,
        strategy_instances=strategy_instances,
        constraint_enforcer=ConstraintEnforcer(
            max_portfolio_exposure=_risk_cfg["max_portfolio_exposure"],
            max_single_asset_pct=_risk_cfg["max_single_asset_pct"],
            sector_map=_load_sector_map(),
            max_sector_pct=_risk_cfg.get("max_sector_exposure", 0.0),
        ),
        vol_targeter=_vol_targeter,
    )

    ts = end

    # Compute equal-weight portfolio daily returns for vol targeting.
    # Uses all symbols in bars_df so vol estimation reflects the current
    # market environment, not just the strategy's holdings.
    _strategy_returns: dict[str, list[float]] | None = None
    if bars_df is not None and not bars_df.empty and len(bars_df) >= 3:
        _ret = bars_df.pct_change().dropna(how="all")
        _port_returns = _ret.mean(axis=1).dropna().tolist()
        if len(_port_returns) >= 2:
            _strategy_returns = {"portfolio": _port_returns}

    # F8: per-strategy feedback regime scale (de-risk/re-risk throttle). The
    # scheduler reads feedback:regime_scale:S* and passes them to the orchestrator.
    # loss_feedback.apply_regime_scale gates APPLY vs SHADOW: when false the
    # orchestrator records the would-be deployment delta (CycleResult.feedback_shadow)
    # without shrinking weights — measure-before-enforce (QX-01).
    _fb_strategy_ids = [e.strategy_id for e in registry.get_active_strategies()]
    _fb_scales: dict[str, float] = _read_feedback_regime_scales(
        config.REDIS_URL, _fb_strategy_ids
    )
    # #32: the flag is bool OR an allowlist of strategy ids — the flip gate is
    # scored per strategy, so passing a bare bool would force all-or-nothing.
    # The orchestrator normalises it (_scale_gate); anything unrecognised there
    # falls back to shadow-only, so no config typo can start shrinking sizing.
    _apply_fb_scale: bool | list = False
    try:
        from src.workers.performance import _load_loss_feedback_config as _load_fb_cfg
        _raw_apply = _load_fb_cfg().get("apply_regime_scale", False)
        _apply_fb_scale = (
            _raw_apply if isinstance(_raw_apply, (bool, list, tuple)) else bool(_raw_apply)
        )
    except Exception as _fb_cfg_exc:
        log.warning("F8: could not load apply_regime_scale flag (%s) — defaulting to shadow-only", _fb_cfg_exc)

    result = orchestrator.run_cycle(
        ts=ts, data_replay=data_replay, portfolio=portfolio, market=market,
        strategy_returns=_strategy_returns,
        feedback_scales=_fb_scales or None,
        apply_feedback_scale=_apply_fb_scale,
    )

    # F8 shadow log: emit the would-be deployment delta per scaled strategy so the
    # forensic report / operator can see what regime_scale would do before it goes live.
    if result.feedback_shadow:
        import json as _fb_json
        log.info(
            "F8 feedback_scale_shadow applied=%s scales=%s",
            _apply_fb_scale,
            _fb_json.dumps(result.feedback_shadow, default=str),
        )
        # #32: persist the shadow so a real trajectory accrues (previously it
        # only lived in a 48h-TTL Redis key). Best-effort — never break the cycle.
        try:
            _f8_rows = _build_f8_shadow_rows(ts, result.feedback_shadow)
            if _f8_rows:
                from src.store.pg_store import PostgreSQLStore as _PGSf8
                _pg_f8 = _PGSf8()
                try:
                    _pg_f8.insert_f8_shadow(_f8_rows)
                finally:
                    _pg_f8.close()
        except Exception as _f8_exc:
            log.warning("F8 shadow persistence failed: %s", _f8_exc)

    log.info(
        "Portfolio cycle: strategies=%s before=%d after=%d constraints=%d final=%d",
        result.strategies_run,
        result.orders_before_constraints,
        result.orders_after_constraints,
        len(result.constraints_fired),
        len(result.final_orders),
    )

    # FIX-E: surface actionable reason when constraints eliminate all strategy orders.
    _log_constraint_block_if_needed(result, _risk_cfg)

    # FIX-C: drop any normal orders for stop-loss symbols — they are force-closed
    # separately below, so the rebalance must not also buy/sell them this cycle.
    if stop_loss_sells:
        _sl_symbols = set(stop_loss_sells.keys())
        result = type(result)(
            strategies_run=result.strategies_run,
            orders_per_strategy=result.orders_per_strategy,
            orders_before_constraints=result.orders_before_constraints,
            orders_after_constraints=result.orders_after_constraints,
            constraints_fired=result.constraints_fired,
            final_orders=[o for o in result.final_orders if o.symbol not in _sl_symbols],
            symbol_strategies=result.symbol_strategies,
        )

    # Hold minimum: don't sell positions entered in the last HOLD_MINIMUM_MINUTES.
    # Prevents buy→sell roundtrips within a single rebalance window (e.g. S4 buys
    # at 18:07, S1 rebalances at 18:22 and immediately sells the same ticker).
    _hold_min = _get_hold_minimum_minutes()
    try:
        from src.store.pg_store import PostgreSQLStore as _PGHold
        _pg_hold = _PGHold()
        try:
            _recently_bought = _pg_hold.fetch_recently_bought_symbols(_hold_min)
        finally:
            _pg_hold.close()
        if _recently_bought:
            _before_hold = len(result.final_orders)
            from src.backtest.engine.types import OrderSide as _OSHold
            result = type(result)(
                strategies_run=result.strategies_run,
                orders_per_strategy=result.orders_per_strategy,
                orders_before_constraints=result.orders_before_constraints,
                orders_after_constraints=result.orders_after_constraints,
                constraints_fired=result.constraints_fired,
                final_orders=[
                    o for o in result.final_orders
                    if not (o.side == _OSHold.SELL and o.symbol in _recently_bought)
                ],
                symbol_strategies=result.symbol_strategies,
            )
            _skipped = _before_hold - len(result.final_orders)
            if _skipped:
                log.info(
                    "Hold minimum (%d min): skipped %d SELL order(s) for recently-bought: %s",
                    _hold_min,
                    _skipped,
                    sorted(_recently_bought),
                )
    except Exception as _hold_exc:
        log.warning("Hold minimum check failed: %s — proceeding without filter", _hold_exc)

    # P0-05: pre-fetch open DB positions BEFORE decision logging so BUY decisions for symbols
    # already in an open trade are skipped (prevents polluting the decision log with duplicate
    # BUY entries on every cycle, which was the root cause of apparent stale-signal replay).
    open_db_symbols: set[str] = set()
    _open_trades: list[dict] = []
    try:
        from src.store.pg_store import PostgreSQLStore as _PGGuard
        _pg_guard = _PGGuard()
        _open_trades = _pg_guard.fetch_trades(status="open", limit=1000)
        open_db_symbols = {t["symbol"] for t in _open_trades}
        _pg_guard.close()
        if open_db_symbols:
            log.info("P0-05 pyramiding guard: %d symbols have open DB trades", len(open_db_symbols))
    except Exception as _guard_exc:
        log.warning(
            "P0-05: open-trade DB fetch failed — all BUYs blocked this cycle (fail-closed): %s",
            _guard_exc,
        )
        open_db_symbols = None
    # #72: origin strategy of each open position (trades.stop_strategy, fixed to
    # reflect CycleResult.symbol_strategies — see _resolve_buy_origin_strategy),
    # used to tag weight-0 SELLs correctly instead of always assuming S4.
    _open_trade_origin: dict[str, str] = {
        t["symbol"]: t["stop_strategy"] for t in _open_trades if t.get("stop_strategy")
    }

    # Anti-stale-ranker-sell: protect open positions with a fresh positive signal from
    # being sold when the S4 ranker returns no output due to min_stocks constraint.
    # Typical trigger: only 1 positive-strength signal exists but ranker requires 2+
    # (the 2nd signal passing abs(score) gate is negative → strength<0 → skipped).
    # Result without this: merged_weights={}, orchestrator sells all held positions
    # even if the original buy signal is still valid.
    #
    # #116: this MUST run BEFORE exit hysteresis. Hysteresis's Redis counter is
    # reset the moment it lets an order "through" (reaches persistence_cycles),
    # on the assumption the order will execute — but a downstream veto here would
    # then restart the count from zero, forever, for as long as protection keeps
    # applying. Filtering protected SELLs out first means hysteresis's counter
    # only ever advances on cycles where the order was genuinely still a sell
    # candidate (NOW, 2026-07-23, -$49.69: reset/veto sawtooth for 2h45min).
    try:
        from src.backtest.engine.types import OrderSide as _OSProtect
        from src.strategies.s4.config import S4Config as _S4CfgProt
        _prot_age = _S4CfgProt().max_signal_age_hours
        _prot_threshold = _get_feedback_threshold(config.REDIS_URL, strategy="S4")
        _sell_candidates: set[str] = {
            o.symbol for o in result.final_orders
            if o.side == _OSProtect.SELL
            and o.allocation_weight == 0.0
            and not result.symbol_strategies.get(o.symbol)
            and isinstance(open_db_symbols, set)
            and o.symbol in open_db_symbols
        }
        if _sell_candidates:
            from src.store.pg_store import PostgreSQLStore as _PGProt
            _pg_prot = _PGProt()
            try:
                _protected = _fresh_signal_protected_symbols(
                    _sell_candidates, _pg_prot, _prot_threshold, _prot_age
                )
            finally:
                _pg_prot.close()
            if _protected:
                result = type(result)(
                    strategies_run=result.strategies_run,
                    orders_per_strategy=result.orders_per_strategy,
                    orders_before_constraints=result.orders_before_constraints,
                    orders_after_constraints=result.orders_after_constraints,
                    constraints_fired=result.constraints_fired,
                    final_orders=[
                        o for o in result.final_orders
                        if not (o.side == _OSProtect.SELL and o.symbol in _protected)
                    ],
                    symbol_strategies=result.symbol_strategies,
                )
                log.info(
                    "Anti-stale-ranker-sell: protected %d position(s) from rebalance SELL "
                    "(fresh positive signal >= %.3f): %s",
                    len(_protected), _prot_threshold, sorted(_protected),
                )
    except Exception as _prot_exc:
        log.warning("Anti-stale-ranker-sell check failed: %s — proceeding without protection", _prot_exc)

    # Exit hysteresis: require a position to be targeted for exit for N consecutive
    # cycles before selling — kills the buy->sell->buy flicker that the bigger sizes
    # (regime fix) amplified. Stop-loss / reversal sells are unaffected (not in final_orders).
    try:
        _persist = _get_exit_persistence_cycles()
        _before_hyst = len(result.final_orders)
        _hyst_orders = _apply_exit_hysteresis(result.final_orders, config.REDIS_URL, _persist)
        if len(_hyst_orders) != _before_hyst:
            result = type(result)(
                strategies_run=result.strategies_run,
                orders_per_strategy=result.orders_per_strategy,
                orders_before_constraints=result.orders_before_constraints,
                orders_after_constraints=result.orders_after_constraints,
                constraints_fired=result.constraints_fired,
                final_orders=_hyst_orders,
                symbol_strategies=result.symbol_strategies,
            )
    except Exception as _hyst_exc:
        log.warning("Exit hysteresis failed: %s — proceeding without it", _hyst_exc)

    # Stop-loss cooldown: symbols stopped out today — BUY blocked for the rest of the session.
    stopped_today: set[str] = _get_stop_loss_cooldown_symbols(config.REDIS_URL)
    if stopped_today:
        log.info("Stop-loss cooldown active for: %s", sorted(stopped_today))

    # Log decisions to execution_decisions so the UI Decision Log tab is populated.
    # Also capture decision_ids for later trade DB writes.
    _symbol_decisions: dict[str, dict] = {}  # {symbol: {decision_id, score, signal_id}}
    _pending_s4_fires: dict[str, int] = {}   # B27-FIX: {symbol: signal_id} to mark after Alpaca confirm
    _s4_signals: dict[str, dict] = {}
    # P0-09: read actual regime multiplier once; used in both decisions and trade writes.
    _regime_mult: float = _get_regime_multiplier_from_redis(config.REDIS_URL)
    _pg = None
    try:
        from src.store.pg_store import PostgreSQLStore
        _pg = PostgreSQLStore()
        # symbol_strategies maps each symbol to the list of strategies that contributed
        # to its merged weight (e.g. {"AAPL": ["S4"], "SPY": ["S2"]}).
        _sym_strats = result.symbol_strategies
        _s4_symbols = [sym for sym, strats in _sym_strats.items() if "S4" in strats]
        # B33-follow-up: use the signal pinned by the ranker at weight-computation
        # time (result.symbol_signal_provenance) instead of re-querying "latest
        # signal" here. A re-query can race a signal that arrives between ranking
        # and this point in the cycle, silently mis-attributing the decision/
        # idempotency-fire to a different signal than the one that was actually
        # ranked (2026-07-15 MSFT incident: ranker used +0.165, re-fetch picked up
        # a -0.110 signal that arrived 34s later). Fall back to the live re-fetch
        # only for S4 symbols the orchestrator did not pin (should not happen in
        # practice — defensive only).
        _s4_provenance: dict[str, dict] = result.symbol_signal_provenance or {}
        _unpinned_s4_symbols = [s for s in _s4_symbols if s not in _s4_provenance]
        _signal_ids = dict(_pg.fetch_latest_signal_ids(_unpinned_s4_symbols)) if _unpinned_s4_symbols else {}
        for _sym in _s4_symbols:
            _prov_sid = _s4_provenance.get(_sym, {}).get("signal_id")
            if _prov_sid is not None:
                _signal_ids[_sym] = _prov_sid
        # P1-S4-IDEMPOTENCY: skip S4 orders whose signal_id already fired today.
        _session_date = ts.strftime("%Y-%m-%d")
        _fired_ids = _get_fired_signal_ids(_session_date, config.REDIS_URL)
        _idempotency_skip: set[str] = set()
        if _fired_ids is None:
            # P2-05-A: Redis unavailable — fail-closed: skip ALL S4 BUY signals this cycle.
            # We cannot verify whether any signal has already been executed today, so we
            # conservatively treat all S4 BUY symbols as already-fired.
            _idempotency_skip = set(_signal_ids.keys())
            log.warning(
                "P2-05-A: Redis unavailable for idempotency check — all %d S4 BUY signals skipped (fail-closed)",
                len(_idempotency_skip),
            )
        else:
            for _sym, _sid in _signal_ids.items():
                if _sid in _fired_ids:
                    _idempotency_skip.add(_sym)
                    log.warning(
                        "P1-S4: signal_id=%s for %s already fired today — skipping (SIGNAL_DUPLICATE_SKIP)",
                        _sid, _sym,
                    )
                    try:
                        _pg.write_audit_log(
                            action="SIGNAL_DUPLICATE_SKIP",
                            table_name="sentiment_signals",
                            record_id=_sid,
                            details={"symbol": _sym, "signal_id": _sid, "session_date": _session_date},
                        )
                    except Exception as _ae:
                        log.warning("P1-S4: duplicate audit write failed: %s", _ae)
        # Load S4 signal details (score + reasoning) for the reason text.
        # B33-follow-up: prefer the pinned provenance (see above) — only fall
        # back to a fresh fetch_signals_for_cycle for symbols the orchestrator
        # did not pin (defensive; should not happen for a symbol with "S4" in
        # _sym_strats this cycle).
        _s4_signals: dict[str, dict] = {
            sym: {
                "score": prov["score"],
                "reasoning": prov["reasoning"],
                "model_id": prov["model_id"],
            }
            for sym, prov in _s4_provenance.items()
        }
        _unpinned_for_signals = [s for s in _s4_symbols if s not in _s4_signals]
        if _unpinned_for_signals:
            try:
                # #109: derive score/reasoning from the SAME signal_id resolved
                # above (fetch by exact id), not a separate "latest signal" query
                # — the two could resolve to different signals and desync the
                # logged conviction (WDC: id=finbert +0.363, score=ensemble −0.385).
                _unpinned_ids = {
                    s: _signal_ids[s] for s in _unpinned_for_signals if s in _signal_ids
                }
                _by_id_rows = (
                    _pg.fetch_signals_by_ids(list(_unpinned_ids.values()))
                    if _unpinned_ids else []
                )
                _s4_signals.update(_s4_signal_metadata_by_id(_unpinned_ids, _by_id_rows))
            except Exception:
                pass
        # FIX-F: pre-fetch last signal (any age, up to 48h) for SELL-weight-0 orders
        # that have no strategy attribution. These are typically stale-expiry closes
        # and need an informative reason ("signal expired 20.3h ago") not the generic
        # "Portfolio rebalance: weight 0.0%".
        from src.backtest.engine.types import OrderSide as _OSReason
        _zero_sell_syms = [
            o.symbol for o in result.final_orders
            if o.side == _OSReason.SELL
            and o.allocation_weight == 0.0
            and not _sym_strats.get(o.symbol)
        ]
        _zero_sell_signals: dict[str, dict] = {}
        if _zero_sell_syms:
            try:
                _zero_raw = _pg.fetch_signals_for_cycle(hours=48, symbols=_zero_sell_syms)
                for _zs in _zero_raw:
                    # Keep most recent per symbol
                    if _zs.symbol not in _zero_sell_signals or \
                            _zs.generated_at > _zero_sell_signals[_zs.symbol]["generated_at"]:
                        _zero_sell_signals[_zs.symbol] = {
                            "generated_at": _zs.generated_at,
                            "score": _zs.score,
                        }
            except Exception as _zse:
                log.warning("FIX-F: stale-signal lookup failed: %s", _zse)
        from src.strategies.s4.config import S4Config as _S4Config
        _s4_max_age_h = _S4Config().max_signal_age_hours
        # #61: symbols whose weight-0 SELL the anti-whipsaw damper suppressed this
        # cycle — filtered out of _orders_to_submit below (never affects BUYs).
        _whipsaw_suppressed_symbols: set[str] = set()
        _anti_whipsaw_enabled = bool(_risk_cfg.get("s4_anti_whipsaw_damping_enabled", False))
        _anti_whipsaw_confirm_cycles = int(_risk_cfg.get("s4_anti_whipsaw_confirm_cycles", 2))
        for order in result.final_orders:
            strats = _sym_strats.get(order.symbol, [])
            # P1-S4-IDEMPOTENCY: skip this order if its signal_id was already fired today.
            if order.symbol in _idempotency_skip:
                continue
            # P0-05: skip BUY decision for symbols already in an open trade (no pyramiding).
            if order.side.value == "BUY" and isinstance(open_db_symbols, set) and order.symbol in open_db_symbols:
                log.info("P0-05: skipping BUY decision for %s — already has an open trade", order.symbol)
                continue
            # Stop-loss cooldown: skip BUY for symbols stopped out earlier today.
            if order.side.value == "BUY" and order.symbol in stopped_today:
                log.info("Stop-loss cooldown: skipping BUY for %s — stopped out today", order.symbol)
                continue
            wt_pct = f"{order.allocation_weight * 100:.1f}%"
            exit_mechanism: str | None = None
            if "S4" in strats:
                sig = _s4_signals.get(order.symbol, {})
                sig_score = sig.get("score", 0.0)
                sig_model = sig.get("model_id", "unknown")
                sig_reasoning = (sig.get("reasoning") or "")[:200]
                other = [s for s in strats if s != "S4"]
                prefix = f"S4+{'+'.join(other)}" if other else "S4"
                reason = (
                    f"{prefix} news-driven: sentiment {sig_score:+.3f} ({sig_model}), "
                    f"portfolio weight {wt_pct}. {sig_reasoning}"
                ).strip()
            elif "S1" in strats and "S2" not in strats:
                reason = f"S1 momentum: time-series momentum signal, portfolio weight {wt_pct}."
            elif "S2" in strats and "S1" not in strats:
                reason = f"S2 VRP: volatility risk premium signal, portfolio weight {wt_pct}."
            elif strats:
                reason = f"{'+'.join(strats)}: merged portfolio weight {wt_pct}."
            else:
                # FIX-F: for SELL-weight-0 with no strategy attribution, surface the
                # real cause (signal expiry, missing signal, etc.) rather than the
                # generic "Portfolio rebalance: weight 0.0%" which gave no insight.
                if order.side.value == "SELL" and order.allocation_weight == 0.0:
                    _origin_strategy = _open_trade_origin.get(order.symbol)
                    if _origin_strategy and _origin_strategy != "S4":
                        # #72: the position was opened by a non-S4 strategy — the
                        # S4-specific classifier below would always misleadingly
                        # tag this [no_signal] (trivially true, it never had an
                        # S4 signal). Whipsaw damping (#61) is S4-only, skip it.
                        exit_mechanism, reason = _reason_and_mechanism_for_non_s4_weight_drop(
                            order.symbol, _origin_strategy, wt_pct
                        )
                        if _origin_strategy == "S1":
                            # #71: start the re-entry cooldown regardless of the
                            # enforce flag, so shadow frequency is measurable and
                            # a later flip doesn't start cold. Enforcement (the
                            # actual BUY-skip) happens in _submit_portfolio_orders.
                            _mark_s1_reentry_cooldown(
                                config.REDIS_URL, order.symbol,
                                minutes=float(_risk_cfg.get("s1_reentry_cooldown_minutes", 30)),
                            )
                    else:
                        _zero_sig = _zero_sell_signals.get(order.symbol)
                        reason = _reason_for_zero_weight_sell(order.symbol, _zero_sig, _s4_max_age_h)
                        # #60: structured tag alongside the reason text (queryable
                        # without parsing free text — see #61 anti-whipsaw damping).
                        exit_mechanism = _classify_zero_weight_exit(_zero_sig, _s4_max_age_h)

                        # #61: require N consecutive "whipsaw" cycles before letting
                        # this SELL through. Streak is always tracked (so a later
                        # flag-flip doesn't start cold); only actually suppressed
                        # when enabled.
                        _prior_streak = _get_whipsaw_streak(config.REDIS_URL, order.symbol)
                        _damping = evaluate_whipsaw_damping(
                            exit_mechanism == "whipsaw", _prior_streak, _anti_whipsaw_confirm_cycles
                        )
                        _set_whipsaw_streak(config.REDIS_URL, order.symbol, _damping.new_streak)
                        if exit_mechanism == "whipsaw":
                            if _anti_whipsaw_enabled and _damping.suppress:
                                _whipsaw_suppressed_symbols.add(order.symbol)
                                log.info(
                                    "#61 anti-whipsaw damping: holding %s one more cycle "
                                    "(streak=%d/%d)", order.symbol, _damping.new_streak,
                                    _anti_whipsaw_confirm_cycles,
                                )
                                continue
                            if not _anti_whipsaw_enabled:
                                # Shadow: flag is off, SELL proceeds unchanged — annotate
                                # what damping WOULD have done for frequency measurement.
                                reason = (
                                    f"{reason} [anti_whipsaw_shadow: would_suppress="
                                    f"{_damping.suppress}, streak={_damping.new_streak}/"
                                    f"{_anti_whipsaw_confirm_cycles}]"
                                )
                else:
                    reason = f"Portfolio rebalance: weight {wt_pct}."
            decision_id = _pg.write_execution_decision(
                tick_time=ts,
                symbol=order.symbol,
                signal_id=_signal_ids.get(order.symbol),
                score=order.allocation_weight,
                signal_score=_s4_signals.get(order.symbol, {}).get("score") if "S4" in strats else None,
                regime_mult=_regime_mult,
                ema_pass=True,
                decision=order.side.value,
                reason=reason,
                exit_mechanism=exit_mechanism,
            )
            _symbol_decisions[order.symbol] = {
                "decision_id": decision_id,
                "score": order.allocation_weight,
                "signal_id": _signal_ids.get(order.symbol),
                # LLM sentiment score — distinct from allocation_weight stored in score.
                "signal_score": _s4_signals.get(order.symbol, {}).get("score") if "S4" in strats else None,
            }
            # B27-FIX: collect S4 signals to mark as fired AFTER Alpaca confirmation.
            # Previously fired here (before submission), causing signals to be consumed
            # even when the order was skipped (dry-run, halt, broker reject, etc.).
            _fired_sig_id = _signal_ids.get(order.symbol)
            if _fired_sig_id is not None and "S4" in strats and order.side.value == "BUY":
                _pending_s4_fires[order.symbol] = _fired_sig_id
    except Exception as _exc:
        log.warning("Failed to log portfolio decisions: %s", _exc)
    finally:
        # B7/B32: return the decisions-log connection to the pool on every path.
        if _pg is not None:
            _pg.close()

    # Check operating mode before submitting orders
    operating_mode = None
    try:
        from redis import Redis as _Redis
        _r = _Redis.from_url(config.REDIS_URL, decode_responses=True)
        try:
            operating_mode = _r.get("system:mode")
        finally:
            _r.close()
    except Exception as exc:
        log.warning("Could not read system:mode from Redis: %s — proceeding with submission", exc)

    if operating_mode in ("dry_run", "halted"):
        log.info("Skipping order submission - %s mode", operating_mode)
        submitted_orders: list[dict] = []
    elif _is_ks_active_failclosed(config.REDIS_URL):
        # P0-06: re-check kill-switch immediately before submission to close the race window.
        # Kill-switch may have been activated after the B2 check at cycle start.
        log.warning("P0-06: Kill-switch active at pre-submission re-check — aborting order submission")
        _emergency_cancel_all(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        try:
            from src.store.pg_store import PostgreSQLStore as _PGKsAudit
            _pg_ks = _PGKsAudit()
            _pg_ks.write_audit_log(
                action="KILLSWITCH_ACTIVATE",
                details={"event": "pre_submission_abort", "source": "portfolio_scheduler"},
            )
            _pg_ks.close()
        except Exception as _ks_audit_exc:
            log.warning("P0-06: Failed to write KS pre-submission audit row: %s", _ks_audit_exc)
        submitted_orders = []
    else:
        fractionable = _get_fractionable_symbols(trading_client)
        # open_db_symbols already fetched before decision logging (P0-05 pre-fetch above).
        # P2-05-A: exclude S4 BUY orders for symbols whose idempotency check was skipped
        # (Redis unavailable). SELLs and non-S4 orders are not affected.
        _orders_to_submit = _apply_idempotency_filter(result.final_orders, _idempotency_skip)
        _orders_to_submit = _apply_whipsaw_damping_filter(_orders_to_submit, _whipsaw_suppressed_symbols)
        submitted_orders = _submit_portfolio_orders(
            _orders_to_submit, trading_client, market,
            fractionable_symbols=fractionable,
            open_trade_symbols=open_db_symbols,  # None = guard unavailable → fail-closed
            regime_mult=_regime_mult,
            risk_cfg=_risk_cfg,
            bars_df=bars_df,
            stop_policy=_stop_policy,
            nav=equity,
            open_trades=_open_trades,
            sym_strats=_sym_strats,
        )

        # #62/#63: reconcile broker-side protective stops for fractional positions.
        # Best-effort — a failure here must never block order submission (already
        # completed above) or the rest of the cycle.
        if _stop_policy is not None and config.ALPACA_FRACTIONAL_STOP_ENABLED:
            try:
                _sync_fractional_protective_stops(trading_client, _stop_policy, ts)
            except Exception as _sync_exc:
                log.warning("Fractional protective stop sync failed: %s", _sync_exc)

    # B27-FIX: mark S4 signals fired only for orders that were actually submitted to Alpaca.
    # Previously this happened during decision logging (before submission), causing signals
    # to be consumed even when the order was skipped (dry-run, halt, broker reject, etc.).
    _submitted_buy_symbols = {o["symbol"] for o in submitted_orders if o.get("side") == "buy"}
    for _sym, _sid in _pending_s4_fires.items():
        if _sym in _submitted_buy_symbols:
            _mark_signal_fired(_sid, _session_date, config.REDIS_URL)
        else:
            log.debug("B27: S4 signal_id=%s for %s NOT marked fired — order not submitted", _sid, _sym)

    # B28-FIX: write BUY trade rows to DB immediately after Alpaca confirms the order.
    # Previously all writes happened in a batch at the end of the cycle (after stop-loss
    # and reversal sells), creating an orphan window: Alpaca held the position but DB had
    # no record, so the next cycle's anti-pyramiding guard would allow a duplicate BUY.
    # SELLs are written later (in the existing batch); the orphan risk for sells is low
    # (the guard only blocks BUYs, not SELLs on already-gone positions).
    _written_buy_order_ids: set[str] = set()
    _buy_orders_to_write = [o for o in submitted_orders if o.get("side") == "buy"]
    if _buy_orders_to_write:
        try:
            from src.store.pg_store import PostgreSQLStore as _PGTradesEarly
            _pg_early = _PGTradesEarly()
            for _sub_b in _buy_orders_to_write:
                _sym_b = _sub_b["symbol"]
                _dec_b = _symbol_decisions.get(_sym_b, {})
                # Freeze stop params at entry using the best available price.
                _raw_px = market.prices.get(_sym_b) if market and getattr(market, "prices", None) else None
                _entry_px_b = float(_raw_px) if isinstance(_raw_px, (int, float)) and not isinstance(_raw_px, bool) else None
                if _entry_px_b is None and _sub_b.get("qty"):
                    _entry_px_b = _sub_b["notional"] / _sub_b["qty"]
                if _entry_px_b is None:
                    _entry_px_b = float(_sub_b["notional"]) if _sub_b.get("notional") else 0.0
                _strategy_b = _resolve_buy_origin_strategy(_sym_b, _sym_strats, _dec_b)
                try:
                    if _stop_policy is None:
                        from src.portfolio.stop_policy import StopPolicy as _StopPolicyFreeze
                        _stop_policy = _StopPolicyFreeze(_risk_cfg, bars_df=bars_df)
                    _frozen_stop = _stop_policy.freeze(
                        _sym_b, _strategy_b, float(_entry_px_b), ts
                    )
                    # Persist non-default sigma for future cycles (last_good fallback).
                    if _frozen_stop and _frozen_stop.sigma_eff is not None:
                        _update_last_good_sigma(config.REDIS_URL, _sym_b, _frozen_stop.sigma_eff)
                except Exception as _freeze_exc:
                    log.warning("Failed to freeze stop for %s: %s", _sym_b, _freeze_exc)
                    _frozen_stop = None
                _pg_early.open_trade(
                    symbol=_sym_b,
                    signal_id=_dec_b.get("signal_id"),
                    decision_id=_dec_b.get("decision_id"),
                    entry_order_id=_sub_b["order_id"],
                    entry_time=ts,
                    entry_notional=_sub_b["notional"],
                    score=_dec_b.get("score", 0.0),
                    regime_mult=_regime_mult,
                    signal_score=_dec_b.get("signal_score"),
                    frozen_stop=_frozen_stop,
                )
                _written_buy_order_ids.add(_sub_b["order_id"])
            _pg_early.close()
        except Exception as _exc_b:
            log.warning("B28: Failed to write BUY trade rows after submission: %s", _exc_b)

    # FIX-C: submit synthetic stop-loss exits. Force-close positions that breached the
    # stop threshold. Runs regardless of the hold-minimum (protection takes priority).
    if stop_loss_sells and operating_mode not in ("dry_run", "halted"):
        for sym, _sl_dec in sorted(stop_loss_sells.items()):
            try:
                from alpaca.trading.enums import OrderSide as _OSsl, TimeInForce as _TIFsl
                from alpaca.trading.requests import MarketOrderRequest as _MORsl
                qty_held = next(
                    (float(p.qty) for p in alpaca_positions if p.symbol == sym), None
                )
                if qty_held and qty_held > 0:
                    # #62 regression: free the whole-share qty reserved by the
                    # protective GTC stop or the full-qty SELL is rejected (40310000).
                    from src.portfolio.fractional_stop_orders import cancel_open_stop_sells as _coss
                    _n_freed_sl = _coss(trading_client, sym)
                    if _n_freed_sl:
                        log.info(
                            "Cancelled %d protective stop(s) for %s before stop-loss exit",
                            _n_freed_sl, sym,
                        )
                    resp = trading_client.submit_order(_MORsl(
                        symbol=sym, qty=qty_held, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
                    ))
                    _order_id = str(resp.id)
                    submitted_orders.append({
                        "symbol": sym, "side": "sell", "order_id": _order_id,
                        "notional": 0.0, "reason": "stop_loss",
                    })
                    log.warning("Stop-loss exit submitted for %s (qty=%s)", sym, qty_held)
                    _mark_stop_loss_today(config.REDIS_URL, sym)
                    # Persist stop_decisions fire log + Decision Log SELL row.
                    _pg_sl = None
                    try:
                        from src.store.pg_store import PostgreSQLStore as _PGS
                        _pg_sl = _PGS()
                        _pg_sl.insert_stop_decision(_sl_dec, _order_id)
                        _pg_sl.write_execution_decision(
                            tick_time=ts,
                            symbol=sym,
                            signal_id=None,
                            score=0.0,
                            signal_score=None,
                            regime_mult=_regime_mult,
                            ema_pass=True,
                            decision="SELL",
                            order_id=_order_id,
                            reason=(
                                f"stop_loss: {sym} px {_sl_dec.observed_price:.2f} "
                                f"<= trigger {_sl_dec.trigger_price:.2f} "
                                f"(d_init {_sl_dec.d_init:.2%}, "
                                f"mode {_sl_dec.mode}, "
                                f"strat {_sl_dec.strategy})"
                            ),
                        )
                    except Exception as _dec_exc:
                        log.warning("Failed to write stop-loss decision for %s: %s", sym, _dec_exc)
                    finally:
                        if _pg_sl is not None:
                            try:
                                _pg_sl.close()
                            except Exception:
                                pass
            except Exception as _sl_sub_exc:
                log.warning("Failed to submit stop-loss exit for %s: %s", sym, _sl_sub_exc)

    # Submit forced sells for sentiment reversal (symbols not already being sold).
    _submit_reversal_force_sells(
        reversal_sell_symbols=reversal_sell_symbols,
        final_orders=result.final_orders,
        stop_loss_sells=stop_loss_sells,
        alpaca_positions=alpaca_positions,
        trading_client=trading_client,
        submitted_orders=submitted_orders,
        ts=ts,
        regime_mult=_regime_mult,
        operating_mode=operating_mode,
    )

    # P2-04: fire divergence alerts if signals and submitted orders don't match.
    _check_divergence_and_alert(
        signal_syms=set(_s4_signals.keys()),
        order_syms={o["symbol"] for o in submitted_orders},
        submitted_count=len(submitted_orders),
        final_count=len(result.final_orders),
        notifier=notifier,
    )

    # Write trade entries/exits to DB for P&L tracking.
    # Also back-fill the Alpaca order_id on execution_decisions rows.
    # B33 (2026-07-15): per-order isolation — one failing order no longer aborts
    # the rest. See _persist_trade_fills.
    if submitted_orders:
        _persist_trade_fills(
            submitted_orders,
            open_trades=_open_trades,
            symbol_decisions=_symbol_decisions,
            written_buy_order_ids=_written_buy_order_ids,
            stop_policy=_stop_policy,
            market=market,
            alpaca_entry_prices=alpaca_entry_prices,
            s4_signals=_s4_signals,
            regime_mult=_regime_mult,
            tick_time=ts,
            sym_strats=_sym_strats,
        )

    # Alert when an approved strategy consistently produces zero target weights.
    # This catches silent strategy death (e.g. S1 killed by a single sparse ticker).
    try:
        _check_strategy_zero_weights(
            result=result,
            active_strategy_ids={e.strategy_id for e in active},
            redis_url=config.REDIS_URL,
            notifier=notifier,
        )
    except Exception as _zw_exc:
        log.warning("Strategy zero-weight alert failed: %s", _zw_exc)

    _persist_cycle_result({
        "timestamp": end,
        "strategies_run": result.strategies_run,
        "orders_count": len(result.final_orders),
        "constraints_fired": [str(c) for c in result.constraints_fired],
        "final_orders": [str(o) for o in result.final_orders],
    })

    return {
        "strategies_run": result.strategies_run,
        "orders_before_constraints": result.orders_before_constraints,
        "orders_after_constraints": result.orders_after_constraints,
        "constraints_fired": len(result.constraints_fired),
        "final_orders": len(result.final_orders),
        "submitted": len(submitted_orders),
    }


_STRATEGY_ZERO_WEIGHTS_KEY = "strategy:zero_weights_cycles:{strategy_id}"
# ~1 trading day at 15-min cadence. A strategy can legitimately produce 0 weights
# for a few cycles at market open or during data gaps; alerting at 3 cycles (~45 min)
# produced spam. 24 cycles catches real silent-death (S1 was dead for 5 weeks).
_STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES = 24
_STRATEGY_ZERO_WEIGHTS_TTL = 7 * 24 * 3600  # 7 days


def _check_strategy_zero_weights(
    result,
    active_strategy_ids: set[str],
    redis_url: str,
    notifier,
) -> None:
    """Track consecutive cycles with zero target weights and alert when stuck.

    A strategy that returns empty target weights for several cycles while still
    enabled is likely data-starved or broken (e.g. S1 sparse-ticker poisoning).
    The alert fires once when the streak reaches the threshold.
    """
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
    except Exception as exc:
        log.warning("Could not connect to Redis for zero-weights tracking: %s", exc)
        return

    try:
        # Strategies that ran but produced 0 weights, plus active strategies that
        # did not run at all (instance build failed).
        zero_weight_ids: set[str] = set()
        for sid in active_strategy_ids:
            if sid not in result.strategies_run:
                zero_weight_ids.add(sid)
            elif result.orders_per_strategy.get(sid, 0) == 0:
                zero_weight_ids.add(sid)

        for sid in active_strategy_ids:
            key = _STRATEGY_ZERO_WEIGHTS_KEY.format(strategy_id=sid)
            if sid in zero_weight_ids:
                streak = int(r.incr(key))
                r.expire(key, _STRATEGY_ZERO_WEIGHTS_TTL)
                # Alert at every threshold multiple so a double increment (e.g.
                # manual cycle trigger overlapping a beat cycle) does not skip
                # the notification permanently.
                if streak > 0 and streak % _STRATEGY_ZERO_WEIGHTS_ALERT_CYCLES == 0:
                    msg = (
                        f"⚠️ *Strategia silenziosa*: {sid} ha prodotto 0 pesi "
                        f"per {streak} cicli consecutivi. "
                        f"Verificare dati/istanza."
                    )
                    _fire_alert(notifier, msg, AlertLevel.WARNING)
                    log.warning(
                        "STRATEGY_ZERO_WEIGHTS: %s produced 0 weights for %d consecutive cycles",
                        sid, streak,
                    )
            else:
                r.delete(key)
    except Exception as exc:
        log.warning("Strategy zero-weights tracking failed: %s", exc)
    finally:
        try:
            r.close()
        except Exception:
            pass


def _apply_zeygos_filter(symbols: list[str], pg) -> list[str]:
    """Intersect symbols with the latest Zeygos universe (score >= 65).

    Fail-open: returns the original list unchanged if no Zeygos data is available
    or the intersection would be empty.
    """
    try:
        universe = pg.fetch_zeygos_universe()
        if not universe:
            return symbols
        filtered = [s for s in symbols if s in universe]
        if not filtered:
            log.warning(
                "Zeygos filter would eliminate all S4 symbols — skipping filter"
            )
            return symbols
        log.info("Zeygos filter: %d → %d symbols", len(symbols), len(filtered))
        return filtered
    except Exception as exc:
        log.warning("Zeygos filter failed: %s — using unfiltered symbols", exc)
        return symbols


def _strategy_symbols(entry) -> list[str]:
    from src.config import config
    syms = list(config.WATCHLIST_SYMBOLS or [])
    if entry.strategy_id == "S2" and "SPY" not in syms:
        syms.append("SPY")
    return syms


# Idempotency store for SKIP_STALE logging: a signal is identified by symbol+generated_at
# (unique per sentiment_signals row). TTL comfortably exceeds S4's signals_lookback_hours
# (96h) so a signal never falls out of the idempotency set while it could still be re-scanned.
_STALE_LOGGED_SIGNALS_KEY = "s4:logged_stale_signals"
_STALE_LOGGED_TTL_SECONDS = 10 * 24 * 3600  # 10 days


def _stale_signal_key(symbol: str, generated_at) -> str:
    from datetime import timezone
    gen = generated_at
    if getattr(gen, "tzinfo", None) is None:
        gen = gen.replace(tzinfo=timezone.utc)
    return f"{symbol}|{gen.isoformat()}"


def _get_logged_stale_signal_keys(redis_url: str) -> set[str] | None:
    """Return signal keys already logged as SKIP_STALE, or None if Redis is unreachable.

    Unlike the S4 fired-signal idempotency gate (which fails CLOSED to protect against
    duplicate orders), this fails OPEN: callers should treat None as "nothing logged yet"
    and log anyway — a duplicate Decision Log row is a minor nuisance, but silently
    dropping visibility into a strong signal is the exact bug this store exists to fix.
    """
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            return set(r.smembers(_STALE_LOGGED_SIGNALS_KEY))
        finally:
            r.close()
    except Exception as exc:
        log.warning("Could not read logged-stale-signal set from Redis: %s", exc)
        return None


def _mark_stale_signals_logged(keys: list[str], redis_url: str) -> None:
    """Add signal keys to the idempotency set; refresh TTL. Fail-silent."""
    if not keys:
        return
    try:
        import redis as _redis
        r = _redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            r.sadd(_STALE_LOGGED_SIGNALS_KEY, *keys)
            r.expire(_STALE_LOGGED_SIGNALS_KEY, _STALE_LOGGED_TTL_SECONDS)
        finally:
            r.close()
    except Exception as exc:
        log.warning("Failed to mark stale signals as logged: %s", exc)


def _load_entry_threshold_baseline() -> float:
    """loss_feedback.threshold_baseline from config/trading.yaml (fallback 0.30). Used as
    the ORDER-GATE FLOOR when feedback:entry_threshold is absent (expired) — so the gate
    never drops to the min_score prefilter (0.10) and let weak signals trade."""
    try:
        import os

        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "..", "config", "trading.yaml")
        with open(path) as f:
            return float(yaml.safe_load(f).get("loss_feedback", {}).get("threshold_baseline", 0.30))
    except Exception:
        return 0.30


_ENTRY_THRESHOLD_BASELINE = _load_entry_threshold_baseline()


def _record_gate_drops(dropped_df, threshold: float) -> None:
    """Write SKIP_THRESHOLD rows to execution_decisions for signals the S4 feedback
    gate dropped (score below threshold), so the Decision Log explains no-trade cycles
    instead of being silently empty. Fail-safe — never breaks the cycle.
    """
    try:
        from datetime import datetime, timezone

        from src.config import config
        from src.store.pg_store import PostgreSQLStore

        regime_mult = _get_regime_multiplier_from_redis(config.REDIS_URL)
        now = datetime.now(timezone.utc)
        pg = PostgreSQLStore()
        for _, row in dropped_df.iterrows():
            sig_score = float(row["score"])
            pg.write_execution_decision(
                tick_time=now,
                symbol=str(row["symbol"]),
                signal_id=None,
                score=0.0,  # no allocation weight — it never reached ranking
                regime_mult=regime_mult,
                ema_pass=False,
                decision="SKIP_THRESHOLD",
                reason=f"score {abs(sig_score):.3f} < feedback threshold {threshold:.3f}",
                signal_score=sig_score,
            )
    except Exception as exc:
        log.warning("Failed to log gate-dropped signals: %s", exc)


def _record_stale_drops(stale_signals, max_age_hours: int, min_score: float) -> None:
    """Write SKIP_STALE rows for signals that (a) mattered (|score| >= min_score) AND
    (b) have not already been logged (idempotency set keyed by symbol+generated_at).

    Signals generated late enough in the session that no cycle runs again before they
    age past max_age (e.g. after-close signals, first evaluated 16h+ later at the next
    day's opening cycle) must still get exactly one Decision Log entry — not be silently
    dropped forever. The idempotency check (rather than a recency cutoff) also prevents
    re-logging the same old signal on every subsequent 15-min re-scan of the
    signals_lookback_hours window. Fail-safe — never breaks the cycle.
    """
    try:
        from datetime import datetime, timezone

        from src.config import config
        from src.store.pg_store import PostgreSQLStore

        notable = [s for s in stale_signals if abs(float(s.score)) >= min_score]
        if not notable:
            return

        already_logged = _get_logged_stale_signal_keys(config.REDIS_URL)
        if already_logged is None:
            already_logged = set()  # fail open: Redis down → log anyway, dedupe later

        to_log = [s for s in notable if _stale_signal_key(s.symbol, s.generated_at) not in already_logged]
        if not to_log:
            return

        now = datetime.now(timezone.utc)
        regime_mult = _get_regime_multiplier_from_redis(config.REDIS_URL)
        pg = PostgreSQLStore()
        logged_keys: list[str] = []
        for sig in to_log:
            gen = sig.generated_at
            if getattr(gen, "tzinfo", None) is None:
                gen = gen.replace(tzinfo=timezone.utc)
            age_h = (now - gen).total_seconds() / 3600.0
            pg.write_execution_decision(
                tick_time=now,
                symbol=sig.symbol,
                signal_id=None,
                score=0.0,
                regime_mult=regime_mult,
                ema_pass=False,
                decision="SKIP_STALE",
                reason=f"signal {age_h:.1f}h old > max_age {max_age_hours}h (score {float(sig.score):.3f})",
                signal_score=float(sig.score),
            )
            logged_keys.append(_stale_signal_key(sig.symbol, sig.generated_at))
        _mark_stale_signals_logged(logged_keys, config.REDIS_URL)
    except Exception as exc:
        log.warning("Failed to log stale-dropped signals: %s", exc)


def _build_strategy_instance(entry, bars_df):
    from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum
    from src.strategies.s2.strategy import VRPStrategy
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config

    sid = entry.strategy_id

    if sid == "S1":
        if len(bars_df) < 21:
            log.warning("S1 needs >=21 bars, got %d — skipping", len(bars_df))
            return None
        return TimeSeriesMomentum(prices=bars_df, config=S1Config())

    if sid == "S2":
        if len(bars_df) < 63:
            log.warning("S2 needs >=63 bars, got %d — skipping", len(bars_df))
            return None
        return VRPStrategy(prices=bars_df)

    if sid == "S4":
        from src.store.pg_store import PostgreSQLStore
        # #81: lone-survivor concentration cap, off by default.
        _fixed_slot = bool(_load_risk_config().get("s4_fixed_slot_sizing_enabled", True))
        s4_config = S4Config(fixed_slot_sizing=_fixed_slot)
        signals_df = None
        store = None
        try:
            store = PostgreSQLStore()
            from src.config import config as _cfg
            s4_symbols = list(_cfg.WATCHLIST_SYMBOLS or [])
            signals = store.fetch_signals_for_cycle(
                hours=s4_config.signals_lookback_hours,
                symbols=s4_symbols,
                news_age_hours=_cfg.MAX_NEWS_AGE_HOURS,  # FIX-03
            )
            if signals:
                # #108: exclude FinBERT-fallback signals from BUY ranking — the
                # reversal SELL path already excludes them (low reliability); the
                # BUY side must match, or S4 buys on the weak local model.
                signals, _fb_dropped = _filter_fallback_signals(signals)
                if _fb_dropped:
                    log.info(
                        "S4: dropped %d fallback signal(s) from BUY ranking (#108): %s",
                        len(_fb_dropped), sorted(s.symbol for s in _fb_dropped),
                    )
            if signals:
                # P1-S4-FRESHNESS: drop signals older than max_signal_age_hours.
                _now_utc = datetime.now(timezone.utc)
                fresh_signals, stale_signals = _filter_stale_signals(
                    signals, s4_config.max_signal_age_hours, _now_utc
                )
                if stale_signals:
                    log.warning(
                        "S4: dropped %d/%d stale signals (age > %dh)",
                        len(stale_signals), len(signals), s4_config.max_signal_age_hours,
                    )
                    for _stale in stale_signals:
                        try:
                            _age_h = round(
                                (_now_utc - _stale.generated_at).total_seconds() / 3600, 2
                            )
                            store.write_audit_log(
                                action="SIGNAL_STALE_SKIP",
                                table_name="sentiment_signals",
                                details={
                                    "symbol": _stale.symbol,
                                    "age_hours": _age_h,
                                    "max_age_hours": s4_config.max_signal_age_hours,
                                    "generated_at": _stale.generated_at.isoformat(),
                                },
                            )
                        except Exception as _ae:
                            log.warning("P1-S4: stale audit write failed: %s", _ae)
                # FIX-D: re-admit stale positive signals for open positions with no
                # counter-signal. Query open trades from DB; fail-open (empty set) on error
                # so stale discard behavior is unchanged when DB is unavailable.
                if stale_signals:
                    try:
                        _open_syms_fd = {
                            t["symbol"]
                            for t in store.fetch_trades(status="open", limit=1000)
                        }
                    except Exception as _fd_exc:
                        log.warning("FIX-D: open-trade query failed (%s) — no stale preservation", _fd_exc)
                        _open_syms_fd = set()
                    fresh_signals = _preserve_stale_signals_for_open_positions(
                        fresh_signals, stale_signals, _open_syms_fd
                    )
                    # Surface notable signals lost to staleness in the Decision Log.
                    _dropped_stale = [s for s in stale_signals if s not in fresh_signals]
                    if _dropped_stale:
                        _record_stale_drops(
                            _dropped_stale, s4_config.max_signal_age_hours, s4_config.min_score
                        )
                    _preserved = [s for s in fresh_signals if s in stale_signals]
                    if _preserved:
                        log.info(
                            "FIX-D: preserved %d stale signal(s) for open positions "
                            "with no counter-signal: %s",
                            len(_preserved),
                            sorted(s.symbol for s in _preserved),
                        )
                signals = fresh_signals
                if signals:
                    import pandas as pd
                    signals_df = pd.DataFrame([{
                        "symbol": s.symbol,
                        "score": s.score,
                        "confidence": s.confidence,
                        "reasoning": s.reasoning,
                        "model_id": s.model_id,
                        "ensemble_std": s.ensemble_std,
                        "fallback_used": s.fallback_used,
                        "generated_at": s.generated_at,
                    } for s in signals])
                    log.info("S4: loaded %d fresh signals (last %dh, max_age=%dh)",
                             len(signals), s4_config.signals_lookback_hours,
                             s4_config.max_signal_age_hours)
                else:
                    log.warning(
                        "S4: all %d signals were stale (max_age=%dh) — no orders this cycle",
                        len(stale_signals), s4_config.max_signal_age_hours,
                    )
            else:
                log.warning(
                    "S4: no signals in DB for last %d hours — strategy will produce no orders",
                    s4_config.signals_lookback_hours,
                )
        except Exception as exc:
            log.warning("S4: failed to load signals from DB: %s — strategy will produce no orders", exc)
        finally:
            if store is not None:
                store.close()
        # Apply signal velocity multiplier to S4 scores before strategy sees them.
        if signals_df is not None and not signals_df.empty:
            # T-01: read the active feedback threshold FIRST, outside the velocity
            # try/except. A velocity-computation or Redis failure must degrade to
            # "raw scores, gate still enforced" — never to an ungated stream.
            from src.config import config as _cfg_fb
            _fb_threshold = _get_feedback_threshold(_cfg_fb.REDIS_URL, strategy="S4")

            # Apply velocity multipliers (best-effort; failures fall back to raw scores).
            try:
                from redis import Redis as _RedisSV
                from src.config import config as _cfg_sv
                _r_sv = _RedisSV.from_url(_cfg_sv.REDIS_URL, decode_responses=True)
                try:
                    multipliers = {
                        sym: _compute_signal_velocity(
                            sym, _r_sv,
                            threshold=_cfg_sv.SIGNAL_VELOCITY_THRESHOLD,
                            boost=_cfg_sv.SIGNAL_VELOCITY_BOOST,
                        )
                        for sym in signals_df["symbol"].unique()
                    }
                finally:
                    _r_sv.close()
                signals_df = signals_df.copy()
                signals_df["score"] = signals_df.apply(
                    lambda row: row["score"] * multipliers.get(row["symbol"], 1.0),
                    axis=1,
                )
                n_boosted = sum(1 for m in multipliers.values() if m != 1.0)
                if n_boosted:
                    log.info("Signal velocity: %d/%d symbols adjusted", n_boosted, len(multipliers))
            except Exception as exc:
                log.warning("Signal velocity application failed: %s — using raw scores", exc)

            # Drop signals below the active feedback threshold (absolute value check
            # so bearish signals are also gated, consistent with BUY-only logic).
            if _fb_threshold is not None and _fb_threshold > s4_config.min_score:
                before = len(signals_df)
                dropped_df = signals_df[signals_df["score"].abs() < _fb_threshold]
                signals_df = signals_df[signals_df["score"].abs() >= _fb_threshold]
                if len(dropped_df):
                    log.info(
                        "S4 feedback gate: dropped %d/%d signals below threshold %.3f",
                        len(dropped_df), before, _fb_threshold,
                    )
                    # Surface the drops in the Decision Log (decision=SKIP_THRESHOLD)
                    # so a no-trade cycle shows WHY, not just an empty log.
                    _record_gate_drops(dropped_df, _fb_threshold)
        # Each Celery task creates a fresh instance with _last_rebalance=None.
        # We intentionally do NOT restore last_rebalance from Redis: the daily gate
        # conflicts with intraday 15-min cycling — if S4 runs on a zero-signal
        # cycle it blocks all subsequent same-day runs, causing BUY→SELL churn.
        # Delta-ordering in the orchestrator is idempotent: if we already hold the
        # target quantity, delta≈0 and no order is generated.
        return NewsDrivenTactical(config=s4_config, signals=signals_df)

    log.warning("Unknown strategy_id '%s' — skipping", sid)
    return None


def _submit_portfolio_orders(
    orders,
    trading_client,
    market,
    _submit_fn=None,
    fractionable_symbols: set[str] | None = None,
    open_trade_symbols: set[str] | frozenset[str] | None = frozenset(),
    regime_mult: float = 1.0,
    _on_broker_reject=None,
    risk_cfg: dict | None = None,
    bars_df=None,
    stop_policy: "StopPolicy" | None = None,
    nav: float | None = None,
    open_trades: list[dict] | None = None,
    sym_strats: dict | None = None,
) -> list[dict]:
    """Submit BUY and SELL orders to Alpaca.

    Args:
        orders: List of CombinedOrder to submit.
        trading_client: Alpaca TradingClient instance.
        market: MarketSnapshot with current prices.
        _submit_fn: Optional override for testing (receives order, qty_or_notional, trading_client).
            For BUY: receives (order, notional, trading_client).
            For SELL: receives (order, qty, trading_client).
        fractionable_symbols: Set of symbols that support notional/fractional orders.
            BUY orders for non-fractionable symbols fall back to whole-share qty.
            If None, all symbols are treated as fractionable.
        open_trade_symbols: Symbols that already have an open trade in the DB (P0-05).
            ``frozenset()`` (default) — guard available, no open trades; all BUYs allowed.
            ``{sym, …}``              — guard available; BUYs for listed symbols are blocked.
            ``None``                  — guard DB unavailable; ALL BUYs blocked (fail-closed).
        regime_mult: Regime multiplier from Redis (P0-09). Scales BUY notional so
            high-volatility regimes (mult=0.2) result in smaller position sizes.
        open_trades: Open DB trade rows; used for aggregate stop-risk budget enforcement.

    Returns:
        List of dicts for successfully submitted orders, each containing:
        symbol, side, order_id, and either notional (BUY) or qty (SELL).
    """
    if stop_policy is None and risk_cfg:
        from src.config import config as _cfg_sp
        from src.portfolio.stop_policy import StopPolicy as _StopPolicy
        stop_policy = _StopPolicy(
            risk_cfg,
            bars_df=bars_df,
            last_good_lookup=_last_good_sigma_lookup(_cfg_sp.REDIS_URL),
        )

    from src.backtest.engine.types import OrderSide

    submitted = []
    _current_open_risk = _open_stop_risk(open_trades)
    _agg_budget = _aggregate_stop_budget(nav, risk_cfg or {}) if nav is not None and nav > 0 else None
    _accepted_risk = 0.0
    for order in orders:
        try:
            if order.side == OrderSide.BUY:
                # P0-05: skip BUY if guard is unavailable (None = fail-closed) or if an open
                # trade already exists for this symbol. SELLs are never blocked.
                if open_trade_symbols is None:
                    log.warning(
                        "P0-05: pyramiding guard unavailable — skipping BUY for %s (fail-closed)",
                        order.symbol,
                    )
                    continue
                if order.symbol in open_trade_symbols:
                    log.warning(
                        "P0-05 pyramiding guard: skipping BUY for %s — open trade exists in DB",
                        order.symbol,
                    )
                    continue
                # Stop-loss cooldown: block re-entry for the rest of the session.
                _sl_cooldown = _get_stop_loss_cooldown_symbols(
                    __import__("src.config", fromlist=["config"]).config.REDIS_URL
                )
                if order.symbol in _sl_cooldown:
                    log.warning(
                        "Stop-loss cooldown: skipping BUY for %s — stopped out today",
                        order.symbol,
                    )
                    continue
                # #68: reversal cooldown — a symbol force-sold on strong bearish
                # sentiment must not be re-bought by ANY strategy while it lives.
                _rev_cooldown = _get_reversal_cooldown_symbols(
                    __import__("src.config", fromlist=["config"]).config.REDIS_URL
                )
                if order.symbol in _rev_cooldown:
                    log.warning(
                        "Reversal cooldown: skipping BUY for %s — force-sold on sentiment reversal",
                        order.symbol,
                    )
                    continue
                # #71: S1 re-entry cooldown — only blocks a BUY that is S1's OWN
                # re-entry (unlike #68, a genuine S4 conviction buy on the same
                # name must not be vetoed by S1's own churn). Flag-gated.
                if (risk_cfg or {}).get("s1_reentry_cooldown_enabled", False):
                    _strats_for_buy = set((sym_strats or {}).get(order.symbol, []))
                    if _strats_for_buy == {"S1"}:
                        _s1_cooldown = _get_s1_reentry_cooldown_symbols(
                            __import__("src.config", fromlist=["config"]).config.REDIS_URL
                        )
                        if order.symbol in _s1_cooldown:
                            log.warning(
                                "S1 re-entry cooldown: skipping BUY for %s — "
                                "recently excluded by S1's own signal",
                                order.symbol,
                            )
                            continue
                price = market.prices.get(order.symbol)
                if price is None or price <= 0:
                    log.warning("No market price for %s — skipping BUY order", order.symbol)
                    continue

                # Phase 4: stop-risk sizing — cap notional so per-position loss at the
                # frozen stop is bounded. A wider protective stop → smaller position.
                # Default mode=fixed keeps sizing close to current behavior.
                _strategy_order = getattr(order, "strategy_id", None)
                _frozen_sizing: "FrozenStop | None" = None
                if stop_policy is not None and nav is not None and nav > 0:
                    try:
                        _frozen_sizing = stop_policy.freeze(
                            order.symbol, _strategy_order, float(price), datetime.now(timezone.utc)
                        )
                        _risk_budget_cfg = risk_cfg or {}
                        _default_bp = float(_risk_budget_cfg.get("stop_risk_budget_bp_per_pos", 12))
                        _per_strat_cfg = (_risk_budget_cfg.get("stop_strategy_params", {}) or {}).get(
                            _strategy_order or "default", {}
                        )
                        _budget_bp = float(_per_strat_cfg.get("risk_budget_bp", _default_bp))
                        _gap_buffer = float(_risk_budget_cfg.get("stop_gap_buffer_pct", 0.005))
                        _B = _budget_bp / 10000.0
                        _max_notional = nav * _B / (_frozen_sizing.d_init + _gap_buffer)
                        _max_qty = _max_notional / (price * regime_mult)
                        if abs(order.quantity) > _max_qty:
                            order = order.with_quantity(min(abs(order.quantity), max(0.0, _max_qty)))
                            log.info(
                                "Stop-risk sizing: %s qty capped %.4f -> %.4f (d_init %.2f%%, budget %.1fbp)",
                                order.symbol, order.quantity, _max_qty,
                                _frozen_sizing.d_init * 100, _budget_bp,
                            )
                    except Exception as _sizing_exc:
                        log.warning("Stop-risk sizing failed for %s: %s — using target qty", order.symbol, _sizing_exc)

                # Phase 4b: aggregate sleeve stop-risk budget (default 100 bp of NAV).
                # Enforced after per-position cap so we never exceed the sleeve budget
                # just by opening many positions with tight stops.
                if _agg_budget is not None and _agg_budget > 0:
                    _d_agg = (_frozen_sizing.d_init if _frozen_sizing is not None else 0.02)
                    _intended_notional = price * order.quantity * regime_mult
                    _intended_risk = _d_agg * _intended_notional
                    _remaining = _agg_budget - _current_open_risk - _accepted_risk
                    if _intended_risk > _remaining and _d_agg > 0:
                        _max_notional_agg = _remaining / _d_agg
                        _max_qty_agg = _max_notional_agg / (price * regime_mult)
                        if _max_qty_agg <= 0:
                            log.warning(
                                "Aggregate stop-risk budget exhausted: skipping BUY for %s "
                                "(open=%.2f, accepted=%.2f, budget=%.2f)",
                                order.symbol, _current_open_risk, _accepted_risk, _agg_budget,
                            )
                            continue
                        if abs(order.quantity) > _max_qty_agg:
                            order = order.with_quantity(min(abs(order.quantity), max(0.0, _max_qty_agg)))
                            log.info(
                                "Aggregate stop-risk sizing: %s qty capped %.4f -> %.4f "
                                "(d_init %.2f%%, remaining budget $%.2f)",
                                order.symbol, order.quantity, _max_qty_agg,
                                _d_agg * 100, _remaining,
                            )

                notional = round(price * order.quantity * regime_mult, 2)
                if notional < _MIN_ORDER_NOTIONAL:
                    log.info(
                        "Min notional skip: %s BUY $%.2f < $%.0f threshold",
                        order.symbol, notional, _MIN_ORDER_NOTIONAL,
                    )
                    continue
                _accepted_risk += (_frozen_sizing.d_init if _frozen_sizing is not None else 0.02) * notional
                # P1-B: Non-fractionable symbols require whole-share qty instead of notional.
                is_fractionable = (fractionable_symbols is None or order.symbol in fractionable_symbols)
                if _submit_fn is not None:
                    _submit_fn(order, notional, trading_client)
                    alpaca_id = f"test-{order.symbol}-buy"
                else:
                    from alpaca.trading.requests import MarketOrderRequest, StopLossRequest, TakeProfitRequest
                    from alpaca.trading.enums import OrderClass
                    from src.config import config as _cfg_order

                    if is_fractionable:
                        base_kwargs: dict = dict(
                            symbol=order.symbol,
                            notional=notional,
                            side="buy",
                            time_in_force="day",
                        )
                    else:
                        # F5: derive whole-share qty from the SCALED notional so regime_mult
                        # (P0-09) applies to non-fractionable BUYs too. Using raw
                        # int(order.quantity) here silently bypassed regime_mult on
                        # whole-share names (mega-caps), leaking full-size deployment in
                        # risk-off regimes. Zero behavior change when regime_mult == 1.0.
                        whole_qty = max(1, int(notional / price))
                        log.info(
                            "P1-B: %s not fractionable — using qty=%d (regime_mult=%.2f, notional=$%.2f)",
                            order.symbol, whole_qty, regime_mult, notional,
                        )
                        base_kwargs = dict(
                            symbol=order.symbol,
                            qty=whole_qty,
                            side="buy",
                            time_in_force="day",
                        )

                    # P2-A: Bracket order — attach take-profit and broker disaster-stop legs.
                    # Requires whole-share qty: Alpaca rejects bracket on notional/fractional orders (error 42210000).
                    if _cfg_order.ALPACA_BRACKET_ENABLED and price and price > 0 and not is_fractionable:
                        tp_price = round(price * (1 + _cfg_order.ALPACA_TAKE_PROFIT_PCT), 2)
                        # Broker disaster stop: wider than the synthetic protective stop.
                        _sl_d_hard = _cfg_order.ALPACA_STOP_LOSS_PCT
                        if stop_policy is not None:
                            try:
                                _sl_frozen = stop_policy.freeze(
                                    order.symbol, None, float(price), datetime.now(timezone.utc)
                                )
                                _sl_sigma = stop_policy._sigma_eff(order.symbol)[0]
                                _sl_d_hard = stop_policy.d_hard(order.symbol, _sl_frozen, _sl_sigma)
                            except Exception as _dhard_exc:
                                log.warning("d_hard compute failed for %s: %s", order.symbol, _dhard_exc)
                                _sl_d_hard = _cfg_order.ALPACA_STOP_LOSS_PCT
                        sl_price = round(price * (1 - _sl_d_hard), 2)
                        base_kwargs["order_class"] = OrderClass.BRACKET
                        base_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_price)
                        base_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_price)
                        log.debug("P2-A bracket %s: tp=%.2f sl=%.2f (d_hard=%.3f, entry≈%.2f)", order.symbol, tp_price, sl_price, _sl_d_hard, price)

                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = trading_client.submit_order(req)
                    alpaca_id = str(alpaca_order.id)
                submitted.append({"symbol": order.symbol, "side": "buy", "order_id": alpaca_id, "notional": notional})
            elif order.side == OrderSide.SELL:
                qty = abs(order.quantity)
                if qty < 1e-6:
                    continue
                # #62 regression: a live GTC protective stop reserves the whole-share
                # qty, so a full-qty SELL is rejected with 40310000. Free it first.
                try:
                    from src.portfolio.fractional_stop_orders import cancel_open_stop_sells
                    _n_freed = cancel_open_stop_sells(trading_client, order.symbol)
                    if _n_freed:
                        log.info(
                            "Cancelled %d protective stop(s) for %s before SELL",
                            _n_freed, order.symbol,
                        )
                except Exception as _cps_exc:
                    log.warning(
                        "Protective-stop cancel before SELL failed for %s: %s — selling anyway",
                        order.symbol, _cps_exc,
                    )
                if _submit_fn is not None:
                    _submit_fn(order, qty, trading_client)
                    alpaca_id = f"test-{order.symbol}-sell"
                else:
                    from alpaca.trading.requests import MarketOrderRequest
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        qty=qty,
                        side="sell",
                        time_in_force="day",
                    )
                    alpaca_order = trading_client.submit_order(req)
                    alpaca_id = str(alpaca_order.id)
                # allocation_weight propagates the target-weight intent so the
                # trade-exit writer can tell a full-close SELL (weight == 0.0 =>
                # final tranche) from a partial trim (weight > 0 => intermediate).
                submitted.append({
                    "symbol": order.symbol, "side": "sell", "order_id": alpaca_id,
                    "qty": qty, "allocation_weight": order.allocation_weight,
                })
            else:
                log.warning("Unknown order side %s for %s — skipping", order.side, order.symbol)
                continue
        except Exception as exc:
            log.warning("Failed to submit order for %s: %s", order.symbol, exc)
            # P2-05-D: notify caller of broker reject so an audit row can be written.
            if _on_broker_reject is not None:
                try:
                    _on_broker_reject(order.symbol, order.side.value, exc)
                except Exception as _cb_exc:
                    log.debug("_on_broker_reject callback raised: %s", _cb_exc)
    return submitted


def _submit_reversal_force_sells(
    reversal_sell_symbols: dict,
    final_orders,
    stop_loss_sells: dict,
    alpaca_positions: list,
    trading_client,
    submitted_orders: list,
    ts,
    regime_mult: float,
    operating_mode: str,
    redis_client=None,
) -> None:
    """Force-sell positions flagged by the sentiment-reversal check.

    Extracted from run_portfolio_cycle after the 2026-07-16 live failure: with a
    GTC protective stop open (#62), the full-qty market SELL was rejected by
    Alpaca (40310000, whole-share qty held_for_orders) and the reversal exit
    silently never happened. The symbol's protective stops are cancelled first.

    Symbols already being sold by the rebalance (final_orders) or claimed by the
    stop-loss path are skipped. Appends submitted orders to ``submitted_orders``
    in place and writes a SELL row to execution_decisions per order.
    """
    if not reversal_sell_symbols or operating_mode in ("dry_run", "halted"):
        return
    # OrderSide values are uppercase ("SELL") — compare case-insensitively so a
    # rebalance SELL already queued for the symbol really is detected.
    already_selling = {
        o.symbol for o in final_orders if o.side.value.lower() == "sell"
    }
    to_force_sell = set(reversal_sell_symbols) - already_selling - set(stop_loss_sells.keys())
    for sym in to_force_sell:
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            from src.portfolio.fractional_stop_orders import cancel_open_stop_sells

            qty_held = next(
                (float(p.qty) for p in alpaca_positions if p.symbol == sym), None
            )
            if qty_held and qty_held > 0:
                _n_freed = cancel_open_stop_sells(trading_client, sym)
                if _n_freed:
                    log.info(
                        "Cancelled %d protective stop(s) for %s before reversal force-sell",
                        _n_freed, sym,
                    )
                req = MarketOrderRequest(
                    symbol=sym,
                    qty=qty_held,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
                resp = trading_client.submit_order(req)
                _rev_order_id = str(resp.id)
                submitted_orders.append({
                    "symbol": sym,
                    "side": "sell",
                    "order_id": _rev_order_id,
                    "notional": 0.0,
                    "reason": "sentiment_reversal",
                })
                log.info("Forced sell submitted for %s (sentiment reversal)", sym)
                # #67 consume-on-fire + #68 re-entry cooldown. Best-effort: a Redis
                # failure must never undo an already-submitted SELL.
                try:
                    from src.config import config as _cfg_rev
                    _r_mark = redis_client
                    _own_mark = False
                    if _r_mark is None:
                        from redis import Redis as _RedisMark
                        _r_mark = _RedisMark.from_url(_cfg_rev.REDIS_URL, decode_responses=True)
                        _own_mark = True
                    try:
                        _identity = reversal_sell_symbols[sym].get("identity")
                        if _identity:
                            _r_mark.setex(
                                f"signal:{sym}:reversal_consumed",
                                _cfg_rev.REDIS_SIGNAL_TTL_SECONDS,
                                str(_identity),
                            )
                        _cd_hours = float(_cfg_rev.SENTIMENT_REVERSAL_REENTRY_COOLDOWN_HOURS)
                        if _cd_hours > 0:
                            _r_mark.setex(
                                f"reversal_cooldown:{sym}",
                                int(_cd_hours * 3600),
                                1,
                            )
                    finally:
                        if _own_mark:
                            _r_mark.close()
                except Exception as _mark_exc:
                    log.warning("Could not mark reversal consume/cooldown for %s: %s", sym, _mark_exc)
                # Write SELL to execution_decisions so Decision Log shows the exit.
                try:
                    from src.config import config
                    from src.store.pg_store import PostgreSQLStore as _PGS
                    _pg_rev = _PGS()
                    _rev_sig = reversal_sell_symbols[sym]
                    _threshold = config.SENTIMENT_REVERSAL_EXIT_THRESHOLD
                    _pg_rev.write_execution_decision(
                        tick_time=ts,
                        symbol=sym,
                        signal_id=_rev_sig.get("signal_id"),
                        score=0.0,
                        signal_score=_rev_sig["score"],
                        regime_mult=regime_mult,
                        ema_pass=True,
                        decision="SELL",
                        order_id=_rev_order_id,
                        reason=f"sentiment_reversal: score {_rev_sig['score']:.3f} < threshold {_threshold:.2f}",
                    )
                    _pg_rev.close()
                except Exception as _dec_exc:
                    log.warning("Could not write sentiment_reversal decision for %s: %s", sym, _dec_exc)
        except Exception as _fs_exc:
            log.warning("Failed to submit forced sell for %s: %s", sym, _fs_exc)


def _sentiment_reversal_sells(
    alpaca_positions: list,
    redis_client,
    threshold: float,
    max_age_minutes: int = 60,
) -> dict:
    """Return symbols held long whose current sentiment score has gone negative.

    Reads signal:{symbol}:sentiment from Redis for each open position.
    Returns {symbol: {score, signal_id, identity}} for symbols that should be
    force-sold. Fail-open: symbols with no signal or unparseable value are NOT sold.

    #67 freshness discipline (2026-07-16: SOXX signal 3861 reused unchanged for
    5 SELLs over 97 min, churn loop with S1 re-buys):
    - age-gate: a signal older than max_age_minutes never triggers a reversal —
      much stricter than the BUY path's 4h, a forced exit must rest on a CURRENT
      read. Unknown age (missing/unparseable generated_at) counts as stale.
    - consume-on-fire: signal:{symbol}:reversal_consumed holds the identity of
      the last signal that already triggered a force-sell; the same signal never
      fires twice. The marker is written by _submit_reversal_force_sells.
    """
    import json as _json
    from datetime import datetime as _dt, timezone as _tz

    reversal: dict = {}
    for pos in alpaca_positions:
        try:
            raw = redis_client.get(f"signal:{pos.symbol}:sentiment")
            if raw is None:
                continue
            data = _json.loads(raw)
            # Do NOT force-sell on a FinBERT fallback signal: it fires when the ensemble
            # diverges (low reliability). A reversal exit must rest on a trustworthy
            # ensemble read (SPCX -0.573 fallback → -20.23 loss on 2026-07-01).
            if data.get("fallback_used"):
                continue
            score = float(data.get("score", 0.0))
            if score >= threshold:
                continue
            gen_raw = data.get("generated_at")
            try:
                gen_at = _dt.fromisoformat(str(gen_raw).replace("Z", "+00:00"))
                if gen_at.tzinfo is None:
                    gen_at = gen_at.replace(tzinfo=_tz.utc)
                age_min = (_dt.now(_tz.utc) - gen_at).total_seconds() / 60.0
            except (TypeError, ValueError):
                age_min = None
            if age_min is None or age_min > max_age_minutes:
                log.info(
                    "Sentiment reversal SKIPPED for %s: signal age %s > %d min gate",
                    pos.symbol,
                    f"{age_min:.0f}min" if age_min is not None else "unknown",
                    max_age_minutes,
                )
                continue
            identity = str(data.get("signal_id") or gen_raw)
            consumed = redis_client.get(f"signal:{pos.symbol}:reversal_consumed")
            if consumed is not None and (
                consumed.decode() if isinstance(consumed, bytes) else str(consumed)
            ) == identity:
                log.info(
                    "Sentiment reversal SKIPPED for %s: signal %s already consumed",
                    pos.symbol, identity,
                )
                continue
            reversal[pos.symbol] = {
                "score": score,
                "signal_id": data.get("signal_id"),
                "identity": identity,
            }
            log.info(
                "Sentiment reversal: %s score=%.3f < threshold=%.2f — forced exit",
                pos.symbol, score, threshold,
            )
        except Exception as exc:
            log.debug("Could not read sentiment for %s: %s", pos.symbol, exc)
    return reversal


def _compute_signal_velocity(
    symbol: str,
    redis_client,
    threshold: float,
    boost: float = 0.20,
) -> float:
    """Return a score multiplier based on how fast sentiment is changing.

    Reads last 3 entries from signal:{symbol}:history (newest first).
    velocity = scores[0] - scores[-1]
    - velocity >  threshold → 1 + boost (accelerating upward)
    - velocity < -threshold → 1 - boost (accelerating downward)
    - |velocity| <= threshold → 1.0 (stable, no adjustment)

    Returns 1.0 if fewer than 2 history points exist.
    """
    import json as _json

    try:
        raw_list = redis_client.lrange(f"signal:{symbol}:history", 0, 2)
        if len(raw_list) < 2:
            return 1.0
        scores = [float(_json.loads(r)["score"]) for r in raw_list]
        velocity = scores[0] - scores[-1]
        if velocity > threshold:
            return 1.0 + boost
        if velocity < -threshold:
            return 1.0 - boost
        return 1.0
    except Exception as exc:
        log.debug("Signal velocity error for %s: %s", symbol, exc)
        return 1.0


def _persist_cycle_result(cycle_data: dict, conn=None) -> None:
    """Persist cycle stats to portfolio_cycles. DB errors are swallowed."""
    import psycopg2

    _local_conn = None
    should_close = False
    try:
        if conn is None:
            from src.config import config
            _local_conn = psycopg2.connect(config.DATABASE_URL.replace("+asyncpg", ""))
            conn = _local_conn
            should_close = True

        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO portfolio_cycles
                   (timestamp, strategies_run, orders_count, constraints_fired, final_orders)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    cycle_data["timestamp"],
                    _json.dumps(cycle_data["strategies_run"]),
                    cycle_data["orders_count"],
                    _json.dumps(cycle_data.get("constraints_fired", [])),
                    _json.dumps(cycle_data.get("final_orders", [])),
                ),
            )
        conn.commit()
    except Exception as exc:
        log.warning("Failed to persist cycle result: %s", exc)
    finally:
        if should_close and _local_conn is not None:
            _local_conn.close()