"""Approved example payloads for /api/mobile/v1 contract tests.

These fixtures mirror the JSON examples in
`docs/superpowers/specs/2026-07-21-android-monitoring-app-design.md`.
"""

from __future__ import annotations

from uuid import uuid4

SNAPSHOT_PAYLOAD = {
    "contract_version": 1,
    "as_of": "2026-07-21T13:42:15Z",
    "data_age_seconds": 32,
    "currency": "USD",
    "min_supported_app_version": "1.0.0",
    "latest_app_version": "1.0.0",
    "operational": {
        "state": "operational",
        "primary_reason": None,
        "mode": "paper",
        "market_phase": "open",
        "pipeline_expected": True,
        "next_expected_activity_at": "2026-07-21T13:52:00Z",
        "active_incident_count": 0,
    },
    "portfolio": {
        "nav": 110307.36,
        "nav_change_today": -115.60,
        "nav_return_today": -0.001047,
        "realized_pnl_today": -18.46,
        "unrealized_pnl": -97.14,
        "cash": 76998.12,
        "cash_pct": 0.69799,
        "gross_exposure": 0.30201,
        "gross_exposure_limit": 0.50,
        "current_drawdown": 0.0145,
        "drawdown_limit": 0.05,
        "open_positions": 7,
        "source": "alpaca_paper",
    },
    "pipeline": {
        "database": {"status": "fresh", "age_seconds": 0},
        "redis": {"status": "fresh", "age_seconds": 0, "writeable": True},
        "signal": {"status": "fresh", "age_seconds": 480},
        "portfolio_cycle": {"status": "fresh", "age_seconds": 300},
        "broker": {"status": "fresh", "age_seconds": 32},
    },
    "strategies": [
        {"id": "S1", "mode": "supervised_paper", "allocation_pct": 0.90, "approved": True},
        {"id": "S4", "mode": "paper", "allocation_pct": 0.10, "approved": True},
    ],
    "degradations": [],
}


PERFORMANCE_PAYLOAD = {
    "contract_version": 1,
    "as_of": "2026-07-21T13:42:15Z",
    "data_age_seconds": 32,
    "currency": "USD",
    "min_supported_app_version": "1.0.0",
    "latest_app_version": "1.0.0",
    "period": "1m",
    "period_start": "2026-06-20T00:00:00Z",
    "period_end": "2026-07-21T13:42:15Z",
    "summary": {
        "nav_start": 109850.00,
        "nav_end": 110307.36,
        "nav_change": 457.36,
        "portfolio_return": 0.004164,
        "realized_pnl": 132.40,
        "max_drawdown": 0.0182,
        "avg_gross_exposure": 0.287,
        "spy_return": 0.021,
        "benchmark_return": 0.006027,
        "alpha": -0.001863,
    },
    "points": [
        {
            "at": "2026-06-20T20:00:00Z",
            "nav": 109850.00,
            "drawdown": 0.0,
            "benchmark_nav": 109850.00,
        }
    ],
    "degradations": [],
}


POSITIONS_PAYLOAD = {
    "contract_version": 1,
    "as_of": "2026-07-21T13:42:15Z",
    "data_age_seconds": 32,
    "currency": "USD",
    "min_supported_app_version": "1.0.0",
    "latest_app_version": "1.0.0",
    "summary": {
        "count": 1,
        "market_value": 6234.10,
        "unrealized_pnl": -77.88,
        "gross_exposure": 0.0565,
    },
    "items": [
        {
            "symbol": "MSFT",
            "qty": 12.3456,
            "avg_entry_price": 511.22,
            "current_price": 505.00,
            "market_value": 6234.10,
            "position_weight": 0.0565,
            "unrealized_pnl": -77.88,
            "unrealized_return": -0.01234,
            "entry_time": "2026-07-20T15:22:00Z",
        }
    ],
    "degradations": [],
}


EVENTS_PAYLOAD = {
    "contract_version": 1,
    "as_of": "2026-07-21T13:42:15Z",
    "data_age_seconds": 32,
    "currency": "USD",
    "min_supported_app_version": "1.0.0",
    "latest_app_version": "1.0.0",
    "items": [
        {
            "id": str(uuid4()),
            "kind": "alert_incident",
            "category": "system",
            "severity": "critical",
            "status": "open",
            "occurred_at": "2026-07-21T13:40:00Z",
            "updated_at": "2026-07-21T13:42:00Z",
            "resolved_at": None,
            "title": "Ciclo di portafoglio in ritardo",
            "summary": "Nessun ciclo completato da 18 minuti durante la finestra operativa.",
            "entity": {"type": "portfolio_cycle", "id": None},
            "measure": {"value": 1080, "unit": "seconds", "threshold": 900},
            "history": [{"state": "opened", "at": "2026-07-21T13:40:00Z"}],
        }
    ],
    "next_cursor": None,
}


LOGIN_REQUEST_PAYLOAD = {
    "username": "monitor-stefano",
    "password": "test-password",
    "device": {
        "installation_id": str(uuid4()),
        "name": "Pixel 9",
        "app_version": "1.0.0",
    },
}


DEVICE_REGISTRATION_PAYLOAD = {
    "installation_id": str(uuid4()),
    "firebase_installation_id": "opaque-fid",
    "name": "Pixel 9",
    "app_version": "1.0.0",
    "push_enabled": True,
}


ERROR_PAYLOAD = {
    "error": {
        "code": "snapshot_unavailable",
        "message": "Monitoring snapshot is temporarily unavailable.",
        "request_id": str(uuid4()),
        "retryable": True,
        "details": {},
    }
}
