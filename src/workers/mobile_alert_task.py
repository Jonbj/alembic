"""Mobile alert worker: evaluate monitoring state and dispatch FCM notifications.

The worker is intentionally narrow: it observes the coherent mobile snapshot,
updates server-owned incidents, and drains the transactional notification outbox.
It never sends financial detail through FCM.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg

from src.api.dependencies import init_asyncpg_pool
from src.mobile_monitoring.builder import MobileSnapshotBuilder
from src.mobile_monitoring.incidents import IncidentStore
from src.mobile_monitoring.models import EventCategory, EventKind, Severity
from src.notifications.fcm import build_fcm_payload, get_fcm_adapter
from src.workers.celery_app import app

logger = logging.getLogger(__name__)


class MobileAlertEvaluator:
    """Map a coherent snapshot to expected active incident fingerprints."""

    def __init__(self, store: IncidentStore, builder: MobileSnapshotBuilder):
        self.store = store
        self.builder = builder

    async def evaluate(self) -> None:
        try:
            snapshot = await self.builder.build_snapshot()
        except Exception as exc:
            logger.warning("Mobile alert evaluation: could not build snapshot: %s", exc)
            await self._expect_critical(
                fingerprint="system:snapshot_unavailable",
                title="Snapshot non disponibile",
                summary="L'aggregatore di stato mobile non ha potuto assemblare uno snapshot.",
                details={"reason": str(exc)},
            )
            return

        expected: set[str] = set()

        # Critical safety: kill-switch.
        if snapshot.operational.state == "blocked" and snapshot.operational.primary_reason == "killswitch_active":
            fp = "system:killswitch"
            expected.add(fp)
            await self.store.record_observation(
                fingerprint=fp,
                kind=EventKind.ALERT_INCIDENT,
                category=EventCategory.CRITICAL,
                severity=Severity.CRITICAL,
                title="Killswitch attivo",
                summary="Il sistema è in halt: nessun ciclo di trading verrà avviato.",
                entity_type="killswitch",
                expected=True,
            )

        # Unknown mode (should never happen with valid config, but catch misconfiguration).
        if snapshot.operational.mode not in ("paper", "live"):
            fp = "system:mode:unknown"
            expected.add(fp)
            await self.store.record_observation(
                fingerprint=fp,
                kind=EventKind.ALERT_INCIDENT,
                category=EventCategory.CRITICAL,
                severity=Severity.CRITICAL,
                title="Modalità operativa sconosciuta",
                summary="La modalità di esecuzione non è né paper né live.",
                entity_type="mode",
                expected=True,
            )

        # Broker/data health derived from the snapshot pipeline.
        broker = snapshot.pipeline.get("broker")
        if broker and broker.status == "stale":
            fp = "pipeline:broker_stale"
            expected.add(fp)
            await self.store.record_observation(
                fingerprint=fp,
                kind=EventKind.ALERT_INCIDENT,
                category=EventCategory.TRADING,
                severity=Severity.CRITICAL,
                title="Dati broker non aggiornati",
                summary="Lo snapshot broker è vecchio oltre la soglia massima.",
                details={"age_seconds": broker.age_seconds},
                entity_type="broker",
                expected=True,
            )
        elif broker and broker.status == "aging":
            fp = "pipeline:broker_aging"
            expected.add(fp)
            await self.store.record_observation(
                fingerprint=fp,
                kind=EventKind.ALERT_INCIDENT,
                category=EventCategory.TRADING,
                severity=Severity.WARNING,
                title="Dati broker invecchiati",
                summary="Lo snapshot broker sta invecchiando durante la finestra operativa.",
                details={"age_seconds": broker.age_seconds},
                entity_type="broker",
                expected=True,
            )

        # Pipeline freshness only when activity is expected.
        if snapshot.operational.pipeline_expected:
            cycle = snapshot.pipeline.get("portfolio_cycle")
            if cycle and cycle.status == "stale":
                fp = "pipeline:portfolio_cycle_late"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.TRADING,
                    severity=Severity.CRITICAL,
                    title="Ciclo di portafoglio in ritardo",
                    summary="Nessun ciclo completato oltre la soglia massima durante la finestra operativa.",
                    details={"age_seconds": cycle.age_seconds},
                    entity_type="portfolio_cycle",
                    expected=True,
                )
            elif cycle and cycle.status == "aging":
                fp = "pipeline:portfolio_cycle_late"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.TRADING,
                    severity=Severity.WARNING,
                    title="Ciclo di portafoglio in ritardo",
                    summary="Nessun ciclo completato entro il budget di freschezza.",
                    details={"age_seconds": cycle.age_seconds},
                    entity_type="portfolio_cycle",
                    expected=True,
                )

            signal = snapshot.pipeline.get("signal")
            if signal and signal.status == "stale":
                fp = "pipeline:signal_stale"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.TRADING,
                    severity=Severity.WARNING,
                    title="Segnali sentiment in ritardo",
                    summary="Nessun segnale sentiment prodotto entro il budget di freschezza.",
                    details={"age_seconds": signal.age_seconds},
                    entity_type="signal_pipeline",
                    expected=True,
                )

        # Risk limits.
        portfolio = snapshot.portfolio
        mode = snapshot.operational.mode
        if portfolio.current_drawdown is not None and portfolio.drawdown_limit is not None:
            if portfolio.current_drawdown >= portfolio.drawdown_limit:
                fp = f"risk:drawdown:{mode}"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.CRITICAL,
                    severity=Severity.CRITICAL,
                    title="Limite di drawdown raggiunto",
                    summary="Il drawdown corrente ha superato il limite configurato.",
                    details={
                        "current_drawdown": portfolio.current_drawdown,
                        "drawdown_limit": portfolio.drawdown_limit,
                    },
                    entity_type="risk",
                    expected=True,
                )

        if portfolio.gross_exposure is not None and portfolio.gross_exposure_limit is not None:
            if portfolio.gross_exposure >= portfolio.gross_exposure_limit:
                fp = f"risk:exposure:{mode}"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.CRITICAL,
                    severity=Severity.CRITICAL,
                    title="Limite di esposizione raggiunto",
                    summary="L'esposizione lorda ha superato il limite configurato.",
                    details={
                        "gross_exposure": portfolio.gross_exposure,
                        "gross_exposure_limit": portfolio.gross_exposure_limit,
                    },
                    entity_type="risk",
                    expected=True,
                )

        # Infrastructure degradations from the snapshot.
        for deg in snapshot.degradations:
            if deg.component in ("database", "redis", "killswitch", "market_clock"):
                fp = f"system:{deg.component}"
                expected.add(fp)
                await self.store.record_observation(
                    fingerprint=fp,
                    kind=EventKind.ALERT_INCIDENT,
                    category=EventCategory.SYSTEM,
                    severity=deg.severity or Severity.WARNING,
                    title=f"Degradazione {deg.component}",
                    summary=deg.reason,
                    entity_type=deg.component,
                    expected=True,
                )

        # Recover incidents whose conditions are no longer present.
        active = await self.store.list_active_fingerprints()
        for fp in active - expected:
            await self.store.record_observation(
                fingerprint=fp,
                kind=EventKind.ALERT_INCIDENT,
                category=EventCategory.SYSTEM,
                severity=Severity.INFO,
                title="Condizione rientrata",
                summary="La condizione allarmante non è più presente.",
                expected=False,
            )

    async def _expect_critical(
        self,
        *,
        fingerprint: str,
        title: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        await self.store.record_observation(
            fingerprint=fingerprint,
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.CRITICAL,
            severity=Severity.CRITICAL,
            title=title,
            summary=summary,
            details=details,
            expected=True,
        )


async def record_order_event(
    pool: asyncpg.Pool,
    *,
    kind: str,
    symbol: str,
    order_id: str,
    reason: str | None = None,
) -> None:
    """Record a terminal order incident (rejected/cancelled) from the order path.

    This is intentionally a narrow seam: callers pass safe, bounded fields only.
    """
    store = IncidentStore(pool)
    fingerprint = f"order:{order_id}:{kind}"
    severity = Severity.CRITICAL if kind == "rejected" else Severity.WARNING
    title = f"Ordine {kind}"
    summary = f"Ordine {kind} per {symbol}" + (f": {reason}" if reason else "")
    await store.record_observation(
        fingerprint=fingerprint,
        kind=EventKind.ORDER,
        category=EventCategory.TRADING,
        severity=severity,
        title=title,
        summary=summary,
        details={"symbol": symbol, "reason": reason},
        entity_type="order",
        entity_id=order_id,
        expected=False,
    )


async def dispatch_due_notifications(pool: asyncpg.Pool, limit: int = 100) -> None:
    """Drain the notification outbox using the configured FCM adapter."""
    store = IncidentStore(pool)
    adapter = get_fcm_adapter()
    rows = await store.list_due_deliveries(limit=limit)
    for row in rows:
        payload = build_fcm_payload(
            event_id=str(row["event_id"]),
            transition=row["transition"],
            severity=row["severity"],
        )
        # TODO: read FCM token from monitor_devices once a token column is added.
        # For the MVP, send to firebase_installation_id if present; FakeFcmAdapter accepts any string.
        device_token = "dummy"
        try:
            result = await adapter.send(device_token=device_token, payload=payload)
        except Exception as exc:
            logger.warning("FCM dispatch failed for delivery %s: %s", row["id"], exc)
            result = None

        if result is None:
            await _schedule_retry(store, row["id"], attempt_count=row["attempt_count"] + 1)
        elif result.accepted:
            await store.record_delivery_attempt(
                row["id"],
                provider_message_id=result.provider_message_id,
            )
        else:
            if result.terminal:
                await store.record_delivery_attempt(
                    row["id"],
                    failed_at=datetime.now(timezone.utc),
                    error_code=result.error_code,
                )
                await store.disable_device_push(row["device_id"])
            else:
                await _schedule_retry(store, row["id"], attempt_count=row["attempt_count"] + 1)


async def _schedule_retry(store: IncidentStore, delivery_id: int, attempt_count: int) -> None:
    backoff = min(2 ** attempt_count * 60, 3600)
    next_attempt = datetime.now(timezone.utc) + timedelta(seconds=backoff)
    await store.record_delivery_attempt(
        delivery_id,
        failed_at=datetime.now(timezone.utc),
        error_code="retry",
        next_attempt_at=next_attempt,
    )


@app.task(name="src.workers.mobile_alert_task.run_mobile_alert_evaluation")
def run_mobile_alert_evaluation() -> None:
    """Celery task entrypoint: evaluate incidents and dispatch notifications."""
    import asyncio

    async def _run() -> None:
        pool = await init_asyncpg_pool()
        builder = MobileSnapshotBuilder(pool=pool)
        store = IncidentStore(pool=pool)
        evaluator = MobileAlertEvaluator(store=store, builder=builder)
        await evaluator.evaluate()
        await dispatch_due_notifications(pool=pool)

    asyncio.run(_run())

