# Auto-Apply Weights with Guardrails — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `check_and_apply_weights` Celery task that auto-applies weekly weight suggestions when VIX, IC variance, and weight delta guardrails all pass; freezes and alerts via Telegram otherwise.

**Architecture:** `run_weekly_weights()` chains `check_and_apply_weights()` with a 5s countdown after storing the suggestion. The new task reads the suggestion from Redis, evaluates four guardrails in sequence (G1: enabled flag, G2: VIX via FRED→Redis cache, G3: IC variance from `purified_icir`, G4: weight delta vs current), and either applies or freezes. Both outcomes write to `weight_update_log` and send a Telegram notification.

**Tech Stack:** FastAPI, Celery, Redis (redis-py), psycopg2, httpx (FRED API), pytest, unittest.mock

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `migrations/003_extend_source_check.sql` | Create | Extend `source` CHECK to include `auto_apply`, `freeze` |
| `src/config.py` | Modify | Add `AUTO_APPLY_*` Pydantic fields + `FRED_API_KEY` |
| `config/workers.yaml` | Modify | Add `auto_apply:` block for documentation |
| `src/connectors/macro.py` | Create | `fetch_vix_from_fred()` — synchronous httpx call |
| `src/store/redis_store.py` | Modify | Add `get_vix_cached()` + `set_vix_cached()` |
| `src/notifications/telegram.py` | Modify | Add `format_auto_apply_message()` + `format_freeze_message()` |
| `src/workers/performance.py` | Modify | Add `check_and_apply_weights()` task + `_get_vix()` helper + chain in `run_weekly_weights()` |
| `tests/connectors/test_macro.py` | Create | Tests for `fetch_vix_from_fred()` |
| `tests/test_redis_store.py` | Modify | Add `TestVixCache` |
| `tests/notifications/test_telegram.py` | Create | Tests for new Telegram formatters |
| `tests/workers/test_performance_worker.py` | Modify | Add `TestCheckAndApplyWeights` (8 tests) |

---

## Task 1: SQL Migration — Extend source CHECK constraint

**Files:**
- Create: `migrations/003_extend_source_check.sql`

- [x] **Step 1: Write the migration**

Create `migrations/003_extend_source_check.sql`:

```sql
-- Migration 003: extend weight_update_log.source to include auto_apply and freeze
-- Safe to run on existing data — only changes the constraint definition.

ALTER TABLE weight_update_log
  DROP CONSTRAINT weight_update_log_source_check;

ALTER TABLE weight_update_log
  ADD CONSTRAINT weight_update_log_source_check
  CHECK (source IN ('suggestion', 'override', 'expired', 'auto_apply', 'freeze'));
```

- [x] **Step 2: Verify SQL syntax**

Run: `psql $DATABASE_URL -f migrations/003_extend_source_check.sql`

Expected: No errors. Skip if `DATABASE_URL` is not set locally.

- [x] **Step 3: Commit**

```bash
git add migrations/003_extend_source_check.sql
git commit -m "feat: extend weight_update_log source CHECK for auto_apply and freeze"
```

---

## Task 2: Config — AUTO_APPLY fields

**Files:**
- Modify: `src/config.py`
- Modify: `config/workers.yaml`

- [x] **Step 1: Add fields to Config**

In `src/config.py`, inside the `Config` class after the `MAX_CONSECUTIVE_FALLBACKS` field and before the validators, add:

```python
    # FRED API
    FRED_API_KEY: str = Field(
        default_factory=lambda: os.environ.get("FRED_API_KEY", "")
    )

    # Auto-apply ensemble weights guardrails
    AUTO_APPLY_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_ENABLED", "true").lower() == "true"
    )
    AUTO_APPLY_VIX_THRESHOLD: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_VIX_THRESHOLD", "30.0"))
    )
    AUTO_APPLY_IC_VARIANCE_THRESHOLD: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_IC_VARIANCE_THRESHOLD", "0.15"))
    )
    AUTO_APPLY_WEIGHT_DELTA_MAX: float = Field(
        default_factory=lambda: float(os.environ.get("AUTO_APPLY_WEIGHT_DELTA_MAX", "0.15"))
    )
    AUTO_APPLY_VIX_REDIS_TTL_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("AUTO_APPLY_VIX_REDIS_TTL_SECONDS", "3600"))
    )
    AUTO_APPLY_VIX_FRED_SERIES: str = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_VIX_FRED_SERIES", "VIXCLS")
    )
```

- [x] **Step 2: Update workers.yaml**

Append to `config/workers.yaml`:

```yaml

auto_apply:
  # Toggle: set AUTO_APPLY_ENABLED=false env var to disable without deploy
  enabled: true
  vix_threshold: 30.0            # block if VIX >= threshold
  ic_variance_threshold: 0.15    # block if std(purified_icir.values()) >= threshold
  weight_delta_max: 0.15         # block if any weight changes by >= 15pp
  vix_redis_ttl_seconds: 3600    # cache VIX in Redis for 1 hour
  vix_fred_series: "VIXCLS"      # FRED series ID for daily VIX
```

- [x] **Step 3: Run tests to verify no regressions**

Run: `pytest tests/ -v --tb=short -q`

Expected: All tests pass.

- [x] **Step 4: Commit**

```bash
git add src/config.py config/workers.yaml
git commit -m "feat: add AUTO_APPLY_* config fields and FRED_API_KEY"
```

---

## Task 3: VIX fetch + Redis cache

**Files:**
- Create: `src/connectors/macro.py`
- Create: `tests/connectors/test_macro.py`
- Modify: `src/store/redis_store.py`
- Modify: `tests/test_redis_store.py`

- [x] **Step 1: Write failing tests for fetch_vix_from_fred()**

Create `tests/connectors/test_macro.py`:

```python
"""Tests for macro data connector."""

from unittest.mock import MagicMock, patch

import pytest


class TestFetchVixFromFred:
    """Tests for fetch_vix_from_fred()."""

    def test_returns_float_with_api_key(self):
        """Fetches VIX via authenticated JSON API when api_key provided."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "observations": [{"date": "2026-05-02", "value": "18.45"}]
        }

        with patch("httpx.get", return_value=mock_resp) as mock_get:
            from src.connectors.macro import fetch_vix_from_fred
            result = fetch_vix_from_fred(series_id="VIXCLS", api_key="test-key")

        assert result == pytest.approx(18.45)
        call_kwargs = mock_get.call_args
        assert "api.stlouisfed.org" in call_kwargs[0][0]
        assert call_kwargs[1]["params"]["api_key"] == "test-key"

    def test_returns_float_without_api_key(self):
        """Fetches VIX via public CSV endpoint when no api_key."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "DATE,VIXCLS\n2026-04-30,20.12\n2026-05-01,19.87\n2026-05-02,18.45"

        with patch("httpx.get", return_value=mock_resp) as mock_get:
            from src.connectors.macro import fetch_vix_from_fred
            result = fetch_vix_from_fred(series_id="VIXCLS", api_key="")

        assert result == pytest.approx(18.45)
        assert "fredgraph.csv" in mock_get.call_args[0][0]

    def test_raises_on_http_error(self):
        """Propagates httpx.HTTPError on network failure."""
        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_vix_from_fred
            with pytest.raises(httpx.HTTPStatusError):
                fetch_vix_from_fred(series_id="VIXCLS", api_key="test-key")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/connectors/test_macro.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'src.connectors.macro'`

- [x] **Step 3: Create src/connectors/macro.py**

```python
"""Macro data connector — FRED API for VIX and other macro indicators."""

import httpx


def fetch_vix_from_fred(series_id: str = "VIXCLS", api_key: str = "") -> float:
    """Fetch latest VIX value from FRED.

    Uses authenticated JSON API when api_key is provided,
    falls back to public CSV endpoint otherwise.

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.TimeoutException: if request exceeds 10s timeout
        ValueError: if response cannot be parsed as float
    """
    if api_key:
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "limit": 1,
            "sort_order": "desc",
        }
        resp = httpx.get(url, params=params, timeout=10.0)
        resp.raise_for_status()
        return float(resp.json()["observations"][0]["value"])
    else:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        lines = resp.text.strip().split("\n")
        _, value = lines[-1].split(",")
        return float(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/connectors/test_macro.py -v`

Expected: 3 tests PASS.

- [x] **Step 5: Write failing tests for RedisStore VIX cache**

Append to `tests/test_redis_store.py`:

```python
class TestVixCache:
    """Tests for RedisStore.get_vix_cached() and set_vix_cached()."""

    def test_get_returns_float_when_key_exists(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"18.45"

        store = RedisStore(redis_client=mock_redis)
        result = store.get_vix_cached()

        assert result == pytest.approx(18.45)
        mock_redis.get.assert_called_once_with("macro:vix:latest")

    def test_get_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_vix_cached() is None

    def test_set_stores_with_ttl(self):
        mock_redis = MagicMock()

        store = RedisStore(redis_client=mock_redis)
        store.set_vix_cached(18.45, ttl=3600)

        mock_redis.setex.assert_called_once_with("macro:vix:latest", 3600, "18.45")
```

- [x] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_redis_store.py::TestVixCache -v`

Expected: FAIL — `AttributeError: 'RedisStore' object has no attribute 'get_vix_cached'`

- [x] **Step 7: Add VIX cache methods to RedisStore**

In `src/store/redis_store.py`, add after `get_performance_report()`:

```python
    def get_vix_cached(self) -> float | None:
        """Get cached VIX value from Redis. Returns None if absent."""
        raw = self._r.get("macro:vix:latest")
        if raw is None:
            return None
        return float(raw)

    def set_vix_cached(self, value: float, ttl: int = 3600) -> None:
        """Cache VIX value in Redis with TTL in seconds."""
        self._r.setex("macro:vix:latest", ttl, str(value))
```

- [x] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_redis_store.py::TestVixCache -v`

Expected: 3 tests PASS.

- [x] **Step 9: Run full test suite for regressions**

Run: `pytest tests/ -q --tb=short`

Expected: All tests pass.

- [x] **Step 10: Commit**

```bash
git add src/connectors/macro.py src/store/redis_store.py \
        tests/connectors/test_macro.py tests/test_redis_store.py
git commit -m "feat: add fetch_vix_from_fred and RedisStore VIX cache"
```

---

## Task 4: Telegram formatters

**Files:**
- Modify: `src/notifications/telegram.py`
- Create: `tests/notifications/test_telegram.py`

- [x] **Step 1: Write failing tests**

Create `tests/notifications/__init__.py` (empty file).

Create `tests/notifications/test_telegram.py`:

```python
"""Tests for Telegram notification formatters."""

from datetime import date

import pytest

from src.notifications.telegram import format_auto_apply_message, format_freeze_message


class TestFormatAutoApplyMessage:
    """Tests for format_auto_apply_message()."""

    def test_contains_success_header(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 0.45, "qwen3.5:cloud": 0.35, "deepseek-v4-pro:cloud": 0.20},
            current_weights={"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33},
            guardrail_values={"vix": 18.4, "ic_variance": 0.08, "weight_delta_max": 0.11},
            next_review_date=date(2026, 5, 12),
        )
        assert "✅" in msg
        assert "automaticamente" in msg

    def test_shows_weight_delta(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            guardrail_values={},
            next_review_date=date(2026, 5, 12),
        )
        assert "+11%" in msg or "+0.11" in msg or "11pp" in msg.lower() or "+11" in msg

    def test_shows_next_review_date(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 1.0},
            current_weights={"opus": 1.0},
            guardrail_values={},
            next_review_date=date(2026, 5, 12),
        )
        assert "2026-05-12" in msg

    def test_shows_guardrail_values(self):
        msg = format_auto_apply_message(
            new_weights={"opus": 1.0},
            current_weights={"opus": 1.0},
            guardrail_values={"vix": 18.4, "ic_variance": 0.08, "weight_delta_max": 0.0},
            next_review_date=date(2026, 5, 12),
        )
        assert "18.4" in msg
        assert "0.08" in msg


class TestFormatFreezeMessage:
    """Tests for format_freeze_message()."""

    def test_contains_warning_header(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX = 38.2 >= 30.0",
        )
        assert "⚠️" in msg
        assert "bloccato" in msg

    def test_shows_freeze_reason(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX = 38.2 >= 30.0",
        )
        assert "VIX = 38.2" in msg

    def test_shows_suggested_weights_not_applied(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="VIX too high",
        )
        assert "NON applicati" in msg
        assert "45%" in msg

    def test_shows_manual_approval_hint(self):
        msg = format_freeze_message(
            suggested_weights={"opus": 0.45},
            current_weights={"opus": 0.34},
            freeze_reason="IC variance too high",
        )
        assert "/api/weights/approve" in msg
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/notifications/test_telegram.py -v`

Expected: FAIL — `ImportError: cannot import name 'format_auto_apply_message'`

- [x] **Step 3: Add formatters to telegram.py**

Append to `src/notifications/telegram.py`:

```python
def format_auto_apply_message(
    new_weights: dict[str, float],
    current_weights: dict[str, float],
    guardrail_values: dict[str, float],
    next_review_date,
) -> str:
    """Format Telegram message for successful auto-apply."""
    lines = ["✅ <b>Pesi aggiornati automaticamente</b>\n", "📊 <b>Nuovi pesi:</b>"]
    for model, w in sorted(new_weights.items()):
        old_w = current_weights.get(model, 0.0)
        delta = w - old_w
        delta_str = f" ({delta:+.0%})" if abs(delta) >= 0.005 else " (=)"
        lines.append(f"  {model}: {w:.0%}{delta_str}")

    lines.append("\n🛡️ <b>Guardrail superati:</b>")
    if "vix" in guardrail_values:
        lines.append(f"  VIX: {guardrail_values['vix']:.1f}")
    if "ic_variance" in guardrail_values:
        lines.append(f"  IC variance: {guardrail_values['ic_variance']:.3f}")
    if "weight_delta_max" in guardrail_values:
        lines.append(f"  Δmax peso: {guardrail_values['weight_delta_max']:.0%}")

    lines.append(f"\n🕐 Prossima revisione: {next_review_date}")
    return "\n".join(lines)


def format_freeze_message(
    suggested_weights: dict[str, float],
    current_weights: dict[str, float],
    freeze_reason: str,
) -> str:
    """Format Telegram message for frozen auto-apply."""
    lines = [
        "⚠️ <b>Auto-apply bloccato — approvazione manuale richiesta</b>\n",
        f"🚫 <b>Guardrail fallito:</b> {freeze_reason}\n",
        "📊 <b>Pesi suggeriti (NON applicati):</b>",
    ]
    for model, w in sorted(suggested_weights.items()):
        old_w = current_weights.get(model, 0.0)
        delta = w - old_w
        delta_str = f" ({delta:+.0%})" if abs(delta) >= 0.005 else " (=)"
        lines.append(f"  {model}: {w:.0%}{delta_str}")

    lines.append("\n👉 Approva manualmente: POST /api/weights/approve")
    return "\n".join(lines)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/notifications/test_telegram.py -v`

Expected: 8 tests PASS.

- [x] **Step 5: Run full test suite for regressions**

Run: `pytest tests/ -q --tb=short`

Expected: All tests pass.

- [x] **Step 6: Commit**

```bash
git add src/notifications/telegram.py \
        tests/notifications/__init__.py \
        tests/notifications/test_telegram.py
git commit -m "feat: add format_auto_apply_message and format_freeze_message to Telegram"
```

---

## Task 5: check_and_apply_weights task

**Files:**
- Modify: `src/workers/performance.py`
- Modify: `tests/workers/test_performance_worker.py`

- [x] **Step 1: Write all 8 failing tests**

Append to `tests/workers/test_performance_worker.py`:

```python
class TestCheckAndApplyWeights:
    """Tests for check_and_apply_weights Celery task."""

    SUGGESTION = {
        "suggested_weights": {
            "opus": 0.45,
            "qwen3.5:cloud": 0.35,
            "deepseek-v4-pro:cloud": 0.20,
        },
        "purified_icir": {
            "opus": 0.31,
            "qwen3.5:cloud": 0.18,
            "deepseek-v4-pro:cloud": 0.09,
        },
        "freeze_reason": "",
        "computed_at": "2026-05-04T08:00:00+00:00",
    }
    CURRENT = {"weights": {"opus": 0.34, "qwen3.5:cloud": 0.33, "deepseek-v4-pro:cloud": 0.33}, "source": "suggestion"}

    def _make_redis(self, suggestion=None, current=None, vix_cached=None):
        mock = MagicMock()
        mock.get_weight_suggestion.return_value = suggestion if suggestion is not None else self.SUGGESTION
        mock.get_current_weights_stored.return_value = current if current is not None else self.CURRENT
        mock.get_vix_cached.return_value = vix_cached
        mock.set_vix_cached = MagicMock()
        mock.set_ensemble_weights = MagicMock()
        mock._r = MagicMock()
        return mock

    def _make_config(self, enabled=True, vix_threshold=30.0, ic_var_threshold=0.15, delta_max=0.15):
        from src.config import Config
        return Config(
            ADMIN_API_KEY="test-api-key-for-testing-only-12345678",
            DATABASE_URL="postgresql://localhost:5432/test",
            AUTO_APPLY_ENABLED=enabled,
            AUTO_APPLY_VIX_THRESHOLD=vix_threshold,
            AUTO_APPLY_IC_VARIANCE_THRESHOLD=ic_var_threshold,
            AUTO_APPLY_WEIGHT_DELTA_MAX=delta_max,
            AUTO_APPLY_VIX_REDIS_TTL_SECONDS=3600,
            AUTO_APPLY_VIX_FRED_SERIES="VIXCLS",
        )

    def test_all_guardrails_pass_applies_weights(self):
        """All guardrails pass → weights applied, log source='auto_apply', Telegram ✅."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_called_once_with(
            self.SUGGESTION["suggested_weights"], source="auto_apply"
        )
        pg.log_weight_update.assert_called_once()
        assert pg.log_weight_update.call_args.kwargs["source"] == "auto_apply"
        assert pg.log_weight_update.call_args.kwargs["approved_by"] == "system"
        notifier.send_alert.assert_called_once()
        assert "✅" in notifier.send_alert.call_args[0][0]

    def test_g1_disabled_exits_silently(self):
        """G1: auto_apply_enabled=False → silent exit, no log, no Telegram."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        cfg = self._make_config(enabled=False)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        pg.log_weight_update.assert_not_called()
        notifier.send_alert.assert_not_called()
        redis.set_ensemble_weights.assert_not_called()

    def test_g2_vix_too_high_freezes(self):
        """G2: VIX >= threshold → freeze, log source='freeze', Telegram ⚠️."""
        redis = self._make_redis(vix_cached=38.5)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config(vix_threshold=30.0)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"
        assert "VIX" in pg.log_weight_update.call_args.kwargs["note"]
        assert "⚠️" in notifier.send_alert.call_args[0][0]

    def test_g2_fred_unavailable_freezes(self):
        """G2: FRED fetch fails → guardrail fails (fail-safe) → freeze."""
        redis = self._make_redis(vix_cached=None)  # cache miss
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg), \
             patch("src.workers.performance._get_vix", return_value=None):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_g3_ic_variance_too_high_freezes(self):
        """G3: std(purified_icir) >= threshold → freeze."""
        # Large spread across IC values → high variance
        high_var_suggestion = {
            **self.SUGGESTION,
            "purified_icir": {"opus": 2.0, "qwen3.5:cloud": 0.01, "deepseek-v4-pro:cloud": 0.01},
        }
        redis = self._make_redis(suggestion=high_var_suggestion, vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config(ic_var_threshold=0.15)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_g4_weight_delta_too_large_freezes(self):
        """G4: max weight delta >= threshold → freeze."""
        big_delta_suggestion = {
            **self.SUGGESTION,
            "suggested_weights": {
                "opus": 0.90,  # +56pp vs current 0.34
                "qwen3.5:cloud": 0.05,
                "deepseek-v4-pro:cloud": 0.05,
            },
        }
        redis = self._make_redis(suggestion=big_delta_suggestion, vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config(delta_max=0.15)

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis.set_ensemble_weights.assert_not_called()
        assert pg.log_weight_update.call_args.kwargs["source"] == "freeze"

    def test_no_suggestion_exits_silently(self):
        """No suggestion in Redis → silent exit, no log, no Telegram."""
        redis = self._make_redis(suggestion=None)
        redis.get_weight_suggestion.return_value = None
        pg = MagicMock()
        notifier = MagicMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        pg.log_weight_update.assert_not_called()
        notifier.send_alert.assert_not_called()

    def test_apply_deletes_snapshot_key(self):
        """Successful apply deletes ensemble:weights:suggestion:snapshot from Redis."""
        redis = self._make_redis(vix_cached=18.4)
        pg = MagicMock()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.performance.RedisStore", return_value=redis), \
             patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
             patch("src.workers.performance.TelegramNotifier", return_value=notifier), \
             patch("src.workers.performance.config", cfg):
            from src.workers.performance import check_and_apply_weights
            check_and_apply_weights()

        redis._r.delete.assert_called_once_with("ensemble:weights:suggestion:snapshot")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/workers/test_performance_worker.py::TestCheckAndApplyWeights -v`

Expected: FAIL — `ImportError` or `AttributeError` for `check_and_apply_weights`

- [x] **Step 3: Add _get_vix helper to performance.py**

In `src/workers/performance.py`, add after the imports and before the first task function:

```python
def _get_vix(redis: "RedisStore") -> float | None:
    """Return VIX from Redis cache, fetching from FRED on cache miss.

    Returns None if both cache and FRED are unavailable (caller treats as fail-safe freeze).
    """
    cached = redis.get_vix_cached()
    if cached is not None:
        return cached
    try:
        from src.connectors.macro import fetch_vix_from_fred
        vix = fetch_vix_from_fred(
            series_id=config.AUTO_APPLY_VIX_FRED_SERIES,
            api_key=config.FRED_API_KEY,
        )
        redis.set_vix_cached(vix, ttl=config.AUTO_APPLY_VIX_REDIS_TTL_SECONDS)
        return vix
    except Exception as e:
        log.warning("Failed to fetch VIX from FRED: %s", e)
        return None
```

- [x] **Step 4: Add check_and_apply_weights task to performance.py**

Append to `src/workers/performance.py` (after `check_suggestion_expiry`):

```python
@app.task(name="src.workers.performance.check_and_apply_weights")
def check_and_apply_weights():
    """Apply suggested ensemble weights if all guardrails pass.

    Guardrails evaluated in sequence — first failure stops evaluation:
      G1: AUTO_APPLY_ENABLED flag (silent exit if disabled)
      G2: VIX < vix_threshold (FRED via Redis cache; fail-safe freeze if unavailable)
      G3: std(purified_icir) < ic_variance_threshold
      G4: max(|Δweight|) < weight_delta_max vs current weights

    On pass: applies weights, logs source='auto_apply', sends Telegram ✅
    On fail: no change, logs source='freeze', sends Telegram ⚠️
    On no suggestion: silent exit
    """
    redis = RedisStore()

    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        return

    # G1: toggle (silent exit — disabled is a normal operational state)
    if not config.AUTO_APPLY_ENABLED:
        return

    suggested_weights = suggestion.get("suggested_weights", {})
    purified_icir = suggestion.get("purified_icir", {})

    freeze_reason = None

    # G2: VIX
    vix = _get_vix(redis)
    if vix is None:
        freeze_reason = "VIX data unavailable (fail-safe)"
    elif vix >= config.AUTO_APPLY_VIX_THRESHOLD:
        freeze_reason = f"VIX = {vix:.1f} >= {config.AUTO_APPLY_VIX_THRESHOLD}"

    # G3: IC variance
    if freeze_reason is None:
        if not purified_icir:
            freeze_reason = "purified_icir missing from suggestion"
        else:
            ic_variance = float(np.std(list(purified_icir.values())))
            if ic_variance >= config.AUTO_APPLY_IC_VARIANCE_THRESHOLD:
                freeze_reason = (
                    f"IC variance = {ic_variance:.3f} >= {config.AUTO_APPLY_IC_VARIANCE_THRESHOLD}"
                )

    # G4: weight delta
    if freeze_reason is None:
        stored = redis.get_current_weights_stored()
        if stored is None:
            freeze_reason = "current weights unavailable (fail-safe)"
        else:
            current_weights = stored.get("weights", {})
            all_models = set(suggested_weights) | set(current_weights)
            max_delta = max(
                abs(suggested_weights.get(m, 0.0) - current_weights.get(m, 0.0))
                for m in all_models
            )
            if max_delta >= config.AUTO_APPLY_WEIGHT_DELTA_MAX:
                freeze_reason = (
                    f"max weight delta = {max_delta:.3f} >= {config.AUTO_APPLY_WEIGHT_DELTA_MAX}"
                )

    pg = PostgreSQLStore()
    notifier = TelegramNotifier()

    if freeze_reason:
        stored = redis.get_current_weights_stored()
        current_weights = (stored or {}).get("weights", {})
        pg.log_weight_update(
            source="freeze",
            applied_weights=current_weights,
            suggested_weights=suggested_weights,
            purified_icir=purified_icir,
            freeze_reason=freeze_reason,
            note=f"Auto-apply blocked: {freeze_reason}",
            approved_by="system",
        )
        from src.notifications.telegram import format_freeze_message
        msg = format_freeze_message(suggested_weights, current_weights, freeze_reason)
        asyncio.run(notifier.send_alert(msg, level="warning"))
        log.info("Auto-apply frozen: %s", freeze_reason)
    else:
        stored = redis.get_current_weights_stored()
        current_weights = (stored or {}).get("weights", {})
        ic_variance = float(np.std(list(purified_icir.values())))
        all_models = set(suggested_weights) | set(current_weights)
        max_delta = max(
            abs(suggested_weights.get(m, 0.0) - current_weights.get(m, 0.0))
            for m in all_models
        )

        redis.set_ensemble_weights(suggested_weights, source="auto_apply")
        redis._r.delete("ensemble:weights:suggestion:snapshot")

        pg.log_weight_update(
            source="auto_apply",
            applied_weights=suggested_weights,
            suggested_weights=suggested_weights,
            purified_icir=purified_icir,
            freeze_reason=None,
            note=json.dumps({"vix": vix, "ic_variance": ic_variance, "max_delta": max_delta}),
            approved_by="system",
        )

        from datetime import timedelta
        from src.notifications.telegram import format_auto_apply_message
        next_review = (datetime.now(timezone.utc) + timedelta(days=7)).date()
        msg = format_auto_apply_message(
            suggested_weights, current_weights,
            {"vix": vix, "ic_variance": ic_variance, "weight_delta_max": max_delta},
            next_review,
        )
        asyncio.run(notifier.send_alert(msg, level="info"))
        log.info("Weights auto-applied successfully")
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/workers/test_performance_worker.py::TestCheckAndApplyWeights -v`

Expected: 8 tests PASS.

- [x] **Step 6: Run full worker test suite for regressions**

Run: `pytest tests/workers/ -v --tb=short`

Expected: All tests pass.

- [x] **Step 7: Commit**

```bash
git add src/workers/performance.py tests/workers/test_performance_worker.py
git commit -m "feat: add check_and_apply_weights task with VIX/IC/delta guardrails"
```

---

## Task 6: Chain into run_weekly_weights + final verification

**Files:**
- Modify: `src/workers/performance.py` (add chain call)
- Modify: `tests/workers/test_performance_worker.py` (update weekly test)

- [x] **Step 1: Add chain call to run_weekly_weights**

In `src/workers/performance.py`, inside `run_weekly_weights()`, after the Telegram alert block (after `asyncio.run(notifier.send_alert(...))`):

```python
        # Chain: trigger guardrail check 5s after suggestion is stored in Redis
        check_and_apply_weights.apply_async(countdown=5)
```

- [x] **Step 2: Update the weekly weights test to assert chain is triggered**

In `tests/workers/test_performance_worker.py`, inside `TestRunWeeklyWeights.test_run_weekly_weights_observational`, add after the existing assertions:

```python
        # Verify check_and_apply_weights was chained
        from unittest.mock import call
        import src.workers.performance as perf_module
        # The apply_async call happens on the task object — verify it was called
        # (We patch at module level so the task's apply_async is the real Celery call;
        #  in tests Celery is configured with ALWAYS_EAGER so it runs synchronously
        #  or we can verify via the mock.)
```

Replace the above comment with this concrete assertion — update the test to patch `check_and_apply_weights`:

Rewrite `test_run_weekly_weights_observational` to add the chain patch:

```python
    @patch("src.workers.performance.check_and_apply_weights")
    @patch("src.workers.performance.compute_purified_icir")
    @patch("src.workers.performance._fetch_all_signals_for_ic")
    @patch("src.workers.performance.RedisStore")
    @patch("src.workers.performance.TelegramNotifier")
    def test_run_weekly_weights_observational(
        self, mock_notifier_cls, mock_redis_cls, mock_fetch_cls,
        mock_purified_cls, mock_apply_task
    ):
        """Test weekly weights computation is observational (no auto-apply)."""
        mock_fetch_cls.return_value = (
            generate_signal_rows(300, "opus", return_correlation=0.3) +
            generate_signal_rows(300, "qwen3.5:cloud", return_correlation=0.2)
        )
        mock_purified_cls.return_value = {
            "opus": 1.2,
            "qwen3.5:cloud": 0.8,
        }
        mock_redis = MagicMock()
        mock_redis.get_ensemble_weights = MagicMock(return_value=None)
        mock_redis._r = MagicMock()
        mock_redis_cls.return_value = mock_redis

        mock_notifier = MagicMock()
        mock_notifier.send_alert = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        run_weekly_weights()

        # Verify suggestion and snapshot keys were set
        setex_calls = mock_redis._r.setex.call_args_list
        assert any(call[0][0] == "ensemble:weights:suggestion" for call in setex_calls)
        assert any(call[0][0] == "ensemble:weights:suggestion:snapshot" for call in setex_calls)

        # Verify Telegram alert was sent
        mock_notifier.send_alert.assert_called()

        # Verify check_and_apply_weights was chained
        mock_apply_task.apply_async.assert_called_once_with(countdown=5)
```

- [x] **Step 3: Run the updated test**

Run: `pytest tests/workers/test_performance_worker.py::TestRunWeeklyWeights -v`

Expected: Both tests PASS.

- [x] **Step 4: Run full test suite**

Run: `pytest -v --tb=short 2>&1 | tail -20`

Expected: All tests pass, 0 failures.

- [x] **Step 5: Verify beat schedule still has 5 tasks**

Run:
```bash
python -c "
from src.workers.celery_app import app
for name in app.conf.beat_schedule:
    print(name)
"
```

Expected:
```
sentiment-worker
performance-daily
performance-weekly
drift-detection
check-suggestion-expiry
```

(`check_and_apply_weights` is NOT in the beat schedule — it is only triggered via chain from `run_weekly_weights`, not on its own schedule.)

- [x] **Step 6: Final commit**

```bash
git add src/workers/performance.py tests/workers/test_performance_worker.py
git commit -m "feat: chain check_and_apply_weights from run_weekly_weights"
```
