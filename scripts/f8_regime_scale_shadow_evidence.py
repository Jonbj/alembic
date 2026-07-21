#!/usr/bin/env python3
"""F8 regime_scale — shadow evidence report (flip-decision support, issue #32).

Read-only. `loss_feedback.apply_regime_scale` ships OFF (shadow): the per-
strategy regime scale (`feedback:regime_scale:S*`) is computed by the loss-
feedback ratchet and logged, but NOT applied to sizing. Unlike #61/#71, the
F8 shadow was NEVER persisted (no annotation in execution_decisions, only a
transient log line + a 48h-TTL Redis key), so there is no recorded trajectory
to read back. This script RECONSTRUCTS the trajectory by faithfully replaying
the real state machine over the persisted `trades`, then VALIDATES the replay
against the current live Redis scale — if the reconstruction lands on the live
values, the trajectory is trustworthy.

State machine replayed (src/workers/performance.run_loss_feedback_check, every
30 min Mon-Fri 14:00-21:00 UTC):
  - trigger (EWMA R <= -0.50 OR >= 3 consecutive teaching losses) AND 4h
    cooldown since last adjustment -> scale *= 0.80 (floor 0.20)
  - recovery (>= 3 consecutive wins) -> scale /= 0.80 (cap 1.0)
  - decay (24h since last adjustment, scale still < 1.0) -> scale /= 0.80
  - 48h TTL: with the cron running only Mon-Fri, a weekend gap (~65h) exceeds
    the TTL, so the key EXPIRES and the scale resets to 1.0 every Monday.

Uses the real LossFeedback / config / helpers so the ratchet matches live.

Run inside the worker container:
    docker compose exec worker python scripts/f8_regime_scale_shadow_evidence.py
Or locally with the live DB + Redis:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
    REDIS_URL=redis://localhost:6379/0 \
        .venv/bin/python scripts/f8_regime_scale_shadow_evidence.py
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta, timezone

import psycopg2
import psycopg2.extras

from src.portfolio.loss_feedback import (
    LossFeedback,
    _is_teaching_trade,
    risk_budget_at_entry,
    strategy_for_trade,
)
from src.workers.performance import _load_loss_feedback_config

STRATEGIES = ("S1", "S4")


def _conn():
    url = os.environ.get(
        "DATABASE_URL", "postgresql://trading:trading@postgres:5432/trading"
    )
    return psycopg2.connect(url)


def _fetch_trades(conn) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT symbol, signal_id, stop_strategy, entry_notional, stop_d_init,
                   net_pnl, exit_reason, exit_time
            FROM trades
            WHERE exit_time IS NOT NULL AND net_pnl IS NOT NULL
            ORDER BY exit_time
            """
        )
        return [dict(r) for r in cur.fetchall()]


def _fetch_daily_nav(conn) -> dict[str, float]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON ((timestamp AT TIME ZONE 'UTC')::date)
                   (timestamp AT TIME ZONE 'UTC')::date, nav
            FROM risk_reports WHERE nav IS NOT NULL
            ORDER BY (timestamp AT TIME ZONE 'UTC')::date, timestamp DESC
            """
        )
        return {str(d): float(n) for d, n in cur.fetchall()}


def _live_scales() -> dict[str, float | None]:
    try:
        import redis as _redis

        r = _redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
        )
        out = {}
        for s in STRATEGIES:
            v = r.get(f"feedback:regime_scale:{s}")
            out[s] = float(v) if v is not None else None
        r.close()
        return out
    except Exception as exc:  # pragma: no cover - diagnostic tool
        print(f"  (could not read live Redis scales: {exc})")
        return {s: None for s in STRATEGIES}


def _ticks(start: datetime, end: datetime):
    """30-min ticks, Mon-Fri 14:00-21:00 UTC inclusive."""
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:  # Mon-Fri
            for h in range(14, 22):
                for m in (0, 30):
                    if h == 21 and m == 30:
                        continue
                    t = datetime.combine(day, time(h, m), tzinfo=timezone.utc)
                    if start <= t <= end:
                        yield t
        day += timedelta(days=1)


def _replay(trades: list[dict], cfg: dict, end: datetime) -> list[dict]:
    """Faithfully replay the ratchet at 30-min cadence. Returns daily EOD rows."""
    baseline = cfg["threshold_baseline"]
    factor = cfg["regime_scale_factor"]
    min_scale = cfg["regime_min_scale"]
    cooldown = timedelta(hours=cfg["cooldown_hours"])
    decay = timedelta(hours=cfg.get("threshold_decay_hours", 24))
    ttl = timedelta(hours=cfg["feedback_ttl_hours"])
    win_streak = cfg["recovery_win_streak"]

    teaching = [t for t in trades if _is_teaching_trade(t.get("exit_reason"))]
    if not teaching:
        return []
    start = teaching[0]["exit_time"]

    state = {s: {"scale": 1.0, "thr": baseline, "last": None} for s in STRATEGIES}
    daily: dict[str, dict[str, float]] = {}

    for tick in _ticks(start, end):
        # Match live fetch semantics: the last 50 CLOSED trades as of this tick,
        # THEN keep the teaching ones (NOT the last 50 teaching trades).
        closed_upto = [t for t in trades if t["exit_time"] <= tick][-50:]
        upto = [t for t in closed_upto if _is_teaching_trade(t.get("exit_reason"))]
        fb = LossFeedback(dict(cfg))
        for t in upto:
            budget = risk_budget_at_entry(t)
            if budget <= 0:
                continue
            fb.record_exit(
                strategy_for_trade(t), t["exit_reason"], float(t["net_pnl"] or 0.0), budget
            )
        for s in STRATEGIES:
            st = state[s]
            # 48h TTL expiry (weekend gap resets the scale).
            if st["last"] is not None and (tick - st["last"]) > ttl:
                st["scale"], st["thr"], st["last"] = 1.0, baseline, None
            o = fb.evaluate(s)
            cooldown_ok = st["last"] is None or (tick - st["last"]) >= cooldown
            if o.triggered and cooldown_ok:
                st["scale"] = max(st["scale"] * factor, min_scale)
                st["thr"] = min(st["thr"] + cfg["threshold_step"], cfg["threshold_max"])
                st["last"] = tick
            elif (not o.triggered) and o.consecutive_wins >= win_streak:
                if not (st["thr"] <= baseline and st["scale"] >= 1.0):
                    st["scale"] = min(st["scale"] / factor, 1.0)
                    st["thr"] = max(st["thr"] - cfg["threshold_step"], baseline)
                    st["last"] = tick
            elif (not o.triggered) and (st["scale"] < 1.0 or st["thr"] > baseline):
                if st["last"] is not None and (tick - st["last"]) >= decay:
                    st["scale"] = min(st["scale"] / factor, 1.0)
                    st["thr"] = max(st["thr"] - cfg["threshold_step"], baseline)
                    st["last"] = tick
            daily.setdefault(str(tick.date()), {})[s] = round(st["scale"], 4)

    return [{"date": d, **v} for d, v in sorted(daily.items())]


def main() -> int:
    cfg = _load_loss_feedback_config()
    conn = _conn()
    try:
        trades = _fetch_trades(conn)
        nav = _fetch_daily_nav(conn)
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    rows = _replay(trades, cfg, now)
    live = _live_scales()

    print("=" * 72)
    print("F8 regime_scale — SHADOW EVIDENCE (issue #32)")
    print(f"apply_regime_scale = {cfg['apply_regime_scale']}  (False = shadow, not applied)")
    print("=" * 72)
    print("\nInstrumentation gap: the F8 shadow scale is NOT persisted (no")
    print("execution_decisions annotation, only a 48h-TTL Redis key). The")
    print("trajectory below is a RECONSTRUCTION by replaying the real ratchet")
    print("over persisted trades, validated against the live Redis scale.\n")

    print("Live Redis scale now:  " + "  ".join(
        f"{s}={live[s]}" if live[s] is not None else f"{s}=<none>" for s in STRATEGIES
    ))
    if rows:
        last = rows[-1]
        print("Reconstruction ended:  " + "  ".join(f"{s}={last[s]}" for s in STRATEGIES))
        ok = all(
            live[s] is not None and abs(last[s] - live[s]) < 0.05 for s in STRATEGIES
        )
        print(f"Validation: {'PASS — reconstruction matches live' if ok else 'DRIFT — see note'}\n")

    # Daily trajectory with NAV change and would-applying-have-helped signal.
    print(f"{'date':12} {'S1':>6} {'S4':>6} {'ΔNAV':>10}  timing")
    prev_nav = None
    helped = drag = 0.0
    for r in rows:
        d = r["date"]
        n = nav.get(d)
        dnav = (n - prev_nav) if (n is not None and prev_nav is not None) else None
        # Guard against corrupt NAV snapshots (a bad init/test row): an
        # implausible one-day equity jump is a data error, not a real move.
        if dnav is not None and abs(dnav) > 5000:
            dnav = None
        if n is not None:
            prev_nav = n
        # de-risked when either sleeve < 1.0; "helped" if de-risked on a down day.
        derisk = min(r["S1"], r["S4"]) < 1.0
        tag = ""
        if dnav is not None and derisk:
            if dnav < 0:
                tag = "de-risk on DOWN day (would have helped)"
                helped += -dnav
            else:
                tag = "de-risk on UP day (would have dragged)"
                drag += dnav
        dnav_s = f"{dnav:+.2f}" if dnav is not None else "—"
        print(f"{d:12} {r['S1']:6.3f} {r['S4']:6.3f} {dnav_s:>10}  {tag}")

    print("\nDirectional read (NOT a precise counterfactual — applying the scale")
    print("would change which trades fire, a feedback the replay cannot model):")
    print(f"  Σ|ΔNAV| on de-risked DOWN days (de-risk aligned): {helped:8.2f}")
    print(f"  Σ ΔNAV  on de-risked UP   days (de-risk drag):    {drag:8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
