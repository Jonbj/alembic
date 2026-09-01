"""Point-in-time, append-only entry-intent events for S4 (#294)."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid5

from src.models.signals import SentimentResult
from src.strategies.s4.config import S4Config

_INTENT_NAMESPACE = UUID("08da204c-8061-5c53-a439-8f12b8202940")
_DECISION_SLOT_MINUTES = 15

REQUIRED_VERSION_COMPONENTS = frozenset({
    "source",
    "resolver",
    "model",
    "gate",
    "ranking",
    "sizing",
    "s1_collision",
    "policy",
})


def build_component_versions(
    *,
    config: S4Config,
    risk_config: dict[str, Any],
    code_version: str,
    config_hash: str,
    policy_version: str,
) -> dict[str, dict[str, Any]]:
    """Snapshot every material component named by the trial contract."""
    return {
        "source": {"version": "news-log:v3", "code_version": code_version},
        "resolver": {"version": "ticker-resolver:v1", "code_version": code_version},
        "model": {"version": "per-signal", "code_version": code_version},
        "gate": {
            "version": "s4-entry-gates:v1",
            "config_hash": config_hash,
            "active_feedback_threshold": None,
            "min_score": config.min_score,
            "min_confidence": config.min_confidence,
            "max_signal_age_hours": config.max_signal_age_hours,
        },
        "ranking": {
            "version": "score-descending:v1",
            "n_top": config.n_top,
            "min_stocks": config.min_stocks,
        },
        "sizing": {
            "version": "fixed-slot:v1" if config.fixed_slot_sizing else "redistributed:v1",
            "bucket_pct": config.bucket_pct,
            "fixed_slot_sizing": config.fixed_slot_sizing,
            "runtime_flag": bool(risk_config.get("s4_fixed_slot_sizing_enabled", True)),
        },
        "s1_collision": {
            "version": "merged-target+anti-pyramiding:v1",
            "code_version": code_version,
        },
        "policy": {
            "version": policy_version,
            "code_version": code_version,
            "config_hash": config_hash,
        },
    }


def build_runtime_component_versions(
    *, config: S4Config, risk_config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Resolve deployed code/config/policy versions without touching decisions."""
    root = Path(__file__).resolve().parents[3]
    files = (root / "config" / "trading.yaml", root / "config" / "s4_exit_trial.yaml")
    digest = hashlib.sha256()
    try:
        for path in files:
            digest.update(path.read_bytes())
        config_hash = digest.hexdigest()[:16]
    except OSError:
        config_hash = "unknown"

    code_version = os.environ.get("ALEMBIC_CODE_VERSION", "").strip()
    if not code_version:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=3,
            )
            code_version = result.stdout.strip() or "unknown"
        except Exception:
            code_version = "unknown"

    policy_version = "unknown"
    try:
        import yaml

        payload = yaml.safe_load(files[1].read_text()) or {}
        policy_version = f"s4-exit-trial:{payload.get('version', 'unknown')}"
    except Exception:
        pass

    return build_component_versions(
        config=config,
        risk_config=risk_config,
        code_version=code_version,
        config_hash=config_hash,
        policy_version=policy_version,
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decision_slot(value: datetime) -> datetime:
    value = _utc(value)
    anchored = value - timedelta(minutes=7)
    minute = anchored.minute - anchored.minute % _DECISION_SLOT_MINUTES
    return anchored.replace(minute=minute, second=0, microsecond=0) + timedelta(minutes=7)


def _signal_key(signal: SentimentResult) -> str:
    if signal.signal_id is not None:
        return f"signal:{signal.signal_id}"
    raw = "|".join((
        signal.symbol,
        _utc(signal.generated_at).isoformat(),
        signal.model_id,
        f"{signal.score:.12g}",
    ))
    return f"synthetic:{hashlib.sha256(raw.encode()).hexdigest()}"


def _causal_event_id(signal: SentimentResult) -> str:
    if signal.news_log_id is not None:
        return f"news:{signal.news_log_id}"
    if signal.content_hash:
        return f"content:{signal.content_hash}"
    return _signal_key(signal)


@dataclass(frozen=True)
class S4IntentEvent:
    event_id: str
    intent_id: str
    causal_event_id: str
    event_type: str
    occurred_at: datetime
    decision_slot: datetime
    symbol: str
    signal_id: int | None
    published_at: datetime | None
    first_seen_at: datetime | None
    model_generated_at: datetime
    decision_at: datetime
    rank: int | None
    competing_candidates: tuple[str, ...]
    s1_state: dict[str, Any]
    anti_pyramiding: bool | None
    reason_code: str
    is_tradable: bool | None
    versions: dict[str, Any]
    snapshot: dict[str, Any]
    missingness: dict[str, str]


@dataclass
class _IntentState:
    candidate: S4IntentEvent
    reason_code: str | None = None
    rank: int | None = None
    is_tradable: bool = False
    s1_state: dict[str, Any] | None = None
    anti_pyramiding: bool | None = None
    disposition_details: dict[str, Any] | None = None


class S4IntentLedger:
    """Build deterministic candidate/disposition events without mutating decisions."""

    def __init__(self, decision_at: datetime, component_versions: dict[str, Any]) -> None:
        missing = REQUIRED_VERSION_COMPONENTS - set(component_versions)
        if missing:
            raise ValueError(f"missing S4 intent version components: {sorted(missing)}")
        self.decision_at = _utc(decision_at)
        self.decision_slot = _decision_slot(decision_at)
        self.component_versions = component_versions
        self._states: dict[str, _IntentState] = {}
        self._disposition_component_updates: dict[str, dict[str, Any]] = {}

    def capture(
        self,
        signals: Iterable[SentimentResult],
        ranking_scores: dict[int, float] | None = None,
    ) -> list[S4IntentEvent]:
        """Append-only candidate events for every observed signal (#294, #401).

        Args:
            signals: signals observed in this decision cycle, before any
                downstream filter. ``signal.score`` is the raw sentiment score
                emitted by the worker; it is the field the contradiction
                guard (dossier) keys on and must stay stable.
            ranking_scores: optional per-signal ranking score (the value the
                ranker actually sees — typically ``raw_score × velocity_multiplier``).
                When supplied, it is persisted alongside ``score`` so the ledger
                row carries the exact key the ranker used to assign ``rank``
                (the field the rank can be reconstructed from). Absent means
                the caller did not compute it; this is declared in ``missingness``
                so the dossier knows it cannot audit this row.
        """
        signals = list(signals)
        competitors = tuple(sorted({signal.symbol for signal in signals}))
        ranking_scores = ranking_scores or {}
        created: list[S4IntentEvent] = []
        for signal in signals:
            key = _signal_key(signal)
            intent_id = str(uuid5(
                _INTENT_NAMESPACE,
                f"s4-entry|{self.decision_slot.isoformat()}|{key}",
            ))
            versions = {name: dict(value) for name, value in self.component_versions.items()}
            versions["source"].update({"name": signal.news_source})
            versions["resolver"].update({
                "method": signal.resolver_method or signal.extraction_method,
                "decision": signal.resolver_decision,
            })
            versions["model"].update({"model_id": signal.model_id})

            missingness: dict[str, str] = {}
            if versions["gate"].get("active_feedback_threshold") is None:
                missingness["active_feedback_threshold"] = (
                    "evaluated_after_candidate_capture"
                )
            for field, value in (
                ("content_hash", signal.content_hash),
                ("first_seen_at", signal.first_seen_at),
                ("published_at", signal.published_at),
            ):
                if value is None:
                    missingness[field] = "not_available_at_decision"
            if signal.resolver_decision is None or (
                signal.resolver_method is None and signal.extraction_method is None
            ):
                missingness["resolver"] = "not_available_at_decision"

            snapshot: dict[str, Any] = {
                "symbol": signal.symbol,
                "score": signal.score,
                "confidence": signal.confidence,
                "fallback_used": signal.fallback_used,
                "ensemble_std": signal.ensemble_std,
                "news_log_id": signal.news_log_id,
                "content_hash": signal.content_hash,
                "extraction_method": signal.extraction_method,
            }
            # #401: rank persistence must be reconstructable. Persist the
            # ranking score atomically with the candidate, NOT by re-reading
            # the signal store later. Keys on signal_id (when present) — that
            # is the only stable handle that survives velocity multipliers,
            # dedup, and any other in-flight mutation.
            if signal.signal_id is not None and signal.signal_id in ranking_scores:
                snapshot["ranking_score"] = float(ranking_scores[signal.signal_id])
            else:
                missingness["ranking_score"] = "not_recorded_at_capture"

            event = S4IntentEvent(
                event_id=str(uuid5(_INTENT_NAMESPACE, f"{intent_id}|candidate")),
                intent_id=intent_id,
                causal_event_id=_causal_event_id(signal),
                event_type="candidate",
                occurred_at=self.decision_at,
                decision_slot=self.decision_slot,
                symbol=signal.symbol,
                signal_id=signal.signal_id,
                published_at=_utc(signal.published_at) if signal.published_at else None,
                first_seen_at=_utc(signal.first_seen_at) if signal.first_seen_at else None,
                model_generated_at=_utc(signal.generated_at),
                decision_at=self.decision_at,
                rank=None,
                competing_candidates=competitors,
                s1_state={
                    "status": "missing",
                    "reason": "not_evaluated_before_rank",
                },
                anti_pyramiding=None,
                reason_code="CANDIDATE_OBSERVED",
                is_tradable=None,
                versions=versions,
                snapshot=snapshot,
                missingness=dict(sorted(missingness.items())),
            )
            self._states[key] = _IntentState(candidate=event)
            created.append(event)
        return created

    def set_disposition(
        self,
        *,
        signal_id: int,
        reason_code: str,
        rank: int | None = None,
        is_tradable: bool | None = None,
        s1_state: dict[str, Any] | None = None,
        anti_pyramiding: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        state = self._states.get(f"signal:{signal_id}")
        if state is None:
            return
        state.reason_code = reason_code
        if rank is not None:
            state.rank = rank
        if is_tradable is not None:
            state.is_tradable = is_tradable
        if s1_state is not None:
            state.s1_state = s1_state
        if anti_pyramiding is not None:
            state.anti_pyramiding = anti_pyramiding
        if details is not None:
            state.disposition_details = details

    @property
    def signal_ids_by_symbol(self) -> dict[str, tuple[int, ...]]:
        by_symbol: dict[str, list[int]] = {}
        for state in self._states.values():
            candidate = state.candidate
            if candidate.signal_id is not None:
                by_symbol.setdefault(candidate.symbol, []).append(candidate.signal_id)
        return {symbol: tuple(ids) for symbol, ids in by_symbol.items()}

    def set_s1_state(self, *, signal_id: int, s1_state: dict[str, Any]) -> None:
        state = self._states.get(f"signal:{signal_id}")
        if state is not None:
            state.s1_state = s1_state

    def update_component_for_disposition(
        self, component: str, **values: Any
    ) -> None:
        if component not in REQUIRED_VERSION_COMPONENTS:
            raise ValueError(f"unknown S4 intent version component: {component}")
        self._disposition_component_updates.setdefault(component, {}).update(values)

    def disposition_events(self, *, default_reason: str) -> list[S4IntentEvent]:
        events: list[S4IntentEvent] = []
        for state in self._states.values():
            candidate = state.candidate
            missingness = dict(candidate.missingness)
            s1_state = state.s1_state
            if s1_state is None:
                s1_state = {"status": "missing", "reason": "not_observed_at_disposition"}
                missingness["s1_state"] = "not_observed_at_disposition"
            snapshot = dict(candidate.snapshot)
            if state.disposition_details:
                snapshot["disposition"] = state.disposition_details
            versions = {name: dict(value) for name, value in candidate.versions.items()}
            for component, values in self._disposition_component_updates.items():
                versions[component].update(values)
            if versions["gate"].get("active_feedback_threshold") is not None:
                missingness.pop("active_feedback_threshold", None)
            if state.reason_code is None:
                missingness["reason_code"] = "not_classified_before_cycle_end"
            events.append(replace(
                candidate,
                event_id=str(uuid5(_INTENT_NAMESPACE, f"{candidate.intent_id}|disposition")),
                event_type="disposition",
                rank=state.rank,
                s1_state=s1_state,
                anti_pyramiding=state.anti_pyramiding,
                reason_code=state.reason_code or default_reason,
                is_tradable=state.is_tradable,
                versions=versions,
                snapshot=snapshot,
                missingness=dict(sorted(missingness.items())),
            ))
        return events
