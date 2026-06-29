# Configurazione LLM Ensemble

## Modelli attivi in produzione (2026-06-29)

| Modello | Provider | Uso | Note |
|---------|----------|-----|------|
| FinBERT | HuggingFace (locale) | Sentiment primario / fallback | int8 quantized, ~50% RAM vs baseline |
| Kimi K2.6 | Ollama (cloud) | Sentiment ensemble principale | Conservativo, ben calibrato su macro |
| GLM-5.2 | Ollama (cloud) | Sentiment ensemble principale | Flagship Zhipu AI, long-horizon reasoning |

## Modelli rimossi

| Modello | Data rimozione | Motivo |
|---------|----------------|--------|
| DeepSeek-V4-Pro | 2026-06-16 | OOM + latency eccessiva su hardware locale |
| GLM-5.1 | 2026-06-16 | IC inferiore a Kimi K2.6 in A/B test |
| Qwen3.5 | 2026-06-29 | Ticker extraction troppo aggressiva (es. MU da notizia macro Iran/US); sostituito da GLM-5.2 |

## Formula segnale

```
score = polarity × confidence
```
- `polarity` ∈ [-1, +1]: direzione sentiment
- `confidence` ∈ [0, 1]: certezza del modello

Il prodotto scala correttamente il segnale direzionale per la certezza del modello. Alta certezza + bassa direzione → piccolo score (corretto); alta direzione + bassa certezza → piccolo score (corretto).

## Fallback chain

```
Ollama (Kimi K2.6 + GLM-5.2, async ensemble)
    ↓ timeout o errore
FinBERT locale (via run_in_executor)
    ↓ timeout o errore
fallback_used=True, score=0.0 (decisione: NO-ORDER)
```

Divergenza ensemble: se `std(scores) > 0.30` → scarta ensemble, usa FinBERT come arbitro.

## FinBERT — Confidence formula

FinBERT usa **entropic confidence** (non il max softmax):
```
confidence = 1 - H(p) / log(3)
```
dove `H(p)` è l'entropia di Shannon della distribuzione a 3 classi (positive/negative/neutral).
Una distribuzione peaked (es. [0.9, 0.05, 0.05]) → alta confidence.
Una distribuzione piatta (es. [0.35, 0.33, 0.32]) → confidence ≈ 0.

## FinBERT int8 quantization

Applicata al caricamento del modello in `src/llm/finbert.py`:
```python
torch.quantization.quantize_dynamic(
    self._pipe.model, {nn.Linear}, dtype=torch.qint8, inplace=True
)
```
Riduce il footprint RAM di ~50% con perdita trascurabile di accuratezza sul task di sentiment classification a 3 classi.

## Configurazione worker

| Worker | Concurrency | Queue | Task assegnati |
|--------|-------------|-------|----------------|
| `worker` | 4 | `celery` | ingestion, performance, retention, portfolio-cycle, execution, telegram-poller |
| `worker-inference` | 1 | `inference` | sentiment-worker, regime-detector, pead-ingestion |

Il `worker-inference` ha concurrency=1 per garantire un singolo processo Python con una singola istanza FinBERT in memoria. Con concurrency>1, ogni subprocess fork allocava una copia completa del modello causando OOM.

## TTL e limiti

- **Task time limit**: 660s (11 min) — accomoda 4 articoli × 90s Ollama + 43s FinBERT warmup + margine
- **Task soft limit**: 600s (10 min) — raise SoftTimeLimitExceeded, worker può cleanup
- **Budget giornaliero**: controllato da `LLMBudgetTracker` via Redis key `llm:budget:{MODEL}:{DATE}`
- **TTL segnale Redis**: 4h — segnali più vecchi ignorati dall'execution engine

## S7 PEAD (classificazione 8-K)

S7 usa Ollama separatamente dal pipeline sentiment principale. Prompt DK-CoT specializzato per earnings surprise detection:

1. Ruolo: "Act as a financial analyst specializing in earnings reports"
2. Reasoning: estrai EPS atteso vs riportato, guidance direction, management tone
3. Output JSON: `{direction, confidence, category, reasoning}`

Vedi `docs/strategies/s7-pead.md` per la documentazione completa.
