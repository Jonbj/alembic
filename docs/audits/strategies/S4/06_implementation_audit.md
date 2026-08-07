# S4 — 06 Implementation Audit

**Strategia:** S4 `NewsDrivenTactical`
**Data:** 2026-08-04
**Verdetto implementazione:** **path live paper funzionante** (realmente eseguita,
64 trade, +$329), MA **alpha non dimostrato** (IC<0 interno) e backtest
**non conclusivo** (fallback sintetico, no costi, drift gate). Runtime confermato
attivo e difensivo (idempotency fail-closed).

---

## Asse 1 — Data timing (event-time vs bar-time)

**Verdetto: CORRETTO (causale, event-time sui segnali).**

- Segnali generati **offline** dal sentiment worker (Celery `inference`),
  scritti in `sentiment_signals` con `generated_at` = timestamp LLM.
- `portfolio_scheduler` legge a ogni ciclo i segnali freschi
  (`generated_at <= now`, age ≤ `max_signal_age_hours=4`).
- Backtest `_signals_as_of(ts)` (`strategy.py:156-169`): `generated_at <= ts` e
  `>= ts - max_age`. Causale, con la stessa freshness window del live (QS-07
  parity).
- **L'LLM non è nel hot path** (Alpha Miner): il scheduler legge pre-computed,
  mai chiama l'LLM sincronamente. Conforme al principio architetturale.

## Asse 2 — Look-ahead bias

**Verdetto: OK sul trading; WARNING sui forward_return (IC, non trading).**

- Trading: segnali usati solo per `t` con `generated_at <= t`. Nessun look-ahead.
- I `forward_return_{,3d,5d}` in `sentiment_signals` sono **label** popolate
  ex-post (da `compute_label_forward_returns`, Alpaca storica) per il calcolo
  IC — **non** usati dal path di trading, solo da `compute_s4_ic.py`. Corretto:
  il forward return è label, non feature.
- **Backtest universe**: `load_universe("s1")` (`backtest.py:234`) → condivide
  il survivorship/look-ahead dell'universo S1 (S1 BUG-2). Non un look-ahead del
  segnale S4, ma dell'universo di pricing.

## Asse 3 — Leakage

**Verdetto: OK.**

- Provenance pinning (`strategy.py:52,65`, `ranking.py:51-67`): `signal_id`
  fissato al rank time, non re-fetchato → no leakage del "latest signal" che
  potrebbe essere più nuovo di quello usato per la decisione (fix B33-follow-up).
- Signal_id resolution nel scheduler (`portfolio_scheduler.py:775-787`, fix #109):
  conviction dallo stesso `signal_id` della decision → no mix-and-match.
- Freshness window `max_signal_age_hours=4` applicata identica backtest/live
  (`strategy.py:167-169`) → no T0 contamination (QS-07).

## Asse 4 — Survivorship bias

**Verdetto: EREDITATO da S1 (DEBOLE).**

- Backtest usa `load_universe("s1")` (`backtest.py:234`) → universo S1 (large/mid
  US liquido, snapshot corrente). S4 eredita il survivorship di S1.
- MA S4 opera su **segnali di news**, non su price momentum → il survivorship
  dell'universo è meno critico che per S1 (S4 seleziona per sentiment, non per
  rendimento passato). Impatto limitato.
- Live: universi gestiti dal portfolio_scheduler (watchlist); non survivorship
  snapshot. Divergenza backtest/live sull'universo.

## Asse 5 — Backtesting methodology

**Verdetto: DEBOLE — fallback sintetico, no costi, no DSR, drift gate.**

- **WF**: `WalkForwardConfig(1260, 252)` (`backtest.py:43`). Corretto split.
- **Same-bar fills**: `Order.market_order` a `ts` con `price = market.price_of`
  (`strategy.py:118`) — fill al close del segnale. Ottimistico (no slippage).
- **Costi non modellati**: nessuno slippage/commissione nel backtest; il live ha
  `cost_bps`/`cost_usd` in `trades`. Backtest pre-cost → overstima.
- **DSR / n_trials**: non presente. `_run_perturbation` (`backtest.py:163-197`)
  testa 5 combo n_top/bucket_pct senza multiple-testing correction.
- **Fallback sintetico (DV-S4-3)**: `_generate_synthetic_signals`
  (`backtest.py:269-289`) produce segnali **casuali** (`rng.uniform(-0.5,0.9)`)
  se PostgreSQL non disponibile → backtest senza DB misura **rumore**. Nessun
  guard/avviso. `reports/s4_backtest/summary.json` **non esiste** (fase 04) →
  o il backtest non è stato mai runnato, o è stato runnato senza DB (rumore).
- **Drift gate (DV-S4-1)**: il backtest usa solo il ranker (`min_score=0.10`);
  il live aggiunge il `feedback:entry_threshold` ratchet (0.30+) **non
  replicato** nel backtest → l'OOS Sharpe backtest non riflette il gate live.
  Il backtest non è rappresentativo del live.

## Asse 6 — Signal generation

**Verdetto: FORMULA CORRETTA, IC NEGATIVO (non-predittivo).**

- `score = polarity × confidence` (`sentiment.py:325,333,367`) — conforme
  CLAUDE.md.
- `effective_strength = score` nel ranker (`ranking.py:186`) — non ri-moltiplica
  confidence (intenzionale, `ranking.py:6-8`).
- Long-only `strength > 0` (`ranking.py:187-189`).
- **IC misurato dal progetto** (`s4_ic.json`, fase 04): IC 1g/3g/5g = −0.018/
  −0.010/−0.026 (tutti), −0.020/−0.061/−0.063 (fallback). **Negativo, non
  significativo**. Il segnale **non predice** i forward return nel campione
  (34 giorni, 2002 obs) — anzi predice al contrario. Questa è la misura di
  validità del segnale ed è fallita.

## Asse 7 — Portfolio allocation (sleeve scaling, caps)

**Verdetto: CORRETTO meccanicamente, MA non risk-adjusted.**

- Sleeve cap 10% (`registry.py:228` hard cap).
- `fixed_slot_sizing=True`: `per_ticker_weight = 1/n_top` (`ranking.py:133`),
  slot vuoti non ridistribuiti (fix #81).
- `allocation_pct` applicato upstream nel scheduler (non nel ranker).
- `regime_mult` applicato (`execution_decisions.regime_mult` colonna presente).
- Sizing **pari peso**, non vol-scaled → non risk-adjusted; coerente con overlay
  tattico ma non con sizing momentum-family.

## Asse 8 — Risk controls (stops, drawdown, kill-switch)

**Verdetto: PARZIALE — entry gate + idempotency, no stop/DD dedicati.**

- **Entry gate ratchet** (`feedback:entry_threshold:S4`, baseline 0.30,
  `portfolio_scheduler.py:1277-1340`): soglia dinamica alzata dal loss-feedback.
  Difensivo, MA adattivo (overfitting risk).
- **Idempotency fired signals** (P2-05-A, `:552,960-987,1349-1354`): Redis set
  per session, fail-closed se Redis down (skip tutti S4 BUY). Difensivo corretto.
- **Exit mechanisms**: `no_signal`/`expired`/`whipsaw` (`:584-669`). Runtime
  mostra molti SELL `[whipsaw]` (peso 0% ma segnale presente) → churn.
- **No stop-loss / drawdown / kill-switch S4-specifici**: S4 si affida agli
  overlay di portfolio (drawdown cap, kill-switch di sistema). Non ha risk
  control proprio (a differenza di S1 stop-loss).

## Asse 9 — Execution (order placement path)

**Verdetto: PATH LIVE REALE (Alpaca paper).**

- `portfolio_scheduler` → `execution.py` → `alpaca-py` `TradingClient` /
  `MarketOrderRequest` (CLAUDE.md). Paper mode (`ALPACA_PAPER_MODE`).
- 64 trade S4 in `trades` (fase 04) → ordini realmente piazzati in paper.
- `execution.engine=portfolio` (default): solo `portfolio-cycle` sottomette
  ordini. S4 è nel path portfolio.
- Nessun `AlpacaBroker` class (CLAUDE.md); `TradingClient` diretto.

## Asse 10 — Accounting (P&L, slippage, costs)

**Verdetto: ATTIVO, con caveat.**

- `trades`: `net_pnl`, `gross_pnl`, `cost_bps`, `cost_usd`, `slippage_est`
  popolati. S4: net +$329.10, gross +$408.97, costs ~$80 (62 closed).
- **Costi paper sottostimati**: paper mode ha spread/costi minori del live;
  `slippage_est` è stima, non reale.
- **Signal_id coupling** in `trades.signal_id` + `execution_decisions.signal_id`
  → tracciabilità decisione↔segnale (fix B33/#109).

## Asse 11 — Paper-trading behavior

**Verdetto: ATTIVO, promotion_blocked corretto.**

- `mode=paper`, `approved=t`, `promotion_blocked=true` (lifecycle DB).
- `registry.py:240`: `mode=live` vietato per S4 (no gate report + IC>placebo non
  confermato). Hard cap 10%.
- `config/strategies.yaml`: "Re-promotion to live requires P1-03 + P1-04 +
  IC>placebo + 90-day paper."
- Coerente: S4 è in paper **proprio perché il suo alpha non è dimostrato** (IC<0,
  fase 04). La governance è corretta; il rischio è che un sistema con alpha
  misurato negativo sia comunque l'overlay live attivo.

## Asse 12 — Runtime behavior (live workers vs codice)

**Verdetto: ATTIVO E CONFERMATO.**

Verifiche DB read-only (2026-08-04):

```
sentiment_signals: 6286 row, 2026-06-15 → 2026-08-03
trades S4: 64 trade, net_pnl +$329.10, 37/62 wins (60%), gross +$408.97
execution_decisions (ultimi 14g): 2794 total, 93 S4-reason (3.3%), 105 BUY / 62 SELL
fallback_counters: consecutive_fallback=0 (reset 2026-08-03)
strategy_lifecycle: S4 mode=paper, approved=t
```

- **S4 è una frazione minore** delle decisioni (93/2794 = 3.3% S4-reason in 14g)
  → S1 domina il portafoglio; S4 è overlay marginale.
- **Pattern runtime osservato**: BUY su sentiment ensemble forte (es. META
  sentiment +0.356 ensemble → BUY), SELL `[whipsaw]` frequenti (NVDA/MSFT/AMZN
  SELL weight 0% con segnale presente) → **churn tattico giornaliero**, molte
  posizioni aperte e chiuse nello stesso giorno/giorni.
- **`score` decision vs `polarity` reason**: il `score` in `execution_decisions`
  (0.020) differisce dal sentiment reason (+0.356) → il `score` colonna è
  regime-scaled o post-gate, non il sentiment raw. Da chiarire (fase 07).
- **consecutive_fallback=0**: al momento non in streak fallback (reset
  2026-08-03). MA la memoria collo #1 documenta 70-86% fallback storico dal GLM
  swap → l'affidabilità ensemble è stata storicamente bassa.

**Runtime vs intent**: il codice S4 fa quello che intende (ranking, gate,
idempotency, exit). Il problema **non è un malfunzionamento** ma che **il segnale
non predice** (IC<0, fase 04) — il sistema esegue fedelmente un segnale
non-predittivo. L'implementazione è sana; l'ipotesi non è validata.

## Sintesi assi

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
| 12 Runtime | ATTIVO E CONFERMATO (overlay marginale, churn, IC<0) |

**Convergenza**: S4 è implementata correttamente ed è runtime-attiva, MA il
backtest non è conclusivo (fallback sintetico + drift gate) e il segnale ha IC
negativo misurato dal progetto stesso. Il problema è di **validità del segnale**,
non di implementazione. Il sistema esegue fedelmente un segnale non-predittivo,
il che è il rischio principale (operare su alpha misurato negativo).

---
**Stato fase:** 06_implementation_audit = **done**. Prossimo cursore: `S4:07_bugs`.