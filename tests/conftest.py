# tests/conftest.py
import os

import pytest

# Set env vars before any src.* import so src.config reads correct values
# regardless of test collection order.
os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")
os.environ.setdefault("DATABASE_URL", "postgresql://localhost:5432/test_db")
# JWT_SECRET_KEY must be set for the API lifespan to start (P0-02 fail-fast).
# Tests use a fixed test secret; production must supply a real one via env.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-do-not-use-in-production-000")
# Auth credentials needed for TestClient login in test_auth_jwt.py.
os.environ.setdefault("ADMIN_USERNAME", "admin")
# bcrypt hash of "secret" — for test login only.
os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    "$2b$12$i6qSOhZRTLWbWoSTukGsw.p2y0hEJEKmEqjHGwjuv3dXqB2Gy2WHO",
)


@pytest.fixture
def sample_news_text():
    return "Apple Inc. reported record quarterly earnings of $1.2B, beating analyst estimates."


@pytest.fixture
def sample_scores():
    return [0.6, 0.5, -0.2, 0.8, -0.1, 0.4, 0.7, -0.3, 0.2, 0.5]


@pytest.fixture
def sample_returns():
    return [0.02, 0.01, -0.015, 0.03, -0.005, 0.01, 0.025, -0.02, 0.005, 0.015]
