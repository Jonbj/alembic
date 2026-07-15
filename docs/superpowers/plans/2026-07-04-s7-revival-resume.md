# S7 Revival — Resume Plan: POC-2 via Alpha Vantage + POC-1 universo completo + correzione doc

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Esecutore: UN SOLO agente, task in ordine 1→10.** Questo piano SOSTITUISCE per l'esecuzione `2026-07-04-s7-revival-pocs.md` (i cui Task 1–3 sono già stati eseguiti — vedi Stato verificato). I **gate restano quelli pre-registrati** nel piano originale: NON modificarli.

**Goal:** Completare il revival month S7: eseguire POC-2 (transcript tone, ALPHA-A3) via Alpha Vantage — mai partito per un equivoco vendor — e ri-eseguire POC-1 sull'universo simboli completo per risolvere l'`INCONCLUSIVE_DATA` (n=15 < 30), correggendo i doc che riportano una premessa falsa.

**Architecture:** Identica al piano originale: script di ricerca offline in `scripts/`, helper puri TDD, output CSV+markdown in `reports/s7_poc/` (`git add -f`). Nessuna modifica a codice live, `strategy_lifecycle` o beat schedule.

**Tech Stack:** Python 3.11 (`.venv/bin/python`), httpx, Alpaca historical bars (IEX), FMP `/stable` (Starter attivo), Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` (free tier, `ALPHAVANTAGE_API_KEY` in `.env` dal 2026-07-04), Ollama Cloud `POST {OLLAMA_BASE_URL}/api/chat`.

---

## Stato verificato al 2026-07-04 (perché questo piano esiste)

Il primo executor ha lavorato sulla **versione pre-correzione** del piano (la correzione vendor `0e84850` è arrivata a esecuzione già iniziata e non è mai stata riletta):

| Task originale | Stato | Evidenza |
|---|---|---|
| 1 — Probe vendor | Parziale: FMP ✓, **probe Alpha Vantage mai fatto** (la vecchia versione provava i transcript FMP → "Restricted Endpoint" → POC-2 abbandonato) | decision report §POC-2 |
| 2 — Helper TDD | Fatto (commit `8891372`) ma versione VECCHIA: manca `reported_quarter_candidates` (serve al fetcher AV), c'è `transcript_matches_event` (solo path FMP, ora morto) | `scripts/s7_poc_helpers.py`; 15 test verdi |
| 3 — POC-1 small/mid | Fatto (commit `9e99444`): **INCONCLUSIVE_DATA, n=15 < 30**. Campione limitato a 600 simboli **alfabetici** su 6.177; 2 bug fixati in corsa (unità market-cap, batch preferred) | `reports/s7_poc/POC1_smallmid_report_2026-07-04.md` |
| 4–6 — POC-2 | **MAI ESEGUITI**: script inesistenti, 0 transcript, 0 score | decision report §POC-2 |
| 7 — Decision report | Scritto (commit `85b0a70`) ma su premessa falsa: "POC-2 richiede Ultimate $99/mo, il PO ha scelto di non fare l'upgrade" — il PO non ha mai preso quella decisione; la via Alpha Vantage a costo zero era già nel piano corretto | `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md` + stessa frase in ROADMAP/s7-pead/CHANGELOG |
| 8 — Verifica suite | Helper tests: 15 passed (verificato 2026-07-04 sera) | pytest |

**Cosa cambia:** (a) POC-2 si esegue con Alpha Vantage (chiave ora in `.env`); (b) POC-1 si ri-esegue senza il cap dei 600 simboli alfabetici — costo vendor zero, solo runtime (~45–90 min), gate INVARIATI; (c) i 4 doc con la premessa falsa vanno corretti subito, non a fine mese.

**Vincoli invariati dal piano originale:** gate pre-registrati immutabili; niente `strategy_lifecycle`/beat; cache transcript NON committata (contenuto vendor); scoring LLM fuori dalle 14:00–21:00 UTC (quota Ollama condivisa col worker live); deadline decisione 2026-08-01.

> **Verifica checkbox (2026-07-15):** Task 2–6 e Task 8 confermati DONE via commit reali
> (7c483d0, 4cc0343, 22f6cc0, d7a1757, 72932db, 1007b13) e via i dati effettivamente
> presenti (`reports/s7_poc/transcripts/`: 48 file; `tone_scores.csv`: 48 righe kimi).
> Il commit `1007b13` mostra un run interim (48/120 transcript, 40% copertura, split-half
> instabile → FAIL su quel criterio) esplicitamente etichettato "NOT the final gate".
> **Task 7 Step 1 spuntato** (il ciclo fetch→score è girato su più giorni, 4→7 luglio, coi
> file transcript datati di conseguenza); **Step 2 e 3 lasciati non spuntati**: il cutoff
> del 2026-07-26 non è ancora arrivato (oggi 2026-07-15) e non risulta un run col subsample
> GLM (`tone_scores.csv` contiene solo righe `kimi-k2.6:cloud`, nessuna `glm-5.2:cloud`).
> **Task 9 e 10 lasciati interamente non spuntati**: nessun `S7_REVIVAL_DECISION_REPORT_*FINAL*`
> in `reports/s7_poc/`, nessun commit successivo a `1007b13` (2026-07-07) che tocchi questo
> lavoro — il fetch giornaliero risulta fermo da allora, ben prima del cutoff pre-registrato.
> **Task 1 lasciato non spuntato** (step di sola verifica manuale, nessun commit atteso).

---

### Task 1: Probe vendor (Alpha Vantage con la chiave reale + FMP ancora attivo)

**Files:** nessuno (solo verifica; nessun commit).

- [ ] **Step 1: Probe Alpha Vantage**

```bash
cd /home/stefano/Documents/Projects/Alembic
set -a; source .env; set +a
curl -s "https://www.alphavantage.co/query?function=EARNINGS_CALL_TRANSCRIPT&symbol=IBM&quarter=2026Q1&apikey=$ALPHAVANTAGE_API_KEY" | head -c 400; echo
```

Expected: JSON `{"symbol": "IBM", "quarter": "2026Q1", "transcript": [{"speaker": ..., "content": ...}]}`. Se compare `"Information"` con richiesta premium → **STOP, segnala al PO**. Un `"Note"` di rate limit invece è atteso (il fetcher lo gestisce). Non stampare MAI la chiave.

- [ ] **Step 2: Probe FMP Starter (serve al Task 3)**

```bash
curl -s "https://financialmodelingprep.com/stable/earnings-calendar?from=2026-01-05&to=2026-01-10&apikey=$FMP_API_KEY" | head -c 300; echo
```

Expected: array JSON di eventi. Se `"Special Endpoint"`/402 → Starter scaduto: STOP, segnala al PO.

---

### Task 2: Helper TDD — `reported_quarter_candidates` sostituisce `transcript_matches_event`

Il fetcher AV chiave i transcript per **trimestre fiscale riportato** (es. call di aprile 2026 → "2026Q1"), senza data call → serve la mappa evento→trimestri candidati. `transcript_matches_event` (match per data call, path FMP) non ha più chiamanti: si rimuove.

**Files:**
- Modify: `scripts/s7_poc_helpers.py`
- Modify: `tests/analysis/test_s7_poc_helpers.py`

- [x] **Step 1: Aggiorna i test (falliranno: import inesistente)**

In `tests/analysis/test_s7_poc_helpers.py`: nell'import sostituire la riga `transcript_matches_event,` con `reported_quarter_candidates,`; sostituire l'intera classe `TestTranscriptMatch` (righe 61–70) con:

```python
class TestReportedQuarterCandidates:
    def test_mid_year_event_reports_previous_quarter(self):
        # call di fine aprile → riporta il Q1 fiscale; fallback Q4 anno prima
        assert reported_quarter_candidates("2026-04-24") == ["2026Q1", "2025Q4"]

    def test_january_event_rolls_over_year(self):
        assert reported_quarter_candidates("2026-01-15") == ["2025Q4", "2025Q3"]

    def test_garbage_returns_empty(self):
        assert reported_quarter_candidates("") == []
        assert reported_quarter_candidates("not-a-date") == []
```

- [x] **Step 2: Run per verificare il fallimento giusto**

Run: `.venv/bin/python -m pytest tests/analysis/test_s7_poc_helpers.py -q`
Expected: `ImportError: cannot import name 'reported_quarter_candidates'`

- [x] **Step 3: Implementa**

In `scripts/s7_poc_helpers.py`: eliminare per intero la funzione `transcript_matches_event` (righe 58–69, docstring inclusa) e al suo posto inserire:

```python
def reported_quarter_candidates(event_date: str) -> list[str]:
    """I due trimestri fiscali candidati per il transcript AV di un evento earnings.

    Alpha Vantage chiave i transcript per fiscal quarter RIPORTATO (es. call di
    aprile 2026 → "2026Q1"), senza data call. Il trimestre riportato precede
    sempre l'evento → il worst case di un match sbagliato è un transcript VECCHIO
    (rumore), mai informazione futura: anti look-ahead strutturale.
    """
    try:
        d = datetime.fromisoformat(event_date)
    except (ValueError, TypeError):
        return []
    y, q = d.year, (d.month - 1) // 3 + 1
    out = []
    for _ in range(2):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        out.append(f"{y}Q{q}")
    return out
```

- [x] **Step 4: Run test → verdi + nessun altro chiamante**

Run: `.venv/bin/python -m pytest tests/analysis/test_s7_poc_helpers.py -q` → Expected: `16 passed`
Run: `grep -rn transcript_matches_event --include='*.py' .` → Expected: nessun risultato.

- [x] **Step 5: Commit**

```bash
git add scripts/s7_poc_helpers.py tests/analysis/test_s7_poc_helpers.py
git commit -m "feat(s7-poc): reported_quarter_candidates for AV quarter-keyed transcripts (replaces dead FMP date-match helper)"
```

---

### Task 3: POC-1 — ri-esecuzione su universo completo

Il run del 2026-07-04 ha campionato i primi **600 simboli in ordine alfabetico** su 6.177 (bias di selezione dichiarato nel report). Starter consente 300 call/min → il lookup completo è solo runtime (~6.200 profile call × 0.2s sleep ≈ 21 min + latenza ≈ 45–90 min totali). **Gate identici** (n≥30, mean net ≥ +1.5%, hit > 55%): si espande il campione, non le soglie.

**Files:**
- Modify: `scripts/backtest_s7_smallmid.py:32`

- [x] **Step 1: Rendi il cap overridabile da env**

Sostituire la riga 32:

```python
_MAX_CAP_LOOKUPS = 600  # Starter: 300 call/min, quota giornaliera ampia
```

con:

```python
# Default 600 riproduce il run 2026-07-04; override MAX_CAP_LOOKUPS=7000 copre
# l'intero universo (~6.200 simboli, Starter 300 call/min → solo runtime).
_MAX_CAP_LOOKUPS = int(os.environ.get("MAX_CAP_LOOKUPS", "600"))
```

- [x] **Step 2: Esegui sul full universe**

Run: `set -a; source .env; set +a; MAX_CAP_LOOKUPS=7000 .venv/bin/python scripts/backtest_s7_smallmid.py 2>&1 | tee /tmp/poc1_full_run.log`
Expected: funnel con ~6.200 lookup; verdetto finale PASS / FAIL / INCONCLUSIVE_DATA. NB: se eseguito in una data diversa dal 2026-07-04 il CSV esce con la nuova data (i vecchi 15 eventi sono un sottoinsieme, la dedup a valle è per (symbol,date)); se eseguito lo stesso giorno sovrascrive il CSV — accettabile, l'originale è in git (`9e99444`).

- [x] **Step 3: Report**

Crea `reports/s7_poc/POC1_smallmid_report_<data-run>_full_universe.md` con: nota esplicita "supersede il run 2026-07-04 (600 simboli alfabetici → universo completo; stessi gate pre-registrati)", funnel scarti, tabella BEAT/MISS (n, mean lordo/netto, mediana, hit), range di market cap effettivo dei sopravvissuti, verdetto. **Interpretazione chiave da includere se n resta < 30:** gli small/mid scartati per no-bars IEX o ADV<$5M non sarebbero comunque tradabili da Alembic via Alpaca → l'INCONCLUSIVE diventa strutturale e per QUESTO sistema equivale operativamente a "ipotesi non sfruttabile", che è decision-grade per il PO.

- [x] **Step 4: Commit**

```bash
git add scripts/backtest_s7_smallmid.py
git add -f reports/s7_poc/poc1_smallmid_events_*.csv reports/s7_poc/POC1_smallmid_report_*_full_universe.md
git commit -m "feat(s7-poc): POC-1 rerun on full symbol universe (removes alphabetical 600-symbol sampling bias)"
```

---

### Task 4: Correzione dei doc con la premessa falsa

Quattro doc affermano che POC-2 richiedeva un upgrade a Ultimate che "il PO ha scelto di non fare". Falso: la via Alpha Vantage a costo zero era nel piano corretto (`0e84850`) e la decisione di non eseguire POC-2 non è mai stata del PO.

**Files:**
- Modify: `docs/ROADMAP_DATA_ALPHA_2026-07-02.md` (riga ALPHA-A3)
- Modify: `docs/strategies/s7-pead.md` (blockquote aggiornamento)
- Modify: `docs/CHANGELOG.md` (entry 2026-07-04)
- Modify: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md` (nota in testa)
- Modify: `docs/superpowers/plans/2026-07-04-s7-revival-pocs.md` (nota superseded)

- [x] **Step 1: ROADMAP — riga ALPHA-A3**

Sostituire (dentro la riga ALPHA-A3):

```
→ **POC NOT EXECUTED 2026-07-04**: transcript FMP gated su piano Ultimate ($99/mo); il PO ha acquistato Starter ($29/mo, non li include) e ha scelto di non fare l'upgrade — nessun dato raccolto (`reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md`)
```

con:

```
→ **POC IN CORSO dal 2026-07-04 via Alpha Vantage** `EARNINGS_CALL_TRANSCRIPT` (free tier, 25 req/giorno, fetch resumabile ~1 settimana; i transcript FMP richiedono Ultimate $99/mo, non acquistato — il primo executor seguiva la versione pre-correzione del piano). Piano: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`; esito entro 2026-08-01
```

- [x] **Step 2: s7-pead.md — blockquote**

Sostituire:

```
> **Aggiornamento 2026-07-04:** POC revival eseguiti — solo POC-1 (small/mid PEAD),
> esito INCONCLUSIVE_DATA (n=15 < 30 minimo). POC-2 (transcript tone) NOT EXECUTED:
> richiede FMP Ultimate ($99/mo), il PO ha acquistato Starter ($29/mo) e scelto di non
> fare l'upgrade. Vedi `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md`.
> Decisione PO pendente.
```

con:

```
> **Aggiornamento 2026-07-04 (corretto in serata):** POC revival IN CORSO. POC-1
> (small/mid PEAD): primo run INCONCLUSIVE_DATA (n=15 < 30, campione 600 simboli
> alfabetici) — in ri-esecuzione su universo completo. POC-2 (transcript tone):
> in corso via Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` free tier (i transcript FMP
> richiedono Ultimate, non acquistato; il primo run seguiva la versione pre-correzione
> del piano). Piano: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
> Esito e decisione PO entro 2026-08-01.
```

- [x] **Step 3: CHANGELOG — correggi l'entry 2026-07-04**

Sostituire il titolo `### S7 revival month — POC-1 eseguito, POC-2 not executed (vendor tier)` con `### S7 revival month — POC-1 primo run, POC-2 riavviato via Alpha Vantage (correzione)`.

Sostituire il bullet:

```
- **POC-2 (transcript tone, ALPHA-A3):** NOT EXECUTED — i transcript FMP richiedono il piano Ultimate ($99/mo); il PO ha acquistato Starter ($29/mo, non li include) e ha scelto di procedere solo con POC-1.
```

con:

```
- **POC-2 (transcript tone, ALPHA-A3):** riavviato in serata — i transcript FMP richiedono Ultimate ($99/mo, non acquistato), ma il piano corretto (`0e84850`) usa Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` (free tier, 25 req/giorno, `ALPHAVANTAGE_API_KEY` in `.env`); il primo executor seguiva la versione pre-correzione del piano. POC-1 in ri-esecuzione su universo completo (era 600 simboli alfabetici su 6.177). Resume plan: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
```

- [x] **Step 4: Decision report — nota INTERIM in testa**

Subito dopo il titolo `# S7 Revival Month — Decision Report (2026-07-04)` inserire:

```
> **NOTA (2026-07-04, sera): report INTERIM con premessa superata.** "Il PO ha deciso
> di procedere solo con POC-1" non è mai stata una decisione del PO: l'executor seguiva
> la versione pre-correzione del piano. POC-2 è eseguibile a costo zero via Alpha Vantage
> `EARNINGS_CALL_TRANSCRIPT` (chiave in `.env` dal 2026-07-04) ed è in corso; POC-1 è in
> ri-esecuzione su universo completo. Report finale sostitutivo a POC completati —
> piano: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
```

- [x] **Step 5: Piano originale — nota superseded**

In `docs/superpowers/plans/2026-07-04-s7-revival-pocs.md`, in coda al blockquote di testa (dopo la riga "**Esecutore: UN SOLO agente Sonnet...**") aggiungere:

```
>
> **SUPERSEDED per l'esecuzione (2026-07-04 sera):** Task 1–3 eseguiti dal primo run
> (versione pre-correzione). L'esecuzione riprende con
> `docs/superpowers/plans/2026-07-04-s7-revival-resume.md` — NON eseguire questo documento.
> I gate pre-registrati qui definiti restano la fonte di verità.
```

- [x] **Step 6: Commit**

```bash
git add docs/ROADMAP_DATA_ALPHA_2026-07-02.md docs/strategies/s7-pead.md docs/CHANGELOG.md docs/superpowers/plans/2026-07-04-s7-revival-pocs.md
git add -f reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md
git commit -m "docs(s7-poc): correct false premise — POC-2 was never a PO decision to skip; restarted via Alpha Vantage"
```

---

### Task 5: POC-2a — fetch transcript (cache idempotente, resumabile)

**Files:**
- Create: `scripts/fetch_s7_transcripts.py`

- [x] **Step 1: Scrivi lo script**

```python
#!/usr/bin/env python3
"""POC-2a: scarica i transcript earnings (Alpha Vantage EARNINGS_CALL_TRANSCRIPT).

I transcript FMP richiedono il piano Ultimate → si usa Alpha Vantage free tier
(25 richieste/giorno, ~5 req/min): lo script è RESUMABILE — processa finché la
quota regge, poi si ferma pulito; va rilanciato nei giorni successivi finché la
copertura è completa (~5-10 giorni di calendario per ~120 eventi).

Eventi = union di reports/s7_backtest/alpha_a5_events_2026-07-03.csv (large)
e reports/s7_poc/poc1_smallmid_events_*.csv (small/mid, se esiste).
Cache: reports/s7_poc/transcripts/{SYM}_{DATE}.json — salta gli esistenti.
Match: AV chiave i transcript per fiscal quarter (nessuna data call) → si provano
i due trimestri precedenti l'evento (reported_quarter_candidates); il worst case
è un transcript vecchio (rumore), mai informazione futura.

Run: set -a; source .env; set +a; .venv/bin/python scripts/fetch_s7_transcripts.py
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
from scripts.s7_poc_helpers import reported_quarter_candidates  # noqa: E402

_AV = "https://www.alphavantage.co/query"
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


def _fetch_quarter(key: str, symbol: str, quarter: str) -> dict | None:
    """Una chiamata AV. Ritorna {"_quota": msg} se la quota giornaliera è finita."""
    r = httpx.get(_AV, params={"function": "EARNINGS_CALL_TRANSCRIPT",
                               "symbol": symbol, "quarter": quarter,
                               "apikey": key}, timeout=30.0)
    if r.status_code != 200:
        return None
    data = r.json()
    if "Note" in data or "Information" in data:
        return {"_quota": str(data.get("Note") or data.get("Information"))}
    if data.get("transcript"):
        return data
    return None


def main() -> None:
    key = os.environ.get("ALPHAVANTAGE_API_KEY", "")
    if not key:
        print("No ALPHAVANTAGE_API_KEY in env"); return
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
        for q in reported_quarter_candidates(date):
            data = _fetch_quarter(key, sym, q)
            time.sleep(13)  # free tier: 5 req/min
            if data and "_quota" in data:
                print(f"\n⏸ Quota giornaliera AV esaurita: {data['_quota'][:120]}")
                print(f"Coperti finora: {hits + cached} match, {misses} miss — rilanciare domani.")
                return
            if data:
                content = "\n".join(
                    f"{s.get('speaker', '?')} ({s.get('title', '')}): {s.get('content', '')}"
                    for s in data["transcript"])
                found = {"symbol": sym, "event_date": date, "quarter": q, "content": content}
                break
        if found:
            with open(path, "w") as f:
                json.dump(found, f)
            hits += 1
        else:
            misses += 1
        if (hits + misses) % 10 == 0:
            print(f"  ...{hits + misses} processati oggi (match {hits}, miss {misses})")

    total = hits + misses + cached
    print(f"\nMatch: {hits + cached}/{total} ({(hits + cached) / max(total, 1):.0%}) — miss {misses}")
    if total and (hits + cached) / total < 0.5:
        print("⚠️ Copertura <50% → il gate POC-2 sarà INCONCLUSIVE_DATA (pre-registrato)")


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Primo run (giorno 1) e annota la copertura**

Run: `set -a; source .env; set +a; .venv/bin/python scripts/fetch_s7_transcripts.py 2>&1 | tee -a /tmp/poc2_fetch.log`
Expected: ~12–25 file JSON in `reports/s7_poc/transcripts/`, poi `⏸ Quota giornaliera AV esaurita`. È il comportamento corretto, non un errore.

- [x] **Step 3: Commit (solo script — la cache transcript NON si committa: contenuto vendor)**

```bash
git add scripts/fetch_s7_transcripts.py
git commit -m "feat(s7-poc): POC-2a transcript fetcher (Alpha Vantage, quarter-keyed, idempotent resumable cache)"
```

---

### Task 6: POC-2b — scoring LLM del tone (DK-CoT) + smoke

**Files:**
- Create: `scripts/score_s7_transcripts.py`

- [x] **Step 1: Scrivi lo script**

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
```

- [x] **Step 2: Smoke su 3 transcript del giorno 1**

Run (smoke): sposta temporaneamente tutti i JSON tranne 3 in `/tmp/`, esegui, verifica 3 righe valide nel CSV, ripristina i JSON, rilancia (idempotente: salta i 3 già scorati e processa il resto della cache giorno-1). **Lanciare fuori dalle 14:00–21:00 UTC.**
Expected: `tone_scores.csv` con una riga per transcript; JSON invalidi < 10%.

- [x] **Step 3: Commit**

```bash
git add scripts/score_s7_transcripts.py
git commit -m "feat(s7-poc): POC-2b LLM tone scoring (DK-CoT, kimi primary, incremental resumable CSV)"
```

---

### Task 7: Protocollo multi-giorno (fetch → score) fino a copertura completa

**Files:** nessuno nuovo (esecuzione ripetuta). Questa fase attraversa più giorni di calendario: la sessione dell'executor NON deve restare aperta — ogni giorno è un rilancio manuale (PO o nuova sessione).

- [x] **Step 1: Ogni giorno, un comando**

```bash
cd /home/stefano/Documents/Projects/Alembic && set -a; source .env; set +a; \
.venv/bin/python scripts/fetch_s7_transcripts.py 2>&1 | tee -a /tmp/poc2_fetch.log && \
.venv/bin/python scripts/score_s7_transcripts.py 2>&1 | tee -a /tmp/poc2_score.log
```

(fuori orario 14–21 UTC; il fetch consuma la quota AV del giorno, lo scoring processa il delta di cache). Expected: la riga `Match: X/Y (Z%)` cresce ogni giorno; a copertura completa il fetch stampa il totale senza `⏸`.

- [ ] **Step 2: Cutoff pre-registrato**

Se al **2026-07-26** la copertura è ancora < 50% degli eventi → fermarsi: il gate POC-2 è `INCONCLUSIVE_DATA` per regola pre-registrata; procedere comunque coi Task 8–10 sui dati raccolti (il buffer di 5 giorni serve alla decisione PO entro il 2026-08-01).

- [ ] **Step 3: Subsample agreement GLM (a copertura completa)**

Run: `TONE_MODEL=glm-5.2:cloud` sui primi 20 transcript (ordina per nome file; sposta temporaneamente gli altri JSON via come nello smoke, poi ripristina). Il CSV accumula righe con `model` diverso — servono al report per la stat di agreement.

---

### Task 8: POC-2c — analisi IC e gate

**Files:**
- Create: `scripts/analyze_s7_tone.py`

- [x] **Step 1: Scrivi lo script**

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

    half = n // 2  # split temporale: ordina per data evento
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

- [x] **Step 2: Esegui**

Run: `.venv/bin/python scripts/analyze_s7_tone.py 2>&1 | tee /tmp/poc2_analysis.log`
Expected: IC, terzili, split-half, agreement, verdetto PASS/FAIL/INCONCLUSIVE_DATA.

- [x] **Step 3: Commit**

```bash
git add scripts/analyze_s7_tone.py
git commit -m "feat(s7-poc): POC-2c tone IC analysis + pre-registered ALPHA-A3 gate"
```

---

### Task 9: Decision report FINALE (sostituisce l'interim)

**Files:**
- Create: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_<data-finale>.md`
- Modify: `docs/ROADMAP_DATA_ALPHA_2026-07-02.md`, `docs/strategies/s7-pead.md`, `docs/CHANGELOG.md`

- [ ] **Step 1: Scrivi il report** con questa struttura esatta:

```markdown
# S7 Revival Month — Decision Report FINALE (<data>)

> Sostituisce l'interim `S7_REVIVAL_DECISION_REPORT_2026-07-04.md` (premessa POC-2 superata).

## Esito sintetico
| POC | Gate | Esito | Numero chiave |
|---|---|---|---|
| POC-1 small/mid PEAD (run universo completo) | net drift ≥+1.5%, hit>55%, n≥30 | PASS/FAIL/INCONCLUSIVE_DATA | ... |
| POC-2 transcript tone | IC≥0.10, spread terzili ≥1.5%, split-half, n≥30 | PASS/FAIL/INCONCLUSIVE_DATA | ... |

## POC-1 — dettaglio  (funnel run completo vs run 600-alfabetico; tabella BEAT/MISS; range cap effettivo; se n<30: nota "gli scartati IEX/ADV non sono comunque tradabili da Alembic → INCONCLUSIVE strutturale = ipotesi non sfruttabile per questo sistema")
## POC-2 — dettaglio  (copertura transcript X/Y e giorni di fetch; IC; terzili; split-half; IC dentro i soli BEAT; agreement kimi/glm; concordanza guidance; JSON-fail rate)
## Costi consuntivi   (FMP Starter $29; Alpha Vantage $0; LLM: stima da len(prompt)/4 × n_chiamate; giorni di calendario usati)
## Raccomandazione al PO (binaria)
- Entrambi FAIL → rimozione completa S7 (beat tasks earnings-pead/pead-ingestion,
  lifecycle → disabled, archivio docs) + disdetta FMP Starter prima del rinnovo
  (valutando prima il riuso Starter per ALPHA-A2/D1 — nota collaterale interim report).
- Un PASS → cosa costruire e con quali dati, con il numero che lo giustifica.
- INCONCLUSIVE_DATA → cosa è mancato, a che costo si otterrebbe, e se l'ostacolo è
  strutturale (non-tradabilità) dirlo esplicitamente.
```

Ogni cella coi numeri reali dei log/CSV. Nessun "TBD".

- [ ] **Step 2: Aggiorna i doc di stato**

- `docs/ROADMAP_DATA_ALPHA_2026-07-02.md`: nelle righe ALPHA-A3 e ALPHA-A5 sostituire "POC IN CORSO..." con l'esito finale + link al report finale.
- `docs/strategies/s7-pead.md`: sostituire il blockquote "in corso" con l'esito + link.
- `docs/CHANGELOG.md`: nuova entry datata: esito POC-1 (run completo), esito POC-2, link report finale.
- `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md`: nella NOTA in testa aggiungere `Report finale: S7_REVIVAL_DECISION_REPORT_<data>.md`.

- [ ] **Step 3: Commit**

```bash
git add -f reports/s7_poc/S7_REVIVAL_DECISION_REPORT_*.md reports/s7_poc/tone_scores.csv
git add docs/ROADMAP_DATA_ALPHA_2026-07-02.md docs/strategies/s7-pead.md docs/CHANGELOG.md
git commit -m "docs(s7-poc): FINAL revival decision report (POC-1 full universe + POC-2 transcript tone)"
```

---

### Task 10: Verifica finale

- [ ] **Step 1: Suite completa**

Run: `.venv/bin/python -m pytest tests/ -q 2>&1 | tail -3`
Expected: nessuna failure NUOVA rispetto alla baseline (10 failed pre-esistenti note al 2026-07-04 — le stesse identiche; i 16 test helper verdi).

- [ ] **Step 2: Lint**

Run: `.venv/bin/python -m ruff check scripts/s7_poc_helpers.py scripts/backtest_s7_smallmid.py scripts/fetch_s7_transcripts.py scripts/score_s7_transcripts.py scripts/analyze_s7_tone.py`
Expected: clean (se ruff non è configurato nel repo, salta e annota).

- [ ] **Step 3: Riepilogo per il PO**

Nel messaggio finale: i due verdetti, i numeri chiave, il path del report finale, e il promemoria **disdetta FMP Starter prima del rinnovo se la decisione è rimozione** (dopo aver valutato il riuso per ALPHA-A2/D1).

---

## Cosa questo piano NON fa (di proposito)

- Non modifica `strategy_lifecycle` né il beat schedule: rimozione/riattivazione S7 = decisione PO a valle del report finale.
- Non modifica i gate pre-registrati del piano originale (soglie, benchmark, costi, cap 120 transcript).
- Non ritesta il PEAD large-cap (FAIL conclusivo 2026-07-03).
- Non committa il contenuto dei transcript (materiale vendor): solo score derivati.
- Non compra nulla: AV Plan 75 ($49.99, chiuderebbe il fetch in 1 giorno) resta un'opzione del PO, non dell'executor.
