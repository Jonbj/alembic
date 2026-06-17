# Prompt 1 — Valutazione e Scrittura Prompt DK-CoT per Sentiment Worker

## Contesto del sistema

Stai analizzando il componente centrale di un sistema di trading algoritmico multi-asset basato su LLM. Il sistema segue il paradigma "Alpha Miner": i modelli linguistici operano **offline**, generando segnali di sentiment pre-calcolati che vengono consumati da QuantConnect Lean (execution engine) senza mai chiamare l'LLM nel loop critico di esecuzione.

Il **Sentiment Worker** è un Celery task schedulato ogni 15 minuti che:
1. Riceve in input un batch di fino a 10 notizie finanziarie (già sanitizzate: Unicode NFKC, HTML stripped, omoglifi normalizzati)
2. Invia il batch a un LLM cloud (Claude Sonnet / GPT-4o / Gemini Pro) in una singola chiamata
3. Riceve output strutturato (JSON) per ogni notizia
4. Calcola `score = polarity × confidence` per ogni notizia
5. Scrive i risultati nel Signal Store (Redis hot cache + PostgreSQL audit)

**Schema output atteso (Pydantic):**
```python
class SentimentResult(BaseModel):
    symbol: str                 # ticker azionario (es. "AAPL", "BTC-USD")
    polarity: float             # [-1.0, +1.0] negativo → positivo
    confidence: float           # [0.0, 1.0] certezza del modello
    score: float                # polarity × confidence → range [-1.0, +1.0]
    reasoning: str              # ragionamento intermedio step-by-step
    source_ids: list[str]       # id delle notizie analizzate
    generated_at: datetime
    model_id: str
    worker_version: str
```

**Struttura prompt attuale (solo scheletro, non testo reale):**
```
1. Role definition: "Sei un analista azionario buy-side esperto..."
2. Step-by-step reasoning su cash flow, competizione, profittabilità
3. Few-shot examples (2-3 casi analoghi con outcome noto)
4. Richiesta bull/bear case esplicito
5. Output forzato in JSON schema
```

**Vincoli critici:**
- Input può contenere notizie in inglese o tradotte automaticamente da italiano/tedesco/francese
- Le notizie riguardano asset multi-class: equity USA/EU, ETF, crypto, futures, forex
- Il sistema deve essere robusto a notizie avversariali scritte per manipolare il sentiment
- L'output DEVE essere parsabile via Pydantic senza fallback — errori di parsing costano un retry API

---

## Il tuo compito

### Parte A — Scrivi il prompt DK-CoT completo

Scrivi il testo completo del **system prompt** e del **user prompt** da usare nel Sentiment Worker. Il prompt deve:

1. Implementare il paradigma **Domain Knowledge Chain-of-Thought (DK-CoT)**: il modello deve ragionare esplicitamente su impatto sui flussi di cassa, posizione competitiva, e profittabilità dell'azienda prima di emettere il verdetto
2. Includere **2-3 esempi few-shot** realistici (notizie finanziarie con reasoning e output JSON atteso)
3. Forzare l'output in **JSON strutturato** compatibile con lo schema `SentimentResult` sopra
4. Gestire il caso in cui la notizia riguarda più simboli (es. una fusione M&A tra due aziende)
5. Gestire il caso di notizie macro (tassi Fed, inflazione) che impattano settori interi senza un singolo simbolo

### Parte B — Analisi critica del prompt

Analizza il prompt che hai scritto secondo questi assi:

1. **Robustezza semantica:** Il prompt può essere manipolato da una notizia scritta ad arte per ottenere un sentiment opposto a quello reale? Fornisci un esempio di attacco e come il prompt vi resiste (o non vi resiste)

2. **Calibrazione confidence:** Il modello tenderà a dare confidence alta sempre (overconfident) o a essere appropriatamente incerto? Cosa nel prompt promuove/penalizza la calibrazione?

3. **Consistenza cross-modello:** Se lo stesso prompt viene inviato a Claude, GPT-4o e Gemini, ci aspettiamo output coerenti? Dove potrebbero divergere significativamente?

4. **Costo token:** Stima il numero approssimativo di token input e output per una chiamata tipica con batch di 5 notizie. È ottimizzabile senza perdere qualità?

5. **Edge case non gestiti:** Elenca almeno 3 situazioni in cui il prompt produrrebbe output inaffidabile o non parsabile

### Parte C — Variante alternativa

Proponi una **variante alternativa** del prompt con un approccio diverso (es. prompt più breve e diretto vs. ragionamento esteso, oppure chain-of-thought per articolo singolo vs. analisi comparativa del batch). Confronta le due varianti su: qualità attesa, costo, robustezza.

---

## Formato risposta atteso

1. System prompt completo (testo pronto all'uso)
2. User prompt template con placeholder per le notizie del batch
3. Analisi critica strutturata (Parti B)
4. Prompt variante alternativo con confronto
5. **Raccomandazione finale:** quale usare in Fase 1 e perché
