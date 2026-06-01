# 01 — Strategy design

Specifiche dettagliate delle 4 strategie. Ogni strategia ha: razionale economico, letteratura di riferimento, definizione precisa del signal, sizing, edge atteso, modalità di degradazione, parametri.

---

## S1 — Time-Series Momentum Multi-Asset (CORE, 40%)

### Razionale economico

Asset che hanno performato bene negli ultimi mesi tendono a continuare a performare bene (e viceversa) su orizzonti di 1-12 mesi. Il fenomeno è documentato su:
- 100+ anni di dati equity (Dow, FTSE, ecc.)
- Cross-asset: equity, bond, commodity, currency
- Cross-regime: regge in bull market, bear market, crisi

Spiegazioni accademiche:
- **Under-reaction**: gli investitori prezzano gradualmente le nuove informazioni
- **Risk-based**: trend è proxy di compensation per tail risk
- **Behavioral**: anchoring, disposition effect, herding

Persistenza attesa: alta. È documentato dal 1900, sopravvissuto a 100 anni di "arbitraggio".

### Letteratura di riferimento

**Implementazione canonica**:
- Moskowitz, Ooi, Pedersen (2012). "Time series momentum". *Journal of Financial Economics*.
- Asness, Moskowitz, Pedersen (2013). "Value and momentum everywhere". *Journal of Finance*.
- Hurst, Ooi, Pedersen (AQR, 2017). "A century of evidence on trend-following investing".

**Critiche e robustezza**:
- Goyal, Jegadeesh (2018). "Cross-sectional and time-series tests of return predictability".
- Da leggere per capire i casi in cui momentum fallisce (es. periodi di alta correlazione, gennaio effect).

### Universo

15 ETF cross-asset (UCITS armonizzati Italia dove possibile, altrimenti US-listed):

| Asset class | Ticker (US-listed) | Alternativa UCITS |
|-------------|---------------------|---------------------|
| US Equity Large | SPY | CSPX |
| US Equity Tech | QQQ | EQQQ |
| US Equity Small | IWM | ZPRR |
| Developed Intl Equity | VEA | IWDA |
| EM Equity | VWO | EIMI |
| Japan Equity | EWJ | CSJP |
| UST Long (20+y) | TLT | IDTL |
| UST Intermediate (7-10y) | IEF | IBTM |
| UST Short (1-3y) | SHY | IBTS |
| IG Credit | LQD | IBCX |
| HY Credit | HYG | IHYG |
| Gold | GLD | SGLN |
| Broad Commodity | DBC | ICOM |
| US REITs | VNQ | IUSP |
| TIPS | TIP | ITPS |

**Decisione di universo**: per backtest e paper trading, usare ticker US-listed (Yahoo Finance free data, copertura 20+ anni). Per live trading eventuale in Italia, swap su UCITS equivalenti.

### Signal

Per ogni asset ad ogni timestamp di rebalance:

```
1. Calcola 12-1 momentum: log(P_t-21 / P_t-252)
   (12 mesi escluso ultimo mese, in giorni di trading)
   
2. Calcola realized vol: σ_t = std(daily_returns_last_60d) * sqrt(252)

3. Risk-adjusted signal: s_i = (12-1 momentum) / σ_i
```

### Position sizing

Inverse-vol weighting:

```
4. Per ogni asset i:
   raw_weight_i = sign(s_i) * (vol_target_per_asset / σ_i)
   
   dove vol_target_per_asset = total_vol_target / sqrt(n_active_assets)
   
5. Cap per asset: |raw_weight_i| ≤ max_leverage_per_asset (default 1.5)

6. Aggregazione: portfolio_vol_target / portfolio_realized_vol → scale factor

7. Final weights: raw_weights * scale_factor, con cap globale max gross 2.0
```

### Parametri (default, configurabili)

```yaml
s1_time_series_momentum:
  universe: [SPY, QQQ, IWM, VEA, VWO, EWJ, TLT, IEF, SHY, LQD, HYG, GLD, DBC, VNQ, TIP]
  lookback_long_days: 252
  lookback_skip_days: 21
  vol_window_days: 60
  total_vol_target: 0.10
  max_leverage_per_asset: 1.5
  max_gross_exposure: 2.0
  rebalance_frequency: monthly  # primo business day
  signal_threshold: 0.0  # long se >0, short se <0, flat se troppo vicino a 0
  short_enabled: false  # iniziare long-only, abilitare short solo dopo IBKR setup
  min_holding_days: 21  # evita whipsaw
```

### Edge atteso

- Sharpe storico (US data, 1985-2024): 0.7-0.9
- Sharpe OOS atteso (post-2020): 0.5-0.7
- Max drawdown: 10-18% (peggior periodo storico: 2018-2020 trend reversal)
- Annual return atteso a vol 10%: 6-8%
- **Crisis alpha**: tipicamente positivo in 2008, 2020 marzo, 2022 (proprio perché segue il trend negativo equity)

### Quando S1 sotto-performa (atteso, non bug)

- **Choppy/range-bound markets**: late 2015, gran parte del 2019, periodi di consolidamento
- **Sharp trend reversal**: gennaio 2018, dicembre 2018
- **Forte mean reversion intraday/intraweek**: poco impatto perché ribilanciamo mensile

Critical: NON modificare parametri durante periodi di sotto-performance. La disciplina sui parametri **è l'edge**.

### Decay monitor specifico

- IC mensile (signal vs forward 1-month return per asset, Spearman)
- Rolling 24-month Sharpe della strategia
- Alert se: rolling Sharpe < -0.5 per 6 mesi, oppure rolling IC negativo per 12 mesi consecutivi

### Implementazione pratica

**Stima effort**: 2-3 settimane part-time

**Componenti**:
- `strategies/s1_ts_momentum/signal.py` — calcolo signal
- `strategies/s1_ts_momentum/sizing.py` — inverse-vol sizing
- `strategies/s1_ts_momentum/strategy.py` — orchestrazione, output target weights
- `strategies/s1_ts_momentum/config.yaml` — parametri
- `tests/test_s1_signal.py` — test su data sintetica + golden examples

**Output del modulo**: `dict[ticker, target_weight]` calcolato as_of timestamp.

---

## S2 — Volatility Risk Premium Harvesting (INCOME, 30%)

### Razionale economico

Le opzioni put hanno implied volatility sistematicamente più alta della volatilità realizzata. Storicamente:
- IV mediana S&P 500 (VIX) ~ 17-18%
- Realized vol S&P 500 ~ 14-15%
- Spread ~ 3-4 punti vol annualizzati = **fonte di income strutturale**

Perché esiste:
- **Compensation per tail risk**: chi vende protezione richiede premio per evento estremo
- **Insurance demand**: istituzionali comprano put per mandato/risk policy
- **Crash phobia**: dopo 1987/2008/2020, mercato sovrastima cronicamente frequenza disastri
- **Volatility skew**: put OTM ancora più sovrastimate di put ATM

Il VRP è il **fattore più persistente** della letteratura quant moderna. Esistono ETF basati su questo (PUTW, JEPI, JEPQ) con AUM combined > 50B$.

### Letteratura di riferimento

- Bollerslev, Tauchen, Zhou (2009). "Expected stock returns and variance risk premia". *Review of Financial Studies*.
- Israelov, Klein (AQR, 2016). "Risk and return of equity index collar strategies".
- Whaley (2002). "Return and risk of CBOE buy write monthly index".
- CBOE — "PUT Index Methodology" (paper pubblico). Replica esatta di una strategia put-write.
- Bondarenko (2014). "Why are put options so expensive?".

### Strategia base: Cash-Secured Short Put su SPY

**Mechanica**:

```
Setup mensile (terzo venerdì):
1. Identifica put SPY scadenza ~30-45 giorni con delta vicino a -0.20
   (probabilità ITM ~ 20%)
2. Vendi 1 contratto per ogni X di capitale collaterale richiesto
   (100 × strike × num_contracts deve essere ≤ cash disponibile)
3. Mantieni fino a:
   a) Scadenza (chiude worthless se SPY > strike): max profit
   b) Stop-loss: se loss su position > 2× premium received: chiudi
   c) Profit target: se 50% del premium catturato: chiudi e riposiziona
4. A scadenza/chiusura, riapri nuova posizione
```

### Refinement con il sistema Alembic

Il valore aggiunto di Alembic vs un naive short-put è in 3 punti:

**1. Regime modulation (riusa regime_classifier esistente)**

```yaml
regime_modulation:
  RISK_ON:    full_size      # 100% allocation
  GOLDILOCKS: full_size      # 100%
  RISK_OFF:   half_size      # 50% allocation, delta -0.15 invece di -0.20
  STRESS:    no_new_positions  # liquida esistenti se in profit, hold se in loss
```

In stress regime, il VRP esplode (favorisce vendita) ma la tail risk pure. **Salire o scendere?** La letteratura mostra che vendere put in regime stressato è altamente profittevole **se sopravvivi**. Per un retail, "sopravvivere" non è garantito. Conservative: ridurre size in stress.

**2. News-based event filter (riusa news ingestion + LLM ensemble)**

```yaml
event_filter:
  block_new_positions_if:
    - llm_aggregated_sentiment_spy < -0.5  # forte sentiment negativo sull'indice
    - days_to_major_event < 7  # FOMC, NFP, ECB se calendarizzato
    - vix_term_structure_inversion: true  # VIX9D > VIX3M
    - cnn_fear_greed_index < 20  # opzionale, da scrapeare
```

**3. Volatility-aware sizing**

Vendi quando IV ricco rispetto a realized, ridui quando IV è cheap.

```
vrp_estimate = VIX / realized_vol_20d - 1
if vrp_estimate < 0.10:  # IV non così ricco
    size_multiplier = 0.5
elif vrp_estimate > 0.50:  # IV molto ricco
    size_multiplier = 1.2
else:
    size_multiplier = 1.0
```

### Parametri

```yaml
s2_vrp:
  underlying: SPY
  target_delta: -0.20  # delta target del put venduto
  delta_tolerance: 0.05
  target_dte: 30-45  # days to expiration
  profit_target_pct: 0.5  # chiudi se hai catturato 50% del premio
  stop_loss_multiplier: 2.0  # chiudi se loss > 2x premium received
  max_capital_allocation: 0.30  # max 30% del portafoglio in collaterale put
  rebalance_check_frequency: daily
  position_reset_frequency: monthly  # default, può chiudere prima per target/stop
  regime_modulation:
    enabled: true
    risk_off_multiplier: 0.5
    stress_block_new: true
  event_filter:
    enabled: true
    sentiment_threshold: -0.5
    block_days_before_major_event: 7
```

### Edge atteso

- Sharpe storico (CBOE PUT index 1986-2024): ~0.85
- Sharpe atteso netto (con Alembic overlay): 0.9-1.1
- Annual return atteso: 7-10% con vol ~9%
- Max drawdown atteso: 15-25% (e.g. March 2020 fu -20% sull'indice PUT)
- Skewness: fortemente negativa (perdi raramente, ma forte quando perdi — è il "premio assicurazione")

### Quando S2 fallisce in modo serio

- **Crash improvviso e severo**: October 1987, March 2020 (settimana 9-13 marzo)
- **Vol cluster con gap up overnight**: gennaio 2018 weekend, agosto 2015
- **VIX > 50 sostenuto**: tipicamente significa drawdown 20-30% per la strategia

La strategia **DEVE** sopravvivere a questi eventi senza blow-up. Per questo il stop-loss meccanico e regime modulation sono critici.

### Infrastruttura tecnica richiesta

**Broker**: IBKR (Alpaca non offre opzioni in IT)
**Data**: option chain real-time, almeno snapshot end-of-day per backtest
**Backtest**: deve modellare bid-ask spread opzioni (significativi: 0.5-2 punti su SPY), assignment risk, early exercise (raro su SPY ma possibile su SPX cash-settled)

### Implementazione pratica

**Stima effort**: 6-8 settimane part-time (è la strategia più complessa tecnicamente)

**Componenti nuovi**:
- `strategies/s2_vrp/option_chain.py` — ingestion + caching chain options
- `strategies/s2_vrp/pricing.py` — Black-Scholes baseline + greeks
- `strategies/s2_vrp/signal.py` — quale put vendere, quando chiudere
- `strategies/s2_vrp/risk.py` — stop-loss meccanico, position monitoring
- `strategies/s2_vrp/regime_overlay.py` — riuso regime classifier
- `strategies/s2_vrp/event_filter.py` — riuso LLM ensemble per news filter
- `brokers/ibkr_options.py` — IBKR adapter per opzioni

### Note importanti

**Test su small size prima**: anche in paper trading, simula con 1 contratto solo. Le greche sotto stress sono non-lineari e i test su backtest non catturano tutto.

**Assignment risk**: SPY è american-style. In paper su Alpaca questa logica non c'è, ma in real con IBKR sì. Modellare assignment in backtest.

**Tassazione**: opzioni in Italia sono tassate al 26% sui guadagni netti. Frequenza alta di trade = molti report. Considerare nel design del tax engine futuro.

---

## S3 — Cross-Sectional Momentum Equity (TILT, 20%)

### Razionale economico

Dentro un universo di azioni, quelle che hanno performato meglio nei mesi recenti tendono a continuare. È il "momentum" classico di Jegadeesh-Titman, documentato dal 1993 e ancora vivo (con decay).

Differenza da S1: S1 è **time-series** (compri se l'asset è in trend up, vendi se in trend down). S3 è **cross-sectional** (compri quelli che sono migliori degli altri, vendi/escludi quelli peggiori).

### Letteratura di riferimento

- Jegadeesh, Titman (1993). "Returns to buying winners and selling losers". *Journal of Finance*. Il paper fondazionale.
- Asness, Frazzini, Israel, Moskowitz (2014). "Fact, fiction and momentum investing". Risposta alle critiche.
- Fama, French (2012). "Size, value and momentum in international stock returns".

### Universe

L'universe corrente di Alembic (72 ticker US large-cap + sector ETF + ADR) è perfetto per questa strategia. Non serve ampliarlo.

**Filtri di liquidità**:
- ADV (average daily volume) > 10M$ ultimi 60 giorni
- Price > 5$ (no penny stock)
- Market cap > 2B$

### Signal

```
1. Per ogni asset i nell'universo, calcola:
   momentum_12_1 = log(P_t-21 / P_t-252)
   
2. Aggiusta per beta (per evitare di sovrappesare semplicemente quello che si è mosso di più):
   beta_i = covariance(returns_i, SPY) / var(SPY)  [rolling 252d]
   residual_momentum = momentum_12_1 - beta_i * SPY_momentum_12_1

3. Cross-sectional ranking per residual_momentum
```

### Position construction

```
4. Long: top decile (top 10% per residual momentum)
5. Excluded: bottom decile (questi mai posseduti, e venduti se in portfolio)
6. Middle 80%: no action

7. Within longs:
   - Equal weight (più robusto di market-cap weight in OOS)
   - Risk-adjusted: weight_i = 1 / σ_i, poi normalizza
```

### Parametri

```yaml
s3_xs_momentum:
  universe_source: existing_alembic_72  # riusa lista corrente
  liquidity_filter:
    min_adv_usd: 10_000_000
    min_price_usd: 5
    min_market_cap_usd: 2_000_000_000
  lookback_long_days: 252
  lookback_skip_days: 21
  beta_adjustment: true
  beta_window_days: 252
  top_decile_pct: 0.10
  bottom_decile_pct: 0.10
  weighting: inverse_vol  # alternatives: equal_weight, market_cap
  vol_window_days: 60
  rebalance_frequency: monthly
  max_position_weight: 0.10  # dentro il bucket S3
  short_enabled: false
```

### Edge atteso

- Sharpe storico (US large-cap 1927-2020): 0.5-0.7
- Sharpe ultimi 15 anni: 0.3-0.5 (momentum è in decay vs storico)
- Annual return atteso: 5-8% premium sopra benchmark
- Max drawdown: 25-40% (momentum crashes sono brutali: 2009, 2020 marzo, 2022 gennaio)

### Quando S3 fallisce (atteso)

- **Mean reversion violenta** post-crash: marzo-giugno 2009, aprile-luglio 2020
- **Style rotation**: value/momentum rotation come Q1 2021
- **High dispersion to low dispersion regime change**

### Implementazione pratica

**Stima effort**: 2-3 settimane part-time

Modulo simile a S1 ma con logica cross-sectional invece di per-asset.

---

## S4 — News-Driven Tactical (R&D SLEEVE, 10%)

### Razionale e ridimensionamento

Questa è la strategia attuale di Alembic, **riposizionata**:
- Era il "core" del sistema → diventa il **10% del portfolio**
- Era validata in produzione → diventa **R&D sleeve** con paper trading prolungato
- Era treated as alpha source → diventa **incremental tilt** sopra una base solida

Razionale del de-prioritization:
- L'edge LLM-based su news public è **incerto e in decay** (vedi analisi precedenti)
- Sample size attuale è insufficiente per claim statistico
- Implementazione corretta esistente, ma alpha mai dimostrato OOS

### Cosa cambia rispetto all'implementazione attuale

**Mantenere**:
- LLM ensemble (GLM, Qwen, Kimi, DeepSeek)
- News ingestion pipeline
- Aggregazione EWMA
- Regime classifier come modulatore
- Statistical rigor framework

**Cambiare** (importante):
1. **Da threshold (>0.30) a cross-sectional ranking**: come S3 ma su universe più piccolo e horizon più breve
2. **Da long-only impulsivo a long/exclude**: vendi i bottom, ma non shortare
3. **Cap rigoroso a 10% del portfolio totale**: anche se signal è forte, max 10%
4. **Horizon esplicito**: 1-5 giorni, non holding indefinito
5. **Decay study come prerequisito**: prima di passare a paper coordinato, valida che IC > 0 su 6+ mesi storici

### Signal

Riusa l'esistente aggregator, ma con questi cambi:

```
1. Per ogni ticker nell'universo, calcola aggregated_signal as today
2. Cross-sectional rank
3. Long top 5 ticker per signal score (subject to liquidity check)
4. Equal weight within S4 bucket, sized to fill exactly 10% of portfolio
5. Hold for max 5 trading days, then auto-close
6. Exit early se: signal flip negative, OR -3% stop on position
```

### Parametri

```yaml
s4_news_tactical:
  universe: alembic_72  # esistente
  signal_aggregation: ewma  # esistente
  half_life_hours: 24  # da decay study
  selection:
    method: cross_sectional_rank
    top_n_long: 5
    bottom_n_exclude: 5  # questi mai in portfolio
  position_sizing:
    method: equal_weight
    bucket_total_pct: 0.10  # 10% di portfolio totale
    max_position_pct: 0.025  # max 2.5% per nome
  exit:
    max_holding_days: 5
    signal_flip_threshold: -0.2
    stop_loss_pct: -0.03
  regime_modulation:
    stress_block_new: true
    risk_off_reduce_50pct: true
```

### Edge atteso

Onestamente: **incerto**. Range plausibile: Sharpe 0.0-0.6 OOS, con alta varianza.

Trattare come moonshot: se funziona, +1-2% sopra portfolio; se non funziona, perde poco perché è solo 10%.

### Promotion/demotion criteria

Dopo 6 mesi di paper trading dentro il sistema multi-strategia:

- **Promote a 20%** if: realized Sharpe > 0.7 OOS, IC > 0.03 stabile, contribution to total Sharpe > 0.15
- **Mantieni a 10%** if: realized Sharpe 0.3-0.7, IC > 0.01
- **Demote a 5%** if: realized Sharpe 0-0.3
- **Retire** if: Sharpe negativo per 6+ mesi, OR IC consistently 0

---

## Combinazione delle strategie

### Allocazione iniziale

| Strategia | Peso target | Note |
|-----------|------------|------|
| S1 | 40% | Core, più stabile |
| S2 | 30% | Income, decorrelato da S1 |
| S3 | 20% | Tilt equity, correlato a S1 ma su asset class diversa |
| S4 | 10% | R&D, alpha incerto |

### Razionale dell'allocazione

- **S1 + S3** sono entrambi momentum, ma su scale diverse (cross-asset vs cross-stock). Correlazione attesa ~0.3.
- **S2** ha correlation bassa con S1/S3 in regime normale (~0.1-0.2), ma sale a 0.5+ in crisi (problema noto del VRP).
- **S4** è semi-indipendente, alpha incerto, peso piccolo.

### Sharpe combinato atteso

Assumendo:
- Sharpe individuale (S1, S2, S3, S4): 0.7, 1.0, 0.6, 0.3 OOS
- Correlation matrix approssimativa:
  ```
       S1   S2   S3   S4
  S1  1.0  0.2  0.4  0.2
  S2  0.2  1.0  0.3  0.1
  S3  0.4  0.3  1.0  0.3
  S4  0.2  0.1  0.3  1.0
  ```

Sharpe combinato (formula portfolio): **~1.1-1.3**

Realistic OOS con costi e slippage: **0.8-1.1**

### Vincoli aggiuntivi cross-strategy

```yaml
portfolio_constraints:
  max_gross_exposure: 2.0  # somma assoluti pesi <= 2 (leverage modesto)
  max_net_exposure: 1.2  # se short attivo
  max_single_asset_across_strategies: 0.15  # se più strategie convergono su stesso asset
  max_sector_concentration: 0.35
  target_total_vol: 0.10  # 10% annualizzato
  vol_target_scaling: true
```

Dettagli implementazione del combiner in `03_backtest_framework.md`.
