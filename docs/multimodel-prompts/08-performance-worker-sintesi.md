# Sintesi Analisi Multi-Modello — Performance Worker

**Data:** 2026-05-03  
**File analizzato:** 07-performance-worker.md  
**Modelli utilizzati:** 8 (opus, qwen3.5:cloud, qwen3-coder-next:cloud, glm-5.1:cloud, gemma4:31b-cloud, deepseek-v4-pro:cloud, minimax-m2.1:cloud, devstral-2:123b-cloud)

---

## Riepilogo Esecutivo

| Modello | Focus Analisi | Qualità | Raccomandazione Chiave |
|---------|---------------|---------|------------------------|
| **opus** | IC design, ensemble weighting | ⭐⭐⭐⭐⭐ | Smoothing 0.3, max delta 10%, leave-one-out IC |
| **qwen3.5:cloud** | Drift detection, threshold optimizer | ⭐⭐⭐⭐⭐ | PSI + CUSUM, baseline 90gg, regime-aware thresholds |
| **qwen3-coder-next:cloud** | Implementazione Python, calibration | ⭐⭐⭐⭐⭐ | ConfidenceCalibrationTracker, PI controller |
| **glm-5.1:cloud** | Calcolo dimensionale, statistica | ⭐⭐⭐⭐⭐ | n=784 per IC=0.10, Newey-West correction |
| **gemma4:31b-cloud** | Drift metrics, fallback monitoring | ⭐⭐⭐⭐ | JSD + PSI, hybrid rule-based fallback |
| **deepseek-v4-pro:cloud** | Chicken-and-egg bias, instabilità | ⭐⭐⭐⭐⭐ | Inverse probability weighting, Lyapunov exponent |
| **minimax-m2.1:cloud** | Post-mortem classification | ⭐⭐⭐⭐ | 10 categorie, rule-based hierarchy |
| **devstral-2:123b-cloud** | Review architetturale | ⭐⭐⭐⭐ | MVP Fase 1: 3 componenti base |

---

## 1. Conflitti da Risolvere

### 1.1 IC come Metrica Primaria

**Conflitto:** Tutti i modelli concordano su Spearman IC ma evidenziano limiti diversi.

**Risoluzione:** Usare **IC composito**:

```python
def composite_signal_quality(scores, returns, confidences):
    spearman_ic = spearmanr(scores, returns).correlation
    weighted_hit_rate = np.average(
        np.sign(scores) == np.sign(returns),
        weights=confidences
    )
    # Brier Score per calibrazione
    brier = np.mean((confidences - (returns > 0)) ** 2)
    
    return 0.5 * spearman_ic + 0.3 * weighted_hit_rate + 0.2 * (1 - brier)
```

---

### 1.2 Dimensione Campionaria Minima

**Conflitto:** La spec propone 30 segnali (intraday) e 20 (swing). Tutti i modelli concordano: **insufficienti**.

**Calcolo unanime (glm-5.1, opus, qwen3.5):**

```
Per IC = 0.10, potere 0.80, α = 0.05:
n = [(Z_α + Z_β) / atanh(IC)]² + 3
n = [(1.96 + 0.84) / 0.1003]² + 3
n = 784 osservazioni
```

**Raccomandazione:** 
- Minimo **300 osservazioni** per IC affidabile (potere ridotto ~0.60)
- Ottimale **800+ osservazioni** per potere 0.80
- Con 50 segnali/giorno: 16 giorni per IC intraday, 6 giorni per IC swing

---

### 1.3 Drift Detection: KS Test vs Alternative

**Conflitto:** La spec propone KS test con p < 0.05.

**Consenso multi-modello:** KS test ha limiti significativi:
- Sensibile al centro distribuzione, non alle code
- Falsi positivi con regime shift
- Non direzionale

**Metrica raccomandata (qwen3.5, gemma4, opus):**

| Metrica | Soglia Gialla | Soglia Rossa | Implementazione |
|---------|---------------|--------------|-----------------|
| **PSI** | 0.10 | 0.25 | Population Stability Index |
| **CUSUM** | 4.0 | 5.0 | Sequential drift detection |
| **JSD** | 0.08 | 0.15 | Jensen-Shannon Divergence |

```python
def drift_alert(baseline, recent, regime):
    psi = calculate_psi(baseline, recent)
    cusum_triggered = cusum_detector(recent)
    
    if psi > 0.25:
        return True, "PSI_severo"
    elif psi > 0.10 and cusum_triggered:
        return True, "PSI_moderato_confermato"
    elif cusum_triggered and len(recent) >= 20:
        return True, "CUSUM_sostenuto"
    
    return False, "nessun_drift"
```

---

### 1.4 Ensemble Weighting: Chicken-and-Egg Bias

**Conflitto:** La spec propone `compute_new_weights()` semplice. Deepseek e opus identificano bias intrinseco.

**Problema:** Modello con peso alto → influenza più segnale ensemble → più trade nel suo direction → IC misurato distorto verso l'alto.

**Soluzione (deepseek):** Leave-one-out IC

```python
def compute_purified_ic(model_signals, forward_returns, ensemble_weights):
    """Per ogni modello, calcola IC usando ensemble che LO ESCLUDE."""
    purified_ic = {}
    
    for target_model in model_signals:
        other_models = [m for m in model_signals if m != target_model]
        # Calcola segnale leave-one-out
        loo_signals = [
            sum(model_signals[m][i] * ensemble_weights[m] for m in other_models)
            for i in range(len(model_signals[target_model]))
        ]
        purified_ic[target_model] = spearmanr(loo_signals, forward_returns)[0]
    
    return purified_ic
```

---

### 1.5 Post-Mortem: Soglia di Attivazione

**Conflitto:** La spec attiva su ogni stop-loss hit (2%). Con 50 trade/giorno → 10-20 post-mortem/giorno.

**Risoluzione (minimax, qwen3.5):** Soglia dinamica

```python
def should_trigger_post_mortem(loss_pct, signal_score, ensemble_std):
    # Base: 3% (1.5× stop-loss)
    if loss_pct > 0.03:
        return True
    
    # Alta confidence o alta divergenza → post-mortem obbligatorio
    if loss_pct > 0.02 and (signal_score > 0.5 or ensemble_std > 0.3):
        return True
    
    # Loss molto grande
    if loss_pct > 0.05:
        return True
    
    return False
```

---

## 2. Dipendenze Cross-File

### 2.1 Performance Worker → Sentiment Signals Schema (File 06)

**Dipendenza:** Performance Worker richiede:
- `confidence` campo per weighted IC
- `ensemble_std` per divergence detection
- `source_ids` per news staleness calculation

**Stato:** File 06 include già questi campi. ✅ Risolta.

---

### 2.2 Performance Worker → Risk Parameters (File 02)

**Dipendenza:** Post-mortem classification richiede:
- Stop-loss threshold (2% intraday, 5% swing)
- Drawdown threshold per circuit breaker

**Stato:** File 02 fornisce parametri. Performance Worker deve importarli.

**Azione:** Creare `config/performance.yaml` con riferimenti a parametri risk.

---

### 2.3 Performance Worker → A/B Test (File 04)

**Dipendenza:** Threshold optimizer usa stessa metodologia A/B test di File 04.

**Stato:** File 04 designa A/B test framework. Performance Worker è consumer.

**Azione:** Condividere codice A/B test tra i due moduli.

---

## 3. Priorità di Implementazione

### BLOCCANTI (pre-implementazione)

| # | Raccomandazione | Modello | Impatto |
|---|-----------------|---------|---------|
| **B1** | Minimo 300 campioni per IC significativo | glm-5.1, opus | Evita update su rumore statistico |
| **B2** | PSI + CUSUM invece di KS-only per drift | qwen3.5, gemma | Riduce falsi positivi 40% |
| **B3** | Leave-one-out IC per ensemble weighting | deepseek | Corregge chicken-and-egg bias |
| **B4** | Confidence Calibration Tracker | qwen3-coder | Rileva miscalibrazione confidence |
| **B5** | Soglia post-mortem 3% (non 2%) | minimax | Riduce overload 60% |

---

### IMPORTANTI (Fase 1)

| # | Raccomandazione | Modello | Impatto |
|---|-----------------|---------|---------|
| **I1** | IC composito (Spearman + weighted hit rate + Brier) | opus | Metrica più robusta |
| **I2** | Smoothing α=0.25 per weight update | opus, devstral | Previene oscillazioni |
| **I3** | Max daily change 10% per pesi | opus | Smooth adaptation |
| **I4** | Baseline 90 giorni (non 6 mesi) | qwen3.5 | Baseline coerente con regime |
| **I5** | Regime-aware thresholds | qwen3.5 | Soglie diverse per bull/bear/high_vol |
| **I6** | Post-mortem 10 categorie | minimax | Classificazione granulare |
| **I7** | Circuit breaker per auto-update | deepseek | Freeze su VIX spike, flash crash |
| **I8** | A/B test 14 giorni per threshold | qwen3.5 | Validazione statistica |
| **I9** | Fallback hybrid rule-based + price action | gemma | Quando LLM sono in drift |
| **I10** | PI controller per stabilità | qwen3-coder | Evita comportamento caotico |

---

### NICE-TO-HAVE (Fase 2+)

| # | Raccomandazione | Modello | Impatto |
|---|-----------------|---------|---------|
| **N1** | Reasoning quality feedback (LLM-as-judge) | opus | Debug prompt degradation |
| **N2** | Feature decay monitor con CUSUM | qwen3.5 | Rileva perdita potere predittivo |
| **N3** | Cross-model correlation matrix | deepseek | Monitora diversificazione |
| **N4** | News freshness score | gemma | Degrada peso segnali vecchi |
| **N5** | Lyapunov exponent monitoring | deepseek | Rileva caos nel feedback loop |

---

## 4. Domande Aperte Residue

### Q1: Frequenza Update Pesi

**Problema:** Giornaliera (spec) vs settimanale (modelli).

**Raccomandazione multi-modello:** **Settimanale** (lunedì mattina)
- Riduce overfitting a rumore settimanale
- Permette accumulo 100+ segnali per update
- Allinea con reporting settimanale

---

### Q2: Min/Max Weight

**Problema:** Spec propone 15%-60%. Modelli raccomandano adjustment.

**Raccomandazione:** **10%-70%**
- Floor 10%: permette quasi-esclusione modelli degradati
- Cap 70%: evita concentrazione eccessiva

---

### Q3: Baseline per Drift Detection

**Problema:** 6 mesi (spec) include multipli regimi.

**Raccomandazione:** **90 giorni rolling** + baseline secondaria 12 mesi
- Baseline primaria: 90gg (un trimestre, regime coerente)
- Baseline secondaria: 12 mesi (confronto stagionale)
- Aggiornare baseline ogni 30gg con rolling window

---

### Q4: When to Disable Auto-Improvement

**Problema:** La spec non definisce circuit breaker.

**Raccomandazione (deepseek, qwen3.5):** Disabilitare se:
- VIX > 40 o VIX +30% in 1 giorno
- SPX gap > 5% all'open
- Volume > 5× media (panic trading)
- Earnings season (>50% portfolio ha earnings)
- Correlazione cross-asset > 0.9 (tutto correlato)
- Drawdown sistema > 5%

---

## 5. Raccomandazioni per Modello

### Opus
**Qualità:** ⭐⭐⭐⭐⭐  
**Contributi chiave:**
- IC composito con Brier Score
- Smoothing α=0.25, max delta 10%
- Leave-one-out IC per bias correction
- PI controller per stabilità

### Qwen3.5:cloud
**Qualità:** ⭐⭐⭐⭐⭐  
**Contributi chiave:**
- PSI + CUSUM per drift detection
- Baseline 90 giorni
- Regime-aware threshold optimizer
- A/B test design 14 giorni

### Qwen3-coder-next:cloud
**Qualità:** ⭐⭐⭐⭐⭐  
**Contributi chiave:**
- ConfidenceCalibrationTracker implementation
- PI controller code
- Post-mortem diagnostic hierarchy

### GLM-5.1:cloud
**Qualità:** ⭐⭐⭐⭐⭐  
**Contributi chiave:**
- Calcolo dimensionale n=784 per IC=0.10
- Newey-West correction per autocorrelazione
- Fisher z-transform per test significatività

### Gemma4:31b-cloud
**Qualità:** ⭐⭐⭐⭐  
**Contributi chiave:**
- JSD + PSI combined
- Hybrid rule-based fallback
- Fallback vs LLM quality monitoring

### Deepseek-v4-pro:cloud
**Qualità:** ⭐⭐⭐⭐⭐  
**Contributi chiave:**
- Chicken-and-egg bias analysis
- Inverse probability weighting
- Circuit breaker conditions
- Lyapunov exponent per caos

### Minimax-m2.1:cloud
**Qualità:** ⭐⭐⭐⭐  
**Contributi chiave:**
- 10 categorie post-mortem
- Rule-based classification hierarchy
- Pattern mining su post-mortem accumulati

### Devstral-2:123b-cloud
**Qualità:** ⭐⭐⭐⭐  
**Contributi chiave:**
- Review architetturale completa
- MVP Fase 1 definition
- Roadmap 3-fasi

---

## 6. Piano di Implementazione Fase 1

### Settimane 1-2: Metrics Foundation

- [ ] Implementare `compute_daily_ic()` con Spearman
- [ ] Implementare `calculate_psi()` per drift detection
- [ ] Logging strutturato segnali + forward returns
- [ ] Dashboard monitoring (IC, hit rate, PSI)

### Settimane 3-4: Post-Mortem + Report

- [ ] Implementare `diagnose_loss()` con 10 categorie
- [ ] Post-mortem per perdite > 3%
- [ ] Report settimanale (NO auto-update)
- [ ] Confidence calibration tracking

### Settimane 5-6: Weight Adjuster (Manual)

- [ ] Implementare `compute_new_weights()` con smoothing
- [ ] Report raccomandazioni pesi (review umana)
- [ ] Leave-one-out IC per bias correction
- [ ] Circuit breaker logic

### Settimane 7-8: Threshold Optimizer

- [ ] Implementare regime-aware bucket analysis
- [ ] A/B test framework per threshold
- [ ] Dashboard threshold performance

### Settimane 9-12: Automazione (Fase 2)

- [ ] Auto-weight update (con guardrail stretti)
- [ ] CUSUM drift detection
- [ ] Fallback hybrid activation
- [ ] PI controller tuning

---

## 7. Stima Complessiva

| Metrica | Valore |
|---------|--------|
| **Settimane stimate (Fase 1)** | 8 |
| **Funzioni critiche** | 5 (IC, PSI, post-mortem, weights, threshold) |
| **Test minimi** | 30 |
| **Campioni per IC affidabile** | 300+ |
| **Baseline per drift** | 90 giorni |
| **Post-mortem categorie** | 10 |

---

## 8. Raccomandazione Finale

**Verdetto: Il design proposto è SOVRA-INGEGNERIZZATO per Fase 1.**

**MVP Fase 1 (8 settimane):**

| Componente | Implementazione | Auto-update? |
|------------|-----------------|--------------|
| **IC Calculator** | Spearman + weighted hit rate | ❌ No |
| **Drift Detection** | PSI + CUSUM | ❌ No (solo alert) |
| **Post-Mortem** | 10 categorie, soglia 3% | ✅ Sì (automatico) |
| **Weight Adjuster** | Report settimanale | ❌ No (review umana) |
| **Threshold Optimizer** | Bucket analysis passiva | ❌ No |
| **Confidence Calibration** | Brier Score tracking | ❌ No |

**Roadmap raccomandata:**

```
Fase 1 (Settimane 1-8): Modalità "Osservativo"
├── Calcola IC, PSI, post-mortem
├── Genera report settimanale
├── NESSUN auto-update pesi
└── Review umana raccomandaioni

Fase 2 (Settimane 9-16): Auto-Update Limitato
├── Auto-weight update (max 5%/giorno)
├── Circuit breaker attivi
├── A/B test threshold
└── Fallback activation

Fase 3 (Settimane 17+): Full Automation
├── PI controller
├── Regime-aware weights
├── Continuous optimization
└── LLM-as-judge per reasoning
```

**Raccomandazione chiave:** Iniziare con **30-60 giorni di modalità osservativa** prima di qualsiasi auto-update. Questo permette di:
- Calibrare guardrail su dati reali
- Comprendere distribuzione naturale IC
- Identificare regime corrente
- Costruire baseline per drift detection

---

*Documento di sintesi generato da analisi multi-modello ricorsiva*  
**Modelli:** opus, qwen3.5:cloud, qwen3-coder-next:cloud, glm-5.1:cloud, gemma4:31b-cloud, deepseek-v4-pro:cloud, minimax-m2.1:cloud, devstral-2:123b-cloud  
**Data:** 2026-05-03
