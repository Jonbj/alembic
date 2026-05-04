# Prompt 7 — Performance Worker: Feedback Loop e Auto-Miglioramento

## Contesto del sistema

Sistema di trading algoritmico multi-asset basato su LLM. Il sistema genera segnali di sentiment tramite un ensemble di 3 modelli LLM (`opus`, `qwen3.5:cloud`, `deepseek-v4-pro:cloud`) con Consensus Gate aggregation. I segnali vengono consumati da QuantConnect Lean per decisioni di trading automatico.

**Il problema che questo componente risolve:** il sistema produce segnali ma non ha mai saputo se erano corretti. Ogni segnale generato — `score=-0.72` su AAPL — viene usato per decidere se entrare o uscire da una posizione, ma nessuno misura se quel -0.72 ha poi predetto correttamente il comportamento del prezzo nelle ore successive. Senza questo loop di feedback, il sistema non impara, non rileva il degrado dei modelli, e non può ottimizzare i propri parametri nel tempo.

**Il componente proposto: Performance Worker** — un 4° Celery worker giornaliero che:
1. Confronta ogni segnale generato con il rendimento effettivo dell'asset nelle ore successive
2. Calcola l'Information Coefficient (IC) per modello, simbolo, regime
3. Aggiusta automaticamente (con guardrail) i pesi dei 3 modelli nell'ensemble
4. Rileva drift nella distribuzione degli output dei modelli
5. Genera post-mortem automatici per ogni perdita superiore allo stop-loss
6. Suggerisce ottimizzazioni sulla soglia di entry (`sentiment_score > 0.3`)

**Schema output dei segnali (già esistente, prodotto dal SentimentWorker):**
```python
class SentimentResult(BaseModel):
    symbol: str
    polarity: float              # [-1.0, +1.0]
    confidence: float            # [0.0, 1.0]
    score: float                 # polarity × confidence
    reasoning: str
    source_ids: list[str]
    generated_at: datetime
    model_id: str                # "ensemble:opus+qwen3.5+deepseek"
    worker_version: str
    fallback_used: bool
    worker_type: Literal["ensemble_llm", "single_llm", "finbert"]
```

**Schema audit log (già esistente, prodotto da QC per ogni ordine):**
```sql
audit_log: id, timestamp, action, symbol, quantity, price,
           signal_score, signal_id → sentiment_signals(id),
           guardrail, approved_by, reason
```

**Design proposto nella spec (da rivedere/migliorare):**

```python
class PerformanceReport(BaseModel):
    period_start: date
    period_end: date
    overall_ic: float
    icir: float                          # IC / std(IC) — stabilità del segnale
    hit_rate: float
    model_ic: dict[str, float]           # IC per modello
    model_icir: dict[str, float]
    recommended_weights: dict[str, float]
    weight_change_applied: bool
    threshold_analysis: dict[str, float] # IC per bucket di score
    threshold_suggestion: float | None
    drift_alerts: list[str]
    post_mortems: list[PostMortem]

class PostMortem(BaseModel):
    trade_id: UUID
    symbol: str
    loss_pct: float
    signal_score: float
    signal_confidence: float
    ensemble_std: float
    regime_at_trade: str
    reasoning_summary: str
    diagnosis: str
    # diagnosis ∈ ["low_confidence_passed", "ensemble_divergence_ignored",
    #               "regime_mismatch", "news_staleness", "market_gap", "unknown"]
```

**Ensemble weight update rule (da rivedere):**
```python
def compute_new_weights(model_icir: dict[str, float]) -> dict[str, float]:
    raw = {m: max(0.0, icir) for m, icir in model_icir.items()}
    total = sum(raw.values()) or 1.0
    weights = {m: v / total for m, v in raw.items()}
    # Guardrail: peso min 15%, max 60%
    weights = {m: max(0.15, min(0.60, w)) for m, w in weights.items()}
    total = sum(weights.values())
    return {m: w / total for m, w in weights.items()}

# Auto-apply se: N_trades >= 50, delta_peso <= 20%, ICIR_overall > 0.1
```

**Nuove tabelle PostgreSQL proposte:**
```sql
CREATE TABLE performance_metrics (
    id UUID PRIMARY KEY, period_start DATE, period_end DATE,
    model_id VARCHAR(100), symbol VARCHAR(20), regime regime_label_enum,
    ic FLOAT, icir FLOAT, hit_rate FLOAT, sample_count INTEGER,
    computed_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE model_weights (
    id UUID PRIMARY KEY, effective_from TIMESTAMPTZ,
    model_id VARCHAR(100), weight FLOAT, icir_basis FLOAT,
    auto_applied BOOLEAN, approved_by VARCHAR(50), notes TEXT
);
```

---

## Il tuo compito

Sei un quantitative researcher con esperienza in sistemi di machine learning per trading e in feedback loop adattativi. Analizza il design proposto e rispondi alle domande seguenti.

### Parte A — Validazione del design IC

1. **IC come metrica primaria:** l'Information Coefficient (correlazione di Spearman tra score previsto e rendimento effettivo) è la metrica giusta per misurare la qualità di un segnale di sentiment? Quali sono i suoi limiti in questo contesto specifico?

2. **Finestre di misurazione:** la spec propone finestre di 4h (intraday), 24h (swing 4h), 72h (swing 1D). Sono appropriate? Considera che il worker gira ogni 15 minuti e i segnali si sovrappongono temporalmente.

3. **Problema di autocorrelazione:** i rendimenti consecutivi (4h, 24h) sono correlati tra loro. Come impatta questo sulla significatività statistica dell'IC? Quale correzione applicare?

4. **Minimo campioni:** il design richiede 30 segnali per intraday, 20 per swing. Sono sufficienti per un IC statisticamente affidabile? Calcola il numero di osservazioni necessarie per un IC di 0.10 con potere statistico 0.80 e α=0.05.

5. **ICIR come misura di stabilità:** il design usa `ICIR = IC_mean / IC_std` per l'aggiornamento dei pesi. È preferibile all'IC grezzo? Quali sono i casi in cui ICIR è fuorviante?

### Parte B — Validazione dell'ensemble weight adjuster

1. **Il meccanismo proposto è corretto?** Analizza la funzione `compute_new_weights` — ci sono casi in cui produrrebbe risultati indesiderati? (es. tutti i modelli con ICIR negativo, un modello con ICIR molto superiore agli altri)

2. **Frequenza di aggiornamento:** i pesi vengono aggiornati giornalmente su finestra rolling 30 giorni. È troppo frequente (rischio overfitting ai dati recenti) o troppo raro (sistema lento ad adattarsi)? Proponi frequenza e finestra ottimali.

3. **Problema di non-stazionarietà:** il mercato cambia regime. Un modello che performa bene in bull market può performare male in bear market. Come evitare che il sistema penalizzi un modello che è semplicemente in un regime sfavorevole?

4. **Guardrail peso 15%–60%:** sono i range giusti? Quali sono le conseguenze di un peso floor troppo alto (15%) e di un floor troppo basso (5%)?

5. **Chicken-and-egg problem:** se `opus` ha peso 42% e `qwen3.5` ha peso 33%, il modello con peso più alto influenza più il segnale finale → influenza più i trade → influenza più il forward return misurato → influenza più il proprio IC. Il sistema misura l'IC correttamente o c'è un bias intrinseco?

### Parte C — Validazione drift detection

1. **KS test per drift:** il design usa Kolmogorov-Smirnov test con `p-value < 0.05` come soglia. È appropriato per questo use case? Quali alternative consideri (Population Stability Index, Jensen-Shannon divergence, CUSUM)?

2. **Falsi positivi:** il mercato stesso cambia distribuzione (regime shift) e questo può far scattare il drift alert anche se il modello funziona correttamente. Come distinguere "drift del modello" da "risposta corretta del modello a un cambio di mercato"?

3. **Finestra baseline:** la spec usa 6 mesi di storico come baseline. È sufficiente? Troppo lungo rischia di includere più regimi di mercato (rende la baseline eterogenea).

### Parte D — Validazione post-mortem automatico

1. **Classificazione diagnosi:** la spec propone 6 categorie di diagnosi per le perdite:
   - `low_confidence_passed`: segnale con confidence < soglia è passato comunque
   - `ensemble_divergence_ignored`: std ensemble era alta ma il segnale è stato usato
   - `regime_mismatch`: regime rilevato incompatibile con la direzione del segnale
   - `news_staleness`: notizia già vecchia al momento dell'uso
   - `market_gap`: evento imprevedibile (earnings gap, news flash)
   - `unknown`: nessuna causa identificabile
   
   Questa classificazione è completa? Mancano categorie importanti? Come automatizzeresti l'assegnazione (rule-based vs ML)?

2. **Utilità operativa:** come useresti i post-mortem accumulati nel tempo per migliorare il sistema? Quali pattern emergerebbero dopo 100 post-mortem?

3. **Soglia di attivazione:** il post-mortem si attiva su ogni stop-loss hit. Con stop-loss al 2% e 50 trade/giorno (stima), questo potrebbe generare molti post-mortem in periodi volatili. Quale soglia è più appropriata?

### Parte E — Threshold Optimizer

1. **Bucket analysis:** la spec divide i segnali in 5 bucket di score: `[0.1–0.2)`, `[0.2–0.3)`, `[0.3–0.4)`, `[0.4–0.6)`, `[0.6–1.0]`. È la discretizzazione giusta? Come eviti che bucket con pochi campioni producano IC falsi?

2. **A/B test della nuova soglia:** la spec richiede 2 settimane di A/B test prima di applicare una nuova soglia. Come struttureresti questo test? Come gestisci il fatto che durante il test metà dei trade usano la vecchia soglia e metà la nuova?

3. **Interazione con il regime:** la soglia ottimale potrebbe essere diversa per regime `risk_on` vs `high_vol`. Il threshold optimizer dovrebbe essere regime-aware?

### Parte F — Componenti mancanti

Analizza il design e identifica:

1. **Cosa manca completamente** che consideri essenziale per un feedback loop efficace (es. feedback sulla qualità del reasoning LLM, feedback sulla calibrazione della confidence, feedback sulla freshness delle notizie)

2. **Rischi di instabilità del sistema:** un feedback loop mal progettato può creare oscillazioni o comportamenti caotici. Identifica i punti di instabilità nel design proposto e come mitigarli.

3. **Latenza del feedback:** il ciclo è giornaliero. In mercati veloci, 24h di lag per aggiustare i pesi è troppo lento? Quando avrebbe senso un ciclo intra-day?

4. **Quando disattivare l'auto-miglioramento:** ci sono condizioni di mercato in cui il Performance Worker dovrebbe smettere di aggiornare i pesi (es. durante un flash crash, durante earnings season ad alto volume)?

---

## Formato risposta atteso

1. Analisi IC con metrica alternativa consigliata se necessario + calcolo dimensione campionaria (Parte A)
2. Correzioni alla funzione `compute_new_weights` con pseudocodice migliorato (Parte B)
3. Raccomandazione drift detection con metrica preferita e soglia (Parte C)
4. Schema diagnosi post-mortem migliorato con algoritmo di classificazione (Parte D)
5. Design threshold optimizer regime-aware (Parte E)
6. Lista componenti mancanti prioritizzati + analisi rischi instabilità (Parte F)
7. **Raccomandazione finale:** il design proposto è implementabile in Fase 1 (backtest/paper) o è sovra-ingegnerizzato? Quale sottoinsieme minimo è necessario per avere un feedback loop utile fin da subito?
