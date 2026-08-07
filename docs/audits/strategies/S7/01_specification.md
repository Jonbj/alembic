# S7 — 01 Specificazione funzionale e matematica

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04
**Stato:** **RIMOSSA il 2026-07-15** (commit `d1e6de6`); sorgente recuperato da
git history (commit `1dd2c35`).
**Fonti:** `git show 1dd2c35:src/strategies/s7/{strategy,signal,__init__}.py`,
`git show 1dd2c35:src/models/pead.py`, `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`,
`docs/strategies/s7-pead.md`, `config/strategies.yaml` (entry S7 rimossa),
`strategy_lifecycle` DB (S7 = research/not approved).
**Stato (lifecycle DB):** `mode=research`, `approved=f`, gate_report
`ALPHA_A5_gate_report_2026-07-03_fmp.md`, nessun `promoted_at`.
**Runtime:** **zero ordini in tutto il lifecycle** (mai wired nel
`PortfolioOrchestrator`, `enabled=false`).

S7 è una strategia **event-driven** rimossa: scommetteva sul PEAD (drift
post-annuncio earnings). Auditata da git history + docs perché il sorgente non
esiste più nel working tree.

---

## 0. Contesto: design rationale (dal lifecycle doc §1)

S7 = **PEAD (Post-Earnings Announcement Drift)**: dopo una sorpresa positiva
negli earnings, il prezzo non incorpora subito tutta l'informazione → drift
positivo misurabile nei giorni successivi (Ball-Brown 1968, Foster et al. 1984).
S7 catturava l'effetto classificando gli 8-K filing SEC via LLM (Ollama, DK-CoT).

**Edge dichiarati** (`ROADMAP_DATA_ALPHA_2026-07-02`, Vettore A):
- **ALPHA-A2** — consensus EPS/revenue esterno → surprise da consensus reale.
  *Stato: mai wired (consensus rotto/assente → surprise_pct null → soglia 0.05
  mai superata).*
- **ALPHA-A3** — transcript tone (alpha qualitativo): tone del transcript →
  signal. *L'edge specifico di S7, dove l'LLM brilla vs fattori numerici.*
- **ALPHA-A5** — POC backtest go/no-go (drift netto ≥1.5% a 20d, hit-rate >55%,
  large vs small cap).
- **Vettore D** (ALPHA-D1) — analyst revisions come alimentatore del drift.

## 1. Segnale: surprise classificata da 8-K via LLM

`EarningsSurpriseClassifier.to_signal` (`signal.py:24-57`, commit `1dd2c35`):

1. Input: `EarningsLLMOutput` (pydantic, `models/pead.py`) — LLM parse dell'8-K:
   - `ticker`, `filing_type` (earnings_8k|guidance|other), `eps_actual`,
     `eps_consensus`, `surprise_pct`, `direction` (beat|miss|inline|no_eps),
     `guidance` (revised-up|down|maintained|no-guidance), `confidence∈[0,1]`.
2. Gate quality (`signal.py:33-47`):
   - `direction ∈ {no_eps, inline}` → reject.
   - `confidence < min_confidence (0.70)` → reject.
   - `surprise_pct is None` → reject (consensus assente).
   - `abs(surprise_pct) < surprise_threshold (0.05)` → reject.
3. Output: `SurpriseSignal` (`models/pead.py:25-49`):
   - `symbol`, `direction` (beat|miss|inline), `surprise_pct`, `confidence`,
     `filing_id`, `detected_at`, `hold_until = detected_at + hold_days (20)`.
   - `is_active(as_of)`: `ts <= hold_until` (hold window 20 giorni).

**Formula di sorpresa** (implicita): `surprise_pct = (eps_actual − eps_consensus) /
|eps_consensus|` (o analogo), MA calcolata **dall'LLM dal testo dell'8-K** o da
consensus esterno (ALPHA-A2). Il lifecycle doc nota: consensus mai wired →
`surprise_pct` spesso null → soglia 0.05 mai superata → **carburante zero**.

## 2. Strategia: sizing long-only beat

`PEADStrategy.compute_target_weights` (`strategy.py:33-60`):

```python
ts = as_of or now(utc)
eligible = [s for s in signals
            if s.direction == "beat"           # LONG-ONLY: solo beat
            and s.confidence >= 0.70
            and s.is_active(as_of=ts)]         # hold window 20d
if not eligible: return {}
weights = {}
sleeve_used = 0.0
for sig in eligible:
    if sleeve_used >= max_sleeve_pct (0.25): break
    alloc = min(max_position_pct (0.05), max_sleeve_pct - sleeve_used)
    if alloc <= 0: break
    weights[sig.symbol] = alloc   # pari peso (0.05) fino a cap sleeve
    sleeve_used += alloc
return weights
```

- **Long-only beat**: `direction == "beat"`; i `miss` **non allocati** (servono
  come trigger di exit nel caller, `strategy.py:16-17`).
- **Sizing**: pari peso `max_position_pct=0.05` per posizione, cap sleeve
  `max_sleeve_pct=0.25` → max 5 posizioni (0.05×5=0.25).
- **Hold**: 20 giorni (`hold_until = detected_at + 20d`), `is_active` gate.
- **min_confidence=0.70**, **surprise_threshold=0.05** (|surprise|≥5%).

## 3. Config (PEADConfig, `strategy.py:13-21`)

| Parametro | Default | Ruolo |
|---|---|---|
| `max_position_pct` | 0.05 | cap per posizione (5%) |
| `max_sleeve_pct` | 0.25 | cap sleeve totale (25%) |
| `min_confidence` | 0.70 | gate LLM confidence |
| `surprise_threshold` | 0.05 | gate |surprise| ≥ 5% |
| `hold_days` | 20 | hold window |
| `strategy_id` | "S7" | |

**Config yaml** (rimossa): `enabled=false`, `allocation_pct=0.15` (lifecycle
doc §2 — nota: 0.15 vs cap sleeve 0.25; allocation sleeve ≠ max_sleeve).

## 4. Pipeline / integrazione (pre-rimozione)

| Componente | Path (rimosso) | Stato |
|---|---|---|
| Strategy | `src/strategies/s7/` | rimosso |
| Worker 8-K | `src/workers/pead_worker.py` | rimosso (Ollama) |
| Worker earnings | `src/workers/earnings_pead_worker.py` | rimosso (Finnhub) |
| EDGAR ingestion | `run_sec_edgar_ingestion_worker` | rimosso |
| Beat task | `pead-ingestion` (celery, 30min, 14:05-21:35 UTC, queue `inference`) | rimosso |
| API routes | `src/api/routes/pead_routes.py` | rimosso |
| Persistenza | `pead_signals` table | **mai materializzata** (DDL solo doc, nessuna migration) |
| Connector | `src/connectors/earnings_calendar.py` | rimosso (no consumer) |
| Redis | `signal:*:pead_event`, `pead:processed:*` | non più scritti (TTL 30d esaurisce) |

## 5. Stato di integrazione runtime (N/A — mai live)

- **Mai wired nel `PortfolioOrchestrator`** (P0-13, commit `6d86d3f`).
- `enabled=false`, `allocation_pct=0.15` (ma sleeve 0.25).
- **Zero ordini in tutto il lifecycle** (carburante zero: consensus assente +
  bug EDGAR ticker → `surprise_pct` null → soglia 0.05 mai superata).
- **`pead_signals` table mai materializzata** (DDL solo in ARCHITECTURE.md,
  nessuna migration la crea nel DB live).
- `strategy_lifecycle`: nessuna row seedata per S7 (migration 025 inserisce solo
  S1/S2/S4); S7 = research/SHELVED in audit history.
- S7 SHELVED 2026-07-03 dopo ALPHA-A5 FAIL; revival POC autorizzato PO 2026-07-15
  (PO-5); POC-2 FAIL → REMOVE 2026-07-15.

## 6. Pseudocodice (design originale)

```
each pead-ingestion tick (30min, market hours):
  8-K filings from EDGAR (earnings_8k) → +5min → Ollama LLM classification
  EarningsLLMOutput {ticker, eps_actual, eps_consensus, surprise_pct, direction, confidence}
  classifier.to_signal:
    reject if direction in {no_eps, inline} or confidence<0.70 or surprise null or |surprise|<0.05
    SurpriseSignal {symbol, direction, surprise_pct, confidence, hold_until=detected_at+20d}
  persist to pead_signals (MAI MATERIALIZZATA)

portfolio cycle (mai wired):
  eligible = active beat signals (is_active, confidence≥0.70, direction=beat)
  pari peso 0.05 per posizione, cap sleeve 0.25 (max 5 posizioni)
  exit when hold_until expires (20d) or miss signal triggers exit
```

## 7. Risultati delle valutazioni (dal lifecycle doc §3 — evidenza locale)

| Valutazione | Data | n | Esito | Ragione |
|---|---|---|---|---|
| Finnhub | 07-03 | 0 | INCONCLUSIVE | 0 eventi (calendar ~30g back) |
| ALPHA-A5 large-cap | 07-03 | 76 | **FAIL** | drift=beta SPY, hit 51% (<55%), no dose-response, media excess +0.05%, mediana −1.07% |
| POC-1 small/mid | 07-04 | 15 | INCONCLUSIVE_DATA | n<30, copertura IEX/liquidità insufficiente |
| POC-2 transcript tone | 07-15 | 73 | **FAIL (decision-grade)** | IC(tone,excess_20d)=+0.012 (~0), tercile spread −0.93% (invertito), split-half −0.230/+0.244 (opposti), cross-model kimi↔glm ρ=+0.858 (FAIL non artefatto) |

**Verdetto finale**: l'edge numerico (raw surprise PEAD) è **competuto su
large-cap** (beta, non alpha); l'edge qualitativo dichiarato (transcript tone) è
**confutato cross-modello** a sample decision-grade (IC≈0); l'universo small/mid
(dove l'edge accademico vive) non è raggiungibile con copertura sufficiente. S7
rimossa (PO-5 condizionale "Se POC-2 FAIL → REMOVE" attivata).

## 8. Punti chiave per le fasi 05-07

- **Mai live**: S7 non ha path runtime attivo → fase 06 "runtime" = MORTO/
  mai deployato. Nessun trade, nessuna row DB materializzata.
- **Consensus mai wired (ALPHA-A2)**: il carburante del segnale era assente →
  `surprise_pct` null → soglia 0.05 mai superata → zero ordini. Bug di
  integrazione (non di logica S7) ma fatale per l'operatività.
- **`pead_signals` table mai materializzata**: DDL solo doc, nessuna migration
  → persistenza mai funzionante. Da citare come bug di integrazione in fase 07.
- **POC-2 FAIL decision-grade** (IC +0.012, n=73): è la **misura di alpha del
  progetto** per S7 → verdetto fase 04 allineato (NEGATIVE/UNPROVEN confutato).
- **Cross-model agreement** (kimi↔glm ρ=+0.858): il FAIL non è artefatto di un
  modello → robustezza del verdetto negativo.

---
**Stato fase:** 01_specification = **done**. Prossimo cursore: `S7:02_hypothesis`.