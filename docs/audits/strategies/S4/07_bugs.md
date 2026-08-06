# S4 — 07 Bug

**Strategia:** S4 `NewsDrivenTactical`
**Data:** 2026-08-04
**Metodo:** ogni bug confermato da repro eseguito o traccia statica
deterministica. Nessun bug asserito senza conferma.

## Riepilogo bug confermati

| ID | Severità | Luogo | Conferma |
|---|---|---|---|
| BUG-A | HIGH (validità backtest) | `backtest.py` (no entry_threshold) vs `portfolio_scheduler.py:1277-1340` | repro_1 ESEGUITO |
| BUG-B | HIGH (validità backtest) | `backtest.py:269-289` (`_generate_synthetic_signals`) | repro_2 ESEGUITO |
| BUG-C | LOW | `strategy.py:74-75` (`health_check` no-op) | traccia statica |
| OBS-1 | osservazione | `execution_decisions.score` vs `signal_score` naming | traccia DB (non bug) |

---

## BUG-A — Drift gate backtest/live: il backtest non applica l'entry gate ratchet (HIGH)

**Luoghi:** `src/workers/portfolio_scheduler.py:1277-1340` (live gate),
`src/strategies/s4/backtest.py` (backtest, **0 riferimenti** a entry_threshold),
`src/strategies/s4/config.py:14-19` (min_score prefiltro).

**Descrizione:** il **gate d'ordine live** è `feedback:entry_threshold:S4`
(ratchet dinamico, baseline 0.30, `portfolio_scheduler.py:1277-1340`). Il
**backtest** non lo replica: applica solo il prefiltro ranker `min_score=0.10`
(`ranking.py:181`). Un segnale con `score ∈ [0.10, 0.30)` è **ammesso in
backtest** ma **respinto in live**. L'OOS Sharpe del backtest over-admit vs il
comportamento live → il backtest **non è rappresentativo** del live.

`config.py:14-19` è esplicito che `min_score` è un prefiltro e il gate ordine è
upstream, MA il backtest non implementa l'upstream gate.

**Conferma (repro_1, statica):**
```
entry_threshold references in backtest.py: 0
entry_threshold references in portfolio_scheduler.py: 9
CONFIRMED: backtest.py has 0 references to entry_threshold; scheduler has 9.
The live ratchet gate (baseline 0.30) is NOT replicated in the backtest.
```

**Impatto:** qualunque OOS Sharpe calcolato dal backtest S4 sovrastima l'ammissione
vs il live. Combinato con BUG-B, il backtest S4 è non-rappresentativo su due
dimensioni. (Nota: `reports/s4_backtest/summary.json` non esiste, quindi il
bug è latente — ma se il backtest viene runnato, produrrà risultati non
comparabili col live.)

## BUG-B — Fallback segnali sintetici: il backtest misura rumore senza guard (HIGH)

**Luogo:** `src/strategies/s4/backtest.py:247-289` (`_load_sentiment_signals`
fallback → `_generate_synthetic_signals`), `backtest.py:139-140` (scrittura
summary.json senza flag).

**Descrizione:** se PostgreSQL non è disponibile, `_load_sentiment_signals`
(`backtest.py:263-266`) cattura l'eccezione e chiama `_generate_synthetic_signals`
(`backtest.py:269-289`), che produce segnali **casuali** (`rng.uniform(-0.5,0.9)`
per score, `rng.uniform(0.3,0.9)` per confidence), `model_id='synthetic'`. Il
backtest runner (`run_s4_backtest_from_prices_and_signals`) poi esegue WF + gate
su questi segnali casuali e scrive `summary.json`/`gate_report.json` **senza
alcun flag** che distingua sintetico da reale. Un backtest runnato senza DB
misura **rumore** (bucket long-only selezionato a caso ≈ beta di mercato
dell'universo), non alpha di sentiment, ed è silenziosamente indistinguibile da
un backtest reale nell'artefatto.

**Conferma (repro_2, eseguito):**
```
synthetic signals: 182 rows, models: {'synthetic'}
score range: [-0.490, 0.889] (rng.uniform(-0.5, 0.9))
reasoning: {'synthetic'}
CONFIRMED: _generate_synthetic_signals produces RNG-uniform signals ... but the
backtest runner writes summary.json with NO flag distinguishing synthetic from real.
```

**Impatto:** `reports/s4_backtest/summary.json` **non esiste** (fase 04) →
coerente con "backtest mai runnato O runnato su rumore sintetico e poi
scartato." Se qualcuno runna il backtest senza DB, otterrà un Sharpe ≈ beta di
mercato dell'universo S1 (long-only su large-cap) che **sembrerà alpha** ma è
rumore + beta. Nessun guard avverte. Questo è il bug più pericoloso per la
**validità delle decisioni**: un numero spurio potrebbe sbloccare la promozione.

## BUG-C — `health_check` è un no-op (LOW)

**Luogo:** `src/strategies/s4/strategy.py:74-75`
```python
def health_check(self) -> bool:
    return True
```

**Descrizione:** `health_check` ritorna `True` incondizionatamente, senza
verificare segnali, dati, o configurazione. A differenza di S3
(`strategy.py:141-151` verifica NaN/inf/empty), S4 non valida nulla. Il
backtest `run_s4_backtest_from_prices_and_signals` non chiama `health_check`
(a differenza di S3 `backtest.py:41`), quindi l'impatto è limitato, MA è un gap
di defensive coding: un caller che si affida a `health_check` non riceve
alcuna garanzia.

**Conferma (traccia statica):** `strategy.py:74-75` ritorna `True` costante;
nessun `if`/validazione. Contrasto con S3 `health_check` (`strategy.py:141-151`)
che verifica `isna().any()`, `isinf().any()`, `empty`.

**Impatto:** LOW — non usato nel path critico backtest; MA in un path live che
lo chiamasse, darebbe falsa sicurezza.

## OBS-1 — `execution_decisions.score` vs `signal_score` (osservazione, non bug)

**Luogo:** `trades`/`execution_decisions.score` (0.020 costante su S4 BUY),
`signal_score` (sentiment raw, es. 0.356).

**Descrizione:** in `execution_decisions`, S4 BUY hanno `score=0.020`
(costante) e `signal_score` = sentiment raw (0.356, 0.388, ...). Traccia DB
(2026-08-04): `score=0.020 = bucket_pct(0.10) × per_ticker_weight(1/5)`, con
`regime_mult=0.700` applicato separatamente al qty. Quindi `score` è il **peso
target** (2%), non il sentiment. **Non è un bug** — conferma che
`fixed_slot_sizing` è **live e funzionante** (tutti i pesi = 2% = 1/5 × 10%,
slot non ridistribuiti). È una **confusione di naming** (colonna `score` che
contiene un peso), non un difetto logico. Documentato per evitare di asserirlo
come bug e per la `cross_review` (conferma fixed-slot live).

---

## Bug non confermati / non ricercati

- **Race conditions**: idempotency fired signals (P2-05-A, `:552,960-987`) è
  difensiva e fail-closed; non ricercata in profondità ma il design è corretto.
- **Accounting divergences**: net_pnl/gross_pnl attivi, costi popolati; nessuna
  divergenza evidente nel campione (P&L +$329, costs ~$80).
- **Signal_id coupling**: FIXATO (#109, B33-follow-up) — la traccia DB mostra
  `signal_id` coerente fra `execution_decisions` e `trades`. Non un bug aperto.
- **Stale-evidence**: freshness `max_signal_age_hours=4` applicata backtest/live
  (QS-07); provenance pinning previene stale "latest signal" fetch.
- **Weekend/off-by-one**: `signals_lookback_hours=96` copre il gap Fri→Tue
  (`config.py:38`); non ricercato in profondità ma mitigato dal design.
- **IC negativo**: NON è un bug di implementazione — è la **misura di validità
  del segnale** (fase 04/06). Il sistema esegue fedelmente un segnale non-
  predittivo; il problema è l'ipotesi, non il codice.

## Sintesi

S4 ha **2 bug HIGH di validità backtest** (BUG-A gate drift, BUG-B fallback
sintetico), **1 bug LOW** (BUG-C health_check no-op), e **1 osservazione non-bug**
(OBS-1 fixed-slot confermato live). Criticamente, **nessun bug nel path live**:
il sistema live paper funziona come progettato (idempotency, provenance, gate
ratchet, fixed-slot). I bug sono nel **backtest/validazione**, che è non-
rappresentativo (gate drift + fallback rumore). Il problema di fondo — IC<0 —
non è un bug ma la **non-validità del segnale**, che la governance riconosce
(`promotion_blocked=true`, P0-13).

I 2 bug di backtest sono i più azionabili: (1) replicare l'entry gate nel backtest
oppure documentare esplicitamente la divergenza; (2) aggiungere un guard che
falisca/avverta quando il backtest gira su segnali sintetici. Entrambi riducono
il rischio di decisioni di promozione basate su backtest non-rappresentativi.

---

## Correzione post-audit (2026-08-06)

**La conclusione "nessun bug nel path live" non regge.** L'analisi delle
perdite del 2026-08-05 ne ha trovati tre, tutti nel path live di S4:

1. **`exit_mechanism` è dedotto, non osservato** (#184). `_classify_zero_weight_exit`
   (`portfolio_scheduler.py:580-601`) ricava l'etichetta dall'età dell'ultimo
   segnale in DB, non dal meccanismo reale. Il 2026-08-05 alle 14:22, nello
   stesso ciclo, FIX-D ha **preservato** i segnali di MCD/NVO/PFE/PLTR e quelle
   quattro posizioni sono state vendute con motivazione `expired` — etichetta
   falsa, perché il segnale non era stato scartato per scadenza.

   Questo tocca direttamente questa fase: OBS-1 e la conclusione di §Sintesi si
   appoggiano a `exit_mechanism`, che non è una fonte affidabile.

2. **Un segnale neutro fresco chiude la posizione** (#83, #169). DIS comprato
   alle 14:22 su sentiment +0.687 e venduto alle 16:07 perché un segnale delle
   16:00 aveva score **0.000** e confidence 0.15 — −$18.76 in 105 minuti. È lo
   stesso errore concettuale che FIX-D corregge per la scadenza (*"expiry means
   no new information, not exit"*), senza un guard equivalente per il neutro.
   Tutte le 8 uscite `whipsaw` del 03-05/08 portano
   `[anti_whipsaw_shadow: would_suppress=True]`.

3. **Meccanismo di azzeramento non spiegato** (#186). NVO, PFE e MCD sono stati
   venduti pur avendo segnale preservato, score sopra il gate 0.300 e posizione
   nei primi 5 per punteggio. La competizione di slot (`n_top=5`) spiega solo
   PLTR, sesto. Il meccanismo reale resta da stabilire — e finché non lo è, il
   **periodo di detenzione effettivo di S4 non è noto**, il che tocca
   l'orizzonte su cui si misura l'IC (#179, #180).

Resta valido il punto centrale della fase: l'IC negativo non è un bug ma la
non-validità del segnale. Ma la frase "il sistema live paper funziona come
progettato" era troppo generosa.

---
**Stato fase:** 07_bugs = **done**. Prossimo cursore: `S4:08_report`.