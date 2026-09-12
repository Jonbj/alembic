"""I target transition sono visibili dall'API portfolio (#468)."""

import os
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")

from src.api.deps import get_pg_store
from src.api.main import app


@pytest.mark.asyncio
async def test_cycle_history_espone_ribilanciamenti_e_pesi_zero() -> None:
    store = MagicMock()
    store.get_portfolio_cycle_history.return_value = [
        {
            "timestamp": "2026-09-01T14:07:00+00:00",
            "strategies_run": ["S1", "S4"],
            "orders_count": 45,
            "constraints_fired": [],
            "final_orders": [],
            "rebalanced_strategies": ["S1", "S4"],
            "zero_weight_symbols": {"S1": ["ARM", "GE", "MMM", "TXN"]},
        }
    ]
    app.dependency_overrides[get_pg_store] = lambda: store
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/portfolio/cycle-history")
    finally:
        app.dependency_overrides.pop(get_pg_store, None)

    assert response.status_code == 200
    row = response.json()[0]
    assert row["rebalanced_strategies"] == ["S1", "S4"]
    assert row["zero_weight_symbols"] == {
        "S1": ["ARM", "GE", "MMM", "TXN"]
    }
