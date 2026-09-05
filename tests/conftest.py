# tests/conftest.py
import contextlib
import os
import re
from urllib.parse import urlsplit

import pytest

# Set env vars before any src.* import so src.config reads correct values
# regardless of test collection order.
os.environ.setdefault("ADMIN_API_KEY", "test-api-key-for-testing-only-12345678")
os.environ.setdefault("DATABASE_URL", "postgresql://trading:trading@localhost:5432/test_db")
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
os.environ.setdefault("MOBILE_TOKEN_PEPPER", "test-pepper")


_TEST_DATABASE_NAME_RE = re.compile(
    r"(?:^|[_-])(?:test|tests|testing|pytest)(?:[_-]|$)", re.IGNORECASE
)


def pytest_configure(config):
    database_url = os.environ["DATABASE_URL"]
    parsed_url = urlsplit(database_url)
    database_name = parsed_url.path.lstrip("/")
    # CI provisions this legacy-named database from scratch.  Limit the exception
    # to a loopback service on a GitHub-hosted runner, never a local/shared server.
    github_ephemeral_db = (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if _TEST_DATABASE_NAME_RE.search(database_name) or github_ephemeral_db:
        return

    raise pytest.UsageError(
        f"Refusing to run tests against non-test database {database_name!r}. "
        "Set DATABASE_URL to a dedicated database whose name contains a "
        "standalone test token (for example 'test_db')."
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


@pytest.fixture
def approved_strategy():
    """Context-manager factory: force strategy_lifecycle.approved=TRUE for a
    strategy id against the real DATABASE_URL, restoring the prior value on exit.

    _run_cycle_inner's approval gate (src/workers/portfolio_scheduler.py,
    _filter_approved_strategies) queries the real DB and is not covered by the
    registry/Alpaca mocks tests otherwise use. Migration 025 seeds S1/S4 as
    approved=FALSE on a freshly migrated Postgres (e.g. a clean CI run), which
    trips `reason=no_approved_strategies` before market-clock/account checks
    downstream ever execute — masking exactly the behavior those tests assert
    on. Tests exercising those downstream checks need this fixture.
    """
    import psycopg2

    @contextlib.contextmanager
    def _ctx(strategy_id: str = "S1"):
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT approved FROM strategy_lifecycle WHERE strategy_id = %s",
                    (strategy_id,),
                )
                row = cur.fetchone()
                prior = row[0] if row else None
                if row is None:
                    cur.execute(
                        "INSERT INTO strategy_lifecycle (strategy_id, approved, promoted_by) "
                        "VALUES (%s, TRUE, 'test-fixture')",
                        (strategy_id,),
                    )
                else:
                    cur.execute(
                        "UPDATE strategy_lifecycle SET approved = TRUE WHERE strategy_id = %s",
                        (strategy_id,),
                    )
                conn.commit()
            yield
        finally:
            with conn.cursor() as cur:
                if prior is None:
                    cur.execute(
                        "DELETE FROM strategy_lifecycle WHERE strategy_id = %s",
                        (strategy_id,),
                    )
                else:
                    cur.execute(
                        "UPDATE strategy_lifecycle SET approved = %s WHERE strategy_id = %s",
                        (prior, strategy_id),
                    )
                conn.commit()
            conn.close()

    return _ctx
