"""Worker seam tests for coherent mobile read-model publication."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from src.mobile_monitoring.builder import MobileSnapshotBuilder
from src.mobile_monitoring.models import (
    Freshness,
    OperationalBlock,
    OperationalState,
    PipelineComponent,
    PortfolioBlock,
    PositionsResponse,
    PositionsSummary,
    SnapshotResponse,
)
from src.mobile_monitoring.read_model import MobileReadBundle, MobileReadModelStore
from src.workers.mobile_monitor_task import (
    _persist_snapshot,
    publish_mobile_read_model,
    run_mobile_monitor_snapshot,
)


def _bundle(
    as_of: datetime,
    *,
    state: OperationalState = OperationalState.OPERATIONAL,
    pipeline_expected: bool = True,
) -> MobileReadBundle:
    snapshot_id = uuid4()
    return MobileReadBundle(
        snapshot=SnapshotResponse(
            snapshot_id=snapshot_id,
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version="1.0.0",
            latest_app_version="1.0.0",
            operational=OperationalBlock(
                state=state,
                mode="paper",
                market_phase="open",
                pipeline_expected=pipeline_expected,
                active_incident_count=0,
            ),
            portfolio=PortfolioBlock(nav=100),
            pipeline={
                "broker": PipelineComponent(
                    status=Freshness.FRESH,
                    age_seconds=0,
                )
            },
            strategies=[],
            degradations=[],
        ),
        positions=PositionsResponse(
            snapshot_id=snapshot_id,
            as_of=as_of,
            data_age_seconds=0,
            currency="USD",
            min_supported_app_version="1.0.0",
            latest_app_version="1.0.0",
            summary=PositionsSummary(count=0),
            items=[],
        ),
    )


@pytest.mark.asyncio
async def test_worker_publishes_one_coherent_bundle_without_persisting_off_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 1, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_bundle = AsyncMock(return_value=bundle)
    read_model = MagicMock(spec=MobileReadModelStore)
    read_model.load.return_value = bundle
    pool = MagicMock(spec=asyncpg.Pool)
    persist = AsyncMock(spec=_persist_snapshot)
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    result = await publish_mobile_read_model(
        builder=builder,
        read_model=read_model,
        pool=pool,
        as_of=as_of,
    )

    assert result == bundle
    builder.build_bundle.assert_awaited_once_with(as_of=as_of)
    read_model.save.assert_called_once_with(bundle)
    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_persists_every_five_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_bundle = AsyncMock(return_value=bundle)
    read_model = MagicMock(spec=MobileReadModelStore)
    read_model.load.return_value = bundle
    pool = MagicMock(spec=asyncpg.Pool)
    persist = AsyncMock(spec=_persist_snapshot)
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    await publish_mobile_read_model(
        builder=builder,
        read_model=read_model,
        pool=pool,
        as_of=as_of,
    )

    persist.assert_awaited_once_with(pool, bundle)


@pytest.mark.asyncio
async def test_worker_does_not_persist_fake_nav_when_broker_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    bundle.snapshot.portfolio.nav = None
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_bundle = AsyncMock(return_value=bundle)
    read_model = MagicMock(spec=MobileReadModelStore)
    read_model.load.return_value = bundle
    pool = MagicMock(spec=asyncpg.Pool)
    persist = AsyncMock(spec=_persist_snapshot)
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    await publish_mobile_read_model(
        builder=builder,
        read_model=read_model,
        pool=pool,
        as_of=as_of,
    )

    persist.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_persists_material_state_transition_off_cadence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 1, tzinfo=timezone.utc)
    previous = _bundle(as_of, state=OperationalState.OPERATIONAL)
    blocked = _bundle(as_of, state=OperationalState.BLOCKED)
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_bundle = AsyncMock(return_value=blocked)
    read_model = MagicMock(spec=MobileReadModelStore)
    read_model.load.return_value = previous
    pool = MagicMock(spec=asyncpg.Pool)
    persist = AsyncMock(spec=_persist_snapshot)
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    await publish_mobile_read_model(
        builder=builder,
        read_model=read_model,
        pool=pool,
        as_of=as_of,
    )

    persist.assert_awaited_once_with(pool, blocked)


@pytest.mark.asyncio
async def test_worker_does_not_persist_off_hours_cadence_without_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    as_of = datetime(2026, 7, 23, 22, 5, tzinfo=timezone.utc)
    paused = _bundle(
        as_of,
        state=OperationalState.PAUSED,
        pipeline_expected=False,
    )
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_bundle = AsyncMock(return_value=paused)
    read_model = MagicMock(spec=MobileReadModelStore)
    read_model.load.return_value = paused
    pool = MagicMock(spec=asyncpg.Pool)
    persist = AsyncMock(spec=_persist_snapshot)
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    await publish_mobile_read_model(
        builder=builder,
        read_model=read_model,
        pool=pool,
        as_of=as_of,
    )

    persist.assert_not_awaited()


def test_celery_entrypoint_returns_observable_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = MagicMock(
        spec=lambda awaitable: None,
        side_effect=lambda awaitable: awaitable.close(),
    )
    monkeypatch.setattr("src.workers.mobile_monitor_task.run_async", run)

    result = run_mobile_monitor_snapshot.run()

    run.assert_called_once()
    assert result == {"status": "ok", "processed": 1}
