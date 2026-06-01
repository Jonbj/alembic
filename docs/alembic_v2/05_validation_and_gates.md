# 05 — Validation, gates e monitoring

Documento operativo per validare ogni strategia prima di farla entrare in produzione (paper) e per monitorare la salute del sistema runtime.

---

## 1. I 5 Validation Gates in dettaglio

Una strategia passa al portfolio combinato (paper) **solo se passa tutti i gate**. Eccezioni documentate:
- S4 (R&D sleeve): criteri più tolleranti su gate 2-4.
- S2 (VRP): **Milestone D PASS con eccezioni** - OOS Sharpe 0.20. Gate 3 FAIL marginale (CV=0.53 vs 0.50), Gate 4 eccezione (3/4 regimi). Strategia accettata: diversificazione VRP, sopravvivenza stress eccellente (COVID max DD -0.44%).
- S3 (Cross-Sectional Momentum): **R&D sleeve in attesa** — gate 3 (CV=2.05 >> max 0.5) e gate 5 (cum_return=-10.07%) FAIL. OOS Sharpe 0.15. S3 esclusa dal portfolio live, tuning parametri rimandato a post-Fase-F. Codice esiste, non eliminato.

### Gate 1 — Statistical Significance

**Per strategie signal-based** (S1, S3, S4):

```python
def gate_1_significance(strategy_outputs, forward_returns, horizon_days):
    """
    Verifica IC del signal vs forward returns.
    """
    # Spearman IC per ogni timestamp di rebalance
    daily_ic = []
    for ts in strategy_outputs.timestamps:
        signal = strategy_outputs.signal_at(ts)  # dict {ticker: signal_value}
        fwd_ret = forward_returns.at(ts, horizon_days)  # dict {ticker: return}
        
        # Spearman rank correlation
        ic = spearmanr(signal.values(), fwd_ret.values())[0]
        daily_ic.append(ic)
    
    # T-test su IC daily series
    t_stat, p_value = ttest_1samp(daily_ic, 0)
    
    # Newey-West HAC correction (autocorrelation-robust)
    nw_se = newey_west_se(daily_ic, lags=5)
    nw_t_stat = mean(daily_ic) / nw_se
    nw_p_value = 2 * (1 - norm.cdf(abs(nw_t_stat)))
    
    return GateResult(
        passed=(mean(daily_ic) > 0 and nw_p_value < 0.01),
        metric_name="IC",
        value=mean(daily_ic),
        p_value=nw_p_value,
        n_obs=len(daily_ic),
        notes=f"NW HAC corrected, ICIR={mean(daily_ic)/std(daily_ic):.3f}"
    )
```

**Per strategie trading-based** (S2):

```python
def gate_1_significance_trading(backtest_returns):
    """
    Per strategie trading, usa Deflated Sharpe Ratio (López de Prado 2018).
    """
    sr = sharpe_ratio(backtest_returns)  # annualized
    
    # Trials cuonti: quante varianti hai testato durante development?
    # Honest reporting: se hai provato 10 set di parametri, n_trials=10
    n_trials = STRATEGY_DEVELOPMENT_TRIALS  # da tracking
    
    # Variance of Sharpes across trials (proxy: bootstrap)
    sr_bootstrap = block_bootstrap_sharpes(backtest_returns, n_iter=1000)
    sr_variance = var(sr_bootstrap)
    
    # Deflated Sharpe (López de Prado)
    skew_ret = skew(backtest_returns)
    kurt_ret = kurtosis(backtest_returns)
    n = len(backtest_returns)
    
    dsr = deflated_sharpe(sr, n_trials, sr_variance, skew_ret, kurt_ret, n)
    
    return GateResult(
        passed=(dsr > 0.5),  # DSR conservative threshold
        metric_name="DSR",
        value=dsr,
        notes=f"SR={sr:.2f}, n_trials={n_trials}"
    )
```

**Pass criteria summary**:
- Signal-based: IC mean > 0 e p-value Newey-West < 0.01 su ≥ 300 obs
- Trading-based: DSR > 0.5 con honest n_trials reporting

---

### Gate 2 — Walk-Forward Consistency

```python
def gate_2_walk_forward(strategy, full_data, in_sample_pct=0.5):
    """
    OOS performance non deve essere drasticamente peggio di in-sample.
    """
    cut_date = full_data.start + (full_data.end - full_data.start) * in_sample_pct
    
    # In-sample backtest (just first half, for comparison)
    is_result = run_backtest(strategy, full_data.start, cut_date)
    
    # Walk-forward su second half
    wf_result = walk_forward(
        strategy,
        full_data,
        train_window_months=24,
        test_window_months=3,
        oos_start=cut_date,
    )
    
    ratio = wf_result.sharpe / is_result.sharpe if is_result.sharpe > 0 else 0
    
    return GateResult(
        passed=(ratio > 0.5 and wf_result.sharpe > 0.3),
        metric_name="OOS_vs_IS_Sharpe_Ratio",
        value=ratio,
        notes=f"IS Sharpe={is_result.sharpe:.2f}, OOS Sharpe={wf_result.sharpe:.2f}"
    )
```

**Pass criteria**: 
- OOS Sharpe > 50% di IS Sharpe
- OOS Sharpe > 0.3 in assoluto
- OOS drawdown < 2x IS drawdown

---

### Gate 3 — Parameter Robustness

```python
def gate_3_robustness(strategy, base_params, full_data, n_variants=20):
    """
    Performance robust to ±20% parameter perturbations.
    """
    variants = generate_param_variants(base_params, perturbation=0.20, n=n_variants)
    
    results = []
    for variant_params in variants:
        result = run_backtest(strategy.with_params(variant_params), full_data)
        results.append(result.sharpe)
    
    median_sr = median(results)
    iqr_sr = percentile(results, 75) - percentile(results, 25)
    
    # Skip stupid variants (Sharpe < 0)
    valid_results = [r for r in results if r > -0.5]
    
    return GateResult(
        passed=(median_sr > 0.5 and (iqr_sr / abs(median_sr)) < 0.4 if median_sr != 0 else False),
        metric_name="Sharpe_median_with_IQR",
        value=median_sr,
        notes=f"Median={median_sr:.2f}, IQR={iqr_sr:.2f}, IQR/median={iqr_sr/abs(median_sr):.2f}"
    )
```

**Pass criteria**:
- Median Sharpe across 20 variants > 0.5
- IQR / median < 40% (low dispersion = robust)

**Rationale**: una strategia che funziona solo con un set preciso di parametri è overfit. Vere strategie hanno una "ridge" di parametri buoni, non un "peak" sharp.

---

**Eccezione esplicita Gate 3 per S2**: S2 (VRP) ha CV=0.53, marginalmente sopra la soglia di 0.50 (6% sopra). Tutte e 5 le perturbazioni hanno Sharpe positivo (0.042-0.324). La strategia sopravvive a tutti e 4 i periodi di stress (COVID max DD -0.44%). Accettato perche: (1) CV solo marginalmente sopra soglia, (2) tutte le varianti positive, (3) eccellente protezione tail-risk.

### Gate 4 — Multi-Regime Stability

```python
def gate_4_regime(strategy, full_data, regime_history):
    """
    Strategy positive in multiple regimes.
    """
    regimes = [RISK_ON, RISK_OFF, GOLDILOCKS, STRESS]
    sharpe_by_regime = {}
    n_days_by_regime = {}
    
    for regime in regimes:
        regime_days = regime_history.filter_to_regime(regime)
        if len(regime_days) < 60:
            continue
        
        subset = full_data.filter_to_days(regime_days)
        result = run_backtest(strategy, subset)
        sharpe_by_regime[regime] = result.sharpe
        n_days_by_regime[regime] = len(regime_days)
    
    positive_regimes = sum(1 for s in sharpe_by_regime.values() if s > 0.3)
    
    return GateResult(
        passed=(positive_regimes >= 3),
        metric_name="positive_regimes",
        value=positive_regimes,
        notes=f"Sharpes: {sharpe_by_regime}"
    )
```

**Pass criteria**: Sharpe > 0.3 in almeno 3 dei 4 regimi macro.

**Eccezione esplicita**: S2 (VRP) intrinsecamente sotto-performa in STRESS (è il "rischio assicurativo" che cattura premium). Per S2, accettato pass con 2 regimi positivi (RISK_ON, GOLDILOCKS), 1 neutro (RISK_OFF), 1 negativo (STRESS), con DD STRESS < 30%.

---

### Gate 5 — Stress Test Survival

```python
def gate_5_stress(strategy, full_data):
    """
    Survives known historical stress periods.
    """
    stress_periods = [
        StressPeriod('2008_GFC', '2008-09-01', '2009-03-31', expected_market_dd=-0.45),
        StressPeriod('2020_COVID', '2020-02-15', '2020-04-15', expected_market_dd=-0.34),
        StressPeriod('2022_RATES', '2022-01-01', '2022-10-31', expected_market_dd=-0.25),
        StressPeriod('2018_VOL', '2018-02-01', '2018-02-15', expected_market_dd=-0.10),
        StressPeriod('2018_Q4', '2018-10-01', '2018-12-31', expected_market_dd=-0.20),
    ]
    
    results = {}
    for sp in stress_periods:
        result = run_backtest(strategy, sp.start, sp.end)
        results[sp.name] = {
            'strategy_dd': result.max_drawdown,
            'market_dd': sp.expected_market_dd,
            'survived': result.max_drawdown > -0.30,
        }
    
    all_survived = all(r['survived'] for r in results.values())
    
    return GateResult(
        passed=all_survived,
        metric_name="stress_survival",
        value=sum(r['survived'] for r in results.values()),
        notes=f"DDs by period: {results}"
    )
```

**Pass criteria**: max drawdown < 30% in **ogni** periodo di stress.

---

## 2. Runtime monitoring

Una volta validata e in paper trading, ogni strategia richiede monitoring continuo. Se una metrica si degrada, **lo dovresti sapere prima** che diventi un problema serio.

### 2.1 Daily metrics (calcolate post-EOD)

Per ogni strategia, ogni giorno:

```python
@dataclass
class DailyStrategyHealth:
    strategy_id: str
    as_of: date
    
    # Trade metrics
    n_trades_today: int
    n_positions: int
    
    # Performance rolling
    sharpe_30d: float
    sharpe_90d: float
    sharpe_252d: float
    sharpe_since_inception: float
    
    # Risk
    realized_vol_30d: float
    current_drawdown_from_high: float
    max_dd_30d: float
    
    # Signal quality (if applicable)
    ic_30d: float
    ic_90d: float
    
    # Drift indicators
    signal_distribution_psi: float  # vs baseline
    output_correlation_with_benchmark: float
    
    # Health flags
    health_status: str  # GREEN, YELLOW, RED
    alerts: list[str]
```

### 2.2 Alert thresholds per strategia

```yaml
monitoring:
  s1_ts_momentum:
    sharpe_30d_warning: 0.0  # below 0, warning
    sharpe_30d_critical: -0.5
    sharpe_252d_warning: 0.3
    realized_vol_breach_multiplier: 1.5  # vs target
    drawdown_warning: -0.08
    drawdown_critical: -0.15
    ic_decay_warning: 0.0  # 30d IC below 0
    
  s2_vrp:
    # VRP è più volatile, soglie diverse
    sharpe_30d_warning: -0.5  # tollera più swing
    sharpe_30d_critical: -1.5
    drawdown_warning: -0.10
    drawdown_critical: -0.25
    
  # s3_xs_momentum:  # S3 not active — R&D sleeve. Enable only if S3 re-enters portfolio.
  #   sharpe_30d_warning: -0.3
  #   drawdown_warning: -0.15
  #   drawdown_critical: -0.30  # momentum crashes brutali, tolleriamo
    
  s4_news_tactical:
    # S4 è R&D, soglie tolleranti
    sharpe_30d_warning: -1.0
    drawdown_warning: -0.05  # è solo 10%, DD nominale piccolo
    # ma anche: se contribution to portfolio < 0 per 6 mesi consecutivi → retire
```

### 2.3 Action on alert

```python
def handle_alert(strategy_id, alert_level, metric):
    if alert_level == "WARNING":
        # Notify (Telegram, email)
        # No automatic action
        notify_developer(strategy_id, alert_level, metric)
        
    elif alert_level == "CRITICAL":
        # Notify + reduce position size
        notify_developer(strategy_id, alert_level, metric, urgent=True)
        if strategy_id != "s2_vrp":  # S2 ha logica specifica
            reduce_strategy_allocation(strategy_id, factor=0.5)
        
    elif alert_level == "EMERGENCY":
        # Stop strategy, close positions, require manual restart
        notify_developer(strategy_id, alert_level, metric, urgent=True)
        stop_strategy(strategy_id)
        close_all_positions(strategy_id)
```

---

## 3. Drift detection

Le strategie possono degradarsi in due modi: **performance drift** (Sharpe scende) o **signal drift** (la distribuzione del signal cambia).

### 3.1 Performance drift (rolling Sharpe)

Tracking semplice, alert se rolling Sharpe scende sotto threshold per N giorni consecutivi.

### 3.2 Signal drift (PSI / KS test)

Per strategie signal-based, monitor la distribuzione del signal nel tempo.

```python
def detect_signal_drift(strategy_id, lookback_days=90):
    """
    Population Stability Index (PSI) on signal distribution.
    PSI < 0.1: no drift
    PSI 0.1-0.2: slight drift, monitor
    PSI > 0.2: significant drift, alert
    """
    baseline_signals = load_signals(strategy_id, period="baseline")
    current_signals = load_signals(strategy_id, period=f"last_{lookback_days}d")
    
    psi = compute_psi(baseline_signals, current_signals, n_bins=10)
    
    return DriftReport(
        psi=psi,
        alert_level=(
            "GREEN" if psi < 0.1
            else "YELLOW" if psi < 0.2
            else "RED"
        )
    )
```

### 3.3 LLM drift (specific per S2 event filter, S4)

Le LLM cambiano nel tempo (provider update, model version). Monitoring specifico:

```python
def monitor_llm_drift():
    """
    Daily check su LLM output distribution.
    """
    for llm_model in ["glm", "qwen", "kimi", "deepseek"]:
        recent_polarity = load_recent_polarity(llm_model, days=7)
        baseline_polarity = load_baseline_polarity(llm_model)
        
        # KS test
        ks_stat, p_value = ks_2samp(baseline_polarity, recent_polarity)
        
        if p_value < 0.01:
            alert(f"LLM {llm_model} drift detected, p={p_value}")
        
        # Refusal rate
        refusal_rate = compute_refusal_rate(llm_model, days=7)
        if refusal_rate > 0.05:  # 5% refusals
            alert(f"LLM {llm_model} elevated refusal rate: {refusal_rate}")
```

---

## 4. Decay study ricorrente

Mensile, automatizzato.

```python
def monthly_decay_study():
    """
    Re-run walk-forward on most recent year. Compare to historical OOS metrics.
    Detect if alpha is decaying.
    """
    for strategy in active_strategies():
        # Walk-forward su ultimo anno
        recent_wf = walk_forward(
            strategy,
            full_data,
            oos_start=today - relativedelta(months=12),
        )
        
        # Historical baseline
        historical_wf = walk_forward(
            strategy,
            full_data,
            oos_end=today - relativedelta(months=12),
        )
        
        # Compare
        sharpe_decay = recent_wf.sharpe - historical_wf.sharpe
        ic_decay = recent_wf.ic_mean - historical_wf.ic_mean
        
        report = DecayReport(
            strategy_id=strategy.id,
            recent_sharpe=recent_wf.sharpe,
            historical_sharpe=historical_wf.sharpe,
            sharpe_decay=sharpe_decay,
            recent_ic=recent_wf.ic_mean,
            historical_ic=historical_wf.ic_mean,
            ic_decay=ic_decay,
            verdict=classify_decay(sharpe_decay, ic_decay),
        )
        
        persist(report)
        if report.verdict in ["DECAYING", "DEAD"]:
            alert(report)
```

### Decay verdict logic

```python
def classify_decay(sharpe_decay, ic_decay):
    if sharpe_decay > -0.2 and ic_decay > -0.01:
        return "HEALTHY"
    elif sharpe_decay > -0.5 and ic_decay > -0.03:
        return "WATCHING"
    elif sharpe_decay > -1.0:
        return "DECAYING"
    else:
        return "DEAD"
```

### Action on decay

- HEALTHY: nothing
- WATCHING: notify, continue
- DECAYING: reduce allocation 50%, deep dive analysis
- DEAD: stop strategy, retire from portfolio

---

## 5. Go/no-go criteria per progressione

### Da backtest a paper trading combinato

Una strategia entra nel portfolio paper combinato se:
- [ ] Tutti i 5 validation gate passed (o eccezioni documentate per S2 e S4)
- [ ] Backtest report rivisto e firmato (commit nel repo)
- [ ] Strategy module testato unit + integration
- [ ] Health check funzionante
- [ ] Decay study baseline definita

### Da paper trading a live (capitale reale)

**Decisione esplicita post Milestone G**, criteri:

- [ ] 90+ giorni paper trading combinato senza problemi tecnici
- [ ] Live performance entro 1σ del backtest atteso
- [ ] Tutte le alert testate (drill: simulare crash, verificare circuit breaker)
- [ ] Disaster recovery testato (DB restore, broker reconnect, data feed loss)
- [ ] Documentazione completa per ogni strategia
- [ ] Reproducibility test passed (re-run di ogni decisione produce stesso output)
- [ ] **Tax engine basico funzionante** (almeno lot accounting + bollo)
- [ ] **Capitale iniziale = 5% del wealth totale**. Mai più. Se va bene, scale-up incrementale.

### Quando ritirare una strategia

- Decay verdict "DEAD" per 2 mesi consecutivi
- Drawdown > 2x DD massimo nei backtest
- Strutturalmente broken (es. asset class non più tradabile, regulatory change)
- Sostituita da una strategia che la subsume con Sharpe migliore

---

## 6. Reporting

### Daily report (automated)

Email/Telegram ogni mattina con:
- Performance ieri (per strategia + combined)
- Trades eseguiti ieri
- Alerts (se presenti)
- Health status per strategia

### Weekly report

Più dettagliato:
- Rolling performance metrics
- Drawdown analysis
- Risk metrics snapshot
- Decay indicators

### Monthly report

Decay study + walk-forward refresh + sensitivity update + comparison vs benchmarks.

### Quarterly review

Decisioni di scope:
- Allocation per-strategy update?
- Strategie da retire?
- Nuove strategie da considerare (R&D)?
- Parameter tweaks documentati (raramente, e con ottime ragioni)?

Le decisioni quarterly **sono le uniche** in cui posso cambiare l'allocazione strategy. Mai reattivamente.

---

## 7. Antipatterns specifici di runtime

### 7.1 "L'ultimo mese è andato male, riduco l'allocazione"
**NO**. L'allocazione si cambia solo a quarterly review formale, basata su decay study + walk-forward refresh.

### 7.2 "Provo a backtestare un parametro diverso, magari va meglio"
**NO** se non hai trigger formale (gate fail, decay alert). Altrimenti è data dredging.

### 7.3 "Aggiungo un ticker che è andato bene last year"
**NO**. L'universe è definito a priori, modifiche richiedono full re-validation.

### 7.4 "Disabilito il regime overlay perché blocca trade in stress"
**NO**. Il regime overlay è il safety net. Disabilitarlo per "perdere meno trade" è il primo passo al blow-up.

### 7.5 "Live diverge dal backtest, c'è un bug → forzo i parametri"
**MAYBE**. Prima diagnostica: data quality, slippage model, look-ahead. Se vero bug, fix. Se è semplicemente noise statistico, accetta.

---

## 8. Reproducibility e audit trail

Ogni decision del sistema deve essere riproducibile.

### Cosa serve

- Git commit hash registrato per ogni run
- Config hash registrato per ogni decision
- Input data snapshot referenziato per ogni decision
- Output deterministico (no random seeds non controllati)

### Audit trail

Per ogni trade in paper o live:
```
{
  "trade_id": "...",
  "strategy_id": "s1_ts_momentum",
  "timestamp": "2026-...",
  "decision_id": "...",
  "git_commit": "abc123",
  "config_hash": "def456",
  "inputs_snapshot": {
    "as_of": "...",
    "signals_used": [...],
    "regime_at_decision": "RISK_ON",
    "constraints_applied": [...],
    "constraints_breached": []
  },
  "rationale": "...",
  "order_submitted": {...},
  "fill_received": {...}
}
```

Persisted forever, immutable, query-able.

### Re-run test

Settimanale: pick a random decision dall'ultima settimana, re-run con stesso input, verifica output identico. Se diverge, debug.

---

## 9. Critical paths del sistema

Componenti che, se rotti, devono fare **stop trading immediato**:

1. **Anti-look-ahead test fail in CI**: blocca deploy. Sistema attuale resta running ma no new strategies.
2. **Risk monitor down**: stop all new positions, alert.
3. **Broker connection broken**: stop new orders, alert. Existing positions stand.
4. **DB corruption / unable to persist decisions**: stop everything until restored.
5. **Drift critical su LLM core (per S4, S2 event filter)**: pause strategies that depend on it.

---

## 10. Cosa significa "il sistema funziona"

Definizione operativa, da riguardare prima di ogni milestone:

**Il sistema funziona quando**:
- Tutte le strategie attive hanno verdict decay "HEALTHY" o "WATCHING"
- Combined Sharpe live entro 1σ del backtest atteso
- No critical alerts negli ultimi 30 giorni
- Reproducibility test ok in ultimo run
- Risk monitor + circuit breaker green

**Il sistema NON funziona quando**:
- 1+ strategie con verdict "DECAYING" o "DEAD"
- Combined Sharpe live > 2σ peggio del backtest
- 1+ critical alert recenti
- Drift detection ha trovato cambiamenti significativi
- Broker reconnection problems persistenti

Nel secondo caso: **scale down or stop**, debugging, decisione consapevole.
