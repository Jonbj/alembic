"""P2-02 Promotion Gate Wiring — integration tests.

Verifies that the promotion gate logic (src/strategies/promotion.py) is wired
into:
  1. portfolio_scheduler: is_strategy_operationally_approved() called per
     active strategy; unapproved strategies excluded from cycle.
  2. API: POST /api/strategies/{id}/promote|approve|demote endpoints exist,
     require auth, and delegate to promotion.py.
  3. API /portfolio/status: includes mode and approved fields.

All tests are RED before the wiring implementation.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from src.config import config


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Read from the live config singleton rather than hardcoding a literal: `config`
# freezes ADMIN_API_KEY from os.environ at first import of src.config (module-level
# `config = Config()`), and test-collection order determines which of several
# competing test-only literals scattered across tests/ happens to still be in
# os.environ at that moment. Using config.ADMIN_API_KEY directly is immune to
# that race — it's always the value the app itself compares against.
_API_KEY = config.ADMIN_API_KEY
_AUTH = {"X-API-Key": _API_KEY}


def _make_db_conn(approved: bool = True, has_row: bool = True):
    """Return a mock db_conn whose lifecycle row matches approved/has_row."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    if has_row:
        row = MagicMock()
        row.__getitem__ = lambda self, k: {
            "strategy_id": "S1",
            "mode": "supervised_paper",
            "target_mode": None,
            "gate_report_id": "s4-gate-2026-06-18",
            "approved": approved,
            "promotion_blocked": False,
        }[k]
        cur.fetchone.return_value = row
    else:
        cur.fetchone.return_value = None
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# 1. Scheduler — approval gate wiring
# ─────────────────────────────────────────────────────────────────────────────

class TestSchedulerApprovalGate:

    def test_filter_approved_strategies_function_exists(self):
        """A helper _filter_approved_strategies (or equivalent) must exist in
        the scheduler module so the gate is independently testable."""
        try:
            from src.workers.portfolio_scheduler import _filter_approved_strategies
        except ImportError:
            pytest.fail(
                "src.workers.portfolio_scheduler must export "
                "_filter_approved_strategies(entries, db_conn). "
                "This isolates the approval gate for unit testing."
            )

    def test_approved_strategy_passes_filter(self):
        """Strategy with approved=True must be included in the filtered list."""
        from src.workers.portfolio_scheduler import _filter_approved_strategies
        from src.strategies.registry import StrategyEntry

        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=MagicMock(),
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
        )
        db_conn = _make_db_conn(approved=True)

        result = _filter_approved_strategies([entry], db_conn)
        assert entry in result, (
            "Strategy S1 with approved=True must pass the filter and be included "
            "in the approved list."
        )

    def test_unapproved_strategy_excluded_from_cycle(self):
        """Strategy with approved=False must be excluded from the cycle."""
        from src.workers.portfolio_scheduler import _filter_approved_strategies
        from src.strategies.registry import StrategyEntry

        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=MagicMock(),
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
        )
        db_conn = _make_db_conn(approved=False)

        result = _filter_approved_strategies([entry], db_conn)
        assert entry not in result, (
            "Strategy S1 with approved=False must be excluded from the cycle. "
            "Running unapproved strategies violates the promotion gate contract."
        )

    def test_no_lifecycle_row_is_fail_open(self):
        """If no lifecycle row exists for a strategy (legacy), it is admitted
        with a warning (fail-open) rather than excluded (fail-closed).

        This preserves backward compatibility for environments where
        strategy_lifecycle has not been populated yet.
        """
        from src.workers.portfolio_scheduler import _filter_approved_strategies
        from src.strategies.registry import StrategyEntry

        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=MagicMock(),
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
        )
        db_conn = _make_db_conn(has_row=False)

        result = _filter_approved_strategies([entry], db_conn)
        assert entry in result, (
            "Strategy with no lifecycle row must be admitted (fail-open). "
            "Fail-closed on missing rows would break environments where "
            "strategy_lifecycle has not yet been seeded."
        )

    def test_db_error_in_filter_is_fail_closed(self):
        """If the DB raises during approval check, the strategy is excluded (fail-closed)."""
        from src.workers.portfolio_scheduler import _filter_approved_strategies
        from src.strategies.registry import StrategyEntry

        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=MagicMock(),
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
        )
        broken_conn = MagicMock()
        broken_conn.cursor.side_effect = Exception("DB connection lost")

        result = _filter_approved_strategies([entry], broken_conn)
        assert entry not in result, (
            "DB error during approval check must cause fail-closed: "
            "the strategy is excluded, not admitted. "
            "A DB outage must never silently grant operational approval."
        )

    def test_multiple_strategies_filtered_independently(self):
        """Each strategy is checked independently; one failure doesn't affect others."""
        from src.workers.portfolio_scheduler import _filter_approved_strategies
        from src.strategies.registry import StrategyEntry

        approved_entry = StrategyEntry("S1", MagicMock(), 0.5, "30 14 * * 1-5", True)
        denied_entry  = StrategyEntry("S4", MagicMock(), 0.1, "30 14 * * 1-5", True)

        # Build a conn that returns approved=True for S1, approved=False for S4
        call_count = [0]
        def make_cursor():
            cur = MagicMock()
            idx = call_count[0]
            call_count[0] += 1
            row = MagicMock()
            approved_val = (idx == 0)  # first call (S1) approved, second (S4) denied
            row.__getitem__ = lambda self, k: {
                "strategy_id": ["S1", "S4"][min(idx, 1)],
                "mode": "supervised_paper",
                "target_mode": None,
                "gate_report_id": "rpt-1",
                "approved": approved_val,
                "promotion_blocked": False,
            }[k]
            cur.fetchone.return_value = row
            ctx = MagicMock()
            ctx.__enter__ = MagicMock(return_value=cur)
            ctx.__exit__ = MagicMock(return_value=False)
            return ctx

        conn = MagicMock()
        conn.cursor.side_effect = make_cursor

        result = _filter_approved_strategies([approved_entry, denied_entry], conn)
        assert approved_entry in result
        assert denied_entry not in result


# ─────────────────────────────────────────────────────────────────────────────
# 2. API — promotion endpoints
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategiesAPIPromotion:

    def test_promote_endpoint_exists(self):
        """POST /api/strategies/S1/promote must not return 404."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.routes.strategies.request_promotion") as mock_rp:
            from src.strategies.promotion import PromotionBlockedError
            mock_rp.side_effect = PromotionBlockedError("gate_report_id required")

            tc = TestClient(app)
            resp = tc.post(
                "/api/strategies/S1/promote",
                json={"target_mode": "paper", "gate_report_id": None, "requested_by": "test"},
                headers=_AUTH,
            )
        assert resp.status_code != 404, (
            "POST /api/strategies/S1/promote must exist (got 404). "
            "Add this endpoint to src/api/routes/strategies.py."
        )

    def test_approve_endpoint_exists(self):
        """POST /api/strategies/S1/approve must not return 404."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.routes.strategies.approve_promotion") as mock_ap:
            from src.strategies.promotion import PromotionBlockedError
            mock_ap.side_effect = PromotionBlockedError("no pending request")

            tc = TestClient(app)
            resp = tc.post(
                "/api/strategies/S1/approve",
                json={"approved_by": "test"},
                headers=_AUTH,
            )
        assert resp.status_code != 404, (
            "POST /api/strategies/S1/approve must exist (got 404). "
            "Add this endpoint to src/api/routes/strategies.py."
        )

    def test_demote_endpoint_exists(self):
        """POST /api/strategies/S1/demote must not return 404."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.routes.strategies.demote_strategy") as mock_dm:
            mock_dm.return_value = None

            tc = TestClient(app)
            resp = tc.post(
                "/api/strategies/S1/demote",
                json={"new_mode": "research", "reason": "test", "demoted_by": "test"},
                headers=_AUTH,
            )
        assert resp.status_code != 404, (
            "POST /api/strategies/S1/demote must exist (got 404). "
            "Add this endpoint to src/api/routes/strategies.py."
        )

    def test_promote_returns_422_on_blocked(self):
        """promote endpoint returns 422 when PromotionBlockedError is raised."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.strategies.promotion import PromotionBlockedError

        _fake_store = MagicMock()
        _fake_store.__exit__ = MagicMock(return_value=False)

        with patch("src.api.routes.strategies.request_promotion") as mock_rp, \
             patch("src.api.routes.strategies._get_db_conn") as mock_db:
            mock_db.return_value = (_fake_store, MagicMock())
            mock_rp.side_effect = PromotionBlockedError("gate_report_id required")

            tc = TestClient(app)
            resp = tc.post(
                "/api/strategies/S1/promote",
                json={"target_mode": "paper", "gate_report_id": None, "requested_by": "test"},
                headers=_AUTH,
            )
        assert resp.status_code == 422, (
            f"promote endpoint must return 422 on PromotionBlockedError, got {resp.status_code}. "
            "The error detail must explain why the promotion was blocked."
        )

    def test_demote_returns_200_on_success(self):
        """demote endpoint returns 200 on success."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        _fake_store = MagicMock()
        _fake_store.__exit__ = MagicMock(return_value=False)

        with patch("src.api.routes.strategies.demote_strategy") as mock_dm, \
             patch("src.api.routes.strategies._get_db_conn") as mock_db:
            mock_db.return_value = (_fake_store, MagicMock())
            mock_dm.return_value = None

            tc = TestClient(app)
            resp = tc.post(
                "/api/strategies/S1/demote",
                json={"new_mode": "paper", "reason": "test demotion", "demoted_by": "test"},
                headers=_AUTH,
            )
        assert resp.status_code == 200, (
            f"demote endpoint must return 200 on success, got {resp.status_code}"
        )

    def test_promote_endpoint_requires_auth(self):
        """POST /api/strategies/S1/promote must return 401/403 without API key."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        tc = TestClient(app)
        resp = tc.post(
            "/api/strategies/S1/promote",
            json={"target_mode": "paper", "gate_report_id": "r1", "requested_by": "test"},
        )
        assert resp.status_code in (401, 403), (
            f"promote endpoint must require authentication, got {resp.status_code}. "
            "Without auth, anyone can trigger promotion requests."
        )

    def test_demote_endpoint_requires_auth(self):
        """POST /api/strategies/S1/demote must return 401/403 without API key."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        tc = TestClient(app)
        resp = tc.post(
            "/api/strategies/S1/demote",
            json={"new_mode": "paper", "reason": "test", "demoted_by": "test"},
        )
        assert resp.status_code in (401, 403), (
            f"demote endpoint must require authentication, got {resp.status_code}. "
        )

    def test_approve_endpoint_requires_auth(self):
        """POST /api/strategies/S1/approve must return 401/403 without API key."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        tc = TestClient(app)
        resp = tc.post(
            "/api/strategies/S1/approve",
            json={"approved_by": "test"},
        )
        assert resp.status_code in (401, 403), (
            f"approve endpoint must require authentication, got {resp.status_code}. "
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. API /portfolio/status — mode and approved fields
# ─────────────────────────────────────────────────────────────────────────────

class TestPortfolioStatusGovernanceFields:

    def test_portfolio_status_includes_mode_field(self):
        """GET /portfolio/status must include 'mode' in each strategy entry."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store

        mock_store = MagicMock()
        mock_store.get_last_portfolio_cycle.return_value = None

        app.dependency_overrides[get_pg_store] = lambda: mock_store
        try:
            tc = TestClient(app)
            resp = tc.get("/portfolio/status", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200
        data = resp.json()
        strategies = data.get("strategies", [])
        assert strategies, "Expected at least one strategy in /portfolio/status"
        for s in strategies:
            assert "mode" in s, (
                f"Strategy entry {s.get('strategy_id')} is missing 'mode' field. "
                "mode must be included so the cockpit shows the governance state."
            )

    def test_portfolio_status_includes_approved_field(self):
        """GET /portfolio/status must include 'approved' in each strategy entry."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store

        mock_store = MagicMock()
        mock_store.get_last_portfolio_cycle.return_value = None

        app.dependency_overrides[get_pg_store] = lambda: mock_store
        try:
            tc = TestClient(app)
            resp = tc.get("/portfolio/status", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200
        data = resp.json()
        strategies = data.get("strategies", [])
        assert strategies
        for s in strategies:
            assert "approved" in s, (
                f"Strategy entry {s.get('strategy_id')} is missing 'approved' field. "
                "approved must be shown so operators can see which strategies are gate-cleared."
            )

    def test_portfolio_status_mode_survives_db_unavailable(self):
        """GET /portfolio/status must not crash when DB is unavailable for mode lookup.

        When strategy_lifecycle is unreachable, mode and approved should be null
        (fail-open) rather than causing a 500.
        """
        from fastapi.testclient import TestClient
        from src.api.main import app
        from src.api.deps import get_pg_store

        mock_store = MagicMock()
        mock_store.get_last_portfolio_cycle.return_value = None
        # _get_connection raises to simulate DB unavailability
        mock_store._get_connection.side_effect = Exception("DB down")

        app.dependency_overrides[get_pg_store] = lambda: mock_store
        try:
            tc = TestClient(app)
            resp = tc.get("/portfolio/status", headers=_AUTH)
        finally:
            app.dependency_overrides.pop(get_pg_store, None)

        assert resp.status_code == 200, (
            f"GET /portfolio/status must return 200 even when DB is unavailable, "
            f"got {resp.status_code}. DB failure must not crash the status endpoint."
        )
