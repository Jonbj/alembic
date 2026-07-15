# Model Comparison — Stage 1 (Retrospective Screen) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resumable offline script that scores the 17 human-labeled
`news_labels` rows with 5 candidate sentiment models (Kimi K2.6, GLM-5.2, gpt-oss:20b,
qwen3.5, deepseek-v4-pro) and reports directional accuracy vs `gt_sentiment_dir` and
JSON-parse reliability per model — a cheap, indicative-only sanity check before the
real measurement in Stage 2 (separate plan).

**Architecture:** A single standalone script, `scripts/compare_models_retro.py`,
mirroring the existing `scripts/score_s7_transcripts.py` pattern (raw `httpx` calls,
no dependency on the live async `OllamaCloudClient`/Redis semaphore — this is a slow,
sequential, one-off batch with no concurrency and no interaction with the live
pipeline). Reuses `_DK_COT_PROMPT` from `src/workers/sentiment.py` and
`LLMClient.parse_json_response` from `src/llm/client.py` — never duplicates them.
Spend is tracked via the existing `LLMBudgetTracker` so cost is measured, not assumed.
Results accumulate in a resumable CSV; a summary function prints a markdown table.

**Tech Stack:** Python, `httpx` (already a dependency, used by `score_s7_transcripts.py`),
`psycopg2` (already used throughout `src/store/pg_store.py`), `csv`/`asyncio` stdlib,
`pytest`.

---

### Task 1: `_direction()` and `_score_one()` — pure scoring helpers

**Files:**
- Create: `scripts/compare_models_retro.py`
- Test: `tests/test_compare_models_retro.py`

- [x] **Step 1: Write the failing tests**

```python
# tests/test_compare_models_retro.py
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.compare_models_retro import _direction, _score_one


def test_direction_positive():
    assert _direction(0.5) == "positive"


def test_direction_negative():
    assert _direction(-0.3) == "negative"


def test_direction_neutral_inside_deadzone():
    assert _direction(0.05) == "neutral"
    assert _direction(-0.05) == "neutral"
    assert _direction(0.0) == "neutral"


def test_score_one_success():
    raw = '{"polarity": 0.4, "confidence": 0.7, "reasoning": "x"}'
    with patch("scripts.compare_models_retro._call", return_value=(raw, 1234)):
        result = _score_one("kimi-k2.6:cloud", "irrelevant prompt")
    assert result == {
        "polarity": 0.4,
        "confidence": 0.7,
        "parse_error": False,
        "latency_ms": 1234,
        "output_chars": len(raw),
    }


def test_score_one_retries_once_then_succeeds():
    raw = '{"polarity": -0.2, "confidence": 0.5, "reasoning": "x"}'
    calls = [RuntimeError("boom"), (raw, 500)]

    def fake_call(model, prompt):
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("scripts.compare_models_retro._call", side_effect=fake_call), \
         patch("scripts.compare_models_retro.time.sleep"):
        result = _score_one("glm-5.2:cloud", "irrelevant prompt")
    assert result == {
        "polarity": -0.2,
        "confidence": 0.5,
        "parse_error": False,
        "latency_ms": 500,
        "output_chars": len(raw),
    }


def test_score_one_fails_both_attempts():
    with patch("scripts.compare_models_retro._call", side_effect=RuntimeError("boom")), \
         patch("scripts.compare_models_retro.time.sleep"):
        result = _score_one("qwen3.5:cloud", "irrelevant prompt")
    assert result == {
        "polarity": 0.0,
        "confidence": 0.0,
        "parse_error": True,
        "latency_ms": 0,
        "output_chars": 0,
    }
```

- [x] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.compare_models_retro'`
(the file doesn't exist yet).

- [x] **Step 3: Write the script with `_direction()` and `_score_one()`**

```python
#!/usr/bin/env python3
"""Stage 1: retrospective screen of candidate sentiment models against the QX-01
golden label set (news_labels, status='labeled').

Indicative only: 17 labeled rows today (2026-07-09), no forward_return computed yet.
Checks directional accuracy vs gt_sentiment_dir and JSON-parse reliability, NOT IC —
the real IC-based ranking comes from Stage 2 (shadow mode on live traffic, see
docs/superpowers/specs/2026-07-09-ensemble-model-comparison-design.md).

Does not use the live async OllamaCloudClient / Redis semaphore: this is a slow,
sequential, one-off batch with no concurrency, fully decoupled from the live worker.

Run: set -a; source .env; set +a; .venv/bin/python scripts/compare_models_retro.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
import time

import httpx
import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import config  # noqa: E402
from src.llm.budget import LLMBudgetTracker  # noqa: E402
from src.llm.client import LLMClient  # noqa: E402
from src.workers.sentiment import _DK_COT_PROMPT  # noqa: E402

_MODELS = [
    "kimi-k2.6:cloud",
    "glm-5.2:cloud",
    "gpt-oss:20b-cloud",
    "qwen3.5:cloud",
    "deepseek-v4-pro:cloud",
]
_BASE = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com")
_OUT = "reports/model_comparison/stage1_retro.csv"
_FIELDS = [
    "label_id", "model", "polarity", "confidence", "gt_sentiment_dir",
    "predicted_dir", "correct", "parse_error", "latency_ms",
]


def _call(model: str, prompt: str) -> tuple[str, int]:
    """POST to Ollama cloud /api/chat. Returns (raw_content, latency_ms). Raises on error."""
    key = os.environ.get("OLLAMA_API_KEY", "")
    if not key:
        raise RuntimeError("OLLAMA_API_KEY not set")
    start = time.monotonic()
    r = httpx.post(
        f"{_BASE}/api/chat",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "stream": False,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=180.0,
    )
    r.raise_for_status()
    latency_ms = int((time.monotonic() - start) * 1000)
    return r.json()["message"]["content"], latency_ms


def _direction(polarity: float) -> str:
    """Map a polarity score to a direction label, matching gt_sentiment_dir's vocabulary."""
    if polarity > 0.1:
        return "positive"
    if polarity < -0.1:
        return "negative"
    return "neutral"


def _score_one(model: str, prompt: str) -> dict:
    """Call `model` with `prompt`, retrying once on any failure. Never raises."""
    for attempt in range(2):
        try:
            raw, latency_ms = _call(model, prompt)
            json_str = LLMClient.parse_json_response(raw)
            parsed = json.loads(json_str)
            return {
                "polarity": float(parsed["polarity"]),
                "confidence": float(parsed["confidence"]),
                "parse_error": False,
                "latency_ms": latency_ms,
                "output_chars": len(raw),
            }
        except Exception as exc:
            print(f"  {model}: tentativo {attempt + 1} fallito: {exc}")
            if attempt == 0:
                time.sleep(2)
    return {
        "polarity": 0.0, "confidence": 0.0, "parse_error": True,
        "latency_ms": 0, "output_chars": 0,
    }
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py -v`
Expected: PASS (6 tests)

- [x] **Step 5: Commit**

```bash
git add scripts/compare_models_retro.py tests/test_compare_models_retro.py
git commit -m "feat(model-comparison): stage 1 scoring helpers (_direction, _score_one)"
```

---

### Task 2: fetch labeled rows + resumable main loop + budget tracking

**Files:**
- Modify: `scripts/compare_models_retro.py`
- Test: `tests/test_compare_models_retro.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_compare_models_retro.py`:

```python
class _NoopTracker:
    """Fake LLMBudgetTracker — records calls without touching Postgres."""

    def __init__(self):
        self.recorded = []

    async def record_spending(self, model_id, input_tokens, output_tokens):
        self.recorded.append((model_id, input_tokens, output_tokens))
        return 0.0

    def close(self):
        pass


def test_main_skips_already_scored_pairs_and_records_spend(tmp_path, monkeypatch):
    import scripts.compare_models_retro as mod

    out_path = tmp_path / "stage1_retro.csv"
    # Pre-existing CSV: label 1 already scored for kimi-k2.6:cloud only.
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=mod._FIELDS)
        w.writeheader()
        w.writerow({
            "label_id": 1, "model": "kimi-k2.6:cloud", "polarity": 0.2,
            "confidence": 0.6, "gt_sentiment_dir": "positive",
            "predicted_dir": "positive", "correct": True,
            "parse_error": False, "latency_ms": 900,
        })
    monkeypatch.setattr(mod, "_OUT", str(out_path))
    monkeypatch.setattr(mod, "_MODELS", ["kimi-k2.6:cloud", "glm-5.2:cloud"])
    monkeypatch.setattr(
        mod, "_fetch_labeled_rows",
        lambda: [{
            "label_id": 1, "body_snippet": "Some news body",
            "gt_tickers": ["AAPL"], "extracted_tickers": [],
            "gt_sentiment_dir": "positive",
        }],
    )
    calls = []

    def fake_score_one(model, prompt):
        calls.append(model)
        return {
            "polarity": 0.3, "confidence": 0.5, "parse_error": False,
            "latency_ms": 100, "output_chars": 200,
        }

    monkeypatch.setattr(mod, "_score_one", fake_score_one)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    tracker = _NoopTracker()
    monkeypatch.setattr(mod, "_build_budget_tracker", lambda: tracker)

    mod.main()

    # label 1 / kimi already done -> must NOT be re-scored.
    assert calls == ["glm-5.2:cloud"]
    with open(out_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2  # the pre-existing row + the new glm-5.2 row
    # Spend recorded only for the one new (uncached) call.
    assert len(tracker.recorded) == 1
    model_id, input_tokens, output_tokens = tracker.recorded[0]
    assert model_id == "glm-5.2:cloud"
    assert input_tokens > 0
    assert output_tokens == 200 // 4
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py::test_main_skips_already_scored_pairs_and_records_spend -v`
Expected: FAIL with `AttributeError: module 'scripts.compare_models_retro' has no attribute '_fetch_labeled_rows'`

- [x] **Step 3: Add `_fetch_labeled_rows()`, `_build_budget_tracker()` and `main()`**

Append to `scripts/compare_models_retro.py`:

```python
def _fetch_labeled_rows() -> list[dict]:
    """Return all news_labels rows with status='labeled', oldest first."""
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT label_id, body_snippet, gt_tickers, extracted_tickers, "
                "gt_sentiment_dir FROM news_labels WHERE status = 'labeled' "
                "ORDER BY label_id"
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def _build_budget_tracker() -> LLMBudgetTracker:
    conn = psycopg2.connect(config.DATABASE_URL)
    return LLMBudgetTracker(conn=conn)


def main() -> None:
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    done = set()
    if os.path.exists(_OUT):
        with open(_OUT) as f:
            done = {(int(r["label_id"]), r["model"]) for r in csv.DictReader(f)}
    new_file = not done

    rows = _fetch_labeled_rows()
    print(f"Labeled rows: {len(rows)} — già scorati: {len(done)}")
    budget_tracker = _build_budget_tracker()

    with open(_OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for row in rows:
            tickers = row["gt_tickers"] or row["extracted_tickers"] or []
            symbol = tickers[0] if tickers else "UNKNOWN"
            prompt = _DK_COT_PROMPT.format(text=(row["body_snippet"] or "")[:600], symbol=symbol)
            for model in _MODELS:
                key = (row["label_id"], model)
                if key in done:
                    continue
                result = _score_one(model, prompt)
                if not result["parse_error"]:
                    asyncio.run(budget_tracker.record_spending(
                        model_id=model,
                        input_tokens=len(prompt) // 4,
                        output_tokens=result["output_chars"] // 4,
                    ))
                predicted_dir = _direction(result["polarity"]) if not result["parse_error"] else ""
                correct = (
                    predicted_dir == row["gt_sentiment_dir"] if not result["parse_error"] else False
                )
                w.writerow({
                    "label_id": row["label_id"], "model": model,
                    "polarity": result["polarity"], "confidence": result["confidence"],
                    "gt_sentiment_dir": row["gt_sentiment_dir"],
                    "predicted_dir": predicted_dir, "correct": correct,
                    "parse_error": result["parse_error"], "latency_ms": result["latency_ms"],
                })
                f.flush()
                time.sleep(1)
    budget_tracker.close()
    print(f"Done → {_OUT}")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py -v`
Expected: PASS (7 tests)

- [x] **Step 5: Commit**

```bash
git add scripts/compare_models_retro.py tests/test_compare_models_retro.py
git commit -m "feat(model-comparison): stage 1 resumable main loop with budget tracking"
```

---

### Task 3: summary report

**Files:**
- Modify: `scripts/compare_models_retro.py`
- Test: `tests/test_compare_models_retro.py`

- [x] **Step 1: Write the failing test**

Append to `tests/test_compare_models_retro.py`:

```python
def test_summary_computes_accuracy_and_parse_fail_rate(tmp_path, monkeypatch, capsys):
    import scripts.compare_models_retro as mod

    out_path = tmp_path / "stage1_retro.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=mod._FIELDS)
        w.writeheader()
        w.writerow({"label_id": 1, "model": "kimi-k2.6:cloud", "polarity": 0.3,
                     "confidence": 0.6, "gt_sentiment_dir": "positive",
                     "predicted_dir": "positive", "correct": True,
                     "parse_error": False, "latency_ms": 900})
        w.writerow({"label_id": 2, "model": "kimi-k2.6:cloud", "polarity": 0.1,
                     "confidence": 0.4, "gt_sentiment_dir": "negative",
                     "predicted_dir": "neutral", "correct": False,
                     "parse_error": False, "latency_ms": 700})
        w.writerow({"label_id": 3, "model": "kimi-k2.6:cloud", "polarity": 0.0,
                     "confidence": 0.0, "gt_sentiment_dir": "positive",
                     "predicted_dir": "", "correct": False,
                     "parse_error": True, "latency_ms": 0})
    monkeypatch.setattr(mod, "_OUT", str(out_path))
    monkeypatch.setattr(mod, "_MODELS", ["kimi-k2.6:cloud"])

    mod._print_summary()

    out = capsys.readouterr().out
    assert "kimi-k2.6:cloud" in out
    assert "0.50" in out  # accuracy: 1 correct / 2 parsed
    assert "0.33" in out  # parse_fail_rate: 1/3
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py::test_summary_computes_accuracy_and_parse_fail_rate -v`
Expected: FAIL with `AttributeError: module 'scripts.compare_models_retro' has no attribute '_print_summary'`

- [x] **Step 3: Add `_print_summary()` and call it from `main()`**

Append to `scripts/compare_models_retro.py` (before the `if __name__ == "__main__":` line):

```python
def _print_summary() -> None:
    """Print a markdown table: accuracy, parse-failure rate, confidence, latency per model."""
    import statistics

    with open(_OUT) as f:
        rows = list(csv.DictReader(f))

    print("\n| model | n | accuracy | parse_fail_rate | avg_confidence | avg_latency_ms |")
    print("|---|---|---|---|---|---|")
    for model in _MODELS:
        model_rows = [r for r in rows if r["model"] == model]
        if not model_rows:
            continue
        n = len(model_rows)
        parsed_ok = [r for r in model_rows if r["parse_error"] == "False"]
        accuracy = (
            sum(1 for r in parsed_ok if r["correct"] == "True") / len(parsed_ok)
            if parsed_ok else 0.0
        )
        parse_fail_rate = 1 - len(parsed_ok) / n
        avg_conf = statistics.mean(float(r["confidence"]) for r in parsed_ok) if parsed_ok else 0.0
        latencies = [float(r["latency_ms"]) for r in model_rows if float(r["latency_ms"]) > 0]
        avg_latency = statistics.mean(latencies) if latencies else 0.0
        print(f"| {model} | {n} | {accuracy:.2f} | {parse_fail_rate:.2f} | {avg_conf:.2f} | {avg_latency:.0f} |")
```

Then change the end of `main()` from:
```python
    budget_tracker.close()
    print(f"Done → {_OUT}")


if __name__ == "__main__":
    main()
```
to:
```python
    budget_tracker.close()
    print(f"Done → {_OUT}")
    _print_summary()


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_compare_models_retro.py -v`
Expected: PASS (8 tests)

- [x] **Step 5: Commit**

```bash
git add scripts/compare_models_retro.py
git commit -m "feat(model-comparison): stage 1 markdown summary report"
```

---

### Task 4: run it

**Files:** none (execution only)

- [x] **Step 1: Run the script against the live database**

Run: `set -a; source .env; set +a; .venv/bin/python scripts/compare_models_retro.py`

Expected: prints `Labeled rows: 17 — già scorati: 0`, then scores 17 × 5 = 85
(label_id, model) pairs (~2-3 min given the 1s pacing + retries), then prints the
markdown summary table. Verify no unhandled exception. If interrupted, rerunning the
same command must resume (skip already-scored pairs per Task 2's cache) — confirm by
checking the printed "già scorati" count on a second run.

- [x] **Step 2: Read the summary table and flag anything unexpected**

Look for: any model with `parse_fail_rate > 0.2` (worth a closer look at its raw
output), or an `accuracy` far below/above the others (small-n=17 means don't
over-read a single-digit-point difference). Report findings back — this step
produces no commit, it's the actual deliverable of Stage 1.
