"""P2-04 Monitoring Wiring / Operator Cockpit — RED tests.

Verifies:
  T1-T4+T10: get_cockpit_alerts() in cockpit.py — required keys, MISCONF detection,
             DB health flag, stale-signal flag.
  T5-T7:     GET /api/system/readiness endpoint — exists, returns required keys,
             reflects Redis unavailability.
  T8-T9:     GET /api/system/decisions endpoint — exists, returns reason field.
  T11-T12:   _check_divergence_and_alert() helper in scheduler — fires _fire_alert
             on signal divergence and execution divergence.

All 12 tests must be RED before implementation.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

_API_KEY = "test-api-key-for-testing-only-12345678"
_AUTH = {"X-API-Key": _API_KEY}

_REQUIRED_ALERT_KEYS = {
    "redis_healthy",
    "redis_writeable",
    "db_healthy",
    "killswitch_active",
    "stale_signals",
    "worker_beat_lag",
    "last_signal_age_minutes",
    "last_cycle_age_minutes",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_mock_pg(last_signal_ts=None, last_cycle_ts=None):
    """Return a mock PostgreSQLStore suitable for get_cockpit_alerts()."""
    pg = MagicMock()
    conn = MagicMock()
    pg._get_connection.return_value = conn

    cursor = MagicMock()
    # cursor context manager
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor

    # Two sequential fetchone calls: first = signal, second = cycle
    cursor.fetchone.side_effect = [
        (last_signal_ts,) if last_signal_ts is not None else (None,),
        (last_cycle_ts,) if last_cycle_ts is not None else (None,),
    ]
    return pg


def _make_mock_redis(ping_raises=None, set_raises=None, ks_active=False):
    """Return a mock raw Redis client."""
    r = MagicMock()
    if ping_raises:
        r.ping.side_effect = ping_raises
    else:
        r.ping.return_value = True

    if set_raises:
        r.set.side_effect = set_raises
    else:
        r.set.return_value = True

    r.get.return_value = "1" if ks_active else None
    return r


# ─────────────────────────────────────────────────────────────────────────────
# T1-T4 + T10: get_cockpit_alerts()
# ─────────────────────────────────────────────────────────────────────────────


class TestCockpitAlerts:

    def test_get_cockpit_alerts_function_exists(self):
        """get_cockpit_alerts must be importable from src.monitoring.cockpit."""
        try:
            from src.monitoring.cockpit import get_cockpit_alerts
        except ImportError:
            pytest.fail(
                "src.monitoring.cockpit must export get_cockpit_alerts(pg, redis_client). "
                "This function aggregates all operator alert flags into a single dict."
            )

    def test_cockpit_alerts_returns_required_keys(self):
        """get_cockpit_alerts must return a dict with all 8 required alert keys."""
        from src.monitoring.cockpit import get_cockpit_alerts

        pg = _make_mock_pg()
        redis_client = _make_mock_redis()

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        missing = _REQUIRED_ALERT_KEYS - set(result.keys())
        assert not missing, (
            f"get_cockpit_alerts() is missing required keys: {missing}. "
            "All 8 keys must be present in the returned dict."
        )

    def test_cockpit_alerts_redis_misconf_detected(self):
        """When redis SET raises ResponseError, redis_writeable must be False
        but redis_healthy must remain True (MISCONF: reads work, writes blocked)."""
        from src.monitoring.cockpit import get_cockpit_alerts
        from redis.exceptions import ResponseError

        pg = _make_mock_pg()
        redis_client = _make_mock_redis(set_raises=ResponseError("MISCONF"))

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        assert result["redis_healthy"] is True, (
            "redis_healthy must be True when PING succeeds — MISCONF only blocks writes."
        )
        assert result["redis_writeable"] is False, (
            "redis_writeable must be False when SET raises ResponseError (MISCONF). "
            "Add a test-write after PING to detect this condition."
        )

    def test_cockpit_alerts_db_healthy_false_when_down(self):
        """When DB raises on SELECT 1, db_healthy must be False."""
        from src.monitoring.cockpit import get_cockpit_alerts

        pg = MagicMock()
        pg._get_connection.side_effect = Exception("DB connection refused")
        redis_client = _make_mock_redis()

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        assert result["db_healthy"] is False, (
            "db_healthy must be False when the DB connection raises. "
            "get_cockpit_alerts must catch DB exceptions and set db_healthy=False."
        )

    def test_stale_signals_flag_true_when_signal_old(self):
        """stale_signals must be True when the most recent signal is older than staleness_hours."""
        from src.monitoring.cockpit import get_cockpit_alerts

        three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
        pg = _make_mock_pg(last_signal_ts=three_hours_ago)
        redis_client = _make_mock_redis()

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client, staleness_hours=2.0)

        assert result["stale_signals"] is True, (
            "stale_signals must be True when last signal is 3h old and threshold is 2h. "
            "Compute: last_signal_age_minutes > staleness_hours * 60."
        )

    def test_killswitch_active_true_when_operator_halt_key_set(self):
        """killswitch_active must be True when system:halted_by_operator is set in Redis,
        even if the drawdown-path key killswitch_active is absent.

        The kill-switch has two activation paths:
          - drawdown path  → sets Redis key ``killswitch_active``
          - operator path  → sets Redis key ``system:halted_by_operator``
        Both must be reflected in the cockpit health dict.  Before the fix, only the
        drawdown-path key was checked, so a manual operator halt was invisible to the
        cockpit (BUG-6).
        """
        from src.monitoring.cockpit import get_cockpit_alerts
        from unittest.mock import MagicMock

        pg = _make_mock_pg()
        redis_client = MagicMock()
        redis_client.ping.return_value = True
        redis_client.set.return_value = True
        # drawdown-path key: absent; operator-halt key: set
        redis_client.get.side_effect = lambda key: (
            b"1" if key == "system:halted_by_operator" else None
        )

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        assert result["killswitch_active"] is True, (
            "killswitch_active must be True when system:halted_by_operator is set in Redis. "
            "Fix: check both 'killswitch_active' and 'system:halted_by_operator' keys. "
            f"Got killswitch_active={result['killswitch_active']!r}."
        )

    def test_killswitch_active_true_when_drawdown_key_set(self):
        """killswitch_active must be True when the drawdown-path key killswitch_active is set."""
        from src.monitoring.cockpit import get_cockpit_alerts

        pg = _make_mock_pg()
        redis_client = _make_mock_redis(ks_active=True)

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        assert result["killswitch_active"] is True, (
            "killswitch_active must be True when Redis key 'killswitch_active' is set."
        )

    def test_killswitch_active_false_when_neither_key_set(self):
        """killswitch_active must be False when both keys are absent."""
        from src.monitoring.cockpit import get_cockpit_alerts

        pg = _make_mock_pg()
        redis_client = _make_mock_redis(ks_active=False)

        result = get_cockpit_alerts(pg=pg, redis_client=redis_client)

        assert result["killswitch_active"] is False, (
            "killswitch_active must be False when neither key is present in Redis."
        )


# ─────────────────────────────────────────────────────────────────────────────
# T5-T7: GET /api/system/readiness
# ─────────────────────────────────────────────────────────────────────────────


class TestReadinessEndpoint:

    def _make_app_client(self, mock_pg=None, mock_redis_store=None):
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store, get_redis_store

        if mock_pg is None:
            mock_pg = _make_mock_pg()
        if mock_redis_store is None:
            raw_r = _make_mock_redis()
            mock_redis_store = MagicMock()
            mock_redis_store._r = raw_r

        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
        client = TestClient(app)
        return client, app, get_pg_store, get_redis_store

    def test_readiness_endpoint_exists(self):
        """GET /api/system/readiness must return something other than 404."""
        client, app, get_pg_store, get_redis_store = self._make_app_client()
        try:
            resp = client.get("/api/system/readiness", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)
            app.dependency_overrides.pop(get_redis_store, None)

        assert resp.status_code != 404, (
            "GET /api/system/readiness must exist. Got 404. "
            "Add this endpoint to src/api/routes/system_routes.py."
        )

    def test_readiness_response_has_required_keys(self):
        """GET /api/system/readiness response must include all required alert keys."""
        client, app, get_pg_store, get_redis_store = self._make_app_client()
        try:
            resp = client.get("/api/system/readiness", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)
            app.dependency_overrides.pop(get_redis_store, None)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        data = resp.json()
        missing = _REQUIRED_ALERT_KEYS - set(data.keys())
        assert not missing, (
            f"GET /api/system/readiness response is missing keys: {missing}. "
            "The endpoint must return the full get_cockpit_alerts() dict."
        )

    def test_readiness_redis_healthy_false_when_unreachable(self):
        """GET /api/system/readiness must return redis_healthy=False when Redis ping fails.

        The response must still be HTTP 200 — health state is encoded in the body,
        not in the HTTP status code.
        """
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store, get_redis_store

        raw_r = _make_mock_redis(ping_raises=ConnectionError("Redis unreachable"))
        mock_redis_store = MagicMock()
        mock_redis_store._r = raw_r
        mock_pg = _make_mock_pg()

        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
        try:
            client = TestClient(app)
            resp = client.get("/api/system/readiness", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)
            app.dependency_overrides.pop(get_redis_store, None)

        assert resp.status_code == 200, (
            f"GET /api/system/readiness must return 200 even when Redis is down. "
            f"Got {resp.status_code}. Encode health state in body, not HTTP status."
        )
        data = resp.json()
        assert data.get("redis_healthy") is False, (
            f"redis_healthy must be False when Redis ping raises. Got: {data.get('redis_healthy')}."
        )


# ─────────────────────────────────────────────────────────────────────────────
# T8-T9: GET /api/system/decisions
# ─────────────────────────────────────────────────────────────────────────────


class TestDecisionsEndpoint:

    def test_decisions_endpoint_exists(self):
        """GET /api/system/decisions must exist (not 404)."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store

        mock_pg = MagicMock()
        mock_pg.fetch_decisions.return_value = []

        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        try:
            client = TestClient(app)
            resp = client.get("/api/system/decisions", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code != 404, (
            "GET /api/system/decisions must exist. Got 404. "
            "Add this endpoint to src/api/routes/system_routes.py."
        )

    def test_decisions_response_has_reason_field(self):
        """Each entry in GET /api/system/decisions must have a 'reason' field."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store

        mock_pg = MagicMock()
        mock_pg.fetch_decisions.return_value = [
            {
                "tick_time": datetime(2026, 6, 20, 14, 7, tzinfo=timezone.utc),
                "symbol": "AAPL",
                "decision": "BUY",
                "reason": "S4 score=0.83 regime=1.0 ema=True",
                "score": 0.83,
                "regime_mult": 1.0,
                "ema_pass": True,
                "order_id": "test-order-id",
                "id": 1,
                "signal_id": None,
                "created_at": datetime(2026, 6, 20, 14, 7, tzinfo=timezone.utc),
            }
        ]

        app.dependency_overrides[get_pg_store] = lambda: mock_pg
        try:
            client = TestClient(app)
            resp = client.get("/api/system/decisions", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        entries = resp.json()
        assert len(entries) > 0, "Expected at least one decision entry"
        first = entries[0]
        assert "reason" in first, (
            f"Each decision entry must have a 'reason' field. Got keys: {list(first.keys())}. "
            "The endpoint must expose the full execution_decisions row including reason."
        )


# ─────────────────────────────────────────────────────────────────────────────
# T11-T12: _check_divergence_and_alert() in scheduler
# ─────────────────────────────────────────────────────────────────────────────


class TestDivergenceAlertsInScheduler:

    def test_check_divergence_and_alert_function_exists(self):
        """_check_divergence_and_alert must be importable from portfolio_scheduler."""
        try:
            from src.workers.portfolio_scheduler import _check_divergence_and_alert
        except ImportError:
            pytest.fail(
                "src.workers.portfolio_scheduler must export _check_divergence_and_alert(). "
                "Extract this helper so divergence logic is independently testable."
            )

    def test_scheduler_fires_warning_on_signal_divergence(self):
        """_check_divergence_and_alert must call _fire_alert when signal/order sets diverge.

        signal_syms={"AAPL","MSFT"}, order_syms=set() → Jaccard overlap=0 < 0.8 threshold
        → check_signal_divergence returns True → _fire_alert must be called.
        The Telegram send is gated by notifications.send_signal_order_divergence_alert
        (default false); this wiring test patches the gate ON to verify the path.
        """
        from src.workers.portfolio_scheduler import _check_divergence_and_alert

        notifier = MagicMock()

        with patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire, \
             patch(
                 "src.workers.portfolio_scheduler._divergence_alert_enabled",
                 return_value=True,
             ):
            _check_divergence_and_alert(
                signal_syms={"AAPL", "MSFT"},
                order_syms=set(),
                submitted_count=0,
                final_count=0,
                notifier=notifier,
            )

        assert mock_fire.called, (
            "_fire_alert must be called when signal/order divergence exceeds threshold "
            "and the alert gate is enabled. "
            "signal_syms={'AAPL','MSFT'} vs order_syms=set() → 0% overlap < 80% threshold. "
            "Wire check_signal_divergence() into _check_divergence_and_alert()."
        )

    def test_scheduler_silent_on_signal_divergence_when_gate_off(self):
        """When notifications.send_signal_order_divergence_alert is false (default),
        _check_divergence_and_alert must NOT call _fire_alert even on divergence.
        The divergence is still detected; only the Telegram send is suppressed.
        """
        from src.workers.portfolio_scheduler import _check_divergence_and_alert

        notifier = MagicMock()

        with patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire, \
             patch(
                 "src.workers.portfolio_scheduler._divergence_alert_enabled",
                 return_value=False,
             ):
            _check_divergence_and_alert(
                signal_syms={"AAPL", "MSFT"},
                order_syms=set(),
                submitted_count=0,
                final_count=0,
                notifier=notifier,
            )

        assert not mock_fire.called, (
            "_fire_alert must NOT be called when the divergence alert gate is off. "
            "Detection still runs; only the Telegram WARNING send is suppressed."
        )

    def test_scheduler_fires_warning_on_execution_divergence(self):
        """_check_divergence_and_alert must call _fire_alert when fill ratio diverges.

        2 final orders, 0 submitted (fill ratio 0.0) vs baseline 1.0 → |0.0-1.0|=1.0 > 0.20
        → check_execution_divergence returns True → _fire_alert must be called.
        """
        from src.workers.portfolio_scheduler import _check_divergence_and_alert

        notifier = MagicMock()

        with patch("src.workers.portfolio_scheduler._fire_alert") as mock_fire:
            _check_divergence_and_alert(
                signal_syms=set(),
                order_syms=set(),
                submitted_count=0,
                final_count=2,
                notifier=notifier,
            )

        assert mock_fire.called, (
            "_fire_alert must be called when execution fill ratio diverges from baseline. "
            "submitted_count=0, final_count=2 → fill_ratio=0.0, |0.0-1.0|=1.0 > 0.20 threshold. "
            "Wire check_execution_divergence() into _check_divergence_and_alert()."
        )
