# Prompt 5 — Mapping FinBERT Output → SentimentResult

## Contesto del sistema

Sistema di trading algoritmico con pipeline LLM. Il **Sentiment Worker** usa un LLM cloud come provider primario (Claude/GPT-4o/Gemini) e **FinBERT** come fallback locale.

**FinBERT** è un modello BERT fine-tuned su testi finanziari (ProsusAI/finbert su HuggingFace). Il suo output è un classificatore a **3 classi**:

```python
# Output nativo FinBERT (HuggingFace pipeline)
{
    "positive": 0.72,   # probabilità
    "negative": 0.18,
    "neutral":  0.10
}
# Somma sempre a 1.0
```

**Schema SentimentResult che il sistema si aspetta (da tutti i provider, LLM e fallback):**

```python
class SentimentResult(BaseModel):
    symbol: str
    polarity: float      # [-1.0, +1.0] negativo → positivo
    confidence: float    # [0.0, 1.0] certezza del modello
    score: float         # polarity × confidence → range [-1.0, +1.0]
    reasoning: str
    source_ids: list[str]
    generated_at: datetime
    model_id: str
    worker_version: str
```

**Il problema:** FinBERT produce 3 probabilità di classe, ma il sistema si aspetta `polarity` scalare continuo e `confidence` separata. Non esiste un mapping "ufficiale" — la scelta del mapping impatta direttamente la qualità del segnale in regime di fallback.

**Frequenza del fallback:** ogni volta che:
- `confidence < 0.4` dal LLM cloud
- Timeout LLM > 10 secondi
- 3 segnali scartati consecutivi (modalità degradata)
- Budget LLM giornaliero esaurito (fallback completo)

**Integrazione nel sistema:** il segnale FinBERT entra nello stesso Signal Store (Redis + PostgreSQL) e viene consumato da QuantConnect esattamente come un segnale LLM. La qualità del mapping determina direttamente le decisioni di trading in fase di fallback.

---

## Il tuo compito

Sei un NLP engineer con esperienza in modelli di sentiment analysis finanziaria e in sistemi di trading quantitativi. Analizza il problema di mapping e rispondi alle seguenti domande.

### Parte A — Analisi del problema di mapping

1. **Perché il mapping è non-triviale:** spiega perché non esiste un mapping "ovvio" da (positive, negative, neutral) a (polarity, confidence). Quali ambiguità esistono?

2. **Tre approcci di mapping possibili** — per ognuno, descrivi la formula matematica completa, le proprietà (simmetria, range, comportamento su casi limite) e i pro/contro:

   a. **Approccio 1:** mapping diretto `polarity = positive - negative`, `confidence = max(positive, negative, neutral)`
   
   b. **Approccio 2:** mapping che ignora neutral e normalizza su (positive + negative), usa neutral come "uncertainty deflator"
   
   c. **Approccio 3:** mapping basato su entropia — la confidence è inversamente proporzionale all'entropia della distribuzione

3. **Comportamento sul caso edge più critico:** come si comporta ognuno dei 3 approcci con questi input?
   ```
   Case 1: positive=0.34, negative=0.33, neutral=0.33  # massima incertezza
   Case 2: positive=0.50, negative=0.01, neutral=0.49  # positivo ma quasi tutto neutral
   Case 3: positive=0.80, negative=0.15, neutral=0.05  # segnale chiaro positivo
   Case 4: positive=0.40, negative=0.40, neutral=0.20  # segnale misto
   ```

### Parte B — Raccomandazione e implementazione

1. **Quale approccio raccomandi** e perché? Considera:
   - Coerenza con la soglia di scarto `confidence < 0.4` del sistema
   - Comportamento in alta incertezza (dovrebbe produrre confidence bassa → segnale scartato)
   - Simmetria del range [-1.0, +1.0] per polarity
   - Interpretabilità del risultato

2. **Implementa il mapping raccomandato** in Python:

```python
from transformers import pipeline
from datetime import datetime, timezone

# Disponibile nel codebase:
# class SentimentResult(BaseModel):
#     symbol, polarity, confidence, score, reasoning, source_ids, generated_at, model_id, worker_version

def finbert_to_sentiment_result(
    finbert_output: dict[str, float],  # {"positive": p, "negative": n, "neutral": u}
    symbol: str,
    source_ids: list[str],
) -> SentimentResult:
    """Implementa qui il mapping completo."""
    ...
```

Includi:
- Gestione input malformato (probabilità che non sommano a 1.0, valori negativi, chiavi mancanti)
- Generazione del campo `reasoning` sintetico (FinBERT non produce reasoning — cosa scrivi?)
- `model_id` appropriato per identificare che il segnale viene da FinBERT
- Garanzia che `score = polarity × confidence` (invariante del sistema)

3. **Test di unità:** scrivi almeno 5 test pytest per i casi edge identificati nella Parte A

### Parte C — Validazione empirica

1. **Come verificheresti** che il mapping scelto produce segnali di qualità comparabile ai segnali LLM cloud?
   - Quale metrica usi per confrontare (IC, distribuzione dei score, correlazione con rendimenti)?
   - Quanti campioni servono per una valutazione affidabile?

2. **Calibration check:** FinBERT tende a essere overconfident su certi tipi di testi finanziari. Come rileveresti e correggeresti un bias sistematico nel mapping?

3. **Degradation monitoring:** come monitoeresti in produzione se la qualità dei segnali FinBERT è "sufficientemente buona" o se sta degradando la performance della strategia?

### Parte D — Alternative a FinBERT

Il fallback attuale è FinBERT. Valuta queste alternative come possibili fallback locali (zero costo, CPU-only):

| Modello | Tipo output | Dimensione | Velocità |
|---|---|---|---|
| ProsusAI/finbert | 3 classi | ~440MB | ~50ms/batch |
| yiyanghkust/finbert-tone | 3 classi | ~440MB | ~50ms/batch |
| cardiffnlp/twitter-roberta-base-sentiment | 3 classi | ~500MB | ~50ms/batch |
| bag-of-words (Loughran-McDonald) | score continuo | <1MB | <1ms/batch |
| VADER (adattato finanza) | score continuo + componenti | <1MB | <1ms/batch |

Per ognuno:
1. È più o meno adatto di FinBERT come fallback per notizie finanziarie?
2. Il suo output si mappa più o meno naturalmente a `{polarity, confidence}`?
3. Raccomandazione: usarlo come fallback primario, secondario, o non usarlo?

---

## Formato risposta atteso

1. Analisi mapping con formule per tutti e 3 gli approcci + tabella comportamento sui 4 casi edge (Parte A)
2. Implementazione Python completa del mapping con test (Parte B)
3. Framework validazione empirica (Parte C) — max 200 parole
4. Tabella comparativa alternative fallback con raccomandazione finale (Parte D)
5. **Raccomandazione sintetica finale:** mapping consigliato + eventuali modifiche alla soglia `confidence < 0.4` per FinBERT vs LLM cloud
