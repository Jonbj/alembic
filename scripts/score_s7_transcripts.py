#!/usr/bin/env python3
"""POC-2b: tone scoring dei transcript via Ollama Cloud (kimi-k2.6:cloud).

DK-CoT (CLAUDE.md): ruolo analista buy-side, ragionamento su guidance/cash flow/
competizione, bull/bear case, output JSON. score = tone_polarity × confidence.
Costo bounded: max 24k char/transcript, 1 chiamata/evento (+retry), sleep 1s
(condividiamo la quota Ollama col sentiment worker live — lanciare fuori orario 14–21 UTC).
Output incrementale su reports/s7_poc/tone_scores.csv → rilanciabile, salta i già scorati.

Run: set -a; source .env; set +a; .venv/bin/python scripts/score_s7_transcripts.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.s7_poc_helpers import parse_tone_json  # noqa: E402
from src.text.sanitizer import sanitize_text  # noqa: E402

_MODEL = os.environ.get("TONE_MODEL", "kimi-k2.6:cloud")
_BASE = os.environ.get("OLLAMA_BASE_URL", "https://ollama.com")
_MAX_CHARS = 24_000
_OUT = "reports/s7_poc/tone_scores.csv"
_FIELDS = ["symbol", "event_date", "model", "tone_polarity", "confidence",
           "guidance", "score", "key_evidence"]

_PROMPT = """Act as a buy-side equity analyst reviewing an earnings call transcript.

Step by step, reason about: (1) guidance — did management raise, maintain, or lower
forward guidance, explicitly or implicitly? (2) cash flow and margins trajectory;
(3) competitive position and demand signals; (4) management tone — confident and
specific vs evasive and hedging (watch for non-answers in Q&A).

Example (analogical): a company beating EPS but guiding down and dodging margin
questions in Q&A → negative tone despite the beat (tone_polarity ≈ -0.4).
A company with an in-line quarter but raised guidance and specific, confident
answers → positive tone (tone_polarity ≈ +0.5).

State the bull case, then the bear case. Then output ONLY a JSON object:
{{"tone_polarity": <float -1..1>, "confidence": <float 0..1>,
 "guidance": "raised"|"maintained"|"lowered"|"none",
 "key_evidence": "<one sentence>"}}

TRANSCRIPT ({symbol}, fiscal quarter {date}):
{text}"""
# NB: le doppie graffe {{ }} nel blocco JSON sono obbligatorie — _PROMPT.format()
# le collassa a graffe singole; graffe singole causerebbero KeyError.


def _call(prompt: str) -> str:
    key = os.environ.get("OLLAMA_API_KEY", "")
    if not key:
        raise RuntimeError("OLLAMA_API_KEY not set")
    r = httpx.post(f"{_BASE}/api/chat",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": _MODEL, "stream": False,
                         "messages": [{"role": "user", "content": prompt}]},
                   timeout=180.0)
    r.raise_for_status()
    return r.json()["message"]["content"]


def main() -> None:
    done = set()
    if os.path.exists(_OUT):
        with open(_OUT) as f:
            done = {(r["symbol"], r["event_date"], r["model"]) for r in csv.DictReader(f)}
    new_file = not done

    files = sorted(glob.glob("reports/s7_poc/transcripts/*.json"))
    print(f"Transcript in cache: {len(files)} — già scorati ({_MODEL}): {len(done)}")

    with open(_OUT, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_FIELDS)
        if new_file:
            w.writeheader()
        for i, path in enumerate(files):
            with open(path) as tf:
                t = json.load(tf)
            k = (t["symbol"], t["event_date"], _MODEL)
            if k in done:
                continue
            text = sanitize_text(t["content"])[:_MAX_CHARS]
            prompt = _PROMPT.format(symbol=t["symbol"], date=t["quarter"], text=text)
            parsed = None
            for attempt in range(2):
                try:
                    parsed = parse_tone_json(_call(prompt))
                    if parsed:
                        break
                except Exception as exc:
                    print(f"  {t['symbol']} {t['event_date']}: tentativo {attempt + 1} fallito: {exc}")
                    time.sleep(3)
            if parsed:
                w.writerow({"symbol": t["symbol"], "event_date": t["event_date"],
                            "model": _MODEL, **{k2: parsed[k2] for k2 in
                            ("tone_polarity", "confidence", "guidance", "score", "key_evidence")}})
                f.flush()
            else:
                print(f"  SKIP {t['symbol']} {t['event_date']}: nessun JSON valido")
            time.sleep(1)
            if (i + 1) % 10 == 0:
                print(f"  ...{i + 1}/{len(files)}")
    print(f"Done → {_OUT}")


if __name__ == "__main__":
    main()
