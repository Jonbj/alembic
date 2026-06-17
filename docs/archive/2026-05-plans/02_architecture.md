# 02 — Architettura multi-strategia

## 1. Principio architetturale

Il sistema si organizza in **strategy modules indipendenti** + **shared infrastructure** + **portfolio combiner**. Ogni strategy module è una funzione pura `(state, market_data, params) → target_weights`. L'infrastruttura condivisa gestisce data, broker, risk, monitoring. Il combiner aggrega gli output per produrre il portafoglio finale.

```
┌────────────────────────────────────────────────────────────────────┐
│                      SHARED INFRASTRUCTURE                         │
│  Data ingestion · Broker adapters · Risk · Monitoring · Storage    │
└──────────────┬────────────────┬─────────────────┬────────┬─────────┘
               │                │                 │        │
        ┌──────▼─────┐  ┌──────▼─────┐  ┌─▼──────┐   ╔════════════╗
        │  S1: TSM   │  │ S2: VRP    │  │ S4: NWS │   ║ S3: XSM   ║
        │  (40%)     │  │  (30%)     │  │  (10%)  │   ║ [R&D sleeve║
        └──────┬─────┘  └──────┬─────┘  └─┬──────┘   ║  gates FAIL║
               │                │          │          ╚════════════╝
               │ target_weights │          │
               └────────────────┴──────────┘
                                    │
                          ┌─────────▼──────────┐
                          │ PORTFOLIO COMBINER │
                          │  Risk parity       │
                          │  Vol targeting     │
                          │  Constraints       │
                          └─────────┬──────────┘
                                    │
                                    │ final_target_weights
                                    │
                          ┌─────────▼──────────┐
                          │  REBALANCER        │
                          │  Drift band check  │
                          │  Order generation  │
                          └─────────┬──────────┘
                                    │
                          ┌─────────▼──────────┐
                          │  EXECUTION         │
                          │  Alpaca / IBKR     │
                          └────────────────────┘
```

---

## 2. Come riusare il codice esistente

### Inventario del codice attuale (da Alembic v1)

Dal repo Jonbj/alembic come da knowledge della discussione:

| Componente esistente | Riuso v2 | Modifica richiesta |
|---|---|---|
| News ingestion pipeline (GDELT, MarketAux, Benzinga) | Sì → S4, S2 event filter | Nessuna |
| LLM ensemble scoring (4 modelli) | Sì → S4, S2 event filter | Nessuna |
| Signal aggregation EWMA | Sì → S4 | Half-life parametrico |
| Regime classifier (Kimi+Qwen LLM pair) | Sì → S1 (filter), S2 (modulation), S4 (modulation) | Esporre come servizio agli strategy module |
| LOO ICIR weight optimization (Telegram) | Sì → S4, S1, S3 cross-validation | Generalizzare per gestire più strategie |
| Performance monitoring (PSI, CUSUM, Newey-West) | Sì → applicabile a tutte le strategie | Generalizzare |
| LLMBudgetTracker | Sì | Nessuna |
| GDELT GKG backtest pipeline | Sì → estendere per multi-strategia | Vedi §3 |
| Risk monitor + circuit breaker | Sì → critical per S2 | Estendere a opzioni |
| Celery worker | Sì | Aggiungere task per S1, S2, S3 |
| Alpaca SDK integration | Sì → S1, S3, S4 paper | Mantenere |
| Postgres + Redis storage | Sì | Nuove tabelle per ogni strategia |
| FastAPI endpoints | Sì | Nuovi endpoint per monitoring multi-strategia |
| Telegram bot per approval flow | Sì | Generalizzare per strategy switches |

### Cosa va aggiunto

**Nuovi componenti**:
- IBKR adapter (per opzioni in S2)
- Option chain data ingestion + storage
- Black-Scholes pricing + greeks
- Multi-strategy backtest engine event-driven
- Portfolio combiner con risk parity
- Cross-strategy constraint enforcer
- Strategy registry (lookup dinamico)

### Cosa va rimosso/deprecato

**Da deprecare** (parti dell'attuale che diventano obsolete):
- Logica "score > 0.30 → buy" diretta: sostituita da S4 con cross-sectional ranking + 10% cap
- Sizing fisso 10% per posizione: sostituito da inverse-vol + portfolio combiner
- Stop -2% fisso: sostituito da ATR-based + risk monitor across strategies

---

## 3. Strategy module contract

Ogni strategy module aderisce a un'interfaccia standard:

```python
from abc import ABC, abstractmethod
from datetime import datetime
from dataclasses import dataclass

@dataclass
class StrategyContext:
    """State + data passato a ogni strategia"""
    as_of: datetime
    current_portfolio: dict[str, float]  # ticker -> weight
    total_portfolio_value_usd: float
    regime: RegimeState
    market_data: MarketDataSnapshot
    strategy_params: dict  # config caricato da YAML
    
@dataclass
class StrategyOutput:
    strategy_id: str
    as_of: datetime
    target_weights: dict[str, float]  # ticker -> weight WITHIN this strategy's bucket
    rationale: dict  # debugging info: che signal ha visto, perché ha deciso così
    confidence: float  # [0, 1], usato dal combiner
    
class BaseStrategy(ABC):
    """Contratto comune a tutte le strategie"""
    
    @property
    @abstractmethod
    def strategy_id(self) -> str: ...
    
    @property
    @abstractmethod
    def target_allocation_pct(self) -> float:
        """Quanta % del portfolio totale questa strategia rivendica"""
        ...
    
    @property
    @abstractmethod
    def rebalance_frequency(self) -> RebalanceFrequency:
        """DAILY | WEEKLY | MONTHLY"""
        ...
    
    @abstractmethod
    def compute_target_weights(self, ctx: StrategyContext) -> StrategyOutput:
        """Calcola i target weights di questa strategia. Funzione pura."""
        ...
    
    @abstractmethod
    def health_check(self, ctx: StrategyContext) -> StrategyHealth:
        """Check di health: signal disponibile? Data fresca? Decay OK?"""
        ...
```

### Implementazione per le 4 strategie

```python
# strategies/s1_ts_momentum/strategy.py
class TimeSeriesMomentum(BaseStrategy):
    strategy_id = "s1_ts_momentum"
    target_allocation_pct = 0.40
    rebalance_frequency = RebalanceFrequency.MONTHLY
    
    def compute_target_weights(self, ctx):
        ...

# strategies/s2_vrp/strategy.py
class VolatilityRiskPremium(BaseStrategy):
    strategy_id = "s2_vrp"
    target_allocation_pct = 0.30
    rebalance_frequency = RebalanceFrequency.DAILY  # check daily, position può durare 30-45gg
    ...
```

---

## 4. Portfolio Combiner

Il combiner prende N `StrategyOutput` e produce target weights finali del portafoglio.

```python
@dataclass
class PortfolioCombiner:
    """Aggrega output multi-strategy in target weights finali del portfolio"""
    
    def combine(
        self,
        strategy_outputs: list[StrategyOutput],
        constraints: PortfolioConstraints,
        risk_params: RiskParams,
    ) -> dict[str, float]:
        """
        Input: lista di output dalle strategie attive
        Output: dict {ticker: target_weight} sommante a target gross exposure
        
        Steps:
        1. Scale ogni strategia per il suo target_allocation_pct
        2. Aggrega ticker-by-ticker across strategies (alcuni ticker appaiono in più strategie)
        3. Applica risk parity overlay (opzionale, configurabile)
        4. Vol targeting: scale per raggiungere target_total_vol
        5. Apply hard constraints (sector, concentration, max single)
        6. Iterative reconciliation se constraint violati
        """
        ...
```

### Algoritmo dettagliato

```python
def combine(strategy_outputs, constraints, risk_params):
    # Step 1: scale per allocazione strategia
    weighted_by_strategy = {}
    for output in strategy_outputs:
        strategy_alloc = STRATEGY_REGISTRY[output.strategy_id].target_allocation_pct
        for ticker, weight in output.target_weights.items():
            weighted_by_strategy.setdefault(ticker, 0.0)
            weighted_by_strategy[ticker] += weight * strategy_alloc
    
    # Step 2: risk parity overlay (opzionale, default OFF nella v1, ON nella v2)
    if risk_params.use_risk_parity:
        weights = apply_risk_parity(weighted_by_strategy, cov_matrix)
    else:
        weights = weighted_by_strategy
    
    # Step 3: vol targeting
    portfolio_vol = compute_portfolio_vol(weights, cov_matrix)
    if portfolio_vol > risk_params.target_total_vol:
        scale = risk_params.target_total_vol / portfolio_vol
        weights = {k: v * scale for k, v in weights.items()}
    
    # Step 4: hard constraints
    weights = enforce_constraints(weights, constraints)
    
    # Step 5: cash residual
    total = sum(abs(w) for w in weights.values())
    if total < 1.0:
        # remainder in cash, implicit
        pass
    elif total > constraints.max_gross_exposure:
        scale = constraints.max_gross_exposure / total
        weights = {k: v * scale for k, v in weights.items()}
    
    return weights
```

### Constraint enforcement

```python
def enforce_constraints(weights, constraints):
    """Applica constraint, ritornando weights più vicini al target che li rispettano"""
    
    # Max per single asset across strategies
    for ticker in list(weights.keys()):
        if abs(weights[ticker]) > constraints.max_single_asset:
            weights[ticker] = sign(weights[ticker]) * constraints.max_single_asset
    
    # Max per sector
    sector_weights = aggregate_by_sector(weights)
    for sector, w in sector_weights.items():
        if w > constraints.max_sector:
            scale_factor = constraints.max_sector / w
            for ticker in tickers_in_sector(sector):
                weights[ticker] *= scale_factor
    
    # Re-validate after adjustments (iterative)
    if not all_constraints_satisfied(weights, constraints):
        return enforce_constraints(weights, constraints)  # recursive
    
    return weights
```

**Importante**: gli output delle strategie sono **target richiesti**, non garantiti. Se constraint impedisce di soddisfare tutti, il combiner sceglie il "best fit" e logga il delta. Questo permette analisi: "S2 ha richiesto 30% in SPY ma constraint sector financial era già al 30% per S1, quindi ho dato solo 18%".

---

## 5. Shared services

### 5.1 Regime Service

Servizio condiviso che fornisce `RegimeState` corrente a tutte le strategie.

```python
class RegimeService:
    def get_current_regime(self, as_of: datetime) -> RegimeState:
        """Riusa regime_classifier esistente. Cache su Redis con TTL 1h."""
        ...
    
    def get_regime_history(self, start: datetime, end: datetime) -> list[RegimeState]:
        """Per backtest e analisi"""
        ...
```

### 5.2 Market Data Service

```python
class MarketDataService:
    def get_price_history(
        self, ticker: str, start: datetime, end: datetime, frequency: Frequency
    ) -> pd.DataFrame: ...
    
    def get_realized_vol(self, ticker: str, as_of: datetime, window_days: int) -> float: ...
    
    def get_correlation_matrix(
        self, tickers: list[str], as_of: datetime, window_days: int
    ) -> pd.DataFrame: ...
    
    def get_option_chain(self, underlying: str, as_of: datetime) -> OptionChain: ...
    """Solo per S2"""
```

### 5.3 News & LLM Signal Service

Riusa esistente, espone interfaccia clean alle strategie:

```python
class NewsSignalService:
    def get_aggregated_signal(
        self, ticker: str, as_of: datetime, horizon: SignalHorizon
    ) -> AggregatedSignal:
        """Riusa pipeline esistente"""
        ...
    
    def get_event_risk_flag(
        self, ticker: str, as_of: datetime, lookahead_days: int
    ) -> EventRiskFlag:
        """Used by S2 event filter. Returns True se evento ad alto rischio incombente."""
        ...
```

### 5.4 Risk Service

```python
class RiskService:
    def compute_portfolio_metrics(
        self, portfolio: dict[str, float], as_of: datetime
    ) -> RiskSnapshot: ...
    
    def check_circuit_breaker(
        self, portfolio: dict[str, float], as_of: datetime
    ) -> CircuitBreakerStatus:
        """Se True, NEW positions blocked, only exits allowed"""
        ...
    
    def stress_test(
        self, portfolio: dict[str, float], scenarios: list[Scenario]
    ) -> StressTestResult: ...
```

### 5.5 Broker Adapter

Interfaccia unificata, implementazioni multiple:

```python
class BrokerAdapter(ABC):
    @abstractmethod
    def get_positions(self) -> list[Position]: ...
    
    @abstractmethod
    def submit_order(self, order: Order) -> Order: ...
    
    @abstractmethod
    def get_account_state(self) -> AccountState: ...

class AlpacaAdapter(BrokerAdapter): ...
class IBKRAdapter(BrokerAdapter): ...  # per opzioni S2
```

---

## 6. Orchestrazione (Celery)

### Task schedule

```python
# Daily, 06:00 ET pre-market
@celery_task
def compute_strategy_signals():
    """Run le strategie e produce StrategyOutput, persistito in DB"""
    for strategy in active_strategies():
        ctx = build_context(strategy, as_of=now())
        output = strategy.compute_target_weights(ctx)
        persist_strategy_output(output)

# Daily, 06:30 ET
@celery_task
def combine_and_rebalance():
    """Aggrega output, applica combiner, genera ordini se drift > band"""
    outputs = load_today_strategy_outputs()
    final_weights = combiner.combine(outputs, constraints, risk_params)
    
    current = broker.get_positions()
    orders = rebalancer.compute_orders(current, final_weights, rebalance_band=0.20)
    
    if circuit_breaker_active():
        log_critical("Circuit breaker active, blocking new orders")
        return
    
    for order in orders:
        broker.submit_order(order)

# Hourly, market hours
@celery_task  
def monitor_positions():
    """Check stop-loss, signal-flip exit, position health"""
    ...

# Daily, post-close
@celery_task
def reconcile_and_snapshot():
    """Reconcile fills, compute risk snapshot, run health checks"""
    ...

# Weekly, Sunday
@celery_task
def decay_study_run():
    """Per ogni strategia, calcola IC rolling e Sharpe rolling. Alert se decay"""
    ...

# Monthly
@celery_task
def walk_forward_validation():
    """Backtest rolling OOS, compare to live. Alert se divergence > soglia"""
    ...
```

---

## 7. Storage layout

### Tabelle nuove (rispetto a v1)

```sql
-- Strategy outputs persisted
CREATE TABLE strategy_outputs (
    id UUID PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    as_of TIMESTAMPTZ NOT NULL,
    target_weights JSONB NOT NULL,
    rationale JSONB,
    confidence FLOAT,
    health_status VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    INDEX (strategy_id, as_of DESC)
);

-- Combined portfolio decisions
CREATE TABLE portfolio_decisions (
    id UUID PRIMARY KEY,
    as_of TIMESTAMPTZ NOT NULL,
    final_target_weights JSONB NOT NULL,
    strategy_outputs_ids UUID[],  -- references
    constraints_applied JSONB,
    constraints_breaches JSONB,  -- log di constraint violati e azione presa
    portfolio_vol_estimated FLOAT,
    gross_exposure FLOAT,
    net_exposure FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Option positions (per S2)
CREATE TABLE option_positions (
    id UUID PRIMARY KEY,
    underlying VARCHAR(10) NOT NULL,
    contract_type VARCHAR(10) NOT NULL,  -- 'PUT' | 'CALL'
    strike FLOAT NOT NULL,
    expiration DATE NOT NULL,
    quantity INT NOT NULL,  -- negative se short
    open_price FLOAT NOT NULL,
    open_date TIMESTAMPTZ NOT NULL,
    close_price FLOAT,
    close_date TIMESTAMPTZ,
    close_reason VARCHAR(50),  -- 'expiration' | 'target_hit' | 'stop_loss' | 'manual'
    pnl_usd FLOAT,
    strategy_id VARCHAR(50) DEFAULT 's2_vrp',
    INDEX (underlying, open_date DESC)
);

-- Strategy health tracking (decay, alerts)
CREATE TABLE strategy_health (
    id UUID PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    as_of DATE NOT NULL,
    rolling_sharpe_3m FLOAT,
    rolling_sharpe_12m FLOAT,
    rolling_ic_3m FLOAT,
    rolling_ic_12m FLOAT,
    n_trades_30d INT,
    realized_vol_30d FLOAT,
    drift_score FLOAT,  -- PSI o simile
    alert_level VARCHAR(20),
    UNIQUE (strategy_id, as_of)
);
```

### Riuso tabelle v1

Tabelle esistenti (news, signal_scores, aggregated_signals, regime_states, decisions, orders, fills) mantengono il loro schema.

---

## 8. Configurazione globale

```yaml
# config/alembic_v2.yaml
version: "2.0.0"

active_strategies:
  - s1_ts_momentum
  - s2_vrp
  # - s3_xs_momentum  # S3 demoted to R&D sleeve 01/06/2026 — gates 3&5 FAIL
  - s4_news_tactical

portfolio:
  target_total_vol: 0.10
  max_gross_exposure: 1.5
  max_net_exposure: 1.2
  rebalance_band_pct: 0.20
  combiner_method: "risk_parity"  # alternatives: "naive_weighted", "mean_variance"
  
constraints:
  max_single_asset: 0.10
  max_sector: 0.35
  max_correlation_concentration: 0.8

circuit_breaker:
  trigger_drawdown_pct: 0.15
  trigger_vol_breach_multiplier: 1.6
  block_new_positions: true
  allow_exits: true

monitoring:
  decay_alert_sharpe_threshold: -0.5
  decay_alert_window_months: 6
  drift_alert_psi_threshold: 0.2

# Strategie config in file separati
strategy_configs:
  s1_ts_momentum: "config/strategies/s1.yaml"
  s2_vrp: "config/strategies/s2.yaml"
  s3_xs_momentum: "config/strategies/s3.yaml"
  s4_news_tactical: "config/strategies/s4.yaml"
```

---

## 9. Anti-pattern da evitare

Lezioni di chi è venuto prima.

### 9.1 NO: ottimizzare parametri su periodo recente
"L'ultimo anno S1 ha sotto-performato, abbassiamo la lookback da 252 a 126" → overfit garantito. **Parametri fissati a priori dalla letteratura, mai cambiati su OOS recente.**

### 9.2 NO: aggiungere strategia perché ultimo backtest era buono
"Ho trovato una variant di S1 che ha Sharpe 1.5 sul 2020-2024" → quasi sicuramente data mining. **Strategy nuove richiedono multiple testing correction prima di entrare in produzione.**

### 9.3 NO: cambiare allocazione strategy in modo reattivo
"S4 sta funzionando benissimo, alziamo a 30%" → fragile. **Allocazione strategy si rivede solo su trigger formale di decay study trimestrale.**

### 9.4 NO: condividere state tra strategie
Strategie devono essere **indipendenti**. Se S1 e S2 dipendono entrambe da una variabile globale che cambia, hai un mess. State condiviso solo via servizi readonly (regime, market data).

### 9.5 NO: ottimizzare per Sharpe storico massimo
Sharpe storico massimo = overfit massimo. **Target: Sharpe OOS plausibile, robusto a parameter sensitivity.**

### 9.6 NO: skip walk-forward per "andare live più veloce"
Walk-forward è il **gate**, non un nice-to-have. **No walk-forward = no paper trading = no live.**
