#!/usr/bin/env python3
"""#134: is the F8 recovery path reachable, or is the floor an absorbing state?

Read-only. #32 left one sleeve (S1) sitting on `regime_min_scale` with zero
observed trigger->recovery cycles while the other (S4) completed one. That could
mean two very different things — the ratchet is correctly de-risking a losing
sleeve, or the sleeve cannot mechanically climb back out — and the two call for
opposite responses. This script measures the second question, which is the one
the data can settle on its own.

The mechanism (src/portfolio/loss_feedback.py + workers/performance.py) has three
branches, and only one of them does not require winning trades:

  trigger  : triggered AND >=cooldown_hours since last adjustment
             -> scale *= factor (floored)          [and RESETS the decay clock]
  recovery : NOT triggered AND consecutive_wins >= recovery_win_streak
             -> scale /= factor (capped at 1.0)
  decay    : NOT triggered AND >=threshold_decay_hours since last adjustment
             -> scale /= factor (capped at 1.0)

Because a trigger resets the same `last_adjustment` clock the decay reads, a
sleeve that re-triggers more often than `threshold_decay_hours` can never decay:
the only way out is a win streak, which is precisely what a losing sleeve does
not have. That is the trap this script quantifies — `decay_starved` counts the
down-steps that reset a decay clock which had not yet elapsed.

Run inside the worker container:
    docker compose exec worker python scripts/ratchet_reachability.py
"""
from __future__ import annotations

import os
import statistics
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


def simulate_ratchet(observations: list[dict], cfg: dict) -> dict:
    """Replay the ratchet over per-tick outcomes and score escapability.

    `observations` are dicts with `tick`, `triggered` and `consecutive_wins` —
    i.e. what LossFeedback.evaluate() returned at each cadence tick, for one
    strategy. Returns counters describing whether the sleeve could get back to
    1.0, not just whether it did.
    """
    factor = cfg["regime_scale_factor"]
    floor = cfg["regime_min_scale"]
    cooldown = timedelta(hours=cfg["cooldown_hours"])
    decay = timedelta(hours=cfg.get("threshold_decay_hours", 24))
    win_streak = cfg["recovery_win_streak"]

    scale = 1.0
    last: datetime | None = None
    stats = {
        "ticks": len(observations),
        "ticks_triggered": 0,
        "down_steps": 0,
        "recovery_steps": 0,
        "decay_steps": 0,
        "decay_starved": 0,
        "episodes": 0,
        "escapes": 0,
        "ticks_at_floor": 0,
        "longest_floor_run_ticks": 0,
        "trigger_gaps_hours": [],
        "episode_lengths_hours": [],
    }
    floor_run = 0
    episode_start: datetime | None = None
    prev_down: datetime | None = None

    for o in observations:
        tick, triggered = o["tick"], o["triggered"]
        stats["ticks_triggered"] += int(triggered)
        cooldown_ok = last is None or (tick - last) >= cooldown

        if triggered and cooldown_ok:
            # A down-step while already suppressed, inside the decay window,
            # resets a clock that had not yet elapsed: the escape hatch closes.
            if scale < 1.0 and last is not None and (tick - last) < decay:
                stats["decay_starved"] += 1
            if scale >= 1.0:
                stats["episodes"] += 1
                episode_start = tick
            scale = max(scale * factor, floor)
            last = tick
            stats["down_steps"] += 1
            if prev_down is not None:
                stats["trigger_gaps_hours"].append(
                    (tick - prev_down).total_seconds() / 3600.0
                )
            prev_down = tick
        elif not triggered and o["consecutive_wins"] >= win_streak:
            if scale < 1.0:
                scale = min(scale / factor, 1.0)
                last = tick
                stats["recovery_steps"] += 1
        elif not triggered and scale < 1.0:
            if last is not None and (tick - last) >= decay:
                scale = min(scale / factor, 1.0)
                last = tick
                stats["decay_steps"] += 1

        if scale >= 1.0 and episode_start is not None:
            stats["escapes"] += 1
            stats["episode_lengths_hours"].append(
                (tick - episode_start).total_seconds() / 3600.0
            )
            episode_start = None

        if scale <= floor + 1e-9:
            floor_run += 1
            stats["ticks_at_floor"] += 1
            stats["longest_floor_run_ticks"] = max(
                stats["longest_floor_run_ticks"], floor_run
            )
        else:
            floor_run = 0

    stats["final_scale"] = round(scale, 4)
    return stats


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


def _ticks(start: datetime, end: datetime):
    """30-min ticks, Mon-Fri 14:00-21:00 UTC — the live cron cadence."""
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:
            for h in range(14, 22):
                for m in (0, 30):
                    if h == 21 and m == 30:
                        continue
                    t = datetime.combine(day, time(h, m), tzinfo=timezone.utc)
                    if start <= t <= end:
                        yield t
        day += timedelta(days=1)


def collect_observations(trades: list[dict], cfg: dict, end: datetime) -> dict:
    """Per-strategy per-tick evaluate() outcomes over the real trade history."""
    teaching = [t for t in trades if _is_teaching_trade(t.get("exit_reason"))]
    if not teaching:
        return {s: [] for s in STRATEGIES}
    out: dict[str, list[dict]] = {s: [] for s in STRATEGIES}

    for tick in _ticks(teaching[0]["exit_time"], end):
        # Match live fetch semantics: last 50 CLOSED trades, then keep teaching.
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
            o = fb.evaluate(s)
            out[s].append({
                "tick": tick,
                "triggered": o.triggered,
                "consecutive_wins": o.consecutive_wins,
                "ewma_r": o.ewma_r,
            })
    return out


def _pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def main() -> int:
    cfg = _load_loss_feedback_config()
    conn = _conn()
    try:
        trades = _fetch_trades(conn)
    finally:
        conn.close()

    obs = collect_observations(trades, cfg, datetime.now(timezone.utc))

    print("=" * 78)
    print("F8 ratchet — RECOVERY REACHABILITY (issue #134)")
    print(f"factor={cfg['regime_scale_factor']}  floor={cfg['regime_min_scale']}"
          f"  cooldown={cfg['cooldown_hours']}h  decay={cfg['threshold_decay_hours']}h"
          f"  win_streak={cfg['recovery_win_streak']}")
    print("=" * 78)

    for s in STRATEGIES:
        st = simulate_ratchet(obs[s], cfg)
        gaps = st["trigger_gaps_hours"]
        med_gap = statistics.median(gaps) if gaps else None
        print(f"\n--- {s} ---")
        print(f"  ticks evaluated            {st['ticks']}")
        print(f"  ticks with triggered=True  {st['ticks_triggered']}"
              f"  ({_pct(st['ticks_triggered'], st['ticks'])})")
        print(f"  down-steps                 {st['down_steps']}")
        print(f"  recovery steps (win streak){st['recovery_steps']:>4}")
        print(f"  decay steps (quiet 24h)    {st['decay_steps']:>4}")
        print(f"  decay clocks starved       {st['decay_starved']:>4}"
              f"   <- down-steps that reset a live decay window")
        print(f"  episodes below 1.0         {st['episodes']}"
              f"   escapes back to 1.0: {st['escapes']}")
        if st["episode_lengths_hours"]:
            print(f"  median escape time         "
                  f"{statistics.median(st['episode_lengths_hours']):.1f}h")
        print(f"  ticks at floor             {st['ticks_at_floor']}"
              f"  ({_pct(st['ticks_at_floor'], st['ticks'])})"
              f"   longest run: {st['longest_floor_run_ticks']} ticks")
        if med_gap is not None:
            verdict = ("STARVED — re-triggers faster than the decay window"
                       if med_gap < cfg["threshold_decay_hours"] else "decay reachable")
            print(f"  median gap between down-steps {med_gap:.1f}h"
                  f"  vs decay window {cfg['threshold_decay_hours']}h  -> {verdict}")
        print(f"  final scale                {st['final_scale']}")

    print("\nReading: `decay` is the only branch that does not need winning trades."
          "\nA sleeve whose median gap between down-steps is shorter than the decay"
          "\nwindow can only leave the floor via a win streak — so the ratchet is an"
          "\nabsorbing state exactly when the sleeve is losing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
