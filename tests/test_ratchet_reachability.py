"""#134: is the F8 recovery path reachable for a sleeve, or is the floor an
absorbing state? Pure-function tests over synthetic trigger sequences."""
from datetime import datetime, timedelta, timezone

from scripts.ratchet_reachability import simulate_ratchet

CFG = {
    "regime_scale_factor": 0.80,
    "regime_min_scale": 0.20,
    "cooldown_hours": 4,
    "threshold_decay_hours": 24,
    "recovery_win_streak": 3,
}

T0 = datetime(2026, 7, 1, 14, 0, tzinfo=timezone.utc)


def _obs(hours_and_states):
    """[(hours_from_T0, triggered, consecutive_wins), ...] -> observations."""
    return [
        {"tick": T0 + timedelta(hours=h), "triggered": t, "consecutive_wins": w}
        for h, t, w in hours_and_states
    ]


def test_persistent_trigger_walks_to_the_floor_and_never_escapes():
    # Triggered every 4h for 10 days: each down-step also resets the decay clock.
    obs = _obs([(h, True, 0) for h in range(0, 240, 4)])
    s = simulate_ratchet(obs, CFG)
    assert s["final_scale"] == CFG["regime_min_scale"]
    assert s["escapes"] == 0
    assert s["decay_steps"] == 0
    assert s["recovery_steps"] == 0
    assert s["decay_starved"] > 0, "repeated triggers must be seen starving the decay"


def test_quiet_period_lets_decay_walk_the_scale_back_to_full():
    obs = _obs([(0, True, 0)] + [(h, False, 0) for h in range(24, 24 * 8, 24)])
    s = simulate_ratchet(obs, CFG)
    assert s["decay_steps"] >= 1
    assert s["final_scale"] == 1.0
    assert s["escapes"] == 1
    assert s["episodes"] == 1


def test_win_streak_recovers_faster_than_decay():
    obs = _obs([(0, True, 0), (5, False, 3)])
    s = simulate_ratchet(obs, CFG)
    assert s["recovery_steps"] == 1
    assert s["final_scale"] == 1.0


def test_cooldown_blocks_a_second_down_step_inside_the_window():
    obs = _obs([(0, True, 0), (1, True, 0), (2, True, 0)])
    s = simulate_ratchet(obs, CFG)
    assert s["down_steps"] == 1, "4h cooldown allows only one adjustment"


def test_decay_needs_the_full_window_since_the_last_adjustment():
    # 23h of quiet is not enough; the scale stays down.
    obs = _obs([(0, True, 0), (23, False, 0)])
    s = simulate_ratchet(obs, CFG)
    assert s["decay_steps"] == 0
    assert s["final_scale"] < 1.0


def test_starvation_counts_only_down_steps_that_reset_a_live_decay_clock():
    # First trigger opens the episode (nothing to starve yet); the second, 5h
    # later and still inside the 24h decay window, is the starving one.
    obs = _obs([(0, True, 0), (5, True, 0)])
    s = simulate_ratchet(obs, CFG)
    assert s["down_steps"] == 2
    assert s["decay_starved"] == 1


def test_floor_time_is_measured():
    obs = _obs([(h, True, 0) for h in range(0, 48, 4)])
    s = simulate_ratchet(obs, CFG)
    assert s["ticks_at_floor"] > 0
    assert s["longest_floor_run_ticks"] == s["ticks_at_floor"]


def test_empty_observations_are_inert():
    s = simulate_ratchet([], CFG)
    assert s["ticks"] == 0
    assert s["final_scale"] == 1.0
    assert s["episodes"] == 0
