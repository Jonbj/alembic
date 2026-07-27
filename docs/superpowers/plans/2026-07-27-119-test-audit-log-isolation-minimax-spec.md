# #119 — Test suite writes real audit_log rows on prod Postgres — Execution Spec

> **For the executing agent (minimax):** You have NO prior context on this repo. Read this whole document once, then execute the single task exactly as written, on ONE git branch with ONE PR that closes #119. Do NOT improvise beyond this spec. A human reviewer reviews the PR before merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based paper-trading system. This is a **test-only** fix: ZERO production code changes, ZERO production risk. You edit only test files.

**Goal:** Close GitHub issue #119. Four API tests override `get_redis_store` and the YAML config path but forget to override the `get_pg_store` FastAPI dependency. The killswitch and config-update endpoints also depend on `get_pg_store` for their audit-log write, so the un-overridden dependency instantiates a **real** `PostgreSQLStore` that connects to the environment's `DATABASE_URL` — the live Postgres behind paper trading — and every local suite run writes synthetic `KILLSWITCH_ACTIVATE` / config-`UPDATE` rows into the real `audit_log`. Fix: override `get_pg_store` with a mock in the affected tests, matching the pattern already used in `tests/api/test_admin_killswitch_token.py`.

**Scope note:** Only the immediate/targeted fix (mock the dependency). Out of scope: giving the test env a separate `DATABASE_URL` (the structural fix), and cleaning the already-written synthetic `audit_log` rows (a prod-data change needing operator sign-off).

**Tech stack:** Python 3, FastAPI + `AsyncClient`/`TestClient`, pytest (run via `uv run pytest`). No production code, no migrations, no config.

**Branch:** `fix/119-test-audit-log-isolation`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v`; `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **Order of work:** apply the dependency-override fix, then add the verification assertions/guard test. Do NOT run the affected tests in their pre-fix state — a pre-fix run connects to the real Postgres and writes to the live `audit_log` (the exact bug). Add the override AND the assertion together, then run once (green).
3. **One branch + one PR** (name above). PR body must contain `closes #119` and a 2-3 line summary.
4. **Touch only these files:** `tests/api/test_api.py`, `tests/api/test_config_routes.py`. Nothing else — no production code.
5. **Never delete/weaken an existing test.** You are ADDING dependency overrides + assertions to existing tests and one new guard test.
6. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`). Known pre-existing failures (NOT yours): `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and a flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve`.
7. **Do not deploy, do not restart containers, do not push to `main`.** PR only.

---

## Root cause (verified — from the issue)

`tests/api/test_api.py` (`test_killswitch_with_valid_key`, `test_killswitch_requires_api_key`) and `tests/api/test_config_routes.py` (its POST-`/api/config` tests) override `get_redis_store` / `require_api_key` / the YAML path but NOT `get_pg_store`. The endpoints `src/api/routes/admin.py::activate_killswitch` and `src/api/routes/config_routes.py::update_config` also depend on `pg: Annotated[PostgreSQLStore, Depends(get_pg_store)]` for the audit log. Un-overridden, that dependency builds a real `PostgreSQLStore()` → connects to the real `DATABASE_URL` → writes synthetic rows to the live `audit_log`. The reference pattern that does it right is `tests/api/test_admin_killswitch_token.py` (overrides both `get_redis_store` and `get_pg_store`).

## Files
- Modify: `tests/api/test_api.py`
- Modify: `tests/api/test_config_routes.py`

## Steps

- [ ] **Step 1 — `test_config_routes.py`: override `get_pg_store` in the autouse fixture.**

The file has an autouse fixture that already overrides auth for every config test:

```python
@pytest.fixture(autouse=True)
def _override_auth():
    """Override auth for all config route tests."""
    app.dependency_overrides[require_api_key] = lambda: "test-key"
    yield
    app.dependency_overrides.pop(require_api_key, None)
```

First add the imports. Change:

```python
from unittest.mock import mock_open, patch
```

to:

```python
from unittest.mock import MagicMock, mock_open, patch

from src.api.deps import get_pg_store
```

Then replace the whole `_override_auth` fixture with (also overriding `get_pg_store` so no config test instantiates a real store):

```python
@pytest.fixture(autouse=True)
def _override_auth():
    """Override auth AND the pg store for all config route tests.

    #119: update_config also depends on get_pg_store for its audit-log write;
    without this override a real PostgreSQLStore connects to the live DATABASE_URL
    and pollutes the production audit_log on every suite run.
    """
    pg_mock = MagicMock()
    app.dependency_overrides[require_api_key] = lambda: "test-key"
    app.dependency_overrides[get_pg_store] = lambda: pg_mock
    yield pg_mock
    app.dependency_overrides.pop(require_api_key, None)
    app.dependency_overrides.pop(get_pg_store, None)
```

- [ ] **Step 2 — `test_config_routes.py`: assert the mock is used in one success test.** To make the override verifiable, add a `pg audit` assertion to the deep-merge test. Find `def test_post_config_deep_merges_nested_dict(tmp_path):` and change its signature and add one assertion at the end:

Change:

```python
def test_post_config_deep_merges_nested_dict(tmp_path):
```

to:

```python
def test_post_config_deep_merges_nested_dict(tmp_path, _override_auth):
```

and at the very end of that test (after the existing `assert "max_position_pct: 0.2" in content`), add:

```python
    # #119: the audit-log write went to the injected mock, not a real store.
    _override_auth.write_audit_log.assert_called()
```

(`_override_auth` is the fixture value — the `pg_mock` it yields.)

- [ ] **Step 3 — `test_api.py`: add imports.** At the top of `tests/api/test_api.py`, find:

```python
from src.api.main import app, get_redis_store
```

and add these two lines right after it:

```python
from src.api.deps import get_pg_store
from unittest.mock import MagicMock
```

- [ ] **Step 4 — `test_api.py`: override `get_pg_store` in the two killswitch tests.** Replace `test_killswitch_requires_api_key` with:

```python
@pytest.mark.asyncio
@pytest.mark.require_auth
async def test_killswitch_requires_api_key(mock_redis_store):
    """Test POST /api/admin/killswitch requires valid API key."""
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    app.dependency_overrides[get_pg_store] = lambda: MagicMock()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 403
    app.dependency_overrides.pop(get_redis_store, None)
    app.dependency_overrides.pop(get_pg_store, None)
```

Replace `test_killswitch_with_valid_key` with:

```python
@pytest.mark.asyncio
async def test_killswitch_with_valid_key(mock_redis_store):
    """Test POST /api/admin/killswitch with valid API key activates killswitch."""
    pg_mock = MagicMock()
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    app.dependency_overrides[get_pg_store] = lambda: pg_mock
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/admin/killswitch")
    assert resp.status_code == 200
    data = resp.json()
    assert data["killswitch"] == "activated"
    assert data["mode"] == "halted"
    # #119: the audit-log write went to the injected mock, not a real store.
    pg_mock.write_audit_log.assert_called()
    app.dependency_overrides.pop(get_redis_store, None)
    app.dependency_overrides.pop(get_pg_store, None)
```

- [ ] **Step 5 — `test_api.py`: add a regression guard test.** Append this test to `tests/api/test_api.py` (it proves the endpoint never instantiates a real `PostgreSQLStore` when the dependency is overridden):

```python
@pytest.mark.asyncio
async def test_killswitch_never_instantiates_real_pg_store(monkeypatch, mock_redis_store):
    """#119: with get_pg_store overridden, the killswitch endpoint must use the
    injected mock and never construct a real PostgreSQLStore (which would connect
    to DATABASE_URL and write to the live audit_log)."""
    import src.store.pg_store as _pgs

    def _boom(self, *args, **kwargs):
        raise AssertionError("real PostgreSQLStore was instantiated (#119)")

    monkeypatch.setattr(_pgs.PostgreSQLStore, "__init__", _boom)

    pg_mock = MagicMock()
    app.dependency_overrides[get_redis_store] = lambda: mock_redis_store
    app.dependency_overrides[get_pg_store] = lambda: pg_mock
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/api/admin/killswitch")
    finally:
        app.dependency_overrides.pop(get_redis_store, None)
        app.dependency_overrides.pop(get_pg_store, None)

    assert resp.status_code == 200
    pg_mock.write_audit_log.assert_called()
```

- [ ] **Step 6 — Run the affected files, confirm green (and that the mock is exercised).**

Run: `uv run pytest tests/api/test_api.py tests/api/test_config_routes.py -v`
Expected: PASS — including the new `write_audit_log.assert_called()` assertions (which prove the override is in effect) and the guard test (which proves no real store is built).

- [ ] **Step 7 — Commit.**

```bash
git add tests/api/test_api.py tests/api/test_config_routes.py
git commit -m "fix(#119): mock get_pg_store in killswitch/config API tests

The killswitch and config-update endpoints depend on get_pg_store for their
audit-log write; four tests overrode get_redis_store but not get_pg_store, so a
real PostgreSQLStore connected to DATABASE_URL and wrote synthetic rows to the
live audit_log on every suite run. Override get_pg_store with a mock (matching
test_admin_killswitch_token.py) + a guard test that no real store is built.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 8 — Full suite + PR.** `uv run pytest -q` (baseline-identical failures only), then open the PR with `closes #119`.

---

## Hand-back checklist (for the human reviewer)

- Verify the two killswitch tests and the config autouse fixture now override `get_pg_store`, and the success paths assert `write_audit_log` on the mock (so the override can't silently regress).
- Confirm zero production files changed (test-only).
- Note out-of-scope items retained from the issue: the structural fix (separate test `DATABASE_URL`) and cleaning the already-written synthetic `audit_log` rows (operator decision).
