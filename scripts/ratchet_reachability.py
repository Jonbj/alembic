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
    r_multiple,
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


def serial_dependence(r_multiples: list[float]) -> dict:
    """Test the premise the whole ratchet rests on: do losses beget losses?

    An equity-curve de-risking rule (which is what F8 is) can only add value if
    the strategy's trade returns are POSITIVELY serially correlated — if losses
    cluster, cutting size after a loss avoids the next one. With independent
    returns the rule is noise-chasing and pays a drag; with NEGATIVE correlation
    it is actively backwards, cutting size exactly before the bounce. The
    practitioner literature is blunt that most systematic strategies show no
    such dependence, so this is a premise to verify, never to assume.

    Two views of the same question:
      - lag-1 autocorrelation of the R-multiples (magnitude as well as sign),
        compared against the ~1.96/sqrt(n) band for zero dependence;
      - a Wald-Wolfowitz runs test on the win/loss signs (fewer runs than
        expected = streaky, more = alternating), which is robust to the fat
        tails that make the autocorrelation of P&L noisy.
    """
    n = len(r_multiples)
    out = {
        "n": n,
        "win_rate": (sum(1 for r in r_multiples if r > 0) / n) if n else None,
        "lag1_autocorr": None,
        "significance_band": (1.96 / (n ** 0.5)) if n else None,
        "runs": None,
        "runs_expected": None,
        "runs_z": None,
        "verdict": "insufficient data",
    }
    if n < 3:
        return out

    mean = sum(r_multiples) / n
    denom = sum((x - mean) ** 2 for x in r_multiples)
    if denom <= 0:
        return out
    num = sum(
        (r_multiples[i] - mean) * (r_multiples[i + 1] - mean) for i in range(n - 1)
    )
    ac = num / denom
    out["lag1_autocorr"] = round(ac, 4)

    wins = [r > 0 for r in r_multiples]
    n_w, n_l = sum(wins), n - sum(wins)
    if n_w and n_l:
        runs = 1 + sum(1 for i in range(n - 1) if wins[i] != wins[i + 1])
        expected = 2 * n_w * n_l / n + 1
        var = (2 * n_w * n_l * (2 * n_w * n_l - n)) / (n * n * (n - 1))
        out["runs"] = runs
        out["runs_expected"] = round(expected, 2)
        if var > 0:
            out["runs_z"] = round((runs - expected) / (var ** 0.5), 3)

    band = out["significance_band"]
    z = out["runs_z"]
    streaky = ac > band or (z is not None and z < -1.96)
    reverting = ac < -band or (z is not None and z > 1.96)
    out["verdict"] = (
        "streaky" if streaky else "mean-reverting" if reverting
        else "no detectable dependence"
    )
    return out


def daily_aggregate(observations: list[dict]) -> list[float]:
    """Collapse trades to ONE budget-weighted R per exit day.

    The ratchet reads closed trades as a sequence, but a sleeve holds many
    names at once, so most neighbours in that sequence are simultaneous exits
    sharing one market move — read in arbitrary within-day order. Counting them
    as consecutive observations turns a single bad day into an N-loss "streak".
    Aggregating by day is the unit the design language ("consecutive losses")
    actually implies, and the only unit on which serial dependence means
    anything.

    `observations` are dicts with `day`, `net_pnl` and `budget`.
    """
    by_day: dict[object, list[float]] = {}
    for o in observations:
        budget = float(o.get("budget") or 0.0)
        if budget <= 0:
            continue
        acc = by_day.setdefault(o["day"], [0.0, 0.0])
        acc[0] += float(o.get("net_pnl") or 0.0)
        acc[1] += budget
    return [pnl / bud for _, (pnl, bud) in sorted(by_day.items()) if bud > 0]


def same_day_neighbour_share(days: list) -> float | None:
    """Fraction of consecutive pairs in the trade sequence sharing an exit day.

    High share = the "sequence" the ratchet consumes is mostly cross-sectional,
    not temporal, so its streak counters are double-counting one event.
    """
    if len(days) < 2:
        return None
    pairs = len(days) - 1
    return sum(1 for a, b in zip(days, days[1:]) if a == b) / pairs


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

    # The premise check: an equity-curve de-risking rule only pays if the
    # sleeve's trade returns cluster. Measured on the same teaching trades the
    # ratchet actually consumes, so the test matches what the rule sees.
    print("\n" + "=" * 78)
    print("PREMISE — do losses beget losses? (serial dependence of teaching R)")
    print("=" * 78)
    for s in STRATEGIES:
        rs = [
            r_multiple(t)
            for t in trades
            if _is_teaching_trade(t.get("exit_reason")) and strategy_for_trade(t) == s
        ]
        teach = [
            t for t in trades
            if _is_teaching_trade(t.get("exit_reason")) and strategy_for_trade(t) == s
        ]
        share = same_day_neighbour_share([t["exit_time"].date() for t in teach])
        d = serial_dependence(rs)
        d_day = serial_dependence(daily_aggregate([
            {"day": t["exit_time"].date(), "net_pnl": t["net_pnl"],
             "budget": risk_budget_at_entry(t)}
            for t in teach
        ]))
        wr = "n/a" if d["win_rate"] is None else f"{100 * d['win_rate']:.1f}%"
        print(f"\n--- {s} ---   n={d['n']}  win_rate={wr}")
        if share is not None:
            print(f"  consecutive pairs sharing an exit DAY   {100 * share:.0f}%"
                  f"   <- the sequence is mostly cross-sectional")
        for label, x in (("per-TRADE", d), ("per-DAY  ", d_day)):
            ac = x["lag1_autocorr"]
            ac_s = "n/a" if ac is None else f"{ac:+.4f}"
            band_s = "" if x["significance_band"] is None else \
                f"  band +/-{x['significance_band']:.3f}"
            z_s = "" if x["runs_z"] is None else f"  runs_z={x['runs_z']:+.3f}"
            print(f"  {label}  n={x['n']:>4}  ac={ac_s}{band_s}{z_s}"
                  f"   -> {x['verdict']}")
    print("\nA de-risk-after-losses rule only adds value on a STREAKY sleeve. On an"
          "\nindependent one it is noise-chasing that pays a drag; on a mean-reverting"
          "\none it cuts size exactly before the bounce. Judge on the per-DAY row:"
          "\nper-TRADE counts one bad day once per open position.")

    print("\nReading: `decay` is the only branch that does not need winning trades."
          "\nA sleeve whose median gap between down-steps is shorter than the decay"
          "\nwindow can only leave the floor via a win streak — so the ratchet is an"
          "\nabsorbing state exactly when the sleeve is losing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
