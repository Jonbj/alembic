"""Shared fixtures for API tests — overrides require_api_key for testing."""
import os

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "require_auth: test checks auth behavior without override")


# Ensure a known test API key is set BEFORE importing the app
os.environ["ADMIN_API_KEY"] = "test-api-key-for-testing-only-12345678"

from src.api.auth import require_api_key
from src.api.main import app


@pytest.fixture(autouse=True)
def _override_api_key(request):
    """Override require_api_key dependency to always pass with the test key.
    
    Tests marked with @pytest.mark.require_auth will NOT get the override,
    allowing them to test authentication behavior.
    """
    if request.node.get_closest_marker("require_auth"):
        app.dependency_overrides.pop(require_api_key, None)
        yield
        app.dependency_overrides.pop(require_api_key, None)
    else:
        app.dependency_overrides[require_api_key] = lambda: "test-api-key-for-testing-only-12345678"
        yield
        app.dependency_overrides.pop(require_api_key, None)