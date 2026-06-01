# 03 — Backtest framework

## 1. Perché serve un nuovo backtest engine

Il backtest pipeline esistente di Alembic v1 è ottimizzato per la strategia singola news-driven con replay GDELT. Per il multi-strategia serve un engine che:

- Permetta di registrare N strategie e farle convivere su stesso capitale virtuale
- Modelli costi reali per asset class diversi (equity, opzioni, etf)
- Faccia walk-forward separato per strategia + combinato
- Replay news + price data point-in-time
- Sia abbastanza veloce per validare ogni strategia in ore (non giorni)
- Sia rigoroso su look-ahead

Le opzioni:

| Tool | Pro | Contro | Verdetto |
|------|-----|--------|----------|
| **Custom built** | Pieno controllo, integrazione perfetta con Alembic | Effort alto (4-6 settimane) | Bocciato |
| **vectorbt** | Velocissimo (numba), API pythonic, supporta multi-asset | Non event-driven, options support debole | **Ok per S1, S3, S4** |
| **NautilusTrader** | Event-driven serio, supporta options, multi-asset | Curva apprendimento ripida, più verboso | **Per S2 e validazione finale** |
| **Backtrader** | Diffuso, options support | Lentissimo, dev paused | Bocciato |
| **QuantConnect LEAN** | Production-grade, già nel repo Alembic | Cloud-coupled, complesso da self-host | Considerare per validation finale |

**Decisione**: **vectorbt per development e exploration delle strategie, NautilusTrader (o LEAN se già nel vostro stack) per validazione finale e simulazione opzioni**.

Workflow tipico:
1. Sviluppi strategia con vectorbt (loop veloce, iterazione facile)
2. Una volta convinto, replica in NautilusTrader/LEAN per validation finale event-driven
3. I numeri devono coincidere entro 5% (se diversi, indaga prima di andare avanti)

---

## 2. Architettura del backtest engine

```
┌─────────────────────────────────────────────────────────────┐
│                    BACKTEST ORCHESTRATOR                    │
│  Define time range · Load configs · Coordinate everything   │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼─────────┐ ┌──────▼─────────┐ ┌─────▼───────────┐
│  DATA REPLAY    │ │ STRATEGY RUNNER│ │ COST MODEL      │
│  Price+News     │ │ Run each       │ │ Slippage,       │
│  point-in-time  │ │ strategy at t  │ │ commission, tax │
└───────┬─────────┘ └──────┬─────────┘ └─────────────────┘
        │                  │
        └────────┬─────────┘
                 │
        ┌────────▼─────────┐
        │ PORTFOLIO STATE  │
        │  Track positions │
        │  Apply orders    │
        │  Compute PnL     │
        └────────┬─────────┘
                 │
        ┌────────▼─────────┐
        │  METRICS ENGINE  │
        │  Sharpe, DD, IC  │
        │  Per-strategy +  │
        │  Combined        │
        └──────────────────┘
```

### Dataflow

```python
def run_backtest(config: BacktestConfig):
    # 1. Load data point-in-time
    data_replay = DataReplay(
        start=config.start,
        end=config.end,
        universe=config.universe,
        news_archive=config.news_archive_path,  # GDELT pre-scored
        price_source=config.price_source,
    )
    
    # 2. Setup
    portfolio = VirtualPortfolio(initial_capital=config.initial_capital)
    strategies = [load_strategy(s) for s in config.active_strategies]
    combiner = PortfolioCombiner(config.combiner_params)
    cost_model = CostModel(config.cost_params)
    metrics = MetricsCollector()
    
    # 3. Event loop
    for as_of in data_replay.timesteps():
        # Build context point-in-time
        ctx = build_context(as_of, data_replay, portfolio)
        
        # Each strategy outputs target weights
        outputs = []
        for strategy in strategies:
            if strategy.should_run_at(as_of):
                output = strategy.compute_target_weights(ctx)
                outputs.append(output)
        
        # Combine
        if outputs:
            final_weights = combiner.combine(outputs, ...)
            
            # Generate orders
            orders = rebalancer.compute_orders(
                portfolio.current_weights(),
                final_weights,
                rebalance_band=config.rebalance_band,
            )
            
            # Simulate execution with costs
            for order in orders:
                fill = cost_model.simulate_fill(order, data_replay.current_market(as_of))
                portfolio.apply_fill(fill)
        
        # Mark-to-market
        portfolio.mark_to_market(data_replay.current_prices(as_of))
        metrics.snapshot(as_of, portfolio, outputs)
    
    # 4. Final report
    return metrics.compute_final_report()
```

---

## 3. Anti-look-ahead enforcement

**Questo è il punto più importante** di tutto il backtest. Un backtest con look-ahead non vale niente.

### Test automatici obbligatori

```python
def test_no_lookahead():
    """Test che il backtest non legga mai dati futuri"""
    
    # Sentinel: data point con valore "FUTURE" che dovrebbe causare crash se letto
    data_replay = DataReplayWithSentinels()
    
    strategies = [TimeSeriesMomentum(), VRP(), ...]
    
    for as_of in data_replay.timesteps():
        ctx = build_context(as_of, data_replay)
        
        # Verify: tutti i timestamps in ctx sono <= as_of
        assert all_inputs_before_or_equal(ctx, as_of)
        
        for strategy in strategies:
            output = strategy.compute_target_weights(ctx)
            # Verify: nessun valore "FUTURE" letto
            assert "FUTURE" not in str(output.rationale)
```

### Convenzioni di codifica

Tutte le data structures interne al backtest hanno **un timestamp di publication**:

```python
@dataclass
class PricePoint:
    ticker: str
    price: float
    timestamp: datetime  # when this price was observed
    
@dataclass
class NewsScore:
    news_id: UUID
    score: float
    news_published_at: datetime  # when news was published
    score_computed_at: datetime  # when LLM scored it (always > published_at)
```

Quando il backtest costruisce il contesto per `as_of=T`:
```python
def build_context(as_of: datetime, data_replay):
    return StrategyContext(
        as_of=as_of,
        prices=data_replay.prices_until(as_of),  # filter publication_time <= T
        news_scores=data_replay.news_scores_until(as_of),  # filter score_computed_at <= T
        regime=data_replay.regime_at(as_of),  # regime as known at time T
        ...
    )
```

### Common look-ahead bugs da evitare

1. **Rolling indicator computed on full series**: `df['vol_60d'] = df['returns'].rolling(60).std()` calcola usando dati che sembrano essere "all data". Bug. Devi farlo con shift o solo storia disponibile.

2. **Earnings/fundamentals con publication date sbagliato**: Yahoo Finance dà earnings con data evento, ma il dato pubblico è disponibile 1-2 giorni dopo. Usa SEC EDGAR per accuratezza.

3. **Survivorship bias nell'universo**: l'universo "S&P 500 oggi" non era l'S&P 500 di 10 anni fa. Servono universi point-in-time.

4. **News timestamp errato**: GDELT timestamp è approssimativo. Per backtest serio, usa il timestamp con offset di sicurezza (es. +15 min).

5. **Option chain shifting**: snapshot opzioni a EOD potrebbe essere "0:00 next day" — sembrare disponibile prima di esserlo.

---

## 4. Cost model

Sotto-stimare costi nei backtest è il peccato classico del retail quant.

### Components

```python
@dataclass
class CostModel:
    commission_per_share: float = 0.0  # Alpaca/IBKR: 0 su equity US
    sec_fee_per_share: float = 0.0000229  # SEC fee per sale
    finra_fee_per_share: float = 0.000145  # FINRA TAF per sale
    
    # Spread cost (half-spread paid on each side)
    spread_tier_a_bps: float = 1.0   # SPY, large ETF
    spread_tier_b_bps: float = 3.0   # large cap stocks (AAPL, MSFT)
    spread_tier_c_bps: float = 8.0   # mid cap
    spread_tier_d_bps: float = 20.0  # small cap, illiquid ETF
    
    # Market impact (square-root model)
    impact_k: float = 10.0  # calibrazione da literature
    
    # Options-specific
    option_commission_per_contract: float = 0.65  # IBKR
    option_bid_ask_spread_pct: float = 0.05  # 5% of mid is realistic for SPY puts
    
    def simulate_fill(self, order: Order, market: MarketSnapshot) -> Fill:
        ...
```

### Equity fill simulation

```python
def simulate_equity_fill(order, market):
    mid_price = (market.bid + market.ask) / 2
    
    # Half-spread paid
    spread_cost_bps = get_spread_tier(order.ticker, market.adv)
    spread_cost = mid_price * spread_cost_bps / 10000
    
    # Market impact
    pct_adv = order.size / market.adv
    impact_bps = impact_k * sqrt(pct_adv) * 10000
    impact_cost = mid_price * impact_bps / 10000
    
    # Direction-adjusted
    sign = 1 if order.side == 'BUY' else -1
    fill_price = mid_price + sign * (spread_cost + impact_cost)
    
    # Commission
    commission = SEC_FEE * order.size if order.side == 'SELL' else 0
    
    return Fill(
        order_id=order.id,
        fill_price=fill_price,
        quantity=order.size,
        commission=commission,
        slippage_bps=(fill_price - mid_price) / mid_price * 10000,
    )
```

### Options fill simulation (crucial per S2)

```python
def simulate_option_fill(order, market, chain):
    contract = chain.get(order.symbol)
    mid_price = (contract.bid + contract.ask) / 2
    
    # Options spread è significativo: 1-5% del prezzo
    half_spread = (contract.ask - contract.bid) / 2
    
    sign = 1 if order.side == 'BUY' else -1
    fill_price = mid_price + sign * half_spread * 0.5  # split the spread, optimistic
    
    commission = OPTION_COMMISSION_PER_CONTRACT * order.quantity
    
    return OptionFill(
        order_id=order.id,
        contract=contract.symbol,
        fill_price=fill_price,
        quantity=order.quantity,
        commission=commission,
    )
```

### Realistic slippage assumptions

Da literature (Almgren, Chriss, ecc.) e nostri test:

| Asset type | Half-spread (bps) | Impact (bps per 1% ADV) |
|------------|-------------------|--------------------------|
| SPY, QQQ | 1-2 | 5 |
| Large cap (S&P 500) | 3-5 | 10 |
| Mid cap (Russell 1000 mid) | 8-15 | 20 |
| Small cap | 20-50 | 40 |
| Niche ETF (CEF, leveraged) | 30-100 | 50 |
| SPY put options | 5-20% del premio | n/a |

**Per S2 (opzioni)**: usa half-spread del 10% del mid del premio come worst-case. Se il backtest funziona con questo assunto, l'edge è reale.

---

## 5. Walk-forward validation

### Setup

```python
@dataclass
class WalkForwardConfig:
    train_window_months: int = 24  # 2 anni training
    test_window_months: int = 3     # 3 mesi OOS
    step_months: int = 1            # rolling step
    refit_strategies_each_window: bool = False  # NO, parametri fissi da literature
```

### Algoritmo

```python
def walk_forward(strategies, full_data, config):
    """
    Rolling walk-forward:
    - Training period: solo per parameter calibration (NEL NOSTRO CASO: NESSUNO, parametri fissi)
    - Test period: backtest OOS pura
    - Step forward
    - Concatenate solo OOS results
    """
    results = []
    
    train_start = full_data.start
    train_end = train_start + relativedelta(months=config.train_window_months)
    
    while train_end + relativedelta(months=config.test_window_months) <= full_data.end:
        test_start = train_end
        test_end = test_start + relativedelta(months=config.test_window_months)
        
        # Run backtest only on test window
        result = run_backtest(
            start=test_start,
            end=test_end,
            strategies=strategies,
            initial_capital=100_000,  # reset each window
        )
        
        results.append(result)
        
        # Step forward
        train_start += relativedelta(months=config.step_months)
        train_end += relativedelta(months=config.step_months)
    
    return concatenate_oos(results)
```

### Output: OOS-only performance

Solo i risultati delle test windows, concatenati. Sharpe, drawdown, ecc. calcolati solo su queste.

Comparison automatica:
- Vs SPY buy-and-hold
- Vs 60/40 (60% SPY + 40% AGG)
- Vs equal-weighted strategy mix (naive combiner)

---

## 6. Validation gates

Una strategia deve **passare tutti questi gate** prima di entrare in paper trading nel sistema combinato.

### Gate 1: Statistical significance del signal

```python
def gate_1_signal_significance(strategy_outputs, returns):
    """
    Per S1, S3, S4: IC del signal vs forward returns
    Per S2: Sharpe del trading P&L direttamente (non c'è IC nel senso classico)
    """
    if strategy.type == "signal_based":
        ic_results = compute_ic(strategy_outputs, returns, horizon)
        return {
            'pass': ic_results.mean > 0 and ic_results.pvalue < 0.01,
            'ic_mean': ic_results.mean,
            'ic_pvalue': ic_results.pvalue,
            'n_obs': ic_results.n,
        }
    elif strategy.type == "trading":
        sharpe = compute_sharpe(backtest.returns)
        dsr = compute_deflated_sharpe(sharpe, n_trials=YOUR_TRIAL_COUNT)
        return {
            'pass': dsr > 0,
            'sharpe': sharpe,
            'deflated_sharpe': dsr,
        }
```

### Gate 2: Walk-forward consistency

```python
def gate_2_walk_forward(strategy, full_data):
    """OOS performance non deve degradare drasticamente vs in-sample"""
    in_sample = run_backtest(strategy, period=first_50pct(full_data))
    oos = walk_forward(strategy, full_data)
    
    return {
        'pass': oos.sharpe > 0.5 * in_sample.sharpe,  # OOS almeno 50% di IS
        'in_sample_sharpe': in_sample.sharpe,
        'oos_sharpe': oos.sharpe,
        'oos_max_dd': oos.max_drawdown,
    }
```

### Gate 3: Robustness to parameters

```python
def gate_3_param_robustness(strategy, base_params, full_data):
    """Performance non deve crollare con piccole variazioni dei parametri"""
    results = []
    for variant in generate_param_variants(base_params, n=20):
        result = run_backtest(strategy.with_params(variant), full_data)
        results.append(result)
    
    sharpes = [r.sharpe for r in results]
    
    return {
        'pass': median(sharpes) > 0.5 and stdev(sharpes) / median(sharpes) < 0.3,
        'sharpe_median': median(sharpes),
        'sharpe_stdev': stdev(sharpes),
        'sharpe_iqr': IQR(sharpes),
    }
```

### Gate 4: Regime stability

```python
def gate_4_regime_stability(strategy, full_data, regime_history):
    """Strategia non deve funzionare solo in 1 regime"""
    sharpe_by_regime = {}
    for regime in [RISK_ON, RISK_OFF, STRESS, GOLDILOCKS]:
        subset = filter_to_regime(full_data, regime_history, regime)
        if len(subset) > 60:  # almeno 60 giorni
            result = run_backtest(strategy, subset)
            sharpe_by_regime[regime] = result.sharpe
    
    positive_regimes = sum(1 for s in sharpe_by_regime.values() if s > 0.3)
    
    return {
        'pass': positive_regimes >= 3,  # positivo in almeno 3 dei 4 regimi
        'sharpe_by_regime': sharpe_by_regime,
    }
```

### Gate 5: Stress tests

```python
def gate_5_stress(strategy, full_data):
    """Sopravvive a periodi noti di stress"""
    stress_periods = [
        ('2008_GFC', '2008-09-01', '2009-03-31'),
        ('2020_COVID', '2020-02-15', '2020-04-15'),
        ('2022_RATES', '2022-01-01', '2022-10-31'),
        ('2018_VOL', '2018-02-01', '2018-02-15'),
    ]
    
    drawdowns = {}
    for name, start, end in stress_periods:
        result = run_backtest(strategy, start, end)
        drawdowns[name] = result.max_drawdown
    
    return {
        'pass': all(dd > -0.30 for dd in drawdowns.values()),  # max DD 30% in qualsiasi stress
        'drawdowns': drawdowns,
    }
```

### Riassunto: una strategia passa se

- Gate 1 ✓ statistical significance (IC o DSR positivi con p<0.01)
- Gate 2 ✓ walk-forward (OOS ≥ 50% di IS)
- Gate 3 ✓ robustness (Sharpe median ≥ 0.5, IQR/median < 0.3)
- Gate 4 ✓ multi-regime (Sharpe > 0.3 in almeno 3 di 4 regimi)
- Gate 5 ✓ stress survival (DD < 30% in periodi noti)

Una strategia che **non** passa tutti i gate **non entra** nel portfolio combinato. Resta in R&D.

---

## 7. Metriche standard per il report

Ogni backtest produce report con queste sezioni.

### Performance

- Total return, CAGR
- Annualized vol
- Sharpe (rf = 3-month T-bill)
- Sortino
- Calmar
- Win rate trades
- Profit factor

### Risk

- Max drawdown
- Drawdown duration (giorni)
- Time-to-recovery
- VaR 95% 1d
- ES 95% 1d
- Skewness, kurtosis dei returns
- Tail ratio (95th percentile / |5th percentile|)

### Attribution (multi-strategy)

- Per-strategy contribution to total return
- Per-strategy contribution to total risk
- Cross-strategy correlation matrix
- Diversification ratio

### Signal quality (signal-based strategies)

- IC mean, IC std, ICIR
- IC p-value e Deflated Sharpe
- Hit rate (% predictions corrette)

### Operations

- Turnover annualizzato
- Total cost (commission + slippage) come % NAV
- N trades
- Average holding period

### Stress

- DD in periodi noti (vedi Gate 5)

### Confronto

- Sharpe vs SPY
- Sharpe vs 60/40
- Sharpe vs equal-weight strategies
- Drawdown vs benchmark in periodi di stress

---

## 8. Tecnicalities di implementazione

### Performance optimization

Vectorbt è veloce ma non infinito. Per backtest su 30 anni daily × 4 strategie:
- Estimate runtime: 10-30 minuti
- Memory: 8-16 GB sufficiente
- Use parquet per data caching tra run

### Reproducibility

```python
@dataclass
class BacktestConfig:
    seed: int = 42  # for any randomness (none should exist, but safety)
    git_commit_hash: str  # auto-populated
    config_yaml_hash: str  # hash of strategy params
    
    # When persisted, allows perfect re-run
```

Run di backtest registrati su DB con seed, commit hash, config hash. Cambio di codice → re-run tutti i gate.

### Caching layers

- **Raw data cache**: parquet files in `~/data/cache/` per ticker, sorted by date
- **News scores cache**: già esiste nel sistema (Postgres), espandere per backtest
- **Backtest results cache**: salvare per `(strategy_id, config_hash, period)`, re-run solo se config change

### Quando ri-fare il backtest completo

- Aggiunta nuova strategia
- Cambio parametri "core" di una strategia esistente (con justifications)
- Cambio cost model
- Quarterly walk-forward refresh

**Mai**: per "vedere come va con parametri diversi" senza track formale. Quello è data dredging.
