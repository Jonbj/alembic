# Alembic — Strategy Reference

This document describes each trading strategy, its signal logic, sizing rules, and integration with the portfolio orchestrator.

> **Governance note (2026-06-21):** Live trading is NOT authorized. Strategy promotions require a passing gate report, an approved `strategy_lifecycle` DB row, and explicit PO sign-off. `GLOBAL_LIVE_PROMOTION_ENABLED` must remain `False`. Authoritative runtime state: `strategy_lifecycle` DB table (historical P2 status: `docs/archive/2026-06-p2-milestone/P2_STATUS_2026-06-21.md`).

---

## Strategy Mode Reference

| Mode | Meaning |
|------|---------|
| `research` | R&D only — no live capital, no portfolio orchestrator wiring |
| `paper` | Runs against paper account; observational only |
| `supervised_paper` | Paper trading with human review required before any promotion |
| `promotion_blocked` | Implementation complete but gate report missing or explicitly blocked; cannot be promoted |
| `live` | Real capital — requires `GLOBAL_LIVE_PROMOTION_ENABLED=True` (currently `False`) + PO sign-off |
| `disabled` | Not active; excluded from `StrategyRegistry.get_active_strategies()` |

---

## S1 — Multi-Lookback Relative Momentum

**Type:** Trend-following long-only
**File:** `src/strategies/s1/`
**Allocation:** 50% (see `config/strategies.yaml`)
**Status:** `supervised_paper` — demoted from paper to supervised_paper 2026-06-18 (P0-01, commit `cb1d43a`)

> Live trading is **NOT authorized** for S1. Promotion from `supervised_paper` to `live` requires: (1) 90 days of controlled paper evidence, (2) P2-05 closure, (3) Kimi P2 Acceptance Audit, (4) PO sign-off, (5) `GLOBAL_LIVE_PROMOTION_ENABLED=True` (currently `False`).

### Signal Logic

Computes a multi-lookback, vol-normalised momentum signal with cross-sectional z-scoring:

```
For each lookback lb in {21, 63, 126, 252} trading days:
    raw_lb = price / price.shift(lb) - 1          (raw return)
    norm_lb = raw_lb / rolling_vol(63d)            (vol-normalised)

signal_raw = weighted_sum(norm_lb, weights)         # exponential: longer lb → more weight
signal = cross_sectional_z_score(signal_raw)        # z-score across all symbols at each date
```

- **Lookbacks:** 1M (21d), 3M (63d), 6M (126d), 12M (252d) — captures momentum at multiple horizons
- **Weighting:** Exponential (longer lookbacks weighted more: 1×, e×, e²×, e³×, normalised)
- **Cross-sectional z-score:** Standardises signals across the universe at each date; a symbol ranks relative to peers, not on absolute return level
- **Long-only:** Negative signals produce zero weight; no shorting

> **Note:** This is _not_ the canonical Moskowitz et al. 12-1 TSMOM. It is best described as "Multi-Lookback Relative Momentum" — the cross-sectional z-score makes it a hybrid time-series/cross-sectional approach.

### Sizing

`src/strategies/s1/sizing.py`:
- `raw_weight = min(target_vol / realised_vol_60d, max_weight)` — inverse-vol sizing
- The signal is only an eligibility filter (`z > signal_threshold`, whose live default is `0.0`);
  its magnitude does **not** scale the weight
- Raw weights are normalised only when their sum exceeds 1.0, so the resulting sleeve-local
  target has sum ≤ 1.0
- Output: `{symbol: sleeve_weight}` — orchestrator scales by `allocation_pct=0.50`

With the live defaults (`target_vol=0.10`, `max_weight=0.20`), the cap binds whenever annualised
volatility is ≤50%. On the 2026-09-01 live universe this covered about 77% of names, flattening most
of the inverse-vol differentiation; this is measured by `scripts/measure_s1_sizing_degeneracy.py`.

### Key Parameters (`S1Config`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lookbacks` | (21, 63, 126, 252) | Lookback windows in trading days |
| `vol_window_signal` | 63 | Rolling vol for return normalisation |
| `vol_window_sizing` | 60 | Rolling vol for inverse-vol sizing |
| `target_vol` | 0.10 | Annualised per-position vol target for sizing |
| `max_weight` | 0.20 | Cap applied to each raw inverse-vol weight |
| `signal_threshold` | 0.0 | Eligibility gate; signal strength does not scale weight |
| `rebalance_frequency` | `MONTHLY` | Cadenza di ribilanciamento — rispettata sia dal backtest sia dal path live (vedi *Rebalance cadence*) |

### Integration

S1 exposes `compute_target_weights(prices: pd.DataFrame) → dict[str, float]`. The orchestrator calls this directly when `strategy_id == "S1"` in `_extract_target_weights()`.

---

## S2 — Volatility Risk Premium (VRP)

**Type:** Mean-reversion, overnight gap
**File:** `src/strategies/s2/`
**Allocation:** 0% — **disabled by default**
**Status:** Research only — OOS Sharpe −0.55, all backtest gates (1–4) failed

> ⚠️ S2 is **not active** in paper or live trading. It is registered in `StrategyRegistry` with `enabled=False, allocation_pct=0.00`. To activate it, you must manually edit `config/strategies.yaml` — doing so is explicitly flagged as requiring research milestone gates to pass first.

### Economic Rationale

The normative theory is documented in
[`docs/strategies/s2-vrp-theory.md`](strategies/s2-vrp-theory.md). In seller-sign terms,
the variance risk premium is the difference between risk-neutral expected variance and
physical expected variance over the same horizon. It is primarily compensation for
downside, jump, convexity, correlation, liquidity, and intermediary-capital risks, not
alpha by definition. A short put is a mixed exposure to that premium; long SPY overnight
is not an equivalent variance-premium exposure.

### Current Implementation (Proxy)

The current `S2ProxyStrategy` is an equity proxy — it does **not** use options. It goes long SPY at close when VRP (VIX / realised_vol_20d - 1) exceeds a threshold and exits at the next open.

This is a simplified stand-in. The intended S2 design (cash-secured short put on SPY at delta −0.20, DTE 30–45d) requires options data, greeks pricing, margin modeling, and an IBKR adapter (Phase D).

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vrp_threshold` | 0.20 | Minimum implied/realised premium |
| `lookback_days` | 63 | Realised vol window (≈ 3 months) |
| `position_size` | 0.25 | Fraction of NAV per trade |

### Integration

S2 runs as `(ts, data_replay, portfolio, market) → list[Order]`. The orchestrator converts orders to implied weights. Currently inactive — all cycles skip S2 since it is disabled in `config/strategies.yaml`.

---

## S4 — News-Driven Tactical

**Type:** News sentiment momentum
**File:** `src/strategies/s4/`
**Allocation:** Configurable via `StrategyRegistry`
**Status:** `promotion_blocked` — allocation capped until dedicated gate report is produced (P0-13, commit `6d86d3f`)

### Signal Logic (live = portfolio path)

The authoritative execution path is `execution.engine: portfolio` — only the portfolio
cycle submits orders. S4 reads pre-computed ensemble sentiment from Redis/PostgreSQL
(written by SentimentWorker every 15 min) and gates it through the chain below.

> **Verificato contro il codice il 2026-09-04.** La versione precedente elencava quattro
> passi in ordine sbagliato e ometteva tre filtri che nella pratica scartano la maggior
> parte dei candidati (freschezza news, esclusione fallback, moltiplicatore di velocity).
> L'ordine qui sotto è quello eseguito da `_build_strategy_instance` in
> `src/workers/portfolio_scheduler.py:3960-4160`.

| # | passo | dove | codice emesso quando scarta |
|---|---|---|---|
| 0 | **Lettura** dei segnali dal DB, finestra `signals_lookback_hours` = **96h** | `fetch_signals_for_cycle` | — |
| 1 | **Freschezza della notizia** (#150): `published_at` più vecchio di `MAX_NEWS_AGE_HOURS` (**2h**) → scartato. **Solo per i simboli senza posizione aperta**: un simbolo già a libro salta questo gate | `_apply_entry_freshness_gate` | `SKIP_ENTRY_FRESHNESS` / `entry_freshness_filtered` |
| 2 | **Esclusione fallback** (#108): i segnali con `fallback_used=true` (FinBERT locale) non partecipano al ranking BUY | `_filter_fallback_signals` | `SKIP_FALLBACK` |
| 3 | **Staleness del segnale**: `generated_at` più vecchio di `max_signal_age_hours` (**4h**) → scaduto. **FIX-D** ri-ammette i segnali stale *positivi* sui simboli con posizione aperta e nessun contro-segnale | `_filter_stale_signals` + `_preserve_stale_signals_for_open_positions` | `SKIP_STALE` / `expired` |
| 4 | **Signal velocity** (#401): `velocity = score[0] − score[−1]` sulle ultime 3 voci di `signal:{sym}:history`; se `|velocity| > SIGNAL_VELOCITY_THRESHOLD` (**0.30**) lo score è moltiplicato per `1 ± SIGNAL_VELOCITY_BOOST` (**±0.20**). **Applicato PRIMA del gate**: la soglia vede lo score post-velocity | `portfolio_scheduler.py:4114-4146` | — (modifica lo score, non scarta) |
| 5 | **Feedback gate = la soglia d'ordine**: `|score| ≥ feedback:entry_threshold:S4` | `_get_feedback_threshold` | `SKIP_THRESHOLD` / `SKIP_ENTRY_GATE` / `below_entry_gate` |
| 6 | **Ranker** — dedup per simbolo, prefiltri, long-only, top-N | `CrossSectionalRanker` | `RANK_DEDUPLICATED`, `RANK_MIN_CONFIDENCE`, `RANK_MIN_SCORE`, `RANK_LONG_ONLY`, `RANK_OUTSIDE_TOP_N` |
| 7 | **Guardie a valle**: anti-pyramiding P0-05 (un simbolo già a libro non riceve un secondo BUY, **nemmeno per riportarlo a peso**), idempotenza per `signal_id`/giorno, hold-minimum 90 min | `portfolio_scheduler.py:2857`, `_apply_idempotency_filter` | `SKIP_PYRAMIDING`, `SKIP_IDEMPOTENCY` |
| 8 | **Submit**: `notional × regime_multiplier` | `_submit_orders` | `SUBMITTED` |

I codici della colonna di destra sono scritti in due posti con vocabolari diversi:
`execution_decisions.decision` (Decision Log della UI: solo `BUY`, `SELL`, `SKIP_THRESHOLD`,
`SKIP_STALE`, `SKIP_FALLBACK`, `SKIP_PYRAMIDING` — `SKIP_EMA`, `SKIP_CAP` e `SKIP_POSITION`
appartengono al path legacy e **non sono mai stati emessi** sotto `engine=portfolio`) e
`s4_intent_events.reason_code`, che è il ledger completo per intento e contiene anche
`CANDIDATE_OBSERVED`, `SKIP_ENTRY_FRESHNESS`, `SKIP_ENTRY_GATE`, `SKIP_IDEMPOTENCY`,
`RANK_*` e `SUBMITTED`.

**Il ranker (passo 6) in dettaglio** — `src/strategies/s4/ranking.py`:

1. **Dedup**: un solo segnale per simbolo, **il più recente per `generated_at`** — *non* il
   più forte. È un comportamento noto e discusso in **#169**: un pezzo di colore pubblicato
   dopo una notizia forte la sovrascrive per quel ciclo.
2. **Prefiltri**: `confidence ≥ min_confidence` (0.30) e `|score| ≥ min_score` (0.10). Sono
   **prefiltri del ranker, NON la soglia d'ordine** (che è il passo 5).
3. **Long-only**: `score ≤ 0` scartato — S4 non apre short.
4. **Top-N**: ordinamento decrescente per score, primi `n_top` (5).
5. **Peso**: `1/n_top` fisso (`fixed_slot_sizing=True`, #81) — con 2 sopravvissuti su 5 slot,
   i 3 slot liberi restano **non investiti**, non redistribuiti.

> **Threshold map — tre concetti distinti, da non confondere:**
> | Nome | Valore | Ruolo |
> |---|---|---|
> | `S4Config.min_score` / `min_confidence` | 0.10 / 0.30 | **prefiltro** del ranker |
> | `feedback:entry_threshold:S4` | baseline 0.30, dinamico (→0.60) | **soglia d'ordine (fonte di verità)** |
> | legacy `ENTRY_THRESHOLD` + `score>0.30 AND price>EMA20` | — | vecchio path `legacy_sentiment`, **INATTIVO** con `engine=portfolio` |
>
> **Non esiste nessun filtro EMA20 nel path portfolio.** L'unico posto in cui il prezzo è
> confrontato con la EMA20 è `src/workers/execution.py`, cioè il path legacy che non gira.

**La chiave del gate è per-strategia** dallo scaffolding del 2026-07-11 (`de2e915`).
`_get_feedback_threshold` legge `feedback:entry_threshold:<strategia>`; se manca ripiega
sulla vecchia chiave nuda `feedback:entry_threshold`, e infine sul pavimento
`loss_feedback.threshold_baseline` (`config/trading.yaml`, 0.30). Valori vivi al 2026-09-04:
`:S4` = **0.30**, `:S1` = **0.0** (S1 non ha un gate d'ingresso discreto, e lo 0.0 è
deliberato: clampare al pavimento armerebbe un gate su una sleeve progettata per non averlo).
Il ratchet scrive per-strategia (`feedback:state:<strategia>`), quindi una perdita di S1 non
alza la soglia di S4. Il pannello e `GET /api/trading/feedback-status` leggevano invece la
vecchia chiave globale: corretto il 2026-09-04 con #474/PR #495, che ora restituisce una voce
per sleeve.

### Uscite

| meccanismo | condizione | dove |
|---|---|---|
| peso target a 0 | il simbolo non è più nel target del ciclo. L'etichetta (`below_entry_gate`, `expired`, `whipsaw`, `no_signal`, `fallback_filtered`, `entry_freshness_filtered`, `unknown`) è la **disposizione osservata** del segnale, non una deduzione dall'età — vedi `docs/exit_mechanism_labels.md` | `src/portfolio/exit_classification.py` |
| `sentiment_reversal` | un segnale **ensemble** (mai un fallback FinBERT) con `score ≤ SENTIMENT_REVERSAL_EXIT_THRESHOLD` (**−0.35**) e non più vecchio di `SENTIMENT_REVERSAL_MAX_AGE_MINUTES` (60 min) forza la chiusura. Consume-on-fire (#67: lo stesso segnale non spara due volte) e cooldown di re-ingresso di 2h (#68) | `_sentiment_reversal_sells` |
| stop-loss | **disattivato** dal 2026-07-15: `risk.stop_loss: 0.0` in `config/trading.yaml` fa uscire `_stop_loss_breached_symbols` con `{}`. Resta la telemetria shadow (`stop_shadow_log`, `stop_shadow_enabled: true`) e l'allarme Telegram a `unprotected_position_alert_pct` (−15%, #161). Coerentemente `stop_decisions` non ha righe dal 2026-07-14 | `config/trading.yaml:172-206` |

> **`sentiment_reversal` non è un'uscita di S4 soltanto.** `_sentiment_reversal_sells` cicla su
> **tutte** le posizioni del broker, senza filtrare per sleeve: un contro-segnale news può
> liquidare una posizione aperta da S1 e tenuta da settimane. È il tema di **#182** (nessuna
> gerarchia d'uscita fra core e overlay); il P&L realizzato viene accreditato alla sleeve
> proprietaria della posizione, non a S4.

### Scoring Formula

```
score = polarity × confidence
```

Where `polarity ∈ [-1, +1]` is the direction of sentiment and `confidence ∈ [0, 1]` is model certainty. A strong call with low confidence yields a small score — the formula correctly penalises uncertainty.

### LLM Ensemble

Due modelli attivi via Ollama Cloud, **selezionati a runtime** dalla chiave Redis
`config:sentiment_llm_models` (fallback env `SENTIMENT_LLM_MODELS`, poi `"all"`):

- **GLM-5.2 + GPT-OSS 20B** (`glm52,gptoss`) — coppia live dal 2026-07-11, verificata sul
  Redis di produzione il 2026-09-02.

> **Corretto il 2026-09-02:** questa riga diceva "Kimi K2.6 + GLM-5.2", coppia sostituita il
> 2026-07-11. Kimi K2.6 e' ancora *registrato* in `src/llm/model_registry.py` ma non e' nella
> coppia attiva: fu tolto per disaccordo direzionale sistematico con GLM-5.2 (fallback 75-80%)
> e per la peggior accuracy di Stage 1 (0,29 a 29s di latenza).
>
> Storia precedente: Qwen3.5 sostituito da GLM-5.2 il 2026-06-29 (estrazione ticker troppo
> aggressiva su news macro); DeepSeek-V4-Pro e GLM-5.1 rimossi il 2026-06-16. Vedi
> `docs/llm-config.md` (tabella dei modelli sempre aggiornata) e `docs/CHANGELOG.md`.

Each uses **DK-CoT** (Domain Knowledge Chain-of-Thought) prompting. Il prompt vivo è la
**Variante A** (`SENTIMENT_PROMPT_VARIANT=a` in `.env`, in produzione dal 2026-09-01T10:33Z,
`bf5bef2e`, #399/#408) — non il `_DK_COT_PROMPT` storico, che resta il default del codice:

1. ruolo: analista buy-side, impatto sul **singolo emittente**;
2. **il titolo dell'articolo è nel prompt** (`Headline: {title}`, primi 200 caratteri). Prima
   veniva scartato pur essendo popolato nel 99,94% delle righe `news_log` — è il difetto di
   #399 («Why Is Robinhood Stock Surging» valutato −0,0098 in una giornata a +8,17%);
3. lo step 1 chiede **come il mercato prezzerà il titolo**, non solo l'effetto sui
   fondamentali, e impone esplicitamente di non ridurre la polarity solo perché la causa è
   di terzi (#408: le notizie di secondo ordine erano sotto-pesate di ~2,2× in magnitudine);
4. bull/bear case esplicito;
5. output JSON strutturato — oltre a `polarity`/`confidence`/`reasoning` il modello restituisce
   `event_type`, `directness`, `materiality`, `novelty`, `risk_flags`, `evidence_sentences`.
   Questi campi sono **feature del segnale**, non ancora consumati dallo scoring, e per contratto
   il modello non produce mai un'azione di trading (no buy/sell/hold).

> **Deroga al freeze.** La Variante A è stata deployata in deroga esplicita a #171, registrata
> in `docs/evidence/OBSERVATION_CHARTER.md`. Cambia la **distribuzione** degli score, non solo
> la loro correttezza (stimati ~2,4× segnali sopra il gate 0,30 a parità di soglia): **ogni
> analisi di S4 che attraversa il 2026-09-01 va segmentata prima/dopo.** La misura dell'effetto
> reale è l'issue aperta #453.

**Divergence check:** If `std(scores) > 0.40` → discard ensemble, use FinBERT local fallback.
La soglia e' `config.ENSEMBLE_DIVERGENCE_STD` (default 0.40, alzata da 0.30 il 2026-07-09).

> **Corretto il 2026-09-02:** qui era scritto 0.30, il valore pre-2026-07-09. Nota misurata
> allora: alzare la soglia 0.30→0.40 **non** ha ridotto il fallback rate — il disaccordo fra i
> modelli e' direzionale/bimodale, non una nuvola gaussiana da allargare. La leva efficace e'
> la scelta della coppia, non la soglia.
>
> Attenzione a non confondere questo controllo con un *gate d'ingresso*: `ensemble_std` fa
> scattare il fallback FinBERT dentro l'aggregatore del sentiment worker, ma non e' mai
> consultato dal portfolio scheduler prima di un ordine (issue #443).

### FinBERT Fallback

FinBERT (BERT fine-tuned on financial text) runs locally. Confidence uses **entropic confidence**:
```
confidence = 1 - H(p) / log(3)
```
where `H(p)` is Shannon entropy of the 3-class softmax (positive/negative/neutral). A peaked distribution → high confidence; flat distribution → near-zero score.

### Regime Scaling

Position size is scaled by `regime_multiplier` (written to Redis by RegimeDetector):
```
order_notional = base_size × regime_multiplier
```

The multiplier (0.2× to 1.0×) prevents full-size entries during bear markets or volatility spikes, even when the sentiment signal is strongly positive.

### Key Parameters (`S4Config`)

> **Verificato contro `src/strategies/s4/config.py` il 2026-08-03.** La tabella precedente
> elencava quattro parametri (`score_threshold`, `signal_max_age_min`, `base_position_size`,
> `stop_loss_pct`) di cui **nessuno esiste in `S4Config`**, e uno era fuorviante di un fattore
> otto: dichiarava una scadenza segnale di 30 minuti contro le 4 ore reali.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_top` | 5 | Numero di ticker selezionati per ciclo |
| `bucket_pct` | 0.10 | Quota di portafoglio assegnata alla sleeve S4 |
| `min_score` | 0.1 | **Prefiltro del ranker**, NON la soglia d'ordine |
| `min_confidence` | 0.3 | **Prefiltro del ranker**, NON la soglia d'ordine |
| `min_stocks` | 1 | Minimo di titoli per emettere ordini (1 = ammesso il lone survivor) |
| `fixed_slot_sizing` | True | Peso fisso 1/`n_top` per ticker; gli slot inutilizzati restano non investiti (#81) |
| `signals_lookback_hours` | 96 | Finestra di lettura dei segnali dal DB (copre il ponte festivo Ven→Mar) |
| `max_signal_age_hours` | 4 | Oltre questa età il segnale è scaduto e la posizione viene chiusa |
| `rebalance_frequency` | DAILY | Cadenza di ribilanciamento della sleeve |

**La soglia d'ordine non è in `S4Config`.** È `feedback:entry_threshold:S4` in Redis (baseline
0.30, alzata dinamicamente dal loop di loss-feedback) ed è applicata a monte, nel portfolio
scheduler. Confondere `min_score` con la soglia d'ordine è l'errore che nel luglio 2026 ha
lasciato il gate disarmato per un giorno e mezzo (issue #163).

#### I parametri che mordono davvero stanno fuori da `S4Config`

`S4Config` copre solo il ranker. Metà della catena dei passi 1-8 è governata da `src/config.py`,
`config/trading.yaml` e Redis — leggere solo la tabella qui sopra dà un'idea sbagliata di quanto
sia filtrato un candidato.

| Parametro | Valore vivo (2026-09-04) | Dove | Effetto |
|---|---|---|---|
| `MAX_NEWS_AGE_HOURS` | 2 | `src/config.py` (env) | passo 1: età massima della **notizia** per un nuovo ingresso |
| `SIGNAL_VELOCITY_THRESHOLD` | 0.30 | `src/config.py` (env) | passo 4: soglia oltre cui scatta il boost |
| `SIGNAL_VELOCITY_BOOST` | 0.20 | `src/config.py` (env) | passo 4: entità del boost (`×1.20` / `×0.80`) |
| `feedback:entry_threshold:S4` | 0.30 | Redis (TTL 96h) | passo 5: **la soglia d'ordine** |
| `loss_feedback.threshold_baseline` | 0.30 | `config/trading.yaml` | pavimento del gate quando la chiave Redis è assente |
| `ENSEMBLE_DIVERGENCE_STD` | 0.40 | `src/config.py` | a monte: sopra questo `std` l'ensemble degrada a FinBERT (che poi il passo 2 scarta) |
| `SENTIMENT_REVERSAL_EXIT_THRESHOLD` | −0.35 | `docker-compose.yml` | uscita forzata |
| `SENTIMENT_REVERSAL_MAX_AGE_MINUTES` | 60 | env (default) | età massima del contro-segnale che può forzare l'uscita |
| `SENTIMENT_REVERSAL_REENTRY_COOLDOWN_HOURS` | 2.0 | env (default) | blocco al rientro dopo un'uscita forzata (#68) |
| `execution.hold_minimum_minutes` | 90 | `config/trading.yaml` | passo 7: una posizione appena aperta non può essere venduta da un ribilanciamento |
| `risk.stop_loss` | **0.0 (disattivato)** | `config/trading.yaml` | nessuno stop protettivo: solo shadow + allarme a −15% |
| `SENTIMENT_PROMPT_VARIANT` | `a` | `.env` | prompt DK-CoT Variante A (#399/#408) — vedi sotto |

---

## S3 — Cross-Sectional Momentum (R&D Sleeve)

**Status:** Research/development — not deployed in paper trading
**Type:** Cross-sectional equity momentum
**File:** `src/strategies/s3/`

### Signal Logic

Ranks all universe securities by 12-1 month return. Goes long top quintile (Q5), short bottom quintile (Q1). Rebalances monthly.

**Universe:** `src/strategies/s3/universe.py` — S&P 500 constituents filtered by liquidity.

**Status:** Gate validation pending. Not active in `StrategyRegistry` until backtest gates pass.

---

## Portfolio Orchestration

All active strategies flow through the `PortfolioOrchestrator` using a **weight-then-order** architecture.

### Sleeve-Local Allocation

Strategies produce **sleeve-local weights** — fractions of their own capital sleeve, not the whole portfolio. The orchestrator scales each by `allocation_pct` and sums to get portfolio-level targets:

```python
# Current active allocations (from config/strategies.yaml):
#   S1: allocation_pct=0.50  (50% of portfolio)
#   S2: disabled             (0% — OOS gates not passed)
#   S4: allocation_pct=0.10  (10% of portfolio, paper overlay)
# Remaining 40% = implicit cash residual

S1.compute_target_weights(prices)   → {AAPL: 0.40, NVDA: 0.20, ...}  # sleeve-local
S4.compute_target_weights(signals)  → {MSFT: 0.30, TSLA: 0.20, ...}  # sleeve-local

merged = {}
for strategy, alloc_pct in [(S1, 0.50), (S4, 0.10)]:
    for sym, wt in strategy_weights.items():
        merged[sym] = merged.get(sym, 0) + wt * alloc_pct
# → AAPL: 0.40×0.50 = 0.20 (20% of portfolio)
# → NVDA: 0.20×0.50 = 0.10
# → MSFT: 0.30×0.10 = 0.03

delta_orders = [BUY/SELL (target_qty - current_qty) for sym in merged]
```

Allocation config is in `config/strategies.yaml` — that file is the **single source of truth**. `StrategyRegistry` reads it at startup with startup validation (sum ≤ 1.0, S4 ≤ 10%, S2 enabled requires explicit override).

### Rebalance cadence

Il portfolio cycle gira ogni 15 minuti, ma **non tutte le sleeve decidono a ogni ciclo**.
Prima di calcolare i pesi l'orchestratore interroga `should_rebalance(ts)` della strategia —
la stessa identica funzione che il backtest chiama da `__call__`, così le due cadenze non
possono divergere in silenzio (#185).

Fuori dalla propria finestra la sleeve **tiene il libro**: ridichiara i simboli che aveva
in target all'ultimo ribilanciamento *e che detiene ancora*, con peso derivato dal valore
corrente della posizione. Il delta contro il portafoglio è quindi esattamente zero — niente
uscite `s1_weight_drop`, niente trim da drift di prezzo, e niente reingresso su un simbolo
uscito nel frattempo per stop. Restano invece pienamente attivi i path che *non* sono
ribilanciamento: stop-loss, `sentiment_reversal`, kill-switch di drawdown.

L'orologio vive in Redis (`strategy:rebalance_state:{strategy_id}`), non nell'istanza: ogni
ciclo ricostruisce le strategie da zero, quindi uno stato in memoria sarebbe sempre vuoto —
che è precisamente il motivo per cui S1 dichiarava `MONTHLY` e ribilanciava ogni quarto d'ora.
Fail-open: se la chiave manca o è illeggibile il gate resta aperto e la sleeve ribilancia.

| sleeve | dichiarata | onorata dal live |
|---|---|---|
| S1 | `MONTHLY` | sì |
| S4 | `DAILY` | **no** — vedi sotto |

S4 è fuori dal perimetro di #185 (`_REBALANCE_CLOCK_STRATEGIES` nello scheduler). Il suo
predicato `DAILY` è su data di calendario: applicarlo ridurrebbe una sleeve tattica
news-driven a una decisione per seduta, congelando sia gli ingressi intraday sia le uscite
`[expired]`/`[whipsaw]`. È un cambio di strategia, non la correzione di churn documentata
nella issue — allargarlo a S4 è una decisione dell'operatore.

### Constraint Enforcement

Applied iteratively (up to 10 passes) after weight merging:

| Constraint | Default | Action |
|-----------|---------|--------|
| Max single asset | 10% NAV | Scale down BUY |
| Max strategy exposure | alloc_pct × 1.5 | Scale down excess |
| Max portfolio exposure | 50% NAV | Scale all BUYs |
| Max sector exposure | 25% NAV | Scale sector BUYs |
| Max correlation cluster | corr > 0.70 | Reduce higher-vol |

### Volatility Overlay

`PortfolioVolTargeter` computes EWMA portfolio vol from strategy return histories. BUY quantities are scaled by `target_vol / estimated_vol` (clamped to [0.5×, 2.0×]) so the portfolio targets 10% annualised volatility.

---

## S7 — PEAD (Post-Earnings Announcement Drift) — REMOVED 2026-07-15

**Status:** **REMOVED 2026-07-15.** Strategy dir, workers, routes, beat tasks, config,
API entries, tests e codice di supporto eliminati. S7 non è più in repo.

**Perché rimossa:** l'edge dichiarato di S7 (transcript tone → alpha, ALPHA-A3) è confutato
a decision-grade su dati reali. Tre valutazioni distinte, tutte negative:

| Valutazione | Data | Esito | n |
|---|---|---|---|
| ALPHA-A5 large-cap (FMP) | 2026-07-03 | FAIL — drift = beta SPY, hit 51%, no dose-response | 76 |
| POC-1 small/mid PEAD | 2026-07-04 | INCONCLUSIVE_DATA — copertura IEX/liquidità insufficiente | 15 |
| POC-2 transcript tone (ALPHA-A3) | 2026-07-15 | FAIL — IC≈0, spread invertito, split-half opposti, cross-model (kimi↔glm ρ=+0.858) | 73 |

La condizionale pre-registrata di PO-5 — *"Se POC-2 FAIL → REMOVE"* — è attivata.

**Cosa resta:** la documentazione storica completa in
`docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` (design, implementazione, 4 run di valutazione,
decisioni PO, evidence synthesis) e i report/CSV raw in `reports/s7_*` (gitignored,
evidenza locale). Il codice rimosso è recuperabile da git se una futura strategia
event-driven volesse riutilizzare la superficie PEAD/8-K.

**Re-introduzione:** richiede un design fresco + gate evaluation ex novo (non una
riattivazione). Il test `TestS7NotInOperationalRegistry` (`tests/test_p0_13_*.py`) fa da
guard: S7 non deve ricomparire nel `StrategyRegistry` operativo, nemmeno disabilitata.
