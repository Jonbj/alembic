# Three-Model Ensemble (Majority-of-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the sentiment ensemble run 3 models with majority-of-3 aggregation: when the full trio diverges, the closest-agreeing pair that passes the divergence check trades and the outlier is persisted as ineligible — converting today's unresolvable 2-model ties (75-80% FinBERT fallback) into decisions.

**Architecture:** Minimal generalization of `EnsembleAggregator.aggregate()` (no new voting scheme), a `deepseek` registry entry, per-model eligibility in `log_llm_responses`, and a configurable/reseedable Ollama semaphore. Activation stays an operator action via the existing Redis selection key — no new feature flags.

**Tech Stack:** Python 3.11, numpy, Redis (Lua for the semaphore), pytest (`.venv/bin/pytest`).

---

## Context (read before Task 1)

Read `CLAUDE.md` and `docs/superpowers/plans/2026-07-11-three-model-ensemble-handoff.md`
(locked decisions D1-D6, Stage 1 model table). Key code facts, verified 2026-07-12:

- `EnsembleAggregator.aggregate()` (`src/llm/ensemble.py:271-312`): filters by
  `min_confidence`, computes `std = np.std(polarities, ddof=1)`, returns `None` when
  `len(eligible) > 1 and std >= divergence_threshold` → caller falls back to FinBERT.
  With 2 models and threshold 0.40, fallback triggers at |Δpolarity| ≥ 0.57 — measured
  bimodal, hence 75-80% fallback.
- Live pair selection: Redis `config:sentiment_llm_models` (now `glm52,gptoss`);
  registry `src/llm/model_registry.py` with `in_all=False` for swap candidates.
  `OllamaDeepseekClient` already exists (`src/llm/client.py:786`) but has NO registry key.
- `PostgreSQLStore.log_llm_responses(signal_id, outputs, min_confidence=0.4,
  force_ineligible=False)` marks eligibility per-output by confidence; caller
  (`src/workers/sentiment.py:~300`) passes `force_ineligible=result.fallback_used`.
- Semaphore: `src/llm/client.py:626` `_OLLAMA_SEM_SLOTS = 2` hardcoded; the Redis token
  pool `ollama:sem` is seeded ONCE via SETNX on `ollama:sem:init` — changing the count
  today requires a manual `redis-cli DEL`.

Constraints:
- Branch `three-model-ensemble-2026-07-12` off `main`. No merge, no deploy, do NOT
  change `config:sentiment_llm_models` — enabling 3-model mode is an operator action.
- Strict TDD. Full suite at the end: only the 10 known pre-existing failures allowed
  (5 `tests/api/test_weight_approval.py`, 3 `tests/workers/test_sec_edgar_ingestion.py`,
  2 `tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading`).
- Do NOT touch the divergence threshold value, FinBERT fallback for the no-majority
  case, or the QS-03 `agreement_weighting` flag (stays default-off).

---

### Task 1: `deepseek` registry entry

**Files:**
- Modify: `src/llm/model_registry.py` (`_MODELS`, `_ALIASES`, `build_sentiment_clients`)
- Test: `tests/llm/test_model_registry.py` (append)

- [ ] **Step 1: Write the failing tests** (append to the existing file)

```python
def test_deepseek_is_selectable():
    _, keys, invalid = normalize_model_selection("glm52,gptoss,deepseek")
    assert invalid == []
    assert set(keys) == {"glm52", "gptoss", "deepseek"}


def test_deepseek_model_id_and_client():
    assert model_ids_for_keys(["deepseek"]) == ["deepseek-v4-pro:cloud"]
    clients = build_sentiment_clients(["deepseek"])
    assert [c.model_id for c in clients] == ["deepseek-v4-pro:cloud"]


def test_all_expansion_still_two_models():
    """deepseek must be in_all=False: registering it must not grow the "all" set."""
    _, keys, _ = normalize_model_selection("all")
    assert set(keys) == {"kimi", "glm52"}
```

- [ ] **Step 2: RED**

Run: `.venv/bin/pytest tests/llm/test_model_registry.py -q`
Expected: first two tests FAIL (`deepseek` invalid token / missing key); third passes.

- [ ] **Step 3: Implement**

In `_MODELS` add (after the gptoss entry):

```python
    SentimentModel("deepseek", "deepseek-v4-pro:cloud", "DeepSeek V4 Pro", in_all=False),
```

In `_ALIASES` add:

```python
    "deepseek-v4-pro": "deepseek",
    "deepseek-v4-pro:cloud": "deepseek",
```

In `build_sentiment_clients`, import `OllamaDeepseekClient` alongside the others and
add `"deepseek": OllamaDeepseekClient,` to the registry dict.

- [ ] **Step 4: GREEN + commit**

Run: `.venv/bin/pytest tests/llm/test_model_registry.py -q` → all PASS.

```bash
git add src/llm/model_registry.py tests/llm/test_model_registry.py
git commit -m "feat(ensemble): register deepseek as selectable third-model candidate (in_all=False)"
```

---

### Task 2: Majority-of-3 in `EnsembleAggregator.aggregate()`

**Files:**
- Modify: `src/llm/ensemble.py:276-280` (divergence check block)
- Test: `tests/llm/test_ensemble.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/llm/test_ensemble.py` (reuse the file's existing `ModelOutput`
construction style — check its imports/helpers at the top and mirror them):

```python
class TestMajorityOfThree:
    def _mk(self, polarity, confidence, model_id):
        return ModelOutput(symbol="AAPL", polarity=polarity, confidence=confidence,
                           reasoning="r", model_id=model_id)

    def test_two_of_three_agree_outlier_dropped(self):
        """Trio std fails, but the closest pair passes → aggregate the pair."""
        agg = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        outputs = [
            self._mk(0.62, 0.8, "glm-5.2:cloud"),
            self._mk(0.58, 0.7, "gpt-oss:20b-cloud"),
            self._mk(-0.70, 0.9, "deepseek-v4-pro:cloud"),  # outlier
        ]
        result = agg.aggregate(outputs)
        assert result is not None
        assert set(result.model_ids) == {"glm-5.2:cloud", "gpt-oss:20b-cloud"}
        assert result.polarity > 0
        # ensemble_std reported is the agreeing PAIR's std, not the trio's.
        assert result.ensemble_std < 0.40

    def test_no_pair_agrees_returns_none(self):
        """Three mutually-divergent outputs → FinBERT fallback (None)."""
        agg = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        outputs = [
            self._mk(0.9, 0.8, "a"),
            self._mk(0.0, 0.8, "b"),
            self._mk(-0.9, 0.8, "c"),
        ]
        assert agg.aggregate(outputs) is None

    def test_two_model_behavior_unchanged(self):
        """With 2 eligible outputs the legacy all-or-nothing check still applies."""
        agg = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        divergent_pair = [self._mk(0.8, 0.8, "a"), self._mk(-0.5, 0.8, "b")]
        assert agg.aggregate(divergent_pair) is None
        agreeing_pair = [self._mk(0.6, 0.8, "a"), self._mk(0.5, 0.7, "b")]
        assert agg.aggregate(agreeing_pair) is not None

    def test_agreeing_trio_uses_all_three(self):
        agg = EnsembleAggregator(min_confidence=0.4, divergence_threshold=0.40)
        outputs = [self._mk(0.6, 0.8, "a"), self._mk(0.5, 0.7, "b"), self._mk(0.55, 0.9, "c")]
        result = agg.aggregate(outputs)
        assert result is not None
        assert len(result.model_ids) == 3
```

- [ ] **Step 2: RED**

Run: `.venv/bin/pytest tests/llm/test_ensemble.py -q -k Majority`
Expected: `test_two_of_three_agree_outlier_dropped` FAILS (aggregate returns None);
the other three pass (they pin current behavior — they are regression guards).

- [ ] **Step 3: Implement**

In `aggregate()`, replace:

```python
        if len(eligible) > 1 and std >= self.divergence_threshold:
            return None
```

with:

```python
        if len(eligible) > 1 and std >= self.divergence_threshold:
            if len(eligible) != 3:
                return None
            # Majority-of-3 (D1, 2026-07-11 handoff brief): when the trio diverges,
            # the closest-agreeing pair trades if it passes the divergence check on
            # its own; the outlier is dropped (persisted as ineligible by the
            # caller via AggregatedResult.model_ids). No pair agreeing → fallback.
            pairs = [
                (eligible[i], eligible[j])
                for i in range(len(eligible))
                for j in range(i + 1, len(eligible))
            ]
            a, b = min(pairs, key=lambda p: abs(p[0].polarity - p[1].polarity))
            pair_std = float(np.std([a.polarity, b.polarity], ddof=1))
            if pair_std >= self.divergence_threshold:
                return None
            eligible = [a, b]
            std = pair_std
```

(The rest of the method — weighting, confidence, `model_ids=[o.model_id for o in
eligible]`, `ensemble_std=std` — is untouched and now naturally reports the pair.)

Update the class docstring's Step 4 description to mention the majority-of-3 branch.

- [ ] **Step 4: GREEN + commit**

Run: `.venv/bin/pytest tests/llm/test_ensemble.py -q` → all PASS.

```bash
git add src/llm/ensemble.py tests/llm/test_ensemble.py
git commit -m "feat(ensemble): majority-of-3 aggregation — closest agreeing pair trades, outlier dropped"
```

---

### Task 3: Outlier persisted as ineligible

**Files:**
- Modify: `src/store/pg_store.py` (`log_llm_responses`)
- Modify: `src/workers/sentiment.py` (the `log_llm_responses` call, ~line 300)
- Test: `tests/store/test_pg_news_llm.py` (append) + `tests/workers/test_sentiment_worker.py` (append)

- [ ] **Step 1: Failing store test** (append to `TestLogLlmResponses`)

```python
    def test_log_llm_responses_eligible_model_ids_filter(self, pg_store):
        """Majority-of-3: only models that entered the consensus are eligible —
        the dropped outlier must be ineligible even with high confidence."""
        outputs = [
            ModelOutput(symbol="AAPL", polarity=0.6, confidence=0.8,
                        reasoning="in", model_id="glm-5.2:cloud"),
            ModelOutput(symbol="AAPL", polarity=-0.7, confidence=0.9,
                        reasoning="outlier", model_id="deepseek-v4-pro:cloud"),
        ]
        pg_store.log_llm_responses(
            signal_id=7, outputs=outputs, eligible_model_ids={"glm-5.2:cloud"},
        )
        _, batch = pg_store._conn.cursor.return_value.executemany.call_args[0]
        batch = list(batch)
        assert batch[0][5] is True    # in consensus, confidence >= 0.4
        assert batch[1][5] is False   # outlier: high confidence but NOT eligible
```

- [ ] **Step 2: RED**

Run: `.venv/bin/pytest tests/store/test_pg_news_llm.py -q -k eligible_model_ids`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'eligible_model_ids'`.

- [ ] **Step 3: Implement in `log_llm_responses`**

Add parameter `eligible_model_ids: set[str] | None = None` (after
`force_ineligible`). Docstring addition: "When provided, a row is eligible only if
its model_id is in the set AND passes the confidence filter (majority-of-3: the
dropped outlier is persisted for audit but must not count as a contributor)."
Eligibility expression becomes:

```python
                            False if force_ineligible else (
                                out.confidence >= min_confidence
                                and (eligible_model_ids is None
                                     or out.model_id in eligible_model_ids)
                            ),
```

- [ ] **Step 4: Failing caller test** (append to `tests/workers/test_sentiment_worker.py`,
mirroring the structure of `test_ensemble_divergence_uses_finbert_fallback`: same mocks,
but `mock_aggregator.aggregate` returns an `AggregatedResult`-like MagicMock with
`model_ids=["glm-5.2:cloud", "gpt-oss:20b-cloud"]`, `polarity=0.6`, `confidence=0.75`,
`reasoning="ok"`, `ensemble_std=0.05`; `run_ensemble_query` returns 3 mock outputs)

```python
    @pytest.mark.asyncio
    async def test_success_path_passes_consensus_model_ids_to_log(self):
        """log_llm_responses must receive eligible_model_ids=set(aggregated.model_ids)
        so a majority-of-3 outlier is persisted as ineligible."""
        # ... build mocks as in test_ensemble_divergence_uses_finbert_fallback,
        # with aggregate returning the successful MagicMock described above ...
        # after process_news_item:
        _kwargs = mock_pg.log_llm_responses.call_args.kwargs
        assert _kwargs["eligible_model_ids"] == {"glm-5.2:cloud", "gpt-oss:20b-cloud"}
        assert _kwargs["force_ineligible"] is False
```

Write the full test by copying the divergence test's scaffolding (mock budget,
mock finbert, mock stores, `make_news_item`) — only the aggregator return and the
final assertions differ. RED first (`call_args.kwargs` lacks the key), then:

- [ ] **Step 5: Implement in `sentiment.py`**

At the `log_llm_responses` call site:

```python
        if raw_outputs:
            # On fallback the raw outputs did NOT enter the signal (FinBERT did);
            # on success, only the consensus models (majority-of-3 may have
            # dropped an outlier) count as contributors.
            pg_store.log_llm_responses(
                signal_id=signal_id,
                outputs=raw_outputs,
                force_ineligible=result.fallback_used,
                eligible_model_ids=(
                    None if result.fallback_used
                    else set(result.model_id.removeprefix("ensemble:").split("+"))
                ),
            )
```

CAREFUL: `result.model_id` is `f"ensemble:{'+'.join(aggregated.model_ids)}"` — the
`removeprefix`/`split` above reconstructs the set. If you find this too indirect,
the cleaner alternative is to thread `aggregated.model_ids` through `run_inference`'s
return value — but that changes its signature and every test that unpacks it; the
string reconstruction is the minimal change and is covered by the Step-4 test.
Pick ONE and make the Step-4 test pass.

- [ ] **Step 6: GREEN + commit**

Run: `.venv/bin/pytest tests/store/test_pg_news_llm.py tests/workers/test_sentiment_worker.py tests/llm/ -q`
Expected: PASS except the 2 known `TestEnsembleWeightReading` failures.

```bash
git add src/store/pg_store.py src/workers/sentiment.py tests/store/test_pg_news_llm.py tests/workers/test_sentiment_worker.py
git commit -m "feat(ensemble): persist majority-of-3 outlier as ineligible via eligible_model_ids"
```

---

### Task 4: Configurable, self-reseeding Ollama semaphore

**Files:**
- Modify: `src/llm/client.py:626-684` (`_OLLAMA_SEM_SLOTS`, `_OllamaSemaphore._ensure_slots`)
- Test: `tests/llm/test_ollama_semaphore.py` (new)

- [ ] **Step 1: Failing tests**

Create `tests/llm/test_ollama_semaphore.py`:

```python
"""Ollama semaphore: env-configurable slot count with automatic pool reseed."""
import os
from unittest.mock import MagicMock, patch

from src.llm.client import _OllamaSemaphore


def test_slots_configurable_via_env():
    with patch.dict(os.environ, {"OLLAMA_SEM_SLOTS": "3"}):
        import importlib
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        try:
            assert client_mod._OLLAMA_SEM_SLOTS == 3
        finally:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OLLAMA_SEM_SLOTS", None)
                importlib.reload(client_mod)


def test_ensure_slots_reseeds_on_size_change():
    """The Lua script must DEL the pool + init flag when the stored size differs
    from the configured slot count — otherwise a config change silently keeps the
    old capacity (the SETNX-once init would never re-run)."""
    sem = _OllamaSemaphore(key="ollama:sem:test", slots=3)
    r = MagicMock()
    sem._ensure_slots(r)
    lua = r.eval.call_args[0][0]
    assert "DEL" in lua            # reseed branch exists
    keys_count = r.eval.call_args[0][1]
    assert keys_count == 3         # pool key, init flag, size key
```

- [ ] **Step 2: RED**

Run: `.venv/bin/pytest tests/llm/test_ollama_semaphore.py -q`
Expected: FAIL (`_OLLAMA_SEM_SLOTS` not env-driven; Lua has no size key / DEL branch).

- [ ] **Step 3: Implement**

```python
_OLLAMA_SEM_SLOTS = int(os.environ.get("OLLAMA_SEM_SLOTS", "2"))
# Default 2 = today's 2-model live ensemble. Set OLLAMA_SEM_SLOTS=3 (compose env
# for worker-inference) when enabling the 3-model selection. The pool self-reseeds
# on size change (see _ensure_slots) — no manual redis-cli DEL needed.
```

(`import os` is already present at the top of client.py — verify, add if not.)

In `_OllamaSemaphore.__init__` add `self._size_key = key + ":size"`.
Replace `_ensure_slots` with:

```python
    def _ensure_slots(self, r) -> None:
        # Reseed when the configured slot count changed: DEL pool + init flag,
        # store the new size, then the SETNX-once init repopulates. NOTE: a DEL
        # while a worker holds a token transiently over-issues by that token for
        # one cycle — acceptable at config-change time (worker-inference has
        # concurrency=1 and changes happen at deploy).
        lua = """
        local size = redis.call('GET', KEYS[3])
        if size ~= ARGV[1] then
            redis.call('DEL', KEYS[1], KEYS[2])
            redis.call('SET', KEYS[3], ARGV[1])
        end
        if redis.call('SETNX', KEYS[2], '1') == 1 then
            for i = 1, tonumber(ARGV[1]) do
                redis.call('RPUSH', KEYS[1], ARGV[2])
            end
        end
        return redis.call('LLEN', KEYS[1])
        """
        r.eval(lua, 3, self._key, self._init_key, self._size_key,
               str(self._slots), self._SLOT)
```

- [ ] **Step 4: GREEN + commit**

Run: `.venv/bin/pytest tests/llm/test_ollama_semaphore.py tests/llm/test_ollama_timeout.py -q`
Expected: PASS.

```bash
git add src/llm/client.py tests/llm/test_ollama_semaphore.py
git commit -m "feat(llm): OLLAMA_SEM_SLOTS env config with self-reseeding Redis pool"
```

---

### Task 5: Full suite + report

- [ ] **Step 1:** `.venv/bin/pytest -q` → only the 10 known pre-existing failures.

- [ ] **Step 2:** Budget projection (report only, no code): 3 models ≈ +50% Ollama
calls (~270/day). deepseek-v4-pro cost in `src/config.py` is (4.0, 12.0) per 1M
tokens — the priciest of the pool. Estimate daily cost at ~600 tokens in / ~200 out
per call and compare with the `llm_budget` limits; put the number in your report.

- [ ] **Step 3:** Final report: branch + commits, test counts, budget estimate, and
confirm you did NOT touch `config:sentiment_llm_models`, env files, or any deploy.

---

## Operator rollout after review (NOT for the implementing agent)

1. Merge; add `OLLAMA_SEM_SLOTS=3` to the worker-inference environment in
   `docker-compose.yml`; `docker compose build worker worker-inference beat api && up -d`.
2. Enable: `docker exec alembic-redis-1 redis-cli SET config:sentiment_llm_models "glm52,gptoss,deepseek"`.
3. Rollback: set the key back to `glm52,gptoss` (semaphore can stay at 3).
4. D6 success metrics (7 trading days): fallback rate < 30%; no sentiment-beat
   overrun; tradeable S4 signals ≥ 3× the 2-model baseline.
