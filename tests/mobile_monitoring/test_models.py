"""Contract tests for the /api/mobile/v1 Pydantic models."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.api.mobile_models import (
    DeviceRegistrationRequest,
    DeviceResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    UserInfo,
)
from src.mobile_monitoring.models import (
    EventsResponse,
    OperationalState,
    PerformanceResponse,
    Period,
    PortfolioBlock,
    PositionsResponse,
    Severity,
    SnapshotResponse,
    StrategyRow,
)
from tests.fixtures import mobile_monitoring as fixtures


class TestMobileContractValidation:
    """Every approved example payload must validate against its model."""

    def test_snapshot_example(self):
        model = SnapshotResponse.model_validate(fixtures.SNAPSHOT_PAYLOAD)
        assert model.operational.state == OperationalState.OPERATIONAL
        assert model.portfolio.nav == Decimal("110307.36")
        assert model.pipeline["broker"].age_seconds == 32
        assert len(model.strategies) == 2

    def test_performance_example(self):
        model = PerformanceResponse.model_validate(fixtures.PERFORMANCE_PAYLOAD)
        assert model.period == "1m"
        assert model.summary.alpha == pytest.approx(-0.001863)
        assert len(model.points) == 1
        assert model.points[0].drawdown == 0.0

    def test_positions_example(self):
        model = PositionsResponse.model_validate(fixtures.POSITIONS_PAYLOAD)
        assert model.summary.count == 1
        assert model.items[0].symbol == "MSFT"
        assert float(model.items[0].qty) == pytest.approx(12.3456)

    def test_events_example(self):
        model = EventsResponse.model_validate(fixtures.EVENTS_PAYLOAD)
        assert len(model.items) == 1
        event = model.items[0]
        assert event.severity == Severity.CRITICAL
        assert event.measure.value == pytest.approx(1080)
        assert event.entity.id is None

    def test_login_request_example(self):
        model = LoginRequest.model_validate(fixtures.LOGIN_REQUEST_PAYLOAD)
        assert model.username == "monitor-stefano"
        assert model.device.name == "Pixel 9"

    def test_device_registration_example(self):
        model = DeviceRegistrationRequest.model_validate(
            fixtures.DEVICE_REGISTRATION_PAYLOAD
        )
        assert model.push_enabled is True

    def test_error_example(self):
        from src.mobile_monitoring.models import MobileErrorResponse

        model = MobileErrorResponse.model_validate(fixtures.ERROR_PAYLOAD)
        assert model.error.code == "snapshot_unavailable"
        assert model.error.retryable is True


class TestMobileContractRejection:
    """Invalid or unsafe values are rejected at the model boundary."""

    def test_invalid_operational_state(self):
        payload = deepcopy(fixtures.SNAPSHOT_PAYLOAD)
        payload["operational"]["state"] = "panic"
        with pytest.raises(ValidationError):
            SnapshotResponse.model_validate(payload)

    def test_allocation_pct_above_one(self):
        with pytest.raises(ValidationError):
            StrategyRow(id="S1", mode="paper", allocation_pct=1.5, approved=True)

    def test_negative_data_age_rejected(self):
        payload = deepcopy(fixtures.SNAPSHOT_PAYLOAD)
        payload["data_age_seconds"] = -1
        with pytest.raises(ValidationError):
            SnapshotResponse.model_validate(payload)

    def test_invalid_period_enum(self):
        # Period is a StrEnum; invalid values raise ValueError.
        with pytest.raises(ValueError):
            Period("2y")

    def test_unknown_event_category_rejected(self):
        payload = deepcopy(fixtures.EVENTS_PAYLOAD)
        payload["items"][0]["category"] = "marketing"
        with pytest.raises(ValidationError):
            EventsResponse.model_validate(payload)

    def test_missing_required_field(self):
        payload = deepcopy(fixtures.SNAPSHOT_PAYLOAD)
        del payload["operational"]["active_incident_count"]
        with pytest.raises(ValidationError):
            SnapshotResponse.model_validate(payload)


class TestNullabilityAndSafety:
    """Unavailable financial values remain nullable; zero is not injected."""

    def test_null_nav_is_not_zero(self):
        payload = deepcopy(fixtures.SNAPSHOT_PAYLOAD)
        payload["portfolio"]["nav"] = None
        model = SnapshotResponse.model_validate(payload)
        assert model.portfolio.nav is None

    def test_portfolio_block_all_nullable(self):
        model = PortfolioBlock()
        assert model.nav is None
        assert model.cash_pct is None
        assert model.open_positions is None

    def test_login_response_enforces_positive_expiry(self):
        from datetime import datetime, timezone
        from uuid import uuid4

        with pytest.raises(ValidationError):
            LoginResponse(
                access_token="a",
                expires_in=0,
                refresh_token="r",
                refresh_expires_at=datetime.now(timezone.utc),
                user=UserInfo(id=uuid4(), username="x"),
                device_id=uuid4(),
            )


class TestAuthRequestShapes:
    """Authentication and device request models forbid unknown fields."""

    def test_login_request_rejects_extra_field(self):
        payload = deepcopy(fixtures.LOGIN_REQUEST_PAYLOAD)
        payload["remember_me"] = True
        with pytest.raises(ValidationError):
            LoginRequest.model_validate(payload)

    def test_refresh_request_requires_token(self):
        with pytest.raises(ValidationError):
            RefreshRequest.model_validate({})

    def test_logout_request_requires_token(self):
        with pytest.raises(ValidationError):
            LogoutRequest.model_validate({})


class TestDeviceResponse:
    """Device response round-trips through its model."""

    def test_device_response_round_trip(self):
        from datetime import datetime, timezone
        from uuid import uuid4

        device_id = uuid4()
        model = DeviceResponse(
            id=device_id,
            installation_id=str(uuid4()),
            name="Pixel 9",
            app_version="1.0.0",
            push_enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        assert model.id == device_id
