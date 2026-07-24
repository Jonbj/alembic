"""Worker seam tests for coherent mobile read-model publication."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

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
from src.mobile_monitoring.read_model import MobileReadBundle
from src.workers.mobile_monitor_task import (
    publish_mobile_read_model,
    run_mobile_monitor_snapshot,
)


def _bundle(as_of: datetime) -> MobileReadBundle:
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
                state=OperationalState.OPERATIONAL,
                mode="paper",
                market_phase="open",
                pipeline_expected=True,
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
    monkeypatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 1, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    builder = MagicMock()
    builder.build_bundle = AsyncMock(return_value=bundle)
    read_model = MagicMock()
    pool = MagicMock()
    persist = AsyncMock()
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
async def test_worker_persists_every_five_minutes(monkeypatch) -> None:
    as_of = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    builder = MagicMock()
    builder.build_bundle = AsyncMock(return_value=bundle)
    read_model = MagicMock()
    pool = MagicMock()
    persist = AsyncMock()
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
    monkeypatch,
) -> None:
    as_of = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    bundle = _bundle(as_of)
    bundle.snapshot.portfolio.nav = None
    builder = MagicMock()
    builder.build_bundle = AsyncMock(return_value=bundle)
    persist = AsyncMock()
    monkeypatch.setattr(
        "src.workers.mobile_monitor_task._persist_snapshot",
        persist,
    )

    await publish_mobile_read_model(
        builder=builder,
        read_model=MagicMock(),
        pool=MagicMock(),
        as_of=as_of,
    )

    persist.assert_not_awaited()


def test_celery_entrypoint_returns_observable_status(monkeypatch) -> None:
    run = MagicMock(side_effect=lambda awaitable: awaitable.close())
    monkeypatch.setattr("src.workers.mobile_monitor_task.run_async", run)

    result = run_mobile_monitor_snapshot.run()

    run.assert_called_once()
    assert result == {"status": "ok", "processed": 1}
