# S4 — 01 Specificazione funzionale e matematica

**Strategia:** S4 `NewsDrivenTactical` (news-driven tactical sentiment overlay)
**Data:** 2026-08-04
**Fonti:** `src/strategies/s4/{strategy,config,ranking,backtest}.py`,
`src/workers/sentiment.py`, `src/workers/portfolio_scheduler.py`,
`config/strategies.yaml`, `config/trading.yaml`, `src/strategies/registry.py`
**Stato (lifecycle DB):** `mode=paper`, `approved=t`, `promotion_blocked=true`
**Stato (yaml):** `enabled=true`, `allocation_pct=0.10`, `mode=paper`,
`promotion_blocked=true`; note: "PROMOTION BLOCKED (P0-13): no gate report exists
and IC>placebo has not been confirmed. Re-promotion to live requires P1-03 +
P1-04 + IC>placebo + 90-day paper."
**Registry:** S4 registrata (`registry.py:27,168`), hard cap 10%
(`registry.py:228`), `mode=live` non ammesso (`registry.py:240`).
**Runtime:** **ATTIVA** in paper — 64 trade in `trades.stop_strategy` (fase 06).

S4 è la **strategia live (paper) attiva** di Alembic: l'unica, insieme a S1, a
essere realmente eseguita. È un overlay tattico news-driven che legge segnali di
sentiment pre-calcolati (offline worker) e li usa come **confirmation gate** /
tactical sleeve, mai nel hot path di esecuzione.

---

## 0. Architettura di principio (Alpha Miner)

S4 segue il paradigma Alpha Miner: l'LLM **non** è nel hot path. Pipeline:
```
[News] → [background sentiment worker (LLM)] → [sentiment_signals DB]
   → [portfolio_scheduler legge segnale, gate entry_threshold] → [ordine Alpaca]
```
- L'inferenza LLM è **offline/background** (worker Celery `inference`).
- Il `portfolio_scheduler` legge da DB/Redis a ogni ciclo, **mai** chiama l'LLM
  sincronamente.
- S4 fornisce il ranking cross-sectionale; l'**entry gate** reale è il
  `feedback:entry_threshold` (feedback loop), non il `min_score` del ranker.

## 1. Segnale: sentiment score

L'LLM produce `polarity ∈ [-1,+1]` e `confidence ∈ [0,1]` per ogni (ticker, news).
La formula di scoring (`src/workers/sentiment.py:325,333,367`):

$$\mathrm{score} = \mathrm{polarity} \times \mathrm{confidence}$$

Il prodotto scala il segnale direzionale per la certezza del modello (alta
polarità + bassa confidence → score piccolo). È la formula di CLAUDE.md,
implementata nel worker. Il ranker **non** moltiplica di nuovo per confidence
(`ranking.py:6-8,183-186`): `effective_strength = score` (altrimenti sarebbe
`confidence²`).

Ensemble: coppia di modelli via Redis `config:sentiment_llm_models` (default
`glm52,gptoss`); fallback FinBERT. `ensemble_std` e `fallback_used` registrati.
LOO ICIR rebalancing aggiorna `ensemble:weights:current` (pesi, non membership).

## 2. Ranker cross-sectionale (strato S4)

`CrossSectionalRanker.rank` (`ranking.py:85-155`):

1. `_filter_and_deduplicate` (`ranking.py:161-192`): per symbol, keep il
   `SentimentResult` più recente per `generated_at`. Filtri:
   - `confidence >= min_confidence` (0.3) — prefiltro ranker
   - `abs(score) >= min_score` (0.1) — prefiltro ranker
   - `strength = score`; **long-only**: `strength > 0` (skip neutral/negative,
     `ranking.py:187-189`).
2. Sort descending per `effective_strength = score`; take `n_top=5`
   (`ranking.py:116-117`).
3. `min_stocks=1`: se <1 candidato passa → bucket vuoto (`ranking.py:107-113`).
4. Sizing:
   - `fixed_slot_sizing=True` (default, `config.py:37`): `per_ticker_weight =
     1/n_top` (1/5 = 0.20 del bucket). Slot non usati restano undeployed
     (fix #81: lone-survivor non prende il bucket intero).
   - `fixed_slot_sizing=False`: `1/n_selected` (legacy).
5. `bucket_weight = bucket_pct = 0.10` (lo sleeve S4 al 10% del NAV).

**Peso finale di un ticker = `bucket_pct × per_ticker_weight`? No** — il ranker
restituisce `per_ticker_weight` (0.20 se fixed, 1/n_selected). Lo sleeve scaling
per `allocation_pct=0.10` è applicato **upstream** nel portfolio_scheduler
(orchestrator), non nel ranker. Il ranker produce pesi **intra-bucket**.

## 3. Entry gate (LIVE, non nel ranker)

**Il gate d'ingresso reale è `feedback:entry_threshold`**, non `min_score`
(`config.py:14-19`). Implementato in `portfolio_scheduler.py:1280-1340`:

- `feedback:entry_threshold:S4` (per-strategy key) o fallback
  `feedback:entry_threshold`; baseline `_ENTRY_THRESHOLD_BASELINE` (0.30,
  `portfolio_scheduler.py:2941-2956`).
- Il ratchet è alzato dinamicamente dal loss-feedback loop; enforce nel
  portfolio_scheduler.
- Logica (`portfolio_scheduler.py:1322,1340`): un ticker entra iff
  `score >= entry_threshold` (segnale fresco e positivo → buy thesis holds).
- `min_score`/`min_confidence` del ranker sono **prefiltri** che scartano prima
  del ranking; l'entry gate è il filtro di **ordine** upstream.

## 4. Universo

- Backtest (`backtest.py:234-236`): `load_universe("s1")` (lo stesso universo
  S1), `start=2010-01-01`, prezzi allineati via DataLoader.
- Live: universi gestiti dal portfolio_scheduler (watchlist S4); i segnali sono
  generati per i ticker nella news pipeline (ticker resolver deterministico).

## 5. Rebalance, entry/exit

`__call__` (`strategy.py:85-150`):
- `_should_rebalance` (`strategy.py:189-203`): **DAILY** default
  (`config.py:40-42`).
- `signals = _signals_as_of(ts)` (`strategy.py:156-187`): righe con
  `generated_at <= ts`; freshness window `max_signal_age_hours=4`
  (`strategy.py:167-169`): drop segnali più vecchi di 4h (QS-07 parity live/backtest).
- `compute_target_weights(signals, as_of=ts)` (`strategy.py:58-66`) → ranker.
- NAV = cash + Σ market_value (`strategy.py:205-211`).
- Exit: chiude posizioni assenti dal target (SELL, `strategy.py:101-114`).
  **Solo long** (`pos.quantity > 0`, `strategy.py:105`).
- Entry/rebalance: `target_qty = NAV·w/price`; `delta`; BUY/SELL; soglia
  `abs(delta) < 1e-4` (`strategy.py:121-148`).

## 6. Config (S4Config defaults, `config.py`)

| Parametro | Default | Ruolo |
|---|---|---|
| `n_top` | 5 | top-N ticker per bucket |
| `bucket_pct` | 0.10 | sleeve S4 (10%) |
| `min_confidence` | 0.3 | prefiltro ranker |
| `min_score` | 0.1 | prefiltro ranker |
| `min_stocks` | 1 | soglia bucket vuoto |
| `fixed_slot_sizing` | True | 1/n_top per slot (#81) |
| `signals_lookback_hours` | 96 | lookback segnali (3-day gap) |
| `max_signal_age_hours` | 4 | freshness window |
| `rebalance_frequency` | DAILY | |

**Wired live**: `fixed_slot_sizing` letto da `trading.yaml
risk.s4_fixed_slot_sizing_enabled` (`portfolio_scheduler.py:3079-3080`,
`config.py:35`). A differenza di S1/S2/S3 (dead config), S4 **è** configurabile
runtime via trading.yaml.

## 7. Backtest (`backtest.py`)

- `run_s4_backtest_from_prices_and_signals` (`backtest.py:24-160`): WF 1260/252,
  OOS Sharpe da concat window returns (`backtest.py:72-79`).
- Hard gates per S4: gate 1 (significance) + gate 5 (stress)
  (`backtest.py:108-111`); `hard_gates_pass`.
- `_run_perturbation` (`backtest.py:163-197`): perturba n_top/bucket_pct (5 combo).
- `run_s4_backtest_full` (`backtest.py:216-244`): carica prezzi + segnali reali
  da PostgreSQL (`_load_sentiment_signals`, `backtest.py:247-266`); fallback
  **segnali sintetici** se DB non disponibile (`_generate_synthetic_signals`,
  `backtest.py:269-289`).
- `note`: "S4 enters portfolio at 10% R&D sleeve regardless of gate results"
  (`backtest.py:136`) → **S4 entra a prescindere dai gate** (overlay di ricerca).

## 8. Stato di integrazione runtime

- **Registry**: S4 registrata, hard cap 10%, `mode=live` vietato
  (`registry.py:228,240`).
- **Live path**: `portfolio_scheduler.py` legge segnali, applica
  `feedback:entry_threshold`, sizing `fixed_slot_sizing` da trading.yaml.
- **Lifecycle DB**: `mode=paper`, `approved=t`, `promotion_blocked=true`.
- **Trades**: 64 trade in `trades.stop_strategy='S4'` (fase 06).
- S4 è **l'overlay live paper attivo**: realmente eseguita, promozione a live
  bloccata (P0-13: nessun gate report, IC>placebo non confermato).

## 9. Pseudocodice (path live paper)

```
each portfolio-cycle tick:
  signals = SELECT from sentiment_signals WHERE ticker IN watchlist
            AND generated_at <= now AND age <= max_signal_age_hours(4)
  ranker:
    dedupe by symbol (latest generated_at)
    filter confidence>=0.3 AND abs(score)>=0.1 AND score>0  (long-only)
    sort by score desc, take n_top=5
    per_ticker_weight = 1/5 (fixed_slot)   # slot vuoti non ridistribuiti
  entry gate (portfolio_scheduler):
    admit ticker iff score >= feedback:entry_threshold:S4 (baseline 0.30, ratchet)
  sleeve scaling:
    final_weight = allocation_pct(0.10) × per_ticker_weight × regime_mult? (S4 path)
  orders: BUY/SELL delta toward target_qty = NAV·final_weight/price
  exits: SELL positions absent from target (long-only)
```

## 10. Punti chiave per le fasi 05-07

- **Entry gate = feedback ratchet, non min_score**: la soglia di ordine è
  dinamica (loss-feedback), non il `min_score=0.1` del ranker. Disaccoppiamento
  potenzialmente fonte di confusione / drift.
- **fixed_slot_sizing (#81)**: override esplicito del default-off discipline
  (perdita reale 2026-07-17 -$77.88) → decisione operatore, non neutra.
- **Backtest fallback sintetico**: se DB non disponibile, segnali casuali
  (`_generate_synthetic_signals`) → backtest può misurare rumore, non alpha.
- **Long-only asimmetrico**: solo `score>0` entra; `score≤0` non va short →
  segnali bear non monetizzati (trailing memory: "BUY su FinBERT-fallback guard
  asimmetrico", functional audit 2026-07-22).
- **Signal_id coupling**: `last_signal_provenance` (`strategy.py:52,65`)
  pinna signal_id per decision logging + idempotency (fix B33 follow-up).
- **IC>placebo non confermato**: la promozione a live è bloccata proprio sul
  criterio alpha (P0-13) → verdetto alpha fase 04 deve confrontarsi con questo.

---
**Stato fase:** 01_specification = **done**. Prossimo cursore: `S4:02_hypothesis`.