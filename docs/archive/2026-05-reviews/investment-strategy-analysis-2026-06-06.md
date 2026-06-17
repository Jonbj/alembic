# Alembic Investment Strategy Analysis

Data analisi: 2026-06-06  
Scopo: analisi delle strategie di investimento adottate da Alembic, confrontando documentazione, codice, scheduler e report di backtest.  
Destinatario operativo: Claude Code, per trasformare questa analisi in interventi sul codice.

Nota: questa analisi valuta coerenza tecnica, robustezza research e rischi di implementazione. Non e una raccomandazione finanziaria.

---

## Executive summary

Alembic e progettato come portafoglio multi-strategy composto da:

- S1 Time-Series / Multi-Lookback Momentum: sleeve core.
- S2 Volatility Risk Premium / short-put income: sleeve income, oggi ancora non validata.
- S3 Cross-Sectional Residual Momentum: sleeve R&D, esclusa dal live.
- S4 News-Driven / LLM Sentiment Tactical: overlay tattico R&D.

La filosofia di portafoglio ha senso: combinare trend/momentum, income da premio di volatilita e alpha tattico da news/sentiment. Pero lo stato attuale del repo mostra tre problemi centrali:

1. La documentazione strategica non coincide sempre con il codice.
2. Le allocation live nel registry non coincidono con le allocation raccomandate nei documenti.
3. L'orchestrator rischia di annullare di fatto l'allocation per strategia quando normalizza i pesi per simbolo.

La valutazione piu prudente e:

| Strategia | Stato consigliato | Motivo |
|---|---:|---|
| S1 | Live/paper core | Backtest e gate migliori del progetto; OOS Sharpe circa 0.51 |
| S2 | Research/paper only | Razionale forte, ma implementazione proxy e backtest falliti |
| S3 | Disabilitata/R&D | Gate falliti, OOS debole, possibile lookahead nel sizing |
| S4 | Overlay piccolo/R&D | Implementazione interessante, ma validazione incompleta e doppio execution path |

Prima di fare tuning alpha, Claude Code dovrebbe sistemare la parte di portfolio construction e governance live: registry, scheduler, orchestrator, allocation effettiva, singolo motore di esecuzione autoritativo.

---

## Fonti principali analizzate

Documentazione:

- `docs/strategies.md`
- `docs/alembic_v2/01_strategy_design.md`
- `docs/ARCHITECTURE.md`
- `docs/NEXT_STEPS_V2.md`

Codice strategie:

- `src/strategies/registry.py`
- `src/strategies/s1/strategy.py`
- `src/strategies/s1/signal.py`
- `src/strategies/s1/sizing.py`
- `src/strategies/s2/config.py`
- `src/strategies/s2/strategy.py`
- `src/strategies/s3/strategy.py`
- `src/strategies/s3/signal.py`
- `src/strategies/s4/config.py`
- `src/strategies/s4/ranking.py`
- `src/strategies/s4/strategy.py`

Portfolio/execution:

- `src/portfolio/orchestrator.py`
- `src/portfolio/constraints.py`
- `src/portfolio/vol_targeting.py`
- `src/workers/portfolio_scheduler.py`
- `src/workers/celery_app.py`
- `src/workers/execution.py`

Report:

- `reports/s1_backtest/summary.json`
- `reports/s1_backtest/gate_report.json`
- `reports/s2_backtest/summary.json`
- `reports/s2_backtest_v2/summary.json`
- `reports/s2_backtest_v2/gate_report.json`
- `reports/s3_backtest/summary.json`
- `reports/s3_backtest/gate_report.json`

---

## Strategia dichiarata nei documenti

### Documento `docs/alembic_v2/01_strategy_design.md`

Questo e il documento piu coerente dal punto di vista investment design.

Allocation dichiarata:

| Strategia | Peso target | Stato |
|---|---:|---|
| S1 | 40% | Core |
| S2 | 30% | Income |
| S3 | 0% live | R&D, esclusa |
| S4 | 10% | R&D / tactical overlay |
| Cash | 20% | Residuo |

Il documento dice esplicitamente che il portafoglio live attuale dovrebbe essere:

```text
S1 40% + S2 30% + S4 10% = 80% deployed + 20% cash residual
```

Interpretazione:

- S1 dovrebbe essere la base stabile.
- S2 dovrebbe aggiungere income decorrelato in condizioni normali.
- S4 dovrebbe essere piccolo perche l'edge LLM/news e incerto.
- S3 e gia stata demossa per risultati insufficienti.

### Documento `docs/strategies.md`

Questo documento descrive un sistema piu implementativo, ma contiene drift rispetto al codice corrente:

- S1 e descritta come Moskowitz/Ooi/Pedersen 12-1 momentum con EMA20 filter.
- S2 e descritta in una sezione come VRP/overnight gap long SPY, mentre il documento v2 parla di short put cash-secured.
- S4 e descritta come threshold strategy su Redis: score > 0.3, price > EMA20, stop-loss, regime multiplier.
- La sezione portfolio descrive una merge logic corretta a somma pesata: `merged[sym] += wt * alloc_pct`.

Il problema e che il codice corrente non implementa sempre questa versione.

---

## Stato reale nel codice

### StrategyRegistry

File: `src/strategies/registry.py`

Il registry attivo carica:

```python
S1 allocation_pct=0.50 enabled=True
S2 allocation_pct=0.20 enabled=True
S4 allocation_pct=0.30 enabled=True
```

Quindi il codice live di default usa:

```text
S1 50% + S2 20% + S4 30%
```

Questo contraddice `docs/alembic_v2/01_strategy_design.md`, che raccomanda:

```text
S1 40% + S2 30% + S4 10% + 20% cash
```

Rischio:

- S4 riceve nel registry il 30%, tre volte il peso raccomandato dal documento v2.
- S2 riceve il 20%, non il 30%.
- S1 riceve il 50%, non il 40%.
- Non c'e una fonte unica di verita per le allocation live.

Valutazione:

Questa e una issue P0/P1, perche una strategia R&D come S4 puo diventare troppo grande senza una decisione esplicita.

---

## Portfolio orchestration e allocation effettiva

File: `src/portfolio/orchestrator.py`

L'orchestrator dichiara di fare:

1. raccolta target weights da ciascuna strategia;
2. scaling per allocation_pct;
3. merge;
4. delta orders;
5. constraint enforcement;
6. vol targeting opzionale.

Il punto critico e questo pattern:

```python
merged_weights[sym] = merged_weights.get(sym, 0.0) + wt * alloc
_weight_alloc_sum[sym] = _weight_alloc_sum.get(sym, 0.0) + alloc
...
merged_weights[sym] = merged_weights[sym] / total_alloc
```

Il commento dice che si vuole fare una media pesata per evitare doppio conteggio.

Pero questa normalizzazione puo annullare l'allocation per strategia.

Esempio:

- S4 targetta `AAPL` al 2% dentro il suo bucket.
- Registry allocation S4 = 30%.
- Prima del normalize: `0.02 * 0.30 = 0.006`, cioe 0.6% del portafoglio.
- `_weight_alloc_sum[AAPL] = 0.30`.
- Dopo normalize: `0.006 / 0.30 = 0.02`, cioe 2% del portafoglio.

Risultato:

- Il peso di strategia viene cancellato per i simboli posseduti da una sola strategia.
- La sleeve allocation conta solo in caso di overlap tra strategie sullo stesso simbolo.
- La promessa del registry come controllo di rischio non e affidabile.

Questo e probabilmente il rischio tecnico piu importante per l'investment implementation.

Comportamento atteso piu coerente:

```python
merged_weights[sym] += strategy_weight[sym] * allocation_pct
```

senza normalizzare per simbolo.

Se due strategie convergono sullo stesso simbolo, il peso dovrebbe sommarsi fino ai limiti cross-strategy, poi essere gestito da:

- max single asset;
- max sector exposure;
- max gross exposure;
- correlation cluster;
- sleeve caps.

La normalizzazione per simbolo puo essere accettabile solo se i pesi delle strategie sono interpretati come "opinion weights" da mediare, non come "capital allocation weights". Ma i documenti parlano chiaramente di sleeve allocation, non di voto medio.

Priorita consigliata per Claude:

1. Scrivere test che dimostri il bug.
2. Cambiare la merge logic in somma pesata senza divisione.
3. Aggiornare constraint tests.
4. Aggiornare documentazione.

Test minimo da aggiungere:

```python
S4 returns {"AAPL": 0.02}
S4 allocation = 0.10
expected merged target for AAPL = 0.002
```

Altro test:

```python
S1 returns {"SPY": 0.10}
S2 returns {"SPY": 0.20}
allocations S1=0.40, S2=0.30
expected merged SPY = 0.10*0.40 + 0.20*0.30 = 0.10
```

---

## Doppio motore di esecuzione

File: `src/workers/celery_app.py`

Celery beat schedula sia:

```text
run-execution     ogni 15 minuti
portfolio-cycle   ogni ora
```

`run-execution` chiama `src.workers.execution.run_execution_worker`.

`portfolio-cycle` chiama `src.workers.portfolio_scheduler.run_portfolio_cycle`.

Questi due sistemi non sono equivalenti:

### `src/workers/execution.py`

Questo e il vecchio motore diretto S4-like:

- legge segnali Redis `signal:{symbol}:sentiment`;
- scarta segnali stale o fallback;
- entra se `score > ENTRY_THRESHOLD`;
- richiede `price > EMA20`;
- size = `portfolio_value * MAX_POSITION_PCT * regime_multiplier`;
- applica cap per ciclo;
- usa stop loss;
- gira ogni 15 minuti.

Parametri rilevanti:

```python
ENTRY_THRESHOLD = 0.3
MAX_POSITION_PCT = 0.10
MAX_CYCLE_NOTIONAL_PCT = 0.20
STOP_LOSS_PCT = 0.02
SIGNAL_MAX_AGE_MIN = 30
EMA_PERIOD = 20
```

### `src/workers/portfolio_scheduler.py`

Questo e il nuovo motore multi-strategy:

- costruisce `StrategyRegistry`;
- costruisce istanze S1/S2/S4;
- crea `PortfolioOrchestrator`;
- genera ordini finali merged;
- li invia ad Alpaca;
- gira ogni ora.

S4 dentro questo motore:

- legge segnali da PostgreSQL, non Redis;
- usa lookback di 4 ore;
- fa ranking cross-sectional;
- ribilancia weekly di default;
- bucket_pct 10%.

Rischio:

Se entrambi i task sono attivi, Alembic puo tradare simultaneamente:

- una strategia S4 threshold/EMA intraday ogni 15 minuti;
- un portfolio S1/S2/S4 ogni ora;
- con logiche e sizing diversi;
- senza una governance unica di exposure.

Questo e un rischio live molto serio.

Decisione richiesta:

Scegliere un solo execution engine autoritativo.

Raccomandazione:

- Per il sistema multi-strategy: mantenere `portfolio-cycle` come motore autoritativo.
- Disabilitare o trasformare `run-execution` in solo observability/dry-run, oppure rinominarlo come legacy e non schedularlo.
- Se si vuole mantenere l'intraday sentiment execution, allora va integrata come S4 dentro il portfolio orchestrator, non come worker separato.

---

## Analisi S1: Momentum core

### Disegno nei documenti

S1 e descritta come Time-Series Momentum multi-asset:

- razionale: persistenza dei trend su 1-12 mesi;
- letteratura: Moskowitz, Ooi, Pedersen; Asness; AQR trend-following;
- universe: ETF cross-asset;
- signal canonico: 12-1 momentum risk-adjusted;
- sizing: inverse vol;
- target vol: 10%;
- allocation v2: 40%.

### Implementazione reale

File principali:

- `src/strategies/s1/strategy.py`
- `src/strategies/s1/signal.py`
- `src/strategies/s1/sizing.py`

Config reale:

```python
lookbacks = (21, 63, 126, 252)
vol_window_signal = 63
vol_window_sizing = 60
target_vol = 0.10
max_weight = 0.20
signal_threshold = 0.0
rebalance_frequency = MONTHLY
```

Signal reale:

```text
1. Per ogni lookback: ret_lb = price / price.shift(lb) - 1
2. Vol-normalizza: ret_lb / rolling_annualized_vol
3. Weighted sum dei lookback, con pesi esponenziali verso lookback piu lunghi
4. Cross-sectional z-score a ogni data
```

Quindi S1 non e esattamente il 12-1 time-series momentum puro dei documenti.

E piu precisamente:

```text
multi-lookback, vol-normalized, cross-sectional z-scored momentum
```

La strategia e long-only:

```python
return ticker if signal > threshold
```

Il sizing:

```python
weight = target_vol / realized_annualized_vol
cap max_weight
```

### Divergenze doc/codice

| Tema | Documentazione | Codice |
|---|---|---|
| Lookback | 12-1 momentum | 21/63/126/252 multi-lookback |
| Signal type | Time-series momentum per asset | Cross-sectional z-score |
| EMA filter | Citato in `docs/strategies.md` | Non presente in S1 |
| Max leverage per asset | v2 cita 1.5 | codice max_weight 0.20 |
| Allocation | v2 40% | registry 50% |

### Evidenza da backtest

`reports/s1_backtest/summary.json`:

```text
oos_sharpe = 0.5128
milestone_b_pass = true
n_windows = 25
mean_sharpe = 0.4877
worst_drawdown = -0.2661
pct_windows_positive = 0.44
```

Gate report:

```text
Gate 1 significance: pass
Gate 2 walk-forward: pass
Gate 3 robustness: pass
Gate 4 regime: pass
Gate 5 stress: pass
```

Dettaglio importante:

- Gate 2 riporta 16 active windows su 25.
- 12 positive su 16 active windows.
- Positive fraction active = 0.75.

### Valutazione S1

S1 e la strategia piu forte del progetto.

Punti positivi:

- Razionale economico robusto.
- Codice relativamente semplice.
- Backtest OOS ragionevole.
- Gate passati.
- Long-only riduce rischio operativo.
- Inverse-vol sizing e cap per posizione aiutano il controllo rischio.

Punti deboli:

- Non e esattamente la strategia descritta nei documenti.
- L'etichetta "Time-Series Momentum" puo essere fuorviante perche il segnale e cross-sectionally z-scored.
- Non c'e EMA filter, nonostante sia documentato.
- `pct_windows_positive` complessivo 0.44 non e altissimo, anche se tra finestre attive migliora.
- Worst drawdown -26.6% non e trascurabile.

Raccomandazione:

- Tenere S1 come core.
- Allineare documentazione al codice, oppure modificare il codice per implementare il 12-1 puro.
- Non fare tuning parametri prima di risolvere orchestration/allocation.
- Se si mantiene il codice attuale, rinominare concettualmente S1 in "Multi-Lookback Relative Momentum" oppure documentare esplicitamente la cross-sectional normalization.

---

## Analisi S2: Volatility Risk Premium / short put

### Disegno nei documenti

Nel documento v2 S2 e una strategia income:

- cash-secured short put su SPY;
- target delta -0.20;
- DTE 30-45 giorni;
- profit target 50%;
- stop loss 2x premium;
- regime modulation;
- event filter;
- allocation target 30%;
- necessita IBKR/options infrastructure.

Razionale:

- volatilita implicita tende a essere maggiore della volatilita realizzata;
- chi vende protezione incassa premio assicurativo;
- edge persistente ma con skew negativo e tail risk.

### Implementazione reale

File principali:

- `src/strategies/s2/config.py`
- `src/strategies/s2/strategy.py`

Config reale:

```python
target_delta = -0.20
min_dte = 30
max_dte = 45
max_collateral_pct = 0.20
vrp_entry_threshold = 0.0
profit_target_pct = 0.50
stop_loss_multiplier = 2.0
underlying_stop_loss_pct = 0.05
regime_scales = {
    "bull": 1.0,
    "sideways": 0.75,
    "bear": 0.25,
    "high_vol": 0.0,
}
sentiment_block_threshold = -0.5
pre_event_block_days = 1
```

Il codice dichiara esplicitamente:

```text
The backtest engine only handles equity-style positions.
Short-put positions are modeled as SPY-equivalent positions.
```

Quindi il backtest engine vede ordini SPY, non vere opzioni.

Il regime e derivato dalla realized volatility:

```python
vol < 0.12 -> bull
vol < 0.20 -> sideways
vol < 0.35 -> bear
else -> high_vol
```

Nel backtest il sentiment filter e saltato:

```python
spy_sentiment = None
```

La strategia compra/vende SPY-equivalent shares per rappresentare exposure/collateral, ma questo non replica completamente:

- payoff convesso/non lineare di una put;
- theta decay;
- vega;
- skew;
- assignment;
- early exercise;
- bid-ask option;
- margin/collateral dynamics;
- gap risk reale.

### Divergenze doc/codice

| Tema | Documentazione | Codice |
|---|---|---|
| Strumento | Short put SPY reale | SPY-equivalent equity proxy |
| Broker richiesto | IBKR options | Alpaca/equity-compatible backtest |
| Event filter | FOMC/NFP/sentiment | sentiment skip nel backtest, event limitato |
| VRP threshold | documenti citano soglie >0.10/0.20 | config `vrp_entry_threshold=0.0` |
| Allocation | v2 30% | registry 20%, config collateral 20% |
| Tail modelling | richiesto esplicitamente | non pienamente modellato |

### Evidenza da backtest

`reports/s2_backtest/summary.json`:

```text
oos_sharpe = -0.2460
milestone_d_pass = false
n_windows = 3
mean_sharpe = -0.3060
pct_windows_positive = 0.3333
```

Gate:

```text
Gate 1 significance: fail
Gate 2 walk-forward: fail
Gate 3 robustness: fail
Gate 4 regime: fail
Gate 5 stress: pass
```

`reports/s2_backtest_v2/summary.json`:

```text
oos_sharpe = -0.5522
milestone_d_pass = false
n_windows = 14
mean_sharpe = -0.2484
pct_windows_positive = 0.2143
```

`reports/s2_backtest_v2/gate_report.json`:

```text
Gate 1 significance: fail
  sharpe = 0.0009
  p_value = 0.957549
  dsr = 0.5215

Gate 2 walk-forward: fail
  oos_sharpe = -0.5522

Gate 3 robustness: fail
  mean_sharpe = -0.185
  cv = 0.6097

Gate 4 regime: fail
  bull sharpe = -1.9478
  high_vol sharpe = 0.0017
  bear sharpe = 0.0307

Gate 5 stress: pass
```

### Valutazione S2

Il razionale investment e valido, ma l'implementazione non e ancora una strategia short-put investibile.

Punti positivi:

- Idea economica solida.
- Buona consapevolezza documentale di tail risk.
- Config include regime modulation.
- Exit logic e put selection sono avviate.

Punti deboli:

- Backtest non usa vere opzioni come asset tradati.
- Risultati OOS falliscono.
- Il gate stress passa probabilmente anche perche la modellazione proxy riduce il rischio reale, non perche la strategia sia robusta.
- Event filter non dimostrato in backtest.
- `vrp_entry_threshold=0.0` rende il criterio VRP molto permissivo.
- Allocation live nel registry non e coerente con i doc.

Raccomandazione:

- Non trattare S2 come sleeve live validata.
- Tenerla in paper/research.
- Prima di assegnare capitale reale, servono:
  - option-chain historical data affidabile;
  - backtest opzioni con bid/ask, greeks, assignment, margin;
  - stress test 2018, 2020, 2022 realistici;
  - confronto contro benchmark PUT/PUTW;
  - decisione broker/options adapter.

Per Claude Code:

- Inserire guardrail: S2 disabled by default oppure allocation 0 finche `milestone_d_pass` non e true.
- Se resta enabled, limitare S2 a dry-run/paper e documentarlo.
- Separare chiaramente `S2ProxyStrategy` da futura `S2OptionsStrategy`.

---

## Analisi S3: Cross-Sectional Residual Momentum

### Disegno nei documenti

S3 nasce come equity cross-sectional momentum:

- universo azionario;
- 12-1 momentum;
- beta adjustment vs SPY;
- long top decile;
- exclude/short bottom decile;
- allocation originale 20%, poi demossa.

Il documento v2 dice:

```text
S3 demoted a R&D sleeve.
Gate 3 e 5 FAIL.
OOS Sharpe 0.15.
CV = 2.05.
S3 esclusa dal portfolio live.
```

### Implementazione reale

File principali:

- `src/strategies/s3/strategy.py`
- `src/strategies/s3/signal.py`

Config reale:

```python
lookback = 252
beta_window = 252
n_deciles = 10
target_vol = 0.10
max_weight = 0.20
long_decile = 10
short_decile = 1
rebalance_frequency = MONTHLY
```

Signal:

```text
residual_momentum = stock_momentum - beta * market_momentum
```

Ranking:

```text
rank ascending by residual_momentum
decile = ceil(rank * n_deciles / n_valid)
```

Portfolio:

- long top decile;
- short bottom decile se `short_decile` non e None.

### Issue tecnica importante: possibile lookahead nel sizing

In `src/strategies/s3/strategy.py`:

```python
self._vol = daily_rets.rolling(config.beta_window).std().iloc[-1] * np.sqrt(252)
```

Questa volatilita e calcolata una volta usando l'ultimo valore della serie completa.

Poi `compute_target_weights()` la usa per tutte le date storiche:

```python
vol = self._vol.get(ticker, np.nan)
raw_w = cfg.target_vol / vol
```

Rischio:

- Nei backtest storici, il sizing di date passate puo usare informazioni future.
- Anche se il segnale non fa lookahead, il sizing puo farlo.
- Questo rende il backtest potenzialmente troppo ottimistico.

Dato che S3 fallisce comunque i gate, il problema rafforza la decisione di tenerla fuori dal live.

### Evidenza da backtest

`reports/s3_backtest/summary.json`:

```text
oos_sharpe = 0.1483
milestone_c_pass = false
n_windows = 21
mean_sharpe = 0.0108
worst_drawdown = -0.4603
pct_windows_positive = 0.3333
```

Gate report:

```text
Gate 1 significance: pass
Gate 2 walk-forward: pass
Gate 3 robustness: fail
  cv = 2.0543
  min_sharpe = -0.0268

Gate 4 regime: pass
Gate 5 stress: fail
  cumulative_return = -0.1007
  sharpe = -5.8171
```

### Valutazione S3

La demozione a R&D e corretta.

Punti positivi:

- Razionale accademico noto.
- Codice signal abbastanza chiaro.
- Beta adjustment sensato.

Punti deboli:

- OOS debole.
- Robustezza pessima.
- Stress fail.
- Drawdown worst -46%.
- Possibile lookahead sizing.
- Short bottom decile puo essere incompatibile con broker/risk policy retail.

Raccomandazione:

- Non riattivare S3.
- Mettere `enabled=False` se mai venisse aggiunta al registry.
- Sistemare sizing lookahead prima di qualsiasi nuovo backtest.
- Valutare long-only top decile/exclude bottom, non short, se si riapre la ricerca.

---

## Analisi S4: News-driven / LLM sentiment tactical

### Disegno nei documenti

S4 e stata ridimensionata nel documento v2:

- da core del sistema a R&D sleeve;
- peso target 10%;
- edge incerto;
- richiede paper trading prolungato;
- passaggio da threshold strategy a cross-sectional ranking;
- top 5 long;
- equal-weight dentro bucket 10%;
- horizon 1-5 giorni;
- decay study come prerequisito.

Questo e un ridimensionamento ragionevole: il segnale news/LLM e potenzialmente interessante, ma il rischio di decay e data-mining e alto.

### Implementazione S4 nuova

File:

- `src/strategies/s4/config.py`
- `src/strategies/s4/ranking.py`
- `src/strategies/s4/strategy.py`

Config:

```python
n_top = 5
bucket_pct = 0.10
min_confidence = 0.3
min_score = 0.1
min_stocks = 3
signals_lookback_hours = 4
rebalance_frequency = WEEKLY
```

Ranking:

```text
1. Deduplica per simbolo, tenendo il segnale piu recente.
2. Filtra confidence < 0.3.
3. Filtra abs(score) < 0.1.
4. Calcola strength = score * confidence.
5. Tiene solo strength positiva.
6. Ordina descending.
7. Seleziona top n_top.
8. Pesa equal weight dentro bucket_pct.
```

Quindi S4 nuova e:

```text
cross-sectional, long-only, top-N, equal-weight, weekly rebalance
```

### Implementazione S4 legacy/direct

File:

- `src/workers/execution.py`

Questa e la versione threshold/EMA intraday:

```text
score > 0.3
fresh signal <= 30 min
fallback_used == False
price > EMA20
notional = portfolio_value * 10% * regime_multiplier
max cycle notional = 20%
stop loss = 2%
```

Questa non e la stessa strategia di `src/strategies/s4`.

### Divergenze doc/codice

| Tema | Documento v2 | Nuovo S4 code | Legacy execution |
|---|---|---|---|
| Metodo | Cross-sectional rank | Si | No, threshold |
| Peso | 10% | `bucket_pct=0.10` | `MAX_POSITION_PCT=0.10` per trade |
| Horizon | 1-5 giorni | weekly rebalance, no explicit max holding days | intraday cycle, stop-loss |
| Source signals | aggregator | PostgreSQL in scheduler | Redis |
| EMA filter | mantenere in vecchia pipeline? | No | Si |
| Regime modulation | Si | Non evidente in S4 ranking | Si |
| Validation | richiesta | non trovata come report dedicato | vecchi backtest/report vari |

### Evidenza da backtest

Non ho trovato un report dedicato equivalente a:

```text
reports/s4_backtest/summary.json
reports/s4_backtest/gate_report.json
```

Ci sono report generici:

- `reports/backtest_gkg-dec25-v1.json`
- `reports/backtest_gkg-nov25-v1.json`
- `reports/backtest_alpaca-smallmid-2506.json`
- altri `backtest_dry-*`

Ma non risultano chiaramente equivalenti ai gate S1/S2/S3.

Inoltre bisogna verificare se eventuali backtest S4 usano segnali reali oppure synthetic/fallback. Se ci sono synthetic signals, non sono una prova sufficiente per promuovere allocation.

### Valutazione S4

S4 e promettente come overlay, ma non come core.

Punti positivi:

- Il passaggio a cross-sectional ranking e migliore del threshold impulsivo.
- Bucket 10% e coerente con il rischio del segnale.
- `min_confidence` e `min_score` evitano segnali troppo deboli.
- Top-N equal-weight e semplice e robusto.

Punti deboli:

- Non vedo gate report solido.
- Due implementazioni operative divergenti.
- Registry assegna 30%, troppo alto rispetto al documento v2.
- Nuovo S4 non sembra applicare regime modulation.
- Nuovo S4 non implementa esplicitamente max holding 5 giorni.
- Legacy S4 puo ancora mandare ordini ogni 15 minuti.
- Redis vs PostgreSQL come source of truth non e chiarito.

Raccomandazione:

- Tenere S4 a massimo 10% finche non passa gate dedicati.
- Disabilitare legacy execution oppure integrarlo nel portfolio orchestrator.
- Aggiungere backtest/gate report S4 comparabile a S1/S2/S3.
- Implementare max holding days e signal flip exit se il documento v2 resta la fonte di verita.
- Aggiungere decay monitor specifico S4 basato su IC/hit-rate per horizon 1d/3d/5d.

---

## Vol targeting

File:

- `src/portfolio/vol_targeting.py`
- `src/workers/portfolio_scheduler.py`
- `src/portfolio/orchestrator.py`

Il documento dice che il portfolio usa vol targeting a 10%.

Nel portfolio scheduler viene creato:

```python
PortfolioVolTargeter(target_vol=0.10)
```

Pero `orchestrator.run_cycle()` viene chiamato senza `strategy_returns`:

```python
result = orchestrator.run_cycle(
    ts=ts, data_replay=data_replay, portfolio=portfolio, market=market,
)
```

Nel codice orchestrator:

```python
if self._vol_targeter is not None and combined and strategy_returns:
    estimated_vol = self._vol_targeter.estimate_vol(strategy_returns)
    scale = self._vol_targeter.compute_scale(estimated_vol)
    combined = self._vol_targeter.scale_orders(combined, scale)
```

Quindi in live/paper scheduler il vol targeting e istanziato ma non applicato, perche mancano i ritorni strategia.

Rischio:

- I documenti promettono portfolio vol target, ma il live path non lo applica.
- L'exposure reale dipende da target weights, constraints e cash, non da vol overlay.

Raccomandazione:

- O alimentare `strategy_returns` dal DB/reporting.
- Oppure disabilitare/commentare vol targeter nel live path finche non e operativo.
- Aggiungere logging esplicito: `vol_targeting_applied: true/false`.

---

## Constraint enforcement

La documentazione cita:

- max single asset;
- max strategy exposure;
- max portfolio exposure;
- max sector exposure;
- max correlation cluster.

Da verificare nel codice `src/portfolio/constraints.py`:

- se tutte queste constraint sono davvero implementate;
- se ricevono exposure per strategia dopo che gli ordini sono marcati come `strategy_id="merged"`;
- se l'orchestrator perde informazione di sleeve originaria.

Punto da investigare:

Gli ordini finali creati dall'orchestrator hanno:

```python
strategy_id="merged"
allocation_weight=target_wt
```

Se il constraint enforcer vuole limitare per-strategy exposure, potrebbe non sapere piu quale strategia ha originato il peso.

Raccomandazione:

- Verificare se `ConstraintEnforcer.enforce()` usa `strategy_id`.
- Se serve controllo per sleeve, mantenere provenance:
  - contributi per simbolo per strategia;
  - target exposure per sleeve;
  - ordini merged ma con metadata esteso.

---

## Tabella di coerenza allocation

| Fonte | S1 | S2 | S3 | S4 | Cash | Note |
|---|---:|---:|---:|---:|---:|---|
| `docs/alembic_v2/01_strategy_design.md` | 40% | 30% | 0% | 10% | 20% | Fonte piu prudente |
| `src/strategies/registry.py` | 50% | 20% | assente | 30% | 0% implicito | S4 troppo alta |
| `src/strategies/s4/config.py` | n/a | n/a | n/a | bucket 10% | n/a | Coerente con doc v2 |
| `src/strategies/s2/config.py` | n/a | collateral 20% | n/a | n/a | n/a | Coerente col registry, non col doc v2 |
| `docs/strategies.md` portfolio example | 50% | 30% | n/a | 20% | n/a | Ulteriore variante |

Conclusione:

Non esiste una fonte unica e affidabile per le allocation.

Raccomandazione:

- Creare un file config esplicito, per esempio `config/strategies.yaml`.
- Il registry deve leggere da li.
- I documenti devono dichiarare che quella e la source of truth.
- Le allocation devono essere validate all'avvio:
  - somma <= 1.0;
  - S3 disabled;
  - S4 <= 0.10 finche research status;
  - S2 disabled o paper-only finche milestone non passa.

---

## Stato report e validazione

| Strategia | Report | OOS Sharpe | Gate principali | Stato |
|---|---|---:|---|---|
| S1 | `reports/s1_backtest/*` | 0.5128 | Tutti pass | Validata relativamente |
| S2 | `reports/s2_backtest/*` | -0.2460 | 1/2/3/4 fail | Non validata |
| S2 v2 | `reports/s2_backtest_v2/*` | -0.5522 | 1/2/3/4 fail | Non validata |
| S3 | `reports/s3_backtest/*` | 0.1483 | 3/5 fail | Esclusa correttamente |
| S4 | report gate dedicato non trovato | n/d | n/d | Non validata formalmente |

Interpretazione:

- S1 e l'unico vero candidato core.
- S2 e S4 non dovrebbero avere allocation alta.
- S3 non dovrebbe essere live.

---

## Rischi principali ordinati per priorita

### P0 - Allocation per strategia potenzialmente annullata dall'orchestrator

File: `src/portfolio/orchestrator.py`

Il normalize per simbolo rischia di cancellare l'allocation pct.

Impatto:

- S4 bucket/registry puo non limitare il capitale effettivo come previsto.
- Le sleeve allocation non sono affidabili.
- I backtest del portfolio orchestrator possono essere concettualmente sbagliati.

Azione:

- Cambiare merge logic in somma pesata.
- Aggiungere test.

### P0 - Due execution engine attivi

File:

- `src/workers/celery_app.py`
- `src/workers/execution.py`
- `src/workers/portfolio_scheduler.py`

Impatto:

- Possibile doppio ordine.
- Governance del rischio frammentata.
- Strategie diverse competono per lo stesso capitale.

Azione:

- Decidere motore autoritativo.
- Disabilitare legacy execution o integrarla nel portfolio orchestrator.

### P1 - Registry non coerente con investment design

File:

- `src/strategies/registry.py`
- `docs/alembic_v2/01_strategy_design.md`

Impatto:

- S4 sovrappesata.
- S2/S1 non allineate.
- Cash residual assente.

Azione:

- Creare source of truth config.
- Allineare default a policy prudente.

### P1 - S2 abilitata nonostante backtest falliti

File:

- `src/strategies/registry.py`
- `reports/s2_backtest_v2/summary.json`

Impatto:

- Sleeve income puo generare exposure reale senza validazione.

Azione:

- Disable by default o paper-only.
- Bloccare promotion finche milestone/gate non passano.

### P1 - S4 allocation registry troppo alta e validazione incompleta

File:

- `src/strategies/registry.py`
- `src/strategies/s4/config.py`

Impatto:

- Alpha incerto puo pesare 30%.

Azione:

- Cap S4 a 10%.
- Aggiungere gate report.

### P1 - Vol targeting non applicato nel live scheduler

File:

- `src/workers/portfolio_scheduler.py`
- `src/portfolio/orchestrator.py`

Impatto:

- Target vol documentato ma non effettivo.

Azione:

- Passare `strategy_returns` o loggare disabled.

### P2 - S1 documentazione non allineata al codice

File:

- `docs/strategies.md`
- `src/strategies/s1/signal.py`

Impatto:

- Confusione research.
- Difficile confrontare risultati con letteratura.

Azione:

- Aggiornare docs o implementare variante 12-1.

### P2 - S3 possible lookahead nel sizing

File:

- `src/strategies/s3/strategy.py`

Impatto:

- Backtest S3 non pienamente affidabile.

Azione:

- Usare rolling vol as-of date.
- Ripetere backtest solo se S3 torna in ricerca attiva.

---

## Target investment policy raccomandata

Finche le issue P0/P1 non sono risolte:

```text
Live/paper deployed:
  S1: 40-50%
  S2: 0%
  S3: 0%
  S4: 0-10%
  Cash: resto
```

Policy prudente consigliata:

```yaml
strategies:
  S1:
    enabled: true
    allocation_pct: 0.50
    mode: paper_or_live
    reason: only validated core sleeve

  S2:
    enabled: false
    allocation_pct: 0.00
    mode: research
    reason: failed OOS gates, proxy implementation

  S3:
    enabled: false
    allocation_pct: 0.00
    mode: research
    reason: failed robustness/stress, possible sizing lookahead

  S4:
    enabled: true
    allocation_pct: 0.10
    mode: paper_only_or_small_overlay
    reason: alpha uncertain, no dedicated gate report found

cash_residual: 0.40
```

Se si vuole seguire esattamente il documento v2:

```yaml
S1: 0.40
S2: 0.30
S3: 0.00
S4: 0.10
cash: 0.20
```

Pero questa allocation include S2 al 30%, che oggi non e supportata dai backtest. Dal punto di vista engineering/research io non la renderei default live finche S2 non viene rifatta o validata.

---

## Brief operativo per Claude Code

### Obiettivo

Rendere Alembic coerente come sistema multi-strategy prima di fare ulteriore tuning alpha.

### Principio guida

Le allocation di strategia devono controllare capitale reale. Una sleeve R&D non deve poter diventare grande per effetto di default, doppio scheduler o bug di normalizzazione.

### Task 1 - Fix allocation merge nel PortfolioOrchestrator

File:

- `src/portfolio/orchestrator.py`
- test esistenti sotto `tests/portfolio/` o nuovo test dedicato.

Richiesta:

- Rimuovere la normalizzazione per simbolo `_weight_alloc_sum`.
- Mergiare come somma pesata:

```python
merged_weights[sym] += strategy_target_weight * strategy_allocation_pct
```

- Aggiungere test:
  - single-strategy symbol must be scaled by allocation;
  - overlapping symbol must sum capital contributions;
  - S4 10% bucket with 5 names produces 2% inside S4, 0.2% portfolio if allocation_pct=10%, oppure chiarire se `bucket_pct` e gia portfolio-level.

Nota importante:

C'e una ambiguita S4:

- `S4Config.bucket_pct=0.10` sembra gia portfolio-level.
- `StrategyRegistry.S4 allocation_pct` scala ancora S4.

Claude deve decidere una semantica unica:

Opzione A:

- Ogni strategia produce weights interni alla sleeve.
- Registry allocation scala tutto.
- Allora S4 `bucket_pct` dovrebbe essere 1.0 dentro la sleeve, o i pesi S4 dovrebbero sommare a 1.0.

Opzione B:

- Ogni strategia produce portfolio-level target weights.
- Registry allocation non deve scalare S4.
- Ma allora il registry perde il ruolo di capital allocation.

Raccomandazione:

Usare Opzione A per tutte le strategie:

- strategia produce sleeve-local weights;
- orchestrator applica allocation;
- constraint enforcer limita exposure totale.

Questo implica refactor S1/S2/S4 semantics.

Soluzione intermedia meno invasiva:

- Documentare che `compute_target_weights()` restituisce portfolio-level weights.
- Eliminare allocation_pct dal merge o usarlo solo come cap.

Ma questa seconda opzione contraddice i documenti.

### Task 2 - Decidere execution engine autoritativo

File:

- `src/workers/celery_app.py`
- `src/workers/execution.py`
- `src/workers/portfolio_scheduler.py`

Richiesta:

- Non schedulare contemporaneamente `run-execution` e `portfolio-cycle` in modalita live.
- Aggiungere config flag, per esempio:

```yaml
execution:
  engine: portfolio
```

Valori:

```text
portfolio
legacy_sentiment
dry_run
disabled
```

Comportamento:

- se `engine=portfolio`, solo `portfolio-cycle` invia ordini;
- se `engine=legacy_sentiment`, solo `run-execution` invia ordini;
- se `dry_run`, entrambi possono calcolare ma nessuno invia;
- se `disabled`, nessuno invia.

### Task 3 - Creare source of truth per strategy allocation

Nuovo file consigliato:

- `config/strategies.yaml`

Esempio:

```yaml
strategies:
  S1:
    enabled: true
    allocation_pct: 0.50
    mode: live
  S2:
    enabled: false
    allocation_pct: 0.00
    mode: research
  S3:
    enabled: false
    allocation_pct: 0.00
    mode: research
  S4:
    enabled: true
    allocation_pct: 0.10
    mode: paper
cash_residual_min: 0.40
```

Modifiche:

- `StrategyRegistry` legge questo file.
- Default hardcoded usati solo fallback safe.
- Validazione:
  - somma allocation enabled <= 1.0;
  - S4 > 0.10 richiede explicit override;
  - S2 enabled richiede explicit override finche gate fail;
  - S3 enabled richiede explicit override.

### Task 4 - Guardrail research/live

Obiettivo:

Impedire che strategie non validate siano attive per errore.

Regole consigliate:

```text
S1 allowed live if latest report milestone pass true.
S2 live blocked unless milestone_d_pass true.
S3 live blocked unless milestone_c_pass true and no lookahead issue.
S4 live allocation >10% blocked unless dedicated S4 gate report pass.
```

Implementazione possibile:

- semplice validator su startup;
- legge `reports/*/summary.json`;
- se manca report, warning o block in live mode;
- in paper mode warning.

### Task 5 - Allineare documentazione S1

File:

- `docs/strategies.md`
- `docs/alembic_v2/01_strategy_design.md`

Decidere:

1. Aggiornare docs al codice multi-lookback cross-sectional z-score.
2. Oppure modificare codice verso 12-1 TSMOM canonico.

Raccomandazione:

Per ora aggiornare docs al codice, perche il codice ha backtest positivo.

### Task 6 - S2 research boundary

File:

- `src/strategies/s2/strategy.py`
- `src/strategies/registry.py`
- docs S2.

Azioni:

- Rinominare/documentare S2 attuale come proxy.
- Non chiamarla "tradable short put" nel live path.
- Disabilitare di default.
- Creare roadmap per vera options strategy:
  - historical option chain;
  - pricing/greeks;
  - margin model;
  - assignment;
  - slippage/bid-ask;
  - IBKR adapter.

### Task 7 - S4 validation

File:

- `src/strategies/s4/*`
- backtest scripts eventuali.

Azioni:

- Creare `reports/s4_backtest/summary.json` e `gate_report.json`.
- Usare segnali reali storici, non synthetic, per report ufficiale.
- Testare horizon 1d/3d/5d.
- Misurare IC, ICIR, hit rate, turnover, slippage sensitivity.
- Separare:
  - S4 ranking strategy;
  - S4 legacy threshold strategy.

### Task 8 - Vol targeting live

File:

- `src/workers/portfolio_scheduler.py`
- `src/portfolio/vol_targeting.py`

Azioni:

- Passare `strategy_returns` reali all'orchestrator.
- Oppure loggare `vol_targeting_applied=false`.
- Aggiungere test/log nel cycle result.

---

## Domande aperte da risolvere prima del refactor

1. I target weights prodotti dalle strategie sono sleeve-local o portfolio-level?
2. `S4Config.bucket_pct=0.10` rappresenta 10% del portfolio totale o 10% della sleeve S4?
3. Il motore legacy `src/workers/execution.py` e ancora parte del prodotto o va dismesso?
4. S2 deve essere paper/live adesso o solo research?
5. La fonte ufficiale delle allocation e `docs/alembic_v2`, `registry.py`, oppure un nuovo config file?
6. Il portfolio live deve mantenere cash residual esplicito?
7. Il broker target per S2 e davvero IBKR, oppure S2 deve restare equity proxy?

---

## Raccomandazione finale

Alembic ha una buona architettura concettuale, ma oggi il rischio non e tanto "la strategia alpha non funziona"; il rischio piu grosso e che il sistema non applichi davvero la policy di capitale che i documenti descrivono.

Ordine corretto dei lavori:

1. Fixare portfolio construction e allocation semantics.
2. Spegnere il doppio execution path.
3. Rendere `config/strategies.yaml` la source of truth.
4. Mettere guardrail live/research.
5. Solo dopo, fare tuning e nuova ricerca su S2/S4.

Strategia consigliata nel frattempo:

```text
S1 = core
S4 = piccolo overlay paper/10%
S2 = research
S3 = disabled
cash = residuale esplicito
```

Questo mantiene vivo il progetto senza sovraesporlo alle parti meno validate.
