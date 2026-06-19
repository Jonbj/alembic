"""P1-10 Promotion Gate Logic — enforcement of strategy lifecycle transitions.

Problems:
- strategy_lifecycle table exists but no code enforces gate_report_id, approved,
  promotion_blocked, or the ordered transition graph.
- promotion_blocked is a data field only — never checked before any state change.
- No audit trail for transitions.
- is_strategy_operationally_approved doesn't exist; workers ignore DB mode.

All tests use mocked DB cursors (same pattern as test_p1_strategy_sot_db.py)
so they run without a live PostgreSQL instance.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db(rows_by_query: dict | None = None, side_effect=None):
    """Return a mock db_conn whose cursor().fetchone() / fetchall() return test data."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cur)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    if side_effect:
        conn.cursor.side_effect = side_effect
    return conn, cur


def _lifecycle_row(
    strategy_id="S1",
    mode="supervised_paper",
    target_mode=None,
    gate_report_id=None,
    approved=False,
    promotion_blocked=False,
):
    """Return a dict-like row matching strategy_lifecycle schema."""
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "strategy_id": strategy_id,
        "mode": mode,
        "target_mode": target_mode,
        "gate_report_id": gate_report_id,
        "approved": approved,
        "promotion_blocked": promotion_blocked,
    }[k]
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 1. Module + exception presence
# ─────────────────────────────────────────────────────────────────────────────

class TestPromotionModuleExists:

    def test_promotion_module_importable(self):
        try:
            import src.strategies.promotion
        except ImportError:
            pytest.fail("src.strategies.promotion must exist")

    def test_promotion_blocked_error_exported(self):
        try:
            from src.strategies.promotion import PromotionBlockedError
        except ImportError:
            pytest.fail("src.strategies.promotion must export PromotionBlockedError")

    def test_request_promotion_exported(self):
        try:
            from src.strategies.promotion import request_promotion
        except ImportError:
            pytest.fail("src.strategies.promotion must export request_promotion()")

    def test_approve_promotion_exported(self):
        try:
            from src.strategies.promotion import approve_promotion
        except ImportError:
            pytest.fail("src.strategies.promotion must export approve_promotion()")

    def test_demote_strategy_exported(self):
        try:
            from src.strategies.promotion import demote_strategy
        except ImportError:
            pytest.fail("src.strategies.promotion must export demote_strategy()")

    def test_is_strategy_operationally_approved_exported(self):
        try:
            from src.strategies.promotion import is_strategy_operationally_approved
        except ImportError:
            pytest.fail(
                "src.strategies.promotion must export is_strategy_operationally_approved()"
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. promotion_blocked enforcement
# ─────────────────────────────────────────────────────────────────────────────

class TestPromotionBlocked:

    def test_s4_cannot_be_promoted_when_promotion_blocked(self):
        """request_promotion raises PromotionBlockedError when promotion_blocked=True.

        S4 has promotion_blocked=True in strategies.yaml and strategy_lifecycle.
        Any promotion attempt must be rejected before touching the DB.
        """
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S4", mode="paper", promotion_blocked=True
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="promotion_blocked"):
            request_promotion(
                strategy_id="S4",
                target_mode="supervised_paper",
                gate_report_id="rpt-001",
                requested_by="operator",
                db_conn=conn,
            )

    def test_s7_cannot_be_promoted_when_promotion_blocked(self):
        """S7 also has promotion_blocked=True — same enforcement applies."""
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S7", mode="research", promotion_blocked=True
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="promotion_blocked"):
            request_promotion(
                strategy_id="S7",
                target_mode="paper",
                gate_report_id="rpt-s7-001",
                requested_by="operator",
                db_conn=conn,
            )

    def test_promotion_blocked_false_does_not_block_by_itself(self):
        """When promotion_blocked=False, failure is for another reason (gate_report_id missing),
        not because of the blocked flag."""
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", promotion_blocked=False, gate_report_id=None
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="gate_report_id"):
            request_promotion(
                strategy_id="S1",
                target_mode="supervised_paper",
                gate_report_id=None,
                requested_by="operator",
                db_conn=conn,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Gate requirements
# ─────────────────────────────────────────────────────────────────────────────

class TestGateRequirements:

    def test_promotion_requires_gate_report_id(self):
        """request_promotion with gate_report_id=None raises PromotionBlockedError."""
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", promotion_blocked=False, gate_report_id=None
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="gate_report_id"):
            request_promotion(
                strategy_id="S1",
                target_mode="supervised_paper",
                gate_report_id=None,
                requested_by="operator",
                db_conn=conn,
            )

    def test_request_promotion_sets_target_mode_and_gate_report(self):
        """A valid request_promotion call writes target_mode and gate_report_id to DB.

        This is step 1 of the two-step flow: request → approve.
        """
        from src.strategies.promotion import request_promotion

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", promotion_blocked=False, gate_report_id=None
        )
        cur.fetchone.return_value = row

        request_promotion(
            strategy_id="S1",
            target_mode="supervised_paper",
            gate_report_id="rpt-s1-2026",
            requested_by="operator",
            db_conn=conn,
        )

        # Must execute an UPDATE on strategy_lifecycle
        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any("update" in sql and "strategy_lifecycle" in sql for sql in executed_sqls), (
            "request_promotion must UPDATE strategy_lifecycle to set target_mode and gate_report_id. "
            f"Executed SQLs: {executed_sqls}"
        )

    def test_approve_promotion_commits_mode_transition(self):
        """approve_promotion flips mode = target_mode when target_mode is set in DB."""
        from src.strategies.promotion import approve_promotion

        conn, cur = _make_db()
        # Row with pending target_mode and gate_report_id already set by request_promotion
        row = _lifecycle_row(
            strategy_id="S1",
            mode="paper",
            target_mode="supervised_paper",
            gate_report_id="rpt-s1-2026",
            approved=False,
            promotion_blocked=False,
        )
        cur.fetchone.return_value = row

        approve_promotion(
            strategy_id="S1",
            approved_by="senior_operator",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any("update" in sql and "strategy_lifecycle" in sql for sql in executed_sqls), (
            "approve_promotion must UPDATE strategy_lifecycle to commit mode transition. "
            f"Executed SQLs: {executed_sqls}"
        )

    def test_approve_promotion_fails_when_no_pending_target_mode(self):
        """approve_promotion raises PromotionBlockedError when target_mode is NULL (no pending request)."""
        from src.strategies.promotion import approve_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", target_mode=None
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="no pending"):
            approve_promotion(
                strategy_id="S1",
                approved_by="senior_operator",
                db_conn=conn,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Transition policy
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitionPolicy:

    def test_live_promotion_blocked_when_global_live_disabled(self):
        """When NO_LIVE_PROMOTION is active, any transition to 'live' is blocked.

        The global no-live policy is checked before anything else.
        """
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1",
            mode="supervised_paper",
            promotion_blocked=False,
            gate_report_id=None,
        )
        cur.fetchone.return_value = row

        with patch("src.strategies.promotion.GLOBAL_LIVE_PROMOTION_ENABLED", False):
            with pytest.raises(PromotionBlockedError, match="live.*disabled|no.live|global"):
                request_promotion(
                    strategy_id="S1",
                    target_mode="live",
                    gate_report_id="rpt-s1-2026",
                    requested_by="operator",
                    db_conn=conn,
                )

    def test_skip_transition_blocked(self):
        """Cannot jump from 'research' directly to 'live' — must go through paper."""
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1",
            mode="research",
            promotion_blocked=False,
            gate_report_id=None,
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="skip|invalid transition|not allowed"):
            request_promotion(
                strategy_id="S1",
                target_mode="live",
                gate_report_id="rpt-s1-2026",
                requested_by="operator",
                db_conn=conn,
            )

    def test_demotion_always_allowed(self):
        """Demotion (supervised_paper → paper) requires no gate or approval."""
        from src.strategies.promotion import demote_strategy

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="supervised_paper", promotion_blocked=True
        )
        cur.fetchone.return_value = row

        # Must not raise even with promotion_blocked=True
        demote_strategy(
            strategy_id="S1",
            new_mode="paper",
            reason="drawdown exceeded threshold",
            demoted_by="risk_monitor",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any("update" in sql and "strategy_lifecycle" in sql for sql in executed_sqls)

    def test_demotion_to_disabled_always_allowed(self):
        """Any strategy can be disabled regardless of promotion_blocked or approved."""
        from src.strategies.promotion import demote_strategy

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S4", mode="paper", promotion_blocked=True
        )
        cur.fetchone.return_value = row

        # Must not raise
        demote_strategy(
            strategy_id="S4",
            new_mode="disabled",
            reason="circuit breaker triggered",
            demoted_by="auto_risk",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any("update" in sql for sql in executed_sqls)

    def test_promotion_to_same_mode_blocked(self):
        """Promoting to the current mode is a no-op error, not a silent pass."""
        from src.strategies.promotion import request_promotion, PromotionBlockedError

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", promotion_blocked=False, gate_report_id=None
        )
        cur.fetchone.return_value = row

        with pytest.raises(PromotionBlockedError, match="already|same mode|no transition"):
            request_promotion(
                strategy_id="S1",
                target_mode="paper",
                gate_report_id="rpt-s1-2026",
                requested_by="operator",
                db_conn=conn,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Audit log
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditLog:

    def test_promotion_request_writes_audit_row(self):
        """request_promotion inserts a row into strategy_lifecycle_audit."""
        from src.strategies.promotion import request_promotion

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1", mode="paper", promotion_blocked=False, gate_report_id=None
        )
        cur.fetchone.return_value = row

        request_promotion(
            strategy_id="S1",
            target_mode="supervised_paper",
            gate_report_id="rpt-s1-2026",
            requested_by="operator",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any(
            "insert" in sql and "strategy_lifecycle_audit" in sql
            for sql in executed_sqls
        ), (
            "request_promotion must insert an audit row into strategy_lifecycle_audit. "
            f"Executed: {executed_sqls}"
        )

    def test_approve_promotion_writes_audit_row(self):
        """approve_promotion inserts a row into strategy_lifecycle_audit with action='approved'."""
        from src.strategies.promotion import approve_promotion

        conn, cur = _make_db()
        row = _lifecycle_row(
            strategy_id="S1",
            mode="paper",
            target_mode="supervised_paper",
            gate_report_id="rpt-s1-2026",
            approved=False,
        )
        cur.fetchone.return_value = row

        approve_promotion(strategy_id="S1", approved_by="senior_operator", db_conn=conn)

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any(
            "insert" in sql and "strategy_lifecycle_audit" in sql
            for sql in executed_sqls
        ), (
            "approve_promotion must insert an audit row into strategy_lifecycle_audit. "
            f"Executed: {executed_sqls}"
        )

    def test_demotion_writes_audit_row(self):
        """demote_strategy inserts a row into strategy_lifecycle_audit."""
        from src.strategies.promotion import demote_strategy

        conn, cur = _make_db()
        row = _lifecycle_row(strategy_id="S1", mode="supervised_paper")
        cur.fetchone.return_value = row

        demote_strategy(
            strategy_id="S1",
            new_mode="paper",
            reason="manual reset",
            demoted_by="operator",
            db_conn=conn,
        )

        executed_sqls = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any(
            "insert" in sql and "strategy_lifecycle_audit" in sql
            for sql in executed_sqls
        ), (
            "demote_strategy must insert an audit row into strategy_lifecycle_audit. "
            f"Executed: {executed_sqls}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Operational approval check
# ─────────────────────────────────────────────────────────────────────────────

class TestOperationalApproval:

    def test_returns_false_when_approved_false(self):
        """Strategies with approved=False in DB are not operationally approved."""
        from src.strategies.promotion import is_strategy_operationally_approved

        conn, cur = _make_db()
        row = _lifecycle_row(strategy_id="S4", mode="paper", approved=False)
        cur.fetchone.return_value = row

        result = is_strategy_operationally_approved(strategy_id="S4", db_conn=conn)
        assert result is False, (
            "is_strategy_operationally_approved must return False when approved=False in DB."
        )

    def test_returns_true_when_approved_true(self):
        """Strategies with approved=True are operationally approved."""
        from src.strategies.promotion import is_strategy_operationally_approved

        conn, cur = _make_db()
        row = _lifecycle_row(strategy_id="S2", mode="disabled", approved=True)
        cur.fetchone.return_value = row

        result = is_strategy_operationally_approved(strategy_id="S2", db_conn=conn)
        assert result is True

    def test_returns_false_when_db_down_fail_closed(self):
        """When DB raises, is_strategy_operationally_approved returns False (fail-closed).

        A DB outage must NOT accidentally grant operational approval.
        """
        from src.strategies.promotion import is_strategy_operationally_approved

        conn = MagicMock()
        conn.cursor.side_effect = Exception("Connection refused")

        result = is_strategy_operationally_approved(strategy_id="S1", db_conn=conn)
        assert result is False, (
            "is_strategy_operationally_approved must fail-closed (return False) when DB is down. "
            "A DB outage must not silently grant operational approval."
        )

    def test_returns_false_when_no_row_in_db(self):
        """When strategy has no row in strategy_lifecycle, it is not approved."""
        from src.strategies.promotion import is_strategy_operationally_approved

        conn, cur = _make_db()
        cur.fetchone.return_value = None  # no row

        result = is_strategy_operationally_approved(strategy_id="S_UNKNOWN", db_conn=conn)
        assert result is False, (
            "is_strategy_operationally_approved must return False when strategy not in DB."
        )
