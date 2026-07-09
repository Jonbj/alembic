#!/usr/bin/env python3
"""Stage 1: retrospective screen of candidate sentiment models against the QX-01
golden label set (news_labels, status='labeled').

Indicative only: 17 labeled rows today (2026-07-09), no forward_return computed yet.
Checks directional accuracy vs gt_sentiment_dir and JSON-parse reliability, NOT IC —
the real IC-based ranking comes from Stage 2 (shadow mode on live traffic, see
docs/superpowers/specs/2026-07-09-ensemble-model-comparison-design.md).

Does not use the live async OllamaCloudClient / Redis semaphore: this is a slow,
sequential, one-off batch with no concurrency, fully decoupled from the live worker.

Imports below (asyncio, csv, psycopg2, LLMBudgetTracker, _DK_COT_PROMPT, config) are used
starting in Task 2's main() loop; this task only adds _call/_direction/_score_one.

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
