# REPORT S4 — News-Driven Tactical (Sentiment Overlay)

**Audit:** Alembic Strategy Audit
**Strategia:** S4 `NewsDrivenTactical` (news-driven tactical sentiment overlay)
**Data:** 2026-08-04
**Verdetto implementazione:** `NEGATIVE` (sul criterio IC — il segnale non predice)
**Verdetto fenomeno:** `DECAYED` (PEAD ~zero post-2017; edge LLM in erosion)
**Stato runtime:** **ATTIVA in paper** (mode=paper, approved, promotion_blocked;
64 trade, +$329 net; 6286 segnali; 2794 decisioni/14g)
**Fonti:** `src/strategies/s4/{strategy,config,ranking,backtest}.py`,
`src/workers/{sentiment,portfolio_scheduler}.py`, `src/strategies/registry.py`,
`docs/evidence/s4_ic.json`, `config/strategies.yaml`, DB read-only, letteratura.

---

## 1. Sintesi esecutiva

S4 è l'**overlay tattico news-driven** — l'unica strategia di sentiment, e una
delle due realmente eseguite (con S1). Segue il paradigma Alpha Miner: l'LLM
genera sentiment offline (`score = polarity × confidence`), il portfolio_scheduler
legge i segnali pre-calcolati a ogni ciclo, mai nel hot path. Ranker cross-
sectionale long-only top-5, fixed-slot 1/5, sleeve cap 10%, entry gate reale =
`feedback:entry_threshold` ratchet (baseline 0.30, alzato dal loss-feedback).

**Il problema centrale non è l'implementazione ma il segnale.** Il progetto
stesso misura l'Information Coefficient del segnale S4
(`docs/evidence/s4_ic.json`, 2026-08-03): IC **negativo** su tutti gli orizzonti
(−0.018/−0.010/−0.026 a 1/3/5g, aggregato; −0.020/−0.061/−0.063 per il fallback),
nessuno significativo. Il segnale **non predice** i forward return — anzi
predice al contrario. Il criterio di promozione P0-13 (IC>placebo) **non è
soddisfatto**, ed è peggiore di placebo. La governance è corretta:
`promotion_blocked=true`, `mode=live` vietato. MA S4 è comunque l'overlay live
attivo — il sistema esegue fedelmente un segnale misurato come non-predittivo.

La **letteratura è sfavorevole** su ogni dimensione dell'implementazione: PEAD
decaduto a ~zero post-2017, costi consumano 70-100% dell'edge su stock liquidi
(S4 usa large-cap), orizzonto tattico giornaliero = edge minimo (1-2 giorni di
predictability), long-only positivo = gamba debole (9 vs 29 bps, Heston-Sinha:
positive incorporata veloce), FinBERT (il fallback S4) documentato Sharpe −0.43
(Lopez-Lira-Tang 2023), edge LLM in erosion attiva (6.54→2.33).

Il P&L live paper +$329 su 64 trade è **small-sample + market beta** (long-only
in mercato rialzista), non sentiment alpha; l'IC cross-sectionale (che isola il
contenuto informativo) è la misura pertinente ed è negativa.

**Raccomandazione**: S4 non dovrebbe essere promossa a live (coerente con
`promotion_blocked`). Il rischi principale è operare su alpha misurato negativo.
I 2 bug di backtest (gate drift, fallback sintetico) vanno chiusi prima di
qualunque ri-validazione. L'IC va monitorato su campione più lungo; se
persiste ≤0, l'overlay va disattivato o ridotto a shadow.

## 2. Specifica (fase 01)

**Segnale** (`sentiment.py:325,333,367`): `score = polarity × confidence`,
`polarity∈[-1,1]`, `confidence∈[0,1]`. Ensemble pair (Redis
`config:sentiment_llm_models`, default `glm52,gptoss`); fallback FinBERT.

**Ranker** (`ranking.py:85-155`): dedupe per symbol (latest `generated_at`);
filtri `confidence≥0.3`, `abs(score)≥0.1`; `effective_strength=score` (non
×conf, `ranking.py:6-8`); **long-only** `strength>0`; sort desc, take `n_top=5`;
`fixed_slot_sizing=True` → `1/n_top` per slot (#81); `bucket_pct=0.10`.

**Entry gate LIVE** (`portfolio_scheduler.py:1277-1340`): `feedback:entry_threshold:S4`
ratchet, baseline 0.30, alzato dal loss-feedback. Ammette iff
`score >= entry_threshold`. `min_score=0.10` è solo prefiltro ranker.

**Universe**: backtest `load_universe("s1")` (large/mid US liquido, 2010-today);
live watchlist gestita dal scheduler.

**Rebalance** DAILY; `max_signal_age_hours=4` (freshness); NAV = cash+Σmv;
exit SELL long-only assenti dal target; soglia delta 1e-4.

**Config** wired via `trading.yaml risk.s4_fixed_slot_sizing_enabled` (non dead
config, a differenza di S1/S2/S3).

## 3. Ipotesi (fase 02)

S4 scommette sul **news sentiment drift** (generalizzazione testuale del PEAD):
i mercati sottoreagiscono alle news, e `polarity×confidence` predice i rendimenti.
MA l'implementazione testa una **variante più debole e più breve** dell'ipotesi
canonica: long-only asimmetrico (no short leg, monetizza solo la gamba debole),
tattico giornaliero (non drift 60-180g), soglia adattiva ratchet (overfitting
risk), come **overlay di conferma a S1** (alpha incrementale, non standalone).
L'orizzonte tattico breve è più debole del PEAD classico (Heston-Sinha: news
giornaliera predice solo 1-2 giorni).

## 4. Letteratura (fase 03)

| Aspetto | Finding | Impatto S4 |
|---|---|---|
| PEAD decay | ~zero post-2017 (Kettell 2022) | fenomeno parente decaduto |
| Costi | consumano 70-100% edge PEAD (Chordia 2009) | large-cap liquido = lato near-zero |
| Orizzonte | news giornaliera → 1-2 giorni (Heston-Sinha) | tattico giornaliero = edge minimo |
| Gamba | long 9 bps vs short 29 bps (Lopez-Lira-Tang) | long-only positivo = debole |
| FinBERT | Sharpe −0.43 (Lopez-Lira-Tang) | FinBERT è il fallback S4 |
| LLM decay | Sharpe 6.54→2.33 (2021-23) | edge LLM in erosion attiva |
| Contextual | embedding features sopravvivono, polarity no (Chung 2023) | S4 usa polarity (decade OOS) |

**Convergenza**: la letteratura non supporta "large-cap, long-only positivo,
tattico giornaliero, fallback FinBERT generi alpha netto post-cost."

## 5. Alpha assessment (fase 04)

**Implementazione: `NEGATIVE` (criterio IC).** Il progetto stesso misura IC<0
per il segnale aggregato e fallback, nessuno significativo (34 giorni, 2002 obs).
Il criterio P0-13 (IC>placebo) non è soddisfatto — peggiore di placebo. P&L
+$329 è small-sample + market beta (long-only in rialzo), non sentiment alpha;
l'IC cross-sectionale (misura pertinente) è negativa.

**Fenomeno: `DECAYED`.** PEAD ~zero post-2017; edge LLM in erosion; polarity
features decadono OOS. La forma generalizzata long-only positiva su large-cap di
S4 è sul lato decaduto/debole.

**Decomposizione beta**: market beta (long-only), momentum beta (overlay S1,
duplicazione — risk per cross_review), news/event beta (partly prezzabile),
size beta (large-cap). L'IC (che netta beta di mercato) è la misura pertinente
ed è ≤0 → nessun contenuto informativo incrementale.

## 6. Implementation audit (fase 06)

| Asse | Verdetto |
|---|---|
| 1 Data timing | OK (causale, LLM offline) |
| 2 Look-ahead | OK trading / WARNING universe S1 |
| 3 Leakage | OK (provenance pinning, fix B33/#109) |
| 4 Survivorship | EREDITATO S1 (debole) |
| 5 Backtest method | DEBOLE (fallback sintetico, no costi, no DSR, drift gate) |
| 6 Signal gen | FORMULA OK, **IC NEGATIVO** (non-predittivo) |
| 7 Allocation | OK meccanico, non risk-adjusted |
| 8 Risk controls | PARZIALE (entry ratchet + idempotency, no stop S4) |
| 9 Execution | PATH LIVE REALE (Alpaca paper) |
| 10 Accounting | ATTIVO (costi paper sottostimati) |
| 11 Paper trading | ATTIVO, promotion_blocked corretto |
| 12 Runtime | ATTIVO E CONFERMATO (overlay marginale 3.3%, churn, IC<0) |

**Runtime (DB read-only 2026-08-04):**
```
sentiment_signals: 6286 (2026-06-15 → 2026-08-03)
trades S4: 64, net_pnl +$329.10, 37/62 wins (60%), gross +$408.97
execution_decisions (14g): 2794 total, 93 S4-reason (3.3%), 105 BUY/62 SELL
execution_decisions.score=0.020 (peso 2% = 10%×1/5, fixed-slot confermato)
regime_mult=0.700 (capital deployment limited)
s4_ic.json: IC 1g/3g/5g = -0.018/-0.010/-0.026 (tutti), -0.020/-0.061/-0.063 (fallback)
```

## 7. Bug confermati (fase 07)

| ID | Severità | Luogo | Conferma |
|---|---|---|---|
| **BUG-A** | HIGH (validità backtest) | backtest.py no entry_threshold vs scheduler:1277-1340 | repro_1 ESEGUITO |
| **BUG-B** | HIGH (validità backtest) | backtest.py:269-289 fallback sintetico | repro_2 ESEGUITO |
| BUG-C | LOW | strategy.py:74-75 health_check no-op | traccia statica |
| OBS-1 | non-bug | execution_decisions.score=weight (fixed-slot confermato) | traccia DB |

**BUG-A**: il backtest non replica l'entry gate ratchet live (0.30); usa solo
`min_score=0.10` → segnali [0.10,0.30) ammessi in backtest, respinti in live →
backtest over-admit, non rappresentativo.

**BUG-B**: se PostgreSQL non disponibile, `_generate_synthetic_signals` produce
segnali RNG casuali; il backtest scrive summary.json **senza flag** sintetico →
un backtest senza DB misura rumore (beta di mercato) indistinguibile da alpha.

**Importante**: nessun bug nel **path live** — idempotency, provenance, gate
ratchet, fixed-slot funzionano. I bug sono nella **validazione**, che è non-
rappresentativa.

## 8. Stato di integrazione

- **Registry**: S4 registrata, hard cap 10% (`registry.py:228`), `mode=live`
  vietato (`registry.py:240`).
- **Lifecycle DB**: `mode=paper`, `approved=t`, `promotion_blocked=true`.
- **Live**: portfolio_scheduler → execution.py → alpaca-py (paper).
- **Config wired**: trading.yaml (non dead config).
- S4 è **l'overlay live attivo** con alpha misurato negativo (IC<0).

## 9. Conclusione e raccomandazione

S4 è implementata correttamente e runtime-attiva, MA:
1. Il **segnale non predice** — il progetto stesso misura IC<0 (P0-13 non
   confermato, peggiore di placebo). La letteratura è sfavorevole su ogni
   dimensione. L'implementazione esegue fedelmente un segnale non-predittivo.
2. Il **backtest è non-rappresentativo** — 2 bug HIGH (gate drift + fallback
   sintetico) invalidano qualunque OOS Sharpe calcolato dal backtest.
3. Il **P&L live +$329** è small-sample + market beta, non sentiment alpha.

**Raccomandazione**:
- **Non promuovere a live** (coerente con `promotion_blocked`). Il rischio di
  operare su alpha misurato negativo è il rischio principale del sistema.
- **Chiudere i 2 bug di backtest** (BUG-A: replicare/documentare il gate drift;
  BUG-B: guard che failisce/avverte su segnali sintetici) prima di qualunque
  ri-validazione.
- **Monitorare l'IC** su campione più lungo (34 giorni è piccolo, ma la
  direzione è coerentemente negativa). Se IC persiste ≤0, **disattivare o
  ridurre a shadow** l'overlay live.
- **Valutare l'incremento a S1** (cross_review): S4 duplica momentum beta
  (sentiment+ ≈ momentum+)? Se non incrementale, l'overlay non ha ragione
  d'essere nemmeno come conferma.
- **Indirizzare l'ensemble reliability** (collo #1: 70-86% fallback FinBERT
  non-predittivo): il pair swap / 3° modello è prerequisito per qualunque
  speranza di IC>0.

**Rischi chiave**: operare su alpha misurato negativo; backtest non-
rappresentativo che potrebbe illudere di validazione; decay attivo del fenomeno;
duplicazione esposizione S1; fallback FinBERT non-predittivo.

---
**Stato audit S4:** fasi 01-08 **done**. Report consolidato.