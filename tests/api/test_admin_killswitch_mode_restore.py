"""Regression tests for restoring the operating mode after a kill-switch halt."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.api.routes.admin import KillswitchRequest, activate_killswitch, deactivate_killswitch
from src.store.redis_store import RedisStore


class _MemoryRedis:
    """Small Redis double covering the commands used by the kill-switch flow."""

    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def get(self, key: str) -> object | None:
        return self.data.get(key)

    def set(self, key: str, value: object) -> "_MemoryRedis":
        self.data[key] = value
        return self

    def setex(self, key: str, _ttl: int, value: object) -> "_MemoryRedis":
        return self.set(key, value)

    def expire(self, _key: str, _ttl: int) -> bool:
        return True

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            deleted += key in self.data
            self.data.pop(key, None)
        return deleted

    def pipeline(self) -> "_MemoryRedis":
        return self

    def execute(self) -> list[object]:
        return []


@pytest.mark.asyncio
async def test_killswitch_deactivation_restores_mode_active_before_halt() -> None:
    redis = _MemoryRedis()
    store = RedisStore(redis_client=redis)
    pg = MagicMock()
    store.set_mode("semi_auto")

    await activate_killswitch(
        store=store,
        pg=pg,
        _="api_key",
        req=KillswitchRequest(reason="test halt"),
    )

    old_activation = datetime.now(timezone.utc) - timedelta(seconds=300)
    redis.set(
        "system:halted_by_operator_reason",
        '{"reason": "test halt", "activated_at": "'
        + old_activation.isoformat()
        + '"}',
    )
    redis.set("ks:recovery_token", "valid_token")

    result = await deactivate_killswitch(
        store=store,
        pg=pg,
        _="api_key",
        confirm_token="valid_token",
    )

    assert result == {"killswitch": "deactivated", "mode": "semi_auto"}
    assert store.get_mode() == "semi_auto"

