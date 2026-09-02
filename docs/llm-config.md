# Configurazione LLM Ensemble

## Selezione della coppia (meccanismo)

La coppia ensemble NON è hardcoded: è selezionata dalla chiave Redis
`config:sentiment_llm_models` (settabile da UI/operatore), con fallback all'env
`SENTIMENT_LLM_MODELS`, poi `"all"`. Il registry dei modelli disponibili è
`src/llm/model_registry.py`: i candidati per swap (`qwen35`, `gptoss`) hanno
`in_all=False`, quindi la selezione `"all"` resta il set live a 2 modelli e
registrare un candidato non allarga silenziosamente l'ensemble.

## Modelli attivi in produzione (2026-07-11)

| Modello | Provider | Uso | Note |
|---------|----------|-----|------|
| FinBERT | HuggingFace (locale) | Fallback su divergenza/timeout/budget | int8 quantized, ~50% RAM vs baseline |
| GLM-5.2 | Ollama (cloud) | Sentiment ensemble | Flagship Zhipu AI; Stage 1: accuracy 0.47, 2.8s |
| GPT-OSS 20B | Ollama (cloud) | Sentiment ensemble | Open-weight, unico vendor non cinese; Stage 1: accuracy 0.41, 0 parse-fail, 8.7s |

## Modelli rimossi / sostituiti

| Modello | Data | Motivo |
|---------|----------------|--------|
| DeepSeek-V4-Pro | 2026-06-16 | OOM + latency eccessiva su hardware locale (resta candidato 3° modello via cloud) |
| GLM-5.1 | 2026-06-16 | IC inferiore a Kimi K2.6 in A/B test |
| Qwen3.5 | 2026-06-29 | Ticker extraction troppo aggressiva (es. MU da notizia macro Iran/US); sostituito da GLM-5.2 |
| Kimi K2.6 | 2026-07-11 | Disaccordo direzionale sistematico con GLM-5.2 (fallback 75-80%); Stage 1: peggior accuracy (0.29) e 29s di latenza; sostituito da GPT-OSS 20B |

## Formula segnale

```
score = polarity × confidence
```
- `polarity` ∈ [-1, +1]: direzione sentiment
- `confidence` ∈ [0, 1]: certezza del modello

Il prodotto scala correttamente il segnale direzionale per la certezza del modello. Alta certezza + bassa direzione → piccolo score (corretto); alta direzione + bassa certezza → piccolo score (corretto).

## Fallback chain

```
Ollama (coppia attiva da config:sentiment_llm_models, async ensemble)
    ↓ timeout o errore
FinBERT locale (via run_in_executor)
    ↓ timeout o errore
fallback_used=True, score=0.0 (decisione: NO-ORDER)
```

Divergenza ensemble: se `std(scores) > 0.40` (config.ENSEMBLE_DIVERGENCE_STD, alzato da 0.30 il 2026-07-09) → scarta ensemble, usa FinBERT come arbitro. Dal 2026-07-11 i raw output divergenti vengono comunque persistiti in `llm_responses` con `eligible=false` per l'audit (prima venivano scartati). Nota misurata (2026-07-11): l'aumento di soglia 0.30→0.40 NON ha ridotto il fallback rate — il disaccordo tra modelli è direzionale/bimodale; la leva efficace è la scelta della coppia, non la soglia.

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
| `worker` | 4 | `celery` | ingestion (`run-news-ingestion`, `run-alpaca-ingestion`), performance (`forward-return-worker`, `reconcile-fills-*`, `reconcile-positions-eod`, `performance-daily/weekly`, `drift-detection`, `check-suggestion-expiry`, `loss-feedback-check`, `shadow-comparison-report`, `counterfactual-worker`), `run-retention-sweep`, `portfolio-cycle`, `run-execution`, `decay-monitor`, `risk-monitor`, `held-news-loss-alert`, mobile (`mobile-monitor-snapshot`, `mobile-alert-evaluation`) |
| `worker-inference` | 1 | `inference` | `sentiment-worker`, `regime-detector` (+ `regime-detector-premarket`), `poll-telegram-updates` |

> **Corretto il 2026-09-02** contro `src/workers/celery_app.py`: la tabella precedente
> assegnava `pead-ingestion` a `worker-inference` (task ritirato col resto di S7 il
> 2026-07-15, vedi la sezione in fondo a questo file) e metteva `telegram-poller` sulla coda
> `celery`, mentre gira sulla coda `inference` — e' li' apposta, perche' con concurrency=1
> un solo processo fa polling e la tastiera di approvazione non si sdoppia.

Il `worker-inference` ha concurrency=1 per garantire un singolo processo Python con una singola istanza FinBERT in memoria. Con concurrency>1, ogni subprocess fork allocava una copia completa del modello causando OOM.

## TTL e limiti

- **Task time limit**: 660s (11 min) — accomoda 4 articoli × 90s Ollama + 43s FinBERT warmup + margine
- **Task soft limit**: 600s (10 min) — raise SoftTimeLimitExceeded, worker può cleanup
- **Budget giornaliero**: controllato da `LLMBudgetTracker` — ledger su PostgreSQL (`llm_budget`) + flag Redis `budget_exhausted` (non esiste una chiave `llm:budget:{MODEL}:{DATE}`)
- **TTL segnale Redis**: 4h — segnali più vecchi ignorati dall'execution engine

## S7 PEAD (classificazione 8-K) — RIMOSSA il 2026-07-15

> **Questa sezione è storica.** S7 è stata rimossa dal repo il 2026-07-15 (edge ALPHA-A3
> confutato, POC-2 FAIL): strategia, worker, route API, task del beat e config sono stati
> eliminati. Un test di guardia (`tests/test_p0_13_strategy_containment.py`) impedisce la
> re-introduzione accidentale. Storia completa: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`.
> Quanto segue descrive com'era configurata quando esisteva.

S7 usava Ollama separatamente dal pipeline sentiment principale. Prompt DK-CoT specializzato per earnings surprise detection:

1. Ruolo: "Act as a financial analyst specializing in earnings reports"
2. Reasoning: estrai EPS atteso vs riportato, guidance direction, management tone
3. Output JSON: `{direction, confidence, category, reasoning}`

Vedi `docs/strategies/s7-pead.md` per la documentazione completa.
