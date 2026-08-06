# S7 — 05 Code Mapping

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04
**Nota critica:** S7 è **rimossa** (commit `d1e6de6`, 2026-07-15). I riferimenti
`file:line` sono ricostruiti da **git history** (commit `1dd2c35`, ultimo stato
prima della rimozione). Nel working tree attuale i file **non esistono**. La
mappatura è quindi una ricostruzione archeologica, non un'ispezione del codice
vivo. Le divergenze (DV) sono vs la specifica di fase 01.

## Mappatura spec → codice (git `1dd2c35`)

| Componente spec (fase 01) | File:line (git `1dd2c35`) | Note |
|---|---|---|
| **Config** `PEADConfig` | `src/strategies/s7/strategy.py:10-19` | dataclass: max_position_pct=0.05, max_sleeve_pct=0.25, min_confidence=0.70, surprise_threshold=0.05, hold_days=20, strategy_id="S7" |
| **Eligible filter** (beat + conf + active) | `strategy.py:49-54` | `s.direction=="beat" and s.confidence>=cfg.min_confidence and s.is_active(as_of=ts)` |
| **Sizing** pari peso cap sleeve | `strategy.py:59-69` | `alloc=min(max_position_pct, max_sleeve_pct - sleeve_used)`, loop break a cap sleeve |
| **Classifier gates** | `src/strategies/s7/signal.py:35-46` | reject no_eps/inline (:35), confidence<0.70 (:38), surprise None (:42), \|surprise\|<0.05 (:45) |
| **SurpriseSignal build** | `signal.py:48-55` | hold_until = detected_at + timedelta(days=hold_days) |
| **EarningsLLMOutput** model | `src/models/pead.py:10-21` | ticker, filing_type, eps_actual, eps_consensus, surprise_pct (None ok), direction, guidance, confidence∈[0,1] |
| **SurpriseSignal** model | `pead.py:24-38` | is_active: `ts <= hold_until` (:37-38) |
| **Filing type** | `pead.py:14` | Field description "earnings_8k | guidance | other" |

## Mappatura runtime (assente — rimosso)

| Componente spec | File (git, rimosso in `d1e6de6`) | Stato working tree |
|---|---|---|
| Worker 8-K Ollama | `src/workers/pead_worker.py` | rimosso |
| Worker Finnhub earnings | `src/workers/earnings_pead_worker.py` | rimosso |
| Connector calendar | `src/connectors/earnings_calendar.py` | rimosso (no consumer) |
| API routes | `src/api/routes/pead_routes.py` | rimosso (+ import in `src/api/main.py`) |
| Beat task | `pead-ingestion` in `celery_app.py` | rimosso |
| Redis store | `src/store/redis_store.py` `write/read_pead_signal`, `is/mark_pead_processed` | rimosso |
| Config entry | `config/strategies.yaml` S7 | rimosso |
| Stop sizing | `config/trading.yaml` S7 stop | rimosso |
| `PEAD_*` settings | `src/config.py` | rimosso |
| API/display constants | `S7_STRATEGY/S7_DETAIL/GATES_S7/SENSITIVITY_S7` in `src/api/routes/strategies.py`, pead rows in `system_routes.py` | rimosso |
| Cross-ref comments | `stop_policy.py`, `portfolio_scheduler.py`, `loss_feedback.py`, `ingestion.py`, `celery_app.py` | rimosso |
| Tests | `test_s7_pead.py`, `test_pead_worker.py`, `test_earnings_pead_worker.py`, `test_earnings_calendar.py` | rimossi |

**Verifica working tree (2026-08-04, read-only):**
```
ls src/strategies/s7/ src/models/pead.py src/workers/pead_worker.py
  → No such file or directory (tutti)
grep "S7|PEAD|pead" src/strategies/registry.py src/workers/portfolio_scheduler.py
  → nessun match (S7 NON è nel registry né nello scheduler)
```
→ **S7 è completamente assente dal path runtime**. La rimozione è pulita.

## Preserved (evidenza + guard, dal commit `d1e6de6`)

| Artefatto | Stato | Scopo |
|---|---|---|
| `tests/test_p0_13_strategy_containment.py::TestS7NotInOperationalRegistry` | **VIVO** nel working tree | guard anti-reintroduzione: S7 non deve rientrare nel `StrategyRegistry` (nemmeno disabled/research). Se presente, deve essere `mode=research` e non in `get_active_strategies()` (`test_p0_13:62-97`). |
| `tests/analysis/test_s7_poc_helpers.py` | VIVO | helper dei POC script (evidenza misurazione) |
| POC scripts `scripts/*s7*`, `*pead*` + `reports/s7_*` | gitignored (evidenza) | misurazioni POC-1/POC-2/ALPHA-A5 |
| `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` | VIVO | storia completa (rimozione + 4 valutazioni) |
| `strategy_lifecycle_audit` DB | immutabile | audit trail (nessuna row S7 seedata v. fase 01) |

## Divergenze spec ↔ codice (DV-S7)

### DV-S7-1 — `surprise_pct` calcolato dall'LLM, non da consensus reale (carburante debole)

**Spec (fase 01)**: surprise da consensus esterno (ALPHA-A2) →
`surprise_pct = (eps_actual − eps_consensus)/|eps_consensus|`.

**Codice** (`pead.py:17`): `surprise_pct: float | None = None` — il campo è
**opzionale**, popolato dall'LLM parsing dell'8-K. Nessun binding a un
consensus esterno (Zacks/Refinitiv/FMP) nel codice. `signal.py:42` reject se
`surprise is None` → se l'LLM non estrae surprise (o consensus assente), il
segnale è scartato.

**Divergenza**: il design dichiarava consensus esterno (ALPHA-A2); il codice
usa LLM-extracted surprise. Il lifecycle doc conferma ALPHA-A2 **mai wired** →
`surprise_pct` spesso null → soglia 0.05 mai superata → **carburante zero** →
zero ordini lifecycle. **DV-S7-1 è la causa strutturale del "mai live"**.

**Impatto**: la strategia non ha mai avuto carburante. Non è un bug di logica
S7 (i gate sono corretti) ma un **gap di integrazione upstream** (consensus
provider non wired). Per un revival, ALPHA-A2 deve essere wired prima.

### DV-S7-2 — Universo ALPHA-A5 (large-cap) vs fenomeno vivo (small-cap)

**Spec (fase 01)**: universo = SEC 8-K filings (large/mid US), ALPHA-A5 large-cap.

**Codice**: nessun filtro universo in `strategy.py`/`signal.py` (l'universo è
implicito nel feed 8-K/earnings calendar, rimosso). Il lifecycle doc §3
conferma: ALPHA-A5 testato su **large-cap** (n=76), POC-1 small/mid fallito per
**copertura IEX insufficiente** (n=15).

**Divergenza**: la letteratura (Quant Decoded 2025, fase 03) indica
small-cap net 3.8% vs large-cap 1.6%. S7 era configurata sull'universo
**competuto**. **DV-S7-2 è la causa strutturale del FAIL numerico** (ALPHA-A5
drift=beta). Per un revival, l'universo deve essere small/mid (MA richiede
copertura dati che il progetto non ha — IEX insufficiente).

### DV-S7-3 — Long-only beat vs PEAD simmetrico

**Spec (fase 01)**: `direction == "beat"` solo (`strategy.py:51`).

**Codice**: `strategy.py:51` filtro `s.direction == "beat"`. I `miss` sono
**non allocati** (`strategy.py:26` docstring: "Miss signals are not allocated;
they serve as a trigger for exit in the caller"). MA il caller (portfolio
scheduler) **non è mai stato wired** → l'exit su miss non esiste.

**Divergenza**: PEAD canonico è **simmetrico** (beat long, miss short). S7
long-only beat = gamba debole (Druz 2015: negatività predice più forte).
**DV-S7-3 è la causa strutturale del FAIL qualitativo parziale** — la gamba
long-only positiva è il lato debole del fenomeno. Per un revival, simmetrizzare
(short su miss) o quantomeno tenere il miss come exit (MA richiede wiring
caller).

### DV-S7-4 — `hold_days=20` vs tone edge orizzonte 5-10g

**Spec (fase 01)**: `hold_days=20` (`strategy.py:18`).

**Codice**: `hold_until = detected_at + timedelta(days=20)` (`signal.py:55`),
`is_active` gate `ts <= hold_until` (`pead.py:37-38`).

**Divergenza**: la letteratura tone (Hameleers 2025, fase 03) indica edge vivo
a **5-10g** (Sharpe>1), decade a 20g. S7 hold 20d → orizzonte oltre il decay
del tone edge. **DV-S7-4 è un mismatch di orizzonte** — troppo lungo per il
tone (alpha specifico), ragionevole per il PEAD numerico (che è competuto su
large-cap). Per un revival tone, hold 5-10g.

### DV-S7-5 — Carburante tone = polarity sentiment, non embedding contestuale

**Spec (fase 01)**: LLM classificazione 8-K → `direction`/`surprise_pct`/
`confidence` (strutturato). L'edge dichiarato è **transcript tone** (ALPHA-A3).

**Codice**: `pead.py:10-21` `EarningsLLMOutput` ha `direction`, `surprise_pct`,
`confidence` — campi **strutturati/discreti**, non embedding vettoriali. Il
"tone" è catturato come `direction` + `confidence` + `guidance` (discreti),
non come embedding contestuale (SBERT).

**Divergenza**: la letteratura (Chung 2023, fase 03) indica edge tone vivo con
**embedding contestuali** (SBERT), non polarity sentiment (che decade OOS
post-2020). S7 usava polarity-strutturato → la forma debole. **DV-S7-5 è la
causa strutturale del FAIL qualitativo** (POC-2 IC +0.012). Per un revival,
usare embedding contestuali, non polarity.

### DV-S7-6 — Caller (portfolio scheduler / orchestrator) mai wired

**Spec (fase 01)**: portfolio cycle legge `SurpriseSignal` attivi, sizing pari
peso cap sleeve, exit su hold_until/miss.

**Codice**: `PEADStrategy.compute_target_weights` (`strategy.py:32-71`) è
definito MA **nessun caller** nel working tree. `grep` su
`portfolio_scheduler.py`/`portfolio_orchestrator.py` → nessun match S7/PEAD.
Il lifecycle doc conferma: mai wired (P0-13), zero ordini lifecycle.

**Divergenza**: la logica di sizing esiste ed è corretta, MA non è mai stata
integrata nel `PortfolioOrchestrator`. **DV-S7-6 = la strategia non ha mai
eseguito** — è rimasta R&D-only (coerente con `mode=research`, `approved=f`).
Non è un bug ma una **scelta di governance** (non promuovere senza POC PASS).

### DV-S7-7 — `pead_signals` table mai materializzata

**Spec (fase 01)**: persistenza `pead_signals` table.

**Codice**: il commit `d1e6de6` message: "pead_signals never materialized (DDL
was doc-only, no migration) → no drop migration needed." Nessuna migration crea
la tabella nel DB live.

**Verifica (read-only, 2026-08-04):**
```
docker exec alembic-postgres-1 psql -U trading -d trading -c "\d pead_signals"
  → did not find any relation (da verificare in fase 06)
```
**Divergenza**: la persistenza dichiarata non è mai esistita. I segnali (se
generati) sarebbero stati in Redis (`signal:*:pead_event`, rimosso) MA non nel
DB. **DV-S7-7 = nessuna persistenza strutturale** → nessuna audit trail DB di
segnali S7 (coerente con zero ordini).

## Sintesi divergenze

| DV | Tipo | Causa | Impatto |
|---|---|---|---|
| DV-S7-1 | carburante | consensus mai wired (LLM-extracted surprise) | zero ordini (strutturale) |
| DV-S7-2 | universo | large-cap competuto vs small-cap vivo | FAIL numerico (ALPHA-A5) |
| DV-S7-3 | direzione | long-only beat vs simmetrico | gamba debole |
| DV-S7-4 | orizzonte | hold 20d vs tone 5-10g | decay del tone edge |
| DV-S7-5 | feature | polarity vs embedding | FAIL qualitativo (POC-2) |
| DV-S7-6 | integrazione | orchestrator mai wired | mai eseguita (governance) |
| DV-S7-7 | persistenza | table mai materializzata | nessuna audit trail DB |

**Le 7 DV sono tutte coerenti** con la decisione di rimozione. La strategia
era configurata sulla **forma debole/competuta** su ogni dimensione
controllabile (universo, direzione, orizzonte, feature, carburante) e non
era integrata (orchestrator, persistenza). La rimozione su POC-2 FAIL è la
**conclusione corretta**: nessun revival parziale (es. solo wired il
consensus) salverebbe S7, perché le DV-2/3/4/5 (universo, direzione,
orizzonte, feature) sono tutte sulla forma debole.

## Confronto con le DV di S1/S4

S7 condivide con S1/S4 le DV di **forma debole** (long-only, polarity, large-cap,
orizzonte mismatch). La differenza è la **governance**: S7 è stata misurata
(POC decision-grade) e killata; S1/S4 no. Per la cross_review: il pattern
"polarity + long-only + large-cap + orizzonte sbagliato" è un **deficit
trasversale** del design alpha del progetto, non specifico di S7.

---
**Stato fase:** 05_code_mapping = **done**. Prossimo cursore: `S7:06_implementation_audit`.