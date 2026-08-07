# S7 — 06 Implementation Audit

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04
**Nota:** S7 è **rimossa**. L'audit è su git history (`1dd2c35`) + lifecycle
doc + DB read-only. L'asse 12 (runtime) è il più importante: S7 non ha mai
eseguito, quindi la maggior parte degli assi è **N/A — mai live**.

## Verdetto sintetico per asse

| # | Asse | Verdetto | Evidenza |
|---|---|---|---|
| 1 | Data timing (event-time) | **OK (design)** | event-driven 8-K → +5min → LLM; MA mai eseguito |
| 2 | Look-ahead bias | **OK (design)** | `detected_at` = filing time; MA backtest mai runnato |
| 3 | Leakage | **N/A** | mai eseguito; nessun path dati vivo |
| 4 | Survivorship | **OK (design)** | universo 8-K = all filings (no survivorship); MA universe ALPHA-A5 large-cap = competuto |
| 5 | Backtesting methodology | **N/A** | backtest mai runnato (`reports/s7_*` gitignored, summary non prodotto) |
| 6 | Signal generation | **OK gates, CARBURANTE ZERO** | gates corretti (`signal.py:35-46`) MA surprise_pct null → reject (DV-S7-1) |
| 7 | Portfolio allocation | **OK (design)** | pari peso cap sleeve (`strategy.py:59-69`); MA caller mai wired (DV-S7-6) |
| 8 | Risk controls | **PARZIALE (design)** | cap sleeve 25%, hold 20d; no stop, no drawdown kill (sleeve isolata) |
| 9 | Execution | **N/A — MAI WIRED** | orchestrator/scheduler nessun match S7; zero ordini lifecycle |
| 10 | Accounting | **N/A** | zero trade → nessun P&L da contabilizzare |
| 11 | Paper trading | **N/A — MAI PROMOSSA** | `mode=research`, `approved=f`, nessun `promoted_at` |
| 12 | Runtime | **MORTO — MAI LIVE** | DB: zero ordini, zero decisioni S7, `pead_signals` inesistente, table non materializzata |

## Dettaglio assi critici

### Asse 6 — Signal generation: OK gates, carburante zero

I gate di `EarningsSurpriseClassifier.to_signal` (`signal.py:35-46`) sono
**corretti e difensivi**:
- reject `no_eps`/`inline` (no evento informativo),
- reject `confidence < 0.70` (LLM non certo),
- reject `surprise_pct is None` (consensus assente),
- reject `|surprise_pct| < 0.05` (sorpresa immateriale).

**MA** il carburante (`surprise_pct`) è opzionale (`pead.py:17`, `None` ok) e
popolato dall'LLM, non da consensus esterno (DV-S7-1, ALPHA-A2 mai wired). Il
lifecycle doc conferma: `surprise_pct` spesso null → **soglia 0.05 mai
superata** → zero segnali passano i gate → zero ordini. I gate sono corretti
MA filtrano tutto perché l'input è debole. **Non un bug di logica** — un gap
upstream (consensus provider non integrato).

### Asse 9 — Execution: N/A — mai wired

`grep` su `portfolio_scheduler.py`/`portfolio_orchestrator.py` (working tree):
**nessun match S7/PEAD**. `PEADStrategy.compute_target_weights` è definito
(`strategy.py:32-71`) MA non ha caller. Il commit `d1e6de6` rimuove tutto il
runtime surface. S7 è **mai stata nel `PortfolioOrchestrator`** (P0-13, guard
`test_p0_13_strategy_containment.py:62-97`). → **zero ordini lifecycle**.

### Asse 12 — Runtime: MORTO — mai live (DB read-only 2026-08-04)

```
strategy_lifecycle WHERE strategy_id='S7':
  mode=research, approved=f, gate_report=ALPHA_A5_gate_report_2026-07-03_fmp.md,
  promoted_at=NULL (MAI promossa)

\d pead_signals → "Did not find any relation" (TABLE NON MATERIALIZZATA)
pg_tables WHERE tablename ILIKE '%pead%' → 0 rows (nessuna table pead)

execution_decisions WHERE reason ILIKE '%s7%' OR ILIKE '%pead%' → 0 (ZERO)
trades exit_reason distribution → portfolio_sell(304), blank(49), stop_loss(33),
  sentiment_reversal(25), LEGACY_FLATTEN(16) → NESSUN tag S7/pead
```

**Conferma runtime**: S7 non ha **mai** prodotto un segnale persistito, una
decisione, o un ordine. `pead_signals` table non esiste (DDL solo doc, nessuna
migration — DV-S7-7). Le reason di `execution_decisions` sono tutte S1/S4
("feedback threshold 0.30x" = S4 gate, "S1 momentum" = S1). **S7 è
completamente assente dal runtime live.**

### Asse 11 — Paper trading: mai promossa

`strategy_lifecycle`: `mode=research`, `approved=f`, nessun `promoted_at`.
S7 non ha mai superato il gate P1 (promotion) → mai paper → mai live. La
governance ha correttamente **trattenuto S7 in research** fino al POC. POC-2
FAIL → REMOVE (PO-5). **Comportamento corretto**: non promuovere senza
evidenza decision-grade PASS.

### Asse 5 — Backtesting methodology: N/A

Nessun `reports/s7_backtest/summary.json` prodotto (gitignored evidence =
POC scripts, non backtest WF formale). L'ALPHA-A5 è un **event-study** (n=76,
drift medio/mediano, hit-rate, dose-response), non un backtest WF con DSR.
Il POC-2 è una **misurazione IC** (Spearman, tercile, split-half), non un
backtest. **S7 non ha un backtest WF formale** → asse 5 N/A. Non è un
deficit: la valutazione è stata a livello di **segnale** (IC) prima di
investire in un backtest WF — metodologicamente corretto (kill sul segnale,
non sul backtest).

### Asse 8 — Risk controls: parziale (design, mai testato)

Design: cap sleeve 25% (`max_sleeve_pct`), cap posizione 5%
(`max_position_pct`), hold 20d (`hold_until`). **No stop-loss, no drawdown
kill, no regime mult**. La sleeve è isolata (25% max) → il danno massimo è
limitato strutturalmente. MA: mai testato in live (zero ordini) →
comportamento reale sconosciuto. Per un revival, aggiungere stop e regime mult
(coerente con S1/S4).

## Confronto runtime S7 vs S1/S4 (cross-strategy)

| Metric | S1 | S4 | S7 |
|---|---|---|---|
| `strategy_lifecycle.mode` | (paper/live) | paper | **research** |
| `approved` | t | t | **f** |
| `promotion_blocked` | n | **t** | n/a (mai promossa) |
| trade lifecycle | 75 | 64 | **0** |
| execution_decisions (14g) | (S1-reason) | 93 (3.3%) | **0** |
| Persistenza signals | DB | DB (`sentiment_signals`) | **nessuna table** |
| `pead_signals` / equivalent | — | — | **inesistente** |

**S7 è l'unica strategia mai mantenuta in research fino a misurazione
decision-grade e killata.** S1/S4 sono live nonostante IC<0/decay. La
differenza è **governance**, non ipotesi (tutte e tre deboli).

## Mancanze di implementazione (non-bug)

- **ALPHA-A2 consensus mai wired** (DV-S7-1) — gap integrazione, causa zero
  ordini. Non un bug di logica S7.
- **ALPHA-D1 analyst revisions mai wired** (Vettore D) — design dichiarava
  revisioni analisti come carburante del drift; mai implementato. Non un bug,
  un feature non costruita.
- **Caller mai wired** (DV-S7-6) — scelta di governance (non promuovere senza
  POC PASS), non un bug.
- **`pead_signals` table mai materializzata** (DV-S7-7) — DDL solo doc, nessuna
  migration. Non un bug, un'omissione di persistenza (irrilevante dato zero
  ordini).

Questi non sono bug di **logica** (i gate/sizing sono corretti) ma **gap di
integrazione upstream**. La fase 07 classifica questi separatamente dai bug
di logica.

## Sintesi

S7 è **il caso più pulito dell'audit**: una strategia configurata sulla forma
debole/competuta del fenomeno PEAD (large-cap, long-only, polarity tone, hold
20d, consensus assente), **mai promossa a paper/live**, misurata a
decision-grade (POC-2 n=73), killata su FAIL pre-registrato (PO-5), e
rimossa pulitamente (full runtime surface eliminato, guard anti-reintroduzione
`test_p0_13`). **Zero ordini lifecycle, zero persistenza DB, zero risk di
esecuzione su alpha negativo.**

**Il verdetto implementazione è NEGATIVE con alta confidenza**, MA la
**governance è positiva** — è l'esempio di best-practice del progetto. Per la
cross_review: il sistema dovrebbe applicare lo stesso disciplinamento a S1/S4
(misurare IC a decision-grade, killare su FAIL) invece di mantenerle live.

---
**Stato fase:** 06_implementation_audit = **done**. Prossimo cursore: `S7:07_bugs`.