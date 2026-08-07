# S1 — 07 Bug confermati

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04
**Metodo di conferma:** ogni bug è confermato con (a) uno script di riproduzione eseguibile sotto `S1/`, (b) una traccia deterministica (grep/DB), o (c) un controesempio matematico. Nessun bug è asserito senza evidenza.

## Legenda severità
`CRITICAL` = perdita di denaro / bias che invalida l'evidenza · `HIGH` = governance/sicurezza · `MED` = qualità/mantenibilità · `LOW` = minore.

---

## BUG-1 — `config/s1_strategy.yaml` è dead config (non wired)
- **Severità:** HIGH (governance) — latente ora, critico sotto freeze
- **Sintomo:** il file è documentato come config di S1 ma non è caricato nel path runtime.
- **Conferma:** `S1/repro_1_deadconfig.py` (eseguito 2026-08-04):
  - `ast.walk` su tutti i `*.py` di `src/` → **0 call site di `*.from_yaml`**;
  - `_build_strategy_instance` (`portfolio_scheduler.py:3068`) usa `S1Config()` defaults;
  - `S1Config()` defaults == `S1Config.from_yaml(yaml)` oggi (target_vol 0.10, lookbacks 21/63/126/252, max_weight 0.20) → il bug è **latente**: editare il yaml non ha effetto, e un operatore potrebbe credere di aver tarato S1.
- **Impatto freeze:** durante 03/08→28/09, un "cambio nel config" è inerte; se qualcuno edita il yaml credendo sia autorizzato, non cambia nulla (falso positivo di intervento) — o peggio, se i defaults venissero cambiati in codice, il yaml suggerirebbe valori diversi non applicati.
- **Loco:** `src/strategies/s1/strategy.py:38-53` (`from_yaml`, morto); `src/workers/portfolio_scheduler.py:3068`; `src/strategies/s1/backtest.py:39` (anche il backtest usa `S1Config()`).

## BUG-2 — Look-ahead nella selezione universo (filtro full-window)
- **Severità:** CRITICAL (invalida l'evidenza di backtest)
- **Sintomo:** `compute_signal` decide l'universo con statistiche sulla **finestra completa** del pannello passato; nel backtest il pannello include tutto lo storico futuro.
- **Conferma:** `S1/repro_2_lookahead.py` (eseguito 2026-08-04) — controesempio deterministico:
  - 3 ticker (A, B sopravvissuti; C delisted dopo giorno 60). as_of = giorno 50.
  - Pannello **truncated** (data ≤ as_of): universo = {A, B, C}, z-score di A = **−0.1697**.
  - Pannello **full** (data → giorno 99): C è droppato (copertura 61/100 = 61% < 75% per via dei NaN futuri 61–99), universo = {A, B}, z-score di A = **−0.7071**.
  - ⇒ alla stessa data, il segnale backtest (pannello full) usa informazione futura per escludere C e alterare lo z-score di A.
- **Loco:** `src/strategies/s1/signal.py:92-116` (filtro coverage full-window), `:118-120` (pannello bilanciato), `:54-57` (docstring che **ammette** il look-ahead).
- **Nota:** il progetto lo sa ("known, accepted look-ahead in backtests") ma non è quantificato né compensato; l'evidenza di backtest S1 va trattata come non-attendibile su questo asse.

## BUG-3 — Survivorship bias (universo non delisting-aware)
- **Severità:** CRITICAL (invalida l'evidenza di backtest)
- **Sintomo:** il backtest usa l'universo **odierno** con prezzi 1993→oggi → solo titoli sopravvissuti; nessun delisted.
- **Conferma:** traccia statica:
  - `src/backtest/data/universe.py:37-38` — `active_at(as_of)` filtra per `inception_date <= as_of` ⇒ **inception-aware** (gestisce le nuove quotazioni, no look-ahead per i late-listed);
  - MA l'appartenenza all'universo proviene da `data/sp500_tickers.csv` (snapshot **corrente**, `config/universe.yaml:29`) e i prezzi via `_fetch_yfinance` (`loader.py:56`) → i titoli **delisted** sono assenti ⇒ **non delisting-aware**.
  - `run_s1_backtest_full` (`backtest.py:207-212`): `load_universe("s1")` + `get_aligned_prices(..., start=1993, end=today)`.
  - Project-acknowledged in `config/strategies.yaml` (nota P0-01: "survivorship bias").
- **Loco:** `src/strategies/s1/backtest.py:207-212`; `src/backtest/data/universe.py`; `src/backtest/data/loader.py`.

## BUG-4 — Note di demotion stale (governance/doc)
- **Severità:** MED (governance — decisioni basate su motivi superati)
- **Sintomo:** `config/strategies.yaml` (S1) elenca "same-bar fill (t+0)" e "zero-cost assumption" come motivi di demotion, ma entrambi sono stati fixati.
- **Conferma:** traccia statica:
  - `src/backtest/engine/orchestrator.py:95` `fill_at_next_open: bool = True` (T+1, "P1-BACKTEST-TPLUS1-FILL"); fill al next-bar open (`:214-231`);
  - `src/backtest/engine/orchestrator.py:171-172` `RealisticCostModel(config/cost_model.yaml)` (costi realistici, "P1-COST-MODEL-REALISM");
  - `src/backtest/engine/orchestrator.py:58-86` `BacktestManifest` (data/code/config hash, P0-10);
  - `WalkForwardRunner` usa i default T+1+costi (`runner.py:60-62`).
  - ⇒ la demotion resta giustificata ma per **altri** motivi (BUG-2, BUG-3, regime circolare, DSR n_trials piccolo, divergenza backtest↔live), non per t+0/zero-cost.
- **Loco:** `config/strategies.yaml` (note S1) vs `orchestrator.py:95,171-172`.

## BUG-5 — d_hard shadow breach su posizione S1 aperta, nessun catastrophe stop wired
- **Severità:** HIGH (paper, ma condizione di revisita documentata è già verificata)
- **Sintomo:** lo stop-shadow log mostra 15 breach `d_hard` su una posizione S1/NOK aperta, con adverse 22.99%, e nessun floor enforce.
- **Conferma:** traccia DB (read-only, 2026-08-04):
  - `stop_shadow_log` ultime 48h, `d_hard_breached=true`: **NOK / S1, n=15, max adverse 22.99%**, first 2026-08-03 14:07, last 2026-08-03 19:52.
  - `trades` per NOK: posizione **aperta** entry 2026-07-14 14:07, entry_price $11.72, **exit_time NULL** (tenuta ~21 giorni, observed ~$9.03 = −22.99%); la precedente entry 07-10 era uscita `stop_loss` il 07-13 (prima della disabilitazione 07-15 del protective stop).
  - `config/trading.yaml:182` `stop_loss: 0.0` (protective disabled); `:194` `stop_shadow_enabled: true`; commento `:180-181`: "if any position rides past -15/20% (d_hard shadow), wire d_hard to a real broker order".
  - ⇒ la condizione di revisita è **verificata su una posizione reale** e d_hard non è wired.
- **Loco:** `config/trading.yaml:172-194`; `src/workers/execution.py:557,722-730` (path stop, shadow-only con stop_loss=0.0).
- **Disclaimer:** non è un "bug di codice" ma una **condizione di rischio live non indirizzata** che la config stessa dice di gestire; durante il freeze 03/08→28/09 l'azione (wire d_hard) è fuori questione, ma l'evidenza va registrata.

---

## Osservazioni NON confermate come bug (registrate per trasparenza)

- **OBS-1 — Pannello bilanciato** (`signal.py:118-120`): droppa date dove un ticker incluso ha NaN. Meccanismo correlato a BUG-2; è una scelta di costruzione del pannello, non un bug isolato. `UNCONFIRMED` come bug standalone.
- **OBS-2 — Sizing non scala con la strength del segnale** (`strategy.py:135-144`): il segnale è un gate binario (z>0); il peso è solo inverse-vol. Scelta di design (vedi `05_code_mapping.md` D2), non un bug. Diverge dalla letteratura momentum ma è intenzionale.
- **OBS-3 — Divergenza codepath backtest↔live** (`__call__` vs `compute_target_weights`): il backtest non replica sleeve-scaling/cap/regime/stop del path live. Divergenza architetturale confermata (traccia in `06_implementation_audit.md` §6.6), non un "bug" ma una limitazione della validità del backtest come simulazione del live.
- **OBS-4 — Regime split circolare** (`backtest.py:180-193`): regimi definiti sugli stessi OOS returns. Confermato come hindsight intra-OOS (traccia in `06` §6.5); grave per la validità del gate di regime, non un bug di codice.

## Sintesi

| ID | Bug | Severità | Conferma |
|---|---|---|---|
| BUG-1 | dead config `s1_strategy.yaml` | HIGH (latente) | repro_1 ✅ |
| BUG-2 | look-ahead selezione universo | CRITICAL | repro_2 ✅ (controesempio) |
| BUG-3 | survivorship (non delisting-aware) | CRITICAL | traccia statica ✅ |
| BUG-4 | note demotion stale | MED | traccia statica ✅ |
| BUG-5 | d_hard breach su posizione aperta, no wire | HIGH | traccia DB ✅ |
| OBS-1..4 | pannello bilanciato / sizing gate / codepath / regime circolare | — | osservazioni |

**Nessun bug confermato richiede azione durante il freeze.** Tutti sono findings di audit (read-only); l'azione è responsabilità dell'operatore e fuori freeze fino al 28/09.

---
**Stato fase:** 07_bugs = **done**. Prossimo cursore: `S1:08_report`.