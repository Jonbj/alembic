"""P0-09 guardrail: beat schedule must include a pre-market regime run.

Root cause (Day 1, 2026-06-23): detect_regime at 07:00 UTC failed (LLM/FRED
unavailable). No fallback run existed, so regime:current was absent for the
entire trading session (14:07–20:00 UTC). All positions sized at ×0.2
(high_vol fallback) instead of ×0.7 (actual sideways regime).

Fix: add a second beat entry at 13:30 UTC Mon-Fri (30 min before NYSE open).
If the 07:00 run succeeds, the 13:30 run is a no-op (same regime, harmless
Redis write). If 07:00 fails, 13:30 rescues the session.
"""
import pytest


class TestRegimePremarketSchedule:
    def _regime_entries(self):
        from src.workers.celery_app import app
        return [
            (name, entry)
            for name, entry in app.conf.beat_schedule.items()
            if entry.get("task") == "src.workers.regime.detect_regime"
        ]

    def test_at_least_two_regime_beat_entries(self):
        """Beat schedule must have ≥2 detect_regime entries (07:00 + 13:30)."""
        entries = self._regime_entries()
        names = [n for n, _ in entries]
        assert len(entries) >= 2, (
            f"Expected ≥2 beat entries for detect_regime, found {len(entries)}: {names}. "
            "Add a pre-market entry (13:30 UTC) so 07:00 failures don't leave "
            "regime:current absent for the entire trading session."
        )

    def test_premarket_entry_fires_at_13_utc(self):
        """One beat entry must fire at hour=13 (13:30 UTC pre-market)."""
        entries = self._regime_entries()
        schedules = [entry["schedule"] for _, entry in entries]
        hours_with_13 = [s for s in schedules if 13 in getattr(s, "hour", set())]
        assert hours_with_13, (
            "No detect_regime beat entry fires at hour=13 (UTC). "
            "Add 'regime-detector-premarket' at crontab(hour=13, minute=30) "
            "to cover 07:00 failures before market open."
        )

    def test_premarket_entry_routed_to_inference_queue(self):
        """Pre-market entry must route to 'inference' queue (Ollama isolation)."""
        entries = self._regime_entries()
        for name, entry in entries:
            sched = entry.get("schedule")
            if 13 in getattr(sched, "hour", set()):
                opts = entry.get("options", {})
                assert opts.get("queue") == "inference", (
                    f"Entry {name!r} fires at hour=13 but queue={opts.get('queue')!r}. "
                    "Must route to 'inference' queue like the 07:00 entry."
                )
                return
        pytest.skip("No 13:xx entry found — covered by test_premarket_entry_fires_at_13_utc")
