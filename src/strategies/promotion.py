"""Promotion Gate Logic for strategy lifecycle transitions.

Enforces the ordered state machine:
    research → paper → supervised_paper → live
    any → disabled  (always allowed — circuit breaker)
    any → lower     (demotion always allowed)

Promotions require ALL of:
  1. promotion_blocked = FALSE on the current lifecycle row
  2. gate_report_id is not None (evidence of a passing backtest)
  3. GLOBAL_LIVE_PROMOTION_ENABLED = True when target is 'live'
  4. Sequential transition (no mode skipping)

Demotions (to a less risky mode or disabled) are always allowed.
Every transition is written to strategy_lifecycle_audit (immutable log).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# Fail-closed gate: any path that cannot confirm this is True must block live
# promotion.  Never set True without PO sign-off + P2-05 closure + Kimi P2 Audit.
# Tests may patch this directly via monkeypatch.
GLOBAL_LIVE_PROMOTION_ENABLED: bool = False

# Ordered risk levels. Higher index = more risk.
_MODE_ORDER: list[str] = ["disabled", "research", "paper", "supervised_paper", "live"]


class PromotionBlockedError(Exception):
    """Raised when a promotion request is rejected by the gate logic."""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def request_promotion(
    strategy_id: str,
    target_mode: str,
    gate_report_id: str | None,
    requested_by: str,
    db_conn,
) -> None:
    """Request a mode promotion for a strategy.

    Validates all prerequisites and writes (target_mode, gate_report_id) to
    strategy_lifecycle. Does NOT commit the transition — call approve_promotion()
    for that.

    Raises:
        PromotionBlockedError: if any prerequisite is not met.
    """
    row = _fetch_lifecycle_row(strategy_id, db_conn)

    current_mode: str = row["mode"]
    promotion_blocked: bool = bool(row["promotion_blocked"])

    # 1. No-op check
    if target_mode == current_mode:
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': already in mode '{current_mode}' — no transition needed."
        )

    # 2. Must be a promotion (target riskier than current), not a demotion
    if not _is_promotion(current_mode, target_mode):
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': transition {current_mode!r} → {target_mode!r} is a "
            "demotion or invalid — use demote_strategy() for downgrades."
        )

    # 3. Sequential transition only (no skipping) — graph constraint, checked before policy
    if not _is_sequential(current_mode, target_mode):
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': skip transition {current_mode!r} → {target_mode!r} is "
            "not allowed. Promotions must be sequential "
            f"(next allowed: {_next_mode(current_mode)!r})."
        )

    # 4. Global live-promotion policy
    if target_mode == "live" and not GLOBAL_LIVE_PROMOTION_ENABLED:
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': live promotion disabled globally "
            "(GLOBAL_LIVE_PROMOTION_ENABLED=False). "
            "No strategy may be promoted to live until the global policy is enabled."
        )

    # 5. promotion_blocked
    if promotion_blocked:
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': promotion_blocked=True. "
            "Remove the block (clear promotion_blocked in strategy_lifecycle and YAML) "
            "before requesting a promotion."
        )

    # 6. gate_report_id required
    if not gate_report_id:
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': gate_report_id is required for promotion. "
            "Run the strategy's backtest gate script and provide the report ID."
        )

    # All checks passed — write pending promotion to DB
    with db_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE strategy_lifecycle
               SET target_mode     = %s,
                   gate_report_id  = %s,
                   promoted_by     = %s,
                   updated_at      = NOW()
             WHERE strategy_id     = %s
            """,
            (target_mode, gate_report_id, requested_by, strategy_id),
        )
        _write_audit(
            cur=cur,
            strategy_id=strategy_id,
            from_mode=current_mode,
            to_mode=target_mode,
            action="requested",
            actor=requested_by,
            reason=f"gate_report_id={gate_report_id}",
            gate_report_id=gate_report_id,
        )
    db_conn.commit()
    log.info(
        "Strategy %s: promotion REQUESTED %s → %s by %s (gate_report=%s)",
        strategy_id, current_mode, target_mode, requested_by, gate_report_id,
    )


def approve_promotion(
    strategy_id: str,
    approved_by: str,
    db_conn,
) -> None:
    """Approve a pending promotion request and commit the mode transition.

    Reads the pending target_mode from strategy_lifecycle. The target_mode
    must have been set by a prior call to request_promotion().

    Raises:
        PromotionBlockedError: if no pending request exists (target_mode is NULL).
    """
    row = _fetch_lifecycle_row(strategy_id, db_conn)

    current_mode: str = row["mode"]
    target_mode = row["target_mode"]
    gate_report_id = row["gate_report_id"]

    if not target_mode:
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': no pending promotion request found "
            "(target_mode is NULL). Call request_promotion() first."
        )

    with db_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE strategy_lifecycle
               SET mode            = %s,
                   target_mode     = NULL,
                   approved        = TRUE,
                   promoted_at     = NOW(),
                   updated_at      = NOW()
             WHERE strategy_id     = %s
            """,
            (target_mode, strategy_id),
        )
        _write_audit(
            cur=cur,
            strategy_id=strategy_id,
            from_mode=current_mode,
            to_mode=target_mode,
            action="approved",
            actor=approved_by,
            reason=f"gate_report_id={gate_report_id}",
            gate_report_id=gate_report_id,
        )
    db_conn.commit()
    log.info(
        "Strategy %s: promotion APPROVED %s → %s by %s",
        strategy_id, current_mode, target_mode, approved_by,
    )


def demote_strategy(
    strategy_id: str,
    new_mode: str,
    reason: str,
    demoted_by: str,
    db_conn,
) -> None:
    """Demote a strategy to a less risky mode or to disabled.

    Demotion is always allowed — no gate, no approval, no promotion_blocked check.
    Useful for circuit-breaker actions and risk-monitor auto-demotions.

    Raises:
        PromotionBlockedError: if new_mode is not actually a downgrade.
    """
    row = _fetch_lifecycle_row(strategy_id, db_conn)
    current_mode: str = row["mode"]

    if new_mode != "disabled" and not _is_demotion(current_mode, new_mode):
        raise PromotionBlockedError(
            f"Strategy '{strategy_id}': {current_mode!r} → {new_mode!r} is not a demotion. "
            "Use request_promotion() for upgrades."
        )

    with db_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE strategy_lifecycle
               SET mode        = %s,
                   target_mode = NULL,
                   approved    = FALSE,
                   updated_at  = NOW()
             WHERE strategy_id = %s
            """,
            (new_mode, strategy_id),
        )
        _write_audit(
            cur=cur,
            strategy_id=strategy_id,
            from_mode=current_mode,
            to_mode=new_mode,
            action="demoted",
            actor=demoted_by,
            reason=reason,
            gate_report_id=None,
        )
    db_conn.commit()
    log.info(
        "Strategy %s: DEMOTED %s → %s by %s (%s)",
        strategy_id, current_mode, new_mode, demoted_by, reason,
    )


def is_strategy_operationally_approved(strategy_id: str, db_conn) -> bool:
    """Return True if the strategy has approved=True in strategy_lifecycle.

    Fail-closed: returns False on any DB error. A DB outage must never
    silently grant operational approval.
    """
    try:
        row = _fetch_lifecycle_row(strategy_id, db_conn)
        if row is None:
            return False
        return bool(row["approved"])
    except Exception as exc:
        log.warning(
            "is_strategy_operationally_approved(%s): DB error (%s) — returning False (fail-closed)",
            strategy_id, exc,
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_lifecycle_row(strategy_id: str, db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT strategy_id, mode, target_mode, gate_report_id,
                   approved, promotion_blocked
              FROM strategy_lifecycle
             WHERE strategy_id = %s
            """,
            (strategy_id,),
        )
        return cur.fetchone()


def _mode_rank(mode: str) -> int:
    try:
        return _MODE_ORDER.index(mode)
    except ValueError:
        return -1


def _is_promotion(from_mode: str, to_mode: str) -> bool:
    return _mode_rank(to_mode) > _mode_rank(from_mode)


def _is_demotion(from_mode: str, to_mode: str) -> bool:
    return _mode_rank(to_mode) < _mode_rank(from_mode)


def _is_sequential(from_mode: str, to_mode: str) -> bool:
    """True only when to_mode is exactly one step above from_mode."""
    return _mode_rank(to_mode) == _mode_rank(from_mode) + 1


def _next_mode(mode: str) -> str | None:
    rank = _mode_rank(mode)
    if rank < 0 or rank >= len(_MODE_ORDER) - 1:
        return None
    return _MODE_ORDER[rank + 1]


def _write_audit(
    cur,
    strategy_id: str,
    from_mode: str,
    to_mode: str,
    action: str,
    actor: str,
    reason: str | None,
    gate_report_id: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO strategy_lifecycle_audit
               (strategy_id, from_mode, to_mode, action, actor, reason, gate_report_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (strategy_id, from_mode, to_mode, action, actor, reason, gate_report_id),
    )
