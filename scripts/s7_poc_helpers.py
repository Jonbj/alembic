"""Pure helpers for the S7 revival POCs (small/mid PEAD + transcript tone).

Kept import-light (no alpaca/httpx) so tests run without network deps.
Gate thresholds are PRE-REGISTERED in the 2026-07-04 plan — do not tune them.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

# Gate POC-1 (pre-registered)
GATE_MIN_N = 30
GATE_MIN_DRIFT_NET = 0.015
GATE_MIN_HIT = 0.55
CAP_MICRO_MAX_MUSD = 300.0
CAP_LARGE_MIN_MUSD = 10_000.0
MIN_ADV_USD = 5_000_000.0  # filtro liquidità: ADV 20g >= $5M


def classify_cap(cap_musd: float) -> str:
    if cap_musd <= 0:
        return "unknown"
    if cap_musd < CAP_MICRO_MAX_MUSD:
        return "micro"
    if cap_musd < CAP_LARGE_MIN_MUSD:
        return "small/mid"
    return "large"


def adv_usd(bars: list, event_date: str, lookback: int = 20) -> float:
    """Mean dollar volume of the last `lookback` bars strictly BEFORE event_date."""
    try:
        ed = datetime.fromisoformat(event_date).date()
    except (ValueError, TypeError):
        return 0.0
    prior = [b for b in bars if b.timestamp.date() < ed]
    window = prior[-lookback:]
    if not window:
        return 0.0
    return sum(float(b.close) * float(b.volume) for b in window) / len(window)


def gate_verdict_smallmid(excess_rets: list[float], cost_bps: int = 30) -> dict:
    """PASS/FAIL sul gate pre-registrato POC-1 (excess vs IWM, netto costi)."""
    haircut = cost_bps / 10_000.0
    net = [r - haircut for r in excess_rets]
    n = len(net)
    if n == 0:
        return {"n": 0, "mean_net": 0.0, "hit_net": 0.0, "verdict": "FAIL"}
    mean_net = sum(net) / n
    hit_net = sum(1 for r in net if r > 0) / n
    ok = n >= GATE_MIN_N and mean_net >= GATE_MIN_DRIFT_NET and hit_net > GATE_MIN_HIT
    return {"n": n, "mean_net": mean_net, "hit_net": hit_net,
            "verdict": "PASS" if ok else "FAIL"}


def transcript_matches_event(transcript_date, event_date: str) -> bool:
    """True se il transcript è datato in [event−2g, event+3g] (guardia anti wrong-quarter
    e anti look-ahead: l'entry è comunque il giorno di borsa DOPO max(call, evento))."""
    if not transcript_date:
        return False
    try:
        td = datetime.fromisoformat(str(transcript_date)[:10]).date()
        ed = datetime.fromisoformat(event_date).date()
    except (ValueError, TypeError):
        return False
    delta = (td - ed).days
    return -2 <= delta <= 3


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_GUIDANCE_VALUES = {"raised", "maintained", "lowered", "none"}


def parse_tone_json(raw: str) -> dict | None:
    """Estrae e valida il blocco JSON dalla risposta LLM. None se non parsabile."""
    m = _JSON_RE.search(raw or "")
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        pol = max(-1.0, min(1.0, float(d["tone_polarity"])))
        conf = max(0.0, min(1.0, float(d["confidence"])))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    guidance = d.get("guidance", "none")
    if guidance not in _GUIDANCE_VALUES:
        guidance = "none"
    return {"tone_polarity": pol, "confidence": conf, "guidance": guidance,
            "key_evidence": str(d.get("key_evidence", ""))[:500],
            "score": pol * conf}


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0  # rank medio per i ties
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman_ic(scores: list[float], rets: list[float]) -> float | None:
    """Spearman rank correlation, implementazione senza scipy (ties → rank medio)."""
    n = len(scores)
    if n < 2 or n != len(rets):
        return None
    rx, ry = _ranks(list(scores)), _ranks(list(rets))
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5
