# RegimeDetector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `detect_regime` Celery task that classifies the daily macro regime (bull/sideways/bear/high_vol) using 2 parallel LLM calls on VIX + yield curve + SPY momentum, and writes the position multiplier to Redis for QuantConnect to consume.

**Architecture:** A new `src/workers/regime.py` task fetches macro data via `src/connectors/macro.py`, calls 2 LLM clients in parallel with `asyncio.gather`, applies consensus logic (conservative on disagreement), and writes `regime:current` + `qc:sizing_multiplier` to Redis. Celery beat triggers it daily at 07:00 UTC Mon–Fri.

**Tech Stack:** Celery, Redis (redis-py), httpx (FRED API), yfinance (SPY), asyncio, pydantic v2, pytest, unittest.mock

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/models/regime.py` | Create | `RegimeOutput`, `MacroSnapshot`, `RegimeState`, `REGIME_DEFAULTS` |
| `src/config.py` | Modify | Add `REGIME_*` Pydantic fields |
| `config/workers.yaml` | Modify | Add `regime:` block (documentation only) |
| `src/connectors/macro.py` | Modify | Add `fetch_yield_curve()` + `fetch_spy_momentum_20d()` |
| `src/store/redis_store.py` | Modify | Add `set_regime()`, `get_regime()`, `set_qc_sizing_multiplier()` |
| `src/notifications/telegram.py` | Modify | Add `format_regime_message()` |
| `src/workers/regime.py` | Create | `detect_regime()` task + `_run_llm_pair()` + `_build_prompt()` + `_make_llm_client()` |
| `src/workers/celery_app.py` | Modify | Add `detect_regime` to beat schedule |
| `tests/models/__init__.py` | Create | Empty init for test discovery |
| `tests/models/test_regime.py` | Create | `TestRegimeOutput`, `TestRegimeState`, `TestRegimeDefaults` |
| `tests/connectors/test_macro.py` | Modify | Add `TestFetchYieldCurve`, `TestFetchSpyMomentum` |
| `tests/test_redis_store.py` | Modify | Add `TestRegimeRedis` |
| `tests/notifications/test_telegram.py` | Modify | Add `TestFormatRegimeMessage` |
| `tests/workers/test_regime_worker.py` | Create | `TestDetectRegime` — 7 scenarios |

---

## Task 1: Pydantic models — `src/models/regime.py`

**Files:**
- Create: `src/models/regime.py`
- Create: `tests/models/__init__.py`
- Create: `tests/models/test_regime.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/models/test_regime.py
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.regime import REGIME_DEFAULTS, MacroSnapshot, RegimeOutput, RegimeState


class TestRegimeOutput:
    def test_valid_bull(self):
        r = RegimeOutput(regime="bull", confidence=0.9, reasoning="uptrend")
        assert r.regime == "bull"
        assert r.data_quality == "complete"
        assert r.regime_secondary is None

    def test_invalid_regime_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="crash", confidence=0.9, reasoning="bad")

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="bull", confidence=1.5, reasoning="x")

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            RegimeOutput(regime="bear", confidence=-0.1, reasoning="x")

    def test_partial_data_quality_accepted(self):
        r = RegimeOutput(regime="sideways", confidence=0.5, reasoning="x", data_quality="partial")
        assert r.data_quality == "partial"

    def test_regime_secondary_optional(self):
        r = RegimeOutput(regime="bear", confidence=0.7, reasoning="x", regime_secondary="sideways")
        assert r.regime_secondary == "sideways"


class TestRegimeState:
    def _make_state(self, regime="bear"):
        return RegimeState(
            regime=regime,
            multiplier=0.4,
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=[{"regime": regime, "reasoning": "test"}],
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_json_roundtrip(self):
        state = self._make_state()
        restored = RegimeState.model_validate_json(state.model_dump_json())
        assert restored.regime == "bear"
        assert restored.multiplier == 0.4
        assert restored.macro_snapshot.vix == pytest.approx(28.4)

    def test_disagreement_defaults_false(self):
        state = self._make_state()
        assert state.disagreement is False

    def test_macro_snapshot_fields(self):
        snap = MacroSnapshot(vix=18.4, yield_curve=0.3, spy_momentum_20d=4.2)
        assert snap.vix == pytest.approx(18.4)
        assert snap.yield_curve == pytest.approx(0.3)
        assert snap.spy_momentum_20d == pytest.approx(4.2)


class TestRegimeDefaults:
    def test_all_four_regimes_present(self):
        assert set(REGIME_DEFAULTS.keys()) == {"bull", "sideways", "bear", "high_vol"}

    def test_bull_highest_multiplier(self):
        assert REGIME_DEFAULTS["bull"] == max(REGIME_DEFAULTS.values())

    def test_high_vol_lowest_multiplier(self):
        assert REGIME_DEFAULTS["high_vol"] == min(REGIME_DEFAULTS.values())

    def test_multipliers_descending(self):
        order = ["bull", "sideways", "bear", "high_vol"]
        values = [REGIME_DEFAULTS[r] for r in order]
        assert values == sorted(values, reverse=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/models/test_regime.py -v
```

Expected: `ERROR` — `src/models/regime.py` does not exist.

- [ ] **Step 3: Create `tests/models/__init__.py` (empty)**

```bash
touch tests/models/__init__.py
```

- [ ] **Step 4: Write minimal implementation**

```python
# src/models/regime.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

REGIME_DEFAULTS: dict[str, float] = {
    "bull": 1.0,
    "sideways": 0.7,
    "bear": 0.4,
    "high_vol": 0.2,
}

RegimeLabel = Literal["bull", "sideways", "bear", "high_vol"]


class RegimeOutput(BaseModel):
    regime: RegimeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    data_quality: Literal["complete", "partial"] = "complete"
    regime_secondary: RegimeLabel | None = None


class MacroSnapshot(BaseModel):
    vix: float
    yield_curve: float
    spy_momentum_20d: float


class RegimeState(BaseModel):
    regime: RegimeLabel
    multiplier: float
    macro_snapshot: MacroSnapshot
    llm_outputs: list[dict]
    disagreement: bool = False
    detected_at: datetime
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/models/test_regime.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add src/models/regime.py tests/models/__init__.py tests/models/test_regime.py
git commit -m "feat: add RegimeOutput, MacroSnapshot, RegimeState Pydantic models"
```

---

## Task 2: Config fields

**Files:**
- Modify: `src/config.py`
- Modify: `config/workers.yaml`

- [ ] **Step 1: Add fields to `src/config.py`**

Locate the `# Fallback settings` block (around line 71) and add the following block after `AUTO_APPLY_VIX_FRED_SERIES`:

```python
    # Regime detection
    REGIME_LLM_MODEL_1: str = Field(
        default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_1", "opus")
    )
    REGIME_LLM_MODEL_2: str = Field(
        default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_2", "qwen3.5:cloud")
    )
    REGIME_MULTIPLIER_BULL: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BULL", "1.0"))
    )
    REGIME_MULTIPLIER_SIDEWAYS: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_SIDEWAYS", "0.7"))
    )
    REGIME_MULTIPLIER_BEAR: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BEAR", "0.4"))
    )
    REGIME_MULTIPLIER_HIGH_VOL: float = Field(
        default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_HIGH_VOL", "0.2"))
    )
    REGIME_REDIS_TTL_SECONDS: int = Field(
        default_factory=lambda: int(os.environ.get("REGIME_REDIS_TTL_SECONDS", "90000"))
    )  # 25h — slightly more than 24h so regime doesn't expire before next run
```

- [ ] **Step 2: Add documentation block to `config/workers.yaml`**

Append to the end of `config/workers.yaml`:

```yaml

regime:
  schedule: "0 7 * * 1-5"     # 07:00 UTC, Mon-Fri (pre-market US)
  llm_model_1: opus            # override with REGIME_LLM_MODEL_1 env var
  llm_model_2: qwen3.5:cloud   # override with REGIME_LLM_MODEL_2 env var
  multipliers:
    bull: 1.0
    sideways: 0.7
    bear: 0.4
    high_vol: 0.2
  redis_ttl_seconds: 90000     # 25h
```

- [ ] **Step 3: Verify config loads without error**

```bash
python -c "from src.config import config; print(config.REGIME_LLM_MODEL_1, config.REGIME_MULTIPLIER_BEAR)"
```

Expected: `opus 0.4`

- [ ] **Step 4: Commit**

```bash
git add src/config.py config/workers.yaml
git commit -m "feat: add REGIME_* config fields for regime detector"
```

---

## Task 3: Macro connectors

**Files:**
- Modify: `src/connectors/macro.py`
- Modify: `tests/connectors/test_macro.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/connectors/test_macro.py`:

```python
class TestFetchYieldCurve:
    def test_returns_float_without_api_key(self):
        """fetch_yield_curve delegates to fetch_vix_from_fred with T10Y2Y series."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "DATE,T10Y2Y\n2026-04-30,-0.50\n2026-05-01,-0.48\n2026-05-02,-0.45"

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_yield_curve
            result = fetch_yield_curve(api_key="")

        assert result == pytest.approx(-0.45)

    def test_returns_float_with_api_key(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "observations": [{"date": "2026-05-02", "value": "-0.45"}]
        }

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_yield_curve
            result = fetch_yield_curve(api_key="test-key")

        assert result == pytest.approx(-0.45)

    def test_propagates_http_error(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )

        with patch("httpx.get", return_value=mock_resp):
            from src.connectors.macro import fetch_yield_curve
            with pytest.raises(httpx.HTTPStatusError):
                fetch_yield_curve(api_key="")


class TestFetchSpyMomentum:
    def _make_mock_ticker(self, n_days=22, start=400.0, end=420.0):
        import numpy as np
        import pandas as pd
        prices = np.linspace(start, end, n_days)
        hist = pd.DataFrame(
            {"Close": prices},
            index=pd.date_range("2026-04-01", periods=n_days, freq="B"),
        )
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist
        return mock_ticker, hist

    def test_returns_float(self):
        mock_ticker, hist = self._make_mock_ticker(n_days=22)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from src.connectors.macro import fetch_spy_momentum_20d
            result = fetch_spy_momentum_20d()

        expected = (hist["Close"].iloc[-1] / hist["Close"].iloc[-20] - 1) * 100
        assert result == pytest.approx(expected, abs=0.01)

    def test_raises_on_insufficient_data(self):
        mock_ticker, _ = self._make_mock_ticker(n_days=15)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from src.connectors.macro import fetch_spy_momentum_20d
            with pytest.raises(ValueError, match="Insufficient"):
                fetch_spy_momentum_20d()

    def test_positive_momentum_on_uptrend(self):
        """22-day uptrend from 400 to 420 → positive momentum."""
        mock_ticker, _ = self._make_mock_ticker(n_days=22, start=400.0, end=420.0)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from src.connectors.macro import fetch_spy_momentum_20d
            result = fetch_spy_momentum_20d()

        assert result > 0

    def test_negative_momentum_on_downtrend(self):
        """22-day downtrend from 420 to 380 → negative momentum."""
        mock_ticker, _ = self._make_mock_ticker(n_days=22, start=420.0, end=380.0)

        with patch("yfinance.Ticker", return_value=mock_ticker):
            from src.connectors.macro import fetch_spy_momentum_20d
            result = fetch_spy_momentum_20d()

        assert result < 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/connectors/test_macro.py::TestFetchYieldCurve tests/connectors/test_macro.py::TestFetchSpyMomentum -v
```

Expected: FAIL — `fetch_yield_curve` and `fetch_spy_momentum_20d` not defined.

- [ ] **Step 3: Add functions to `src/connectors/macro.py`**

Append to the end of `src/connectors/macro.py`:

```python
def fetch_yield_curve(api_key: str = "") -> float:
    """Fetch T10Y2Y yield curve spread from FRED.

    T10Y2Y is the 10-year minus 2-year Treasury yield spread in percentage
    points. Negative values indicate an inverted yield curve (recession signal).

    Raises:
        httpx.HTTPStatusError: on non-2xx HTTP response
        httpx.RequestError: on network failure
        ValueError: if response cannot be parsed
    """
    return fetch_vix_from_fred(series_id="T10Y2Y", api_key=api_key)


def fetch_spy_momentum_20d() -> float:
    """Fetch SPY 20-trading-day price momentum as percentage return.

    Returns:
        Momentum as float (e.g., 4.2 for +4.2%, -8.1 for -8.1%)

    Raises:
        ValueError: if fewer than 20 trading days of history available
    """
    import yfinance as yf

    ticker = yf.Ticker("SPY")
    hist = ticker.history(period="1mo")
    if len(hist) < 20:
        raise ValueError(
            f"Insufficient SPY price history: {len(hist)} days (need 20)"
        )
    close = hist["Close"]
    return float((close.iloc[-1] / close.iloc[-20] - 1) * 100)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/connectors/test_macro.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/connectors/macro.py tests/connectors/test_macro.py
git commit -m "feat: add fetch_yield_curve and fetch_spy_momentum_20d to macro connector"
```

---

## Task 4: Redis store methods

**Files:**
- Modify: `src/store/redis_store.py`
- Modify: `tests/test_redis_store.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_redis_store.py`:

```python
class TestRegimeRedis:
    """Tests for RegimeState persistence and set_qc_sizing_multiplier."""

    def _make_state(self, regime="bear"):
        from src.models.regime import MacroSnapshot, RegimeState
        return RegimeState(
            regime=regime,
            multiplier=0.4,
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=[{"regime": regime, "reasoning": "test"}],
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_set_regime_calls_setex(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)
        state = self._make_state()

        store.set_regime(state, ttl=90000)

        mock_redis.setex.assert_called_once()
        key, ttl, value = mock_redis.setex.call_args[0]
        assert key == "regime:current"
        assert ttl == 90000
        assert "bear" in value

    def test_get_regime_roundtrip(self):
        mock_redis = MagicMock()
        state = self._make_state()
        mock_redis.get.return_value = state.model_dump_json().encode()

        store = RedisStore(redis_client=mock_redis)
        result = store.get_regime()

        assert result is not None
        assert result.regime == "bear"
        assert result.multiplier == pytest.approx(0.4)
        assert result.macro_snapshot.vix == pytest.approx(28.4)
        mock_redis.get.assert_called_once_with("regime:current")

    def test_get_regime_returns_none_when_absent(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        store = RedisStore(redis_client=mock_redis)
        assert store.get_regime() is None

    def test_get_regime_returns_none_on_corrupted_data(self):
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"not-valid-json"

        store = RedisStore(redis_client=mock_redis)
        assert store.get_regime() is None

    def test_set_qc_sizing_multiplier(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        store.set_qc_sizing_multiplier(0.4, ttl=90000)

        mock_redis.setex.assert_called_once_with("qc:sizing_multiplier", 90000, "0.4")

    def test_set_qc_sizing_multiplier_bull(self):
        mock_redis = MagicMock()
        store = RedisStore(redis_client=mock_redis)

        store.set_qc_sizing_multiplier(1.0, ttl=90000)

        mock_redis.setex.assert_called_once_with("qc:sizing_multiplier", 90000, "1.0")
```

Also add this import at the top of the test file (the `datetime` and `timezone` imports are likely already there; add them if missing):

```python
from datetime import datetime, timezone
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_redis_store.py::TestRegimeRedis -v
```

Expected: FAIL — `set_regime`, `get_regime`, `set_qc_sizing_multiplier` not defined.

- [ ] **Step 3: Add methods to `src/store/redis_store.py`**

Find the `delete_suggestion_snapshot` method (end of the VIX cache section) and add the following block after it, before the `# OPERATING MODE` section:

```python
    # =========================================================================
    # REGIME DETECTION
    # =========================================================================

    def set_regime(self, state: "RegimeState", ttl: int) -> None:  # type: ignore[name-defined]
        """Persist RegimeState JSON in Redis with TTL."""
        from src.models.regime import RegimeState  # local import to avoid circular
        self._r.setex("regime:current", ttl, state.model_dump_json())

    def get_regime(self) -> "RegimeState | None":  # type: ignore[name-defined]
        """Read RegimeState from Redis. Returns None if absent or corrupted."""
        from src.models.regime import RegimeState
        raw = self._r.get("regime:current")
        if raw is None:
            return None
        try:
            return RegimeState.model_validate_json(raw)
        except Exception:
            return None

    def set_qc_sizing_multiplier(self, value: float, ttl: int) -> None:
        """Write qc:sizing_multiplier with TTL. Overwrites existing value."""
        self._r.setex("qc:sizing_multiplier", ttl, str(value))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_redis_store.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/store/redis_store.py tests/test_redis_store.py
git commit -m "feat: add set_regime, get_regime, set_qc_sizing_multiplier to RedisStore"
```

---

## Task 5: Telegram formatter

**Files:**
- Modify: `src/notifications/telegram.py`
- Modify: `tests/notifications/test_telegram.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/notifications/test_telegram.py`:

```python
class TestFormatRegimeMessage:
    def _make_state(self, regime="bear", disagreement=False, prev_regime_in_outputs=None):
        from src.models.regime import MacroSnapshot, RegimeState
        outputs = [
            {"regime": prev_regime_in_outputs or regime, "reasoning": "Inverted curve"},
            {"regime": regime, "reasoning": "Selloff"},
        ]
        return RegimeState(
            regime=regime,
            multiplier={"bull": 1.0, "sideways": 0.7, "bear": 0.4, "high_vol": 0.2}[regime],
            macro_snapshot=MacroSnapshot(vix=28.4, yield_curve=-0.6, spy_momentum_20d=-7.1),
            llm_outputs=outputs,
            disagreement=disagreement,
            detected_at=datetime(2026, 5, 5, 7, 0, 0, tzinfo=timezone.utc),
        )

    def test_regime_change_shows_arrow(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime="bull", disagreement=False)
        assert "BULL" in msg
        assert "BEAR" in msg
        assert "→" in msg
        assert "0.4" in msg

    def test_first_run_no_arrow(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bull")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "→" not in msg
        assert "BULL" in msg

    def test_disagreement_note_included(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear", disagreement=True, prev_regime_in_outputs="bull")
        msg = format_regime_message(state, previous_regime="sideways", disagreement=True)
        assert "Disaccordo" in msg

    def test_macro_data_shown(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "28.4" in msg
        assert "-0.60" in msg or "-0.6" in msg
        assert "-7.1" in msg

    def test_reasoning_included(self):
        from src.notifications.telegram import format_regime_message
        state = self._make_state("bear")
        msg = format_regime_message(state, previous_regime=None, disagreement=False)
        assert "Inverted curve" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/notifications/test_telegram.py::TestFormatRegimeMessage -v
```

Expected: FAIL — `format_regime_message` not defined.

- [ ] **Step 3: Add formatter to `src/notifications/telegram.py`**

Ensure these imports exist at the module level of `tests/notifications/test_telegram.py` (add if missing):
```python
from datetime import datetime, timezone
```

Add this import at the top of `src/notifications/telegram.py` (if not already present):
```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.models.regime import RegimeState
```

Then append to the end of `src/notifications/telegram.py`:

```python
def format_regime_message(
    state: "RegimeState",
    previous_regime: str | None,
    disagreement: bool,
) -> str:
    """Format Telegram message for a regime change notification."""
    regime_upper = state.regime.upper()
    mult = state.multiplier

    if previous_regime:
        header = f"📊 <b>Regime: {previous_regime.upper()} → {regime_upper}</b> (×{mult})"
    else:
        header = f"📊 <b>Regime iniziale: {regime_upper}</b> (×{mult})"

    snap = state.macro_snapshot
    data_line = (
        f"VIX: {snap.vix:.1f} | T10Y2Y: {snap.yield_curve:.2f}% | SPY 20d: {snap.spy_momentum_20d:+.1f}%"
    )

    lines = [header, data_line]

    if state.llm_outputs:
        reasoning = state.llm_outputs[0].get("reasoning", "")
        if reasoning:
            lines.append(f"Reasoning: {reasoning}")

    if disagreement and len(state.llm_outputs) >= 2:
        r1 = state.llm_outputs[0].get("regime", "?")
        r2 = state.llm_outputs[1].get("regime", "?")
        lines.append(f"⚠️ Disaccordo LLM: {r1} vs {r2} → applico {state.regime}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/notifications/test_telegram.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add src/notifications/telegram.py tests/notifications/test_telegram.py
git commit -m "feat: add format_regime_message to Telegram notifications"
```

---

## Task 6: Regime worker

**Files:**
- Create: `src/workers/regime.py`
- Create: `tests/workers/test_regime_worker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/workers/test_regime_worker.py
"""Tests for detect_regime Celery task."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.regime import MacroSnapshot, RegimeOutput, RegimeState


class TestDetectRegime:
    """7 scenarios covering all consensus branches."""

    BULL = RegimeOutput(regime="bull", confidence=0.85, reasoning="uptrend", data_quality="complete")
    BEAR = RegimeOutput(regime="bear", confidence=0.78, reasoning="downturn", data_quality="complete")
    PARTIAL = RegimeOutput(regime="bull", confidence=0.5, reasoning="x", data_quality="partial")

    def _make_redis(self, current_regime=None):
        mock = MagicMock()
        mock.get_regime.return_value = current_regime
        mock.set_regime = MagicMock()
        mock.set_qc_sizing_multiplier = MagicMock()
        return mock

    def _make_config(self):
        from src.config import Config
        return Config(
            ADMIN_API_KEY="test-api-key-for-testing-only-12345678",
            DATABASE_URL="postgresql://localhost:5432/test",
            REGIME_LLM_MODEL_1="opus",
            REGIME_LLM_MODEL_2="qwen3.5:cloud",
            REGIME_MULTIPLIER_BULL=1.0,
            REGIME_MULTIPLIER_SIDEWAYS=0.7,
            REGIME_MULTIPLIER_BEAR=0.4,
            REGIME_MULTIPLIER_HIGH_VOL=0.2,
            REGIME_REDIS_TTL_SECONDS=90000,
        )

    def _run(self, llm_return, redis, notifier, cfg, vix=18.4, yield_curve=0.3, spy=4.2):
        """Run detect_regime with all dependencies patched (normal path)."""
        with patch("src.workers.regime.RedisStore", return_value=redis), \
             patch("src.workers.regime.TelegramNotifier", return_value=notifier), \
             patch("src.workers.regime._run_llm_pair", new=AsyncMock(return_value=llm_return)), \
             patch("src.workers.regime._make_llm_client", return_value=MagicMock()), \
             patch("src.workers.regime.config", cfg), \
             patch("src.workers.regime.fetch_vix_from_fred", return_value=vix), \
             patch("src.workers.regime.fetch_yield_curve", return_value=yield_curve), \
             patch("src.workers.regime.fetch_spy_momentum_20d", return_value=spy):
            from src.workers.regime import detect_regime
            detect_regime()

    # 1. All signals ok, LLM consensus → regime applied
    def test_consensus_applies_regime(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.BULL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_called_once()
        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bull"
        assert state.multiplier == pytest.approx(1.0)
        assert state.disagreement is False
        redis.set_qc_sizing_multiplier.assert_called_once_with(1.0, ttl=90000)
        # First run (no previous) → Telegram sent
        notifier.send_alert.assert_called_once()

    # 2. LLM disagreement → conservative multiplier, Telegram ⚠️
    def test_disagreement_applies_conservative_regime(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        # bull vs bear → should pick bear (lower multiplier)
        self._run((self.BULL, self.BEAR), redis, notifier, cfg)

        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bear"
        assert state.multiplier == pytest.approx(0.4)
        assert state.disagreement is True
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "Disaccordo" in msg or "bear" in msg.lower()

    # 3. LLM-1 fails → use LLM-2
    def test_one_llm_failure_uses_other(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((None, self.BEAR), redis, notifier, cfg)

        state = redis.set_regime.call_args[0][0]
        assert state.regime == "bear"
        assert state.disagreement is False

    # 4. Both LLMs fail → Redis unchanged, Telegram 🚨
    def test_both_llms_fail_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((None, None), redis, notifier, cfg)

        redis.set_regime.assert_not_called()
        redis.set_qc_sizing_multiplier.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "🚨" in msg

    # 5. data_quality partial → Redis unchanged, Telegram ⚠️
    def test_partial_data_quality_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.PARTIAL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "⚠️" in msg

    # 6. Regime unchanged from previous → no Telegram
    def test_regime_unchanged_no_telegram(self):
        previous = RegimeState(
            regime="bull",
            multiplier=1.0,
            macro_snapshot=MacroSnapshot(vix=15.0, yield_curve=0.3, spy_momentum_20d=4.0),
            llm_outputs=[],
            detected_at=datetime(2026, 5, 4, 7, 0, 0, tzinfo=timezone.utc),
        )
        redis = self._make_redis(current_regime=previous)
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        self._run((self.BULL, self.BULL), redis, notifier, cfg)

        redis.set_regime.assert_called_once()
        notifier.send_alert.assert_not_called()

    # 7. Macro data fetch fails → Redis unchanged, Telegram 🚨
    def test_macro_fetch_failure_no_redis_write(self):
        redis = self._make_redis()
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()
        cfg = self._make_config()

        with patch("src.workers.regime.RedisStore", return_value=redis), \
             patch("src.workers.regime.TelegramNotifier", return_value=notifier), \
             patch("src.workers.regime.config", cfg), \
             patch("src.workers.regime.fetch_vix_from_fred", side_effect=Exception("network error")), \
             patch("src.workers.regime.fetch_yield_curve", return_value=0.3), \
             patch("src.workers.regime.fetch_spy_momentum_20d", return_value=4.2):
            from src.workers.regime import detect_regime
            detect_regime()

        redis.set_regime.assert_not_called()
        notifier.send_alert.assert_called_once()
        msg = notifier.send_alert.call_args[0][0]
        assert "🚨" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/workers/test_regime_worker.py -v
```

Expected: ERROR — `src/workers/regime.py` does not exist.

- [ ] **Step 3: Write minimal implementation**

```python
# src/workers/regime.py
"""RegimeDetector Celery task — daily macro regime classification."""

import asyncio
import logging
from datetime import datetime, timezone

from src.config import config
from src.connectors.macro import fetch_spy_momentum_20d, fetch_vix_from_fred, fetch_yield_curve
from src.models.regime import MacroSnapshot, RegimeLabel, RegimeOutput, RegimeState
from src.notifications.telegram import TelegramNotifier, format_regime_message
from src.store.redis_store import RedisStore
from src.workers.celery_app import app

log = logging.getLogger(__name__)

_REGIME_PROMPT_TEMPLATE = """\
You are a buy-side macro strategist. Analyze the following market data and classify
the current regime into one of: bull, sideways, bear, high_vol.

Market Data:
- VIX: {vix:.1f}  (CBOE Volatility Index)
- Yield Curve (10Y-2Y spread): {yield_curve:.2f}%  (negative = inverted)
- SPY 20d momentum: {spy_momentum:+.1f}%

Quantitative Guidelines (use as anchors, not rigid rules):
- VIX > 30 → high_vol candidate
- T10Y2Y < -0.5% → recession signal (bear)
- SPY 20d < -8% → risk-off (bear)
- SPY 20d in [-3%, +3%] + VIX < 25 → sideways candidate

Reasoning (2 steps max):
1. Classify each signal as bullish/bearish/neutral
2. Synthesize with priority: high_vol > bear > sideways > bull
   Note any signal interactions that justify overriding guidelines.

Output ONLY valid JSON:
{{
  "regime": "bull"|"sideways"|"bear"|"high_vol",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence on macro picture>",
  "data_quality": "complete"|"partial",
  "regime_secondary": "<optional: second-most-likely regime or null>"
}}

Few-shot Examples:

Example 1 (high_vol):
VIX=38, T10Y2Y=-0.8%, SPY=-12%
→ {{"regime": "high_vol", "confidence": 0.92, "reasoning": "Extreme volatility with inverted curve and sharp selloff indicates panic regime", "data_quality": "complete"}}

Example 2 (sideways):
VIX=16, T10Y2Y=+0.4%, SPY=+1.2%
→ {{"regime": "sideways", "confidence": 0.68, "reasoning": "Low volatility and flat momentum suggest range-bound consolidation", "data_quality": "complete", "regime_secondary": "bull"}}

Example 3 (bear):
VIX=24, T10Y2Y=-0.6%, SPY=-7%
→ {{"regime": "bear", "confidence": 0.78, "reasoning": "Inverted yield curve and negative momentum with elevated volatility", "data_quality": "complete"}}"""


def _build_prompt(vix: float, yield_curve: float, spy_momentum: float) -> str:
    return _REGIME_PROMPT_TEMPLATE.format(
        vix=vix, yield_curve=yield_curve, spy_momentum=spy_momentum
    )


def _make_llm_client(model_id: str):
    """Instantiate an LLM client by model_id string."""
    from src.llm.client import DeepseekClient, OpusClient, Qwen35Client

    registry = {
        "opus": OpusClient,
        "qwen3.5:cloud": Qwen35Client,
        "deepseek-v4-pro:cloud": DeepseekClient,
    }
    cls = registry.get(model_id)
    if cls is None:
        raise ValueError(
            f"Unknown model_id {model_id!r}. Available: {sorted(registry)}"
        )
    return cls()


async def _run_llm_pair(
    prompt: str, client1, client2
) -> tuple[RegimeOutput | None, RegimeOutput | None]:
    """Run two LLM clients in parallel. Returns None for any that fail."""
    results = await asyncio.gather(
        client1.complete(prompt, RegimeOutput),
        client2.complete(prompt, RegimeOutput),
        return_exceptions=True,
    )
    r1 = results[0] if not isinstance(results[0], BaseException) else None
    r2 = results[1] if not isinstance(results[1], BaseException) else None
    if isinstance(results[0], BaseException):
        log.warning("LLM-1 failed in regime detection: %s", results[0])
    if isinstance(results[1], BaseException):
        log.warning("LLM-2 failed in regime detection: %s", results[1])
    return r1, r2


@app.task(name="src.workers.regime.detect_regime")
def detect_regime() -> None:
    """Classify daily macro regime and update qc:sizing_multiplier in Redis.

    Guardrail cascade:
      - Macro fetch fails → no Redis write, Telegram 🚨
      - Both LLMs fail → no Redis write, Telegram 🚨
      - data_quality partial → no Redis write, Telegram ⚠️
      - Disagreement → conservative (lower) multiplier, Telegram ⚠️ on change
      - Consensus → apply regime, Telegram 📊 only if regime changed
    """
    redis = RedisStore()
    notifier = TelegramNotifier()

    # 1. Fetch macro data
    try:
        vix = fetch_vix_from_fred(
            series_id=config.AUTO_APPLY_VIX_FRED_SERIES,
            api_key=config.FRED_API_KEY,
        )
        yield_curve = fetch_yield_curve(api_key=config.FRED_API_KEY)
        spy_momentum = fetch_spy_momentum_20d()
    except Exception as e:
        log.error("Failed to fetch macro data for regime detection: %s", e)
        asyncio.run(notifier.send_alert(
            "🚨 RegimeDetector fallito — dati macro non disponibili. Regime invariato.",
            level="error",
        ))
        return

    # 2. Run 2 LLMs in parallel
    prompt = _build_prompt(vix, yield_curve, spy_momentum)
    client1 = _make_llm_client(config.REGIME_LLM_MODEL_1)
    client2 = _make_llm_client(config.REGIME_LLM_MODEL_2)
    r1, r2 = asyncio.run(_run_llm_pair(prompt, client1, client2))

    # CASO 1: both fail
    if r1 is None and r2 is None:
        log.error("Both LLMs failed in detect_regime")
        asyncio.run(notifier.send_alert(
            "🚨 RegimeDetector fallito — regime invariato. Controllare i log.",
            level="error",
        ))
        return

    # CASO 2: one fails — use the other for both
    if r1 is None:
        r1 = r2
    elif r2 is None:
        r2 = r1

    # CASO 3: partial data quality
    if r1.data_quality == "partial" or r2.data_quality == "partial":
        log.warning("Partial data quality in regime detection — skipping Redis write")
        asyncio.run(notifier.send_alert(
            "⚠️ RegimeDetector: dati macro incompleti — regime invariato.",
            level="warning",
        ))
        return

    # CASO 4/5: build multiplier map and apply consensus
    multipliers: dict[str, float] = {
        "bull": config.REGIME_MULTIPLIER_BULL,
        "sideways": config.REGIME_MULTIPLIER_SIDEWAYS,
        "bear": config.REGIME_MULTIPLIER_BEAR,
        "high_vol": config.REGIME_MULTIPLIER_HIGH_VOL,
    }

    disagreement = r1.regime != r2.regime
    if disagreement:
        regime: RegimeLabel = min(r1.regime, r2.regime, key=lambda r: multipliers[r])
    else:
        regime = r1.regime

    multiplier = multipliers[regime]

    # 3. Persist state
    previous = redis.get_regime()
    snapshot = MacroSnapshot(vix=vix, yield_curve=yield_curve, spy_momentum_20d=spy_momentum)
    state = RegimeState(
        regime=regime,
        multiplier=multiplier,
        macro_snapshot=snapshot,
        llm_outputs=[r1.model_dump(), r2.model_dump()],
        disagreement=disagreement,
        detected_at=datetime.now(timezone.utc),
    )

    redis.set_regime(state, ttl=config.REGIME_REDIS_TTL_SECONDS)
    redis.set_qc_sizing_multiplier(multiplier, ttl=config.REGIME_REDIS_TTL_SECONDS)

    # 4. Telegram — only if regime changed or first run
    regime_changed = previous is None or previous.regime != regime
    if regime_changed:
        prev_label = previous.regime if previous else None
        msg = format_regime_message(state, prev_label, disagreement)
        level = "info" if regime in ("bull", "sideways") else "warning"
        asyncio.run(notifier.send_alert(msg, level=level))

    log.info("Regime detected: %s (×%.1f), disagreement=%s", regime, multiplier, disagreement)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/workers/test_regime_worker.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/workers/regime.py tests/workers/test_regime_worker.py
git commit -m "feat: add detect_regime Celery task with VIX/yield-curve/SPY guardrails"
```

---

## Task 7: Wire beat schedule

**Files:**
- Modify: `src/workers/celery_app.py`

- [ ] **Step 1: Add the beat entry**

In `src/workers/celery_app.py`, add the following entry to `app.conf.beat_schedule` after the `"check-suggestion-expiry"` block:

```python
    # Regime detection daily at 07:00 UTC Mon-Fri (pre-market US)
    "regime-detector": {
        "task": "src.workers.regime.detect_regime",
        "schedule": crontab(hour=7, minute=0, day_of_week="1-5"),
    },
```

- [ ] **Step 2: Verify the full test suite still passes**

```bash
pytest tests/ -q
```

Expected: all existing tests pass, no regressions.

- [ ] **Step 3: Commit**

```bash
git add src/workers/celery_app.py
git commit -m "feat: wire detect_regime to Celery beat schedule (07:00 UTC Mon-Fri)"
```

---

## Final check

- [ ] **Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass.
