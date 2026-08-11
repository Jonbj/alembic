"""#134 — F8 (feedback:regime_scale) is RETIRED.

The serial-dependence premise that an equity-curve de-risk rule needs was
falsified on the per-DAY unit (S1 +0.065, S4 +0.017 — 'no detectable
dependence'), and the mechanism itself was independently broken: a trigger
reset the same `last_adjustment` clock the decay branch reads, so a sleeve
that re-triggered more often than the decay window could only escape via a
win streak — which a losing sleeve does not have. The decision (issue #134,
2026-08-07) is to retire F8, not re-tune it.

Production status at the time of the decision: `apply_regime_scale: false`
in config/trading.yaml — already shadow-only, already inert on the live
portfolio path. This is therefore a removal of code without behavior
change, and does not consume a deroga against the observation freeze (#171).

Scope of removal: the `regime_scale` lever of the loss-feedback mechanism.
The `entry_threshold` lever (under #191) is INDEPENDENT and stays.

These tests act as a guard: F8 must NOT be re-introduced. Re-introduction
requires a fresh design + premise retest (the per-DAY scatter must actually
show dependence), not a quiet re-add to trading.yaml or a resurrection of
the helpers it relied on.

Lifecycle: docs/F8_LIFECYCLE_HISTORY_2026-08-10.md.
"""
from __future__ import annotations

import importlib

import pytest


class TestF8RedisGone:
    """The Redis keys feedback:regime_scale[:S*] are no longer written or read."""

    def test_no_set_feedback_regime_scale_method(self):
        """RedisStore.set_feedback_regime_scale must be gone — F8 is retired."""
        from src.store.redis_store import RedisStore

        assert not hasattr(RedisStore, "set_feedback_regime_scale"), (
            "RedisStore.set_feedback_regime_scale must be removed — F8 is retired. "
            "Re-introduction requires a fresh design + premise retest (#134)."
        )

    def test_no_get_feedback_regime_scale_method(self):
        """RedisStore.get_feedback_regime_scale must be gone too."""
        from src.store.redis_store import RedisStore

        assert not hasattr(RedisStore, "get_feedback_regime_scale"), (
            "RedisStore.get_feedback_regime_scale must be removed — F8 is retired. "
            "If the consumer is gone, the producer must be gone too (#134)."
        )


class TestF8PerformanceWorkerGone:
    """The performance worker no longer touches the regime_scale lever."""

    def test_no_load_feedback_regime_scale_in_execution(self):
        """execution._load_feedback_regime_scale must be gone."""
        from src.workers import execution

        assert not hasattr(execution, "_load_feedback_regime_scale"), (
            "execution._load_feedback_regime_scale must be removed — F8 is retired. "
            "regime_mult *= feedback_scale was the only call site of the regime_scale "
            "lever in the execution path (#134)."
        )

    def test_performance_config_has_no_regime_scale_keys(self):
        """_load_loss_feedback_config must not return regime_scale config keys."""
        from src.workers.performance import _load_loss_feedback_config

        cfg = _load_loss_feedback_config()
        # The F8 lever is fully gone — none of its config keys may leak back via
        # a default or a loaded value.
        for forbidden in (
            "regime_scale_factor",
            "regime_min_scale",
            "apply_regime_scale",
        ):
            assert forbidden not in cfg, (
                f"_load_loss_feedback_config returns {forbidden!r} — F8 is retired, "
                "this key must not exist in the config. Remove the default or the "
                "loader (#134)."
            )

    def test_trading_yaml_has_no_f8_keys(self):
        """config/trading.yaml must not carry F8 shadow-only fallbacks."""
        from pathlib import Path

        import yaml

        yaml_path = Path(__file__).resolve().parents[1] / "config" / "trading.yaml"
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f) or {}
        fb = cfg.get("loss_feedback", {})
        for forbidden in (
            "regime_scale_factor",
            "regime_min_scale",
            "apply_regime_scale",
        ):
            assert forbidden not in fb, (
                f"config/trading.yaml loss_feedback still has {forbidden!r} — "
                f"F8 is retired, this key must be removed (#134)."
            )


class TestF8OrchestratorGateGone:
    """The orchestrator's _scale_gate and feedback_shadow plumbing are gone."""

    def test_no_scale_gate_in_orchestrator(self):
        """PortfolioOrchestrator._scale_gate is the F8 apply-gate helper."""
        from src.portfolio import orchestrator

        assert not hasattr(orchestrator, "_scale_gate"), (
            "PortfolioOrchestrator._scale_gate must be removed — F8 is retired. "
            "The scale gate existed only to gate the regime_scale lever (#134)."
        )

    def test_no_feedback_shadow_field_in_cycle_result(self):
        """CycleResult.feedback_shadow recorded F8's would-be delta per cycle."""
        from src.portfolio.orchestrator import CycleResult

        from dataclasses import fields
        names = {f.name for f in fields(CycleResult)}
        assert "feedback_shadow" not in names, (
            "CycleResult.feedback_shadow must be removed — F8 is retired. "
            "The shadow existed only to log would-be regime_scale effects (#134)."
        )


class TestF8SchedulerGone:
    """The portfolio scheduler no longer reads/writes F8."""

    def test_no_read_feedback_regime_scales(self):
        """portfolio_scheduler._read_feedback_regime_scales is F8-only."""
        from src.workers import portfolio_scheduler

        assert not hasattr(portfolio_scheduler, "_read_feedback_regime_scales"), (
            "portfolio_scheduler._read_feedback_regime_scales must be removed — "
            "F8 is retired. The helper existed only to read feedback:regime_scale:S* "
            "and pass the dict to the orchestrator (#134)."
        )

    def test_no_build_f8_shadow_rows(self):
        """portfolio_scheduler._build_f8_shadow_rows is F8-only."""
        from src.workers import portfolio_scheduler

        assert not hasattr(portfolio_scheduler, "_build_f8_shadow_rows"), (
            "portfolio_scheduler._build_f8_shadow_rows must be removed — "
            "F8 is retired. The helper converted CycleResult.feedback_shadow into "
            "f8_regime_scale_shadow rows, and the writer is gone too (#134)."
        )


class TestF8PgStoreGone:
    """The pg_store writer for the F8 shadow table is gone."""

    def test_no_insert_f8_shadow(self):
        """PostgreSQLStore.insert_f8_shadow is the only writer of the shadow table."""
        from src.store import pg_store

        assert not hasattr(pg_store, "insert_f8_shadow"), (
            "PostgreSQLStore.insert_f8_shadow must be removed — F8 is retired. "
            "The f8_regime_scale_shadow table has no other writer (#134)."
        )


class TestF8LifecycleHistoryExists:
    """The F8 lifecycle history doc exists and is the canonical reference."""

    def test_lifecycle_history_doc_present(self):
        from pathlib import Path

        docs_root = Path(__file__).resolve().parents[1] / "docs"
        candidates = list(docs_root.glob("F8_LIFECYCLE_HISTORY_*.md"))
        assert candidates, (
            "docs/F8_LIFECYCLE_HISTORY_*.md must exist — the lifecycle record is "
            "the post-removal reference, matching the S7 model "
            "(docs/S7_LIFECYCLE_HISTORY_2026-07-15.md)."
        )
        # Pin the date so the file is findable for future readers.
        text = candidates[0].read_text()
        assert "F8" in text and "ritirato" in text.lower() or "ritirata" in text.lower(), (
            "F8 lifecycle doc must declare F8 ritirato/a (cf. S7 doc wording)."
        )
