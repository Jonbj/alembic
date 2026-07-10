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


def _build_budget_tracker() -> tuple[LLMBudgetTracker, "psycopg2.extensions.connection"]:
    """Build a tracker backed by an explicit connection.

    ``LLMBudgetTracker.close()`` is a no-op when a ``conn=`` is passed in (see
    ``src/llm/budget.py``: passing ``conn`` sets ``_owns_connection = False``), so the
    raw connection is returned alongside the tracker and must be closed by the caller —
    mirroring the pattern already used in ``src/workers/sentiment.py``.
    """
    conn = psycopg2.connect(config.DATABASE_URL)
    return LLMBudgetTracker(conn=conn), conn


def main() -> None:
    os.makedirs(os.path.dirname(_OUT), exist_ok=True)
    is_new_file = not os.path.exists(_OUT)
    done = set()
    if not is_new_file:
        with open(_OUT) as f:
            done = {(int(r["label_id"]), r["model"]) for r in csv.DictReader(f)}

    rows = _fetch_labeled_rows()
    print(f"Labeled rows: {len(rows)} — già scorati: {len(done)}")
    budget_tracker, budget_conn = _build_budget_tracker()

    try:
        with open(_OUT, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            if is_new_file:
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
    finally:
        budget_conn.close()
    print(f"Done → {_OUT}")
    _print_summary()


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


if __name__ == "__main__":
    main()
