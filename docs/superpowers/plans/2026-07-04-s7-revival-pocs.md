# S7 Revival Month — POC Small/Mid PEAD + Transcript Tone (ALPHA-A3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Esecutore: UN SOLO agente Sonnet, task in ordine 1→8, nessun subagent.** Ogni task committa da solo. Se un task fallisce per dati/vendor (non per codice), scrivilo nel report e prosegui dove possibile.

**Goal:** In un mese (deadline decisione: **2026-08-01**) rispondere in modo binario alla domanda "S7 si tiene o si elimina", testando le due ipotesi mai campionate dal gate ALPHA-A5: (1) PEAD su universo small/mid-cap, (2) tone-analysis LLM sui transcript earnings (ALPHA-A3).

**Contesto:** Il gate ALPHA-A5 del 2026-07-03 ha dato FAIL conclusivo sul PEAD large-cap (excess vs SPY +0.05%, mediana −1.07% → beta + 5 outlier). S7 è `research`/blocked in `strategy_lifecycle`. Il PO ha autorizzato **1 mese di FMP Starter (~$29)** che sblocca sia il calendario earnings storico (`from` param) sia i transcript. Report di riferimento: `reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md`.

**Architecture:** Due POC come script di ricerca offline in `scripts/` (stesso stile self-contained di `scripts/backtest_s7_pead.py`, da cui si riusano i fetcher). Helper puri estratti e testati TDD (pattern esistente: `tests/backtest/test_backtest_runner.py` importa da `scripts.`). Nessuna modifica al codice live, nessuna modifica a `strategy_lifecycle` (decisione riservata al PO). Output: CSV + report markdown in `reports/` (gitignored → `git add -f`, prassi già usata per i gate report).

**Tech Stack:** Python 3.11 (`.venv/bin/python`), httpx, pandas/numpy (già nel venv), Alpaca historical bars (IEX), FMP `/stable`, Ollama Cloud `POST {OLLAMA_BASE_URL}/api/chat` (Bearer `OLLAMA_API_KEY`), `src.text.sanitizer.sanitize_text`.

**Gate pre-registrati (decisi il 2026-07-04, NON modificabili durante l'esecuzione):**

| POC | Gate PASS | Note |
|---|---|---|
| POC-1 small/mid PEAD | n≥30 eventi BEAT small/mid con prezzo; media excess vs **IWM** a 20d, **al netto di 30bps** round-trip, ≥ +1.5%; hit-rate (excess netto > 0) > 55% | large-cap NON si ritesta (già FAIL) |
| POC-2 transcript tone | n≥30 eventi con transcript matchato; Spearman IC(tone_score, excess_20d vs SPY) ≥ +0.10; spread terzile top−bottom ≥ +1.5%; IC > 0 in entrambe le metà del campione (split-half) | modello primario `kimi-k2.6:cloud`; costo cap: max 120 transcript, max 24.000 char ciascuno |
| Copertura dati | se transcript matchati < 50% degli eventi o eventi small/mid con barre < 30 → verdetto **INCONCLUSIVE_DATA** (≠ FAIL alpha) | va scritto nel report, decide il PO |

**Esito → azione:** entrambi FAIL → il PO ordina la rimozione completa di S7 (task beat `earnings-pead`/`pead-ingestion`, lifecycle → disabled, archivio doc). Almeno un PASS → piano dedicato di build. Il piano NON esegue la rimozione.

---

## Prerequisito (manuale, PO)

FMP Starter attivo sulla stessa `FMP_API_KEY` già in `.env`. Il Task 1 lo verifica e **abortisce il piano** se non attivo.

---

### Task 1: Probe vendor — Starter attivo?

**Files:** nessuno (solo verifica; nessun commit).

- [ ] **Step 1: Verifica `from` param sbloccato**

```bash
cd /home/stefano/Documents/Projects/Alembic
set -a; source .env; set +a
curl -s "https://financialmodelingprep.com/stable/earnings-calendar?from=2026-01-05&to=2026-01-10&apikey=$FMP_API_KEY" | head -c 300; echo
```

Expected: array JSON di eventi earnings (`[{"symbol":...`). Se contiene `"Special Endpoint"` o `402` → Starter NON attivo: **STOP, segnala al PO, non proseguire.**

- [ ] **Step 2: Verifica transcript sbloccati**

```bash
curl -s "https://financialmodelingprep.com/stable/earning-call-transcript?symbol=AAPL&year=2026&quarter=1&apikey=$FMP_API_KEY" | head -c 300; echo
```

Expected: JSON con campo `content` (testo transcript). Se `"Restricted Endpoint"` → STOP come sopra.

---

### Task 2: Helper puri POC-1 (TDD)

**Files:**
- Create: `scripts/s7_poc_helpers.py`
- Test: `tests/analysis/test_s7_poc_helpers.py`

- [ ] **Step 1: Scrivi i test (falliranno: modulo inesistente)**

```python
"""Helper puri dei POC S7 revival (small/mid PEAD + transcript tone)."""
from __future__ import annotations

import pytest

from scripts.s7_poc_helpers import (
    classify_cap,
    adv_usd,
    gate_verdict_smallmid,
    transcript_matches_event,
    parse_tone_json,
    spearman_ic,
)


class _Bar:
    def __init__(self, day: str, close: float, volume: float):
        from datetime import datetime, timezone
        self.timestamp = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
        self.close = close
        self.volume = volume


class TestClassifyCap:
    def test_buckets(self):
        assert classify_cap(150.0) == "micro"        # < $300M: escluso
        assert classify_cap(2_000.0) == "small/mid"  # $300M–$10B
        assert classify_cap(50_000.0) == "large"
        assert classify_cap(0.0) == "unknown"


class TestAdvUsd:
    def test_mean_dollar_volume_before_event_only(self):
        bars = [_Bar(f"2026-03-{d:02d}", 10.0, 1_000_000) for d in range(2, 12)]
        # 10 barre da $10M ADV ciascuna, tutte prima dell'evento
        assert adv_usd(bars, "2026-03-15", lookback=5) == pytest.approx(10_000_000)

    def test_excludes_bars_on_or_after_event(self):
        bars = [_Bar("2026-03-10", 10.0, 1_000_000), _Bar("2026-03-16", 999.0, 9e9)]
        assert adv_usd(bars, "2026-03-15", lookback=5) == pytest.approx(10_000_000)

    def test_empty_returns_zero(self):
        assert adv_usd([], "2026-03-15") == 0.0


class TestGateVerdict:
    def test_pass_case(self):
        rets = [0.03] * 40  # 3% excess lordo, netto 30bps = 2.7%
        v = gate_verdict_smallmid(rets, cost_bps=30)
        assert v["n"] == 40 and v["mean_net"] == pytest.approx(0.027)
        assert v["hit_net"] == 1.0 and v["verdict"] == "PASS"

    def test_fail_on_low_n(self):
        assert gate_verdict_smallmid([0.03] * 29, cost_bps=30)["verdict"] == "FAIL"

    def test_haircut_can_flip_verdict(self):
        rets = [0.016] * 40  # lordo sopra soglia, netto 1.3% < 1.5%
        assert gate_verdict_smallmid(rets, cost_bps=30)["verdict"] == "FAIL"


class TestTranscriptMatch:
    def test_within_window(self):
        assert transcript_matches_event("2026-04-24 21:00:00", "2026-04-24")
        assert transcript_matches_event("2026-04-22", "2026-04-24")   # −2 giorni
        assert transcript_matches_event("2026-04-27", "2026-04-24")   # +3 giorni

    def test_outside_window_or_garbage(self):
        assert not transcript_matches_event("2026-01-30", "2026-04-24")
        assert not transcript_matches_event("", "2026-04-24")
        assert not transcript_matches_event(None, "2026-04-24")


class TestParseToneJson:
    def test_extracts_json_block_from_chatter(self):
        raw = 'Reasoning...\n{"tone_polarity": 0.6, "confidence": 0.8, "guidance": "raised", "key_evidence": "x"}\nDone.'
        d = parse_tone_json(raw)
        assert d["tone_polarity"] == 0.6 and d["guidance"] == "raised"

    def test_clamps_out_of_range(self):
        raw = '{"tone_polarity": 1.7, "confidence": 1.2, "guidance": "none", "key_evidence": ""}'
        d = parse_tone_json(raw)
        assert d["tone_polarity"] == 1.0 and d["confidence"] == 1.0

    def test_invalid_returns_none(self):
        assert parse_tone_json("no json here") is None
        assert parse_tone_json('{"tone_polarity": "alto"}') is None


class TestSpearmanIC:
    def test_perfect_monotonic(self):
        assert spearman_ic([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)

    def test_perfect_inverse(self):
        assert spearman_ic([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)

    def test_needs_min_two(self):
        assert spearman_ic([1], [2]) is None
```

- [ ] **Step 2: Run per verificare il fallimento giusto**

Run: `.venv/bin/python -m pytest tests/analysis/test_s7_poc_helpers.py -q`
Expected: `ModuleNotFoundError: No module named 'scripts.s7_poc_helpers'`

- [ ] **Step 3: Implementa `scripts/s7_poc_helpers.py`**

```python
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
```

- [ ] **Step 4: Run test → verdi**

Run: `.venv/bin/python -m pytest tests/analysis/test_s7_poc_helpers.py -q`
Expected: `15 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/s7_poc_helpers.py tests/analysis/test_s7_poc_helpers.py
git commit -m "feat(s7-poc): pure helpers for revival POCs (cap buckets, ADV, gates, tone parse, spearman)"
```

---

### Task 3: POC-1 — backtest small/mid PEAD

**Files:**
- Create: `scripts/backtest_s7_smallmid.py`
- Riusa da `scripts/backtest_s7_pead.py`: `_alpaca_bars`, `_forward_return`, `_market_caps` (import diretto, come già fa `scripts/analyze_s7_events.py`)

- [ ] **Step 1: Scrivi lo script**

```python
#!/usr/bin/env python3
"""POC-1 S7 revival: PEAD su universo small/mid-cap ($300M–$10B), FMP Starter.

Gate pre-registrato (piano 2026-07-04): n>=30 BEAT small/mid, media excess vs IWM
a 20d netta di 30bps >= +1.5%, hit netto > 55%. Large-cap NON si ritesta (FAIL 07-03).

Run: set -a; source .env; set +a; .venv/bin/python scripts/backtest_s7_smallmid.py
"""
from __future__ import annotations

import csv
import os
import sys
import time
from datetime import datetime, timedelta

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backtest_s7_pead import (  # noqa: E402
    _SURPRISE_THRESHOLD, _alpaca_bars, _forward_return, _market_caps,
)
from scripts.s7_poc_helpers import (  # noqa: E402
    MIN_ADV_USD, adv_usd, classify_cap, gate_verdict_smallmid,
)

_FMP = "https://financialmodelingprep.com/stable"
_START = os.environ.get("BT_START", "2026-01-01")
_END = os.environ.get("BT_END", "2026-05-15")
_MAX_CAP_LOOKUPS = 600  # Starter: 300 call/min, quota giornaliera ampia


def _fmp_earnings_range(key: str, start: str, end: str) -> list[dict]:
    """Calendario earnings con from/to (sbloccato da Starter), chunk 30 giorni."""
    out: dict[tuple, dict] = {}
    d0 = datetime.fromisoformat(start).date()
    d1 = datetime.fromisoformat(end).date()
    cur = d0
    while cur <= d1:
        chunk_end = min(cur + timedelta(days=30), d1)
        r = httpx.get(f"{_FMP}/earnings-calendar",
                      params={"from": cur.isoformat(), "to": chunk_end.isoformat(),
                              "apikey": key}, timeout=30.0)
        r.raise_for_status()
        for e in r.json() or []:
            if e.get("date"):
                out[(e.get("symbol"), e["date"])] = e
        print(f"  ...calendar {cur}..{chunk_end}: cum {len(out)} records")
        time.sleep(0.25)
        cur = chunk_end + timedelta(days=1)
    return list(out.values())


def main() -> None:
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        print("No FMP_API_KEY in env"); return

    print(f"# POC-1 small/mid PEAD — {_START}..{_END}\n")
    raw = _fmp_earnings_range(key, _START, _END)
    events = []
    for e in raw:
        a, est = e.get("epsActual"), e.get("epsEstimated")
        if a is None or not est:
            continue
        surprise = (a - est) / abs(est)
        if abs(surprise) < _SURPRISE_THRESHOLD:
            continue
        events.append({"symbol": e["symbol"], "date": e["date"], "surprise": surprise,
                       "dir": "BEAT" if surprise > 0 else "MISS"})
    print(f"Eventi |surprise|>={_SURPRISE_THRESHOLD}: {len(events)}")

    symbols = sorted({e["symbol"] for e in events})
    caps = _market_caps(symbols[:_MAX_CAP_LOOKUPS], key)
    smallmid_syms = {s for s, c in caps.items() if classify_cap(c) == "small/mid"}
    events = [e for e in events if e["symbol"] in smallmid_syms]
    print(f"Eventi small/mid ($300M–$10B): {len(events)} su {len(smallmid_syms)} simboli")

    bars = _alpaca_bars(sorted(smallmid_syms) + ["IWM"])
    iwm = bars.get("IWM", [])

    rows, no_bars, illiquid = [], 0, 0
    for e in events:
        b = bars.get(e["symbol"]) or []
        if len(b) < 25:
            no_bars += 1
            continue
        if adv_usd(b, e["date"]) < MIN_ADV_USD:
            illiquid += 1
            continue
        fr = _forward_return(b, e["date"])
        bench = _forward_return(iwm, e["date"])
        if fr is None or bench is None:
            no_bars += 1
            continue
        rows.append({"symbol": e["symbol"], "date": e["date"], "dir": e["dir"],
                     "surprise": round(e["surprise"], 4), "ret_20d": round(fr, 4),
                     "iwm_20d": round(bench, 4), "excess_20d": round(fr - bench, 4),
                     "cap_musd": round(caps.get(e["symbol"], 0.0), 0),
                     "adv_usd": round(adv_usd(b, e["date"]), 0)})
    print(f"Con barre+liquidità: {len(rows)} (scartati: {no_bars} no-bars IEX, {illiquid} illiquidi <$5M ADV)")
    print("NB: copertura IEX bassa sui small-cap è ANCHE un proxy di non-tradabilità via Alpaca.\n")

    os.makedirs("reports/s7_poc", exist_ok=True)
    out_csv = f"reports/s7_poc/poc1_smallmid_events_{datetime.now():%Y-%m-%d}.csv"
    if rows:
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        print(f"CSV → {out_csv}\n")

    for d in ("BEAT", "MISS"):
        sel = [r["excess_20d"] for r in rows if r["dir"] == d]
        sign = 1 if d == "BEAT" else -1
        v = gate_verdict_smallmid([sign * x for x in sel], cost_bps=30)
        print(f"{d}: n={v['n']} mean_net={v['mean_net']:+.2%} hit_net={v['hit_net']:.0%} → {v['verdict']}")

    beat = [r["excess_20d"] for r in rows if r["dir"] == "BEAT"]
    verdict = gate_verdict_smallmid(beat, cost_bps=30)
    tag = "INCONCLUSIVE_DATA" if verdict["n"] < 30 else verdict["verdict"]
    print(f"\n## GATE POC-1 (BEAT long, excess IWM, netto 30bps): {tag}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Esegui**

Run: `set -a; source .env; set +a; .venv/bin/python scripts/backtest_s7_smallmid.py 2>&1 | tee /tmp/poc1_run.log`
Expected: CSV in `reports/s7_poc/`, verdetto PASS/FAIL/INCONCLUSIVE_DATA stampato. Runtime atteso 5–15 min (cap lookups con sleep).

- [ ] **Step 3: Scrivi il report**

Crea `reports/s7_poc/POC1_smallmid_report_<YYYY-MM-DD>.md` con: parametri (finestra, soglie, filtri), tabella BEAT/MISS (n, mean lordo, mean netto, hit, mediana — calcola la mediana dal CSV), conteggio scarti (no-bars vs illiquidi, con la nota sulla copertura IEX), verdetto gate, 3 righe di interpretazione oneste. Modello di riferimento per lo stile: `reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md`.

- [ ] **Step 4: Commit**

```bash
git add scripts/backtest_s7_smallmid.py
git add -f reports/s7_poc/poc1_smallmid_events_*.csv reports/s7_poc/POC1_smallmid_report_*.md
git commit -m "feat(s7-poc): POC-1 small/mid PEAD backtest + gate report (excess IWM, net 30bps)"
```

---

### Task 4: POC-2a — fetch transcript (cache idempotente)

**Files:**
- Create: `scripts/fetch_s7_transcripts.py`

- [ ] **Step 1: Scrivi lo script**

```python
#!/usr/bin/env python3
"""POC-2a: scarica i transcript earnings (FMP Starter) per gli eventi ALPHA-A5.

Eventi = union di reports/s7_backtest/alpha_a5_events_2026-07-03.csv (large)
e reports/s7_poc/poc1_smallmid_events_*.csv (small/mid, se esiste).
Cache: reports/s7_poc/transcripts/{SYM}_{DATE}.json — rilanciabile, salta gli esistenti.
Match: la data del transcript deve cadere in [evento−2g, evento+3g], altrimenti scartato.

Run: set -a; source .env; set +a; .venv/bin/python scripts/fetch_s7_transcripts.py
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys
import time
from datetime import datetime

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.s7_poc_helpers import transcript_matches_event  # noqa: E402

_FMP = "https://financialmodelingprep.com/stable"
_CACHE = "reports/s7_poc/transcripts"
_MAX_TRANSCRIPTS = 120  # cost cap pre-registrato


def _load_events() -> list[dict]:
    events, seen = [], set()
    paths = ["reports/s7_backtest/alpha_a5_events_2026-07-03.csv"]
    paths += sorted(glob.glob("reports/s7_poc/poc1_smallmid_events_*.csv"))
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p) as f:
            for r in csv.DictReader(f):
                k = (r["symbol"], r["date"])
                if k not in seen:
                    seen.add(k)
                    events.append(r)
    return events


def _quarter_candidates(event_date: str) -> list[tuple[int, int]]:
    d = datetime.fromisoformat(event_date)
    q = (d.month - 1) // 3 + 1
    prev = (d.year, q - 1) if q > 1 else (d.year - 1, 4)
    return [(d.year, q), prev]


def main() -> None:
    key = os.environ.get("FMP_API_KEY", "")
    if not key:
        print("No FMP_API_KEY"); return
    os.makedirs(_CACHE, exist_ok=True)

    events = _load_events()[:_MAX_TRANSCRIPTS]
    print(f"Eventi da coprire (cap {_MAX_TRANSCRIPTS}): {len(events)}")
    hits = misses = cached = 0

    for e in events:
        sym, date = e["symbol"], e["date"]
        path = f"{_CACHE}/{sym}_{date}.json"
        if os.path.exists(path):
            cached += 1
            continue
        found = None
        for year, q in _quarter_candidates(date):
            r = httpx.get(f"{_FMP}/earning-call-transcript",
                          params={"symbol": sym, "year": year, "quarter": q,
                                  "apikey": key}, timeout=30.0)
            time.sleep(0.25)
            if r.status_code != 200:
                continue
            data = r.json() or []
            item = data[0] if isinstance(data, list) and data else None
            if item and item.get("content") and transcript_matches_event(item.get("date"), date):
                found = {"symbol": sym, "event_date": date, "transcript_date": item.get("date"),
                         "year": year, "quarter": q, "content": item["content"]}
                break
        if found:
            with open(path, "w") as f:
                json.dump(found, f)
            hits += 1
        else:
            misses += 1
        if (hits + misses) % 20 == 0:
            print(f"  ...{hits + misses} processati (match {hits}, miss {misses})")

    total = hits + misses + cached
    print(f"\nMatch: {hits + cached}/{total} ({(hits + cached) / max(total, 1):.0%}) — miss {misses}")
    if total and (hits + cached) / total < 0.5:
        print("⚠️ Copertura <50% → il gate POC-2 sarà INCONCLUSIVE_DATA (pre-registrato)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Esegui e annota la copertura**

Run: `set -a; source .env; set +a; .venv/bin/python scripts/fetch_s7_transcripts.py 2>&1 | tee /tmp/poc2_fetch.log`
Expected: file JSON in `reports/s7_poc/transcripts/`, riga finale `Match: X/Y`. Annota X/Y: entra nel report finale.

- [ ] **Step 3: Commit (solo script — la cache transcript NON si committa: contenuto vendor)**

```bash
git add scripts/fetch_s7_transcripts.py
git commit -m "feat(s7-poc): POC-2a transcript fetcher with idempotent cache and date-match guard"
```

---

### Task 5: POC-2b — scoring LLM del tone (DK-CoT)

**Files:**
- Create: `scripts/score_s7_transcripts.py`

- [ ] **Step 1: Scrivi lo script**

```python
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

TRANSCRIPT ({symbol}, call date {date}):
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
            prompt = _PROMPT.format(symbol=t["symbol"], date=t["transcript_date"], text=text)
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
```

- [ ] **Step 2: Smoke su 3 transcript, poi run completo**

Run (smoke): sposta temporaneamente tutti i JSON tranne 3 in `/tmp/`, esegui, verifica 3 righe valide nel CSV, ripristina i JSON, rilancia (idempotente: salta i 3). **Lanciare fuori dalle 14:00–21:00 UTC** per non contendere la quota Ollama al worker live.
Expected: `tone_scores.csv` con una riga per transcript; JSON invalidi < 10%.

- [ ] **Step 3: Subsample agreement GLM (20 eventi)**

Run: `TONE_MODEL=glm-5.2:cloud` sui primi 20 transcript (ordina per nome file, sposta gli altri via come nello smoke). Il CSV accumula righe con `model` diverso — servono al report per la stat di agreement.

- [ ] **Step 4: Commit**

```bash
git add scripts/score_s7_transcripts.py
git add -f reports/s7_poc/tone_scores.csv
git commit -m "feat(s7-poc): POC-2b LLM tone scoring (DK-CoT, kimi primary + glm agreement subsample)"
```

---

### Task 6: POC-2c — analisi IC e gate

**Files:**
- Create: `scripts/analyze_s7_tone.py`

- [ ] **Step 1: Scrivi lo script**

```python
#!/usr/bin/env python3
"""POC-2c: IC del tone score vs excess return 20d + gate ALPHA-A3 pre-registrato.

Join: tone_scores.csv (kimi) × eventi (alpha_a5 large + poc1 small/mid) sui campi
(symbol, event_date). Excess: vs SPY per i large (già nel CSV alpha_a5), vs IWM
per gli small/mid (CSV poc1). Gate: n>=30, Spearman IC >= +0.10, spread terzili
top-bottom >= +1.5%, IC > 0 in entrambe le metà (split per data evento).
In più: agreement kimi/glm sul subsample e concordanza guidance vs surprise (A4-lite).
"""
from __future__ import annotations

import csv
import glob
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.s7_poc_helpers import spearman_ic  # noqa: E402


def _load_returns() -> dict[tuple, dict]:
    out = {}
    with open("reports/s7_backtest/alpha_a5_events_2026-07-03.csv") as f:
        for r in csv.DictReader(f):
            if r.get("excess_20d") not in ("", None):
                out[(r["symbol"], r["date"])] = {"excess": float(r["excess_20d"]),
                                                 "surprise": float(r["surprise"])}
    for p in sorted(glob.glob("reports/s7_poc/poc1_smallmid_events_*.csv")):
        with open(p) as f:
            for r in csv.DictReader(f):
                out[(r["symbol"], r["date"])] = {"excess": float(r["excess_20d"]),
                                                 "surprise": float(r["surprise"])}
    return out


def main() -> None:
    rets = _load_returns()
    kimi, glm = {}, {}
    with open("reports/s7_poc/tone_scores.csv") as f:
        for r in csv.DictReader(f):
            k = (r["symbol"], r["event_date"])
            d = {"score": float(r["score"]), "guidance": r["guidance"]}
            (kimi if r["model"].startswith("kimi") else glm)[k] = d

    joined = [(k, kimi[k]["score"], rets[k]["excess"], rets[k]["surprise"], kimi[k]["guidance"])
              for k in sorted(kimi) if k in rets]
    n = len(joined)
    print(f"Eventi con tone (kimi) e ritorno: n={n}")
    if n == 0:
        print("Nessun match — INCONCLUSIVE_DATA"); return

    scores = [j[1] for j in joined]
    excess = [j[2] for j in joined]
    ic = spearman_ic(scores, excess)
    print(f"Spearman IC(tone, excess_20d): {ic:+.3f}")

    order = sorted(joined, key=lambda j: j[1])
    third = max(n // 3, 1)
    bot = [j[2] for j in order[:third]]
    top = [j[2] for j in order[-third:]]
    spread = st.mean(top) - st.mean(bot)
    print(f"Terzili: top {st.mean(top):+.2%} vs bottom {st.mean(bot):+.2%} → spread {spread:+.2%}")

    half = n // 2  # joined è ordinato per (symbol, date); split per data evento:
    by_date = sorted(joined, key=lambda j: j[0][1])
    ic1 = spearman_ic([j[1] for j in by_date[:half]], [j[2] for j in by_date[:half]])
    ic2 = spearman_ic([j[1] for j in by_date[half:]], [j[2] for j in by_date[half:]])
    print(f"Split-half per data: IC prima metà {ic1:+.3f}, seconda metà {ic2:+.3f}")

    # IC del tone DENTRO i soli BEAT: il tone aggiunge oltre il segno della surprise?
    beats = [j for j in joined if j[3] > 0]
    ic_beat = spearman_ic([j[1] for j in beats], [j[2] for j in beats]) if len(beats) > 2 else None
    print(f"IC dentro i soli BEAT (n={len(beats)}): {ic_beat if ic_beat is None else f'{ic_beat:+.3f}'}")

    # A4-lite: concordanza guidance vs segno surprise
    conc = [(j[4] == "raised") == (j[3] > 0) for j in joined if j[4] in ("raised", "lowered")]
    if conc:
        print(f"Concordanza guidance/surprise: {sum(conc) / len(conc):.0%} (n={len(conc)})")

    # Agreement kimi/glm sul subsample
    both = [(kimi[k]["score"], glm[k]["score"]) for k in kimi if k in glm]
    if len(both) > 2:
        agree_ic = spearman_ic([b[0] for b in both], [b[1] for b in both])
        print(f"Agreement kimi/glm (subsample n={len(both)}): Spearman {agree_ic:+.3f}")

    ok = (n >= 30 and ic is not None and ic >= 0.10 and spread >= 0.015
          and ic1 is not None and ic2 is not None and ic1 > 0 and ic2 > 0)
    tag = "INCONCLUSIVE_DATA" if n < 30 else ("PASS" if ok else "FAIL")
    print(f"\n## GATE ALPHA-A3: {tag}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Esegui**

Run: `.venv/bin/python scripts/analyze_s7_tone.py 2>&1 | tee /tmp/poc2_analysis.log`
Expected: IC, terzili, split-half, agreement, verdetto.

- [ ] **Step 3: Commit**

```bash
git add scripts/analyze_s7_tone.py
git commit -m "feat(s7-poc): POC-2c tone IC analysis + pre-registered ALPHA-A3 gate"
```

---

### Task 7: Report finale di decisione

**Files:**
- Create: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_<YYYY-MM-DD>.md`

- [ ] **Step 1: Scrivi il report** con questa struttura esatta:

```markdown
# S7 Revival Month — Decision Report (<data>)

## Esito sintetico
| POC | Gate | Esito | Numero chiave |
|---|---|---|---|
| POC-1 small/mid PEAD | net drift ≥+1.5%, hit>55%, n≥30 | PASS/FAIL/INCONCLUSIVE_DATA | ... |
| POC-2 transcript tone | IC≥0.10, spread terzili ≥1.5%, split-half | PASS/FAIL/INCONCLUSIVE_DATA | ... |

## POC-1 — dettaglio  (parametri, funnel scarti, tabella BEAT/MISS, onestà su copertura IEX)
## POC-2 — dettaglio  (copertura transcript X/Y, IC, terzili, split-half, agreement kimi/glm, concordanza guidance, JSON-fail rate)
## Costi consuntivi   (FMP $29; LLM: stima da len(prompt)/4 × n_chiamate; tempo)
## Raccomandazione al PO (binaria)
- Entrambi FAIL → rimozione completa S7 (beat tasks earnings-pead/pead-ingestion,
  lifecycle → disabled, archivio docs) + disdetta FMP Starter prima del rinnovo.
- Un PASS → cosa costruire e con quali dati, con il numero che lo giustifica.
- INCONCLUSIVE_DATA → cosa è mancato e a che costo si otterrebbe.
```

Ogni cella va riempita con i numeri reali dei log/CSV dei Task 3–6. Nessun "TBD".

- [ ] **Step 2: Aggiorna i doc di stato**

- `docs/ROADMAP_DATA_ALPHA_2026-07-02.md`: nella riga **ALPHA-A3** (tabella vettore A) aggiungi in coda: `→ POC ESEGUITO <data>, esito <PASS/FAIL/INCONCLUSIVE_DATA> (reports/s7_poc/S7_REVIVAL_DECISION_REPORT_<data>.md)`. Nella riga **ALPHA-A5** aggiungi: `→ POC small/mid ESEGUITO <data>, esito <...> (stesso report)`.
- `docs/strategies/s7-pead.md`: sotto il banner SHELVED aggiungi una riga: `Aggiornamento <data>: POC revival eseguiti — vedi reports/s7_poc/S7_REVIVAL_DECISION_REPORT_<data>.md. Decisione PO pendente.`
- `docs/CHANGELOG.md`: nuova entry datata con 3 righe: esito POC-1, esito POC-2, rimando al report.

- [ ] **Step 3: Commit**

```bash
git add -f reports/s7_poc/S7_REVIVAL_DECISION_REPORT_*.md
git add docs/ROADMAP_DATA_ALPHA_2026-07-02.md docs/strategies/s7-pead.md docs/CHANGELOG.md
git commit -m "docs(s7-poc): revival month decision report + roadmap/strategy status update"
```

---

### Task 8: Verifica finale

- [ ] **Step 1: Suite completa**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -3`
Expected: nessuna failure NUOVA rispetto alla baseline (10 failed pre-esistenti note al 2026-07-04 — le stesse identiche; i nuovi test di Task 2 tutti verdi).

- [ ] **Step 2: Lint**

Run: `.venv/bin/python -m ruff check scripts/s7_poc_helpers.py scripts/backtest_s7_smallmid.py scripts/fetch_s7_transcripts.py scripts/score_s7_transcripts.py scripts/analyze_s7_tone.py`
Expected: clean (se ruff non è configurato nel repo, salta questo step e annotalo).

- [ ] **Step 3: Riepilogo per il PO**

Stampa nel messaggio finale: i due verdetti, i numeri chiave, il path del decision report, e il promemoria **disdetta FMP Starter prima del rinnovo se la decisione è rimozione**.

---

## Cosa questo piano NON fa (di proposito)

- Non modifica `strategy_lifecycle` né il beat schedule: la rimozione o riattivazione di S7 è decisione PO a valle del report.
- Non ritesta il PEAD large-cap (FAIL conclusivo 2026-07-03).
- Non costruisce la strategia live transcript-tone: solo il segnale e la sua validazione.
- Non committa il contenuto dei transcript (materiale vendor): solo score derivati.
