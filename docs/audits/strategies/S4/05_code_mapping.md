# S4 — 05 Code Mapping (spec → codice)

**Strategia:** S4 `NewsDrivenTactical`
**Data:** 2026-08-04
**Fonti:** `src/strategies/s4/{strategy,config,ranking,backtest}.py`,
`src/workers/sentiment.py`, `src/workers/portfolio_scheduler.py`,
`src/strategies/registry.py`, `src/models/signals.py`.

S4 ha **due path**: backtest (offline, `backtest.py`) e live paper
(`portfolio_scheduler.py`). Il mapping copre entrambi, con divergenze rispetto
alla spec della fase 01 e tra i due path.

---

## 1. Config (S4Config, `config.py`)

| Componente spec | Codice | Note |
|---|---|---|
| `n_top=5` | `config.py:12` | top-N ticker per bucket |
| `bucket_pct=0.10` | `config.py:13` | sleeve S4 10% |
| `min_confidence=0.3` | `config.py:18` | prefiltro ranker (NON gate ordine) |
| `min_score=0.1` | `config.py:19` | prefiltro ranker (NON gate ordine) |
| `min_stocks=1` | `config.py:24` | soglia bucket vuoto |
| `fixed_slot_sizing=True` | `config.py:37` | 1/n_top per slot (#81) |
| `signals_lookback_hours=96` | `config.py:38` | lookback segnali (3-day gap Fri→Tue) |
| `max_signal_age_hours=4` | `config.py:39` | freshness window |
| `rebalance_frequency=DAILY` | `config.py:40-42` | tattico giornaliero |

**Wired live**: `fixed_slot_sizing` letto da `trading.yaml
risk.s4_fixed_slot_sizing_enabled` (`portfolio_scheduler.py:3079-3080`,
`config.py:35`). A differenza di S1/S2/S3 (dead config), S4 è **configurabile
runtime**. `S4Config` costruito nel scheduler con questo override.

## 2. Segnale: sentiment score (path upstream)

| Componente spec | Codice | Note |
|---|---|---|
| `score = polarity × confidence` | `sentiment.py:325,333,367` | formula CLAUDE.md. Ensemble aggregato (`:333` `aggregated.polarity × aggregated.confidence`), per-modello (`:325,367`). |
| Ensemble pair | Redis `config:sentiment_llm_models` (default `glm52,gptoss`) | CLAUDE.md; swap candidates `in_all=False`. |
| `ensemble_std`, `fallback_used` | `SentimentResult` (`models/signals.py`) | registrati in `sentiment_signals` |
| Forward returns | `sentiment_signals.forward_return_{,3d,5d}` | popolati da `compute_label_forward_returns` (Alpaca storica) |

## 3. Ranker cross-sectionale (`ranking.py`)

| Componente spec | Codice | Note |
|---|---|---|
| `rank` | `ranking.py:85-155` | |
| Dedupe per symbol (latest `generated_at`) | `ranking.py:170-175` | keep più recente |
| Filtro `confidence >= min_confidence` | `ranking.py:179` | prefiltro |
| Filtro `abs(score) >= min_score` | `ranking.py:181` | prefiltro |
| `effective_strength = score` (non ×conf) | `ranking.py:186` | intenzionale: score già ×conf (`ranking.py:6-8`) |
| **Long-only**: `strength > 0` | `ranking.py:187-189` | skip neutral/negative (DV-S4: no short leg) |
| Sort desc, take `n_top=5` | `ranking.py:116-117` | |
| `min_stocks=1`: <1 → bucket vuoto | `ranking.py:107-113` | |
| `per_ticker_weight = 1/n_top` (fixed) | `ranking.py:133` | #81; slot vuoti non ridistribuiti |
| `per_ticker_weight = 1/n_selected` (legacy) | `ranking.py:133` | se `fixed_slot_sizing=False` |
| `bucket_weight = bucket_pct` | `ranking.py:153` | 0.10 |
| Provenance `signal_id/score/reasoning/model_id` | `ranking.py:51-67,135-148` | B33-follow-up: pinna per decision logging |

**Nota**: il ranker restituisce pesi **intra-bucket** (`per_ticker_weight`).
Lo sleeve scaling per `allocation_pct=0.10` è **upstream** nel scheduler.

## 4. Strategy `__call__` (path backtest, `strategy.py`)

| Componente spec | Codice | Note |
|---|---|---|
| `__call__` | `strategy.py:85-150` | |
| `_should_rebalance` DAILY | `strategy.py:189-203` | `ts.date() != last.date()` |
| `_signals_as_of(ts)` | `strategy.py:156-187` | `generated_at <= ts` |
| Freshness `max_signal_age_hours=4` | `strategy.py:167-169` | QS-07 parity live/backtest: drop >4h |
| `compute_target_weights` | `strategy.py:58-66` | via ranker |
| NAV = cash + Σ market_value | `strategy.py:205-211` | |
| Exit: SELL posizioni assenti dal target | `strategy.py:101-114` | **solo long** (`pos.quantity > 0`, `:105`) |
| Entry: `target_qty = NAV·w/price` | `strategy.py:121-124` | |
| Soglia `abs(delta) < 1e-4` | `strategy.py:126` | |
| `health_check` → True (no-op) | `strategy.py:74-75` | non verifica nulla |

## 5. Entry gate LIVE (`portfolio_scheduler.py`) — diverge dal ranker

| Componente spec | Codice | Note |
|---|---|---|
| `feedback:entry_threshold:S4` (per-strategy) | `portfolio_scheduler.py:1277-1300` | ratchet dinamico |
| Fallback `feedback:entry_threshold` | `:1295` | key globale |
| Baseline `_ENTRY_THRESHOLD_BASELINE` | `:2941-2956` | 0.30 (floor; `:1305` nota: era 0.10 min_score, fix #163) |
| Ammette iff `score >= entry_threshold` | `:1316-1340` | `:1340` `{sym for sym,sig if sig.score >= entry_threshold}` |
| Ratchet alzato da loss-feedback | (loop feedback) | dinamico, non OOS-pulito |

**Divergenza chiave**: il gate d'ordine reale è `feedback:entry_threshold`
(baseline 0.30, ratchet), NON `min_score=0.10` del ranker. `config.py:14-19` è
esplicito: `min_score`/`min_confidence` sono **prefiltri**. Il sistema opera a
due filtri: ranker prefiltro (0.10) → entry gate ratchet (0.30+). Disaccoppiamento
potenzialmente fonte di drift tra backtest (che usa solo il ranker) e live (che
aggiunge il ratchet).

## 6. Sleeve scaling + registry cap

| Componente spec | Codice | Note |
|---|---|---|
| Hard cap 10% | `registry.py:228` | `S4 allocation exceeds 10% hard cap` |
| `mode=live` vietato | `registry.py:240` | no gate report + IC>placebo non confermato |
| S4Config live construction | `portfolio_scheduler.py:3079-3080` | `S4Config(fixed_slot_sizing=_fixed_slot)` da trading.yaml |
| S4 in `_SAFE_DEFAULTS` | `registry.py:27` | 10%, enabled |

## 7. Idempotency / fired signals (path live)

| Componente spec | Codice | Note |
|---|---|---|
| `_S4_FIRED_SIGNALS_TTL=108000` (30h) | `portfolio_scheduler.py:552` | idempotency per session |
| `_get_fired_signal_ids` | `:960-977` | Redis; fail-closed se unreachable (P2-05-A) |
| `_filter_fired` skip syms | `:984-987` | se Redis down → skip tutti S4 BUY |
| `_mark_fired_signal` | `:1349-1354` | aggiunge a set Redis, TTL prima scrittura |
| Signal_id resolution | `:775-787` | #109: conviction dallo stesso signal_id della decision |

## 8. Exit classification (path live)

| Componente spec | Codice | Note |
|---|---|---|
| Weight-0 SELL reason | `:584-594` | `no_signal`/`expired`/`whipsaw` |
| `max_age_hours` expired | `:647-665` | `[expired] age > max_signal_age` |
| Non-S4 position tag | `:609-623` | `[no_signal]` trivially true per posizioni non-S4 |

## 9. Backtest (`backtest.py`)

| Componente spec | Codice | Note |
|---|---|---|
| `run_s4_backtest_from_prices_and_signals` | `backtest.py:24-160` | WF 1260/252 |
| OOS Sharpe (concat, sort) | `backtest.py:72-79` | `sharpe_ratio(periods=252)` |
| Hard gates: gate1 + gate5 | `backtest.py:108-111` | `hard_gates_pass` |
| `_run_perturbation` | `backtest.py:163-197` | 5 combo n_top/bucket_pct |
| `run_s4_backtest_full` | `backtest.py:216-244` | prezzi + segnali reali da PG |
| `_load_sentiment_signals` | `backtest.py:247-266` | da `PostgreSQLStore.fetch_signals_for_backtest_batch` |
| **Fallback segnali sintetici** | `backtest.py:269-289` | `_generate_synthetic_signals`: RNG uniform, **segnali casuali** se DB non disponibile |
| `note`: "enters at 10% regardless of gates" | `backtest.py:136` | overlay R&D, gate non-blocking |

**Divergenza critica**: il backtest **fallback sintetico** genera segnali casuali
(`rng.uniform(-0.5,0.9)`) se PostgreSQL non è disponibile → un backtest run senza
DB misura **rumore**, non alpha. Nessun guard che avverta l'utente.

## 10. Divergenze spec ↔ codice / path

| ID | Divergenza | Dettaglio |
|---|---|---|
| DV-S4-1 | Gate ordine ≠ ranker prefiltro | `min_score=0.10` (ranker) vs `entry_threshold=0.30+` ratchet (live). Backtest usa solo ranker → drift backtest/live. |
| DV-S4-2 | Long-only asimmetrico | `ranking.py:187-189` `strength>0`; exit solo long `strategy.py:105`. No short leg → metà drift non monetizzata. |
| DV-S4-3 | Fallback sintetico nel backtest | `backtest.py:269-289` RNG; misura rumore se DB assente, senza guard. |
| DV-S4-4 | health_check no-op | `strategy.py:74-75` → True sempre; non verifica segnali/dati. |
| DV-S4-5 | Tattico giornaliero vs PEAD 60-180g | `rebalance_frequency=DAILY`, `max_signal_age_hours=4` → orizzonte 1-2g, non drift forte. |
| DV-S4-6 | Overlay di conferma a S1, non standalone | orchestrator combina sleeve; duplicazione momentum beta (cross_review). |
| DV-S4-7 | `effective_strength = score` non ri-normalizza | intenzionale (score già ×conf), MA non vol-scaled (sizing pari peso). |

## 11. Punti chiave per le fasi 06/07

- **DV-S4-1 (gate drift backtest/live)**: il backtest non applica il ratchet →
  l'OOS Sharpe del backtest (se calcolato) non riflette il gate live. Bug/gap.
- **DV-S4-3 (fallback sintetico)**: se il backtest è stato run senza DB, il
  risultato è rumore. Verificare quale `summary.json` esiste (fase 06: nessuno
  in `reports/s4_backtest/`). Da confermare in fase 07.
- **DV-S4-2 (long-only asimmetrico)**: non un bug, ma limita l'edge alla gamba
  debole (letteratura fase 03).
- **Idempotency fired signals (P2-05-A)**: fail-closed se Redis down → skip S4
  BUY. Comportamento difensivo corretto, MA può nascondere perdita di segnali.
- **Signal_id coupling #109**: conviction dallo stesso signal_id (`:775-787`)
  — fix di un bug reale (WDC signal_id=4427 divergente). Da citare in cross_review.
- **IC computation** (`scripts/compute_s4_ic.py`): è la **vera** misura di alpha
  del progetto, separata dal backtest. IC<0 (fase 04). Il backtest Sharpe è
  quasi secondario rispetto all'IC per la decisione di promozione.

---
**Stato fase:** 05_code_mapping = **done**. Prossimo cursore: `S4:06_implementation_audit`.