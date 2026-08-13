"""Shared fixtures for API tests — overrides require_api_key for testing."""
import os

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "require_auth: test checks auth behavior without override"
    )
    config.addinivalue_line(
        "markers", "rate_limit: test exercises the real rate-limit dependency"
    )


# Ensure a known test API key is set BEFORE importing the app
os.environ["ADMIN_API_KEY"] = "test-api-key-for-testing-only-12345678"

# JWT test credentials — bcrypt hash of "secret"
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD_HASH", "$2b$12$i6qSOhZRTLWbWoSTukGsw.p2y0hEJEKmEqjHGwjuv3dXqB2Gy2WHO")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only-not-for-prod")
os.environ.setdefault("JWT_EXPIRE_MINUTES", "60")

os.environ.setdefault("MOBILE_TOKEN_PEPPER", "test-pepper")

from src.api.auth import require_api_key  # noqa: E402
from src.api.main import app  # noqa: E402
from src.api.rate_limit import (  # noqa: E402
    get_admin_action_rate_limiter,
    get_admin_login_rate_limiter,
    require_rate_limited_admin,
)
from src.rate_limit import RateLimitResult  # noqa: E402


class _AllowRateLimiter:
    """Keep unrelated API tests independent from shared Redis counters."""

    def check(self, **dimensions: str) -> RateLimitResult:
        del dimensions
        return RateLimitResult(allowed=True, retry_after_seconds=0)


@pytest.fixture(autouse=True)
def _override_api_key(request):
    """Override require_api_key dependency to always pass with the test key.

    Tests marked with @pytest.mark.require_auth will NOT get the override,
    allowing them to test authentication behavior.
    """
    exercises_rate_limit = request.node.get_closest_marker("rate_limit") is not None
    if not exercises_rate_limit:
        app.dependency_overrides[get_admin_login_rate_limiter] = _AllowRateLimiter
        app.dependency_overrides[get_admin_action_rate_limiter] = _AllowRateLimiter

    if request.node.get_closest_marker("require_auth"):
        app.dependency_overrides.pop(require_api_key, None)
        app.dependency_overrides.pop(require_rate_limited_admin, None)
        yield
        app.dependency_overrides.pop(require_api_key, None)
        app.dependency_overrides.pop(require_rate_limited_admin, None)
    else:
        app.dependency_overrides[require_api_key] = lambda: (
            "test-api-key-for-testing-only-12345678"
        )
        app.dependency_overrides[require_rate_limited_admin] = lambda: (
            "test-api-key-for-testing-only-12345678"
        )
        yield
        app.dependency_overrides.pop(require_api_key, None)
        app.dependency_overrides.pop(require_rate_limited_admin, None)

    app.dependency_overrides.pop(get_admin_login_rate_limiter, None)
    app.dependency_overrides.pop(get_admin_action_rate_limiter, None)
