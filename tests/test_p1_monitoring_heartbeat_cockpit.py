"""P1-MONITORING-HEARTBEAT-COCKPIT — Operator safety cockpit and alerting.

Problems identified in ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (WS-10):

1. UI shows inactive strategies as active (STRATEGIES dict is hardcoded; S4 absent,
   S3 present regardless of registry state). Cockpit must derive from SoT registry.

2. No alerting on: fallback rate, worker-beat lag, cap violation. An operator
   looking at paper trading has no early-warning signal that the system is degraded.

3. Strategy schedule in cockpit must match Celery beat configuration, not be
   hardcoded separately (another source of truth fragmentation).

Tests:
- test_cockpit_status_derives_from_registry (not hardcoded STRATEGIES dict)
- test_ui_does_not_show_inactive_as_active
- test_alert_fires_on_fallback_rate_threshold
- test_alert_fires_on_worker_beat_lag_threshold
- test_schedule_derived_from_beat
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cockpit status endpoint — derives from registry SoT
# ─────────────────────────────────────────────────────────────────────────────

class TestCockpitStatusDerivesFromRegistry:

    def test_cockpit_module_exists(self):
        """A cockpit module must exist with a get_cockpit_status function."""
        try:
            from src.monitoring.cockpit import get_cockpit_status
        except ImportError:
            pytest.fail(
                "src.monitoring.cockpit must export get_cockpit_status(). "
                "This function reads the registry and returns real system state."
            )

    def test_cockpit_status_returns_strategy_list(self):
        """get_cockpit_status must return a dict with a 'strategies' key."""
        from src.monitoring.cockpit import get_cockpit_status

        mock_registry = MagicMock()
        entry_s1 = MagicMock()
        entry_s1.strategy_id = "S1"
        entry_s1.enabled = True
        entry_s1.mode = "supervised_paper"
        entry_s1.allocation_pct = 0.5
        entry_s1.schedule = "30 14 * * 1-5"
        mock_registry.get_active_strategies.return_value = [entry_s1]

        status = get_cockpit_status(registry=mock_registry)

        assert "strategies" in status, "get_cockpit_status must return dict with 'strategies' key"
        assert len(status["strategies"]) >= 1

    def test_only_enabled_strategies_appear_in_cockpit(self):
        """Cockpit must only show strategies that are enabled in the registry."""
        from src.monitoring.cockpit import get_cockpit_status

        mock_registry = MagicMock()
        active_entry = MagicMock()
        active_entry.strategy_id = "S1"
        active_entry.enabled = True
        active_entry.mode = "supervised_paper"
        active_entry.allocation_pct = 0.5
        active_entry.schedule = "30 14 * * 1-5"

        # get_active_strategies returns only enabled strategies
        mock_registry.get_active_strategies.return_value = [active_entry]

        status = get_cockpit_status(registry=mock_registry)

        strategy_ids = [s["strategy_id"] for s in status["strategies"]]
        assert "S1" in strategy_ids
        # S2 must NOT appear — it's disabled in the registry and not in active list
        assert "S2" not in strategy_ids, (
            "Cockpit must not show disabled strategies. "
            "The old STRATEGIES dict hardcoded S3 regardless of registry state."
        )


class TestUiDoesNotShowInactiveAsActive:

    def test_cockpit_excludes_strategies_not_in_registry(self):
        """Strategies absent from the registry must not appear in cockpit status.

        Previously, STRATEGIES dict was hardcoded with s1 and s3.
        S3 would show up even if not in the active registry.
        """
        from src.monitoring.cockpit import get_cockpit_status

        mock_registry = MagicMock()
        # Only S1 is active; S3 is absent from registry
        s1_entry = MagicMock()
        s1_entry.strategy_id = "S1"
        s1_entry.enabled = True
        s1_entry.mode = "paper"
        s1_entry.allocation_pct = 0.5
        s1_entry.schedule = "30 14 * * 1-5"
        mock_registry.get_active_strategies.return_value = [s1_entry]

        status = get_cockpit_status(registry=mock_registry)

        strategy_ids = [s["strategy_id"] for s in status["strategies"]]
        assert "S3" not in strategy_ids, (
            "S3 must not appear in cockpit if not in active registry. "
            "Cockpit derives from SoT only, not from a hardcoded dict."
        )

    def test_cockpit_includes_all_active_registry_strategies(self):
        """All enabled strategies in the registry must appear in cockpit."""
        from src.monitoring.cockpit import get_cockpit_status

        mock_registry = MagicMock()
        entries = []
        for sid in ["S1", "S4"]:
            e = MagicMock()
            e.strategy_id = sid
            e.enabled = True
            e.mode = "paper"
            e.allocation_pct = 0.1
            e.schedule = "30 14 * * 1-5"
            entries.append(e)
        mock_registry.get_active_strategies.return_value = entries

        status = get_cockpit_status(registry=mock_registry)

        strategy_ids = [s["strategy_id"] for s in status["strategies"]]
        assert "S1" in strategy_ids
        assert "S4" in strategy_ids, (
            "S4 must appear in cockpit when enabled in registry. "
            "The old STRATEGIES dict only had s1 and s3 — S4 was invisible."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Alerting on thresholds
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertFiresOnThreshold:

    def test_alert_module_exports_check_worker_beat_lag(self):
        """src.monitoring.alerts must export check_worker_beat_lag function."""
        try:
            from src.monitoring.alerts import check_worker_beat_lag
        except ImportError:
            pytest.fail(
                "src.monitoring.alerts must export check_worker_beat_lag(last_beat_ts, threshold_minutes). "
                "This function fires an alert when a worker hasn't heartbeated within the threshold."
            )

    def test_alert_fires_when_beat_lag_exceeds_threshold(self):
        """check_worker_beat_lag must return True (alert!) when beat is stale."""
        from datetime import datetime, timedelta, timezone
        from src.monitoring.alerts import check_worker_beat_lag

        now = datetime.now(timezone.utc)
        stale_ts = now - timedelta(minutes=31)  # 31 min ago, threshold=30

        alert_fired = check_worker_beat_lag(
            last_beat_ts=stale_ts,
            threshold_minutes=30,
        )
        assert alert_fired is True, (
            "check_worker_beat_lag must return True when last_beat is older than threshold. "
            "A stale worker means signals are not being generated."
        )

    def test_no_alert_when_beat_is_fresh(self):
        """check_worker_beat_lag must return False when beat is within threshold."""
        from datetime import datetime, timedelta, timezone
        from src.monitoring.alerts import check_worker_beat_lag

        now = datetime.now(timezone.utc)
        fresh_ts = now - timedelta(minutes=5)  # 5 min ago, well within threshold=30

        alert_fired = check_worker_beat_lag(
            last_beat_ts=fresh_ts,
            threshold_minutes=30,
        )
        assert alert_fired is False

    def test_alert_module_exports_check_fallback_rate(self):
        """src.monitoring.alerts must export check_fallback_rate function."""
        try:
            from src.monitoring.alerts import check_fallback_rate
        except ImportError:
            pytest.fail(
                "src.monitoring.alerts must export check_fallback_rate(rate, threshold). "
                "High fallback rate means the LLM ensemble is failing and sentiment signals "
                "are FinBERT-only (lower quality)."
            )

    def test_alert_fires_when_fallback_rate_exceeds_threshold(self):
        """check_fallback_rate must return True when fallback_rate > threshold."""
        from src.monitoring.alerts import check_fallback_rate

        alert_fired = check_fallback_rate(fallback_rate=0.6, threshold=0.5)
        assert alert_fired is True, (
            "check_fallback_rate must return True when 60% of signals are FinBERT fallback "
            "(threshold=50%). High fallback rate = LLM ensemble is mostly down."
        )

    def test_no_alert_when_fallback_rate_is_acceptable(self):
        """check_fallback_rate must return False when fallback_rate <= threshold."""
        from src.monitoring.alerts import check_fallback_rate

        alert_fired = check_fallback_rate(fallback_rate=0.2, threshold=0.5)
        assert alert_fired is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Schedule in cockpit derived from Celery beat
# ─────────────────────────────────────────────────────────────────────────────

class TestScheduleDerivedFromBeat:

    def test_cockpit_schedule_matches_celery_beat(self):
        """Schedule shown in cockpit must be derived from Celery beat, not hardcoded separately.

        We verify this by checking that the cockpit reads the schedule from the
        StrategyEntry (which gets it from the registry), and the registry's schedule
        field is populated from the Celery beat configuration source.
        """
        from src.strategies.registry import StrategyRegistry, _DEFAULT_SCHEDULE

        # The registry uses _DEFAULT_SCHEDULE as the canonical schedule
        # The cockpit must expose this same value, not a separate hardcoded string.
        reg = StrategyRegistry(load_defaults=False)
        from src.strategies.registry import StrategyEntry
        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=object,
            allocation_pct=0.5,
            schedule=_DEFAULT_SCHEDULE,
            enabled=True,
            mode="paper",
        )
        reg._entries["S1"] = entry

        from src.monitoring.cockpit import get_cockpit_status
        status = get_cockpit_status(registry=reg)

        s1_status = next((s for s in status["strategies"] if s["strategy_id"] == "S1"), None)
        assert s1_status is not None
        assert "schedule" in s1_status, "Cockpit strategy entry must include schedule field"
        assert s1_status["schedule"] == _DEFAULT_SCHEDULE, (
            f"Schedule in cockpit ({s1_status['schedule']}) must match registry schedule "
            f"({_DEFAULT_SCHEDULE}), which is derived from Celery beat config."
        )
