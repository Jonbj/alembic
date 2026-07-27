"""#32: F8 shadow evidence — read the persisted trajectory instead of only
replaying it. Pure-function tests (no DB, no Redis)."""
from datetime import datetime, timezone

from scripts.f8_regime_scale_shadow_evidence import (
    gate_verdict,
    merge_recorded_rows,
    splice_trajectory,
)


def _ts(day, hour=16, minute=0):
    return datetime(2026, 7, day, hour, minute, tzinfo=timezone.utc)


def _row(day, strategy, scale, hour=16):
    return {"cycle_ts": _ts(day, hour), "strategy": strategy, "scale": scale}


# --- merge_recorded_rows -------------------------------------------------

def test_absent_strategy_on_a_recorded_day_is_full_scale():
    # Rows exist only when a scale is active (<1.0), so a strategy with no row
    # on a day the cycle ran was NOT de-risked — that is 1.0, not missing data.
    rows = merge_recorded_rows([_row(21, "S1", 0.41)], strategies=("S1", "S4"))
    assert rows == [{"date": "2026-07-21", "S1": 0.41, "S4": 1.0, "source": "recorded"}]


def test_last_cycle_of_the_day_wins():
    recorded = [
        _row(21, "S1", 0.41, hour=14),
        _row(21, "S1", 0.328, hour=17),
        _row(21, "S1", 0.2, hour=20),
    ]
    rows = merge_recorded_rows(recorded, strategies=("S1", "S4"))
    assert rows[0]["S1"] == 0.2


def test_days_are_sorted_and_one_row_each():
    recorded = [_row(24, "S4", 0.8), _row(21, "S1", 0.41), _row(22, "S1", 0.2)]
    rows = merge_recorded_rows(recorded, strategies=("S1", "S4"))
    assert [r["date"] for r in rows] == ["2026-07-21", "2026-07-22", "2026-07-24"]


def test_empty_recorded_yields_no_rows():
    assert merge_recorded_rows([], strategies=("S1", "S4")) == []


# --- splice_trajectory ---------------------------------------------------

def test_recorded_wins_from_its_first_date_onward():
    replay = [
        {"date": "2026-07-20", "S1": 0.2, "S4": 1.0},
        {"date": "2026-07-21", "S1": 0.9, "S4": 0.9},  # replay drift
    ]
    recorded = [{"date": "2026-07-21", "S1": 0.2, "S4": 0.8, "source": "recorded"}]
    out = splice_trajectory(replay, recorded)
    assert [r["date"] for r in out] == ["2026-07-20", "2026-07-21"]
    assert out[0]["source"] == "replay"
    assert out[1]["S1"] == 0.2 and out[1]["S4"] == 0.8
    assert out[1]["source"] == "recorded"


def test_no_recorded_data_falls_back_to_pure_replay():
    replay = [{"date": "2026-07-20", "S1": 0.2, "S4": 1.0}]
    out = splice_trajectory(replay, [])
    assert out == [{"date": "2026-07-20", "S1": 0.2, "S4": 1.0, "source": "replay"}]


def test_replay_days_after_the_recorded_window_are_dropped():
    # Once persistence is live the recorded set is authoritative; a replay day
    # past its end would silently reintroduce reconstructed numbers.
    replay = [{"date": "2026-07-21", "S1": 0.2, "S4": 0.8},
              {"date": "2026-07-22", "S1": 0.9, "S4": 0.9}]
    recorded = [{"date": "2026-07-21", "S1": 0.2, "S4": 0.8, "source": "recorded"}]
    out = splice_trajectory(replay, recorded)
    assert [r["date"] for r in out] == ["2026-07-21"]


# --- gate_verdict --------------------------------------------------------

def _traj(values, strategy="S1"):
    return [{"date": f"2026-07-{20 + i:02d}", strategy: v} for i, v in enumerate(values)]


def test_recovery_cycle_observed_passes_the_gate():
    # S4 shape: de-risked, then decayed back to full.
    v = gate_verdict(_traj([1.0, 0.8, 0.512, 0.8, 1.0], "S4"), "S4", min_scale=0.2)
    assert v["recovery_cycles"] == 1
    assert v["current_floor_streak"] == 0
    assert v["gate"] == "PASS"


def test_pinned_at_floor_without_recovery_fails_the_gate():
    # S1 shape: ratcheted to the floor and never released.
    v = gate_verdict(_traj([1.0, 0.64, 0.41, 0.2, 0.2, 0.2, 0.2, 0.2], "S1"), "S1",
                     min_scale=0.2)
    assert v["recovery_cycles"] == 0
    assert v["days_at_floor"] == 5
    assert v["current_floor_streak"] == 5
    assert v["gate"] == "FAIL"
    assert "no trigger->recovery cycle" in v["reason"]
    assert "floor" in v["reason"]


def test_floor_streak_counts_only_trailing_days():
    v = gate_verdict(_traj([0.2, 0.2, 0.41, 0.2], "S1"), "S1", min_scale=0.2)
    assert v["days_at_floor"] == 3
    assert v["current_floor_streak"] == 1


def test_never_de_risked_has_no_recovery_and_no_floor():
    v = gate_verdict(_traj([1.0, 1.0, 1.0], "S4"), "S4", min_scale=0.2)
    assert v["recovery_cycles"] == 0
    assert v["days_at_floor"] == 0
    assert v["gate"] == "FAIL"
    assert "no trigger->recovery cycle" in v["reason"]


def test_empty_trajectory_is_not_a_pass():
    v = gate_verdict([], "S1", min_scale=0.2)
    assert v["gate"] == "FAIL"
